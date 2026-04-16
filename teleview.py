import asyncio
import aiohttp
import re
import random
import time
from datetime import timedelta
from aiohttp_socks import ProxyConnector
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, CallbackQueryHandler, ConversationHandler
)

# ================= CONFIG =================
BOT_TOKEN = "8759135008:AAFc5a-Ek1RrtmAwd7vWK04kdyt21TNgE4I"

# 30+ proxy sources (auto-refresh every 10 seconds)
PROXY_SOURCES = [
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
    "https://raw.githubusercontent.com/Thordata/awesome-free-proxy-list/main/proxies/socks5.txt",
    "https://raw.githubusercontent.com/Ian-Lusule/Proxies/main/proxies/socks5.txt",
    "https://raw.githubusercontent.com/iplocate/free-proxy-list/main/protocols/socks5.txt",
    "https://raw.githubusercontent.com/GoekhanDev/free-proxy-list/main/data/txt/socks5.txt",
    "https://raw.githubusercontent.com/joy-deploy/free-proxy-list/main/data/latest/types/socks5/proxies.txt",
    "https://raw.githubusercontent.com/Loclki/PROXY-List/master/socks5.txt",
    "https://raw.githubusercontent.com/Argh94/Proxy-List/main/socks5.txt",
    "https://raw.githubusercontent.com/gfpcom/free-proxy-list/main/list/socks5.txt",
    "https://raw.githubusercontent.com/fyvri/fresh-proxy-list/main/socks5.txt",
    "https://raw.githubusercontent.com/ShadowsocksR/Proxy-List/master/socks5.txt",
    "https://raw.githubusercontent.com/mmpx12/proxy-list/master/socks5.txt",
    "https://raw.githubusercontent.com/saschazesiger/Free-Proxies/master/socks5.txt",
    "https://raw.githubusercontent.com/officialputuid/tools/main/Proxy/socks5.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5&timeout=10000",
    "https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&sort_by=lastChecked&sort_type=desc&protocols=socks5",
    "https://proxyspace.pro/socks5.txt",
    "https://www.proxy-list.download/api/v1/get?type=socks5",
    "https://multiproxy.org/txt_all/proxy.txt",
    "https://rootjazz.com/proxies/proxies.txt",
    "https://openproxy.space/list/socks5",
    "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks5.txt",
    "https://raw.githubusercontent.com/manuGMG/proxy-365/main/SOCKS5.txt",
    "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5_RAW.txt",
    "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
    "https://raw.githubusercontent.com/zevtyardt/proxy-list/main/socks5.txt",
    "https://raw.githubusercontent.com/clarketm/Proxy-list/master/socks5.txt",
    "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/proxies/socks5.txt",
    "https://raw.githubusercontent.com/ALIILAPRO/Proxy/main/socks5.txt",
]

# Performance settings
WORKER_COUNT = 1500
PROXY_REFRESH_SECONDS = 5
REQUEST_TIMEOUT = 2
CONNECT_TIMEOUT = 1
MAX_PROXY_FAILURES = 1

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Referer": "https://t.me/",
}

# Conversation states
WAITING_FOR_LINK, WAITING_FOR_TARGET = range(2)

