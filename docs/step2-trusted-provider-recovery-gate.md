# STEP 2 — Trusted provider recovery gate (application-level only)

## What changed
Added `bind_with_provider_verification` as a fail-closed **pure application gate** for jobs stuck in `submission_unknown`. The gate rejects missing provider verification, HTTP-success-like truthy objects/strings, provider errors, mismatched request hashes, malformed request IDs and repeated binding. The new unit tests use only local fake callbacks; no external calls.

## Security boundary and remaining blockers
**This does not yet make STEP 2 PASS.** A caller-supplied `recovery_evidence` string in the proposed PR #70 SQL migration is not independent provider proof. The new gate is not wired to the worker, database RPC, or provider API. A malicious or mistaken caller could still assert verification if the existing SQL proposal were deployed. **Do not apply that migration yet.**

Before activation:
1. Establish whether fal.ai offers an authenticated, read-only lookup for a known request ID and a trustworthy way to correlate it to the original submission. Never invent an endpoint.
2. Persist correlation material *before* submission, and verify request ID, model and tenant/job association through a trusted server-side adapter. Reject ambiguous matches.
3. Ensure the SQL RPC requires server-authorized proof and is not directly callable with only a user-supplied evidence string. Consider a restricted, audited operator reconciliation workflow if the provider cannot independently prove association.
4. Test actual worker → provider adapter → SQL contract against an ephemeral PostgreSQL instance; include duplicate, mismatch, timeout and malicious-evidence cases.
5. Require separate approval before any live Supabase migration, wallet write, provider POST, or paid generation.

No external provider request, database write, customer wallet action or deployment was performed by this change.
