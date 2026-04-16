import asyncio, aiohttp, re, random, time
from datetime import timedelta
from aiohttp_socks import ProxyConnector
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- CONFIG ---
BOT_TOKEN = "8254387734:AAEd4VK_abdQuwgbFEiadoqj7UwlxDpmg3A"

SOURCES = [
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5&timeout=5000",
    "https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&sort_by=lastChecked&sort_type=desc",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
    "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/socks5.txt",
    "https://proxyspace.pro/socks5.txt",
    "https://api.openproxylist.xyz/socks5.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks5.txt",
    "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-socks5.txt"
]

class ViewEngine:
    def __init__(self):
        self.is_running = False
        self.channel, self.post_id, self.target = "", 0, 0
        self.success, self.start_views, self.current_views = 0, 0, 0
        self.start_time = None
        self.proxies = []
        self.used_proxies = {} 
        self.custom_urls = []
        self.custom_ips = []
        # የፍጥነት ጣሪያውን ከፍ አድርገነዋል
        self.sem = asyncio.Semaphore(4000) 

    async def get_views(self):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"https://t.me/{self.channel}/{self.post_id}?embed=1", timeout=5) as r:
                    html = await r.text()
                    m = re.search(r'<span class="tgme_widget_message_views">([^<]+)</span>', html)
                    if m:
                        v = m.group(1).replace('K', '000').replace('M', '000000').replace('.', '')
                        return int(''.join(filter(str.isdigit, v)))
        except: return 0
        return 0

    async def scrape_all(self):
        all_srcs = SOURCES + self.custom_urls
        temp = self.custom_ips.copy()
        async with aiohttp.ClientSession() as s:
            # Parallel Scraping ለፈጣን ፕሮክሲ አሰባሰብ
            tasks = [s.get(url, timeout=10) for url in all_srcs]
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            for r in responses:
                if isinstance(r, aiohttp.ClientResponse):
                    try:
                        text = await r.text()
                        found = re.findall(r"\d{1,3}(?:\.\d{1,3}){3}(?::\d{1,5})?", text)
                        temp.extend([('socks5', p) for p in found])
                    except: pass
        
        now = time.time()
        self.used_proxies = {p: t for p, t in self.used_proxies.items() if now - t < 600}
        available = [p for p in temp if p[1] not in self.used_proxies]
        self.proxies = list(set(available))
        random.shuffle(self.proxies)

    async def hit(self, pt, p):
        async with self.sem:
            if not self.is_running: return
            try:
                # Connection Timeout ቀንሰነዋል (ፈጣን ያልሆኑትን ፕሮክሲዎች ወዲያው ይተዋል)
                conn = ProxyConnector.from_url(f"{pt}://{p}")
                h = {
                    'User-Agent': 'Mozilla/5.0 (Linux; Android 10; SM-G960F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36',
                    'Referer': f'https://t.me/{self.channel}/{self.post_id}?embed=1',
                    'X-Requested-With': 'XMLHttpRequest'
                }
                async with aiohttp.ClientSession(connector=conn, timeout=aiohttp.ClientTimeout(total=4, connect=2)) as s:
                    async with s.get(f"https://t.me/{self.channel}/{self.post_id}?embed=1", headers=h) as r:
                        token = re.search(r'data-view="([^"]+)"', await r.text())
                        if token:
                            async with s.post(f"https://t.me/v/?views={token.group(1)}", headers=h) as vr:
                                if "true" in await vr.text():
                                    self.success += 1
                                    self.used_proxies[p] = time.time()
            except: pass

engine = ViewEngine()

async def work(msg):
    while engine.is_running:
        engine.current_views = await engine.get_views()
        added = max(0, engine.current_views - engine.start_views)
        
        if engine.current_views >= (engine.start_views + engine.target):
            engine.is_running = False
            await msg.edit_text(f"✅ ተጠናቋል!\nViews: {engine.current_views}")
            break

        elapsed = time.time() - engine.start_time
        speed = int(added / (elapsed / 60)) if elapsed > 0 else 0
        
        text = (f"🔥 **MAXIMUM TURBO SPEED**\n"
                f"━━━━━━━━━━━━━━━\n"
                f"📈 Views: `{engine.current_views}`\n"
                f"⚡ Speed: `{speed} v/min` | 🛠 Success: `{engine.success}`\n"
                f"📡 Available: `{len(engine.proxies)}` | ❄️ Cool: `{len(engine.used_proxies)}` \n"
                f"━━━━━━━━━━━━━━━\n"
                f"💡 Tip: Speed ቀንሶ Success ከጨመረ ቴሌግራም Freeze አድርጎታል።")
        try: await msg.edit_text(text, parse_mode="Markdown")
        except: pass
        
        await engine.scrape_all()
        # 4000 ፕሮክሲዎች በአንዴ!
        tasks = [engine.hit(pt, p) for pt, p in engine.proxies[:4000]]
        if tasks: await asyncio.gather(*tasks)
        await asyncio.sleep(0.5)

async def add(update, context):
    if len(context.args) < 3: return
    engine.channel, engine.post_id, engine.target = context.args[0].replace("@",""), int(context.args[1]), int(context.args[2])
    engine.is_running, engine.success, engine.start_time = True, 0, time.time()
    engine.start_views = await engine.get_views()
    msg = await update.message.reply_text("🚀 ፈጣን ፍጥነት እየተዘጋጀ ነው...")
    context.application.create_task(work(msg))

async def reset(update, context):
    engine.used_proxies.clear()
    engine.proxies.clear()
    await update.message.reply_text("♻️ ፕሮክሲዎች ታድሰዋል!")

if __name__ == "__main__":
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("stop", lambda u,c: setattr(engine,'is_running',False)))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, lambda u,c: engine.custom_urls.append(u.message.text)))
    app.run_polling()
