# Berry AI Wallet — Setup & Verification

This PR is a **read-only Wallet foundation**. It does not accept payments, change balances from Telegram, or generate AI videos.

## Setup order (important)

1. **Back up your Supabase database** before running any migration.
2. In the **correct** Supabase project, open **SQL Editor** and run the full [ai_wallet_schema.sql](./ai_wallet_schema.sql) file.
3. In **Render → berry-store-bot → Environment**, confirm the existing `TENANT_ID`, `SUPABASE_URL`, `SUPABASE_KEY`, and **server-side** `SUPABASE_SERVICE_KEY` are set. Keep `SUPABASE_SERVICE_KEY` secret. Also set `DASHBOARD_ADMIN_SECRET` to access dashboard Wallet reports.
4. Verify the PR's **Python & JavaScript syntax checks** and test in a staging bot. Merge only after the existing shop, orders and receipt upload still work.
5. Deploy the latest **main** commit using Render after merge. Open Telegram as the configured `ADMIN_ID`, select **AI Video → My Wallet**.
6. With the migration installed, a new account with no transactions correctly shows `RM0.00`. Without it, the UI shows **Belum tersedia** instead of pretending a balance exists.
7. In the admin dashboard, open **AI Wallet** to view account balances and the recent ledger entries. The dashboard cannot perform adjustments.

## Ledger model

- `ai_wallets`: each `(tenant_id, user_id)` has one MYR balance.
- `ai_wallet_transactions`: immutable transaction history keyed by `(tenant_id, idempotency_key)`.
- `ai_wallet_apply_transaction(...)`: service-role-only database RPC that serializes updates per wallet, enforces non-negative balances and idempotency, and records a ledger entry in the same database transaction.
- The RPC is **not currently called by the bot**; do not use it for customer top-ups until the payment-verification, reversal, and fraud-review flows are implemented.
- No AI model charges, refunds or top-up handling are enabled in this PR.
- Wallet data is read using `SUPABASE_SERVICE_KEY` server-side. Never expose that key in Telegram, dashboard JavaScript or GitHub.

## Test cases before enabling money movement

- Wallet balance absent/new user → RM0.00 **only** after DB succeeds.
- Wrong `TENANT_ID` → zero rows for another tenant.
- Schema missing, Supabase unavailable or service key absent → `Belum tersedia`.
- Different users must not see each other's wallet or history.
- Atomic RPC test under service role: debit cannot cause a negative balance, exact idempotency-key retries cannot charge twice, conflicting reuse of a key is rejected.
- Receipt photo upload and Browse Shop still behave as before.

## Limitations

The dashboard currently displays a maximum of **200 wallet accounts** and **100 latest transactions** per tenant, not a full financial report. There is no payment gateway, manual credit button, reconciliation, admin auditing interface or customer top-up yet. These require separate testing and review before enabling.
