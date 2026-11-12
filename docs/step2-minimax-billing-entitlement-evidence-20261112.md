# STEP 2 — MiniMax H3 Max Turbo read-only billing and entitlement evidence

Date: 2026-11-12. Staging only. No paid inference, no account purchase, no customer activation, no production modifications.

## Official model/schema evidence
- Exact endpoint: `minimax/h3-max-turbo/text-to-video`.
- Input supports `duration` float and `resolution` enum `480P`, `768P`, `1080P`. Selected evaluation configuration is requested duration 10, resolution 480P, balanced prompt expansion and safety checker on.
- Official schema: output can run **up to about 0.7 seconds longer** than requested. Wording is approximate, **not** an enforceable contractual hard maximum of 10.7 billed seconds.
- Public fal pricing lists USD **0.025 per second** for this endpoint and notes settings can change final costs.
- Official API schema and public pricing do **not** establish whether invoice seconds are measured exactly, rounded to whole seconds, rounded up, or charged by requested vs delivered length. No hard invoice ceiling can be inferred.
Sources: https://fal.ai/models/minimax/h3-max-turbo/text-to-video/api ; https://fal.ai/pricing ; https://fal.ai/models/minimax/h3-max-turbo/text-to-video

## Authenticated staging evidence (existing, no new paid call)
Deployment `dep-dbqqbaifngtc738checg` LIVE, commit `441025479ae3db6f7daf046bbb4ebc81bd020099`.
Staging logs at 2026-11-12 11:40:58 UTC:
- `minimax/h3-max-turbo/text-to-video`: GET pricing HTTP 200, `pricing_read_verified`, USD `0.0175` per `seconds`.
- `fal-ai/flux/schnell`: USD `0.003` per `megapixels`.
- `fal-ai/wan/v2.2-a14b/text-to-video`: USD `0.08` per `seconds`.
This establishes authenticated pricing metadata read access ONLY. It does not establish that the MiniMax inference endpoint accepts this account, whether account has sufficient balance or usable concurrency, or that USD 0.0175 is permanent and applies to every 480P generation.

## Illustrations, not certified maximum cost
At 10 billed seconds, USD 0.175 using authenticated metadata; USD 0.25 using public listing.
At 10.7 billed seconds (hypothetical, not hard maximum), USD 0.18725 authenticated; USD 0.2675 public.
No claim about billing rounding, maximum cost, tax, FX, or all-in RM1 net margin is authorized.

## Account inference entitlement — NOT VERIFIED
Official documentation describes API key authentication and queue submission/status/result, but a pricing GET HTTP 200 does not prove entitlement to submit the exact model. No safe read-only account-specific inference-entitlement or balance check was identified in the reviewed official model documentation. Do not submit an inference request, even as a test. Provider dashboard/support or an explicitly documented authenticated read-only entitlement/balance endpoint must supply evidence. Never log key or full account details.

## Required provider questions before approval
1. For exact `minimax/h3-max-turbo/text-to-video`, `duration=10`, `resolution=480P`: what is the guaranteed maximum **billable** duration, including output overrun?
2. Are billable seconds based on requested duration, generated file duration, or another quantity? What rounding increments and minimums apply?
3. Is USD 0.0175/s from the authenticated pricing endpoint a promotional/account-specific/tier rate, and what is its validity/price-change policy relative to public USD 0.025/s?
4. Does the existing API key/account have inference entitlement for this exact endpoint, and how can entitlement, available balance, concurrency, and any additional surcharges be verified **without** submitting a paid job?

## Decision
**BLOCKED / NO-GO** for a hard maximum per-generation USD cost, retail price, RM1 net margin, and customer activation. Existing staging-only helper `minimum_video_sale_cents` is for verified inputs; it does not manufacture their provenance. Keep provider spending at zero and customer generation/checkout disabled. No production or wallet writes.
