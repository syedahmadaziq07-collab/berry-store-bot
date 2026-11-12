"""Restricted operator reconciliation for SUBMISSION_UNKNOWN jobs.

Authorization + audit layer wrapping UnknownOutcomeReconciler. Properties:
  - Only pre-authorized operator identities (server-side allowlist) may act.
  - Every attempt (allowed or refused) is appended to a durable audit log
    record; the log itself never contains prompts, URLs, keys or refunds.
  - No blind provider retry: the only provider interaction is the existing
    GET status read performed by the wrapped reconciler; a refused request
    performs zero provider calls.
Fail-closed: any inconsistency raises JobError and the job stays held.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from video_myr_worker import JobError


class OperatorReconciliationAudit:
    """Append-only audit trail. Production writes go to the store; tests use
    an in-memory list. Records contain only identifiers and outcomes."""

    def __init__(self, sink=None):
        self._sink = sink if sink is not None else []

    def append(self, record):
        if not isinstance(record, dict) or set(record) != {
                "at", "operator_ref", "job_id", "case_id", "action", "decision"}:
            raise JobError("Invalid audit record")
        self._sink.append(dict(record))
        return record


class RestrictedOperatorReconciler:
    """Authorized, audited facade over UnknownOutcomeReconciler actions.

    operator_refs: exact-match allowlist supplied by server configuration.
    Never derived from request input.
    """

    ACTIONS = ("hold", "bind_request", "confirm_delivery")

    def __init__(self, reconciler, *, operator_refs, audit=None):
        if not isinstance(operator_refs, (set, frozenset, tuple, list)) or not operator_refs:
            raise JobError("Operator allowlist required")
        self._operators = frozenset(operator_refs)
        for ref in self._operators:
            if not isinstance(ref, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", ref):
                raise JobError("Invalid operator reference")
        self._reconciler = reconciler
        self.audit = audit if audit is not None else OperatorReconciliationAudit()

    def _authorized(self, job_id, case_id, action, operator_ref):
        now = datetime.now(timezone.utc).isoformat()
        base = {"at": now, "operator_ref": str(operator_ref), "job_id": str(job_id),
                "case_id": str(case_id), "action": str(action)}
        if operator_ref not in self._operators:
            self.audit.append(dict(base, decision="refused_unauthorized"))
            raise JobError("Operator not authorized for reconciliation")
        return base

    def hold(self, job_id, case_id, *, operator_ref, **evidence):
        base = self._authorized(job_id, case_id, "hold", operator_ref)
        case = self._reconciler.prepare_hold(job_id, case_id, operator_ref=operator_ref, **evidence)
        out = self._reconciler.apply(case)
        self.audit.append(dict(base, decision="applied"))
        return out

    def bind_request(self, job_id, case_id, receipt, *, operator_ref, **evidence):
        # Authorization FIRST: an unauthorized caller must never trigger the
        # read-only provider status GET inside prepare_bind_request.
        base = self._authorized(job_id, case_id, "bind_request", operator_ref)
        case = self._reconciler.prepare_bind_request(
            job_id, case_id, receipt, operator_ref=operator_ref, **evidence)
        out = self._reconciler.apply(case)
        self.audit.append(dict(base, decision="applied"))
        return out

    def confirm_delivery(self, job_id, case_id, receipt, *, operator_ref, **evidence):
        base = self._authorized(job_id, case_id, "confirm_delivery", operator_ref)
        case = self._reconciler.prepare_delivery(
            job_id, case_id, receipt, operator_ref=operator_ref, **evidence)
        out = self._reconciler.apply(case)
        self.audit.append(dict(base, decision="applied"))
        return out