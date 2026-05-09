import asyncio
import aiohttp
import re
import random
import time
from aiohttp_socks import ProxyConnector
from telegram import Update
from telegram.error import RetryAfter
from telegram.ext import Application, CommandHandler, ContextTypes

# --- CONFIG ---
BOT_TOKEN = "8254387734:AAGR0IdVPqIrIQjETI4yZIRYhSgNnLBg6uA"

# አዳዲስ እና ፈጣን የሆኑ SOCKS5 ፕሮክሲዎችን የሚያቀርቡ ምርጥ ምንጮች
PROXY_SOURCES = [
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
    "https://raw.githubusercontent.com/roosterkid/openproxylist/main/SOCKS5_RAW.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
    "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
    "https://raw.githubusercontent.com/rdavydov/proxy-list/main/proxies/socks5.txt",
    "https://raw.githubusercontent.com/prxytokyo/proxy-list/main/socks5.txt",
    "https://raw.githubusercontent.com/ErcinDogaocul/Free-Proxy-List/main/proxies/socks5.txt",
    "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/socks5.txt",
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5&timeout=5000",
    "https://www.proxy-list.download/api/v1/get?type=socks5"
]

class ViewEngine:
    def __init__(self):
        self.is_running = False
        self.channel, self.post_id, self.target = "", 0, 0
        self.success, self.start_views, self.current_views = 0, 0, 0
        self.start_time = None
        self.proxies = []
        # ፍጥነትን ለመጨመር በአንድ ጊዜ እስከ 2000 ፕሮክሲዎችን እንዲሞክር ተደርጓል
        self.sem = asyncio.Semaphore(2000) 

    async def get_views(self):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"https://t.me/{self.channel}/{self.post_id}?embed=1", timeout=5, ssl=False) as r:
                    html = await r.text()
                    m = re.search(r'class="tgme_widget_message_views">([0-9\.]+[KkMm]?)', html)
                    if m:
                        v = m.group(1).upper().replace('K', '000').replace('M', '000000').replace('.', '')
                        return int(''.join(filter(str.isdigit, v)))
        except:
            return 0
        return 0

    async def scrape_all(self):
        temp = []
        print("🔍 አዳዲስ ፕሮክሲዎችን በመሰብሰብ ላይ...")
        async with aiohttp.ClientSession() as s:
            for url in PROXY_SOURCES:
                try:
                    async with s.get(url, timeout=10, ssl=False) as r:
                        text = await r.text()
                        found = re.findall(r"\d{1,3}(?:\.\d{1,3}){3}(?::\d{1,5})?", text)
                        temp.extend([('socks5', p) for p in found])
                except: 
                    continue
        self.proxies = list(set(temp))
        random.shuffle(self.proxies)
        print(f"✅ {len(self.proxies)} ፕሮክሲዎች ተገኝተዋል!")

    async def hit(self, pt, p):
        async with self.sem:
            if not self.is_running: return
            try:
                ua = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.randint(115, 124)}.0.0.0 Safari/537.36"
                h = {
                    'User-Agent': ua,
                    'X-Requested-With': 'XMLHttpRequest',
                    'Referer': f'https://t.me/{self.channel}/{self.post_id}?embed=1',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Connection': 'keep-alive'
                }
                
                conn = ProxyConnector.from_url(f"{pt}://{p}")
                # Fail-Fast: የሞተ ፕሮክሲ ላይ ጊዜ እንዳያባክን Timeout ወደ 4 ሰከንድ ዝቅ ብሏል
                timeout = aiohttp.ClientTimeout(total=4, connect=2)
                
                async with aiohttp.ClientSession(connector=conn, timeout=timeout) as s:
                    async with s.get(f"https://t.me/{self.channel}/{self.post_id}?embed=1", headers=h, ssl=False) as r:
                        res = await r.text()
                        token = re.search(r'data-view="([^"]+)"', res)
                        
                        if token:
                            async with s.post(f"https://t.me/v/?views={token.group(1)}", headers=h, ssl=False) as vr:
                                response_text = await vr.text()
                                if "true" in response_text:
                                    self.success += 1
            except: 
                pass

engine = ViewEngine()

async def work(msg):
    last_edit_time = 0
    last_status = ""
    
    await engine.scrape_all()
    
    while engine.is_running:
        v = await engine.get_views()
        if v > 0: engine.current_views = v
        
        added = max(0, engine.current_views - engine.start_views)
        elapsed = time.time() - engine.start_time
        speed = int(added / (elapsed / 60)) if elapsed > 0 else 0
        
        status = (f"🚀 **ULTRA SPEED PROXY ENGINE**\n"
                  f"━━━━━━━━━━━━━━━\n"
                  f"📈 Views: `{engine.current_views}`\n"
                  f"✅ Success Hits: `{engine.success}`\n"
                  f"⚡ Speed: `{speed} v/min`\n"
                  f"📡 Pool: `{len(engine.proxies)}`\n"
                  f"━━━━━━━━━━━━━━━")
        
        current_time = time.time()
        # የቴሌግራም ኤዲት ሪሚት እንዳያግደው በየ 5 ሰከንዱ ብቻ ሜሴጁን አፕዴት ያደርጋል
        if (current_time - last_edit_time) > 5 and status != last_status:
            try: 
                await msg.edit_text(status, parse_mode="Markdown")
                last_edit_time = current_time
                last_status = status
            except RetryAfter as e:
                await asyncio.sleep(e.retry_after)
            except:
                pass

        if engine.current_views >= (engine.start_views + engine.target):
            engine.is_running = False
            try: await msg.edit_text(f"✅ ተጠናቋል!\nViews: {engine.current_views}")
            except: pass
            break

        # ፕሮክሲ ካለቀበት ዳግም ያወርዳል
        if len(engine.proxies) == 0:
            await engine.scrape_all()
            
        # በአንድ ጊዜ ብዙ ፕሮክሲዎችን መላክ (Batching)
        batch = engine.proxies[:2500]
        random.shuffle(batch)
        
        tasks = [engine.hit(pt, p) for pt, p in batch] 
        if tasks: 
            await asyncio.gather(*tasks)
        
        # Zero-delay: ያለምንም እረፍት ወዲያውኑ ወደ ሚቀጥለው ዙር ያልፋል
        await asyncio.sleep(0.1)

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 3:
        return await update.message.reply_text("አጠቃቀም: `/add channel post_id target`")
    
    engine.channel, engine.post_id, engine.target = context.args[0].replace("@",""), int(context.args[1]), int(context.args[2])
    engine.is_running, engine.success, engine.start_time = True, 0, time.time()
    
    msg = await update.message.reply_text("🔥 Ultra Speed Engine started. Gathering proxies...")
    engine.start_views = await engine.get_views()
    
    context.application.create_task(work(msg))

if __name__ == "__main__":
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("stop", lambda u,c: setattr(engine, 'is_running', False)))
    
    print("🤖 ቦት ተጀምሯል! ወደ ቴሌግራም ሄደህ /add ብለህ እዘዘው።")
    app.run_polling()
