"""Static regression tests for server-side order dashboard access."""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
BOT = (ROOT / "bot.py").read_text(encoding="utf-8")
DASH = (ROOT / "dashboard.html").read_text(encoding="utf-8")


class OrdersDashboardSecurity(unittest.TestCase):
    def test_python_parses(self):
        ast.parse(BOT)

    def test_no_direct_orders_queries_in_dashboard(self):
        self.assertNotIn("sb.from('orders')", DASH)
        self.assertNotIn('sb.from("orders")', DASH)
        self.assertIn("function orderQuery()", DASH)
        self.assertIn("/api/dashboard/orders?", DASH)
        self.assertIn("'X-Dashboard-Secret':_dashSecret", DASH)

    def test_proxy_requires_secret_and_server_key(self):
        start = BOT.index("def dashboard_orders_read():")
        end = BOT.index('@_app.route("/api/dashboard/approve-order"', start)
        endpoint = BOT[start:end]
        self.assertIn("_check_dashboard_secret()", endpoint)
        self.assertIn("not TENANT_ID or not SUPABASE_SERVICE_KEY", endpoint)
        self.assertIn("allowed_columns", endpoint)
        self.assertIn("allowed_filters", endpoint)
        self.assertIn('("tenant_id", f"eq.{TENANT_ID}")', endpoint)
        self.assertIn("_sb_admin_headers()", endpoint)
        self.assertIn("query.append((key,", endpoint)


if __name__ == "__main__":
    unittest.main()
