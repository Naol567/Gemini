import asyncio
import aiohttp
import re
import random
import time
import multiprocessing as mp
from datetime import timedelta
from aiohttp_socks import ProxyConnector
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ContextTypes, CallbackQueryHandler, ConversationHandler
)

# ================= CONFIG =================
BOT_TOKEN = "8254387734:AAEd4VK_abdQuwgbFEiadoqj7UwlxDpmg3A"

# Multi‑processing settings (adjust to your hardware)
NUM_PROCESSES = 10            # Number of parallel processes
WORKERS_PER_PROCESS = 1500    # Workers per process
PROXY_REFRESH_SECONDS = 5     # Refresh proxy list every 5 seconds
REQUEST_TIMEOUT = 3
CONNECT_TIMEOUT = 2
MAX_PROXY_FAILURES = 1

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Referer": "https://t.me/",
}

# 30+ proxy sources (constantly updated)
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

# Conversation states
WAITING_FOR_LINK, WAITING_FOR_TARGET = range(2)

# ================= PROXY SCRAPER =================
async def scrape_proxies():
    new_proxies = set()
    async def fetch(url):
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=5) as r:
                    text = await r.text()
                    found = re.findall(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{1,5}", text)
                    for proxy in found:
                        new_proxies.add(('socks5', proxy))
        except:
            pass
    await asyncio.gather(*[fetch(url) for url in PROXY_SOURCES])
    return list(new_proxies)

# ================= WORKER PROCESS =================
async def worker_process(process_id, channel, post_id, target, stats_dict, stop_flag):
    """Runs until target reached or stop flag set"""
    is_running = True
    success = 0
    failures = 0
    proxy_failures = {}
    sem = asyncio.Semaphore(WORKERS_PER_PROCESS)
    q = asyncio.Queue()
    
    async def get_current_views():
        try:
            async with aiohttp.ClientSession(headers=HEADERS) as s:
                url = f"https://t.me/{channel}/{post_id}?embed=1"
                async with s.get(url, timeout=5) as r:
                    html = await r.text()
                    patterns = [
                        r'<span class="tgme_widget_message_views">([^<]+)</span>',
                        r'data-views="([^"]+)"',
                        r'<div class="tgme_widget_message_views">([^<]+)</div>',
                    ]
                    for pat in patterns:
                        m = re.search(pat, html)
                        if m:
                            v = m.group(1).replace('K', '000').replace('M', '000000').replace('.', '')
                            return int(''.join(filter(str.isdigit, v)))
        except:
            return 0
        return 0
    
    async def hit(proxy_type, proxy_str):
        nonlocal success, failures
        async with sem:
            if not is_running or stop_flag.is_set():
                return False
            if proxy_failures.get((proxy_type, proxy_str), 0) >= MAX_PROXY_FAILURES:
                return False
            try:
                connector = ProxyConnector.from_url(f"{proxy_type}://{proxy_str}")
                async with aiohttp.ClientSession(
                    connector=connector,
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT, connect=CONNECT_TIMEOUT),
                    headers=HEADERS
                ) as s:
                    embed_url = f"https://t.me/{channel}/{post_id}?embed=1"
                    async with s.get(embed_url) as resp:
                        html = await resp.text()
                        token_match = re.search(r'data-view="([^"]+)"', html)
                        if not token_match:
                            token_match = re.search(r'view":"([^"]+)"', html)
                        if token_match:
                            token = token_match.group(1)
                            view_url = f"https://t.me/v/?views={token}"
                            async with s.post(view_url, headers={"X-Requested-With": "XMLHttpRequest"}) as vr:
                                text = await vr.text()
                                if "true" in text or '"ok":true' in text:
                                    success += 1
                                    return True
            except Exception:
                proxy_failures[(proxy_type, proxy_str)] = proxy_failures.get((proxy_type, proxy_str), 0) + 1
                failures += 1
            return False
    
    async def worker():
        while is_running and not stop_flag.is_set():
            try:
                proxy = await asyncio.wait_for(q.get(), timeout=0.3)
                await hit(*proxy)
                q.task_done()
            except asyncio.TimeoutError:
                continue
    
    async def refresher():
        nonlocal is_running
        last_refresh = 0
        while is_running and not stop_flag.is_set():
            now = time.time()
            if now - last_refresh >= PROXY_REFRESH_SECONDS:
                proxies = await scrape_proxies()
                # Clear queue and refill
                while not q.empty():
                    try:
                        q.get_nowait()
                    except:
                        break
                for proxy in proxies:
                    await q.put(proxy)
                last_refresh = now
            else:
                if q.qsize() < 200:
                    proxies = await scrape_proxies()
                    for proxy in proxies[:300]:
                        await q.put(proxy)
            await asyncio.sleep(2)
    
    # Initial proxy fill
    proxies = await scrape_proxies()
    for proxy in proxies:
        await q.put(proxy)
    
    # Start workers and refresher
    workers = [asyncio.create_task(worker()) for _ in range(WORKERS_PER_PROCESS)]
    ref = asyncio.create_task(refresher())
    
    start_views = await get_current_views()
    start_time = time.time()
    
    while is_running and not stop_flag.is_set():
        current_views = await get_current_views()
        added = max(0, current_views - start_views)
        # Update shared stats
        stats_dict[process_id] = {
            'success': success,
            'failures': failures,
            'current_views': current_views,
            'added': added,
            'queue_size': q.qsize(),
            'running': True,
            'speed': int(added / ((time.time() - start_time) / 60)) if (time.time() - start_time) > 0 else 0
        }
        if current_views >= start_views + target:
            break
        await asyncio.sleep(1)
    
    is_running = False
    stats_dict[process_id] = {
        'success': success,
        'failures': failures,
        'current_views': await get_current_views(),
        'added': 0,
        'queue_size': 0,
        'running': False
    }
    for w in workers:
        w.cancel()
    ref.cancel()
    await asyncio.gather(*workers, return_exceptions=True)

