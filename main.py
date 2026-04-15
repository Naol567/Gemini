"""
Telegram Task Worker Bot — Production Single File
==================================================
• Master bot controls multiple client accounts via PostgreSQL-stored sessions
• OTP + optional 2FA login flow built-in via /login command
• Tasks: join channels, start bots with referral params
• Per-account proxy (SOCKS5/HTTP) support
• Random delays between accounts (anti-flood)
• Full inline keyboard questionnaire flow

Deploy on Railway.app with the PostgreSQL plugin.
"""

import asyncio
import logging
import os
import re
import random
from urllib.parse import urlparse, parse_qs
from dataclasses import dataclass
from typing import Optional

import asyncpg
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import StartBotRequest
from telethon.errors import (
    SessionPasswordNeededError,
    PhoneCodeInvalidError,
    PhoneCodeExpiredError,
    PasswordHashInvalidError,
    FloodWaitError,
    PhoneNumberInvalidError,
)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
    ConversationHandler,
)

# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# ENV VARS  (set all of these on Railway)
# ─────────────────────────────────────────────────────────────────────────────
BOT_TOKEN    = os.environ["MASTER_BOT_TOKEN"]
ADMIN_ID     = int(os.environ["ADMIN_TELEGRAM_ID"])
TG_API_ID    = int(os.environ["TG_API_ID"])
TG_API_HASH  = os.environ["TG_API_HASH"]
DATABASE_URL = os.environ["DATABASE_URL"]

# ─────────────────────────────────────────────────────────────────────────────
# CONVERSATION STATES  (for /login multi-step flow)
# ─────────────────────────────────────────────────────────────────────────────
(
    LOGIN_LABEL,
    LOGIN_PHONE,
    LOGIN_PROXY,
    LOGIN_PROXY_DETAILS,
    LOGIN_OTP,
    LOGIN_2FA,
) = range(6)

# ─────────────────────────────────────────────────────────────────────────────
# IN-MEMORY STATE
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class PendingTask:
    """Tracks a task being configured via the questionnaire."""
    link:        str
    task_type:   Optional[str] = None   # 'bot' | 'channel'
    open_when:   Optional[str] = None   # 'immediate' | 'after_join'
    username:    Optional[str] = None
    start_param: Optional[str] = None

@dataclass
class LoginSession:
    """Tracks an in-progress login for one account."""
    label:        str  = ""
    phone:        str  = ""
    proxy_host:   Optional[str] = None
    proxy_port:   Optional[int] = None
    proxy_type:   str  = "SOCKS5"
    proxy_user:   Optional[str] = None
    proxy_pass:   Optional[str] = None
    client:       Optional[TelegramClient] = None
    phone_hash:   Optional[str] = None   # returned by send_code_request

# pending task per admin user_id
pending_tasks: dict[int, PendingTask] = {}

# active login session per admin user_id
login_sessions: dict[int, LoginSession] = {}

# ─────────────────────────────────────────────────────────────────────────────
# DATABASE
# ─────────────────────────────────────────────────────────────────────────────
_pool: Optional[asyncpg.Pool] = None

async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(DATABASE_URL, min_size=2, max_size=10)
    return _pool

async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id          SERIAL PRIMARY KEY,
                label       TEXT NOT NULL UNIQUE,
                session_str TEXT NOT NULL,
                phone       TEXT,
                proxy_host  TEXT,
                proxy_port  INTEGER,
                proxy_type  TEXT DEFAULT 'SOCKS5',
                proxy_user  TEXT,
                proxy_pass  TEXT,
                active      BOOLEAN DEFAULT TRUE,
                created_at  TIMESTAMPTZ DEFAULT NOW()
            );
            CREATE TABLE IF NOT EXISTS task_log (
                id          SERIAL PRIMARY KEY,
                task_type   TEXT NOT NULL,
                target_link TEXT NOT NULL,
                account_id  INTEGER REFERENCES accounts(id),
                status      TEXT,
                detail      TEXT,
                executed_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)
    log.info("[DB] Tables ready.")

