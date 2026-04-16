import os
import asyncio
import logging
import re
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

MAX_CONCURRENT = 30
VIEW_TIMEOUT = 10
PROXY_API_URL = "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=5000&country=all&ssl=all&anonymity=all"

# Conversation states
WAITING_FOR_LINK, WAITING_FOR_COUNT = range(2)

# ------------------ Live Proxy Fetcher ------------------
class ProxyFetcher:
    @staticmethod
    async def fetch_live_proxies() -> List[str]:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(PROXY_API_URL, timeout=15) as resp:
                    if resp.status != 200:
                        logging.error(f"Proxy API returned {resp.status}")
                        return []
                    text = await resp.text()
                    proxies = []
                    for line in text.splitlines():
                        line = line.strip()
                        if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{2,5}$", line):
                            proxies.append(line)
                    logging.info(f"Fetched {len(proxies)} raw proxies from API")
                    return proxies
        except Exception as e:
            logging.error(f"Failed to fetch proxies: {e}")
            return []

# ------------------ View Booster (THE CORRECTED LOGIC) ------------------
class TelegramBooster:
    def __init__(self, channel: str, post_id: int, concurrency: int = MAX_CONCURRENT):
        self.channel = channel
        self.post_id = post_id
        self.concurrency = concurrency
        self.ua = UserAgent()
        self.success_sent = 0
        self.failed_sent = 0

    async def request(self, proxy: str, proxy_type: str) -> bool:
        # Prepare the proxy connector
        if proxy_type == 'socks4':
            connector = ProxyConnector.from_url(f'socks4://{proxy}')
        elif proxy_type == 'socks5':
            connector = ProxyConnector.from_url(f'socks5://{proxy}')
        elif proxy_type == 'https':
            connector = ProxyConnector.from_url(f'https://{proxy}')
        else:
            connector = ProxyConnector.from_url(f'http://{proxy}')
        
        # Use a cookie jar to capture the 'stel_ssid' cookie
        jar = aiohttp.CookieJar(unsafe=True)
        async with aiohttp.ClientSession(cookie_jar=jar, connector=connector) as session:
            try:
                # Step 1: GET the embed page to get the token and cookie
                embed_url = f'https://t.me/{self.channel}/{self.post_id}?embed=1&mode=tme'
                headers = {
                    'referer': f'https://t.me/{self.channel}/{self.post_id}',
                    'user-agent': self.ua.random
                }
                async with session.get(embed_url, headers=headers, timeout=VIEW_TIMEOUT) as embed_response:
                    # Check for the required 'stel_ssid' cookie
                    if jar.filter_cookies(embed_response.url).get('stel_ssid'):
                        html_content = await embed_response.text()
                        # Extract the data-view token using regex
                        views_token_match = re.search(r'data-view="([^"]+)"', html_content)
                        if views_token_match:
                            views_token = views_token_match.group(1)
                            # Step 2: POST to the views endpoint with the token
                            post_url = f'https://t.me/v/?views={views_token}'
                            post_headers = {
                                'referer': f'https://t.me/{self.channel}/{self.post_id}?embed=1&mode=tme',
                                'user-agent': self.ua.random,
                                'x-requested-with': 'XMLHttpRequest'
                            }
                            async with session.post(post_url, headers=post_headers, timeout=VIEW_TIMEOUT) as views_response:
                                response_text = await views_response.text()
                                # A successful response is the string "true" with a 200 status code
                                if response_text == "true" and views_response.status == 200:
                                    self.success_sent += 1
                                    return True
                                else:
                                    self.failed_sent += 1
                                    return False
                        else:
                            self.failed_sent += 1
                            return False
                    else:
                        self.failed_sent += 1
                        return False
            except Exception:
                self.failed_sent += 1
                return False

    async def send_views(self, proxies: List[str], proxy_type: str, target_count: int) -> int:
        if not proxies:
            return 0
        
        semaphore = asyncio.Semaphore(self.concurrency)
        self.success_sent = 0
        
        async def worker(proxy: str):
            async with semaphore:
                if self.success_sent < target_count:
                    await self.request(proxy, proxy_type)
        
        # Create tasks, cycling through proxies
        proxy_count = len(proxies)
        tasks = [worker(proxies[i % proxy_count]) for i in range(target_count)]
        await asyncio.gather(*tasks)
        
        return self.success_sent

# ------------------ Bot Handlers (Unchanged) ------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔥 *Ultimate View Bot* 🔥\n\n"
        "Send me a Telegram post URL like:\n"
        "`https://t.me/durov/123`\n\n"
        "Then I'll ask how many views you want.\n"
        "I will fetch fresh proxies automatically.",
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
        "Now send the *number of views* (e.g., 5000).\n"
        "⚠️ Large numbers may take several minutes.",
        parse_mode="Markdown"
    )
    return WAITING_FOR_COUNT

async def receive_count(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        count = int(update.message.text.strip())
        if count <= 0:
            raise ValueError
    except ValueError:
        await update.message.reply_text("❌ Send a positive integer (e.g., 1000).")
        return WAITING_FOR_COUNT

    channel = context.user_data["channel"]
    post_id = context.user_data["post_id"]

    status_msg = await update.message.reply_text(
        f"🚀 Preparing to send *{count}* views to `{channel}/{post_id}`...\n"
        "🌐 Fetching fresh proxies from API...",
        parse_mode="Markdown"
    )

    raw_proxies = await ProxyFetcher.fetch_live_proxies()
    if not raw_proxies:
        await status_msg.edit_text("❌ Failed to fetch proxies from API. Try again later.")
        return ConversationHandler.END

    await status_msg.edit_text(f"📡 Fetched {len(raw_proxies)} proxies. Starting to send views...")

    booster = TelegramBooster(channel, post_id, concurrency=MAX_CONCURRENT)
    # Use 'http' as the default proxy type
    sent = await booster.send_views(raw_proxies, "http", count)

    await status_msg.edit_text(
        f"✅ *Complete!*\n"
        f"Successfully sent {sent} out of {count} views.\n"
        f"Success rate: {sent/count*100:.1f}%\n\n"
        f"Use /start to try another post.",
        parse_mode="Markdown"
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled. Use /start to begin again.")
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
