import unittest
import httpx

from berry_fal_authcheck import check_fal_pricing_auth


class FalReadonlyAuthTests(unittest.TestCase):
    def test_valid_response_and_no_post(self):
        methods = []
        def handle(req):
            methods.append(req.method)
            self.assertEqual(req.url.path, "/v1/models/pricing")
            return httpx.Response(200, json={"prices": []})
        client = httpx.Client(transport=httpx.MockTransport(handle))
        self.assertEqual(check_fal_pricing_auth(api_key="test-key", client=client), "http_200")
        self.assertEqual(methods, ["GET"])

    def test_unauthorized_does_not_disclose_body(self):
        client = httpx.Client(transport=httpx.MockTransport(
            lambda req: httpx.Response(401, text="private-secret")))
        result = check_fal_pricing_auth(api_key="test-key", client=client)
        self.assertEqual(result, "http_401")
        self.assertNotIn("private-secret", result)

    def test_invalid_key_without_network(self):
        self.assertEqual(check_fal_pricing_auth(api_key=" "), "missing_key")
        self.assertEqual(check_fal_pricing_auth(api_key="bad key"), "invalid_key_format")


if __name__ == "__main__":
    unittest.main()
