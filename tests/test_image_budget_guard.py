"""Budget guard tests: RM5 ceiling, worst-case rejection, atomic semantics."""
import unittest

from image_budget_guard import (BudgetExceeded, MAX_BUDGET_CENTS, can_afford,
                                preflight, remaining_budget,
                                validate_budget_config)


class BudgetGuardTests(unittest.TestCase):
    def test_owner_ceiling_is_500_cents(self):
        self.assertEqual(MAX_BUDGET_CENTS, 500)

    def test_cap_above_rm5_rejected(self):
        with self.assertRaises(BudgetExceeded):
            validate_budget_config(501, 0, 0)

    def test_remaining_and_afford(self):
        self.assertEqual(remaining_budget(500, 100, 50), 350)
        self.assertTrue(can_afford(500, 100, 50, 350))
        self.assertFalse(can_afford(500, 100, 50, 351))

    def test_worst_case_exactly_remaining_allowed(self):
        self.assertTrue(can_afford(500, 0, 0, 500))
        self.assertFalse(can_afford(500, 0, 0, 501))
        with self.assertRaises(BudgetExceeded):
            preflight(True, 501, 500, 0, 0)

    def test_unknown_submission_retains_reservation(self):
        # A job with unknown outcome keeps its full worst-case reserved:
        # used=0, reserved=worst-case of an ambiguous job.
        self.assertEqual(remaining_budget(500, 0, 400), 100)
        self.assertFalse(can_afford(500, 0, 400, 101))

    def test_invalid_inputs_rejected(self):
        for args in ((None, 0, 0), (500, -1, 0), (500, 0, -1),
                     (500, 501, 0), (500, 0, 501)):
            with self.assertRaises(BudgetExceeded):
                validate_budget_config(*args)

    def test_preflight_full_pass(self):
        out = preflight(True, 100, 500, 100, 100)
        self.assertEqual(out["remaining_after"], 200)
        self.assertEqual(out["worst_case_cents"], 100)

    def test_preflight_rejects_unauthorized(self):
        with self.assertRaises(BudgetExceeded):
            preflight(False, 100, 500, 0, 0)

    def test_preflight_rejects_worst_case_over_remaining(self):
        with self.assertRaises(BudgetExceeded):
            preflight(True, 201, 500, 100, 200)

    def test_preflight_rejects_bad_worst_case(self):
        for wc in (0, -1, 1.5, True, "100", None):
            with self.assertRaises(BudgetExceeded):
                preflight(True, wc, 500, 0, 0)


if __name__ == "__main__":
    unittest.main()
