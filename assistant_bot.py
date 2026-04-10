"""
Squad 4x Assistant Bot – Answers /ask commands only
- Responds to /ask <question> in groups or private
- Shows typing animation, then replies via Gemini
- Never reveals "Gemini", only "Squad 4x Assistant"
"""

import os
import asyncio
import logging
import re

from telethon import TelegramClient, events
from telethon.tl.types import SendMessageTypingAction
import google.generativeai as genai

# ========== LOGGING ==========
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ========== ENVIRONMENT VARIABLES ==========
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
GROUP_ID = int(os.environ["GROUP_ID"])               # The group where bot listens (optional, can be None)
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]

# Optional: allow the bot to answer in private chats as well (no need GROUP_ID)
# Set ALLOW_PRIVATE = True to enable
ALLOW_PRIVATE = os.environ.get("ALLOW_PRIVATE", "false").lower() == "true"

# ========== GEMINI SETUP ==========
# Support multiple keys (comma-separated) for rotation
_keys = [k.strip() for k in GEMINI_API_KEY.split(",") if k.strip()]
_current_key_index = 0
_quota_exhausted = False

def get_gemini_model():
    genai.configure(api_key=_keys[_current_key_index])
    return genai.GenerativeModel("gemini-2.0-flash")

def rotate_key():
    global _current_key_index, _quota_exhausted
    next_idx = (_current_key_index + 1) % len(_keys)
    if next_idx == 0 and len(_keys) == 1:
        _quota_exhausted = True
        return False
    _current_key_index = next_idx
    _quota_exhausted = False
    log.info("🔄 Switched to Gemini key #%s", _current_key_index+1)
    return True

# ========== TELEGRAM CLIENT ==========
bot = TelegramClient("assistant_bot", API_ID, API_HASH)

# ========== HELPER: ASK GEMINI ==========
async def ask_gemini(question: str) -> str:
    """Send question to Gemini, return answer or error message."""
    global _quota_exhausted
    if _quota_exhausted:
        return "I'm sorry, the assistant service is temporarily unavailable. Please try again later."

    tried = 0
    total = len(_keys)
    while True:
        try:
            model = get_gemini_model()
            response = await asyncio.to_thread(model.generate_content, question)
            answer = response.text.strip()
            return answer
        except Exception as e:
            err = str(e)
            if "429" in err or "quota" in err.lower() or "RESOURCE_EXHAUSTED" in err:
                tried += 1
                if not rotate_key():
                    _quota_exhausted = True
                    return "Assistant offline. Please contact group admin."
                continue
            log.warning(f"Gemini error: {e}")
            return "Sorry, I encountered an error while processing your request."

# ========== COMMAND HANDLER ==========
@bot.on(events.NewMessage)
async def ask_command_handler(event):
    # Ignore messages from the bot itself
    if event.out:
        return

    # Check if the message is in the allowed chat
    is_group = event.is_group
    is_private = event.is_private

    if is_group:
        # If GROUP_ID is set, only respond in that specific group
        if GROUP_ID and event.chat_id != GROUP_ID:
            return
    elif is_private:
        if not ALLOW_PRIVATE:
            return
    else:
        return

    text = event.raw_text or ""
    if not text:
        return

    # Check for /ask command (case-insensitive, can have bot mention)
    # Pattern: /ask@BotName question or /ask question
    match = re.match(r'^/ask(?:@\w+)?\s+(.+)', text, re.IGNORECASE)
    if not match:
        return

    question = match.group(1).strip()
    if not question:
        await event.reply("Please provide a question. Example: `/ask What is a broker?`")
        return

    log.info(f"📨 /ask command from {event.sender_id}: {question[:100]}")

    # Show typing animation
    async with bot.action(event.chat_id, SendMessageTypingAction()):
        await asyncio.sleep(2)   # Simulate thinking/typing
        answer = await ask_gemini(question)

    # Format answer professionally
    reply_text = f"🤖 *Squad 4x Assistant*:\n\n{answer}"

    # Send the reply
    await event.reply(reply_text, parse_mode="markdown")

    log.info(f"✅ Replied to /ask from {event.sender_id}")

# ========== START COMMAND (optional) ==========
@bot.on(events.NewMessage(pattern='/start'))
async def start_cmd(event):
    if event.out:
        return
    await event.reply(
        "🤖 *Squad 4x Assistant Bot*\n\n"
        "I answer your questions using AI. Simply use:\n"
        "`/ask <your question>`\n\n"
        "Example: `/ask What is a Forex broker?`\n\n"
        "I never reveal my AI provider – I'm just your group assistant.",
        parse_mode="markdown"
    )

# ========== MAIN ==========
async def main():
    await bot.start(bot_token=BOT_TOKEN)
    me = await bot.get_me()
    log.info(f"🤖 Assistant Bot started: @{me.username}")
    if GROUP_ID:
        log.info(f"Listening to group ID: {GROUP_ID}")
    if ALLOW_PRIVATE:
        log.info("Also listening to private chats")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
