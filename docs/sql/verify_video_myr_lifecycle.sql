-- Run ONLY in isolated validation, after the candidate schema. All dummy data rolls back.
BEGIN;
SELECT set_config('request.jwt.claims','{"role":"service_role"}',true);
DO $$
DECLARE t uuid:=gen_random_uuid(); j uuid:=gen_random_uuid(); j2 uuid:=gen_random_uuid();
 j3 uuid:=gen_random_uuid(); j4 uuid:=gen_random_uuid(); budget uuid:=gen_random_uuid(); r jsonb; p jsonb; b numeric; n bigint; rejected boolean;
BEGIN
 INSERT INTO public.tenants(id) VALUES(t);
 INSERT INTO berry_private.ai_video_test_budgets(tenant_id,budget_id,test_user_id,max_cost_cents,max_generations,expires_at)
 VALUES(t,budget,900000088,200,2,now()+interval '1 hour');
 PERFORM public.ai_wallet_apply_transaction(t,900000088,5,'topup','video-fixture:fund','fixture');
 p:=jsonb_build_object('user_id',900000088,'request_hash',repeat('a',64),'arguments',jsonb_build_object('prompt','isolated fixture'),
 'quote',jsonb_build_object('tool_key','video','provider_model_id','fal-ai/wan/v2.2-5b/text-to-video',
 'mapping_revision',1,'credits',2500,'debit_cents',200,'all_in_cost_cents',100,'cost_reference','fixture arithmetic only'));
 r:=public.berry_video_job(t,j,'reserve',p);
 PERFORM public.berry_video_job(t,j,'reserve',p);
 SELECT balance INTO b FROM public.ai_wallets WHERE tenant_id=t AND user_id=900000088;
 SELECT count(*) INTO n FROM public.ai_wallet_transactions WHERE tenant_id=t AND kind='debit';
 IF b<>3 OR n<>1 THEN RAISE EXCEPTION 'double debit'; END IF;
 rejected:=false;
 BEGIN PERFORM public.berry_video_job(t,j,'reserve',jsonb_set(p,'{arguments,prompt}','"changed"'));
 EXCEPTION WHEN raise_exception THEN rejected:=SQLERRM='idempotency conflict'; END;
 IF NOT rejected THEN RAISE EXCEPTION 'changed prompt replay accepted'; END IF;
 r:=public.berry_video_job(t,j,'claim_submit',jsonb_build_object('budget_id',budget));
 IF r->>'claimed'<>'true' THEN RAISE EXCEPTION 'submit not claimed'; END IF;
 r:=public.berry_video_job(t,j,'claim_submit',jsonb_build_object('budget_id',budget));
 IF r->>'claimed'<>'false' THEN RAISE EXCEPTION 'duplicate submit claimed'; END IF;
 PERFORM public.berry_video_job(t,j,'submission_unknown');
 rejected:=false;
 BEGIN PERFORM public.berry_video_job(t,j,'refund_before_submit');
 EXCEPTION WHEN raise_exception THEN rejected:=true; END;
 IF NOT rejected THEN RAISE EXCEPTION 'ambiguous refund allowed'; END IF;
 IF (SELECT reserved_generations FROM berry_private.ai_video_test_budgets WHERE tenant_id=t)<>1 THEN RAISE EXCEPTION 'duplicate budget charge'; END IF;
 -- A second job is refunded once before submission, using the same actual MYR ledger.
 PERFORM public.berry_video_job(t,j2,'reserve',p);
 PERFORM public.berry_video_job(t,j2,'refund_before_submit');
 PERFORM public.berry_video_job(t,j2,'refund_before_submit');
 SELECT balance INTO b FROM public.ai_wallets WHERE tenant_id=t AND user_id=900000088;
 IF b<>3 THEN RAISE EXCEPTION 'refund replay mismatch'; END IF;
 -- Failed reservations must not leave either job or debit behind.
 rejected:=false;
 BEGIN PERFORM public.berry_video_job(t,j3,'reserve',jsonb_set(jsonb_set(p,'{quote,debit_cents}','600'),'{quote,credits}','7500'));
 EXCEPTION WHEN raise_exception THEN rejected:=SQLERRM='Insufficient wallet balance'; END;
 IF NOT rejected OR EXISTS(SELECT 1 FROM berry_private.ai_video_jobs WHERE tenant_id=t AND job_id=j3) THEN
  RAISE EXCEPTION 'failed debit left a job'; END IF;
 -- Definitive provider failure needs a bound request and evidence; unknown holds cannot use it.
 PERFORM public.berry_video_job(t,j3,'reserve',p);
 PERFORM public.berry_video_job(t,j3,'claim_submit',jsonb_build_object('budget_id',budget));
 PERFORM public.berry_video_job(t,j3,'queued',jsonb_build_object('provider_request_id','fixture-1',
 'queue_status_url','https://queue.fal.run/fal-ai/wan/requests/fixture-1/status',
 'queue_result_url','https://queue.fal.run/fal-ai/wan/requests/fixture-1'));
 rejected:=false;
 BEGIN PERFORM public.berry_video_job(t,j3,'provider_failed','{"provider_request_id":"fixture-1"}');
 EXCEPTION WHEN raise_exception THEN rejected:=true; END;
 IF NOT rejected THEN RAISE EXCEPTION 'failure without evidence refunded'; END IF;
 PERFORM public.berry_video_job(t,j3,'provider_failed','{"provider_request_id":"fixture-1","failure_evidence":"fixture confirmed terminal failure"}');
 PERFORM public.berry_video_job(t,j3,'provider_failed','{"provider_request_id":"fixture-1","failure_evidence":"fixture confirmed terminal failure"}');
 IF (SELECT reserved_cost_cents FROM berry_private.ai_video_test_budgets WHERE tenant_id=t)<>200 THEN RAISE EXCEPTION 'budget reservation mismatch'; END IF;
 SELECT balance INTO b FROM public.ai_wallets WHERE tenant_id=t AND user_id=900000088;
 IF b<>3 OR b<>(SELECT sum(amount) FROM public.ai_wallet_transactions WHERE tenant_id=t) THEN
  RAISE EXCEPTION 'MYR ledger reconciliation mismatch'; END IF;
 IF NOT EXISTS(SELECT 1 FROM berry_private.ai_video_job_events
  WHERE tenant_id=t AND job_id=j3 AND action='provider_failed'
   AND evidence->>'failure_evidence'='fixture confirmed terminal failure') THEN
  RAISE EXCEPTION 'missing failure audit'; END IF;
 -- Exhausted budget must leave the next job reserved with no outbound submission claim.
 PERFORM public.berry_video_job(t,j4,'reserve',p);
 rejected:=false;
 BEGIN PERFORM public.berry_video_job(t,j4,'claim_submit',jsonb_build_object('budget_id',budget));
 EXCEPTION WHEN raise_exception THEN rejected:=SQLERRM='approved test budget unavailable or exhausted'; END;
 IF NOT rejected OR (public.berry_video_job(t,j4,'get')->>'state')<>'reserved' THEN
  RAISE EXCEPTION 'exhausted budget claimed submission'; END IF;
 PERFORM public.berry_video_job(t,j4,'refund_before_submit');
 rejected:=false;
 BEGIN UPDATE berry_private.ai_video_test_budgets SET max_cost_cents=501 WHERE tenant_id=t;
 EXCEPTION WHEN check_violation THEN rejected:=true; END;
 IF NOT rejected THEN RAISE EXCEPTION 'owner budget ceiling bypassed'; END IF;
 rejected:=false;
 BEGIN UPDATE berry_private.ai_video_test_budgets SET max_generations=6 WHERE tenant_id=t;
 EXCEPTION WHEN check_violation THEN rejected:=true; END;
 IF NOT rejected THEN RAISE EXCEPTION 'generation ceiling bypassed'; END IF;
 -- Exercise the invoker permissions as the actual worker role, not just postgres.
 EXECUTE 'SET LOCAL ROLE service_role';
 PERFORM public.berry_video_job(t,j,'get');
 rejected:=false;
 BEGIN UPDATE berry_private.ai_video_test_budgets SET max_cost_cents=500 WHERE tenant_id=t;
 EXCEPTION WHEN insufficient_privilege THEN rejected:=true; END;
 IF NOT rejected THEN RAISE EXCEPTION 'worker expanded approved budget'; END IF;
 EXECUTE 'RESET ROLE';
 IF has_function_privilege('anon','public.berry_video_job(uuid,uuid,text,jsonb)','EXECUTE')
 OR has_function_privilege('authenticated','public.berry_video_job(uuid,uuid,text,jsonb)','EXECUTE') THEN
  RAISE EXCEPTION 'public job access'; END IF;
 PERFORM set_config('request.jwt.claims','{"role":"anon"}',true);
 rejected:=false;
 BEGIN PERFORM public.berry_video_job(t,j,'get');
 EXCEPTION WHEN insufficient_privilege THEN rejected:=true; END;
 IF NOT rejected THEN RAISE EXCEPTION 'unauthorized job read'; END IF;
END $$;
SELECT 'PASS: actual MYR debit/job atomicity, stable replay, prompt binding, claim-once, unknown hold, refund-once, overspend rollback, evidence-bound failure, ledger reconciliation, budget exhaustion, RM5/5 ceilings, worker grant restrictions, role denial' AS evidence;
ROLLBACK;
