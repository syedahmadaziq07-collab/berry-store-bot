"""Staging-only Berry Credits pricing policy matching the existing Telegram top-up.

RM1 = 1,250 credits. No wallet mutations or generation are performed here.
"""
from decimal import Decimal, ROUND_CEILING

CREDITS_PER_MYR = 1250
MYR_PER_CREDIT = Decimal("1") / Decimal(CREDITS_PER_MYR)
TOPUP_PACKAGES = {"starter": (Decimal("5"), 6250),
                  "creator": (Decimal("10"), 12500),
                  "pro": (Decimal("20"), 25000),
                  "studio": (Decimal("50"), 62500)}
MIN_GROSS_PROFIT_MYR = Decimal("1.00")


def required_credits(api_cost_myr, *, extra_cost_myr="0", min_profit_myr=MIN_GROSS_PROFIT_MYR):
    """Round UP so estimated gross margin meets threshold; never guess unknown fees."""
    cost = Decimal(str(api_cost_myr)) + Decimal(str(extra_cost_myr))
    profit = Decimal(str(min_profit_myr))
    if not cost.is_finite() or not profit.is_finite() or cost < 0 or profit < 0:
        raise ValueError("Costs and profit must be finite nonnegative amounts")
    return int(((cost + profit) / MYR_PER_CREDIT).to_integral_value(rounding=ROUND_CEILING))


def gross_profit_myr(credits, api_cost_myr, *, extra_cost_myr="0"):
    if isinstance(credits, bool) or not isinstance(credits, int) or credits < 0:
        raise ValueError("Credits must be nonnegative integer")
    cost = Decimal(str(api_cost_myr)) + Decimal(str(extra_cost_myr))
    if not cost.is_finite() or cost < 0:
        raise ValueError("Cost must be finite nonnegative")
    return MYR_PER_CREDIT * credits - cost
