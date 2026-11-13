"""STEP 2 blocker synthesis: MiniMax pricing (documented rates) + retail gate.

Uses ONLY officially documented public rates for
minimax/h3-max-turbo/text-to-video (fetched 2026-11-13 from the model page):
  480p: USD 0.01625/s (through Oct 31 2026 promo 35%),
        USD 0.0175/s (Nov 1–15 2026 promo 30%),
        USD 0.025/s  (standard, from Nov 16 2026).
Billing unit: per second of video generated.

The fail-closed retail formula (from docs/step2-minimax-cost-bound-20261112):
  provider_usd_bound = unit_usd * max_seconds
  minimum_retail_myr_cents = ceil_to_2sen(
      (provider_usd_bound*fx + fixed_myr + 1.00)/(1-fee_fraction))

Authenticated staging observation (USD 0.0175 at 480p) matches the
Nov 1–15 promo rate; the standard USD 0.025/s is the conservative
worst-case bound used for retail math. No paid calls here.
"""
import unittest
from decimal import Decimal, ROUND_CEILING


def minimum_retail_myr_cents(unit_usd, max_seconds, fx, fixed_myr="0", fee_fraction="0"):
    for name, v in (("unit_usd", unit_usd), ("max_seconds", max_seconds),
                    ("fx", fx), ("fixed_myr", fixed_myr),
                    ("fee_fraction", fee_fraction)):
        d = Decimal(str(v))
        if not d.is_finite():
            raise ValueError(f"non-finite {name}")
    unit = Decimal(str(unit_usd))
    seconds = Decimal(str(max_seconds))
    fx_d = Decimal(str(fx))
    fixed = Decimal(str(fixed_myr))
    fee = Decimal(str(fee_fraction))
    if unit <= 0 or seconds <= 0 or fx_d <= 0 or fixed < 0:
        raise ValueError("invalid inputs")
    if not (Decimal("0") <= fee < Decimal("0.9")):
        raise ValueError("fee fraction out of range")
    bound = unit * seconds
    gross_myr = bound * fx_d + fixed + Decimal("1.00")
    cents = gross_myr / (Decimal("1") - fee) * 100
    # ceil to RM0.02 (2 sen) steps
    cents = (cents / 2).to_integral_value(rounding=ROUND_CEILING) * 2
    return int(cents)


class MiniMaxRetailGateTests(unittest.TestCase):
    # Documented standard 480p rate from 2026-11-16: USD 0.025/s.
    def test_standard_480p_10s_minimum_retail(self):
        # bound = 0.25 USD; fx 4.7 -> RM1.175 + RM1 = RM2.175 -> 218 sen
        # (rounded up to 2-sen multiple: 218).
        self.assertEqual(minimum_retail_myr_cents("0.025", 10, "4.7"), 218)

    def test_promo_rate_lowers_cost_but_standard_used_for_gate(self):
        # Promo 0.0175: bound 0.175 USD -> RM0.8225 + 1 = 1.8225 -> 184 sen
        self.assertEqual(minimum_retail_myr_cents("0.0175", 10, "4.7"), 184)
        self.assertLess(184, 218)

    def test_fee_fraction_raises_retail(self):
        base = minimum_retail_myr_cents("0.025", 10, "4.7")
        with_fee = minimum_retail_myr_cents("0.025", 10, "4.7", fee_fraction="0.05")
        self.assertGreater(with_fee, base)

    def test_fixed_cost_adds(self):
        base = minimum_retail_myr_cents("0.025", 10, "4.7")
        with_fixed = minimum_retail_myr_cents("0.025", 10, "4.7", fixed_myr="0.05")
        self.assertEqual(with_fixed, base + 6)

    def test_invalid_inputs_fail_closed(self):
        for bad in ((0, 10, "4.7"), ("0.025", 0, "4.7"), ("0.025", 10, 0),
                    ("0.025", 10, "4.7", "0.95")):
            with self.assertRaises(ValueError):
                minimum_retail_myr_cents(*bad[:3],
                                          **({"fee_fraction": bad[3]} if len(bad) > 3 else {}))

    def test_margin_at_least_rm1_when_fee_zero(self):
        cents = minimum_retail_myr_cents("0.025", 10, "4.7")
        cost = Decimal("0.25") * Decimal("4.7") * 100
        self.assertGreaterEqual(Decimal(cents) - cost, Decimal("100"))

    def test_max_seconds_includes_overrun_bound(self):
        # documented ~0.7s overrun: 10.7s worst case at standard rate.
        c10 = minimum_retail_myr_cents("0.025", 10, "4.7")
        c107 = minimum_retail_myr_cents("0.025", "10.7", "4.7")
        self.assertGreater(c107, c10)


if __name__ == "__main__":
    unittest.main()
