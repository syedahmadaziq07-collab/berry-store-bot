"""Static release gates for Berry Store payment security (no live data)."""
from pathlib import Path
import ast
import unittest

ROOT = Path(__file__).resolve().parents[1]
BOT = (ROOT / "bot.py").read_text(encoding="utf-8")
RPC = (ROOT / "docs/sql/berry_approve_topup_order.sql").read_text(encoding="utf-8")
LOCKDOWN = (ROOT / "docs/sql/berry_orders_access_lockdown.sql").read_text(encoding="utf-8")


class PaymentReleaseGates(unittest.TestCase):
    def test_bot_parses(self):
        ast.parse(BOT)

    def test_orders_never_use_anon_key(self):
        self.assertIn('if table == "orders":', BOT)
        self.assertIn('SUPABASE_SERVICE_KEY required for orders', BOT)
        for method in ("sb_get", "sb_post", "sb_upsert", "sb_patch"):
            start = BOT.index("def " + method + "(")
            end = BOT.find("\ndef ", start + 5)
            code = BOT[start:end if end != -1 else None]
            self.assertIn("_orders_api_headers(table, _sb_headers())", code, method)

    def test_approval_idempotency(self):
        self.assertIn("for update", RPC.lower())
        self.assertIn("ai_wallet_apply_transaction", RPC)
        self.assertIn("idempotency_key='berry-topup:'||o.id", RPC)
        self.assertIn("t.reference=o.id", RPC)
        self.assertIn("o.status = 'waiting_approval'", RPC)
        self.assertIn("o.status = 'completed'", RPC)
        self.assertIn("auth.role() is distinct from 'service_role'", RPC)
        self.assertIn("revoke all on function", RPC.lower())

    def test_lockdown_denies_public(self):
        self.assertIn("drop policy if exists allow_all", LOCKDOWN.lower())
        self.assertIn("revoke all privileges on table public.orders from anon, authenticated, public", LOCKDOWN.lower())
        self.assertIn("grant select, insert, update, delete on table public.orders to service_role", LOCKDOWN.lower())

    def test_feature_flag_defaults_off(self):
        self.assertIn('_get_env("BERRY_TOPUP_CHECKOUT_ENABLED") == "true"', BOT)


if __name__ == "__main__":
    unittest.main()
