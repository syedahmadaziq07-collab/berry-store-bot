# Durable isolated staging jobs

This release adds a server-only job store and worker protocol in `staging_job_worker.py`.
It does not activate customer generation, Telegram polling, actual top-ups or paid provider calls.
Only `https://cirsdvkfkvypprnmyykk.supabase.co` is accepted by the new store. Tables are separate
synthetic wallets in `berry_private`; existing shop/customer wallets are never referenced.

## Verified behavior

- Reserve the MYR debit in integer cents, job snapshot and debit ledger in one transaction.
- Exact credit/MYR equivalence and supplied all-in cost plus RM1 arithmetic guard.
- Store only argument digest, user identity, quote and provider/delivery identifiers; raw prompts are not saved.
- Replay the same job and payload without charging again; reject a changed user, quote or argument hash.
- Acquire a durable submission claim before provider calls; a new process cannot consume it twice.
- Bind provider success/failure to the stored provider request ID.
- Refund once on pre-submit cancellation or definitive queued provider failure.
- On network timeout or an external result whose DB persistence fails, hold `submitting`/`submission_unknown`.
  Never resubmit or refund automatically. This protects against a second bill after an unknown first outcome.
- Claim delivery once; hold ambiguous Telegram sends as `delivery_unknown` without another automatic send.
- Reject anon/authenticated RPC execution. Use RLS and revoked private-table access, with a trusted server role only.

`docs/sql/verify_staging_job_lifecycle.sql` ran successfully against isolated staging and rolled
back all test data. It verifies success-to-delivery, immutable replay, mismatch rejection,
refund-once, no refund after delivery, unknown submission/delivery hold, reconciliation and execution grants.
The first SQL test exposed a Postgres regex repetition limit in request ID validation; that
was fixed with an explicit character-length check and the entire SQL suite passed afterward.

107 Python tests pass locally. Worker tests use a protocol fixture and mocked provider/Telegram
effects. They are not real provider/Telegram E2E. New modules are packaged and syntax-checked
in the isolated admin image but are not automatically started.

## Deployment and migration scope

Applied only to cirsdvkfkvypprnmyykk:
1. `isolated_staging_job_lifecycle`
2. `bind_staging_results_to_provider_request`
3. `fix_staging_provider_identifier_validation`

The SQL source represents the final function and table state. Apply its table setup only to a
new isolated environment; existing staging has the migration already. No production migration
or customer wallet integration was performed. The legacy boolean-callback submission method
now always fails closed because verification alone did not atomically consume a submission.

## Remaining launch gates

The supplied cost reference is an audit field, not proof that provider costs are verified.
Independent provider price/size/duration, FX, payment fees, retries, refunds and operating
allocation still need validation. Paid inference and real Telegram delivery remain disabled
by default and need owner-authorized test budget plus a dedicated staging bot.

Unknown outcomes need an audited operator reconciliation flow before customer launch;
manual DB edits or blind retries are not an approved recovery workflow. No automated
recovery daemon starts in this release. Full shop/payment fixture integration and authenticated
browser E2E remain separate work items.
