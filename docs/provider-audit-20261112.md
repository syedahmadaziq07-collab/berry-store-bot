# Provider audit — 12 November 2026 MYT

Customer launch NO-GO. No production changes, provider calls or spend.

- PASS code identification: fal.ai queue transport, credential name FAL_KEY. This is a server-only
  connector, not evidence of an active paid production provider.
- PASS actual isolated mapping: revision4 video public label Berry Video Wan2.2,
  provider_model_id fal-ai/wan/v2.2-a14b/text-to-video, enabled=false, credit_cost=0.
  Generic submission URL: https://queue.fal.run/fal-ai/wan/v2.2-a14b/text-to-video .
  Parameter/schema/account acceptance and real inference not validated.
- Legacy Gemini Omni Flash 15s720p UI is preview, not active routing. PixVerse3.5 image-to-video
  lives in old unmerged drafts14/27. Wan2.2-5B tests are fixtures, not the configured A14B model.
- BLOCKED key presence until staging startup presence-only metadata is deployed. Metadata iterates
  environment names only; does not retrieve secret values. No public configuration endpoint added.
- BLOCKED provider account authorization, model access and usable existing balance: neither public
  docs nor key-name presence proves those. No purchases, top-ups or auto-top-up allowed.
- BLOCKED exact maximum cost: need authenticated model pricing/estimate for exact duration, frames,
  resolution, output count and settings; FX settlement upper bound, conversion/payment fees,
  tax/storage/operating allocation and failure/refund allocation. No number invented or enabled.
- PASS existing fail-closed budget/pricing gates: unknown outcome consumes its full reserved test
  cost/count, never grants another provider POST; RM5/5 ceilings and no grant seeded. Customer price
  must be a multiple of RM0.02 (25 credits), revenue minus verified ALL-IN cost at least RM1.
  With revenue-proportional fee fraction f and fixed all-in cost C, price floor is
  ceil_to_RM0.02((C+RM1)/(1-f)). C must include provider bound, FX/fees and other allocated costs.
  A fixture/allocation assumption is not independent RM1 NET proof.

## Official evidence

https://fal.ai/models/fal-ai/wan/v2.2-a14b/text-to-video : official page currently announces removal
on4 January2027, recommending migration. Do not commit a long-term customer launch to it without
reviewing successor/model cost. Current page did not expose an exact price in retrieved content.
https://fal.ai/docs/documentation/model-apis/pricing : authenticated pricing endpoint
GET https://api.fal.ai/v1/models/pricing?endpoint_id=MODEL_ID ; never generate to discover cost.
https://fal.ai/models/fal-ai/pixverse/v3.5/image-to-video : public5s example USD0.20 at720p,
USD0.40 at1080p, USD0.15 at360p/540p. Those are not A14B prices or all-in MYR maxima.
https://fal.ai/models/google/gemini-omni-flash/reference-to-video : token billing, approxUSD0.13/s
at720p; approximation is not a maximum and cannot authorize spend within RM5.
https://fal.ai/docs/documentation/model-apis/request-tags : X-Fal-Tags supports correlation;
account tag reporting must be enabled by provider. Tags alone are not an idempotency guarantee.

Next: deploy metadata to staging and report presence only, then implement audited reconciliation.
Actual activation needs controlled bot identity, secure provider account authorization, verified
cost/access/balance and runtime E2E. Production still requires backup/rotation/migration safety and
specific owner deployment approval. Do not ask owner to calculate pricing or inspect source.
