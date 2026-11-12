"""AI Video orchestration for the existing MYR wallet. Not enabled in the bot yet.

External effects remain OFF; deployment requires production DB/cost/security/E2E gates.
An ambiguous external response is NEVER resubmitted or refunded automatically.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass
from urllib.parse import urlparse
from uuid import UUID, uuid5

import httpx

DATABASE_ORIGINS = {"https://cirsdvkfkvypprnmyykk.supabase.co",
                    "https://gtqthdxltczovkiuoyyr.supabase.co"}


class JobError(RuntimeError):
    pass


@dataclass(frozen=True)
class JobQuote:
    tool_key: str
    provider_model_id: str
    mapping_revision: int
    credits: int
    debit_cents: int
    all_in_cost_cents: int
    cost_reference: str

    def payload(self):
        from fal_provider import FalProvider
        if self.tool_key != "video":
            raise JobError("Unsupported tool")
        FalProvider._model(self.provider_model_id)
        for value in (self.mapping_revision, self.credits, self.debit_cents, self.all_in_cost_cents):
            if type(value) is not int:
                raise JobError("Quote values must be integers")
        if (self.mapping_revision <= 0 or self.debit_cents <= 0 or self.debit_cents % 2
                or self.debit_cents > 999999999999 or self.all_in_cost_cents < 0
                or self.debit_cents - self.all_in_cost_cents < 100
                or self.credits * 100 != self.debit_cents * 1250
                or not isinstance(self.cost_reference, str) or not self.cost_reference.strip()
                or len(self.cost_reference) > 200):
            raise JobError("Invalid price or missing cost reference")
        return asdict(self)


def request_hash(user_id, quote, arguments):
    if type(user_id) is not int or user_id <= 0 or not isinstance(arguments, dict):
        raise JobError("Invalid job identity or arguments")
    try:
        body = json.dumps({"user_id": user_id, "quote": quote, "arguments": arguments},
                          sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError) as exc:
        raise JobError("Invalid generation arguments") from exc
    if len(body) > 64 * 1024:
        raise JobError("Generation arguments exceed limit")
    return hashlib.sha256(body).hexdigest()


def telegram_job_id(tenant_id, update_id):
    if type(update_id) is not int or update_id < 0:
        raise JobError("Invalid Telegram update id")
    return str(uuid5(UUID(tenant_id), "berry-generation:" + str(update_id)))


def trusted_result_url(value):
    try:
        p = urlparse(value)
        if (p.scheme != "https" or not p.hostname or
                not (p.hostname == "fal.media" or p.hostname.endswith(".fal.media"))
                or p.username or p.password or p.port or p.fragment):
            raise ValueError()
    except (ValueError, TypeError, AttributeError) as exc:
        raise JobError("Untrusted media result URL") from exc
    return value


def queue_urls(model, request_id, status_url, response_url):
    """Use the provider-returned root-app URLs, binding both to this request."""
    if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", request_id):
        raise JobError("Invalid provider request identifier")
    from fal_provider import FalProvider
    FalProvider._model(model)
    root = "https://queue.fal.run/" + "/".join(model.split("/")[:2]) + "/requests/" + request_id
    if response_url != root or status_url != root + "/status":
        raise JobError("Queue URL does not match model and request")
    return {"provider_request_id": request_id, "queue_status_url": status_url, "queue_result_url": response_url}


class MyrVideoJobStore:
    """Service-only RPC; no direct wallet table writes or balance conversion."""
    def __init__(self, url, key, tenant_id, client=None):
        if url.rstrip("/") not in DATABASE_ORIGINS or not key:
            raise JobError("Approved Berry database required")
        self.tenant_id = str(UUID(tenant_id))
        self._url, self._key = url.rstrip("/"), key
        self._client = client

    def action(self, job_id, action, payload=None):
        job_id = str(UUID(job_id))
        if self._client is None:
            self._client = httpx.Client(timeout=15, follow_redirects=False)
        try:
            r = self._client.post(self._url + "/rest/v1/rpc/berry_video_job",
                headers={"apikey": self._key, "Authorization": "Bearer " + self._key},
                json={"p_tenant": self.tenant_id, "p_job": job_id,
                      "p_action": action, "p_payload": payload or {}})
            r.raise_for_status()
            data = r.json()
            if not isinstance(data, dict) or data.get("job_id") != job_id or not isinstance(data.get("state"), str):
                raise ValueError()
            return data
        except (httpx.HTTPError, ValueError, TypeError):
            raise JobError("Job result unavailable; reconcile durable state before retrying") from None

    def recoverable(self, limit=20):
        if type(limit) is not int or not 1 <= limit <= 20:
            raise JobError("Invalid recovery limit")
        if self._client is None:
            self._client = httpx.Client(timeout=15, follow_redirects=False)
        try:
            r = self._client.post(self._url + "/rest/v1/rpc/berry_video_recoverable_jobs",
                headers={"apikey": self._key, "Authorization": "Bearer " + self._key},
                json={"p_tenant": self.tenant_id, "p_limit": limit})
            r.raise_for_status()
            data = r.json()
            if not isinstance(data, list) or len(data) > limit:
                raise ValueError()
            return data
        except (httpx.HTTPError, ValueError, TypeError):
            raise JobError("Recovery list unavailable") from None

    def close(self):
        if self._client is not None:
            self._client.close()


class MyrVideoWorker:
    def __init__(self, store, provider, delivery, *, budget_id=None, verified_costs=None, verified_until=None, allow_external=False):
        self.store, self.provider, self.delivery = store, provider, delivery
        self.allow_external = allow_external is True
        self.budget_id = str(UUID(budget_id)) if budget_id else None
        # Server-reviewed bindings: request hash -> all-in worst-case cost in MYR cents.
        # Never populate this from customer input or an unverified mapping row.
        self.verified_costs = dict(verified_costs or {})
        self.verified_until = verified_until

    def reserve(self, job_id, user_id, quote: JobQuote, arguments):
        q = quote.payload()
        return self.store.action(job_id, "reserve", {"user_id": user_id, "quote": q,
                    "arguments": arguments, "request_hash": request_hash(user_id, q, arguments)})

    def submit(self, job_id, arguments):
        if not self.allow_external:
            raise JobError("External provider submission disabled")
        # Verify identity, exact frozen quote and arguments BEFORE claiming.
        job = self.store.action(job_id, "get")
        q = JobQuote(**job["quote"]).payload()
        if request_hash(job["user_id"], q, arguments) != job["request_hash"]:
            raise JobError("Job arguments do not match reservation")
        if (not self.budget_id or type(self.verified_until) is not int
                or not time.time() < self.verified_until <= time.time() + 900
                or type(self.verified_costs.get(job["request_hash"])) is not int
                or self.verified_costs[job["request_hash"]] != q["all_in_cost_cents"]):
            raise JobError("Verified parameter-bound cost and approved test budget required")
        claim = self.store.action(job_id, "claim_submit", {"budget_id": self.budget_id})
        if claim.get("claimed") is not True:
            return claim
        try:
            response = self.provider.submit(q["provider_model_id"], arguments)
            request_id = response["request_id"]
            recovery = queue_urls(q["provider_model_id"], request_id,
                                  response["status_url"], response["response_url"])
            return self.store.action(job_id, "queued", recovery)
        except Exception:
            # Even a failure recording the successful HTTP response is ambiguous.
            # If this write also fails, persisted 'submitting' still blocks replay.
            try:
                self.store.action(job_id, "submission_unknown")
            except JobError:
                pass
            raise JobError("Submission outcome unknown; no retry or refund performed") from None

    def poll(self, job_id):
        """Resume a queued job after restart using GETs, never another submission.

        Error or expired output is held for reconciliation, never blindly refunded.
        """
        if not self.allow_external:
            raise JobError("External provider polling disabled")
        job = self.store.action(job_id, "get")
        if job["state"] != "queued":
            return job
        try:
            recovery = queue_urls(job["quote"]["provider_model_id"], job["provider_request_id"],
                                  job["queue_status_url"], job["queue_result_url"])
            status = self.provider.status(recovery["queue_status_url"])
            if status.get("request_id") != job["provider_request_id"]:
                raise JobError("Provider status request mismatch")
            if status.get("error") or status.get("error_type"):
                raise JobError("Provider failure requires definitive reconciliation")
            if status.get("status") in ("IN_QUEUE", "IN_PROGRESS"):
                return job
            if status.get("status") != "COMPLETED":
                raise JobError("Unexpected provider status")
            result = self.provider.result(recovery["queue_result_url"])
            if job["quote"]["tool_key"] == "image":
                if len(result["images"]) != 1:
                    raise JobError("Unexpected number of output images")
                url = result["images"][0]["url"]
            else:
                url = result["video"]["url"]
            return self.provider_succeeded(job_id, job["provider_request_id"], url)
        except Exception:
            raise JobError("Provider result unavailable; job held without resubmission or refund") from None

    def provider_succeeded(self, job_id, provider_request_id, result_url):
        # Caller must obtain a definitive provider result for the stored request.
        return self.store.action(job_id, "succeed", {"provider_request_id": provider_request_id,
                                 "result_url": trusted_result_url(result_url)})

    def provider_failed(self, job_id, provider_request_id, failure_evidence):
        # Only definitive provider failure, never timeout/network errors.
        return self.store.action(job_id, "provider_failed", {"provider_request_id": provider_request_id, "failure_evidence": failure_evidence})

    def deliver(self, job_id):
        if not self.allow_external:
            raise JobError("External Telegram delivery disabled")
        job = self.store.action(job_id, "get")
        # Terminal/ambiguous jobs are returned without another Telegram send.
        if job["state"] != "succeeded":
            return job
        url = trusted_result_url(job["result_url"])
        claim = self.store.action(job_id, "claim_delivery")
        if claim.get("claimed") is not True:
            return claim
        try:
            message_id = self.delivery.send(job["user_id"], job["quote"]["tool_key"], url)
            return self.store.action(job_id, "delivered", {"delivery_id": str(message_id)})
        except Exception:
            try:
                self.store.action(job_id, "delivery_unknown")
            except JobError:
                pass
            raise JobError("Delivery outcome unknown; no duplicate send or refund performed") from None

    def recover_once(self):
        """Bounded iteration; unknown outcomes are excluded from automatic recovery."""
        if not self.allow_external:
            raise JobError("External recovery disabled")
        rows = self.store.recoverable(20)
        if not isinstance(rows, list) or len(rows) > 20:
            raise JobError("Invalid recovery batch")
        seen, outcomes = set(), []
        for row in rows:
            job_id = None
            try:
                job_id = str(UUID(row["job_id"]))
                if job_id in seen:
                    continue
                seen.add(job_id)
                job = self.store.action(job_id, "get")
                if job["state"] == "reserved":
                    job = self.submit(job_id, job["arguments"])
                if job["state"] == "queued":
                    job = self.poll(job_id)
                if job["state"] == "succeeded":
                    job = self.deliver(job_id)
                outcomes.append({"job_id": job_id, "state": job["state"]})
            except Exception:
                outcomes.append({"job_id": job_id, "state": "held"})
        return outcomes

    def run_recovery(self, stop_event, interval_seconds=15):
        """Explicit runtime hook. Never starts on import; stop_event enables shutdown."""
        if type(interval_seconds) is not int or not 1 <= interval_seconds <= 60:
            raise JobError("Invalid recovery interval")
        if not self.allow_external:
            raise JobError("External recovery disabled")
        while not stop_event.is_set():
            try:
                self.recover_once()
            except JobError:
                pass  # No external retry of an ambiguous submission/delivery.
            if stop_event.wait(interval_seconds):
                break
