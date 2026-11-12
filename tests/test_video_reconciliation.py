import copy
import hashlib
import unittest
from unittest.mock import Mock
from uuid import uuid4
import httpx
from fal_provider import FalProvider, FalProviderError
from video_reconciliation import UnknownOutcomeReconciler
from video_myr_worker import JobError

class ReconciliationTests(unittest.TestCase):
    def setUp(self):
        self.job_id,self.case_id,self.tenant=map(str,(uuid4(),uuid4(),uuid4()))
        self.tags={'berry_job':self.job_id,'berry_hash':'a'*64,'berry_tenant':self.tenant}
        self.job={'state':'submission_unknown','request_hash':'a'*64,'submission_tags':self.tags,
                  'quote':{'provider_model_id':'fal-ai/wan/v2.2-a14b/text-to-video'},'user_id':900000088}
        self.store=Mock(tenant_id=self.tenant);self.store.action.return_value=self.job
        self.provider=Mock();self.provider.status.return_value={'request_id':'fixture','status':'IN_QUEUE'}
        self.r=UnknownOutcomeReconciler(self.store,self.provider,allow_reads=True)
        self.receipt={'correlation_tags':self.tags,'provider_model_id':self.job['quote']['provider_model_id'],'provider_request_id':'fixture'}
        self.evidence={'operator_ref':'operator:fixture','evidence_ref':'fal-account-export:fixture','evidence_sha256':'b'*64}
    def test_default_disabled_no_provider_read(self):
        with self.assertRaises(JobError):UnknownOutcomeReconciler(self.store,self.provider).prepare_bind_request(self.job_id,self.case_id,self.receipt,**self.evidence)
        self.provider.status.assert_not_called()
    def test_bind_is_get_only_and_frozen_replay(self):
        case=self.r.prepare_bind_request(self.job_id,self.case_id,self.receipt,**self.evidence)
        self.r.apply(case);self.r.apply(copy.deepcopy(case))
        self.assertEqual(self.store.reconcile.call_args_list[0],self.store.reconcile.call_args_list[1])
        self.provider.status.assert_called_once_with('https://queue.fal.run/fal-ai/wan/requests/fixture/status')
        self.provider.submit.assert_not_called()
    def test_reject_unrelated_receipts_before_network(self):
        for field,value in [('correlation_tags',{}),('provider_model_id','fal-ai/other'),('provider_request_id','../evil')]:
            with self.subTest(field=field),self.assertRaises(JobError):
                self.r.prepare_bind_request(self.job_id,self.case_id,dict(self.receipt,**{field:value}),**self.evidence)
        self.provider.status.assert_not_called()
    def test_legacy_without_tags_stays_held(self):
        self.job['submission_tags']=None
        with self.assertRaises(JobError):self.r.prepare_bind_request(self.job_id,self.case_id,self.receipt,**self.evidence)
        self.provider.status.assert_not_called()
    def test_mismatched_status_cannot_apply(self):
        for status in ({'request_id':'other','status':'COMPLETED'},{'request_id':'fixture','status':'UNKNOWN'}):
            self.provider.status.return_value=status
            with self.assertRaises(JobError):self.r.prepare_bind_request(self.job_id,self.case_id,self.receipt,**self.evidence)
        self.store.reconcile.assert_not_called()
    def test_hold_has_no_external_effect(self):
        case=self.r.prepare_hold(self.job_id,self.case_id,reason_code='unverified',**self.evidence)
        self.r.apply(case);self.provider.status.assert_not_called();self.provider.submit.assert_not_called()
    def test_refund_and_resubmit_forbidden(self):
        for action in ('refund','resubmit','provider_failed','reserve'):
            with self.assertRaises(JobError):self.r.apply({'job_id':self.job_id,'case_id':self.case_id,'action':action,'evidence':{}})
        self.store.reconcile.assert_not_called()
    def test_delivery_requires_matching_receipt_no_send(self):
        self.job.update(state='delivery_unknown',result_url='https://fal.media/fixture.mp4')
        receipt={'recipient_id':900000088,'delivery_id':'123','result_sha256':hashlib.sha256(self.job['result_url'].encode()).hexdigest()}
        evidence=dict(self.evidence,evidence_ref='telegram-receipt:fixture')
        case=self.r.prepare_delivery(self.job_id,self.case_id,receipt,**evidence)
        self.assertEqual(case['action'],'confirm_delivery')
        for field,value in [('recipient_id',900000089),('delivery_id',True),('result_sha256','c'*64)]:
            with self.assertRaises(JobError):self.r.prepare_delivery(self.job_id,self.case_id,dict(receipt,**{field:value}),**evidence)
        self.job['result_url']=None
        with self.assertRaises(JobError):self.r.prepare_delivery(self.job_id,self.case_id,receipt,**evidence)
        self.provider.assert_not_called()
    def test_invalid_evidence_rejected(self):
        for field,value in [('reason_code',None),('operator_ref','bad\nlog'),('evidence_sha256','bad')]:
            kwargs=dict(self.evidence,reason_code='hold');kwargs[field]=value
            with self.assertRaises(JobError):self.r.prepare_hold(self.job_id,self.case_id,**kwargs)
    def test_correlation_header_contract_and_no_retry(self):
        requests=[]
        def transport(request):
            requests.append(request)
            raise httpx.ReadTimeout('fixture')
        p=FalProvider('fixture',httpx.Client(transport=httpx.MockTransport(transport)))
        with self.assertRaises(FalProviderError):p.submit('fal-ai/wan/v2.2-a14b/text-to-video',{'prompt':'fixture'},correlation=self.tags)
        self.assertEqual(len(requests),1)
        self.assertEqual(requests[0].headers['X-Fal-Tags'],','.join(k+'='+self.tags[k] for k in sorted(self.tags)))
        with self.assertRaises(FalProviderError):p.submit('fal-ai/wan',{},correlation=dict(self.tags,berry_job='bad\r\n'))
        self.assertEqual(len(requests),1)
