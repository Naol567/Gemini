import asyncio, aiohttp, re, random, time
from aiohttp_socks import ProxyConnector
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- CONFIG ---
BOT_TOKEN = "8254387734:AAEd4VK_abdQuwgbFEiadoqj7UwlxDpmg3A"

# አዳዲስ እና ፈጣን የፕሮክሲ ምንጮች (GitHub ያልሆኑ)
NEW_SOURCES = [
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5&timeout=5000&country=all",
    "https://proxyspace.pro/socks5.txt",
    "https://api.openproxylist.xyz/socks5.txt",
    "https://www.proxy-list.download/api/v1/get?type=socks5",
    "https://www.proxyscan.io/download?type=socks5"
]

class ViewEngine:
    def __init__(self):
        self.is_running = False
        self.channel, self.post_id, self.target = "", 0, 0
        self.success, self.start_views, self.current_views = 0, 0, 0
        self.start_time = None
        self.proxies = []
        self.sem = asyncio.Semaphore(2000) # ያኔ የሰራው ፍጥነት

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

    async def refresh_proxies(self):
        """አዳዲስ ፕሮክሲዎችን ከምንጮች መሰብሰብ"""
        temp = []
        async with aiohttp.ClientSession() as s:
            for url in NEW_SOURCES:
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
                # ያኔ ሰርቶልኛል ያልከው ዋናው Header (ቁልፉ ይሄ ነው)
                h = {
                    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15',
                    'Referer': f'https://t.me/{self.channel}/{self.post_id}?embed=1',
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': '*/*',
                    'Accept-Language': 'en-US,en;q=0.9'
                }
                async with aiohttp.ClientSession(connector=conn, timeout=aiohttp.ClientTimeout(total=5, connect=2)) as s:
                    async with s.get(f"https://t.me/{self.channel}/{self.post_id}?embed=1", headers=h) as r:
                        res = await r.text()
                        token = re.search(r'data-view="([^"]+)"', res)
                        if token:
                            # እውነተኛ ቪው ለማስቆጠር የሚደረግ ፖስት
                            async with s.post(f"https://t.me/v/?views={token.group(1)}", headers=h) as vr:
                                if "true" in await vr.text():
                                    self.success += 1
            except: pass

engine = ViewEngine()

async def work(msg):
    while engine.is_running:
        # የቪው ብዛት ማረጋገጥ
        v = await engine.get_views()
        if v > 0: engine.current_views = v
        
        added = max(0, engine.current_views - engine.start_views)
        if engine.current_views >= (engine.start_views + engine.target):
            engine.is_running = False
            await msg.edit_text(f"✅ ስራ ተጠናቋል!\nአጠቃላይ ቪው: {engine.current_views}")
            break

        elapsed = time.time() - engine.start_time
        speed = int(added / (elapsed / 60)) if elapsed > 0 else 0
        
        status = (f"🔥 **NON-GITHUB TURBO MODE**\n"
                  f"━━━━━━━━━━━━━━━\n"
                  f"📈 Views: `{engine.current_views}`\n"
                  f"⚡ Speed: `{speed} v/min` | ✅ Success: `{engine.success}`\n"
                  f"📡 Fresh Pool: `{len(engine.proxies)}` \n"
                  f"━━━━━━━━━━━━━━━")
        try: await msg.edit_text(status, parse_mode="Markdown")
        except: pass
        
        # በየዙሩ አዳዲስ ፕሮክሲዎችን ማምጣት
        await engine.refresh_proxies()
        
        # ስራውን ማስጀመር
        tasks = [engine.hit(pt, p) for pt, p in engine.proxies[:2500]]
        if tasks: await asyncio.gather(*tasks)
        await asyncio.sleep(0.5)

async def add(update, context):
    if len(context.args) < 3:
        return await update.message.reply_text("ትክክለኛ አጠቃቀም: `/add channel post_id target`")
    
    engine.channel = context.args[0].replace("@","")
    engine.post_id = int(context.args[1])
    engine.target = int(context.args[2])
    engine.is_running, engine.success, engine.start_time = True, 0, time.time()
    engine.start_views = await engine.get_views()
    
    msg = await update.message.reply_text("🚀 አዳዲስ ምንጮችን በመጠቀም ስራ ተጀመረ...")
    context.application.create_task(work(msg))

if __name__ == "__main__":
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("stop", lambda u,c: setattr(engine, 'is_running', False)))
    app.run_polling()
