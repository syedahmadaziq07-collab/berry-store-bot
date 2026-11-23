"""Pending QR checkouts are resumable across Browse Shop, Turnitin and Top Up."""

import ast
import asyncio
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, Mock, patch


ROOT = Path(__file__).resolve().parents[1]
BOT = (ROOT / "bot.py").read_text(encoding="utf-8")


class FakeButton:
    def __init__(self, label, callback_data):
        self.text = label
        self.callback_data = callback_data


class FakeMarkup:
    def __init__(self, rows):
        self.inline_keyboard = rows


def extract_pending_guard(fake_orders):
    module = ast.parse(BOT)
    fn = next(node for node in module.body
              if isinstance(node, ast.AsyncFunctionDef)
              and node.name == "_offer_existing_unpaid_order")
    async def run_supabase(_name, callback):
        return callback()

    sent = SimpleNamespace(message_id=123)
    bot = SimpleNamespace(send_message=AsyncMock(return_value=sent))
    track = Mock()
    namespace = {
        "_run_supabase": run_supabase,
        "_ensure_checkout_customer": AsyncMock(return_value=True),
        "sb_get": lambda _table, _query: fake_orders,
        "_safe_error": str,
        "log": Mock(),
        "InlineKeyboardButton": FakeButton,
        "InlineKeyboardMarkup": FakeMarkup,
        "track_flow_message": track,
    }
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "bot.py", "exec"), namespace)
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=321),
        effective_chat=SimpleNamespace(id=321),
    )
    context = SimpleNamespace(bot=bot)
    return namespace["_offer_existing_unpaid_order"], update, context, track


