-- Optional production activation patch, NOT applied by git push or Render deploy.
-- Run once AFTER berry_turnitin_manual_services.sql and berry_channel_announcements.sql
-- on the correct, owner-verified tenant database. No existing orders are modified.
-- Announcements remain disabled unless BERRY_CHANNEL_ANNOUNCEMENTS_ENABLED=true.
BEGIN;

-- Prevent installing this patch into an unrelated or unprepared database.
DO $$ BEGIN
  IF pg_catalog.to_regclass('berry_private.channel_announcement_claims') IS NULL
     OR pg_catalog.to_regclass('berry_private.turnitin_jobs') IS NULL THEN
    RAISE EXCEPTION 'Turnitin + announcement tables must exist first';
  END IF;
END $$;

ALTER TABLE berry_private.channel_announcement_claims
  DROP CONSTRAINT IF EXISTS channel_announcement_claims_event_type_check;
ALTER TABLE berry_private.channel_announcement_claims
  ADD CONSTRAINT channel_announcement_claims_event_type_check
  CHECK (event_type IN ('shop','topup','video','turnitin'));

CREATE OR REPLACE FUNCTION public.berry_channel_announcement_claim(
  p_tenant uuid, p_kind text, p_event_id text, p_channel_id bigint
) RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE
  v_allowed boolean := false;
  v_claimed boolean := false;
BEGIN
  IF current_user NOT IN ('service_role','postgres') THEN
    RAISE EXCEPTION 'service role required' USING ERRCODE='42501';
  END IF;
  IF p_tenant IS NULL OR p_kind NOT IN ('shop','topup','video','turnitin')
     OR p_event_id IS NULL OR length(p_event_id) NOT BETWEEN 1 AND 128
     OR p_channel_id IS NULL OR p_channel_id >= 0 THEN
    RAISE EXCEPTION 'invalid announcement claim';
  END IF;
  IF p_kind='shop' THEN
    SELECT EXISTS(
      SELECT 1 FROM public.orders o WHERE o.tenant_id=p_tenant
        AND o.id=p_event_id AND o.status='completed'
        AND o.id !~ '^BT[0-9A-F]{24}$'
        AND o.id !~ '^TT[0-9A-F]{24}$'
    ) INTO v_allowed;
  ELSIF p_kind='topup' THEN
    SELECT EXISTS(
      SELECT 1 FROM public.orders o
      JOIN public.ai_wallet_transactions t
        ON t.tenant_id=o.tenant_id AND t.user_id=o.user_id
       AND t.idempotency_key='berry-topup:'||o.id
       AND t.kind='topup' AND t.amount=o.amount AND t.reference=o.id
      WHERE o.tenant_id=p_tenant AND o.id=p_event_id
        AND o.id ~ '^BT[0-9A-F]{24}$' AND o.status='completed'
    ) INTO v_allowed;
  ELSIF p_kind='turnitin' THEN
    -- Payment approval alone is NOT delivery. Both states must be committed.
    SELECT EXISTS(
      SELECT 1 FROM berry_private.turnitin_jobs j
      JOIN public.orders o ON o.tenant_id=j.tenant_id AND o.id=j.order_id
      WHERE j.tenant_id=p_tenant AND j.order_id=p_event_id
        AND j.order_id ~ '^TT[0-9A-F]{24}$'
        AND j.state='delivered' AND j.report_file_id IS NOT NULL
        AND j.delivered_at IS NOT NULL AND o.status='completed'
    ) INTO v_allowed;
  ELSE
    IF pg_catalog.to_regclass('berry_private.ai_video_jobs') IS NOT NULL THEN
      EXECUTE
        'SELECT EXISTS (SELECT 1 FROM berry_private.ai_video_jobs
           WHERE tenant_id=$1 AND job_id::text=$2 AND state=''delivered'')'
      INTO v_allowed USING p_tenant,p_event_id;
    END IF;
  END IF;
  IF NOT v_allowed THEN
    RAISE EXCEPTION 'completed source event not confirmed';
  END IF;
  INSERT INTO berry_private.channel_announcement_claims(
    tenant_id,event_type,event_id,channel_id
  ) VALUES(p_tenant,p_kind,p_event_id,p_channel_id)
  ON CONFLICT DO NOTHING
  RETURNING true INTO v_claimed;
  RETURN COALESCE(v_claimed,false);
END $$;

-- Supply safe order metadata for the group announcement after the report is
-- claimed; the Python sender masks username before any public message.
CREATE OR REPLACE FUNCTION public.berry_turnitin_delivery_claim(
  p_tenant uuid,p_order_id text,p_admin bigint
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE j berry_private.turnitin_jobs%ROWTYPE; o public.orders%ROWTYPE; v_total bigint;
BEGIN
 IF current_user NOT IN ('service_role','postgres') THEN
   RAISE EXCEPTION 'server only' USING ERRCODE='42501';
 END IF;
 IF p_admin IS NULL OR p_admin<=0 THEN RAISE EXCEPTION 'admin id missing'; END IF;
 SELECT * INTO j FROM berry_private.turnitin_jobs
 WHERE tenant_id=p_tenant AND order_id=p_order_id FOR UPDATE;
 IF NOT FOUND OR j.state<>'processing' OR j.assignment_file_id IS NULL THEN
   RAISE EXCEPTION 'report delivery not allowed';
 END IF;
 SELECT * INTO o FROM public.orders
 WHERE tenant_id=p_tenant AND id=p_order_id AND status='completed';
 IF NOT FOUND THEN RAISE EXCEPTION 'payment must be confirmed'; END IF;
 SELECT coalesce(sum(quantity),0) INTO v_total FROM public.orders
 WHERE tenant_id=p_tenant AND status='completed';
 UPDATE berry_private.turnitin_jobs SET state='delivering',updated_at=now()
 WHERE order_id=p_order_id AND tenant_id=p_tenant;
 RETURN jsonb_build_object('order_id',p_order_id,'user_id',j.user_id,
   'plan',j.plan_code,'progress_message_id',j.progress_message_id,
   'username',o.username,'product_name',o.product_name,
   'quantity',o.quantity,'total_sold',v_total);
END $$;

REVOKE ALL ON FUNCTION public.berry_channel_announcement_claim(uuid,text,text,bigint)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.berry_channel_announcement_claim(uuid,text,text,bigint)
  TO service_role;
REVOKE ALL ON FUNCTION public.berry_turnitin_delivery_claim(uuid,text,bigint)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.berry_turnitin_delivery_claim(uuid,text,bigint)
  TO service_role;
COMMIT;
