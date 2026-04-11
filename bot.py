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
from datetime import datetime
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

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

# ─── Load Environment Variables ───────────────────────────────────────────────

def _get_env(key: str, fallback: str = "") -> str:
    """Get env var, strip whitespace, return fallback if empty."""
    return (os.getenv(key) or fallback).strip()

BOT_TOKEN    = _get_env("BOT_TOKEN") or _get_env("TOKEN")
SUPABASE_URL = _get_env("SUPABASE_URL").rstrip("/")
SUPABASE_KEY = _get_env("SUPABASE_KEY")
ADMIN_ID     = 0
PORT         = int(_get_env("PORT", "8000"))

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

def _init_supabase():
    """Create (or recreate) Supabase client. Returns True on success."""
    global _sb_client
    if not _supabase_ready:
        return False
    try:
        from supabase import create_client
        _sb_client = create_client(SUPABASE_URL, SUPABASE_KEY)
        log.info("Supabase ✅ client berjaya dibuat")
        return True
    except Exception as exc:
        log.error(f"Supabase ❌ gagal buat client: {exc}")
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

# ─── Flask Keep-Alive Server ──────────────────────────────────────────────────

from flask import Flask, jsonify

_app = Flask(__name__)

@_app.route("/")
def _index():
    return "Bot hidup ✅", 200

@_app.route("/health")
def _health():
    return jsonify(status="ok", supabase=_sb_client is not None), 200

def _start_flask():
    log.info(f"Flask keep-alive berjalan di port {PORT}")
    _app.run(host="0.0.0.0", port=PORT, use_reloader=False, threaded=True)

threading.Thread(target=_start_flask, daemon=True).start()

# ─── Telegram Imports ─────────────────────────────────────────────────────────

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
        products = get_sb().table("products").select("*").execute().data
    except Exception as exc:
        log.warning(f"Supabase shop: {exc}")
        msg = "⚠️ Gagal muatkan produk. Cuba lagi."
        if update.callback_query:
            await update.callback_query.edit_message_text(msg, reply_markup=back_home())
        else:
            await update.message.reply_text(msg, reply_markup=back_home())
        return

    if not products:
        text, kb = "⚠️ Tiada produk tersedia.", back_home()
    else:
        text = (
            "╭ - - - - - - - - - - - - - - - - - - - ╮\n"
            "┊  LIST PRODUCT\n"
            "┊ - - - - - - - - - - - - - - - - - - - -\n"
        )
        rows = []
        for i, p in enumerate(products, 1):
            text += f"┊ {i}. {p['name']} ( {p['stock']} )\n"
            rows.append([InlineKeyboardButton(str(i), callback_data=f"product_{p['id']}")])
        text += "╰ - - - - - - - - - - - - - - - - - - - ╯"
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
        p = get_sb().table("products").select("*").eq("id", product_id).single().execute().data
    except Exception as exc:
        log.warning(f"Supabase product: {exc}")
        await update.callback_query.edit_message_text("⚠️ Gagal muatkan produk.", reply_markup=back_shop())
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
    try:
        sb = get_sb()
        p  = sb.table("products").select("*").eq("id", product_id).single().execute().data
    except Exception as exc:
        log.warning(f"Supabase create_order fetch: {exc}")
        await update.callback_query.answer("⚠️ Ralat sambungan. Cuba lagi.", show_alert=True)
        return

    if p["stock"] < qty:
        await update.callback_query.answer("⚠️ Stok tidak mencukupi!", show_alert=True)
        return

    order_id = f"ORD{random.randint(10000, 99999)}{user.id}"
    total    = round(p["price"] * qty, 2)
    try:
        sb.table("orders").insert({
            "id": order_id, "user_id": user.id, "username": user.username or "",
            "product_id": product_id, "product_name": p["name"],
            "quantity": qty, "amount": total, "status": "pending",
        }).execute()
    except Exception as exc:
        log.warning(f"Supabase create_order insert: {exc}")
        await update.callback_query.answer("⚠️ Gagal buat order. Cuba lagi.", show_alert=True)
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
    query = update.callback_query
    try:
        order = get_sb().table("orders").select("*").eq("id", order_id).single().execute().data
    except Exception as exc:
        log.warning(f"Supabase payment: {exc}")
        await query.edit_message_text("⚠️ Gagal muatkan maklumat pembayaran.")
        return

    await query.answer()

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
        await update.callback_query.answer("⛔ Bukan admin.", show_alert=True); return
    try:
        sb    = get_sb()
        order = sb.table("orders").select("*").eq("id", order_id).single().execute().data
        sb.table("orders").update({"status": "completed"}).eq("id", order_id).execute()
        if order.get("product_id"):
            p = sb.table("products").select("stock").eq("id", order["product_id"]).single().execute().data
            sb.table("products").update({"stock": max(0, p["stock"] - order["quantity"])}).eq("id", order["product_id"]).execute()
    except Exception as exc:
        log.warning(f"Supabase approve: {exc}")
        await update.callback_query.answer("⚠️ Ralat approve.", show_alert=True); return

    log.info(f"Order {order_id} approved by admin")
    await update.callback_query.edit_message_caption(
        caption=(update.callback_query.message.caption or "") + "\n\n✅ APPROVED", reply_markup=None)
    try:
        await context.bot.send_message(chat_id=order["user_id"],
            text="✅ Payment confirmed! Admin will send your account shortly.")
    except Exception as exc:
        log.warning(f"Notify user approve: {exc}")


