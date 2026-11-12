"""STEP 3/2 — enforceable server-side budget guard (owner-approved RM5 cap).

Policy (owner authorization 2026-11-13):
  - RM5.00 (500 MYR cents) is the TOTAL cumulative spend ceiling across AI
    Image and AI Video combined.
  - Every operation must be rejected when its WORST-CASE charge exceeds the
    remaining budget; worst-case = frozen all_in_cost_cents of the job.
  - The provider cannot bound a failed/ambiguous request's charge, so any
    job whose outcome is unknown retains its full worst-case reservation
    against the budget until operator reconciliation resolves it.
  - Atomic reservation: budget check + increment happen inside the job
    claim transaction (mirrors berry_video_test_budgets); concurrent claims
    serialize on the job row lock.

This module holds the pure policy logic; durable state lives in the
ai_*_test_budgets tables (CHECK cap <= 500) enforced by PostgreSQL.
No network, wallet or provider calls here.
"""
from __future__ import annotations

MAX_BUDGET_CENTS = 500          # RM5.00 hard ceiling
RESERVED_UNRESOLVED = "submission_unknown"


class BudgetExceeded(RuntimeError):
    """Raised instead of submitting a paid request that could overspend."""


def validate_budget_config(cap_cents, used_cents, reserved_cents):
    """Validate a budget row fetched from the database (defense-in-depth)."""
    for name, value in (("cap", cap_cents), ("used", used_cents),
                        ("reserved", reserved_cents)):
        if type(value) is not int or value < 0:
            raise BudgetExceeded(f"Invalid budget {name}")
    if cap_cents > MAX_BUDGET_CENTS:
        raise BudgetExceeded("Budget cap exceeds the RM5 owner ceiling")
    if used_cents > cap_cents or reserved_cents > cap_cents:
        raise BudgetExceeded("Budget state inconsistent (over cap)")
    return True


def can_afford(cap_cents, used_cents, reserved_cents, worst_case_cents):
    """True when the worst-case charge fits the remaining budget."""
    validate_budget_config(cap_cents, used_cents, reserved_cents)
    if type(worst_case_cents) is not int or worst_case_cents <= 0:
        raise BudgetExceeded("Worst-case charge must be a positive integer cent amount")
    remaining = cap_cents - used_cents - reserved_cents
    return worst_case_cents <= remaining


def remaining_budget(cap_cents, used_cents, reserved_cents):
    validate_budget_config(cap_cents, used_cents, reserved_cents)
    return cap_cents - used_cents - reserved_cents


def preflight(authorized, worst_case_cents, cap_cents, used_cents, reserved_cents):
    """Full paid-submission preflight. Raises BudgetExceeded on any violation.

    Returns a verdict dict for logging (no secrets, no raw provider data).
    """
    if authorized is not True:
        raise BudgetExceeded("Paid submission not authorized")
    validate_budget_config(cap_cents, used_cents, reserved_cents)
    if not can_afford(cap_cents, used_cents, reserved_cents, worst_case_cents):
        raise BudgetExceeded(
            "Worst-case charge exceeds remaining budget; refusing submission")
    return {
        "authorized": True,
        "worst_case_cents": worst_case_cents,
        "remaining_after": remaining_budget(
            cap_cents, used_cents, reserved_cents) - worst_case_cents,
    }
