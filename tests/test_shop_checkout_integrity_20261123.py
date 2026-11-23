"""Regression tests for no-write Berry Store shop checkout integrity."""
import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, Mock

BOT = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
TREE = ast.parse(BOT)


def function(name, namespace):
    fn = next(n for n in TREE.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
              and n.name == name)
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "bot.py", "exec"), namespace)
    return namespace[name]


class Markup:
    def __init__(self, rows):
        self.inline_keyboard = rows


class Button:
    def __init__(self, text, callback_data):
        self.text, self.callback_data = text, callback_data


class CustomerRegistrationTests(TestCase):
    def test_missing_customer_is_created_once_and_verified(self):
        rows = []
        inserted = []
        def select(table, params):
            self.assertEqual(table, "users")
            self.assertIn("id=eq.321", params)
            return rows.copy()
        def insert(table, customer):
            inserted.append(customer)
            rows.append({"id": customer["id"]})
            return rows
        ns = {"SUPABASE_SERVICE_KEY": "server-only-key", "sb_admin_get": select,
              "sb_admin_post": insert, "_httpx": SimpleNamespace(HTTPStatusError=Exception)}
        register = function("_register_checkout_customer", ns)
        user = SimpleNamespace(id=321, username="buyer", first_name="Lucas")
        self.assertTrue(register(user))
        self.assertTrue(register(user))
        self.assertEqual(len(inserted), 1)
        self.assertEqual(inserted[0]["username"], "buyer")

    def test_registration_without_service_role_fails_closed(self):
        register = function("_register_checkout_customer", {"SUPABASE_SERVICE_KEY": ""})
        with self.assertRaises(RuntimeError):
            register(SimpleNamespace(id=321))

    def test_foreign_tenant_duplicate_user_is_not_reassigned(self):
        class Duplicate(Exception):
            def __init__(self):
                self.response = SimpleNamespace(status_code=409)
        writes = []
        def conflict(_table, row):
            writes.append(row)
            raise Duplicate()
        ns = {"SUPABASE_SERVICE_KEY": "server-only-key",
              "sb_admin_get": lambda *_: [],
              "sb_admin_post": conflict,
              "_httpx": SimpleNamespace(HTTPStatusError=Duplicate)}
        register = function("_register_checkout_customer", ns)
        self.assertFalse(register(SimpleNamespace(id=321, username="other")))
        self.assertEqual(len(writes), 1)

    def test_unregistered_customer_cannot_reach_any_checkout(self):
        ns = {"_run_supabase": AsyncMock(return_value=False),
              "_register_checkout_customer": Mock(),
              "_safe_error": str, "log": Mock(), "back_shop": lambda: Markup([])}
        ensure = function("_ensure_checkout_customer", ns)
        update = SimpleNamespace(effective_user=SimpleNamespace(id=321),
                                 effective_chat=SimpleNamespace(id=321))
        ctx = SimpleNamespace(bot=SimpleNamespace(send_message=AsyncMock()))
        self.assertFalse(asyncio.run(ensure(update, ctx)))
        self.assertIn("/start", ctx.bot.send_message.await_args.args[1])
        self.assertIn("Tiada order", ctx.bot.send_message.await_args.args[1])


