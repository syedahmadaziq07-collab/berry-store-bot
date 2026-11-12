"""Isolated fail-closed provider recovery gate tests; no network or DB."""
import unittest

from step2_sql_recovery_model import (
    Job, RecoveryRejected, bind_with_provider_verification,
)


class TrustedRecoveryGateTests(unittest.TestCase):
    def setUp(self):
        self.job = Job("submission_unknown", "a" * 64)
        self.args = dict(request_id="mock_r1", recovery_request_hash="a" * 64)

    def test_rejects_absent_or_truthy_unverified_provider_evidence(self):
        for verifier in (None, lambda *_: {"status": "COMPLETED"},
                         lambda *_: "verified", lambda *_: 1, lambda *_: False):
            with self.subTest(verifier=verifier), self.assertRaises(RecoveryRejected):
                bind_with_provider_verification(
                    self.job, **self.args, verify_provider_request=verifier
                )

    def test_rejects_provider_errors_and_unknown_correlations(self):
        def unavailable(*_):
            raise TimeoutError("provider unavailable")
        for kw in (
            dict(self.args, recovery_request_hash="b" * 64),
            dict(self.args, request_id="../bad"),
        ):
            with self.subTest(kw=kw), self.assertRaises(RecoveryRejected):
                bind_with_provider_verification(self.job, **kw,
                                                verify_provider_request=lambda *_: True)
        with self.assertRaises(RecoveryRejected):
            bind_with_provider_verification(self.job, **self.args,
                                            verify_provider_request=unavailable)

    def test_accepts_only_explicit_trusted_confirmation_once(self):
        calls = []
        def verified(request_id, request_hash):
            calls.append((request_id, request_hash))
            return True
        queued = bind_with_provider_verification(
            self.job, **self.args, verify_provider_request=verified
        )
        self.assertEqual(calls, [("mock_r1", "a" * 64)])
        self.assertEqual(queued.state, "queued")
        self.assertEqual(queued.provider_request_id, "mock_r1")
        with self.assertRaises(RecoveryRejected):
            bind_with_provider_verification(
                queued, **self.args, verify_provider_request=verified
            )
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
