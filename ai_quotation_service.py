"""STEP 3 — immutable, expiring, tenant-bound quotation service.

A quotation is computed server-side, frozen at creation, bound to
(customer, tenant, product, parameters), and carries a unique id, creation
timestamp and expiry. Storage is DURABLE (Supabase via the reviewed quote
RPCs) so quotations survive process restarts and redeploys. Expired/
replayed/altered/cross-tenant/cancelled quotes are rejected. Cancellation
never touches any wallet. No provider POST, no wallet debit and no paid
generation occurs in this module.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from uuid import UUID

from ai_pricing_engine import price_product
from ai_product_catalog import get_product, validate_customer_selection
from ai_quote_store import InMemoryQuoteStore, QuotationError, SupabaseQuoteStore


class QuotationService:
    """Quotation creation over a durable store with HMAC integrity.

    signing_key MUST come from server secrets (BERRY_QUOTE_SIGNING_KEY);
    there is deliberately NO BOT_TOKEN fallback.
    """

    TTL_SECONDS = 600  # 10 minutes

    def __init__(self, signing_key, store, *, rate_limit_per_minute=6):
        if not isinstance(signing_key, str) or len(signing_key) < 16:
            raise QuotationError(
                "Quotation signing key required (min 16 chars, from secrets)")
        if store is None:
            raise QuotationError("Quote store required")
        self._key = signing_key.encode()
        self.store = store
        self._limit = rate_limit_per_minute

    def _tag(self, document):
        core = {k: v for k, v in document.items() if k != "integrity"}
        canonical = json.dumps(core, sort_keys=True, separators=(",", ":"))
        return hmac.new(self._key, canonical.encode(), hashlib.sha256).hexdigest()

    def create(self, *, tenant_id, customer_id, product_key, aspect_ratio,
               prompt, pricing, fx_rate, operational, now=None,
               idempotency_key=None, planning_seconds=None):
        now = int(time.time()) if now is None else int(now)
        if idempotency_key is not None and (
                not isinstance(idempotency_key, str) or len(idempotency_key) > 128):
            raise QuotationError("Idempotency key tidak sah")
        if not self.store.rate_ok(customer_id, self._limit):
            raise QuotationError("Terlalu banyak permintaan; cuba sebentar lagi")
        product = get_product(product_key)
        validate_customer_selection(product, aspect_ratio)
        if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 1500:
            raise QuotationError("Prompt tidak sah")
        priced = price_product(product, pricing, fx_rate=fx_rate,
                               operational=operational, now=now,
                               planning_seconds=planning_seconds)
        quote_id = str(UUID(secrets.token_hex(16).replace("-", "")[:32]))
        document = {
            "quote_id": quote_id,
            "created_at": now,
            "expires_at": now + self.TTL_SECONDS,
            "tenant_id": str(tenant_id),
            "customer_id": int(customer_id),
            "product_id": priced["product_id"],
            "product_key": product.product_key,
            "product_name": product.name,
            "model_id": priced["model_id"],
            "mapping_revision": priced["mapping_revision"],
            "duration_seconds": product.duration_seconds,
            "resolution": product.resolution,
            "aspect_ratio": aspect_ratio,
            "prompt_sha256": hashlib.sha256(prompt.strip().encode()).hexdigest(),
            "provider_rate_usd": priced["provider_rate_usd"],
            "planning_seconds": priced["planning_seconds"],
            "selling_cents": priced["selling_cents"],
            "credits": priced["credits"],
            "debit_cents": priced["debit_cents"],
            "catalog_revision": 1,
            "state": "active",
            "_total_cost_cents": priced["total_cost_cents"],
            "_fx_source": priced["fx_source"],
            "_fx_timestamp": priced["fx_timestamp"],
        }
        document["integrity"] = self._tag(document)
        from datetime import datetime, timezone
        expires_iso = datetime.fromtimestamp(
            document["expires_at"], timezone.utc).isoformat()
        result = self.store.create(
            quote_id=quote_id, customer_id=customer_id,
            product_key=product.product_key,
            mapping_revision=priced["mapping_revision"],
            payload_json=json.dumps(document, sort_keys=True,
                                    separators=(",", ":")),
            integrity=document["integrity"],
            idempotency_key=idempotency_key, expires_at=expires_iso)
        if result.get("duplicate"):
            stored = dict(result.get("payload") or {})
            stored["integrity"] = result.get("integrity")
            if result.get("state") != "active" or now > _iso_to_epoch(
                    result.get("expires_at")):
                raise QuotationError(
                    "Idempotent quotation unavailable; use a new key")
            if stored.get("integrity") != self._tag(stored):
                raise QuotationError("Quotation integrity failure")
            return dict(stored)
        return dict(document)

    # ── retrieval / validation (durable, ownership enforced by RPC) ─────────
    def get_valid(self, quote_id, *, tenant_id, customer_id, now=None):
        now = int(time.time()) if now is None else int(now)
        try:
            UUID(str(quote_id))
        except (ValueError, TypeError, AttributeError):
            raise QuotationError("Quotation tidak ditemui") from None
        record = self.store.get(quote_id, customer_id)
        payload = dict(record.get("payload") or {})
        payload["integrity"] = record.get("integrity")
        if record.get("state") == "cancelled":
            raise QuotationError("Quotation telah dibatalkan")
        expires = _iso_to_epoch(record.get("expires_at"))
        if now > expires:
            raise QuotationError("Quotation telah luput")
        if record.get("integrity") != self._tag(payload):
            raise QuotationError("Quotation telah diubah")
        return dict(payload)

    def cancel(self, quote_id, *, tenant_id, customer_id, now=None):
        try:
            UUID(str(quote_id))
        except (ValueError, TypeError, AttributeError):
            raise QuotationError("Quotation tidak ditemui") from None
        record = self.store.cancel(quote_id, customer_id)
        payload = dict(record.get("payload") or {})
        payload["state"] = "cancelled"
        payload["integrity"] = self._tag(payload)
        return payload

    def customer_view(self, document):
        """Customer-facing projection: no internal costs or infrastructure."""
        return {k: v for k, v in document.items() if not k.startswith("_")} | {
            "price_myr": f"RM{document['selling_cents'] / 100:.2f}"}


def _iso_to_epoch(value):
    from datetime import datetime
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(datetime.fromisoformat(
            str(value).replace("Z", "+00:00")).timestamp())
    except Exception:
        raise QuotationError("Quotation expiry tidak sah") from None