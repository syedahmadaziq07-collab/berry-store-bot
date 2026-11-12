# STEP 2 — MiniMax authenticated pricing and maximum-cost gate (2026-11-12)

Scope: read-only staging evidence; no paid inference, no customer checkout/generation, no production or wallet writes.

## Observed, independently from Render staging deployment dep-dbqq71mi0phs73de7hng

GET pricing authenticated HTTP 200; `pricing_read_verified`:
- `minimax/h3-max-turbo/text-to-video`: USD 0.0175 per `seconds`
- `fal-ai/flux/schnell`: USD 0.003 per `megapixels`
- `fal-ai/wan/v2.2-a14b/text-to-video`: USD 0.08 per `seconds`
Pricing lookup is **not** account inference authorization, account balance, or a maximum invoice guarantee.
Prior PR51 reference public rate USD 0.025 per output second differs from the authenticated USD 0.0175. Do not assume either rate remains valid indefinitely, nor treat authenticated price as permanent/non-promotional without provider confirmation.

## MiniMax selected configuration and unresolved billing ceiling

Selected for evaluation: 10s requested duration, 480P, text-to-video, balanced prompt expansion, safety enabled. Prior official-schema research notes approximately 0.7s output overrun. Approximate overrun is **not** a contractual maximum; 10s requested is not proof of <=10 billed seconds. Provider billing may have rounding or additional units. No paid test authorized.

At authenticated rate: 10 exactly billed seconds = USD 0.175; 10.7 hypothetical billed seconds = USD 0.18725. These are illustrations, NOT maximum cost. Reference public rate at 10s = USD 0.25; 10.7s = USD 0.2675. Avoid mixing public and authenticated prices.

## Mandatory retail gate (FAIL CLOSED)

Only after provider confirms rate applicability and hard max billed seconds for exact model/params, upper-bound FX, FX spread/taxes, storage/hosting/delivery allocation and revenue-proportional fees:
`provider_usd_bound = verified_unit_usd_per_second * verified_max_billable_seconds`
`minimum_retail_myr = round_up_to_RM0.02((provider_usd_bound * verified_fx_bound + verified_fixed_myr_cost + RM1)/(1 - verified_revenue_fee_fraction))`
Berry Credits = MYR retail * 1250. The helper `minimum_video_sale_cents` requires explicit finite positive seconds and unit price; it cannot independently certify their provenance. Missing/unbounded/stale inputs: block offer activation and customer checkout.

## Remaining blockers and next safe evidence

1. Confirm exact MiniMax 10s/480P inference entitlement, usable account balance and concurrency via authorized read-only account controls; pricing GET does not prove these.
2. Obtain provider-backed hard maximum billable duration and billing rounding rule, including output overrun; absent guarantee means cannot certify hard cost bound.
3. Confirm whether authenticated USD 0.0175 is a permanent applicable account rate, promo, tier or time-limited discount.
4. Obtain conservative documented USD/MYR upper-bound and complete FX/settlement/tax/hosting/storage/delivery/revenue fee bounds.
5. Only then compute retail price, obtain owner approval and proceed to isolated staging runtime/E2E gates under separately authorized spending. No paid generation now.

Existing customer-facing mapping remains disabled; provisional RM2.50/3125 credits is NOT approved. STEP 2 PARTIAL; launch NO-GO.
