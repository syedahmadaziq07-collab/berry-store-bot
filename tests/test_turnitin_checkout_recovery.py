"""Regression checks for paid Turnitin jobs no longer blocking new checkouts."""

import asyncio
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, patch

with patch.dict(sys.modules, {"httpx": ModuleType("httpx")}):
    from berry_turnitin_flow import TurnitinError, TurnitinFlow


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (ROOT / "docs/sql/berry_turnitin_concurrent_paid_orders.sql").read_text(
    encoding="utf-8"
)


class TurnitinCheckoutRecoveryTests(TestCase):
    def test_database_allows_parallel_paid_reports_but_only_one_unpaid_order(self):
        self.assertIn("CREATE OR REPLACE FUNCTION public.berry_turnitin_checkout", MIGRATION)
        self.assertIn("existing unpaid order must be resolved first", MIGRATION)
        self.assertNotIn("previous report not finished", MIGRATION)
        self.assertNotIn("state IN ('awaiting_upload','processing','delivering')", MIGRATION)
        self.assertIn("request_key=p_key", MIGRATION)
        self.assertIn("FOR UPDATE", MIGRATION)
        self.assertIn("bundle component out of stock", MIGRATION)
        self.assertIn("'pending_payment'", MIGRATION)
        self.assertNotIn("UPDATE public.orders", MIGRATION)
        self.assertNotIn("DELETE FROM", MIGRATION)

    def test_repeated_plan_click_does_not_trigger_generic_error(self):
        class AlreadyShowingError(Exception):
            pass

        update = SimpleNamespace(
            callback_query=SimpleNamespace(edit_message_text=AsyncMock(
                side_effect=AlreadyShowingError(
                    "BadRequest: Message is not modified: same content and reply markup"
                )
            )),
            effective_message=SimpleNamespace(reply_text=AsyncMock()),
        )
        asyncio.run(TurnitinFlow.respond(update, "Plan already shown"))
        update.effective_message.reply_text.assert_not_awaited()

    def test_unexpected_edit_error_is_not_hidden(self):
        update = SimpleNamespace(callback_query=SimpleNamespace(
            edit_message_text=AsyncMock(side_effect=RuntimeError("network unavailable"))
        ))
        with self.assertRaisesRegex(RuntimeError, "network unavailable"):
            asyncio.run(TurnitinFlow.respond(update, "Test"))

    def test_new_checkout_shows_payment_page_even_with_old_processing_order(self):
        calls = []

        class Backend:
            tenant_id = "92c1e5ca-8498-438f-b777-3dc1c3195c1b"

            def rpc(self, name, **kwargs):
                calls.append((name, kwargs))
                return {
                    "created": True, "order_id": kwargs["p_order_id"],
                    "state": "pending_payment", "amount": "3.10"
                }

        payment_page = AsyncMock()
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=123, username="customer"),
            effective_chat=SimpleNamespace(id=123, type="private"),
            update_id=456,
            callback_query=SimpleNamespace(edit_message_text=AsyncMock()),
        )
        flow = TurnitinFlow(Backend(), admin_id=987, checkout_enabled=True,
                            admin_only=False, payment_page=payment_page)
        asyncio.run(flow.checkout(update, SimpleNamespace(), "similarity"))
        payment_page.assert_awaited_once()
        self.assertEqual(calls[0][0], "checkout")
        self.assertEqual(calls[0][1]["p_user"], 123)
        self.assertEqual(calls[0][1]["p_plan"], "similarity")
        self.assertRegex(calls[0][1]["p_order_id"], r"^TT[0-9A-F]{24}$")

    def test_failed_checkout_explains_unpaid_order_without_claiming_stock_is_zero(self):
        class Backend:
            tenant_id = "92c1e5ca-8498-438f-b777-3dc1c3195c1b"

            def rpc(self, name, **kwargs):
                raise TurnitinError("backend rejected checkout")

        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=123, username="customer"),
            effective_chat=SimpleNamespace(id=123, type="private"),
            update_id=457,
            callback_query=SimpleNamespace(edit_message_text=AsyncMock()),
        )
        flow = TurnitinFlow(Backend(), admin_id=987, checkout_enabled=True,
                            admin_only=False, payment_page=AsyncMock())
        asyncio.run(flow.checkout(update, SimpleNamespace(), "similarity"))
        message = update.callback_query.edit_message_text.await_args.args[0]
        self.assertIn("My Orders", message)
        self.assertNotIn("stock habis", message)

