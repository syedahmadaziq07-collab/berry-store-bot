"""Pure isolated recovery model for proposed SQL transition; no DB connections."""
from dataclasses import dataclass


class RecoveryRejected(ValueError):
    pass


@dataclass(frozen=True)
class Job:
    state: str
    request_hash: str
    provider_request_id: str | None = None


def bind_ambiguous(job, *, request_id, recovery_mode, recovery_request_hash, evidence):
    if job.state != "submission_unknown" or job.provider_request_id is not None:
        raise RecoveryRejected("invalid_state")
    if recovery_mode != "operator_verified" or recovery_request_hash != job.request_hash:
        raise RecoveryRejected("missing_correlation")
    if not isinstance(evidence, str) or not 20 <= len(evidence.strip()) <= 500:
        raise RecoveryRejected("missing_operator_evidence")
    if not isinstance(request_id, str) or not 1 <= len(request_id) <= 256 or not all(
        c.isascii() and (c.isalnum() or c in "_-") for c in request_id
    ):
        raise RecoveryRejected("invalid_request_id")
    return Job("queued", job.request_hash, request_id)


def bind_with_provider_verification(
    job, *, request_id, recovery_request_hash, verify_provider_request
):
    """Fail-closed application gate; never accept caller-supplied attestations.

    verify_provider_request is a *trusted server-side* adapter that must check the
    provider's authenticated request lookup and independently persisted correlation.
    This function does not make a network request and does not authorize SQL writes.
    """
    if job.state != "submission_unknown" or job.provider_request_id is not None:
        raise RecoveryRejected("invalid_state")
    if not isinstance(recovery_request_hash, str) or recovery_request_hash != job.request_hash:
        raise RecoveryRejected("missing_correlation")
    if not isinstance(request_id, str) or not 1 <= len(request_id) <= 256 or not all(
        c.isascii() and (c.isalnum() or c in "_-") for c in request_id
    ):
        raise RecoveryRejected("invalid_request_id")
    if not callable(verify_provider_request):
        raise RecoveryRejected("provider_verification_unavailable")
    try:
        verified = verify_provider_request(request_id, recovery_request_hash)
    except Exception as exc:
        raise RecoveryRejected("provider_verification_failed") from exc
    # Only the exact True value is accepted: never trust truthy dicts, strings,
    # HTTP 200 responses, or an unverified provider status payload.
    if verified is not True:
        raise RecoveryRejected("provider_verification_failed")
    return Job("queued", job.request_hash, request_id)
