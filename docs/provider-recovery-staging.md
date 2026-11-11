# Restart recovery for queued AI requests

Queued jobs now persist the provider-returned status/result URLs alongside the request ID.
Both the worker and database bind the URLs to the immutable quote's root model app and the
stored request. This is important for endpoint paths such as `fal-ai/flux/schnell`: queue
recovery uses the root app (`fal-ai/flux`), not the nested endpoint path.

`StagingJobWorker.poll(job_id)` reads a queued request's status and, only when completed,
fetches the result and records a validated image/video URL. A restarted worker does not
submit again. It rejects another request's status, different model URLs, unexpected numbers
of image outputs, and untrusted media URLs. A timeout, expired result or ambiguous provider
error holds the job without resubmission or automatic refund.

Source references checked 12 November MYT:
- https://fal.ai/docs/api-reference/inference-api/queue/submit-path
- https://fal.ai/docs/api-reference/inference-api/queue/status
- https://fal.ai/docs/api-reference/inference-api/queue/result

129 Python tests pass. Eight additional worker cases cover restart polling, in-progress
state, retrying GET after timeout, wrong request status, tampered recovery URL, malformed or
extra outputs, untrusted submit response and root-app handling for nested model endpoints.
Actual isolated Supabase SQL verification also passes model-bound URL rejection and durable
URL storage along with the existing lifecycle assertions. Test data rolls back.

This is a callable recovery operation, not a running daemon. Continuous queue scheduling,
live provider output retention, paid image/video runs, Telegram delivery and an audited
operator flow for unknown outcomes remain required before customer launch. All external
operations remain disabled by default, and no real inference was made in this release.
