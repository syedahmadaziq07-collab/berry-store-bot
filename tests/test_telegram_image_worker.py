"""STEP 3 — MyrImageWorker lifecycle tests (mocked provider/delivery/store).

Covers: no-retry submission gate, polling, delivery claim-once, recovery,
duplicate workers, timeout, malformed responses, unknown holds.
No network, no wallet, no paid calls.
"""
import unittest
from unittest.mock import Mock
from uuid import uuid4

import httpx

from staging_job_worker import JobQuote
from telegram_image_worker import MyrImageWorker
from video_myr_worker import JobError

USER = 900000088
Q = JobQuote('image', 'fal-ai/flux/schnell', 1, 1325, 106, 6, 'fixture')
ARGS = {'prompt': 'kucing', 'aspect_ratio': '1:1', 'num_images': 1}
JOB = str(uuid4())


class Store:
    """In-memory mirror of the image job lifecycle contract."""

    def __init__(self):
        self.tenant_id = str(uuid4())
        self.lock = __import__('threading').RLock()
        self.jobs = {}
        self.provider_failures = 0

    def action(self, job_id, action, payload=None):
        payload = payload or {}
        with self.lock:
            claimed = False
            j = self.jobs.get(job_id)
            if action == 'reserve':
                if j is None:
                    self.jobs[job_id] = dict(payload, job_id=job_id,
                                             state='reserved')
                elif any(self.jobs[job_id][k] != v for k, v in payload.items()):
                    raise JobError('conflict')
            elif action == 'claim_submit' and j and j['state'] == 'reserved':
                j['state'] = 'submitting'
                claimed = True
            elif action == 'queued':
                j.update(payload, state='queued')
            elif action in ('submission_unknown', 'delivery_unknown'):
                j['state'] = action
            elif action == 'succeed':
                j.update(payload, state='succeeded')
            elif action == 'provider_failed':
                self.provider_failures += 1
                j.update(payload, state='provider_failed')
            elif action == 'claim_delivery' and j and j['state'] == 'succeeded':
                j['state'] = 'delivering'
                claimed = True
            elif action == 'delivered':
                j.update(payload, state='delivered')
            return dict(dict(j), claimed=claimed) if j else {'state': None}

    def recoverable(self, limit):
        return [{'job_id': k} for k, j in self.jobs.items()
                if j['state'] in ('reserved', 'queued', 'succeeded')][:limit]


def make_worker(**kw):
    store = Store()
    provider = Mock()
    provider.submit.return_value = {
        'request_id': 'fixture-req-1',
        'status_url': 'https://queue.fal.run/fal-ai/flux/requests/fixture-req-1/status',
        'response_url': 'https://queue.fal.run/fal-ai/flux/requests/fixture-req-1'}
    provider.status.return_value = {'request_id': 'fixture-req-1',
                                    'status': 'IN_QUEUE'}
    delivery = Mock()
    delivery.send.return_value = 555
    worker = MyrImageWorker(store, provider, delivery, allow_external=True,
                            budget_id=str(uuid4()))
    worker.reserve(JOB, USER, Q, ARGS)
    return worker, store, provider, delivery


