"""Staging contract adapter with injected MOCK RPC/provider only.

No HTTP, Supabase client, wallet, credentials, or runtime integration.
Fail closed on unknown RPC outcome; never auto-resubmit a paid request.
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
        if not isinstance(result, dict) or result.get("state") is None:
            raise AdapterBlocked("rpc_contract_unknown")
        return result

    def claim_then_submit(self, tenant, job, budget_id):
        try:
            UUID(budget_id)
        except (TypeError, ValueError, AttributeError):
            raise AdapterBlocked("invalid_budget_identity") from None
        claimed = self._call(tenant, job, "claim_submit", {"budget_id": budget_id})
        if claimed.get("state") != "submitting" or claimed.get("budget_id") != budget_id:
            raise AdapterBlocked("claim_not_confirmed")
        # Durable uncertainty BEFORE outbound fake call. If this RPC is ambiguous,
        # no fake submit occurs. No retry is attempted.
        unknown = self._call(tenant, job, "submission_unknown", {})
        if unknown.get("state") != "submission_unknown":
            raise AdapterBlocked("unknown_state_not_confirmed")
        try:
            request = self.provider.submit(job)
        except Exception:
            return "submission_unknown"
        if not isinstance(request, dict) or not isinstance(request.get("request_id"), str):
            return "submission_unknown"
        payload = {
            "provider_request_id": request["request_id"],
            "queue_status_url": request.get("status_url"),
            "queue_result_url": request.get("response_url"),
        }
        try:
            bound = self._call(tenant, job, "queued", payload)
        except AdapterBlocked:
            return "submission_unknown"
        return bound["state"] if bound["state"] == "queued" else "submission_unknown"

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
