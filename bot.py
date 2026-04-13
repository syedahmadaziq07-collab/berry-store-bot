"""
Telegram Store Bot — Stable Version for Replit
Run: python bot.py
"""

import os
import sys
import time
import random
import logging
import threading
import asyncio
import json
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

# ─── Kill Any Other Running Bot Instance ──────────────────────────────────────
# Runs BEFORE polling starts. Forces Telegram to drop any existing session
# (other Replit tab, old Render deploy, etc.) so this instance takes over cleanly.

import httpx as _httpx_early
import os as _os_early

_EARLY_TOKEN = (
    (_os_early.getenv("BOT_TOKEN") or "").strip() or
    (_os_early.getenv("TOKEN") or "").strip() or
    (_os_early.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
)

if _EARLY_TOKEN:
    try:
        _httpx_early.get(
            f"https://api.telegram.org/bot{_EARLY_TOKEN}/close",
            timeout=10,
        )
        print("✅ Old sessions closed")
    except Exception as _e:
        print(f"⚠️ Could not close old session: {_e}")

    try:
        _httpx_early.get(
            f"https://api.telegram.org/bot{_EARLY_TOKEN}/deleteWebhook?drop_pending_updates=true",
            timeout=10,
        )
        print("✅ Webhook cleared, pending updates dropped")
    except Exception as _e:
        print(f"⚠️ Could not clear webhook: {_e}")

    print("🚀 This instance is now the ONLY running bot!")

# ─── Logging Setup ────────────────────────────────────────────────────────────
# Logs to console AND to bot.log file for debugging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot.log", encoding="utf-8"),
    ],
)
log = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

# ─── Load Environment Variables ───────────────────────────────────────────────

def _get_env(key: str, fallback: str = "") -> str:
    """Get env var, strip whitespace, return fallback if empty."""
    return (os.getenv(key) or fallback).strip()

BOT_TOKEN    = _get_env("BOT_TOKEN") or _get_env("TOKEN") or _get_env("TELEGRAM_BOT_TOKEN")
SUPABASE_URL = _get_env("SUPABASE_URL").rstrip("/")
SUPABASE_KEY = _get_env("SUPABASE_KEY")
ADMIN_ID     = 0
PORT         = int(_get_env("PORT", "8000"))
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
PRODUCTS_CACHE_FILE = os.path.join(BASE_DIR, "products_cache.json")

def _redact(text: object) -> str:
    value = str(text)
    for secret in (BOT_TOKEN, SUPABASE_KEY):
        if secret:
            value = value.replace(secret, "[REDACTED]")
    return value[:500]

def _safe_error(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {_redact(exc)}"

try:
    ADMIN_ID = int(_get_env("ADMIN_ID", "0"))
except ValueError:
    log.warning("ADMIN_ID bukan nombor — ditetapkan kepada 0")

# ─── Startup Check ────────────────────────────────────────────────────────────

log.info("=" * 50)
log.info(f"BOT_TOKEN    : {'✅ set' if BOT_TOKEN else '❌ MISSING'}")
log.info(f"SUPABASE_URL : {'✅ ' + SUPABASE_URL[:35] if SUPABASE_URL else '❌ MISSING'}")
log.info(f"SUPABASE_KEY : {'✅ set (len=' + str(len(SUPABASE_KEY)) + ')' if SUPABASE_KEY else '❌ MISSING'}")
log.info(f"ADMIN_ID     : {ADMIN_ID if ADMIN_ID else '❌ MISSING'}")
log.info("=" * 50)

if not BOT_TOKEN:
    log.critical("BOT_TOKEN tidak ditetapkan. Set dalam Replit Secrets → BOT_TOKEN")
    sys.exit(1)

def _validate_telegram_token() -> bool:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getMe"
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            payload = json.loads(response.read().decode("utf-8"))
        bot = payload.get("result") or {}
        username = bot.get("username") or "unknown"
        log.info(f"Telegram token ✅ valid for @{username}")
        return True
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            log.critical("Telegram token rejected by Telegram API. Update the TELEGRAM_BOT_TOKEN secret, then restart the workflow.")
            return False
        log.warning(f"Telegram token precheck HTTP error code={exc.code}; polling will still try to start.")
        return True
    except Exception as exc:
        log.warning(f"Telegram token precheck skipped due to network/error: {_safe_error(exc)}")
        return True

# Validate Supabase config
_supabase_ready = False
log.info(f"[SUPABASE] SUPABASE_URL set={bool(SUPABASE_URL)} value_prefix={SUPABASE_URL[:30]!r}")
log.info(f"[SUPABASE] SUPABASE_KEY set={bool(SUPABASE_KEY)} len={len(SUPABASE_KEY)} starts_with_eyJ={SUPABASE_KEY.startswith('eyJ')}")
if SUPABASE_URL and SUPABASE_KEY:
    if not SUPABASE_URL.startswith("https://"):
        log.warning(f"[SUPABASE] ❌ SUPABASE_URL mesti bermula 'https://' — got: {SUPABASE_URL[:40]!r}")
        SUPABASE_URL = ""
    elif not SUPABASE_KEY.startswith("eyJ"):
        log.warning(f"[SUPABASE] ❌ SUPABASE_KEY tidak bermula 'eyJ' (len={len(SUPABASE_KEY)}) — guna anon/public key dari Supabase dashboard")
        SUPABASE_KEY = ""
    elif len(SUPABASE_KEY) <= 100:
        log.warning(f"[SUPABASE] ❌ SUPABASE_KEY terlalu pendek len={len(SUPABASE_KEY)} — pastikan key penuh disalin")
        SUPABASE_KEY = ""
    else:
        _supabase_ready = True
        log.info("[SUPABASE] ✅ URL dan KEY lulus semakan format")
else:
    missing = []
    if not SUPABASE_URL: missing.append("SUPABASE_URL")
    if not SUPABASE_KEY: missing.append("SUPABASE_KEY")
    log.warning(f"[SUPABASE] ❌ Supabase tidak dikonfigurasi — pemboleh ubah hilang: {', '.join(missing)}")
log.info(f"[SUPABASE] _supabase_ready={_supabase_ready}")

# ─── Supabase REST Helpers (direct httpx, no library) ────────────────────────

import httpx as _httpx

_products_cache = {"data": [], "updated_at": 0.0}
_supabase_ok    = False


def _sb_headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def sb_get(table: str, params: str = "") -> list:
    """SELECT rows. Returns list of dicts."""
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if params:
        url += "?" + params
    r = _httpx.get(url, headers=_sb_headers(), timeout=15)
    r.raise_for_status()
    data = r.json()
    log.debug(f"[SB GET] {table}?{params} → {len(data) if isinstance(data, list) else data}")
    return data


def sb_post(table: str, data: dict) -> list:
    """INSERT a row. Returns list of inserted rows."""
    r = _httpx.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers={**_sb_headers(), "Prefer": "return=representation"},
        json=data, timeout=15,
    )
    r.raise_for_status()
    return r.json()