class ViewEngine:
    def __init__(self):
        self.is_running = False
        self.channel = ""
        self.post_id = 0
        self.target = 0
        self.success = 0
        self.start_views = 0
        self.current_views = 0
        self.start_time = None
        self.proxies = []
        self.proxy_failures = {}
        self.proxy_queue = asyncio.Queue()
        self.workers = []
        self.sem = asyncio.Semaphore(WORKER_COUNT)

    async def get_views(self):
        try:
            async with aiohttp.ClientSession(headers=HEADERS) as s:
                url = f"https://t.me/{self.channel}/{self.post_id}?embed=1"
                async with s.get(url, timeout=5) as r:
                    html = await r.text()
                    patterns = [
                        r'<span class="tgme_widget_message_views">([^<]+)</span>',
                        r'data-views="([^"]+)"',
                        r'<div class="tgme_widget_message_views">([^<]+)</div>',
                    ]
                    for pat in patterns:
                        m = re.search(pat, html)
                        if m:
                            v = m.group(1).replace('K', '000').replace('M', '000000').replace('.', '')
                            return int(''.join(filter(str.isdigit, v)))
        except:
            return 0
        return 0

    async def scrape_all_proxies(self):
        new_proxies = set()
        async def fetch(url):
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(url, timeout=5) as r:
                        text = await r.text()
                        found = re.findall(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{1,5}", text)
                        for proxy in found:
                            new_proxies.add(('socks5', proxy))
            except:
                pass
        await asyncio.gather(*[fetch(url) for url in PROXY_SOURCES])
        self.proxies = list(new_proxies)
        random.shuffle(self.proxies)
        for p in self.proxies:
            if p not in self.proxy_failures:
                self.proxy_failures[p] = 0
        return len(self.proxies)

    async def hit(self, proxy_type, proxy_str):
        async with self.sem:
            if not self.is_running:
                return False
            if self.proxy_failures.get((proxy_type, proxy_str), 0) >= MAX_PROXY_FAILURES:
                return False
            try:
                connector = ProxyConnector.from_url(f"{proxy_type}://{proxy_str}")
                async with aiohttp.ClientSession(
                    connector=connector,
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT, connect=CONNECT_TIMEOUT),
                    headers=HEADERS
                ) as s:
                    embed_url = f"https://t.me/{self.channel}/{self.post_id}?embed=1"
                    async with s.get(embed_url) as resp:
                        html = await resp.text()
                        token_match = re.search(r'data-view="([^"]+)"', html)
                        if not token_match:
                            token_match = re.search(r'view":"([^"]+)"', html)
                        if token_match:
                            token = token_match.group(1)
                            view_url = f"https://t.me/v/?views={token}"
                            async with s.post(view_url, headers={"X-Requested-With": "XMLHttpRequest"}) as vr:
                                text = await vr.text()
                                if "true" in text or '"ok":true' in text:
                                    self.success += 1
                                    return True
            except Exception:
                self.proxy_failures[(proxy_type, proxy_str)] = self.proxy_failures.get((proxy_type, proxy_str), 0) + 1
            return False

    async def worker(self):
        while self.is_running:
            try:
                proxy = await asyncio.wait_for(self.proxy_queue.get(), timeout=0.3)
                await self.hit(*proxy)
                self.proxy_queue.task_done()
            except asyncio.TimeoutError:
                continue
            except:
                continue

    async def proxy_refresher(self):
        last_refresh = 0
        while self.is_running:
            now = time.time()
            if now - last_refresh >= PROXY_REFRESH_SECONDS:
                await self.scrape_all_proxies()
                self.proxy_queue = asyncio.Queue()
                for proxy in self.proxies:
                    if self.proxy_failures.get(proxy, 0) < MAX_PROXY_FAILURES:
                        await self.proxy_queue.put(proxy)
                last_refresh = now
            else:
                if self.proxy_queue.qsize() < 200 and self.proxies:
                    for proxy in self.proxies[:300]:
                        if self.proxy_failures.get(proxy, 0) < MAX_PROXY_FAILURES:
                            await self.proxy_queue.put(proxy)
            await asyncio.sleep(2)

    async def run(self, msg, target_minutes=1):
        await self.scrape_all_proxies()
        for proxy in self.proxies:
            await self.proxy_queue.put(proxy)
        self.workers = [asyncio.create_task(self.worker()) for _ in range(WORKER_COUNT)]
        refresher = asyncio.create_task(self.proxy_refresher())
        deadline = time.time() + (target_minutes * 60)
        while self.is_running:
            self.current_views = await self.get_views()
            added = max(0, self.current_views - self.start_views)
            if self.current_views >= (self.start_views + self.target):
                self.is_running = False
                await msg.edit_text(f"✅ Target reached in {int(time.time() - self.start_time)} sec!\nViews: {self.current_views}\nHits: {self.success}")
                break
            if time.time() > deadline:
                self.is_running = False
                await msg.edit_text(f"⏰ Time limit ({target_minutes} min) reached!\nViews: {self.current_views} / {self.start_views + self.target}\nHits: {self.success}")
                break
            prog = min(100, int((added / self.target) * 100)) if self.target > 0 else 0
            bar = "▓" * (prog // 10) + "░" * (10 - (prog // 10))
            elapsed = time.time() - self.start_time
            speed = int(added / (elapsed / 60)) if elapsed > 0 else 0
            text = (f"🚀 **ULTRA BOOSTER (1 MIN)**\n━━━━━━━━━━━━\n📊 [{bar}] {prog}%\n✅ Views: `{self.current_views}` | 🎯 `{self.start_views + self.target}`\n⚡ Speed: `{speed} v/min`\n🛠 Hits: `{self.success}`\n🌐 Proxies: `{self.proxy_queue.qsize()}`")
            try:
                await msg.edit_text(text, parse_mode="Markdown")
            except:
                pass
            await asyncio.sleep(1)
        refresher.cancel()
        for w in self.workers:
            w.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)

