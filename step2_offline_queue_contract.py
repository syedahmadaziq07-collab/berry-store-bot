"""Offline-only queue status contract for future worker integration.

No network, wallet, provider submission, database calls, or spending.
Not wired to a running worker. Unknown outcomes fail closed.
"""
from dataclasses import dataclass

STATUSES = frozenset(("IN_QUEUE", "IN_PROGRESS", "COMPLETED"))


class QueueContractError(ValueError):
    pass


@dataclass(frozen=True)
class PollDecision:
    action: str
    next_delay_seconds: int | None = None


def classify_queue_status(payload, *, request_id, attempt, max_attempts=12):
    if not isinstance(payload, dict) or not isinstance(request_id, str) or not request_id:
        raise QueueContractError("invalid_status")
    if payload.get("request_id") != request_id:
        raise QueueContractError("request_mismatch")
    if type(attempt) is not int or type(max_attempts) is not int or not (0 <= attempt < max_attempts <= 100):
        raise QueueContractError("poll_budget_exhausted")
    status = payload.get("status")
    if status not in STATUSES:
        raise QueueContractError("unknown_status")
    if status == "COMPLETED":
        return PollDecision("fetch_result")
    return PollDecision("poll", min(2 ** min(attempt, 5), 30))


def classify_submit_outcome(*, transport_succeeded, request_id=None):
    if transport_succeeded and isinstance(request_id, str) and request_id:
        return "bind_request"
    # A timeout/5xx after POST may still have created a billed request.
    return "submission_unknown"


def authorize_offline_budget(*, cap_cents, reserved_cents, candidate_cents, generation_count, max_generations):
    values = (cap_cents, reserved_cents, candidate_cents, generation_count, max_generations)
    if any(type(x) is not int for x in values):
        return False
    if not (0 < cap_cents <= 500 and 0 <= reserved_cents <= cap_cents and
            candidate_cents > 0 and generation_count >= 0 and max_generations > 0):
        return False
    return generation_count < max_generations and candidate_cents <= cap_cents - reserved_cents
