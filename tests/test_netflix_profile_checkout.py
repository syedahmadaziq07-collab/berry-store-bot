"""Netflix menu item 10: profile setup before private/semi-private QR checkout."""
import ast
import asyncio
from pathlib import Path
import re
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, Mock


BOT = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
TREE = ast.parse(BOT)


def extract(*names, ns=None):
    chosen = [node for node in TREE.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
    assert {node.name for node in chosen} == set(names)
    namespace = {"re": re, **(ns or {})}
    exec(compile(ast.Module(body=chosen, type_ignores=[]), "bot.py", "exec"), namespace)
    return namespace


class FakeButton:
    def __init__(self, text, callback_data):
        self.text = text
        self.callback_data = callback_data


class FakeMarkup:
    def __init__(self, rows):
        self.inline_keyboard = rows


class NetflixProfileCheckoutTests(TestCase):
    def test_scope_is_product_id_nine_private_semi_only(self):
        n = extract("_needs_netflix_profile", ns={"NETFLIX_PRODUCT_ID": 9})["_needs_netflix_profile"]
        self.assertTrue(n(9, "Private 1 Month"))
        self.assertTrue(n(9, "Semi Private 1 Month"))
        self.assertFalse(n(9, "Sharing 1 Month"))
        self.assertFalse(n(10, "Private 1 Month"))
        self.assertFalse(n(7, "Semi Private 1 Month"))
        self.assertFalse(n(9, "Not Private"))
        self.assertFalse(n(9, None))

    def test_name_and_pin_validation_keeps_leading_zero(self):
        valid = extract("_valid_netflix_profile")["_valid_netflix_profile"]
        self.assertTrue(valid({"name": "Lucas", "pin": "0000"}))
        self.assertTrue(valid({"name": "Lucas", "pin": "0098"}))
        for pin in ("000", "00000", "12ab", "12 3", "١٢٣٤", 1234, ""):
            with self.subTest(pin=pin):
                self.assertFalse(valid({"name": "Lucas", "pin": pin}))
        for name in ("", "A" * 33, "Line\nBreak"):
            self.assertFalse(valid({"name": name, "pin": "0000"}))

    def test_exact_customer_prompt_examples(self):
        ns = extract("_netflix_name_prompt", "_netflix_pin_prompt")
        self.assertIn("Contoh: Lucas", ns["_netflix_name_prompt"]())
        self.assertIn("Contoh: 0000", ns["_netflix_pin_prompt"]("Lucas"))

    def test_numeric_pin_is_consumed_before_product_number_routing(self):
        marker = "if await _handle_netflix_profile_text(update, context, text):"
        self.assertIn(marker, BOT)
        self.assertLess(BOT.index(marker), BOT.index("if text.isdigit():"))
        self.assertIn('log.info("[MESSAGE] text=[NETFLIX_PROFILE_INPUT_REDACTED]")', BOT)

    def test_profile_text_flow_name_pin_and_back_can_retry(self):
        seen = []
        async def create(*args, **kw):
            seen.append((args, kw))
        ns = extract(
            "_needs_netflix_profile", "_valid_netflix_profile",
            "_netflix_pin_prompt", "_handle_netflix_profile_text",
            ns={
                "NETFLIX_PRODUCT_ID": 9,
                "InlineKeyboardButton": FakeButton,
                "InlineKeyboardMarkup": FakeMarkup,
                "create_order": create,
            },
        )
        message = SimpleNamespace(reply_text=AsyncMock())
        update = SimpleNamespace(message=message)
        flow = {
            "step": "name", "product_id": 9, "variant_id": 10,
            "variant_label": "Private 1 Month", "variant_price": 17.90,
        }
        context = SimpleNamespace(user_data={"netflix_profile_flow": flow})
        consume = ns["_handle_netflix_profile_text"]
        self.assertTrue(asyncio.run(consume(update, context, "Lucas")))
        self.assertEqual(context.user_data["netflix_profile_flow"]["step"], "pin")
        self.assertTrue(asyncio.run(consume(update, context, "abc")))
        self.assertEqual(context.user_data["netflix_profile_flow"]["step"], "pin")
        self.assertFalse(seen)
        self.assertTrue(asyncio.run(consume(update, context, "0000")))
        self.assertNotIn("netflix_profile_flow", context.user_data)
        self.assertEqual(context.user_data["selected_variant_id"], 10)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][0][2:4], (9, 1))
        self.assertEqual(seen[0][1]["variant_price"], 17.9)
        self.assertEqual(seen[0][1]["netflix_profile"], {"name": "Lucas", "pin": "0000"})
        self.assertTrue(any("PIN mesti" in x.args[0] for x in message.reply_text.await_args_list))

    def _checkout_harness(self, variant_label="Private 1 Month",
                          net_profile=None, stock=15, live_price="17.90"):
        events = []
        inserted = []
        def sb_get(table, query):
            if table == "products":
                return [{"id": 9, "name": "NETFLIX ORIGINAL 4K PREMIUM",
                         "stock": 15, "price": "7", "auto_delivery": False}]
            if table == "product_variants":
                return [{"id": 10, "variant_name": variant_label, "stock": stock,
                         "price": live_price, "description": "Private package",
                         "product_id": 9}]
            raise AssertionError(f"unexpected table {table}")
        def sb_post(_table, doc):
            inserted.append(doc)
            events.append("order_insert")
            return [{"id": doc["id"]}]
        async def run_supabase(_name, callback, **kw):
            return callback()
        async def send_message(chat_id, text, **kwargs):
            events.append("owner" if chat_id == 999 else "customer")
            return SimpleNamespace(message_id=len(events))
        async def send_qr(*args, **kwargs):
            events.append("qr")
        async def setting(_key, default=None):
            return default
        ns = {
            "time": SimpleNamespace(monotonic=lambda: 1.0),
            "random": SimpleNamespace(randint=lambda a,b: 95759),
            "NETFLIX_PRODUCT_ID": 9,
            "_run_supabase": run_supabase,
            "sb_get": sb_get, "sb_post": sb_post, "sb_patch": Mock(return_value=[{"id":"ok"}]),
            "log": Mock(),
            "_safe_error": str,
            "_offer_existing_unpaid_order": AsyncMock(return_value=False),
            "send_payment_page": AsyncMock(side_effect=send_qr),
            "delete_flow_messages": AsyncMock(return_value=[]),
            "_setting": setting,
            "back_shop": lambda: FakeMarkup([]),
            "track_flow_message": Mock(),
            "InlineKeyboardButton": FakeButton,
            "InlineKeyboardMarkup": FakeMarkup,
            "ADMIN_ID": 999,
        }
        ns.update(extract("_needs_netflix_profile", "_valid_netflix_profile",
                          "create_order", ns=ns))
        ctx = SimpleNamespace(
            user_data={
                "shop_products": [{"id": 9, "name": "NETFLIX ORIGINAL 4K PREMIUM",
                                   "stock": 15, "price": "7"}],
                "selected_variant_id": 10,
            },
            bot=SimpleNamespace(send_message=AsyncMock(side_effect=send_message)),
        )
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=321, username="customer"),
            effective_chat=SimpleNamespace(id=321),
            callback_query=None,
        )
        return ns, ctx, update, events, inserted

    def test_admin_receives_one_combined_message_then_qr_at_live_variant_price(self):
        ns, ctx, update, events, inserted = self._checkout_harness(live_price="19.90")
        asyncio.run(ns["create_order"](
            update, ctx, 9, 1,
            variant_label="Private 1 Month", variant_price=17.90,
            netflix_profile={"name": "Lucas", "pin": "0000"},
        ))
        self.assertEqual(events, ["order_insert", "owner", "customer", "qr"])
        self.assertEqual(len(inserted), 1)
        self.assertEqual(inserted[0]["amount"], 19.90)  # DB revalidation wins
        owner = ctx.bot.send_message.await_args_list[0]
        self.assertEqual(owner.kwargs["chat_id"], 999)
        notification = owner.kwargs["text"]
        self.assertIn("Nama profile: Lucas", notification)
        self.assertIn("PIN 4 digit: 0000", notification)
        self.assertIn("Order: ORD95759321", notification)
        self.assertIn("Private 1 Month", notification)
        self.assertNotIn("0000", ctx.bot.send_message.await_args_list[1].args[1])
        qr = ns["send_payment_page"].await_args
        self.assertEqual(qr.args[3]["amount"], 19.90)
        self.assertEqual(qr.args[4], "ORD95759321")

    def test_no_direct_checkout_without_profile_for_netflix_private(self):
        ns, ctx, update, events, inserted = self._checkout_harness()
        asyncio.run(ns["create_order"](update, ctx, 9, 1,
                                      variant_label="Private 1 Month", variant_price=17.90))
        self.assertFalse(inserted)
        self.assertNotIn("qr", events)
        self.assertFalse(ns["send_payment_page"].await_count)

    def test_out_of_stock_never_notifies_admin_or_opens_qr(self):
        ns, ctx, update, events, inserted = self._checkout_harness(stock=0)
        asyncio.run(ns["create_order"](
            update, ctx, 9, 1,
            variant_label="Private 1 Month", variant_price=17.90,
            netflix_profile={"name": "Lucas", "pin": "0000"},
        ))
        self.assertFalse(inserted)
        self.assertNotIn("owner", events)
        self.assertNotIn("qr", events)

    def test_other_products_and_netflix_sharing_keep_existing_flow(self):
        needs = extract("_needs_netflix_profile", ns={"NETFLIX_PRODUCT_ID": 9})["_needs_netflix_profile"]
        self.assertFalse(needs(9, "Sharing 1 Month"))
        self.assertFalse(needs(1, "Private 1 Month"))
        src = ast.get_source_segment(BOT, next(
            n for n in TREE.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "on_button"))
        self.assertIn("if _needs_netflix_profile(pid, v_label):", src)
        self.assertIn("await create_order(update, context, pid, 1,", src)
        self.assertLess(src.index("if _needs_netflix_profile(pid, v_label):"),
                        src.index("await create_order(update, context, pid, 1,"))


if __name__ == "__main__":
    import unittest
    unittest.main()
