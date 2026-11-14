-- Private, append-only-ish per-channel announcement ledger.
-- A claim is recorded BEFORE an external Telegram send to guarantee
-- at-most-once send attempts per (tenant, event, channel) even on retries.
-- If Telegram delivery outcome is uncertain, reconcile MANUALLY; no blind retry.
-- No historical orders / wallet balances are changed by this migration.
CREATE TABLE IF NOT EXISTS berry_private.channel_announcement_claims (
  tenant_id uuid NOT NULL REFERENCES public.tenants(id),
  event_type text NOT NULL CHECK (event_type IN ('shop','topup','video')),
  event_id text NOT NULL CHECK (length(event_id) BETWEEN 1 AND 128),
  channel_id bigint NOT NULL CHECK (channel_id < 0),
  state text NOT NULL DEFAULT 'claimed' CHECK (state IN ('claimed','sent')),
  claimed_at timestamptz NOT NULL DEFAULT now(),
  sent_at timestamptz,
  message_id bigint,
  PRIMARY KEY(tenant_id,event_type,event_id,channel_id)
);
ALTER TABLE berry_private.channel_announcement_claims ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON berry_private.channel_announcement_claims FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON berry_private.channel_announcement_claims TO service_role;

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
  IF p_tenant IS NULL OR p_kind NOT IN ('shop','topup','video')
     OR p_event_id IS NULL OR length(p_event_id) NOT BETWEEN 1 AND 128
     OR p_channel_id IS NULL OR p_channel_id >= 0 THEN
    RAISE EXCEPTION 'invalid announcement claim';
  END IF;
  IF p_kind='shop' THEN
    SELECT EXISTS(
      SELECT 1 FROM public.orders o WHERE o.tenant_id=p_tenant
        AND o.id=p_event_id AND o.status='completed'
        AND o.id !~ '^BT[0-9A-F]{24}$'
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
  ELSE
    -- Video jobs are not live in production yet. Fail closed unless the
    -- reviewed durable worker table exists and state is exactly delivered.
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
REVOKE ALL ON FUNCTION public.berry_channel_announcement_claim(uuid,text,text,bigint)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.berry_channel_announcement_claim(uuid,text,text,bigint)
  TO service_role;

CREATE OR REPLACE FUNCTION public.berry_channel_announcement_mark_sent(
  p_tenant uuid,p_kind text,p_event_id text,p_channel_id bigint,p_message_id bigint
) RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE v_updated boolean := false;
BEGIN
  IF current_user NOT IN ('service_role','postgres') THEN
    RAISE EXCEPTION 'service role required' USING ERRCODE='42501';
  END IF;
  IF p_message_id IS NULL OR p_message_id <= 0 THEN
    RAISE EXCEPTION 'invalid message id';
  END IF;
  UPDATE berry_private.channel_announcement_claims
     SET state='sent',sent_at=now(),message_id=p_message_id
   WHERE tenant_id=p_tenant AND event_type=p_kind AND event_id=p_event_id
     AND channel_id=p_channel_id AND state='claimed';
  GET DIAGNOSTICS v_updated = ROW_COUNT;
  RETURN v_updated;
END $$;
REVOKE ALL ON FUNCTION public.berry_channel_announcement_mark_sent(uuid,text,text,bigint,bigint)
  FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.berry_channel_announcement_mark_sent(uuid,text,text,bigint,bigint)
  TO service_role;
