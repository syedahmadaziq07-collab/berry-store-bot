import unittest
from decimal import Decimal
from ai_wallet_quote_check import check_telegram_wallet_for_ai
from ai_wallet_pricing_adapter import WalletPricingUnavailable


class Bridge:
    def __init__(self, balance):
        self.balance = Decimal(balance)
        self.calls = 0
    def balance_myr(self, user_id):
        self.calls += 1
        return self.balance


class Tests(unittest.TestCase):
    def test_eligible_only_no_charge(self):
        bridge = Bridge("5")
        result = check_telegram_wallet_for_ai(bridge, 123, api_cost_myr="0.05",
                         extra_cost_myr="0", confirmed_costs=True)
        self.assertTrue(result["eligible_for_reservation"])
        self.assertFalse(result["reservation_created"])
        self.assertFalse(result["generation_authorized"])
        self.assertEqual(result["credits"], 1325)
        self.assertEqual(result["wallet_debit_myr"], "1.06")
        self.assertEqual(bridge.calls, 1)

    def test_low_balance(self):
        result = check_telegram_wallet_for_ai(Bridge("0.5"), 123, api_cost_myr="0.05",
                         extra_cost_myr="0", confirmed_costs=True)
        self.assertFalse(result["eligible_for_reservation"])

    def test_unverified_cost_fails_before_wallet_read(self):
        bridge = Bridge("5")
        with self.assertRaises(WalletPricingUnavailable):
            check_telegram_wallet_for_ai(bridge, 123, api_cost_myr="0.05",
                         extra_cost_myr="0")
        self.assertEqual(bridge.calls, 0)


if __name__ == "__main__":
    unittest.main()
