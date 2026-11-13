import unittest
from decimal import Decimal
from fal_pricing import PricingUnavailable
from minimax_retail_guard import minimax_10s_guarded_quote, MODEL


class FakePricing:
    def __init__(self, price="0.0175", unit="seconds"):
        self.price, self.unit = price, unit
    def exact_price(self, model):
        assert model == MODEL
        return float(self.price), self.unit


class MiniMaxRetailGuardTests(unittest.TestCase):
    def test_promo_rate_uses_standard_floor_and_11_seconds(self):
        q = minimax_10s_guarded_quote(
            FakePricing(), fx_myr_per_usd="4.70",
            verified_extra_cost_myr="0.20", all_extra_costs_verified=True)
        self.assertEqual(q["reserved_billed_seconds"], 11)
        self.assertEqual(q["reference_rate_usd_per_second"], "0.025")
        self.assertEqual(q["all_in_cost_cents"], 150)
        self.assertGreaterEqual(q["debit_cents"] - q["all_in_cost_cents"], 100)

    def test_high_api_rate_does_not_get_undercut(self):
        q = minimax_10s_guarded_quote(
            FakePricing("0.04"), fx_myr_per_usd="5.0",
            verified_extra_cost_myr="0", all_extra_costs_verified=True)
        self.assertEqual(q["reference_rate_usd_per_second"], "0.04")
        self.assertEqual(q["all_in_cost_cents"], 220)
        self.assertGreaterEqual(q["estimated_gross_margin_cents"], 100)

    def test_unknown_fee_or_fx_fails_closed(self):
        for kw in (
            {"verified_extra_cost_myr": None, "all_extra_costs_verified": True},
            {"verified_extra_cost_myr": "0", "all_extra_costs_verified": False},
            {"verified_extra_cost_myr": "-0.01", "all_extra_costs_verified": True},
        ):
            with self.subTest(kw=kw), self.assertRaises(PricingUnavailable):
                minimax_10s_guarded_quote(FakePricing(), fx_myr_per_usd="4.7", **kw)
        with self.assertRaises(PricingUnavailable):
            minimax_10s_guarded_quote(FakePricing(), fx_myr_per_usd="NaN",
                                      verified_extra_cost_myr="0", all_extra_costs_verified=True)

    def test_wrong_billing_unit_fails_closed(self):
        with self.assertRaises(PricingUnavailable):
            minimax_10s_guarded_quote(FakePricing(unit="requests"), fx_myr_per_usd=4.7,
                                      verified_extra_cost_myr="0", all_extra_costs_verified=True)


if __name__ == "__main__":
    unittest.main()
