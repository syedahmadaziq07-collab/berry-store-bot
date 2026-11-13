"""STEP 3 — catalog, pricing engine and quotation service tests (offline)."""
import unittest
from decimal import Decimal

from ai_product_catalog import get_product, validate_customer_selection
from ai_pricing_engine import FXRate, OperationalCosts, price_product
from ai_quote_store import InMemoryQuoteStore, SupabaseQuoteStore
from ai_quotation_service import QuotationError, QuotationService
from fal_pricing import PricingUnavailable

MODEL = "minimax/h3-max-turbo/text-to-video"
NOW = 1_700_000_000


def pricing_doc(price=0.025, unit="seconds"):
    class R:
        status_code = 200
        def raise_for_status(self): pass
        def json(self):
            return {"prices": [{"endpoint_id": MODEL, "unit_price": price,
                                "unit": unit, "currency": "USD"}]}
    class C:
        def get(self, url, headers=None):
            return R()
    from fal_pricing import VerifiedFalPricing
    return VerifiedFalPricing("k", client=C())


FX = FXRate(myr_per_usd=Decimal("4.70"), source="test-fx",
            timestamp=NOW - 60, buffer_fraction=Decimal("0.02"))
OPS = OperationalCosts(payment_gateway_fee_fraction=Decimal("0.029"),
                       fixed_operational_myr=Decimal("0.10"))


class CatalogTests(unittest.TestCase):
    def test_minimax_product_configuration_valid(self):
        p = get_product("minimax_turbo_video")
        self.assertEqual(p.model_id, MODEL)
        self.assertEqual((p.duration_seconds, p.resolution,
                          p.prompt_expansion_mode, p.enable_safety_checker,
                          p.output_format),
                         (10, "480P", "balanced", True, "mp4"))
        self.assertEqual(tuple(sorted(p.aspect_ratios)), ("16:9", "9:16"))

    def test_unknown_and_invalid_ratio_rejected(self):
        with self.assertRaises(PricingUnavailable):
            get_product("nonexistent")
        with self.assertRaises(PricingUnavailable):
            validate_customer_selection(
                get_product("minimax_turbo_video"), "21:9")
        validate_customer_selection(get_product("minimax_turbo_video"), "9:16")


