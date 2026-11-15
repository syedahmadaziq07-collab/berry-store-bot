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


def isolated_sync(name, namespace):
    fn = next(n for n in TREE.body if isinstance(n, ast.FunctionDef) and n.name == name)
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

    def test_database_reads_reuse_one_bounded_pool_with_separate_auth_headers(self):
        response = SimpleNamespace(raise_for_status=Mock(), json=Mock(return_value=[{"id": 1}]))
        client = SimpleNamespace(get=Mock(return_value=response))
        namespace = {
            "_sb_read_client": client,
            "SUPABASE_URL": "https://example.supabase.co",
            "_ensure_tenant_filter": lambda table, query: query + "&tenant_id=eq.test",
            "_sb_headers": lambda: {"Authorization": "Bearer publishable"},
            "_sb_admin_headers": lambda: {"Authorization": "Bearer service-key"},
            "_orders_api_headers": lambda table, headers: headers,
            "log": SimpleNamespace(debug=lambda *_: None),
        }
        get = isolated_sync("sb_get", namespace)
        admin_get = isolated_sync("sb_admin_get", namespace)
        self.assertEqual(get("products", "select=id"), [{"id": 1}])
        self.assertEqual(admin_get("products", "select=id"), [{"id": 1}])
        self.assertEqual(client.get.call_count, 2)
        public_kwargs = client.get.call_args_list[0].kwargs
        admin_kwargs = client.get.call_args_list[1].kwargs
        self.assertEqual(public_kwargs["headers"]["Authorization"], "Bearer publishable")
        self.assertEqual(admin_kwargs["headers"]["Authorization"], "Bearer service-key")
        self.assertEqual(public_kwargs["timeout"], 15)
        self.assertIn("tenant_id=eq.test", client.get.call_args_list[0].args[0])
        self.assertIn("max_connections=20", BOT)
        self.assertIn("max_keepalive_connections=10", BOT)


if __name__ == "__main__":
    unittest.main()
