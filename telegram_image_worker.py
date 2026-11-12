"""STEP 3 — durable AI Image generation worker (production shape).

Mirrors the reviewed MyrVideoWorker lifecycle for images:
  reserve → claim → (durable SUBMISSION_UNKNOWN) → POST once (via the
  WorkerSubmissionGate no-retry protocol) → poll via GET → deliver via
  TelegramImageDelivery (sendPhoto, ack) → settle/refund through the store.

Fail-closed everywhere: timeouts/ambiguous outcomes hold the job for
operator reconciliation; never a blind resubmit, never an auto refund.
No provider, wallet or Telegram action occurs at import time.
"""
from __future__ import annotations

from uuid import UUID

from staging_job_worker import JobQuote
from step2_no_retry_protocol import Attempt, State
from step2_submission_gate import WorkerSubmissionGate
from video_myr_worker import JobError, queue_urls, request_hash, trusted_result_url


class MyrImageWorker:
    def __init__(self, store, provider, delivery, *, budget_id=None,
                 allow_external=False):
        self.store, self.provider, self.delivery = store, provider, delivery
        self.allow_external = allow_external is True
        self.budget_id = str(UUID(budget_id)) if budget_id else None

    # ── reservation ─────────────────────────────────────────────────────────
    def reserve(self, job_id, user_id, quote: JobQuote, arguments):
        q = quote.payload()
        if q["tool_key"] != "image":
            raise JobError("Unsupported tool")
        return self.store.action(job_id, "reserve", {
            "user_id": user_id, "quote": q, "arguments": arguments,
            "request_hash": request_hash(user_id, q, arguments)})

    # ── submission (no-retry gate; the ONLY path to a provider POST) ────────
    def submit(self, job_id, arguments):
        if not self.allow_external:
            raise JobError("External provider submission disabled")
        job = self.store.action(job_id, "get")
        q = JobQuote(**job["quote"]).payload()
        if q["tool_key"] != "image":
            raise JobError("Unsupported tool")
        if request_hash(job["user_id"], q, arguments) != job["request_hash"]:
            raise JobError("Job arguments do not match reservation")
        claim = self.store.action(job_id, "claim_submit",
                                  {"budget_id": self.budget_id})
        if claim.get("claimed") is not True:
            return claim
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
            raise JobError(
                "Submission outcome unknown; no retry or refund performed") from None
        try:
            request_id = bound.provider_request_id
            recovery = queue_urls(q["provider_model_id"], request_id,
                                  post_response["status_url"],
                                  post_response["response_url"])
            return self.store.action(job_id, "queued", recovery)
        except Exception:
            raise JobError(
                "Submission outcome unknown; no retry or refund performed") from None

    # ── polling (GET only; never a second POST) ─────────────────────────────
    def poll(self, job_id):
        if not self.allow_external:
            raise JobError("External provider polling disabled")
        job = self.store.action(job_id, "get")
        if job["state"] != "queued":
            return job
        try:
            recovery = queue_urls(job["quote"]["provider_model_id"],
                                  job["provider_request_id"],
                                  job["queue_status_url"], job["queue_result_url"])
            status = self.provider.status(recovery["queue_status_url"])
            if status.get("request_id") != job["provider_request_id"]:
                raise JobError("Provider status request mismatch")
            if status.get("error") or status.get("error_type"):
                if status.get("status") != "COMPLETED":
                    raise JobError("Nonterminal provider error held")
                return self.provider_failed(job_id, job["provider_request_id"])
            if status.get("status") in ("IN_QUEUE", "IN_PROGRESS"):
                return job
            if status.get("status") != "COMPLETED":
                raise JobError("Unexpected provider status")
            result = self.provider.result(recovery["queue_result_url"])
            urls = [img["url"] for img in result.get("images", [])]
            expected = job["arguments"].get("num_images", 1)
            if len(urls) != expected:
                raise JobError("Unexpected number of output images")
            for u in urls:
                trusted_result_url(u)
            return self.store.action(job_id, "succeed", {
                "provider_request_id": job["provider_request_id"],
                "result_urls": urls})
        except JobError:
            raise
        except Exception:
            raise JobError(
                "Provider result unavailable; job held") from None

    def provider_failed(self, job_id, provider_request_id):
        return self.store.action(job_id, "provider_failed", {
            "provider_request_id": provider_request_id})

    # ── delivery (sendPhoto; claim-once; ambiguous hold) ────────────────────
    def deliver(self, job_id):
        if not self.allow_external:
            raise JobError("External Telegram delivery disabled")
        job = self.store.action(job_id, "get")
        if job["state"] != "succeeded":
            return job
        urls = [trusted_result_url(u) for u in job["result_urls"]]
        for url in urls:
            claim = self.store.action(job_id, "claim_delivery")
            if claim.get("claimed") is not True:
                return claim
            try:
                message_id = self.delivery.send(job["user_id"], "image", url)
                self.store.action(job_id, "delivered", {
                    "delivery_id": str(message_id), "result_url": url})
            except Exception:
                try:
                    self.store.action(job_id, "delivery_unknown")
                except JobError:
                    pass
                raise JobError(
                    "Delivery outcome unknown; no duplicate send") from None
        return self.store.action(job_id, "get")

    # ── bounded recovery (restart-safe; no new submissions for unknowns) ────
    def recover_once(self, limit=20):
        if not self.allow_external:
            raise JobError("External recovery disabled")
        rows = self.store.recoverable(limit)
        outcomes = []
        for row in rows:
            job_id = None
            try:
                job_id = str(UUID(row["job_id"]))
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
