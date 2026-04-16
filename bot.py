import os
import asyncio
import logging
import re
import random
from typing import List, Optional

import aiohttp
from aiohttp_socks import ProxyConnector
from fake_useragent import UserAgent
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ------------------ Configuration ------------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN environment variable not set!")

MAX_CONCURRENT = 20          # Lower concurrency to avoid bans
VIEW_TIMEOUT = 15
PROXY_TEST_TIMEOUT = 8

# Multiple proxy sources (more reliable)
PROXY_SOURCES = [
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt",
    "https://raw.githubusercontent.com/opsxcq/proxy-list/master/list.txt",
    "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=5000&country=all&ssl=all&anonymity=all",
    "https://www.proxy-list.download/api/v1/get?type=http",
]

# Conversation states
WAITING_FOR_LINK, WAITING_FOR_COUNT = range(2)

# ------------------ Proxy Fetcher (Multi-Source) ------------------
class ProxyFetcher:
    @staticmethod
    async def fetch_proxies() -> List[str]:
        """Fetch proxies from multiple sources."""
        all_proxies = set()
        
        async def fetch_one(url: str):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, timeout=15) as resp:
                        if resp.status == 200:
                            text = await resp.text()
                            # Extract IP:PORT patterns
                            found = re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}:\d{2,5}\b", text)
                            for p in found:
                                all_proxies.add(p)
                            logging.info(f"Fetched {len(found)} proxies from {url.split('/')[2]}")
            except Exception as e:
                logging.warning(f"Failed to fetch from {url}: {e}")
        
        # Fetch from all sources concurrently
        tasks = [fetch_one(url) for url in PROXY_SOURCES]
        await asyncio.gather(*tasks)
        
        proxies = list(all_proxies)
        logging.info(f"Total unique proxies fetched: {len(proxies)}")
        return proxies
    
    @staticmethod
    async def validate_proxy(proxy: str) -> bool:
        """Test if a proxy can connect to Telegram."""
        connector = ProxyConnector.from_url(f"http://{proxy}")
        try:
            async with aiohttp.ClientSession(connector=connector) as session:
                # Test with a simple Telegram page (not the embed)
                async with session.get("https://t.me/", timeout=PROXY_TEST_TIMEOUT) as resp:
                    return resp.status == 200
        except Exception:
            return False
    
    @staticmethod
    async def get_working_proxies(proxies: List[str], max_to_test: int = 200) -> List[str]:
        """Test proxies and return only working ones."""
        if not proxies:
            return []
        
        # Take a random sample to avoid testing all (saves time)
        sample = random.sample(proxies, min(max_to_test, len(proxies)))
        logging.info(f"Testing {len(sample)} proxies (this may take ~30 seconds)...")
        
        semaphore = asyncio.Semaphore(30)
        working = []
        
        async def test_one(proxy: str):
            async with semaphore:
                if await ProxyFetcher.validate_proxy(proxy):
                    working.append(proxy)
        
        await asyncio.gather(*[test_one(p) for p in sample])
        logging.info(f"Found {len(working)} working proxies")
        return working

