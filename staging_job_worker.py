"""Isolated staging job orchestration. Not imported or enabled by the customer bot.

Only synthetic wallets are supported. Paid inference/delivery remain off by default.
An ambiguous external response is NEVER resubmitted or refunded automatically.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from urllib.parse import urlparse
from uuid import UUID, uuid5

import httpx

STAGING_ORIGIN = "https://cirsdvkfkvypprnmyykk.supabase.co"


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
        if self.tool_key not in ("image", "video"):
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


class StagingJobStore:
    """Service-only RPC restricted to the known isolated staging project."""
    def __init__(self, url, key, tenant_id, client=None):
        if url.rstrip("/") != STAGING_ORIGIN or not key:
            raise JobError("Isolated staging job database required")
        self.tenant_id = str(UUID(tenant_id))
        self._url, self._key = STAGING_ORIGIN, key
        self._client = client

    def action(self, job_id, action, payload=None):
        job_id = str(UUID(job_id))
        if self._client is None:
            self._client = httpx.Client(timeout=15, follow_redirects=False)
        try:
            r = self._client.post(self._url + "/rest/v1/rpc/berry_staging_job",
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

    def close(self):
        if self._client is not None:
            self._client.close()


class StagingJobWorker:
    def __init__(self, store, provider, delivery, *, allow_external=False):
        self.store, self.provider, self.delivery = store, provider, delivery
        self.allow_external = allow_external is True

    def reserve(self, job_id, user_id, quote: JobQuote, arguments):
        q = quote.payload()
        return self.store.action(job_id, "reserve", {"user_id": user_id, "quote": q,
                    "request_hash": request_hash(user_id, q, arguments)})

    def submit(self, job_id, arguments):
        if not self.allow_external:
            raise JobError("External provider submission disabled")
        # Verify identity, exact frozen quote and arguments BEFORE claiming.
        job = self.store.action(job_id, "get")
        q = JobQuote(**job["quote"]).payload()
        if request_hash(job["user_id"], q, arguments) != job["request_hash"]:
            raise JobError("Job arguments do not match reservation")
        claim = self.store.action(job_id, "claim_submit")
        if claim.get("claimed") is not True:
            return claim
        # PR #75 integration: the WorkerSubmissionGate is now the sole path to
        # the provider POST. claim_fn durably persists SUBMISSION_UNKNOWN
        # BEFORE the network call; the gate allows exactly one POST and binds
        # the response to it. Any failure leaves the job held, never retried.
        from step2_no_retry_protocol import Attempt, State
        from step2_submission_gate import WorkerSubmissionGate
        post_response = {}

        def durable_unknown():
            self.store.action(job_id, "submission_unknown")
            return Attempt(State.SUBMITTING, generation=0)

        def provider_post():
            nonlocal post_response
            post_response = self.provider.submit(q["provider_model_id"], arguments)
            return post_response

        gate = WorkerSubmissionGate(durable_unknown, provider_post)
        try:
            bound = gate.submit(Attempt(State.SUBMITTING, generation=0))
        except Exception:
            # Fail-closed: POST error/timeout, or a failed durable-unknown commit,
            # both leave the job held; never a second POST or a refund.
            raise JobError("Submission outcome unknown; no retry or refund performed") from None
        try:
            request_id = bound.provider_request_id
            recovery = queue_urls(q["provider_model_id"], request_id,
                                  post_response["status_url"], post_response["response_url"])
            return self.store.action(job_id, "queued", recovery)
        except Exception:
            # Even a failure recording the successful HTTP response is ambiguous.
            # Persisted 'submission_unknown' (written before the POST) blocks replay.
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

    def provider_failed(self, job_id, provider_request_id):
        # Only definitive provider failure, never timeout/network errors.
        return self.store.action(job_id, "provider_failed", {"provider_request_id": provider_request_id})

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
