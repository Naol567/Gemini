import aiohttp, asyncio
from re import search, compile
from aiohttp_socks import ProxyConnector
from argparse import ArgumentParser
from os import system, name
from threading import Thread
from time import sleep

user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36"
REGEX = compile(r"\d{1,3}(?:\.\d{1,3}){3}(?::\d{1,5})?")

# የፕሮክሲ ምንጮች (አንተ የላክካቸው)
AUTO_PROXY_SOURCES = [
    "https://raw.githubusercontent.com/javadbazokar/PROXY-List/refs/heads/main/http.txt",
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/http/data.txt",
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/officialputuid/KangProxy/KangProxy/http/http.txt",
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks4.txt"
]

class Telegram:
    def __init__(self, channel: str, post: int):
        self.tasks = 225  # የቅድሙ ፍጥነት
        self.channel = channel
        self.post = post
        self.sucsess_sent = 0
        self.proxy_error = 0

    async def request(self, proxy: str, proxy_type: str):
        try:
            # የቅድሙ የ Connector አጠቃቀም
            if proxy_type == 'socks4': connector = ProxyConnector.from_url(f'socks4://{proxy}')
            elif proxy_type == 'socks5': connector = ProxyConnector.from_url(f'socks5://{proxy}')
            else: connector = ProxyConnector.from_url(f'http://{proxy}')
            
            jar = aiohttp.CookieJar(unsafe=True)
            async with aiohttp.ClientSession(cookie_jar=jar, connector=connector) as session:
                async with session.get(
                    f'https://t.me/{self.channel}/{self.post}?embed=1&mode=tme', 
                    headers={'referer': f'https://t.me/{self.channel}/{self.post}', 'user-agent': user_agent},
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as embed_response:
                    
                    if jar.filter_cookies(embed_response.url).get('stel_ssid'):
                        html = await embed_response.text()
                        views_token = search('data-view="([^"]+)"', html)
                        
                        if views_token:
                            views_response = await session.post(
                                'https://t.me/v/?views=' + views_token.group(1), 
                                headers={
                                    'referer': f'https://t.me/{self.channel}/{self.post}?embed=1&mode=tme',
                                    'user-agent': user_agent, 'x-requested-with': 'XMLHttpRequest'
                                }, timeout=aiohttp.ClientTimeout(total=5)
                            )
                            if (await views_response.text() == "true"):
                                self.sucsess_sent += 1
        except:
            self.proxy_error += 1

    def run_auto_tasks(self):
        while True:
            # ፕሮክሲዎችን በየዙሩ መፈለግ
            auto = Auto()
            if not auto.proxies:
                sleep(5); continue

            async def inner(proxies_list):
                # የቅድሙ asyncio.wait አጠቃቀም
                await asyncio.wait([asyncio.create_task(self.request(p, pt)) for pt, p in proxies_list])

            # ፕሮክሲዎቹን በ 225 Tasks መከፋፈል
            chunks = [auto.proxies[i:i+self.tasks] for i in range(0, len(auto.proxies), self.tasks)]
            for chunk in chunks:
                asyncio.run(inner(chunk))
            
            sleep(2)

    def cli(self):
        while True:
            system('cls' if name=='nt' else 'clear')
            print(f"--- Telegram Views (Original Structure) ---\n")
            print(f"Target: @{self.channel}/{self.post}")
            print(f"Success: {self.sucsess_sent}")
            print(f"Errors: {self.proxy_error}")
            sleep(2)

class Auto:
    def __init__(self):
        self.proxies = []
        asyncio.run(self.init())

    async def scrap(self, url):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    text = await resp.text()
                    found = REGEX.findall(text)
                    p_type = 'socks5' if 'socks5' in url else ('socks4' if 'socks4' in url else 'http')
                    for p in found:
                        self.proxies.append((p_type, p))
        except: pass

    async def init(self):
        tasks = [asyncio.create_task(self.scrap(url)) for url in AUTO_PROXY_SOURCES]
        if tasks: await asyncio.wait(tasks)

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument('-c', '--channel', required=True)
    parser.add_argument('-pt', '--post', required=True, type=int)
    parser.add_argument('-m', '--mode', default='auto')
    args = parser.parse_args()

    api = Telegram(args.channel, args.post)
    Thread(target=api.cli, daemon=True).start()
    api.run_auto_tasks()
