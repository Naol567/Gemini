import asyncio, aiohttp, re, random, time
from datetime import timedelta
from aiohttp_socks import ProxyConnector
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- CONFIG ---
# ያንተን የቦት ቶከን እዚህ አስገባ
BOT_TOKEN = "8254387734:AAEd4VK_abdQuwgbFEiadoqj7UwlxDpmg3A"

# ያኔ በፍጥነት እንዲሰበስብ የረዳው የፕሮክሲ ዝርዝር
SOURCES = [
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5&timeout=5000",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
    "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/socks5.txt",
    "https://proxyspace.pro/socks5.txt",
    "https://api.openproxylist.xyz/socks5.txt",
    "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt"
]

class ViewEngine:
    def __init__(self):
        self.is_running = False
        self.channel, self.post_id, self.target = "", 0, 0
        self.success, self.start_views, self.current_views = 0, 0, 0
        self.start_time = None
        self.proxies = []
        self.custom_urls = []
        self.custom_ips = []
        # ያኔ ፍጥነት የጨመረው ሴማፎር
        self.sem = asyncio.Semaphore(2500) 

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
        """ሁሉንም ምንጮች በአንዴ የሚሰበስብ"""
        all_srcs = SOURCES + self.custom_urls
        temp = self.custom_ips.copy()
        async with aiohttp.ClientSession() as s:
            for url in all_srcs:
                try:
                    async with s.get(url, timeout=10) as r:
                        text = await r.text()
                        found = re.findall(r"\d{1,3}(?:\.\d{1,3}){3}(?::\d{1,5})?", text)
                        temp.extend([('socks5', p) for p in found])
                except: pass
        self.proxies = list(set(temp))
        random.shuffle(self.proxies)

    async def hit(self, pt, p):
        async with self.sem:
            if not self.is_running: return
            try:
                conn = ProxyConnector.from_url(f"{pt}://{p}")
                # ያኔ የጨመርነው ወሳኝ ሴቲንግ (Headers)
                headers = {
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15',
                    'Referer': f'https://t.me/{self.channel}/{self.post_id}?embed=1',
                    'X-Requested-With': 'XMLHttpRequest'
                }
                async with aiohttp.ClientSession(connector=conn, timeout=aiohttp.ClientTimeout(total=5, connect=2)) as s:
                    async with s.get(f"https://t.me/{self.channel}/{self.post_id}?embed=1", headers=headers) as r:
                        res = await r.text()
                        token = re.search(r'data-view="([^"]+)"', res)
                        if token:
                            async with s.post(f"https://t.me/v/?views={token.group(1)}", headers=headers) as vr:
                                if "true" in await vr.text():
                                    self.success += 1
            except: pass

engine = ViewEngine()

async def work(msg):
    while engine.is_running:
        v = await engine.get_views()
        if v > 0: engine.current_views = v
        
        added = max(0, engine.current_views - engine.start_views)
        if engine.current_views >= (engine.start_views + engine.target):
            engine.is_running = False
            await msg.edit_text(f"✅ ተጠናቋል!\nViews: {engine.current_views}")
            break

        elapsed = time.time() - engine.start_time
        speed = int(added / (elapsed / 60)) if elapsed > 0 else 0
        
        text = (f"🚀 **ULTRA TURBO ACTIVATED**\n"
                f"━━━━━━━━━━━━━━━\n"
                f"📈 Views: `{engine.current_views}`\n"
                f"🎯 Target: `{engine.start_views + engine.target}`\n"
                f"⚡ Speed: `{speed} v/min` | ✅ Success: `{engine.success}`\n"
                f"📡 Pool: `{len(engine.proxies)}` \n"
                f"━━━━━━━━━━━━━━━")
        try: await msg.edit_text(text, parse_mode="Markdown")
        except: pass
        
        await engine.scrape_all()
        # ፕሮክሲዎቹን በፍጥነት መርጨት
        tasks = [engine.hit(pt, p) for pt, p in engine.proxies[:3000]]
        if tasks: await asyncio.gather(*tasks)
        await asyncio.sleep(1)

async def add(update, context):
    if len(context.args) < 3: return
    engine.channel, engine.post_id, engine.target = context.args[0].replace("@",""), int(context.args[1]), int(context.args[2])
    engine.is_running, engine.success, engine.start_time = True, 0, time.time()
    engine.start_views = await engine.get_views()
    msg = await update.message.reply_text("🔥 ስራ ተጀመረ...")
    context.application.create_task(work(msg))

async def handle_msg(update, context):
    txt = update.message.text.strip()
    if txt.startswith("http"):
        engine.custom_urls.append(txt)
        await update.message.reply_text("✅ API URL ተጨምሯል!")
    else:
        found = re.findall(r"\d{1,3}(?:\.\d{1,3}){3}(?::\d{1,5})?", txt)
        if found:
            engine.custom_ips.extend([('socks5', p) for p in found])
            await update.message.reply_text(f"✅ {len(found)} IPs ተቀብያለሁ!")

if __name__ == "__main__":
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("stop", lambda u,c: setattr(engine, 'is_running', False)))
    app.add_handler(CommandHandler("reset", lambda u,c: (engine.proxies.clear(), engine.custom_urls.clear(), engine.custom_ips.clear())))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    app.run_polling()
