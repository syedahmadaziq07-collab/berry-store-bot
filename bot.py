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
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

# ─── Logging Setup ────────────────────────────────────────────────────────────
# Logs to console AND to bot.log file for debugging

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
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

try:
    ADMIN_ID = int(_get_env("ADMIN_ID", "0"))
except ValueError:
    log.warning("ADMIN_ID bukan nombor — ditetapkan kepada 0")

# ─── Startup Check ────────────────────────────────────────────────────────────

log.info("=" * 60)
log.info("DEBUG STARTUP — ENVIRONMENT VARIABLES")
log.info("=" * 60)
log.info(f"BOT_TOKEN        : {'✅ set' if BOT_TOKEN else '❌ MISSING'}")
log.info(f"SUPABASE_URL     : {SUPABASE_URL[:30] + '...' if SUPABASE_URL else '❌ MISSING'}")
log.info(f"SUPABASE_URL len : {len(SUPABASE_URL)} chars")
log.info(f"SUPABASE_KEY len : {len(SUPABASE_KEY)} chars")
log.info(f"SUPABASE_KEY ok  : {'✅ starts with eyJ' if SUPABASE_KEY.startswith('eyJ') else '❌ does NOT start with eyJ'}")
log.info(f"ADMIN_ID         : {ADMIN_ID if ADMIN_ID else '❌ MISSING or 0'}")
log.info(f"PORT             : {PORT}")
log.info("=" * 60)

if not BOT_TOKEN:
    log.critical("BOT_TOKEN tidak ditetapkan. Set dalam Replit Secrets → BOT_TOKEN")
    sys.exit(1)

# Validate Supabase config
_supabase_ready = False
if SUPABASE_URL and SUPABASE_KEY:
    if not SUPABASE_URL.startswith("https://"):
        log.warning(f"SUPABASE_URL tidak valid (mesti https://): {SUPABASE_URL[:40]}")
        SUPABASE_URL = ""
    elif not (SUPABASE_KEY.startswith("eyJ") and len(SUPABASE_KEY) > 100):
        log.warning(f"SUPABASE_KEY format salah (len={len(SUPABASE_KEY)}). Guna anon/public key dari Supabase.")
        SUPABASE_KEY = ""
    else:
        _supabase_ready = True
else:
    log.warning("Supabase tidak dikonfigurasi — fungsi kedai tidak aktif")

# ─── Supabase Client ──────────────────────────────────────────────────────────

_sb_client = None
_products_cache = {"data": [], "updated_at": 0.0}

def _init_supabase():
    """Create (or recreate) Supabase client. Returns True on success."""
    global _sb_client
    log.debug(f"[SUPABASE INIT] _supabase_ready={_supabase_ready}")
    if not _supabase_ready:
        log.warning("[SUPABASE INIT] Skipped — _supabase_ready is False. Check SUPABASE_URL and SUPABASE_KEY.")
        return False
    try:
        from supabase import create_client
        _sb_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        log.info("[SUPABASE INIT] ✅ Client berjaya dibuat")
        return True
    except Exception as exc:
        log.error(f"[SUPABASE INIT] ❌ create_client failed: {exc}")
        _sb_client = None
        return False

def get_sb():
    """Return Supabase client, auto-reconnect once if None."""
    global _sb_client
    if _sb_client is None:
        _init_supabase()
    if _sb_client is None:
        raise RuntimeError("Supabase tidak tersedia")
    return _sb_client

_init_supabase()

def _reset_supabase(reason: str):
    global _sb_client
    log.warning(f"Supabase client reset: {reason}")
    _sb_client = None

async def _run_supabase(label: str, operation, attempts: int = 3, timeout: int = 12):
    last_exc = None
    for attempt in range(1, attempts + 1):
        started = time.monotonic()
        try:
            result = await asyncio.wait_for(
                asyncio.to_thread(lambda: operation(get_sb())),
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
                f"type={type(exc).__name__} error={str(exc)[:300]}"
            )
            _reset_supabase(f"{label} attempt {attempt} failed")
            if attempt < attempts:
                await asyncio.sleep(min(0.4 * (2 ** (attempt - 1)) + random.uniform(0, 0.3), 3))
    raise last_exc

def _cache_products(products):
    _products_cache["data"] = products or []
    _products_cache["updated_at"] = time.time()

