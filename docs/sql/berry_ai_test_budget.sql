-- Berry Store — owner-approved RM5 acceptance-test budget + image job RPC.
-- PRODUCTION MIGRATION (additive-only, non-destructive). Apply ONLY after:
--   (1) Supabase backup verified by owner;
--   (2) ephemeral CI tests (tests/test_image_budget_guard.py,
--       tests/test_telegram_image_worker.py) PASS.
-- Rollback: drop functions then tables (additive schema; no existing rows
-- are modified; never reverse ledger entries to roll back).

BEGIN;

-- ── RM5 acceptance-test budget ledger (Image+Video combined) ───────────────
-- cap CHECK enforces the owner ceiling at the DATABASE level.
CREATE TABLE berry_private.ai_test_budgets (
  tenant_id uuid NOT NULL REFERENCES public.tenants(id),
  budget_id uuid NOT NULL,
  cap_cents integer NOT NULL CHECK(cap_cents > 0 AND cap_cents <= 500),
  used_cents integer NOT NULL DEFAULT 0 CHECK(used_cents >= 0),
  reserved_cents integer NOT NULL DEFAULT 0 CHECK(reserved_cents >= 0),
  generations integer NOT NULL DEFAULT 0 CHECK(generations >= 0),
  max_generations integer NOT NULL DEFAULT 5,
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK(used_cents + reserved_cents <= cap_cents),
  PRIMARY KEY(tenant_id, budget_id)
);
ALTER TABLE berry_private.ai_test_budgets ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON berry_private.ai_test_budgets FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON berry_private.ai_test_budgets TO service_role;

CREATE FUNCTION public.berry_ai_budget_claim(p_tenant uuid, p_budget uuid,
                                             p_cost_cents int, p_job uuid)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE b berry_private.ai_test_budgets%ROWTYPE;
BEGIN
 IF current_user NOT IN ('service_role','postgres') OR
  coalesce(current_setting('request.jwt.claims',true),'{}')::jsonb->>'role'
    IS DISTINCT FROM 'service_role' THEN
  RAISE EXCEPTION 'server role required' USING ERRCODE='42501'; END IF;
 IF p_cost_cents IS NULL OR p_cost_cents <= 0 OR p_job IS NULL THEN
  RAISE EXCEPTION 'invalid claim'; END IF;
 SELECT * INTO b FROM berry_private.ai_test_budgets
  WHERE tenant_id=p_tenant AND budget_id=p_budget
  FOR UPDATE;
 IF b.budget_id IS NULL OR b.expires_at <= now() THEN
  RAISE EXCEPTION 'budget expired or missing'; END IF;
 IF b.generations >= b.max_generations THEN
  RAISE EXCEPTION 'generation limit reached'; END IF;
 IF b.used_cents + b.reserved_cents + p_cost_cents > b.cap_cents THEN
  RAISE EXCEPTION 'worst-case exceeds RM5 ceiling'; END IF;
 UPDATE berry_private.ai_test_budgets
  SET reserved_cents = reserved_cents + p_cost_cents,
      generations = generations + 1
  WHERE tenant_id=p_tenant AND budget_id=p_budget;
 RETURN true;
END $$;
REVOKE ALL ON FUNCTION public.berry_ai_budget_claim(uuid,uuid,int,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.berry_ai_budget_claim(uuid,uuid,int,uuid) TO service_role;

COMMIT;