engine = ViewEngine()

# ================= BOT HANDLERS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔥 **Ultimate Proxy Booster Bot**\n\n"
        "Send me a Telegram post link like:\n"
        "`https://t.me/username/123` or `@username/123`\n\n"
        "I will delete your link and ask for target views.",
        parse_mode="Markdown"
    )
    return WAITING_FOR_LINK

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    text = message.text.strip()
    await message.delete()  # Delete the user's link message

    # Improved regex: allows letters, numbers, underscores, hyphens, dots in channel name
    match = re.search(r'(?:https?://)?(?:t\.me/|@)?([a-zA-Z0-9_\-\.]+)/(\d+)', text)
    if not match:
        await message.reply_text("❌ Invalid link format. Send like: `https://t.me/channel-name/123`", parse_mode="Markdown")
        return WAITING_FOR_LINK

    channel = match.group(1)
    post_id = int(match.group(2))
    context.user_data['channel'] = channel
    context.user_data['post_id'] = post_id

    # Get current views (optional)
    engine.channel = channel
    engine.post_id = post_id
    current = await engine.get_views()
    await message.reply_text(
        f"✅ **Link received:** `{channel}/{post_id}`\n"
        f"📊 **Current views:** `{current}`\n\n"
        f"Now send the **target number of views** (e.g., `5000`)\n"
        f"I will try to reach it **within 1 minute** using 2500+ proxies.",
        parse_mode="Markdown"
    )
    return WAITING_FOR_TARGET

async def handle_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("Please send a valid number (e.g., `5000`)", parse_mode="Markdown")
        return WAITING_FOR_TARGET

    target = int(text)
    context.user_data['target'] = target

    keyboard = [
        [InlineKeyboardButton("✅ YES, START", callback_data="confirm_yes")],
        [InlineKeyboardButton("❌ CANCEL", callback_data="confirm_no")]
    ]
    await update.message.reply_text(
        f"⚠️ **CONFIRMATION**\n\n"
        f"Channel: `{context.user_data['channel']}`\n"
        f"Post ID: `{context.user_data['post_id']}`\n"
        f"Target views: `{target}`\n\n"
        f"🔥 This will use **extreme concurrency** (1500 workers) and **2500+ proxies**.\n"
        f"⏱️ Will stop after 1 minute.\n\n"
        f"**Do you want to start?**",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_FOR_TARGET  # Stay in this state until callback

async def confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "confirm_yes":
        channel = context.user_data.get('channel')
        post_id = context.user_data.get('post_id')
        target = context.user_data.get('target')
        if not all([channel, post_id, target]):
            await query.edit_message_text("❌ Missing data. Please use /start again.")
            return ConversationHandler.END

        engine.channel = channel
        engine.post_id = post_id
        engine.target = target
        engine.is_running = True
        engine.success = 0
        engine.start_time = time.time()
        engine.start_views = await engine.get_views()
        if engine.start_views == 0:
            await query.edit_message_text("⚠️ Could not fetch current views. Make sure post exists and is public.")
            engine.is_running = False
            return ConversationHandler.END

        msg = await query.edit_message_text("🔥 **BOOSTER ACTIVATED**\nStarting...", parse_mode="Markdown")
        asyncio.create_task(engine.run(msg, target_minutes=1))
    else:
        await query.edit_message_text("❌ Cancelled. Use /start to begin again.")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    engine.is_running = False
    await update.message.reply_text("🛑 Boosting stopped (if running).")
    return ConversationHandler.END

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_FOR_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link)],
            WAITING_FOR_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_target)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(confirm_callback))
    print("🚀 BOT STARTED - Fixed regex and conversation handler")
    print("⚠️ WARNING: This method does NOT increase real view counts (Telegram patched it).")
    app.run_polling()

if __name__ == "__main__":
    main()