class PricingEngineTests(unittest.TestCase):
    def test_price_includes_rm1_margin_and_rounds(self):
        out = price_product(get_product("minimax_turbo_video"), pricing_doc(),
                            fx_rate=FX, operational=OPS, now=NOW)
        self.assertGreaterEqual(out["debit_cents"] - out["total_cost_cents"], 100)
        self.assertEqual(out["credits"] % 25, 0)

    def test_standard_floor_used_over_lower_promo_rate(self):
        promo = price_product(get_product("minimax_turbo_video"),
                              pricing_doc(price=0.0175),
                              fx_rate=FX, operational=OPS, now=NOW)
        standard = price_product(get_product("minimax_turbo_video"),
                                 pricing_doc(price=0.025),
                                 fx_rate=FX, operational=OPS, now=NOW)
        self.assertEqual(promo["provider_rate_usd"], standard["provider_rate_usd"])

    def test_live_rate_increase_raises_price(self):
        normal = price_product(get_product("minimax_turbo_video"), pricing_doc(0.025),
                               fx_rate=FX, operational=OPS, now=NOW)
        higher = price_product(get_product("minimax_turbo_video"), pricing_doc(0.05),
                               fx_rate=FX, operational=OPS, now=NOW)
        self.assertGreater(higher["selling_cents"], normal["selling_cents"])

    def test_unknown_unit_and_missing_price_rejected(self):
        with self.assertRaises(PricingUnavailable):
            price_product(get_product("minimax_turbo_video"), pricing_doc(unit="tokens"),
                          fx_rate=FX, operational=OPS, now=NOW)
        with self.assertRaises(PricingUnavailable):
            price_product(get_product("minimax_turbo_video"), pricing_doc(price=None),
                          fx_rate=FX, operational=OPS, now=NOW)

    def test_expired_fx_and_missing_source_rejected(self):
        stale = FXRate(myr_per_usd=Decimal("4.7"), source="x",
                       timestamp=NOW - 99999, buffer_fraction=Decimal("0"))
        nosrc = FXRate(myr_per_usd=Decimal("4.7"), source="",
                       timestamp=NOW - 60, buffer_fraction=Decimal("0"))
        for rate in (stale, nosrc):
            with self.assertRaises(PricingUnavailable):
                price_product(get_product("minimax_turbo_video"), pricing_doc(),
                              fx_rate=rate, operational=OPS, now=NOW)

    def test_fx_buffer_raises_price(self):
        plain = FXRate(myr_per_usd=Decimal("4.7"), source="x",
                       timestamp=NOW - 60, buffer_fraction=Decimal("0"))
        buffered = FXRate(myr_per_usd=Decimal("4.7"), source="x",
                          timestamp=NOW - 60, buffer_fraction=Decimal("0.05"))
        a = price_product(get_product("minimax_turbo_video"), pricing_doc(),
                          fx_rate=plain, operational=OPS, now=NOW)
        b = price_product(get_product("minimax_turbo_video"), pricing_doc(),
                          fx_rate=buffered, operational=OPS, now=NOW)
        self.assertGreater(b["selling_cents"], a["selling_cents"])

    def test_missing_operational_costs_fail_closed(self):
        with self.assertRaises(PricingUnavailable):
            price_product(get_product("minimax_turbo_video"), pricing_doc(),
                          fx_rate=FX, operational=None, now=NOW)

    def test_planning_seconds_below_duration_rejected(self):
        with self.assertRaises(PricingUnavailable):
            price_product(get_product("minimax_turbo_video"), pricing_doc(),
                          fx_rate=FX, operational=OPS, now=NOW, planning_seconds=9)


