BEGIN;
SELECT set_config('request.jwt.claims','{"role":"service_role"}',true);
DO $$
DECLARE t uuid:=gen_random_uuid(); first_batch jsonb; second_batch jsonb; overlap_count int;
BEGIN
 INSERT INTO public.tenants(id) VALUES(t);
 INSERT INTO public.ai_wallets(tenant_id,user_id,balance) VALUES(t,900000088,0);
 -- Queue-selection fixtures only; deliberately no wallet or provider operation.
 INSERT INTO berry_private.ai_video_jobs(tenant_id,job_id,user_id,request_hash,arguments,quote,debit_cents,state)
 SELECT t,gen_random_uuid(),900000088,repeat('a',64),'{}','{}',200,'reserved' FROM generate_series(1,25);
 INSERT INTO berry_private.ai_video_jobs(tenant_id,job_id,user_id,request_hash,arguments,quote,debit_cents,state)
 SELECT t,gen_random_uuid(),900000088,repeat('a',64),'{}','{}',200,'submission_unknown';
 EXECUTE 'SET LOCAL ROLE service_role';
 first_batch:=public.berry_video_recoverable_jobs(t,20);
 second_batch:=public.berry_video_recoverable_jobs(t,5);
 EXECUTE 'RESET ROLE';
 SELECT count(*) INTO overlap_count FROM jsonb_array_elements(first_batch) a JOIN jsonb_array_elements(second_batch) b ON a->>'job_id'=b->>'job_id';
 IF jsonb_array_length(first_batch)<>20 OR jsonb_array_length(second_batch)<>5 OR overlap_count<>0 THEN
  RAISE EXCEPTION 'held jobs starve later candidates'; END IF;
 IF EXISTS(SELECT 1 FROM berry_private.ai_video_jobs WHERE tenant_id=t AND state='submission_unknown' AND last_recovery_scan_at IS NOT NULL) THEN
  RAISE EXCEPTION 'unknown job scanned for automatic recovery'; END IF;
 IF EXISTS(SELECT 1 FROM berry_private.ai_video_jobs WHERE tenant_id=t AND state NOT IN ('reserved','submission_unknown')) THEN
  RAISE EXCEPTION 'scan changed lifecycle state'; END IF;
 IF EXISTS(SELECT 1 FROM public.ai_wallet_transactions WHERE tenant_id=t) THEN RAISE EXCEPTION 'scan touched money'; END IF;
END $$;
SELECT 'PASS:25 held jobs fairly scanned across20+5, unknown excluded, service-role access, no lifecycle/ledger mutation' AS evidence;
ROLLBACK;
