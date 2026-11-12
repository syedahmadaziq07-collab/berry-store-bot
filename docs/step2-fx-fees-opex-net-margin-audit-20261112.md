# STEP 2 — FX, payment fees, operating cost and RM1 net margin audit
Date: 2026-11-12. Read-only analysis; staging documentation only. No paid generation, checkout, wallet or production changes.

## Verified sources and limits
- Bank Negara Malaysia KL USD/MYR reference rate on 2026-11-12: **4.0805 MYR/USD** (reference only, NOT a conservative settlement upper bound, processor FX quote, spread or guarantee). https://www.bnm.gov.my/kuala-lumpur-usd/myr-reference-rate
- BNM interbank indicative rate is not a merchant's actual settlement FX; processor conversion, spread, tax and card/transfer fees remain account-dependent. https://www.bnm.gov.my/latest-rates
- ToyyibPay published Standard FPX B2C **RM1.00 per successful transaction**, B2B RM2.00; local cards 1.5%, foreign cards 3.5%; onboarding/annual fees for card plan and applicable terms may alter totals. These are **market comparators**, NOT evidence that Berry Store uses ToyyibPay or has this fee schedule. https://www.toyyibpay.com/pricing-plans/
- Billplz documentation: plan/payment-method-dependent FPX flat fees and card/wallet percentage fees; **8% SST on transaction fee**, not the whole transaction. Some fees deducted from credit balance, others from payout; annual membership may apply. These are **comparators**, NOT Berry Store account fees. https://support.billplz.com/guide/pricing
- Authenticated staging fal.ai pricing metadata: MiniMax H3 Max Turbo USD **0.0175/second**. Public reference USD 0.025/second differs. Neither provides a guaranteed maximum billed seconds or permanent price entitlement. See docs/step2-minimax-billing-entitlement-evidence-20261112.md.

## Actual Berry Store payment economics — NOT VERIFIED
Existing repository pricing modules define RM1=1,250 credits and top-up packages RM5/10/20/50. `berry_credit_pricing.py` labels a threshold MIN_GROSS_PROFIT_MYR, which alone does **not** establish net margin. `ai_wallet_pricing_adapter.py` accepts `confirmed_costs=True` from caller; this flag is not independent evidence of provider, FX, fees or OPEX. `provider_readiness.py` provides `minimum_sale_cents` and `minimum_video_sale_cents` for independently verified upper bounds.
No evidence reviewed establishes the actual payment gateway/account plan, merchant fees, fee incidence (top-up vs AI debit), effective cost allocation, taxes, refunds/chargebacks, FX settlement method, Render/Supabase/Telegram delivery/storage per-generation upper bounds, retry costs, or rate validity.

## Correct unit economics and fee allocation
Distinguish customer top-up payment from subsequent **internal wallet debit**: payment gateway fees arise when collecting/top-up funds, not necessarily on each internal AI debit. Allocate top-up transaction costs to spent credits conservatively, based on actual funded package and payment method, with clear accounting for unused credits, refunds and breakage; do not double-charge per generation without justification. Any per-generation platform fee is separately evidenced.
For a **verified** USD provider cost upper bound U, **verified** MYR/USD effective upper bound X, **verified** fixed per-generation and allocated top-up/opex bound F, and **verified** revenue-proportional effective fee bound p (0 <= p < 1):
`minimum_retail_MYR = ceil_to_RM0.02((U*X + F + RM1)/(1-p))`
`minimum_credits = minimum_retail_MYR * 1250`
Actual accounting must ensure gross revenue net of taxes, FX, gateway fees, storage, delivery, refunds, operational allocations and paid retries still leaves >=RM1.
Missing bounds must block quote/customer activation. Reference FX and competitor payment rates MUST NOT be silently promoted to verified Berry Store bounds.

## Illustrative arithmetic ONLY — not a retail quote
At precisely 10 billable seconds, USD 0.0175/s => USD 0.175; multiplying by BNM 4.0805 gives RM 0.7140875 **before** FX spread, fees, taxes and OPEX. This is not a maximum, since hard billed seconds and applicable pricing remain unverified. At public USD 0.025/s, 10 seconds => USD 0.25, RM 1.020125 at same reference FX. Neither implies RM1 net at any retail price.
For an illustrative ToyyibPay Standard RM5 FPX B2C top-up, the published RM1 transaction fee is 20% of gross top-up; actual Berry Store provider and method not established. Allocation and taxes must be independently verified.

## Evidence needed before RM1 net PASS
1. fal.ai contractual max billed seconds, rounding, price applicability, paid retry behavior and entitlement.
2. Actual merchant provider, signed pricing/fee schedule, settlement currency, tax treatment, chargeback/refund handling, payment mix and verified upper fee allocation for top-up denominations.
3. Effective USD/MYR purchase/settlement upper bound with FX spread and fees, expiration and a safe re-quote/kill switch on stale data.
4. Maximum Render/Supabase storage, egress, Telegram delivery, CDN, video retention, failed/retried generation, support/refund and other per-generation costs; choose explicit allocations and bound them.
5. Independent evidence provenance, effective dates, upper-bound expiry, and owner sign-off before `confirmed_costs` can be true. No fabricated costs.

## Decision
**STEP 2 PARTIAL / RM1 NET MARGIN BLOCKED / CUSTOMER OFFER NO-GO.** This checkpoint is documentation only, with no runtime or production changes and no paid inference.
