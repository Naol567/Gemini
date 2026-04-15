# 📡 Telegram View Booster — Integration Guide

Built by analyzing: https://github.com/vwh/telegram-views

---

## 📁 Files

| File | Purpose |
|------|---------|
| `view_booster.py` | Core engine — proxy scraping, token fetching, view sending |
| `boost_commands.py` | Telegram bot command handlers (drop-in for your bot) |
| `standalone_boost.py` | CLI tool — run without a bot |
| `requirements_boost.txt` | Dependencies |

---

## ⚙️ How It Works (Technical)

1. **Token Fetch** — Hits `https://t.me/{channel}/{post}?embed=1&mode=tme`
   and extracts the `data-view="..."` token from HTML

2. **View Send** — POSTs to `https://t.me/v/?views={token}` through a proxy
   Each successful 200 OK = +1 view on the post

3. **Proxies** — Uses free public proxy lists scraped from GitHub
   Rotates through them with async concurrency (50 at a time by default)

---

## 🤖 Option A — Add to Your Existing Bot

In your main bot file (wherever you build the Application):

```python
from boost_commands import register_boost_handlers, ADMIN_IDS

# Add your Telegram user ID so only you can use these commands
ADMIN_IDS.append(YOUR_TELEGRAM_USER_ID)  # e.g. 123456789

# After building your application:
register_boost_handlers(application)
```

### Bot Commands Available:

| Command | Description |
|---------|-------------|
| `/boost @Squad_4xx 42 200` | Boost post #42 with 200 views |
| `/boost @Squad_4xx 42 500 socks5` | Use SOCKS5 proxies |
| `/stopboost` | Cancel running boost |
| `/proxies` | Check available proxy count |

---

## 🖥️ Option B — Standalone CLI (no bot needed)

```bash
# Install deps
pip install aiohttp aiohttp-socks

# Auto mode (scrapes proxies automatically)
python standalone_boost.py --channel Squad_4xx --post 42 --views 300 --mode auto

# List mode (your own proxy file)
python standalone_boost.py --channel Squad_4xx --post 42 --views 200 --mode list --type socks5 --proxy proxies.txt

# Rotate mode (single proxy)
python standalone_boost.py --channel Squad_4xx --post 42 --views 100 --mode rotate --proxy user:pass@1.2.3.4:8080
```

---

## 🚀 Deploy on Railway

1. Add these files to your existing Railway project repo
2. Add to your `requirements.txt`: `aiohttp>=3.9.0` and `aiohttp-socks>=0.8.0`
3. In your bot's main file, add `register_boost_handlers(application)`
4. Set env var: `BOT_CHANNEL=Squad_4xx`
5. Push and redeploy — done!

---

## ⚠️ Notes

- Free proxies have HIGH failure rates (~60-80%) — this is normal
  The booster compensates by sending more requests than target views
- SOCKS5 proxies tend to work better than HTTP for this use case
- Views may take a few minutes to appear on Telegram
- Telegram may not count all views if they come too fast — 50 concurrency is safe
- Cap per run is set to 2000 views in `boost_commands.py` (change `min(int(args[2]), 2000)`)
