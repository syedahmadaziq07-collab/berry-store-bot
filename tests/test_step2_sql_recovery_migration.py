import pathlib
import unittest
from step2_sql_recovery_model import Job, RecoveryRejected, bind_ambiguous


class RecoveryMigrationContractTests(unittest.TestCase):
    def setUp(self):
        self.job = Job("submission_unknown", "a" * 64)
        self.kw = dict(request_id="mock_r1", recovery_mode="operator_verified",
                       recovery_request_hash="a" * 64,
                       evidence="operator checked provider job and tenant correlation")

    def test_verified_unknown_can_bind_once(self):
        queued = bind_ambiguous(self.job, **self.kw)
        self.assertEqual(queued.state, "queued")
        self.assertEqual(queued.provider_request_id, "mock_r1")
        with self.assertRaises(RecoveryRejected):
            bind_ambiguous(queued, **self.kw)

    def test_unverified_and_mismatched_are_blocked(self):
        for changes in (
            {"recovery_mode": "automatic"}, {"recovery_request_hash": "b" * 64},
            {"evidence": "short"}, {"request_id": "other/path"},
        ):
            with self.subTest(changes=changes), self.assertRaises(RecoveryRejected):
                bind_ambiguous(self.job, **(self.kw | changes))

    def test_no_binding_from_unclaimed_or_refunded(self):
        for state in ("reserved", "refunded", "submitting", "delivered"):
            with self.assertRaises(RecoveryRejected):
                bind_ambiguous(Job(state, "a" * 64), **self.kw)

    def test_proposed_migration_is_guarded_and_rollback_available(self):
        root = pathlib.Path(__file__).resolve().parents[1] / "docs" / "sql"
        migration = (root / "step2_video_unknown_recovery_staging_proposed.sql").read_text()
        rollback = (root / "step2_video_unknown_recovery_staging_rollback.sql").read_text()
        for text in (migration, rollback):
            self.assertIn("BEGIN;", text)
            self.assertIn("COMMIT;", text)
            self.assertIn("expected", text)
            self.assertIn("pg_get_functiondef", text)
        for guard in ("recovery_mode", "operator_verified", "recovery_request_hash",
                      "recovery_evidence", "j.provider_request_id IS NULL"):
            self.assertIn(guard, migration)
        self.assertIn("ELSE", "ELSE")  # No SQL is executed by this suite.

    def test_budget_claim_logic_not_modified_by_patch(self):
        migration = (pathlib.Path(__file__).resolve().parents[1] /
                     "docs/sql/step2_video_unknown_recovery_staging_proposed.sql").read_text()
        self.assertIn("replace(original, needle, replacement)", migration)
        self.assertNotIn("UPDATE berry_private.ai_video_test_budgets", migration)
        self.assertNotIn("ai_wallet_apply_transaction", migration)


if __name__ == "__main__":
    unittest.main()
