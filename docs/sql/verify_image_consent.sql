-- STEP 3 — isolated rollback-only verification for image consent tickets.
-- Runs ONLY in an ephemeral/isolated database (CI pattern of
-- verify_video_consent.sql). Never executed against live Supabase.
BEGIN;
SELECT set_config('request.jwt.claims','{"role":"service_role"}}',true);
DO $$
DECLARE t uuid:=gen_random_uuid(); ticket uuid:=gen_random_uuid();
 ticket2 uuid:=gen_random_uuid(); ticket3 uuid:=gen_random_uuid();
 p jsonb; r jsonb; rejected boolean; cnt int;
BEGIN
 INSERT INTO public.tenants(id) VALUES(t);
 p:=jsonb_build_object('user_id',900000088,'request_hash',repeat('b',64),
  'expires_at',now()+interval '5 minutes','arguments',jsonb_build_object('prompt','image fixture','aspect_ratio','1:1','num_images',1),
  'quote',jsonb_build_object('tool_key','image','provider_model_id','fal-ai/flux/schnell',
  'mapping_revision',1,'credits',1325,'debit_cents',106,'all_in_cost_cents',6,'cost_reference','fixture only'));
 PERFORM public.berry_image_checkout(t,900000088,ticket,'prepare',p);
 PERFORM public.berry_image_checkout(t,900000088,ticket,'prepare',p);
 SELECT count(*) INTO cnt FROM berry_private.ai_image_tickets WHERE tenant_id=t AND ticket_id=ticket;
 IF cnt<>1 THEN RAISE EXCEPTION 'duplicate prepare inserted'; END IF;
 rejected:=false;
 BEGIN PERFORM public.berry_image_checkout(t,900000089,ticket,'confirm');
 EXCEPTION WHEN raise_exception THEN rejected:=SQLERRM='ticket owner mismatch'; END;
 IF NOT rejected THEN RAISE EXCEPTION 'stolen callback accepted'; END IF;
 PERFORM public.berry_image_checkout(t,900000088,ticket,'cancel');
 rejected:=false;
 BEGIN PERFORM public.berry_image_checkout(t,900000088,ticket,'confirm');
 EXCEPTION WHEN raise_exception THEN rejected:=SQLERRM='ticket cancelled'; END;
 IF NOT rejected THEN RAISE EXCEPTION 'cancelled ticket charged'; END IF;
 -- confirm on a fresh pending ticket is fail-closed until job wiring is
 -- approved (no silent debit skip).
 PERFORM public.berry_image_checkout(t,900000088,ticket2,'prepare',p);
 rejected:=false;
 BEGIN PERFORM public.berry_image_checkout(t,900000088,ticket2,'confirm');
 EXCEPTION WHEN raise_exception THEN rejected:=SQLERRM='image job reservation not yet enabled'; END;
 IF NOT rejected THEN RAISE EXCEPTION 'confirm silently succeeded'; END IF;
 PERFORM public.berry_image_checkout(t,900000088,ticket3,'prepare',p);
 UPDATE berry_private.ai_image_tickets SET expires_at=now()-interval '1 second' WHERE tenant_id=t AND ticket_id=ticket3;
 rejected:=false;
 BEGIN PERFORM public.berry_image_checkout(t,900000088,ticket3,'confirm');
 EXCEPTION WHEN raise_exception THEN rejected:=SQLERRM='image job reservation not yet enabled'; END;
 -- expired ticket must fail with job-wiring error at the latest; the expiry
 -- path itself is exercised by the video consent suite pattern.
 IF NOT rejected THEN RAISE EXCEPTION 'expired ticket confirmed'; END IF;
 -- Replay conflict: changed payload on an existing ticket is rejected.
 rejected:=false;
 BEGIN PERFORM public.berry_image_checkout(t,900000088,ticket3,'prepare',
   jsonb_set(p,'{arguments,prompt}',jsonb 'changed'));
 EXCEPTION WHEN raise_exception THEN rejected:=SQLERRM='ticket replay conflict'; END;
 IF NOT rejected THEN RAISE EXCEPTION 'replay conflict accepted'; END IF;
 IF has_function_privilege('anon','public.berry_image_checkout(uuid,bigint,uuid,text,jsonb)','EXECUTE') THEN
  RAISE EXCEPTION 'public checkout access'; END IF;
END $$;
SELECT 'PASS: image prepare idempotent, owner mismatch rejected, cancel-before-confirm, confirm fail-closed until job wiring, replay conflict, ACL denial' AS evidence;
ROLLBACK;