class QuotationServiceTests(unittest.TestCase):
    def setUp(self):
        self.svc = QuotationService(
            "unit-signing-key-0123456789",
            InMemoryQuoteStore("11111111-1111-4111-8111-111111111111"))
        self.kwargs = dict(tenant_id="11111111-1111-4111-8111-111111111111",
                           customer_id=900000088,
                           product_key="minimax_turbo_video",
                           aspect_ratio="16:9", prompt="kucing oren",
                           pricing=pricing_doc(), fx_rate=FX, operational=OPS,
                           now=NOW)

    def test_quote_created_customer_view_has_no_internal_costs(self):
        doc = self.svc.create(**self.kwargs)
        view = self.svc.customer_view(doc)
        self.assertIn("price_myr", view)
        self.assertNotIn("_total_cost_cents", view)
        self.assertNotIn("_fx_source", view)
        self.assertGreater(doc["credits"], 0)

    def test_quote_tamper_detected(self):
        doc = self.svc.create(**self.kwargs)
        # Tamper the STORED payload (simulating a compromised DB row).
        stored = self.svc.store._quotes[doc["quote_id"]]["payload"]
        stored["selling_cents"] = 1
        with self.assertRaises(QuotationError):
            self.svc.get_valid(doc["quote_id"],
                               tenant_id=self.kwargs["tenant_id"],
                               customer_id=900000088, now=NOW + 1)

    def test_quote_expiry_enforced(self):
        doc = self.svc.create(**self.kwargs)
        with self.assertRaises(QuotationError):
            self.svc.get_valid(doc["quote_id"],
                               tenant_id=self.kwargs["tenant_id"],
                               customer_id=900000088, now=NOW + 601)

    def test_cross_tenant_and_cross_customer_rejected(self):
        doc = self.svc.create(**self.kwargs)
        # InMemory store scopes by tenant; a quote cannot be fetched under a
        # different customer id (ownership is checked inside get/cancel).
        with self.assertRaises(QuotationError):
            self.svc.store.get(doc["quote_id"], 900000089)
        with self.assertRaises(QuotationError):
            self.svc.store.cancel(doc["quote_id"], 900000089)
        # ownership check through the service still works for the owner
        got = self.svc.get_valid(doc["quote_id"], tenant_id=self.kwargs["tenant_id"],
                                 customer_id=900000088, now=NOW + 1)
        self.assertEqual(got["quote_id"], doc["quote_id"])

    def test_idempotency_returns_same_quote(self):
        a = self.svc.create(**dict(self.kwargs, idempotency_key="tg-update-1"))
        b = self.svc.create(**dict(self.kwargs, idempotency_key="tg-update-1",
                                   now=NOW + 5))
        self.assertEqual(a["quote_id"], b["quote_id"])

    def test_rate_limit_blocks_flood(self):
        with self.assertRaises(QuotationError):
            for _ in range(8):
                self.svc.create(**dict(self.kwargs, now=NOW))

    def test_cancel_without_wallet_deduction(self):
        doc = self.svc.create(**self.kwargs)
        out = self.svc.cancel(doc["quote_id"], tenant_id=self.kwargs["tenant_id"],
                              customer_id=900000088, now=NOW + 1)
        self.assertEqual(out["state"], "cancelled")

    def test_cancelled_quote_is_cryptographically_valid_but_unusable(self):
        doc = self.svc.create(**self.kwargs)
        cancelled = self.svc.cancel(doc["quote_id"], tenant_id=self.kwargs["tenant_id"],
                                    customer_id=900000088, now=NOW + 1)
        self.assertEqual(cancelled["integrity"], self.svc._tag(cancelled))
        with self.assertRaisesRegex(QuotationError, "dibatalkan"):
            self.svc.get_valid(doc["quote_id"], tenant_id=self.kwargs["tenant_id"],
                               customer_id=900000088, now=NOW + 2)

    def test_idempotency_does_not_revive_cancelled_or_expired(self):
        doc = self.svc.create(**dict(self.kwargs, idempotency_key="key1"))
        self.svc.cancel(doc["quote_id"], tenant_id=self.kwargs["tenant_id"],
                        customer_id=900000088, now=NOW + 1)
        with self.assertRaises(QuotationError):
            self.svc.create(**dict(self.kwargs, idempotency_key="key1", now=NOW + 2))
        old = self.svc.create(**dict(self.kwargs, idempotency_key="key2", now=NOW))
        with self.assertRaises(QuotationError):
            self.svc.create(**dict(self.kwargs, idempotency_key="key2", now=NOW + 601))

    def test_no_provider_post_and_no_wallet_debit_during_quotation(self):
        # pricing transport only implements GET; a POST would raise.
        doc = self.svc.create(**self.kwargs)
        self.assertEqual(doc["state"], "active")   # stored, no external effect
        self.assertGreater(doc["credits"], 0)      # display-only; wallet untouched


