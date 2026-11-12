"""Read-only fal.ai pricing inspection for selected Berry Store candidate.

No provider generation, account purchase, or credential disclosure. Pricing metadata
is NOT a final MYR cost proof. Never enable a model based on this result alone.
"""
from __future__ import annotations

import os
import re
import httpx

SELECTED_MODEL = "minimax/h3-max-turbo/text-to-video"
PRICING_URL = "https://api.fal.ai/v1/models/pricing"

class PricingProbeError(RuntimeError):
    pass


def fetch_pricing(*, model=SELECTED_MODEL, api_key=None, client=None):
    """Return raw authenticated pricing data to trusted server code only.

    Never log or serialize returned content into public customer endpoints. The
    response may require interpretation of pricing units/tiers before quoting.
    """
    if model != SELECTED_MODEL:
        raise PricingProbeError("Model not approved for this pricing probe")
    key = api_key if api_key is not None else os.environ.get("FAL_KEY", "")
    if not isinstance(key, str) or not key.strip():
        raise PricingProbeError("Provider credential not configured")
    owned = client is None
    if owned:
        client = httpx.Client(timeout=10, follow_redirects=False, trust_env=False)
    try:
        response = client.get(PRICING_URL,
            params={"endpoint_id": model},
            headers={"Authorization": "Key " + key, "Accept": "application/json"})
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, (dict, list)):
            raise PricingProbeError("Unexpected pricing response")
        return data
    except (httpx.HTTPError, ValueError) as exc:
        raise PricingProbeError("Authenticated pricing lookup failed") from None
    finally:
        if owned:
            client.close()


def minimum_retail_cents(*, all_in_cost_cents, revenue_fee_bps=0):
    """Round up to Berry Store's RM0.02 price step; require RM1 NET margin."""
    if (type(all_in_cost_cents) is not int or all_in_cost_cents < 0
        or type(revenue_fee_bps) is not int or not 0 <= revenue_fee_bps < 10000):
        raise ValueError("Verified cost and fee rate required")
    numerator = (all_in_cost_cents + 100) * 10000
    denominator = 10000 - revenue_fee_bps
    cents = (numerator + denominator - 1) // denominator
    return ((cents + 1) // 2) * 2