class GenericCheckoutTests(TestCase):
    def harness(self, *, product_id=6, variant_id=None, variant_product_id=None,
                live_rows=True, active=True, stock=10):
        events, inserted = [], []
        def read(table, _query):
            if table == "products":
                return ([{"id": product_id, "name": "Demo Product", "price": 20,
                          "stock": stock, "is_active": active, "status": "active"}]
                        if live_rows else [])
            if table == "product_variants":
                return [{"id": variant_id, "product_id": variant_product_id,
                         "variant_name": "Demo Variant", "stock": stock,
                         "price": 11.5, "description": "Warranty 7 hari."}]
            raise AssertionError("Unexpected table " + table)
        def insert(_table, doc):
            inserted.append(doc.copy())
            events.append("insert")
            return [{"id": doc["id"]}]
        async def execute(_name, callback, **_kwargs):
            return callback()
        async def setting(_key, value=None):
            return value
        async def send_message(*_args, **_kwargs):
            events.append("message")
            return SimpleNamespace(message_id=1000)
        ns = {
            "time": SimpleNamespace(monotonic=lambda: 1),
            "random": SimpleNamespace(randint=lambda a, b: 99999),
            "Update": object, "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
            "_run_supabase": execute, "sb_get": read, "sb_post": insert,
            "_safe_error": str, "log": Mock(),
            "delete_flow_messages": AsyncMock(return_value=[]),
            "_offer_existing_unpaid_order": AsyncMock(return_value=False),
            "_valid_netflix_profile": lambda _: True,
            "_needs_netflix_profile": lambda *_: False,
            "_setting": setting,
            "back_shop": lambda: Markup([]),
            "track_flow_message": Mock(),
            "InlineKeyboardMarkup": Markup, "InlineKeyboardButton": Button,
        }
        fn = function("create_order", ns)
        data = {"shop_products": [{"id": product_id, "name": "Demo Product",
                                  "stock": stock, "price": 20}]}
        if variant_id is not None:
            data["selected_variant_id"] = variant_id
        ctx = SimpleNamespace(user_data=data,
                              bot=SimpleNamespace(send_message=AsyncMock(side_effect=send_message)))
        update = SimpleNamespace(effective_user=SimpleNamespace(id=321, username="demo"),
                                 effective_chat=SimpleNamespace(id=321), callback_query=None)
        return fn, ctx, update, inserted, events

    def test_plain_product_never_inherits_old_variant_or_description(self):
        fn, ctx, update, inserted, events = self.harness()
        ctx.user_data["selected_variant_id"] = 99
        ctx.user_data["selected_variant_desc"] = "Previous Netflix plan"
        asyncio.run(fn(update, ctx, 6, 1))
        self.assertEqual(len(inserted), 1)
        self.assertIsNone(inserted[0]["variant_id"])
        self.assertNotIn("selected_variant_id", ctx.user_data)
        self.assertNotIn("Previous Netflix plan", ctx.bot.send_message.await_args.args[1])

    def test_variant_must_belong_to_selected_product(self):
        fn, ctx, update, inserted, events = self.harness(
            product_id=2, variant_id=14, variant_product_id=9)
        asyncio.run(fn(update, ctx, 2, 1, variant_label="Demo Variant", variant_price=10))
        self.assertEqual(inserted, [])
        self.assertTrue(events)
        self.assertIn("Variant", ctx.bot.send_message.await_args.args[1])

    def test_variant_reuses_authoritative_price(self):
        fn, ctx, update, inserted, _ = self.harness(
            product_id=2, variant_id=14, variant_product_id=2)
        asyncio.run(fn(update, ctx, 2, 1, variant_label="Demo Variant", variant_price=10))
        self.assertEqual(inserted[0]["variant_id"], 14)
        self.assertEqual(inserted[0]["amount"], 11.5)

    def test_cached_product_is_rejected_if_missing_live(self):
        fn, ctx, update, inserted, _ = self.harness(live_rows=False)
        asyncio.run(fn(update, ctx, 6, 1))
        self.assertFalse(inserted)
        self.assertIn("Tak dapat semak produk", ctx.bot.send_message.await_args.args[1])

    def test_inactive_product_cannot_checkout(self):
        fn, ctx, update, inserted, _ = self.harness(active=False)
        asyncio.run(fn(update, ctx, 6, 1))
        self.assertFalse(inserted)
        self.assertIn("tidak lagi tersedia", ctx.bot.send_message.await_args.args[1])

    def test_no_unguarded_variant_id_before_insertion(self):
        self.assertIn("if variant_price is not None else None", BOT)
        self.assertIn("if not await _ensure_checkout_customer(update, context):", BOT)
        self.assertIn("Order variant/product mismatch; manual review required", BOT)
        self.assertIn("if not changed:", BOT)

    def test_product_details_use_real_production_columns(self):
        segment = ast.get_source_segment(BOT, next(
            n for n in TREE.body if isinstance(n, ast.AsyncFunctionDef)
            and n.name == "show_product"))
        self.assertIn("auto_delivery,is_active,status", segment)
        self.assertNotIn("auto_delivery,delivery_mode,is_active", segment)
