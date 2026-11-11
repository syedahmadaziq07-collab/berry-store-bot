import unittest
from decimal import Decimal
from berry_credit_pricing import (CREDITS_PER_MYR, TOPUP_PACKAGES,
                                  required_credits, gross_profit_myr)


class PricingTests(unittest.TestCase):
    def test_existing_bot_topup(self):
        self.assertEqual(CREDITS_PER_MYR, 1250)
        self.assertEqual(TOPUP_PACKAGES, {
            "starter": (Decimal("5"), 6250),
            "creator": (Decimal("10"), 12500),
            "pro": (Decimal("20"), 25000),
            "studio": (Decimal("50"), 62500)})

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
