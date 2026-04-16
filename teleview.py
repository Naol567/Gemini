import aiohttp, asyncio
from re import search, compile
from aiohttp_socks import ProxyConnector
from argparse import ArgumentParser
from os import name
from threading import Thread
from time import sleep
import random

user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
REGEX = compile(r"\d{1,3}(?:\.\d{1,3}){3}(?::\d{1,5})?")

# ተጨማሪ 20+ የፕሮክሲ ምንጮች
AUTO_PROXY_SOURCES = [
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all",
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks4&timeout=10000&country=all",
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5&timeout=10000&country=all",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks4.txt",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks4.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/socks5.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
    "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
    "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
    "https://raw.githubusercontent.com/sunny9577/proxy-switcher/master/proxy_list.txt",
    "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt",
    "https://raw.githubusercontent.com/officialputuid/KangProxy/KangProxy/http/http.txt",
    "https://proxyspace.pro/http.txt",
    "https://proxyspace.pro/socks4.txt",
    "https://proxyspace.pro/socks5.txt"
]

class Telegram:
    def __init__(self, channel: str, post: int, amount: int):
        self.tasks = 500  # በአንድ ጊዜ 500 ፕሮክሲ ይሞከራል
        self.channel = channel
        self.post = post
        self.amount = amount
        self.sucsess_sent = 0
        self.proxy_error = 0
        self.proxies = []

    async def scrap_all(self):
        self.proxies.clear()
        async with aiohttp.ClientSession() as session:
            tasks = [self.fetch(session, url) for url in AUTO_PROXY_SOURCES]
            await asyncio.gather(*tasks)
        self.proxies = list(set(self.proxies)) # Double የሆኑትን ለማጥፋት
        random.shuffle(self.proxies)

    async def fetch(self, session, url):
        try:
            async with session.get(url, timeout=15) as resp:
                text = await resp.text()
                found = REGEX.findall(text)
                p_type = 'socks5' if 'socks5' in url else ('socks4' if 'socks4' in url else 'http')
                for p in found:
                    self.proxies.append((p_type, p))
        except: pass

    async def request(self, proxy: str, proxy_type: str):
        if self.sucsess_sent >= self.amount: return
        try:
            connector = ProxyConnector.from_url(f'{proxy_type}://{proxy}')
            jar = aiohttp.CookieJar(unsafe=True) 
            async with aiohttp.ClientSession(connector=connector, cookie_jar=jar) as session:
                async with session.get(
                    f'https://t.me/{self.channel}/{self.post}?embed=1&mode=tme', 
                    headers={'referer': f'https://t.me/{self.channel}', 'user-agent': user_agent},
                    timeout=10
                ) as response:
                    html = await response.text()
                    token = search(r'data-view="([^"]+)"', html)
                    if token:
                        async with session.post(
                            f'https://t.me/v/?views={token.group(1)}', 
                            headers={
                                'referer': f'https://t.me/{self.channel}/{self.post}?embed=1&mode=tme',
                                'user-agent': user_agent, 'x-requested-with': 'XMLHttpRequest'
                            }, timeout=10
                        ) as v_resp:
                            if (await v_resp.text() == "true"):
                                self.sucsess_sent += 1
        except:
            self.proxy_error += 1

    async def run_auto_tasks(self):
        while self.sucsess_sent < self.amount:
            print(f" [!] {len(self.proxies)} ፕሮክሲዎች ተገኝተዋል። ሙከራ እየተደረገ ነው...")
            if not self.proxies or len(self.proxies) < 100:
                await self.scrap_all()

            for i in range(0, len(self.proxies), self.tasks):
                if self.sucsess_sent >= self.amount: break
                batch = self.proxies[i:i+self.tasks]
                await asyncio.gather(*[self.request(p, pt) for pt, p in batch])
                await asyncio.sleep(0.1) # ለ CPU እረፍት
            
            self.proxies.clear() # አሮጌዎቹን ለማጽዳት

    def cli(self):
        while self.sucsess_sent < self.amount:
            print(f"\n🚀 [ HIGH SPEED MODE ]")
            print(f"Target: @{self.channel}/{self.post}")
            print(f"Success Logs: {self.sucsess_sent} / {self.amount}")
            print(f"Proxy Errors: {self.proxy_error}")
            print(f"----------------------\n")
            sleep(10)

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument('-c', '--channel', required=True)
    parser.add_argument('-pt', '--post', required=True, type=int)
    parser.add_argument('-a', '--amount', default=5000, type=int)
    args = parser.parse_args()

    api = Telegram(args.channel, args.post, args.amount)
    Thread(target=api.cli, daemon=True).start()
    asyncio.run(api.run_auto_tasks())
