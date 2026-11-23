"""Regression tests for the production Cancel Previous Order callback.

On 2026-11-22 the callback cancel_review:ORD... was accidentally rewritten
as cancel_order:review:ORD..., resulting in an order-not-found response.
"""
import ast
import asyncio
from pathlib import Path
import re
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, Mock

BOT = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
PARSED = ast.parse(BOT)
EXAMPLE_ID = "ORD911245363369071"


class FakeButton:
    def __init__(self, text, callback_data):
        self.text = text
        self.callback_data = callback_data


class FakeMarkup:
    def __init__(self, rows):
        self.inline_keyboard = rows


class CancelReviewCallbackRegressionTests(TestCase):
    def test_legacy_cancel_normalizer_does_not_capture_new_callback_names(self):
        router = next(node for node in PARSED.body if isinstance(
            node, ast.AsyncFunctionDef) and node.name == "on_button")
        condition = next(
            node.test for node in ast.walk(router)
            if isinstance(node, ast.If)
            and isinstance(node.test, ast.Call)
            and isinstance(node.test.func, ast.Attribute)
            and node.test.func.attr == "fullmatch"
            and "cancel_" in (ast.get_source_segment(BOT, node.test) or "")
        )
        compiled = compile(ast.fix_missing_locations(ast.Expression(body=condition)),
                           "bot.py", "eval")
        def matches(data):
            return bool(eval(compiled, {"re": re, "data": data}))
        self.assertFalse(matches("cancel_review:" + EXAMPLE_ID))
        self.assertFalse(matches("cancel_review:TT" + "A" * 24))
        self.assertFalse(matches("cancel_review:BT" + "A" * 24))
        self.assertFalse(matches("cancel_order:" + EXAMPLE_ID))
        self.assertFalse(matches("cancel_request:" + EXAMPLE_ID))
        for oid in (EXAMPLE_ID, "TT" + "A" * 24, "BT" + "B" * 24):
            self.assertTrue(matches("cancel_" + oid))

    def test_cancel_review_routes_to_receipt_review_not_pending_cancel(self):
        router = BOT[BOT.index("# ─── Button Router ─"): ]
        self.assertIn('elif data.startswith("cancel_review:"):', router)
        self.assertIn('await show_cancel_review(update, context, data.split(":", 1)[1])', router)
        self.assertIn('elif data.startswith("request_cancel:"):', router)
        self.assertIn('elif data.startswith("cancel_order:"):', router)
        self.assertLess(router.index('elif data.startswith("cancel_review:"):'),
                        router.rindex('elif data.startswith("cancel_order:"):'))

    def test_waiting_approval_order_offers_request_review(self):
        names = ("_customer_order", "show_cancel_review")
        funcs = [node for node in PARSED.body
                 if isinstance(node, ast.AsyncFunctionDef) and node.name in names]
        queried = []
        def get_orders(table, params):
            queried.append((table, params))
            return [{
                "id": EXAMPLE_ID, "user_id": 321, "product_name": "Test Product",
                "amount": "10.00", "status": "waiting_approval",
            }]
        async def run_supabase(_name, cb):
            return cb()
        bot = SimpleNamespace(send_message=AsyncMock())
        ns = {
            "_run_supabase": run_supabase,
            "sb_get": get_orders,
            "log": Mock(),
            "_safe_error": str,
            "InlineKeyboardButton": FakeButton,
            "InlineKeyboardMarkup": FakeMarkup,
            "back_home": Mock(),
        }
        exec(compile(ast.Module(body=funcs, type_ignores=[]), "bot.py", "exec"), ns)
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=321),
            effective_chat=SimpleNamespace(id=321),
        )
        asyncio.run(ns["show_cancel_review"](update, SimpleNamespace(bot=bot), EXAMPLE_ID))
        bot.send_message.assert_awaited_once()
        self.assertEqual(queried[0][0], "orders")
        self.assertIn("id=eq." + EXAMPLE_ID, queried[0][1])
        self.assertIn("user_id=eq.321", queried[0][1])
        args = bot.send_message.await_args
        self.assertIn("Pembatalan perlu disemak oleh admin", args.args[1])
        actions = [b.callback_data for row in args.kwargs["reply_markup"].inline_keyboard
                   for b in row]
        self.assertEqual(actions, [
            "request_cancel:" + EXAMPLE_ID,
            "order_view:" + EXAMPLE_ID,
        ])

    def test_live_product_revalidation_uses_actual_schema(self):
        create = next(node for node in PARSED.body if isinstance(
            node, ast.AsyncFunctionDef) and node.name == "create_order")
        code = ast.get_source_segment(BOT, create)
        self.assertIn("select=id,name,stock,price,auto_delivery,is_active,status&id=", code)
        self.assertNotIn("select=id,name,stock,price,auto_delivery,delivery_mode", code)


if __name__ == "__main__":
    import unittest
    unittest.main()
