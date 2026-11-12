# STEP 2 — Mock Supabase RPC adapter and pre-submit safety blocker
Date: 2026-11-12. **No live Supabase RPC calls, wallet writes or provider inference.**

## Read-only staging SQL evidence
`public.berry_video_job(p_tenant uuid,p_job uuid,p_action text,p_payload jsonb)` and `public.berry_video_reconcile(p_tenant uuid,p_job uuid,p_case uuid,p_action text,p_evidence jsonb)` were confirmed from staging `pg_proc` metadata.
- `claim_submit` atomically reserves budget against `berry_private.ai_video_test_budgets` for an already-reserved job, checking expiry, user, maximum cost and generation count, then sets state `submitting`.
- `queued` accepts first provider request binding **only from `submitting`** (or idempotent repeated binding after queued/completion).
- `submission_unknown` changes `submitting` to `submission_unknown`; **`queued` cannot subsequently bind a newly returned provider request from `submission_unknown`**.
- This makes a durable pre-submit uncertainty marker incompatible with successful request-ID binding under current SQL. An unguarded crash after POST while state is `submitting` could cause a duplicate submit on restart. **Do not wire paid provider transport until state protocol is reviewed and fixed in a separate authorized migration.**
- The `reserve` action debits customer wallet; it was NOT called. No staging SQL writes occurred.

## Mock-only implementation
`step2_mock_supabase_rpc_adapter.py` accepts only injected fake RPC/provider objects. It maps `claim_submit` to the exact Supabase RPC argument keys, rejects unconfirmed/ambiguous claims, forbids any provider submit even after a fake claim, and allows read-only fake polling of a previously bound queued request.
`tests/test_step2_mock_supabase_rpc_adapter.py` covers fake claim, duplicate claim, RPC timeout unknown outcome, no outbound even after claim, and restart recovery using persisted request ID. All use in-memory mocks; no actual Supabase connection, budget grant, provider request, customer wallet, Render deploy or production access.

## Decisions
- **Atomic budget claim: DB SQL logic inspected, mocked RPC contract tested; not live integration PASS.**
- **Paid submission: BLOCKED by missing safe durable pre-submit protocol.**
- **Real recovery and concurrency: NOT TESTED.** No production-ready worker exists.
- **RM5** remains a maximum budget, never authorization to spend. Provider hard billed-duration ceiling, FX, fees and RM1 net margin remain unverified.
- **STEP 2 PARTIAL / customer generation NO-GO.**
