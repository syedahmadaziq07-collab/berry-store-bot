# STEP 2 — Isolated persisted mock-worker integration checkpoint
Date: 2026-11-12. **Test-only scaffold; not production/staging runtime wiring.**

## Design
`step2_mock_persisted_worker.py` is a SQLite-backed, dependency-injected fake worker harness. It is NOT imported by `admin_app.py` or `bot.py`, has no fal HTTP client, no Supabase client, no wallet and no customer-facing routes. It cannot make a paid generation call by itself. Its only provider dependency is a fake object passed in by tests.

A local `BEGIN IMMEDIATE` transaction atomically reserves a candidate cost under a max 500-cent cap and generation-count limit, before fake provider submission. It does **not** use the real Supabase `berry_video_job` budget RPC; the actual DB integration remains blocked/unverified.

Before calling the injected fake `submit`, the harness persists `submission_unknown`; if a timeout/crash occurs, restart does not resubmit automatically. A returned request ID binds to `queued`. Polling uses the existing PR #67 offline contract with bounded attempts; unknown/timeout status becomes `needs_review`. Completion becomes `result_pending`, not delivered/succeeded, because result fetch and delivery are not implemented.

## Tests
`tests/test_step2_mock_persisted_worker.py` exercises:
- Budget claim before any fake submission, exhaustion and full-cap arithmetic.
- Ambiguous submit timeout and restart without blind resubmit.
- Restart recovery using persisted request ID for polling.
- Unknown status requiring manual review.
- Poll-attempt exhaustion and duplicate claim refusal.

## Explicit limitations
- This is a **local mock integration test**, not a real worker, deployment, queue webhook, distributed lock, concurrent Supabase RPC, verified provider cost or paid budget grant.
- Crash window between an actual remote submit and recording the provider ID remains ambiguous and requires provider-side reconciliation; the harness intentionally blocks retries.
- Real staging DB and customer wallet tables were NOT written. No migration, deployment, secrets, paid generation, checkout or production modifications.
- RM5 is a hard **offline mock ceiling**, not spending permission. The real worker must call `public.berry_video_job(...,'claim_submit',...)` before any paid outbound request and must prove tenant, budget, quote provenance and idempotency independently.
- Missing provider max billable seconds, FX, fees, entitlement and RM1 net margin remain **BLOCKED**. Customer activation NO-GO.
