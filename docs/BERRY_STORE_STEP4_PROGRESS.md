# Berry Store STEP 4 — shared display & wallet-safety progress

Base: `deploy/berry-ai-private-mapping-staging-20261111`.
Branch: `feat/step4-wallet-display-precision-20261112`.

**Status: IN PROGRESS / NO-GO for launch.**

## STEP 4 scope (from the verified roadmap, not invented)
The STEP 1 audit's Shared group remains after image/video integration:
- S01 (P1, GPT WORK): unify exact MYR/Berry-Credits balance display — the
  legacy My Wallet section int-truncates odd-cent balances (RM4.99 showed
  6,237 instead of 6,237.5). No dependencies on unapproved operations.
- S02 (P0): top-up/QR/receipt/approval real payment journey — BLOCKED on
  owner bank evidence and disputed orders; not safe to start.
- S03/S04 (P0): production migrations and reference-binding security —
  BLOCKED on explicit production approval.
- S05 (P1): authenticated dashboard monitoring — BLOCKED on owner login
  authorization.

## Implemented (this branch)
- `bot.py` My Wallet S01 fix: exact Decimal conversion
  (`Decimal(balance)*1250`, formatted `,.2f` then trailing-zero strip) —
  fractional credits now preserved (RM4.99 → `6,237.5 Berry Credits`),
  whole balances stay clean (`RM5.00` → `6,250`). Display-only change:
  MYR accounting units untouched, no wallet reads/writes, no RPC change.
- `tests/test_step4_wallet_display.py` (6/6 local PASS): odd-cent
  preservation, whole-balance formatting, thousands separators, display-only
  contract, non-numeric fallback raises.
- CI: `.github/workflows/step4-wallet-display.yml` (py_compile bot.py +
  suite).

## Acceptance and blockers
- S01 CODE COMPLETE + unit-verified. Live Telegram verification of the
  rendered wallet message requires the controlled staging bot identity
  (owner gate) — not claimed as PASS.
- S02/S03/S04/S05 remain BLOCKED on owner approvals as recorded in
  docs/step1-ai-image-video-audit.md.
