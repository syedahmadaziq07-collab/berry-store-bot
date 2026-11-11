# Berry AI Model Mapping — staged integration

## Goal

Allow an administrator to present a Berry-branded name in Telegram while
privately selecting a real fal.ai model slug, without conflating the two.

- `display_name`: customer-facing brand (e.g., `Berry Image Pro`).
- `provider_model_id`: private provider slug (e.g., `fal-ai/flux/dev`).
- `tool_key`: stable Telegram tool identifier.
- `credit_cost`: proposed Berry Credits per generation **only**.
- `enabled`: whether to show the configured public label.

## Implemented in this branch

- `ai_model_mapping.py`: strict schema validation and separate
  `public_label()` / `resolve_provider_model()` helpers.
- `GET /api/admin/v1/ai/model-mappings`: authenticated, tenant-scoped
  read of the dedicated `bot_settings` key `ai_model_mappings`.
- `PUT /api/admin/v1/ai/model-mappings`: admin-session/CSRF/idempotency
  protected. The existing staging host **blocks all business writes** unless
  both `ADMIN_WRITES_ENABLED` and `ADMIN_ISOLATED_DATABASE` are enabled.
  Do **not** change either flag on the production-linked staging service.
- React editor at AI Studio and AI Model Catalog. The mapping editor remains
  accessible even if optional AI catalogue tables do not exist.
- Telegram AI Studio **admin preview** reads the public label; it never
  displays `provider_model_id` and does not activate payment or generation.
- Dedicated Python unit tests and frontend + Python CI.

## Not implemented / release blockers

- fal.ai execution, provider model catalogue validation, secure FAL_KEY
  provisioning, pricing quote and cost tracking.
- Atomic credit debit/refund, async job runner, retries, image/video delivery
  and customer-facing public AI Studio. **Nothing charges the wallet.**
- A separate writable staging Supabase project and validated migration/audit
  strategy; current staging intentionally returns HTTP 423 for PUT.
- Final browser E2E testing and Telegram integration verification.
- GitHub CI results must pass before considering merge. No production deploy
  or merge has been authorized.

## How to enable *after* isolated staging is prepared

1. Create an isolated Supabase staging project with copied schema and
   synthetic non-customer records. Do not use real financial data.
2. Confirm `bot_settings` has unique key `(tenant_id,key)`; current
   production schema already contains this structure, but do not alter it.
3. Configure that staging instance with test credentials and the two
   write-enable flags. Use a staging bot token, **not** the production token.
4. Log in, create a mapping, save, reload and validate labels/IDs.
5. Verify Telegram preview in a non-production bot and only then build
   a separate authorized fal.ai generation worker.
6. Review and explicitly approve deployment/merge when ready.

This feature must **not** be represented as a working paid fal.ai service.
