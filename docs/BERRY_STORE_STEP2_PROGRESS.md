# Berry Store STEP 2 — verified checkpoint (2026-11-12)

**Status: PARTIAL / NO-GO for real paid AI video generation.**

## GitHub evidence
- PR #72 merged: exact staging SQL function snapshot compiled and tested against ephemeral PostgreSQL.
- PR #73 merged: fail-closed trusted provider verification gate and regression tests; NOT connected to production worker.
- PR #74 merged: read-only mock RPC recovery preflight and regression tests; NOT connected to production worker.
- Four GitHub Actions workflows passed on PR #74 head `a839b312d662bde90575cdde4b1156e9b2d76b56`.
- PR #74 staging merge commit: `cfffb735153a15f4e725fba18c695f736de4c56b`.

## Official provider API findings
- Queue submit: POST `https://queue.fal.run/{owner}/{app}/{path}` for 3-part endpoint IDs; response includes request_id and status/result URLs.
- Queue status: GET `https://queue.fal.run/{owner}/{app}/requests/{request_id}/status` requires **known request_id**.
- Queue result: GET `https://queue.fal.run/{owner}/{app}/requests/{request_id}`.
- Documentation inspected does NOT establish a request lookup by caller-supplied correlation hash or an exactly-once idempotency key for the submit endpoint. **Never assume either exists.**
- Public pricing page lists `minimax/h3-max-turbo/text-to-video` at USD 0.025/video second, while previous account-authenticated pricing observations differed. Account-specific applicability and full billed duration must be verified before paid launch.
- Sources: https://fal.ai/docs/api-reference/inference-api/queue/submit-path ; https://fal.ai/docs/api-reference/inference-api/queue/status ; https://fal.ai/docs/api-reference/inference-api/queue/result ; https://fal.ai/docs/documentation/model-apis/pricing ; https://fal.ai/pricing

## Blocking gaps
1. No provider-authoritative correlation for a submission whose POST response was lost; status lookup requires known request ID. Manual operator evidence is not cryptographic proof.
2. Existing staging SQL allows caller-supplied `recovery_evidence` in proposed migration. **Do not apply PR #70 proposed SQL as-is**.
3. No durable, production-integrated worker protocol proven to prevent duplicate paid submissions after unknown POST outcome.
4. No live staging migration, wallet write, paid generation, or Render deploy has been authorized or executed.
5. Provider account entitlement, pricing applicability, hard billing duration, FX/fees, RM1 net margin, and staging E2E are not verified.

## Next safe engineering tasks
- Build a provider-agnostic, durable *no-retry* submission state machine with operator hold for unknown outcomes.
- Ensure worker never submits a second POST after a durable claim, even after restart.
- Create ephemeral Postgres worker integration tests for crash before/after POST, timeout, concurrent claim, and tenant isolation.
- Design a restricted operator reconciliation route that cannot accept arbitrary user-supplied proof.
- Validate account-specific fal pricing with read-only authenticated endpoint; do not call paid inference.
- Request separate approval for live staging migration and any spending, wallet writes or deployments.

