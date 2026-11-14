"""Safety tests for Berry Credits checkout, independent of live Telegram and Supabase."""
from pathlib import Path
import ast
import unittest


ROOT = Path(__file__).resolve().parents[1]
CODE = (ROOT / "bot.py").read_text(encoding="utf-8")
SQL = (ROOT / "docs/sql/berry_approve_topup_order.sql").read_text(encoding="utf-8")
CREATE_SQL = (ROOT / "docs/sql/berry_create_topup_order.sql").read_text(encoding="utf-8")


class BerryTopupContractTests(unittest.TestCase):
    def test_bot_syntax(self):
        ast.parse(CODE)

    def test_feature_flag_off_by_default(self):
        self.assertIn('_get_env("BERRY_TOPUP_CHECKOUT_ENABLED") == "true"', CODE)

    def test_qr_reused(self):
        self.assertIn('await send_payment_page(context, update.effective_chat.id, user.id, order, order["id"])', CODE)

    def test_receipt_support(self):
        self.assertIn('application/pdf', CODE)
        self.assertIn('image/png', CODE)
        self.assertIn('image/jpeg', CODE)
        self.assertIn('filters.Document.ALL, handle_topup_document', CODE)

    def test_approval_atomic_sql(self):
        self.assertIn('for update', SQL.lower())
        self.assertIn('ai_wallet_apply_transaction(', SQL)
        self.assertIn("o.status = 'waiting_approval'", SQL)
        self.assertIn("o.status = 'completed'", SQL)
        self.assertIn("idempotency_key='berry-topup:'||o.id", SQL)
        self.assertIn('revoke all on function', SQL.lower())

    def test_production_migration_preserves_existing_shop_orders(self):
        # Historical Browse Shop users can have multiple active orders.
        self.assertIn("berry_topup_one_active_user", CREATE_SQL)
        self.assertIn("id ~ '^BT[0-9A-F]{24}
        for credits in (6250, 12500, 25000, 62500):
            self.assertIn(str(credits), SQL)
        self.assertIn('Decimal(balance.replace', CODE)


if __name__ == "__main__":
    unittest.main()
", CREATE_SQL)
        self.assertNotIn("CREATE UNIQUE INDEX IF NOT EXISTS berry_orders_one_active_user", CREATE_SQL)
        self.assertIn("CREATE TABLE IF NOT EXISTS berry_private.topup_checkout_requests", CREATE_SQL)
        self.assertIn("current_user NOT IN ('service_role','postgres')", CREATE_SQL)
        self.assertIn("REVOKE ALL ON FUNCTION public.berry_create_topup_order(", CREATE_SQL)

    def test_no_idempotency_key_attached_to_legacy_order(self):
        self.assertIn("Existing Browse Shop order takes precedence", CREATE_SQL)
        self.assertIn("checkout replay mismatch", CREATE_SQL)
        self.assertIn("IF o.id ~ '^BT[0-9A-F]{24}
        for credits in (6250, 12500, 25000, 62500):
            self.assertIn(str(credits), SQL)
        self.assertIn('Decimal(balance.replace', CODE)


if __name__ == "__main__":
    unittest.main()
", CREATE_SQL)
        self.assertIn("pg_advisory_xact_lock", CREATE_SQL)

    def test_manual_qr_checkout_admin_only_by_default(self):
        self.assertIn('_get_env("BERRY_TOPUP_ADMIN_ONLY", "true") != "false"', CODE)
        self.assertIn("update.effective_user.id != ADMIN_ID", CODE)
        self.assertIn("send_payment_page(context, update.effective_chat.id", CODE)
        self.assertIn("Admin akan semak pembayaran dahulu.", CODE)

    def test_no_credit_before_approval_and_retryable_failure(self):
        start = CODE.index("async def _store_topup_receipt(")
        end = CODE.index("async def show_ai_video_text(", start)
        upload = CODE[start:end]
        self.assertNotIn("_topup_approve_atomic(", upload)
        self.assertIn('"status": "waiting_approval"', upload)
        start = CODE.index('    if str(order_id).startswith("BT"):',CODE.index('async def approve_order('))
        end = CODE.index('    # ── Instant loading feedback',start)
        approval = CODE[start:end]
        self.assertIn("await _approve_order_core(context, order_id)", approval)
        self.assertIn("except Exception as exc:", approval)
        self.assertNotIn('caption="⏳ Memproses..."', approval)

    def test_reject_filters_receipt_and_photo_checks_status(self):
        self.assertIn('&receipt_file_id=not.is.null', CODE)
        self.assertIn('rows[0].get("status") != "pending"', CODE)

    def test_credit_mapping(self):
        for credits in (6250, 12500, 25000, 62500):
            self.assertIn(str(credits), SQL)
        self.assertIn('Decimal(balance.replace', CODE)


if __name__ == "__main__":
    unittest.main()