class UnifiedPendingActionsTests(TestCase):
    def test_pending_turnitin_or_shop_or_topup_offers_same_two_buttons(self):
        for oid in ("TT" + "A" * 24, "ORD12345", "BT" + "B" * 24):
            with self.subTest(order_id=oid):
                guard, update, ctx, track = extract_pending_guard([{
                    "id": oid,
                    "product_name": "Previous order",
                    "amount": "3.10",
                    "status": "pending",
                }])
                self.assertTrue(asyncio.run(guard(update, ctx)))
                kw = ctx.bot.send_message.await_args.kwargs
                self.assertIn("Previous order", ctx.bot.send_message.await_args.args[1])
                buttons = [btn for row in kw["reply_markup"].inline_keyboard for btn in row]
                self.assertEqual([btn.callback_data for btn in buttons], [
                    f"pay:{oid}", f"cancel_order:{oid}", "myorders",
                ])
                self.assertEqual(len(buttons), 3)
                track.assert_called_once()

    def test_no_unpaid_order_does_not_block_new_checkout(self):
        guard, update, ctx, _ = extract_pending_guard([])
        self.assertFalse(asyncio.run(guard(update, ctx)))
        ctx.bot.send_message.assert_not_awaited()

    def test_receipt_under_review_exposes_resume_and_cancel_review_never_payment(self):
        for oid in ("ORD12345", "TT" + "C" * 24, "BT" + "B" * 24):
            for status in ("waiting", "waiting_approval"):
                with self.subTest(order_id=oid, status=status):
                    guard, update, ctx, _ = extract_pending_guard([{
                        "id": oid, "product_name": "Previous", "amount": "3.10",
                        "status": status,
                    }])
                    self.assertTrue(asyncio.run(guard(update, ctx)))
                    kw = ctx.bot.send_message.await_args.kwargs
                    actions = [btn.callback_data
                               for row in kw["reply_markup"].inline_keyboard
                               for btn in row]
                    self.assertEqual(actions, [
                        f"order_view:{oid}", f"cancel_review:{oid}", "myorders",
                    ])
                    self.assertNotIn(f"pay:{oid}", actions)
                    self.assertNotIn(f"cancel_order:{oid}", actions)
                    self.assertIn("jangan buat bayaran kedua",
                                  ctx.bot.send_message.await_args.args[1])

    def test_database_lookup_failure_fails_closed(self):
        guard, update, ctx, _ = extract_pending_guard([])
        async def unavailable(*args):
            raise RuntimeError("db offline")
        guard.__globals__["_run_supabase"] = unavailable
        self.assertTrue(asyncio.run(guard(update, ctx)))
        self.assertIn("Tak dapat semak", ctx.bot.send_message.await_args.args[1])

    def test_all_three_checkout_paths_share_pending_order_guard(self):
        for fn_name in ("create_order", "checkout_ai_topup"):
            node = next(n for n in ast.parse(BOT).body
                        if isinstance(n, ast.AsyncFunctionDef) and n.name == fn_name)
            code = ast.get_source_segment(BOT, node)
            self.assertIn("_offer_existing_unpaid_order(update, context)", code)
        self.assertIn("pending_order_guard=_offer_existing_unpaid_order", BOT)

    def test_continue_pay_can_reopen_qr_after_rapid_tap_window(self):
        node = next(n for n in ast.parse(BOT).body
                    if isinstance(n, ast.FunctionDef) and n.name == "_payment_reopen_allowed")
        ns = {"time": SimpleNamespace(monotonic=lambda: 1.0)}
        exec(compile(ast.Module(body=[node], type_ignores=[]), "bot.py", "exec"), ns)
        allow = ns["_payment_reopen_allowed"]
        storage = {}
        self.assertTrue(allow(storage, "TT1", now=1.0))
        self.assertFalse(allow(storage, "TT1", now=2.1))
        self.assertTrue(allow(storage, "TT1", now=4.0))
        self.assertTrue(allow(storage, "BT1", now=4.1))
        self.assertFalse(allow(storage, "BT1", now=4.2))
        self.assertIn("_payment_reopen_allowed(context.user_data, order_id)", BOT)
        self.assertNotIn("context.user_data.setdefault('payment_opened', set())", BOT)
        self.assertIn('if order.get("status") != "pending":', BOT)

    def test_cancel_confirmation_is_not_deleted_after_success(self):
        route = BOT[BOT.index('elif data.startswith("cancel_order:"):',
                              BOT.index("# ─── Button Router")):
                    BOT.index('elif data.startswith("approve_"):',
                              BOT.index("# ─── Button Router"))]
        cleanup = route[route.index("await cancel_order(update, context, order_id)"):]
        self.assertIn('"payment_qr"', cleanup)
        self.assertIn('"receipt_instruction"', cleanup)
        self.assertNotIn('"error_message"', cleanup)

    def test_cancel_after_receipt_requires_admin_review(self):
        parsed = ast.parse(BOT)
        names = {node.name for node in parsed.body
                 if isinstance(node, ast.AsyncFunctionDef)}
        for name in ("show_existing_order", "show_cancel_review",
                     "request_order_cancellation", "admin_review_shop_cancel",
                     "admin_confirm_shop_cancel"):
            self.assertIn(name, names)
        router = BOT[BOT.index("# ─── Button Router"):]
        for callback in ("order_view:", "cancel_review:", "request_cancel:",
                         "admin_cancel_review:", "admin_cancel_confirm:"):
            self.assertIn(f'data.startswith("{callback}")', router)
        # No direct cancellation from a customer once their receipt exists.
        request = next(node for node in parsed.body
                       if isinstance(node, ast.AsyncFunctionDef)
                       and node.name == "request_order_cancellation")
        request_code = ast.get_source_segment(BOT, request)
        self.assertIn("ADMIN_ID", request_code)
        self.assertNotIn('{"status": "cancelled"}', request_code)

    def test_approved_or_cancelled_order_cannot_be_resurrected(self):
        # All admin transitions must be guarded by current status, and check
        # the returned rows before stock or notifications are changed.
        self.assertIn('receipt_file_id=not.is.null', BOT)
        self.assertIn('raise ValueError("Order was already updated or cancelled")', BOT)
        self.assertIn('raise ValueError("Order not in cancellable payment-review state")', BOT)
        self.assertIn('raise ValueError("Order not awaiting review or already closed")', BOT)
        self.assertIn('cancelled = bool(updated)', BOT)

    def test_turnitin_checkout_uses_guard_before_creating_order(self):
        with patch.dict(sys.modules, {"httpx": ModuleType("httpx")}):
            from berry_turnitin_flow import TurnitinFlow
        backend = SimpleNamespace(tenant_id="92c1e5ca-8498-438f-b777-3dc1c3195c1b")
        pending = AsyncMock(return_value=True)
        payment = AsyncMock()
        update = SimpleNamespace(
            effective_user=SimpleNamespace(id=12, username="testing"),
            effective_chat=SimpleNamespace(type="private"),
        )
        flow = TurnitinFlow(backend, 12, checkout_enabled=True,
                            payment_page=payment, pending_order_guard=pending)
        asyncio.run(flow.checkout(update, SimpleNamespace(), "similarity"))
        pending.assert_awaited_once()
        payment.assert_not_awaited()

