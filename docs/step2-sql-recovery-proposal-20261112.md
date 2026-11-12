# STEP 2 — Proposed guarded SQL recovery migration (NOT applied)
Date 2026-11-12. Staging database `cirsdvkfkvypprnmyykk` read-only inspected. No DB writes, wallet changes or paid generation.

## Verified live SQL
- `public.berry_video_job` is service-role protected, uses per-job advisory transaction lock and `FOR UPDATE`.
- `claim_submit` atomically increments the budget row with `reserved_cost_cents + all_in_cost_cents <= max_cost_cents` and generation count cap; budget table CHECK restricts `max_cost_cents` to 1..500. No budget rows were inserted or modified.
- `submission_unknown` cannot currently bind a newly recovered request ID with `queued`; a worker must never blindly resubmit.
- `reserve` and some refund actions write wallet; they were NOT called.

## Proposed, not executed
`docs/sql/step2_video_unknown_recovery_staging_proposed.sql` uses a fingerprint-checked, transactional `pg_get_functiondef` patch to add a narrowly guarded `submission_unknown -> queued` transition requiring operator-verified evidence, matching request hash, no prior provider ID and existing strict queue URL validation. The companion rollback restores the original branch using the exact migration fingerprint. Neither script is applied automatically.
- The operator evidence field is an **attestation**, not cryptographic provider proof. It must be verified out of band against actual fal queue request and tenant; do not enable auto recovery based on a caller-supplied string alone.
- This does **not** solve exactly-once submission across an external provider boundary, nor does it authorize provider POSTs. The worker remains disabled.
- SQL migration deployment requires a separate approved staging-only, transactionally isolated execution and manual evidence checks; do not run against live wallet jobs.
- No real SQL transaction test has run: CI tests are pure state-model and static SQL guards, not PostgreSQL execution or concurrency proofs. PostgreSQL rollback-safe integration tests remain outstanding.
- No production or Render deploy; customer generation remains NO-GO.

## Required future gates
- Review service-role access and operator identity/evidence provenance, provider URL model route, and migration fingerprint on isolated staging.
- Run PostgreSQL tests in rollback-only isolated fixture tenant with fake jobs and budgets **without wallet mutation**; verify concurrency and 500-cent exhaustion.
- Verify provider billed-duration hard max, entitlement, fees, FX, RM1 net margin. **STEP 2 PARTIAL**.
