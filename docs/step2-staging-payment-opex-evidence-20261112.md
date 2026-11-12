# STEP 2 — Staging payment path and per-generation OPEX evidence
Date: 2026-11-12. Read-only audit of GitHub staging branch, Render staging service, and Supabase staging metadata. No production access, paid generation, checkout calls, SQL writes, or wallet mutations.

## Scope
GitHub: `deploy/berry-ai-private-mapping-staging-20261111`. Render: `berry-gemini-admin-staging` / `srv-dbq2g9mk1f9s73de0u50`. Supabase: staging project `cirsdvkfkvypprnmyykk`.

## Payment and top-up flow observed in staging code
- `berry_credit_pricing.py`: RM1 = 1250 credits. Top-up tiers: starter RM5/6250, creator RM10/12500, pro RM20/25000, studio RM50/62500.
- `topup_checkout.py`: server-side `berry_create_topup_order` RPC over HTTPS with stable idempotency key. It creates/looks up a pending order; it is NOT a payment gateway charge and is NOT evidence of enabled checkout.
- `docs/sql/berry_create_topup_order.sql`: one active order per user, plan prices controlled by SQL; `berry_private.topup_checkout_requests` stores idempotency references.
- `docs/sql/berry_approve_topup_order.sql`: only approves `waiting_approval` orders with receipt and credits wallet atomically using `ai_wallet_apply_transaction`; manual receipt approval workflow. This SQL file alone does not prove live runtime customer checkout or payment acceptance.
- No payment processor SDK/merchant contract/automated payment capture was established by the audited files. This is an evidence limit, NOT a repository-wide proof of absence. Do not use ToyyibPay/Billplz published fees as Berry Store actual fees.
- `AI_WALLET_SETUP.md` describes earlier read-only foundation; code and staging metadata provide more current evidence, but customer activation is still NO-GO.

## Supabase staging metadata (read-only)
- `public.orders`, `public.ai_wallets`, `public.ai_wallet_transactions` exist and have RLS enabled (per `list_tables`). `orders` has `amount`, `status`, `receipt_file_id`, `approved_by` fields; wallet balances are numeric MYR and transactions contain `amount`, `kind`, `idempotency_key`.
- `information_schema.routines` confirms `public.berry_create_topup_order` and `public.berry_approve_topup_order` exist. Metadata only: no invocation, balance/receipt/order-row reads, or writes.
- No verified payment processor settlement ledger, merchant fee data or provider billing records were obtained from staging metadata.

## Render staging configuration (read-only)
- `get_service` confirms `berry-gemini-admin-staging`, Docker web service, Oregon, **plan=free**, **one instance**, `autoDeploy=no`, branch `deploy/berry-ai-private-mapping-staging-20261111`, no PR previews.
- Free service plan is NOT evidence of zero total cost or zero allocated OPEX. Actual invoices, account-wide service costs, Supabase storage/egress, retention, Telegram delivery, CDN, operational support and paid retry caps are unverified.
- No environment secret values, paid account usage, or invoices inspected. No production service inspected.

## Required verified net margin inputs
1. Payment collection rail (manual bank transfer/QR vs gateway), merchant bank fees, receipts, chargebacks/refunds, settlement FX, actual top-up payment costs and allocated fee per spent MYR; avoid charging gateway fees on each internal wallet debit without evidence.
2. fal.ai maximum billable seconds, exact unit rate applicability, retries/failed charges and inference entitlement.
3. Conservative effective USD/MYR upper bound (with spread/FX fees), expiry and fail-closed refresh.
4. Bounded per-generation Render/Supabase/storage/egress/Telegram delivery and support/retention allocations, including traffic and retry scenarios.
5. Independently verified all-in upper bounds before `confirmed_costs=True` and owner-approved retail price.

## Decision
**Payment method partially identified: receipt-based manual approval in code. Gateway identity NOT established. Cost ceiling NOT established. STEP 2 PARTIAL / RM1 net BLOCKED / customer generation NO-GO.**
