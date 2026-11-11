import unittest
import httpx
from decimal import Decimal
from telegram_wallet_bridge import TelegramWalletBridge
from ai_wallet_pricing_adapter import WalletPricingUnavailable


class WalletBridgeTests(unittest.TestCase):
    def test_read_only_and_tenant_scoped(self):
        seen = []
        def handler(request):
            seen.append(request)
            return httpx.Response(200, json=[{"balance": "2.00"}])
        bridge = TelegramWalletBridge("https://example.supabase.co", "dummy", "tenant-test",
                                      transport=httpx.MockTransport(handler))
        self.assertEqual(bridge.balance_myr(123), Decimal("2.00"))
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0].method, "GET")
        self.assertIn("tenant_id=eq.tenant-test", str(seen[0].url))
        self.assertIn("user_id=eq.123", str(seen[0].url))

    def test_bad_user_fails_closed(self):
        bridge = TelegramWalletBridge("https://example.supabase.co", "dummy", "tenant-test")
        with self.assertRaises(WalletPricingUnavailable):
            bridge.balance_myr(-1)


if __name__ == "__main__":
    unittest.main()
