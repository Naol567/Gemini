"""
view_booster.py
───────────────
Telegram post view booster using proxy rotation.
Integrates with your existing python-telegram-bot setup.

How it works:
  1. Fetch embed page → extract __token from JS
  2. POST to https://t.me/v/?views=<token> through proxies
  3. Each successful POST = +1 view on the post
"""

import asyncio
import re
import logging
import aiohttp
from typing import Optional

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────
# PROXY SCRAPER SOURCES (free, public lists)
# ─────────────────────────────────────────────
PROXY_SOURCES = {
    "http": [
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
        "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
        "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/proxies.txt",
        "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    ],
    "socks4": [
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt",
        "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt",
    ],
    "socks5": [
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
        "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
    ],
}

# ─────────────────────────────────────────────
# TOKEN EXTRACTOR
# ─────────────────────────────────────────────
async def fetch_view_token(
    channel: str,
    post_id: int,
    session: aiohttp.ClientSession,
    proxy: Optional[str] = None,
) -> Optional[str]:
    """Fetch the view token from Telegram embed page."""
    url = f"https://t.me/{channel}/{post_id}?embed=1&mode=tme"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://telegram.org/",
    }
    try:
        async with session.get(
            url, headers=headers, proxy=proxy, timeout=aiohttp.ClientTimeout(total=10)
        ) as resp:
            if resp.status != 200:
                return None
            html = await resp.text()
            match = re.search(r'data-view="([^"]+)"', html)
            if not match:
                # fallback pattern
                match = re.search(r'"views"\s*:\s*"([^"]+)"', html)
            return match.group(1) if match else None
    except Exception:
        return None


# ─────────────────────────────────────────────
# SEND ONE VIEW
# ─────────────────────────────────────────────
async def send_view(
    token: str,
    session: aiohttp.ClientSession,
    proxy: Optional[str] = None,
) -> bool:
    """Send a single view using the token."""
    url = f"https://t.me/v/?views={token}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        ),
        "X-Requested-With": "XMLHttpRequest",
        "Referer": "https://telegram.org/",
    }
    try:
        async with session.post(
            url, headers=headers, proxy=proxy, timeout=aiohttp.ClientTimeout(total=8)
        ) as resp:
            text = await resp.text()
            return resp.status == 200 and "true" in text.lower()
    except Exception:
        return False


# ─────────────────────────────────────────────
# PROXY SCRAPER
# ─────────────────────────────────────────────
async def scrape_proxies(proxy_type: str = "http") -> list[str]:
    """Scrape free proxies from public sources."""
    sources = PROXY_SOURCES.get(proxy_type, PROXY_SOURCES["http"])
    proxies = []
    prefix = proxy_type if proxy_type != "http" else "http"

    async with aiohttp.ClientSession() as session:
        for url in sources:
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        text = await resp.text()
                        for line in text.strip().splitlines():
                            line = line.strip()
                            if line and ":" in line:
                                proxies.append(f"{prefix}://{line}")
            except Exception:
                continue

    # deduplicate
    proxies = list(set(proxies))
    logger.info(f"Scraped {len(proxies)} {proxy_type} proxies")
    return proxies


# ─────────────────────────────────────────────
# MAIN BOOST ENGINE
# ─────────────────────────────────────────────
async def boost_views(
    channel: str,
    post_id: int,
    target_views: int = 100,
    proxy_type: str = "http",
    proxy_list: Optional[list[str]] = None,
    concurrency: int = 50,
    progress_callback=None,  # async callable(sent, total, failed)
) -> dict:
    """
    Boost views on a Telegram post.

    Args:
        channel: Channel username without @ (e.g. "Squad_4xx")
        post_id: Post number (integer)
        target_views: How many views to send
        proxy_type: "http", "socks4", "socks5"
        proxy_list: Optional pre-loaded proxy list; if None, auto-scrapes
        concurrency: Max concurrent requests
        progress_callback: async fn(sent, total, failed) for live updates

    Returns:
        {"sent": int, "failed": int, "total_attempted": int}
    """
    channel = channel.lstrip("@")

    # Get proxies
    if proxy_list is None:
        if progress_callback:
            await progress_callback(0, target_views, 0, status="scraping")
        proxy_list = await scrape_proxies(proxy_type)

    if not proxy_list:
        return {"sent": 0, "failed": 0, "total_attempted": 0, "error": "No proxies found"}

    sent = 0
    failed = 0
    semaphore = asyncio.Semaphore(concurrency)

    # Fetch token first (no proxy, direct)
    async with aiohttp.ClientSession() as session:
        token = await fetch_view_token(channel, post_id, session)

    if not token:
        return {"sent": 0, "failed": 0, "total_attempted": 0, "error": "Could not fetch view token"}

    async def _do_one_view(proxy: str):
        nonlocal sent, failed
        async with semaphore:
            connector = None
            if proxy.startswith("socks"):
                try:
                    from aiohttp_socks import ProxyConnector
                    connector = ProxyConnector.from_url(proxy)
                except ImportError:
                    pass  # skip socks if lib not installed

            try:
                async with aiohttp.ClientSession(connector=connector) as s:
                    ok = await send_view(token, s, proxy=proxy if not connector else None)
                    if ok:
                        sent += 1
                    else:
                        failed += 1
            except Exception:
                failed += 1

            if progress_callback and (sent + failed) % 10 == 0:
                await progress_callback(sent, target_views, failed, status="running")

    # Cycle proxies if we have fewer than target_views
    proxies_to_use = []
    while len(proxies_to_use) < target_views:
        proxies_to_use.extend(proxy_list)
    proxies_to_use = proxies_to_use[:target_views]

    tasks = [_do_one_view(p) for p in proxies_to_use]
    await asyncio.gather(*tasks)

    if progress_callback:
        await progress_callback(sent, target_views, failed, status="done")

    return {
        "sent": sent,
        "failed": failed,
        "total_attempted": target_views,
        "proxies_used": len(proxy_list),
    }