def _cached_products(max_age: int = 300):
    products = _products_cache.get("data") or []
    updated_at = float(_products_cache.get("updated_at") or 0)
    age = time.time() - updated_at if updated_at else 999999
    if products and age <= max_age:
        return products, int(age)
    return [], int(age)

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
        supabase=_sb_client is not None,
        cached_products=len(cached),
        products_cache_age_seconds=age if cached else None,
    ), 200

def _start_flask():
    log.info(f"Flask keep-alive berjalan di port {PORT}")
    _app.run(host="0.0.0.0", port=PORT, use_reloader=False, threaded=True)

threading.Thread(target=_start_flask, daemon=True).start()

# ─── Telegram Imports ─────────────────────────────────────────────────────────

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import Conflict
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

# ─── /start ───────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    log.info(f"/start from {user.id} (@{user.username})")

    # Instant reply so user knows bot is alive
    await update.message.reply_text("Bot hidup ✅")

    total_users = total_sold = 0
    try:
        sb = get_sb()
        sb.table("users").upsert({
            "id": user.id,
            "username": user.username or "",
            "first_name": user.first_name or "",
        }).execute()
        total_users = len(sb.table("users").select("id").execute().data)
        total_sold  = len(sb.table("orders").select("id").eq("status", "completed").execute().data)
    except Exception as exc:
        log.warning(f"Supabase /start: {exc}")

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
    try:
        result = await _run_supabase(
            "products.list",
            lambda sb: sb.table("products").select("id, name, stock, price, duration").order("id").execute(),
        )
        products = result.data or []
        _cache_products(products)
        log.info(f"Products loaded: {len(products)} items source=supabase")
    except Exception as exc:
        products, age = _cached_products()
        if products:
            log.error(f"Shop error using cached products age_s={age}: {exc}", exc_info=True)
        else:
            log.error(f"Shop error no cache available: {exc}", exc_info=True)
            msg = f"⚠️ Gagal muatkan produk. Cuba lagi.\nError: {str(exc)[:100]}"
            if update.callback_query:
                await update.callback_query.edit_message_text(msg, reply_markup=back_home())
            else:
                await update.message.reply_text(msg, reply_markup=back_home())
            return

    if not products:
        text = "⚠️ Tiada produk tersedia."
        kb = back_home()
    else:
        text = "╭─────────────────────╮\n┊  LIST PRODUCT\n┊─────────────────────\n"
        rows = []
        for i, p in enumerate(products, 1):
            text += f"┊ {i}. {p['name']} ( {p['stock']} )\n"
            rows.append([InlineKeyboardButton(str(i), callback_data=f"product_{p['id']}")])
        text += "╰─────────────────────╯"
        rows.append([InlineKeyboardButton("🏠 Home", callback_data="home")])
        kb = InlineKeyboardMarkup(rows)

    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=kb)
    else:
        await update.message.reply_text(text, reply_markup=kb)

# ─── Product Detail ───────────────────────────────────────────────────────────

async def show_product(update: Update, context: ContextTypes.DEFAULT_TYPE, product_id: int, qty: int = 1):
    """Show product detail with live quantity and total price."""
    qty = max(1, min(qty, 10))   # clamp between 1–10

    try:
        result = await _run_supabase(
            f"products.detail id={product_id}",
            lambda sb: sb.table("products").select("*").eq("id", product_id).single().execute(),
        )
        p = result.data
    except Exception as exc:
        cached, age = _cached_products()
        p = next((item for item in cached if str(item.get("id")) == str(product_id)), None)
        if p:
            log.warning(f"Supabase product detail fallback id={product_id} cache_age_s={age}: {exc}")
        else:
            log.warning(f"Supabase product detail failed id={product_id}: {exc}", exc_info=True)
            await update.callback_query.edit_message_text("⚠️ Gagal muatkan produk. Cuba lagi.", reply_markup=back_shop())
            return

    total = round(p["price"] * qty, 2)
    stock = p.get("stock", 0)

    await update.callback_query.edit_message_text(
        f"📦 {p['name']}\n"
        f"├─ Stock   : {stock} units\n"
        f"├─ Price   : RM {p['price']}\n"
        f"├─ Duration: {p.get('duration', '-')}\n"
        f"└─ Total   : RM {total}\n\n"
        f"• Akaun diberikan selepas bayar.\n"
        f"• Akaun peribadi, tidak dikongsi.",
        reply_markup=InlineKeyboardMarkup([
            [
                InlineKeyboardButton("➖", callback_data=f"qty_minus_{product_id}_{qty}"),
                InlineKeyboardButton(f"  {qty}  ",  callback_data="qty_display"),
                InlineKeyboardButton("➕", callback_data=f"qty_plus_{product_id}_{qty}"),
            ],
            [InlineKeyboardButton(f"🛒 Buy Now  x{qty}  (RM {total})", callback_data=f"buy_{product_id}_{qty}")],
            [InlineKeyboardButton("⬅️ Back to Shop", callback_data="shop")],
        ]),
    )

