"""STEP 3 — environment readiness audit (presence-only; NO secret values).

Reads only environment NAMES and whether the app can validate them. Prints
PRESENT / MISSING / INVALID / UNVERIFIED per variable. Never logs or returns
secret values themselves — only status + (for non-secrets) validity verdicts.
Run on the production host (e.g. via a one-off admin command) to produce the
readiness report the owner asked for.
"""
from __future__ import annotations

import os
from decimal import Decimal, InvalidOperation

SECRET_VARS = {"FAL_KEY", "BOT_TOKEN", "SUPABASE_SERVICE_KEY",
               "BERRY_QUOTE_SIGNING_KEY"}


def _present(name):
    return bool((os.environ.get(name) or "").strip())


def audit_environment(environ=None) -> list:
    env = os.environ if environ is None else environ
    report = []

    def add(name, status, note=""):
        report.append({"variable": name, "status": status, "note": note})

    # Gating flag
    flag = (env.get("BERRY_QUOTE_FLOW_ENABLED") or "").strip().lower()
    add("BERRY_QUOTE_FLOW_ENABLED",
        "PRESENT" if flag == "true" else
        ("INVALID" if flag and flag != "true" else "MISSING"),
        "must be literal 'true' to enable quotation")

    # Secrets: presence + format hints only, never values.
    for name in ("SUPABASE_URL", "SUPABASE_SERVICE_KEY", "TENANT_ID",
                 "FAL_KEY", "BERRY_QUOTE_SIGNING_KEY"):
        if not _present_in(env, name):
            add(name, "MISSING", "required for production quotation")
        elif name in SECRET_VARS:
            add(name, "PRESENT", "value never displayed")
        elif name == "SUPABASE_URL":
            v = (env.get(name) or "").strip()
            add(name, "PRESENT" if v.startswith("https://") else "INVALID",
                "must be an https Supabase URL")
        elif name == "TENANT_ID":
            v = (env.get(name) or "").strip()
            try:
                import uuid as _u
                _u.UUID(v)
                add(name, "PRESENT", "valid UUID")
            except (ValueError, TypeError):
                add(name, "INVALID", "must be a UUID")
        else:
            key = (env.get(name) or "").strip()
            add("BERRY_QUOTE_SIGNING_KEY",
                "PRESENT" if len(key) >= 16 else "INVALID",
                "min 16 chars, dedicated secret (no BOT_TOKEN fallback)")
            break

    # BERRY_QUOTE_SIGNING_KEY length check (without exposing value)
    sk = (env.get("BERRY_QUOTE_SIGNING_KEY") or "").strip()
    if sk:
        report = [r for r in report if r["variable"] != "BERRY_QUOTE_SIGNING_KEY"
                  or r["status"] != "PRESENT"] if False else report
        for r in report:
            if r["variable"] == "BERRY_QUOTE_SIGNING_KEY" and r["status"] == "PRESENT":
                r["status"] = "PRESENT" if len(sk) >= 16 else "INVALID"
                r["note"] = "min 16 chars, dedicated secret"

    # Operational costs (non-secret, validated)
    fee = (env.get("BERRY_AI_PAYMENT_FEE_FRACTION") or "").strip()
    if not fee:
        add("BERRY_AI_PAYMENT_FEE_FRACTION", "MISSING",
            "OWNER INPUT REQUIRED: verified payment gateway fee fraction")
    else:
        try:
            f = Decimal(fee)
            add("BERRY_AI_PAYMENT_FEE_FRACTION",
                "PRESENT" if 0 <= f < 1 else "INVALID",
                "decimal fraction in [0,1)")
        except InvalidOperation:
            add("BERRY_AI_PAYMENT_FEE_FRACTION", "INVALID", "not a decimal")

    fixed = (env.get("BERRY_AI_FIXED_COST_MYR") or "").strip()
    if not fixed:
        add("BERRY_AI_FIXED_COST_MYR", "MISSING",
            "OWNER INPUT REQUIRED: verified fixed operational cost in MYR")
    else:
        try:
            fv = Decimal(fixed)
            add("BERRY_AI_FIXED_COST_MYR",
                "PRESENT" if fv >= 0 else "INVALID", "nonnegative MYR decimal")
        except InvalidOperation:
            add("BERRY_AI_FIXED_COST_MYR", "INVALID", "not a decimal")

    # FX: auto mode (default) or manual override
    manual = all(((env.get(k) or "").strip()) for k in
                 ("BERRY_AI_FX_MYR_PER_USD", "BERRY_AI_FX_SOURCE",
                  "BERRY_AI_FX_SOURCE_TIMESTAMP"))
    if manual:
        add("BERRY_AI_FX_MYR_PER_USD", "PRESENT",
            "manual override active (auto provider not used)")
        add("BERRY_AI_FX_SOURCE", "PRESENT", "audit source label")
        add("BERRY_AI_FX_SOURCE_TIMESTAMP", "PRESENT",
            "publication unix timestamp")
    else:
        add("BERRY_AI_FX_MYR_PER_USD", "UNVERIFIED",
            "auto mode: rate fetched live from frankfurter reference API; "
            "no env value needed")
        add("BERRY_AI_FX_SOURCE", "UNVERIFIED", "auto: 'frankfurter.dev-v2-reference'")
        add("BERRY_AI_FX_SOURCE_TIMESTAMP", "UNVERIFIED",
            "auto: published date from provider response")
    buf = (env.get("BERRY_AI_FX_BUFFER") or "").strip()
    add("BERRY_AI_FX_BUFFER",
        "PRESENT" if buf else "UNVERIFIED",
        "optional; default conservative 0.02")
    return report


def _present_in(env, name):
    return bool((env.get(name) or "").strip())


def format_report(report) -> str:
    lines = ["[AI_QUOTE] environment readiness:"]
    for r in report:
        lines.append(f"  {r['variable']}: {r['status']}"
                     + (f" ({r['note']})" if r["note"] else ""))
    return "\n".join(lines)
