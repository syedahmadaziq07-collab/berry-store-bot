# Berry Store soft launch tracker

Updated 12 November 2026 MYT. Owner target: staging today, 12 November; final report before 08:00 13 November MYT.
Current customer launch decision: **NO-GO**. Production is unchanged.

Recovery batch follow-up: bounded, deduplicated recovery iterations implemented; one failed job cannot block other completed deliveries. External actions remain disabled by default. No scheduler or live bot started; this is not external E2E. Local suite: 134 tests PASS. PR #41 and packaging follow-up CI PASS; merged and deployed to staging. Recovery module is included and syntax-checked in the admin image; no scheduler starts.

| Area | Status | Evidence / remaining work |
| --- | --- | --- |
| Shop fixture source merge | BLOCKED | PR #42 head 0f1cdef: all three CI workflows queued with no safety-run jobs allocated. Fixture and tenant constraints are applied/tested ONLY in isolated Supabase staging; source merge awaits CI. GitHub public Actions status is operational as of the 12 November check, so queue root cause remains unknown. |
| Backend regression suite | PASS | 134 tests in isolated Python environment; all passed. Mock-backed contracts, not customer E2E. |
| Provider restart recovery | PASS | Queue status/result URLs are durably frozen and bound to model/request. Worker tests resume through GET-only polling; malformed/expired results stay held. Provider traffic mocked; no actual inference or live recovery loop tested. |
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
| Isolated payment/MYR fixture | PASS | Minimal tenants/orders fixture plus actual existing wallet and top-up approval RPCs installed in isolated staging. SQL rollback suite passes checkout replay, ownership, approval/receipt gates, MYR debit/refund, reference conflict and reconciliation. Full shop fixture and authenticated UI remain incomplete. |
| Telegram bot E2E | BLOCKED | No dedicated staging Telegram bot runtime/session confirmed. Never start production-token polling. |
| Real provider generation/delivery | BLOCKED | Paid inference budget/approval and staging bot access required; no billable calls made. Durable job lifecycle, delivery retries and ambiguous provider outcomes remain unverified. |
| Minimum RM1 net profit | BLOCKED | Arithmetic only enforces margin on supplied costs. Provider model/size/duration pricing, FX, payment fees, refunds/retries and operating allocation not independently verified. Existing mapping credit prices are not authorization to generate. |
| Real top-up/payment | BLOCKED | Dummy receipt-to-approval-to-credit contract PASS; bank/payment-provider verification and real Telegram payment E2E remain unverified. Keep disabled. |
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

## Atomic checkout follow-up

Top-up checkout now uses one service-only RPC rather than a read-then-insert race. Its stable Telegram-update key and per-user lock reuse active orders and reject changed ownership. Replayed completed orders never reopen payment, and waiting-approval orders never request another payment. The generic MYR ledger also binds replay to the original reference. Customer checkout flag remains disabled; migrations apply only to isolated staging.

## Latest verified release checkpoint (12 November MYT)

- PRs #38 (durable staging jobs), #39 (atomic checkout/MYR contract) and #40 (provider restart recovery) are merged into staging. All CI workflows on their reviewed heads passed.
- Application commit 40c5b62107081756f4ba09a08db49aa284e75200 is LIVE on Render deployment dep-dbqa6556e07s73ficc5g.
- Post-deploy public audit: 12 menu shells and 14 unauthenticated API guards PASS. No error-level logs in the immediate checked post-live interval. This is not authenticated business E2E or a long-duration stability test.
- Mapping revision 4 still has image/video disabled. No real payment, customer wallet mutation, production deploy or provider spend occurred.
- 129 Python tests PASS; frontend CI includes its 16 tests, type-check and build. Direct staging SQL verifies both private job lifecycle and the existing MYR wallet/top-up contract.
- Still IN PROGRESS: full shop fixture coverage, customer bot/job-wallet integration, continuous recovery scheduling and an audited unknown-outcome operator flow. Do not treat the isolated synthetic job wallet as the existing customer wallet.
- Still BLOCKED for actual external E2E: authenticated staging browser session, dedicated staging Telegram test bot/account, approved provider test budget, independent all-in cost verification.
- Hourly continuation is active with the staging target today and final GO/NO-GO report scheduled for 13 November at approximately 08:00 MYT. No unattended completion guarantee.

## Recovery batch release, 12 November MYT

PASS: 134 local backend tests and all four PR CI workflows. PR #41 merged; application 4154d472 LIVE at dep-dbqbfomi0phs73cj1vtg. Recovery module packaged and syntax-checked. No daemon, real provider/Telegram call or customer payment enabled. Post-live error logs empty in immediate check interval. External E2E and RM1 net margin remain BLOCKED; customer launch remains NO-GO.

## Isolated shop fixture checkpoint

PASS: staging-only products, variants, users, credential metadata, categories and settings schema added. All dashboard COLUMNS fields exist (0 missing). Actual SQL relation/access-control smoke suite PASS; test data rolled back. Eight dashboard integration contract tests PASS. No real account credentials stored, production data copied, dashboard configuration changed or writes enabled. This fixture is not a full production schema clone: live checkout/delivery and tenant-integrity semantics still need end-to-end verification. Authenticated browser E2E remains BLOCKED.