# ------------------ View Booster (Original Working Method) ------------------
class TelegramBooster:
    def __init__(self, channel: str, post_id: int, concurrency: int = MAX_CONCURRENT):
        self.channel = channel
        self.post_id = post_id
        self.concurrency = concurrency
        self.ua = UserAgent()
        self.success_count = 0
        self.fail_count = 0

    async def send_one_view(self, proxy: str) -> bool:
        """Attempt to send one view using the given proxy."""
        connector = ProxyConnector.from_url(f"http://{proxy}")
        try:
            async with aiohttp.ClientSession(connector=connector) as session:
                # Step 1: Get the embed page to extract token
                embed_url = f"https://t.me/{self.channel}/{self.post_id}?embed=1"
                headers = {"User-Agent": self.ua.random, "Referer": "https://t.me/"}
                async with session.get(embed_url, headers=headers, timeout=VIEW_TIMEOUT) as resp:
                    if resp.status != 200:
                        return False
                    html = await resp.text()
                    # Extract token - original method from telegram-views
                    match = re.search(r'window\.telegramEmbed\s*=\s*"([^"]+)"', html)
                    if not match:
                        # Fallback to data-view attribute
                        match = re.search(r'data-view="([^"]+)"', html)
                    if not match:
                        return False
                    token = match.group(1)
                
                # Step 2: POST to the iv endpoint (original working method)
                post_url = "https://t.me/iv"
                post_data = f"token={token}&post_id={self.post_id}&channel={self.channel}"
                post_headers = {
                    "User-Agent": self.ua.random,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Referer": embed_url,
                    "Origin": "https://t.me",
                }
                async with session.post(post_url, headers=post_headers, data=post_data, timeout=VIEW_TIMEOUT) as post_resp:
                    return post_resp.status == 200
        except Exception as e:
            logging.debug(f"View failed for {proxy}: {e}")
            return False

    async def send_views(self, proxies: List[str], target_count: int) -> int:
        if not proxies:
            return 0
        
        semaphore = asyncio.Semaphore(self.concurrency)
        self.success_count = 0
        
        async def worker(proxy: str):
            async with semaphore:
                if self.success_count >= target_count:
                    return
                if await self.send_one_view(proxy):
                    self.success_count += 1
        
        # Cycle through proxies
        tasks = []
        for i in range(target_count):
            proxy = proxies[i % len(proxies)]
            tasks.append(worker(proxy))
        
        await asyncio.gather(*tasks)
        return self.success_count

# ------------------ Bot Handlers ------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔥 *Ultimate View Bot (Fixed)* 🔥\n\n"
        "Send me a Telegram post URL like:\n"
        "`https://t.me/durov/123`\n\n"
        "Then I'll ask how many views you want.\n\n"
        "*Important*: Use a *public* post (not private channel).",
        parse_mode="Markdown"
    )
    return WAITING_FOR_LINK

async def receive_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    url = update.message.text.strip()
    match = re.search(r"t\.me/([^/]+)/(\d+)", url)
    if not match:
        await update.message.reply_text("❌ Invalid URL. Use format: `https://t.me/username/post_id`", parse_mode="Markdown")
        return WAITING_FOR_LINK
    
    channel = match.group(1)
    post_id = int(match.group(2))
    context.user_data["channel"] = channel
    context.user_data["post_id"] = post_id
    
    await update.message.reply_text(
        f"✅ Target: `{channel}/{post_id}`\n\n"
        "Now send the *number of views* (start with 10 to test).",
        parse_mode="Markdown"
    )
    return WAITING_FOR_COUNT

async def receive_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        count = int(update.message.text.strip())
        if count <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Send a positive integer.")
        return WAITING_FOR_COUNT
    
    channel = context.user_data["channel"]
    post_id = context.user_data["post_id"]
    
    status_msg = await update.message.reply_text(
        "🚀 Starting...\n"
        "🌐 Fetching proxies from multiple sources...",
        parse_mode="Markdown"
    )
    
    # Step 1: Fetch proxies
    raw_proxies = await ProxyFetcher.fetch_proxies()
    if len(raw_proxies) < 10:
        await status_msg.edit_text("❌ Failed to fetch enough proxies. Try again later.")
        return ConversationHandler.END
    
    await status_msg.edit_text(f"📡 Fetched {len(raw_proxies)} proxies. Testing for working ones...")
    
    # Step 2: Validate proxies
    working_proxies = await ProxyFetcher.get_working_proxies(raw_proxies, max_to_test=300)
    if len(working_proxies) < 5:
        await status_msg.edit_text("❌ Less than 5 working proxies found. Please try again later.")
        return ConversationHandler.END
    
    await status_msg.edit_text(f"✅ Found {len(working_proxies)} working proxies. Sending {count} views...\n⏱️ This may take a minute.")
    
    # Step 3: Send views
    booster = TelegramBooster(channel, post_id, concurrency=MAX_CONCURRENT)
    sent = await booster.send_views(working_proxies, count)
    
    await status_msg.edit_text(
        f"✅ *Complete!*\n"
        f"Successfully sent {sent} out of {count} views.\n"
        f"Success rate: {sent/count*100:.1f}%\n\n"
        f"*Note*: If views didn't increase, Telegram may have patched this method.\n"
        f"Use /start to try again.",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled.")
    return ConversationHandler.END

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
    
    logging.info("Bot started. Polling...")
    app.run_polling()

if __name__ == "__main__":
    main()
