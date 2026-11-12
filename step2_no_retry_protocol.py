"""Fail-closed submission protocol for an external non-idempotent paid API.

Pure reference logic for an atomic database claim. The caller MUST persist
SUBMISSION_UNKNOWN *before* making a provider POST, in one durable transaction.
A worker restart, timeout, or ambiguous response can NEVER authorize a retry.
This module performs no provider, wallet, or database operations.
"""
from dataclasses import dataclass
from enum import Enum


class SubmissionBlocked(RuntimeError):
    pass


class State(str, Enum):
    RESERVED = "reserved"
    SUBMITTING = "submitting"
    SUBMISSION_UNKNOWN = "submission_unknown"
    QUEUED = "queued"
    SUCCEEDED = "succeeded"
    FAILED = "provider_failed"


@dataclass(frozen=True)
class Attempt:
    state: State
    post_attempted: bool = False
    provider_request_id: str | None = None
    generation: int = 0


def authorize_single_post(job: Attempt, *, persisted: bool) -> Attempt:
    """The sole transition that can authorize one provider POST.

    `persisted` must be confirmation of a committed database transaction
    that atomically marked the job SUBMISSION_UNKNOWN and fenced competing
    workers. Never call this function on an uncommitted or stale snapshot.
    """
    if job.state != State.SUBMITTING or job.post_attempted or job.provider_request_id:
        raise SubmissionBlocked("submission_already_claimed_or_not_ready")
    if persisted is not True:
        raise SubmissionBlocked("durable_unknown_marker_not_confirmed")
    return Attempt(State.SUBMISSION_UNKNOWN, True, None, job.generation + 1)


def record_response(job: Attempt, *, request_id: str, trusted_response: bool) -> Attempt:
    """Bind a response to the only prior POST; no resubmission permitted."""
    if job.state != State.SUBMISSION_UNKNOWN or not job.post_attempted:
        raise SubmissionBlocked("no_pending_submission")
    if job.provider_request_id is not None:
        raise SubmissionBlocked("request_already_bound")
    if trusted_response is not True:
        raise SubmissionBlocked("untrusted_response")
    if not isinstance(request_id, str) or not request_id or len(request_id) > 256 or not all(
        c.isascii() and (c.isalnum() or c in "_-") for c in request_id
    ):
        raise SubmissionBlocked("invalid_request_id")
    return Attempt(State.QUEUED, True, request_id, job.generation)


def restart_action(job: Attempt) -> str:
    """Never POST on restart if there is any chance the provider saw a POST."""
    if job.post_attempted or job.state in (
        State.SUBMISSION_UNKNOWN, State.QUEUED, State.SUCCEEDED, State.FAILED
    ):
        return "poll_existing" if job.provider_request_id else "operator_hold"
    if job.state == State.SUBMITTING:
        # No persisted evidence that no previous worker sent the request.
        return "operator_hold"
    return "no_submission_authorized"
