"""STEP 3 — immutable, expiring, tenant-bound quotation service.

A quotation is computed server-side, frozen at creation, bound to
(customer, tenant, product, parameters), and carries a unique id, creation
timestamp and expiry. Expired/replayed/altered/cross-tenant quotes are
rejected. Cancellation never touches any wallet. No provider POST, no
wallet debit and no paid generation occurs in this module.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time

from ai_pricing_engine import price_product
from ai_product_catalog import get_product, validate_customer_selection
from fal_pricing import PricingUnavailable


class QuotationError(PricingUnavailable):
    pass


class QuotationService:
    """Quote store with tamper-evident HMAC integrity over canonical JSON."""

    TTL_SECONDS = 600  # 10 minutes

    def __init__(self, signing_key, *, rate_limit_per_minute=6, store=None):
        if not isinstance(signing_key, str) or len(signing_key) < 16:
            raise QuotationError("Quotation signing key required")
        self._key = signing_key.encode()
        self._store = store
        self._quotes = {}
        self._idempotency = {}
        self._rate = {}
        self._limit = rate_limit_per_minute

    def _rate_ok(self, scope, now):
        window = self._rate.get(scope)
        if window and now - window[0] <= 60 and window[1] >= self._limit:
            return False
        if window and now - window[0] <= 60:
            self._rate[scope] = (window[0], window[1] + 1)
        else:
            self._rate[scope] = (now, 1)
        return True

    def _tag(self, document):
        core = {k: v for k, v in document.items() if k != "integrity"}
        canonical = json.dumps(core, sort_keys=True, separators=(",", ":"))
        return hmac.new(self._key, canonical.encode(), hashlib.sha256).hexdigest()

    def create(self, *, tenant_id, customer_id, product_key, aspect_ratio,
               prompt, pricing, fx_rate, operational, now=None,
               idempotency_key=None, planning_seconds=None):
        now = int(time.time()) if now is None else int(now)
        scope = f"{tenant_id}:{customer_id}"
        if not self._rate_ok(scope, now):
            raise QuotationError("Terlalu banyak permintaan; cuba sebentar lagi")
        if idempotency_key is not None:
            if not isinstance(idempotency_key, str) or len(idempotency_key) > 128:
                raise QuotationError("Idempotency key tidak sah")
            existing = (self._store.by_idempotency(tenant_id, customer_id, idempotency_key)
                        if self._store is not None else self._idempotency.get(f"{scope}:{idempotency_key}"))
            if existing is not None:
                doc = existing if self._store is not None else self._quotes.get(existing)
                if doc is None or doc.get("state") == "cancelled" or now > doc["expires_at"]:
                    raise QuotationError("Idempotent quotation unavailable; use a new key")
                if doc["integrity"] != self._tag(doc):
                    raise QuotationError("Quotation integrity failure")
                if (doc["product_key"] != product_key or doc["aspect_ratio"] != aspect_ratio
                        or doc["prompt_sha256"] != hashlib.sha256(prompt.strip().encode()).hexdigest()):
                    raise QuotationError("Idempotency key reused with different parameters")
                return dict(doc)
        product = get_product(product_key)
        validate_customer_selection(product, aspect_ratio)
        if not isinstance(prompt, str) or not 1 <= len(prompt.strip()) <= 1500:
            raise QuotationError("Prompt tidak sah")
        priced = price_product(product, pricing, fx_rate=fx_rate,
                               operational=operational, now=now,
                               planning_seconds=planning_seconds)
        quote_id = secrets.token_urlsafe(16)
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
            "_total_cost_cents": priced["total_cost_cents"],
            "_fx_source": priced["fx_source"],
            "_fx_timestamp": priced["fx_timestamp"],
        }
        document["integrity"] = self._tag(document)
        if self._store is not None:
            saved = self._store.save(document, idempotency_key)
            # A concurrent request may have won the unique idempotency key.
            if saved["quote_id"] != document["quote_id"]:
                if (saved["product_key"] != product_key or saved["aspect_ratio"] != aspect_ratio
                        or saved["prompt_sha256"] != document["prompt_sha256"]):
                    raise QuotationError("Idempotency key reused with different parameters")
                if saved["integrity"] != self._tag(saved) or saved.get("state") == "cancelled" or now > saved["expires_at"]:
                    raise QuotationError("Existing quotation invalid")
            return dict(saved)
        self._quotes[quote_id] = document
        if idempotency_key is not None:
            self._idempotency[f"{scope}:{idempotency_key}"] = quote_id
        return dict(document)

    # ── retrieval / validation ──────────────────────────────────────────────
    def get_valid(self, quote_id, *, tenant_id, customer_id, now=None):
        now = int(time.time()) if now is None else int(now)
        doc = (self._store.get(quote_id, tenant_id, customer_id)
               if self._store is not None else self._quotes.get(quote_id))
        if doc is None:
            raise QuotationError("Quotation tidak ditemui")
        if doc["tenant_id"] != str(tenant_id) or doc["customer_id"] != int(customer_id):
            raise QuotationError("Quotation bukan milik anda")
        if doc["integrity"] != self._tag(doc):
            raise QuotationError("Quotation telah diubah")
        if now > doc["expires_at"]:
            raise QuotationError("Quotation telah luput")
        if doc.get("state") == "cancelled":
            raise QuotationError("Quotation telah dibatalkan")
        return dict(doc)

    def cancel(self, quote_id, *, tenant_id, customer_id, now=None):
        doc = self.get_valid(quote_id, tenant_id=tenant_id,
                             customer_id=customer_id, now=now)
        old_integrity = doc["integrity"]
        doc["state"] = "cancelled"
        doc["integrity"] = self._tag(doc)
        if self._store is not None:
            self._store.cancel(dict(doc, _old_integrity=old_integrity))
        else:
            self._quotes[quote_id] = doc
        return doc

    def customer_view(self, document):
        """Customer-facing projection: no internal costs or infrastructure."""
        return {k: v for k, v in document.items() if not k.startswith("_")} | {
            "price_myr": f"RM{document['selling_cents'] / 100:.2f}"}