import asyncio
import copy
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from types import SimpleNamespace as NS
from unittest.mock import Mock,AsyncMock
from uuid import uuid4
from telegram_video_flow import TelegramVideoFlow,VerifiedVideoOffer,start_video_recovery,stop_video_recovery
from telegram_video_handlers import consent_callback,prepare_prompt,request_prompt
from video_myr_worker import JobError,JobQuote,MyrVideoWorker

USER=900000088
Q=JobQuote('video','fal-ai/wan/v2.2-5b/text-to-video',1,2500,200,100,'fixture, not live price evidence')

class Store:
    """Protocol fixture only; real MYR and consent SQL are tested separately in isolation."""
    def __init__(self):
        self.tenant_id=str(uuid4()); self.tickets={};self.jobs={}
        self.lock=threading.RLock();self.money=Decimal(5);self.debits=0;self.refunds=0;self.claims=0
    def balance(self,user):return self.money
    def recoverable(self,limit):return [{'job_id':k} for k,j in self.jobs.items() if j['state'] in ('reserved','queued','succeeded')][:limit]
    def action(self,key,action,payload=None):
        payload=payload or {}
        with self.lock:
            claimed=False
            if action=='reserve' and key not in self.jobs:
                if self.money<2:raise JobError('balance')
                self.money-=2;self.debits+=1
                self.jobs[key]=dict(payload,job_id=key,state='reserved')
            j=self.jobs[key]
            if action=='claim_submit' and j['state']=='reserved':
                j['state']='submitting';claimed=True;self.claims+=1
            elif action=='queued':j.update(payload,state='queued')
            elif action=='submission_unknown':j['state']='submission_unknown'
            elif action=='succeed':j.update(payload,state='succeeded')
            elif action=='claim_delivery' and j['state']=='succeeded':j['state']='delivering';claimed=True
            elif action=='delivered':j.update(payload,state='delivered')
            elif action=='delivery_unknown':j['state']='delivery_unknown'
            elif action in ('refund_before_submit','provider_failed'):
                if j['state']!='refunded':
                    if j['state'] not in ('reserved','queued'):raise JobError('unknown hold')
                    self.money+=2;self.refunds+=1;j['state']='refunded'
            return dict(copy.deepcopy(j),claimed=claimed)
    def checkout(self,user,key,action,payload=None):
        with self.lock:
            if action=='prepare' and key not in self.tickets:
                self.tickets[key]=dict(ticket_id=key,user_id=user,state='pending',payload=payload,job=None)
            t=self.tickets[key]
            if t['user_id']!=user:raise JobError('owner')
            if action=='confirm':
                if t['state']=='cancelled':raise JobError('cancelled')
                if t['state']=='pending':
                    t['job']=self.action(key,'reserve',t['payload']);t['state']='confirmed'
                else:t['job']=self.action(key,'get')
            elif action=='cancel':
                if t['state']=='confirmed':
                    j=self.action(key,'get')
                    if j['state']=='reserved':j=self.action(key,'refund_before_submit');t['state']='cancelled'
                    t['job']=j
                else:t['state']='cancelled'
            return copy.deepcopy(t)

