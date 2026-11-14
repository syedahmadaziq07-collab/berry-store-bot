"""Berry Store private support relay. Customer never sees the admin's Telegram account."""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone

LOG = logging.getLogger(__name__)
HEADER = re.compile(r"\A📩 BERRY SUPPORT\n🆔 Telegram ID: ([1-9][0-9]{3,19})(?:\n|$)")
USER_ID = re.compile(r"\A[1-9][0-9]{3,19}\Z")


def reply_target(message, bot_id: int) -> int | None:
    """Trust only replies to bot-authored support notifications."""
    original = getattr(message, "reply_to_message", None)
    sender = getattr(original, "from_user", None)
    if not original or not sender or sender.id != bot_id:
        return None
    match = HEADER.match(original.text or original.caption or "")
    return int(match.group(1)) if match else None


def support_keyboard(active: bool = False):
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    action = ("✅ End Chat", "support:end") if active else ("💬 Start Chat", "support:start")
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(action[0], callback_data=action[1])],
        [InlineKeyboardButton("🏠 Home", callback_data="home")],
    ])


class SupportStore:
    """Tenant-scoped session state via server-side service-role REST helpers."""
    TABLE = "berry_support_sessions"

    def __init__(self, get, upsert, patch, tenant_id: str):
        self.get, self.upsert, self.patch, self.tenant_id = get, upsert, patch, tenant_id

    def _ready(self):
        if not self.tenant_id:
            raise RuntimeError("Support tenant not configured")

    async def is_open(self, user_id: int) -> bool:
        self._ready()
        rows = await asyncio.to_thread(
            self.get, self.TABLE, f"select=status&user_id=eq.{int(user_id)}&limit=1")
        return bool(rows and rows[0].get("status") == "open")

    async def open(self, user_id: int):
        self._ready()
        rows = await asyncio.to_thread(self.upsert, self.TABLE, {
            "tenant_id": self.tenant_id, "user_id": int(user_id),
            "status": "open", "closed_at": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        if not rows or rows[0].get("status") != "open":
            raise RuntimeError("Support session was not opened")

    async def close(self, user_id: int) -> bool:
        self._ready()
        now = datetime.now(timezone.utc).isoformat()
        rows = await asyncio.to_thread(
            self.patch, self.TABLE,
            f"user_id=eq.{int(user_id)}&status=eq.open",
            {"status": "closed", "closed_at": now, "updated_at": now})
        return bool(rows)


class AnonymousSupport:
    MENU = (
        "💬 BERRY SUPPORT\n\n"
        "Hey! 👋 Ada apa-apa yang kami boleh bantu?\n\n"
        "Terus je taip mesej dekat sini. Team Berry Store akan reply secepat mungkin! 🍓\n\n"
        "🔒 Chat ini dikendalikan melalui Berry Store Bot."
    )
    ACTIVE = (
        "💬 BERRY SUPPORT — CHAT AKTIF\n\n"
        "Okay, boleh terus taip atau hantar gambar/fail dekat sini. 🍓\n"
        "Mesej awak akan sampai kepada team support kami.\n\n"
        "Bila dah selesai, tekan End Chat."
    )
    CLOSED = (
        "✅ Sesi support dah tamat.\n\n"
        "Terima kasih kerana menghubungi Berry Store! 🍓\n"
        "Kalau ada apa-apa lagi, tekan Start Chat untuk chat semula."
    )

    def __init__(self, store: SupportStore, admin_id: int):
        self.store, self.admin_id = store, int(admin_id)

    async def _display(self, update, text, active=False):
        kb = support_keyboard(active)
        q = getattr(update, "callback_query", None)
        if q:
            try:
                await q.edit_message_text(text, reply_markup=kb)
                return
            except Exception:
                await q.message.reply_text(text, reply_markup=kb)
        else:
            await update.effective_message.reply_text(text, reply_markup=kb)

    async def menu(self, update, context):
        await self._display(update, self.MENU)

    async def start(self, update, context):
        user_id = update.effective_user.id
        if user_id == self.admin_id:
            await self._display(update, "🛡 Admin: guna /reply ID mesej atau /close ID.")
            return
        try:
            await self.store.open(user_id)
        except Exception as exc:
            LOG.warning("[SUPPORT] open failed: %s", type(exc).__name__)
            await self._display(update, "⚠️ Support belum tersedia. Cuba lagi sebentar.")
            return
        await self._display(update, self.ACTIVE, active=True)

    async def end(self, update, context):
        user_id = update.effective_user.id
        if user_id == self.admin_id:
            await self._display(update, "🛡 Admin: guna /close TELEGRAM_ID.")
            return
        try:
            await self.store.close(user_id)
        except Exception as exc:
            LOG.warning("[SUPPORT] close failed: %s", type(exc).__name__)
            await self._display(update, "⚠️ Tak dapat tamatkan chat. Cuba lagi.")
            return
        await self._display(update, self.CLOSED)

    async def leave(self, user_id: int):
        """When customer navigates to another menu, stop routing uploads to Support."""
        if user_id != self.admin_id:
            await self.store.close(user_id)

    async def _deliver(self, context, user_id: int, message, text=None):
        if user_id == self.admin_id or not await self.store.is_open(user_id):
            await message.reply_text("⚠️ Chat customer ini dah ditutup. Minta customer buka Support semula.")
            return
        try:
            if text is not None or message.text:
                await context.bot.send_message(
                    chat_id=user_id, text=text if text is not None else message.text)
            else:
                # copy_message never shows a "forwarded from @owner" header.
                await context.bot.copy_message(
                    chat_id=user_id, from_chat_id=self.admin_id,
                    message_id=message.message_id)
        except Exception as exc:
            LOG.warning("[SUPPORT] admin reply failed: %s", type(exc).__name__)
            await message.reply_text("⚠️ Mesej gagal dihantar. Customer mungkin block bot.")
            return
        await message.reply_text(f"✅ Reply dihantar kepada Telegram ID {user_id}.")

    async def admin_reply(self, update, context):
        if (not update.effective_user or update.effective_user.id != self.admin_id
                or update.effective_chat.type != "private"):
            return
        args = context.args or []
        if len(args) < 2 or not USER_ID.fullmatch(args[0]):
            await update.message.reply_text("Format: /reply TELEGRAM_ID mesej")
            return
        await self._deliver(
            context, int(args[0]), update.message, text=" ".join(args[1:]).strip())

    async def admin_close(self, update, context):
        if (not update.effective_user or update.effective_user.id != self.admin_id
                or update.effective_chat.type != "private"):
            return
        args = context.args or []
        if len(args) != 1 or not USER_ID.fullmatch(args[0]):
            await update.message.reply_text("Format: /close TELEGRAM_ID")
            return
        target = int(args[0])
        if target == self.admin_id:
            await update.message.reply_text("⚠️ Tak boleh tutup chat admin sendiri.")
            return
        try:
            changed = await self.store.close(target)
        except Exception as exc:
            LOG.warning("[SUPPORT] admin close failed: %s", type(exc).__name__)
            await update.message.reply_text("⚠️ Gagal tutup chat. Cuba lagi.")
            return
        if not changed:
            await update.message.reply_text("ℹ️ Tiada chat aktif untuk Telegram ID ini.")
            return
        try:
            await context.bot.send_message(
                chat_id=target, text=self.CLOSED, reply_markup=support_keyboard())
        except Exception as exc:
            LOG.warning("[SUPPORT] close notice failed: %s", type(exc).__name__)
        await update.message.reply_text(f"✅ Chat {target} dah ditutup.")

    async def relay(self, update, context) -> bool:
        message = getattr(update, "effective_message", None)
        user = getattr(update, "effective_user", None)
        chat = getattr(update, "effective_chat", None)
        if not message or not user or not chat or chat.type != "private":
            return False
        if message.text and message.text.startswith("/"):
            return False
        if user.id == self.admin_id:
            target = reply_target(message, context.bot.id)
            if target is None:
                return False
            await self._deliver(context, target, message)
            return True
        try:
            active = await self.store.is_open(user.id)
        except Exception as exc:
            LOG.warning("[SUPPORT] session lookup failed: %s", type(exc).__name__)
            return False
        if not active or message.text == "🏠 Home":
            return False
        username = f"@{user.username}" if user.username else "Tiada username"
        header = f"📩 BERRY SUPPORT\n🆔 Telegram ID: {user.id}\n👤 Customer: {username}"
        try:
            if message.text:
                await context.bot.send_message(
                    chat_id=self.admin_id,
                    text=f"{header}\n\n💬 {message.text}"[:4096])
            else:
                caption = f"{header}\n\n{(message.caption or '')[:700]}"[:1024]
                try:
                    await context.bot.copy_message(
                        chat_id=self.admin_id, from_chat_id=user.id,
                        message_id=message.message_id, caption=caption)
                except Exception:
                    # Some Telegram media cannot carry captions: send header first.
                    await context.bot.send_message(chat_id=self.admin_id, text=header)
                    await context.bot.copy_message(
                        chat_id=self.admin_id, from_chat_id=user.id,
                        message_id=message.message_id)
        except Exception as exc:
            LOG.warning("[SUPPORT] relay failed: %s", type(exc).__name__)
            await message.reply_text("⚠️ Mesej belum sampai. Cuba hantar sekali lagi.")
            return True
        await message.reply_text("🍓 Mesej dah sampai! Team support akan reply di sini.")
        return True
