"""Offline tests for durable quote persistence. No live DB, provider or wallet."""
import json
import unittest
from decimal import Decimal
import httpx

from ai_quotation_service import QuotationService, QuotationError
from ai_pricing_engine import FXRate, OperationalCosts
from supabase_quote_store import SupabaseQuoteStore

NOW = 1700000000
TENANT = "11111111-1111-4111-8111-111111111111"


class FixturePricing:
    def exact_price(self, model):
        assert model == "minimax/h3-max-turbo/text-to-video"
        return 0.025, "seconds"


class InMemoryRest:
    def __init__(self):
        self.rows = {}
    def handler(self, request):
        method = request.method
        params = dict(request.url.params)
        if method == "POST":
            row = json.loads(request.content)
            if row["quote_id"] in self.rows or any(
                v["tenant_id"] == row["tenant_id"] and
                v["customer_id"] == row["customer_id"] and
                v["idempotency_key"] is not None and
                v["idempotency_key"] == row["idempotency_key"]
                for v in self.rows.values()):
                return httpx.Response(409, json={"code": "23505"})
            self.rows[row["quote_id"]] = row
            return httpx.Response(201, json=[row])
        found = [v for v in self.rows.values()
                 if all(str(v.get(k)) == val[3:] for k, val in params.items()
                        if val.startswith("eq.") and k != "integrity")]
        if method == "GET":
            return httpx.Response(200, json=[{"document": v["document"]} for v in found])
        if method == "PATCH":
            integrity = params["integrity"][3:]
            found = [v for v in found if v["state"] == "active"
                     and v["integrity"] == integrity]
            if not found:
                return httpx.Response(200, json=[])
            payload = json.loads(request.content)
            found[0].update(payload)
            return httpx.Response(200, json=[{"quote_id": found[0]["quote_id"]}])
        return httpx.Response(400)
    def store(self):
        client = httpx.Client(transport=httpx.MockTransport(self.handler))
        return SupabaseQuoteStore("https://gtqthdxltczovkiuoyyr.supabase.co",
                                  "fixture-service-key", client=client)


class DurableQuoteTests(unittest.TestCase):
    def setUp(self):
        self.db = InMemoryRest()
        self.kw = dict(tenant_id=TENANT, customer_id=123456, product_key="minimax_turbo_video",
                       aspect_ratio="16:9", prompt="a dog running", pricing=FixturePricing(),
                       fx_rate=FXRate(Decimal("4.7"), "test", NOW-30, Decimal("0.02")),
                       operational=OperationalCosts(Decimal("0.029"), Decimal("0.10")),
                       now=NOW, idempotency_key="tg:123")
    def svc(self):
        return QuotationService("unit-signing-secret-long-enough", store=self.db.store())

    def test_survives_process_restart_and_idempotency(self):
        one = self.svc().create(**self.kw)
        another = self.svc().create(**dict(self.kw, now=NOW+1))
        self.assertEqual(one["quote_id"], another["quote_id"])
        self.assertEqual(one["integrity"], another["integrity"])
        self.assertEqual(self.svc().get_valid(one["quote_id"], tenant_id=TENANT,
                                              customer_id=123456, now=NOW+2)["quote_id"],
                         one["quote_id"])

    def test_cancel_persists_and_does_not_resurrect(self):
        one = self.svc().create(**self.kw)
        self.svc().cancel(one["quote_id"], tenant_id=TENANT,
                          customer_id=123456, now=NOW+1)
        with self.assertRaises(QuotationError):
            self.svc().get_valid(one["quote_id"], tenant_id=TENANT,
                                 customer_id=123456, now=NOW+2)
        with self.assertRaises(QuotationError):
            self.svc().create(**dict(self.kw, now=NOW+2))

    def test_tenant_customer_separation(self):
        one = self.svc().create(**self.kw)
        for tenant, customer in ((TENANT, 222), ("22222222-2222-4222-8222-222222222222", 123456)):
            with self.assertRaises(QuotationError):
                self.svc().get_valid(one["quote_id"], tenant_id=tenant,
                                     customer_id=customer, now=NOW+1)

    def test_changed_prompt_cannot_reuse_key(self):
        self.svc().create(**self.kw)
        with self.assertRaises(QuotationError):
            self.svc().create(**dict(self.kw, prompt="changed", now=NOW+1))


if __name__ == "__main__":
    unittest.main()