def run_process(process_id, channel, post_id, target, stats_dict, stop_flag):
    asyncio.run(worker_process(process_id, channel, post_id, target, stats_dict, stop_flag))

# ================= BOT HANDLERS =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🔥 **Ultimate Proxy Booster (No Time Limit)**\n\n"
        "Send me a Telegram post link like:\n"
        "`https://t.me/username/123` or `@username/123`\n\n"
        "I will delete your link and ask for target views.",
        parse_mode="Markdown"
    )
    return WAITING_FOR_LINK

async def handle_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    text = message.text.strip()
    await message.delete()
    match = re.search(r'(?:https?://)?(?:t\.me/|@)?([a-zA-Z0-9_\-\.]+)/(\d+)', text)
    if not match:
        await message.reply_text("❌ Invalid link format. Send like: `https://t.me/my-channel/123`", parse_mode="Markdown")
        return WAITING_FOR_LINK
    channel = match.group(1)
    post_id = int(match.group(2))
    context.user_data['channel'] = channel
    context.user_data['post_id'] = post_id
    await message.reply_text(
        f"✅ **Link received:** `{channel}/{post_id}`\n\n"
        f"Now send the **target number of views** (e.g., `5000`)\n"
        f"I will use **{NUM_PROCESSES} processes × {WORKERS_PER_PROCESS} workers** = **{NUM_PROCESSES * WORKERS_PER_PROCESS} concurrent tasks**.\n"
        f"No time limit – will run until target reached.",
        parse_mode="Markdown"
    )
    return WAITING_FOR_TARGET

