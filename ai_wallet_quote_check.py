"""Staging-only preflight for AI jobs; read-only and fail-closed.

This does not reserve credits or authorize paid generation.
"""
from ai_wallet_pricing_adapter import quote_for_wallet, WalletPricingUnavailable


def check_telegram_wallet_for_ai(bridge, telegram_user_id: int, *,
                                 api_cost_myr, extra_cost_myr, confirmed_costs=False):
    quote = quote_for_wallet(api_cost_myr, extra_cost_myr=extra_cost_myr,
                             confirmed_costs=confirmed_costs)
    balance = bridge.balance_myr(telegram_user_id)
    return {
        "eligible_for_reservation": balance >= quote["wallet_debit_myr"],
        "credits": quote["credits"],
        "wallet_debit_myr": str(quote["wallet_debit_myr"]),
        "balance_myr": str(balance),
        "reservation_created": False,
        "generation_authorized": False,
    }
