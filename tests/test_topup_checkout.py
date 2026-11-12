import json
import unittest
from uuid import uuid4

import httpx

from topup_checkout import CheckoutUnavailable, create_topup_order

URL="https://cirsdvkfkvypprnmyykk.supabase.co"
TENANT=str(uuid4())


class CheckoutTests(unittest.TestCase):
    def call(self, client, **kwargs):
        args=dict(client=client,url=URL,service_key="fixture-secret",tenant_id=TENANT,
                  user_id=900000004,username="fixture",plan="starter",update_id=42)
        args.update(kwargs)
        return create_topup_order(**args)

    def test_stable_key_and_server_scoped_rpc(self):
        requests=[]
        def respond(r):
            requests.append(json.loads(r.content))
            self.assertEqual(r.url.path,"/rest/v1/rpc/berry_create_topup_order")
            self.assertEqual(r.headers['authorization'],'Bearer fixture-secret')
            return httpx.Response(200,json={"order":{"id":"BT"+"A"*24,"tenant_id":TENANT,
                 "user_id":900000004,"status":"pending"},"created":False})
        client=httpx.Client(transport=httpx.MockTransport(respond))
        self.call(client); self.call(client)
        self.assertEqual(requests[0]['p_key'],requests[1]['p_key'])
        self.assertNotEqual(requests[0]['p_proposed_id'],requests[1]['p_proposed_id'])
        self.assertEqual(requests[0]['p_tenant'],TENANT)
        self.assertEqual(requests[0]['p_user'],900000004)
        self.assertNotIn('amount',requests[0])

    def test_changed_update_and_user_get_different_keys(self):
        keys=[]
        def respond(r):
            body=json.loads(r.content);keys.append(body['p_key'])
            return httpx.Response(200,json={"order":{"id":"x","tenant_id":TENANT,
                 "user_id":body['p_user'],"status":"pending"},"created":True})
        client=httpx.Client(transport=httpx.MockTransport(respond))
        self.call(client);self.call(client,update_id=43);self.call(client,user_id=900000005)
        self.assertEqual(len(set(keys)),3)

    def test_ambiguous_http_is_not_retried_and_secret_is_not_reported(self):
        calls=[]
        def respond(r):
            calls.append(r)
            raise httpx.ReadTimeout('fixture-secret')
        with self.assertRaises(CheckoutUnavailable) as e:
            self.call(httpx.Client(transport=httpx.MockTransport(respond)))
        self.assertEqual(len(calls),1)
        self.assertNotIn('fixture-secret',str(e.exception))

    def test_wrong_identity_or_malformed_rpc_fails_closed(self):
        for result in ({},[],{"order":{},"created":True},
                       {"order":{"id":"x","tenant_id":TENANT,"user_id":1,"status":"pending"},"created":True}):
            with self.subTest(result=result),self.assertRaises(CheckoutUnavailable):
                self.call(httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=result))))

    def test_redirect_is_not_followed(self):
        calls=[]
        def respond(r):
            calls.append(r)
            return httpx.Response(302,headers={'location':'https://evil.test'})
        with self.assertRaises(CheckoutUnavailable):
            self.call(httpx.Client(transport=httpx.MockTransport(respond)))
        self.assertEqual(len(calls),1)

    def test_invalid_request_never_contacts_network(self):
        def respond(r):
            self.fail('Invalid checkout reached network')
        client=httpx.Client(transport=httpx.MockTransport(respond))
        for overrides in ({'plan':'unknown'},{'user_id':True},{'update_id':True},
                          {'url':'http://test.supabase.co'},{'service_key':''},{'username':'x'*201}):
            with self.subTest(overrides=overrides),self.assertRaises(CheckoutUnavailable):
                self.call(client,**overrides)


if __name__=='__main__':
    unittest.main()
