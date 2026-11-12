import unittest
import httpx
from fal_provider import FalProvider, FalProviderError


class FalProviderTests(unittest.TestCase):
    def test_requires_secret(self):
        provider = FalProvider(api_key="")
        with self.assertRaises(FalProviderError):
            provider.submit("fal-ai/flux/dev", {"prompt": "hello"})

    def test_submits_to_queue_without_leaking_key(self):
        def handler(request):
            self.assertEqual(request.url.host, "queue.fal.run")
            self.assertEqual(request.headers["Authorization"], "Key secret-for-test")
            return httpx.Response(200, json={"request_id": "abc", "status": "IN_QUEUE"})
        provider = FalProvider(api_key="secret-for-test", client=httpx.Client(transport=httpx.MockTransport(handler)))
        self.assertEqual(provider.submit("fal-ai/flux/dev", {"prompt": "test"})["request_id"], "abc")

    def test_rejects_external_result_url(self):
        provider = FalProvider(api_key="test")
        with self.assertRaises(FalProviderError):
            provider.result("https://attacker.example/steal")

    def test_rejects_invalid_model(self):
        provider = FalProvider(api_key="test")
        with self.assertRaises(FalProviderError):
            provider.submit("../bad", {"prompt": "x"})


if __name__ == "__main__":
    unittest.main()
