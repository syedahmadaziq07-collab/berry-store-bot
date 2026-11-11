# Berry Store soft launch tracker

Updated 12 November 2026 MYT. Owner target: staging today, 12 November; final report before 08:00 13 November MYT.
Current customer launch decision: **NO-GO**. Production is unchanged.

| Area | Status | Evidence / remaining work |
| --- | --- | --- |
| Backend regression suite | PASS | 107 tests in isolated Python environment; all passed. Mock-backed contracts, not customer E2E. |
| Durable staging job lifecycle | PASS | Separate synthetic MYR cent wallet and immutable quote/ledger. Actual SQL rollback suite passes claim-once, request binding, definitive-failure refunds, ambiguous-outcome hold and ledger reconciliation. Worker tests cover concurrent submits/deliveries and restart/retry safety. External calls disabled by default. Not wired into customer bot. |
| Frontend | PASS | 16 tests, TypeScript check and production asset build. |
| Public staging routes/auth guards | PASS | 12 menu shells and 14 unauthenticated API guards; evidence/soft-launch-public-audit-20261112.json. |
| Wallet quote precision | PASS | Quotes now use common unit of 25 credits = RM0.02; avoids RPC rejecting sub-cent amounts. 1,001 cost cases tested. |
| Cost validation | PASS | Negative individual costs cannot cancel positive costs; nonfinite values rejected. |
| Staging synthetic reservation/refund | PASS | Actual Supabase SQL with assertions: replay debit once, conflicting key rejected, insufficient balance rejected, repeated refund restores original balance. Entire transaction rolled back. |
| Concurrent synthetic reserve/refund | PASS | Staging RPCs serialized by tenant/job advisory lock. Eight simultaneous duplicate reservations all succeeded with one debit; eight duplicate refunds restored balance once. Eight different 1,000-credit jobs against 5,000 credits accepted five and rejected three. Synthetic-credit prototype only; not the customer MYR ledger. |
| Supabase security | PASS | Staging advisor has only informational RLS/no-policy notices, consistent with service-only tables; not a production security signoff. |
| Staging pricing release | PASS | PR #36, commit 29e28fcb, Render dep-dbq9j2l6e07s73fgm41g LIVE. Post-deploy: 12 shells and 14 auth guards PASS. Pricing modules remain preparatory code; no customer billing activated. |
| Dashboard authenticated E2E | BLOCKED | No authenticated browser session is available in this workspace. Public shells are not evidence of working business operations. |
| Isolated shop/payment fixtures | BLOCKED | AI staging has private mapping/test wallets and empty AI catalogue; no complete isolated shop/order/wallet schema. Dashboard business reads remain separately configured; do not mutate production data. |
| Telegram bot E2E | BLOCKED | No dedicated staging Telegram bot runtime/session confirmed. Never start production-token polling. |
| Real provider generation/delivery | BLOCKED | Paid inference budget/approval and staging bot access required; no billable calls made. Durable job lifecycle, delivery retries and ambiguous provider outcomes remain unverified. |
| Minimum RM1 net profit | BLOCKED | Arithmetic only enforces margin on supplied costs. Provider model/size/duration pricing, FX, payment fees, refunds/retries and operating allocation not independently verified. Existing mapping credit prices are not authorization to generate. |
| Real top-up/payment | BLOCKED | Owner approval required; receipt verification and payment-to-wallet E2E incomplete. Keep disabled. |
| Production rollout | BLOCKED | Owner approval required after review of E2E evidence. |

## Work priority

1. Merge safe pricing/validation and full-suite CI into staging only; deploy and verify.
2. Repair concurrent reservation semantics in isolated test schema and prove parallel replay/overspend handling.
3. Prepare an isolated complete shop/order/MYR ledger fixture; integrate durable job reservation, settlement and refund with immutable quote snapshots.
4. Use a dedicated staging Telegram bot and authorized test account for real E2E; validate timeouts, duplicate updates, delivery failure and restart recovery.
5. Verify all-in model costs and obtain a bounded provider test budget before billable inference.
6. Run authenticated dashboard/browser and Telegram-to-provider-to-delivery E2E. Keep each unsupported operation disabled.
7. Publish GO/NO-GO with exact evidence. No customer launch based solely on tests with mocks or LIVE deploy status.

Report automation scheduled for approximately 08:00 MYT on 13 November 2026. Scheduling the report does not imply a continuous background coding process.

## Latest findings

- Mapping revision 4 has image and video both disabled. Image has an obsolete 4-credit placeholder price; video has zero price. Neither is safe to enable.
- Production service key previously pasted into chat requires owner-approved rotation and coordinated service updates before security signoff. No key was read or rotated during this work.
- Dedicated synthetic concurrency fixture (tenant aaaaaaaa-2222-4222-8222-222222222222, user 900000002) remains in AI staging. Cleanup DELETE confirmation expired; no customer data or money is involved. Do not claim cleanup completed.
- Current blockers needing owner input: authenticated staging dashboard session; dedicated staging Telegram bot token through secure configuration; bounded provider test spend. Production and real payments remain approval-gated.