# ─── Quantity ─────────────────────────────────────────────────────────────────

async def qty_adjust(update: Update, context: ContextTypes.DEFAULT_TYPE, product_id: int, current_qty: int, delta: int):
    """Recalculate qty and refresh product detail. Qty is embedded in callback_data, not user_data."""
    new_qty = max(1, min(current_qty + delta, 10))
    await show_product(update, context, product_id, new_qty)

# ─── Create Order ─────────────────────────────────────────────────────────────

async def create_order(update: Update, context: ContextTypes.DEFAULT_TYPE, product_id: int, qty: int):
    user = update.effective_user
    print(f"[CREATE_ORDER] product_id={product_id} qty={qty} user={user.id}")
    try:
        product_result = await _run_supabase(
            f"products.order_fetch id={product_id}",
            lambda sb: sb.table("products").select("*").eq("id", product_id).single().execute(),
        )
        p = product_result.data
    except Exception as exc:
        log.warning(f"Supabase create_order fetch product_id={product_id}: {exc}", exc_info=True)
        print(f"[CREATE_ORDER] ERROR fetching product: {exc}")
        # answer() already called in on_button — use edit instead
        await update.callback_query.edit_message_text(
            "⚠️ Ralat sambungan. Cuba lagi.", reply_markup=back_shop())
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
            lambda sb: sb.table("orders").insert({
                "id": order_id, "user_id": user.id, "username": user.username or "",
                "product_id": product_id, "product_name": p["name"],
                "quantity": qty, "amount": total, "status": "pending",
            }).execute(),
            attempts=1,
        )
    except Exception as exc:
        log.warning(f"Supabase create_order insert: {exc}")
        print(f"[CREATE_ORDER] ERROR inserting order: {exc}")
        await update.callback_query.edit_message_text(
            f"⚠️ Gagal buat order.\n\nRalat: {exc}\n\nSila hubungi admin.",
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

async def show_payment(update: Update, context: ContextTypes.DEFAULT_TYPE, order_id: str):
    # answer() already called in on_button — do NOT call query.answer() here
    query = update.callback_query
    try:
        order = get_sb().table("orders").select("*").eq("id", order_id).single().execute().data
    except Exception as exc:
        log.warning(f"Supabase payment: {exc}")
        await query.edit_message_text("⚠️ Gagal muatkan maklumat pembayaran.", reply_markup=back_shop())
        return

    qr = os.path.join(os.path.dirname(os.path.abspath(__file__)), "payment_qr.png")

    # Send QR photo with order details as caption
    if os.path.exists(qr):
        await context.bot.send_photo(
            chat_id=query.message.chat_id,
            photo=open(qr, "rb"),
            caption=(
                f"💳 PAYMENT DETAILS\n\n"
                f"Order ID: {order_id}\n"
                f"Amount: RM {order['amount']}\n\n"
                f"Scan QR code below to pay 👇"
            ),
        )
    else:
        log.warning("payment_qr.png not found — skipping QR photo")
        await context.bot.send_message(
            chat_id=query.message.chat_id,
            text=(
                f"💳 PAYMENT DETAILS\n\n"
                f"Order ID: {order_id}\n"
                f"Amount: RM {order['amount']}\n\n"
                f"⚠️ QR code tidak tersedia. Hubungi admin."
            ),
        )

    # Send separate message with action buttons
    await context.bot.send_message(
        chat_id=query.message.chat_id,
        text="After payment, click the button below:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ I Have Paid",  callback_data=f"paid_{order_id}")],
            [InlineKeyboardButton("❌ Cancel Order", callback_data=f"cancel_{order_id}")],
        ]),
    )

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
        sb    = get_sb()
        sb.table("orders").update({"receipt_file_id": file_id, "status": "waiting_approval"}).eq("id", order_id).execute()
        order = sb.table("orders").select("*").eq("id", order_id).single().execute().data
    except Exception as exc:
        log.warning(f"Supabase receipt: {exc}")
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
        log.warning(f"Admin photo notify: {exc}")

