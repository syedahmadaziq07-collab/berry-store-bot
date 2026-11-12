"""STEP 3 â€” AI Image consent flow tests (gaps I02/I03/I04).

No network, no wallet writes, no paid calls: deterministic mocks only.
Covers concurrent confirm, replay protection, cancel-before-confirm and
disabled-by-default wiring.
"""
import copy
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
from uuid import uuid4

from staging_job_worker import JobError, JobQuote
from telegram_image_flow import TelegramImageFlow, VerifiedImageOffer
from telegram_image_offer_builder import VerifiedImageOfferBuilder
from video_myr_worker import JobError as VideoJobError

JOBS = (JobError, VideoJobError)

USER = 900000088
CATALOG = [dict(model_id='fal-ai/flux/schnell', label='Berry Image FLUX',
                settings_label='FLUX Schnell', mapping_revision=1, credits=1325,
                debit_cents=106, all_in_cost_cents=6,
                cost_reference='fixture image cost')]


class TicketStore:
    """In-memory mirror of the berry_image_checkout contract."""

    def __init__(self):
        self.tenant_id = str(uuid4())
        self.lock = threading.RLock()
        self.tickets = {}
        self.prepares = 0
        self.confirms = 0

    def checkout(self, user, key, action, payload=None):
        payload = payload or {}
        with self.lock:
            if action == 'prepare':
                self.prepares += 1
                if key not in self.tickets:
                    self.tickets[key] = dict(ticket_id=key, user_id=user,
                                             state='pending', payload=payload, job=None)
                t = self.tickets[key]
                if t['user_id'] != user:
                    raise JobError('ticket owner mismatch')
                if t['payload'].get('request_hash') != payload.get('request_hash'):
                    raise JobError('ticket replay conflict')
                return copy.deepcopy(t)
            t = self.tickets[key]
            if t['user_id'] != user:
                raise JobError('ticket owner mismatch')
            if action == 'get':
                return copy.deepcopy(t)
            if action == 'confirm':
                self.confirms += 1
                if t['state'] == 'cancelled':
                    raise JobError('ticket cancelled')
                if t['payload'].get('expires_at', '') < time.strftime(
                        '%Y-%m-%dT%H:%M:%S', time.gmtime()):
                    raise JobError('quote expired')
                t['state'] = 'confirmed'
            elif action == 'cancel':
                t['state'] = 'cancelled'
            return copy.deepcopy(t)


class Worker:
    def __init__(self, store):
        self.store = store
        self.allow_external = False
        self.budget_id = None


def make_flow(store=None, **kwargs):
    store = store or TicketStore()
    worker = Worker(store)
    builder = VerifiedImageOfferBuilder(CATALOG)
    options = dict(test_user_id=USER, enabled=True)
    options.update(kwargs)
    return TelegramImageFlow(worker, builder, **options), store, worker


