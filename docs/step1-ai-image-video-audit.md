# STEP 1/12 — AI Image & AI Video audit

**STEP 1: PASS — audit coverage32/32 components. Customer launch: NO-GO.**

Snapshot12 November2026 MYT, source/deployed staging b6a4cf8930eca4be1b9b6e74962344f633824291.
Production app80655e2; main e8712cb. PASS means the audit is complete and gaps are assigned,
NOT that Image/Video features are ready. No end-to-end AI customer feature is PRODUCTION VERIFIED.

All database checks in this milestone were read-only catalog/configuration/aggregate checks.
No migrations, wallet/order writes, provider generation, payments, purchases or production deploy
were executed for STEP1. Regression tests use local fixtures/mocks. Prior actual isolated SQL
contract runs are clearly distinguished from freshly repeated read-only checks.

## Status meanings

CODE COMPLETE: implemented source, without live acceptance. PARTIAL: some integration exists,
remaining gaps explicit. MISSING: no required working path. MOCK ONLY: positive external behavior
has only been tested with fixtures/mocked transport. STAGING VERIFIED: the stated isolated contract,
metadata or packaging check passed; not full feature E2E. PRODUCTION VERIFIED requires explicitly
scoped real production evidence; existing deployment/ACL metadata does not prove generation.

## Audit matrix