def sb_upsert(table: str, data: dict) -> list:
    """UPSERT (insert or update). Returns list of rows."""
    r = _httpx.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers={**_sb_headers(), "Prefer": "return=representation,resolution=merge-duplicates"},
        json=data, timeout=15,
    )
    r.raise_for_status()
    return r.json()


def sb_patch(table: str, params: str, data: dict) -> list:
    """UPDATE rows matching params. Returns list of updated rows."""
    r = _httpx.patch(
        f"{SUPABASE_URL}/rest/v1/{table}?{params}",
        headers={**_sb_headers(), "Prefer": "return=representation"},
        json=data, timeout=15,
    )
    r.raise_for_status()
    return r.json()


def _test_supabase() -> tuple:
    """Quick connectivity check. Returns (ok: bool, detail: str)."""
    try:
        rows = sb_get("products", "select=id&limit=1")
        return True, f"test data={rows}"
    except _httpx.HTTPStatusError as exc:
        return False, f"HTTP {exc.response.status_code}: {exc.response.text[:200]}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


# ── Startup connectivity test — 3 attempts ────────────────────────────────────
for _attempt in range(1, 4):
    log.info(f"[SUPABASE] Startup test attempt {_attempt}/3 — URL={SUPABASE_URL[:40]!r} KEY_len={len(SUPABASE_KEY)}")
    _ok, _detail = _test_supabase()
    if _ok:
        log.info(f"[SUPABASE] ✅ Sambungan berjaya — {_detail}")
        _supabase_ok = True
        break
    log.warning(f"[SUPABASE] ❌ Attempt {_attempt} gagal — {_detail}")
    if _attempt < 3:
        log.info("[SUPABASE] Retry dalam 2 saat...")
        time.sleep(2)
else:
    log.error("[SUPABASE] ❌ Semua 3 percubaan gagal. Bot akan cuba semula apabila diperlukan.")


async def _run_supabase(label: str, operation, attempts: int = 3, timeout: int = 12):
    """Run a zero-arg callable in a thread with retry logic."""
    last_exc = None
    for attempt in range(1, attempts + 1):
        started = time.monotonic()
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(operation),
                timeout=timeout,
            )
            elapsed_ms = int((time.monotonic() - started) * 1000)
            log.info(f"Supabase {label} ok attempt={attempt} duration_ms={elapsed_ms}")
            return result
        except Exception as exc:
            last_exc = exc
            elapsed_ms = int((time.monotonic() - started) * 1000)
            log.warning(
                f"Supabase {label} failed attempt={attempt}/{attempts} duration_ms={elapsed_ms} "
                f"error={_safe_error(exc)}"
            )
            if attempt < attempts:
                await asyncio.sleep(min(0.4 * (2 ** (attempt - 1)) + random.uniform(0, 0.3), 3))
    raise last_exc

def _cache_products(products):
    _products_cache["data"] = products or []
    _products_cache["updated_at"] = time.time()
    try:
        with open(PRODUCTS_CACHE_FILE, "w", encoding="utf-8") as cache_file:
            json.dump(_products_cache, cache_file, ensure_ascii=False)
    except Exception as exc:
        log.warning(f"Product cache write failed: {_safe_error(exc)}")

def _load_products_cache_from_disk():
    try:
        if not os.path.exists(PRODUCTS_CACHE_FILE):
            return
        with open(PRODUCTS_CACHE_FILE, "r", encoding="utf-8") as cache_file:
            cached = json.load(cache_file)
        if isinstance(cached, dict) and isinstance(cached.get("data"), list):
            _products_cache["data"] = cached.get("data") or []
            _products_cache["updated_at"] = float(cached.get("updated_at") or 0)
            log.info(f"Product cache loaded from disk count={len(_products_cache['data'])}")
    except Exception as exc:
        log.warning(f"Product cache load failed: {_safe_error(exc)}")

def _cached_products(max_age: int | None = 300):
    products = _products_cache.get("data") or []
    updated_at = float(_products_cache.get("updated_at") or 0)
    age = time.time() - updated_at if updated_at else 999999
    if products and (max_age is None or age <= max_age):
        return products, int(age)
    return [], int(age)

_load_products_cache_from_disk()

# ─── Flask Keep-Alive Server ──────────────────────────────────────────────────

from flask import Flask, jsonify

_app = Flask(__name__)

@_app.route("/")
def _index():
    return "Bot hidup ✅", 200

@_app.route("/health")
def _health():
    cached, age = _cached_products()
    return jsonify(
        status="ok",
        supabase=_supabase_ok,
        cached_products=len(cached),
        products_cache_age_seconds=age if cached else None,
    ), 200

def _start_flask():
    log.info(f"Flask keep-alive berjalan di port {PORT}")
    _app.run(host="0.0.0.0", port=PORT, use_reloader=False, threaded=True)

threading.Thread(target=_start_flask, daemon=True).start()

# ─── Telegram Imports ─────────────────────────────────────────────────────────

from telegram import (
    Update,
    InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
)
from telegram.error import Conflict, InvalidToken
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ─── UI Helpers ───────────────────────────────────────────────────────────────

def main_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛍 Browse Shop", callback_data="shop"),
         InlineKeyboardButton("📦 My Orders",   callback_data="myorders")],
        [InlineKeyboardButton("👥 Referral",    callback_data="referral"),
         InlineKeyboardButton("💬 Support",     callback_data="support")],
    ])

def back_home():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Home", callback_data="home")]])

def back_shop():
    return InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Shop", callback_data="shop")]])

def build_product_keyboard(products: list) -> ReplyKeyboardMarkup:
    """Number buttons in the keyboard tray, 3 per row, plus a Home button."""
    buttons = []
    row = []
    for i, _ in enumerate(products, 1):
        row.append(KeyboardButton(str(i)))
        if len(row) == 3:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([KeyboardButton("🏠 Home")])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=True)

