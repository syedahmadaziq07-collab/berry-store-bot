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

if __name__ == "__main__":
    unittest.main()
