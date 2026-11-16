"""Owner-fulfilled Turnitin report workflow for Berry Store.

Not an official Turnitin API client; NO scan, AI detection or automatic
document analysis occurs. Customers pay via the existing manual QR flow,
the owner checks reports with properly authorized service access and returns
the result through Telegram. All RPCs use service-role headers, on a private
tenant-scoped database. Public checkout is OFF by default.
"""
from __future__ import annotations

import asyncio
import logging
import math
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import httpx
from turnitin_catalog import SERVICE_CODES, SERVICE_LABELS, available_stock, is_bundle

LOG = logging.getLogger(__name__)
ORDER_RE = re.compile(r"^TT[0-9A-F]{24}$")
MAX_RECEIPT = 10 * 1024 * 1024
MAX_ASSIGNMENT = 20 * 1024 * 1024
PROGRESS_TARGET_SECONDS = 15 * 60
PROGRESS_MAX_WAITING = 99
ASSIGNMENT_MIMES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
REPORT_MIMES = {"application/pdf"}
RECEIPT_MIMES = {"application/pdf", "image/jpeg", "image/png"}


class TurnitinError(RuntimeError):
    pass


def elapsed_estimate(submitted_at: str | None, now: datetime | None = None) -> int:
    """Waiting-time estimate: reach 99% at 15 minutes, hold until delivery."""
    if not submitted_at:
        return 0
    when = datetime.fromisoformat(submitted_at.replace("Z", "+00:00"))
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    elapsed_seconds = max(0, int((now - when).total_seconds()))
    return min(PROGRESS_MAX_WAITING,
               elapsed_seconds * PROGRESS_MAX_WAITING // PROGRESS_TARGET_SECONDS)


def progress_message(order_id: str, percent: int) -> str:
    """Attractive status animation; the percentage is a TIMER, not an API scan."""
    value = max(0, min(100, int(percent)))
    filled = value // 10
    bar = "▰" * filled + "▱" * (10 - filled)
    if value == 100:
        return (f"✅ REPORT DELIVERED — 100%\n"
                f"Order: {order_id}\n"
                f"{bar} 100%\n"
                "📩 Report telah berjaya dihantar.")
    return (f"📑 Assignment sedang diproses\n"
            f"Order: {order_id}\n\n"
            f"{bar} {value}%\n"
            "⏳ Anggaran menunggu — fail awak tengah kami uruskan 😊")


class TurnitinBackend:
    def __init__(self, url: str, key: str, tenant_id: str):
        self.url = url.rstrip("/")
        self.key = key
        self.tenant_id = str(uuid.UUID(tenant_id))
        if not self.url.startswith("https://") or not self.url.endswith(".supabase.co") or not key:
            raise TurnitinError("Private Turnitin backend is not configured")

    def rpc(self, name: str, **kwargs):
        allowed = {
            "catalog", "checkout", "receipt", "approve", "reject", "submit",
            "cancel", "progress_attach", "processing", "progress_mark",
            "delivery_stage", "delivery_claim", "delivery_complete", "customer_status",
            "customer_orders",
        }
        if name not in allowed:
            raise TurnitinError("Invalid Turnitin RPC")
        try:
            r = httpx.post(
                f"{self.url}/rest/v1/rpc/berry_turnitin_{name}",
                headers={"apikey": self.key, "Authorization": f"Bearer {self.key}"},
                json={"p_tenant": self.tenant_id, **kwargs},
                timeout=18, follow_redirects=False,
            )
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError):
            raise TurnitinError(f"Turnitin {name} database unavailable") from None


