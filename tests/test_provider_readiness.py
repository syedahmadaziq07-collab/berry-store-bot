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
        self.assertEqual(len(seen),len(MODELS))
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

    def test_isolated_mapping_scopes_probe_without_business_database_access(self):
        factory=Mock();factory.return_value.__enter__=Mock(return_value=Mock())
        factory.return_value.__exit__=Mock(return_value=False)
        emit=Mock()
        staging_startup_probe({'RENDER_SERVICE_ID':STAGING_SERVICE,'AI_MAPPING_SUPABASE_URL':STAGING_DATABASE},factory,emit)
        factory.assert_not_called() # No key: no request even with verified mapping scope.
        self.assertIn('credential_unavailable',emit.call_args.args[0])
        staging_startup_probe({'RENDER_SERVICE_ID':'production','AI_MAPPING_SUPABASE_URL':STAGING_DATABASE,'FAL_KEY':'fixture'},factory,emit)
        factory.assert_not_called()

    def test_transport_diagnostics_do_not_leak_exception_or_key(self):
        for exc,kind in [(httpx.ReadTimeout('secret-fixture'),'timeout'),(httpx.LocalProtocolError('secret-fixture'),'local_request_rejected'),(httpx.ConnectError('secret-fixture'),'transport_error')]:
            client=Mock();client.get.side_effect=exc
            result=pricing_probe('secret-fixture',client)
            self.assertTrue(all(r['error_kind']==kind for r in result))
            self.assertNotIn('secret-fixture',json.dumps(result))

    def test_outer_credential_whitespace_normalized_inside_runtime(self):
        def transport(request):
            self.assertEqual(request.headers['Authorization'],'Key fixture-key')
            return httpx.Response(401)
        result=pricing_probe('  fixture-key\r\n',httpx.Client(transport=httpx.MockTransport(transport)))
        self.assertTrue(all(r['http_status']==401 for r in result))
        self.assertNotIn('fixture-key',json.dumps(result))
    def test_embedded_controls_rejected_before_network(self):
        for key in ('fixture\nkey','fixture key','fixture\tkey','',None,'é','a'*4097):
            client=Mock();result=pricing_probe(key,client)
            client.get.assert_not_called()
            self.assertTrue(all(r['error_kind']=='credential_format_invalid' for r in result))
