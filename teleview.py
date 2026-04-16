# // Telegram Auto Views 2024 - Optimized Version \\
# Fixed for automatic proxy scraping from provided links

import aiohttp, asyncio
from re import search, compile
from aiohttp_socks import ProxyConnector
from argparse import ArgumentParser
from os import system, name
from threading import Thread
from time import sleep

user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36"
# IP:PORT ፎርማትን ለመለየት
REGEX = compile(r"\d{1,3}(?:\.\d{1,3}){3}(?::\d{1,5})?")

# አንተ የላክካቸው የፕሮክሲ ምንጮች
AUTO_PROXY_SOURCES = [
    "https://raw.githubusercontent.com/javadbazokar/PROXY-List/refs/heads/main/http.txt",
    "https://raw.githubusercontent.com/proxifly/free-proxy-list/main/proxies/protocols/http/data.txt",
    "https://raw.githubusercontent.com/zloi-user/hideip.me/main/http.txt",
    "https://openproxylist.xyz/http.txt",
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/officialputuid/KangProxy/KangProxy/http/http.txt",
    "https://raw.githubusercontent.com/tuanminpay/live-proxy/master/http.txt",
    "https://raw.githubusercontent.com/mmpx12/proxy-list/master/http.txt",
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt"
]

class Telegram:
    def __init__(self, channel: str, post: int) -> None:
        self.tasks = 150 # በአንድ ጊዜ የሚላኩ ቪውዎች ብዛት
        self.channel = channel
        self.post = post
        self.sucsess_sent = 0
        self.failled_sent = 0
        self.proxy_error = 0
        self.token_error = 0
        self.cookie_error = 0

    async def request(self, proxy: str, proxy_type: str):
        try:
            if proxy_type == 'socks4': connector = ProxyConnector.from_url(f'socks4://{proxy}')
            elif proxy_type == 'socks5': connector = ProxyConnector.from_url(f'socks5://{proxy}')
            else: connector = ProxyConnector.from_url(f'http://{proxy}')
            
            async with aiohttp.ClientSession(connector=connector) as session:
                # 1. ፖስቱን በመጎብኘት Token መውሰድ
                async with session.get(
                    f'https://t.me/{self.channel}/{self.post}?embed=1&mode=tme', 
                    headers={'user-agent': user_agent},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    html = await response.text()
                    token = search(r'data-view="([^"]+)"', html)
                    
                    if token:
                        # 2. ቪው መላክ
                        async with session.post(
                            f'https://t.me/v/?views={token.group(1)}', 
                            headers={
                                'referer': f'https://t.me/{self.channel}/{self.post}?embed=1&mode=tme',
                                'user-agent': user_agent,
                                'x-requested-with': 'XMLHttpRequest'
                            }, timeout=aiohttp.ClientTimeout(total=10)
                        ) as v_resp:
                            if (await v_resp.text() == "true"):
                                self.sucsess_sent += 1
                            else:
                                self.failled_sent += 1
                    else:
                        self.token_error += 1
        except:
            self.proxy_error += 1

    def run_auto_tasks(self):
        while True:
            auto = Auto()
            if not auto.proxies:
                print(" [!] No proxies found, retrying...")
                sleep(5); continue

            async def inner(proxies_list):
                tasks_list = [asyncio.create_task(self.request(p, pt)) for pt, p in proxies_list]
                await asyncio.wait(tasks_list)

            # ፕሮክሲዎቹን በቡድን (Chunks) መላክ
            chunks = [auto.proxies[i:i+self.tasks] for i in range(0, len(auto.proxies), self.tasks)]
            for chunk in chunks:
                asyncio.run(inner(chunk))
            
            print(f" [!] Finished one cycle. Total Success: {self.sucsess_sent}")
            sleep(2)

    def cli(self):
        logo = "--- Telegram Auto Views 2024 (Optimized) ---"
        while True:
            system('cls' if name=='nt' else 'clear')
            print(logo)
            print(f"""
        TARGET: @{self.channel}/{self.post}
        
        SUCCESS: {self.sucsess_sent}
        FAILED:  {self.failled_sent}
        
        ERRORS:
        Proxy Error:  {self.proxy_error}
        Token Error:  {self.token_error}
            """)
            sleep(2)

class Auto:
    def __init__(self):
        self.proxies = []
        asyncio.run(self.init())

    async def scrap(self, url):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers={'user-agent': user_agent}, timeout=15) as resp:
                    text = await resp.text()
                    found = REGEX.findall(text)
                    for p in found:
                        # ለቀላልነት ሁሉንም እንደ http/socks5 መሞከር
                        p_type = 'socks5' if 'socks5' in url else 'http'
                        self.proxies.append((p_type, p))
        except:
            pass

    async def init(self):
        tasks = [asyncio.create_task(self.scrap(url)) for url in AUTO_PROXY_SOURCES]
        if tasks:
            await asyncio.wait(tasks)

if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument('-c', '--channel', required=True, help='Channel username')
    parser.add_argument('-pt', '--post', required=True, type=int, help='Post ID')
    parser.add_argument('-m', '--mode', default='auto', help='Mode (auto)')
    args = parser.parse_args()

    api = Telegram(args.channel, args.post)
    
    # UI thread
    Thread(target=api.cli, daemon=True).start()
    
    # Start process
    api.run_auto_tasks()
