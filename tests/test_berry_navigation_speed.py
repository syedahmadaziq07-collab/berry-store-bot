"""Offline regression checks for low-latency Telegram navigation."""

import ast
import asyncio
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock


BOT = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
TREE = ast.parse(BOT)


def isolated(name, namespace):
    fn = next(n for n in TREE.body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "<isolated>", "exec"), namespace)
    return namespace[name]


class NavigationSpeedTests(unittest.IsolatedAsyncioTestCase):
    async def test_live_product_and_variant_queries_start_together(self):
        started = set()
        both_started = asyncio.Event()
        products = [{"id": 1, "name": "CapCut", "stock": 4, "is_active": True, "status": "active"}]
        variants = [{"id": 2, "product_id": 1, "stock": 0}]

        async def run_supabase(label, operation):
            started.add(label)
            if len(started) == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=1)
            return products if label == "products.list" else variants

        cache = {"products": [], "variants": [], "timestamp": 0}
        namespace = {
            "asyncio": asyncio, "time": time, "CACHE_TTL": 60,
            "_products_cache_data": cache, "_run_supabase": run_supabase,
            "TENANT_ID": "test-tenant", "log": SimpleNamespace(info=lambda *_: None),
        }
        load = isolated("_get_cached_products_and_variants", namespace)
        actual_products, actual_variants = await load(force=True)
        self.assertEqual(started, {"products.list", "product_variants.all"})
        self.assertEqual(actual_products, products)
        self.assertEqual(actual_variants, variants)  # Sold-out variants remain visible.
        self.assertIs(cache["products"], actual_products)

    async def test_flow_message_deletes_happen_concurrently(self):
        started = set()
        both_started = asyncio.Event()

        async def delete(_bot, _chat, message_id):
            started.add(message_id)
            if len(started) == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=1)
            return True

        namespace = {
            "asyncio": asyncio, "safe_delete_message": delete,
            "_flow_key": lambda: "flow_messages",
            "log": SimpleNamespace(info=lambda *_: None),
        }
        cleanup = isolated("delete_flow_messages", namespace)
        context = SimpleNamespace(user_data={"flow_messages": {"shop_list": 11, "variant_select": 12}})
        deleted = await cleanup(context, object(), chat_id=55, user_id=100)
        self.assertEqual(deleted, {11, 12})
        self.assertEqual(context.user_data["flow_messages"], {})

    async def test_tenant_check_is_nonblocking_and_per_update(self):
        check = Mock(return_value=True)
        namespace = {"asyncio": asyncio, "is_tenant_active": check, "ADMIN_ID": 42}
        guard = isolated("_block_if_expired", namespace)
        context = SimpleNamespace(user_data={})
        update = SimpleNamespace(update_id=100, effective_user=SimpleNamespace(id=101))
        self.assertFalse(await guard(update, context))
        self.assertFalse(await guard(update, context))
        self.assertEqual(check.call_count, 1)
        update.update_id = 101
        self.assertFalse(await guard(update, context))
        self.assertEqual(check.call_count, 2)

    async def test_expired_tenant_is_never_cached_as_active(self):
        check = Mock(return_value=False)
        edit = AsyncMock()
        namespace = {"asyncio": asyncio, "is_tenant_active": check, "ADMIN_ID": 42}
        guard = isolated("_block_if_expired", namespace)
        context = SimpleNamespace(user_data={})
        update = SimpleNamespace(
            update_id=100, effective_user=SimpleNamespace(id=101),
            callback_query=SimpleNamespace(edit_message_text=edit), message=None,
        )
        self.assertTrue(await guard(update, context))
        self.assertTrue(await guard(update, context))
        self.assertEqual(check.call_count, 2)
        self.assertEqual(edit.await_count, 2)

    def test_shop_overlaps_live_stock_reads_with_message_cleanup(self):
        shop = BOT[BOT.index("async def show_shop("):BOT.index("# ─── Variant Helpers", BOT.index("async def show_shop("))]
        self.assertLess(shop.index("catalog_task = asyncio.create_task("),
                        shop.index("await delete_flow_messages("))
        self.assertLess(shop.index("credentials_task = asyncio.create_task("),
                        shop.index("await delete_flow_messages("))
        self.assertIn("_get_cached_products_and_variants(force=True)", shop)
        self.assertIn("return_exceptions=True", shop)


if __name__ == "__main__":
    unittest.main()
