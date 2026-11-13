"""Verified fal.ai pricing adapter (official Platform API contract).

RESOLVED STEP 2 BLOCKER: the exact pricing endpoint and schema are confirmed
from official documentation (https://fal.ai/docs/documentation/model-apis/pricing):

  GET https://api.fal.ai/v1/models/pricing?endpoint_id=<endpoint_id>
  Authorization: Key $FAL_KEY

  {"prices": [{"endpoint_id": "fal-ai/flux/dev", "unit_price": 0.025,
               "unit": "image", "currency": "USD"}],
   "next_cursor": null, "has_more": false}

Fail-closed rules:
  - Only https://api.fal.ai with the exact /v1/models/pricing path is allowed.
  - A price is accepted ONLY when the parsed JSON contains a prices array with
    an exact endpoint_id match, a finite positive numeric unit_price, a known
    billing unit, and currency == "USD".
  - Missing model, non-200, redirects, malformed JSON or non-numeric prices
    NEVER become an assumed cost — they raise.
  - MYR conversion requires a server-configured FX rate; never inferred.

This module performs read-only GETs. It never calls inference/queue endpoints
and never performs any wallet or database operation.
"""
from __future__ import annotations

import re
from urllib.parse import quote, urlparse

import httpx

PRICING_ORIGIN = "https://api.fal.ai"
PRICING_PATH = "/v1/models/pricing"
KNOWN_UNITS = {"image", "images", "megapixel", "megapixels", "video_second", "second", "seconds", "video", "videos", "request", "requests"}

_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_./-]*$")


class PricingUnavailable(RuntimeError):
    """Raised instead of guessing any cost."""


class VerifiedFalPricing:
    """Read-only client for the verified fal pricing Platform API."""

    def __init__(self, api_key=None, client=None):
        self._key = api_key
        self._client = client

    def configured(self):
        return bool(self._key and self._key.strip())

    @staticmethod
    def _model(endpoint_id):
        if not isinstance(endpoint_id, str) or not _MODEL.fullmatch(endpoint_id) or ".." in endpoint_id:
            raise PricingUnavailable("Invalid fal endpoint identifier")
        return endpoint_id

    @staticmethod
    def _url(endpoint_id):
        # Only the verified pricing endpoint is ever contacted.
        return f"{PRICING_ORIGIN}{PRICING_PATH}?endpoint_id={quote(endpoint_id, safe='')}"

    def _get(self, endpoint_id):
        endpoint_id = self._model(endpoint_id)
        if not self.configured():
            raise PricingUnavailable("Pricing read requires an authenticated key")
        target = self._url(endpoint_id)
        parsed = urlparse(target)
        if parsed.scheme != "https" or parsed.hostname != "api.fal.ai" or parsed.path != PRICING_PATH:
            raise PricingUnavailable("Untrusted pricing URL")
        headers = {"Authorization": "Key " + self._key, "Accept": "application/json"}
        if self._client is None:
            self._client = httpx.Client(timeout=15, follow_redirects=False)
        try:
            response = self._client.get(target, headers=headers)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # A failed read NEVER becomes an assumed price.
            raise PricingUnavailable("Pricing metadata unavailable") from exc

    def exact_price(self, endpoint_id):
        """Return (unit_price, unit) for endpoint_id, or raise."""
        data = self._get(endpoint_id)
        if not isinstance(data, dict) or not isinstance(data.get("prices"), list):
            raise PricingUnavailable("Invalid pricing document shape")
        if any(not isinstance(row, dict) for row in data["prices"]):
            raise PricingUnavailable("Invalid pricing row shape")
        matches = [row for row in data["prices"] if row.get("endpoint_id") == endpoint_id]
        if len(matches) != 1:
            raise PricingUnavailable("Missing or ambiguous model pricing")
        row = matches[0]
        price = row.get("unit_price")
        unit = row.get("unit")
        if row.get("currency") != "USD":
            raise PricingUnavailable("Unexpected pricing currency; refusing to convert blindly")
        if isinstance(price, bool) or not isinstance(price, (int, float)) or not price > 0:
            raise PricingUnavailable("Pricing entry is not a positive numeric price")
        if unit not in KNOWN_UNITS:
            raise PricingUnavailable("Unknown billing unit")
        Decimal_price(price)  # Reject NaN and Infinity before building any quote.
        return float(price), unit

    def verified_quote_credits(self, endpoint_id, *, units, fx_rate,
                               extra_cost_myr="0", confirmed_costs=True):
        """Build a Berry-Credits quote from a VERIFIED provider price.

        Chains fal_pricing cost_bound (integer cents, ceiling) into the
        existing berry_credit_pricing policy: whole-credit round-up so the
        RM1 minimum margin holds on the frozen all-in cost. Never guesses:
        any invalid/unavailable pricing raises PricingUnavailable.
        """
        from decimal import Decimal as _D
        if confirmed_costs is not True:
            raise PricingUnavailable("Verified provider costs required")
        all_in_cents = self.cost_bound_myr_cents(
            endpoint_id, units=units, fx_rate=fx_rate)
        api_cost_myr = _D(all_in_cents) / 100
        from berry_credit_pricing import required_credits, gross_profit_myr, CREDITS_PER_MYR
        credits = required_credits(api_cost_myr, extra_cost_myr=extra_cost_myr)
        # Align to the existing wallet RPC's common 25-credit (RM0.02) unit.
        credits = ((credits + 24) // 25) * 25
        if gross_profit_myr(credits, api_cost_myr, extra_cost_myr=extra_cost_myr) < _D("1.00"):
            raise PricingUnavailable("Insufficient margin")
        debit_cents = int((_D(credits) / _D(CREDITS_PER_MYR) * 100)
                          .to_integral_value(rounding="ROUND_CEILING"))
        return {"credits": credits, "debit_cents": debit_cents,
                "all_in_cost_cents": all_in_cents, "unit_price_usd": None,
                "endpoint_id": endpoint_id, "units": units}

    def cost_bound_myr_cents(self, endpoint_id, *, units, fx_rate):
        """Worst-case MYR cent cost bound for a verified unit price.

        units: integer number of billable units (image count or video seconds)
        fx_rate: server-configured MYR per USD rate (never inferred).
        Returns integer cents (ceiling). Raises on any invalid input.
        """
        price_usd, unit = self.exact_price(endpoint_id)
        if type(units) is not int or units <= 0 or units > 10000:
            raise PricingUnavailable("Invalid unit count")
        if isinstance(fx_rate, bool) or not isinstance(fx_rate, (int, float)) or fx_rate <= 0:
            raise PricingUnavailable("Server-configured FX rate required")
        myr = Decimal_price(price_usd) * Decimal_price(fx_rate) * units
        cents = (myr * 100).to_integral_value(rounding="ROUND_CEILING")
        if cents <= 0:
            raise PricingUnavailable("Computed cost bound is not positive")
        return int(cents)


def Decimal_price(value):
    from decimal import Decimal
    d = Decimal(str(value))
    if not d.is_finite():
        raise PricingUnavailable("Non-finite numeric value")
    return d