| ID | Feature | Current status | Evidence from code/tests/deployment | Missing work | Owner | Priority | PR/commit |
| --- | --- | --- | --- | --- | --- | --- | --- |
| I01 | AI Image — Telegram menu | PARTIAL | bot.py show_ai_studio_section(image) shows unavailable/admin-only placeholder. | Implement a real customer entry and access gates. | GPT WORK | P1 | PR26/46; b6a4cf8 |
| I02 | AI Image — prompt input | MISSING | No image prompt state/handler connected to provider or MYR job. | Add validated prompt workflow and receipt precedence. | GPT WORK | P0 | bot.py; PR46 |
| I03 | AI Image — model/parameters | PARTIAL | Private rev4 maps FLUX Schnell; no live image settings validation/UI selection. | Implement parameter-bound approved model/size/output-count offer. | GPT WORK | P0 | ai_job_service.py; PR26/38 |
| I04 | AI Image — preview/Confirm/Cancel | MISSING | New durable consent/controller is video-only; no image ticket flow. | Image consent and expiry/ownership/idempotency tests. | GPT WORK | P0 | telegram_video_flow.py; PR45/46 |
| I05 | AI Image — provider transport | PARTIAL | fal_provider.py generic queue POST exists; AIJobService accepts image quote but legacy submit_reserved always raises. | Connect image-specific schema/real wallet/runtime; real provider acceptance. | GPT WORK | P0 | PR38/40/46 |
| I06 | AI Image — mapping/credential metadata | STAGING VERIFIED | Actual rev4: fal-ai/flux/schnell, Berry Image FLUX Schnell, enabled=false,4 credits. Staging FAL_KEY NAME present=true. | Validate key/account/model access; replace obsolete price; leave disabled. | GPT WORK; PEMILIK account authorization if needed | P0 | PR26/48; b6a4cf8 |
| I07 | AI Image — pricing/FX/RM1 NET | MISSING | 4 credits = RM0.0032 revenue: below RM1 even at zero cost and below MYR cent granularity. No verified all-in image cost. | Get actual model price/parameters, FX/fees/tax/operating/failure allocation; enforce price floor. | GPT WORK | P0 | berry_credit_pricing.py; ai_wallet_pricing_adapter.py; mapping rev4 |
| I08 | AI Image — real MYR debit/refund | MISSING | Existing public MYR ledger is available, but MyrVideoWorker.JobQuote and RPC accept video only. | Image job integration to existing ledger, not synthetic balances. | GPT WORK | P0 | video_myr_worker.py; PR39/46 |
| I09 | AI Image — durable jobs/queue | PARTIAL | StagingJobWorker supports image with separate synthetic wallets; actual synthetic SQL was tested previously. Not customer MYR integration. | Production-schema image jobs and ledger-bound lifecycle. | GPT WORK | P0 | PR38/40; staging_job_worker.py |
| I10 | AI Image — polling/restart/timeout | MOCK ONLY | Image result parsing, GET polling, claim-once and timeout holds covered by synthetic/mock provider worker tests. No live daemon. | Exercise real runtime/provider restarts and unknown reconciliation after MYR integration. | GPT WORK | P0 | tests/test_staging_job_worker.py; PR40/41 |
| I11 | AI Image — Telegram delivery | MISSING | Synthetic worker injects delivery.send; concrete TelegramVideoDelivery rejects image. No customer image delivery adapter wired. | Implement sendPhoto/document fallback and acknowledgment/unknown handling. | GPT WORK | P0 | telegram_video_delivery.py; staging_job_worker.py |
| I12 | AI Image — controlled real E2E | MISSING | No actual image generation or Telegram image delivery evidence. | Controlled identity, verified cost/access/balance, real flow within shared cap after gates. | GPT WORK; PEMILIK account/identity authorization | P0 | docs/soft-launch-progress.md |
| V01 | AI Video — Telegram navigation | PARTIAL | Admin Gemini/photo preview exists; controlled text-to-video menu code exists only when explicit flow injected. Normal startup injects none. | Configure reviewed controlled runtime and test identity; customer entry remains locked. | GPT WORK; PEMILIK identity authorization | P0 | bot.py show_ai_video/build_app; PR45/46 |
| V02 | AI Video — prompt validation | CODE COMPLETE | TelegramVideoFlow validates1–1500 chars and16:9/9:16; handler tests cover receipt precedence/private-user authorization. | Real Telegram input acceptance remains E2E gate. | GPT WORK | P1 | telegram_video_handlers.py; tests/test_telegram_video_flow.py; PR46 |
| V03 | AI Video — model/parameters/photo input | PARTIAL | Gemini Omni Flash15s720p UI is preview; actual mapping is Wan A14B. Live offer_builder has no concrete account-verified implementation; tests inject fixtures. | Choose supported model settings from schema, bind cost to exact args; real photo ingestion absent. | GPT WORK | P0 | bot.py; telegram_video_flow.py; PR45/46 |
| V04 | AI Video — preview/Confirm/Cancel | STAGING VERIFIED | Durable user-bound tickets and atomic confirm/cancel SQL installed; prior isolated actual SQL and current handler/unit tests PASS. No preview debit; duplicate/cancel/expiry protected. | Real Telegram callbacks with actual DB/runtime; replay/load E2E. | GPT WORK | P0 | PR45/46; verify_video_consent.sql |
| V05 | AI Video — provider integration | PARTIAL | fal.ai queue transport implemented; no paid request executed. Name presence is not key validity or model access. | Authenticated read-only provider check, cost offer, controlled inference only after gates. | GPT WORK; PEMILIK provider login if required | P0 | fal_provider.py; PR45/46/48 |
| V06 | AI Video — mapping/endpoints | STAGING VERIFIED | Actual rev4: fal-ai/wan/v2.2-a14b/text-to-video, enabled=false,0 credits. POST https://queue.fal.run/fal-ai/wan/v2.2-a14b/text-to-video . | Verified price/schema/account acceptance; consider announced4Jan2027 model removal before long-term launch. | GPT WORK | P0 | PR26/48; docs/provider-audit-20261112.md |
| V07 | AI Video — pricing/FX/RM1 NET | PARTIAL | JobQuote enforces supplied all-in-cost arithmetic >=100 cents and RM0.02 debit steps. Fresh cost-binding gate exists; no independently verified provider/FX/fee inputs. | Authenticated exact-model price/max billable units, FX settlement/fees, tax/operating/refund allocation; prove NET. | GPT WORK | P0 | PR36/45/46/48; video_myr_worker.py |
| V08 | AI Video — atomic MYR debit/refund | STAGING VERIFIED | Actual existing MYR RPC called in same transaction as job; prior isolated SQL asserts debit/refund once, overspend rollback and ledger reconciliation. | Actual runtime-to-DB E2E; no customer money tests. Production migration approval after safety. | GPT WORK; PEMILIK production approval | P0 | PR39/45/46; berry_video_myr_lifecycle.sql |
| V09 | AI Video — jobs/queue/budget/audit | STAGING VERIFIED | Jobs/tickets/events/budget tables and three video RPCs installed isolated. Read-only count0 jobs/0 tickets/0 grants. Budget <=RM5 and<=5 claims; unknown retains reservation. | Runtime startup and continuous monitoring; do not seed grant before access/cost approval. | GPT WORK | P0 | PR46; migration20261112033719 |
| V10 | AI Video — polling/recovery/unknown | PARTIAL | Bound GET polling, terminal-error refund and recovery hooks coded/tested with mocked provider; no loop active. Reconciliation RPC absent. WIP candidate not tested/applied/deployed. | Finish audited cases, authoritative correlated receipts, idempotent operator resolution and race/failure tests. | GPT WORK | P0 | PR40/41/46; WIP d215ebea |
| V11 | AI Video — Telegram delivery | MOCK ONLY | sendVideo adapter validates recipient/ack, trusted URLs and redacted errors; claim-once/unknown tests PASS. No real video sent. | Real Telegram size/codec/URL delivery, timeout/shutdown/restart and receipt reconciliation. | GPT WORK | P0 | telegram_video_delivery.py; PR45/46 |
| V12 | AI Video — controlled real E2E | MISSING | No Telegram→provider→video→wallet reconciliation run.169 regression tests are not live E2E. | Controlled bot identity, authorized account/existing balance and known cost, then bounded test. | GPT WORK; PEMILIK authorization | P0 | PR45 draft; docs/soft-launch-progress.md |
| S01 | Shared — MYR/Berry Credits display | PARTIAL | RM1=1250; RM5=6250; new video quote preserves fractional credits. Legacy My Wallet section still int-truncates odd-cent balances. | Unify exact balance display; keep MYR accounting, no synthetic substitution. | GPT WORK | P1 | bot.py show_ai_studio_section(wallet); PR36/46 |
| S02 | Shared — top-up/QR/receipt/approval | PARTIAL | Source reuses send_payment_page Browse Shop QR; isolated checkout/approval/credit-once contracts previously PASS. Main PR43 not deployed; production checkout RPC absent. Two receipts unverified. | Complete controlled real payment journey separately; do not touch disputed orders; reconcile bank evidence. | GPT WORK; PEMILIK bank evidence | P0 | PR39/43/44 |
| S03 | Shared — tables/migrations | STAGING VERIFIED | Read-only catalog/migration history confirms isolated20261112033719 consent migration and required tables. Production berry_private/video_job/checkout absent. | Review production-compatible migration and backup/rollback; explicit approval before applying. | GPT WORK; PEMILIK production approval | P0 | PR44/46; migration history |
| S04 | Shared — RPC/RLS/idempotency security | PARTIAL | 8 scoped staging tables RLS=true/no anon/auth SELECT;6 scoped RPCs no anon/auth EXECUTE. Production wallet RLS/ACL and empty search_path verified; deployed wallet replay guard checks user/amount/kind but not reference. | Patch production reference binding only after review/approval; broader security signoff and real concurrency evidence. | GPT WORK; PEMILIK risky release approval | P0 | PR39/44/46; read-only catalogs/function-line check |
| S05 | Shared — dashboard/auth/AI monitoring | PARTIAL | Unit auth/session guards and public12 shells/14 unauthorized APIs PASS. Provider test/mutation routes return501; health reports polling_disabled and ai not_verified. No authenticated browser E2E or full AI job monitoring. | Authorized dashboard session, actual backend reads/monitoring, persistent audit/session production architecture. | GPT WORK; PEMILIK login authorization | P1 | admin_app.py; PR25/46/48 |
| S06 | Shared — staging deploy/runtime | STAGING VERIFIED | Render b6a4cf8 LIVE dep-dbqjjgec6qcc73fhokgg;169 backend tests/5 CI PASS; public12/14 check refreshed. FAL_KEY name present=true at04:00:27Z. Admin image never starts bot polling. | Controlled Telegram worker startup/health/shutdown, not another public-shell claim. | GPT WORK | P0 | PR48; Render metadata/startup boolean |
| S07 | Shared — production version/alignment | PARTIAL | Render production80655e2 LIVE dep-dbq7t5e1egvs73cr9vs0; main e8712cb includes PR43 ahead of deployed app. PR45 draft and new lifecycle not production. Production FAL_KEY presence not safely verified. | Approved release after migration/rotation/backup/E2E; no production deploy during audit. | GPT WORK; PEMILIK deployment approval | P0 | PR26/43/44/45; Render metadata |
| S08 | Shared — secrets/backup/rollback/release | PARTIAL | No secrets read/disclosed. Exposed-key rotation not verified; recoverable production backup/restore and real rollback unverified. Staging advisors only24 INFO RLS/no-policy notices, not security signoff. | Verify backup/PITR and restore drill, coordinated rotation/revocation, monitoring/rollback and final owner GO. | GPT WORK; PEMILIK account/production authorization | P0 | PR44/45; production-ai-video-launch.md; advisor metadata |

