# Production AI Video progress — 12 November 2026 MYT

LAUNCH STATUS: **NO-GO**. Source candidate only. No production database changes, no deployment,
no customer order/wallet mutation, no paid provider or Telegram request in this iteration.

## Owner decisions

- BLOCKED: both existing receipts remain unverified. Do not approve, reject, cancel, delete or
  change either order or customer wallet. Only owner bank evidence can resolve reconciliation.
- Authorized provider tests: RM5 TOTAL, at most 5 paid generations, stop at either limit.
  No credit purchases, provider top-ups or auto top-up. Existing authorized balance/access only.
  Exact worst-case model/parameters, FX and additional costs must be verified before any request.

## Verified evidence

| Component | Status | Evidence and limits |
| --- | --- | --- |
| PR43 / PR44 audit | PASS | PR43 merged e8712cb; PR44 draft ea0c093. PR44 syntax and host/frontend CI PASS. Neither establishes deployed payment behavior. |
| Real MYR job transaction | PASS | Candidate `berry_video_myr_lifecycle.sql` executed only in isolated cirsdvkfkvypprnmyykk, with entire DDL + fixtures rolled back. Uses existing public.ai_wallets and ai_wallet_apply_transaction; no synthetic wallet replacement. |
| Debit/refund invariants | PASS | Actual SQL asserts debit once, frozen prompt/quote replay, overspend rollback with no orphan job, refund once and MYR ledger reconciliation. Not production concurrency/load evidence. |
| Durable submission/delivery claims | PASS | SQL claim-once and ambiguous submission refund denial; Python regression tests concurrent submissions/deliveries, GET polling after restart and timeout holds. Provider/Telegram traffic mocked in automated tests. |
| Budget guard | PASS | Actual SQL asserts consumed cost/count do not repeat, exhausted grant cannot claim, max RM5/5 constraints, service worker cannot expand grant. No grant created outside rollback fixture. Unknown outcomes retain full worst-case reserved budget. |
| Audit evidence | PASS | Failure evidence and bound request/budget/delivery metadata saved in private append-only-for-worker event table. Terminal provider failure needs matching request plus evidence. No automatic unknown resolution. |
| Telegram transport | PASS | Automated tests verify sendVideo acknowledgment/recipient, URL restriction, negative ACK and redacted error. NOT real Telegram delivery. |
| Unit regression | PASS | 54 local tests: 15 worker/delivery + 4 provider + 27 payment + 6 topup + 2 restart safety checks. An initial local provider-test failure (SOCKS environment at constructor) was fixed by lazy client initialization; rerun PASS. |
| Startup queued-update preservation | PASS | Source patch removes early import-time Telegram close/deleteWebhook calls and preserves pending updates on webhook removal/polling restart. Two source safety checks PASS. Not deployed or live-restart validated. |
| Production migration | BLOCKED | Verify recoverable backup, schema compatibility and explicit high-risk migration confirmation. Source is not executed in production. No duplicate order disposition required by this candidate; checkout PR44 remains independently blocked. |
| Bot menu/confirmation and continuous worker runtime | IN PROGRESS | New worker is not imported/enabled by bot. Customer callback identity, durable confirmation binding, pricing expiry, controlled startup still required. Bounded recovery listing/loop implemented with stop event, deduplication, failure isolation and no automatic unknown recovery; no scheduler is started. |
| Live provider costs / RM1 NET | BLOCKED | Public model page did not expose a parameter-bound price in retrieved content. No quote invented. Need account-authorized price, FX/fees/tax/retry/operating allocation and existing balance verification. The SQL arithmetic threshold is not independent net-margin proof. |
| Real E2E | BLOCKED | Authorized controlled Telegram identity/runtime and provider access without reading secrets, real cost bound and security/rotation gates not established. RM5 budget alone does not authorize bank payment or customer wallet edits. |
| Security / rollout | BLOCKED | Exposed-key secure rotation and production security signoff incomplete. No launch or activation. |

## Impact and rollback

Candidate adds only private jobs, events, budget grants and one service-only RPC. Reserves debit in
same transaction as job insert; uses existing ledger idempotency keys scoped to tenant/job. DDL
is transactional; a failure rolls back all DDL. Runtime effects default OFF. No customer-order SQL.
Before production migration: verify backup/restore metadata, review locks/FKs/privileges and actual
schema, then obtain specific confirmation. Post-commit rollback: disable external worker first,
retain jobs/events and ledger; revert app only after handling in-flight jobs. Never reverse ledger
entries or drop audit tables blindly. Existing unknown submissions/deliveries require audited
reconciliation; neither automatic resubmit nor blind refund is implemented.

NEXT ACTION: review candidate and CI; wire authenticated Telegram confirm/cancel to durable MYR
jobs while gates remain disabled. Complete real cost/access/rotation/test-identity gates before
seeding any budget grant or issuing paid request. Reconciliation stays BLOCKED pending owner evidence.