class TurnitinFlow:
    def __init__(self, backend, admin_id: int, *, checkout_enabled=False,
                 admin_only=True, payment_page=None, on_delivered=None):
        self.backend = backend
        self.admin_id = int(admin_id)
        self.checkout_enabled = checkout_enabled is True
        self.admin_only = admin_only is True
        self.payment_page = payment_page
        self.on_delivered = on_delivered

    def allowed(self, user_id: int):
        return bool(self.checkout_enabled and self.admin_id > 0
                    and (not self.admin_only or user_id == self.admin_id))

    @staticmethod
    def private(update):
        return bool(update.effective_chat and update.effective_chat.type == "private")

    async def call(self, name: str, **kwargs):
        return await asyncio.to_thread(self.backend.rpc, name, **kwargs)

    @staticmethod
    async def respond(update, text, reply_markup=None):
        if update.callback_query:
            try:
                return await update.callback_query.edit_message_text(text, reply_markup=reply_markup)
            except Exception as exc:
                # Telegram rejects edits that exactly repeat the current card.
                # Double-tapping a plan must not trigger the generic error DM.
                if "message is not modified" in str(exc).casefold():
                    return None
                raise
        return await update.effective_message.reply_text(text, reply_markup=reply_markup)

    async def menu(self, update, context):
        if not self.private(update):
            await self.respond(update, "🔐 Turnitin Services hanya tersedia dalam private chat.")
            return
        if self.admin_only and update.effective_user.id != self.admin_id:
            await self.respond(
                update,
                "📑 Turnitin Services\n\n"
                "Similarity Check dan AI Writing Check sedang disediakan. "
                "Belum menerima tempahan atau bayaran pelanggan.")
            return
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔍 Turnitin Similarity",callback_data="turnitin:plan:similarity")],
            [InlineKeyboardButton("🤖 AI Detection",callback_data="turnitin:category:ai")],
            [InlineKeyboardButton("🎁 Bundle Packages",callback_data="turnitin:category:bundle")],
            [InlineKeyboardButton("📂 My Orders",callback_data="turnitin:orders")],
            [InlineKeyboardButton("🏠 Back to Home",callback_data="home")],
        ])
        await self.respond(update,
            "🍓 BERRY STORE\n━━━━━━━━━━━━━━━━━━\n\n"
            "Selamat datang ke perkhidmatan semakan dokumen Berry Store!\n\n"
            "Pilih kategori servis yang awak perlukan 👇",
            kb)

    async def category(self, update, context, category: str):
        """Second level: show only the approved services in one category."""
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        if not self.private(update) or category not in ("ai", "bundle"):
            return
        if self.admin_only and update.effective_user.id != self.admin_id:
            return await self.menu(update, context)
        try:
            plans = await self.call("catalog")
        except TurnitinError:
            await self.respond(update, "⚠️ Senarai servis belum boleh dimuatkan. Cuba lagi sekejap.",
                InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back",callback_data="turnitin")]]))
            return
        codes = (("ai", "gptzero_basic", "gptzero_standard", "gptzero_premium")
                 if category == "ai" else
                 ("bundle_basic", "bundle_standard", "bundle_premium", "bundle_turnitin_ai"))
        title = "🤖 AI DETECTION" if category == "ai" else "🎁 BUNDLE PACKAGES"
        intro = ("Pilih jenis AI checker yang sesuai dengan assignment awak."
                 if category == "ai" else
                 "Nak semak similarity dan AI sekali jalan? Pilih pakej yang sesuai.")
        entries, buttons = [], []
        for code in codes:
            plan = next((p for p in plans if p.get("code") == code), None)
            if not plan:
                continue
            price = Decimal(str(plan["price_myr"]))
            stock = available_stock(plan)
            active = bool(plan["enabled"] and price > 0 and stock > 0)
            label = SERVICE_LABELS[code]
            entries.append(f"{label}\n💰 RM{price:.2f} · 📦 Stock {stock}"
                           + ("" if active else " · 🔒 Belum tersedia"))
            buttons.append([InlineKeyboardButton(label, callback_data=f"turnitin:plan:{code}")])
        if not entries:
            entries.append("Belum ada servis dalam kategori ini.")
        buttons.append([InlineKeyboardButton("⬅️ Back to Categories",callback_data="turnitin")])
        await self.respond(update,
            f"{title}\n━━━━━━━━━━━━━━━━━━\n\n{intro}\n\n"
            + "\n\n".join(entries)
            + "\n\n📑 Tekan pilihan di bawah untuk baca description sebelum checkout.",
            InlineKeyboardMarkup(buttons))

    async def plan(self, update, context, code: str):
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        if code not in SERVICE_CODES or not self.private(update):
            return
        try:
            plans = await self.call("catalog")
        except TurnitinError:
            await self.respond(update, "⚠️ Servis tidak tersedia.")
            return
        p = next((x for x in plans if x.get("code")==code), None)
        if not p:
            await self.respond(update, "⚠️ Pelan belum dikonfigurasi.")
            return
        price = Decimal(str(p["price_myr"]))
        stock = available_stock(p)
        active = bool(p["enabled"] and price>0 and stock>0 and self.allowed(update.effective_user.id))
        title = SERVICE_LABELS[code]
        upload_steps = "5. Admin semak & hantar 2 PDF report kepada awak.\n" if is_bundle(code) else "5. Admin semak & hantar PDF report kepada awak.\n"
        text = (
            f"📑 {title}\n━━━━━━━━━━━━━━━━━━\n\n"
            f"{p['description']}\n\n"
            f"💰 Harga: RM{price:.2f}\n📦 Stock: {stock}\n"
            f"⏱️ Anggaran: {int(p.get('turnaround_minutes') or 15)} minit\n\n"
            "LANGKAH SETERUSNYA\n"
            "1. Confirm tempahan.\n2. Bayar QR Browse Shop & upload resit.\n"
            "3. Admin sahkan bayaran.\n4. Upload PDF/DOCX.\n"
            f"{upload_steps}\n"
            "📎 Pastikan fail yang dihantar ialah dokumen milik awak atau yang dibenarkan untuk disemak."
        )
        back_action = ("turnitin:category:bundle" if is_bundle(code) else
                       "turnitin:category:ai" if code != "similarity" else "turnitin")
        kb = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Confirm & Pay" if active else "🔒 Belum boleh checkout",
              callback_data=f"turnitin:buy:{code}" if active else "turnitin:locked")],
            [InlineKeyboardButton("⬅️ Back",callback_data=back_action)],
        ])
        await self.respond(update,text,kb)

    async def checkout(self, update, context, code: str):
        if not self.private(update) or code not in SERVICE_CODES:
            return
        if not self.allowed(update.effective_user.id):
            await self.respond(update, "🔒 Turnitin Checkout belum dibuka kepada pelanggan.")
            return
        if self.payment_page is None:
            await self.respond(update,"⚠️ Payment belum tersedia.")
            return
        user = update.effective_user
        key = uuid.uuid5(uuid.NAMESPACE_URL,
            f"turnitin:{self.backend.tenant_id}:{user.id}:{update.update_id}")
        oid = "TT" + uuid.uuid4().hex[:24].upper()
        try:
            out = await self.call("checkout", p_user=user.id, p_plan=code,
                        p_key=str(key), p_order_id=oid, p_username=user.username or "")
        except TurnitinError:
            await self.respond(update,
                "⚠️ Checkout belum berjaya. Jika ada tempahan yang belum dibayar, "
                "selesaikan atau batalkan dulu melalui My Orders. "
                "Kalau masih gagal, cuba sebentar lagi atau hubungi Support.")
            return
        oid = out["order_id"]
        if out.get("state") != "pending_payment":
            await self.respond(update,"ℹ️ Order sudah dalam pemprosesan. Semak My Turnitin Orders.")
            return
        await self.payment_page(context, update.effective_chat.id, user.id,
            {"id":oid,"status":"pending","amount":out["amount"]},oid)

    async def cancel(self, update, context, oid: str):
        if not self.private(update): return
        try:
            out=await self.call("cancel",p_user=update.effective_user.id,p_order_id=oid)
        except TurnitinError:
            await self.respond(update,
                "⚠️ Order tidak boleh dibatalkan setelah resit dihantar atau pembayaran disahkan.")
            return
        await self.respond(update,f"✅ Turnitin order {oid} dibatalkan. Tiada stock ditolak.")

    async def receipt(self, update, context, oid: str, file_id: str, *, as_document=False):
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        if not self.private(update) or not ORDER_RE.fullmatch(str(oid)):
            return
        try:
            status = await self.call("receipt",p_user=update.effective_user.id,
                              p_order_id=oid,p_file_id=file_id)
        except TurnitinError:
            await update.effective_message.reply_text("⚠️ Resit tak dapat disimpan. Cuba semula.")
            return
        context.user_data.pop("pending_receipt",None)
        await update.effective_message.reply_text(
            f"✅ Resit diterima untuk {oid}. Admin akan verify duit masuk dahulu.\n"
            "Jangan upload assignment sebelum bayaran diluluskan.")
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Approve",callback_data=f"approve_{oid}"),
            InlineKeyboardButton("❌ Reject",callback_data=f"reject_{oid}")]])
        caption = f"📑 TURNITIN PAYMENT\nOrder: {oid}\nUser: {update.effective_user.id}\nSemak transaksi bank sebelum Approve."
        try:
            if as_document:
                await context.bot.send_document(chat_id=self.admin_id,
                      document=file_id,caption=caption,reply_markup=kb)
            else:
                await context.bot.send_photo(chat_id=self.admin_id,
                      photo=file_id,caption=caption,reply_markup=kb)
        except Exception as exc:
            LOG.warning("[TURNITIN] admin receipt notify failed: %s",type(exc).__name__)

    async def approve(self, update, context, oid: str, *, rejected=False):
        if update.effective_user.id != self.admin_id or not self.private(update):
            return
        try:
            out = await self.call("reject" if rejected else "approve",
                 p_order_id=oid,p_admin=self.admin_id)
        except TurnitinError:
            await update.effective_message.reply_text(
                "⚠️ Tidak dapat sahkan order. Butang resit masih boleh digunakan selepas semak DB.")
            return
        original = update.callback_query.message.caption or ""
        try:
            await update.callback_query.edit_message_caption(
                caption=original+("\n\n❌ REJECTED" if rejected else "\n\n✅ PAYMENT APPROVED"),
                reply_markup=None)
        except Exception:
            pass
        if not rejected and not out.get("already_approved"):
            try:
                from telegram import InlineKeyboardButton,InlineKeyboardMarkup
                await context.bot.send_message(chat_id=int(out["user_id"]),
                     text=f"✅ Bayaran Turnitin disahkan!\nOrder: {oid}\n"
                          "Sekarang tekan Upload Assignment dan hantar fail PDF/DOCX.",
                     reply_markup=InlineKeyboardMarkup([[
                          InlineKeyboardButton("📎 Upload Assignment",
                            callback_data=f"turnitin:upload:{oid}")]]))
            except Exception as exc:
                LOG.warning("[TURNITIN] approved DM failed: %s",type(exc).__name__)

    async def orders(self,update,context):
        from telegram import InlineKeyboardButton,InlineKeyboardMarkup
        if not self.private(update): return
        try:
            orders = await self.call("customer_orders",p_user=update.effective_user.id)
        except TurnitinError:
            await self.respond(update,"⚠️ Gagal baca order Turnitin.")
            return
        if not orders:
            await self.respond(update,"📂 Tiada order Turnitin lagi.",
                InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back",callback_data="turnitin")]]))
            return
        lines = ["📂 MY TURNITIN ORDERS\n━━━━━━━━━━━━━━━━━━"]
        buttons=[]
        for o in orders[:10]:
            oid=o["order_id"]
            lines.append(f"\n• {oid}\n  {o['plan']} — {o['state']}")
            if o["state"]=="awaiting_upload":
                buttons.append([InlineKeyboardButton("📎 Upload "+oid[-6:],
                    callback_data=f"turnitin:upload:{oid}")])
            else:
                buttons.append([InlineKeyboardButton("🔎 Status "+oid[-6:],
                    callback_data=f"turnitin:status:{oid}")])
        buttons.append([InlineKeyboardButton("⬅️ Back",callback_data="turnitin")])
        await self.respond(update,"\n".join(lines),InlineKeyboardMarkup(buttons))

    async def upload_prompt(self,update,context,oid):
        if not self.private(update): return
        try:
            result=await self.call("customer_status",p_user=update.effective_user.id,
                                  p_order_id=oid)
        except TurnitinError:
            await self.respond(update,"⛔ Order tidak dijumpai atau bukan milik anda.")
            return
        if result["state"]!="awaiting_upload":
            await self.respond(update,f"Status: {result['state']}. Upload belum dibenarkan.")
            return
        context.user_data["turnitin_assignment_order"]=oid
        await self.respond(update,
           f"📎 UPLOAD ASSIGNMENT\nOrder: {oid}\n\n"
           "Hantar satu fail PDF atau DOCX (maksimum 20MB).\n"
           "Bot akan hantar kepada owner untuk semakan manual.\n"
           "Pastikan dokumen tidak mengandungi maklumat sensitif yang tidak perlu.")

    async def show_status(self,update,context,oid):
        if not self.private(update): return
        try:
            j=await self.call("customer_status",p_user=update.effective_user.id,p_order_id=oid)
        except TurnitinError:
            await self.respond(update,"⛔ Tidak dapat semak order ini.")
            return
        pct=elapsed_estimate(j.get("submitted_at")) if j["state"]=="processing" else (
            100 if j["state"]=="delivered" else 0)
        await self.respond(update,
            progress_message(oid, pct) if j["state"] in ("processing", "delivered") else
            f"📑 Order {oid}\nStatus: {j['state']}\n"
            "Fail hanya diproses selepas bayaran dan upload disahkan.")

    async def document(self,update,context,doc):
        if not self.private(update): return False
        uid=update.effective_user.id
        oid=str(context.user_data.get("pending_receipt") or "")
        # A pending Browse Shop/Berry Credits receipt takes precedence. Never
        # treat its PDF as a different paid Turnitin assignment.
        if oid and not ORDER_RE.fullmatch(oid):
            return False
        if ORDER_RE.fullmatch(oid):
            if doc.mime_type not in RECEIPT_MIMES or (doc.file_size or 0)>MAX_RECEIPT:
                await update.effective_message.reply_text("⚠️ Resit PDF/JPG/PNG maksimum 10MB.")
            else:
                await self.receipt(update,context,oid,doc.file_id,as_document=True)
            return True
        if uid==self.admin_id and context.user_data.get("turnitin_admin_delivery"):
            await self.report(update,context,doc)
            return True
        oid=str(context.user_data.get("turnitin_assignment_order") or "")
        if not ORDER_RE.fullmatch(oid):
            try:
                active=await self.call("customer_orders",p_user=uid)
                awaiting=[j["order_id"] for j in active if j["state"]=="awaiting_upload"]
                if len(awaiting)==1: oid=awaiting[0]
            except TurnitinError:
                return False
        if not ORDER_RE.fullmatch(oid):
            return False
        if (doc.mime_type not in ASSIGNMENT_MIMES or
            (doc.file_size or 0)>MAX_ASSIGNMENT or not doc.file_name):
            await update.effective_message.reply_text(
                "⚠️ Hanya PDF/DOCX maksimum 20MB. Sila hantar fail assignment yang sah.")
            return True
        name=re.sub(r"[\r\n\t<>]", "_",doc.file_name.strip())[:180]
        try:
            await self.call("submit",p_user=uid,p_order_id=oid,
                            p_file_id=doc.file_id,p_file_name=name)
        except TurnitinError:
            await update.effective_message.reply_text(
                "⚠️ Fail tidak boleh diterima. Pastikan bayaran telah Approve dan belum upload.")
            return True
        context.user_data.pop("turnitin_assignment_order",None)
        msg=await update.effective_message.reply_text(
            progress_message(oid, 0))
        try:
            await self.call("progress_attach",p_order_id=oid,p_message_id=msg.message_id)
        except TurnitinError:
            LOG.warning("[TURNITIN] progress message attach uncertain")
        try:
            await context.bot.send_document(chat_id=self.admin_id,document=doc.file_id,
               caption=f"📑 TURNITIN ASSIGNMENT\nOrder: {oid}\nType: {name}\n"
               f"Owner command: /Turnitin{oid[2:]}\n"
               "Buat semakan manual dan hantar PDF report menggunakan command tersebut.")
        except Exception as exc:
            LOG.warning("[TURNITIN] assignment admin delivery failed: %s",type(exc).__name__)
            await update.effective_message.reply_text(
                "⚠️ Fail direkod tetapi notifikasi admin gagal. Hubungi support dengan Order ID.")
        return True

    async def admin_command(self,update,context):
        if update.effective_user.id != self.admin_id or not self.private(update):
            return
        raw=update.effective_message.text or ""
        oid="TT"+raw.removeprefix("/Turnitin").removeprefix("/turnitin")
        if not ORDER_RE.fullmatch(oid):
            await update.effective_message.reply_text(
                "Format salah. Copy /Turnitin<24-digit-order-code> daripada notifikasi admin.")
            return
        # Read status without acquiring delivery claim; claim only when PDF is sent.
        try:
            data=await self.call("processing")
        except TurnitinError:
            await update.effective_message.reply_text("⚠️ Database tak tersedia.")
            return
        job = next((j for j in data if j["order_id"] == oid), None)
        if job is None:
            await update.effective_message.reply_text(
                "⛔ Order tidak sedang diproses. Semak Order ID atau status dahulu.")
            return
        context.user_data["turnitin_admin_delivery"]=oid
        context.user_data["turnitin_admin_bundle"] = oid if is_bundle(job.get("plan", "")) else ""
        instruction = (
            "Hantar PDF pertama, kemudian PDF kedua. Kedua-duanya akan sampai kepada customer.\n"
            if is_bundle(job.get("plan", "")) else
            "Hantar satu PDF report. Bot akan deliver kepada pelanggan yang betul.\n"
        )
        await update.effective_message.reply_text(
            f"📄 REPORT DELIVERY\nOrder: {oid}\n" + instruction +
            "⚠️ Hanya hantar apabila report siap dan telah disemak.")

    async def report(self,update,context,doc):
        oid=str(context.user_data.get("turnitin_admin_delivery") or "")
        if not ORDER_RE.fullmatch(oid): return
        if doc.mime_type not in REPORT_MIMES or (doc.file_size or 0)>MAX_ASSIGNMENT:
            await update.effective_message.reply_text("⚠️ Hantar report PDF maksimum 20MB.")
            return
        bundle = context.user_data.get("turnitin_admin_bundle") == oid
        if bundle:
            try:
                stage = await self.call("delivery_stage",p_order_id=oid,
                                        p_admin=self.admin_id,p_file_id=doc.file_id)
            except TurnitinError:
                await update.effective_message.reply_text(
                    "⚠️ PDF bundle tidak dapat disimpan. Semak order sebelum cuba lagi.")
                return
            if stage.get("staged"):
                await update.effective_message.reply_text(
                    f"✅ PDF pertama untuk {oid} disimpan. Sekarang hantar PDF kedua.")
                return
        try:
            target=await self.call("delivery_claim",p_order_id=oid,p_admin=self.admin_id)
        except TurnitinError:
            await update.effective_message.reply_text(
                "⚠️ Order tidak boleh dihantar atau sudah dalam delivery. Jangan send dua kali.")
            return
        context.user_data.pop("turnitin_admin_delivery",None)
        context.user_data.pop("turnitin_admin_bundle",None)
        try:
            first_pdf = target.get("staged_report_file_id") if bundle else None
            if first_pdf:
                await context.bot.send_document(chat_id=int(target["user_id"]),
                    document=first_pdf,caption=f"✅ REPORT 1/2 SIAP!\nOrder: {oid}")
            await context.bot.send_document(chat_id=int(target["user_id"]),
                document=doc.file_id,caption=(f"✅ REPORT 2/2 SIAP!\nOrder: {oid}"
                    if bundle else f"✅ REPORT SIAP!\nOrder: {oid}") +
                    "\nTerima kasih kerana menggunakan Berry Store.")
        except Exception as exc:
            LOG.warning("[TURNITIN] report send uncertain: %s; no retry",
                        type(exc).__name__)
            await update.effective_message.reply_text(
                "⚠️ Telegram delivery tidak pasti. State DELIVERING dikunci; "
                "semak chat penerima sebelum sebarang retry.")
            return
        try:
            marked=await self.call("delivery_complete",p_order_id=oid,p_file_id=doc.file_id)
            if marked is not True:
                raise TurnitinError("Unconfirmed completed delivery")
        except TurnitinError:
            await update.effective_message.reply_text(
                "⚠️ Report sudah dihantar tetapi DB acknowledgment gagal. "
                "Jangan hantar semula — perlu reconcile.")
            return
        mid=target.get("progress_message_id")
        if mid:
            try:
                await context.bot.edit_message_text(
                    chat_id=int(target["user_id"]),message_id=int(mid),
                    text=progress_message(oid, 100))
            except Exception:
                pass
        if self.on_delivered is not None:
            try:
                await self.on_delivered(context, oid, target)
            except Exception as exc:
                LOG.warning("[TURNITIN] optional announcement unavailable: %s",
                            type(exc).__name__)
        await update.effective_message.reply_text(
            f"✅ Report {oid} berjaya dihantar kepada pelanggan. Status DELIVERED.")

    async def tick(self,context):
        try:
            jobs=await self.call("processing")
        except TurnitinError:
            return
        for j in jobs:
            target=elapsed_estimate(j.get("submitted_at"))
            previous=int(j.get("last_display_percent") or 0)
            mid=j.get("progress_message_id")
            if target<=previous or not mid: continue
            try:
                await context.bot.edit_message_text(
                    chat_id=int(j["user_id"]),message_id=int(mid),
                    text=progress_message(j["order_id"], target))
            except Exception as exc:
                LOG.warning("[TURNITIN] progress update failed: %s",type(exc).__name__)
                continue
            try:
                await self.call("progress_mark",p_order_id=j["order_id"],p_percent=target)
            except TurnitinError:
                LOG.warning("[TURNITIN] progress DB ack uncertain")
