"""
Squad 4x Assistant Bot – Responds to /ask <question> only
- Works in groups and private chats
- Shows typing animation, replies via Gemini
- Never mentions "Gemini"
"""

import os
import asyncio
import logging
import re

from telethon import TelegramClient, events
from telethon.tl.types import SendMessageTypingAction
import google.generativeai as genai

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ========== ENV ==========
API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
GROUP_ID = os.environ.get("GROUP_ID")
if GROUP_ID:
    GROUP_ID = int(GROUP_ID)
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
ALLOW_PRIVATE = os.environ.get("ALLOW_PRIVATE", "false").lower() == "true"

# ========== GEMINI ==========
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

async def ask_gemini(question: str) -> str:
    global _quota_exhausted
    if _quota_exhausted:
        return "Assistant service temporarily unavailable. Try again later."

    tried = 0
    total = len(_keys)
    while True:
        try:
            model = get_gemini_model()
            response = await asyncio.to_thread(model.generate_content, question)
            return response.text.strip()
        except Exception as e:
            err = str(e)
            if "429" in err or "quota" in err.lower() or "RESOURCE_EXHAUSTED" in err:
                tried += 1
                if not rotate_key():
                    _quota_exhausted = True
                    return "Assistant offline. Contact admin."
                continue
            log.error(f"Gemini error: {e}")
            return "Sorry, an error occurred."

# ========== BOT CLIENT ==========
bot = TelegramClient("assistant_bot", API_ID, API_HASH)

# ========== /ASK HANDLER ==========
@bot.on(events.NewMessage)
async def ask_handler(event):
    if event.out:
        return

    # Log every message for debugging
    log.info(f"Received message from {event.sender_id} in chat {event.chat_id}: {event.raw_text}")

    # Check if it's a group or private
    if event.is_group:
        if GROUP_ID and event.chat_id != GROUP_ID:
            log.info(f"Ignoring group {event.chat_id}, not my target group")
            return
    elif event.is_private:
        if not ALLOW_PRIVATE:
            log.info("Private messages not allowed (ALLOW_PRIVATE=false)")
            return
    else:
        return

    text = event.raw_text or ""
    # Match /ask or /ask@BotName followed by a space and some text
    match = re.match(r'^/ask(?:@\w+)?\s+(.+)', text, re.IGNORECASE)
    if not match:
        return

    question = match.group(1).strip()
    log.info(f"✅ /ask command detected. Question: {question[:100]}")

    # Typing animation
    async with bot.action(event.chat_id, SendMessageTypingAction()):
        await asyncio.sleep(2)
        answer = await ask_gemini(question)

    reply = f"🤖 *Squad 4x Assistant*:\n\n{answer}"
    await event.reply(reply, parse_mode="markdown")
    log.info("Reply sent.")

# ========== /START ==========
@bot.on(events.NewMessage(pattern='/start'))
async def start_cmd(event):
    await event.reply(
        "🤖 *Squad 4x Assistant Bot*\n\n"
        "Use `/ask <your question>` to get answers.\n"
        "Example: `/ask What is a Forex broker?`",
        parse_mode="markdown"
    )

# ========== MAIN ==========
async def main():
    await bot.start(bot_token=BOT_TOKEN)
    me = await bot.get_me()
    log.info(f"✅ Assistant Bot started: @{me.username}")
    if GROUP_ID:
        log.info(f"Listening to group ID: {GROUP_ID}")
    if ALLOW_PRIVATE:
        log.info("Also listening to private chats")
    else:
        log.info("Private chats disabled (set ALLOW_PRIVATE=true to enable)")
    await bot.run_until_disconnected()

if __name__ == "__main__":
    asyncio.run(main())
