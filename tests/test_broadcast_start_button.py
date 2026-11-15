"""Broadcast command should preserve announcement paragraphs and show START."""

import ast
import asyncio
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock


ROOT = Path(__file__).resolve().parents[1]


class _Button:
    def __init__(self, text, callback_data):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, inline_keyboard):
        self.inline_keyboard = inline_keyboard


def _load_broadcast(users):
    source = ast.parse((ROOT / "bot.py").read_text(encoding="utf-8"))
    functions = [
        node for node in source.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name in {"broadcast_start_keyboard", "cmd_broadcast"}
    ]
    namespace = {
        "ADMIN_ID": 99,
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "InlineKeyboardMarkup": _Markup,
        "InlineKeyboardButton": _Button,
        "_block_if_expired": AsyncMock(return_value=False),
        "_run_supabase": AsyncMock(return_value=users),
        "sb_get": lambda *_args: users,
        "_safe_error": str,
        "log": SimpleNamespace(info=lambda *_args: None, warning=lambda *_args, **_kwargs: None),
        "re": re,
    }
    module = ast.Module(body=functions, type_ignores=[])
    exec(compile(module, str(ROOT / "bot.py"), "exec"), namespace)
    return namespace


def _request(message, user_id=99):
    reply_text = AsyncMock()
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_message=SimpleNamespace(text=message),
        message=SimpleNamespace(reply_text=reply_text),
    )
    bot = SimpleNamespace(send_message=AsyncMock())
    context = SimpleNamespace(bot=bot, args=["unused"])
    return update, context, reply_text


class BroadcastStartButtonTests(unittest.TestCase):
    def test_each_recipient_gets_full_paragraphs_and_menu_start(self):
        module = _load_broadcast([{"id": 101}, {"id": 102}])
        content = "📚 Turnitin dah ada!\n\nBoleh semak assignment sekarang."
        update, context, reply_text = _request("/broadcast " + content)

        asyncio.run(module["cmd_broadcast"](update, context))

        self.assertEqual(context.bot.send_message.await_count, 2)
        self.assertEqual(
            [c.kwargs["chat_id"] for c in context.bot.send_message.await_args_list],
            [101, 102],
        )
        for call in context.bot.send_message.await_args_list:
            self.assertEqual(call.kwargs["text"], content)
            keyboard = call.kwargs["reply_markup"].inline_keyboard
            self.assertEqual(len(keyboard), 1)
            self.assertEqual(keyboard[0][0].text, "🚀 START")
            self.assertEqual(keyboard[0][0].callback_data, "home")
        self.assertIn("2 pengguna", reply_text.await_args.args[0])

    def test_command_with_bot_mention_preserves_shop_stock_list(self):
        module = _load_broadcast([{"id": 201}])
        content = "🛍️ Stok terkini:\n✅ Canva\n✅ ChatGPT\n\nWarranty 7 hari."
        update, context, _reply = _request("/broadcast@berryshopps_bot\n" + content)

        asyncio.run(module["cmd_broadcast"](update, context))

        self.assertEqual(context.bot.send_message.await_args.kwargs["text"], content)

    def test_non_admin_cannot_send_announcement(self):
        module = _load_broadcast([{"id": 101}])
        update, context, reply_text = _request("/broadcast Tolong beli!", user_id=123)

        asyncio.run(module["cmd_broadcast"](update, context))

        context.bot.send_message.assert_not_awaited()
        self.assertIn("Bukan admin", reply_text.await_args.args[0])

    def test_empty_command_does_not_send(self):
        module = _load_broadcast([{"id": 101}])
        update, context, reply_text = _request("/broadcast\n")

        asyncio.run(module["cmd_broadcast"](update, context))

        context.bot.send_message.assert_not_awaited()
        self.assertIn("Sila masukkan mesej", reply_text.await_args.args[0])


if __name__ == "__main__":
    unittest.main()
