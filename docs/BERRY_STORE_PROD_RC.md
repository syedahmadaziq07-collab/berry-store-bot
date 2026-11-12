# Berry Store — Production Release Candidate (main)

Branch: `feat/prod-ai-studio-integration-20261112` (from `main` @ 409567c).
Render production service: berry-store-bot-1 (`python bot.py`), auto-deploy OFF.

**Status: RELEASE CANDIDATE — pending review; NOT deployed.**

## Audit findings on main (409567c)
1. **CRITICAL startup bug (owner directive #5, CONFIRMED):** bot.py ran an
   import-time block calling Telegram `/close` and
   `deleteWebhook?drop_pending_updates=true` on EVERY start — silently
   discarding queued customer messages — plus raw `print` of API errors that
   can embed the bot token. `main()` also called
   `delete_webhook(drop_pending_updates=True)` and
   `run_polling(drop_pending_updates=True)`.
2. AI Studio customer-facing features: only Shop/Home/wallet-balance/
   transactions/topup-preview/templates/guide menus are live; every AI
   generation feature (image/video/transform/voice/enhance/storyboard etc.)
   is a "belum tersedia" placeholder. Wallet is read-only. Checkout flag
   `BERRY_TOPUP_CHECKOUT_ENABLED` defaults OFF; no production checkout RPC.

## Changes in this candidate
1. **Startup safety fix:** removed the entire import-time early-token block;
   `delete_webhook(drop_pending_updates=False)` once in main();
   `run_polling(drop_pending_updates=False)`. Customer messages queued during
   downtime are now preserved. No import-time network calls remain.
2. **S01 wallet display fix:** exact Decimal conversion preserves fractional
   credits (RM4.99 → 6,237.5) — display only, MYR accounting untouched.
3. **Disabled-by-default AI Image Studio wiring:** gated entry
   (`ai_image_prompt` callback) requiring literal env
   `BERRY_IMAGE_STUDIO_ENABLED=true` + `BERRY_IMAGE_STUDIO_TEST_USER_ID`;
   `_image_flow` only reads `bot_data` and never constructs a worker/store;
   the underlying `TelegramImageFlow.confirm` still requires
   `allow_external` + `budget_id` which no production configuration supplies.
   Includes reviewed STEP 3 modules (image flow, sendPhoto delivery, offer
   builder) and their dependencies (staging_job_worker, video_myr_worker,
   fal_provider) — all inert at import.
4. Tests: `test_prod_ai_studio_integration.py` (13 cases: AST-verified
   pending-update preservation, flags default-off, gated entry, wallet
   display, uuid5 idempotency) + carried-over image suites 20/20.
   topup/payment suites 12+5 OK (unchanged contracts).
   CI: `.github/workflows/prod-ai-studio-integration.yml`.

## Payment/top-up audit (directive #7)
`BERRY_TOPUP_CHECKOUT_ENABLED` gate + `TENANT_ID` + `SUPABASE_SERVICE_KEY`
required; `checkout_ai_topup` shows "belum aktif" when disabled; plan screens
are previews only. No payment collection, wallet mutation, or crediting is
activated by this branch. The production checkout RPC does not exist on main;
no migrations are included or applied.

## Rollback plan
- Auto-deploy is OFF: a deploy happens only after explicit owner action.
- Rollback = redeploy previous commit `409567c` on Render (no DB schema change
  exists in this candidate — zero migration risk).
- Post-deploy smoke tests: (1) `/start` responds; (2) Render logs show no
  import-time Telegram calls and `delete_webhook` once with
  `drop_pending_updates=False`; (3) My Wallet shows fractional credits
  correctly; (4) `/healthz` and dashboard 200; (5) queued customer messages
  received during downtime are processed (not dropped).

## Remaining blockers (unchanged)
- Real AI generation: requires STEP 2 operational gates (pricing, entitlement,
  margin, E2E) and owner approval — all features stay disabled.
- Payment activation: owner bank-evidence reconciliation for disputed orders.
- Production DB migrations: none included; any future migration needs
  explicit approval.