Tenant isolation follow-up PASS: composite foreign keys reject cross-tenant product references for variants, credentials and orders. Actual staging SQL rejection tests passed and rolled back. PR #42 is now merged at 1df8302; Render dep-dbqias2fngtc73fmf790 is LIVE. Its PR body retained the old queued note; do not infer a fresh CI PASS from that text.

## Real MYR video consent integration — 12 November MYT

IN PROGRESS: port PR45 controlled Telegram consent integration into staging without enabling it.
CODE COMPLETE source: bot Confirm/Cancel router, user-bound durable ticket, atomic existing MYR
job/debit on Confirm, no debit on preview, cancel-before-submit refund, provider terminal failure
refund, GET recovery, claim-once delivery and explicit recovery startup/shutdown hooks. Default
build_app has no live controller; no Telegram polling/runtime or paid generation is started.

PASS: actual isolated SQL lifecycle and consent rollback suites: ticket ownership, expiry, cancel,
duplicate confirm/debit, refund once, overspend rollback, unknown holds, budget caps and audit.
No customer wallet/order writes. Candidate uses public.ai_wallets / existing MYR RPC; synthetic
staging wallets remain separate and are not substituted. All candidate DDL/fixtures rolled back.
PASS: 71 focused production-candidate checks including actual PTB20.7 markup contract. Initial
host CI failure due missing Telegram UI test dependency fixed with separate pinned UI contract.
Full staging backend regression: 167 tests PASS. CI, packaging/deploy and post-deploy guards still IN PROGRESS. PR45 head 04025000 has all six CI PASS; its production PR remains draft and unmerged.

BLOCKED: authenticated dashboard session and controlled Telegram/provider access; verified model
maximum cost, FX/fees and RM1 NET; production backup/rotation/migration/real E2E/owner rollout approval.
Owner provider cap now RM5 total / at most 5 paid generations from existing authorized balance;
no purchase/top-up, and no spend without verified worst-case bound. Two unverified production
receipt orders remain untouched. Payment/generation disabled. LAUNCH NO-GO.

## Verified staging deployment — 12 November 2026, 11:39 MYT

- PASS: PR46 merged staging only, application 7b82f01bd17b60e3760c41419e1f758489e716cb.
  Render dep-dbqj9a2fngtc73fp57v0 LIVE at 03:38:52Z. No production merge/deploy.
- PASS: all eight CI workflows on reviewed head13131ce2924328e41c7bc3cd6d21c34c5b5e852c.
  167 complete staging backend tests; frontend16 tests/typecheck/build/audit in CI.
  PR45 candidate head3e03c3c9 has six CI PASS and117 backend tests; remains DRAFT/unmerged main.
- PASS: migration berry_video_myr_consent_staging_20261112 installed ONLY isolated project.
  Earlier DDL-validation transaction was rolled back; reviewed schema is now persisted for staging.
  Both actual SQL lifecycle/consent suites PASS after migration, dummy data rolled back.
  Post-test counts:0 jobs,0 tickets,0 budget grants,0 audit events. No customer money involved.
- PASS: public staging audit at03:39:09Z:12 shells +14 unauthenticated API guards.
  Evidence: docs/evidence/video-consent-public-audit-20261112.json. No error-level logs in
  checked immediate03:38:53Z–03:39:35Z interval. This is NOT authenticated business or Telegram E2E.
- PASS: mapping revision4 still has0 enabled image/video mappings. No controller or recovery daemon
  is started by normal bot/admin deployment. No provider request, Telegram send or payment activation.
- PASS (staging advisory scope): no WARN/ERROR notices;24 INFO RLS-with-no-policy findings for
  service-only tables. Documentation: https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy
- BLOCKED: actual account pricing endpoint requires authorized provider access; published model
  page alone did not establish a parameter-bound maximum. Pricing API documentation:
  https://fal.ai/docs/documentation/model-apis/pricing . No FX/fees/net-margin proof invented.
- BLOCKED: controlled Telegram identity and provider existing-balance/access; authenticated
  dashboard session; production backup/rotation/migration approval and actual E2E.
  Both unverified production receipt orders remain untouched. Owner budget is RM5 total/5 max;
  actual spend in this iteration RM0, paid generations0.

Readiness: consent source CODE COMPLETE for controlled text-to-video; database contracts and
admin packaging/public guards STAGING VERIFIED. Live bot/provider/delivery NOT VERIFIED.
PRODUCTION READY: NO. PRODUCTION LIVE: NO for these changes. Customer launch NO-GO.
Next safe work: audited unknown-outcome operator reconciliation and authenticated integration
coverage; exact model/cost/access proof before any paid attempt. Never enable from CI/LIVE alone.

Checkpoint for continuation: PR45 must remain draft until remaining runtime/cost/security/E2E
acceptance; staging deployment above is current. Do not create another runtime port/deploy of46.
No rollback of ledger rows or re-submission of unknown jobs is authorized. Production main and
customer money/orders remain restricted; latest directive requires explicit owner approval for
production merge/deploy. No secrets have been read/disclosed. Reuse this checkpoint and inspect
current branch/CI/deploy state before further writes.