async def fetch_active_accounts() -> list:
    pool = await get_pool()
    async with pool.acquire() as conn:
        return await conn.fetch(
            "SELECT * FROM accounts WHERE active = TRUE ORDER BY id"
        )

async def upsert_account(label, session_str, phone=None,
                         proxy_host=None, proxy_port=None,
                         proxy_type="SOCKS5", proxy_user=None, proxy_pass=None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO accounts
                (label, session_str, phone, proxy_host, proxy_port,
                 proxy_type, proxy_user, proxy_pass)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            ON CONFLICT (label) DO UPDATE
            SET session_str=$2, phone=$3, proxy_host=$4, proxy_port=$5,
                proxy_type=$6, proxy_user=$7, proxy_pass=$8,
                active=TRUE
        """, label, session_str, phone,
             proxy_host, proxy_port, proxy_type, proxy_user, proxy_pass)

async def delete_account(label: str) -> bool:
    pool = await get_pool()
    async with pool.acquire() as conn:
        r = await conn.execute("DELETE FROM accounts WHERE label = $1", label)
        return r == "DELETE 1"

async def log_task(task_type, target_link, account_id, status, detail=None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO task_log (task_type, target_link, account_id, status, detail)
            VALUES ($1,$2,$3,$4,$5)
        """, task_type, target_link, account_id, status, detail)

# ─────────────────────────────────────────────────────────────────────────────
# TELETHON HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def build_proxy_tuple(proxy_host, proxy_port, proxy_type="SOCKS5",
                      proxy_user=None, proxy_pass=None):
    """Returns a Telethon proxy tuple or None."""
    if not proxy_host or not proxy_port:
        return None
    try:
        import socks
        type_map = {
            "SOCKS5": socks.SOCKS5,
            "SOCKS4": socks.SOCKS4,
            "HTTP":   socks.HTTP,
        }
        return (
            type_map.get(proxy_type.upper(), socks.SOCKS5),
            proxy_host,
            int(proxy_port),
            True,
            proxy_user or None,
            proxy_pass or None,
        )
    except ImportError:
        log.warning("PySocks not installed — proxy ignored.")
        return None

def build_proxy_from_record(record) -> Optional[tuple]:
    return build_proxy_tuple(
        record["proxy_host"], record["proxy_port"],
        record["proxy_type"] or "SOCKS5",
        record["proxy_user"], record["proxy_pass"],
    )

async def make_client(session_str: str = "", proxy=None) -> TelegramClient:
    """Create a Telethon client with optional StringSession and proxy."""
    return TelegramClient(
        StringSession(session_str),
        TG_API_ID,
        TG_API_HASH,
        proxy=proxy,
    )

# ─────────────────────────────────────────────────────────────────────────────
# TASK EXECUTION
# ─────────────────────────────────────────────────────────────────────────────

async def execute_task_on_account(record, task_type: str,
                                   target: str, start_param: str = None):
    """Execute one task on one account. Returns (status, detail)."""
    client = None
    try:
        proxy  = build_proxy_from_record(record)
        client = await make_client(record["session_str"], proxy)
        await client.connect()

        if not await client.is_user_authorized():
            return "error", "Session expired — please /login again"

        if task_type == "channel":
            await client(JoinChannelRequest(target))
            return "ok", f"Joined {target}"

        elif task_type == "bot":
            entity = await client.get_entity(target)
            await client(StartBotRequest(
                bot=entity,
                peer=entity,
                start_param=start_param or "",
            ))
            return "ok", f"Started @{target} ref='{start_param or ''}'"

        return "skipped", f"Unknown type: {task_type}"

    except FloodWaitError as e:
        return "error", f"FloodWait {e.seconds}s"
    except Exception as exc:
        return "error", str(exc)
    finally:
        if client and client.is_connected():
            await client.disconnect()


