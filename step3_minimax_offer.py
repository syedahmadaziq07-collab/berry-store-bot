"""Offline-safe Step 3 MiniMax offer factory. Not wired into customer checkout.

Caller supplies *verified* FX and all costs. Pricing is fetched by caller's
authenticated pricing adapter only when building an offer, never on import.
"""
import time

from berry_admin_minimax_trial import mini_max_arguments
from fal_pricing import PricingUnavailable
from minimax_retail_guard import MODEL, minimax_10s_guarded_quote
from telegram_video_flow import VerifiedVideoOffer
from video_myr_worker import JobQuote


def make_minimax_staging_offer_builder(pricing, *, fx_myr_per_usd,
                                      verified_extra_cost_myr,
                                      all_extra_costs_verified,
                                      mapping_revision=1, ttl_seconds=300):
    """Return fail-closed offer builder; no submit, wallet or delivery effects."""
    if type(mapping_revision) is not int or mapping_revision <= 0:
        raise PricingUnavailable("Valid mapping revision required")
    if type(ttl_seconds) is not int or not 1 <= ttl_seconds <= 900:
        raise PricingUnavailable("Quote expiry must be 1–900 seconds")

    def build(prompt, ratio):
        if ratio not in ("16:9", "9:16"):
            raise PricingUnavailable("Unsupported aspect ratio")
        arguments = mini_max_arguments(prompt)
        arguments["aspect_ratio"] = ratio
        cost = minimax_10s_guarded_quote(
            pricing, fx_myr_per_usd=fx_myr_per_usd,
            verified_extra_cost_myr=verified_extra_cost_myr,
            all_extra_costs_verified=all_extra_costs_verified,
        )
        quote = JobQuote(
            tool_key="video", provider_model_id=MODEL,
            mapping_revision=mapping_revision,
            credits=cost["credits"], debit_cents=cost["debit_cents"],
            all_in_cost_cents=cost["all_in_cost_cents"],
            cost_reference="fal authenticated rate + standard floor; 11s buffer; verified FX and extras",
        )
        quote.payload()
        return VerifiedVideoOffer(
            label="MiniMax Turbo 10s • 480P",
            settings_label="10s • 480P • balanced • " + ratio,
            quote=quote, arguments=arguments,
            verified_until=int(time.time()) + ttl_seconds,
        )

    return build
