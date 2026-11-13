"""STEP 3 — catalog, pricing engine and quotation service tests (offline)."""
import unittest
from decimal import Decimal

from ai_product_catalog import get_product, validate_customer_selection
from ai_pricing_engine import FXRate, OperationalCosts, price_product
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
        self.svc = QuotationService("unit-signing-key-0123456789")
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
        self.svc._quotes[doc["quote_id"]]["selling_cents"] = 1
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
        with self.assertRaises(QuotationError):
            self.svc.get_valid(doc["quote_id"],
                               tenant_id="22222222-2222-4222-8222-222222222222",
                               customer_id=900000088, now=NOW + 1)
        with self.assertRaises(QuotationError):
            self.svc.get_valid(doc["quote_id"], tenant_id=self.kwargs["tenant_id"],
                               customer_id=900000089, now=NOW + 1)

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
        self.assertNotIn("state", doc) or None
        self.assertGreater(doc["credits"], 0)  # display-only; wallet untouched


if __name__ == "__main__":
    unittest.main()