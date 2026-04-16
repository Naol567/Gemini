import asyncio
import aiohttp
import re
import random
import time
from datetime import timedelta
from aiohttp_socks import ProxyConnector
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ================= CONFIG =================
BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

# List of ULTIMATE proxy sources (30+ sources for maximum proxy pool)
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

# Performance settings for LIGHT SPEED
WORKER_COUNT = 1000            # Ultra-high concurrency (adjust based on your network)
PROXY_REFRESH_SECONDS = 10     # Refresh proxy list every 10 seconds
REQUEST_TIMEOUT = 3            # Aggressive timeout for speed
CONNECT_TIMEOUT = 2
MAX_PROXY_FAILURES = 1         # Remove proxy after 1 failure

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Referer": "https://t.me/",
}

class ViewEngine:
    def __init__(self):
        self.is_running = False
        self.channel = self.post_id = self.target = ""
        self.success = self.start_views = self.current_views = 0
        self.start_time = None
        self.proxies = []               # list of (type, proxy_str)
        self.proxy_failures = {}        # track failures per proxy
        self.proxy_queue = asyncio.Queue()
        self.workers = []
        self.sem = asyncio.Semaphore(WORKER_COUNT)

    async def get_views(self):
        """Fetch current view count from embed page"""
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
        """Fetch proxies from all sources in parallel for maximum speed"""
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
        # Fetch all sources concurrently
        await asyncio.gather(*[fetch(url) for url in PROXY_SOURCES])
        self.proxies = list(new_proxies)
        random.shuffle(self.proxies)
        # Initialize failure counters
        for p in self.proxies:
            if p not in self.proxy_failures:
                self.proxy_failures[p] = 0
        return len(self.proxies)

    async def hit(self, proxy_type, proxy_str):
        """Send one view request through a proxy"""
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
        """Worker that consumes proxies from queue"""
        while self.is_running:
            try:
                proxy = await asyncio.wait_for(self.proxy_queue.get(), timeout=0.5)
                await self.hit(*proxy)
                self.proxy_queue.task_done()
            except asyncio.TimeoutError:
                continue
            except:
                continue

    async def proxy_refresher(self):
        """Background task to refresh proxy list and refill queue"""
        last_refresh = 0
        while self.is_running:
            now = time.time()
            if now - last_refresh >= PROXY_REFRESH_SECONDS:
                await self.scrape_all_proxies()
                # Rebuild queue with fresh proxies
                self.proxy_queue = asyncio.Queue()
                for proxy in self.proxies:
                    if self.proxy_failures.get(proxy, 0) < MAX_PROXY_FAILURES:
                        await self.proxy_queue.put(proxy)
                last_refresh = now
            else:
                # Top up queue if low
                if self.proxy_queue.qsize() < 100 and self.proxies:
                    for proxy in self.proxies[:200]:
                        if self.proxy_failures.get(proxy, 0) < MAX_PROXY_FAILURES:
                            await self.proxy_queue.put(proxy)
            await asyncio.sleep(2)

    async def run(self, msg):
        # Initial proxy fetch
        await self.scrape_all_proxies()
        # Fill queue
        for proxy in self.proxies:
            await self.proxy_queue.put(proxy)
        # Start workers
        self.workers = [asyncio.create_task(self.worker()) for _ in range(WORKER_COUNT)]
        # Start refresher
        refresher = asyncio.create_task(self.proxy_refresher())
        
        # Main monitoring loop
        while self.is_running:
            self.current_views = await self.get_views()
            added = max(0, self.current_views - self.start_views)
            if self.current_views >= (self.start_views + self.target):
                self.is_running = False
                await msg.edit_text(f"✅ **Target reached!**\nViews: {self.current_views}\nSuccessful hits: {self.success}")
                break
            
            # Progress display
            prog = min(100, int((added / self.target) * 100)) if self.target > 0 else 0
            bar = "▓" * (prog // 10) + "░" * (10 - (prog // 10))
            elapsed = time.time() - self.start_time
            speed = int(added / (elapsed / 60)) if elapsed > 0 else 0
            rem = str(timedelta(seconds=int((self.target - added) / max(speed/60, 1)))) if added > 0 else "..."
            text = (f"🚀 **ULTIMATE PROXY BOOSTER**\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📊 [{bar}] {prog}%\n"
                    f"✅ Views: `{self.current_views}` | 🎯 `{self.start_views + self.target}`\n"
                    f"⚡ Speed: `{speed} views/min`\n"
                    f"🕒 Remaining: `{rem}`\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"🛠 Success: `{self.success}`\n"
                    f"🌐 Proxies in queue: `{self.proxy_queue.qsize()}`")
            try:
                await msg.edit_text(text, parse_mode="Markdown")
            except:
                pass
            await asyncio.sleep(2)
        
        # Cleanup
        refresher.cancel()
        for w in self.workers:
            w.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)

engine = ViewEngine()

# ================= BOT HANDLERS =================
async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 3:
        await update.message.reply_text("Usage: `/add channel post_id target`")
        return
    engine.channel = context.args[0].replace("@", "")
    engine.post_id = int(context.args[1])
    engine.target = int(context.args[2])
    engine.is_running = True
    engine.success = 0
    engine.start_time = time.time()
    engine.start_views = await engine.get_views()
    if engine.start_views == 0:
        await update.message.reply_text("⚠️ Could not fetch views. Make sure post exists and is public.")
        engine.is_running = False
        return
    msg = await update.message.reply_text(f"🔥 Starting booster...\nCurrent views: {engine.start_views}")
    asyncio.create_task(engine.run(msg))

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    engine.is_running = False
    await update.message.reply_text("🛑 Stopped.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📊 **Status**\n"
        f"Running: `{engine.is_running}`\n"
        f"Proxies loaded: `{len(engine.proxies)}`\n"
        f"Queue size: `{engine.proxy_queue.qsize()}`\n"
        f"Successes: `{engine.success}`",
        parse_mode="Markdown"
    )

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    found = re.findall(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+", txt)
    if found:
        for proxy in found:
            engine.proxies.append(('socks5', proxy))
            engine.proxy_failures[('socks5', proxy)] = 0
        await update.message.reply_text(f"✅ Added {len(found)} custom proxies.")
    else:
        await update.message.reply_text("Send me proxies as `IP:PORT` (one per line)")

if __name__ == "__main__":
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    print("🚀 ULTIMATE PROXY BOOSTER STARTED")
    app.run_polling()
