"""Integration gate wiring the durable no-retry protocol (PR #75) into workers.

This module is the ONLY sanctioned path from a reserved/submitting job to an
outbound provider POST. It enforces, in order:
  1. Durable SUBMISSION_UNKNOWN marker committed BEFORE any network call.
  2. Exactly one POST authorization per job (generation-fenced).
  3. Response binding strictly to that single prior POST.
  4. On restart, poll existing request or operator hold — never a new POST.

Fail-closed: any inconsistency raises SubmissionBlocked and no POST happens.
No provider, wallet, or database calls are made by this module itself.
"""
from step2_no_retry_protocol import Attempt, State, SubmissionBlocked, record_response, authorize_single_post


class WorkerSubmissionGate:
    """Applies the PR #75 state machine to a worker submit/poll cycle.

    The worker supplies a `claim_fn` that must durably persist the
    SUBMISSION_UNKNOWN marker (raising on failure) and return the committed
    Attempt snapshot. The gate then authorizes exactly one POST.
    """

    def __init__(self, claim_fn, post_fn):
        if not callable(claim_fn) or not callable(post_fn):
            raise SubmissionBlocked("invalid_gate_functions")
        self._claim_fn = claim_fn
        self._post_fn = post_fn

    def submit(self, snapshot):
        """snapshot: Attempt-like view of the persisted job state."""
        if not isinstance(snapshot, Attempt):
            raise SubmissionBlocked("invalid_snapshot")
        if snapshot.state not in (State.RESERVED, State.SUBMITTING):
            raise SubmissionBlocked("job_not_submittable")
        # Durable marker must commit before the POST; claim_fn fences duplicates.
        durable = self._claim_fn()
        if not isinstance(durable, Attempt):
            raise SubmissionBlocked("claim_failed")
        authorized = authorize_single_post(durable, persisted=True)
        response = self._post_fn()
        # Any response shape error keeps the job in operator-hold, no retry.
        if not isinstance(response, dict) or not response.get("request_id"):
            raise SubmissionBlocked("untrusted_or_malformed_response")
        return record_response(authorized, request_id=response["request_id"],
                                trusted_response=True)