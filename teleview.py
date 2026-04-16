import asyncio
import aiohttp
import re
import random
from aiohttp_socks import ProxyConnector
import os

SOURCES = [
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5&timeout=10000",
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
    "https://raw.githubusercontent.com/Zaeem20/FREE_PROXIES_LIST/master/socks5.txt",
    "https://raw.githubusercontent.com/officialputuid/KangProxy/KangProxy/socks5/socks5.txt",
    "https://proxyspace.pro/socks5.txt"
]

class SMMUltra:
    def __init__(self, channel, post, target):
        self.channel = channel
        self.post = post
        self.target = target
        self.success = 0
        self.sem = asyncio.Semaphore(1000)
        self.uas = [
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Mobile/15E148 Safari/604.1",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ]

    async def get_proxies(self):
        proxies = []
        async with aiohttp.ClientSession() as s:
            for url in SOURCES:
                try:
                    async with s.get(url, timeout=10) as r:
                        text = await r.text()
                        found = re.findall(r"\d{1,3}(?:\.\d{1,3}){3}(?::\d{1,5})?", text)
                        proxies.extend([('socks5', p) for p in found])
                except: pass
        return list(set(proxies))

    async def send_view(self, ptype, proxy):
        async with self.sem:
            if self.success >= self.target: return
            try:
                conn = ProxyConnector.from_url(f"{ptype}://{proxy}")
                async with aiohttp.ClientSession(connector=conn, timeout=aiohttp.ClientTimeout(total=10, connect=3)) as s:
                    headers = {
                        'User-Agent': random.choice(self.uas),
                        'Referer': f'https://t.me/{self.channel}/{self.post}?embed=1',
                        'X-Requested-With': 'XMLHttpRequest'
                    }
                    async with s.get(f"https://t.me/{self.channel}/{self.post}?embed=1", headers=headers) as r:
                        token = re.search(r'data-view="([^"]+)"', await r.text())
                        if token:
                            async with s.post(f"https://t.me/v/?views={token.group(1)}", headers=headers) as vr:
                                if "true" in await vr.text(): self.success += 1
            except: pass

    async def run(self):
        print(f"🚀 ቦቱ ተጀምሯል! Target: {self.target} views")
        while self.success < self.target:
            proxies = await self.get_proxies()
            if not proxies:
                await asyncio.sleep(5); continue
            random.shuffle(proxies)
            await asyncio.gather(*[self.send_view(pt, p) for pt, p in proxies])
            print(f"📈 አሁን የደረሰው ቪው: {self.success}")
            await asyncio.sleep(2)

if __name__ == "__main__":
    # እዚህ ጋር የቻናልህን እና የፖስቱን መረጃ ቀይር
    target_channel = "xauusd_x1"
    target_post = 164
    target_amount = 5000 

    bot = SMMUltra(target_channel, target_post, target_amount)
    asyncio.run(bot.run())
