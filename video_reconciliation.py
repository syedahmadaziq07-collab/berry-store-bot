"""Audited operator-only ambiguity handling; no submit/refund/delivery operation exists here.

Provider account receipts must be independently reviewed, not copied from customer input.
Uncorrelated legacy jobs stay held. No absence-of-record -> refund assumption.
"""
import hashlib
import re
from datetime import datetime,timezone
from uuid import UUID
from video_myr_worker import JobError,queue_urls

class UnknownOutcomeReconciler:
    def __init__(self,store,provider,*,allow_reads=False):
        self.store,self.provider,self.allow_reads=store,provider,allow_reads is True

    def _evidence(self,job,operator_ref,evidence_ref,evidence_sha256,reason_code):
        if (not isinstance(operator_ref,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}',operator_ref)
            or not isinstance(evidence_sha256,str) or not re.fullmatch(r'[0-9a-f]{64}',evidence_sha256)
            or not isinstance(evidence_ref,str) or not re.fullmatch(r'(fal-account-export|telegram-receipt|operator-hold):[A-Za-z0-9_./-]{1,200}',evidence_ref)
            or not re.fullmatch(r'[a-z_]{1,64}',reason_code)):
            raise JobError('Reviewed operator evidence required')
        return {'operator_ref':operator_ref,'evidence_ref':evidence_ref,'evidence_sha256':evidence_sha256,
                'reason_code':reason_code,'expected_state':job['state'],'request_hash':job['request_hash'],
                'observed_at':datetime.now(timezone.utc).isoformat()}

    def prepare_hold(self,job_id,case_id,*,operator_ref,evidence_ref,evidence_sha256,reason_code):
        job=self.store.action(job_id,'get')
        evidence=self._evidence(job,operator_ref,evidence_ref,evidence_sha256,reason_code)
        return {'job_id':str(UUID(job_id)),'case_id':str(UUID(case_id)),'action':'hold','evidence':evidence}

    def prepare_bind_request(self,job_id,case_id,receipt,*,operator_ref,evidence_ref,evidence_sha256):
        if not self.allow_reads:raise JobError('Provider reconciliation reads disabled')
        job=self.store.action(job_id,'get')
        expected={'berry_job':str(UUID(job_id)),'berry_hash':job['request_hash'],'berry_tenant':self.store.tenant_id}
        if (job['state'] not in ('submitting','submission_unknown') or job.get('submission_tags')!=expected
            or not isinstance(receipt,dict) or receipt.get('correlation_tags')!=expected
            or receipt.get('provider_model_id')!=job['quote']['provider_model_id']):
            raise JobError('Authoritative correlated account receipt required; keep job held')
        ident=receipt.get('provider_request_id')
        model=job['quote']['provider_model_id'];root='https://queue.fal.run/'+'/'.join(model.split('/')[:2])+'/requests/'+str(ident)
        recovery=queue_urls(model,ident,root+'/status',root)
        evidence=self._evidence(job,operator_ref,evidence_ref,evidence_sha256,'correlated_provider_receipt')
        # GET confirms the candidate request exists. Account receipt establishes ownership;
        # status alone is insufficient to bind a different customer's request.
        status=self.provider.status(recovery['queue_status_url'])
        if status.get('request_id')!=ident or status.get('status') not in ('IN_QUEUE','IN_PROGRESS','COMPLETED'):
            raise JobError('Provider receipt status unverified; keep job held')
        evidence.update(provider_model_id=model,provider_request_id=ident,correlation_tags=expected)
        return {'job_id':str(UUID(job_id)),'case_id':str(UUID(case_id)),'action':'bind_request','evidence':evidence}

    def prepare_delivery(self,job_id,case_id,receipt,*,operator_ref,evidence_ref,evidence_sha256):
        job=self.store.action(job_id,'get')
        if (job['state'] not in ('delivering','delivery_unknown') or not isinstance(receipt,dict)
            or type(receipt.get('recipient_id')) is not int or receipt['recipient_id']!=job['user_id']
            or receipt.get('result_sha256')!=hashlib.sha256(job['result_url'].encode()).hexdigest()
            or not re.fullmatch(r'[0-9]{1,30}',str(receipt.get('delivery_id')))):
            raise JobError('Authoritative Telegram receipt required; keep delivery held')
        evidence=self._evidence(job,operator_ref,evidence_ref,evidence_sha256,'confirmed_telegram_receipt')
        evidence.update(recipient_id=receipt['recipient_id'],delivery_id=str(receipt['delivery_id']),result_sha256=receipt['result_sha256'])
        return {'job_id':str(UUID(job_id)),'case_id':str(UUID(case_id)),'action':'confirm_delivery','evidence':evidence}

    def apply(self,case):
        """Apply the SAME frozen case on retry/restart; never regenerate evidence timestamps."""
        if (not isinstance(case,dict) or set(case)!={'job_id','case_id','action','evidence'}
            or case['action'] not in ('hold','bind_request','confirm_delivery')):
            raise JobError('Invalid frozen reconciliation case')
        return self.store.reconcile(case['job_id'],case['case_id'],case['action'],case['evidence'])
