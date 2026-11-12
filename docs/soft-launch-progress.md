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

## Provider identity audit — 12 November MYT

PASS: actual revision4 mapping identifies fal.ai / Wan2.2 A14B text-to-video, disabled,0 credits.
Gemini15s is UI preview; PixVerse3.5 is in legacy unmerged drafts. Do not confuse the Wan5B
regression fixture with the configured A14B model. Official A14B page announces4 January2027
removal. See docs/provider-audit-20261112.md for sources, exact endpoint and pricing limits.
PASS:169 full local backend tests. Presence-only startup metadata added; unit test proves that
only environment names are accessed, never secret values. IN PROGRESS: CI/staging deployment and
actual Render FAL_KEY present/absent observation. No public metadata API or production change.
BLOCKED: authenticated provider access/balance and exact cost/FX/fee bounds. No paid call.
NEXT: audited unknown-outcome reconciliation; controlled E2E stays gated. LAUNCH NO-GO.

## STEP 1/12 — complete Image/Video audit, 12 November MYT

PASS audit coverage32/32, NOT launch acceptance. Complete matrix with status/evidence/missing work,
GPT WORK/PEMILIK owner, P0/P1/P2 priority and PR/commit: docs/step1-ai-image-video-audit.md .
Structured evidence: docs/evidence/step1-ai-audit-20261112.json .169 backend tests +1 PTB contract
and compile PASS; fresh12 public shells/14 auth guards PASS. STEP1 DB checks were read-only.

Image: placeholder menu; missing prompt/consent/MYR job/delivery, synthetic/mock worker not real
acceptance. Actual FLUX Schnell mapping disabled4 credits (invalid for RM1 target/cent precision).
Video: controlled consent and isolated MYR contract exist; no runtime builder enabled or real E2E.
Wan A14B mapping disabled0 credits, not Gemini preview or Wan5B fixture. Live Render staging
FAL_KEY NAME present=true, without value access. Account/key validity/balance/max cost still unknown.
New production metadata gap: deployed wallet replay checks identity/amount/kind, not reference;
production private schema/checkout/video RPC absent. No production write or customer record touched.
Unknown reconciliation candidate saved WIP d215ebea, NOT validated/applied/deployed or counted PASS.
Production backup/rotation/real rollback and per-tool real E2E remain missing. Customer NO-GO.
Next milestone STEP2/12: close P0 reconciliation/runtime/provider-cost gaps; Image remains separate.

STEP1 follow-up source audit: production80655e2 still drops pending updates and has raw early HTTP
exception logging; staging fix is not deployed production. Actual production topup flag value is
unverified, not assumedOFF. Recovery fairness/thread shutdown are open verification gaps.

## STEP 2/12 — reconciliation and provider readiness

PARTIAL/NO-GO. See docs/step2-provider-runtime-readiness.md. PASS184 backend +1 pinned Telegram
markup; three actual isolated SQL rollback suites (lifecycle, consent, reconciliation). First new
SQL run FAIL PostgreSQL regex repetition bound; corrected and all reruns PASS. No fixture data
retained, RM0/0 paid generations. Correlated operator reconciliation adds no refund/resubmit action.
Recovery startup/shutdown now tested against duplicate tasks and orphaned in-flight thread.
IN PROGRESS PR/CI/staging migration/deploy and authenticated read-only pricing GET observation.
BLOCKED exact cost/FX/fees/RM1 NET/account balance and authorized Telegram identity. Customer flags
remain disabled; Image lifecycle still missing. Production/orders/customer wallets untouched.

STEP2 milestone PASS: PR50 merged5294c1a after6 CI PASS, deployed staging dep-dbqkm6qfngtc73ft8q30
LIVE13:14:49MYT. Isolated reconciliation migration installed; lifecycle/consent/reconciliation SQL
suites PASS afterinstall;0 jobs/cases/grants. PR52 closed as superseded old WIP, branch retained.
IN PROGRESS follow-up recovery fairness and pricing-gate diagnostics. Provider probe emitted no
pricing result, so authenticated access remains UNVERIFIED (not assumed rejected). RM0.

STEP2 PASS additional: PR53 mergedbe80ee39,4/4 CI, fairness migration installed isolated and all4
SQL suites PASS. LIVE dep-dbqko8qjnfac73906h60 at13:18:53MYT. Probe gate service_match=true,
database_match=false; no authentication result. Do not enable wallet runtime from service identity.
IN PROGRESS scope pricing GET to isolated AI mapping config, without altering business DB/settings.

STEP2 PASS PR54 deployed47f12cb0/dep-dbqkpkrbc2fs73dm9leg at13:22:07MYT,3/3 CI.
Actual AI mapping scope verified true. Authenticated read-only price attempts for FLUX/Wan/MiniMax
all UNVERIFIED with no HTTP status; do not infer invalid credentials. Diagnostic follow-up pending.
Mapping revision4 still0 enabled flags. SQL safety source/staging verified, real runtime/E2E blocked.

## Bounded staging continuation —12November18:50MYT

