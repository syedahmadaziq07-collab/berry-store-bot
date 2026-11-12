# STEP 2 — Full-function isolated PostgreSQL clone

Snapshot of `public.berry_video_job` obtained **read-only** from staging pg_get_functiondef on 2026-11-12. The snapshot is installed in a GitHub Actions PostgreSQL 16 **ephemeral database** with schema-compatible test tables and a wallet dependency that unconditionally raises. No Supabase database connection or provider HTTP call.

The new CI job compiles the exact function snapshot, executes `claim_submit` with real row locks and budget updates against fake rows, tests duplicate and concurrent claims against a 500-cent cap, tests missing service-role fail-closed, tests wallet denial, and executes the **actual proposed migration and rollback scripts** against this ephemeral function. It compares the restored function definition to the original.

This is a more representative integration test than PR #71, but does not prove actual production tenant permissions, provider idempotency, pricing provenance, real wallet integration or a safe external POST. The proposed migration's operator evidence is still a caller-supplied string; do not treat it as independent provider verification. The ephemeral database is destroyed after CI.

**No migration applied to Supabase staging, no customer wallet writes, no paid generation, no Render deploy, no production. STEP 2 PARTIAL / NO-GO.**
