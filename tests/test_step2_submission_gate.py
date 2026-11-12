"""Durable no-retry worker integration gate tests (PR #75 wiring).

No paid requests, databases, or network: deterministic fake claim/post functions.
"""
import unittest
from step2_no_retry_protocol import Attempt, State, SubmissionBlocked
from step2_submission_gate import WorkerSubmissionGate


def snap(state, post=False, rid=None, gen=0):
    return Attempt(state, post, rid, gen)


class WorkerGateTests(unittest.TestCase):
    def post_success(self):
        pass

    def make(self, claim_result, post_result, posts=None):
        posts = posts if posts is not None else []
        def claim():
            if isinstance(claim_result, Exception):
                raise claim_result
            return claim_result
        def post():
            posts.append(1)
            if callable(post_result):
                return post_result()
            return post_result
        return WorkerSubmissionGate(claim, post), posts

    def test_single_post_then_bound(self):
        gate, posts = self.make(
            snap(State.SUBMITTING, gen=3),
            {"request_id": "rid-1"})
        out = gate.submit(snap(State.SUBMITTING, gen=3))
        self.assertEqual((out.state, out.provider_request_id, out.generation),
                         (State.QUEUED, "rid-1", 4))
        self.assertEqual(len(posts), 1)

    def test_claim_failure_blocks_post(self):
        gate, posts = self.make(SubmissionBlocked("commit failed"), {"request_id": "x"})
        with self.assertRaises(SubmissionBlocked):
            gate.submit(snap(State.SUBMITTING))
        self.assertEqual(posts, [])

    def test_claim_returning_non_attempt_blocks_post(self):
        gate, posts = self.make({"claimed": True}, {"request_id": "x"})
        with self.assertRaises(SubmissionBlocked):
            gate.submit(snap(State.SUBMITTING))
        self.assertEqual(posts, [])

    def test_stale_claim_generation_blocks_post(self):
        # A competing worker already advanced the durable state.
        gate, posts = self.make(snap(State.SUBMISSION_UNKNOWN, post=True, rid=None, gen=4),
                                {"request_id": "x"})
        with self.assertRaises(SubmissionBlocked):
            gate.submit(snap(State.SUBMITTING, gen=3))
        self.assertEqual(posts, [])

    def test_already_posted_durable_state_blocks_post(self):
        gate, posts = self.make(snap(State.QUEUED, post=True, rid="r1"), {"request_id": "x"})
        with self.assertRaises(SubmissionBlocked):
            gate.submit(snap(State.SUBMITTING))
        self.assertEqual(posts, [])

    def test_malformed_response_keeps_unknown_and_no_retry(self):
        gate, posts = self.make(snap(State.SUBMITTING), {"no_request_id": True})
        with self.assertRaises(SubmissionBlocked):
            gate.submit(snap(State.SUBMITTING))
        self.assertEqual(len(posts), 1)
        # A second submit attempt after restart must never POST again.
        with self.assertRaises(SubmissionBlocked):
            gate.submit(snap(State.SUBMISSION_UNKNOWN, post=True))
        self.assertEqual(len(posts), 1)

    def test_non_dict_response_blocks(self):
        gate, posts = self.make(snap(State.SUBMITTING), "rid-2")
        with self.assertRaises(SubmissionBlocked):
            gate.submit(snap(State.SUBMITTING))
        self.assertEqual(len(posts), 1)

    def test_non_submittable_states_rejected_before_claim_or_post(self):
        for state in (State.QUEUED, State.SUCCEEDED, State.FAILED,
                      State.SUBMISSION_UNKNOWN):
            gate, posts = self.make(snap(state), {"request_id": "x"})
            with self.assertRaises(SubmissionBlocked):
                gate.submit(snap(state))
            self.assertEqual(posts, [])

    def test_constructor_rejects_non_callable(self):
        with self.assertRaises(SubmissionBlocked):
            WorkerSubmissionGate(None, lambda: {})
        with self.assertRaises(SubmissionBlocked):
            WorkerSubmissionGate(lambda: None, "not-callable")

    def test_non_attempt_snapshot_rejected(self):
        gate, _ = self.make(snap(State.SUBMITTING), {"request_id": "x"})
        with self.assertRaises(SubmissionBlocked):
            gate.submit({"state": "submitting"})


if __name__ == "__main__":
    unittest.main()