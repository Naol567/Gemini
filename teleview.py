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

class ViewEngine:
    def __init__(self):
        self.is_running = False
        self.channel, self.post_id, self.target = "", 0, 0
        self.success, self.start_views, self.current_views = 0, 0, 0
        self.start_time = None
        self.proxies = []
        self.sem = asyncio.Semaphore(800) 

    async def get_views(self):
        try:
            # We also add ssl=False here just in case your local machine is having certificate issues
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
        async with aiohttp.ClientSession() as s:
            for url in PROXY_SOURCES:
                try:
                    async with s.get(url, timeout=6, ssl=False) as r:
                        text = await r.text()
                        found = re.findall(r"\d{1,3}(?:\.\d{1,3}){3}(?::\d{1,5})?", text)
                        temp.extend([('socks5', p) for p in found])
                except: 
                    continue
        self.proxies = list(set(temp))
        random.shuffle(self.proxies)

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
                
                # Setup the SOCKS5 proxy connector
                conn = ProxyConnector.from_url(f"{pt}://{p}")
                timeout = aiohttp.ClientTimeout(total=8, connect=3)
                
                # The ClientSession will AUTOMATICALLY handle cookies between requests now
                async with aiohttp.ClientSession(connector=conn, timeout=timeout) as s:
                    # ssl=False prevents cheap proxies from crashing the request due to bad certificates
                    async with s.get(f"https://t.me/{self.channel}/{self.post_id}?embed=1", headers=h, ssl=False) as r:
                        res = await r.text()
                        token = re.search(r'data-view="([^"]+)"', res)
                        
                        if token:
                            # Send the POST request (the session automatically attaches the cookies from the GET request)
                            async with s.post(f"https://t.me/v/?views={token.group(1)}", headers=h, ssl=False) as vr:
                                if "true" in await vr.text():
                                    self.success += 1
            except: 
                pass

engine = ViewEngine()

async def work(msg):
    last_edit_time = 0
    last_status = ""
    
    while engine.is_running:
        v = await engine.get_views()
        if v > 0: engine.current_views = v
        
        added = max(0, engine.current_views - engine.start_views)
        elapsed = time.time() - engine.start_time
        speed = int(added / (elapsed / 60)) if elapsed > 0 else 0
        
        status = (f"🚀 **FIXED PROXY ENGINE**\n"
                  f"━━━━━━━━━━━━━━━\n"
                  f"📈 Views: `{engine.current_views}`\n"
                  f"✅ Success Hits: `{engine.success}`\n"
                  f"⚡ Speed: `{speed} v/min`\n"
                  f"📡 Pool: `{len(engine.proxies)}`\n"
                  f"━━━━━━━━━━━━━━━")
        
        current_time = time.time()
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

        await engine.scrape_all()
        
        tasks = [engine.hit(pt, p) for pt, p in engine.proxies[:2000]] 
        if tasks: await asyncio.gather(*tasks)
        
        await asyncio.sleep(0.5)

async def add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) < 3:
        return await update.message.reply_text("አጠቃቀም: `/add channel post_id target`")
    
    engine.channel, engine.post_id, engine.target = context.args[0].replace("@",""), int(context.args[1]), int(context.args[2])
    engine.is_running, engine.success, engine.start_time = True, 0, time.time()
    engine.start_views = await engine.get_views()
    
    msg = await update.message.reply_text("🔥 System fixed. Sending traffic...")
    context.application.create_task(work(msg))

if __name__ == "__main__":
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("stop", lambda u,c: setattr(engine, 'is_running', False)))
    app.run_polling()
