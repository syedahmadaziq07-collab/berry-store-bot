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

    def test_minimax_is_only_under_text_to_video_not_input_menu(self):
        source = self._source()
        input_menu = source.split('if section == "video":', 1)[1].split(
            'elif section == "topup":', 1)[0]
        text_model_menu = source.split("async def show_ai_video_text(", 1)[1].split(
            "async def show_ai_video_duration(", 1)[0]
        self.assertNotIn('callback_data="ai_quote_menu"', input_menu)
        self.assertNotIn("MiniMax 10s Quotation", input_menu)
        self.assertIn('callback_data="ai_video_text"', input_menu)
        self.assertIn('callback_data="ai_quote_menu"', text_model_menu)
        self.assertIn('BERRY_QUOTE_FLOW_ENABLED', text_model_menu)
        self.assertIn('callback_data="ai_quote_ratio:16:9"', source)
        self.assertIn('callback_data="ai_quote_ratio:9:16"', source)


    def test_input_type_goes_to_model_choice_first(self):
        source = self._source()
        section = source.split('if section == "video":', 1)[1].split(
            'elif section == "topup":', 1)[0]
        self.assertIn('callback_data="ai_video_models:15"', section)
        self.assertIn('callback_data="ai_video_text"', section)
        self.assertNotIn('callback_data="ai_video_duration"', section)
        self.assertNotIn('Teks → Video (akan datang)', section)

    def test_text_to_video_shows_reviewed_minimax_model_and_remains_gated(self):
        source = self._source()
        section = source.split("async def show_ai_video_text(", 1)[1].split(
            "async def show_ai_video_duration(", 1)[0]
        self.assertIn('get_product("minimax_turbo_video")', section)
        self.assertIn('callback_data="ai_quote_menu"', section)
        self.assertIn('BERRY_QUOTE_FLOW_ENABLED', section)
        self.assertNotIn("provider.submit", section)
        self.assertNotIn("wallet_debit", section)

    def test_image_to_video_model_preview_is_not_paid(self):
        source = self._source()
        section = source.split("async def show_ai_video_models(", 1)[1].split(
            "async def show_ai_video_ratio(", 1)[0]
        self.assertIn("Gemini Omni Flash", section)
        self.assertIn("Tiada caj", section)
        self.assertIn('callback_data="ai_studio:video"', section)


if __name__ == "__main__":
    unittest.main()
