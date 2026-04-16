import asyncio, aiohttp, re, random, time
from aiohttp_socks import ProxyConnector
from telegram.ext import Application, CommandHandler, MessageHandler, filters

# --- CONFIG ---
BOT_TOKEN = "8254387734:AAEd4VK_abdQuwgbFEiadoqj7UwlxDpmg3A"

# አንተ የሰጠኸኝ ሙሉ የፕሮክሲ ዝርዝር
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

class ViewEngine:
    def __init__(self):
        self.is_running = False
        self.channel, self.post_id, self.target = "", 0, 0
        self.success, self.start_views, self.current_views = 0, 0, 0
        self.proxies = []
        self.sem = asyncio.Semaphore(2000) # ከፍተኛ ፍጥነት

    async def get_views(self):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(f"https://t.me/{self.channel}/{self.post_id}?embed=1", timeout=5) as r:
                    html = await r.text()
                    m = re.search(r'class="tgme_widget_message_views">([0-9\.]+[KkMm]?)', html)
                    if m:
                        v = m.group(1).upper().replace('K', '000').replace('M', '000000').replace('.', '')
                        return int(''.join(filter(str.isdigit, v)))
        except: return 0
        return 0

    async def scrape_all(self):
        """ሁሉንም ምንጮች በአንዴ ሰብስቦ ዳታውን ማጥራት"""
        temp = []
        async with aiohttp.ClientSession() as s:
            for url in PROXY_SOURCES:
                try:
                    async with s.get(url, timeout=10) as r:
                        if "geonode" in url: # ለ Geonode JSON አያያዝ
                            data = await r.json()
                            for p in data.get('data', []):
                                temp.append(('socks5', f"{p['ip']}:{p['port']}"))
                        else: # ለሌሎቹ በሙሉ (Text Based)
                            text = await r.text()
                            found = re.findall(r"\d{1,3}(?:\.\d{1,3}){3}(?::\d{1,5})?", text)
                            temp.extend([('socks5', p) for p in found])
                except: pass
        self.proxies = list(set(temp)) # ተመሳሳይ አይፒዎችን ማጥፋት
        random.shuffle(self.proxies)

    async def hit(self, pt, p):
        async with self.sem:
            if not self.is_running: return
            try:
                # ቴሌግራም እንዳይነቃ የተለያየ መለያ መጠቀም
                h = {
                    'User-Agent': f'Mozilla/5.0 (iPhone; CPU iPhone OS {random.randint(15,17)}_0 like Mac OS X) AppleWebKit/605.1.15',
                    'X-Requested-With': 'XMLHttpRequest',
                    'Referer': f'https://t.me/{self.channel}/{self.post_id}?embed=1'
                }
                conn = ProxyConnector.from_url(f"{pt}://{p}")
                async with aiohttp.ClientSession(connector=conn, timeout=aiohttp.ClientTimeout(total=5, connect=2)) as s:
                    async with s.get(f"https://t.me/{self.channel}/{self.post_id}?embed=1", headers=h) as r:
                        res = await r.text()
                        token = re.search(r'data-view="([^"]+)"', res)
                        if token:
                            async with s.post(f"https://t.me/v/?views={token.group(1)}", headers=h) as vr:
                                if "true" in await vr.text():
                                    self.success += 1
            except: pass

engine = ViewEngine()

async def work(msg):
    while engine.is_running:
        v = await engine.get_views()
        if v > 0: engine.current_views = v
        
        status = (f"🚀 **ULTRA MULTI-SOURCE ACTIVE**\n"
                  f"━━━━━━━━━━━━━━━\n"
                  f"📊 Views: `{engine.current_views}`\n"
                  f"✅ Success: `{engine.success}`\n"
                  f"📡 Proxy Pool: `{len(engine.proxies)}` \n"
                  f"━━━━━━━━━━━━━━━")
        try: await msg.edit_text(status, parse_mode="Markdown")
        except: pass

        if engine.current_views >= (engine.start_views + engine.target):
            engine.is_running = False
            break

        await engine.scrape_all()
        # ፕሮክሲዎቹን በከፍተኛ ፍጥነት መርጨት
        tasks = [engine.hit(pt, p) for pt, p in engine.proxies[:3000]]
        if tasks: await asyncio.gather(*tasks)
        await asyncio.sleep(1)

async def add(update, context):
    if len(context.args) < 3: return
    engine.channel, engine.post_id, engine.target = context.args[0].replace("@",""), int(context.args[1]), int(context.args[2])
    engine.is_running, engine.success = True, 0
    engine.start_views = await engine.get_views()
    msg = await update.message.reply_text("🔄 በ 30+ ምንጮች ስራ እየተጀመረ ነው...")
    context.application.create_task(work(msg))

if __name__ == "__main__":
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("add", add))
    app.add_handler(CommandHandler("stop", lambda u,c: setattr(engine, 'is_running', False)))
    app.run_polling()
