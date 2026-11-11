-- Run ONLY on cirsdvkfkvypprnmyykk. Synthetic data; entire test rolls back.
BEGIN;
DO $$
DECLARE
 t uuid:=gen_random_uuid(); j uuid:=gen_random_uuid(); j2 uuid:=gen_random_uuid(); j3 uuid:=gen_random_uuid();
 j4 uuid:=gen_random_uuid(); j5 uuid:=gen_random_uuid();
 q jsonb:='{"tool_key":"image","provider_model_id":"fal-ai/flux/schnell","mapping_revision":4,"credits":1325,"debit_cents":106,"all_in_cost_cents":6,"cost_reference":"synthetic-only"}';
 p jsonb; r jsonb; rejected boolean; b bigint; n bigint;
BEGIN
 INSERT INTO berry_private.staging_job_wallets VALUES(t,900000003,2000);
 p:=jsonb_build_object('user_id',900000003,'quote',q,'request_hash',repeat('a',64));
 -- Atomic debit and immutable idempotency snapshot.
 PERFORM public.berry_staging_job(t,j,'reserve',p);
 PERFORM public.berry_staging_job(t,j,'reserve',p);
 SELECT balance_cents INTO b FROM berry_private.staging_job_wallets WHERE tenant_id=t;
 IF b<>1894 THEN RAISE EXCEPTION 'duplicate debit'; END IF;
 rejected:=false;
 BEGIN PERFORM public.berry_staging_job(t,j,'reserve',p||jsonb_build_object('request_hash',repeat('b',64)));
 EXCEPTION WHEN raise_exception THEN IF SQLERRM='idempotency conflict' THEN rejected:=true; ELSE RAISE; END IF; END;
 IF NOT rejected THEN RAISE EXCEPTION 'changed request accepted'; END IF;
 r:=public.berry_staging_job(t,j,'claim_submit');
 IF r->>'claimed'<>'true' THEN RAISE EXCEPTION 'first claim failed'; END IF;
 r:=public.berry_staging_job(t,j,'claim_submit');
 IF r->>'claimed'<>'false' THEN RAISE EXCEPTION 'duplicate submit claim'; END IF;
 rejected:=false;
 BEGIN PERFORM public.berry_staging_job(t,j,'queued','{"provider_request_id":"fixture-1","queue_status_url":"https://queue.fal.run/other/model/requests/fixture-1/status","queue_result_url":"https://queue.fal.run/other/model/requests/fixture-1"}');
 EXCEPTION WHEN raise_exception THEN IF SQLERRM='invalid queue recovery URLs' THEN rejected:=true; ELSE RAISE; END IF; END;
 IF NOT rejected THEN RAISE EXCEPTION 'queue URLs not bound to model'; END IF;
 PERFORM public.berry_staging_job(t,j,'queued','{"provider_request_id":"fixture-1","queue_status_url":"https://queue.fal.run/fal-ai/flux/requests/fixture-1/status","queue_result_url":"https://queue.fal.run/fal-ai/flux/requests/fixture-1"}');
 r:=public.berry_staging_job(t,j,'get');
 IF r->>'queue_status_url'<>'https://queue.fal.run/fal-ai/flux/requests/fixture-1/status' THEN RAISE EXCEPTION 'queue recovery URL not persisted'; END IF;
 rejected:=false;
 BEGIN PERFORM public.berry_staging_job(t,j,'succeed','{"provider_request_id":"wrong-job","result_url":"https://fal.media/fixture.png"}');
 EXCEPTION WHEN raise_exception THEN IF SQLERRM='provider request mismatch' THEN rejected:=true; ELSE RAISE; END IF; END;
 IF NOT rejected THEN RAISE EXCEPTION 'cross-job result accepted'; END IF;
 PERFORM public.berry_staging_job(t,j,'succeed','{"provider_request_id":"fixture-1","result_url":"https://fal.media/fixture.png"}');
 r:=public.berry_staging_job(t,j,'claim_delivery');
 IF r->>'claimed'<>'true' THEN RAISE EXCEPTION 'first delivery claim failed'; END IF;
 r:=public.berry_staging_job(t,j,'claim_delivery');
 IF r->>'claimed'<>'false' THEN RAISE EXCEPTION 'duplicate delivery claim'; END IF;
 PERFORM public.berry_staging_job(t,j,'delivered','{"delivery_id":"123"}');
 PERFORM public.berry_staging_job(t,j,'delivered','{"delivery_id":"123"}');
 rejected:=false;
 BEGIN PERFORM public.berry_staging_job(t,j,'provider_failed','{"provider_request_id":"fixture-1","queue_status_url":"https://queue.fal.run/fal-ai/flux/requests/fixture-1/status","queue_result_url":"https://queue.fal.run/fal-ai/flux/requests/fixture-1"}');
 EXCEPTION WHEN raise_exception THEN IF SQLERRM='refund forbidden for ambiguous or completed job' THEN rejected:=true; ELSE RAISE; END IF; END;
 IF NOT rejected THEN RAISE EXCEPTION 'delivered job refunded'; END IF;
 -- Definitive failure refunds exactly once.
 PERFORM public.berry_staging_job(t,j2,'reserve',p);
 PERFORM public.berry_staging_job(t,j2,'claim_submit');
 PERFORM public.berry_staging_job(t,j2,'queued','{"provider_request_id":"fixture-2","queue_status_url":"https://queue.fal.run/fal-ai/flux/requests/fixture-2/status","queue_result_url":"https://queue.fal.run/fal-ai/flux/requests/fixture-2"}');
 PERFORM public.berry_staging_job(t,j2,'provider_failed','{"provider_request_id":"fixture-2","queue_status_url":"https://queue.fal.run/fal-ai/flux/requests/fixture-2/status","queue_result_url":"https://queue.fal.run/fal-ai/flux/requests/fixture-2"}');
 PERFORM public.berry_staging_job(t,j2,'provider_failed','{"provider_request_id":"fixture-2","queue_status_url":"https://queue.fal.run/fal-ai/flux/requests/fixture-2/status","queue_result_url":"https://queue.fal.run/fal-ai/flux/requests/fixture-2"}');
 -- Cancellation only before submission.
 PERFORM public.berry_staging_job(t,j3,'reserve',p);
 PERFORM public.berry_staging_job(t,j3,'refund_before_submit');
 PERFORM public.berry_staging_job(t,j3,'refund_before_submit');
 -- Unknown provider submission cannot be resubmitted or refunded.
 PERFORM public.berry_staging_job(t,j4,'reserve',p);
 PERFORM public.berry_staging_job(t,j4,'claim_submit');
 PERFORM public.berry_staging_job(t,j4,'submission_unknown');
 r:=public.berry_staging_job(t,j4,'claim_submit');
 IF r->>'claimed'<>'false' THEN RAISE EXCEPTION 'unknown submission retried'; END IF;
 rejected:=false;
 BEGIN PERFORM public.berry_staging_job(t,j4,'refund_before_submit');
 EXCEPTION WHEN raise_exception THEN IF SQLERRM='refund forbidden for ambiguous or completed job' THEN rejected:=true; ELSE RAISE; END IF; END;
 IF NOT rejected THEN RAISE EXCEPTION 'unknown submission refunded'; END IF;
 -- Unknown Telegram delivery cannot automatically resend.
 PERFORM public.berry_staging_job(t,j5,'reserve',p);
 PERFORM public.berry_staging_job(t,j5,'claim_submit');
 PERFORM public.berry_staging_job(t,j5,'queued','{"provider_request_id":"fixture-5","queue_status_url":"https://queue.fal.run/fal-ai/flux/requests/fixture-5/status","queue_result_url":"https://queue.fal.run/fal-ai/flux/requests/fixture-5"}');
 PERFORM public.berry_staging_job(t,j5,'succeed','{"provider_request_id":"fixture-5","result_url":"https://fal.media/fixture.png"}');
 PERFORM public.berry_staging_job(t,j5,'claim_delivery');
 PERFORM public.berry_staging_job(t,j5,'delivery_unknown');
 r:=public.berry_staging_job(t,j5,'claim_delivery');
 IF r->>'claimed'<>'false' THEN RAISE EXCEPTION 'unknown delivery retried'; END IF;
 SELECT balance_cents INTO b FROM berry_private.staging_job_wallets WHERE tenant_id=t;
 SELECT sum(amount_cents) INTO n FROM berry_private.staging_job_ledger WHERE tenant_id=t;
 IF b<>1682 OR b<>2000+n THEN RAISE EXCEPTION 'ledger does not reconcile'; END IF;
 SELECT count(*) INTO n FROM berry_private.staging_job_ledger WHERE tenant_id=t AND kind='refund';
 IF n<>2 THEN RAISE EXCEPTION 'refund count mismatch'; END IF;
 IF has_function_privilege('anon','public.berry_staging_job(uuid,uuid,text,jsonb)','EXECUTE')
 OR has_function_privilege('authenticated','public.berry_staging_job(uuid,uuid,text,jsonb)','EXECUTE') THEN
  RAISE EXCEPTION 'public execution allowed'; END IF;
END $$;
SELECT 'PASS: atomic reservation, replay, immutable quote, submit/delivery claims, provider binding, refund once, unknown outcomes, ledger reconciliation, private execution' AS evidence;
ROLLBACK;
