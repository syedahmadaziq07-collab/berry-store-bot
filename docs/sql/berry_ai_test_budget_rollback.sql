-- Rollback for berry_ai_test_budget.sql (additive-only migration).
-- Safe: no existing business rows are touched. Never reverse ledger entries.
BEGIN;
DROP FUNCTION IF EXISTS public.berry_ai_budget_claim(uuid,uuid,int,uuid);
DROP TABLE IF EXISTS berry_private.ai_test_budgets;
COMMIT;
