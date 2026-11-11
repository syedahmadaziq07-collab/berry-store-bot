import unittest
from decimal import Decimal
from ai_wallet_pricing_adapter import quote_for_wallet, can_afford, WalletPricingUnavailable

class WalletAdapterTests(unittest.TestCase):
    def test_requires_verified_costs(self):
        with self.assertRaises(WalletPricingUnavailable):
            quote_for_wallet("0.02", extra_cost_myr="0")
    def test_myr_wallet_conversion(self):
        q = quote_for_wallet("0.02", extra_cost_myr="0.03", confirmed_costs=True)
        self.assertEqual(q["credits"], 1313)
        self.assertEqual(q["wallet_debit_myr"], Decimal("1.0504"))
        self.assertTrue(can_afford("1.06", q))
        self.assertFalse(can_afford("1.05", q))

if __name__ == "__main__":
    unittest.main()
