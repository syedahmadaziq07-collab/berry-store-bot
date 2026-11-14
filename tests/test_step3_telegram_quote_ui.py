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

    def _invoke(self, flow, *, preview=False):
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
            "_quote_preview_owner": lambda update: preview,
            "_safe_edit_or_send": send,
        }
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "bot.py", "exec"),
             namespace)
        asyncio.run(namespace["_ai_quote_menu"](
            SimpleNamespace(callback_query=object()), SimpleNamespace()))
        return captured

    def test_reply_text_includes_persisted_quote_id(self):
        from telegram_quote_flow import TelegramQuoteFlow
        flow = TelegramQuoteFlow(None, None,
                                 fx_provider=lambda: None, operational=None)
        quote_id = "11111111-1111-4111-8111-111111111111"
        view = {
            "quote_id": quote_id,
            "product_name": "MiniMax Turbo Video",
            "duration_seconds": 10,
            "resolution": "480P",
            "aspect_ratio": "16:9",
            "price_myr": "RM3.00",
            "credits": 3750,
            "expires_at": "2026-11-14T03:00:00+00:00",
        }
        response = flow.quote_reply_text(view)
        self.assertIn(quote_id, response)
        self.assertIn("RM3.00", response)
        self.assertIn("3,750", response)
        self.assertIn("tiada debit", response)

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

    def test_owner_preview_reaches_ratio_without_financial_config(self):
        result = self._invoke(None, preview=True)
        self.assertIn("ADMIN PREVIEW", result["text"])
        self.assertIn("belum", result["text"])
        callbacks = [button.callback_data
                     for row in result["markup"].inline_keyboard
                     for button in row]
        self.assertIn("ai_quote_ratio:16:9", callbacks)
        self.assertIn("ai_quote_ratio:9:16", callbacks)

    def test_admin_preview_prompt_never_invokes_pricing_or_provider(self):
        source = self._source()
        tree = ast.parse(source)
        fn = next(node for node in tree.body
                  if isinstance(node, ast.AsyncFunctionDef)
                  and node.name == "_ai_quote_prompt_text")
        replies = []

        async def reply(text):
            replies.append(text)

        ns = {
            "Update": object,
            "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
            "_quote_preview_owner": lambda update: True,
            # Deliberately no _quote_flow, store, pricing or fal imports.
        }
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "bot.py", "exec"), ns)
        context = SimpleNamespace(
            user_data={"ai_quote_flow": {
                "stage": "preview_prompt", "aspect_ratio": "9:16"}})
        update = SimpleNamespace(message=SimpleNamespace(
            text="A safe prompt", reply_text=reply))
        consumed = asyncio.run(ns["_ai_quote_prompt_text"](update, context))
        self.assertTrue(consumed)
        self.assertNotIn("ai_quote_flow", context.user_data)
        self.assertIn("ADMIN PREVIEW PASS", replies[0])
        self.assertIn("9:16", replies[0])
        self.assertIn("Tiada quotation", replies[0])

    def test_fx_probe_is_owner_only_and_read_only(self):
        source = self._source()
        self.assertIn('CommandHandler("quotefx", owner_quote_fx)', source)
        block = source.split("async def owner_quote_fx(", 1)[1].split(
            'app.add_handler(CommandHandler("quotefx"', 1)[0]
        self.assertIn('chat.type != "private"', block)
        self.assertIn("user.id != admin_id", block)
        self.assertIn("asyncio.to_thread(provider.get_rate)", block)
        self.assertNotIn("wallet_debit", block)
        self.assertNotIn("provider.submit", block)

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
