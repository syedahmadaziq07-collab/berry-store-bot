# Berry AI Model Mapping — staging verification & release gates

## Running staging preview (safe draft)

- The Gemini AI Studio and AI Model Catalog pages display a **Model Mapping** editor.
- Admin can set customer-facing display_name separately from internal
  provider_model_id, tool_key, credit_cost and enabled.
- Mapping editor uses authenticated `GET /api/admin/v1/ai/model-mappings` and
  `PUT /api/admin/v1/ai/model-mappings`.
- The PUT route requires authenticated session, CSRF, Origin verification and
  an idempotency UUID, **and** `ADMIN_MODE=staging` plus
  `ADMIN_MODEL_MAPPING_DRAFT_ENABLED=true`.
- The saved draft is written **ONLY** to the server's local SQLite admin state
  file, keyed by tenant. It is **not** written to Supabase or production bot.
- Render free-service local filesystem is ephemeral. Drafts can disappear
  after redeploy/restart. Never advertise them as durable configuration.
- The React UI visibly discloses this limitation.
- Existing mutation guard still blocks shop/order/customer/wallet/broadcast
  mutations if `ADMIN_WRITES_ENABLED=false` and
  `ADMIN_ISOLATED_DATABASE=false`.

## SECURITY: why not store in bot_settings

`public.bot_settings` has a public SELECT RLS policy. Therefore storing
private provider mapping JSON in its `value` is **not safe**: anyone with
Data API read access may discover the provider ID. Earlier PR prototype
did that; it was removed. `bot.py` no longer reads mapping from this public
table. Never put FAL_KEY or other credentials in model configuration.

## Still required before customer AI Video launch

- Provision audited, tenant-scoped **private** model mapping storage with
  RLS and restricted grants, or an isolated staging database.
- Implement server-only bot resolution of provider_model_id from that store.
- Provider model compatibility validation and secure fal.ai generation worker.
- Atomic wallet debit/refund, durable job state and Telegram delivery.
- Browser authenticated E2E with real staging data, then deliberate release.
- Replace weak staging password; production is connected read-only for this
  dashboard's business routes and should not have shared service-role keys
  with a publicly guessable admin login.

## Verification

GitHub Actions: `AI Mapping Staging Draft Integration Tests` executes
Python unit tests for auth/CSRF/tenant separation/write isolation and React
TypeScript build. Provider requests and production writes are NOT tested
or enabled. Browser login/full E2E remains a separate acceptance test.

## New: isolated private persistent mapping (CODE ONLY; feature flag OFF)

A server-only `ai_model_mapping_store.py` now supports restricted Supabase
`berry_ai_model_mappings_get/put` RPCs with an optimistic revision, tenant ID
and idempotency key. The admin API retains its established authentication,
CSRF and Origin controls; all non-mapping business writes stay locked.

The private database is **a different Supabase PROJECT** from the currently
connected Berry Store business Supabase. A distinct URL is required by the
server-side configuration; this avoids writing model mappings into the existing
production-linked database. The SQL is **review only**:
`docs/sql/berry_private_ai_model_mappings.sql`. No SQL has been applied.

Only after provisioning a dedicated, verified staging Supabase project,
reviewing SQL/security and rotating the weak staging admin credentials:

1. Apply the reviewed migration to the **isolated staging project only**.
2. Set staging Render service variables through its secret UI:
   `AI_MAPPING_SUPABASE_URL`, `AI_MAPPING_SUPABASE_SERVICE_KEY`,
   `ADMIN_MODEL_MAPPING_PRIVATE_ENABLED=true`. Keep
   `ADMIN_MODE=staging`, `ADMIN_WRITES_ENABLED=false` and
   `ADMIN_ISOLATED_DATABASE=false`. `TENANT_ID` remains a server-owned UUID.
3. Do NOT copy production service keys or Telegram bot token into this project;
   the stage mapping project must use its **own** service-role key.
4. Deploy the PR #26 staging branch **only**, verify GET revision=0, test
   PUT/reload/redeploy persistence, concurrency conflict (409), unauthenticated
   401, missing CSRF 403, same-tenant isolation, non-mapping writes 423.
5. Verify `anon` and `authenticated` have no schema/table/RPC grants.
   Confirm private model IDs never appear in customer Telegram copy or an
   unauthenticated response. Keep bot customer generation disabled.

The React editor now reads a response mode header and distinguishes
`staging-draft-only` from `private-persistent-staging`. In absence of the
explicit private feature flag it still uses the original ephemeral draft.
If the flag is ON but private DB configuration is invalid, the API fails
closed instead of silently switching back to ephemeral storage.

### Remaining release gates

- No dedicated staging Supabase database or Render secrets have yet been
  provisioned/verified; no staging deploy of this new mode performed.
- The server-only `resolve()` helper is ready for a **future isolated staging
  Telegram worker**, but the live bot is NOT wired to mapping.
- fal.ai requests, Berry Credits debit/refund and Telegram delivery have not
  been run or enabled by this change.
- Browser-authenticated end-to-end tests are still required.
- The service-role credential previously shared through chat should be rotated
  through the Supabase/Render secret interfaces (never paste secrets in chat).