# ─── Cancel Order ─────────────────────────────────────────────────────────────

async def cancel_order(update: Update, context: ContextTypes.DEFAULT_TYPE, order_id: str):
    try:
        get_sb().table("orders").update({"status": "cancelled"}).eq("id", order_id).execute()
    except Exception as exc:
        log.warning(f"Supabase cancel: {exc}")
    await update.callback_query.edit_message_text(
        f"❌ Order {order_id} dibatalkan.",
        reply_markup=back_home(),
    )

# ─── My Orders ────────────────────────────────────────────────────────────────

async def my_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    try:
        orders = get_sb().table("orders").select("*").eq("user_id", user.id).order("id", desc=True).execute().data
    except Exception as exc:
        log.warning(f"Supabase my_orders: {exc}")
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
    try:
        sb    = get_sb()
        order = sb.table("orders").select("*").eq("id", order_id).single().execute().data
        sb.table("orders").update({"status": "completed"}).eq("id", order_id).execute()
        if order.get("product_id"):
            p = sb.table("products").select("stock").eq("id", order["product_id"]).single().execute().data
            sb.table("products").update({"stock": max(0, p["stock"] - order["quantity"])}).eq("id", order["product_id"]).execute()
    except Exception as exc:
        log.warning(f"Supabase approve: {exc}")
        print(f"[APPROVE] ERROR: {exc}")
        await update.callback_query.edit_message_caption(
            caption=f"⚠️ Ralat approve: {exc}", reply_markup=None)
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
        log.warning(f"Notify user approve: {exc}")

    # Message 2 → Admin (copy-paste /send command)
    try:
        await context.bot.send_message(
            chat_id=ADMIN_ID,
            text=f"/send {order_id}",
        )
    except Exception as exc:
        log.warning(f"Notify admin send command: {exc}")

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
        log.warning(f"Notify admin template: {exc}")


async def reject_order(update: Update, context: ContextTypes.DEFAULT_TYPE, order_id: str):
    if update.effective_user.id != ADMIN_ID:
        await update.callback_query.edit_message_caption(
            caption="⛔ Bukan admin.", reply_markup=None)
        return
    try:
        sb    = get_sb()
        order = sb.table("orders").select("*").eq("id", order_id).single().execute().data
        sb.table("orders").update({"status": "rejected"}).eq("id", order_id).execute()
    except Exception as exc:
        log.warning(f"Supabase reject: {exc}")
        print(f"[REJECT] ERROR: {exc}")
        await update.callback_query.edit_message_caption(
            caption=f"⚠️ Ralat reject: {exc}", reply_markup=None)
        return

    log.info(f"Order {order_id} rejected by admin")
    await update.callback_query.edit_message_caption(
        caption=(update.callback_query.message.caption or "") + "\n\n❌ REJECTED", reply_markup=None)
    try:
        await context.bot.send_message(chat_id=order["user_id"],
            text=f"⚠️ Bayaran Order {order_id} ditolak.\nHubungi support untuk bantuan.")
    except Exception as exc:
        log.warning(f"Notify user reject: {exc}")

# ─── Referral / Support / Home ────────────────────────────────────────────────

async def show_referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user    = update.effective_user
    me      = await context.bot.get_me()
    ref     = f"https://t.me/{me.username}?start=ref_{user.id}"
    await update.callback_query.edit_message_text(
        f"👥 REFERRAL\n─────────────────────\nLink referral anda:\n{ref}\n\nKongsi dan dapatkan reward!",
        reply_markup=back_home())


