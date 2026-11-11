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
        end = BOT.index('@_app.route("/api/admin/v1/shop/products"', start)
        handler = BOT[start:end]
        self.assertIn("_gemini_session_guard()", handler)
        self.assertIn("SUPABASE_SERVICE_KEY", handler)
        self.assertIn("TENANT_ID", handler)
        self.assertIn('sb_admin_get("orders"', handler)
        self.assertIn('sb_admin_get("products"', handler)
        self.assertIn('sb_admin_get("users"', handler)
        self.assertNotIn("sb_patch(", handler)
        self.assertNotIn("sb_post(", handler)

    def test_signed_cookie_auth_and_csrf(self):
        for required in ('URLSafeTimedSerializer', 'max_age=_GEMINI_AUTH_TTL',
                         'httponly=True', 'secure=True', 'samesite="Strict"',
                         'X-CSRF-Token', 'hmac.compare_digest',
                         'def gemini_admin_login():', 'def gemini_admin_me():',
                         'def gemini_admin_logout():'):
            self.assertIn(required, BOT)
        self.assertNotIn('berrystore2026!', BOT)

    def test_read_only_list_adapters(self):
        start = BOT.index("def berry_control_center_lists():")
        end = BOT.index('@_app.route("/api/dashboard/orders"', start)
        handler = BOT[start:end]
        for required in ("_gemini_session_guard()", "SUPABASE_SERVICE_KEY",
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


    def test_extra_adapters_never_return_credential_passwords(self):
        start = BOT.index("def berry_control_center_extra_reads():")
        end = BOT.index('@_app.route("/api/dashboard/orders"', start)
        handler = BOT[start:end]
        self.assertIn("_gemini_session_guard()", handler)
        self.assertIn('("credentials", "id,product_id,variant_id,is_used,created_at")', handler)
        self.assertNotIn("email,password", handler)
        self.assertNotIn("sb_admin_patch(", handler)
        self.assertNotIn("sb_admin_post(", handler)
        self.assertIn("safe_keys =", handler)

    def test_wallet_reads_are_authenticated_and_read_only(self):
        start = BOT.index("def berry_control_center_module_reads():")
        end = BOT.index('@_app.route("/api/dashboard/orders"', start)
        handler = BOT[start:end]
        self.assertIn("_gemini_session_guard()", handler)
        self.assertIn('sb_admin_get("ai_wallets"', handler)
        self.assertIn('sb_admin_get("ai_wallet_transactions"', handler)
        self.assertNotIn("sb_admin_patch(", handler)

if __name__ == "__main__":
    unittest.main()
