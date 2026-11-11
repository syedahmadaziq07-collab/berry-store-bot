-- ISOLATED AI STAGING ONLY. Synthetic credit prototype, not the MYR customer ledger.
-- Existing berry_private.ai_wallet_test_* tables must be present.
CREATE OR REPLACE FUNCTION public.berry_ai_test_reserve(
 p_tenant uuid, p_user bigint, p_job uuid, p_credits bigint
) RETURNS text LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE j record; n bigint;
BEGIN
 IF current_user NOT IN ('service_role','postgres') THEN
  RAISE EXCEPTION 'server role required' USING ERRCODE='42501';
 END IF;
 IF p_tenant IS NULL OR p_job IS NULL OR p_user IS NULL OR p_credits IS NULL
    OR p_user<=0 OR p_credits<=0 THEN RAISE EXCEPTION 'invalid reservation'; END IF;
 -- A replay waits for the original transaction before reading its result.
 -- Use the same lock for reserve and refund, before row locks.
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(
   'berry-test-job:'||p_tenant::text||':'||p_job::text,0));
 SELECT * INTO j FROM berry_private.ai_wallet_test_jobs WHERE tenant_id=p_tenant AND job_id=p_job;
 IF FOUND THEN
  IF j.user_id<>p_user OR j.credits<>p_credits THEN RAISE EXCEPTION 'idempotency conflict'; END IF;
  RETURN j.status;
 END IF;
 UPDATE berry_private.ai_wallet_test_balances SET balance_credits=balance_credits-p_credits
  WHERE tenant_id=p_tenant AND user_id=p_user AND balance_credits>=p_credits
  RETURNING balance_credits INTO n;
 IF NOT FOUND THEN RAISE EXCEPTION 'insufficient credits'; END IF;
 INSERT INTO berry_private.ai_wallet_test_jobs(tenant_id,job_id,user_id,credits,status)
  VALUES(p_tenant,p_job,p_user,p_credits,'reserved');
 RETURN 'reserved';
END $$;

CREATE OR REPLACE FUNCTION public.berry_ai_test_refund(p_tenant uuid,p_job uuid)
RETURNS text LANGUAGE plpgsql SECURITY INVOKER SET search_path = '' AS $$
DECLARE j record;
BEGIN
 IF current_user NOT IN ('service_role','postgres') THEN
  RAISE EXCEPTION 'server role required' USING ERRCODE='42501';
 END IF;
 IF p_tenant IS NULL OR p_job IS NULL THEN RAISE EXCEPTION 'invalid refund'; END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(
   'berry-test-job:'||p_tenant::text||':'||p_job::text,0));
 SELECT * INTO j FROM berry_private.ai_wallet_test_jobs
  WHERE tenant_id=p_tenant AND job_id=p_job FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'unknown job'; END IF;
 IF j.status='refunded' THEN RETURN 'refunded'; END IF;
 IF j.status<>'reserved' THEN RAISE EXCEPTION 'job cannot refund automatically'; END IF;
 UPDATE berry_private.ai_wallet_test_balances SET balance_credits=balance_credits+j.credits
  WHERE tenant_id=p_tenant AND user_id=j.user_id;
 IF NOT FOUND THEN RAISE EXCEPTION 'wallet missing'; END IF;
 UPDATE berry_private.ai_wallet_test_jobs SET status='refunded' WHERE tenant_id=p_tenant AND job_id=p_job;
 RETURN 'refunded';
END $$;
REVOKE ALL ON FUNCTION public.berry_ai_test_reserve(uuid,bigint,uuid,bigint) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.berry_ai_test_refund(uuid,uuid) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.berry_ai_test_reserve(uuid,bigint,uuid,bigint) TO service_role;
GRANT EXECUTE ON FUNCTION public.berry_ai_test_refund(uuid,uuid) TO service_role;
