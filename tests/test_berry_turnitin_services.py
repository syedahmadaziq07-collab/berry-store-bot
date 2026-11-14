"""Turnitin manual service design, privacy and 30-second status contract."""
import asyncio
import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import AsyncMock

# Some offline CI jobs intentionally omit httpx. Inject a stub only while
# importing pure timer/flow logic; no network clients are instantiated here.
import sys
from types import ModuleType
from unittest.mock import patch
with patch.dict(sys.modules, {"httpx": ModuleType("httpx")}):
    from berry_turnitin_flow import TurnitinFlow, elapsed_estimate, progress_message

ROOT = Path(__file__).resolve().parents[1]
BOT = (ROOT / "bot.py").read_text(encoding="utf-8")
FLOW = (ROOT / "berry_turnitin_flow.py").read_text(encoding="utf-8")
SQL = (ROOT / "docs/sql/berry_turnitin_manual_services.sql").read_text(encoding="utf-8")
ADMIN = (ROOT / "admin_app.py").read_text(encoding="utf-8")


class TurnitinServiceTests(TestCase):
    def test_sources_are_valid_python(self):
        for src in (BOT, FLOW, ADMIN):
            ast.parse(src)

    def test_loading_one_percent_each_thirty_seconds(self):
        now = datetime(2026, 11, 14, 8, 0, tzinfo=timezone.utc)
        started = now.isoformat()
        for sec, expected in [(0, 0), (29, 0), (30, 1), (59, 1),
                              (60, 2), (90, 3), (900, 30),
                              (2970, 99), (12000, 99)]:
            self.assertEqual(
                elapsed_estimate(started, now + timedelta(seconds=sec)),
                expected, f"seconds={sec}")
        self.assertEqual(elapsed_estimate(started, now-timedelta(seconds=1)), 0)

    def test_progress_represents_timer_not_scan(self):
        m = progress_message("TTAAAAAAAAAAAAAAAAAAAAAAAA", 20)
        self.assertIn("20%", m)
        self.assertIn("30 saat", m)
        self.assertIn("bukan progress scan Turnitin", m)
        self.assertNotIn("100%", m)
        self.assertIn("99%", progress_message("TTTEST", 99))
        completed = progress_message("TTTEST", 100)
        self.assertIn("REPORT DELIVERED", completed)
        self.assertIn("100%", completed)

    def test_ticker_edits_existing_message_and_marks_progress_once(self):
        start = (datetime.now(timezone.utc)-timedelta(seconds=95)).isoformat()
        calls = []
        class FakeBackend:
            def rpc(self, name, **kwargs):
                calls.append((name, kwargs))
                if name == "processing":
                    return [{"order_id":"TTAAAAAAAAAAAAAAAAAAAAAAAA",
                             "user_id":123, "submitted_at":start,
                             "last_display_percent":1,"progress_message_id":765}]
                if name == "progress_mark":
                    return True
                raise AssertionError(name)
        flow = TurnitinFlow(FakeBackend(), 1)
        bot = SimpleNamespace(edit_message_text=AsyncMock())
        asyncio.run(flow.tick(SimpleNamespace(bot=bot)))
        bot.edit_message_text.assert_awaited_once()
        payload = bot.edit_message_text.await_args.kwargs
        self.assertEqual(payload["chat_id"],123)
        self.assertEqual(payload["message_id"],765)
        self.assertIn("3%",payload["text"])
        markers = [c for c in calls if c[0] == "progress_mark"]
        self.assertEqual(len(markers),1)
        self.assertEqual(markers[0][1]["p_percent"],3)

    def test_privacy_and_stock_rules(self):
        self.assertIn("ENABLE ROW LEVEL SECURITY", SQL)
        self.assertIn("REVOKE ALL ON berry_private.turnitin_plans", SQL)
        self.assertIn("current_user NOT IN ('service_role','postgres')", SQL)
        self.assertIn("stock=stock-1", SQL)
        self.assertIn("j.state<>'waiting_approval'", SQL)
        self.assertIn("j.user_id<>p_user", SQL)
        self.assertIn("state='delivered'", SQL)
        self.assertIn("request_key", SQL)
        self.assertIn("No cross-tenant auto-seeding", SQL)
        self.assertNotIn("SELECT t.id,\'similarity\'", SQL)
        self.assertIn("DEFAULT 0 CHECK(price_myr>=0)", SQL)
        self.assertIn("DEFAULT false", SQL)
        self.assertNotIn("turnitin.com/api", FLOW)

    def test_bot_wiring_checkout_gates_and_report_delivery(self):
        self.assertIn('"📑 Turnitin", callback_data="turnitin"',BOT)
        self.assertIn('"BERRY_TURNITIN_CHECKOUT_ENABLED"', BOT)
        self.assertIn('"BERRY_TURNITIN_ADMIN_ONLY", "true"', BOT)
        self.assertIn('if str(order_id).startswith("TT"):', BOT)
        self.assertIn('filters.Document.ALL, _turnitin_document_router', BOT)
        self.assertIn('_turnitin_admin_report_command', BOT)
        self.assertIn('interval=30, first=30', BOT)
        self.assertIn("await flow.tick(context)", BOT)
        self.assertIn("if str(order_id).startswith(\"TT\"):", BOT)

    def test_no_cross_flow_receipt_interception(self):
        self.assertIn("if oid and not ORDER_RE.fullmatch(oid):", FLOW)
        self.assertIn("return False", FLOW)
        self.assertIn("if self.admin_only and update.effective_user.id != self.admin_id:", FLOW)
        self.assertIn("Belum menerima tempahan atau bayaran pelanggan.", FLOW)

    def test_dashboard_is_protected_against_mutations(self):
        self.assertIn('"/turnitin/plans/<code>"', ADMIN)
        self.assertIn('"admin_edit"', ADMIN)
        self.assertIn('g.idempotency_key',ADMIN)
        self.assertIn('ADMIN_ISOLATED_DATABASE',ADMIN)
        self.assertIn('X-CSRF-Token', ADMIN)
        self.assertNotIn("SELECT assignment_file_id", ADMIN)


if __name__ == "__main__":
    main()
