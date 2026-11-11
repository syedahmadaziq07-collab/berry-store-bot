"""Execute actual handler code without importing/starting the Telegram bot."""
import ast
import logging
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, patch

SOURCE=Path(__file__).resolve().parents[1]/'bot.py'


class HandlerTests(IsolatedAsyncioTestCase):
    def setUp(self):
        tree=ast.parse(SOURCE.read_text())
        names={'checkout_ai_topup','_topup_plan_for_order'}
        nodes=[n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name in names]
        nodes.insert(0,ast.ImportFrom(module='__future__',names=[ast.alias(name='annotations')],level=0))
        async def run(label, operation, **kwargs):
            self.assertEqual(kwargs.get('attempts'),1)
            return operation()
        self.send=AsyncMock()
        self.ns={'Decimal':Decimal,'_topup_enabled':lambda:True,'BERRY_TOPUP_PLANS':{'starter':('Starter',5,6250)},
                 '_run_supabase':run,'_httpx':object(),'SUPABASE_URL':'https://fixture.supabase.co',
                 'SUPABASE_SERVICE_KEY':'fixture-only','TENANT_ID':'00000000-0000-4000-8000-000000000001',
                 'send_payment_page':self.send,'log':logging.getLogger('test')}
        exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),str(SOURCE),'exec'),self.ns)
        self.reply=AsyncMock()
        self.update=SimpleNamespace(update_id=42,effective_user=SimpleNamespace(id=7,username='fixture'),
            effective_chat=SimpleNamespace(id=7),callback_query=SimpleNamespace(message=SimpleNamespace(reply_text=self.reply)))
        self.context=SimpleNamespace()

    async def checkout(self,order,created=False):
        with patch('topup_checkout.create_topup_order',return_value=(order,created)) as client:
            await self.ns['checkout_ai_topup'](self.update,self.context,'starter')
            return client

    def order(self,status='pending',name='Berry Credits Top Up: starter'):
        return {'id':'BT'+'A'*24,'user_id':7,'product_name':name,'amount':5,'status':status}

    async def test_new_checkout_sends_shared_payment_page(self):
        client=await self.checkout(self.order(),True)
        self.send.assert_awaited_once()
        self.assertEqual(client.call_args.args[-1],42)

    async def test_existing_pending_topup_reuses_order(self):
        await self.checkout(self.order())
        self.send.assert_awaited_once()

    async def test_completed_callback_never_sends_qr_again(self):
        await self.checkout(self.order('completed'))
        self.send.assert_not_awaited()
        self.assertIn('ditutup',self.reply.call_args.args[0])

    async def test_receipt_waiting_approval_does_not_ask_for_another_payment(self):
        await self.checkout(self.order('waiting_approval'))
        self.send.assert_not_awaited()
        self.assertIn('Tak perlu bayar sekali lagi',self.reply.call_args.args[0])

    async def test_active_shop_order_does_not_open_topup_qr(self):
        await self.checkout(self.order(name='A shop item'))
        self.send.assert_not_awaited()
        self.assertIn('Browse Shop',self.reply.call_args.args[0])

    async def test_disabled_checkout_never_calls_rpc(self):
        self.ns['_topup_enabled']=lambda:False
        with patch('topup_checkout.create_topup_order') as client:
            await self.ns['checkout_ai_topup'](self.update,self.context,'starter')
        client.assert_not_called()
        self.send.assert_not_awaited()
