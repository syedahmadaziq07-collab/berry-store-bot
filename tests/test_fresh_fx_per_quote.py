"""Fresh-FX-per-quotation integration: frozen quotes keep their snapshot,
new quotes get the latest fresh rate. No network (mocked provider)."""
import unittest
from decimal import Decimal
from uuid import uuid4

from ai_pricing_engine import FXRate, OperationalCosts
from ai_quotation_service import QuotationService
from ai_quote_store import InMemoryQuoteStore
from telegram_quote_flow import TelegramQuoteFlow

NOW = 1_730_000_000
TENANT = "11111111-1111-4111-8111-111111111111"


def pricing_doc(price=0.025):
    class R:
        status_code = 200
        def raise_for_status(self): pass
        def json(self):
            return {"prices": [{"endpoint_id": "minimax/h3-max-turbo/text-to-video",
                                "unit_price": price, "unit": "seconds",
                                "currency": "USD"}]}
    class C:
        def get(self, url, headers=None):
            return R()
    from fal_pricing import VerifiedFalPricing
    return VerifiedFalPricing("k", client=C())


class FreshFXPerQuoteTests(unittest.TestCase):
    def _flow(self, rates):
        calls = {"i": 0}

        def fx_provider():
            i = calls["i"]
            calls["i"] += 1
            return rates[min(i, len(rates) - 1)]

        svc = QuotationService("unit-signing-key-0123456789",
                               InMemoryQuoteStore(TENANT))
        return (TelegramQuoteFlow(svc, pricing_doc(), fx_provider=fx_provider,
                                  operational=OperationalCosts(
                                      payment_gateway_fee_fraction=Decimal("0.029"),
                                      fixed_operational_myr=Decimal("0.10"))),
                calls)

    def _rate(self, value, ts):
        return FXRate(myr_per_usd=Decimal(value), source="test-fx",
                      timestamp=ts, buffer_fraction=Decimal("0.02"))

    def test_each_quote_uses_latest_fx_and_freezes_it(self):
        flow, calls = self._flow([self._rate("4.40", NOW - 60),
                                  self._rate("4.60", NOW - 50)])
        a = flow.build_quote(tenant_id=TENANT, customer_id=900000088,
                             prompt="a", aspect_ratio="16:9",
                             idempotency_key=str(uuid4()), now=NOW)
        b = flow.build_quote(tenant_id=TENANT, customer_id=900000088,
                             prompt="b", aspect_ratio="16:9",
                             idempotency_key=str(uuid4()), now=NOW)
        self.assertEqual(calls["i"], 2)          # provider called per quote
        self.assertGreater(b["selling_cents"], a["selling_cents"])  # 4.60 > 4.40
        # Frozen snapshots differ per quote:
        self.assertNotEqual(a["_fx_timestamp"], b["_fx_timestamp"])

    def test_fx_provider_failure_fails_closed(self):
        def boom():
            raise RuntimeError("fx down")
        svc = QuotationService("unit-signing-key-0123456789",
                               InMemoryQuoteStore(TENANT))
        flow = TelegramQuoteFlow(svc, pricing_doc(), fx_provider=boom,
                                 operational=OperationalCosts(
                                     payment_gateway_fee_fraction=Decimal("0.029"),
                                     fixed_operational_myr=Decimal("0.10")))
        with self.assertRaises(Exception):
            flow.build_quote(tenant_id=TENANT, customer_id=900000088,
                             prompt="x", aspect_ratio="16:9",
                             idempotency_key=str(uuid4()))

    def test_none_fx_fails_closed(self):
        svc = QuotationService("unit-signing-key-0123456789",
                               InMemoryQuoteStore(TENANT))
        flow = TelegramQuoteFlow(svc, pricing_doc(), fx_provider=lambda: None,
                                 operational=OperationalCosts(
                                     payment_gateway_fee_fraction=Decimal("0.029"),
                                     fixed_operational_myr=Decimal("0.10")))
        with self.assertRaises(Exception):
            flow.build_quote(tenant_id=TENANT, customer_id=900000088,
                             prompt="x", aspect_ratio="16:9",
                             idempotency_key=str(uuid4()))


if __name__ == "__main__":
    unittest.main()
