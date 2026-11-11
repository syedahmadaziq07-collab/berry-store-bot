"""Bounded recovery iteration; no scheduler, submissions or refunds are started."""
from uuid import UUID
from staging_job_worker import JobError


def recover_batch(worker, job_ids):
    if worker.allow_external is not True:
        raise JobError("External recovery disabled")
    if not isinstance(job_ids, (list, tuple)) or len(job_ids) > 20:
        raise JobError("Recovery batch must contain at most 20 jobs")
    # Validate the whole batch before any external action; deduplicate updates.
    try:
        ids = list(dict.fromkeys(str(UUID(value)) for value in job_ids))
    except (ValueError, TypeError, AttributeError):
        raise JobError("Invalid recovery job identifier") from None
    results = []
    for job_id in ids:
        try:
            job = worker.poll(job_id)
            if job["state"] == "succeeded":
                job = worker.deliver(job_id)
            results.append({"job_id": job_id, "state": job["state"], "result": "PASS"})
        except Exception:
            # One unavailable provider/job must not discard other ready deliveries.
            # No raw exception, URL, prompt or credential is included in results.
            results.append({"job_id": job_id, "state": "reconcile", "result": "BLOCKED"})
    return results
