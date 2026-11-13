"""Conservative MiniMax 10s retail quote, OFF by default.

This helper does not enable a store checkout, submit a model request, or
guarantee a net margin. Caller must supply verified FX and ALL extra costs.
"""
from decimal import Decimal, ROUND_CEILING
from fal_pricing import PricingUnavailable, Decimal_price
from berry_credit_pricing import required_credits, gross_profit_myr, CREDITS_PER_MYR

MODEL = "minimax/h3-max-turbo/text-to-video"
STANDARD_480P_USD_PER_SECOND = Decimal("0.025")
MAX_BILLED_SECONDS_BUDGET = 11  # 10s requested plus a whole-second allowance


def minimax_10s_guarded_quote(pricing, *, fx_myr_per_usd,
                              verified_extra_cost_myr=None,
                              all_extra_costs_verified=False):
    """Return conservative MYR quote or fail closed.

    Always prices >= standard 480P rate, even if API returns promo pricing.
    11 units is a prudential allowance, NOT an assured maximum billing cap.
    """
    if all_extra_costs_verified is not True or verified_extra_cost_myr is None:
        raise PricingUnavailable("Verified payment and operational costs required")
    fx = Decimal_price(fx_myr_per_usd)
    extra = Decimal_price(verified_extra_cost_myr)
    if fx <= 0 or extra < 0:
        raise PricingUnavailable("Invalid FX or extra costs")
    price, unit = pricing.exact_price(MODEL)
    if unit not in {"seconds", "second", "video_second"}:
        raise PricingUnavailable("Unexpected MiniMax billing unit")
    rate = max(Decimal_price(price), STANDARD_480P_USD_PER_SECOND)
    api_cost_myr = rate * MAX_BILLED_SECONDS_BUDGET * fx
    total_cost_myr = api_cost_myr + extra
    credits = required_credits(api_cost_myr, extra_cost_myr=extra)
    credits = ((credits + 24) // 25) * 25
    if gross_profit_myr(credits, api_cost_myr, extra_cost_myr=extra) < Decimal("1"):
        raise PricingUnavailable("Margin below minimum")
    debit_cents = int((Decimal(credits) * 100 / CREDITS_PER_MYR)
                      .to_integral_value(rounding=ROUND_CEILING))
    total_cost_cents = int((total_cost_myr * 100).to_integral_value(rounding=ROUND_CEILING))
    # Recheck using rounded all-in cost, not only the unrounded estimate.
    if debit_cents - total_cost_cents < 100:
        credits += 25
        debit_cents = int((Decimal(credits) * 100 / CREDITS_PER_MYR)
                          .to_integral_value(rounding=ROUND_CEILING))
    if debit_cents - total_cost_cents < 100:
        raise PricingUnavailable("Rounded margin below minimum")
    return {
        "model": MODEL, "credits": credits, "debit_cents": debit_cents,
        "all_in_cost_cents": total_cost_cents, "reserved_billed_seconds": MAX_BILLED_SECONDS_BUDGET,
        "reference_rate_usd_per_second": str(rate),
        "estimated_gross_margin_cents": debit_cents - total_cost_cents,
        "note": "Forecast only; actual net margin requires billing reconciliation",
    }
