# Production AI Video launch gate — 12 November 2026 MYT

LAUNCH STATUS: NO-GO. No production migration, activation, wallet write or provider spend performed.

DONE: PR #43 merged (e8712cb), five CI workflows on its reviewed head PASS. Production Render remains
on 80655e2, so #43 is not live. Read-only production metadata confirms missing berry_private schema
and berry_create_topup_order RPC. Aggregate audit confirms one duplicate active-order group with
two orders and two receipts. No customer identities or receipt contents were exported.

IN PROGRESS: corrected migration now validates duplicates before DDL, creates the private schema,
revokes public access, grants service-role usage and wraps the complete change in a transaction.
27 local production-branch regression tests PASS. Exact revised SQL applied only in isolated staging;
actual payment-contract rollback suite PASS. Both PR44 CI checks PASS. This is preparation, not approval to run it in production.

## Concrete migration impact and rollback plan

1. Confirm a current platform backup/PITR restore point and recovery procedure with metadata evidence.
   Backup availability is NOT yet verified. Capture existing orders schema, constraints and function
   definitions without customer rows or secrets for a reviewed schema rollback artifact.
2. Owner/admin reconciles both existing receipts against bank settlement. Decide each order's valid
   disposition explicitly. Do not infer that either receipt is unpaid, duplicated or safe to cancel.
3. Re-run read-only aggregate preflight. If duplicates remain, migration stops before schema/index writes.
4. Review index lock/build impact and service-role permissions. Run the exact final SQL in isolated
   schema-compatible validation, including concurrency and receipt/approval/credit tests.
5. Obtain specific production migration confirmation. Execute with checkout disabled. Verify function
   permissions and existing order/wallet invariants before any activation.
6. Pre-commit failure: transaction rollback restores the pre-migration state. After successful commit,
   disable checkout first; revert application to the known live commit if required. Preserve request
   audit rows and orders. Never blindly drop tables/functions/indexes or reverse wallet entries.
   A post-commit schema rollback requires a reviewed dependency-aware script; not yet approved.

## Remaining real acceptance gates

- Production application deployment is withheld while required migration/security gates are incomplete.
- Controlled real RM5 QR/receipt/approval/6,250-credit journey requires an authorized test identity;
  it must not change existing customer balances. No bank payment is authorized by this document.
- Customer video handlers must use the existing production MYR wallet with durable job reservations;
  synthetic staging job balances are not a replacement. This integration is not complete.
- Real video model, parameter-bound costs, FX/fees/retries and at least RM1 net margin unverified.
- Owner now authorizes RM5 total / at most 5 paid generations from existing authorized provider balance.
  No purchases/top-ups. Exact maximum model/parameter/FX/fee cost must be verified before each request;
  no paid request has run. Budget authorization does not authorize bank payments or customer wallet edits.
- Live Telegram delivery, restart recovery, definitive refund and ambiguous reconciliation unverified.
- Exposed production secret rotation needs coordinated owner-approved secure configuration, service
  rollout and old-key revocation. No secret values were read or rotated here.

NEXT ACTION: validate this migration revision in isolation and finish safe code integration while
payment reconciliation, verified backup, test identity, verified cost/access and secure rotation remain blocked.
See PR45 and docs/production-ai-video-progress.md for MYR lifecycle implementation evidence.
