"""Production model catalog for AI Image/Video offers.

Bridges the verified fal pricing chain (fal_pricing.VerifiedFalPricing) into
the frozen offer builders used by the Telegram flows. Fail-closed: an offer
is produced ONLY when a verified unit price, a server-configured FX rate and
an RM1-margin-satisfying quote all succeed. No network calls at import; the
probe client is injected. Generation/wallet effects remain gated elsewhere.
"""
from __future__ import annotations

from decimal import Decimal

from fal_pricing import PricingUnavailable, VerifiedFalPricing
from video_myr_worker import JobError
from telegram_image_flow import VerifiedImageOffer
from staging_job_worker import JobQuote


class ProductionModelCatalog:
    """Reviewed server-side catalog entry: endpoint + label + billable units."""

    def __init__(self, entries):
        if not isinstance(entries, (list, tuple)) or not entries:
            raise JobError("Reviewed production catalog required")
        self._entries = {}
        for e in entries:
            if not isinstance(e, dict) or not e.get("endpoint_id") or not e.get("label"):
                raise JobError("Invalid catalog entry")
            if e.get("tool_key") not in ("image", "video"):
                raise JobError("Invalid tool key")
            self._entries[e["endpoint_id"]] = e

    def entry(self, endpoint_id):
        e = self._entries.get(endpoint_id)
        if e is None:
            raise JobError("Model tidak berada dalam katalog")
        return e

    def build_image_offer(self, pricing: VerifiedFalPricing, *, endpoint_id,
                          prompt, aspect="1:1", count=1, fx_rate,
                          mapping_revision=1, expiry_seconds=300, clock=None):
        """Frozen image offer priced from a VERIFIED provider price."""
        import time
        e = self.entry(endpoint_id)
        if e["tool_key"] != "image":
            raise JobError("Model bukan imej")
        quote = pricing.verified_quote_credits(
            endpoint_id, units=count, fx_rate=fx_rate)
        jq = JobQuote("image", endpoint_id, mapping_revision,
                      quote["credits"], quote["debit_cents"],
                      quote["all_in_cost_cents"],
                      f"verified:{endpoint_id}")
        now = clock() if clock else time.time()
        arguments = {"prompt": prompt.strip(), "aspect_ratio": aspect,
                     "num_images": count}
        return VerifiedImageOffer(
            e["label"], f'{e["label"]} {aspect} x{count}', jq, arguments,
            int(now) + expiry_seconds)

    def cost_snapshot(self, pricing: VerifiedFalPricing, *, endpoint_id, units, fx_rate):
        """Verified integer-cent cost snapshot for monitoring/audit."""
        e = self.entry(endpoint_id)
        return {
            "endpoint_id": endpoint_id,
            "tool_key": e["tool_key"],
            "units": units,
            "all_in_cost_cents": pricing.cost_bound_myr_cents(
                endpoint_id, units=units, fx_rate=fx_rate),
        }
