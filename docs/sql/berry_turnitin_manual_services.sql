-- Turnitin manual report fulfilment, v1; default OFF and no paid orders created.
-- This does NOT integrate with official Turnitin services or claim any scan.
-- All document IDs are private metadata, not publicly accessible.
CREATE SCHEMA IF NOT EXISTS berry_private;
CREATE TABLE IF NOT EXISTS berry_private.turnitin_plans(
 tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
 code text NOT NULL CHECK(code IN ('similarity','ai')),
 title text NOT NULL CHECK(length(title) BETWEEN 3 AND 100),
 description text NOT NULL CHECK(length(description) BETWEEN 10 AND 2000),
 price_myr numeric(10,2) NOT NULL DEFAULT 0 CHECK(price_myr>=0),
 stock integer NOT NULL DEFAULT 0 CHECK(stock>=0),
 enabled boolean NOT NULL DEFAULT false,
 turnaround_minutes integer NOT NULL DEFAULT 15 CHECK(turnaround_minutes BETWEEN 1 AND 1440),
 updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant_id,code)
);
CREATE TABLE IF NOT EXISTS berry_private.turnitin_jobs(
 tenant_id uuid NOT NULL REFERENCES public.tenants(id) ON DELETE CASCADE,
 order_id text NOT NULL PRIMARY KEY REFERENCES public.orders(id),
 request_key uuid NOT NULL,
 user_id bigint NOT NULL,
 plan_code text NOT NULL CHECK(plan_code IN ('similarity','ai')),
 state text NOT NULL DEFAULT 'pending_payment'
   CHECK(state IN ('pending_payment','waiting_approval','awaiting_upload','processing',
                   'delivering','delivered','rejected','cancelled')),
 receipt_file_id text,
 assignment_file_id text,
 assignment_name text,
 submitted_at timestamptz,
 progress_message_id bigint,
 last_display_percent integer NOT NULL DEFAULT 0 CHECK(last_display_percent BETWEEN 0 AND 100),
 report_file_id text,
 delivered_at timestamptz,
 updated_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(tenant_id,request_key),
 FOREIGN KEY(tenant_id,plan_code) REFERENCES berry_private.turnitin_plans(tenant_id,code)
);
CREATE INDEX IF NOT EXISTS berry_turnitin_jobs_active ON berry_private.turnitin_jobs(tenant_id,state,updated_at);
CREATE INDEX IF NOT EXISTS berry_turnitin_jobs_customer ON berry_private.turnitin_jobs(tenant_id,user_id,updated_at DESC);
CREATE TABLE IF NOT EXISTS berry_private.turnitin_admin_edits(
 tenant_id uuid NOT NULL,
 idempotency_key uuid NOT NULL,
 code text NOT NULL,
 payload jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant_id,idempotency_key)
);
ALTER TABLE berry_private.turnitin_plans ENABLE ROW LEVEL SECURITY;
ALTER TABLE berry_private.turnitin_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE berry_private.turnitin_admin_edits ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON berry_private.turnitin_plans,berry_private.turnitin_jobs,berry_private.turnitin_admin_edits FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON berry_private.turnitin_plans,berry_private.turnitin_jobs,berry_private.turnitin_admin_edits TO service_role;
GRANT USAGE ON SCHEMA berry_private TO service_role;
-- Seed only the named Berry Store tenant, and never assign fictitious price or stock.
INSERT INTO berry_private.turnitin_plans(tenant_id,code,title,description)
SELECT t.id,'similarity','Similarity Check','Semakan kesamaan dokumen secara manual oleh admin. Hasil bergantung pada akses perkhidmatan yang sah.'
FROM public.tenants t WHERE lower(trim(both '@' from coalesce(to_jsonb(t)->>'bot_username','')))='berryshopps_bot'
ON CONFLICT DO NOTHING;
INSERT INTO berry_private.turnitin_plans(tenant_id,code,title,description)
SELECT t.id,'ai','AI Writing Check','Semakan indikator penulisan AI secara manual oleh admin. Skor pengesan AI bukan bukti muktamad.'
FROM public.tenants t WHERE lower(trim(both '@' from coalesce(to_jsonb(t)->>'bot_username','')))='berryshopps_bot'
ON CONFLICT DO NOTHING;

