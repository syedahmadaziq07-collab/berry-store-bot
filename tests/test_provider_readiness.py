import json
import unittest
from unittest.mock import Mock
import httpx
from provider_readiness import *

class ReadinessTests(unittest.TestCase):
    def test_fixed_get_allowlist_no_secret_output(self):
        seen=[]
        def transport(req):
            seen.append(req)
            return httpx.Response(200,json={'prices':[{'endpoint_id':req.url.params['endpoint_id'],'unit_price':0.1,'unit':'image','currency':'USD','secret':'fixture-key'}]})
        result=pricing_probe('fixture-key',httpx.Client(transport=httpx.MockTransport(transport)))
        self.assertEqual(len(seen),2)
        self.assertTrue(all(r.method=='GET' and r.url.host=='api.fal.ai' and r.url.path=='/v1/models/pricing' for r in seen))
        self.assertNotIn('fixture-key',json.dumps(result))
        self.assertTrue(all(r['status']=='pricing_read_verified' for r in result))
    def test_errors_redirects_malformed_remain_unverified(self):
        for code,payload in [(401,{'secret':'fixture'}),(302,{}),(200,{'prices':[]}),(200,{'prices':'bad'})]:
            client=httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(code,json=payload,headers={'Location':'https://evil.test'})))
            result=pricing_probe('fixture-key',client)
            self.assertTrue(all(r['status']=='unverified' for r in result))
            self.assertNotIn('fixture',json.dumps(result))
    def test_never_runs_on_production_or_wrong_database(self):
        factory=Mock()
        for env in ({},{'RENDER_SERVICE_ID':'production','FAL_KEY':'fixture'}, {'RENDER_SERVICE_ID':STAGING_SERVICE,'SUPABASE_URL':'https://production.supabase.co'}):
            staging_startup_probe(env,factory)
        factory.assert_not_called()
    def test_profit_bound_rounds_up_to_even_cents(self):
        # Fixture bounds only, NOT actual provider pricing or FX.
        self.assertEqual(minimum_sale_cents('.1','5','.2','.05'),180)
        for bad in ('NaN','Infinity','-1','0'):
            with self.assertRaises(ValueError):minimum_sale_cents(bad,5,0,0)
        with self.assertRaises(ValueError):minimum_sale_cents(1,5,0,1)
