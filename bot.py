import asyncio
import logging
import re
from typing import Optional, List

import aiohttp
from aiohttp_socks import ProxyConnector
from fake_useragent import UserAgent
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ------------------ Configuration ------------------
BOT_TOKEN = "YOUR_BOT_TOKEN"  # Set this as Railway env variable
MAX_CONCURRENT = 20            # Concurrent requests
VIEW_TIMEOUT = 15              # Seconds per request

# Conversation states
WAITING_FOR_LINK, WAITING_FOR_COUNT = range(2)

# ------------------ Proxy Scraper (from original repo) ------------------
class AutoScraper:
    def __init__(self):
        self.proxies = []

    async def fetch_proxies(self) -> List[str]:
        """Scrape proxies from all sources."""
        sources = []
        for fname in ["auto/http.txt", "auto/socks4.txt", "auto/socks5.txt"]:
            try:
                with open(fname, "r") as f:
                    sources.extend([line.strip() for line in f if line.strip()])
            except FileNotFoundError:
                logging.warning(f"Missing {fname}, skipping.")

        if not sources:
            return []

        async def fetch_one(url: str) -> List[str]:
            try:
                async with aiohttp.ClientSession() as sess:
                    async with sess.get(url, timeout=10) as resp:
                        text = await resp.text()
                        # Extract IP:PORT
                        ips = re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}\b", text)
                        return list(set(ips))
            except Exception:
                return []

        tasks = [fetch_one(url) for url in sources]
        results = await asyncio.gather(*tasks)
        all_proxies = []
        for res in results:
            all_proxies.extend(res)
        unique = list(set(all_proxies))
        logging.info(f"Scraped {len(unique)} proxies")
        return unique

# ------------------ View Booster (adapted from telegram-views) ------------------
class TelegramBooster:
    def __init__(self, channel: str, post_id: int, concurrency: int = MAX_CONCURRENT):
        self.channel = channel
        self.post_id = post_id
        self.concurrency = concurrency
        self.ua = UserAgent()

    async def _get_view_token(self, proxy: str, proxy_type: str) -> Optional[str]:
        url = f"https://t.me/{self.channel}/{self.post_id}?embed=1"
        headers = {"User-Agent": self.ua.random}
        connector = None
        if proxy:
            connector = ProxyConnector.from_url(f"{proxy_type}://{proxy}")
        try:
            async with aiohttp.ClientSession(connector=connector) as sess:
                async with sess.get(url, headers=headers, timeout=VIEW_TIMEOUT) as resp:
                    text = await resp.text()
                    match = re.search(r'window\.telegramEmbed="([^"]+)"', text)
                    return match.group(1) if match else None
        except Exception:
            return None

    async def _send_view(self, token: str, proxy: str, proxy_type: str) -> bool:
        url = "https://t.me/iv"
        headers = {
            "User-Agent": self.ua.random,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        data = f"token={token}&post_id={self.post_id}&channel={self.channel}"
        connector = None
        if proxy:
            connector = ProxyConnector.from_url(f"{proxy_type}://{proxy}")
        try:
            async with aiohttp.ClientSession(connector=connector) as sess:
                async with sess.post(url, headers=headers, data=data, timeout=VIEW_TIMEOUT) as resp:
                    return resp.status == 200
        except Exception:
            return False

    async def send_one_view(self, proxy: str, proxy_type: str) -> bool:
        token = await self._get_view_token(proxy, proxy_type)
        if token:
            return await self._send_view(token, proxy, proxy_type)
        return False

    async def send_views(self, proxies: List[str], proxy_type: str, target_count: int) -> int:
        """Send views using a rotating proxy list until target reached."""
        semaphore = asyncio.Semaphore(self.concurrency)
        success = 0

        async def worker(proxy: str):
            nonlocal success
            if success >= target_count:
                return
            async with semaphore:
                ok = await self.send_one_view(proxy, proxy_type)
                if ok:
                    success += 1

        # Cycle through proxies
        proxy_cycle = (proxies[i % len(proxies)] for i in range(target_count * 2))
        tasks = [worker(next(proxy_cycle)) for _ in range(target_count)]
        await asyncio.gather(*tasks)
        return success

# ------------------ Bot Handlers (Conversation) ------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔥 *Ultimate View Bot* 🔥\n\n"
        "Send me a Telegram post URL like:\n"
        "`https://t.me/durov/123`\n\n"
        "Then I'll ask how many views you want.",
        parse_mode="Markdown"
    )
    return WAITING_FOR_LINK

async def receive_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    # Validate URL
    match = re.search(r"t\.me/([^/]+)/(\d+)", url)
    if not match:
        await update.message.reply_text("❌ Invalid URL. Use format: `https://t.me/username/post_id`", parse_mode="Markdown")
        return WAITING_FOR_LINK

    channel = match.group(1)
    post_id = int(match.group(2))
    context.user_data["channel"] = channel
    context.user_data["post_id"] = post_id

    await update.message.reply_text(
        f"✅ Target set: `{channel}/{post_id}`\n\n"
        "Now send me the *number of views* you want (e.g., 100).",
        parse_mode="Markdown"
    )
    return WAITING_FOR_COUNT

async def receive_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        count = int(update.message.text.strip())
        if count <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Please send a positive integer (e.g., 50).")
        return WAITING_FOR_COUNT

    channel = context.user_data["channel"]
    post_id = context.user_data["post_id"]

    status_msg = await update.message.reply_text(
        f"🚀 Starting to send *{count}* views to `{channel}/{post_id}`...\n"
        "🌐 Scraping proxies...",
        parse_mode="Markdown"
    )

    # Step 1: Scrape proxies
    scraper = AutoScraper()
    proxies = await scraper.fetch_proxies()
    if not proxies:
        await status_msg.edit_text("❌ No proxies found. Try again later or use different sources.")
        return ConversationHandler.END

    await status_msg.edit_text(f"📡 Found {len(proxies)} proxies. Sending views...")

    # Step 2: Send views (use http proxies, fallback to socks5)
    booster = TelegramBooster(channel, post_id, concurrency=MAX_CONCURRENT)
    sent = await booster.send_views(proxies, "http", count)

    await status_msg.edit_text(
        f"✅ *Done!*\n"
        f"Successfully sent {sent} out of {count} views to `{channel}/{post_id}`.\n\n"
        f"Use /start to try another post.",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Operation cancelled. Use /start to begin again.")
    return ConversationHandler.END

# ------------------ Main ------------------
def main():
    logging.basicConfig(level=logging.INFO)
    app = Application.builder().token(BOT_TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_FOR_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_link)],
            WAITING_FOR_COUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_count)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv_handler)

    app.run_polling()

if __name__ == "__main__":
    main()
