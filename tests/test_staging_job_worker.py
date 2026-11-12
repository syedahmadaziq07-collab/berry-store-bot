import copy
import hashlib
import json
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest.mock import Mock
from uuid import uuid4

import httpx

from staging_job_worker import (JobError, JobQuote, STAGING_ORIGIN, StagingJobStore,
    StagingJobWorker, request_hash, telegram_job_id, trusted_result_url, queue_urls)

QUOTE = JobQuote("image", "fal-ai/flux/schnell", 4, 1325, 106, 6, "fixture-cost-only")
ARGS = {"prompt": "synthetic fixture"}
JOB = str(uuid4())


class MemoryStore:
    """Worker protocol fixture. Database transitions tested separately on Supabase."""
    def __init__(self):
        self.lock = threading.Lock()
        self.job = None
    def action(self, job_id, action, payload=None):
        payload = payload or {}
        with self.lock:
            claimed = False
            if action == "reserve":
                if self.job is None:
                    self.job = dict(payload, job_id=job_id, state="reserved")
                elif any(self.job[k] != v for k, v in payload.items()):
                    raise JobError("conflict")
            elif action == "claim_submit" and self.job["state"] == "reserved":
                self.job["state"], claimed = "submitting", True
            elif action == "queued":
                if self.job["state"] != "submitting": raise JobError("invalid queued transition")
                self.job.update(state="queued", **payload)
            elif action in ("submission_unknown", "delivery_unknown"):
                self.job["state"] = action
            elif action == "succeed":
                self.job.update(state="succeeded", **payload)
            elif action == "claim_delivery" and self.job["state"] == "succeeded":
                self.job["state"], claimed = "delivering", True
            elif action == "delivered":
                self.job.update(state="delivered", **payload)
            return dict(copy.deepcopy(self.job), claimed=claimed)


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.store = MemoryStore()
        self.provider = Mock()
        self.provider.submit.return_value = {"request_id": "fixture-request-1",
            "status_url": "https://queue.fal.run/fal-ai/flux/requests/fixture-request-1/status",
            "response_url": "https://queue.fal.run/fal-ai/flux/requests/fixture-request-1"}
        self.delivery = Mock()
        self.delivery.send.return_value = 123
        self.worker = StagingJobWorker(self.store, self.provider, self.delivery, allow_external=True)
        self.worker.reserve(JOB, 900000003, QUOTE, ARGS)

    def test_external_actions_default_disabled(self):
        worker = StagingJobWorker(self.store, self.provider, self.delivery)
        with self.assertRaises(JobError):
            worker.submit(JOB, ARGS)
        with self.assertRaises(JobError):
            worker.deliver(JOB)
        self.provider.submit.assert_not_called()
        self.delivery.send.assert_not_called()

    def test_restart_and_concurrent_update_submit_only_once(self):
        workers = [StagingJobWorker(self.store, self.provider, self.delivery, allow_external=True) for _ in range(8)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda w: w.submit(JOB, ARGS), workers))
        self.provider.submit.assert_called_once_with(QUOTE.provider_model_id, ARGS)
        self.assertEqual(self.store.job["state"], "queued")

    def test_full_worker_flow_delivery_once_across_restart(self):
        self.worker.submit(JOB, ARGS)
        self.worker.provider_succeeded(JOB, "fixture-request-1", "https://v3.fal.media/files/fixture.png")
        workers = [StagingJobWorker(self.store, self.provider, self.delivery, allow_external=True) for _ in range(8)]
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda w: w.deliver(JOB), workers))
        self.delivery.send.assert_called_once_with(900000003, "image", "https://v3.fal.media/files/fixture.png")
        self.assertEqual(self.store.job["state"], "delivered")

    def test_timeout_is_not_retried_or_refunded(self):
        self.provider.submit.side_effect = httpx.ReadTimeout("ambiguous")
        with self.assertRaisesRegex(JobError, "unknown"):
            self.worker.submit(JOB, ARGS)
        self.assertEqual(self.store.job["state"], "submission_unknown")
        self.worker.submit(JOB, ARGS)
        self.provider.submit.assert_called_once()

    def test_failed_claim_never_posts(self):
        original = self.store.action
        def action(job, op, payload=None):
            if op == 'claim_submit': raise JobError('claim unavailable')
            return original(job, op, payload)
        self.store.action = action
        with self.assertRaises(JobError): self.worker.submit(JOB, ARGS)
        self.provider.submit.assert_not_called()
        self.assertEqual(self.store.job['state'], 'reserved')

    def test_invalid_claim_state_never_posts(self):
        original = self.store.action
        def action(job, op, payload=None):
            result = original(job, op, payload)
            if op == 'claim_submit': result['state'] = 'submission_unknown'
            return result
        self.store.action = action
        with self.assertRaises(JobError): self.worker.submit(JOB, ARGS)
        self.provider.submit.assert_not_called()

    def test_response_persistence_failure_still_blocks_resubmission(self):
        original = self.store.action
        def action(job, op, payload=None):
            if op in ("queued", "submission_unknown"):
                raise JobError("DB temporarily unavailable")
            return original(job, op, payload)
        self.store.action = action
        with self.assertRaises(JobError):
            self.worker.submit(JOB, ARGS)
        self.provider.submit.assert_called_once()
        self.assertEqual(self.store.job["state"], "submitting")
        self.worker.submit(JOB, ARGS)
        self.provider.submit.assert_called_once()

    def test_delivery_timeout_does_not_send_again(self):
        self.worker.submit(JOB, ARGS)
        self.worker.provider_succeeded(JOB, "fixture-request-1", "https://fal.media/fixture.png")
        self.delivery.send.side_effect = TimeoutError()
        with self.assertRaises(JobError):
            self.worker.deliver(JOB)
        self.worker.deliver(JOB)
        self.delivery.send.assert_called_once()
        self.assertEqual(self.store.job["state"], "delivery_unknown")

    def test_changed_arguments_cannot_consume_a_reservation(self):
        with self.assertRaises(JobError):
            self.worker.submit(JOB, {"prompt": "different"})
        self.provider.submit.assert_not_called()
        self.assertEqual(self.store.job["state"], "reserved")

    def test_changed_quote_replay_is_rejected(self):
        with self.assertRaises(JobError):
            self.worker.reserve(JOB, 900000003, replace(QUOTE, mapping_revision=5), ARGS)

    def test_untrusted_result_never_reaches_delivery(self):
        for url in ("http://fal.media/x", "https://fal.media.evil.test/x", "https://127.0.0.1/x",
                    "https://user@fal.media/x", "https://fal.media:443/x", "file:///tmp/x"):
            with self.subTest(url=url), self.assertRaises(JobError):
                self.worker.provider_succeeded(JOB, "fixture-request-1", url)
        self.delivery.send.assert_not_called()

    def test_restart_resumes_status_and_result_without_second_submit(self):
        self.worker.submit(JOB, ARGS)
        self.provider.status.return_value={"request_id":"fixture-request-1","status":"COMPLETED"}
        self.provider.result.return_value={"images":[{"url":"https://fal.media/fixture.png"}]}
        restarted=StagingJobWorker(self.store,self.provider,self.delivery,allow_external=True)
        self.assertEqual(restarted.poll(JOB)["state"],"succeeded")
        self.provider.submit.assert_called_once()
        self.provider.status.assert_called_once_with(self.store.job['queue_status_url'])
        self.provider.result.assert_called_once_with(self.store.job['queue_result_url'])

    def test_running_job_only_checks_status(self):
        self.worker.submit(JOB, ARGS)
        self.provider.status.return_value={"request_id":"fixture-request-1","status":"IN_PROGRESS"}
        self.assertEqual(self.worker.poll(JOB)["state"],"queued")
        self.provider.result.assert_not_called()
        self.provider.submit.assert_called_once()

    def test_poll_timeout_holds_debit_and_can_retry_get_only(self):
        self.worker.submit(JOB, ARGS)
        self.provider.status.side_effect=httpx.ReadTimeout('fixture')
        for _ in range(2):
            with self.assertRaises(JobError):
                self.worker.poll(JOB)
        self.assertEqual(self.store.job['state'],'queued')
        self.provider.submit.assert_called_once()

    def test_wrong_provider_status_request_is_not_attached_to_job(self):
        self.worker.submit(JOB, ARGS)
        self.provider.status.return_value={"request_id":"another-job","status":"COMPLETED"}
        with self.assertRaises(JobError):
            self.worker.poll(JOB)
        self.provider.result.assert_not_called()
        self.assertEqual(self.store.job['state'],'queued')

    def test_tampered_recovery_url_never_receives_api_key(self):
        self.worker.submit(JOB, ARGS)
        self.store.job['queue_status_url']='https://queue.fal.run/other/model/requests/fixture-request-1/status'
        with self.assertRaises(JobError):
            self.worker.poll(JOB)
        self.provider.status.assert_not_called()

    def test_malformed_or_extra_output_is_held_for_reconciliation(self):
        self.worker.submit(JOB, ARGS)
        self.provider.status.return_value={"request_id":"fixture-request-1","status":"COMPLETED"}
        for result in ({}, {"images":[]}, {"images":[{"url":"https://fal.media/one"},{"url":"https://fal.media/two"}]}):
            self.provider.result.return_value=result
            with self.assertRaises(JobError):
                self.worker.poll(JOB)
        self.assertEqual(self.store.job['state'],'queued')
        self.delivery.send.assert_not_called()

    def test_submit_url_mismatch_is_unknown_and_not_resubmitted(self):
        self.provider.submit.return_value['status_url']='https://evil.test/status'
        with self.assertRaises(JobError):
            self.worker.submit(JOB,ARGS)
        self.worker.submit(JOB,ARGS)
        self.provider.submit.assert_called_once()
        self.assertEqual(self.store.job['state'],'submission_unknown')