async def handle_target(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.isdigit():
        await update.message.reply_text("Please send a valid number (e.g., `5000`)", parse_mode="Markdown")
        return WAITING_FOR_TARGET
    target = int(text)
    context.user_data['target'] = target
    keyboard = [[InlineKeyboardButton("✅ YES, START", callback_data="confirm_yes")],
                [InlineKeyboardButton("❌ CANCEL", callback_data="confirm_no")]]
    await update.message.reply_text(
        f"⚠️ **CONFIRMATION**\n\n"
        f"Channel: `{context.user_data['channel']}`\n"
        f"Post ID: `{context.user_data['post_id']}`\n"
        f"Target views: `{target}`\n\n"
        f"🔥 This will launch **{NUM_PROCESSES} parallel processes** each with **{WORKERS_PER_PROCESS} workers**.\n"
        f"⏱️ No time limit – will run until target reached or you `/stop`.\n\n"
        f"**Do you want to start?**",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    return WAITING_FOR_TARGET

async def confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "confirm_yes":
        channel = context.user_data.get('channel')
        post_id = context.user_data.get('post_id')
        target = context.user_data.get('target')
        if not all([channel, post_id, target]):
            await query.edit_message_text("❌ Missing data. Use /start again.")
            return ConversationHandler.END
        
        manager = mp.Manager()
        stats_dict = manager.dict()
        stop_flag = manager.Event()
        processes = []
        for i in range(NUM_PROCESSES):
            p = mp.Process(target=run_process, args=(i, channel, post_id, target, stats_dict, stop_flag))
            p.start()
            processes.append(p)
        
        msg = await query.edit_message_text("🚀 **Launching multi‑process booster...**\n(No time limit, will run until target reached)", parse_mode="Markdown")
        start_time = time.time()
        last_update = 0
        
        # Store stop flag in context for /stop command
        context.user_data['stop_flag'] = stop_flag
        context.user_data['processes'] = processes
        
        while True:
            await asyncio.sleep(2)
            # Check if all processes finished
            all_done = all(not stats_dict.get(i, {}).get('running', True) for i in range(NUM_PROCESSES))
            total_success = sum(stats_dict.get(i, {}).get('success', 0) for i in range(NUM_PROCESSES))
            total_failures = sum(stats_dict.get(i, {}).get('failures', 0) for i in range(NUM_PROCESSES))
            
            # Get current views
            try:
                async with aiohttp.ClientSession(headers=HEADERS) as s:
                    url = f"https://t.me/{channel}/{post_id}?embed=1"
                    async with s.get(url, timeout=5) as r:
                        html = await r.text()
                        m = re.search(r'<span class="tgme_widget_message_views">([^<]+)</span>', html)
                        if m:
                            v = m.group(1).replace('K', '000').replace('M', '000000').replace('.', '')
                            current_views = int(''.join(filter(str.isdigit, v)))
                        else:
                            current_views = 0
            except:
                current_views = 0
            
            # Get start views (from first process or stored)
            if not hasattr(confirm_callback, 'start_views'):
                confirm_callback.start_views = current_views
            start_views = confirm_callback.start_views
            added = max(0, current_views - start_views)
            elapsed = time.time() - start_time
            speed = int(added / (elapsed / 60)) if elapsed > 0 else 0
            prog = min(100, int((added / target) * 100)) if target > 0 else 0
            bar = "▓" * (prog // 10) + "░" * (10 - (prog // 10))
            text = (f"🚀 **MULTI‑PROCESS BOOSTER (No Time Limit)**\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📊 [{bar}] {prog}%\n"
                    f"✅ Views: `{current_views}` | 🎯 `{start_views + target}`\n"
                    f"⚡ Speed: `{speed} views/min`\n"
                    f"🛠 Total hits: `{total_success}`\n"
                    f"❌ Failures: `{total_failures}`\n"
                    f"⚙️ Processes: `{NUM_PROCESSES}` | Workers: `{NUM_PROCESSES * WORKERS_PER_PROCESS}`\n"
                    f"⏱️ Running for: `{str(timedelta(seconds=int(elapsed)))}`")
            if time.time() - last_update > 2:
                try:
                    await msg.edit_text(text, parse_mode="Markdown")
                    last_update = time.time()
                except:
                    pass
            if current_views >= start_views + target or all_done:
                break
            if stop_flag.is_set():
                await msg.edit_text("🛑 **Stopped by user.**", parse_mode="Markdown")
                break
        
        # Terminate all processes
        for p in processes:
            p.terminate()
            p.join()
        await msg.edit_text(f"✅ **Boosting finished**\nFinal views: {current_views}\nTotal hits: {total_success}")
    else:
        await query.edit_message_text("❌ Cancelled. Use /start to begin again.")
    return ConversationHandler.END

async def stop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Stop the boosting process"""
    stop_flag = context.user_data.get('stop_flag')
    if stop_flag:
        stop_flag.set()
        await update.message.reply_text("🛑 Stopping booster... (may take a few seconds)")
    else:
        await update.message.reply_text("No active booster to stop.")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🛑 Cancelled.")
    return ConversationHandler.END

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            WAITING_FOR_LINK: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link)],
            WAITING_FOR_TARGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_target)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv_handler)
    app.add_handler(CallbackQueryHandler(confirm_callback))
    app.add_handler(CommandHandler("stop", stop_command))
    print(f"🚀 ULTIMATE PROXY BOOSTER STARTED - No time limit")
    print(f"   Processes: {NUM_PROCESSES} | Workers per process: {WORKERS_PER_PROCESS} | Total concurrency: {NUM_PROCESSES * WORKERS_PER_PROCESS}")
    print("⚠️ WARNING: This method does NOT increase real view counts (Telegram patched it).")
    print("   The 'hits' counter shows fake successes. Real views will not change.")
    app.run_polling()

if __name__ == "__main__":
    mp.freeze_support()
    main()
