"""Verified fal pricing adapter tests. Mocked transport only; no real requests."""
import unittest
from decimal import Decimal

import httpx

from fal_pricing import PRICING_ORIGIN, PRICING_PATH, VerifiedFalPricing, PricingUnavailable

MODEL = "fal-ai/wan/v2.2-5b/text-to-video"


def doc(model=MODEL, price=0.025, unit="second", currency="USD"):
    return {"prices": [{"endpoint_id": model, "unit_price": price,
                        "unit": unit, "currency": currency}],
            "next_cursor": None, "has_more": False}


def client_with(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


class VerifiedPricingTests(unittest.TestCase):
    def test_exact_price_from_verified_document(self):
        calls = []

        def transport(request):
            calls.append(request)
            return httpx.Response(200, json=doc())

        c = client_with(transport)
        p = VerifiedFalPricing("fixture-key", client=c)
        price, unit = p.exact_price(MODEL)
        self.assertEqual((price, unit), (0.025, "second"))
        self.assertEqual(len(calls), 1)
        self.assertIn("api.fal.ai/v1/models/pricing", str(calls[0].url))
        self.assertIn("endpoint_id=" + MODEL.replace("/", "%2F"), str(calls[0].url))
        self.assertEqual(calls[0].headers["authorization"], "Key fixture-key")

    def test_missing_model_raises_never_guessed(self):
        c = client_with(lambda r: httpx.Response(200, json={"prices": [], "has_more": False}))
        p = VerifiedFalPricing("k", client=c)
        with self.assertRaises(PricingUnavailable):
            p.exact_price(MODEL)

    def test_invalid_shapes_never_become_prices(self):
        for body in ("not-json", {"prices": {}}, {"prices": [1]}, "list",
                     doc(price="0.025"), doc(price=None), doc(price=True),
                     doc(price=0), doc(price=-1), doc(currency="EUR"),
                     doc(unit="unknown_unit"), {}, None):
            with self.subTest(body=body):
                c = client_with(lambda r, b=body: (
                    httpx.Response(200, json=b) if isinstance(b, (dict, list)) or isinstance(b, str) and b != "not-json"
                    else httpx.Response(200, text=b)))
                p = VerifiedFalPricing("k", client=c)
                with self.assertRaises(PricingUnavailable):
                    p.exact_price(MODEL)

    def test_non_200_and_redirect_never_become_prices(self):
        for status in (500, 403, 404, 503):
            c = client_with(lambda r, s=status: httpx.Response(s, json={}))
            p = VerifiedFalPricing("k", client=c)
            with self.assertRaises(PricingUnavailable):
                p.exact_price(MODEL)
        c = client_with(lambda r: httpx.Response(307, headers={"Location": "https://evil.test"}))
        p = VerifiedFalPricing("k", client=c)
        with self.assertRaises(PricingUnavailable):
            p.exact_price(MODEL)

    def test_unauthenticated_probe_refuses(self):
        p = VerifiedFalPricing(None)
        with self.assertRaises(PricingUnavailable):
            p.exact_price(MODEL)
        p2 = VerifiedFalPricing("")
        self.assertFalse(p2.configured())

    def test_invalid_endpoint_identifier_rejected(self):
        p = VerifiedFalPricing("k")
        for bad in ("", "no-slash", "../evil", "a/b/../c", None, 5, "a//b"):
            with self.assertRaises(PricingUnavailable):
                p._model(bad)

    def test_url_contract_only_verified_pricing_endpoint(self):
        url = VerifiedFalPricing._url(MODEL)
        self.assertTrue(url.startswith(PRICING_ORIGIN + PRICING_PATH))
        from urllib.parse import urlparse
        parsed = urlparse(url)
        self.assertEqual((parsed.scheme, parsed.hostname, parsed.path),
                         ("https", "api.fal.ai", PRICING_PATH))

    def test_cost_bound_integer_cents_ceiling(self):
        # USD 0.025/sec * 10 sec * FX 4.7 = RM 1.175 -> 118 cents (ceiling)
        c = client_with(lambda r: httpx.Response(200, json=doc()))
        p = VerifiedFalPricing("k", client=c)
        self.assertEqual(p.cost_bound_myr_cents(MODEL, units=10, fx_rate=4.7), 118)
        # USD 0.03/req * 1 * 4.0 = RM 0.12 -> 12 cents
        c2 = client_with(lambda r: httpx.Response(200, json=doc(price=0.03, unit="request")))
        p2 = VerifiedFalPricing("k", client=c2)
        self.assertEqual(p2.cost_bound_myr_cents(MODEL, units=1, fx_rate=4.0), 12)

    def test_cost_bound_rejects_bad_units_and_fx(self):
        c = client_with(lambda r: httpx.Response(200, json=doc()))
        p = VerifiedFalPricing("k", client=c)
        for units in (0, -1, 1.0, True, "10", 10001):
            with self.assertRaises(PricingUnavailable):
                p.cost_bound_myr_cents(MODEL, units=units, fx_rate=4.7)
        for fx in (None, 0, -1, True, "4.7"):
            with self.assertRaises(PricingUnavailable):
                p.cost_bound_myr_cents(MODEL, units=10, fx_rate=fx)


    def test_verified_quote_credits_meets_rm1_margin(self):
        # USD 0.025/sec * 10 sec * 4.7 = RM1.175 (118 cents).
        # required_credits = ceil((1.175+1.00)/0.0008)=2719 -> aligned 2725.
        # debit = ceil(2725/1250*100)=218 cents (RM2.18); margin 2.18-1.175 >= RM1.
        c = client_with(lambda r: httpx.Response(200, json=doc()))
        p = VerifiedFalPricing("k", client=c)
        q = p.verified_quote_credits(MODEL, units=10, fx_rate=4.7)
        self.assertEqual(q["all_in_cost_cents"], 118)
        self.assertEqual(q["credits"] % 25, 0)
        self.assertEqual(q["debit_cents"], 218)
        # margin check: debit_myr - all_in >= 1.00
        from decimal import Decimal
        self.assertGreaterEqual(Decimal(q["debit_cents"]) / 100 - Decimal(q["all_in_cost_cents"]) / 100,
                                Decimal("1.00"))

    def test_verified_quote_requires_verified_costs(self):
        c = client_with(lambda r: httpx.Response(200, json=doc()))
        p = VerifiedFalPricing("k", client=c)
        with self.assertRaises(PricingUnavailable):
            p.verified_quote_credits(MODEL, units=10, fx_rate=4.7, confirmed_costs=False)


    def test_real_staging_units_megapixels_and_seconds(self):
        for unit, model in (("megapixels", "fal-ai/flux/schnell"),
                            ("seconds", "minimax/h3-max-turbo/text-to-video")):
            with self.subTest(unit=unit):
                payload = {"prices": [{"endpoint_id": model, "unit_price": 0.0175,
                                       "unit": unit, "currency": "USD"}]}
                c = client_with(lambda r, p=payload: httpx.Response(200, json=p))
                self.assertEqual(VerifiedFalPricing("k", client=c).exact_price(model),
                                 (0.0175, unit))

    def test_duplicate_and_malformed_rows_fail_closed(self):
        for rows in ([{"endpoint_id": MODEL, "unit_price": 0.025,
                       "unit": "seconds", "currency": "USD"}] * 2,
                     [None, {"endpoint_id": MODEL, "unit_price": 0.025,
                             "unit": "seconds", "currency": "USD"}]):
            with self.subTest(rows=rows):
                c = client_with(lambda r, p=rows: httpx.Response(200, json={"prices": p}))
                with self.assertRaises(PricingUnavailable):
                    VerifiedFalPricing("k", client=c).exact_price(MODEL)


if __name__ == "__main__":
    unittest.main()
