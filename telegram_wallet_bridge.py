"""Read-only Telegram wallet bridge for staging AI quote checks.

The live Telegram bot stores ai_wallets.balance in MYR. This bridge
does NOT reserve, debit, refund, create wallets or access Telegram sessions.
Production balance is never copied into staging or changed.
"""
from decimal import Decimal
import httpx
from ai_wallet_pricing_adapter import can_afford, WalletPricingUnavailable


class TelegramWalletBridge:
    def __init__(self, supabase_url: str, service_key: str, tenant_id: str, *, transport=None):
        self.url = supabase_url.rstrip("/")
        self.key = service_key
        self.tenant = tenant_id
        self.transport = transport

    def balance_myr(self, telegram_user_id: int) -> Decimal:
        if not self.url.startswith("https://") or not self.key or not self.tenant:
            raise WalletPricingUnavailable("Wallet connection unavailable")
        if type(telegram_user_id) is not int or telegram_user_id <= 0:
            raise WalletPricingUnavailable("Invalid Telegram user")
        headers = {"apikey": self.key, "Authorization": "Bearer " + self.key}
        params = {"select": "balance", "tenant_id": "eq." + self.tenant,
                  "user_id": "eq." + str(telegram_user_id), "limit": "1"}
        try:
            with httpx.Client(timeout=8, transport=self.transport) as client:
                response = client.get(self.url + "/rest/v1/ai_wallets",
                                      params=params, headers=headers)
                response.raise_for_status()
                rows = response.json()
            if not isinstance(rows, list) or len(rows) > 1:
                raise ValueError("Unexpected wallet response")
            value = Decimal(str(rows[0]["balance"] if rows else "0"))
            if not value.is_finite() or value < 0:
                raise ValueError("Invalid wallet balance")
            return value
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            raise WalletPricingUnavailable("Wallet balance could not be verified") from exc

    def can_afford_quote(self, telegram_user_id: int, quote: dict) -> bool:
        return can_afford(self.balance_myr(telegram_user_id), quote)