class QuoteAndStoreTests(unittest.TestCase):
    def test_queue_urls_use_root_app_for_nested_model_endpoint(self):
        response='https://queue.fal.run/fal-ai/wan/requests/fixture-id'
        r=queue_urls('fal-ai/wan/v2.2-a14b/text-to-video','fixture-id',response+'/status',response)
        self.assertEqual(r['queue_result_url'],response)
        with self.assertRaises(JobError):
            queue_urls('fal-ai/wan/v2.2-a14b/text-to-video','different-id',response+'/status',response)
    def test_quote_rejects_underpricing_fractional_cents_bool_and_unknown_costs(self):
        for q in (replace(QUOTE, debit_cents=105), replace(QUOTE, credits=4),
                  replace(QUOTE, all_in_cost_cents=7), replace(QUOTE, mapping_revision=True),
                  replace(QUOTE, cost_reference="")):
            with self.subTest(q=q), self.assertRaises(JobError):
                q.payload()

    def test_hash_canonical_and_no_raw_prompt_saved(self):
        h = request_hash(7, QUOTE.payload(), {"a": 1, "b": 2})
        self.assertEqual(h, request_hash(7, QUOTE.payload(), {"b": 2, "a": 1}))
        self.assertEqual(len(h), 64)
        with self.assertRaises(JobError):
            request_hash(7, QUOTE.payload(), {"bad": float("nan")})

    def test_telegram_update_identity_is_durable_and_tenant_scoped(self):
        tenant = str(uuid4())
        self.assertEqual(telegram_job_id(tenant, 42), telegram_job_id(tenant, 42))
        self.assertNotEqual(telegram_job_id(tenant, 42), telegram_job_id(str(uuid4()), 42))

    def test_store_refuses_production_and_other_hosts(self):
        for url in ("https://gtqthdxltczovkiuoyyr.supabase.co", "https://other.supabase.co", STAGING_ORIGIN+".evil.test"):
            with self.assertRaises(JobError):
                StagingJobStore(url, "fixture", str(uuid4()))

    def test_rpc_is_private_and_tenant_scoped(self):
        tenant = str(uuid4())
        def respond(r):
            self.assertEqual(r.url.host, "cirsdvkfkvypprnmyykk.supabase.co")
            body = json.loads(r.content)
            self.assertEqual(body["p_tenant"], tenant)
            self.assertEqual(r.headers["authorization"], "Bearer fixture-secret")
            return httpx.Response(200, json={"job_id": JOB, "state": "reserved"})
        client = httpx.Client(transport=httpx.MockTransport(respond))
        store = StagingJobStore(STAGING_ORIGIN, "fixture-secret", tenant, client=client)
        self.assertEqual(store.action(JOB, "get")["state"], "reserved")


if __name__ == "__main__":
    unittest.main()