# ─── /start ───────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    log.info(f"/start from {user.id} (@{user.username})")

    # Instant reply so user knows bot is alive
    await update.message.reply_text("Bot hidup ✅")

    total_users = total_sold = 0
    try:
        def start_stats():
            sb_upsert("users", {
                "id": user.id,
                "username": user.username or "",
                "first_name": user.first_name or "",
            })
            users = sb_get("users", "select=id")
            sold  = sb_get("orders", "select=id&status=eq.completed")
            return len(users), len(sold)
        total_users, total_sold = await _run_supabase("start.stats", start_stats)
    except Exception as exc:
        log.warning(f"Supabase /start: {_safe_error(exc)}")

    now = datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).strftime("%A, %d %B %Y %H:%M:%S")
    await update.message.reply_text(
        f"Welcome to Berry Store.\n"
        f"Updated: {now}\n\n"
        f"👋 Hi {user.first_name}!\n\n"
        f"👤 Account\n"
        f"• ID: {user.id}\n"
        f"• Username: @{user.username or 'tiada'}\n\n"
        f"📊 Store Stats\n"
        f"• Total Users: {total_users}\n"
        f"• Total Sold: {total_sold} pcs\n\n"
        f"Tekan butang di bawah untuk mula!",
        reply_markup=main_kb(),
    )

# ─── Shop ─────────────────────────────────────────────────────────────────────

async def show_shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ── Instant loading feedback ───────────────────────────────────────────────
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text("⏳ Memuatkan produk...")
        except Exception:
            pass

    try:
        products = await _run_supabase(
            "products.list",
            lambda: sb_get("products", "select=id,name,stock,price,duration&order=id"),
        ) or []
        _cache_products(products)
        log.info(f"Products loaded: {len(products)} items source=supabase")
    except Exception as exc:
        products, age = _cached_products(max_age=None)
        if products:
            log.error(f"Shop error using cached products age_s={age}: {_safe_error(exc)}", exc_info=True)
        else:
            log.error(f"Shop error no cache available: {_safe_error(exc)}", exc_info=True)
            msg = "⚠️ Gagal muatkan produk. Sila cuba lagi atau hubungi @berryrc"
            if update.callback_query:
                await update.callback_query.edit_message_text(msg, reply_markup=back_home())
            else:
                await update.message.reply_text(msg, reply_markup=back_home())
            return

    if not products:
        text = "⚠️ Tiada produk tersedia."
        if update.callback_query:
            await update.callback_query.edit_message_text(text, reply_markup=back_home())
        else:
            await update.message.reply_text(text, reply_markup=back_home())
        return

    # Save product list so handle_message can resolve number → product
    context.user_data["shop_products"] = products

    text = "╭─────────────────────╮\n┊  LIST PRODUCT\n┊─────────────────────\n"
    for i, p in enumerate(products, 1):
        text += f"┊ {i}. {p['name']} ( {p['stock']} )\n"
    text += "╰─────────────────────╯\n\nTaip nombor atau tekan butang di bawah 👇"

    # ReplyKeyboardMarkup cannot go on edit_message_text — must use send_message.
    # When triggered via inline button: the loading message stays; new message has the keyboard.
    if update.callback_query:
        await context.bot.send_message(
            chat_id=update.callback_query.message.chat_id,
            text=text,
            reply_markup=build_product_keyboard(products),
        )
    else:
        await update.message.reply_text(text, reply_markup=build_product_keyboard(products))

# ─── Product Detail ───────────────────────────────────────────────────────────

async def show_product(update: Update, context: ContextTypes.DEFAULT_TYPE, product_id: int, qty: int = 1):
    """Show product detail with live quantity and total price."""
    qty = max(1, min(qty, 10))   # clamp between 1–10

    try:
        rows = await _run_supabase(
            f"products.detail id={product_id}",
            lambda: sb_get("products", f"select=*&id=eq.{product_id}&limit=1"),
        )
        p = rows[0] if rows else None
    except Exception as exc:
        cached, age = _cached_products(max_age=None)
        p = next((item for item in cached if str(item.get("id")) == str(product_id)), None)
        if p:
            log.warning(f"Supabase product detail fallback id={product_id} cache_age_s={age}: {_safe_error(exc)}")
        else:
            log.warning(f"Supabase product detail failed id={product_id}: {_safe_error(exc)}", exc_info=True)
            err_msg = "⚠️ Gagal muatkan produk. Cuba lagi."
            if update.callback_query:
                await update.callback_query.edit_message_text(err_msg, reply_markup=back_shop())
            else:
                await update.message.reply_text(err_msg, reply_markup=back_shop())
            return

    total = round(p["price"] * qty, 2)
    stock = p.get("stock", 0)

    product_text = (
        f"📦 {p['name']}\n"
        f"├─ Stock   : {stock} units\n"
        f"├─ Price   : RM {p['price']}\n"
        f"├─ Duration: {p.get('duration', '-')}\n"
        f"└─ Total   : RM {total}\n\n"
        f"• Akaun diberikan selepas bayar.\n"
        f"• Akaun peribadi, tidak dikongsi."
    )
    product_kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➖", callback_data=f"qty_minus_{product_id}_{qty}"),
            InlineKeyboardButton(f"  {qty}  ",  callback_data="qty_display"),
            InlineKeyboardButton("➕", callback_data=f"qty_plus_{product_id}_{qty}"),
        ],
        [InlineKeyboardButton(f"🛒 Buy Now  x{qty}  (RM {total})", callback_data=f"buy_{product_id}_{qty}")],
        [InlineKeyboardButton("⬅️ Back to Shop", callback_data="shop")],
    ])

    if update.callback_query:
        await update.callback_query.edit_message_text(product_text, reply_markup=product_kb)
    else:
        # ReplyKeyboardRemove and InlineKeyboardMarkup cannot share one message.
        # First message dismisses the reply keyboard; second shows the product detail.
        await update.message.reply_text("🔍 Memuatkan produk...", reply_markup=ReplyKeyboardRemove())
        await update.message.reply_text(product_text, reply_markup=product_kb)

# ─── Quantity ─────────────────────────────────────────────────────────────────

async def qty_adjust(update: Update, context: ContextTypes.DEFAULT_TYPE, product_id: int, current_qty: int, delta: int):
    """Recalculate qty and refresh product detail. Qty is embedded in callback_data, not user_data."""
    new_qty = max(1, min(current_qty + delta, 10))
    await show_product(update, context, product_id, new_qty)

# ─── Create Order ─────────────────────────────────────────────────────────────

