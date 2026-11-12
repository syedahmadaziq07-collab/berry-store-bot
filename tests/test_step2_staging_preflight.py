"""Staging E2E preflight tests. Deterministic, offline, zero-cost."""
import unittest

from step2_staging_preflight import PreflightCheck, StagingE2EPreflight, run_preflight

ALL_PASS = dict(pricing_verified=True, staging_db_writable=True,
                operator_allowlist_configured=True, worker_runtime_deployed=True,
                delivery_channel_configured=True, budget_cap_cents=500)


class PreflightTests(unittest.TestCase):
    def test_empty_inputs_fail_closed_with_reasons(self):
        r = run_preflight()
        self.assertFalse(r["ready_for_e2e_request"])
        self.assertEqual(len(r["checks"]), 6)
        for c in r["checks"]:
            self.assertEqual(c["status"], "FAIL")
            self.assertTrue(c["reason"])

    def test_all_pass_reports_ready_but_authorizes_nothing(self):
        r = run_preflight(**ALL_PASS)
        self.assertTrue(r["ready_for_e2e_request"])
        for c in r["checks"]:
            self.assertEqual(c["status"], "PASS")
        self.assertIn("authorizes nothing", r["note"])

    def test_partial_input_reports_exact_failing_check(self):
        r = run_preflight(pricing_verified=True, budget_cap_cents=500)
        failed = [c["check"] for c in r["checks"] if c["status"] == "FAIL"]
        self.assertEqual(sorted(failed), [
            "delivery_channel_configured", "operator_allowlist_configured",
            "staging_migration_applied", "worker_runtime_deployed"])

    def test_budget_ceiling_bounds(self):
        for cap in (None, 0, -1, 501, 12.0, True, "500"):
            r = run_preflight(**dict(ALL_PASS, budget_cap_cents=cap))
            cap_check = [c for c in r["checks"] if c["check"] == "budget_ceiling_rm5"][0]
            self.assertEqual(cap_check["status"], "FAIL")
        for cap in (1, 250, 500):
            r = run_preflight(**dict(ALL_PASS, budget_cap_cents=cap))
            cap_check = [c for c in r["checks"] if c["check"] == "budget_ceiling_rm5"][0]
            self.assertEqual(cap_check["status"], "PASS")

    def test_preflight_check_object_contract(self):
        c = PreflightCheck("x", True, "ok")
        self.assertEqual(c.as_dict(), {"check": "x", "status": "PASS", "reason": "ok"})
        c2 = PreflightCheck("y", "truthy-string", "no")
        # passed must be strictly True
        self.assertEqual(c2.as_dict()["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()