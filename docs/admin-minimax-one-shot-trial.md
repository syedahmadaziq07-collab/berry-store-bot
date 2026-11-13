# Berry Store one-shot MiniMax trial (owner-only)

This change is **disabled by default** and is a diagnostic, not a production
customer feature. It uses existing FalProvider queue and TelegramVideoDelivery
but deliberately does not debit MYR wallets or require a customer order.

## Admin experience

Once enabled on a controlled Telegram bot runtime:

1. In the owner's PRIVATE chat, send `/videotest A white kitten running through a sunny garden`.
2. The bot previews MiniMax H3 Max Turbo, 10 seconds, 480P, balanced, 16:9.
   **No provider POST** occurs during preview.
3. Within 3 minutes send `/videotest_confirm`. This creates a local single-attempt
   checkpoint BEFORE one provider POST; automatic paid POST retry is forbidden.
4. The bot emits request_id when available, polls GET status/result and sends
   a finished MP4 through Telegram.
5. Check fal.ai Requests/Usage and compare the real charge before doing anything else.

A failed/ambiguous submit may still cost money. Never repeat the command in
a fresh deployment unless account billing and provider request status were
reconciled. One successful test does not prove a maximum bill or RM1 NET margin.

## Opt-in environment

Set securely in the chosen bot runtime (do not reveal keys in chat):

- `BOT_TOKEN`: the bot token for that runtime
- `ADMIN_ID`: owner's Telegram numeric ID
- `FAL_KEY`: fal.ai key
- `BERRY_MINIMAX_TRIAL_ENABLED=true`
- `BERRY_MINIMAX_TRIAL_MODE=staging`
- optional `BERRY_MINIMAX_TRIAL_STATE_PATH`: private checkpoint file.
  Default `/tmp/berry_minimax_trial_once.json`.

No environment toggles are changed by this PR. Never run two bot processes
polling the same Telegram token at the same time. On Render Free, local state
is not durable across fresh deployments; this is not a transactional exactly-once
or hard spending-cap mechanism.

## Release boundary

- Preparing a PR against `main` is NOT permission to merge, deploy, or enable
  production, regardless of customer count.
- The cleanest test is via a dedicated test Telegram bot token with a staging
  runtime. For an owner-approved trial on the current production bot, require
  separate explicit deployment/activation approval.
- The provider's published USD0.025/s normal rate implies USD0.25 for exactly
  ten billed seconds; real usage may differ and can exceed that estimate.
- No customer checkout, wallet, orders, mapping, database schema or secrets are
  modified by this code.