async def create_order(update: Update, context: ContextTypes.DEFAULT_TYPE, product_id: int, qty: int):
    user = update.effective_user
    log.info(f"[CREATE_ORDER] product_id={product_id} qty={qty} user={user.id}")

    # ── Instant loading feedback ───────────────────────────────────────────────
    try:
        await update.callback_query.edit_message_text("⏳ Memproses order...")
    except Exception:
        pass

    try:
        rows = await _run_supabase(
            f"products.order_fetch id={product_id}",
            lambda: sb_get("products", f"select=*&id=eq.{product_id}&limit=1"),
        )
        p = rows[0] if rows else None
    except Exception as exc:
        cached, age = _cached_products(max_age=None)
        p = next((item for item in cached if str(item.get("id")) == str(product_id)), None)
        if p:
            log.warning(f"Supabase create_order product fallback id={product_id} cache_age_s={age}: {_safe_error(exc)}")
        else:
            log.warning(f"Supabase create_order fetch product_id={product_id}: {_safe_error(exc)}", exc_info=True)
            await update.callback_query.edit_message_text(
                "⚠️ Ralat berlaku. Sila cuba lagi atau hubungi @berryrc",
                reply_markup=back_shop())
            return

    if p["stock"] < qty:
        await update.callback_query.edit_message_text(
            "⚠️ Stok tidak mencukupi!", reply_markup=back_shop())
        return

    order_id = f"ORD{random.randint(10000, 99999)}{user.id}"
    total    = round(p["price"] * qty, 2)
    print(f"[CREATE_ORDER] Inserting order {order_id} total=RM{total}")
    try:
        await _run_supabase(
            f"orders.insert id={order_id}",
            lambda: sb_post("orders", {
                "id": order_id, "user_id": user.id, "username": user.username or "",
                "product_id": product_id, "product_name": p["name"],
                "quantity": qty, "amount": total, "status": "pending",
            }),
            attempts=1,
        )
    except Exception as exc:
        log.warning(f"Supabase create_order insert: {_safe_error(exc)}")
        await update.callback_query.edit_message_text(
            "⚠️ Ralat berlaku. Sila cuba lagi atau hubungi @berryrc",
            reply_markup=back_shop())
        return

    log.info(f"Order created: {order_id} by {user.id}")
    context.user_data[f"qty_{product_id}"] = 1
    await update.callback_query.edit_message_text(
        f"🧾 ORDER SUMMARY\n─────────────────────\n"
        f"• Produk  : {p['name']}\n"
        f"• Quantity: {qty}\n"
        f"• Harga   : RM {p['price']}\n"
        f"• Total   : RM {total}\n\n"
        f"Sila teruskan ke pembayaran.",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💳 Proceed to Payment", callback_data=f"payment_{order_id}")],
            [InlineKeyboardButton("⬅️ Back to Shop",       callback_data="shop")],
        ]),
    )

# ─── Payment ──────────────────────────────────────────────────────────────────

def get_qr_path():
    possible_paths = [
        "payment_qr.png",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "payment_qr.png"),
        "/opt/render/project/src/payment_qr.png",
        "telegram-bot/payment_qr.png",
    ]
    for path in possible_paths:
        if os.path.exists(path):
            log.info(f"[QR] Found at: {path}")
            return path
    log.warning(f"[QR] Not found. Checked: {possible_paths}")
    return None


async def show_payment(update: Update, context: ContextTypes.DEFAULT_TYPE, order_id: str):
    # answer() already called in on_button — do NOT call query.answer() here
    query = update.callback_query

    # ── FIX 1: Immediate loading indicator so user knows the bot is working ─────
    try:
        await query.edit_message_text("⏳ Memuatkan butiran pembayaran...")
    except Exception as exc:
        log.warning(f"[PAYMENT] edit_loading failed: {_safe_error(exc)}")

    # ── FIX 2: Order fetch with null-check guard ────────────────────────────────
    try:
        rows = await _run_supabase(
            f"orders.payment id={order_id}",
            lambda: sb_get("orders", f"select=*&id=eq.{order_id}&limit=1"),
        )
        order = rows[0] if rows else None
        if not order:
            log.warning(f"[PAYMENT] order {order_id} not found in DB")
            await query.edit_message_text("⚠️ Order tidak dijumpai.", reply_markup=back_shop())
            return
    except Exception as exc:
        log.warning(f"[PAYMENT] Supabase fetch failed: {_safe_error(exc)}", exc_info=True)
        await query.edit_message_text("⚠️ Gagal muatkan maklumat pembayaran.", reply_markup=back_shop())
        return

    # ── QR path: check multiple locations ──────────────────────────────────────
    qr = get_qr_path()

    # ── FIX 3: send_photo with proper context manager + its own try/except ──────
    qr_sent = False
    if qr:
        try:
            with open(qr, "rb") as qr_file:
                await context.bot.send_photo(
                    chat_id=query.message.chat_id,
                    photo=qr_file,
                    caption=(
                        f"💳 PAYMENT DETAILS\n\n"
                        f"Order ID: {order_id}\n"
                        f"Amount: RM {order['amount']}\n\n"
                        f"Scan QR code below to pay 👇"
                    ),
                )
            qr_sent = True
        except Exception as exc:
            log.warning(f"[PAYMENT] send_photo failed, falling back to text: {_safe_error(exc)}")

    if not qr_sent:
        try:
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=(
                    f"💳 PAYMENT DETAILS\n\n"
                    f"Order ID: {order_id}\n"
                    f"Amount: RM {order['amount']}\n\n"
                    f"⚠️ QR code tidak tersedia. Hubungi admin."
                ),
            )
        except Exception as exc:
            log.warning(f"[PAYMENT] text fallback also failed: {_safe_error(exc)}")

    # ── FIX 4: Action buttons in its own try/except — user must always see these ─
    try:
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text="After payment, click the button below:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ I Have Paid",  callback_data=f"paid_{order_id}")],
                [InlineKeyboardButton("❌ Cancel Order", callback_data=f"cancel_{order_id}")],
            ]),
        )
    except Exception as exc:
        log.error(f"[PAYMENT] send action buttons failed — user may be stuck: {_safe_error(exc)}")

    # Admin notify is already safe inside _admin_notify (has its own try/except) ─
    await _admin_notify(context,
        f"🔔 ORDER BARU!\n• Order: {order_id}\n• User: @{order.get('username','')}\n"
        f"• Produk: {order.get('product_name','')}\n• RM {order['amount']}")

# ─── Paid / Receipt ───────────────────────────────────────────────────────────

async def handle_paid(update: Update, context: ContextTypes.DEFAULT_TYPE, order_id: str):
    context.user_data["pending_receipt"] = order_id
    await update.callback_query.edit_message_text(
        f"📸 Upload screenshot resit pembayaran untuk:\nOrder ID: {order_id}\n\nHantar gambar sekarang:"
    )


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    order_id = context.user_data.get("pending_receipt")
    if not order_id:
        return

    user    = update.effective_user
    file_id = update.message.photo[-1].file_id
    try:
        def save_receipt():
            sb_patch("orders", f"id=eq.{order_id}", {"receipt_file_id": file_id, "status": "waiting_approval"})
            rows = sb_get("orders", f"select=*&id=eq.{order_id}&limit=1")
            return rows[0] if rows else {}
        order = await _run_supabase(f"orders.receipt id={order_id}", save_receipt)
    except Exception as exc:
        log.warning(f"Supabase receipt: {_safe_error(exc)}", exc_info=True)
        await update.message.reply_text("⚠️ Gagal simpan resit. Cuba lagi.")
        return

    context.user_data.pop("pending_receipt", None)
    await update.message.reply_text(
        f"✅ Resit diterima!\nOrder ID: {order_id}\nAdmin akan sahkan pembayaran anda.",
        reply_markup=main_kb(),
    )
    try:
        await context.bot.send_photo(
            chat_id=ADMIN_ID, photo=file_id,
            caption=(
                f"📸 RESIT BARU\n• Order: {order_id}\n"
                f"• User: @{user.username or user.id}\n"
                f"• Produk: {order.get('product_name','')}\n• RM {order['amount']}"
            ),
            reply_markup=InlineKeyboardMarkup([[
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{order_id}"),
                InlineKeyboardButton("❌ Reject",  callback_data=f"reject_{order_id}"),
            ]]),
        )
    except Exception as exc:
        log.warning(f"Admin photo notify: {_safe_error(exc)}")

