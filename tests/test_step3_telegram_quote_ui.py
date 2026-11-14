"""STEP 3 Telegram quote menu regression: no network, wallet or paid generation."""
import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
import unittest


class _Button:
    def __init__(self, text, *, callback_data):
        self.text = text
        self.callback_data = callback_data


class _Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


class QuoteMenuUITests(unittest.TestCase):
    @staticmethod
    def _source():
        return (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8-sig")

    def _invoke(self, flow):
        tree = ast.parse(self._source())
        fn = next(node for node in tree.body
                  if isinstance(node, ast.AsyncFunctionDef)
                  and node.name == "_ai_quote_menu")
        captured = {}

        async def send(query, text, reply_markup=None):
            captured.update(text=text, markup=reply_markup)

        namespace = {
            "Update": object,
            "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
            "InlineKeyboardButton": _Button,
            "InlineKeyboardMarkup": _Markup,
            "_quote_flow": lambda context: flow,
            "_safe_edit_or_send": send,
        }
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "bot.py", "exec"),
             namespace)
        asyncio.run(namespace["_ai_quote_menu"](
            SimpleNamespace(callback_query=object()), SimpleNamespace()))
        return captured

    def test_enabled_quote_menu_has_usable_ratio_buttons(self):
        result = self._invoke(SimpleNamespace(
            product_menu_text=lambda: "MiniMax menu"))
        self.assertEqual(result["text"], "MiniMax menu")
        callbacks = [button.callback_data
                     for row in result["markup"].inline_keyboard
                     for button in row]
        self.assertIn("ai_quote_ratio:16:9", callbacks)
        self.assertIn("ai_quote_ratio:9:16", callbacks)
        self.assertIn("ai_studio:video", callbacks)

    def test_disabled_quote_menu_fails_closed(self):
        result = self._invoke(None)
        self.assertIn("belum tersedia", result["text"])
        self.assertIsNone(result["markup"])

    def test_admin_video_menu_exposes_quote_entry_only_behind_gate(self):
        source = self._source()
        self.assertIn('if _get_env("BERRY_QUOTE_FLOW_ENABLED") == "true":', source)
        self.assertIn('callback_data="ai_quote_menu"', source)
        self.assertIn('callback_data="ai_quote_ratio:16:9"', source)
        self.assertIn('callback_data="ai_quote_ratio:9:16"', source)


if __name__ == "__main__":
    unittest.main()
