-- STAGING REVIEW FIRST. Requires tenants/orders and wallet schema.
-- Refuse to build if duplicate active data already exists; never delete it.
-- Protect legacy shop inserts as well as this RPC.
CREATE UNIQUE INDEX IF NOT EXISTS berry_orders_one_active_user
 ON public.orders(tenant_id,user_id) WHERE status IN ('pending','waiting','waiting_approval');
CREATE TABLE IF NOT EXISTS berry_private.topup_checkout_requests (
 tenant_id uuid NOT NULL, idempotency_key uuid NOT NULL, user_id bigint NOT NULL,
 plan text NOT NULL, order_id text NOT NULL REFERENCES public.orders(id),
 created_at timestamptz NOT NULL DEFAULT now(), PRIMARY KEY(tenant_id,idempotency_key)
);
ALTER TABLE berry_private.topup_checkout_requests ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON berry_private.topup_checkout_requests FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT ON berry_private.topup_checkout_requests TO service_role;

CREATE OR REPLACE FUNCTION public.berry_create_topup_order(
 p_tenant uuid,p_user bigint,p_plan text,p_key uuid,p_proposed_id text,p_username text DEFAULT ''
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE r record; o public.orders%ROWTYPE; expected numeric(12,2);
BEGIN
 IF current_user NOT IN ('service_role','postgres') THEN
  RAISE EXCEPTION 'server role required' USING ERRCODE='42501'; END IF;
 IF p_tenant IS NULL OR p_user IS NULL OR p_user<=0 OR p_plan IS NULL OR p_key IS NULL
   OR p_proposed_id IS NULL OR p_proposed_id !~ '^BT[0-9A-F]{24}$'
   OR char_length(coalesce(p_username,''))>200 THEN RAISE EXCEPTION 'invalid checkout'; END IF;
 CASE p_plan WHEN 'starter' THEN expected:=5; WHEN 'creator' THEN expected:=10;
  WHEN 'pro' THEN expected:=20; WHEN 'studio' THEN expected:=50;
  ELSE RAISE EXCEPTION 'invalid plan'; END CASE;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(
  'berry-topup-key:'||p_tenant::text||':'||p_key::text,0));
 SELECT * INTO r FROM berry_private.topup_checkout_requests WHERE tenant_id=p_tenant AND idempotency_key=p_key;
 IF FOUND THEN
  IF r.user_id<>p_user OR r.plan<>p_plan THEN RAISE EXCEPTION 'checkout idempotency conflict'; END IF;
  SELECT * INTO o FROM public.orders WHERE tenant_id=p_tenant AND id=r.order_id;
  IF NOT FOUND THEN RAISE EXCEPTION 'checkout order missing'; END IF;
  RETURN jsonb_build_object('order',to_jsonb(o),'created',false,'replayed',true);
 END IF;
 -- Concurrent callbacks, including different callback IDs, share this user lock.
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(
  'berry-topup-user:'||p_tenant::text||':'||p_user::text,0));
 SELECT * INTO o FROM public.orders WHERE tenant_id=p_tenant AND user_id=p_user
   AND status IN ('pending','waiting','waiting_approval') ORDER BY created_at,id LIMIT 1 FOR UPDATE;
 IF FOUND THEN
  INSERT INTO berry_private.topup_checkout_requests(tenant_id,idempotency_key,user_id,plan,order_id)
   VALUES(p_tenant,p_key,p_user,p_plan,o.id);
  RETURN jsonb_build_object('order',to_jsonb(o),'created',false,'replayed',false);
 END IF;
 INSERT INTO public.orders(id,tenant_id,user_id,username,product_id,product_name,quantity,amount,status)
  VALUES(p_proposed_id,p_tenant,p_user,coalesce(p_username,''),NULL,'Berry Credits Top Up: '||p_plan,1,expected,'pending')
  RETURNING * INTO o;
 INSERT INTO berry_private.topup_checkout_requests(tenant_id,idempotency_key,user_id,plan,order_id)
  VALUES(p_tenant,p_key,p_user,p_plan,o.id);
 RETURN jsonb_build_object('order',to_jsonb(o),'created',true,'replayed',false);
END $$;
REVOKE ALL ON FUNCTION public.berry_create_topup_order(uuid,bigint,text,uuid,text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.berry_create_topup_order(uuid,bigint,text,uuid,text,text) TO service_role;
