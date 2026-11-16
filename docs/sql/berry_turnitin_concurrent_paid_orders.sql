-- Turnitin checkout: do not block a fresh paid service because a previously
-- approved report is waiting for upload, being processed, or being delivered.
-- Keep the single-unpaid-order rule because receipt uploads share one active
-- Telegram pending_receipt slot. Preserve all orders, jobs, and inventory.
CREATE OR REPLACE FUNCTION public.berry_turnitin_checkout(
 p_tenant uuid,p_user bigint,p_plan text,p_key uuid,p_order_id text,p_username text DEFAULT ''
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE plan berry_private.turnitin_plans%ROWTYPE;
 job berry_private.turnitin_jobs%ROWTYPE;
 ord public.orders%ROWTYPE;
BEGIN
 IF current_user NOT IN ('service_role','postgres') THEN RAISE EXCEPTION 'server only' USING ERRCODE='42501'; END IF;
 IF p_tenant IS NULL OR p_user IS NULL OR p_user<=0 OR p_key IS NULL
    OR p_plan IS NULL OR p_plan NOT IN (
        'similarity','ai','gptzero_basic','gptzero_standard','gptzero_premium',
        'bundle_basic','bundle_standard','bundle_premium','bundle_turnitin_ai')
    OR p_order_id !~ '^TT[0-9A-F]{24}$' OR length(coalesce(p_username,''))>150
 THEN RAISE EXCEPTION 'invalid checkout'; END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(
   'berry-turnitin-user:'||p_tenant::text||':'||p_user::text,0));
 SELECT * INTO job FROM berry_private.turnitin_jobs WHERE tenant_id=p_tenant AND request_key=p_key;
 IF FOUND THEN
   IF job.user_id<>p_user OR job.plan_code<>p_plan THEN RAISE EXCEPTION 'replay conflict'; END IF;
   SELECT * INTO ord FROM public.orders WHERE id=job.order_id AND tenant_id=p_tenant;
   IF NOT FOUND THEN RAISE EXCEPTION 'orphan order'; END IF;
   RETURN jsonb_build_object('created',false,'order_id',ord.id,'amount',ord.amount,
                             'state',job.state,'plan',job.plan_code);
 END IF;
 -- Leave receipts unambiguous: only one unpaid order can be open per user.
 SELECT * INTO ord FROM public.orders WHERE tenant_id=p_tenant AND user_id=p_user
   AND status IN ('pending','waiting','waiting_approval') ORDER BY created_at,id LIMIT 1;
 IF FOUND THEN RAISE EXCEPTION 'existing unpaid order must be resolved first'; END IF;
 -- A paid order may remain processing for hours while the owner prepares a
 -- report. It must not stop the customer from buying another check.
 SELECT * INTO plan FROM berry_private.turnitin_plans
   WHERE tenant_id=p_tenant AND code=p_plan FOR UPDATE;
 IF NOT FOUND OR NOT plan.enabled OR plan.price_myr<=0 OR plan.stock<1 THEN
   RAISE EXCEPTION 'turnitin plan unavailable'; END IF;
 IF EXISTS (
   SELECT 1 FROM berry_private.turnitin_plan_components link
   LEFT JOIN berry_private.turnitin_plans c
     ON c.tenant_id=link.tenant_id AND c.code=link.component_code
   WHERE link.tenant_id=p_tenant AND link.bundle_code=p_plan
     AND (c.code IS NULL OR NOT c.enabled OR c.stock<link.quantity)
 ) THEN RAISE EXCEPTION 'bundle component out of stock'; END IF;
 INSERT INTO public.orders(id,tenant_id,user_id,username,product_id,product_name,quantity,amount,status)
 VALUES(p_order_id,p_tenant,p_user,coalesce(p_username,''),NULL,plan.title,1,plan.price_myr,'pending')
 RETURNING * INTO ord;
 INSERT INTO berry_private.turnitin_jobs(tenant_id,order_id,request_key,user_id,plan_code)
 VALUES(p_tenant,ord.id,p_key,p_user,p_plan);
 RETURN jsonb_build_object('created',true,'order_id',ord.id,'amount',ord.amount,
                            'state','pending_payment','plan',p_plan);
END $$;
