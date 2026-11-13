import unittest
import httpx
from fal_pricing_probe import fetch_pricing, minimum_retail_cents, PricingProbeError, SELECTED_MODEL

class PricingProbeTests(unittest.TestCase):
    def test_authenticated_get_only_and_correct_model(self):
        def handler(req):
            self.assertEqual(req.method, "GET")
            self.assertEqual(req.url.host, "api.fal.ai")
            self.assertEqual(req.url.path, "/v1/models/pricing")
            self.assertEqual(req.url.params["endpoint_id"], SELECTED_MODEL)
            self.assertEqual(req.headers["Authorization"], "Key dummy")
            return httpx.Response(200, json={"prices": []})
        client = httpx.Client(transport=httpx.MockTransport(handler))
        self.assertEqual(fetch_pricing(api_key="dummy", client=client), {"prices": []})

    def test_rejects_missing_key_and_other_models(self):
        with self.assertRaises(PricingProbeError):
            fetch_pricing(api_key="")
        with self.assertRaises(PricingProbeError):
            fetch_pricing(model="wan/v2.6/text-to-video", api_key="dummy")

    def test_redacts_http_failure(self):
        client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(401, text="secret-token")))
        with self.assertRaisesRegex(PricingProbeError, "lookup failed") as ctx:
            fetch_pricing(api_key="dummy", client=client)
        self.assertNotIn("secret-token", str(ctx.exception))

    def test_profit_floor_and_even_cents(self):
        self.assertEqual(minimum_retail_cents(all_in_cost_cents=115), 216)
        self.assertEqual(minimum_retail_cents(all_in_cost_cents=115, revenue_fee_bps=500), 228)
        for bad in (-1, 1.5, None):
            with self.assertRaises(ValueError):
                minimum_retail_cents(all_in_cost_cents=bad)

if __name__ == "__main__":
    unittest.main()
