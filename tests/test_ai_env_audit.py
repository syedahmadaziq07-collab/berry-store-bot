"""Environment readiness audit tests (presence-only; no secret values)."""
import unittest

from ai_env_audit import audit_environment, format_report


FULLY_CONFIGURED = {
    "BERRY_QUOTE_FLOW_ENABLED": "true",
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_SERVICE_KEY": "x" * 40,
    "TENANT_ID": "11111111-1111-4111-8111-111111111111",
    "FAL_KEY": "keyid:secret",
    "BERRY_QUOTE_SIGNING_KEY": "y" * 32,
    "BERRY_AI_PAYMENT_FEE_FRACTION": "0.029",
    "BERRY_AI_FIXED_COST_MYR": "0.10",
}


class EnvAuditTests(unittest.TestCase):
    def _get(self, env, name):
        return next(r for r in audit_environment(env) if r["variable"] == name)

    def test_fully_configured_reports_present(self):
        for name in ("BERRY_QUOTE_FLOW_ENABLED", "SUPABASE_URL",
                     "SUPABASE_SERVICE_KEY", "TENANT_ID", "FAL_KEY",
                     "BERRY_QUOTE_SIGNING_KEY"):
            self.assertEqual(self._get(FULLY_CONFIGURED, name)["status"],
                             "PRESENT", name)
        self.assertEqual(
            self._get(FULLY_CONFIGURED, "BERRY_AI_PAYMENT_FEE_FRACTION")["status"],
            "PRESENT")

    def test_missing_costs_are_owner_input_required(self):
        env = dict(FULLY_CONFIGURED)
        del env["BERRY_AI_PAYMENT_FEE_FRACTION"]
        r = self._get(env, "BERRY_AI_PAYMENT_FEE_FRACTION")
        self.assertEqual(r["status"], "MISSING")
        self.assertIn("OWNER INPUT REQUIRED", r["note"])

    def test_auto_fx_mode_unverified_not_missing(self):
        env = dict(FULLY_CONFIGURED)  # no manual FX vars
        r = self._get(env, "BERRY_AI_FX_MYR_PER_USD")
        self.assertEqual(r["status"], "UNVERIFIED")
        self.assertIn("auto", r["note"])

    def test_manual_fx_override_present(self):
        env = dict(FULLY_CONFIGURED,
                   BERRY_AI_FX_MYR_PER_USD="4.45",
                   BERRY_AI_FX_SOURCE="manual-audit",
                   BERRY_AI_FX_SOURCE_TIMESTAMP="1730000000")
        self.assertEqual(self._get(env, "BERRY_AI_FX_MYR_PER_USD")["status"],
                         "PRESENT")

    def test_invalid_values_flagged(self):
        env = dict(FULLY_CONFIGURED, TENANT_ID="not-a-uuid",
                   SUPABASE_URL="http://insecure",
                   BERRY_QUOTE_SIGNING_KEY="short",
                   BERRY_AI_PAYMENT_FEE_FRACTION="1.5")
        self.assertEqual(self._get(env, "TENANT_ID")["status"], "INVALID")
        self.assertEqual(self._get(env, "SUPABASE_URL")["status"], "INVALID")
        self.assertEqual(self._get(env, "BERRY_QUOTE_SIGNING_KEY")["status"],
                         "INVALID")
        self.assertEqual(
            self._get(env, "BERRY_AI_PAYMENT_FEE_FRACTION")["status"], "INVALID")

    def test_disabled_flag_missing_or_invalid(self):
        self.assertEqual(self._get({}, "BERRY_QUOTE_FLOW_ENABLED")["status"],
                         "MISSING")
        self.assertEqual(
            self._get(dict(FULLY_CONFIGURED,
                           BERRY_QUOTE_FLOW_ENABLED="yes"),
                      "BERRY_QUOTE_FLOW_ENABLED")["status"], "INVALID")

    def test_report_never_contains_secret_values(self):
        env = dict(FULLY_CONFIGURED)
        text = format_report(audit_environment(env))
        self.assertNotIn("x" * 40, text)     # service key value
        self.assertNotIn("keyid:secret", text)
        self.assertNotIn("y" * 32, text)

    def test_empty_environment_reports_missing(self):
        report = audit_environment({})
        statuses = {r["variable"]: r["status"] for r in report}
        self.assertEqual(statuses["SUPABASE_URL"], "MISSING")
        self.assertEqual(statuses["FAL_KEY"], "MISSING")
        self.assertEqual(statuses["BERRY_AI_FIXED_COST_MYR"], "MISSING")


if __name__ == "__main__":
    unittest.main()
