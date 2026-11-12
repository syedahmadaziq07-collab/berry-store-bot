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

    def test_contract_failures_are_distinct_and_redacted(self):
        valid = {'endpoint_id': MODELS[0], 'unit_price': .1, 'unit': 'image', 'currency': 'USD'}
        cases = [(None, 'envelope_not_object'), ({}, 'prices_missing'),
                 ({'prices': 'sensitive-fixture'}, 'prices_not_object_array'),
                 ({'prices': [None]}, 'prices_not_object_array'),
                 ({'prices': []}, 'endpoint_not_found'),
                 ({'prices': [valid, valid]}, 'endpoint_ambiguous')]
        for field, value, reason in [('unit_price', True, 'price_type_invalid'),
                                     ('unit_price', 'sensitive-fixture', 'price_value_invalid'),
                                     ('unit_price', 'NaN', 'price_value_invalid'),
                                     ('unit_price', -1, 'price_value_invalid'),
                                     ('currency', 'sensitive-fixture', 'currency_unsupported'),
                                     ('unit', 'sensitive-fixture', 'billing_unit_unsupported')]:
            cases.append(({'prices': [dict(valid, **{field: value})]}, reason))
        for payload, reason in cases:
            client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=json.dumps(payload), headers={'Content-Type': 'application/json'})))
            result = pricing_probe('fixture-key', client)[0]
            self.assertEqual(result['validation_error'], reason)
            self.assertEqual(result['status'], 'unverified')
            self.assertNotIn('sensitive-fixture', json.dumps(result))
            self.assertNotIn('fixture-key', json.dumps(result))

    def test_official_plural_billing_units_are_accepted_without_conversion(self):
        # Public fal.ai pricing uses plural labels (e.g. seconds and megapixels).
        # Keep the provider's exact unit; this is not a verified per-generation cap.
        for unit in ('seconds', 'megapixels', 'images', 'videos', 'requests'):
            row = {'endpoint_id': MODELS[0], 'unit_price': '0.025',
                   'unit': unit, 'currency': 'USD'}
            parsed = parse_pricing({'prices': [row]}, MODELS[0])
            self.assertEqual(parsed['status'], 'pricing_read_verified')
            self.assertEqual(parsed['unit'], unit)
            self.assertEqual(parsed['unit_price'], '0.025')
        with self.assertRaisesRegex(PricingContractError, 'billing_unit_unsupported'):
            parse_pricing({'prices': [{'endpoint_id': MODELS[0],
                'unit_price': 0.025, 'unit': 'unknown-unit', 'currency': 'USD'}]}, MODELS[0])

    def test_http_200_non_json_body_is_not_pricing(self):
        client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, text='<html>sensitive-fixture</html>')))
        result = pricing_probe('fixture-key', client)
        self.assertTrue(all(r['validation_error'] == 'body_not_json' for r in result))
        self.assertNotIn('sensitive-fixture', json.dumps(result))
