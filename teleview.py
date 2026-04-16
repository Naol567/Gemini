import asyncio
import aiohttp
import re
import random
import time
from datetime import timedelta
from aiohttp_socks import ProxyConnector
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- CONFIG ---
BOT_TOKEN = "8254387734:AAEd4VK_abdQuwgbFEiadoqj7UwlxDpmg3A"

class ViewEngine:
    def __init__(self):
        self.is_running = False
        self.channel, self.post_id, self.target = "", 0, 0
        self.success, self.start_views, self.current_views = 0, 0, 0
        self.start_time = None
        self.proxies = []
        self.custom_urls = [
            "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5&timeout=5000",
            "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
            "https://proxylist.geonode.com/api/proxy-list?limit=500&page=1&sort_by=lastChecked&sort_type=desc"
        ]
        self.custom_ips = []
        # መካከለኛ ፍጥነት (በአንድ ጊዜ 1200) - ለRailway አስተማማኝ ነው
        self.sem = asyncio.Semaphore(1200) 

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
        temp = self.custom_ips.copy()
        async with aiohttp.ClientSession() as s:
            for url in self.custom_urls:
                try:
                    async with s.get(url, timeout=5) as r:
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
                # Timeoutን በማሳጠር ፍጥነት መጨምር
                async with aiohttp.ClientSession(connector=conn, timeout=aiohttp.ClientTimeout(total=7, connect=2)) as s:
                    async with s.get(f"https://t.me/{self.channel}/{self.post_id}?embed=1") as r:
                        res_text = await r.text()
                        token = re.search(r'data-view="([^"]+)"', res_text)
                        if token:
                            async with s.post(f"https://t.me/v/?views={token.group(1)}", headers={'X-Requested-With': 'XMLHttpRequest'}) as vr:
                                if "true" in await vr.text():
                                    self.success += 1
            except: pass

    async def work(self, msg):
        while self.is_running:
            # የቪው ብዛት ማረጋገጥ
            new_v = await self.get_views()
            if new_v > 0: self.current_views = new_v
            
            added = max(0, self.current_views - self.start_views)
            
            if self.current_views >= (self.start_views + self.target):
                self.is_running = False
                await msg.edit_text(f"✅ ተጠናቋል! \nጠቅላላ ቪው: {self.current_views}")
                break

            # ሪፖርት ማሳያ
            prog = min(100, int((added / self.target) * 100)) if self.target > 0 else 0
            elapsed = time.time() - self.start_time
            speed = int(added / (elapsed / 60)) if elapsed > 0 else 0
            
            status_text = (f"🚀 **FAST TURBO ACTIVE**\n"
                           f"━━━━━━━━━━━━━━━\n"
                           f"📊 Progress: {prog}%\n"
                           f"✅ Views: `{self.current_views}`\n"
                           f"⚡ Speed: `{speed} v/min`\n"
                           f"🛠 Success: `{self.success}`\n"
                           f"━━━━━━━━━━━━━━━\n"
                           f"💡 መቆጠር ካቆመ ፕሮክሲ እየቀየርኩ ነው...")
            
            try: await msg.edit_text(status_text, parse_mode="Markdown")
            except: pass

            # ፕሮክሲዎችን ማደስ
            await self.scrape_all()
            
            # ስራውን በቡድን (Batch) መላክ
            batch_size = 1000
            for i in range(0, len(self.proxies), batch_size):
                if not self.is_running: break
                batch = self.proxies[i:i+batch_size]
                await asyncio.gather(*[self.hit(pt, p) for pt, p in batch])
                await asyncio.sleep(0.5) # ለ Railway ትንፋሽ መስጫ

engine = ViewEngine()

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("👋 ቦቱ ዝግጁ ነው! \n`/add channel post_id target` ይላኩ።")

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 3: return await update.message.reply_text("💡 `/add xauusd_x1 164 1000` ይበሉ")
    if engine.is_running: return await update.message.reply_text("⚠️ ቦቱ ስራ ላይ ነው!")
    
    engine.channel, engine.post_id, engine.target = context.args[0].replace("@",""), int(context.args[1]), int(context.args[2])
    engine.is_running, engine.success, engine.start_time = True, 0, time.time()
    engine.start_views = await engine.get_views()
    
    msg = await update.message.reply_text("🔥 ቪው መላክ ተጀመረ...")
    context.application.create_task(engine.work(msg))

async def stop(update, context):
    engine.is_running = False
    await update.message.reply_text("🛑 ቆሟል።")

async def handle_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = update.message.text.strip()
    if txt.startswith("http"):
        engine.custom_urls.append(txt)
        await update.message.reply_text("✅ API URL ተጨምሯል።")
    else:
        found = re.findall(r"\d{1,3}(?:\.\d{1,3}){3}(?::\d{1,5})?", txt)
        if found:
            engine.custom_ips.extend([('socks5', p) for p in found])
            await update.message.reply_text(f"✅ {len(found)} ፕሮክሲዎች ተቀብያለሁ።")

if __name__ == "__main__":
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_input))
    app.run_polling()
