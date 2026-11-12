"""Restricted operator reconciliation tests. No network, no DB, no paid calls."""
import unittest
from unittest.mock import Mock
from uuid import uuid4

from video_myr_worker import JobError
from video_reconciliation import UnknownOutcomeReconciler
from step2_operator_reconciliation import (
    OperatorReconciliationAudit, RestrictedOperatorReconciler)

JOB = str(uuid4())
CASE = str(uuid4())
EV = {"operator_ref": "ops.alice", "evidence_ref": "fal-account-export:2026-11-12",
      "evidence_sha256": "a" * 64, "reason_code": "hold"}

RECEIPT = {"correlation_tags": None, "provider_model_id": "fal-ai/wan/v2.2-5b/text-to-video",
           "provider_request_id": "fixture-1"}


class Store:
    def __init__(self):
        self.tenant_id = str(uuid4())
        self.job = {"job_id": JOB, "state": "submission_unknown",
                    "request_hash": "b" * 64,
                    "quote": {"provider_model_id": "fal-ai/wan/v2.2-5b/text-to-video"},
                    "submission_tags": {"berry_job": JOB, "berry_hash": "b" * 64,
                                        "berry_tenant": self.tenant_id},
                    "user_id": 900000088}
        self.applied = []

    def action(self, job_id, action, payload=None):
        if action == "get":
            return dict(self.job)
        raise JobError("unexpected store action " + action)

    def reconcile(self, job_id, case_id, action, evidence):
        self.applied.append((str(job_id), str(case_id), action, evidence))
        return {"job_id": str(job_id), "state": "held"}


def make_reconciler(store, **status_result):
    provider = Mock()
    status = status_result.get("status", {"request_id": "fixture-1", "status": "IN_QUEUE"})
    provider.status.return_value = status
    inner = UnknownOutcomeReconciler(store, provider, allow_reads=True)
    return inner, provider


class RestrictedReconcilerTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.inner, self.provider = make_reconciler(self.store)
        self.ops = RestrictedOperatorReconciler(self.inner, operator_refs=("ops.alice", "ops.bob"))

    def test_authorized_hold_applies_and_audits(self):
        out = self.ops.hold(JOB, CASE, **EV)
        self.assertEqual(len(self.store.applied), 1)
        self.assertEqual(out["state"], "held")
        record = self.ops.audit._sink[-1]
        self.assertEqual(record["decision"], "applied")
        self.assertEqual(record["action"], "hold")
        self.assertEqual(record["operator_ref"], "ops.alice")
        self.assertIn("at", record)

    def test_unauthorized_operator_refused_before_any_provider_call(self):
        ev = dict(EV, operator_ref="ops.mallory")
        with self.assertRaises(JobError):
            self.ops.hold(JOB, CASE, **ev)
        self.assertEqual(self.store.applied, [])
        self.provider.status.assert_not_called()
        record = self.ops.audit._sink[-1]
        self.assertEqual(record["decision"], "refused_unauthorized")

    def test_unauthorized_bind_request_never_touches_provider(self):
        ev = dict(EV, operator_ref="attacker", reason_code="correlated_provider_receipt")
        with self.assertRaises(JobError):
            self.ops.bind_request(JOB, CASE, dict(RECEIPT), **ev)
        self.provider.status.assert_not_called()
        self.assertEqual(self.store.applied, [])

    def test_authorized_bind_request_single_read_only_status_call(self):
        ev = {k: v for k, v in EV.items() if k != "reason_code"}
        receipt = dict(RECEIPT)
        receipt["correlation_tags"] = self.store.job["submission_tags"]
        case = self.ops.bind_request(JOB, CASE, receipt, **ev)
        self.assertEqual(case["job_id"], self.store.job["job_id"])
        self.provider.status.assert_called_once()
        url = self.provider.status.call_args[0][0]
        self.assertTrue(url.startswith("https://queue.fal.run/"))
        self.assertIn("/status", url)
        self.assertEqual(self.ops.audit._sink[-1]["decision"], "applied")

    def test_audit_rejects_malformed_records(self):
        with self.assertRaises(JobError):
            OperatorReconciliationAudit().append({"nope": 1})

    def test_constructor_requires_nonempty_valid_allowlist(self):
        for refs in (None, [], (), ("bad ref!",)):
            with self.assertRaises(JobError):
                RestrictedOperatorReconciler(self.inner, operator_refs=refs)

    def test_audit_sink_is_append_only_records(self):
        sink = []
        audit = OperatorReconciliationAudit(sink)
        audit.append({"at": "t", "operator_ref": "ops.alice", "job_id": JOB,
                      "case_id": CASE, "action": "hold", "decision": "applied"})
        self.assertEqual(len(sink), 1)
        # mutating the returned record must not alter the sink copy
        rec = audit.append({"at": "t2", "operator_ref": "ops.bob", "job_id": JOB,
                            "case_id": CASE, "action": "hold", "decision": "applied"})
        rec["decision"] = "tampered"
        self.assertEqual(sink[-1]["decision"], "applied")


if __name__ == "__main__":
    unittest.main()