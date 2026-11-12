# STEP 2/12 — provider and runtime readiness

Status PARTIAL; customer launch NO-GO. Scope staging only, RM0/zero paid generations.
Base STEP1 PR49 /384adcfe. Existing staging deploy b6a4cf8/dep-dbqjjgec6qcc73fhokgg.
No overlapping reconciliation PR/deploy found. Production and two unverified orders untouched.

## Provider evidence (official docs checked 12 November 2026)

| Tool | Actual disabled mapping | Endpoint | Schema and readiness |
|---|---|---|---|
| Image | fal.ai FLUX Schnell,4 credits | https://queue.fal.run/fal-ai/flux/schnell | Required prompt; image_size enum/custom dimensions; num_images default1; steps default4; seed; safety checker; jpeg/png. images output. Official listing present, authenticated inference availability unverified. Image customer lifecycle missing. |
| Video | fal.ai Wan2.2 A14B,0 credits | https://queue.fal.run/fal-ai/wan/v2.2-a14b/text-to-video | prompt;17–161 frames(default81);4–60fps(default16);480p/580p/720p(default720p); aspect16:9/9:16/1:1; negative prompt; steps; seed; input/output safety; prompt expansion; interpolation alters output FPS. Official removal4Jan2027; migration needed before then. Account access unverified. |

Sources:
- https://fal.ai/models/fal-ai/flux/schnell/api
- https://fal.ai/models/fal-ai/wan/v2.2-a14b/text-to-video/api
- https://fal.ai/docs/documentation/model-apis/pricing
- https://fal.ai/docs/documentation/model-apis/request-tags

FAL_KEY name presence was verified on staging in STEP1, not validity/balance. A staging-service
and isolated-database restricted startup probe now performs only authenticated GET pricing
for the two fixed models. Credential stays inside runtime; no raw response/error/headers logged.
Probe success means pricing read permission only, not inference access or sufficient balance.
IN PROGRESS: actual probe result after reviewed staging deployment. No POST inference supported
by this probe. Account concurrency is not inferred from public defaults or pricing responses.

## Cost and margin

BLOCKED: actual bounded units per request, exact model/options pricing, account balance/access,
FX upper bound, taxes/FX fees and allocated hosting/storage/delivery costs not independently proved.
Never use fixture prices, reference-model prices or current FX spot as guaranteed maximum.
Provider docs describe per-output billing and no queue/server-error charge; unknown outcomes still
hold budget and wallet, never infer a refund from absent status. No automatic paid retry.

Tested formula: saleMYR >= (providerUSDbound * FXbound + fixedMYRbound + RM1)/(1-saleFeeFraction).
Round UP to RM.02 granularity (25 integer Berry Credits), credits=saleMYR*1250.
`minimum_sale_cents` rejects missing/nonfinite/negative bounds and invalid percentage fees.
Formula is CODE COMPLETE, actual RM1 NET verification BLOCKED. Mapping prices unchanged/disabled.

## Reconciliation and runtime

PASS candidate SQL transaction tests against isolated actual MYR tables: durable correlation tags,
operator cases, hold/bind-known-request/confirm-delivery, exact case replay, conflicting/stale/hash/
recipient evidence rejection, no ambiguous refund/resubmit, private ACL and evidence write protection.
All fixtures and candidate DDL rolled back during validation. No synthetic ledger substituted.
Initial SQL validation FAIL due PostgreSQL regex repetition limit; changed bound to length+charset;
rerun PASS. Legacy lifecycle and consent suites also PASS against candidate schema.

Unknown submission binding requires independently reviewed account evidence correlated to durable
job/hash/tenant/model plus authenticated request GET. Tags are NOT provider idempotency. Tag reports
require account enablement; legacy jobs without tags remain held. Operator evidence is a trusted
server boundary, not a customer API or cryptographic provider attestation. Delivery confirmation
requires matching recipient/media digest/message receipt, never resend. No new refund action.

PASS184 backend tests +1 actual PTB20.7 markup contract; provider/Telegram traffic in regression
is mocked. Recovery startup idempotent; shutdown drains current thread instead of pretending task
cancellation stops a thread. Known queued polling and durable budget ceilings remain covered.
IN PROGRESS: PR review/CI, persisted staging migration, staging deploy/public health verification.

Runtime remains OFF: no concrete account-priced offer builder, test identity/budget grant or worker
activation. Staging service is admin-only, not a Telegram daemon. Recovery fairness under >20
blocked jobs still needs engineering; this release does not claim production worker readiness.
No public reconciliation endpoint. No automatic source-of-truth evidence retrieval implemented.

## Release and rollback

Additive nullable column + private audit table + RPC; no existing rows/orders modified. Previous
application can coexist with schema. Roll back app to b6a4cf8 if required, retain audit table/column;
never delete ledger/audit history to roll back. Production migration is NOT authorized/applied.
Backup restore, secret rotation and controlled real E2E remain separate release gates.

## Owner actions only where access is required

1. If read-only probe cannot establish account authorization/balance, authorize the existing fal
   account through https://fal.ai/login (same account as configured key); billing page
   https://fal.ai/dashboard/usage-billing/billing . Do not purchase credits or share keys in chat.
2. Authorize dedicated Telegram test bot/user and authenticated staging dashboard session through
   secure configuration. Existing customer identities/wallets must not be used.
3. If account lacks tag reports, request enablement through fal account support before relying on
   correlated account exports. Unverified cases remain held; no blind refund or resubmit.

Owner bank reconciliation and production rollout approvals remain outstanding but are not blockers
for this isolated staging change. GPT WORK owns remaining runtime/coverage/cost-source engineering.
