"""No paid requests or database calls: deterministic safety regression tests."""
import unittest
from step2_no_retry_protocol import (
    Attempt, State, SubmissionBlocked, authorize_single_post,
    record_response, restart_action,
)


class DurableNoRetryTests(unittest.TestCase):
    def test_durable_marker_is_required(self):
        job = Attempt(State.SUBMITTING)
        for value in (False, None, 1, "true"):
            with self.subTest(value=value), self.assertRaises(SubmissionBlocked):
                authorize_single_post(job, persisted=value)

    def test_exactly_one_post_authorization(self):
        first = authorize_single_post(Attempt(State.SUBMITTING), persisted=True)
        self.assertEqual(first.state, State.SUBMISSION_UNKNOWN)
        self.assertTrue(first.post_attempted)
        with self.assertRaises(SubmissionBlocked):
            authorize_single_post(first, persisted=True)
        self.assertEqual(restart_action(first), "operator_hold")

    def test_timeout_and_restart_never_retry(self):
        first = authorize_single_post(Attempt(State.SUBMITTING), persisted=True)
        self.assertEqual(restart_action(first), "operator_hold")
        self.assertEqual(restart_action(Attempt(State.SUBMITTING)), "operator_hold")
        self.assertEqual(restart_action(Attempt(State.RESERVED)), "no_submission_authorized")

    def test_trusted_response_binds_once(self):
        first = authorize_single_post(Attempt(State.SUBMITTING), persisted=True)
        queued = record_response(first, request_id="mock_r1", trusted_response=True)
        self.assertEqual(restart_action(queued), "poll_existing")
        with self.assertRaises(SubmissionBlocked):
            record_response(queued, request_id="mock_r1", trusted_response=True)

    def test_invalid_or_untrusted_responses_fail_closed(self):
        first = authorize_single_post(Attempt(State.SUBMITTING), persisted=True)
        for request_id, trusted in (("mock_r1", False), ("../bad", True),
                                    ("", True), ("mock_r1", "true")):
            with self.subTest(request_id=request_id, trusted=trusted), self.assertRaises(SubmissionBlocked):
                record_response(first, request_id=request_id, trusted_response=trusted)

    def test_no_second_generation_after_known_outcome(self):
        for state in (State.QUEUED, State.SUCCEEDED, State.FAILED):
            with self.subTest(state=state), self.assertRaises(SubmissionBlocked):
                authorize_single_post(Attempt(state, True, "mock_r1", 1), persisted=True)


if __name__ == "__main__":
    unittest.main()
