"""Zero-cost mock-only regression tests; NOT a substitute for AI worker integration tests."""
import json
import unittest
from unittest.mock import Mock

import httpx

from provider_readiness import (
    MODELS, STAGING_DATABASE, STAGING_SERVICE, minimum_video_sale_cents,
    pricing_probe, staging_startup_probe,
)


class Step2ProviderSafetyMocks(unittest.TestCase):
    def test_pricing_probe_never_submits_inference_or_follows_redirect(self):
        requests = []

        def responder(req):
            requests.append(req)
            return httpx.Response(307, headers={"Location": "https://queue.fal.run/paid"})

        with httpx.Client(transport=httpx.MockTransport(responder)) as client:
            result = pricing_probe("fixture-only", client)
        self.assertEqual(len(requests), len(MODELS))
        self.assertTrue(all(r.method == "GET" and r.url.host == "api.fal.ai"
                            and r.url.path == "/v1/models/pricing" for r in requests))
        self.assertTrue(all(r["status"] == "unverified" for r in result))
        self.assertNotIn("fixture-only", json.dumps(result))

    def test_timeout_has_no_retry_and_no_secret_leak(self):
        attempts = []

        def timeout(req):
            attempts.append(req)
            raise httpx.ReadTimeout("fixture-private")

        with httpx.Client(transport=httpx.MockTransport(timeout)) as client:
            result = pricing_probe("fixture-private", client)
        self.assertEqual(len(attempts), len(MODELS))
        self.assertTrue(all(r["error_kind"] == "timeout" for r in result))
        self.assertNotIn("fixture-private", json.dumps(result))

    def test_production_identity_never_opens_network(self):
        factory = Mock()
        staging_startup_probe({
            "RENDER_SERVICE_ID": "production",
            "AI_MAPPING_SUPABASE_URL": STAGING_DATABASE,
            "FAL_KEY": "fixture-only",
        }, factory, emit=lambda *_args, **_kwargs: None)
        factory.assert_not_called()

    def test_missing_billing_ceiling_fails_closed(self):
        for ceiling in (None, 0, -1, "NaN", "Infinity"):
            with self.subTest(ceiling=ceiling):
                with self.assertRaises(ValueError):
                    minimum_video_sale_cents(".0175", ceiling, "5", "0", "0")

    def test_pricing_metadata_not_a_verified_cost_cap(self):
        # A valid metadata response is only a unit-price read, not a quote.
        with httpx.Client(transport=httpx.MockTransport(
            lambda req: httpx.Response(200, json={"prices": [{
                "endpoint_id": req.url.params["endpoint_id"],
                "unit_price": ".0175", "unit": "seconds", "currency": "USD",
            }]})
        )) as client:
            rows = pricing_probe("fixture-only", client)
        self.assertTrue(all(r["status"] == "pricing_read_verified" for r in rows))
        # No inference entitlement or billed-duration maximum is returned.
        self.assertTrue(all("max_billable_seconds" not in r
                            and "inference_entitlement" not in r for r in rows))


if __name__ == "__main__":
    unittest.main()
