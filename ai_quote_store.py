"""STEP 3 â€” durable quotation store backends.

  - SupabaseQuoteStore: production. Atomic idempotent create, ownership-
    checked get/cancel, durable per-minute rate limiting via the RPCs in
    docs/sql/ai_quotations.sql. Quotes survive restarts; cross-tenant reads
    are impossible (ownership enforced inside the RPC); service-role only.
  - InMemoryQuoteStore: tests only (single-process determinism).
"""
from __future__ import annotations

import json
import time
from uuid import UUID

import httpx

from fal_pricing import PricingUnavailable


class QuotationError(PricingUnavailable):
    pass


class SupabaseQuoteStore:
    """Production storage over the reviewed quote RPCs (service-role only)."""

    def __init__(self, url, key, tenant_id, client=None):
        if not url or not key:
            raise QuotationError("Quote database configuration required")
        self.url = url.rstrip("/")
        self._key = key
        self.tenant_id = str(UUID(str(tenant_id)))
        self._client = client

    def _rpc(self, function, body):
        if self._client is None:
            self._client = httpx.Client(timeout=15, follow_redirects=False)
        try:
            r = self._client.post(
                self.url + f"/rest/v1/rpc/{function}",
                headers={"apikey": self._key,
                         "Authorization": "Bearer " + self._key},
                json=body)
            r.raise_for_status()
            return r.json()
        except (httpx.HTTPError, ValueError, TypeError):
            raise QuotationError(
                "Quote store unavailable; quotation blocked") from None

    def rate_ok(self, customer_id, limit):
        try:
            return self._rpc("berry_ai_quote_rate",
                             {"p_tenant": self.tenant_id,
                              "p_customer": int(customer_id),
                              "p_limit": int(limit)}) is True
        except QuotationError:
            return False  # DB down â†’ fail closed

    def create(self, *, quote_id, customer_id, product_key, mapping_revision,
               payload_json, integrity, idempotency_key, expires_at):
        return self._rpc("berry_ai_quote_create", {
            "p_tenant": self.tenant_id, "p_customer": int(customer_id),
            "p_quote": str(quote_id), "p_product": product_key,
            "p_mapping": int(mapping_revision), "p_payload": payload_json,
            "p_integrity": integrity, "p_idempotency": idempotency_key,
            "p_expires": expires_at})

    def get(self, quote_id, customer_id):
        return self._rpc("berry_ai_quote_get", {
            "p_tenant": self.tenant_id, "p_customer": int(customer_id),
            "p_quote": str(quote_id)})

    def cancel(self, quote_id, customer_id):
        return self._rpc("berry_ai_quote_cancel", {
            "p_tenant": self.tenant_id, "p_customer": int(customer_id),
            "p_quote": str(quote_id)})


class InMemoryQuoteStore:
    """Test-only mirror of the same contract (no network)."""

    def __init__(self, tenant_id):
        self.tenant_id = str(tenant_id)
        self._quotes = {}
        self._idem = {}
        self._rate = {}

    def rate_ok(self, customer_id, limit):
        now = int(time.time())
        scope = (self.tenant_id, int(customer_id))
        w = self._rate.get(scope)
        if w and now - w[0] <= 60:
            if w[1] >= limit:
                return False
            self._rate[scope] = (w[0], w[1] + 1)
        else:
            self._rate[scope] = (now, 1)
        return True

    def create(self, *, quote_id, customer_id, product_key, mapping_revision,
               payload_json, integrity, idempotency_key, expires_at):
        scope = (self.tenant_id, int(customer_id))
        if idempotency_key is not None:
            existing = self._idem.get((scope, idempotency_key))
            if existing is not None:
                doc = self._quotes.get(existing)
                if doc is None:
                    return {"duplicate": False}
                return {"duplicate": True, "state": doc["state"],
                        "expires_at": doc["expires_at"],
                        "payload": doc["payload"], "integrity": doc["integrity"]}
        from datetime import datetime, timezone
        payload = json.loads(payload_json) if isinstance(payload_json, str) \
            else dict(payload_json)
        payload["state"] = "active"
        self._quotes[str(quote_id)] = {
            "tenant_id": self.tenant_id, "customer_id": int(customer_id),
            "product_key": product_key, "mapping_revision": mapping_revision,
            "payload": payload, "integrity": integrity,
            "state": "active", "expires_at": expires_at}
        if idempotency_key is not None:
            self._idem[(scope, idempotency_key)] = str(quote_id)
        return {"duplicate": False}

    def get(self, quote_id, customer_id):
        doc = self._quotes.get(str(quote_id))
        if doc is None or doc["tenant_id"] != self.tenant_id \
                or doc["customer_id"] != int(customer_id):
            raise QuotationError("Quotation tidak ditemui")
        return {"state": doc["state"], "expires_at": doc["expires_at"],
                "payload": doc["payload"], "integrity": doc["integrity"]}

    def cancel(self, quote_id, customer_id):
        doc = self._quotes.get(str(quote_id))
        if doc is None or doc["customer_id"] != int(customer_id):
            raise QuotationError("Quotation tidak ditemui")
        doc["state"] = "cancelled"
        doc["payload"]["state"] = "cancelled"
        return {"state": "cancelled", "payload": doc["payload"],
                "integrity": doc["integrity"]}