CREATE OR REPLACE FUNCTION public.berry_turnitin_catalog(p_tenant uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE x jsonb;
BEGIN
 IF current_user NOT IN ('service_role','postgres') THEN
   RAISE EXCEPTION 'server only' USING ERRCODE='42501';
 END IF;
 SELECT coalesce(jsonb_agg(jsonb_build_object('code',code,'title',title,
   'description',description,'price_myr',price_myr,'stock',stock,
   'enabled',enabled,'turnaround_minutes',turnaround_minutes) ORDER BY code),'[]'::jsonb)
 INTO x FROM berry_private.turnitin_plans WHERE tenant_id=p_tenant;
 RETURN x;
END $$;

CREATE OR REPLACE FUNCTION public.berry_turnitin_checkout(
 p_tenant uuid,p_user bigint,p_plan text,p_key uuid,p_order_id text,p_username text DEFAULT ''
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE plan berry_private.turnitin_plans%ROWTYPE;
 job berry_private.turnitin_jobs%ROWTYPE;
 ord public.orders%ROWTYPE;
BEGIN
 IF current_user NOT IN ('service_role','postgres') THEN RAISE EXCEPTION 'server only' USING ERRCODE='42501'; END IF;
 IF p_tenant IS NULL OR p_user IS NULL OR p_user<=0 OR p_key IS NULL
    OR p_plan NOT IN ('similarity','ai') OR p_order_id !~ '^TT[0-9A-F]{24}$'
    OR length(coalesce(p_username,''))>150 THEN RAISE EXCEPTION 'invalid checkout'; END IF;
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
 SELECT * INTO ord FROM public.orders WHERE tenant_id=p_tenant AND user_id=p_user
   AND status IN ('pending','waiting','waiting_approval') ORDER BY created_at,id LIMIT 1;
 IF FOUND THEN RAISE EXCEPTION 'existing unpaid order must be resolved first'; END IF;
 SELECT * INTO job FROM berry_private.turnitin_jobs WHERE tenant_id=p_tenant AND user_id=p_user
   AND state IN ('awaiting_upload','processing','delivering')
   ORDER BY updated_at DESC LIMIT 1;
 IF FOUND THEN RAISE EXCEPTION 'previous report not finished'; END IF;
 SELECT * INTO plan FROM berry_private.turnitin_plans
   WHERE tenant_id=p_tenant AND code=p_plan FOR UPDATE;
 IF NOT FOUND OR NOT plan.enabled OR plan.price_myr<=0 OR plan.stock<1 THEN
   RAISE EXCEPTION 'turnitin plan unavailable'; END IF;
 INSERT INTO public.orders(id,tenant_id,user_id,username,product_id,product_name,quantity,amount,status)
 VALUES(p_order_id,p_tenant,p_user,coalesce(p_username,''),NULL,plan.title,1,plan.price_myr,'pending')
 RETURNING * INTO ord;
 INSERT INTO berry_private.turnitin_jobs(tenant_id,order_id,request_key,user_id,plan_code)
 VALUES(p_tenant,ord.id,p_key,p_user,p_plan);
 RETURN jsonb_build_object('created',true,'order_id',ord.id,'amount',ord.amount,
                            'state','pending_payment','plan',p_plan);
END $$;

CREATE OR REPLACE FUNCTION public.berry_turnitin_receipt(
 p_tenant uuid,p_user bigint,p_order_id text,p_file_id text
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE j berry_private.turnitin_jobs%ROWTYPE;
BEGIN
 IF current_user NOT IN ('service_role','postgres') THEN RAISE EXCEPTION 'server only' USING ERRCODE='42501'; END IF;
 IF p_file_id IS NULL OR length(p_file_id) NOT BETWEEN 5 AND 512 THEN RAISE EXCEPTION 'invalid receipt'; END IF;
 SELECT * INTO j FROM berry_private.turnitin_jobs WHERE tenant_id=p_tenant AND order_id=p_order_id FOR UPDATE;
 IF NOT FOUND OR j.user_id<>p_user OR j.state<>'pending_payment' THEN RAISE EXCEPTION 'receipt not allowed'; END IF;
 UPDATE public.orders SET status='waiting_approval',receipt_file_id=p_file_id,updated_at=now()
 WHERE id=p_order_id AND tenant_id=p_tenant AND user_id=p_user AND status='pending';
 IF NOT FOUND THEN RAISE EXCEPTION 'order is not pending'; END IF;
 UPDATE berry_private.turnitin_jobs SET state='waiting_approval',receipt_file_id=p_file_id,updated_at=now()
 WHERE order_id=p_order_id;
 RETURN jsonb_build_object('order_id',p_order_id,'state','waiting_approval');
END $$;

CREATE OR REPLACE FUNCTION public.berry_turnitin_approve(
 p_tenant uuid,p_order_id text,p_admin bigint
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE j berry_private.turnitin_jobs%ROWTYPE; price numeric;
BEGIN
 IF current_user NOT IN ('service_role','postgres') THEN RAISE EXCEPTION 'server only' USING ERRCODE='42501'; END IF;
 IF p_admin IS NULL OR p_admin<=0 THEN RAISE EXCEPTION 'admin id missing'; END IF;
 SELECT * INTO j FROM berry_private.turnitin_jobs WHERE tenant_id=p_tenant AND order_id=p_order_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'turnitin order not found'; END IF;
 IF j.state IN ('awaiting_upload','processing','delivering','delivered') THEN
   RETURN jsonb_build_object('order_id',j.order_id,'user_id',j.user_id,'plan',j.plan_code,
    'state',j.state,'already_approved',true);
 END IF;
 IF j.state<>'waiting_approval' OR j.receipt_file_id IS NULL THEN RAISE EXCEPTION 'unverified payment'; END IF;
 UPDATE berry_private.turnitin_plans SET stock=stock-1,updated_at=now()
   WHERE tenant_id=p_tenant AND code=j.plan_code AND stock>0 AND enabled=true AND price_myr>0
 RETURNING price_myr INTO price;
 IF NOT FOUND THEN RAISE EXCEPTION 'out of stock: refund or contact customer'; END IF;
 UPDATE public.orders SET status='completed',updated_at=now()
   WHERE id=p_order_id AND tenant_id=p_tenant AND status='waiting_approval';
 IF NOT FOUND THEN RAISE EXCEPTION 'order payment state invalid'; END IF;
 UPDATE berry_private.turnitin_jobs SET state='awaiting_upload',updated_at=now() WHERE order_id=p_order_id;
 RETURN jsonb_build_object('order_id',p_order_id,'user_id',j.user_id,
                           'plan',j.plan_code,'state','awaiting_upload','already_approved',false);
END $$;

CREATE OR REPLACE FUNCTION public.berry_turnitin_reject(
 p_tenant uuid,p_order_id text,p_admin bigint
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE j berry_private.turnitin_jobs%ROWTYPE;
BEGIN
 IF current_user NOT IN ('service_role','postgres') THEN RAISE EXCEPTION 'server only' USING ERRCODE='42501'; END IF;
 IF p_admin IS NULL OR p_admin<=0 THEN RAISE EXCEPTION 'admin id missing'; END IF;
 SELECT * INTO j FROM berry_private.turnitin_jobs WHERE tenant_id=p_tenant AND order_id=p_order_id FOR UPDATE;
 IF NOT FOUND OR j.state<>'waiting_approval' THEN RAISE EXCEPTION 'rejection not allowed'; END IF;
 UPDATE public.orders SET status='rejected',updated_at=now()
   WHERE id=p_order_id AND tenant_id=p_tenant AND status='waiting_approval';
 IF NOT FOUND THEN RAISE EXCEPTION 'order state invalid'; END IF;
 UPDATE berry_private.turnitin_jobs SET state='rejected',updated_at=now() WHERE order_id=p_order_id;
 RETURN jsonb_build_object('order_id',p_order_id,'user_id',j.user_id,'state','rejected');
END $$;

CREATE OR REPLACE FUNCTION public.berry_turnitin_submit(
 p_tenant uuid,p_user bigint,p_order_id text,p_file_id text,p_file_name text
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE j berry_private.turnitin_jobs%ROWTYPE; t timestamptz;
BEGIN
 IF current_user NOT IN ('service_role','postgres') THEN RAISE EXCEPTION 'server only' USING ERRCODE='42501'; END IF;
 IF p_file_id IS NULL OR length(p_file_id) NOT BETWEEN 5 AND 512 OR
    p_file_name IS NULL OR length(p_file_name) NOT BETWEEN 1 AND 180 THEN
    RAISE EXCEPTION 'invalid assignment'; END IF;
 SELECT * INTO j FROM berry_private.turnitin_jobs WHERE tenant_id=p_tenant AND order_id=p_order_id FOR UPDATE;
 IF NOT FOUND OR j.user_id<>p_user OR j.state<>'awaiting_upload' THEN
    RAISE EXCEPTION 'paid customer upload required'; END IF;
 IF NOT EXISTS(SELECT 1 FROM public.orders WHERE tenant_id=p_tenant AND id=p_order_id AND status='completed')
 THEN RAISE EXCEPTION 'payment not approved'; END IF;
 t:=now();
 UPDATE berry_private.turnitin_jobs SET state='processing',assignment_file_id=p_file_id,
   assignment_name=p_file_name,submitted_at=t,updated_at=t WHERE order_id=p_order_id;
 RETURN jsonb_build_object('order_id',p_order_id,'state','processing','submitted_at',t);
END $$;

CREATE OR REPLACE FUNCTION public.berry_turnitin_progress_attach(
 p_tenant uuid,p_order_id text,p_message_id bigint
) RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 IF current_user NOT IN ('service_role','postgres') THEN RAISE EXCEPTION 'server only' USING ERRCODE='42501'; END IF;
 IF p_message_id IS NULL OR p_message_id<=0 THEN RAISE EXCEPTION 'invalid message'; END IF;
 UPDATE berry_private.turnitin_jobs SET progress_message_id=p_message_id,updated_at=now()
 WHERE tenant_id=p_tenant AND order_id=p_order_id AND state='processing'
   AND progress_message_id IS NULL;
 RETURN FOUND;
END $$;

CREATE OR REPLACE FUNCTION public.berry_turnitin_processing(p_tenant uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE v jsonb;
BEGIN
 IF current_user NOT IN ('service_role','postgres') THEN RAISE EXCEPTION 'server only' USING ERRCODE='42501'; END IF;
 SELECT coalesce(jsonb_agg(jsonb_build_object('order_id',x.order_id,'user_id',x.user_id,
   'submitted_at',x.submitted_at,'progress_message_id',x.progress_message_id,
   'last_display_percent',x.last_display_percent) ORDER BY x.submitted_at),'[]'::jsonb)
 INTO v FROM (SELECT * FROM berry_private.turnitin_jobs
    WHERE tenant_id=p_tenant AND state='processing' ORDER BY submitted_at LIMIT 100) x;
 RETURN v;
END $$;

CREATE OR REPLACE FUNCTION public.berry_turnitin_progress_mark(
 p_tenant uuid,p_order_id text,p_percent integer
) RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 IF current_user NOT IN ('service_role','postgres') THEN RAISE EXCEPTION 'server only' USING ERRCODE='42501'; END IF;
 IF p_percent NOT BETWEEN 0 AND 99 THEN RAISE EXCEPTION 'invalid percent'; END IF;
 UPDATE berry_private.turnitin_jobs SET last_display_percent=p_percent
   WHERE tenant_id=p_tenant AND order_id=p_order_id AND state='processing'
     AND last_display_percent<p_percent;
 RETURN FOUND;
END $$;

CREATE OR REPLACE FUNCTION public.berry_turnitin_delivery_claim(
 p_tenant uuid,p_order_id text,p_admin bigint
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE j berry_private.turnitin_jobs%ROWTYPE;
BEGIN
 IF current_user NOT IN ('service_role','postgres') THEN RAISE EXCEPTION 'server only' USING ERRCODE='42501'; END IF;
 IF p_admin IS NULL OR p_admin<=0 THEN RAISE EXCEPTION 'admin id missing'; END IF;
 SELECT * INTO j FROM berry_private.turnitin_jobs WHERE tenant_id=p_tenant AND order_id=p_order_id FOR UPDATE;
 IF NOT FOUND OR j.state<>'processing' OR j.assignment_file_id IS NULL THEN
   RAISE EXCEPTION 'report delivery not allowed'; END IF;
 UPDATE berry_private.turnitin_jobs SET state='delivering',updated_at=now() WHERE order_id=p_order_id;
 RETURN jsonb_build_object('order_id',p_order_id,'user_id',j.user_id,'plan',j.plan_code);
END $$;

CREATE OR REPLACE FUNCTION public.berry_turnitin_delivery_complete(
 p_tenant uuid,p_order_id text,p_file_id text
) RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 IF current_user NOT IN ('service_role','postgres') THEN RAISE EXCEPTION 'server only' USING ERRCODE='42501'; END IF;
 IF p_file_id IS NULL OR length(p_file_id) NOT BETWEEN 5 AND 512 THEN
   RAISE EXCEPTION 'invalid report'; END IF;
 UPDATE berry_private.turnitin_jobs SET state='delivered',report_file_id=p_file_id,
   delivered_at=now(),last_display_percent=100,updated_at=now()
 WHERE tenant_id=p_tenant AND order_id=p_order_id AND state='delivering';
 RETURN FOUND;
END $$;

CREATE OR REPLACE FUNCTION public.berry_turnitin_customer_status(
 p_tenant uuid,p_order_id text,p_user bigint
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE j berry_private.turnitin_jobs%ROWTYPE;
BEGIN
 IF current_user NOT IN ('service_role','postgres') THEN RAISE EXCEPTION 'server only' USING ERRCODE='42501'; END IF;
 SELECT * INTO j FROM berry_private.turnitin_jobs WHERE tenant_id=p_tenant
   AND order_id=p_order_id AND user_id=p_user;
 IF NOT FOUND THEN RAISE EXCEPTION 'order not found'; END IF;
 RETURN jsonb_build_object('order_id',j.order_id,'state',j.state,'plan',j.plan_code,
  'submitted_at',j.submitted_at,'delivered_at',j.delivered_at);
END $$;

CREATE OR REPLACE FUNCTION public.berry_turnitin_admin_view(p_tenant uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE plans jsonb; jobs jsonb;
BEGIN
 IF current_user NOT IN ('service_role','postgres') THEN RAISE EXCEPTION 'server only' USING ERRCODE='42501'; END IF;
 plans:=public.berry_turnitin_catalog(p_tenant);
 SELECT coalesce(jsonb_agg(jsonb_build_object(
   'order_id',j.order_id,'plan',j.plan_code,'state',j.state,
   'user_id',j.user_id,'created_at',o.created_at,'submitted_at',j.submitted_at,
   'delivered_at',j.delivered_at,'has_assignment',j.assignment_file_id IS NOT NULL)
   ORDER BY o.created_at DESC),'[]'::jsonb) INTO jobs
 FROM (SELECT * FROM berry_private.turnitin_jobs WHERE tenant_id=p_tenant
       ORDER BY updated_at DESC LIMIT 200) j
 JOIN public.orders o ON o.id=j.order_id AND o.tenant_id=j.tenant_id;
 RETURN jsonb_build_object('plans',plans,'jobs',jobs);
END $$;

CREATE OR REPLACE FUNCTION public.berry_turnitin_admin_edit(
 p_tenant uuid,p_code text,p_payload jsonb,p_key uuid,p_actor text
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE p berry_private.turnitin_plans%ROWTYPE; existing berry_private.turnitin_admin_edits%ROWTYPE;
        new_title text; new_desc text; new_price numeric; new_stock integer;
        new_enabled boolean; new_minutes integer; result jsonb;
BEGIN
 IF current_user NOT IN ('service_role','postgres') THEN RAISE EXCEPTION 'server only' USING ERRCODE='42501'; END IF;
 IF p_tenant IS NULL OR p_code NOT IN ('similarity','ai') OR p_key IS NULL
    OR p_actor IS NULL OR length(p_actor) NOT BETWEEN 1 AND 100
    OR p_payload IS NULL OR jsonb_typeof(p_payload)<>'object'
    OR (SELECT count(*) FROM jsonb_object_keys(p_payload))<>6 OR
    (SELECT bool_or(k NOT IN ('title','description','price_myr','stock','enabled','turnaround_minutes'))
       FROM jsonb_object_keys(p_payload) k) THEN RAISE EXCEPTION 'invalid admin input'; END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(
   'turnitin-plan-edit:'||p_tenant::text||':'||p_key::text,0));
 SELECT * INTO existing FROM berry_private.turnitin_admin_edits WHERE tenant_id=p_tenant AND idempotency_key=p_key;
 IF FOUND THEN
   IF existing.code<>p_code OR existing.payload<>p_payload THEN RAISE EXCEPTION 'admin replay conflict'; END IF;
   RETURN jsonb_build_object('status','replayed','code',p_code);
 END IF;
 new_title:=p_payload->>'title'; new_desc:=p_payload->>'description';
 new_price:=(p_payload->>'price_myr')::numeric;
 new_stock:=(p_payload->>'stock')::integer;
 new_enabled:=(p_payload->>'enabled')::boolean;
 new_minutes:=(p_payload->>'turnaround_minutes')::integer;
 IF new_title IS NULL OR length(new_title) NOT BETWEEN 3 AND 100
    OR new_desc IS NULL OR length(new_desc) NOT BETWEEN 10 AND 2000
    OR new_price IS NULL OR new_price<0 OR new_price>9999
    OR new_stock IS NULL OR new_stock<0 OR new_stock>100000
    OR new_enabled IS NULL
    OR new_minutes IS NULL OR new_minutes NOT BETWEEN 1 AND 1440
    OR (new_enabled AND (new_price<=0 OR new_stock=0)) THEN
   RAISE EXCEPTION 'invalid plan configuration';
 END IF;
 UPDATE berry_private.turnitin_plans SET title=new_title,description=new_desc,
   price_myr=round(new_price,2),stock=new_stock,enabled=new_enabled,
   turnaround_minutes=new_minutes,updated_at=now()
 WHERE tenant_id=p_tenant AND code=p_code RETURNING * INTO p;
 IF NOT FOUND THEN RAISE EXCEPTION 'plan not initialized'; END IF;
 INSERT INTO berry_private.turnitin_admin_edits(tenant_id,idempotency_key,code,payload)
 VALUES(p_tenant,p_key,p_code,p_payload);
 RETURN jsonb_build_object('status','committed','code',p_code,'stock',p.stock,
                           'price_myr',p.price_myr,'enabled',p.enabled);
END $$;

DO $$
DECLARE fn record;
BEGIN
 FOR fn IN SELECT p.oid::regprocedure AS signature
           FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
           WHERE n.nspname='public' AND p.proname LIKE 'berry_turnitin_%'
 LOOP
   EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC,anon,authenticated',fn.signature);
   EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO service_role',fn.signature);
 END LOOP;
END $$;