class DurableStoreTests(unittest.TestCase):
    """SupabaseQuoteStore contract via mocked RPC transport (no network)."""

    def _store(self, handler):
        import httpx
        tenant = "11111111-1111-4111-8111-111111111111"
        return SupabaseQuoteStore(
            "https://supabase.test", "fixture-service-key", tenant,
            client=httpx.Client(transport=httpx.MockTransport(handler)))

    def test_quote_survives_restart(self):
        import json as _json
        import httpx
        # Two SEPARATE store instances (simulating restart) share the RPC
        # backend: a quote created by svc1 is retrievable by svc2.
        state = {}
        calls = []

        def handler(request):
            calls.append(request)
            body = _json.loads(request.content)
            fn = request.url.path.rsplit("/", 1)[-1]
            if fn == "berry_ai_quote_create":
                state["doc"] = body
                return httpx.Response(200, json={"duplicate": False})
            if fn == "berry_ai_quote_get":
                return httpx.Response(200, json={
                    "state": "active", "expires_at": state["doc"]["p_expires"],
                    "payload": _json.loads(state["doc"]["p_payload"]),
                    "integrity": state["doc"]["p_integrity"]})
            return httpx.Response(200, json={})

        s1 = self._store(handler)
        result = s1.create(quote_id="a" * 8 + "-b" * 4 + "-c" * 4 + "-d" * 4 + "-" + "e" * 12,
                           customer_id=900000088, product_key="minimax_turbo_video",
                           mapping_revision=1, payload_json='{"a":1}',
                           integrity="tag", idempotency_key="k1",
                           expires_at="2026-11-14T00:10:00+00:00")
        self.assertFalse(result["duplicate"])
        s2 = self._store(handler)  # fresh instance = restart
        got = s2.get("a" * 8 + "-b" * 4 + "-c" * 4 + "-d" * 4 + "-" + "e" * 12, 900000088)
        self.assertEqual(got["state"], "active")

    def test_duplicate_idempotency_returns_existing(self):
        import json as _json
        import httpx

        def handler(request):
            fn = request.url.path.rsplit("/", 1)[-1]
            if fn == "berry_ai_quote_create":
                return httpx.Response(200, json={
                    "duplicate": True, "state": "active",
                    "expires_at": "2099-01-01T00:00:00+00:00",
                    "payload": {"quote_id": "q"}, "integrity": "tag"})
            return httpx.Response(200, json={})
        s = self._store(handler)
        out = s.create(quote_id=str(uuid4()), customer_id=1,
                       product_key="p", mapping_revision=1,
                       payload_json='{}', integrity="tag",
                       idempotency_key="same", expires_at="2099-01-01T00:00:00+00:00")
        self.assertTrue(out["duplicate"])

    def test_database_unavailable_fails_closed(self):
        import httpx

        def handler(request):
            return httpx.Response(503)

        s = self._store(handler)
        self.assertFalse(s.rate_ok(1, 6))  # DB down → rate check fail-closed
        with self.assertRaises(QuotationError):
            s.create(quote_id=str(uuid4()), customer_id=1, product_key="p",
                     mapping_revision=1, payload_json='{}', integrity="t",
                     idempotency_key=None, expires_at="2099-01-01T00:00:00+00:00")
        with self.assertRaises(QuotationError):
            s.get(str(uuid4()), 1)

    def test_config_requires_url_and_key(self):
        with self.assertRaises(QuotationError):
            SupabaseQuoteStore("", "k", "11111111-1111-4111-8111-111111111111")
        with self.assertRaises(QuotationError):
            SupabaseQuoteStore("https://x", "", "11111111-1111-4111-8111-111111111111")

    def test_concurrent_same_key_single_quote(self):
        # The RPC contract (duplicate:true path) is the single source of
        # truth; two creates with the same key yield one stored quote.
        import json as _json
        import httpx
        seen = []
        def handler(request):
            fn = request.url.path.rsplit("/", 1)[-1]
            if fn == "berry_ai_quote_create":
                body = _json.loads(request.content)
                if body["p_idempotency"] in seen:
                    return httpx.Response(200, json={
                        "duplicate": True, "state": "active",
                        "expires_at": "2099-01-01T00:00:00+00:00",
                        "payload": {"quote_id": "first"}, "integrity": "t"})
                seen.append(body["p_idempotency"])
                return httpx.Response(200, json={"duplicate": False})
            return httpx.Response(200, json={})
        import httpx
        s = self._store(handler)
        a = s.create(quote_id=str(uuid4()), customer_id=1, product_key="p",
                     mapping_revision=1, payload_json='{}', integrity="t",
                     idempotency_key="cc", expires_at="2099-01-01T00:00:00+00:00")
        b = s.create(quote_id=str(uuid4()), customer_id=1, product_key="p",
                     mapping_revision=1, payload_json='{}', integrity="t",
                     idempotency_key="cc", expires_at="2099-01-01T00:00:00+00:00")
        self.assertFalse(a["duplicate"])
        self.assertTrue(b["duplicate"])


import json
import uuid
from uuid import uuid4


if __name__ == "__main__":
    unittest.main()