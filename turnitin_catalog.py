"""Approved Berry Store document-check catalog, shared by bot and admin API.

The supplier fulfils the checks; this module does not perform Turnitin/GPTZero
analysis or integrate with their APIs. Prices, stock and descriptions are read
from the tenant's private database, never from these presentation defaults.
"""

from __future__ import annotations


SERVICE_LABELS = {
    "similarity": "🔍 Turnitin Similarity Check",
    "ai": "🤖 Turnitin AI Writing Check",
    "gptzero_basic": "📝 GPTZero Basic · 250–50,000 aksara",
    "gptzero_standard": "📝 GPTZero Standard · 50,001–100,000 aksara",
    "gptzero_premium": "📝 GPTZero Premium · 100,001–150,000 aksara",
    "bundle_basic": "🎁 Bundle Basic · Similarity + GPTZero",
    "bundle_standard": "🎁 Bundle Standard · Similarity + GPTZero",
    "bundle_premium": "🎁 Bundle Premium · Similarity + GPTZero",
    "bundle_turnitin_ai": "🎁 Bundle Turnitin · Similarity + AI",
}

SERVICE_CODES = frozenset(SERVICE_LABELS)


def is_bundle(code: str) -> bool:
    return code.startswith("bundle_") and code in SERVICE_CODES


def available_stock(plan: dict) -> int:
    """For bundles, only advertise stock backed by both component services."""
    return max(0, int(plan.get("available_stock", plan.get("stock", 0))))
