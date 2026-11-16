"""Regressions for Berry Store's midnight sales report (Malaysia time)."""

import ast
from datetime import datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock
from zoneinfo import ZoneInfo


SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")
NAMES = {
    "_to_float_amount",
    "_fetch_completed_orders_for_period",
    "_build_sales_report_text",
    "_send_daily_sales_report",
}


def report_namespace():
    tree = ast.parse(SOURCE)
    funcs = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in NAMES]
    namespace = {
        "datetime": datetime,
        "dt_time": dt_time,
        "timedelta": timedelta,
        "timezone": timezone,
        "ZoneInfo": ZoneInfo,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object()),
        "ADMIN_ID": 123,
        "log": Mock(),
        "_safe_error": str,
    }
    compiled = ast.Module(body=[ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0), *funcs], type_ignores=[])
    exec(compile(ast.fix_missing_locations(compiled), "bot.py", "exec"), namespace)
    return namespace


class DailySalesReportTests(unittest.IsolatedAsyncioTestCase):
    async def test_report_totals_and_top_products(self):
        ns = report_namespace()
        report = ns["_build_sales_report_text"](
            datetime(2026, 11, 14),
            [
                {"product_name": "Canva", "amount": "3.10"},
                {"product_name": "Canva", "amount": "4.00"},
                {"product_name": "CapCut", "amount": "3.92"},
            ],
        )
        self.assertIn("Total Orders Completed: 3", report)
        self.assertIn("Total Sales: RM 11.02", report)
        self.assertIn("1. Canva — RM 7.10 / 2 orders", report)

    async def test_uses_real_columns_and_includes_completed_sales(self):
        ns = report_namespace()
        queries = []

        def fetch(table, query):
            self.assertEqual(table, "orders")
            queries.append(query)
            return [{"id": "ORDER1", "product_name": "Canva", "amount": 4.10}]

        async def run(label, operation):
            return operation()

        ns.update(sb_get=fetch, _run_supabase=run)
        start = datetime(2026, 11, 14, 16, tzinfo=timezone.utc)
        end = start + timedelta(days=1)
        result = await ns["_fetch_completed_orders_for_period"](start, end)
        self.assertEqual(len(result), 1)
        self.assertIn("status=in.(completed,approved)", queries[0])
        self.assertIn("created_at=gte.2026-11-14T16:00:00Z", queries[0])
        self.assertIn("created_at=lt.2026-11-15T16:00:00Z", queries[0])
        self.assertNotIn("completed_at", queries[0])
        self.assertNotIn("order_date", queries[0])

    async def test_fetches_more_than_one_database_page(self):
        ns = report_namespace()
        queries = []

        async def run(label, operation):
            return operation()

        def fetch(table, query):
            queries.append(query)
            if "offset=0" in query:
                return [{"id": f"O{i}", "amount": 1} for i in range(1000)]
            return [{"id": "O1000", "amount": 1}]

        ns.update(sb_get=fetch, _run_supabase=run)
        start = datetime(2026, 11, 14, 16, tzinfo=timezone.utc)
        result = await ns["_fetch_completed_orders_for_period"](start, start + timedelta(days=1))
        self.assertEqual(len(result), 1001)
        self.assertEqual(len(queries), 2)
        self.assertIn("offset=1000", queries[1])

    async def test_query_errors_are_not_reported_as_zero_sales(self):
        ns = report_namespace()

        async def failed(*args):
            raise RuntimeError("database unavailable")

        ns["_run_supabase"] = failed
        start = datetime(2026, 11, 14, 16, tzinfo=timezone.utc)
        with self.assertRaisesRegex(RuntimeError, "database unavailable"):
            await ns["_fetch_completed_orders_for_period"](start, start + timedelta(days=1))

        class FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 11, 16, 0, 0, tzinfo=tz)

        ns["datetime"] = FixedDatetime
        bot = SimpleNamespace(send_message=AsyncMock())
        await ns["_send_daily_sales_report"](SimpleNamespace(bot=bot))
        text = bot.send_message.await_args.kwargs["text"]
        self.assertIn("tak dapat dijana", text)
        self.assertNotIn("RM 0.00", text)

    async def test_midnight_report_covers_previous_malaysia_day(self):
        ns = report_namespace()
        times = []

        class FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 11, 16, 0, 0, tzinfo=tz)

        async def fetch(start, end):
            times.append((start, end))
            return [{"id": "ORDER1", "product_name": "Canva", "amount": "3.10"}]

        ns.update(datetime=FixedDatetime, _fetch_completed_orders_for_period=fetch)
        bot = SimpleNamespace(send_message=AsyncMock())
        await ns["_send_daily_sales_report"](SimpleNamespace(bot=bot))
        self.assertEqual(times[0][0], datetime(2026, 11, 14, 16, tzinfo=timezone.utc))
        self.assertEqual(times[0][1], datetime(2026, 11, 15, 16, tzinfo=timezone.utc))
        text = bot.send_message.await_args.kwargs["text"]
        self.assertIn("Date: 15/11/2026", text)
        self.assertIn("Total Sales: RM 3.10", text)


if __name__ == "__main__":
    unittest.main()
