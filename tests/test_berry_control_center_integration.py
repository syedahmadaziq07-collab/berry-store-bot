"""Release gates for Gemini Berry Store control center integration."""
import ast
from pathlib import Path
import unittest

BOT = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")

class ControlCenterIntegrationTests(unittest.TestCase):
    def test_bot_parses(self):
        ast.parse(BOT)

    def test_overview_requires_admin_secret_and_server_key(self):
        start = BOT.index("def berry_control_center_overview():")
        end = BOT.index('@_app.route("/api/dashboard/orders"', start)
        handler = BOT[start:end]
        self.assertIn("_check_dashboard_secret()", handler)
        self.assertIn("SUPABASE_SERVICE_KEY", handler)
        self.assertIn("TENANT_ID", handler)
        self.assertIn('sb_admin_get("orders"', handler)
        self.assertIn('sb_admin_get("products"', handler)
        self.assertIn('sb_admin_get("users"', handler)
        self.assertNotIn("sb_patch(", handler)
        self.assertNotIn("sb_post(", handler)

    def test_read_only_list_adapters(self):
        start = BOT.index("def berry_control_center_lists():")
        end = BOT.index('@_app.route("/api/dashboard/orders"', start)
        handler = BOT[start:end]
        for required in ("_check_dashboard_secret()", "SUPABASE_SERVICE_KEY",
                         "TENANT_ID", "sb_admin_get(", '"products"',
                         '"orders"', '"users"', "limit=500"):
            self.assertIn(required, handler)
        for forbidden in ("sb_admin_patch(", "sb_admin_post(", "password",
                          "receipt_file_id", "SUPABASE_SERVICE_KEY)"):
            self.assertNotIn(forbidden, handler)

    def test_overview_returns_gemini_kpi_contract(self):
        start = BOT.index("def berry_control_center_overview():")
        end = BOT.index('@_app.route("/api/admin/v1/shop/products"', start)
        handler = BOT[start:end]
        for field in ("kpis=kpis", "revenueTrend=[]", "categoryRevenue={}",
                      '"completedOrdersCount"', '"pendingOrdersCount"',
                      '"totalProducts"', "dataLimited=limited"):
            self.assertIn(field, handler)


if __name__ == "__main__":
    unittest.main()
