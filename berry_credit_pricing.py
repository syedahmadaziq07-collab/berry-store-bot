"""Staging-only Berry Credits pricing policy. No top-up or wallet writes."""
from decimal import Decimal, ROUND_CEILING

TOPUP_PRICE_MYR = Decimal("6.00")
TOPUP_CREDITS = 5000
MIN_GROSS_PROFIT_MYR = Decimal("1.00")
MYR_PER_CREDIT = TOPUP_PRICE_MYR / TOPUP_CREDITS


def required_credits(api_cost_myr, *, extra_cost_myr="0", min_profit_myr=MIN_GROSS_PROFIT_MYR):
    """Conservative minimum credits, rounded UP, including known extra costs.

    A top-up bonus or discounted credit package changes effective unit value;
    never use this formula unchanged if either is offered.
    """
    cost = Decimal(str(api_cost_myr)) + Decimal(str(extra_cost_myr))
    profit = Decimal(str(min_profit_myr))
    if not cost.is_finite() or not profit.is_finite() or cost < 0 or profit < 0:
        raise ValueError("Costs and profit must be finite nonnegative amounts")
    return int(((cost + profit) / MYR_PER_CREDIT).to_integral_value(rounding=ROUND_CEILING))


def gross_profit_myr(credits, api_cost_myr, *, extra_cost_myr="0"):
    if isinstance(credits, bool) or not isinstance(credits, int) or credits < 0:
        raise ValueError("Credits must be nonnegative integer")
    return MYR_PER_CREDIT * credits - Decimal(str(api_cost_myr)) - Decimal(str(extra_cost_myr))
