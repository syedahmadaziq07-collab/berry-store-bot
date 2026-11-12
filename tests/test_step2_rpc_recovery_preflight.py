"""Read-only mock RPC recovery preflight regression tests."""
import unittest
from uuid import uuid4

from step2_mock_supabase_rpc_adapter import AdapterBlocked, MockRpcVideoAdapter


class Rpc:
    def __init__(self):
        self.calls = []
        self.state = "submission_unknown"
        self.request_hash = "a" * 64
        self.provider_request_id = None

    def call(self, name, args):
        self.calls.append((name, args))
        assert name == "berry_video_job" and args["p_action"] == "get"
        return {
            "state": self.state,
            "request_hash": self.request_hash,
            "provider_request_id": self.provider_request_id,
        }


class Provider:
    def __init__(self):
        self.submits = 0

    def submit(self, *_):
        self.submits += 1
        raise AssertionError("never submit")


class RecoveryPreflightTests(unittest.TestCase):
    def setUp(self):
        self.rpc, self.provider = Rpc(), Provider()
        self.adapter = MockRpcVideoAdapter(self.rpc, self.provider)
        self.tenant, self.job = str(uuid4()), str(uuid4())

    def preflight(self, verifier):
        return self.adapter.recovery_preflight(
            self.tenant, self.job, "mock_r1", verifier
        )

    def test_verified_preflight_is_read_only(self):
        result = self.preflight(lambda request_id, h: request_id == "mock_r1" and h == "a" * 64)
        self.assertEqual(result["decision"], "operator_review_required")
        self.assertIs(result["write_performed"], False)
        self.assertEqual([x[1]["p_action"] for x in self.rpc.calls], ["get"])
        self.assertEqual(self.provider.submits, 0)

    def test_unverified_response_rejected_without_write(self):
        for verifier in (None, lambda *_: {"status": "COMPLETED"}, lambda *_: False):
            with self.subTest(verifier=verifier), self.assertRaises(AdapterBlocked):
                self.preflight(verifier)
        self.assertTrue(all(x[1]["p_action"] == "get" for x in self.rpc.calls))
        self.assertEqual(self.provider.submits, 0)

    def test_missing_hash_and_wrong_state_fail_closed(self):
        self.rpc.request_hash = None
        with self.assertRaisesRegex(AdapterBlocked, "missing_persisted_request_hash"):
            self.preflight(lambda *_: True)
        self.rpc.request_hash = "a" * 64
        self.rpc.state = "queued"
        with self.assertRaisesRegex(AdapterBlocked, "recovery_state_not_unknown"):
            self.preflight(lambda *_: True)

    def test_already_bound_provider_request_rejected(self):
        self.rpc.provider_request_id = "existing"
        with self.assertRaisesRegex(AdapterBlocked, "trusted_recovery_preflight_rejected"):
            self.preflight(lambda *_: True)


if __name__ == "__main__":
    unittest.main()