async def run_task_on_all_accounts(task_type: str, target: str,
                                    start_param: str = None,
                                    delay_min: float = 4.0,
                                    delay_max: float = 12.0) -> list[dict]:
    accounts = await fetch_active_accounts()
    if not accounts:
        return []

    results = []
    for i, record in enumerate(accounts):
        if i > 0:
            delay = random.uniform(delay_min, delay_max)
            log.info("[Worker] Delay %.1fs before account #%d", delay, i + 1)
            await asyncio.sleep(delay)

        log.info("[Worker] Running on: %s", record["label"])
        status, detail = await execute_task_on_account(
            record, task_type, target, start_param
        )
        await log_task(task_type, target, record["id"], status, detail)
        results.append({"label": record["label"], "status": status, "detail": detail})
        log.info("[Worker]  → %s: %s", status, detail)

    return results

# ─────────────────────────────────────────────────────────────────────────────
# MISC HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def extract_link_parts(link: str) -> tuple[str, Optional[str]]:
    m = re.match(r"https?://t\.me/([^/?#\s]+)", link)
    if not m:
        return link.lstrip("@"), None
    username = m.group(1)
    qs       = parse_qs(urlparse(link).query)
    param    = qs.get("start", [None])[0] or qs.get("startapp", [None])[0]
    return username, param

def is_admin(uid: int) -> bool:
    return uid == ADMIN_ID

def format_results(results: list[dict]) -> str:
    if not results:
        return "⚠️ No active accounts found. Add accounts with /login."
    ok      = sum(1 for r in results if r["status"] == "ok")
    errors  = sum(1 for r in results if r["status"] == "error")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    lines   = ["📊 *Task Results*\n"]
    for r in results:
        icon = {"ok": "✅", "error": "❌", "skipped": "⏭️"}.get(r["status"], "❔")
        lines.append(f"{icon} `{r['label']}` — {r['detail']}")
    lines.append(f"\n*Total:* {len(results)} | ✅ {ok} | ❌ {errors} | ⏭️ {skipped}")
    return "\n".join(lines)

# ─────────────────────────────────────────────────────────────────────────────
# /login  CONVERSATION HANDLER
# ─────────────────────────────────────────────────────────────────────────────

async def login_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    """Entry point: /login"""
    if not is_admin(update.effective_user.id):
        return ConversationHandler.END
    uid = update.effective_user.id
    login_sessions[uid] = LoginSession()
    await update.message.reply_text(
        "🔐 *Add a New Account — Login Flow*\n\n"
        "Step 1/5 — Enter a short *label* for this account.\n"
        "_Example:_ `account1` or `my_second_phone`\n\n"
        "Send /cancel at any time to abort.",
        parse_mode="Markdown",
    )
    return LOGIN_LABEL


async def login_got_label(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid   = update.effective_user.id
    label = update.message.text.strip()
    if not re.match(r"^\w{1,30}$", label):
        await update.message.reply_text(
            "⚠️ Label must be letters/numbers/underscores, max 30 chars. Try again:"
        )
        return LOGIN_LABEL

    login_sessions[uid].label = label
    await update.message.reply_text(
        f"✅ Label: `{label}`\n\n"
        "Step 2/5 — Enter the phone number for this account.\n"
        "_Format:_ `+251912345678` (with country code)",
        parse_mode="Markdown",
    )
    return LOGIN_PHONE


async def login_got_phone(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid   = update.effective_user.id
    phone = update.message.text.strip()

    if not re.match(r"^\+\d{7,15}$", phone):
        await update.message.reply_text(
            "⚠️ Invalid format. Use international format: `+251912345678`",
            parse_mode="Markdown",
        )
        return LOGIN_PHONE

    login_sessions[uid].phone = phone

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔌 Yes, use a proxy", callback_data="proxy:yes"),
            InlineKeyboardButton("⏭️ No proxy",         callback_data="proxy:no"),
        ]
    ])
    await update.message.reply_text(
        f"✅ Phone: `{phone}`\n\n"
        "Step 3/5 — Does this account need a proxy?",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )
    return LOGIN_PROXY


