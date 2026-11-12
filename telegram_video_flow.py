"""Production bot consent/controller. No configuration or network action on import.

Installer requires an explicit controlled identity, verified server offer builder,
existing budget grant and deployment safety gates. No default activation exists.
"""
import asyncio
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID
from video_myr_worker import JobError, JobQuote, request_hash, telegram_job_id


@dataclass(frozen=True)
class VerifiedVideoOffer:
    label: str
    settings_label: str
    quote: JobQuote
    arguments: dict
    verified_until: int


class TelegramVideoFlow:
    def __init__(self, worker, offer_builder, *, test_user_id, enabled=False):
        if type(test_user_id) is not int or test_user_id<=0:
            raise JobError('Controlled test identity required')
        self.worker, self.offer_builder = worker, offer_builder
        self.test_user_id = test_user_id
        self.enabled = enabled is True

    def authorize(self, user_id, private=True):
        if not self.enabled or user_id != self.test_user_id or private is not True:
            raise JobError('AI Video belum diaktifkan untuk akaun ini')

    def _bind_cost(self, user_id, offer):
        if (not isinstance(offer, VerifiedVideoOffer) or type(offer.verified_until) is not int
                or not time.time()<offer.verified_until<=time.time()+900):
            raise JobError('Harga provider belum disahkan atau sudah luput')
        quote=offer.quote.payload()
        binding=request_hash(user_id,quote,offer.arguments)
        self.worker.verified_costs[binding]=quote['all_in_cost_cents']
        self.worker.verified_until=offer.verified_until
        return quote,binding

    def prepare(self, user_id, update_id, prompt, ratio='16:9'):
        self.authorize(user_id)
        if not isinstance(prompt,str) or not 1<=len(prompt.strip())<=1500 or ratio not in ('16:9','9:16'):
            raise JobError('Prompt atau tetapan tidak sah')
        # This builder is reviewed server configuration, never client JSON/mapping prices.
        offer=self.offer_builder(prompt.strip(),ratio)
        quote,binding=self._bind_cost(user_id,offer)
        balance=self.worker.store.balance(user_id)
        if balance*100 < quote['debit_cents']:
            raise JobError('Baki Berry Credits tidak mencukupi')
        ticket=telegram_job_id(self.worker.store.tenant_id,update_id)
        payload={'user_id':user_id,'quote':quote,'arguments':offer.arguments,'request_hash':binding,
                 'expires_at':datetime.fromtimestamp(offer.verified_until,timezone.utc).isoformat(),
                 'label':offer.label,'settings_label':offer.settings_label,'prompt':prompt.strip(),'ratio':ratio}
        result=self.worker.store.checkout(user_id,ticket,'prepare',payload)
        return dict(result,balance_myr=str(balance),balance_credits=int(balance*1250))

    def _refresh_exact_cost(self, user_id, payload):
        # Restart recovery can refresh costs only for the same frozen provider/settings/price.
        offer=self.offer_builder(payload['prompt'],payload['ratio'])
        quote,binding=self._bind_cost(user_id,offer)
        if (quote != payload['quote'] or offer.arguments != payload['arguments']
                or binding != payload['request_hash']):
            raise JobError('Harga atau model berubah; dapatkan quote baharu')

    def confirm(self, user_id, ticket_id):
        self.authorize(user_id)
        ticket_id=str(UUID(ticket_id))
        ticket=self.worker.store.checkout(user_id,ticket_id,'get')
        if ticket['state']=='pending':
            if not self.worker.allow_external or not self.worker.budget_id:
                raise JobError('Generation belum diaktifkan; tiada debit dibuat')
            self._refresh_exact_cost(user_id,ticket['payload'])
        result=self.worker.store.checkout(user_id,ticket_id,'confirm')
        job=result.get('job')
        if job and job['state']=='reserved':
            self._refresh_exact_cost(user_id,result['payload'])
            job=self.worker.submit(ticket_id,job['arguments'])
        if job and job['state']=='queued': job=self.worker.poll(ticket_id)
        if job and job['state']=='succeeded': job=self.worker.deliver(ticket_id)
        return dict(result,job=job)

    def cancel(self, user_id, ticket_id):
        self.authorize(user_id)
        return self.worker.store.checkout(user_id,str(UUID(ticket_id)),'cancel')

    def recover_once(self):
        self.authorize(self.test_user_id)
        # Resume only this controlled identity. Each reserved job is re-priced before submission.
        outcomes=[]
        for row in self.worker.store.recoverable(20):
            try:
                ticket=self.worker.store.checkout(self.test_user_id,row['job_id'],'get')
                if ticket['state']=='confirmed':
                    outcomes.append(self.confirm(self.test_user_id,row['job_id']))
            except Exception:
                outcomes.append({'state':'held'})
        return outcomes


async def start_video_recovery(application):
    flow=application.bot_data.get('berry_video_flow')
    if flow is None or not flow.enabled:
        return
    flow.authorize(flow.test_user_id)
    if not flow.worker.allow_external:
        return
    async def loop():
        while True:
            try:
                await asyncio.to_thread(flow.recover_once)
            except Exception:
                pass  # No raw HTTP exceptions/tokens; durable state is retained.
            await asyncio.sleep(15)
    application.bot_data['berry_video_recovery_task']=asyncio.create_task(loop())


async def stop_video_recovery(application):
    task=application.bot_data.pop('berry_video_recovery_task',None)
    if task:
        task.cancel()
        try: await task
        except asyncio.CancelledError: pass
