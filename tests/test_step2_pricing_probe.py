"""Read-only fal pricing probe tests. Mocked transport only; no network, no paid calls."""
import unittest

import httpx

from step2_pricing_probe import (FalPricingProbe, PricingProbeError,
                                 READ_ONLY_PRICING_ORIGINS)

MODEL = "minimax/h3-max-turbo/text-to-video"


def client_with(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


class PricingProbeTests(unittest.TestCase):
    def setUp(self):
        self.probe = FalPricingProbe(api_key="fixture-key")

    def test_valid_documented_price_extracted(self):
        doc = {"models": {MODEL: {"price": 0.025}}}
        c = client_with(lambda r: httpx.Response(200, json=doc))
        self.assertEqual(self.probe.exact_price(MODEL, client=c if c else None) if False else
                         FalPricingProbe("k", client=c).exact_price(MODEL), 0.025)

    def test_flat_mapping_document_accepted(self):
        doc = {MODEL: 0.03}
        c = client_with(lambda r: httpx.Response(200, json=doc))
        self.assertEqual(FalPricingProbe("k", client=c).exact_price(MODEL), 0.03)

    def test_invalid_json_never_becomes_a_price(self):
        c = client_with(lambda r: httpx.Response(200, text="not-json"))
        with self.assertRaises(PricingProbeError):
            FalPricingProbe("k", client=c).exact_price(MODEL)

    def test_non_200_never_becomes_a_price(self):
        c = client_with(lambda r: httpx.Response(503, json={}))
        with self.assertRaises(PricingProbeError):
            FalPricingProbe("k", client=c).exact_price(MODEL)

    def test_missing_model_and_nonnumeric_price_raise(self):
        for doc in ({"models": {}}, {"models": {MODEL: {"price": "0.025"}}},
                    {"models": {MODEL: None}}, {"models": {MODEL: True}},
                    {"models": []}, "list-not-dict"):
            c = client_with(lambda r, d=doc: httpx.Response(200, json=d))
            with self.assertRaises(PricingProbeError):
                FalPricingProbe("k", client=c).exact_price(MODEL)

    def test_redirect_is_rejected(self):
        c = client_with(lambda r: httpx.Response(
            307, headers={"Location": "https://evil.test/pricing"}))
        with self.assertRaises(PricingProbeError):
            FalPricingProbe("k", client=c).exact_price(MODEL)

    def test_unauthenticated_probe_refuses_to_read(self):
        with self.assertRaises(PricingProbeError):
            self.probe.exact_price(MODEL)

    def test_only_read_only_pricing_origins_allowed(self):
        for url in ("https://queue.fal.run/minimax/h3-max-turbo/text-to-video",
                    "https://fal.ai/api/inference",
                    "http://fal.ai/api/pricing",
                    "https://evil.test/pricing",
                    "https://fal.ai/api/pricing?x=1"):
            with self.assertRaises(PricingProbeError):
                self.probe._origin_allowed(url)
        self.assertEqual(self.probe._origin_allowed("https://fal.ai/api/pricing"),
                         "https://fal.ai/api/pricing")

    def test_invalid_model_identifier_rejected(self):
        for bad in ("", "no-slash", "../evil", "a/b/../../c", None, 5):
            with self.assertRaises(PricingProbeError):
                self.probe._model(bad)

    def test_unit_price_never_verifies_generation_bound(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(200, json={'models': {MODEL: {'price': 0.025}}})
        probe = FalPricingProbe('fixture-key', client=client_with(handler))
        for bound in (12, 200, 500, 999999):
            with self.assertRaisesRegex(PricingProbeError, 'maximum generation cost'):
                probe.verify_documented_cost_bound(MODEL, bound, fx_rate=4.7)
        self.assertEqual(calls, [])

    def test_cost_bound_requires_server_fx_rate(self):
        doc = {"models": {MODEL: {"price": 0.025}}}
        c = client_with(lambda r: httpx.Response(200, json=doc))
        probe = FalPricingProbe("k", client=c)
        for fx in (None, 0, -1, True, "4.7"):
            with self.assertRaises(PricingProbeError):
                probe.verify_documented_cost_bound(MODEL, 200, fx_rate=fx)
        for bound in (True, 12.0, "200"):
            with self.assertRaises(PricingProbeError):
                probe.verify_documented_cost_bound(MODEL, bound, fx_rate=4.7)


if __name__ == "__main__":
    unittest.main()