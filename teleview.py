import asyncio, aiohttp, re, random, time
from datetime import timedelta
from aiohttp_socks import ProxyConnector
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- CONFIG ---
BOT_TOKEN = "8254387734:AAEd4VK_abdQuwgbFEiadoqj7UwlxDpmg3A"

# የቀድሞዎቹ ቋሚ ምንጮች (አልተወገዱም!)
SOURCES = [
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5&timeout=5000",
    "https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&sort_by=lastChecked&sort_type=desc",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
    "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/socks5.txt",
    "https://proxyspace.pro/socks5.txt"
]

class ViewEngine:
    def __init__(self):
        self.is_running = False
        self.channel, self.post_id, self.target = "", 0, 0
        self.success, self.start_views, self.current_views = 0, 0, 0
        self.start_time = None
        self.proxies = [] 
        self.custom_ips = []
        self.sem = asyncio.Semaphore(2500) # ያው Extreme Speed

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

    async def scrape_fixed_sources(self):
        temp = []
        async with aiohttp.ClientSession() as s:
            for url in SOURCES:
                try:
                    async with s.get(url, timeout=10) as r:
                        content = await r.text()
                        found = re.findall(r"\d{1,3}(?:\.\d{1,3}){3}(?::\d{1,5})?", content)
                        temp.extend([('socks5', p) for p in found])
                except: pass
        return temp

    async def scan_github_repo(self, repo_url):
        repo_path = repo_url.replace("https://github.com/", "").strip("/")
        api_url = f"https://api.github.com/repos/{repo_path}/contents"
        found_proxies = []
        async with aiohttp.ClientSession() as s:
            async def fetch_recursive(url):
                try:
                    async with s.get(url, timeout=10) as r:
                        items = await r.json()
                        if not isinstance(items, list): return
                        for item in items:
                            if item['type'] == 'file' and item['name'].endswith(('.txt', '.list')):
                                async with s.get(item['download_url']) as fr:
                                    text = await fr.text()
                                    ips = re.findall(r"\d{1,3}(?:\.\d{1,3}){3}(?::\d{1,5})?", text)
                                    found_proxies.extend([('socks5', p) for p in ips])
                            elif item['type'] == 'dir':
                                await fetch_recursive(item['url'])
                except: pass
            await fetch_recursive(api_url)
        return found_proxies

    async def hit(self, pt, p):
        async with self.sem:
            if not self.is_running: return
            try:
                conn = ProxyConnector.from_url(f"{pt}://{p}")
                h = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                    'Referer': f'https://t.me/{self.channel}/{self.post_id}?embed=1',
                    'X-Requested-With': 'XMLHttpRequest'
                }
                async with aiohttp.ClientSession(connector=conn, timeout=aiohttp.ClientTimeout(total=7)) as s:
                    async with s.get(f"https://t.me/{self.channel}/{self.post_id}?embed=1", headers=h) as r:
                        token = re.search(r'data-view="([^"]+)"', await r.text())
                        if token:
                            async with s.post(f"https://t.me/v/?views={token.group(1)}", headers=h) as vr:
                                if "true" in await vr.text(): self.success += 1
            except: pass

engine = ViewEngine()

async def work(msg):
    while engine.is_running:
        curr = await engine.get_views()
        if curr > 0: engine.current_views = curr
        
        added = max(0, engine.current_views - engine.start_views)
        if engine.current_views >= (engine.start_views + engine.target):
            engine.is_running = False
            await msg.edit_text(f"✅ ተጠናቋል! Views: {engine.current_views}")
            break

        elapsed = time.time() - engine.start_time
        speed = int(added / (elapsed / 60)) if elapsed > 0 else 0
        
        text = (f"🚀 **ULTRA TURBO ACTIVATED**\n"
                f"━━━━━━━━━━━━━━━\n"
                f"✅ Views: `{engine.current_views}`\n"
                f"⚡ Speed: `{speed} v/min`\n"
                f"🛠 Success: `{engine.success}`\n"
                f"📡 Proxies: `{len(engine.proxies)}`\n"
                f"━━━━━━━━━━━━━━━")
        try: await msg.edit_text(text, parse_mode="Markdown")
        except: pass
        
        # ስራውን ማሰማራት
        tasks = [engine.hit(pt, p) for pt, p in engine.proxies[:3000]]
        if tasks: await asyncio.gather(*tasks)
        await asyncio.sleep(1)

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    
    if "github.com" in txt:
        status_msg = await update.message.reply_text("🔍 GitHub Repo እየመረመርኩ ነው...")
        repo_proxies = await engine.scan_github_repo(txt)
        fixed_proxies = await engine.scrape_fixed_sources()
        engine.proxies = list(set(repo_proxies + fixed_proxies))
        await status_msg.edit_text(f"✅ ምርመራ ተጠናቋል!\n\n📊 ከ GitHub: **{len(repo_proxies)}**\n🌐 ከ SOURCES: **{len(fixed_proxies)}**\n🎯 ጠቅላላ: **{len(engine.proxies)}** ፕሮክሲዎች ተገኝተዋል።")
    else:
        ips = re.findall(r"\d{1,3}(?:\.\d{1,3}){3}(?::\d{1,5})?", txt)
        if ips:
            engine.proxies.extend([('socks5', p) for p in ips])
            await update.message.reply_text(f"✅ {len(ips)} አይፒዎች ተጨምረዋል። ጠቅላላ: {len(engine.proxies)}")

async def add(update, context):
    if not engine.proxies:
        # ገና ፕሮክሲ ካልተጫነ ቋሚዎቹን ጫን
        await update.message.reply_text("🔄 ፕሮክሲዎችን ከ SOURCES እያመጣሁ ነው...")
        engine.proxies = await engine.scrape_fixed_sources()
        
    if len(context.args) < 3: return
    engine.channel, engine.post_id, engine.target = context.args[0].replace("@",""), int(context.args[1]), int(context.args[2])
    engine.is_running, engine.success, engine.start_time = True, 0, time.time()
    engine.start_views = await engine.get_views()
    msg = await update.message.reply_text("🚀 ስራ ተጀመረ...")
    context.application.create_task(work(msg))

if __name__ == "__main__":
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("stop", lambda u,c: setattr(engine, 'is_running', False)))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_input))
    app.run_polling()
