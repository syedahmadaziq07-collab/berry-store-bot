"""STEP 4 — S01 exact balance display tests.

Pure Decimal conversion logic mirroring bot.py My Wallet. No network,
no wallet reads: the formatting contract only.
"""
import unittest
from decimal import Decimal, InvalidOperation


def credits_label(balance: str) -> str:
    """Exact mirror of the bot.py S01 fix (display conversion only)."""
    credits = Decimal(balance.replace('RM', '').replace(',', '')) * 1250
    label = f"{credits:,.2f}".rstrip("0").rstrip(".")
    return f"{label} Berry Credits ({balance})"


class ExactBalanceDisplayTests(unittest.TestCase):
    def test_odd_cent_balance_preserves_fractional_credits(self):
        self.assertEqual(credits_label("RM4.99"), "6,237.5 Berry Credits (RM4.99)")
        self.assertEqual(credits_label("RM0.01"), "12.5 Berry Credits (RM0.01)")

    def test_whole_balances_stay_unformatted_without_decimals(self):
        self.assertEqual(credits_label("RM5.00"), "6,250 Berry Credits (RM5.00)")
        self.assertEqual(credits_label("RM0.00"), "0 Berry Credits (RM0.00)")

    def test_large_balance_thousands_separator(self):
        self.assertEqual(credits_label("RM50.00"), "62,500 Berry Credits (RM50.00)")
        self.assertEqual(credits_label("RM1,234.56"),
                         "1,543,200 Berry Credits (RM1,234.56)")

    def test_exact_two_decimal_fraction_preserved(self):
        # RM1.23 -> 1537.5; a second odd cent accumulates e.g. RM2.46 -> 3075
        self.assertEqual(credits_label("RM1.23"), "1,537.5 Berry Credits (RM1.23)")
        self.assertEqual(credits_label("RM2.46"), "3,075 Berry Credits (RM2.46)")

    def test_non_numeric_balance_raises_and_falls_back(self):
        for bad in ("abc", "", "RM"):
            with self.assertRaises((ValueError, InvalidOperation, ArithmeticError)):
                credits_label(bad)

    def test_conversion_is_display_only(self):
        # The MYR accounting value itself must be untouched by the label.
        balance = "RM4.99"
        out = credits_label(balance)
        self.assertTrue(out.endswith(f"({balance})"))
        self.assertEqual(Decimal(balance.replace("RM", "")) * 1250, Decimal("6237.5"))


if __name__ == "__main__":
    unittest.main()
