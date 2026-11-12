import os
import tempfile
import unittest
from step2_mock_persisted_worker import MockWorker, WorkerBlocked


class FakeProvider:
    def __init__(self):
        self.submissions = 0
        self.timeout = False
        self.current = "IN_QUEUE"

    def submit(self, job_id):
        self.submissions += 1
        if self.timeout:
            raise TimeoutError("ambiguous")
        return "fake-r1"

    def status(self, request_id):
        return {"request_id": request_id, "status": self.current}


class PersistedWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "jobs.sqlite")
        self.provider = FakeProvider()
        self.worker = MockWorker(self.path, self.provider)
        self.worker.configure_budget(500, 2)

    def tearDown(self):
        self.worker.close()
        self.tmp.cleanup()

    def test_atomic_budget_before_fake_submit_and_exhaustion(self):
        self.worker.create("a")
        self.worker.create("b")
        self.worker.claim("a", 400)
        with self.assertRaisesRegex(WorkerBlocked, "budget_exhausted"):
            self.worker.claim("b", 101)
        self.assertEqual(self.provider.submissions, 0)
        self.assertEqual(self.worker.state("b"), "reserved")
        self.worker.claim("b", 100)
        self.assertEqual(self.worker.submit_once("a"), "queued")
        self.assertEqual(self.provider.submissions, 1)

    def test_timeout_unknown_never_resubmits_even_after_restart(self):
        self.worker.create("a")
        self.worker.claim("a", 100)
        self.provider.timeout = True
        self.assertEqual(self.worker.submit_once("a"), "submission_unknown")
        self.worker.close()
        self.worker = MockWorker(self.path, self.provider)
        with self.assertRaises(WorkerBlocked):
            self.worker.submit_once("a")
        self.assertEqual(self.provider.submissions, 1)

    def test_restart_polling_uses_same_request(self):
        self.worker.create("a")
        self.worker.claim("a", 100)
        self.worker.submit_once("a")
        self.worker.close()
        self.worker = MockWorker(self.path, self.provider)
        self.assertEqual(self.worker.poll_once("a"), "queued")
        self.provider.current = "IN_PROGRESS"
        self.assertEqual(self.worker.poll_once("a"), "queued")
        self.provider.current = "COMPLETED"
        self.assertEqual(self.worker.poll_once("a"), "result_pending")
        self.assertEqual(self.provider.submissions, 1)

    def test_poll_timeout_or_unknown_status_requires_review(self):
        self.worker.create("a")
        self.worker.claim("a", 100)
        self.worker.submit_once("a")
        self.provider.current = "FAILED"
        self.assertEqual(self.worker.poll_once("a"), "needs_review")
        with self.assertRaises(WorkerBlocked):
            self.worker.poll_once("a")

    def test_poll_attempt_limit_and_duplicate_claim(self):
        self.worker.create("a")
        self.worker.claim("a", 100)
        with self.assertRaises(WorkerBlocked):
            self.worker.claim("a", 100)
        self.worker.submit_once("a")
        self.assertEqual(self.worker.poll_once("a", max_attempts=1), "queued")
        self.assertEqual(self.worker.poll_once("a", max_attempts=1), "needs_review")


if __name__ == "__main__":
    unittest.main()
