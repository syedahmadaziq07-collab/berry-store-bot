# STEP 2 — Owner-only MiniMax 10-second paid smoke test

**Scope:** Isolated diagnostic, NOT a customer release, wallet transaction, certified cost
ceiling, or a replacement for the existing MyrVideoWorker/consent lifecycle.

## Existing infrastructure facts

- Render `berry-gemini-admin-staging` deploys `Dockerfile.admin`, which runs Flask/Gunicorn
  and **never runs bot.py / Telegram polling**. Merging to staging alone will NOT expose
  Telegram /videotest.
- Render `berry-store-bot-1` polls Telegram from `main` (production service). This
  PR does NOT change that service or its environment. Do not point two polling
  instances at the SAME Telegram bot token simultaneously.
- Price reads (HTTP 200) do not establish paid inference entitlement. A billing
  account endpoint HTTP 403 may indicate missing billing scope, not inference denial.

## Opt-in configuration for a *dedicated test bot runtime*

Use a separate Telegram bot token and isolated test runtime for the first paid test
or obtain explicit approval for a carefully controlled update of the current bot.
The latter changes production and must not be inferred from a staging PR.

Required server-side variables:

- `BOT_TOKEN`: chosen test bot token (never print or commit)
- `ADMIN_ID`: your own integer Telegram user ID (>0)
- `FAL_KEY`: fal.ai key entered securely
- `BERRY_MINIMAX_TRIAL_ENABLED=true`
- `BERRY_MINIMAX_TRIAL_MODE=staging`
- optional `BERRY_MINIMAX_TRIAL_STATE_PATH`: persistent private local checkpoint
  location (default /tmp/berry_minimax_trial_once.json)

For an entirely isolated test bot, other ordinary bot.py initialization dependencies
(Supabase tenant configuration, etc.) may still need valid test values; do not reuse
production database/service secrets without scope review.

**Important:** /tmp on a disposable container is NOT durable across service
re-creation. The test does NOT guarantee exactly-once execution across fresh
deployments or separate processes. Do not enable multiple test runners; do not
manually reset the state file or redeploy after an uncertain POST without inspecting
fal.ai Requests/Usage.

## Test procedure (after test bot actually deployed)

1. In a PRIVATE chat with the test bot as ADMIN_ID, type
   `/videotest A white kitten running across a sunny garden`.
   It only previews details; sends **no paid request**.
2. To knowingly authorize exactly one provider POST, type
   `/videotest_confirm` within 3 minutes.
3. The runner durably claims a local attempt *before* the POST, records provider
   request_id if received, polls GET queue status/result without POST retry and
   sends video with the existing trusted TelegramVideoDelivery transport.
4. If it fails or times out, **do not submit again**. Check fal.ai Requests/Usage
   first using the request_id where available; the missing POST response can be
   ambiguous and still billable.
5. Compare fal.ai Usage/credits before and after, allowing for reporting delay.
   A single actual bill proves that sample cost only, not a billing maximum.

Selected parameters: `minimax/h3-max-turbo/text-to-video`,
`duration=10`, `resolution=480P`, `prompt_expansion_mode=balanced`,
`aspect_ratio=16:9`, `enable_safety_checker=true`.

The public standard reference USD0.025 per video second implies USD0.25
for exactly 10 billed seconds. Actual duration, promotion, billing rounding
and surcharges may differ, and the request is **not bounded by an enforced
USD spending ceiling**. User authorizes one attempted generation only.

## Acceptance

The experiment proves model API connectivity and sample inference, only after
one actual MP4 and provider usage are observed. It does **not** establish RM1
guaranteed NET margin, customer checkout, billing maximum, production release,
or all STEP 2 gates.

Disable `BERRY_MINIMAX_TRIAL_ENABLED` after the experiment. Never enable
customer pricing/checkout as a side effect of this diagnostic.
