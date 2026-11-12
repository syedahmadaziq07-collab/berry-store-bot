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