async def login_proxy_choice(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    uid   = query.from_user.id

    if query.data == "proxy:no":
        # No proxy — go straight to OTP step
        return await _send_otp(query.message, uid, edit=True)
    else:
        await query.edit_message_text(
            "Step 4/5 — Enter proxy details in this format:\n\n"
            "`host|port|type|username|password`\n\n"
            "_Examples:_\n"
            "`proxy.example.com|1080|SOCKS5|user|pass`\n"
            "`1.2.3.4|8080|HTTP` (no auth)\n\n"
            "Supported types: `SOCKS5`, `SOCKS4`, `HTTP`",
            parse_mode="Markdown",
        )
        return LOGIN_PROXY_DETAILS


async def login_got_proxy(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid  = update.effective_user.id
    text = update.message.text.strip()
    sess = login_sessions[uid]

    try:
        parts = [p.strip() for p in text.split("|")]
        sess.proxy_host = parts[0]
        sess.proxy_port = int(parts[1])
        sess.proxy_type = parts[2].upper() if len(parts) > 2 else "SOCKS5"
        sess.proxy_user = parts[3] if len(parts) > 3 else None
        sess.proxy_pass = parts[4] if len(parts) > 4 else None
        await update.message.reply_text(
            f"✅ Proxy set: `{sess.proxy_host}:{sess.proxy_port}` ({sess.proxy_type})",
            parse_mode="Markdown",
        )
    except Exception:
        await update.message.reply_text(
            "⚠️ Could not parse proxy. Format: `host|port|type|user|pass`\n"
            "Continuing without proxy.",
            parse_mode="Markdown",
        )

    return await _send_otp(update.message, uid, edit=False)


async def _send_otp(message, uid: int, edit: bool = False) -> int:
    """
    Internal helper: connect the Telethon client and request the OTP.
    """
    sess  = login_sessions[uid]
    proxy = build_proxy_tuple(
        sess.proxy_host, sess.proxy_port,
        sess.proxy_type, sess.proxy_user, sess.proxy_pass,
    )

    text = f"📲 Sending OTP to `{sess.phone}`..."
    if edit:
        await message.edit_text(text, parse_mode="Markdown")
    else:
        await message.reply_text(text, parse_mode="Markdown")

    try:
        client = await make_client("", proxy)
        await client.connect()
        result = await client.send_code_request(sess.phone)
        sess.client     = client
        sess.phone_hash = result.phone_code_hash

        if edit:
            await message.edit_text(
                f"✅ OTP sent to `{sess.phone}`\n\n"
                "Step 4/5 — Enter the OTP code you received:\n"
                "_Type just the digits, e.g._ `12345`",
                parse_mode="Markdown",
            )
        else:
            await message.reply_text(
                f"✅ OTP sent to `{sess.phone}`\n\n"
                "Step 4/5 — Enter the OTP code you received:\n"
                "_Type just the digits, e.g._ `12345`",
                parse_mode="Markdown",
            )
        return LOGIN_OTP

    except PhoneNumberInvalidError:
        await message.reply_text("❌ That phone number is invalid. Use /login to restart.")
        _cleanup_login(uid)
        return ConversationHandler.END

    except FloodWaitError as e:
        await message.reply_text(
            f"⏳ Telegram asks to wait {e.seconds} seconds before trying again."
        )
        _cleanup_login(uid)
        return ConversationHandler.END

    except Exception as exc:
        log.exception("OTP send failed")
        await message.reply_text(f"❌ Failed to send OTP: {exc}")
        _cleanup_login(uid)
        return ConversationHandler.END


async def login_got_otp(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid  = update.effective_user.id
    code = update.message.text.strip().replace(" ", "")
    sess = login_sessions.get(uid)

    if not sess or not sess.client:
        await update.message.reply_text("⚠️ Session lost. Use /login to restart.")
        return ConversationHandler.END

    try:
        await sess.client.sign_in(
            phone=sess.phone,
            code=code,
            phone_code_hash=sess.phone_hash,
        )
        # Login successful, no 2FA needed
        return await _finish_login(update.message, uid)

    except SessionPasswordNeededError:
        # Account has 2FA enabled
        await update.message.reply_text(
            "🔒 *Two-Factor Authentication (2FA) required.*\n\n"
            "Step 5/5 — Enter your 2FA password:\n"
            "_(Your message will not be stored; it is only used once to sign in)_",
            parse_mode="Markdown",
        )
        return LOGIN_2FA

    except PhoneCodeInvalidError:
        await update.message.reply_text(
            "❌ Wrong OTP code. Please try again (check your Telegram messages):"
        )
        return LOGIN_OTP

    except PhoneCodeExpiredError:
        await update.message.reply_text(
            "⏳ OTP expired. Use /login to request a new one."
        )
        _cleanup_login(uid)
        return ConversationHandler.END

    except Exception as exc:
        log.exception("OTP sign-in failed")
        await update.message.reply_text(f"❌ Sign-in error: {exc}\nUse /login to retry.")
        _cleanup_login(uid)
        return ConversationHandler.END


async def login_got_2fa(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid      = update.effective_user.id
    password = update.message.text.strip()
    sess     = login_sessions.get(uid)

    # Delete the password message immediately for security
    try:
        await update.message.delete()
    except Exception:
        pass

    if not sess or not sess.client:
        await ctx.bot.send_message(uid, "⚠️ Session lost. Use /login to restart.")
        return ConversationHandler.END

    try:
        await sess.client.sign_in(password=password)
        return await _finish_login_bot(ctx.bot, uid)

    except PasswordHashInvalidError:
        await ctx.bot.send_message(
            uid,
            "❌ Wrong 2FA password. Please try again:\n"
            "_(Message deleted for security)_",
            parse_mode="Markdown",
        )
        return LOGIN_2FA

    except Exception as exc:
        log.exception("2FA sign-in failed")
        await ctx.bot.send_message(uid, f"❌ 2FA error: {exc}\nUse /login to retry.")
        _cleanup_login(uid)
        return ConversationHandler.END


async def _finish_login(message, uid: int) -> int:
    """Save session after successful sign-in (used when we have a message object)."""
    sess = login_sessions[uid]
    session_str = sess.client.session.save()

    await upsert_account(
        sess.label, session_str, sess.phone,
        sess.proxy_host, sess.proxy_port,
        sess.proxy_type, sess.proxy_user, sess.proxy_pass,
    )

    proxy_info = f"{sess.proxy_host}:{sess.proxy_port}" if sess.proxy_host else "None"
    await message.reply_text(
        f"🎉 *Account `{sess.label}` logged in successfully!*\n\n"
        f"📱 Phone: `{sess.phone}`\n"
        f"🔌 Proxy: `{proxy_info}`\n"
        f"💾 Session saved to database.\n\n"
        f"Use /accounts to see all accounts.",
        parse_mode="Markdown",
    )
    _cleanup_login(uid)
    return ConversationHandler.END


async def _finish_login_bot(bot, uid: int) -> int:
    """Save session after successful 2FA (we only have bot, not message)."""
    sess = login_sessions[uid]
    session_str = sess.client.session.save()

    await upsert_account(
        sess.label, session_str, sess.phone,
        sess.proxy_host, sess.proxy_port,
        sess.proxy_type, sess.proxy_user, sess.proxy_pass,
    )

    proxy_info = f"{sess.proxy_host}:{sess.proxy_port}" if sess.proxy_host else "None"
    await bot.send_message(
        uid,
        f"🎉 *Account `{sess.label}` logged in with 2FA!*\n\n"
        f"📱 Phone: `{sess.phone}`\n"
        f"🔌 Proxy: `{proxy_info}`\n"
        f"💾 Session saved to database.\n\n"
        f"Use /accounts to see all accounts.",
        parse_mode="Markdown",
    )
    _cleanup_login(uid)
    return ConversationHandler.END


def _cleanup_login(uid: int):
    """Disconnect and remove a login session from memory."""
    sess = login_sessions.pop(uid, None)
    if sess and sess.client and sess.client.is_connected():
        asyncio.create_task(sess.client.disconnect())


async def login_cancel(update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> int:
    uid = update.effective_user.id
    _cleanup_login(uid)
    await update.message.reply_text("❌ Login cancelled.")
    return ConversationHandler.END

# ─────────────────────────────────────────────────────────────────────────────
# STANDARD COMMAND HANDLERS
# ─────────────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text(
        "🤖 *Task Worker Bot*\n\n"
        "Send a `t.me/...` link to run a task across all accounts.\n\n"
        "📋 *Commands:*\n"
        "/login — add a new account (OTP + 2FA)\n"
        "/accounts — list all accounts\n"
        "/removeaccount — remove an account\n"
        "/help — usage guide",
        parse_mode="Markdown",
    )


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    await update.message.reply_text(
        "📖 *Help*\n\n"
        "*Add an account:*\n"
        "→ /login — interactive wizard (OTP + 2FA supported)\n\n"
        "*Remove an account:*\n"
        "→ `/removeaccount label`\n\n"
        "*Run a task:*\n"
        "→ Send any `t.me/...` link and follow the prompts\n\n"
        "*Proxy format (during /login):*\n"
        "`host|port|SOCKS5|user|pass`\n"
        "`host|port|HTTP` (no auth)\n\n"
        "*Notes:*\n"
        "• Sessions are stored in PostgreSQL — survive redeploys\n"
        "• 2FA password is deleted from chat immediately after entry\n"
        "• Tasks run with random delays between accounts",
        parse_mode="Markdown",
    )


async def cmd_accounts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    accounts = await fetch_active_accounts()
    if not accounts:
        await update.message.reply_text(
            "No accounts yet. Use /login to add one."
        )
        return
    lines = [f"📋 *Accounts ({len(accounts)})*\n"]
    for a in accounts:
        proxy = (f"{a['proxy_type']} {a['proxy_host']}:{a['proxy_port']}"
                 if a["proxy_host"] else "No proxy")
        lines.append(
            f"• `{a['label']}` | {a['phone'] or 'no phone'} | {proxy}"
        )
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_removeaccount(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    if not ctx.args:
        await update.message.reply_text(
            "Usage: `/removeaccount label`", parse_mode="Markdown"
        )
        return
    label   = ctx.args[0].strip()
    removed = await delete_account(label)
    if removed:
        await update.message.reply_text(
            f"🗑️ Account `{label}` removed.", parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            f"⚠️ Account `{label}` not found.", parse_mode="Markdown"
        )

# ─────────────────────────────────────────────────────────────────────────────
# TASK QUESTIONNAIRE  (link → inline keyboard flow)
# ─────────────────────────────────────────────────────────────────────────────

async def handle_link(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        return
    text = (update.message.text or "").strip()
    if "t.me/" not in text:
        return

    uid           = update.effective_user.id
    username, param = extract_link_parts(text)
    pending_tasks[uid] = PendingTask(
        link=text, username=username, start_param=param
    )

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🎮 Mini-App / Bot",   callback_data="type:bot"),
        InlineKeyboardButton("📢 Channel / Group",  callback_data="type:channel"),
    ]])
    await update.message.reply_text(
        f"🔗 `{text}`\n\n❓ *Q1:* What type is this task?",
        reply_markup=keyboard,
        parse_mode="Markdown",
    )


async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid  = query.from_user.id
    data = query.data

    if not is_admin(uid):
        return

    # ── proxy choice during login ─────────────────────────────────────────────
    if data.startswith("proxy:"):
        return await login_proxy_choice(update, ctx)

    # ── task questionnaire ────────────────────────────────────────────────────
    task = pending_tasks.get(uid)
    if not task:
        await query.edit_message_text("⚠️ Session expired. Send the link again.")
        return

    if data.startswith("type:"):
        task.task_type = data.split(":")[1]
        label = "Mini-App / Bot" if task.task_type == "bot" else "Channel / Group"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("⚡ Open Immediately",        callback_data="when:immediate"),
            InlineKeyboardButton("⏳ After Joining/Starting",  callback_data="when:after_join"),
        ]])
        await query.edit_message_text(
            f"✅ Type: *{label}*\n\n❓ *Q2:* When should the task run?",
            reply_markup=keyboard,
            parse_mode="Markdown",
        )

    elif data.startswith("when:"):
        task.open_when = data.split(":")[1]
        type_label = "Mini-App / Bot" if task.task_type == "bot" else "Channel / Group"
        when_label = "Immediately" if task.open_when == "immediate" else "After joining/starting"
        accounts   = await fetch_active_accounts()

        summary = (
            "📋 *Task Summary*\n\n"
            f"🔗 Link: `{task.link}`\n"
            f"🏷️ Type: {type_label}\n"
            f"⏱️ Timing: {when_label}\n"
        )
        if task.start_param:
            summary += f"🎯 Ref param: `{task.start_param}`\n"
        summary += f"\n👥 Will run on *{len(accounts)} account(s)*."

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("🚀 Confirm & Start", callback_data="confirm"),
            InlineKeyboardButton("❌ Cancel",           callback_data="cancel"),
        ]])
        await query.edit_message_text(
            summary, reply_markup=keyboard, parse_mode="Markdown"
        )

    elif data == "confirm":
        await query.edit_message_text(
            "⏳ Running task across all accounts...\n_(may take a few minutes)_",
            parse_mode="Markdown",
        )
        task = pending_tasks.pop(uid, None)
        if not task:
            await ctx.bot.send_message(uid, "⚠️ Task data lost. Please try again.")
            return

        results = await run_task_on_all_accounts(
            task_type=task.task_type,
            target=task.username,
            start_param=task.start_param,
        )
        await ctx.bot.send_message(
            uid, format_results(results), parse_mode="Markdown"
        )

    elif data == "cancel":
        pending_tasks.pop(uid, None)
        await query.edit_message_text("❌ Task cancelled.")