# ─── Cancel Order ─────────────────────────────────────────────────────────────

async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE, order_id: str):
    try:
        await _run_supabase(
            f"orders.cancel id={order_id}",
            lambda: sb_patch("orders", f"id=eq.{order_id}", {"status": "cancelled"}),
        )
    except Exception as exc:
        log.warning(f"Supabase cancel: {_safe_error(exc)}")
    await update.callback_query.edit_message_text(
        f"❌ Order {order_id} dibatalkan.",
        reply_markup=back_home(),
    )

# ─── My Orders ────────────────────────────────────────────────────────────────

async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    # ── Instant loading feedback ───────────────────────────────────────────────
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text("⏳ Memuatkan orders...")
        except Exception:
            pass

    try:
        orders = await _run_supabase(
            f"orders.user user={user.id}",
            lambda: sb_get("orders", f"select=*&user_id=eq.{user.id}&order=id.desc"),
        ) or []
    except Exception as exc:
        log.warning(f"Supabase my_orders: {_safe_error(exc)}", exc_info=True)
        msg = "⚠️ Gagal muatkan orders. Cuba lagi."
        if update.callback_query:
            await update.callback_query.edit_message_text(msg, reply_markup=back_home())
        else:
            await update.message.reply_text(msg, reply_markup=back_home())
        return

    EMOJI = {"pending": "⏳", "waiting_approval": "🔍", "completed": "✅", "cancelled": "❌", "rejected": "🚫"}
    if not orders:
        text = "📦 Anda belum ada sebarang order."
    else:
        text = "📦 MY ORDERS\n" + "─" * 25 + "\n"
        for o in orders[:10]:
            text += f"{EMOJI.get(o['status'],'❓')} {o['id']}\n   {o.get('product_name','')}\n   RM {o['amount']} — {o['status']}\n\n"

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=back_home())
    else:
        await update.message.reply_text(text, reply_markup=back_home())

# ─── Admin: Approve / Reject ──────────────────────────────────────────────────

async def approve_order(update: Update, context: ContextTypes.DEFAULT_TYPE, order_id: str):
    if update.effective_user.id != ADMIN_ID:
        await update.callback_query.edit_message_caption(
            caption="⛔ Bukan admin.", reply_markup=None)
        return

    # ── Instant loading feedback ───────────────────────────────────────────────
    try:
        await update.callback_query.edit_message_caption(
            caption="⏳ Memproses...", reply_markup=None)
    except Exception:
        pass

    try:
        def approve_tx():
            rows = sb_get("orders", f"select=*&id=eq.{order_id}&limit=1")
            order_data = rows[0] if rows else {}
            sb_patch("orders", f"id=eq.{order_id}", {"status": "completed"})
            if order_data.get("product_id"):
                prod_rows = sb_get("products", f"select=stock&id=eq.{order_data['product_id']}&limit=1")
                if prod_rows:
                    new_stock = max(0, prod_rows[0]["stock"] - order_data.get("quantity", 1))
                    sb_patch("products", f"id=eq.{order_data['product_id']}", {"stock": new_stock})
            return order_data
        order = await _run_supabase(f"orders.approve id={order_id}", approve_tx, attempts=1, timeout=15)
    except Exception as exc:
        log.warning(f"Supabase approve: {_safe_error(exc)}", exc_info=True)
        await update.callback_query.edit_message_caption(
            caption="⚠️ Ralat approve. Sila cuba lagi.", reply_markup=None)
        return

    log.info(f"Order {order_id} approved by admin")
    await update.callback_query.edit_message_caption(
        caption=(update.callback_query.message.caption or "") + "\n\n✅ APPROVED", reply_markup=None)
    # Message 1 → Customer
    try:
        await context.bot.send_message(
            chat_id=order["user_id"],
            text=(
                "✅ Pembayaran anda telah disahkan!\n\n"
                "✅ Payment dah confirm!\n\n"
                "Akaun akan dihantar secepat mungkin 🚀\n"
                "(biasanya laju je, tak lebih dari 1 jam 😉)\n\n"
                "Kalau lebih 1 jam tak dapat apa-apa, jangan segan terus DM admin: @berryrc ya 🙌"
            ),
        )
    except Exception as exc:
        log.warning(f"Notify user approve: {_safe_error(exc)}")

    # Message 2 → Admin (copy-paste /send command)
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"/send {order_id}",
        )
    except Exception as exc:
        log.warning(f"Notify admin send command: {_safe_error(exc)}")

    # Message 3 → Admin (account template to fill in)
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"Order: {order_id}\n"
                f"Produk: {order.get('product_name', '-')}\n"
                f"Customer: @{order.get('username', '-')}\n\n"
                f"Email: \n"
                f"Password: "
            ),
        )
    except Exception as exc:
        log.warning(f"Notify admin template: {_safe_error(exc)}")


async def reject_order(update: Update, context: ContextTypes.DEFAULT_TYPE, order_id: str):
    if update.effective_user.id != ADMIN_ID:
        await update.callback_query.edit_message_caption(
            caption="⛔ Bukan admin.", reply_markup=None)
        return

    # ── Instant loading feedback ───────────────────────────────────────────────
    try:
        await update.callback_query.edit_message_caption(
            caption="⏳ Memproses...", reply_markup=None)
    except Exception:
        pass

    try:
        def reject_tx():
            rows = sb_get("orders", f"select=*&id=eq.{order_id}&limit=1")
            order_data = rows[0] if rows else {}
            sb_patch("orders", f"id=eq.{order_id}", {"status": "rejected"})
            return order_data
        order = await _run_supabase(f"orders.reject id={order_id}", reject_tx, attempts=1)
    except Exception as exc:
        log.warning(f"Supabase reject: {_safe_error(exc)}", exc_info=True)
        await update.callback_query.edit_message_caption(
            caption="⚠️ Ralat reject. Sila cuba lagi.", reply_markup=None)
        return

    log.info(f"Order {order_id} rejected by admin")
    await update.callback_query.edit_message_caption(
        caption=(update.callback_query.message.caption or "") + "\n\n❌ REJECTED", reply_markup=None)
    try:
        await context.bot.send_message(chat_id=order["user_id"],
            text=f"⚠️ Bayaran Order {order_id} ditolak.\nHubungi support untuk bantuan.")
    except Exception as exc:
        log.warning(f"Notify user reject: {_safe_error(exc)}")

