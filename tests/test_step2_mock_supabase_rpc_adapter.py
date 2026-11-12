import unittest
from uuid import uuid4
from step2_mock_supabase_rpc_adapter import MockRpcVideoAdapter, AdapterBlocked

TENANT, JOB, BUDGET = [str(uuid4()) for _ in range(3)]


class FakeRpc:
    def __init__(self):
        self.calls = []
        self.fail = False
        self.state = "reserved"
        self.budget_claims = 0

    def call(self, name, args):
        self.calls.append((name, args))
        if self.fail:
            raise TimeoutError("ambiguous RPC")
        action = args["p_action"]
        if action == "claim_submit":
            if self.state != "reserved":
                return {"state": self.state}
            self.state = "submitting"
            self.budget_claims += 1
            return {"state": self.state, "budget_id": args["p_payload"]["budget_id"]}
        if action == "get":
            return {"state": self.state, "provider_request_id": "mock-r1"}
        raise AssertionError("unexpected RPC action")


class FakeProvider:
    def __init__(self):
        self.submits = 0
        self.polls = 0

    def submit(self, job):
        self.submits += 1
        raise AssertionError("no outbound allowed")

    def status(self, request_id):
        self.polls += 1
        return {"request_id": request_id, "status": "IN_PROGRESS"}


class MockRpcAdapterTests(unittest.TestCase):
    def setUp(self):
        self.rpc, self.provider = FakeRpc(), FakeProvider()
        self.adapter = MockRpcVideoAdapter(self.rpc, self.provider)

    def test_claim_before_outbound_and_correct_rpc_signature(self):
        self.assertEqual(self.adapter.claim_only(TENANT, JOB, BUDGET), "claim_confirmed_mock_only")
        name, args = self.rpc.calls[0]
        self.assertEqual(name, "berry_video_job")
        self.assertEqual(args["p_action"], "claim_submit")
        self.assertEqual(args["p_payload"], {"budget_id": BUDGET})
        self.assertEqual(self.provider.submits, 0)

    def test_duplicate_claim_cannot_reauthorize(self):
        self.adapter.claim_only(TENANT, JOB, BUDGET)
        with self.assertRaises(AdapterBlocked):
            self.adapter.claim_only(TENANT, JOB, BUDGET)
        self.assertEqual(self.rpc.budget_claims, 1)

    def test_rpc_timeout_is_unknown_and_blocks_submission(self):
        self.rpc.fail = True
        with self.assertRaisesRegex(AdapterBlocked, "rpc_outcome_unknown"):
            self.adapter.claim_only(TENANT, JOB, BUDGET)
        self.assertEqual(self.provider.submits, 0)

    def test_outbound_blocked_even_after_mock_claim(self):
        self.adapter.claim_only(TENANT, JOB, BUDGET)
        with self.assertRaisesRegex(AdapterBlocked, "durable_pre_submit_protocol_missing"):
            self.adapter.submit(TENANT, JOB)
        self.assertEqual(self.provider.submits, 0)

    def test_restart_recovery_only_polls_bound_request(self):
        self.rpc.state = "queued"
        adapter_after_restart = MockRpcVideoAdapter(self.rpc, self.provider)
        self.assertEqual(adapter_after_restart.recover(TENANT, JOB), "poll")
        self.assertEqual(self.provider.polls, 1)
        self.assertEqual(self.provider.submits, 0)
        self.rpc.state = "submission_unknown"
        self.assertEqual(adapter_after_restart.recover(TENANT, JOB), "needs_manual_reconciliation")
        self.assertEqual(self.provider.polls, 1)


if __name__ == "__main__":
    unittest.main()
