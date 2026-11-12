"""STEP 3 — parameter-bound verified image offer builder (gap I03).

Builds a frozen, expiry-bound offer from a SERVER-REVIEWED configuration
catalog only. The catalog is supplied by deployment configuration, never by
client input, mapping rows, or provider responses. Every parameter (model,
aspect ratio, image count, price) is bound into the frozen quote/arguments
and the request hash, so any drift is rejected at confirm time.
"""
from __future__ import annotations

import re

from staging_job_worker import JobError, JobQuote
from telegram_image_flow import VerifiedImageOffer

ALLOWED_ASPECTS = ("1:1", "16:9", "9:16", "4:3", "3:4")
MIN_PROMPT, MAX_PROMPT = 1, 1500
MAX_COUNT = 4
MAX_EXPIRY_SECONDS = 900


class VerifiedImageOfferBuilder:
    """Offer builder from a reviewed catalog.

    Catalog entries: {model_id, label, settings_label, mapping_revision,
    credits, debit_cents, all_in_cost_cents, cost_reference,
    allowed_aspects, num_images}. All pricing integers are frozen exactly
    like a JobQuote; all_in_cost must remain unverified-marked (cost_reference)
    until account pricing verification (STEP 2 gate).
    """

    def __init__(self, catalog, clock=None):
        if not isinstance(catalog, (list, tuple)) or not catalog:
            raise JobError("Reviewed image catalog required")
        self._entries = []
        for entry in catalog:
            if not isinstance(entry, dict):
                raise JobError("Invalid catalog entry")
            try:
                quote = JobQuote(
                    "image", entry["model_id"], entry["mapping_revision"],
                    entry["credits"], entry["debit_cents"], entry["all_in_cost_cents"],
                    entry["cost_reference"]).payload()
            except (KeyError, TypeError, JobError) as exc:
                raise JobError("Invalid catalog entry") from exc
            aspects = entry.get("allowed_aspects", ALLOWED_ASPECTS)
            if (not isinstance(aspects, (list, tuple)) or not aspects
                    or any(a not in ALLOWED_ASPECTS for a in aspects)):
                raise JobError("Invalid catalog aspects")
            self._entries.append({
                "quote": quote, "label": entry["label"],
                "settings_label": entry["settings_label"],
                "allowed_aspects": tuple(aspects)})
        self._clock = clock

    def _now(self):
        return self._clock() if self._clock is not None else __import__("time").time()

    def __call__(self, prompt, aspect, count):
        return self.build(prompt, aspect, count)

    def build(self, prompt, aspect, count, *, expiry_seconds=300):
        if not isinstance(prompt, str) or not MIN_PROMPT <= len(prompt.strip()) <= MAX_PROMPT:
            raise JobError("Prompt tidak sah")
        if aspect not in ALLOWED_ASPECTS:
            raise JobError("Nisbah aspek tidak disokong")
        if type(count) is not int or not 1 <= count <= MAX_COUNT:
            raise JobError("Bilangan imej tidak sah")
        if type(expiry_seconds) is not int or not 0 < expiry_seconds <= MAX_EXPIRY_SECONDS:
            raise JobError("Tempoh sah offer tidak sah")
        entry = next((e for e in self._entries if aspect in e["allowed_aspects"]), None)
        if entry is None:
            raise JobError("Tiada model menyokong tetapan ini")
        # Price scales with image count but stays integer cents and never
        # falls below the single-image all-in cost floor.
        base = entry["quote"]
        total_cost = base["all_in_cost_cents"] * count
        total_debit = base["debit_cents"] * count
        total_credits = base["credits"] * count
        if total_debit - total_cost < 100:
            raise JobError("Margin bawah had minimum")
        quote = JobQuote("image", base["provider_model_id"], base["mapping_revision"],
                         total_credits, total_debit, total_cost,
                         base["cost_reference"])
        arguments = {"prompt": prompt.strip(), "aspect_ratio": aspect,
                     "num_images": count}
        return VerifiedImageOffer(
            entry["label"], f'{entry["settings_label"]} {aspect} x{count}', quote,
            arguments, int(self._now()) + expiry_seconds)
