"""Read-only fal.ai pricing validation. Never calls inference endpoints.

A price is accepted ONLY from an authenticated GET to a trusted pricing
source whose JSON response parses and exposes an exact per-model price.
Invalid shapes, missing prices, non-200 responses or network errors are
NEVER converted into an assumed cost — they raise and yield no value.
No request payload is sent; no submission endpoint is contacted.
"""
from __future__ import annotations

import re
from urllib.parse import urlparse

import httpx


class PricingProbeError(RuntimeError):
    pass


# Known fal.ai pricing endpoints (READ-ONLY documentation/pricing metadata).
# Never add queue.fal.run or any inference/submit URL here.
READ_ONLY_PRICING_ORIGINS = {"https://fal.ai"}
READ_ONLY_PRICING_PATHS = {"/pricing", "/api/pricing"}

_MODEL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*/[A-Za-z0-9][A-Za-z0-9_./-]*$")


class FalPricingProbe:
    def __init__(self, api_key=None, client=None):
        self._key = api_key
        self._client = client

    def configured(self):
        return bool(self._key and self._key.strip())

    @staticmethod
    def _model(model_id):
        if not isinstance(model_id, str) or not _MODEL.fullmatch(model_id) or ".." in model_id:
            raise PricingProbeError("Invalid fal.ai model identifier")
        return model_id

    @staticmethod
    def _origin_allowed(url):
        parsed = urlparse(url)
        if (parsed.scheme != "https" or parsed.username or parsed.password
                or parsed.port or parsed.query or parsed.fragment):
            raise PricingProbeError("Untrusted pricing URL")
        origin = f"{parsed.scheme}://{parsed.hostname}"
        if origin not in READ_ONLY_PRICING_ORIGINS or parsed.path not in READ_ONLY_PRICING_PATHS:
            raise PricingProbeError("Read-only pricing origin required; inference URLs forbidden")
        return url

    def _get(self, url):
        target = self._origin_allowed(url)
        if not self.configured():
            raise PricingProbeError("Pricing probe requires an authenticated key")
        headers = {"Authorization": "Key " + self._key, "Accept": "application/json"}
        if self._client is None:
            self._client = httpx.Client(timeout=15, follow_redirects=False)
        try:
            response = self._client.get(target, headers=headers)
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            # A failed read NEVER becomes an assumed price.
            raise PricingProbeError("Pricing metadata unavailable") from exc

    def exact_price(self, model_id, *, pricing_url="https://fal.ai/api/pricing"):
        """Return the documented price entry for model_id, or raise.

        Accepts only a parsed JSON object/dict containing an exact, complete
        entry for the model (e.g. {"models": {"<id>": {"price": ...}}} or a
        flat {model_id: price} mapping). Partial or ambiguous data raises.
        """
        self._model(model_id)
        data = self._get(pricing_url)
        if not isinstance(data, dict):
            raise PricingProbeError("Invalid pricing document shape")
        models = data.get("models")
        if models is not None and not isinstance(models, dict):
            raise PricingProbeError("Invalid pricing models shape")
        entries = models if isinstance(models, dict) else data
        entry = entries.get(model_id)
        if entry is None:
            raise PricingProbeError("Model not present in pricing document")
        if isinstance(entry, dict):
            price = entry.get("price", entry.get("per_second", entry.get("value")))
        else:
            price = entry
        # Number-typed price ONLY; strings/None never become a cost.
        if isinstance(price, bool) or not isinstance(price, (int, float)):
            raise PricingProbeError("Pricing entry is not a numeric price")
        return price

    def verify_documented_cost_bound(self, model_id, all_in_cost_cents, *,
                                      pricing_url="https://fal.ai/api/pricing",
                                      fx_rate=None):
        """Validate that the frozen all-in cost bound is not below the exact
        documented unit price (per second). fx_rate converts USD price to MYR
        cents and must be supplied by server configuration, never inferred.

        Raises if the document is invalid or the bound would under-price the
        provider's documented rate. Returns the verified numeric price.
        """
        price = self.exact_price(model_id, pricing_url=pricing_url)
        if type(all_in_cost_cents) is not int:
            raise PricingProbeError("Cost bound must be integer cents")
        if isinstance(fx_rate, bool) or not isinstance(fx_rate, (int, float)) or fx_rate <= 0:
            raise PricingProbeError("Server-configured FX rate required")
        # MYR cents per unit = USD unit price * fx_rate(MYR/USD) * 100
        documented_myr_cents = price * fx_rate * 100
        if all_in_cost_cents < documented_myr_cents:
            raise PricingProbeError("Frozen cost bound is below documented provider price")
        return price