# ─────────────────────────────────────────────────────────────────────────────
# APP SETUP & ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

async def post_init(application: Application):
    await init_db()
    log.info("[Bot] Database initialised.")


def main():
    log.info("[Bot] Starting Task Worker Bot...")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # /login conversation (OTP + 2FA wizard)
    login_conv = ConversationHandler(
        entry_points=[CommandHandler("login", login_start)],
        states={
            LOGIN_LABEL:        [MessageHandler(filters.TEXT & ~filters.COMMAND, login_got_label)],
            LOGIN_PHONE:        [MessageHandler(filters.TEXT & ~filters.COMMAND, login_got_phone)],
            LOGIN_PROXY:        [CallbackQueryHandler(login_proxy_choice, pattern="^proxy:")],
            LOGIN_PROXY_DETAILS:[MessageHandler(filters.TEXT & ~filters.COMMAND, login_got_proxy)],
            LOGIN_OTP:          [MessageHandler(filters.TEXT & ~filters.COMMAND, login_got_otp)],
            LOGIN_2FA:          [MessageHandler(filters.TEXT & ~filters.COMMAND, login_got_2fa)],
        },
        fallbacks=[CommandHandler("cancel", login_cancel)],
        allow_reentry=True,
    )

    app.add_handler(login_conv)
    app.add_handler(CommandHandler("start",         cmd_start))
    app.add_handler(CommandHandler("help",          cmd_help))
    app.add_handler(CommandHandler("accounts",      cmd_accounts))
    app.add_handler(CommandHandler("removeaccount", cmd_removeaccount))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_link))
    app.add_handler(CallbackQueryHandler(handle_callback))

    log.info("[Bot] Polling started.")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
