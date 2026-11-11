# Berry AI Studio — Credits & pricing specification (draft)

Status: **Design approved for implementation; NOT live.** Dashboard changes deferred. This is a Telegram-first wallet/top-up design.

## Exchange rate and plans
- 1 MYR = 1,250 Berry Credits; 1 credit = RM0.0008.
- Starter: RM5 → 6,250 credits.
- Creator: RM10 → 12,500 credits.
- Pro: RM20 → 25,000 credits.
- Studio: RM50 → 62,500 credits.
- No bonus credits in phase 1; no expiry unless explicitly disclosed and approved.
- Display both credits and MYR equivalent at purchase/generation confirmation.

## Profit objective
Target **RM1.00 per successful video generation**, after provider cost, payment processing, FX fees and risk allowance if feasible. Treat this as a pricing target, not guaranteed realized net profit.
- Provider price in USD must be verified for actual model, duration, resolution and audio settings.
- Formula: cost_myr = provider_usd * conservative_fx_rate + per_generation_payment_cost + risk_buffer.
- retail_myr = round_up_to_cent(cost_myr + 1.00).
- required_credits = ceil(retail_myr * 1250).
- Actual customer MYR-equivalent charge = required_credits / 1250. Rounding must not reduce the target margin.
- Do not list a duration/model combo until provider support and price are verified. Prior sample price tables are estimates, NOT production price lists.

## Telegram flow
1. AI Studio > Wallet > Top Up shows the four MYR plans and exact credit quantities.
2. Customer selects a plan and completes an existing verified payment flow; wallet credits only after server-side payment confirmation, never from screenshot alone.
3. Wallet shows available/reserved balance and immutable transaction history.
4. AI Studio > Video > model > supported duration/resolution > image > prompt > review exact credits and MYR equivalent.
5. Explicit customer confirmation reserves credits atomically; submit provider job once with unique idempotency key.
6. On successful completed video, settle reservation into debit and deliver MP4.
7. On provider failure, release reservation/refund; ambiguous timeout requires reconciliation before retry to prevent duplicate provider charges.
8. On insufficient balance, offer top-up without losing draft request.

## Security and reliability
- Server-side Supabase service role only; never ship privileged key to Telegram users or web clients.
- Tenant_id and Telegram user ID required for every wallet mutation.
- Use existing ai_wallets, ai_wallet_transactions and ai_wallet_apply_transaction RPC after inspecting actual schema; avoid duplicating tables or inventing columns.
- Immutable ledger with unique transaction/job reference and idempotent atomic debits/credits; prevent negative balances and double charges.
- Persist jobs and reservations across Render restarts. Rate limits and admin kill switch.
- Keep admin-only video generation until payment, ledger, reconciliation and real API pricing are tested.
- Do not change Render env, merge, deploy, or activate customer billing without explicit owner approval.

## Acceptance tests
- Plan amounts map to correct credits.
- Customer sees exact RM value and refund policy.
- Concurrent double-click never double-charges.
- Repeated payment webhooks never double-credit.
- Failed job releases held credits exactly once.
- Tenant isolation and unauthorized top-ups are rejected.
- Model price change cannot affect an already-confirmed request.
- Existing Telegram shop/order flows remain intact.
