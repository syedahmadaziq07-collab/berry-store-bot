"""STEP 3 — Dynamic pricing engine with verified FX + operational costs.

Formula (all Decimal; no floats in money paths):
  provider_cost_myr = max(verified_live_rate, conservative_floor_rate)
                      * planning_billed_seconds * (fx + fx_buffer)
  total_cost_myr    = provider_cost_myr + operational_costs_myr
  selling_myr_cents = ceil_to_RM0.02(
      (total_cost_myr + MIN_PROFIT_MYR) / (1 - fee_fraction))
  credits           = ceil(selling_myr * 1250) aligned to 25-credit units

Fail-closed inputs: FX rate must be present, positive, non-expired and carry
a source + timestamp; operational costs must come from approved config.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from typing import Optional

from fal_pricing import PricingUnavailable, VerifiedFalPricing

CREDITS_PER_MYR = 1250
MIN_PROFIT_MYR = Decimal("1.00")
FEE_FRACTION_MAX = Decimal("0.9")
DEFAULT_PLANNING_SECONDS = 11  # 10s requested + whole-second allowance
MAX_FX_AGE_SECONDS = 6 * 3600  # FX older than 6h is rejected as stale


@dataclass(frozen=True)
class FXRate:
    myr_per_usd: Decimal
    source: str
    timestamp: int          # unix seconds
    buffer_fraction: Decimal  # e.g. 0.02 => +2% safety margin


def effective_fx(rate: FXRate, now: int) -> Decimal:
    if not isinstance(rate, FXRate):
        raise PricingUnavailable("FX rate object required")
    if rate.myr_per_usd <= 0:
        raise PricingUnavailable("Invalid FX rate")
    if rate.timestamp > now:
        raise PricingUnavailable("FX timestamp in the future")
    if now - rate.timestamp > MAX_FX_AGE_SECONDS:
        raise PricingUnavailable("FX rate expired")
    if not (Decimal("0") <= rate.buffer_fraction < FEE_FRACTION_MAX):
        raise PricingUnavailable("Invalid FX buffer")
    if not rate.source or len(rate.source) > 128:
        raise PricingUnavailable("FX source required for audit")
    return rate.myr_per_usd * (Decimal("1") + rate.buffer_fraction)


@dataclass(frozen=True)
class OperationalCosts:
    payment_gateway_fee_fraction: Decimal   # e.g. 0.029
    fixed_operational_myr: Decimal          # hosting/storage/delivery share


def validate_operational_costs(costs: OperationalCosts) -> Decimal:
    if not isinstance(costs, OperationalCosts):
        raise PricingUnavailable("Operational costs required")
    fee = costs.payment_gateway_fee_fraction
    if not isinstance(fee, Decimal) or not (Decimal("0") <= fee <= FEE_FRACTION_MAX):
        raise PricingUnavailable("Invalid payment gateway fee fraction")
    fixed = costs.fixed_operational_myr
    if not isinstance(fixed, Decimal) or fixed < 0:
        raise PricingUnavailable("Invalid fixed operational cost")
    return fee


def price_product(product, pricing: VerifiedFalPricing, *, fx_rate: FXRate,
                  operational: OperationalCosts, now: int,
                  planning_seconds: Optional[int] = None) -> dict:
    """Compute the fail-closed selling price for a catalog product.

    Returns integer-cent breakdown with the conservative provider floor.
    """
    fee_fraction = validate_operational_costs(operational)
    fx = effective_fx(fx_rate, now)
    price, unit = pricing.exact_price(product.model_id)
    if unit not in {"seconds", "second", "video_second"}:
        raise PricingUnavailable("Unexpected provider billing unit for product")
    live = Decimal_price(price)
    # Conservative floor: never price below the documented standard rate.
    from minimax_retail_guard import STANDARD_480P_USD_PER_SECOND as FLOOR_USD
    rate = live if live > FLOOR_USD else FLOOR_USD
    seconds = planning_seconds if planning_seconds is not None \
        else DEFAULT_PLANNING_SECONDS
    if type(seconds) is not int or seconds < product.duration_seconds:
        raise PricingUnavailable("Planning seconds below product duration")
    provider_cost = rate * Decimal(seconds) * fx
    total_cost = provider_cost + operational.fixed_operational_myr
    # selling = (total_cost + MIN_PROFIT) / (1 - fee), ceil to RM0.02
    selling_myr = ((total_cost + MIN_PROFIT_MYR)
                   / (Decimal("1") - fee_fraction))
    selling_cents = (selling_myr * 100).to_integral_value(rounding=ROUND_CEILING)
    selling_cents = int((Decimal(selling_cents) / 2)
                        .to_integral_value(rounding=ROUND_CEILING) * 2)
    credits = int((Decimal(selling_cents) / 100 * CREDITS_PER_MYR)
                  .to_integral_value(rounding=ROUND_CEILING))
    credits = ((credits + 24) // 25) * 25
    debit_cents = int((Decimal(credits) * 100 / CREDITS_PER_MYR)
                      .to_integral_value(rounding=ROUND_CEILING))
    margin_cents = debit_cents - int((total_cost * 100)
                                     .to_integral_value(rounding=ROUND_CEILING))
    if margin_cents < int(MIN_PROFIT_MYR * 100):
        raise PricingUnavailable("Margin below RM1 minimum")
    return {
        "product_id": product.product_id,
        "product_key": product.product_key,
        "model_id": product.model_id,
        "mapping_revision": product.mapping_revision,
        "provider_rate_usd": str(rate),
        "live_rate_usd": str(live),
        "planning_seconds": seconds,
        "fx_effective": str(fx),
        "fx_source": fx_rate.source,
        "fx_timestamp": fx_rate.timestamp,
        "total_cost_cents": int((total_cost * 100)
                                .to_integral_value(rounding=ROUND_CEILING)),
        "selling_cents": selling_cents,
        "credits": credits,
        "debit_cents": debit_cents,
        "estimated_margin_cents": margin_cents,
        "catalog_revision": 1,
    }


def Decimal_price(value):
    from fal_pricing import Decimal_price as _dp
    return _dp(value)
