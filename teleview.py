import aiohttp, asyncio
from re import search, compile
from aiohttp_socks import ProxyConnector
from argparse import ArgumentParser
from os import system, name
from threading import Thread
from time import sleep
import random

user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36"
REGEX = compile(r"\d{1,3}(?:\.\d{1,3}){3}(?::\d{1,5})?")

# የፕሮክሲ ምንጮች (ሁሉንም አይነት ፕሮቶኮል የያዙ)
AUTO_PROXY_SOURCES = [
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=10000",
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks4&timeout=10000",
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5&timeout=10000",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks4.txt",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/officialputuid/KangProxy/KangProxy/http/http.txt",
    "https://proxyspace.pro/http.txt",
    "https://proxyspace.pro/socks4.txt",
    "https://proxyspace.pro/socks5.txt"
]

class Telegram:
    def __init__(self, channel: str, post: int, amount: int) -> None:
        self.tasks = 100 
        self.channel = channel
        self.post = post
        self.amount = amount
        self.sucsess_sent = 0
        self.proxy_error = 0
        self.token_error = 0
        self.proxies = []

    async def scrap_all(self):
        self.proxies.clear()
        async with aiohttp.ClientSession() as session:
            tasks = [self.fetch(session, url) for url in AUTO_PROXY_SOURCES]
            await asyncio.gather(*tasks)
        random.shuffle(self.proxies)

    async def fetch(self, session, url):
        try:
            async with session.get(url, timeout=10) as resp:
                text = await resp.text()
                found = REGEX.findall(text)
                # ፕሮቶኮሉን መለየት
                p_type = 'socks5' if 'socks5' in url else ('socks4' if 'socks4' in url else 'http')
                for p in found:
                    self.proxies.append((p_type, p))
        except: pass

    async def request(self, proxy: str, proxy_type: str):
        if self.sucsess_sent >= self.amount: return
        try:
            connector = ProxyConnector.from_url(f'{proxy_type}://{proxy}')
            # unsafe=True ኩኪዎችን ለማንኛውም domain እንዲቀበል ያደርጋል
            jar = aiohttp.CookieJar(unsafe=True) 
            async with aiohttp.ClientSession(connector=connector, cookie_jar=jar) as session:
                # 1. መጀመሪያ ፖስቱን ይጎበኛል (stel_ssid ኩኪ ለማግኘት)
                async with session.get(
                    f'https://t.me/{self.channel}/{self.post}?embed=1&mode=tme', 
                    headers={'referer': f'https://t.me/{self.channel}/{self.post}', 'user-agent': user_agent},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as embed_response:
                    
                    html = await embed_response.text()
                    token = search(r'data-view="([^"]+)"', html)
                    
                    if token:
                        # 2. ቪው መላክ (ኩኪው አብሮ ይሄዳል)
                        async with session.post(
                            f'https://t.me/v/?views={token.group(1)}', 
                            headers={
                                'referer': f'https://t.me/{self.channel}/{self.post}?embed=1&mode=tme',
                                'user-agent': user_agent, 'x-requested-with': 'XMLHttpRequest'
                            }, timeout=aiohttp.ClientTimeout(total=10)
                        ) as v_resp:
                            if (await v_resp.text() == "true"):
                                self.sucsess_sent += 1
        except:
            self.proxy_error += 1

    async def run_auto_tasks(self):
        while self.sucsess_sent < self.amount:
            print(f" [!] አዳዲስ ፕሮክሲዎች እየተፈለጉ ነው...")
            await self.scrap_all()
            
            if not self.proxies:
                await asyncio.sleep(5); continue

            # ፕሮክሲዎቹን በቡድን (Chunks) መላክ
            for i in range(0, len(self.proxies), self.tasks):
                if self.sucsess_sent >= self.amount: break
                batch = self.proxies[i:i+self.tasks]
                tasks_list = [self.request(p, pt) for pt, p in batch]
                await asyncio.gather(*tasks_list)
            
            await asyncio.sleep(2)

    def cli(self):
        while self.sucsess_sent < self.amount:
            system('cls' if name=='nt' else 'clear')
            print(f"""
    ======================================
       TELEGRAM VIEWS BOT - FINAL FIX
    ======================================
    Target: @{self.channel}/{self.post}
    Success: {self.sucsess_sent} / {self.amount}
    Errors: {self.proxy_error}
    ======================================
    """)
            sleep(2)

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument('-c', '--channel', required=True)
    parser.add_argument('-pt', '--post', required=True, type=int)
    parser.add_argument('-m', '--mode', default='auto')
    parser.add_argument('-a', '--amount', default=1000, type=int)
    args = parser.parse_args()

    api = Telegram(args.channel, args.post, args.amount)
    Thread(target=api.cli, daemon=True).start()
    asyncio.run(api.run_auto_tasks())
