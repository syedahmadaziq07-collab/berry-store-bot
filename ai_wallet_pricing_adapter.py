"""Staging-only wallet pricing adapter; no writes, charges or Telegram side effects.

The existing bot stores ai_wallets.balance in MYR, while UI displays Berry Credits.
A future atomic wallet RPC must debit MYR and ledger the corresponding credit units.
"""
from decimal import Decimal
from berry_credit_pricing import CREDITS_PER_MYR, required_credits, gross_profit_myr

class WalletPricingUnavailable(RuntimeError):
    pass

def quote_for_wallet(api_cost_myr, *, extra_cost_myr, confirmed_costs=False):
    """Require verified all-in cost inputs; never generate using guesses."""
    if confirmed_costs is not True:
        raise WalletPricingUnavailable("Verified provider and transaction costs required")
    credits = required_credits(api_cost_myr, extra_cost_myr=extra_cost_myr)
    debit_myr = Decimal(credits) / Decimal(CREDITS_PER_MYR)
    if gross_profit_myr(credits, api_cost_myr, extra_cost_myr=extra_cost_myr) < Decimal("1.00"):
        raise WalletPricingUnavailable("Insufficient margin")
    return {"credits": credits, "wallet_debit_myr": debit_myr}

def can_afford(balance_myr, quote):
    balance = Decimal(str(balance_myr))
    if not balance.is_finite() or balance < 0:
        raise WalletPricingUnavailable("Invalid wallet balance")
    return balance >= quote["wallet_debit_myr"]
