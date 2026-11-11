"""Validated, provider-independent AI model configuration for Berry Store.

This module intentionally does NOT run an AI job, charge a wallet or claim a
provider is working. The public Telegram label and the private provider slug
are separate, and the latter must never appear in Telegram copy.
"""
import json
import re

SETTING_KEY = "ai_model_mappings"
TOOL_KEYS = frozenset({"image", "video", "transform", "voice", "enhance", "storyboard"})
MODEL_RE = re.compile(r"^[a-z0-9][a-z0-9_./-]{2,159}$", re.ASCII)
LABEL_RE = re.compile(r"^[^\x00-\x1f\x7f<>]{1,64}$")
MAX_ENTRIES = 16


class MappingValidationError(ValueError):
    pass


def validate_mappings(value):
    """Return normalized mappings or raise. No silent dropping of invalid data."""
    if not isinstance(value, list) or len(value) > MAX_ENTRIES:
        raise MappingValidationError("Model mappings mesti berupa senarai (maksimum 16).")
    normalized = []
    used = set()
    for entry in value:
        if not isinstance(entry, dict):
            raise MappingValidationError("Setiap model mesti objek.")
        if set(entry) != {"tool_key", "display_name", "provider_model_id", "credit_cost", "enabled"}:
            raise MappingValidationError("Field model tidak sah.")
        key = entry["tool_key"]
        name = entry["display_name"]
        provider_id = entry["provider_model_id"]
        cost = entry["credit_cost"]
        enabled = entry["enabled"]
        if not isinstance(key, str) or key not in TOOL_KEYS or key in used:
            raise MappingValidationError("Jenis alat AI tidak sah atau berulang.")
        if not isinstance(name, str) or not LABEL_RE.fullmatch(name) or name != name.strip():
            raise MappingValidationError("Nama paparan mesti 1–64 aksara tanpa HTML/newline.")
        if not isinstance(provider_id, str) or not MODEL_RE.fullmatch(provider_id):
            raise MappingValidationError("Model ID fal.ai tidak sah.")
        if isinstance(cost, bool) or not isinstance(cost, int) or not 0 <= cost <= 1_000_000:
            raise MappingValidationError("Caj Berry Credits mesti integer 0–1000000.")
        if type(enabled) is not bool:
            raise MappingValidationError("Status model mesti boolean.")
        normalized.append({"tool_key": key, "display_name": name,
                           "provider_model_id": provider_id,
                           "credit_cost": cost, "enabled": enabled})
        used.add(key)
    return normalized


def encode_mappings(value):
    return json.dumps(validate_mappings(value), separators=(",", ":"), ensure_ascii=False)


def decode_mappings(raw):
    if not raw:
        return []
    try:
        return validate_mappings(json.loads(raw))
    except (TypeError, ValueError) as exc:
        raise MappingValidationError("Konfigurasi model AI tersimpan tidak sah.") from exc


def public_label(mappings, tool_key):
    """Only return a customer-facing brand label, never a provider/model ID."""
    for row in mappings:
        if row["tool_key"] == tool_key and row["enabled"]:
            return row["display_name"]
    return None


def resolve_provider_model(mappings, tool_key):
    """Internal use ONLY by a future authorized, paid AI generation worker."""
    for row in mappings:
        if row["tool_key"] == tool_key and row["enabled"]:
            return row["provider_model_id"]
    return None
