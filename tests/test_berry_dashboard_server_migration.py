"""Static security gates for Berry Store server-only dashboard migration.

These checks do not substitute for authenticated HTTP and Telegram integration tests.
"""
import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
BOT = (ROOT / "bot.py").read_text(encoding="utf-8")
DASH = (ROOT / "dashboard.html").read_text(encoding="utf-8")


class DashboardMigrationTests(unittest.TestCase):
    def test_bot_compiles(self):
        ast.parse(BOT)

    def test_browser_has_no_supabase_client_or_key(self):
        for forbidden in ("supabase.createClient(", "sb.channel(", "sb.auth.",
                          "bs_key', key", "localStorage.getItem('bs_key')",
                          'id="cfgKey"', "Service Role Key", "@supabase/supabase-js"):
            self.assertNotIn(forbidden, DASH)
        self.assertIn("sb={from:serverTable}", DASH)
        self.assertIn("localStorage.removeItem('bs_key')", DASH)
        self.assertIn("localStorage.removeItem('bs_dash_secret')", DASH)

    def test_server_only_gateway(self):
        start = BOT.index("def dashboard_table_gateway():")
        end = BOT.index('@_app.route("/api/dashboard/orders"', start)
        route = BOT[start:end]
        for required in ("_check_dashboard_secret()", "SUPABASE_SERVICE_KEY",
                         "_DASHBOARD_ACTIONS[table]", "_DASHBOARD_TABLE_FIELDS[table]",
                         '"tenant_id", f"eq.{TENANT_ID}"',
                         '"Unsafe write filter"', '"Write fields not permitted"',
                         '"Credentials detail access denied"'):
            self.assertIn(required, route)

    def test_write_table_permissions(self):
        self.assertIn('"users": {"select"}', BOT)
        self.assertIn('"credentials": {"select","insert"}', BOT)
        self.assertIn('"products": {"select","update"}', BOT)
        self.assertIn('"product_variants": {"select","insert","update","delete"}', BOT)
        self.assertIn('table != "product_variants" or not filters', BOT)

    def test_legacy_order_proxy_remains(self):
        self.assertIn("def dashboard_orders_read():", BOT)
        self.assertIn("function orderQuery()", DASH)
        self.assertNotIn("sb.from('orders')", DASH)


if __name__ == "__main__":
    unittest.main()
