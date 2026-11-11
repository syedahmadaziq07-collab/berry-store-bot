"""Server-only mapping storage for a separate, isolated staging Supabase project.

No calls are made at import time. Never use public.bot_settings for provider IDs.
"""
from __future__ import annotations

from urllib.parse import urlparse
from uuid import UUID

import httpx
from ai_model_mapping import validate_mappings


class PrivateMappingError(RuntimeError):
    pass


class PrivateMappingConflict(PrivateMappingError):
    pass


class PrivateMappingStore:
    """Access restricted RPCs using a backend-only key, never a browser key."""

    def __init__(self, url, service_key, tenant_id, business_url="", client=None):
        self.url = (url or "").rstrip("/")
        self.key = service_key or ""
        self.tenant = tenant_id or ""
        self.business_url = (business_url or "").rstrip("/")
        self.client = client or httpx.Client(timeout=15, follow_redirects=False)

    def configured(self):
        try:
            UUID(self.tenant)
            parsed = urlparse(self.url)
            return bool(
                self.key and self.url != self.business_url and
                parsed.scheme == "https" and parsed.hostname and
                parsed.hostname.endswith(".supabase.co") and
                not parsed.port and not parsed.username and not parsed.password and
                parsed.path in ("", "/") and not parsed.query and not parsed.fragment
            )
        except (TypeError, ValueError, AttributeError):
            return False

    def _rpc(self, name, payload):
        if not self.configured():
            raise PrivateMappingError("Private staging mapping database belum dikonfigurasi")
        try:
            response = self.client.post(
                self.url + "/rest/v1/rpc/" + name,
                headers={
                    "apikey": self.key,
                    "Authorization": "Bearer " + self.key,
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        except httpx.HTTPError as exc:
            raise PrivateMappingError("Keputusan sambungan mapping tidak pasti; semak state sebelum cuba lagi") from exc
        if response.status_code == 409:
            raise PrivateMappingConflict("Mapping telah berubah; refresh sebelum simpan semula")
        if response.status_code != 200:
            raise PrivateMappingError("Private mapping RPC tidak tersedia atau menolak permintaan")
        try:
            data = response.json()
            if not isinstance(data, dict) or type(data.get("revision")) is not int or data["revision"] < 0:
                raise ValueError("bad revision")
            data["mappings"] = validate_mappings(data.get("mappings"))
        except (ValueError, TypeError, KeyError) as exc:
            raise PrivateMappingError("Respons private mapping tidak sah") from exc
        return data

    def get(self):
        return self._rpc("berry_ai_model_mappings_get", {"p_tenant": self.tenant})

    def put(self, mappings, idempotency_key, expected_revision):
        normalized = validate_mappings(mappings)
        UUID(idempotency_key)
        if type(expected_revision) is not int or expected_revision < 0:
            raise ValueError("Expected revision tidak sah")
        return self._rpc("berry_ai_model_mappings_put", {
            "p_tenant": self.tenant,
            "p_payload": normalized,
            "p_key": idempotency_key,
            "p_expected_revision": expected_revision,
        })

    def resolve(self, tool_key):
        """For a future isolated staging bot worker only; no automatic jobs."""
        from ai_model_mapping import resolve_provider_model
        return resolve_provider_model(self.get()["mappings"], tool_key)
