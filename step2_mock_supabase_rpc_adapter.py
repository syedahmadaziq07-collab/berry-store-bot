"""Test-only Supabase RPC contract adapter with injected fake RPC.

No Supabase client, no provider HTTP, no wallet, no runtime wiring.
CRITICAL: staging SQL permits queued only from submitting, but
submission_unknown only from submitting; there is no safe durable
pre-submit marker that can subsequently bind a provider request.
Therefore this adapter NEVER calls provider.submit. Fail closed.
"""
from uuid import UUID
from step2_offline_queue_contract import classify_queue_status


class AdapterBlocked(RuntimeError):
    pass


class MockRpcVideoAdapter:
    def __init__(self, rpc, provider):
        if rpc is None or provider is None:
            raise AdapterBlocked("mock_dependencies_required")
        self.rpc, self.provider = rpc, provider

    def _call(self, tenant, job, action, payload):
        try:
            UUID(tenant); UUID(job)
        except (TypeError, ValueError, AttributeError):
            raise AdapterBlocked("invalid_identity") from None
        try:
            result = self.rpc.call("berry_video_job", {
                "p_tenant": tenant, "p_job": job,
                "p_action": action, "p_payload": payload,
            })
        except Exception:
            raise AdapterBlocked("rpc_outcome_unknown") from None
        if not isinstance(result, dict) or not isinstance(result.get("state"), str):
            raise AdapterBlocked("rpc_contract_unknown")
        return result

    def claim_only(self, tenant, job, budget_id):
        try:
            UUID(budget_id)
        except (TypeError, ValueError, AttributeError):
            raise AdapterBlocked("invalid_budget_identity") from None
        claimed = self._call(tenant, job, "claim_submit", {"budget_id": budget_id})
        if claimed.get("state") != "submitting" or claimed.get("budget_id") != budget_id:
            raise AdapterBlocked("claim_not_confirmed")
        return "claim_confirmed_mock_only"

    def submit(self, tenant, job):
        # Never call provider even after a confirmed fake budget claim.
        # A real worker needs an approved SQL state/lease protocol first.
        raise AdapterBlocked("durable_pre_submit_protocol_missing")

    def recover(self, tenant, job, attempt=0):
        state = self._call(tenant, job, "get", {})
        if state["state"] != "queued":
            return "needs_manual_reconciliation"
        request_id = state.get("provider_request_id")
        if not isinstance(request_id, str) or not request_id:
            return "needs_manual_reconciliation"
        try:
            status = self.provider.status(request_id)
            decision = classify_queue_status(status, request_id=request_id, attempt=attempt)
        except Exception:
            return "needs_manual_reconciliation"
        return decision.action
