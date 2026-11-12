-- Isolated fixtures only. Roll back all fixture state.
BEGIN;
SELECT set_config('request.jwt.claims','{"role":"service_role"}',true);
DO $$
DECLARE t uuid:=gen_random_uuid(); ticket uuid:=gen_random_uuid(); ticket2 uuid:=gen_random_uuid();
 ticket3 uuid:=gen_random_uuid(); p jsonb; r jsonb; b numeric; rejected boolean;
BEGIN
 INSERT INTO public.tenants(id) VALUES(t);
 PERFORM public.ai_wallet_apply_transaction(t,900000088,5,'topup','consent:fund','fixture');
 p:=jsonb_build_object('user_id',900000088,'request_hash',repeat('b',64),
 'expires_at',now()+interval '5 minutes','arguments',jsonb_build_object('prompt','consent fixture'),
 'quote',jsonb_build_object('tool_key','video','provider_model_id','fal-ai/wan/v2.2-5b/text-to-video',
 'mapping_revision',1,'credits',2500,'debit_cents',200,'all_in_cost_cents',100,'cost_reference','fixture only'));
 PERFORM public.berry_video_checkout(t,900000088,ticket,'prepare',p);
 PERFORM public.berry_video_checkout(t,900000088,ticket,'prepare',p);
 SELECT balance INTO b FROM public.ai_wallets WHERE tenant_id=t AND user_id=900000088;
 IF b<>5 OR EXISTS(SELECT 1 FROM berry_private.ai_video_jobs WHERE tenant_id=t) THEN RAISE EXCEPTION 'preview debited'; END IF;
 rejected:=false;
 BEGIN PERFORM public.berry_video_checkout(t,900000089,ticket,'confirm');
 EXCEPTION WHEN raise_exception THEN rejected:=SQLERRM='ticket owner mismatch'; END;
 IF NOT rejected THEN RAISE EXCEPTION 'stolen callback accepted'; END IF;
 PERFORM public.berry_video_checkout(t,900000088,ticket,'cancel');
 rejected:=false;
 BEGIN PERFORM public.berry_video_checkout(t,900000088,ticket,'confirm');
 EXCEPTION WHEN raise_exception THEN rejected:=SQLERRM='ticket cancelled'; END;
 IF NOT rejected THEN RAISE EXCEPTION 'cancelled ticket charged'; END IF;
 PERFORM public.berry_video_checkout(t,900000088,ticket2,'prepare',p);
 PERFORM public.berry_video_checkout(t,900000088,ticket2,'confirm');
 PERFORM public.berry_video_checkout(t,900000088,ticket2,'confirm');
 SELECT balance INTO b FROM public.ai_wallets WHERE tenant_id=t AND user_id=900000088;
 IF b<>3 OR (SELECT count(*) FROM public.ai_wallet_transactions WHERE tenant_id=t AND kind='debit')<>1 THEN
  RAISE EXCEPTION 'duplicate confirm double charged'; END IF;
 PERFORM public.berry_video_checkout(t,900000088,ticket2,'cancel');
 PERFORM public.berry_video_checkout(t,900000088,ticket2,'cancel');
 SELECT balance INTO b FROM public.ai_wallets WHERE tenant_id=t AND user_id=900000088;
 IF b<>5 OR (SELECT count(*) FROM public.ai_wallet_transactions WHERE tenant_id=t AND kind='refund')<>1 THEN
  RAISE EXCEPTION 'cancel-before-submit refund mismatch'; END IF;
 PERFORM public.berry_video_checkout(t,900000088,ticket3,'prepare',p);
 UPDATE berry_private.ai_video_tickets SET expires_at=now()-interval '1 second' WHERE tenant_id=t AND ticket_id=ticket3;
 rejected:=false;
 BEGIN PERFORM public.berry_video_checkout(t,900000088,ticket3,'confirm');
 EXCEPTION WHEN raise_exception THEN rejected:=SQLERRM='quote expired'; END;
 IF NOT rejected THEN RAISE EXCEPTION 'expired quote charged'; END IF;
 IF has_function_privilege('anon','public.berry_video_checkout(uuid,bigint,uuid,text,jsonb)','EXECUTE') THEN
  RAISE EXCEPTION 'public checkout access'; END IF;
END $$;
SELECT 'PASS: preview has no debit, ticket identity, stable replay, cancel-before-confirm, confirm debit once, cancel refund once, expiry and ACL denial' AS evidence;
ROLLBACK;