PASS fresh state: PR55 merged14dc3bb; final3 CI PASS, deployment dep-dbqkr12jnfac7390f2v0
LIVE13:24:45MYT. No in-flight deploy or newer reconciliation implementation found. Its runtime
logs confirm service/mapping scope true and all3 price attempts local_request_rejected before
an HTTP status. This does not prove invalid account credentials or unavailable models.
PASS188 backend regression tests after safe pricing-header normalization/validation. Only leading/
trailing whitespace removed internally; embedded control/space characters fail before network.
Secret values never exported/logged. No generation-client or security-control changes.
IN PROGRESS reviewed staging PR/CI/deploy and post-fix metadata observation. No SQL migration
needed for this change. BLOCKED actual account/balance/cost/FX/fees/net margin and real E2E.
Customer generation/checkout remains disabled; production/two receipt orders/wallets untouched.

### Verified outcome —12November18:52MYT

PASS PR56 headdf81d1d5:188 backend tests;3 CI43203929788/43203929800/43203929856 PASS.
Merged staging5053a972; LIVE dep-dbqpkc2jnfac739d9tmg at18:51:55MYT. Fresh public checks
18:52:27MYT:12 shells/14 unauthorized guards PASS; evidence provider-header-public-20261112.json.
Staging jobs0,budget grants0. No database writes in this bounded iteration; RM0/0 paid generations.
BLOCKED NEW OWNER ACTION: all3 runtime metadata checks report credential_format_invalid after
outer-whitespace normalization, at18:51:53MYT. No provider HTTP request is made for invalid format.
FAL_KEY NAME present does not imply usable secret. We did not inspect/export its value or alter it.
Owner must replace the malformed staging FAL_KEY using Render's secure environment editor with
an intact key from the authorized fal account. Never send key in chat. See exact links/instructions
in docs/step2-provider-runtime-readiness.md. Account access/balance/pricing/FX/fees/RM1 NET unverified.
NEXT: after secure correction rerun GET-only readiness; separately continue disabled controlled
runtime/image integrations. Do not duplicate PR56/deploy; do not enable customer flows. NO-GO.

## 2026-11-12 STEP2 pricing response diagnosis
PASS: owner-updated staging deploy dep-dbqprc2jnfac739dpha0 is LIVE on5053a972.
Authenticated pricing GET now HTTP200 for all3 models; old credential-format blocker resolved.
FAIL: all3 responses still invalid_response. Official pricing schema matches endpoint/envelope;
provider-specific billing units are possible, but actual failure field is not yet established.
IN PROGRESS: explicit fail-closed schema validation with constant-only failure diagnostics.
190 regression tests PASS, including malformed/ambiguous rows, non-JSON200 and redaction.
No raw responses, secret values, inference, database changes or generation activation.
Business database_match=false remains unchanged; isolated mapping_match=true scopes GET only.
BLOCKED: maximum billable units, account inference access/balance, FX/fees and RM1 NET still unverified.
Next: staging CI/review/deploy, inspect sanitized validation reason, then fix confirmed contract mismatch.

## 13 November 2026 — bounded staging continuation
PASS state audit: staging fe994788 includes PR60 plural billing-unit fix and PR61 cost-bound helper.
Render remains LIVE44102547/dep-dbqqbaifngtc738checg; no in-flight deploy. PR76 worker integration
and PR79 production candidate remain open; neither overwritten or merged by this iteration.
IN PROGRESS PR59 refreshed onto latest staging: remove superseded parser changes, preserve PR60/61,
and retain only GET /v1/account/billing?expand=credits. Output is positive-balance boolean and HTTP
status; never username, exact balance, secrets or raw response. Pricing permission does not imply
billing-read permission, inference entitlement or adequate budget. No automatic permission changes.
PASS245 tests discovered:233 pass,12 PostgreSQL-dependent tests skipped locally (not counted PASS).
BLOCKED unchanged: hard billable-duration ceiling, FX/fees/OPEX evidence, RM1 net margin, controlled
Telegram/provider E2E and isolated business-wallet runtime. No generation, grants, payments or SQL
migration performed. PR70 proposal remains unapplied. Customer activation and production prohibited.
NEXT: review/CI PR59, staging-only deploy, sanitized account result and public behavior checks.

### Verified outcome —13 November00:45MYT
PASS PR59 latest head05202c98:3 CI43261815613/43261815622/43261816415;233 local PASS,12 PG skips.
Merged d4627501; LIVE dep-dbquq06k1f9s73fe247g at2026-11-12T16:45:14Z.
PASS fresh pricing GET200: FLUX0.003 USD/megapixels, Wan0.08 USD/seconds, MiniMax0.0175 USD/seconds.
PASS12 public staging shells and14 unauthorized API guards after deployment; not authenticated E2E.
BLOCKED NEW VERIFIED: account billing GET403. Existing credential does not authorize this read;
no balance value or positive-balance conclusion obtained. This is NOT evidence of zero funds or
inference denial. No permission expansion attempted. Owner-account authorization is required to
verify balance via official Billing portal or an appropriately scoped secure read-only credential.
Do not replace a working inference key with a billing-only key or paste any key in chat.
Evidence: docs/evidence/staging-balance-readiness-20261113.json and staging-balance-public-20261113.json.
Latest state supersedes older credential_format_invalid instructions: key format and pricing GET
work. Do NOT ask owner to recreate FAL_KEY merely for pricing. Business database_match=false unchanged.
STEP2 PARTIAL/launch NO-GO. Hard billing duration, effective FX/fees/OPEX, RM1 NET and real E2E remain
unverified. PR76 worker integration needs separate review, staging compatibility/SQL validation and
safe deployment; PR79 production candidate untouched. No production, customer, migration, payment,
provider inference or budget-grant mutation. RM0/0 paid generations in this iteration.
