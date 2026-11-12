"""STEP 3 — AI Image consent flow tests (gaps I02/I04).

No network, no wallet writes, no paid calls: deterministic mocks only.
"""
import unittest
from unittest.mock import Mock
from uuid import uuid4

from staging_job_worker import JobQuote
from telegram_image_flow import TelegramImageFlow, VerifiedImageOffer
from video_myr_worker import JobError

USER = 900000088
Q = JobQuote('image', 'fal-ai/flux/schnell', 4, 1325, 106, 6, 'fixture image cost')


class Worker:
    def __init__(self):
        self.store = Mock(tenant_id=str(uuid4()))
        self.allow_external = False
        self.budget_id = None


def make_flow(**kwargs):
    worker = Worker()
    builder = Mock(side_effect=lambda p, a, c: VerifiedImageOffer(
        'Fixture Image', f'fixture {a} x{c}', Q,
        {'prompt': p, 'aspect_ratio': a, 'num_images': c}, 4102444800))
    options = dict(test_user_id=USER, enabled=True)
    options.update(kwargs)
    return TelegramImageFlow(worker, builder, **options), worker, builder


class ImageFlowTests(unittest.TestCase):
    def test_prepare_returns_frozen_ticket_without_debit_or_submit(self):
        flow, worker, builder = make_flow()
        t = flow.prepare(USER, 42, 'kucing comel')
        self.assertTrue(t['ticket_id'])
        self.assertEqual(t['quote']['tool_key'], 'image')
        self.assertEqual(len(t['request_hash']), 64)
        self.assertEqual(t['arguments'],
                         {'prompt': 'kucing comel', 'aspect_ratio': '1:1', 'num_images': 1})

    def test_prompt_validation_rejects_empty_and_oversize(self):
        flow, _, _ = make_flow()
        for prompt in ('', '   ', 'x' * 1501, None, 5):
            with self.assertRaises(JobError):
                flow.prepare(USER, 1, prompt)

    def test_aspect_and_count_bounds(self):
        flow, _, _ = make_flow()
        for aspect in ('21:9', 'evil', None, ''):
            with self.assertRaises(JobError):
                flow.prepare(USER, 1, 'p', aspect=aspect)
        for count in (0, 5, -1, 1.0, True, '2'):
            with self.assertRaises(JobError):
                flow.prepare(USER, 1, 'p', count=count)
        t = flow.prepare(USER, 1, 'p', aspect='16:9', count=4)
        self.assertEqual(t['arguments']['num_images'], 4)

    def test_disabled_or_wrong_identity_refused(self):
        flow, _, _ = make_flow(enabled=False)
        with self.assertRaises(JobError):
            flow.prepare(USER, 1, 'p')
        flow2, _, _ = make_flow()
        with self.assertRaises(JobError):
            flow2.prepare(111, 1, 'p')

    def test_confirm_requires_enabled_worker_and_budget(self):
        flow, worker, _ = make_flow()
        with self.assertRaises(JobError):
            flow.confirm(USER, 't')
        worker.allow_external = True
        with self.assertRaises(JobError):
            flow.confirm(USER, 't')
        worker.budget_id = str(uuid4())
        out = flow.confirm(USER, 't')
        self.assertEqual(out['state'], 'confirmed_stub')

    def test_invalid_offer_builder_output_rejected(self):
        worker = Worker()
        builder = Mock(return_value={'not': 'an offer'})
        flow = TelegramImageFlow(worker, builder, test_user_id=USER, enabled=True)
        with self.assertRaises(JobError):
            flow.prepare(USER, 1, 'p')

    def test_non_image_quote_rejected(self):
        worker = Worker()
        video_q = JobQuote('video', 'fal-ai/wan/v2.2-5b/text-to-video', 1, 2500, 200, 100, 'x')
        builder = Mock(side_effect=lambda p, a, c: VerifiedImageOffer(
            'l', 's', video_q, {}, 4102444800))
        flow = TelegramImageFlow(worker, builder, test_user_id=USER, enabled=True)
        with self.assertRaises(JobError):
            flow.prepare(USER, 1, 'p')

    def test_constructor_requires_positive_int_identity(self):
        _, _, builder = make_flow()
        for uid in (0, -1, 'abc', None, 1.5):
            with self.assertRaises(JobError):
                TelegramImageFlow(Worker(), builder, test_user_id=uid)


if __name__ == '__main__':
    unittest.main()
