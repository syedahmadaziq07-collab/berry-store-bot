import copy
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
from uuid import uuid4
import httpx
from video_myr_worker import MyrVideoJobStore, MyrVideoWorker, JobError, JobQuote, request_hash

Q=JobQuote('video','fal-ai/wan/v2.2-5b/text-to-video',1,2500,200,100,'fixture costs, not live verification')
ARGS={'prompt':'controlled fixture','num_frames':81}
JOB=str(uuid4())
BUDGET=str(uuid4())

class Store:
    def __init__(self):
        self.tenant_id=str(uuid4())
        self.job=None
        self.lock=threading.Lock()
        self.claim_budget=None
    def action(self, job_id, action, payload=None):
        payload=payload or {}
        with self.lock:
            claimed=False
            if action=='reserve':
                self.job=dict(payload,job_id=job_id,state='reserved')
            elif action=='claim_submit' and self.job['state']=='reserved':
                self.job['state']='submitting'
                self.job['submission_tags']={'berry_job':job_id,'berry_hash':self.job['request_hash'],'berry_tenant':self.tenant_id}
                self.claim_budget=payload['budget_id']
                claimed=True
            elif action=='queued':
                if self.job['state'] != 'submitting': raise JobError('invalid queued transition')
                self.job.update(payload,state='queued')
            elif action == 'submission_unknown':
                if self.job['state'] not in ('submitting','submission_unknown'): raise JobError('invalid unknown transition')
                self.job['state']=action
            elif action == 'delivery_unknown': self.job['state']=action
            elif action=='succeed': self.job.update(payload,state='succeeded')
            elif action=='claim_delivery' and self.job['state']=='succeeded':
                self.job['state']='delivering'; claimed=True
            elif action=='delivered': self.job.update(payload,state='delivered')
            return dict(copy.deepcopy(self.job),claimed=claimed)