## 2026-11-12 update 2 — gate wired into StagingJobWorker.submit
- `staging_job_worker.StagingJobWorker.submit` now routes the provider POST
  through `step2_submission_gate.WorkerSubmissionGate` (PR #75 protocol):
  - Durable `submission_unknown` marker is persisted BEFORE the network POST
    (via `claim_fn`), fencing all competing workers.
  - The gate authorizes exactly one POST; the response is bound to that POST
    only (`provider_request_id`), then validated by `queue_urls` and persisted.
  - Any failure (POST timeout, malformed response, persistence failure) raises
    `JobError`; the job stays held with no second POST and no refund.
  - Net safety improvement: if the durable `submission_unknown` write itself
    fails, NO provider POST happens at all (previously one POST could occur).
- Test change: `test_response_persistence_failure_still_blocks_resubmission`
    updated to assert zero provider POSTs when the durable marker commit fails.
- Verification: test_staging_job_worker.py 22/22 OK, test_step2* suite 60/60
  OK (12 skipped require Postgres, unchanged), test_video_myr_worker.py 12/12 OK,
  test_step2_no_retry_protocol.py 6/6 OK. Python 3.13, no network/DB/paid calls.
- Still NO-GO for paid generation; no migration, wallet write, or deploy.

## 2026-11-12 update 3 — gate wired into MyrVideoWorker + Postgres fixtures
- `video_myr_worker.MyrVideoWorker.submit` now routes the provider POST through
  `WorkerSubmissionGate` (same PR #75 protocol as StagingJobWorker): durable
  `submission_unknown` before POST, exactly one POST, response bound to
  `provider_request_id`, validated by `queue_urls`, correlation tags checked
  before the POST, and any failure held without retry or automatic refund.
- New worker regression tests (`test_video_myr_worker.py`, +5): failed
  durable-marker write prevents any POST; malformed and non-dict provider
  responses hold in `submission_unknown` with no second POST; crash after POST
  (state forced to `submission_unknown`) never re-POSTs on restart; correlation
  tag mismatch blocks before POST. 17/17 OK.
- New isolated PostgreSQL 16 fixtures (`test_step2_postgres_rollback.py`, +3,
  CI-only with `BERRY_STEP2_LOCAL_POSTGRES=1`): durable unknown marker
  persisted before POST with claim/re-claim fencing; crash-after-POST binds
  the response exactly once; wallet single debit with refund-attempt blocked
  by CHECK constraint and no double debit on re-claim.
- `.github/workflows/step2-postgres-rollback.yml` now also runs the four
  no-retry gate worker suites in CI on the same job.
- Local verification: video_myr 17/17, staging worker 22/22, all step2 63/63
  (15 skipped require ephemeral Postgres — run in CI). Python 3.13, no
  network/DB/paid calls.
- Still NO-GO for paid generation; no migration, wallet write, or deploy.

## 2026-11-12 update 4 — CI failure fixes (workflow run 43239066961)
- Fixed `pg_temp.claim_submit` PL/pgSQL: `UPDATE ... RETURNING id` without a
  destination raised `query has no destination for result data`. Now uses
  `RETURNING id INTO v_row` with `v_row IS NULL` fencing — semantics unchanged
  (atomic claim to `submission_unknown`, re-claim refused).
- Fixed `test_wallet_single_debit_and_no_refund_on_unknown`: the original
  assertion `used=used-400` is schema-legal (result 0 satisfies CHECK(used>=0)),
  so `CheckViolation not raised` was a faulty test expectation, not a safety
  gap. Corrected to assert the over-refund (401 > 400 balance) is rejected by
  CHECK, the budget is untouched after rollback, and — the real safety proof —
  state fencing prevents any second claim/debit and the job never returns to
  `reserved`, so no code path can double-debit or auto-refund.
- Local: step2 63/63 OK (15 CI-only Postgres skips), video_myr 17/17,
  staging worker 22/22, no-retry 6/6. Pushed for CI re-run on PR #76.

## 2026-11-12 update 5 — final review, operator reconciliation, pricing probe
Final code review of PR #76 (fencing/crash/wallet invariants) found:
- Atomic claim fencing: sound — claim_submit + durable submission_unknown
  before POST; re-claim refused; state fencing is the authoritative guard
  (gate generation is snapshot metadata, not the fence).
- Crash recovery: sound — restart on submission_unknown never POSTs; binding
  from unknown allowed once (queue_urls + request-id checks).
- Wallet invariants: sound — single debit on claim; no automatic refund path;
  over-refund schema-blocked; job never returns to reserved.
- Cosmetic fix: removed unused SubmissionBlocked import (no behavior change).
Remaining gaps (documented, not blockers for these commits): pricing
applicability/entitlement live verification and staging E2E remain unverified
and require owner approval.

New restricted operator reconciliation (`step2_operator_reconciliation.py`):
- `RestrictedOperatorReconciler` wraps `UnknownOutcomeReconciler` with an
  exact-match server-side operator allowlist; authorization is checked BEFORE
  the (read-only) provider status GET so an unauthorized caller triggers zero
  provider calls; every attempt is appended to an append-only audit record
  (identifiers + decision only — no prompts, URLs, keys or refunds); actions
  limited to hold / bind_request / confirm_delivery; no refund and no
  resubmission action exists. Tests: 7/7 OK
  (tests/test_step2_operator_reconciliation.py).

New read-only pricing probe (`step2_pricing_probe.py`):
- `FalPricingProbe` performs authenticated GETs ONLY to allowlisted
  read-only pricing paths on fal.ai (queue.fal.run/inference URLs are
  rejected); an exact numeric per-model price is accepted only from a valid
  parsed JSON document; invalid shapes, missing models, non-numeric prices,
  non-200 responses, redirects and network errors NEVER become an assumed
  cost (they raise). `verify_documented_cost_bound` rejects frozen cost
  bounds below the documented USD price converted with a server-configured
  FX rate. Tests: 11/11 OK (tests/test_step2_pricing_probe.py, mocked
  transport; no real requests, no inference).
CI: both new suites added to step2-postgres-rollback.yml job.
Local totals: step2 81/81 OK (15 CI-only Postgres skips), video_myr 17/17,
staging 22/22, reconciliation 10/10.

## 2026-11-12 update 6 — E2E preflight, pricing audit, evidence classification
New `step2_staging_preflight.py` (+5 tests, all pass): deterministic offline
E2E readiness gate with six checks — pricing verified, staging migration
applied, operator allowlist configured, worker runtime deployed, delivery
channel configured, budget ceiling ≤ RM5 in integer cents. Fail-closed with
exact reasons; a PASS authorizes nothing (E2E still needs owner approval).

fal.ai pricing documentation audit (read-only, docs page
https://fal.ai/docs/documentation/model-apis/pricing):
- Confirmed billing units: video models bill **per second or per video**;
  image per image/megapixel; others per request/compute seconds.
- Confirmed prepaid-credit model; queue time and server errors are free.
- The documentation states prices are queryable "programmatically through the
  Platform APIs" but the exact Platform pricing endpoint URL and response
  schema could NOT be extracted from the fetched page (client-rendered docs).
  **Therefore the probe's `https://fal.ai/api/pricing` path is an
  UNVERIFIED assumption and must not be cited as evidence.** Before any
  pricing claim, the operator must confirm the exact documented Platform API
  pricing endpoint and schema, then run the probe read-only. Currency
  handling: documentation prices are USD; MYR conversion requires a
  server-configured FX rate (probe enforces this and rejects bounds below
  documented price). Entitlement: documentation does not establish
  account-level entitlement; account applicability remains unverified.

Evidence classification (mock vs real) — current state:
- Mock/unit-verified (no real provider/DB): no-retry gate, worker submit/poll
  fencing, operator reconciliation authorization/audit, pricing probe
  parsing/fail-closed behavior, E2E preflight logic.
- Real database, isolated ephemeral PostgreSQL 16 (CI-only): claim atomicity,
  durable-unknown-before-POST, crash-after-POST single binding, wallet
  single-debit/no-refund CHECKs. NOT the real staging Supabase.
- Real staging Supabase evidence (read-only, prior PRs): table existence,
  zero-row snapshot, Render deploy metadata — NOT worker correctness.
- Real provider evidence: NONE. No authenticated pricing response, no
  entitlement, no queue response has ever been captured. Nothing in this
  branch claims real provider verification.

Operator reconciliation connection audit:
- `UnknownOutcomeReconciler.apply()` maps to the real staging RPC
  `public.berry_video_reconcile` (docs/sql/berry_video_unknown_reconciliation.sql,
  service-role only, RLS, evidence JSONB) — the SQL path exists and is
  CI-tested via clones, but the restricted facade
  (`step2_operator_reconciliation.py`) is NOT yet wired into any running
  staging service/daemon; there is no admin route or CLI entry point yet.
  Precise blocker: need an operator entry point (admin UI route or service
  command) + allowlist configuration + staging deployment, all requiring
  owner approval. Currently it is safely isolated and tested, not connected.

STEP 2 acceptance requirements and exact blockers:
1. No-retry submission protocol integrated — DONE (code+tests, PR #76).
2. Isolated PostgreSQL fencing/persistence evidence — DONE (CI ephemeral PG16).
3. Restricted operator reconciliation — code DONE; staging wiring BLOCKED on
   owner-approved operator entry point + deployment.
4. Account-specific pricing verification — BLOCKED: exact Platform pricing
   endpoint/schema unconfirmed; requires authenticated read-only call by the
   operator (no code change; the probe is ready once the endpoint is
   confirmed).
5. Entitlement & billed-duration hard max — BLOCKED: provider docs do not
   establish them; needs owner/provider confirmation.
6. FX/fees and RM1 net margin — BLOCKED: requires verified FX source +
   pricing verification (4).
7. Staging E2E (non-paid) — BLOCKED: preflight implemented; requires
   approved migration, worker deployment, delivery channel, budget config.
8. Live migration/wallet writes/paid generation/Render deploy — BLOCKED on
   explicit owner approval (never automatic).
Local totals after this update: step2 86/86 OK (15 CI-only skips).

## 2026-11-12 update — no-retry gate wired toward worker integration
- New `step2_submission_gate.py`: single sanctioned path from a submittable job
  to one provider POST, enforcing the PR #75 state machine (durable
  SUBMISSION_UNKNOWN before POST, exactly one POST authorization, response
  binding to the prior POST only, restart → poll/operator-hold, never a new POST).
- New tests `tests/test_step2_submission_gate.py` (10 cases, deterministic, no
  network/DB/paid calls): single POST + binding, claim commit failure blocks POST,
  non-Attempt claim result blocks POST, stale generation blocks POST,
  already-POSTed durable state blocks POST, malformed/non-dict response keeps
  hold with no retry, non-submittable states rejected pre-claim, constructor and
  snapshot validation. All pass locally (Python 3.13).
- New CI workflow `.github/workflows/step2-submission-gate.yml` mirrors the
  existing `step2-durable-no-retry.yml` pattern.
- Remaining integration gap (unchanged risk, now narrowed): `StagingJobWorker.submit`
  and `VideoMyrWorker.submit` still perform their own claim/POST sequence and must
  be refactored to route through `WorkerSubmissionGate`; plus ephemeral-Postgres
  crash/timeout/concurrency/tenant-isolation integration tests. Still NO-GO for
  paid generation; no migration, wallet write, or deploy performed.
