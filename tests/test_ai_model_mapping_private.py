"""Isolated private-mapping API contract tests (no real Supabase writes)."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import httpx
from werkzeug.security import generate_password_hash

from admin_app import create_app
from ai_model_mapping_store import PrivateMappingStore, PrivateMappingConflict

PREFIX = "/api/admin/v1"
URL = "https://test-staging.supabase.co"
BUSINESS = "https://test-production.supabase.co"
TENANT = str(uuid4())
MAPPING = [{"tool_key": "video", "display_name": "Berry Video Pro",
            "provider_model_id": "fal-ai/pixverse/v3.5/image-to-video",
            "credit_cost": 1250, "enabled": True}]


class PrivateMappingContract(unittest.TestCase):
    def test_isolated_url_gate(self):
        self.assertFalse(PrivateMappingStore(BUSINESS, "secret", TENANT, BUSINESS).configured())
        self.assertFalse(PrivateMappingStore("http://test-staging.supabase.co", "secret", TENANT, BUSINESS).configured())
        self.assertFalse(PrivateMappingStore(URL, "", TENANT, BUSINESS).configured())
        self.assertTrue(PrivateMappingStore(URL, "secret", TENANT, BUSINESS).configured())

    def test_get_put_rpc_and_no_provider_id_in_public_response_without_login(self):
        requests = []
        def respond(req):
            requests.append(req)
            assert req.headers["authorization"] == "Bearer test-service-role"
            assert req.url.host == "test-staging.supabase.co"
            if req.url.path.endswith("_get"):
                return httpx.Response(200, json={"mappings": [], "revision": 0})
            return httpx.Response(200, json={"mappings": MAPPING, "revision": 1})
        client = httpx.Client(transport=httpx.MockTransport(respond))
        private = PrivateMappingStore(URL, "test-service-role", TENANT, BUSINESS, client=client)
        self.assertEqual(private.get()["revision"], 0)
        self.assertEqual(private.put(MAPPING, str(uuid4()), 0)["revision"], 1)
        self.assertEqual(len(requests), 2)

    def test_revision_conflict_is_distinct(self):
        client = httpx.Client(transport=httpx.MockTransport(lambda req: httpx.Response(409)))
        private = PrivateMappingStore(URL, "role", TENANT, BUSINESS, client=client)
        with self.assertRaises(PrivateMappingConflict):
            private.put(MAPPING, str(uuid4()), 0)


class StagingPrivateRouteContract(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store = MagicMock()
        self.store.configured.return_value = False
        self.mapping = MagicMock()
        self.mapping.configured.return_value = True
        self.mapping.get.return_value = {"mappings": [], "revision": 0}
        self.mapping.put.return_value = {"mappings": MAPPING, "revision": 1}
        self.config = {
            "TESTING": True, "ADMIN_PASSWORD_HASH": generate_password_hash("Private-Test-#415"),
            "DASHBOARD_ADMIN_SECRET": "", "ADMIN_STATE_PATH": str(Path(tmp.name) / "state.sqlite"),
            "ADMIN_MODE": "staging", "TENANT_ID": TENANT,
            "ADMIN_WRITES_ENABLED": False, "ADMIN_ISOLATED_DATABASE": False,
            "ADMIN_MODEL_MAPPING_PRIVATE_ENABLED": True,
            "ADMIN_MODEL_MAPPING_DRAFT_ENABLED": False,
        }
        self.app = create_app(self.config, store=self.store, mapping_store=self.mapping)
        self.client = self.app.test_client()
        self.base = {"base_url": "https://localhost"}

    def login(self):
        r = self.client.post(PREFIX + "/auth/login", json={"password": "Private-Test-#415"}, **self.base)
        self.assertEqual(r.status_code, 200)
        return r.get_json()["csrfToken"]

    def test_no_anonymous_access_and_private_read_mode(self):
        self.assertEqual(self.client.get(PREFIX + "/ai/model-mappings", **self.base).status_code, 401)
        self.login()
        r = self.client.get(PREFIX + "/ai/model-mappings", **self.base)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.headers["X-Berry-Mapping-Mode"], "private-persistent-staging")
        self.assertEqual(r.headers["X-Berry-Mapping-Revision"], "0")

    def test_private_write_requires_csrf_revision_and_idempotency(self):
        csrf = self.login()
        endpoint = PREFIX + "/ai/model-mappings"
        key = str(uuid4())
        common = {"Idempotency-Key": key, "X-Berry-Mapping-Revision": "0"}
        self.assertEqual(self.client.put(endpoint, json=MAPPING, headers=common, **self.base).status_code, 403)
        headers = dict(common, **{"X-CSRF-Token": csrf})
        headers.pop("X-Berry-Mapping-Revision")
        self.assertEqual(self.client.put(endpoint, json=MAPPING, headers=headers, **self.base).status_code, 400)
        headers["X-Berry-Mapping-Revision"] = "0"
        response = self.client.put(endpoint, json=MAPPING, headers=headers, **self.base)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Berry-Mapping-Revision"], "1")
        self.mapping.put.assert_called_once_with(MAPPING, key, 0)
        self.store.mutate.assert_not_called()

    def test_production_mode_never_exposes_private_write(self):
        app = create_app({**self.config, "ADMIN_MODE": "production"}, store=self.store, mapping_store=self.mapping)
        client = app.test_client()
        login = client.post(PREFIX + "/auth/login", json={"password": "Private-Test-#415"}, **self.base)
        self.assertEqual(login.status_code, 200)
        r = client.put(PREFIX + "/ai/model-mappings", json=MAPPING,
                       headers={"X-CSRF-Token": login.get_json()["csrfToken"],
                                "X-Berry-Mapping-Revision": "0", "Idempotency-Key": str(uuid4())}, **self.base)
        self.assertEqual(r.status_code, 423)
        self.mapping.put.assert_not_called()

    def test_other_mutations_still_locked(self):
        csrf = self.login()
        r = self.client.put(PREFIX + "/shop/products/1", json={"name": "x"},
                            headers={"X-CSRF-Token": csrf, "Idempotency-Key": str(uuid4())},
                            **self.base)
        self.assertEqual(r.status_code, 423)
        self.store.mutate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
