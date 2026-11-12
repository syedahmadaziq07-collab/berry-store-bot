# STEP 2 — Isolated PostgreSQL rollback-only checkpoint

## Scope
A new GitHub Actions workflow starts an **ephemeral PostgreSQL 16 service** with hardcoded non-secret test credentials. `tests/test_step2_postgres_rollback.py` uses only this local service (`127.0.0.1`), session-local `pg_temp` tables/functions and explicit `ROLLBACK` in teardown. No Supabase URL, service-role credential, production or customer wallet is used.

## Real PostgreSQL tests
- Atomic UPDATE reservation on temporary budget and job tables, with cap 500 cents and generation limit.
- Budget exhaustion, duplicate claim, CHECK constraint on max 500 cents.
- Ambiguous state recovery binds a request once, cannot overwrite it.
- Two independent transactions check advisory lock exclusion and lock release on rollback.
- PostgreSQL text replacement round-trip checks migration/rollback fingerprint behavior against **synthetic text only**.

## Crucial limits
These are actual PostgreSQL tests but **not execution of live `public.berry_video_job` or the proposed SQL migration**. The real SQL uses service-role checks, wallet reservations, tenant keys and other dependencies, so it is deliberately never invoked. The PostgreSQL tests simulate the relevant atomic budget pattern with temporary fixture functions. The migration script is **NOT APPLIED** and its PL/pgSQL replacement function has **NOT been compiled/executed** in PostgreSQL. The advisory-lock test proves lock exclusion, not full concurrent budget contention under the live function. The migration's operator evidence remains caller-provided, not independently authenticated provider proof.

CI must show this new workflow PASS in addition to existing three gates. If the new workflow is skipped or not triggered, do not claim real PostgreSQL test PASS.

## Decision
STEP 2 PARTIAL / NO-GO. Next gate is an isolated clone of the full live function with fake wallet dependencies and verified SQL compile/rollback; only then consider controlled staging migration review. No paid generation, wallet writes, customer activation, production change or Render deploy.