# ─── Referral / Support / Home ────────────────────────────────────────────────

async def show_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try:
        me  = await context.bot.get_me()
        ref = f"https://t.me/{me.username}?start=ref_{user.id}"
        await update.callback_query.edit_message_text(
            f"👥 REFERRAL\n─────────────────────\nLink referral anda:\n{ref}\n\nKongsi dan dapatkan reward!",
            reply_markup=back_home())
    except Exception as exc:
        log.warning(f"show_referral error: {_safe_error(exc)}")
        try:
            await update.callback_query.edit_message_text(
                "⚠️ Ralat berlaku. Sila cuba lagi atau hubungi @berryrc",
                reply_markup=back_home())
        except Exception:
            pass


async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.edit_message_text(
        "💬 SUPPORT\n─────────────────────\nHubungi admin:\n• Telegram: @berryrc\n\nMasa operasi: 9am – 11pm",
        reply_markup=back_home())


async def show_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    total_users = total_sold = 0

    # ── Instant loading feedback ───────────────────────────────────────────────
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text("⏳ Memuatkan...")
        except Exception:
            pass

    try:
        def home_stats():
            users = sb_get("users", "select=id")
            sold  = sb_get("orders", "select=id&status=eq.completed")
            return len(users), len(sold)
        total_users, total_sold = await _run_supabase("home.stats", home_stats)
    except Exception as exc:
        log.warning(f"Supabase home: {_safe_error(exc)}")
    await update.callback_query.edit_message_text(
        f"👋 Hi {user.first_name}!\nWelcome to My Store.\n\n"
        f"👤 Account\n• ID: {user.id}\n• Username: @{user.username or 'tiada'}\n\n"
        f"📊 Store Stats\n• Total Users: {total_users}\n• Total Sold: {total_sold} pcs\n\n"
        f"Tekan butang di bawah untuk mula!",
        reply_markup=main_kb())

# ─── Admin Helper ─────────────────────────────────────────────────────────────

async def _admin_notify(context: ContextTypes.DEFAULT_TYPE, text: str):
    if not ADMIN_ID:
        return
    try:
        await context.bot.send_message(chat_id=ADMIN_ID, text=text)
    except Exception as exc:
        log.warning(f"Admin notify: {_safe_error(exc)}")

# ─── Rate Limiter ─────────────────────────────────────────────────────────────
# Max 5 button presses per 3 seconds per user.

_rate_data: dict[int, list] = {}
_RATE_WINDOW = 3.0
_RATE_MAX    = 5

def _is_rate_limited(user_id: int) -> bool:
    now = time.monotonic()
    stamps = [t for t in _rate_data.get(user_id, []) if now - t < _RATE_WINDOW]
    if len(stamps) >= _RATE_MAX:
        _rate_data[user_id] = stamps
        return True
    stamps.append(now)
    _rate_data[user_id] = stamps
    return False

# ─── Button Router ────────────────────────────────────────────────────────────

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    data = q.data
    # Answer FIRST — dismisses the Telegram loading spinner immediately.
    # Never call q.answer() again inside any sub-handler.
    await q.answer()
    log.info(f"Button: {data} from {update.effective_user.id}")

    # ── Rate limit check ──────────────────────────────────────────────────────
    if _is_rate_limited(update.effective_user.id):
        await q.answer("⏳ Terlalu laju! Sila tunggu sebentar.", show_alert=True)
        return

    try:
        if   data == "home":               await show_home(update, context)
        elif data == "shop":               await show_shop(update, context)
        elif data == "myorders":           await my_orders(update, context)
        elif data == "referral":           await show_referral(update, context)
        elif data == "support":            await show_support(update, context)
        elif data == "qty_display":        pass  # display-only button, answer() already called above

        elif data.startswith("product_"):
            await show_product(update, context, int(data.split("_")[1]))

        elif data.startswith("qty_minus_"):
            parts = data.split("_")          # ['qty', 'minus', pid, qty]
            await qty_adjust(update, context, int(parts[2]), int(parts[3]), -1)

        elif data.startswith("qty_plus_"):
            parts = data.split("_")          # ['qty', 'plus', pid, qty]
            await qty_adjust(update, context, int(parts[2]), int(parts[3]), +1)

        elif data.startswith("buy_"):
            parts = data.split("_")
            await create_order(update, context, int(parts[1]), int(parts[2]))

        elif data.startswith("payment_"):
            await show_payment(update, context, data[len("payment_"):])

        elif data.startswith("paid_"):
            await handle_paid(update, context, data[len("paid_"):])

        elif data.startswith("cancel_"):
            await cancel_order(update, context, data[len("cancel_"):])

        elif data.startswith("approve_"):
            await approve_order(update, context, data[len("approve_"):])

        elif data.startswith("reject_"):
            await reject_order(update, context, data[len("reject_"):])

        else:
            log.warning(f"Unknown callback_data: {data!r}")
            try:
                await q.edit_message_text(
                    "⚠️ Butang tidak dikenali. Sila mulakan semula.",
                    reply_markup=back_home(),
                )
            except Exception:
                pass

    except Exception as exc:
        log.error(f"Button handler error [{data}]: {_safe_error(exc)}", exc_info=True)
        try:
            await q.message.reply_text(
                "⚠️ Ralat berlaku. Sila cuba lagi atau hubungi @berryrc"
            )
        except Exception:
            pass

# ─── Admin: Send Account Details ─────────────────────────────────────────────

pending_send: dict[int, str] = {}   # {admin_user_id: order_id}

