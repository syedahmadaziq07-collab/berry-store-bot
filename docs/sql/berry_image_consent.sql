-- STEP 3 — AI Image durable consent tickets (gap I04).
-- Mirrors the verified video consent pattern from berry_video_myr_lifecycle.sql.
-- CANDIDATE ONLY: NOT applied to any live database. Execution requires the
-- same isolated-staging review and explicit owner approval as the video SQL.

BEGIN;

CREATE TABLE berry_private.ai_image_tickets (
 tenant_id uuid NOT NULL REFERENCES public.tenants(id), ticket_id uuid NOT NULL,
 user_id bigint NOT NULL CHECK(user_id>0), payload jsonb NOT NULL,
 state text NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','confirmed','cancelled')),
 expires_at timestamptz NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(tenant_id,ticket_id)
);
ALTER TABLE berry_private.ai_image_tickets ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON berry_private.ai_image_tickets FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON berry_private.ai_image_tickets TO service_role;

CREATE FUNCTION public.berry_image_checkout(p_tenant uuid,p_user bigint,p_ticket uuid,p_action text,p_payload jsonb DEFAULT '{}'::jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE t berry_private.ai_image_tickets%ROWTYPE; e timestamptz;
BEGIN
 IF current_user NOT IN ('service_role','postgres') OR
 coalesce(current_setting('request.jwt.claims',true),'{}')::jsonb->>'role' IS DISTINCT FROM 'service_role' THEN
  RAISE EXCEPTION 'server role required' USING ERRCODE='42501'; END IF;
 IF p_tenant IS NULL OR p_user IS NULL OR p_user<=0 OR p_ticket IS NULL
 OR p_action IS NULL OR p_action NOT IN ('prepare','get','confirm','cancel') THEN RAISE EXCEPTION 'invalid checkout'; END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended('berry-image-ticket:'||p_tenant::text||':'||p_ticket::text,0));
 SELECT * INTO t FROM berry_private.ai_image_tickets WHERE tenant_id=p_tenant AND ticket_id=p_ticket FOR UPDATE;
 IF t.ticket_id IS NOT NULL AND t.user_id<>p_user THEN RAISE EXCEPTION 'ticket owner mismatch'; END IF;
 IF p_action='prepare' THEN
  IF p_payload->>'user_id' IS DISTINCT FROM p_user::text
   OR jsonb_typeof(p_payload->'arguments') IS DISTINCT FROM 'object'
   OR jsonb_typeof(p_payload->'quote') IS DISTINCT FROM 'object' OR p_payload->>'request_hash' IS NULL
   OR p_payload->>'request_hash' !~ '^[0-9a-f]{64}$'
   OR p_payload->'quote'->>'tool_key' IS DISTINCT FROM 'image' THEN RAISE EXCEPTION 'invalid ticket payload'; END IF;
  IF t.ticket_id IS NOT NULL THEN
   IF t.payload-'expires_at' <> p_payload-'expires_at' THEN RAISE EXCEPTION 'ticket replay conflict'; END IF;
  ELSE
   e:=(p_payload->>'expires_at')::timestamptz;
   IF e IS NULL OR e<=now() OR e>now()+interval '15 minutes' THEN RAISE EXCEPTION 'invalid quote expiry'; END IF;
   INSERT INTO berry_private.ai_image_tickets(tenant_id,ticket_id,user_id,payload,expires_at)
    VALUES(p_tenant,p_ticket,p_user,p_payload,e) RETURNING * INTO t;
  END IF;
 ELSIF t.ticket_id IS NULL THEN RAISE EXCEPTION 'unknown ticket';
 ELSIF p_action='confirm' THEN
  IF t.state='cancelled' THEN RAISE EXCEPTION 'ticket cancelled'; END IF;
  IF t.state='pending' THEN
   IF t.expires_at<=now() THEN RAISE EXCEPTION 'quote expired'; END IF;
   -- Job reservation is delegated to the existing verified image-capable
   -- job lifecycle (staging_job_worker / berry_staging_job). Wiring the
   -- exact job RPC requires the STEP 3 runtime gate; until then confirm is
   -- rejected fail-closed rather than silently skipping the debit.
   RAISE EXCEPTION 'image job reservation not yet enabled';
  END IF;
 ELSIF p_action='cancel' THEN
  UPDATE berry_private.ai_image_tickets SET state='cancelled' WHERE tenant_id=p_tenant AND ticket_id=p_ticket;
  t.state:='cancelled';
 END IF;
 RETURN jsonb_build_object('ticket_id',t.ticket_id,'user_id',t.user_id,'state',t.state,'payload',t.payload,'job',NULL);
END $$;
REVOKE ALL ON FUNCTION public.berry_image_checkout(uuid,bigint,uuid,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.berry_image_checkout(uuid,bigint,uuid,text,jsonb) TO service_role;

COMMIT;
