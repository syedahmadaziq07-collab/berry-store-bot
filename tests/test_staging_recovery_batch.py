import unittest
from uuid import uuid4
from unittest.mock import Mock
from staging_job_worker import JobError
from staging_recovery_batch import recover_batch


class RecoveryBatchTests(unittest.TestCase):
    def test_disabled_does_not_read_or_send(self):
        worker=Mock(allow_external=False)
        with self.assertRaises(JobError): recover_batch(worker,[str(uuid4())])
        worker.poll.assert_not_called()

    def test_all_ids_validated_before_first_action(self):
        worker=Mock(allow_external=True)
        with self.assertRaises(JobError): recover_batch(worker,[str(uuid4()),'invalid'])
        worker.poll.assert_not_called()

    def test_failure_isolated_duplicates_removed_and_no_submission(self):
        first,second=str(uuid4()),str(uuid4())
        worker=Mock(allow_external=True)
        worker.poll.side_effect=[RuntimeError('secret-do-not-return'),{'state':'succeeded'}]
        worker.deliver.return_value={'state':'delivered'}
        result=recover_batch(worker,[first,second,second])
        self.assertEqual([r['result'] for r in result],['BLOCKED','PASS'])
        worker.deliver.assert_called_once_with(second)
        worker.submit.assert_not_called()
        worker.provider_failed.assert_not_called()
        self.assertNotIn('secret',str(result))

    def test_unknown_and_running_are_not_resent(self):
        worker=Mock(allow_external=True)
        worker.poll.side_effect=[{'state':'submission_unknown'},{'state':'queued'}]
        recover_batch(worker,[str(uuid4()),str(uuid4())])
        worker.deliver.assert_not_called()
        worker.submit.assert_not_called()

    def test_batch_limit(self):
        worker=Mock(allow_external=True)
        with self.assertRaises(JobError): recover_batch(worker,[str(uuid4()) for _ in range(21)])
        worker.poll.assert_not_called()
