import unittest
from step2_offline_queue_contract import (
    QueueContractError, authorize_offline_budget, classify_queue_status,
    classify_submit_outcome,
)


class OfflineQueueContractTests(unittest.TestCase):
    def test_polling_backoff_and_completion(self):
        for attempt in (0, 1, 5, 11):
            for status in ("IN_QUEUE", "IN_PROGRESS"):
                decision = classify_queue_status({"request_id": "r1", "status": status},
                                                 request_id="r1", attempt=attempt)
                self.assertEqual(decision.action, "poll")
                self.assertLessEqual(decision.next_delay_seconds, 30)
        self.assertEqual(classify_queue_status(
            {"request_id": "r1", "status": "COMPLETED"}, request_id="r1", attempt=0
        ).action, "fetch_result")

    def test_timeout_unknown_status_and_poll_budget_fail_closed(self):
        for payload, attempt in (
            ({"request_id": "r1", "status": "FAILED"}, 0),
            ({"request_id": "r2", "status": "COMPLETED"}, 0),
            ({"request_id": "r1", "status": "IN_QUEUE"}, 12),
            ({}, 0),
        ):
            with self.assertRaises(QueueContractError):
                classify_queue_status(payload, request_id="r1", attempt=attempt)

    def test_restart_reuses_bound_id_without_resubmit(self):
        snapshot = {"request_id": "r1", "status": "IN_PROGRESS"}
        self.assertEqual(classify_queue_status(
            snapshot, request_id="r1", attempt=0
        ).action, "poll")
        self.assertEqual(classify_queue_status(
            snapshot, request_id="r1", attempt=1
        ).action, "poll")

    def test_unknown_submit_never_auto_retries(self):
        self.assertEqual(classify_submit_outcome(transport_succeeded=False),
                         "submission_unknown")
        self.assertEqual(classify_submit_outcome(transport_succeeded=True),
                         "submission_unknown")
        self.assertEqual(classify_submit_outcome(
            transport_succeeded=True, request_id="r1"), "bind_request")

    def test_rm5_cap_and_generation_count(self):
        self.assertTrue(authorize_offline_budget(cap_cents=500, reserved_cents=400,
                        candidate_cents=100, generation_count=0, max_generations=1))
        for args in (
            (501, 0, 1, 0, 1), (500, 400, 101, 0, 1),
            (500, 0, 100, 1, 1), (500, 500, 1, 0, 1),
            (500, -1, 1, 0, 1), (500, 0, 0, 0, 1),
        ):
            self.assertFalse(authorize_offline_budget(
                cap_cents=args[0], reserved_cents=args[1],
                candidate_cents=args[2], generation_count=args[3],
                max_generations=args[4]))


if __name__ == "__main__":
    unittest.main()