class FlowTests(unittest.TestCase):
    def setUp(self):
        self.store=Store(); self.provider=Mock();self.delivery=Mock()
        self.provider.submit.return_value={'request_id':'fixture',
            'status_url':'https://queue.fal.run/fal-ai/wan/requests/fixture/status',
            'response_url':'https://queue.fal.run/fal-ai/wan/requests/fixture'}
        self.provider.status.return_value={'request_id':'fixture','status':'IN_QUEUE'}
        self.delivery.send.return_value=11
        self.worker=MyrVideoWorker(self.store,self.provider,self.delivery,allow_external=True,budget_id=str(uuid4()))
        self.builder=Mock(side_effect=lambda p,r:VerifiedVideoOffer('Fixture Video','fixture 5s 720p',Q,
            {'prompt':p,'aspect_ratio':r},int(time.time())+300))
        self.flow=TelegramVideoFlow(self.worker,self.builder,test_user_id=USER,enabled=True)
        self.ticket=self.flow.prepare(USER,123,'hello')['ticket_id']
    def test_odd_cent_balance_keeps_fractional_credits(self):
        self.store.money=Decimal('4.99')
        ticket=self.flow.prepare(USER,125,'precision')
        self.assertEqual(ticket['balance_credits'],'6,237.5')
    def test_prepare_never_debits_or_submits(self):
        self.assertEqual(self.store.money,5);self.assertEqual(self.store.debits,0)
        self.provider.submit.assert_not_called()
    def test_duplicate_confirm_debit_and_post_once(self):
        with ThreadPoolExecutor(max_workers=8) as p:list(p.map(lambda _:self.flow.confirm(USER,self.ticket),range(8)))
        self.assertEqual(self.store.debits,1);self.assertEqual(self.store.claims,1)
        self.provider.submit.assert_called_once()
    def test_cancel_then_confirm_never_charges(self):
        self.flow.cancel(USER,self.ticket)
        with self.assertRaises(JobError):self.flow.confirm(USER,self.ticket)
        self.assertEqual(self.store.debits,0)
        self.provider.submit.assert_not_called()
    def test_cancel_race_preserves_ledger(self):
        def call(action):
            try:getattr(self.flow,action)(USER,self.ticket)
            except JobError:pass
        with ThreadPoolExecutor(max_workers=2) as p:list(p.map(call,['confirm','cancel']))
        self.assertLessEqual(self.store.debits,1);self.assertLessEqual(self.store.refunds,1)
        self.assertEqual(self.store.money,Decimal(5)-2*self.store.debits+2*self.store.refunds)
        self.assertLessEqual(self.provider.submit.call_count,1)
    def test_wrong_user_and_disabled_flow_denied(self):
        with self.assertRaises(JobError):self.flow.confirm(USER+1,self.ticket)
        self.flow.enabled=False
        with self.assertRaises(JobError):self.flow.confirm(USER,self.ticket)
        self.assertEqual(self.store.debits,0)
    def test_changed_price_blocks_before_debit(self):
        self.builder.side_effect=lambda p,r:VerifiedVideoOffer('new','changed',
            JobQuote('video',Q.provider_model_id,2,3750,300,100,'changed'),{'prompt':p,'aspect_ratio':r},int(time.time())+300)
        with self.assertRaises(JobError):self.flow.confirm(USER,self.ticket)
        self.assertEqual(self.store.debits,0)
    def test_timeout_then_restart_no_resubmit_or_refund(self):
        self.provider.submit.side_effect=TimeoutError()
        with self.assertRaises(JobError):self.flow.confirm(USER,self.ticket)
        self.flow.recover_once()
        self.flow.confirm(USER,self.ticket)
        self.provider.submit.assert_called_once();self.assertEqual(self.store.refunds,0)
    def test_terminal_provider_error_refunds_once(self):
        self.provider.status.return_value={'request_id':'fixture','status':'COMPLETED','error':'fixture','error_type':'validation_error'}
        self.flow.confirm(USER,self.ticket);self.flow.confirm(USER,self.ticket)
        self.assertEqual(self.store.refunds,1);self.assertEqual(self.store.money,5)
        self.delivery.send.assert_not_called()
    def test_nonterminal_error_and_wrong_request_never_refund(self):
        for status in ({'request_id':'fixture','status':'IN_PROGRESS','error':'fixture'},
                       {'request_id':'wrong','status':'COMPLETED','error':'fixture'}):
            self.provider.status.return_value=status
            with self.assertRaises(JobError):self.flow.confirm(USER,self.ticket)
            self.assertEqual(self.store.refunds,0)
    def test_recovery_delivers_once_after_restart(self):
        self.flow.confirm(USER,self.ticket)
        self.provider.status.return_value={'request_id':'fixture','status':'COMPLETED'}
        self.provider.result.return_value={'video':{'url':'https://fal.media/fixture.mp4'}}
        self.flow.recover_once();self.flow.recover_once()
        self.provider.submit.assert_called_once();self.delivery.send.assert_called_once()
        self.assertEqual(self.store.jobs[self.ticket]['state'],'delivered')

class HandlerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.f=FlowTests();self.f.setUp()
        self.message=NS(reply_text=AsyncMock(),text='new prompt')
        self.update=NS(effective_user=NS(id=USER),effective_chat=NS(type='private'),
            update_id=124,message=self.message,callback_query=NS(message=self.message))
        self.context=NS(application=NS(bot_data={'berry_video_flow':self.f.flow}),user_data={})
    async def test_prompt_buttons_and_confirm_reach_real_controller(self):
        await request_prompt(self.update,self.context)
        self.assertTrue(await prepare_prompt(self.update,self.context,keyboard_factory=lambda rows:rows))
        markup=self.message.reply_text.call_args.kwargs['reply_markup']
        data=markup[0][0][1]
        self.assertTrue(data.startswith('ai_video_confirm:'))
        ident=data.split(':',1)[1]
        await consent_callback(self.update,self.context,'confirm',ident)
        await consent_callback(self.update,self.context,'confirm',ident)
        self.assertEqual(self.f.store.debits,1);self.f.provider.submit.assert_called_once()
    async def test_cancel_and_receipt_precedence(self):
        self.context.user_data['pending_receipt']='untouched-order'
        with self.assertRaises(JobError):await request_prompt(self.update,self.context)
        self.context.user_data['ai_video_flow']={'stage':'live_prompt','ratio':'16:9'}
        self.assertFalse(await prepare_prompt(self.update,self.context))
        self.assertEqual(self.context.user_data['pending_receipt'],'untouched-order')
        await consent_callback(self.update,self.context,'cancel',self.f.ticket)
        self.assertEqual(self.f.store.debits,0)
    async def test_group_callback_denied(self):
        self.update.effective_chat.type='group'
        with self.assertRaises(JobError):await consent_callback(self.update,self.context,'confirm',self.f.ticket)
        self.assertEqual(self.f.store.debits,0)
    async def test_recovery_hooks_disabled_by_default(self):
        app=NS(bot_data={})
        await start_video_recovery(app);await stop_video_recovery(app)
        self.assertNotIn('berry_video_recovery_task',app.bot_data)
