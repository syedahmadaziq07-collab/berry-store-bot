"""Authenticated staging-only draft storage; never makes external DB/AI calls."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

from werkzeug.security import generate_password_hash
from admin_app import create_app

BASE = "/api/admin/v1"
SAMPLE = [{"tool_key": "video", "display_name": "Berry Video Pro",
           "provider_model_id": "fal-ai/pixverse/v3.5/image-to-video",
           "credit_cost": 1250, "enabled": True}]


class DraftMappingTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.dir.cleanup)
        self.state = str(Path(self.dir.name) / "state.sqlite")
        self.store = MagicMock()
        self.store.configured.return_value = False
        self.config = {
            "TESTING": True,
            "ADMIN_PASSWORD_HASH": generate_password_hash("Strong-Test-Passphrase-#413"),
            "DASHBOARD_ADMIN_SECRET": "",
            "ADMIN_STATE_PATH": self.state,
            "TENANT_ID": "tenant-one",
            "ADMIN_MODE": "staging",
            "ADMIN_WRITES_ENABLED": False,
            "ADMIN_ISOLATED_DATABASE": False,
            "ADMIN_MODEL_MAPPING_DRAFT_ENABLED": True,
        }
        self.app = create_app(self.config, store=self.store)
        self.client = self.app.test_client()
        self.base = {"base_url": "https://localhost"}

    def login(self):
        result = self.client.post(BASE + "/auth/login", json={
            "password": "Strong-Test-Passphrase-#413"}, **self.base)
        self.assertEqual(result.status_code, 200)
        return result.get_json()["csrfToken"]

    def put(self, content, csrf=None, **headers):
        hdr = {"Idempotency-Key": str(uuid4())}
        if csrf is not None:
            hdr["X-CSRF-Token"] = csrf
        hdr.update(headers)
        return self.client.put(BASE + "/ai/model-mappings",
                               json=content, headers=hdr, **self.base)

    def test_unauthenticated_get_and_put_are_denied(self):
        self.assertEqual(self.client.get(BASE + "/ai/model-mappings", **self.base).status_code, 401)
        self.assertEqual(self.put(SAMPLE).status_code, 401)

    def test_save_reload_is_local_and_non_production(self):
        csrf = self.login()
        self.assertEqual(self.client.get(BASE + "/ai/model-mappings", **self.base).get_json(), [])
        response = self.put(SAMPLE, csrf)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("X-Berry-Mapping-Mode"), "staging-draft-only")
        self.assertEqual(response.get_json(), SAMPLE)
        self.assertEqual(self.client.get(BASE + "/ai/model-mappings", **self.base).get_json(), SAMPLE)
        # New app instance reading same local file (process restart on same disk).
        app2 = create_app(self.config, store=self.store)
        other = app2.test_client()
        response2 = other.post(BASE + "/auth/login", json={
            "password": "Strong-Test-Passphrase-#413"}, **self.base)
        self.assertEqual(response2.status_code, 200)
        self.assertEqual(other.get(BASE + "/ai/model-mappings", **self.base).get_json(), SAMPLE)
        self.store.read.assert_not_called()
        self.store.mutate.assert_not_called()

    def test_wrong_csrf_and_cross_site_are_denied(self):
        self.login()
        self.assertEqual(self.put(SAMPLE).status_code, 403)
        self.assertEqual(self.put(SAMPLE, "incorrect").status_code, 403)
        self.assertEqual(self.put(SAMPLE, self.login(), Origin="https://evil.example").status_code, 403)

    def test_invalid_data_rejected_and_prior_draft_retained(self):
        csrf = self.login()
        self.assertEqual(self.put(SAMPLE, csrf).status_code, 200)
        bad = [{**SAMPLE[0], "display_name": "<h1>script</h1>"}]
        self.assertEqual(self.put(bad, csrf).status_code, 400)
        self.assertEqual(self.client.get(BASE + "/ai/model-mappings", **self.base).get_json(), SAMPLE)

    def test_other_business_mutations_still_locked(self):
        csrf = self.login()
        response = self.client.put(BASE + "/shop/products/1",
                                   json={"name": "x"},
                                   headers={"X-CSRF-Token": csrf,
                                            "Idempotency-Key": str(uuid4())}, **self.base)
        self.assertEqual(response.status_code, 423)
        self.store.mutate.assert_not_called()

    def test_draft_disabled_blocks_save_even_when_logged_in(self):
        config = {**self.config, "ADMIN_MODEL_MAPPING_DRAFT_ENABLED": False}
        app = create_app(config, store=self.store)
        client = app.test_client()
        login = client.post(BASE + "/auth/login",
                            json={"password": "Strong-Test-Passphrase-#413"}, **self.base)
        self.assertEqual(login.status_code, 200)
        hdr = {"X-CSRF-Token": login.get_json()["csrfToken"],
               "Idempotency-Key": str(uuid4())}
        self.assertEqual(client.get(BASE + "/ai/model-mappings", **self.base).status_code, 423)
        self.assertEqual(client.put(BASE + "/ai/model-mappings", json=SAMPLE,
                                    headers=hdr, **self.base).status_code, 423)

    def test_draft_does_not_work_in_production_mode(self):
        config = {**self.config, "ADMIN_MODE": "production"}
        app = create_app(config, store=self.store)
        client = app.test_client()
        login = client.post(BASE + "/auth/login",
                            json={"password": "Strong-Test-Passphrase-#413"}, **self.base)
        self.assertEqual(login.status_code, 200)
        hdr = {"X-CSRF-Token": login.get_json()["csrfToken"],
               "Idempotency-Key": str(uuid4())}
        self.assertEqual(client.put(BASE + "/ai/model-mappings", json=SAMPLE,
                                    headers=hdr, **self.base).status_code, 423)

    def test_draft_scoped_by_tenant(self):
        csrf = self.login()
        self.assertEqual(self.put(SAMPLE, csrf).status_code, 200)
        another = create_app({**self.config, "TENANT_ID": "tenant-two"}, store=self.store)
        client = another.test_client()
        logged = client.post(BASE + "/auth/login", json={
            "password": "Strong-Test-Passphrase-#413"}, **self.base)
        self.assertEqual(logged.status_code, 200)
        self.assertEqual(client.get(BASE + "/ai/model-mappings", **self.base).get_json(), [])


if __name__ == "__main__":
    unittest.main()