class ImageFlowTests(unittest.TestCase):
    def test_prepare_creates_pending_ticket_without_debit(self):
        flow, store, _ = make_flow()
        t = flow.prepare(USER, 42, 'kucing comel')
        self.assertEqual(t['state'], 'pending')
        self.assertEqual(t['payload']['quote']['tool_key'], 'image')
        self.assertEqual(t['payload']['arguments']['num_images'], 1)
        self.assertEqual(store.confirms, 0)

    def test_prepare_replay_same_payload_is_idempotent(self):
        flow, store, _ = make_flow()
        flow.prepare(USER, 42, 'kucing comel')
        flow.prepare(USER, 42, 'kucing comel')
        self.assertEqual(len(store.tickets), 1)
        self.assertEqual(store.prepares, 2)

    def test_prompt_and_parameter_validation(self):
        flow, _, _ = make_flow()
        for prompt in ('', '   ', 'x' * 1501, None, 5):
            with self.assertRaises(JOBS):
                flow.prepare(USER, 1, prompt)
        for aspect in ('21:9', 'evil', None, ''):
            with self.assertRaises(JOBS):
                flow.prepare(USER, 1, 'p', aspect=aspect)
        for count in (0, 5, -1, 1.0, True, '2'):
            with self.assertRaises(JOBS):
                flow.prepare(USER, 1, 'p', count=count)

    def test_count_scales_frozen_price_with_margin_floor(self):
        builder = VerifiedImageOfferBuilder(CATALOG)
        offer4 = builder.build('p', '1:1', 4)
        self.assertEqual(offer4.quote.payload()['debit_cents'], 106 * 4)
        self.assertEqual(offer4.quote.payload()['credits'], 1325 * 4)
        self.assertGreaterEqual(
            offer4.quote.payload()['debit_cents'] - offer4.quote.payload()['all_in_cost_cents'], 100)

    def test_offer_builder_rejects_bad_expiry_and_missing_aspect_support(self):
        builder = VerifiedImageOfferBuilder(CATALOG)
        for seconds in (0, -1, 901, 12.0, True):
            with self.assertRaises(JOBS):
                builder.build('p', '1:1', 1, expiry_seconds=seconds)
        narrow = [dict(CATALOG[0], allowed_aspects=('1:1',))]
        nb = VerifiedImageOfferBuilder(narrow)
        with self.assertRaises(JOBS):
            nb.build('p', '16:9', 1)
        bad = [dict(CATALOG[0], debit_cents=50)]
        with self.assertRaises(JOBS):
            VerifiedImageOfferBuilder(bad)

    def test_builder_constructor_rejects_bad_catalog(self):
        for catalog in (None, [], [{}], ['string'],
                        [dict(CATALOG[0], allowed_aspects=('nope',))]):
            with self.assertRaises(JOBS):
                VerifiedImageOfferBuilder(catalog)

    def test_disabled_or_wrong_identity_refused(self):
        flow, _, _ = make_flow(enabled=False)
        with self.assertRaises(JOBS):
            flow.prepare(USER, 1, 'p')
        flow2, _, _ = make_flow()
        with self.assertRaises(JOBS):
            flow2.prepare(111, 1, 'p')

    def test_confirm_requires_enabled_worker_and_budget_fail_closed(self):
        flow, store, worker = make_flow()
        t = flow.prepare(USER, 1, 'p')
        with self.assertRaises(JOBS):
            flow.confirm(USER, t['ticket_id'])
        worker.allow_external = True
        with self.assertRaises(JOBS):
            flow.confirm(USER, t['ticket_id'])
        worker.budget_id = str(uuid4())
        out = flow.confirm(USER, t['ticket_id'])
        self.assertEqual(out['state'], 'confirmed')

    def test_concurrent_confirm_transitions_once(self):
        flow, store, worker = make_flow()
        worker.allow_external = True
        worker.budget_id = str(uuid4())
        t = flow.prepare(USER, 1, 'p')
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _: flow.confirm(USER, t['ticket_id']), range(8)))
        self.assertEqual(store.confirms, 8)
        self.assertEqual(store.tickets[t['ticket_id']]['state'], 'confirmed')

    def test_cancel_then_confirm_never_charges(self):
        flow, store, worker = make_flow()
        worker.allow_external = True
        worker.budget_id = str(uuid4())
        t = flow.prepare(USER, 1, 'p')
        flow.cancel(USER, t['ticket_id'])
        with self.assertRaises(JOBS):
            flow.confirm(USER, t['ticket_id'])
        self.assertEqual(store.tickets[t['ticket_id']]['state'], 'cancelled')

    def test_owner_mismatch_rejected_before_confirm(self):
        flow, store, worker = make_flow()
        worker.allow_external = True
        worker.budget_id = str(uuid4())
        t = flow.prepare(USER, 1, 'p')
        with self.assertRaises(JOBS):
            flow.confirm(111, t['ticket_id'])
        self.assertEqual(store.tickets[t['ticket_id']]['state'], 'pending')

    def test_expired_quote_rejected_at_confirm(self):
        flow, store, worker = make_flow()
        worker.allow_external = True
        worker.budget_id = str(uuid4())
        t = flow.prepare(USER, 1, 'p')
        store.tickets[t['ticket_id']]['payload']['expires_at'] = '2000-01-01T00:00:00'
        with self.assertRaises(JOBS):
            flow.confirm(USER, t['ticket_id'])

    def test_non_image_quote_rejected(self):
        store = TicketStore()
        worker = Worker(store)
        video_q = JobQuote('video', 'fal-ai/wan/v2.2-5b/text-to-video',
                           1, 2500, 200, 100, 'x')
        builder = Mock(side_effect=lambda p, a, c: VerifiedImageOffer(
            'l', 's', video_q, {}, int(time.time()) + 300))
        flow = TelegramImageFlow(worker, builder, test_user_id=USER, enabled=True)
        with self.assertRaises(JOBS):
            flow.prepare(USER, 1, 'p')

    def test_constructor_requires_positive_int_identity(self):
        store = TicketStore()
        builder = VerifiedImageOfferBuilder(CATALOG)
        for uid in (0, -1, 'abc', None, 1.5):
            with self.assertRaises(JOBS):
                TelegramImageFlow(Worker(store), builder, test_user_id=uid)


if __name__ == '__main__':
    unittest.main()