## Independent Image and Video conclusions

AI Image is not a completed product: Telegram placeholder, no prompt/consent path, no real MYR
job integration and no wired image delivery. FLUX Schnell routing is disabled,4-credit price is
invalid for the target and MYR precision. Synthetic worker success must not be promoted to image
customer acceptance. Concrete transport endpoint is https://queue.fal.run/fal-ai/flux/schnell .

AI Video has significantly more source and isolated contract coverage, but is disabled. Real
server offer_builder/model settings/account validation are missing; ordinary startup installs no
controlled flow. Preview Gemini15s differs from actual Wan A14B mapping. Polling/delivery positives
use mocked provider/Telegram. Unknown operator reconciliation is not installed. No paid E2E.

## Fresh verification and evidence

-169 complete backend tests PASS on audited staging source;1 actual PTB20.7 markup serialization
 contract PASS; Python compile PASS. Test outputs may print local key-presence=false because local
 test environment differs from Render. Do NOT confuse that with live staging=true metadata.
- Live public check12:04:59 MYT:12/12 HTML shells and14/14 unauthorized API guards PASS; authenticated
 dashboard still unverified. Evidence: evidence/step1-ai-public-audit-20261112.json.
- Source PR48 all5 CI workflows PASS; host workflow includes frontend16 tests, typecheck, build and
 npm audit. This audit documentation PR must pass its own CI before merge.
