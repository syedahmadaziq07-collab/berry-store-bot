# STEP 2 — Balanced AI provider/model decision (draft, NOT activation)

Date: 2026-11-12. Owner chose Balanced. Customer launch remains NO-GO. This document is a shortlist and acceptance contract, not evidence of live account pricing or authorization.

## Candidate routes (disabled until acceptance)

| Tier | Candidate fal.ai endpoint | Status |
| --- | --- | --- |
| Image Fast | `fal-ai/flux/schnell` | Existing rev4 mapping, disabled; existing 4-credit price invalid |
| Image Balanced | `fal-ai/flux-2-pro` | Candidate only; verify official schema and account entitlement |
| Video Budget 10s (owner selected) | `minimax/h3-max-turbo/text-to-video` | SELECTED for evaluation, NOT verified or enabled; check endpoint, exact 10s/480p support and authenticated pricing |
| Video fallback | `fal-ai/ltx-2.3/text-to-video` or `wan/v2.6/text-to-video` | Candidates only; compare if selected MiniMax fails budget/technical gates |

Do not use Wan 2.2 A14B as a long-term default: audit notes provider-announced retirement 2027-01-04. Existing mapping must remain disabled until migrated and verified.

## Owner's *draft* retail prices (not approved for production)

- Image Fast RM1.50 = 1,875 credits
- Image Balanced RM2.00 = 2,500 credits
- Video Budget 10s: RM2.50 = 3,125 credits, **provisional only**; user selected the model, not a verified selling price. Prior estimate US$0.025/s for 480p text-to-video is NOT authenticated billing proof. Reference-to-video screenshot shows US$0.05/s at 480p plus reference input charges; do not substitute that route or price. Confirm exact text-to-video endpoint, duration and all-in margin before setting retail.

1 MYR = 1,250 credits. Actual MYR debit must be ledger-authoritative; credit display is derived. Prices must be validated against the final cost before any enablement.

## Mandatory cost gate

For the selected MiniMax text-to-video route, explicitly verify 10-second duration and cheapest supported resolution. For each exact model, duration, resolution, image count and parameter set: use authenticated read-only pricing/estimate where available; bind timestamped price and max billable units, account entitlement, usable balance, upper-bound FX, settlement fees, tax, storage, retries and operational/failure allocation. Never infer a maximum from an approximate marketing price.

Let C be *verified worst-case all-in MYR cost*, f be any revenue-proportional fee fraction (0 <= f < 1), P be retail MYR. Require `P * (1 - f) - C >= RM1.00`. Round required retail price UP to the supported MYR step (currently RM0.02), and fail closed if any input is absent, stale or unbounded. If the owner's draft price fails, propose a revised price for approval; do not silently change or enable.

Official read-only pricing API documented in prior provider audit: `GET https://api.fal.ai/v1/models/pricing?endpoint_id=MODEL_ID`. Never log tokens or raw secret-bearing responses. Do not purchase credits or infer account balance from environment-variable presence.

## Required remaining STEP 2 work

1. Finish unknown-outcome reconciliation from WIP branch, including SQL and race/restart tests. Unknown submission/delivery must not be blindly refunded or resubmitted.
2. Implement and test private durable provider mapping for both image and video; retain disabled flags.
3. Verify provider pricing, schema and access independently for each candidate; confirm real runtime offer builder and cost-bound quote.
4. Validate controlled staging runtime, startup/shutdown, recovery, monitoring and Telegram identity without paid inference.
5. Run regression, isolated SQL and CI; produce reviewable PR(s) against staging with precise PASS/BLOCKED evidence.

No production deploy, customer activation, wallet/order mutation or paid generation is authorized by this document. Prior test cap RM5 total and <=5 paid generations remains an upper limit, not authorization to spend. Production release needs separate approval.
