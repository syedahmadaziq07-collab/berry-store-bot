import unittest
from decimal import Decimal
from berry_credit_pricing import TOPUP_CREDITS, TOPUP_PRICE_MYR, required_credits, gross_profit_myr


class PricingTests(unittest.TestCase):
    def test_topup(self):
        self.assertEqual(TOPUP_CREDITS, 5000)
        self.assertEqual(TOPUP_PRICE_MYR, Decimal("6.00"))

    def test_margin_guard(self):
        for cost in ("0.012", "0.51", "0.999"):
            credits = required_credits(cost)
            self.assertGreaterEqual(gross_profit_myr(credits, cost), Decimal("1.00"))
            self.assertLess(gross_profit_myr(credits - 1, cost), Decimal("1.00"))

    def test_invalid_cost(self):
        with self.assertRaises(ValueError):
            required_credits("-0.01")


if __name__ == "__main__":
    unittest.main()
