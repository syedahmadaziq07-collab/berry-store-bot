# STEP 2 — fal queue contract and isolated offline tests
Date: 2026-11-12. **Not wired to a running worker. No paid calls.**

## Provider documentation reviewed
Official https://fal.ai/docs/documentation/model-apis/inference/queue describes:
- POST submission to queue.fal.run, returning request_id and status/response URLs.
- Status values IN_QUEUE, IN_PROGRESS, COMPLETED; completed response may contain an error, so COMPLETED does **not** guarantee successful output.
- Queue processing may automatically retry runner failures up to 10 times; client timeout does not necessarily cancel server processing.
- Persist request_id for restart recovery. Webhooks can be retried; deduplicate using request_id.
- Cancel during IN_PROGRESS is best effort and may still complete.
- A POST timeout is ambiguous: do not blindly resubmit or refund.

## Existing implementation evidence
- GitHub staging source searches and attempted candidate worker paths did not identify a deployable fal video worker. `provider_readiness.py` is a pricing-only GET probe.
- Supabase staging `public.berry_video_job` has advisory transaction locks, idempotent reservation, state transitions, and budget reservation in `claim_submit`; `public.berry_video_reconcile` requires operator evidence. No DB mutation was performed.
- No proof exists that an actual worker calls `claim_submit` before any paid provider POST. RM5 hard cap remains unproven end-to-end.

## Offline test-only scaffold
- `step2_offline_queue_contract.py` contains **pure functions only**: bounded poll decision/backoff, request-ID correlation, fail-closed ambiguous submission, and conservative offline RM500-cent budget arithmetic.
- `tests/test_step2_offline_queue_contract.py` exercises queue statuses, unknown status/timeout budget, restart using the same request ID, ambiguous submit outcome, budget exhaustion and generation-count cap.
- This is a **simulation/contract test**, not actual worker integration, crash recovery, concurrency, callback, SQL transaction or provider authorization test. No network, DB or wallet access. Do not enable it in customer runtime.

## Important limitations / next work
- A persisted job state machine and worker must be implemented and tested in isolated staging with mocked provider transport, using the exact provider model route and response URL contract.
- The existing SQL `queued` URL validator must be checked against fal's documented `response_url` format and the exact selected model path before worker wiring. No unreviewed migration here.
- Budget must be checked atomically on real submission path; offline arithmetic does not enforce database budget.
- No provider-backed billed-duration ceiling, rate validity, FX/fees or inference entitlement. **STEP 2 PARTIAL / customer generation NO-GO**.
