"""Anonymous support: durable state, private relay and no owner identity leaks."""
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from berry_anonymous_support import AnonymousSupport, SupportStore, reply_target


class SupportStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_session_open_close_and_tenant_scope(self):
        row = {}
        def get(table, params):
            self.assertEqual(table, "berry_support_sessions")
            self.assertIn("user_id=eq.12345", params)
            return [row] if row else []
        def upsert(table, data):
            self.assertEqual(data["tenant_id"], "tenant-1")
            row.update(data)
            return [dict(row)]
        def patch(table, params, data):
            self.assertIn("status=eq.open", params)
            if row.get("status") != "open":
                return []
            row.update(data)
            return [dict(row)]
        store = SupportStore(get, upsert, patch, "tenant-1")
        self.assertFalse(await store.is_open(12345))
        await store.open(12345)
        self.assertTrue(await store.is_open(12345))
        self.assertTrue(await store.close(12345))
        self.assertFalse(await store.close(12345))
        self.assertFalse(await store.is_open(12345))

    async def test_missing_tenant_fails_closed(self):
        store = SupportStore(lambda *x: [], lambda *x: [], lambda *x: [], "")
        with self.assertRaises(RuntimeError):
            await store.is_open(12345)


class SupportRelayTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.store = SimpleNamespace(
            is_open=AsyncMock(return_value=True),
            open=AsyncMock(),
            close=AsyncMock(return_value=True))
        self.flow = AnonymousSupport(self.store, 42)
        self.bot = SimpleNamespace(
            id=987, send_message=AsyncMock(), copy_message=AsyncMock())
        self.ctx = SimpleNamespace(bot=self.bot)

    def update(self, uid=12345, text="Hi", reply=None, caption=None):
        msg = SimpleNamespace(
            text=text, caption=caption, message_id=77,
            reply_to_message=reply, reply_text=AsyncMock())
        user = SimpleNamespace(id=uid, username="buyer")
        return SimpleNamespace(
            effective_message=msg, message=msg, effective_user=user,
            effective_chat=SimpleNamespace(type="private", id=uid))

    async def test_customer_text_to_admin_contains_customer_id(self):
        u = self.update()
        self.assertTrue(await self.flow.relay(u, self.ctx))
        args = self.bot.send_message.await_args.kwargs
        self.assertEqual(args["chat_id"], 42)
        self.assertIn("🆔 Telegram ID: 12345", args["text"])
        u.message.reply_text.assert_awaited_once()

    async def test_admin_reply_to_bot_message_keeps_admin_anonymous(self):
        original = SimpleNamespace(
            from_user=SimpleNamespace(id=987),
            text="📩 BERRY SUPPORT\n🆔 Telegram ID: 12345\n👤 Customer: @buyer\n\n💬 Hi",
            caption=None)
        u = self.update(uid=42, text="Boleh saya bantu?", reply=original)
        self.assertTrue(await self.flow.relay(u, self.ctx))
        self.assertEqual(self.bot.send_message.await_args.kwargs,
                         {"chat_id": 12345, "text": "Boleh saya bantu?"})

    async def test_spoofed_reply_from_non_bot_is_ignored(self):
        original = SimpleNamespace(
            from_user=SimpleNamespace(id=555),
            text="📩 BERRY SUPPORT\n🆔 Telegram ID: 12345", caption=None)
        u = self.update(uid=42, text="test", reply=original)
        self.assertFalse(await self.flow.relay(u, self.ctx))
        self.bot.send_message.assert_not_awaited()
        self.assertIsNone(reply_target(u.message, 987))

    async def test_closed_session_blocks_admin_reply(self):
        self.store.is_open.return_value = False
        u = self.update(uid=42, text="Hi")
        await self.flow._deliver(self.ctx, 12345, u.message)
        self.bot.send_message.assert_not_awaited()

    async def test_customer_media_copied_without_forward(self):
        u = self.update(text=None, caption="screenshot")
        self.assertTrue(await self.flow.relay(u, self.ctx))
        args = self.bot.copy_message.await_args.kwargs
        self.assertEqual(args["chat_id"], 42)
        self.assertIn("🆔 Telegram ID: 12345", args["caption"])

    async def test_admin_media_reply_copied_to_customer(self):
        original = SimpleNamespace(
            from_user=SimpleNamespace(id=987), text=None,
            caption="📩 BERRY SUPPORT\n🆔 Telegram ID: 12345\nFile")
        u = self.update(uid=42, text=None, reply=original)
        self.assertTrue(await self.flow.relay(u, self.ctx))
        self.assertEqual(self.bot.copy_message.await_args.kwargs["chat_id"], 12345)

    async def test_admin_close_notifies_customer(self):
        u = self.update(uid=42)
        ctx = SimpleNamespace(bot=self.bot, args=["12345"])
        with patch("berry_anonymous_support.support_keyboard", return_value=object()):
            await self.flow.admin_close(u, ctx)
        self.store.close.assert_awaited_once_with(12345)
        self.assertEqual(self.bot.send_message.await_args.kwargs["chat_id"], 12345)

    async def test_non_admin_cannot_close(self):
        u = self.update(uid=99999)
        await self.flow.admin_close(u, SimpleNamespace(bot=self.bot, args=["12345"]))
        self.store.close.assert_not_awaited()

    async def test_non_admin_cannot_reply_command(self):
        u = self.update(uid=99999)
        await self.flow.admin_reply(u, SimpleNamespace(bot=self.bot, args=["12345", "Hi"]))
        self.bot.send_message.assert_not_awaited()


class IntegrationContractTests(unittest.TestCase):
    def test_bot_routes_and_privacy(self):
        bot = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
        self.assertNotIn("@" + "berryrc", bot)
        self.assertIn('CommandHandler("reply", cmd_support_reply)', bot)
        self.assertIn('CommandHandler("close", cmd_support_close)', bot)
        self.assertIn('callback_data="support"', bot)
        self.assertIn("text=AnonymousSupport.MENU", bot)
        self.assertIn('InlineKeyboardButton("💬 Start Chat", callback_data="support:start")', bot)
        self.assertIn('await _send_post_order_support(context, int(delivery["user_id"]))', bot)
        self.assertIn('await _send_post_order_support(context, int(result["user_id"]))', bot)
        self.assertIn('await _send_post_order_support(context, int(buyer_id))', bot)
        self.assertIn("MessageHandler(filters.ChatType.PRIVATE & ~filters.COMMAND, _support_message_router)", bot)
        self.assertIn("group=-2", bot)
        self.assertIn("group=-1", bot)
        self.assertNotIn("forward_message", bot)


if __name__ == "__main__":
    unittest.main()
