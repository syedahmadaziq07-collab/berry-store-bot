# Berry Store STEP 3 — AI Image integration progress

Base: `deploy/berry-ai-private-mapping-staging-20261111` (PR #75 included).
Branch: `feat/step3-ai-image-consent-20261112`.

**Status: IN PROGRESS / NO-GO for customer image generation.**

## STEP 3 objectives (from the verified roadmap, not invented)
The 12-step roadmap is recorded in `docs/soft-launch-progress.md` and the
STEP 1 audit matrix (`docs/step1-ai-image-video-audit.md`): STEP 1 = Image/Video
audit; STEP 2 = reconciliation & provider readiness; the next P0 gap group is
the **AI Image integration** (STEP 1 audit IDs I02/I04/I11, all P0, owner
GPT WORK): validated image prompt workflow with receipt precedence (I02),
image consent/expiry/ownership/idempotency ticket flow (I04), and
sendPhoto/document image delivery with acknowledgment/unknown handling (I11).

## Implemented (this branch)
- `telegram_image_flow.py` — `TelegramImageFlow` + `VerifiedImageOffer`:
  image-specific controlled ticket flow mirroring the video-only pattern
  (controlled test identity, enabled=False default, prompt 1–1500 chars,
  aspect 1:1/16:9/9:16/4:3/3:4, count 1–4, frozen quote via
  `staging_job_worker.JobQuote` (image-capable), request-hash binding,
  confirm requires enabled worker + budget, prepare never debits).
- `telegram_image_delivery.py` — `TelegramImageDelivery` (sendPhoto):
  recipient/tool validation, trusted fal.media URL only, Telegram ack
  verification (ok/message_id/chat), token-bearing URLs never raised in
  errors; ambiguous outcomes held for reconciliation, never resent blindly.
- Tests: `tests/test_telegram_image_flow.py` (8/8) and
  `tests/test_telegram_image_delivery.py` (6/6), all local PASS, mocked
  transport, zero network/wallet/paid calls.
- CI: `.github/workflows/step3-image-consent.yml` (py_compile + both suites).

## Update 1 — SQL tickets, parameter-bound offers, lifecycle wiring (commit 2)
- `docs/sql/berry_image_consent.sql` (I04): durable `berry_private.ai_image_tickets`
  table + `public.berry_image_checkout` RPC mirroring the verified video
  pattern (service-role only, RLS, advisory ticket lock, prepare idempotent
  replay check, owner mismatch, cancel-before-confirm, expiry ≤15 min,
  tool_key='image' enforced). **CANDIDATE ONLY — not applied to any database**;
  `confirm` on a pending ticket is fail-closed (`image job reservation not yet
  enabled`) until job wiring is approved — it never silently skips the debit.
- `docs/sql/verify_image_consent.sql`: isolated rollback-only verification
  script (CI ephemeral pattern): idempotent prepare, stolen-callback and
  cancelled-ticket rejection, fail-closed confirm, replay conflict, ACL
  denial. Not executed against live Supabase.
- `telegram_image_offer_builder.py` (I03): `VerifiedImageOfferBuilder` builds
  frozen offers from a reviewed server catalog — model, aspect (1:1/16:9/9:16/
  4:3/3:4), count 1–4, integer-cent pricing scaled by count with margin floor
  ≥100 cents, expiry ≤900 s; invalid catalogs/aspects/expiry rejected
  fail-closed. Callable interface for the flow.
- `telegram_image_flow.py` upgraded: prepare persists through the durable
  store checkout adapter (mirroring video `TelegramVideoFlow`), confirm checks
  the pending state and requires enabled worker + budget, cancel routes
  through checkout. All transitions via `store.checkout` — no direct state.
- Tests: `test_telegram_image_flow.py` expanded to 14 cases (concurrent
  confirm ×8, replay idempotency, cancel-before-confirm, owner mismatch,
  expired quote, price scaling/margin floor, catalog validation, identity
  gating) + 6 delivery cases = 20/20 PASS locally, zero network/wallet/paid
  calls. staging_job_worker suite still 22/22 (no regression).
- Remaining: image job reservation RPC wiring (needs approved runtime gate),
  ephemeral-Postgres CI job for `verify_image_consent.sql`, Telegram handler
  entry points. Still NO-GO; no migrations applied, no deployment.

## Update 2 — ephemeral PostgreSQL 16 CI evidence (commit 3)
- Fixed JSON typo (`}}` → `}`) in `docs/sql/verify_image_consent.sql`.
- New `tests/test_step3_image_consent_postgres.py` (12 cases): installs the
  candidate DDL in an isolated schema (roles DDL for service_role/anon/
  authenticated) and verifies — prepare idempotent (single row), replay with
  changed payload rejected, owner mismatch rejected, non-image tool_key
  rejected, invalid request_hash rejected, past expiry rejected, confirm
  fail-closed (`image job reservation not yet enabled`), cancel-then-confirm
  rejected, expired-ticket confirm rejected, **concurrent prepare ×4 → single
  row** (advisory lock), **wallet isolation** (no wallet table/function exists
  — debit structurally impossible), anon ACL EXECUTE denied.
- `.github/workflows/step3-image-consent.yml` gains an `image-consent-postgres`
  job (postgres:16 service, psycopg 3, `BERRY_STEP3_LOCAL_POSTGRES=1`),
  mirroring the step2-postgres-rollback pattern. 12 tests skipped locally
  (no local Postgres) — real evidence comes from CI only.
- Fail-closed review of builder/checkout adapter: VerifiedImageOfferBuilder
  rejects bad catalog/aspects/expiry/margin-floor; checkout enforces tool_key,
  request_hash format, expiry window, owner, replay, service-role JWT claim;
  confirm refuses pending tickets until job wiring is approved (never a
  silent debit skip). No issues remaining in the reviewed modules.

## Acceptance criteria (I02/I04/I11) and remaining blockers
- I02 prompt input: CODE COMPLETE (validated prompt + frozen ticket). Real
  Telegram input acceptance is a live E2E gate — BLOCKED on STEP 2 owner gates.
- I04 consent ticket: controller CODE COMPLETE; durable image ticket SQL
  (preview/no-debit, expiry, ownership, idempotency) still to be built on the
  video consent SQL pattern — NOT STARTED.
- I11 delivery: sendPhoto adapter CODE COMPLETE (mock-verified). Real
  Telegram delivery and image-result URL/size handling remain live E2E —
  BLOCKED on controlled identity approval.
- I03/I05–I08 (parameter-bound offer, MYR wallet integration, runtime):
  NOT STARTED; depend on STEP 2 pricing/entitlement verification.
- No production changes, migrations, wallet writes, paid generation or
  deployments on this branch.