async def reject_order(update: Update, context: ContextTypes.DEFAULT_TYPE, order_id: str):
    if update.effective_user.id != ADMIN_ID:
        await update.callback_query.answer("⛔ Bukan admin.", show_alert=True); return
    try:
        sb    = get_sb()
        order = sb.table("orders").select("*").eq("id", order_id).single().execute().data
        sb.table("orders").update({"status": "rejected"}).eq("id", order_id).execute()
    except Exception as exc:
        log.warning(f"Supabase reject: {exc}")
        await update.callback_query.answer("⚠️ Ralat reject.", show_alert=True); return

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
    await q.answer()
    log.debug(f"Button: {data} from {update.effective_user.id}")

    try:
        if   data == "home":               await show_home(update, context)
        elif data == "shop":               await show_shop(update, context)
        elif data == "myorders":           await my_orders(update, context)
        elif data == "referral":           await show_referral(update, context)
        elif data == "support":            await show_support(update, context)
        elif data == "qty_display":        await q.answer("Guna ➖ ➕ untuk tukar qty")

        elif data.startswith("product_"):
            # product_{product_id}
            await show_product(update, context, int(data.split("_")[1]))

        elif data.startswith("qty_minus_"):
            # qty_minus_{product_id}_{current_qty}
            parts = data.split("_")          # ['qty', 'minus', pid, qty]
            await qty_adjust(update, context, int(parts[2]), int(parts[3]), -1)

        elif data.startswith("qty_plus_"):
            # qty_plus_{product_id}_{current_qty}
            parts = data.split("_")          # ['qty', 'plus', pid, qty]
            await qty_adjust(update, context, int(parts[2]), int(parts[3]), +1)

        elif data.startswith("buy_"):
            # buy_{product_id}_{qty}
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

    try:
        await context.bot.send_message(
            chat_id=buyer_id,
            text=(
                f"🎉 Your account is ready!\n"
                f"Order ID: {order_id}\n\n"
                f"{details}\n\n"
                f"Keep this info safe. Do not share with anyone."
            ),
        )
        await update.message.reply_text(f"✅ Account details sent to buyer (Order: {order_id})")
        log.info(f"Account details sent for order {order_id} → buyer {buyer_id}")
    except Exception as exc:
        log.warning(f"Send account details error: {exc}")
        await update.message.reply_text(f"⚠️ Failed to send to buyer: {exc}")


# ─── Global Error Handler ─────────────────────────────────────────────────────

async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE):
    log.error(f"Telegram error: {context.error}", exc_info=True)

# ─── Build Application ────────────────────────────────────────────────────────

def build_app() -> Application:
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",  cmd_start))
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
            # run_polling only returns on clean shutdown
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
