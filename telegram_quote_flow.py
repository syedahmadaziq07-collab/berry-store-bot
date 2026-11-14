"""STEP 3 — Telegram quotation flow (gated, read-only, no wallet effects).

Flow: product menu → aspect ratio → prompt (text) → server-side quotation.
The quotation step NEVER submits a provider request or debits a wallet —
customer checkout/provider execution stays OFF until a later approved step.
"""
from __future__ import annotations

from ai_product_catalog import get_product
from ai_quotation_service import QuotationError
from fal_pricing import PricingUnavailable


class TelegramQuoteFlow:
    """Server-side quotation controller wired into the existing bot.

    fx_provider: a call returning a FRESH FXRate per quotation (auto-retrieval
    with cache+TTL+fail-closed). Frozen quotations keep their own FX snapshot.
    """

    def __init__(self, quotation_service, pricing, *, fx_provider, operational):
        self.svc = quotation_service
        self.pricing = pricing
        self.fx_provider = fx_provider
        self.ops = operational

    def _fresh_fx(self):
        rate = self.fx_provider() if callable(self.fx_provider) else None
        if rate is None:
            raise QuotationError("Kadar FX belum disahkan; quotation ditahan")
        return rate

    def product_menu_text(self):
        try:
            product = get_product("minimax_turbo_video")
        except PricingUnavailable:
            return ("🎬 AI VIDEO\n━━━━━━━━━━━━━━━━━━\n\n"
                    "🚧 Produk AI belum tersedia.\n🔒 Tiada caj dikenakan.")
        return ("🎬 MiniMax Turbo Video\n━━━━━━━━━━━━━━━━━━\n\n"
                f"{product.description}\n\n"
                f"Durasi: {product.duration_seconds} saat • "
                f"{product.resolution} • {product.prompt_expansion_mode}\n\n"
                "Pilih nisbah aspek untuk quotation:")

    def start_prompt(self, user_id, aspect_ratio):
        """Validate ratio and enter the prompt stage."""
        product = get_product("minimax_turbo_video")
        if aspect_ratio not in product.aspect_ratios:
            raise QuotationError("Nisbah aspek tidak disokong")
        return {"stage": "prompt", "aspect_ratio": aspect_ratio}

    def build_quote(self, *, tenant_id, customer_id, prompt, aspect_ratio,
                    idempotency_key=None, now=None):
        """Compute the quotation server-side; fail-closed on any bad input.

        Every quotation fetches the CURRENT fresh FX snapshot (provider call
        inside); the created quotation freezes that snapshot permanently."""
        import time as _time
        fx_rate = self._fresh_fx()
        return self.svc.create(tenant_id=tenant_id, customer_id=customer_id,
                               product_key="minimax_turbo_video",
                               aspect_ratio=aspect_ratio, prompt=prompt,
                               pricing=self.pricing, fx_rate=fx_rate,
                               operational=self.ops,
                               idempotency_key=idempotency_key,
                               now=now if now is not None else int(_time.time()))

    def quote_reply_text(self, view):
        return ("🧾 QUOTATION AI VIDEO\n━━━━━━━━━━━━━━━━━━\n\n"
                f"{view['product_name']}\n"
                f"Durasi: {view['duration_seconds']} saat • {view['resolution']}\n"
                f"Nisbah: {view['aspect_ratio']}\n\n"
                f"Harga: {view['price_myr']}\n"
                f"Berry Credits: {view['credits']:,}\n"
                f"Quote ID: {view['quote_id']}\n\n"
                f"⏳ Quote sah sehingga "
                f"{view['expires_at']} (10 minit).\n"
                "🔒 Ini quotation sahaja — tiada debit atau penjanaan dibuat.")
