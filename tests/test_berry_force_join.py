"""Mandatory /start channel membership checks without Telegram or database calls."""
import ast
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

BOT = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
TREE = ast.parse(BOT)


class StopProcessing(Exception):
    pass


def isolated(name, namespace):
    fn = next(n for n in TREE.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "<isolated>", "exec"), namespace)
    return namespace[name]


class ForceJoinTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.ns = {
            "ADMIN_ID": 42,
            "REQUIRED_CHANNEL": "@berrystorrel",
            "REQUIRED_CHANNEL_URL": "https://t.me/berrystorrel",
            "log": SimpleNamespace(error=lambda *a: None, warning=lambda *a: None),
            "_safe_error": str,
            "re": re,
            "Update": object,
            "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
            "ApplicationHandlerStop": StopProcessing,
            "InlineKeyboardButton": lambda label, **kw: SimpleNamespace(text=label, **kw),
            "InlineKeyboardMarkup": lambda rows: rows,
        }
        self.check = isolated("_check_membership", self.ns)
        self.send = isolated("_send_join_message", self.ns)
        self.guard = isolated("_force_join_message_guard", self.ns)

    async def test_member_allowed_left_and_kicked_blocked(self):
        bot = SimpleNamespace(get_chat_member=AsyncMock())
        for status, expected in (
            ("member", True), ("administrator", True), ("creator", True),
            ("left", False), ("kicked", False),
        ):
            bot.get_chat_member.return_value = SimpleNamespace(status=status)
            self.assertEqual(await self.check(bot, 100), expected, status)
        bot.get_chat_member.return_value = SimpleNamespace(status="restricted", is_member=True)
        self.assertTrue(await self.check(bot, 100))
        bot.get_chat_member.return_value.is_member = False
        self.assertFalse(await self.check(bot, 100))

    async def test_unavailable_channel_fails_closed_but_admin_can_manage(self):
        bot = SimpleNamespace(get_chat_member=AsyncMock(side_effect=RuntimeError("not admin")))
        self.assertFalse(await self.check(bot, 100))
        self.assertTrue(await self.check(bot, 42))
        self.assertEqual(bot.get_chat_member.await_count, 1)

    async def test_join_message_has_channel_and_verify_button(self):
        message = SimpleNamespace(reply_text=AsyncMock())
        await self.send(SimpleNamespace(message=message, callback_query=None))
        args, kwargs = message.reply_text.await_args
        self.assertIn("@berrystorrel", args[0])
        self.assertEqual(kwargs["reply_markup"][0][0].url, "https://t.me/berrystorrel")
        self.assertEqual(kwargs["reply_markup"][1][0].callback_data, "verify_join")

    async def test_nonmember_upload_stopped_before_any_handler(self):
        self.ns["_check_membership"] = AsyncMock(return_value=False)
        self.ns["_send_join_message"] = AsyncMock()
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=100),
            effective_message=SimpleNamespace(text=None),
        )
        with self.assertRaises(StopProcessing):
            await self.guard(update, SimpleNamespace(bot=object()))
        self.ns["_send_join_message"].assert_awaited_once_with(update)

    async def test_joined_user_and_owner_allowed(self):
        self.ns["_check_membership"] = AsyncMock(return_value=True)
        self.ns["_send_join_message"] = AsyncMock()
        for user_id in (100, 42):
            update = SimpleNamespace(
                effective_user=SimpleNamespace(id=user_id),
                effective_message=SimpleNamespace(text="1"),
            )
            await self.guard(update, SimpleNamespace(bot=object()))
        self.ns["_send_join_message"].assert_not_awaited()
        self.assertEqual(self.ns["_check_membership"].await_count, 1)

    def test_start_gates_before_welcome_and_all_buttons_gated(self):
        start = BOT[BOT.index("async def cmd_start("):BOT.index("# ─── Shop ─", BOT.index("async def cmd_start("))]
        self.assertLess(
            start.index("if not await _check_membership(context.bot, user.id):"),
            start.index('reply_text("Bot hidup ✅")'),
        )
        self.assertNotIn('enable_force_join', start)
        buttons = BOT[BOT.index("async def on_button("):BOT.index("    # ── Rate limit check", BOT.index("async def on_button("))]
        self.assertIn('if data == "verify_join":', buttons)
        self.assertIn("if not await _check_membership(context.bot, update.effective_user.id):", buttons)
        self.assertIn('context.user_data.pop("force_join_pending_start", "")', buttons)

    def test_private_message_guard_is_registered_early(self):
        app = BOT[BOT.index("def build_app()"):BOT.index('app.add_handler(CommandHandler("ping"')]
        self.assertIn("MessageHandler(filters.ChatType.PRIVATE, _force_join_message_guard)", app)
        self.assertIn("group=-2", app)


if __name__ == "__main__":
    unittest.main()