async def send_account_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin uses /send ORDER_ID then types account details to forward to buyer."""
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Not allowed")
        return

    if not context.args:
        await update.message.reply_text("Usage: /send ORDER_ID")
        return

    order_id = context.args[0]
    try:
        rows = await _run_supabase(
            f"orders.send_fetch id={order_id}",
            lambda: sb_get("orders", f"select=user_id,product_name,status&id=eq.{order_id}&limit=1"),
        )
        if not rows:
            await update.message.reply_text(f"⚠️ Order {order_id} tidak dijumpai.")
            return
        order = rows[0]
    except Exception as exc:
        log.warning(f"Supabase /send fetch: {_safe_error(exc)}", exc_info=True)
        await update.message.reply_text(f"⚠️ Ralat ambil order. Cuba lagi.")
        return

    pending_send[ADMIN_ID] = {"order_id": order_id, "user_id": order["user_id"]}
    log.info(f"Admin /send initiated for order {order_id} → user {order['user_id']}")
    await update.message.reply_text(
        f"📦 Order: {order_id}\n"
        f"🛍 Product: {order.get('product_name', '')}\n\n"
        f"Send account details now (email & password):"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages: reply keyboard numbers, Home button, and admin account delivery."""
    user_id = update.effective_user.id
    text    = (update.message.text or "").strip()

    # ── Reply keyboard: "🏠 Home" button ──────────────────────────────────────
    if text == "🏠 Home":
        await update.message.reply_text(
            f"👋 Hi {update.effective_user.first_name}!\nWelcome to Berry Store.",
            reply_markup=ReplyKeyboardRemove(),
        )
        await update.message.reply_text(
            "Pilih menu di bawah:",
            reply_markup=main_kb(),
        )
        return

    # ── Reply keyboard: number selects a product ───────────────────────────────
    if text.isdigit():
        products = context.user_data.get("shop_products") or []
        if products:
            idx = int(text) - 1
            if 0 <= idx < len(products):
                product_id = products[idx]["id"]
                log.info(f"Keyboard product select: user={user_id} number={text} product_id={product_id}")
                await show_product(update, context, product_id)
                return
            else:
                await update.message.reply_text(
                    f"⚠️ Nombor '{text}' tidak wujud. Pilih 1–{len(products)}.",
                )
                return

    # ── Admin: pending_receipt (customer uploading receipt text — not used but kept) ─

    # ── Admin: account delivery flow ──────────────────────────────────────────
    if user_id != ADMIN_ID or ADMIN_ID not in pending_send:
        return

    info     = pending_send.pop(ADMIN_ID)
    order_id = info["order_id"]
    buyer_id = info["user_id"]
    details  = update.message.text

    # Fetch product duration from order → product
    duration = "-"
    try:
        def duration_lookup():
            o_rows = sb_get("orders", f"select=product_id&id=eq.{order_id}&limit=1")
            if not o_rows or not o_rows[0].get("product_id"):
                return "-"
            p_rows = sb_get("products", f"select=duration&id=eq.{o_rows[0]['product_id']}&limit=1")
            return p_rows[0].get("duration") or "-" if p_rows else "-"
        duration = await _run_supabase(f"orders.duration id={order_id}", duration_lookup)
    except Exception as exc:
        log.warning(f"Could not fetch duration for order {order_id}: {_safe_error(exc)}")

    try:
        await context.bot.send_message(
            chat_id=buyer_id,
            text=(
                f"🎉 Akaun anda sudah sedia!\n"
                f"Order ID: {order_id}\n\n"
                f"{details}\n\n"
                f"⚠️ Simpan maklumat ini. Jangan kongsi dengan sesiapa.\n"
                f"📌 Tempoh: {duration}\n"
                f"💬 Ada masalah? Hubungi: @berryrc"
            ),
        )
        await update.message.reply_text(f"✅ Maklumat akaun berjaya dihantar kepada pembeli (Order: {order_id})")
        log.info(f"Account details sent for order {order_id} → buyer {buyer_id}")
    except Exception as exc:
        log.warning(f"Send account details error: {_safe_error(exc)}")
        await update.message.reply_text(f"⚠️ Gagal hantar kepada pembeli: {_safe_error(exc)}")


# ─── /stock ───────────────────────────────────────────────────────────────────

async def cmd_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Bukan admin.")
        return

    try:
        products = await _run_supabase(
            "products.stock_list",
            lambda: sb_get("products", "select=id,name,stock&order=id"),
        ) or []
    except Exception as exc:
        log.warning(f"stock fetch error: {_safe_error(exc)}", exc_info=True)
        await update.message.reply_text("⚠️ Gagal muatkan produk. Cuba lagi.")
        return

    # No args → show product list with IDs
    if not context.args:
        if not products:
            await update.message.reply_text("⚠️ Tiada produk dalam database.")
            return
        lines = ["📦 SENARAI PRODUK & STOK", "─────────────────────"]
        for p in products:
            lines.append(f"ID {p['id']}  |  {p['name']}  |  Stok: {p['stock']}")
        lines.append("─────────────────────")
        lines.append("Guna: /stock <id> <kuantiti>")
        lines.append("Contoh: /stock 1 50")
        await update.message.reply_text("\n".join(lines))
        return

    # Validate args: /stock <product_id> <quantity>
    if len(context.args) != 2:
        await update.message.reply_text("⚠️ Format salah.\nGuna: /stock <id> <kuantiti>\nContoh: /stock 1 50")
        return

    try:
        product_id = int(context.args[0])
        new_stock  = int(context.args[1])
    except ValueError:
        await update.message.reply_text("⚠️ ID dan kuantiti mesti nombor.\nContoh: /stock 1 50")
        return

    if new_stock < 0:
        await update.message.reply_text("⚠️ Stok tidak boleh negatif.")
        return

    # Find product name for confirmation message
    product = next((p for p in products if p["id"] == product_id), None)
    if not product:
        await update.message.reply_text(f"⚠️ Produk ID {product_id} tidak dijumpai.\nGuna /stock untuk tengok senarai.")
        return

    try:
        await _run_supabase(
            f"products.stock_update id={product_id}",
            lambda: sb_patch("products", f"id=eq.{product_id}", {"stock": new_stock}),
        )
        refreshed = [{**p, "stock": new_stock} if p["id"] == product_id else p for p in products]
        _cache_products(refreshed)
    except Exception as exc:
        log.warning(f"stock update error: {_safe_error(exc)}", exc_info=True)
        await update.message.reply_text("⚠️ Gagal update stok. Cuba lagi.")
        return

    log.info(f"Stock updated: product {product_id} → {new_stock} by admin")
    await update.message.reply_text(
        f"✅ Stok berjaya dikemaskini!\n\n"
        f"Produk : {product['name']}\n"
        f"Stok lama: {product['stock']}\n"
        f"Stok baru: {new_stock}"
    )

# ─── /broadcast ───────────────────────────────────────────────────────────────

