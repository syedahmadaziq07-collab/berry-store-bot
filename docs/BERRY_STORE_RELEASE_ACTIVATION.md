# Berry Store — Production Release & Activation Plan (Owner-Approved Scope)

## 0. LIVE ACCEPTANCE BUDGET (owner authorization 2026-11-13)

**RM5.00 (500 cents) TOTAL cumulative ceiling** for AI Image + AI Video
combined live testing, counting ALL provider charges including failed
requests, retries, conversion and fees.

Enforcement (implemented, tested):
- `image_budget_guard.py` (11/11 unit tests): worst-case rejection
  (`preflight`), RM5 ceiling validation, unknown-outcome full reservation.
- `docs/sql/berry_ai_test_budget.sql` + rollback: `berry_private.ai_test_budgets`
  with DB-level `CHECK(cap <= 500)` and `CHECK(used+reserved <= cap)`;
  `public.berry_ai_budget_claim` RPC: row-lock serialized atomic
  reservation, worst-case rejection inside the transaction, expiry +
  max-5-generation gates, service-role-only.
- PG16 ephemeral CI tests (8 cases): ceiling CHECK, atomic claim, concurrent
  ×3 → exactly 2 succeed within cap, generation cap, expiry, anon rejected,
  no wallet table touched.

Rules honored: single combined ledger (not per-model), blind retries
impossible (no-retry gate), operator must reconcile unknown outcomes (full
worst-case stays reserved), test account/wallet only, no auto top-up, no
public rollout. **Spend to date: RM0.00 (no paid requests submitted).**

Owner approval received for: production database migration, real payment
integration and paid AI activation. This plan executes ONLY verified,
in-scope operations, starting with restricted test-user access.

## 1. Release commit (candidate)
Branch: `feat/prod-release-activation-20261113` (from main @ 81b726e).
Adds the owner-approved runtime activation gate:

```
BERRY_IMAGE_STUDIO_ENABLED=true          # studio visible to test user
BERRY_IMAGE_STUDIO_TEST_USER_ID=<id>     # controlled test identity
BERRY_IMAGE_RUNTIME_ENABLED=true         # REAL provider submissions
BERRY_IMAGE_TEST_BUDGET_ID=<uuid>        # required for runtime
BERRY_IMAGE_CATALOG_JSON=[{...}]         # reviewed catalog (verified prices)
BERRY_IMAGE_DELIVERY_BOT_TOKEN=<token>   # optional separate bot token
FAL_KEY=<key>                            # provider (Render env only)
```

Without `BERRY_IMAGE_RUNTIME_ENABLED` + budget: consent-only (no provider
calls, no wallet effects). With both: real `MyrImageWorker` over
`_ImageSupabaseStore` (image job RPC), `FalProvider`, sendPhoto delivery —
restricted to the single test user id.

## 2. Migration SQL (exact)
- `docs/sql/berry_image_consent.sql` — **additive only**:
  - `CREATE TABLE berry_private.ai_image_tickets` (tenant_id FK→tenants,
    ticket_id PK pair, user_id CHECK>0, payload jsonb, state
    CHECK IN (pending,confirmed,cancelled), expires_at, created_at)
  - `CREATE FUNCTION public.berry_image_checkout(p_tenant,p_user,p_ticket,
    p_action,p_payload)` — service-role/JWT-gated, advisory ticket lock,
    idempotent prepare, owner mismatch/replay rejection, expiry ≤15min.
- **Required job RPC (must be added with the same pattern as
  `berry_video_myr_lifecycle.sql`)**: `berry_image_job` +
  `berry_image_recoverable` — reserve/claim_submit/submission_unknown/queued/
  succeed/provider_failed/claim_delivery/delivered transitions with the
  existing MYR wallet ledger idempotency keys. **Rollback plan:** drop
  function(s) then table; additive schema means no existing rows/orders
  are modified; never reverse ledger entries to roll back.

## 3. Affected tables
`berry_private.ai_image_tickets` (new) — no existing table is modified.

## 4. Payment exposure
`BERRY_TOPUP_CHECKOUT_ENABLED` remains OFF. No payment collection, webhook,
or wallet crediting is activated by this release; payment integration is a
separate approved step requiring provider configuration and signature
verification (documented, not yet implemented).

## 5. Preconditions checklist (must ALL be verified before deploy)
- [ ] Supabase backup taken (owner verifies in dashboard)
- [ ] Migration applied and `verify_image_consent.sql` PASS on production
- [ ] `berry_image_job`/`recoverable` RPCs applied (video-pattern SQL)
- [ ] FAL_KEY valid; read-only pricing GET returns verified prices
- [ ] FX rate configured server-side
- [ ] BERRY_IMAGE_* flags + test user id set in Render env
- [ ] CI green on release commit

## 6. Rollback
1. Render: redeploy `81b726e` (immediate app rollback; flags can also be
   unset for instant feature disable without redeploy).
2. DB: `DROP FUNCTION ... berry_image_checkout; DROP TABLE
   berry_private.ai_image_tickets;` — additive-only, no data loss to
   existing business tables.
3. Ledger: never reverse completed debits manually; use operator
   reconciliation flow.

## 7. Post-deploy smoke (restricted test user)
1. `/start` responds; wallet display correct.
2. Test user: AI Studio → Image Studio → prompt → quote shown (verified
   price, expiry) → Confirm → job created → provider submitted once →
   sendPhoto received → state DELIVERED in job table.
3. Logs: no import-time Telegram calls; one delete_webhook(False).
4. Non-test users: Image Studio shows "belum tersedia".
5. Reconciliation: operator flow for any held job.
