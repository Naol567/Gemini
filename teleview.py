import asyncio
import aiohttp
import re
import random
import time
from datetime import timedelta
from aiohttp_socks import ProxyConnector
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

# Enhanced proxy sources with redundancy and fallbacks
SOURCES = [
    # Primary SOCKS5 sources (most reliable)
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
    
    # Backup HTTP/HTTPS sources (will filter for SOCKS5 support)
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5&timeout=5000",
    "https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&sort_by=lastChecked&sort_type=desc",
    "https://proxyspace.pro/socks5.txt",
    "https://www.proxy-list.download/api/v1/get?type=socks5",
    "https://multiproxy.org/txt_all/proxy.txt",
]

# High-performance connection settings
MAX_CONNECTIONS = 300
REQUEST_TIMEOUT = 8
CONNECT_TIMEOUT = 4
WORKER_COUNT = 100
PROXY_REFRESH_INTERVAL = 30  # Refresh every 30 seconds
MAX_FAILURES = 3

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Referer": "https://t.me/",
}

class ViewEngine:
    def __init__(self):
        self.is_running = False
        self.channel = ""
        self.post_id = 0
        self.target = 0
        self.success = 0
        self.failures = 0
        self.start_views = 0
        self.current_views = 0
        self.start_time = None
        self.proxies = []  # list of (type, proxy_str)
        self.proxy_stats = {}  # track failures per proxy
        self.queue = asyncio.Queue()
        self.workers = []
        self.semaphore = asyncio.Semaphore(WORKER_COUNT)
        self.last_refresh = 0

    async def get_views(self):
        """Get current view count from embed page"""
        try:
            async with aiohttp.ClientSession(headers=HEADERS) as s:
                url = f"https://t.me/{self.channel}/{self.post_id}?embed=1"
                async with s.get(url, timeout=10) as r:
                    html = await r.text()
                    patterns = [
                        r'<span class="tgme_widget_message_views">([^<]+)</span>',
                        r'data-views="([^"]+)"',
                        r'<div class="tgme_widget_message_views">([^<]+)</div>'
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
        """Scrape proxies from all sources with parallel fetching"""
        temp_proxies = []
        
        async def fetch_source(url):
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.get(url, timeout=15) as r:
                        if "application/json" in r.headers.get("Content-Type", ""):
                            data = await r.json()
                            if isinstance(data, dict):
                                proxies = data.get('data') or data.get('proxies') or data.get('list') or []
                            else:
                                proxies = data
                            if isinstance(proxies, list):
                                for p in proxies:
                                    if isinstance(p, dict):
                                        ip = p.get('ip') or p.get('host')
                                        port = p.get('port')
                                        if ip and port:
                                            temp_proxies.append(('socks5', f"{ip}:{port}"))
                        else:
                            text = await r.text()
                            found = re.findall(r"\d{1,3}(?:\.\d{1,3}){3}:\d{1,5}", text)
                            temp_proxies.extend([('socks5', p) for p in found])
            except:
                pass
        
        # Fetch all sources concurrently
        tasks = [fetch_source(url) for url in SOURCES]
        await asyncio.gather(*tasks)
        
        # Deduplicate and shuffle
        self.proxies = list(set(temp_proxies))
        random.shuffle(self.proxies)
        
        # Initialize failure tracking for new proxies
        for proxy in self.proxies:
            if proxy not in self.proxy_stats:
                self.proxy_stats[proxy] = 0
        
        print(f"Scraped {len(self.proxies)} unique proxies")
        return len(self.proxies)

    async def hit(self, proxy_type, proxy_str):
        """Try to register a view using a single proxy"""
        if not self.is_running:
            return False
        
        async with self.semaphore:
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
            except:
                self.failures += 1
                self.proxy_stats[(proxy_type, proxy_str)] = self.proxy_stats.get((proxy_type, proxy_str), 0) + 1
            return False

    async def worker(self):
        """Worker that consumes proxies from queue"""
        while self.is_running:
            try:
                proxy = await asyncio.wait_for(self.queue.get(), timeout=2)
                await self.hit(*proxy)
                self.queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception:
                continue

    async def refresh_proxy_queue(self):
        """Refresh proxy list and replenish queue"""
        current_time = time.time()
        if current_time - self.last_refresh >= PROXY_REFRESH_INTERVAL:
            await self.scrape_all_proxies()
            # Filter out failed proxies (those with too many failures)
            healthy_proxies = [
                p for p in self.proxies 
                if self.proxy_stats.get(p, 0) < MAX_FAILURES
            ]
            for proxy in healthy_proxies:
                await self.queue.put(proxy)
            self.last_refresh = current_time
            print(f"Queue refilled: {self.queue.qsize()} proxies ready")
        else:
            # If queue is low, add more proxies
            if self.queue.qsize() < 50 and self.proxies:
                for proxy in self.proxies[:100]:
                    await self.queue.put(proxy)

    async def run(self, msg):
        # Initial proxy fetch
        await self.scrape_all_proxies()
        
        # Start worker pool
        self.workers = [asyncio.create_task(self.worker()) for _ in range(WORKER_COUNT)]
        
        # Main loop
        while self.is_running:
            await self.refresh_proxy_queue()
            
            # Update view count
            self.current_views = await self.get_views()
            added = max(0, self.current_views - self.start_views)
            
            # Check if target reached
            if self.current_views >= (self.start_views + self.target):
                self.is_running = False
                await msg.edit_text(f"✅ Target reached!\nViews: {self.current_views}\nSuccessful hits: {self.success}")
                break
            
            # Progress display
            prog = min(100, int((added / self.target) * 100)) if self.target > 0 else 0
            bar = "▓" * (prog // 10) + "░" * (10 - (prog // 10))
            elapsed = time.time() - self.start_time
            speed = int(added / (elapsed / 60)) if elapsed > 0 else 0
            rem_time = str(timedelta(seconds=int((self.target - added) / max(speed/60, 1)))) if added > 0 else "..."
            success_rate = int((self.success / max(self.success + self.failures, 1)) * 100)
            
            text = (f"🚀 **ULTIMATE PROXY BOOSTER**\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"📊 [{bar}] {prog}%\n"
                    f"✅ Views: `{self.current_views}` | 🎯 Target: `{self.start_views + self.target}`\n"
                    f"⚡ Speed: `{speed} views/min`\n"
                    f"🕒 Remaining: `{rem_time}`\n"
                    f"━━━━━━━━━━━━━━━\n"
                    f"📈 Performance:\n"
                    f"• Successful hits: `{self.success}`\n"
                    f"• Failed attempts: `{self.failures}`\n"
                    f"• Success rate: `{success_rate}%`\n"
                    f"• Proxies in queue: `{self.queue.qsize()}`\n"
                    f"• Total proxies: `{len(self.proxies)}`")
            try:
                await msg.edit_text(text, parse_mode="Markdown")
            except:
                pass
            
            await asyncio.sleep(3)
        
        # Stop workers
        for w in self.workers:
            w.cancel()
        await asyncio.gather(*self.workers, return_exceptions=True)

engine = ViewEngine()

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 3:
        await update.message.reply_text(
            "Usage: `/add channel post_id target`\n"
            "Example: `/add mychannel 123 5000`\n\n"
            "⚠️ Note: Free proxies are often slow. For best results, consider using residential proxies."
        )
        return
    
    engine.channel = context.args[0].replace("@", "")
    engine.post_id = int(context.args[1])
    engine.target = int(context.args[2])
    engine.is_running = True
    engine.success = 0
    engine.failures = 0
    engine.start_time = time.time()
    engine.start_views = await engine.get_views()
    
    if engine.start_views == 0:
        await update.message.reply_text("⚠️ Could not fetch current views. Make sure the post exists and is public.")
        engine.is_running = False
        return
    
    msg = await update.message.reply_text(f"🔥 Starting booster...\nCurrent views: {engine.start_views}")
    asyncio.create_task(engine.run(msg))

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    engine.is_running = False
    await update.message.reply_text("🛑 Stopped.")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"📊 **Bot Status**\n"
        f"━━━━━━━━━━━━━━━\n"
        f"• Running: `{engine.is_running}`\n"
        f"• Proxies loaded: `{len(engine.proxies)}`\n"
        f"• Queue size: `{engine.queue.qsize()}`\n"
        f"• Success rate: `{engine.success}/{engine.success + engine.failures}`\n\n"
        f"💡 To add custom proxies: Send them as messages to this bot in format: `IP:PORT`",
        parse_mode="Markdown"
    )

async def handle_msg(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    found = re.findall(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d+", txt)
    if found:
        engine.proxies.extend([('socks5', f) for f in found])
        for f in found:
            engine.proxy_stats[('socks5', f)] = 0
        await update.message.reply_text(f"✅ Added {len(found)} custom proxy(ies). Total: {len(engine.proxies)}")
    else:
        await update.message.reply_text(
            "❌ Invalid format.\n"
            "Send proxies as: `IP:PORT`\n"
            "Example: `192.168.1.1:1080`",
            parse_mode="Markdown"
        )

if __name__ == "__main__":
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    print("🚀 Ultimate Proxy Booster Bot Started!")
    print("━━━━━━━━━━━━━━━━━━━━━━")
    print("📌 Commands:")
    print("   /add @channel post_id target - Start boosting")
    print("   /stop - Stop boosting")
    print("   /status - Check bot status")
    print("━━━━━━━━━━━━━━━━━━━━━━")
    print("💡 To add proxies: Send IP:PORT as messages")
    app.run_polling()