async def cmd_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Bukan admin.")
        return

    message = " ".join(context.args).strip() if context.args else ""
    if not message:
        await update.message.reply_text(
            "⚠️ Sila masukkan mesej.\n\nContoh:\n/broadcast Produk baru dah ada! Check /start sekarang 🔥"
        )
        return

    try:
        users = await _run_supabase(
            "broadcast.users",
            lambda: sb_get("users", "select=id"),
        ) or []
    except Exception as exc:
        log.warning(f"broadcast fetch users error: {_safe_error(exc)}", exc_info=True)
        await update.message.reply_text("⚠️ Gagal ambil senarai pengguna. Cuba lagi.")
        return

    if not users:
        await update.message.reply_text("⚠️ Tiada pengguna dalam database.")
        return

    sent = failed = 0
    for u in users:
        try:
            await context.bot.send_message(chat_id=u["id"], text=message)
            sent += 1
        except Exception as exc:
            log.warning(f"broadcast failed for user {u['id']}: {_safe_error(exc)}")
            failed += 1

    log.info(f"Broadcast done: {sent} sent, {failed} failed")
    await update.message.reply_text(
        f"📢 Broadcast selesai!\n\n"
        f"✅ Berjaya dihantar : {sent} pengguna\n"
        f"❌ Gagal            : {failed} pengguna"
    )

# ─── /adminorders ─────────────────────────────────────────────────────────────

async def cmd_adminorders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Bukan admin.")
        return

    try:
        orders = await _run_supabase(
            "admin.orders_pending",
            lambda: sb_get("orders", "select=id,user_id,username,product_name,amount,status&status=in.(pending,waiting_approval)&order=id.desc&limit=10"),
        ) or []
    except Exception as exc:
        log.warning(f"adminorders error: {_safe_error(exc)}", exc_info=True)
        await update.message.reply_text("⚠️ Gagal muatkan orders. Cuba lagi.")
        return

    if not orders:
        await update.message.reply_text("✅ Tiada order yang menunggu tindakan.")
        return

    STATUS_LABEL = {
        "pending":          "⏳ Belum bayar",
        "waiting_approval": "🔍 Tunggu approve",
    }

    lines = ["📋 PENDING ORDERS", "─────────────────────"]
    for o in orders:
        label = STATUS_LABEL.get(o["status"], o["status"])
        lines.append(
            f"{label}\n"
            f"  Order  : {o['id']}\n"
            f"  Produk : {o.get('product_name', '-')}\n"
            f"  Customer: @{o.get('username', '-')}\n"
            f"  RM {o['amount']}\n"
        )

    lines.append("─────────────────────")
    lines.append(f"Total: {len(orders)} order")

    await update.message.reply_text("\n".join(lines))

# ─── /ping ────────────────────────────────────────────────────────────────────

async def cmd_ping(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Pong! Bot hidup ✅")

# ─── /admin Dashboard ─────────────────────────────────────────────────────────

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Bukan admin.")
        return

    try:
        all_orders_result = await _run_supabase(
            "admin.orders_summary",
            lambda sb: sb.table("orders").select("status, amount").execute(),
        )
        products_result = await _run_supabase(
            "admin.products_summary",
            lambda sb: sb.table("products").select("name, stock, price").execute(),
        )
        users_result = await _run_supabase(
            "admin.users_summary",
            lambda sb: sb.table("users").select("id").execute(),
        )

        all_orders     = all_orders_result.data or []
        products       = products_result.data or []
        total_users    = len(users_result.data or [])

        pending        = [o for o in all_orders if o["status"] == "pending"]
        waiting        = [o for o in all_orders if o["status"] == "waiting_approval"]
        completed      = [o for o in all_orders if o["status"] == "completed"]
        total_revenue  = sum(float(o["amount"]) for o in completed)
        low_stock      = [p for p in products if p.get("stock", 0) <= 3]

    except Exception as exc:
        log.warning(f"Admin dashboard error: {_safe_error(exc)}", exc_info=True)
        await update.message.reply_text(f"⚠️ Gagal muatkan data: {_safe_error(exc)}")
        return

    now = datetime.now(ZoneInfo("Asia/Kuala_Lumpur")).strftime("%d/%m/%Y %H:%M")

    lines = [
        f"🛠 ADMIN DASHBOARD",
        f"📅 {now}",
        f"─────────────────────",
        f"👤 Total Users   : {total_users}",
        f"📦 Total Orders  : {len(all_orders)}",
        f"✅ Completed     : {len(completed)}",
        f"🔍 Pending Resit : {len(waiting)}",
        f"⏳ Pending Pay   : {len(pending)}",
        f"💰 Total Revenue : RM {total_revenue:.2f}",
        f"─────────────────────",
    ]

    if low_stock:
        lines.append("⚠️ LOW STOCK (≤3 unit):")
        for p in low_stock:
            lines.append(f"  • {p['name']} — {p['stock']} unit")
    else:
        lines.append("✅ Semua stok mencukupi")

    await update.message.reply_text("\n".join(lines))

# ─── Global Error Handler ─────────────────────────────────────────────────────

async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    if isinstance(context.error, Conflict):
        log.error(
            "Telegram polling conflict detected. Another running bot instance is using the same token. "
            "Stop the old Replit/deployment/session that uses this bot token."
        )
        return
    if isinstance(context.error, InvalidToken):
        log.error("Telegram token rejected by Telegram API. Check the TELEGRAM_BOT_TOKEN secret.")
        return
    log.error(f"Telegram error: {_safe_error(context.error)}", exc_info=True)

# ─── Build Application ────────────────────────────────────────────────────────

def build_app() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("ping",        cmd_ping))
    app.add_handler(CommandHandler("admin",       cmd_admin))
    app.add_handler(CommandHandler("adminorders", cmd_adminorders))
    app.add_handler(CommandHandler("stock",       cmd_stock))
    app.add_handler(CommandHandler("broadcast",   cmd_broadcast))
    app.add_handler(CommandHandler("shop",   show_shop))
    app.add_handler(CommandHandler("orders", my_orders))
    app.add_handler(CommandHandler("send",   send_account_command))
    app.add_handler(CallbackQueryHandler(on_button))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(on_error)
    return app

# ─── Auto-Restart Polling Loop ────────────────────────────────────────────────

def main():
    if not _validate_telegram_token():
        sys.exit(1)

    retry_delay = 5          # seconds before first retry
    max_delay   = 120        # cap at 2 minutes
    attempt     = 0

    while True:
        attempt += 1
        log.info(f"Bot starting (attempt #{attempt})...")
        try:
            app = build_app()
            app.run_polling(
                drop_pending_updates=True,
                allowed_updates=Update.ALL_TYPES,
                close_loop=False,
            )
            log.info("Bot berhenti dengan bersih.")
            break

        except KeyboardInterrupt:
            log.info("Bot dihenti oleh pengguna (Ctrl+C).")
            break

        except InvalidToken:
            log.critical("Telegram token rejected by Telegram API. Update the TELEGRAM_BOT_TOKEN secret, then restart the workflow.")
            sys.exit(1)

        except Exception as exc:
            log.error(f"Bot crash: {_safe_error(exc)}", exc_info=True)
            log.info(f"Restart dalam {retry_delay}s...")
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_delay)   # exponential backoff


if __name__ == "__main__":
    main()
