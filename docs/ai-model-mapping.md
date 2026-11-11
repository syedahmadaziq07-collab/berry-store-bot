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
