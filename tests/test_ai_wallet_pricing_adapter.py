import unittest
from decimal import Decimal
from ai_wallet_pricing_adapter import quote_for_wallet, can_afford, WalletPricingUnavailable

class WalletAdapterTests(unittest.TestCase):
    def test_requires_verified_costs(self):
        with self.assertRaises(WalletPricingUnavailable):
            quote_for_wallet("0.02", extra_cost_myr="0")
    def test_myr_wallet_conversion(self):
        q = quote_for_wallet("0.02", extra_cost_myr="0.03", confirmed_costs=True)
        self.assertEqual(q["credits"], 1325)
        self.assertEqual(q["wallet_debit_myr"], Decimal("1.06"))
        self.assertTrue(can_afford("1.06", q))
        self.assertFalse(can_afford("1.05", q))

    def test_all_quotes_match_cent_wallet_and_preserve_margin(self):
        from berry_credit_pricing import gross_profit_myr
        for mills in range(1001):
            cost = Decimal(mills) / 1000
            q = quote_for_wallet(cost, extra_cost_myr="0.017", confirmed_costs=True)
            self.assertEqual(q["wallet_debit_myr"], q["wallet_debit_myr"].quantize(Decimal("0.01")))
            self.assertEqual(Decimal(q["credits"]) / 1250, q["wallet_debit_myr"])
            self.assertGreaterEqual(gross_profit_myr(q["credits"], cost, extra_cost_myr="0.017"), 1)

if __name__ == "__main__":
    unittest.main()
