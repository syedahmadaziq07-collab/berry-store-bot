"""Manual QR Berry Credits safety gates (no bank, Telegram or live wallet calls)."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE = (ROOT / "bot.py").read_text(encoding="utf-8")
CREATE = (ROOT / "docs/sql/berry_create_topup_order.sql").read_text(encoding="utf-8")


class ManualTopupReleaseTests(unittest.TestCase):
    def test_python_parses_and_has_no_str_call_warning(self):
        ast.parse(CODE)
        segment = CODE.split('elif section == "topup":', 1)[1].split(
            'elif section == "wallet":', 1)[0]
        self.assertIn('            + ("✅ QR payment', segment)

    def test_production_schema_does_not_restrict_old_shop_orders(self):
        self.assertIn("berry_topup_one_active_user", CREATE)
        self.assertIn("id ~ '^BT[0-9A-F]{24}$'", CREATE)
        self.assertNotIn("CREATE UNIQUE INDEX IF NOT EXISTS berry_orders_one_active_user", CREATE)
        self.assertIn("CREATE TABLE IF NOT EXISTS berry_private.topup_checkout_requests", CREATE)
        self.assertIn("current_user NOT IN ('service_role','postgres')", CREATE)
        self.assertIn("REVOKE ALL ON FUNCTION public.berry_create_topup_order(", CREATE)

    def test_idempotency_and_shop_reuse(self):
        self.assertIn("Existing Browse Shop order takes precedence", CREATE)
        self.assertIn("checkout replay mismatch", CREATE)
        self.assertIn("IF o.id ~ '^BT[0-9A-F]{24}$'", CREATE)
        self.assertIn("pg_advisory_xact_lock", CREATE)

    def test_checkout_admin_only_by_default(self):
        self.assertIn('_get_env("BERRY_TOPUP_CHECKOUT_ENABLED") == "true"', CODE)
        self.assertIn('_get_env("BERRY_TOPUP_ADMIN_ONLY", "true") != "false"', CODE)
        self.assertIn("update.effective_user.id != ADMIN_ID", CODE)
        self.assertIn("send_payment_page(context, update.effective_chat.id", CODE)

    def test_receipt_does_not_credit_wallet(self):
        start = CODE.index("async def _store_topup_receipt(")
        end = CODE.index("async def show_ai_video_text(", start)
        upload = CODE[start:end]
        self.assertNotIn("_topup_approve_atomic(", upload)
        self.assertIn('"status": "waiting_approval"', upload)
        self.assertIn("Admin akan semak pembayaran dahulu.", upload)

    def test_approve_failure_retains_original_admin_buttons(self):
        start = CODE.index('    if str(order_id).startswith("BT"):', CODE.index("async def approve_order("))
        end = CODE.index("    # ── Instant loading feedback", start)
        approval = CODE[start:end]
        self.assertIn("await _approve_order_core(context, order_id)", approval)
        self.assertIn("except Exception as exc:", approval)
        self.assertNotIn('caption="⏳ Memproses..."', approval)

    def test_reject_filters_receipt_and_photo_checks_status(self):
        self.assertIn("&receipt_file_id=not.is.null", CODE)
        self.assertIn('rows[0].get("status") != "pending"', CODE)


if __name__ == "__main__":
    unittest.main()
