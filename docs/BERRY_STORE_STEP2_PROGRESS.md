# Berry Store STEP 2 — verified checkpoint (2026-11-12)

**Status: PARTIAL / NO-GO for real paid AI video generation.**

## GitHub evidence
- PR #72 merged: exact staging SQL function snapshot compiled and tested against ephemeral PostgreSQL.
- PR #73 merged: fail-closed trusted provider verification gate and regression tests; NOT connected to production worker.
- PR #74 merged: read-only mock RPC recovery preflight and regression tests; NOT connected to production worker.
- Four GitHub Actions workflows passed on PR #74 head `a839b312d662bde90575cdde4b1156e9b2d76b56`.
- PR #74 staging merge commit: `cfffb735153a15f4e725fba18c695f736de4c56b`.

## Official provider API findings
- Queue submit: POST `https://queue.fal.run/{owner}/{app}/{path}` for 3-part endpoint IDs; response includes request_id and status/result URLs.
- Queue status: GET `https://queue.fal.run/{owner}/{app}/requests/{request_id}/status` requires **known request_id**.
- Queue result: GET `https://queue.fal.run/{owner}/{app}/requests/{request_id}`.
- Documentation inspected does NOT establish a request lookup by caller-supplied correlation hash or an exactly-once idempotency key for the submit endpoint. **Never assume either exists.**
- Public pricing page lists `minimax/h3-max-turbo/text-to-video` at USD 0.025/video second, while previous account-authenticated pricing observations differed. Account-specific applicability and full billed duration must be verified before paid launch.
- Sources: https://fal.ai/docs/api-reference/inference-api/queue/submit-path ; https://fal.ai/docs/api-reference/inference-api/queue/status ; https://fal.ai/docs/api-reference/inference-api/queue/result ; https://fal.ai/docs/documentation/model-apis/pricing ; https://fal.ai/pricing

## Blocking gaps
1. No provider-authoritative correlation for a submission whose POST response was lost; status lookup requires known request ID. Manual operator evidence is not cryptographic proof.
2. Existing staging SQL allows caller-supplied `recovery_evidence` in proposed migration. **Do not apply PR #70 proposed SQL as-is**.
3. No durable, production-integrated worker protocol proven to prevent duplicate paid submissions after unknown POST outcome.
4. No live staging migration, wallet write, paid generation, or Render deploy has been authorized or executed.
5. Provider account entitlement, pricing applicability, hard billing duration, FX/fees, RM1 net margin, and staging E2E are not verified.

## Next safe engineering tasks
- Build a provider-agnostic, durable *no-retry* submission state machine with operator hold for unknown outcomes.
- Ensure worker never submits a second POST after a durable claim, even after restart.
- Create ephemeral Postgres worker integration tests for crash before/after POST, timeout, concurrent claim, and tenant isolation.
- Design a restricted operator reconciliation route that cannot accept arbitrary user-supplied proof.
- Validate account-specific fal pricing with read-only authenticated endpoint; do not call paid inference.
- Request separate approval for live staging migration and any spending, wallet writes or deployments.

**No claim of STEP 2 PASS until all release gates are verified.**
