# STEP 2 — Runtime polling, recovery, idempotency and budget-guard checkpoint
Date: 2026-11-12. Staging read-only inspection only. No inference, checkout, wallet writes, production access or deploy.

## Verified runtime and database evidence
- Render service `srv-dbq2g9mk1f9s73de0u50`, `berry-gemini-admin-staging`, Docker Free, one instance, manual deploy (`autoDeploy=no`), branch `deploy/berry-ai-private-mapping-staging-20261111`.
- Render deployment `dep-dbqqbaifngtc738checg` is LIVE at commit `441025479ae3db6f7daf046bbb4ebc81bd020099` (PR #61). Subsequent documentation PRs #62–#64 are merged on staging GitHub but not deployed; no runtime drift claim beyond this fact.
- Supabase staging `cirsdvkfkvypprnmyykk` metadata confirms `berry_private.ai_video_jobs`, `ai_video_job_events`, `ai_video_reconciliation_cases`, `ai_video_test_budgets`, `ai_video_tickets`, `staging_ai_jobs`, `staging_job_ledger`, `staging_job_wallets` and other test structures exist.
- Read-only aggregate SELECT returned 0 rows in `ai_video_jobs`, 0 in `ai_video_reconciliation_cases`, 0 in `ai_video_test_budgets` at inspection time. Zero rows is a clean snapshot, not proof of worker/recovery/budget correctness.

## Code audit
- `provider_readiness.py` contains read-only authenticated pricing probe gated to isolated staging service and staging mapping DB, with no inference call; `minimum_sale_cents` and `minimum_video_sale_cents` validate numerical cost bounds but cannot prove provenance. Unknown provider billing ceiling/FX/fees => customer quote NO-GO.
- `ai_model_mapping_store.py` uses server-side mapping RPC, expected revision and idempotency key for mapping changes; this is NOT AI generation job idempotency.
- `topup_checkout.py` uses stable idempotency keys and avoids retrying unknown HTTP outcomes; this is top-up order idempotency, NOT provider inference idempotency.
- Prior staging SQL reconciliation suites were reported passing in PR #50 and associated audit, but were NOT re-executed during this read-only checkpoint. No live AI worker jobs were created.

## Runtime gate matrix
| Gate | Evidence | Decision |
|---|---|---|
| Staging service identity and live deploy | Render service and deploy metadata | PASS |
| Pricing metadata GET | Previously observed HTTP 200 for selected models, not re-run here | PREVIOUSLY VERIFIED |
| Polling loop bounded intervals, stop conditions, backoff, queue timeouts | No live job exercised and no worker-specific implementation verified in this checkpoint | UNVERIFIED |
| Recovery after crash/restart and orphaned job reconciliation | Existing SQL structures and historical suite evidence only | PARTIAL |
| Provider submit idempotency and unknown-outcome no-double-charge | Historical SQL reconciliation evidence; no provider contract or live submission | PARTIAL |
| Budget reservation, hard RM5 cap, concurrency and retry accounting | Budget table exists but 0 rows; no atomic enforcement proven here | BLOCKED |
| All-in maximum billed seconds/FX/fees and RM1 net | Provider/merchant proof missing | BLOCKED |
| Customer checkout/generation | Explicitly disabled | NO-GO |

## Next safe tests (must be isolated, zero-cost)
1. Inspect exact staging SQL functions and runtime worker source with explicit path references; prove lock, transition and budget invariants via unit and SQL transaction rollback tests, not production tables.
2. Add mock HTTP provider tests for queued/running/completed/failed/cancelled, duplicate callbacks, timeout/unknown submit, restart recovery, concurrency, stale leases, no blind retry and cap exhaustion. Use only mocked network, never fal inference.
3. Verify that RM5 is a *ceiling* and not permission to spend, and that no code path can create a paid request without separately authorized owner action.
4. Inspect CI results for any new test-only PR, then review/merge staging only. Do not deploy unless code changes and safety checks explicitly justify it.
5. Keep customer checkout and generation off until provider billing ceiling, entitlement, cost bounds and account-specific fees are verified.

## Decision
**STEP 2 PARTIAL / NO-GO**. This audit does not claim a working generation worker or certified budget guard. No production, wallet or paid operations performed.