- Read-only isolated mappings rev4: image FLUX Schnell disabled4 credits; video Wan2.2 A14B disabled0.
- Read-only8 table RLS/SELECT checks and6 RPC execution ACLs PASS as scoped. Installed migration names
 and0 jobs/tickets/grants verified. Reconciliation RPC absent, WIP not counted as completion.
- Production wallet function metadata: SECURITY DEFINER, empty search_path, public execution denied.
 Targeted function-line inspection confirms replay conflict compares user/amount/kind, not reference.
 This is a newly confirmed P0 release gap, not a wallet mutation or proof of exploited loss.
- Security advisory scope:24 INFO service-only RLS/no-policy notices; no WARN/ERROR returned for
 staging. https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy
- Structured evidence summary: evidence/step1-ai-audit-20261112.json. No secret values/customer rows.

## Provider/cost facts and limits

Provider connector is fal.ai. FAL_KEY NAME is present in live Render staging. This does not prove
nonempty/valid credentials, model access, balance or account permission. Production key presence
has not been verified; no production startup/config change is authorized for this audit.

Official actual-model page https://fal.ai/models/fal-ai/wan/v2.2-a14b/text-to-video announces removal
on4 January2027. Re-evaluate model longevity. Exact account price and parameter-bound maximum were
not established. Gemini approximate token/second estimates and PixVerse prices are different
models and cannot justify a Wan maximum. No FX settlement bound, fees/tax/operating/failure allocation
or minimum RM1 NET proof exists. Current source only enforces arithmetic on supplied cost.

For revenue fee fraction f and fixed all-in bound C, minimum sale price is
ceil_to_RM0.02((C+RM1)/(1-f)); credits=priceMYR*1250. Values C/f must be verified first, not guessed.
Budget remains RM5 total/max5 paid generations from an existing authorized balance. STEP1 spendRM0,
paid generations0. No auto-purchase/top-up and no retrying an ambiguous paid POST.
Official pricing API reference: https://fal.ai/docs/documentation/model-apis/pricing .

## Owner actions required (only access/financial/release decisions)

1. If account access cannot be validated through a future secure server-side read-only check,
 authorize/login the existing fal account via https://fal.ai/login . Use the account already holding
 the configured key. Billing: https://fal.ai/dashboard/usage-billing/billing . Work will calculate
 pricing; owner must not be asked to research it. No credits purchase/top-up is authorized.
2. Authorize a dedicated Telegram test bot/user and authenticated staging dashboard session for
 controlled E2E. Put any bot credential directly into secure Render configuration; never into chat.
 Existing FAL_KEY is present: do not recreate or disclose it merely to prove presence. If provider
 requires replacement, use https://fal.ai/dashboard/keys and secure environment input only.
3. Bank reconciliation for the two receipts remains owner-only. No approve/reject/cancel/delete
 or customer wallet change until settlement evidence is supplied. This audit did not inspect receipts.
4. Before production release, owner account authorization/approval is needed for backup/restore,
 coordinated secret rotation and the final risky migration/merge/deploy. Work prepares/reviews/tests
 the plan; this milestone grants no production changes. Do not share secret values or backup data in chat.

No owner is asked to code, run tests, audit source, calculate price or prepare PRs.

## Checkpoint and STEP 2/12

Audit source/report branch is audit/step1-ai-image-video-20261112. Current application staging
b6a4cf8 (PR48), not an audit-document deployment. PR45 stays DRAFT/unmerged production; PR44 also
DRAFT. Do not redeploy the app for these audit documents. Preserve both disputed orders untouched.

Unknown-reconciliation implementation was paused for the explicit STEP1 audit request. Candidate
checkpoint d215ebeacd4680df6a3abb56ca0e726c220d22a0 on wip/unknown-reconciliation-before-step1-20261112
is saved, NOT validated/applied/deployed. It adds correlated tags and immutable operator cases;
new SQL/module need actual tests and review. Tags do not guarantee provider idempotency and tag
reporting needs provider enablement. Legacy uncorrelated unknown jobs must stay held.

STEP2/12 next: close P0 shared reconciliation/runtime/provider-cost gaps and plan separate Image
integration. Reuse source/checkpoint, avoid duplicate PR/deploy, run free tests first, preserve
financial/production restrictions. No claim of100% until real per-tool E2E and approved production
post-deploy acceptance. All implementation gaps remain open despite STEP1 audit PASS.