class VideoTests(unittest.TestCase):
    def setUp(self):
        self.store=Store(); self.provider=Mock(); self.delivery=Mock()
        self.provider.submit.return_value={'request_id':'fixture1',
            'status_url':'https://queue.fal.run/fal-ai/wan/requests/fixture1/status',
            'response_url':'https://queue.fal.run/fal-ai/wan/requests/fixture1'}
        self.delivery.send.return_value=123
        self.binding={request_hash(900000088,Q.payload(),ARGS):100}
        self.worker=self.make()
        self.worker.reserve(JOB,900000088,Q,ARGS)
    def make(self, **kwargs):
        options=dict(allow_external=True,budget_id=BUDGET,verified_costs=self.binding,verified_until=int(time.time())+300)
        options.update(kwargs)
        return MyrVideoWorker(self.store,self.provider,self.delivery,**options)
    def test_default_disabled(self):
        w=MyrVideoWorker(self.store,self.provider,self.delivery)
        with self.assertRaises(JobError): w.submit(JOB,ARGS)
        self.provider.submit.assert_not_called()
    def test_no_budget_or_unverified_cost_blocks_before_claim(self):
        for w in (self.make(budget_id=None),self.make(verified_costs={})):
            with self.assertRaises(JobError): w.submit(JOB,ARGS)
        self.assertEqual(self.store.job['state'],'reserved')
        self.provider.submit.assert_not_called()
    def test_concurrent_submits_only_one_post_with_budget(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _:self.make().submit(JOB,ARGS),range(8)))
        self.provider.submit.assert_called_once_with(Q.provider_model_id,ARGS,correlation=self.store.job["submission_tags"])
        self.assertEqual(self.store.claim_budget,BUDGET)
    def test_expired_or_unbounded_cost_proof_blocks(self):
        for expiry in (None, int(time.time())-1, int(time.time())+3600):
            with self.assertRaises(JobError):self.make(verified_until=expiry).submit(JOB,ARGS)
        self.provider.submit.assert_not_called()
    def test_parameter_change_fails_before_post(self):
        with self.assertRaises(JobError): self.worker.submit(JOB,dict(ARGS,num_frames=161))
        self.provider.submit.assert_not_called()
    def test_timeout_holds_without_retry(self):
        self.provider.submit.side_effect=httpx.ReadTimeout('fixture')
        with self.assertRaises(JobError):self.worker.submit(JOB,ARGS)
        self.worker.submit(JOB,ARGS)
        self.assertEqual(self.store.job['state'],'submission_unknown')
        self.provider.submit.assert_called_once()
    def test_resume_get_poll_and_delivery_once(self):
        self.worker.submit(JOB,ARGS)
        self.provider.status.return_value={'request_id':'fixture1','status':'COMPLETED'}
        self.provider.result.return_value={'video':{'url':'https://v3.fal.media/fixture.mp4'}}
        self.make().poll(JOB)
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda _:self.make().deliver(JOB),range(8)))
        self.provider.submit.assert_called_once()
        self.delivery.send.assert_called_once_with(900000088,'video','https://v3.fal.media/fixture.mp4')
        self.assertEqual(self.store.job['state'],'delivered')
    def test_delivery_timeout_not_resent(self):
        self.worker.submit(JOB,ARGS)
        self.worker.provider_succeeded(JOB,'fixture1','https://fal.media/fixture.mp4')
        self.delivery.send.side_effect=httpx.ReadTimeout('fixture')
        with self.assertRaises(JobError):self.worker.deliver(JOB)
        self.make().deliver(JOB)
        self.delivery.send.assert_called_once()
        self.assertEqual(self.store.job['state'],'delivery_unknown')
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

    def test_gate_malformed_response_holds_without_retry(self):
        self.provider.submit.return_value = {"no_request_id": True}
        with self.assertRaises(JobError):
            self.worker.submit(JOB, ARGS)
        self.provider.submit.assert_called_once()
        self.assertEqual(self.store.job["state"], "submission_unknown")
        # Restart: a second submit performs no POST (claim refused, job held).
        out = self.make().submit(JOB, ARGS)
        self.assertEqual(out["state"], "submission_unknown")
        self.provider.submit.assert_called_once()

    def test_gate_non_dict_response_holds_without_retry(self):
        self.provider.submit.return_value = "fixture-request-id"
        with self.assertRaises(JobError):
            self.worker.submit(JOB, ARGS)
        self.provider.submit.assert_called_once()
        self.assertEqual(self.store.job["state"], "submission_unknown")

    def test_gate_restart_after_unknown_never_posts_again(self):
        # Simulate crash after POST with response lost: state persisted as
        # submission_unknown. A restarted worker must never POST again.
        self.worker.submit(JOB, ARGS)
        self.assertEqual(self.store.job["state"], "queued")
        # Force unknown state as if the queued write was lost after the POST.
        self.store.job["state"] = "submission_unknown"
        out = self.make().submit(JOB, ARGS)
        self.assertEqual(out["state"], "submission_unknown")
        self.provider.submit.assert_called_once()

    def test_gate_correlation_tags_still_required_before_post(self):
        claim = self.store.action
        def action(job, op, payload=None):
            out = claim(job, op, payload)
            if op == "claim_submit":
                out["submission_tags"] = {"berry_job": str(uuid4())}
            return out
        self.store.action = action
        with self.assertRaises(JobError):
            self.worker.submit(JOB, ARGS)
        self.provider.submit.assert_not_called()

    def test_rpc_targets_real_wallet_lifecycle(self):
        seen=[]
        def handler(r):
            seen.append(str(r.url))
            return httpx.Response(200,json={'job_id':JOB,'state':'reserved'})
        client=httpx.Client(transport=httpx.MockTransport(handler))
        store=MyrVideoJobStore('https://cirsdvkfkvypprnmyykk.supabase.co','fixture-key',str(uuid4()),client)
        store.action(JOB,'get'); store.close()
        self.assertEqual(seen,['https://cirsdvkfkvypprnmyykk.supabase.co/rest/v1/rpc/berry_video_job'])

class RecoveryTests(unittest.TestCase):
    setUp = VideoTests.setUp
    make = VideoTests.make
    def test_recovery_resumes_queued_job_without_second_submission(self):
        self.worker.submit(JOB,ARGS)
        self.store.recoverable=Mock(return_value=[{'job_id':JOB},{'job_id':JOB}])
        self.provider.status.return_value={'request_id':'fixture1','status':'COMPLETED'}
        self.provider.result.return_value={'video':{'url':'https://fal.media/fixture.mp4'}}
        result=self.worker.recover_once()
        self.assertEqual(result,[{'job_id':JOB,'state':'delivered'}])
        self.provider.submit.assert_called_once()
        self.delivery.send.assert_called_once()
    def test_recovery_isolates_bad_row(self):
        self.store.recoverable=Mock(return_value=[{'job_id':'invalid'},{'job_id':JOB}])
        self.provider.status.return_value={'request_id':'fixture1','status':'IN_QUEUE'}
        result=self.worker.recover_once()
        self.assertEqual([r['state'] for r in result],['held','queued'])
    def test_loop_disabled_or_stopped_without_external_effects(self):
        event=threading.Event();event.set()
        self.worker.run_recovery(event)
        with self.assertRaises(JobError):self.make(allow_external=False).run_recovery(event)
        self.provider.submit.assert_not_called()
