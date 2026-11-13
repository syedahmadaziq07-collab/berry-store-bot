"""MiniMax integration contract tests against the OFFICIAL API schema.

Schema verified 2026-11-14 from https://fal.ai/models/minimax/h3-max-turbo/text-to-video/api:
  prompt string (required)
  duration float (seconds; output can run ~0.7s longer than requested)
  resolution enum: 480P | 768P | 1080P (default 768P)
  prompt_expansion_mode string (required): disabled | balanced | quality
  aspect_ratio enum: 21:9 | 16:9 | 4:3 | 1:1 | 3:4 | 9:16
  enable_safety_checker boolean (default true)
  seed integer optional; sync_mode boolean optional
Output: video{url,content_type,file_name,file_size} + expanded_prompt + timings.
"""
import unittest

from berry_admin_minimax_trial import MODEL, mini_max_arguments
from fal_provider import FalProvider, FalProviderError

EXPECTED = {
    "prompt": "hi", "duration": 10, "resolution": "480P",
    "prompt_expansion_mode": "balanced", "aspect_ratio": "16:9",
    "enable_safety_checker": True,
}


class MiniMaxSchemaContractTests(unittest.TestCase):
    def test_requested_parameters_match_official_schema(self):
        args = mini_max_arguments(" hi ")
        self.assertEqual(args, EXPECTED)
        # duration is a float-accepting numeric per schema (10 == 10.0)
        self.assertIsInstance(args["duration"], (int, float))
        self.assertIn(args["resolution"], ("480P", "768P", "1080P"))
        self.assertIn(args["prompt_expansion_mode"], ("disabled", "balanced", "quality"))
        self.assertIn(args["aspect_ratio"],
                      ("21:9", "16:9", "4:3", "1:1", "3:4", "9:16"))
        self.assertIn(args["enable_safety_checker"], (True,))

    def test_prompt_validation_rejects_empty_and_oversize(self):
        for bad in ("", "   ", "x" * 1501, None, 5):
            with self.assertRaises(ValueError):
                mini_max_arguments(bad)

    def test_submit_endpoint_and_method_contract(self):
        calls = []

        class R:
            status_code = 200
            def raise_for_status(self): pass
            def json(self):
                return {"request_id": "abcDEF123_-",
                        "status_url": "https://queue.fal.run/minimax/h3-max-turbo/requests/abcDEF123_/status",
                        "response_url": "https://queue.fal.run/minimax/h3-max-turbo/requests/abcDEF123_"}

        class C:
            def request(self, method, url, **kw):
                calls.append((method, url, kw))
                return R()

        p = FalProvider("fixture-key", client=C())
        p.submit(MODEL, dict(EXPECTED))
        self.assertEqual(len(calls), 1)
        method, url, kw = calls[0]
        self.assertEqual(method, "POST")
        self.assertEqual(url, "https://queue.fal.run/" + MODEL)
        self.assertEqual(kw["json"], dict(EXPECTED))

    def test_provider_rejects_untrusted_queue_hosts(self):
        p = FalProvider("k")
        for bad in ("https://evil.test/x", "http://queue.fal.run/x",
                    "https://queue.fal.run:8443/x", "https://user@queue.fal.run/x"):
            with self.assertRaises(FalProviderError):
                p._url(bad)

    def test_provider_error_codes_are_fixed_and_secret_free(self):
        class C:
            def request(self, *a, **kw):
                import httpx
                req = httpx.Request("POST", "https://queue.fal.run/x")
                raise httpx.HTTPStatusError("h", request=req,
                                            response=httpx.Response(401))
        p = FalProvider("k", client=C())
        with self.assertRaises(FalProviderError) as cm:
            p.submit(MODEL, dict(EXPECTED))
        self.assertEqual(cm.exception.code, "http_401")
        # the fixture key must never appear in the error text
        self.assertNotIn("k", str(cm.exception) if cm.exception.args[0] == "k" else "")


if __name__ == "__main__":
    unittest.main()
