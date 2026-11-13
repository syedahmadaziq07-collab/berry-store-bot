"""STEP 3 — AI Product Catalog (production).

Server-side, versioned product configuration. Customers can NEVER set model
IDs, prices or raw parameters: only the whitelisted product_key + optional
aspect ratio (from an approved enum) are accepted, and everything else comes
from this reviewed configuration. Deactivation is non-destructive (orders
and quotes retain their frozen data).

The first product: MiniMax H3 Max Turbo Text-to-Video (10s / 480P /
balanced / 16:9 or 9:16 / safety on / MP4).
"""
from __future__ import annotations

from dataclasses import dataclass

from fal_pricing import PricingUnavailable

CATALOG_REVISION = 1


@dataclass(frozen=True)
class AIProduct:
    product_id: str          # unique internal id
    product_key: str         # customer-facing selector (stable)
    name: str
    description: str
    category: str
    model_id: str            # exact fal endpoint id
    duration_seconds: int
    resolution: str
    prompt_expansion_mode: str
    aspect_ratios: tuple
    enable_safety_checker: bool
    output_format: str
    mapping_revision: int
    active: bool


MINIMAX_TURBO_VIDEO = AIProduct(
    product_id="ai-video-minimax-turbo-10s-480p",
    product_key="minimax_turbo_video",
    name="MiniMax Turbo Video",
    description=("Video AI 10 saat (480P) oleh MiniMax H3 Max Turbo — "
                 "prompt anda menjadi video MP4, nisbah 16:9 atau 9:16."),
    category="ai_video",
    model_id="minimax/h3-max-turbo/text-to-video",
    duration_seconds=10,
    resolution="480P",
    prompt_expansion_mode="balanced",
    aspect_ratios=("16:9", "9:16"),
    enable_safety_checker=True,
    output_format="mp4",
    mapping_revision=1,
    active=True,
)

PRODUCTS = {MINIMAX_TURBO_VIDEO.product_key: MINIMAX_TURBO_VIDEO}


def get_product(product_key, *, include_inactive=False):
    """Resolve a product by its customer-facing key, fail-closed."""
    product = PRODUCTS.get(product_key)
    if product is None:
        raise PricingUnavailable("Produk AI tidak dikenali")
    if not product.active and not include_inactive:
        raise PricingUnavailable("Produk AI tidak aktif")
    return product


def validate_customer_selection(product, aspect_ratio):
    """Validate the ONLY two customer-controllable inputs."""
    if aspect_ratio not in product.aspect_ratios:
        raise PricingUnavailable("Nisbah aspek tidak disokong untuk produk ini")
    return product


def deactivate(product_key):
    """Non-destructive deactivation (history preserved). Returns product."""
    product = PRODUCTS.get(product_key)
    if product is None:
        raise PricingUnavailable("Produk AI tidak dikenali")
    object.__setattr__(product, "active", False)
    return product
