"""Safety tests for Berry Credits checkout, independent of live Telegram and Supabase."""
from pathlib import Path
import ast
import unittest


ROOT = Path(__file__).resolve().parents[1]
CODE = (ROOT / "bot.py").read_text(encoding="utf-8")
SQL = (ROOT / "docs/sql/berry_approve_topup_order.sql").read_text(encoding="utf-8")


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

    def test_credit_mapping(self):
        for credits in (6250, 12500, 25000, 62500):
            self.assertIn(str(credits), SQL)
        self.assertIn('Decimal(balance.replace', CODE)


if __name__ == "__main__":
    unittest.main()
