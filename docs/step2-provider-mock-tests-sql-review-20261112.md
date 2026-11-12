# STEP 2 — Mock-only provider safety tests and SQL reconciliation review
Date: 2026-11-12. Staging source and Supabase staging SQL definitions inspected read-only; no paid calls or wallet writes.

## SQL function findings
Read-only `pg_get_functiondef` inspection of `public.berry_video_job`, `public.berry_video_checkout`, `public.berry_video_reconcile` on isolated staging:
- `berry_video_job` serializes per-job transitions with advisory transaction lock and `FOR UPDATE`, validates quote minimum margin of 100 cents **against caller-provided all_in_cost_cents**, and uses an idempotent wallet debit on reservation. It cannot independently verify provider cost provenance.
- `claim_submit` atomically increments `berry_private.ai_video_test_budgets.reserved_cost_cents` and `reserved_generations` only when budget unexpired, within `max_generations` and `max_cost_cents`. This is a DB-side budget gate, **not** proof that a worker never bypasses it. There is no budget grant in staging snapshot (0 rows).
- `queued` validates provider request ID and recovery URLs; `submission_unknown` marks ambiguous outcome; `provider_failed` requires definitive failure evidence and matching provider request; refunds are forbidden for ambiguous jobs. `claim_delivery` and `delivery_unknown` track delivery uncertainty.
- `berry_video_reconcile` accepts operator evidence with strict fields, recent observed time, expected state and request hash; its full transition and concurrent behavior still need isolated transaction tests.
- The SQL is live in staging but **none of these state-mutating functions were invoked** in this audit, as requested.

## Mock tests in this PR
`tests/test_step2_provider_safety_mocks.py` tests the existing `provider_readiness.py` behavior using `httpx.MockTransport` only:
1. Pricing probe sends GETs to the fixed metadata endpoint and never follows redirects to a paid queue.
2. Pricing timeout does not cause a retry of the same model and redacts sensitive error text.
3. Production service identity prevents the staging startup probe from opening network.
4. Missing, zero, negative or non-finite billed duration is rejected before a retail bound is calculated.
5. Valid pricing metadata does not assert inference entitlement or a maximum billed duration.

These are **real executable mocked tests** of the current pricing probe, but they do NOT test worker polling, provider submission, callbacks, crash/restart recovery, delivery or SQL transaction idempotency. No complete provider worker was identified in the inspected staging source; adding simulated tests of a fictitious worker would provide misleading assurance.

## Outstanding test matrix
- Polling queued/running/complete/fail/cancel and backoff/timeout: BLOCKED until actual worker source and provider queue contract are identified.
- Restart recovery, stale leases, duplicate callbacks and delivery unknown: BLOCKED pending worker implementation plus isolated transaction rollback tests.
- SQL concurrent claims, budget exhaustion and RM5 hard cap: SQL logic inspected, but **NOT RUN**; verify budget grants capped to RM500 cents and worker authorization before paid use. RM5 is a ceiling, never spending permission.
- No live generation, no payment, no wallet mutations, no production access, no customer activation.

## Decision
**STEP 2 PARTIAL / NO-GO**. CI for mock tests can pass while worker/SQL integration remains unverified. Provider cost ceiling, effective FX, all-in OPEX and RM1 net margin are still blocked.
