-- Isolated staging only. Random tenant and dummy MYR ledger; rollback ALL fixtures.
BEGIN;
SELECT set_config('request.jwt.claims','{"role":"service_role"}',true);
DO $$
DECLARE t uuid:=gen_random_uuid(); j uuid:=gen_random_uuid(); b uuid:=gen_random_uuid(); c uuid:=gen_random_uuid();
 p jsonb; r jsonb; e jsonb; original jsonb; rejected boolean; n bigint; bal numeric;
BEGIN
 INSERT INTO public.tenants(id) VALUES(t);
 INSERT INTO berry_private.ai_video_test_budgets(tenant_id,budget_id,test_user_id,max_cost_cents,max_generations,expires_at)
 VALUES(t,b,900000088,500,5,now()+interval '1 hour');
 PERFORM public.ai_wallet_apply_transaction(t,900000088,5,'topup','reconcile:fund','fixture');
 p:=jsonb_build_object('user_id',900000088,'request_hash',repeat('a',64),'arguments','{"prompt":"fixture"}'::jsonb,
 'quote',jsonb_build_object('tool_key','video','provider_model_id','fal-ai/wan/v2.2-a14b/text-to-video',
 'mapping_revision',4,'credits',2500,'debit_cents',200,'all_in_cost_cents',100,'cost_reference','fixture not real price'));
 PERFORM public.berry_video_job(t,j,'reserve',p);
 r:=public.berry_video_job(t,j,'claim_submit',jsonb_build_object('budget_id',b));
 IF r->'submission_tags' IS DISTINCT FROM jsonb_build_object('berry_job',j::text,'berry_hash',repeat('a',64),'berry_tenant',t::text) THEN RAISE EXCEPTION 'missing frozen correlation'; END IF;
 PERFORM public.berry_video_job(t,j,'submission_unknown');
 e:=jsonb_build_object('operator_ref','operator:fixture','evidence_ref','operator-hold:fixture','evidence_sha256',repeat('b',64),
 'request_hash',repeat('a',64),'reason_code','unverified','observed_at',now(),'expected_state','submission_unknown');
 EXECUTE 'SET LOCAL ROLE service_role';
 original:=public.berry_video_reconcile(t,j,c,'hold',e);
 r:=public.berry_video_reconcile(t,j,c,'hold',e);
 IF r<>original THEN RAISE EXCEPTION 'unstable case replay'; END IF;
 rejected:=false;
 BEGIN PERFORM public.berry_video_reconcile(t,j,c,'hold',e||'{"reason_code":"changed"}');
 EXCEPTION WHEN raise_exception THEN rejected:=true; END;
 IF NOT rejected THEN RAISE EXCEPTION 'case replay conflict accepted'; END IF;
 FOREACH r IN ARRAY ARRAY[e||jsonb_build_object('observed_at',now()-interval '1 hour'),e||'{"request_hash":"wrong"}',e||'{"expected_state":"reserved"}',e||'{"secret":"forbidden"}'] LOOP
  rejected:=false;
  BEGIN PERFORM public.berry_video_reconcile(t,j,gen_random_uuid(),'hold',r);
  EXCEPTION WHEN raise_exception THEN rejected:=true; END;
  IF NOT rejected THEN RAISE EXCEPTION 'invalid evidence accepted'; END IF;
 END LOOP;
 rejected:=false;
 BEGIN PERFORM public.berry_video_reconcile(t,j,gen_random_uuid(),'refund',e);
 EXCEPTION WHEN raise_exception THEN rejected:=true; END;
 IF NOT rejected THEN RAISE EXCEPTION 'reconcile refunded unknown'; END IF;
 rejected:=false;
 BEGIN PERFORM public.berry_video_job(t,j,'refund_before_submit');
 EXCEPTION WHEN raise_exception THEN rejected:=true; END;
 IF NOT rejected THEN RAISE EXCEPTION 'unknown refund allowed'; END IF;
 r:=public.berry_video_job(t,j,'claim_submit',jsonb_build_object('budget_id',b));
 IF r->>'claimed'<>'false' THEN RAISE EXCEPTION 'unknown resubmitted'; END IF;
 e:=e||jsonb_build_object('evidence_ref','fal-account-export:fixture','provider_model_id','fal-ai/wan/v2.2-a14b/text-to-video',
 'provider_request_id','fixture-'||j::text,'correlation_tags',r->'submission_tags');
 rejected:=false;
 BEGIN PERFORM public.berry_video_reconcile(t,j,gen_random_uuid(),'bind_request',e||'{"correlation_tags":{}}');
 EXCEPTION WHEN raise_exception THEN rejected:=true; END;
 IF NOT rejected THEN RAISE EXCEPTION 'unrelated receipt accepted'; END IF;
 c:=gen_random_uuid(); original:=public.berry_video_reconcile(t,j,c,'bind_request',e);
 r:=public.berry_video_reconcile(t,j,c,'bind_request',e);
 IF r<>original OR r->>'state'<>'queued' THEN RAISE EXCEPTION 'bind replay failed'; END IF;
 PERFORM public.berry_video_job(t,j,'succeed',jsonb_build_object('provider_request_id','fixture-'||j::text,'result_url','https://fal.media/fixture.mp4'));
 PERFORM public.berry_video_job(t,j,'claim_delivery');
 PERFORM public.berry_video_job(t,j,'delivery_unknown');
 e:=jsonb_build_object('operator_ref','operator:fixture','evidence_ref','telegram-receipt:fixture','evidence_sha256',repeat('b',64),
 'request_hash',repeat('a',64),'reason_code','confirmed_delivery','observed_at',now(),'expected_state','delivery_unknown',
 'recipient_id',900000088,'delivery_id','123','result_sha256',encode(sha256(convert_to('https://fal.media/fixture.mp4','UTF8')),'hex'));
 rejected:=false;
 BEGIN PERFORM public.berry_video_reconcile(t,j,gen_random_uuid(),'confirm_delivery',e||'{"recipient_id":900000089}');
 EXCEPTION WHEN raise_exception THEN rejected:=true; END;
 IF NOT rejected THEN RAISE EXCEPTION 'wrong recipient accepted'; END IF;
 c:=gen_random_uuid(); original:=public.berry_video_reconcile(t,j,c,'confirm_delivery',e);
 r:=public.berry_video_reconcile(t,j,c,'confirm_delivery',e);
 IF r<>original OR r->>'state'<>'delivered' THEN RAISE EXCEPTION 'delivery replay failed'; END IF;
 rejected:=false;
 BEGIN DELETE FROM berry_private.ai_video_reconciliation_cases WHERE tenant_id=t;
 EXCEPTION WHEN insufficient_privilege THEN rejected:=true; END;
 IF NOT rejected THEN RAISE EXCEPTION 'worker can delete evidence'; END IF;
 EXECUTE 'RESET ROLE';
 SELECT balance INTO bal FROM public.ai_wallets WHERE tenant_id=t AND user_id=900000088;
 SELECT count(*) INTO n FROM public.ai_wallet_transactions WHERE tenant_id=t;
 IF bal<>3 OR n<>2 THEN RAISE EXCEPTION 'reconciliation changed money'; END IF;
 IF (SELECT reserved_generations FROM berry_private.ai_video_test_budgets WHERE tenant_id=t)<>1 THEN RAISE EXCEPTION 'budget replay'; END IF;
 IF (SELECT count(*) FROM berry_private.ai_video_reconciliation_cases WHERE tenant_id=t)<>3 THEN RAISE EXCEPTION 'case audit mismatch'; END IF;
 IF has_function_privilege('anon','public.berry_video_reconcile(uuid,uuid,uuid,text,jsonb)','EXECUTE')
 OR has_function_privilege('authenticated','public.berry_video_reconcile(uuid,uuid,uuid,text,jsonb)','EXECUTE') THEN RAISE EXCEPTION 'public reconciliation access'; END IF;
END $$;
SELECT 'PASS: correlation persisted, hold/bind/delivery replay, conflicting/stale/unrelated evidence rejected, no resubmit/refund/money mutation, immutable worker evidence, private ACL' AS evidence;
ROLLBACK;
