import asyncio, aiohttp, re, random, time
from datetime import timedelta
from aiohttp_socks import ProxyConnector
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- CONFIG ---
BOT_TOKEN = "8254387734:AAEd4VK_abdQuwgbFEiadoqj7UwlxDpmg3A"

# ዋና የፕሮክሲ ምንጮች
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
        self.custom_urls = []
        self.custom_ips = []
        self.sem = asyncio.Semaphore(2500) # ያው የቀድሞው Extreme Speed ፍጥነት

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
            for url in all_srcs:
                try:
                    async with s.get(url, timeout=10) as r:
                        content = await r.text()
                        found = re.findall(r"\d{1,3}(?:\.\d{1,3}){3}(?::\d{1,5})?", content)
                        temp.extend([('socks5', p) for p in found])
                except: pass
        self.proxies = list(set(temp))
        random.shuffle(self.proxies)

    async def hit(self, pt, p):
        async with self.sem:
            if not self.is_running: return
            try:
                conn = ProxyConnector.from_url(f"{pt}://{p}")
                # ቴሌግራም ጥያቄውን እንዲቀበለው የተደረገ ማስተካከያ
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
                    'Referer': f'https://t.me/{self.channel}/{self.post_id}?embed=1',
                    'X-Requested-With': 'XMLHttpRequest'
                }
                async with aiohttp.ClientSession(connector=conn, timeout=aiohttp.ClientTimeout(total=7, connect=3)) as s:
                    async with s.get(f"https://t.me/{self.channel}/{self.post_id}?embed=1", headers=headers) as r:
                        token = re.search(r'data-view="([^"]+)"', await r.text())
                        if token:
                            async with s.post(f"https://t.me/v/?views={token.group(1)}", headers=headers) as vr:
                                if "true" in await vr.text(): self.success += 1
            except: pass

engine = ViewEngine()

async def work(msg):
    while engine.is_running:
        engine.current_views = await engine.get_views()
        added = max(0, engine.current_views - engine.start_views)
        
        if engine.current_views >= (engine.start_views + engine.target):
            engine.is_running = False
            await msg.edit_text(f"✅ ተጠናቋል!\nጠቅላላ ቪው: {engine.current_views}")
            break

        prog = min(100, int((added / engine.target) * 100)) if engine.target > 0 else 0
        bar = "▓" * (prog // 10) + "░" * (10 - (prog // 10))
        elapsed = time.time() - engine.start_time
        speed = int(added / (elapsed / 60)) if elapsed > 0 else 0
        rem_time = str(timedelta(seconds=int((engine.target - added) / (added / elapsed)))) if added > 0 else "..."

        text = (f"🚀 **ULTRA TURBO ACTIVATED**\n"
                f"━━━━━━━━━━━━━━━\n"
                f"📊 Progress: [{bar}] {prog}%\n"
                f"✅Views: `{engine.current_views}` | 🎯Target: `{engine.start_views + engine.target}`\n"
                f"⚡Speed: `{speed} views/min`\n"
                f"🕒Rem: `{rem_time}`\n"
                f"━━━━━━━━━━━━━━━\n"
                f"🛠 Success Logs: {engine.success}")
        try: await msg.edit_text(text, parse_mode="Markdown")
        except: pass
        
        await engine.scrape_all()
        # ከፍተኛ የፕሮክሲ ፍሰት - ያው ቅድሙ 3000
        tasks = [engine.hit(pt, p) for pt, p in engine.proxies[:3000]]
        if tasks:
            await asyncio.gather(*tasks)
        await asyncio.sleep(1)

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 3: return
    if engine.is_running: return await update.message.reply_text("⚠️ ቦቱ ስራ ላይ ነው!")
    
    engine.channel, engine.post_id, engine.target = context.args[0].replace("@",""), int(context.args[1]), int(context.args[2])
    engine.is_running, engine.success, engine.start_time = True, 0, time.time()
    engine.start_views = await engine.get_views()
    msg = await update.message.reply_text("🔥 ፍጥነት እየጨመረ ነው...")
    context.application.create_task(work(msg))

async def handle_msg(update, context):
    txt = update.message.text
    if txt.startswith("http"):
        engine.custom_urls.append(txt)
        await update.message.reply_text("✅ አዲስ API URL ተጨምሯል!")
    else:
        found = re.findall(r"\d{1,3}(?:\.\d{1,3}){3}(?::\d{1,5})?", txt)
        if found:
            engine.custom_ips.extend([('socks5', p) for p in found])
            await update.message.reply_text(f"✅ {len(found)} ፕሮክሲዎች ተቀብያለሁ!")

async def stop(update, context):
    engine.is_running = False
    await update.message.reply_text("🛑 ስራው ተቋርጧል!")

if __name__ == "__main__":
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_msg))
    app.run_polling()