class ImageWorkerTests(unittest.TestCase):
    def test_happy_path_reserve_submit_poll_deliver(self):
        w, s, p, d = make_worker()
        w.submit(JOB, ARGS)
        self.assertEqual(s.jobs[JOB]['state'], 'queued')
        p.status.return_value = {'request_id': 'fixture-req-1',
                                 'status': 'COMPLETED'}
        p.result.return_value = {'images': [{'url': 'https://fal.media/a.png'}]}
        w.poll(JOB)
        self.assertEqual(s.jobs[JOB]['state'], 'succeeded')
        w.deliver(JOB)
        self.assertEqual(s.jobs[JOB]['state'], 'delivered')
        d.send.assert_called_once_with(USER, 'image', 'https://fal.media/a.png')

    def test_timeout_is_unknown_and_never_retried(self):
        w, s, p, _ = make_worker()
        p.submit.side_effect = httpx.ReadTimeout('ambiguous')
        with self.assertRaises(JobError):
            w.submit(JOB, ARGS)
        self.assertEqual(s.jobs[JOB]['state'], 'submission_unknown')
        w.submit(JOB, ARGS)
        p.submit.assert_called_once()

    def test_duplicate_worker_submit_only_one_post(self):
        w, s, p, _ = make_worker()
        w2 = MyrImageWorker(s, p, Mock(), allow_external=True,
                            budget_id=str(uuid4()))
        w.submit(JOB, ARGS)
        w2.submit(JOB, ARGS)
        p.submit.assert_called_once()

    def test_malformed_response_holds_unknown(self):
        w, s, p, _ = make_worker()
        p.submit.return_value = {'no_request_id': True}
        with self.assertRaises(JobError):
            w.submit(JOB, ARGS)
        self.assertEqual(s.jobs[JOB]['state'], 'submission_unknown')

    def test_wrong_provider_status_request_held(self):
        w, s, p, _ = make_worker()
        w.submit(JOB, ARGS)
        p.status.return_value = {'request_id': 'other', 'status': 'COMPLETED'}
        with self.assertRaises(JobError):
            w.poll(JOB)
        self.assertEqual(s.jobs[JOB]['state'], 'queued')

    def test_nonterminal_error_held_no_refund(self):
        w, s, p, _ = make_worker()
        w.submit(JOB, ARGS)
        p.status.return_value = {'request_id': 'fixture-req-1',
                                 'status': 'IN_PROGRESS', 'error': 'x'}
        with self.assertRaises(JobError):
            w.poll(JOB)
        self.assertEqual(s.provider_failures, 0)

    def test_terminal_error_fails_once(self):
        w, s, p, _ = make_worker()
        w.submit(JOB, ARGS)
        p.status.return_value = {'request_id': 'fixture-req-1',
                                 'status': 'COMPLETED', 'error': 'x',
                                 'error_type': 'validation_error'}
        w.poll(JOB)
        self.assertEqual(s.jobs[JOB]['state'], 'provider_failed')
        self.assertEqual(s.provider_failures, 1)

    def test_wrong_image_count_held(self):
        w, s, p, _ = make_worker()
        w.submit(JOB, ARGS)
        p.status.return_value = {'request_id': 'fixture-req-1',
                                 'status': 'COMPLETED'}
        p.result.return_value = {'images': []}
        with self.assertRaises(JobError):
            w.poll(JOB)
        self.assertEqual(s.jobs[JOB]['state'], 'queued')

    def test_untrusted_result_url_never_accepted(self):
        w, s, p, _ = make_worker()
        w.submit(JOB, ARGS)
        p.status.return_value = {'request_id': 'fixture-req-1',
                                 'status': 'COMPLETED'}
        p.result.return_value = {'images': [{'url': 'https://evil.test/a.png'}]}
        with self.assertRaises(JobError):
            w.poll(JOB)
        self.assertEqual(s.jobs[JOB]['state'], 'queued')

    def test_delivery_timeout_held_no_duplicate_send(self):
        w, s, p, d = make_worker()
        w.submit(JOB, ARGS)
        p.status.return_value = {'request_id': 'fixture-req-1',
                                 'status': 'COMPLETED'}
        p.result.return_value = {'images': [{'url': 'https://fal.media/a.png'}]}
        w.poll(JOB)
        d.send.side_effect = httpx.ReadTimeout('telegram ambiguous')
        with self.assertRaises(JobError):
            w.deliver(JOB)
        self.assertEqual(s.jobs[JOB]['state'], 'delivery_unknown')
        d.send.assert_called_once()

    def test_recover_once_delivers_after_restart(self):
        w, s, p, d = make_worker()
        w.submit(JOB, ARGS)
        p.status.return_value = {'request_id': 'fixture-req-1',
                                 'status': 'COMPLETED'}
        p.result.return_value = {'images': [{'url': 'https://fal.media/a.png'}]}
        out = w.recover_once()
        self.assertEqual(out, [{'job_id': JOB, 'state': 'delivered'}])
        p.submit.assert_called_once()
        d.send.assert_called_once()

    def test_default_disabled(self):
        store, provider, delivery = Store(), Mock(), Mock()
        w = MyrImageWorker(store, provider, delivery)
        with self.assertRaises(JobError):
            w.submit(JOB, ARGS)
        with self.assertRaises(JobError):
            w.poll(JOB)
        with self.assertRaises(JobError):
            w.deliver(JOB)
        with self.assertRaises(JobError):
            w.recover_once()
        provider.submit.assert_not_called()
        delivery.send.assert_not_called()


if __name__ == '__main__':
    unittest.main()