async def show_support(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.edit_message_text(
        "💬 SUPPORT\n─────────────────────\nHubungi admin:\n• Telegram: @berryrc\n\nMasa operasi: 9am – 11pm",
        reply_markup=back_home())


async def show_home(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    total_users = total_sold = 0
    try:
        sb          = get_sb()
        total_users = len(sb.table("users").select("id").execute().data)
        total_sold  = len(sb.table("orders").select("id").eq("status", "completed").execute().data)
    except Exception as exc:
        log.warning(f"Supabase home: {exc}")
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
        log.warning(f"Admin notify: {exc}")

# ─── Button Router ────────────────────────────────────────────────────────────

async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query
    data = q.data
    # Answer FIRST — dismisses the Telegram loading spinner immediately.
    # Never call q.answer() again inside any sub-handler.
    await q.answer()
    print(f"[BUTTON] Callback received: {q.data} from user {update.effective_user.id}")
    log.info(f"Button: {data} from {update.effective_user.id}")

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

    except Exception as exc:
        log.error(f"Button handler error [{data}]: {exc}", exc_info=True)
        try:
            await q.message.reply_text("⚠️ Ralat berlaku. Cuba lagi.")
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
        order = get_sb().table("orders").select("user_id,product_name,status").eq("id", order_id).single().execute().data
    except Exception as exc:
        log.warning(f"Supabase /send fetch: {exc}")
        await update.message.reply_text(f"⚠️ Order {order_id} not found.")
        return

    pending_send[ADMIN_ID] = {"order_id": order_id, "user_id": order["user_id"]}
    log.info(f"Admin /send initiated for order {order_id} → user {order['user_id']}")
    await update.message.reply_text(
        f"📦 Order: {order_id}\n"
        f"🛍 Product: {order.get('product_name', '')}\n\n"
        f"Send account details now (email & password):"
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Captures admin's next text message and forwards it as account details to the buyer."""
    user_id = update.effective_user.id

    if user_id != ADMIN_ID or ADMIN_ID not in pending_send:
        return

    info     = pending_send.pop(ADMIN_ID)
    order_id = info["order_id"]
    buyer_id = info["user_id"]
    details  = update.message.text

    # Fetch product duration from order → product
    duration = "-"
    try:
        sb    = get_sb()
        order = sb.table("orders").select("product_id").eq("id", order_id).single().execute().data
        if order.get("product_id"):
            p        = sb.table("products").select("duration").eq("id", order["product_id"]).single().execute().data
            duration = p.get("duration") or "-"
    except Exception as exc:
        log.warning(f"Could not fetch duration for order {order_id}: {exc}")

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
        log.warning(f"Send account details error: {exc}")
        await update.message.reply_text(f"⚠️ Gagal hantar kepada pembeli: {exc}")


# ─── /stock ───────────────────────────────────────────────────────────────────

async def cmd_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Bukan admin.")
        return

    try:
        result = await _run_supabase(
            "products.stock_list",
            lambda sb: sb.table("products").select("id, name, stock").order("id").execute(),
        )
        products = result.data or []
    except Exception as exc:
        log.warning(f"stock fetch error: {exc}", exc_info=True)
        await update.message.reply_text(f"⚠️ Gagal muatkan produk: {exc}")
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
        sb.table("products").update({"stock": new_stock}).eq("id", product_id).execute()
    except Exception as exc:
        log.warning(f"stock update error: {exc}")
        await update.message.reply_text(f"⚠️ Gagal update stok: {exc}")
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
        users = get_sb().table("users").select("id").execute().data
    except Exception as exc:
        log.warning(f"broadcast fetch users error: {exc}")
        await update.message.reply_text(f"⚠️ Gagal ambil senarai pengguna: {exc}")
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
            log.warning(f"broadcast failed for user {u['id']}: {exc}")
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
        sb     = get_sb()
        orders = (
            sb.table("orders")
            .select("id, user_id, username, product_name, amount, status")
            .in_("status", ["pending", "waiting_approval"])
            .order("id", desc=True)
            .limit(10)
            .execute()
            .data
        )
    except Exception as exc:
        log.warning(f"adminorders error: {exc}")
        await update.message.reply_text(f"⚠️ Gagal muatkan orders: {exc}")
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
        log.warning(f"Admin dashboard error: {exc}", exc_info=True)
        await update.message.reply_text(f"⚠️ Gagal muatkan data: {exc}")
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
    log.error(f"Telegram error: {context.error}", exc_info=True)

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
            )
            log.info("Bot berhenti dengan bersih.")
            break

        except KeyboardInterrupt:
            log.info("Bot dihenti oleh pengguna (Ctrl+C).")
            break

        except Exception as exc:
            log.error(f"Bot crash: {exc}", exc_info=True)
            log.info(f"Restart dalam {retry_delay}s...")
            time.sleep(retry_delay)
            retry_delay = min(retry_delay * 2, max_delay)   # exponential backoff


if __name__ == "__main__":
    main()
