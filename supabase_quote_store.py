"""Durable, server-only Supabase quotation store for Berry Store.

No wallet operations. Every request uses service-role key server-side only.
The database enforces tenant/user ownership and idempotency uniqueness.
"""
from __future__ import annotations

import json
import re
import httpx

class QuoteStoreUnavailable(RuntimeError):
    pass

_ID = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


class SupabaseQuoteStore:
    def __init__(self, url, service_key, *, client=None):
        if not isinstance(url, str) or not re.fullmatch(
                r"https://[a-z0-9-]+\\.supabase\\.co", url.rstrip("/")):
            raise ValueError("Invalid Supabase origin")
        if not isinstance(service_key, str) or not service_key.strip():
            raise ValueError("Service-role credential required")
        self._url = url.rstrip("/") + "/rest/v1/ai_quotations"
        self._key = service_key.strip()
        self._client = client or httpx.Client(timeout=12, follow_redirects=False)

    def _request(self, method, *, params=None, payload=None, prefer=None):
        headers = {"apikey": self._key, "Authorization": "Bearer " + self._key,
                   "Content-Type": "application/json"}
        if prefer:
            headers["Prefer"] = prefer
        try:
            response = self._client.request(method, self._url, params=params,
                                            json=payload, headers=headers)
            response.raise_for_status()
            return response.json() if response.content else []
        except (httpx.HTTPError, ValueError):
            raise QuoteStoreUnavailable("Quotation database operation failed") from None

    def save(self, document, idempotency_key=None):
        row = {
            "quote_id": document["quote_id"], "tenant_id": document["tenant_id"],
            "customer_id": document["customer_id"],
            "idempotency_key": idempotency_key,
            "document": document, "integrity": document["integrity"],
            "state": document.get("state", "active"),
            "expires_at_epoch": document["expires_at"],
        }
        try:
            self._request("POST", payload=row, prefer="return=representation")
        except QuoteStoreUnavailable:
            # Duplicate idempotency key may be a legitimate retry, but every
            # other DB failure must still fail closed.
            if idempotency_key is None:
                raise
            existing = self.by_idempotency(document["tenant_id"],
                                           document["customer_id"], idempotency_key)
            if existing is None:
                raise
            return existing
        return dict(document)

    def by_idempotency(self, tenant_id, customer_id, key):
        rows = self._request("GET", params={
            "tenant_id": "eq." + str(tenant_id),
            "customer_id": "eq." + str(customer_id),
            "idempotency_key": "eq." + str(key),
            "select": "document", "limit": "2",
        })
        if not isinstance(rows, list) or len(rows) > 1:
            raise QuoteStoreUnavailable("Ambiguous quotation")
        return dict(rows[0]["document"]) if rows else None

    def get(self, quote_id, tenant_id, customer_id):
        if not isinstance(quote_id, str) or not _ID.fullmatch(quote_id):
            raise QuoteStoreUnavailable("Invalid quotation identifier")
        rows = self._request("GET", params={
            "quote_id": "eq." + quote_id, "tenant_id": "eq." + str(tenant_id),
            "customer_id": "eq." + str(customer_id), "select": "document", "limit": "2",
        })
        if not isinstance(rows, list) or len(rows) > 1:
            raise QuoteStoreUnavailable("Ambiguous quotation")
        return dict(rows[0]["document"]) if rows else None

    def cancel(self, document):
        # Strict compare-and-swap; only active quote with matching integrity can
        # transition. Cancellation is idempotent only after a fresh read by owner.
        quote_id = document["quote_id"]
        rows = self._request("PATCH", params={
            "quote_id": "eq." + quote_id,
            "tenant_id": "eq." + str(document["tenant_id"]),
            "customer_id": "eq." + str(document["customer_id"]),
            "state": "eq.active",
            "integrity": "eq." + document["_old_integrity"],
            "select": "quote_id",
        }, payload={"state": "cancelled", "integrity": document["integrity"],
                    "document": {k: v for k, v in document.items()
                                 if k != "_old_integrity"}},
           prefer="return=representation")
        if not isinstance(rows, list) or len(rows) != 1:
            raise QuoteStoreUnavailable("Quotation state changed or unavailable")
