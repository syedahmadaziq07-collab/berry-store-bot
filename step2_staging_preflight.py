"""Non-paid staging E2E preflight checks.

Deterministic, offline readiness checks run BEFORE any staging E2E is
requested. Each check inspects configuration and code wiring only — no
provider calls, no database connections, no wallet access, no deployment.
A preflight NEVER authorizes execution; it only reports PASS/FAIL reasons
so an operator knows exactly what remains before E2E can be requested.
"""
from __future__ import annotations


class PreflightCheck:
    __slots__ = ("name", "passed", "reason")

    def __init__(self, name, passed, reason):
        self.name, self.passed, self.reason = name, passed is True, str(reason)

    def as_dict(self):
        return {"check": self.name, "status": "PASS" if self.passed else "FAIL",
                "reason": self.reason}


class StagingE2EPreflight:
    """Aggregates readiness checks for a (future, separately approved)
    non-paid staging end-to-end run."""

    def __init__(self, *, pricing_verified=False, staging_db_writable=False,
                 operator_allowlist_configured=False, worker_runtime_deployed=False,
                 delivery_channel_configured=False, budget_cap_cents=None):
        self._inputs = {
            "pricing_verified": pricing_verified,
            "staging_db_writable": staging_db_writable,
            "operator_allowlist_configured": operator_allowlist_configured,
            "worker_runtime_deployed": worker_runtime_deployed,
            "delivery_channel_configured": delivery_channel_configured,
            "budget_cap_cents": budget_cap_cents,
        }

    def checks(self):
        out = []
        i = self._inputs
        out.append(PreflightCheck(
            "pricing_documented_and_verified", i["pricing_verified"],
            "account-specific fal pricing must be verified read-only against the "
            "documented Platform API pricing source" if not i["pricing_verified"]
            else "verified against documented pricing source"))
        out.append(PreflightCheck(
            "staging_migration_applied", i["staging_db_writable"],
            "staging SQL migration is NOT applied; requires explicit owner approval"
            if not i["staging_db_writable"] else "applied"))
        out.append(PreflightCheck(
            "operator_allowlist_configured", i["operator_allowlist_configured"],
            "server-side operator allowlist not yet configured for staging"
            if not i["operator_allowlist_configured"] else "configured"))
        out.append(PreflightCheck(
            "worker_runtime_deployed", i["worker_runtime_deployed"],
            "no staging worker daemon deployed; deploy requires approval"
            if not i["worker_runtime_deployed"] else "deployed"))
        out.append(PreflightCheck(
            "delivery_channel_configured", i["delivery_channel_configured"],
            "isolated test Telegram delivery channel not configured"
            if not i["delivery_channel_configured"] else "configured"))
        cap = i["budget_cap_cents"]
        cap_ok = type(cap) is int and 0 < cap <= 500
        out.append(PreflightCheck(
            "budget_ceiling_rm5", cap_ok,
            "test budget ceiling must be integer cents in (0, 500] (RM5 max)"
            if not cap_ok else f"ceiling={cap} cents"))
        return out

    def report(self):
        checks = self.checks()
        ready = all(c.passed for c in checks)
        return {
            "ready_for_e2e_request": ready,
            "note": ("preflight PASS authorizes nothing; E2E execution still "
                     "requires explicit owner approval and zero-cost guarantees"),
            "checks": [c.as_dict() for c in checks],
        }


def run_preflight(**inputs):
    return StagingE2EPreflight(**inputs).report()
