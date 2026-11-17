"""Regression coverage for the Gemini -> Berry Store Promotion Center bridge.

Uses only Flask's test client and mocked HTTP responses. No third-party
posting, no Supabase writes, and no real promotion campaign creation.
"""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from werkzeug.security import generate_password_hash
from admin_app import create_app

BASE = "https://admin.qa.test"
ROOT = "/api/admin/v1/promotion"
TOKEN = "test-proxy-token-only-not-for-production-" + ("k" * 40)
CSRF_UUID = "12121212-1212-4121-8121-121212121212"


class FakeStore:
    def configured(self):
        return True

    def read(self, table):
        return []


class GeminiPromotionBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        config = {
            "TESTING": True,
            "ADMIN_PASSWORD_HASH": generate_password_hash("qa-only-password", method="pbkdf2:sha256:1000"),
            "DASHBOARD_ADMIN_SECRET": "",
            "ADMIN_STATE_PATH": str(Path(self.tmp.name) / "state.sqlite3"),
            "TENANT_ID": "92c1e5ca-8498-438f-b777-3dc1c3195c1b",
            "PROMOTION_BRIDGE_ENABLED": True,
            "PROMOTION_BRIDGE_TOKEN": TOKEN,
        }
        with patch("provider_readiness.staging_startup_probe"):
            self.app = create_app(config, store=FakeStore())
        self.client = self.app.test_client()

    def login(self):
        result = self.client.post("/api/admin/v1/auth/login", base_url=BASE, json={"password": "qa-only-password"})
        self.assertEqual(result.status_code, 200)
        return result.json["csrfToken"]

    def test_unauthenticated_connection_cannot_be_read(self):
        with patch("admin_app.httpx.get") as probe:
            response = self.client.get(ROOT + "/connection", base_url=BASE)
        self.assertEqual(response.status_code, 401)
        probe.assert_not_called()

    def test_connected_only_after_successful_upstream_probe(self):
        self.login()
        expected = {"destinations": [], "campaigns": [], "deliveries": [], "threads_accounts": [], "templates": []}
        with patch("admin_app.httpx.get", return_value=httpx.Response(200, json=expected)) as probe:
            response = self.client.get(ROOT + "/connection", base_url=BASE)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json["connected"])
        self.assertFalse(response.json["googleFormsAutoSubmit"])
        self.assertNotIn(TOKEN, response.text)
        self.assertEqual(probe.call_args.kwargs["headers"]["X-Promotion-Bridge-Token"], TOKEN)

    def test_bridge_auth_failure_is_disconnected_not_a_false_positive(self):
        self.login()
        with patch("admin_app.httpx.get", return_value=httpx.Response(401, json={"error": "Denied"})):
            response = self.client.get(ROOT + "/connection", base_url=BASE)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json["connected"])

    def test_bridge_unreachable_is_disconnected_and_login_remains_valid(self):
        self.login()
        with patch("admin_app.httpx.get", side_effect=httpx.ConnectError("not reachable")):
            response = self.client.get(ROOT + "/connection", base_url=BASE)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json["connected"])
        self.assertEqual(self.client.get("/api/admin/v1/auth/me", base_url=BASE).status_code, 200)

    def test_upstream_401_does_not_expire_gemini_admin_session(self):
        self.login()
        with patch("admin_app.httpx.request", return_value=httpx.Response(401, json={"error": "upstream invalid token"})):
            response = self.client.get(ROOT + "/state", base_url=BASE)
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(TOKEN, response.text)
        self.assertEqual(self.client.get("/api/admin/v1/auth/me", base_url=BASE).status_code, 200)

    def test_state_proxies_without_returning_token(self):
        self.login()
        expected = {"destinations": [], "campaigns": [], "deliveries": [], "threads_accounts": [], "templates": []}
        with patch("admin_app.httpx.request", return_value=httpx.Response(200, json=expected)) as upstream:
            response = self.client.get(ROOT + "/state", base_url=BASE)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, expected)
        self.assertNotIn(TOKEN, response.text)
        self.assertTrue(upstream.call_args.args[1].endswith("/api/dashboard/promotion/state"))
        self.assertEqual(upstream.call_args.kwargs["headers"]["X-Promotion-Bridge-Token"], TOKEN)

    def test_promotion_write_requires_csrf_and_uuid(self):
        csrf = self.login()
        with patch("admin_app.httpx.request") as upstream:
            missing_csrf = self.client.post(ROOT + "/destination", base_url=BASE, json={"name": "Test"})
            self.assertEqual(missing_csrf.status_code, 403)
            no_uuid = self.client.post(ROOT + "/destination", base_url=BASE, json={"name": "Test"},
                                       headers={"X-CSRF-Token": csrf})
            self.assertEqual(no_uuid.status_code, 400)
        upstream.assert_not_called()

    def test_authorized_write_forwards_to_one_allowlisted_route(self):
        csrf = self.login()
        with patch("admin_app.httpx.request", return_value=httpx.Response(200, json={"name": "Test"})) as upstream:
            response = self.client.post(ROOT + "/destination", base_url=BASE, json={"name": "Test"},
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": CSRF_UUID})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["name"], "Test")
        self.assertEqual(upstream.call_args.args[0], "POST")
        self.assertNotIn(TOKEN, response.text)

    def test_proxy_cannot_post_to_arbitrary_backend_path(self):
        csrf = self.login()
        with patch("admin_app.httpx.request") as upstream:
            response = self.client.post(ROOT + "/orders/approve", base_url=BASE, json={},
                headers={"X-CSRF-Token": csrf, "Idempotency-Key": CSRF_UUID})
        self.assertEqual(response.status_code, 404)
        upstream.assert_not_called()

    def test_shop_writes_still_locked_when_promotion_enabled(self):
        csrf = self.login()
        response = self.client.post("/api/admin/v1/shop/products", base_url=BASE, json={"name": "Do not create"},
            headers={"X-CSRF-Token": csrf, "Idempotency-Key": CSRF_UUID})
        self.assertEqual(response.status_code, 423)


if __name__ == "__main__":
    unittest.main()
