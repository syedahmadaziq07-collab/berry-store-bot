-- Berry Store Main: approved 9-service document-check catalog (2026-11-15).
-- Apply after berry_turnitin_manual_services.sql. Existing jobs, order IDs,
-- receipts, delivered reports and sold stock are intentionally preserved.
-- The reports are fulfilled by the owner; no supplier API is integrated.
BEGIN;

ALTER TABLE berry_private.turnitin_plans DROP CONSTRAINT IF EXISTS turnitin_plans_code_check;
ALTER TABLE berry_private.turnitin_plans ADD CONSTRAINT turnitin_plans_code_check CHECK (
  code IN ('similarity','ai','gptzero_basic','gptzero_standard','gptzero_premium',
           'bundle_basic','bundle_standard','bundle_premium','bundle_turnitin_ai')
);
ALTER TABLE berry_private.turnitin_jobs DROP CONSTRAINT IF EXISTS turnitin_jobs_plan_code_check;
ALTER TABLE berry_private.turnitin_jobs ADD CONSTRAINT turnitin_jobs_plan_code_check CHECK (
  plan_code IN ('similarity','ai','gptzero_basic','gptzero_standard','gptzero_premium',
                'bundle_basic','bundle_standard','bundle_premium','bundle_turnitin_ai')
);
ALTER TABLE berry_private.turnitin_jobs ADD COLUMN IF NOT EXISTS staged_report_file_id text;

CREATE TABLE IF NOT EXISTS berry_private.turnitin_plan_components (
  tenant_id uuid NOT NULL,
  bundle_code text NOT NULL,
  component_code text NOT NULL,
  quantity integer NOT NULL DEFAULT 1 CHECK(quantity BETWEEN 1 AND 100),
  PRIMARY KEY (tenant_id,bundle_code,component_code),
  CHECK (bundle_code IN ('bundle_basic','bundle_standard','bundle_premium','bundle_turnitin_ai')),
  CHECK (component_code IN ('similarity','ai','gptzero_basic','gptzero_standard','gptzero_premium')),
  FOREIGN KEY (tenant_id,bundle_code) REFERENCES berry_private.turnitin_plans(tenant_id,code),
  FOREIGN KEY (tenant_id,component_code) REFERENCES berry_private.turnitin_plans(tenant_id,code)
);
ALTER TABLE berry_private.turnitin_plan_components ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON berry_private.turnitin_plan_components FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON berry_private.turnitin_plan_components TO service_role;

-- Seed only the explicitly approved tenant, never other storefronts.
INSERT INTO berry_private.turnitin_plans
  (tenant_id,code,title,description,price_myr,stock,enabled,turnaround_minutes)
VALUES
  ('92c1e5ca-8498-438f-b777-3dc1c3195c1b','similarity','Turnitin Similarity Check',
   'Semak tahap persamaan teks assignment awak. Termasuk 1 Similarity Report dalam PDF. Upload fail PDF atau DOCX selepas bayaran disahkan.',3.10,40,true,15),
  ('92c1e5ca-8498-438f-b777-3dc1c3195c1b','ai','Turnitin AI Writing Check',
   'Semak indikator AI writing untuk dokumen berbahasa English. Termasuk 1 AI Writing Report dalam PDF. Upload fail PDF atau DOCX selepas bayaran disahkan.',9.00,40,true,15),
  ('92c1e5ca-8498-438f-b777-3dc1c3195c1b','gptzero_basic','GPTZero Basic (250–50,000 aksara)',
   'Sesuai untuk dokumen 250 hingga 50,000 aksara. Termasuk 1 GPTZero AI Check Report dalam PDF. Upload fail PDF atau DOCX selepas bayaran disahkan.',4.00,40,true,15),
  ('92c1e5ca-8498-438f-b777-3dc1c3195c1b','gptzero_standard','GPTZero Standard (50,001–100,000 aksara)',
   'Sesuai untuk dokumen 50,001 hingga 100,000 aksara. Termasuk 1 GPTZero AI Check Report dalam PDF. Upload fail PDF atau DOCX selepas bayaran disahkan.',5.00,40,true,15),
  ('92c1e5ca-8498-438f-b777-3dc1c3195c1b','gptzero_premium','GPTZero Premium (100,001–150,000 aksara)',
   'Sesuai untuk dokumen 100,001 hingga 150,000 aksara. Termasuk 1 GPTZero AI Check Report dalam PDF. Upload fail PDF atau DOCX selepas bayaran disahkan.',6.00,40,true,15),
  ('92c1e5ca-8498-438f-b777-3dc1c3195c1b','bundle_basic','Bundle Basic: Similarity + GPTZero',
   'Dua semakan dalam satu order: Turnitin Similarity dan GPTZero Basic (250–50,000 aksara). Awak terima 2 laporan PDF berasingan. Upload 1 fail PDF atau DOCX.',7.00,40,true,15),
  ('92c1e5ca-8498-438f-b777-3dc1c3195c1b','bundle_standard','Bundle Standard: Similarity + GPTZero',
   'Dua semakan dalam satu order: Turnitin Similarity dan GPTZero Standard (50,001–100,000 aksara). Awak terima 2 laporan PDF berasingan. Upload 1 fail PDF atau DOCX.',8.00,40,true,15),
  ('92c1e5ca-8498-438f-b777-3dc1c3195c1b','bundle_premium','Bundle Premium: Similarity + GPTZero',
   'Dua semakan dalam satu order: Turnitin Similarity dan GPTZero Premium (100,001–150,000 aksara). Awak terima 2 laporan PDF berasingan. Upload 1 fail PDF atau DOCX.',9.00,40,true,15),
  ('92c1e5ca-8498-438f-b777-3dc1c3195c1b','bundle_turnitin_ai','Bundle Turnitin: Similarity + AI',
   'Dua semakan dalam satu order: Turnitin Similarity dan Turnitin AI Writing Check (English). Awak terima 2 laporan PDF berasingan. Upload 1 fail PDF atau DOCX.',15.00,40,true,15)
ON CONFLICT (tenant_id,code) DO UPDATE SET
  title=EXCLUDED.title, description=EXCLUDED.description,
  price_myr=EXCLUDED.price_myr, updated_at=now();
-- DO NOT update stock/enabled on conflict: existing sales and owner settings matter.

INSERT INTO berry_private.turnitin_plan_components(tenant_id,bundle_code,component_code,quantity)
VALUES
  ('92c1e5ca-8498-438f-b777-3dc1c3195c1b','bundle_basic','similarity',1),
  ('92c1e5ca-8498-438f-b777-3dc1c3195c1b','bundle_basic','gptzero_basic',1),
  ('92c1e5ca-8498-438f-b777-3dc1c3195c1b','bundle_standard','similarity',1),
  ('92c1e5ca-8498-438f-b777-3dc1c3195c1b','bundle_standard','gptzero_standard',1),
  ('92c1e5ca-8498-438f-b777-3dc1c3195c1b','bundle_premium','similarity',1),
  ('92c1e5ca-8498-438f-b777-3dc1c3195c1b','bundle_premium','gptzero_premium',1),
  ('92c1e5ca-8498-438f-b777-3dc1c3195c1b','bundle_turnitin_ai','similarity',1),
  ('92c1e5ca-8498-438f-b777-3dc1c3195c1b','bundle_turnitin_ai','ai',1)
ON CONFLICT (tenant_id,bundle_code,component_code) DO NOTHING;

CREATE OR REPLACE FUNCTION public.berry_turnitin_catalog(p_tenant uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE x jsonb;
BEGIN
  IF current_user NOT IN ('service_role','postgres') THEN RAISE EXCEPTION 'server only' USING ERRCODE='42501'; END IF;
  SELECT coalesce(jsonb_agg(jsonb_build_object(
    'code',p.code,'title',p.title,'description',p.description,'price_myr',p.price_myr,
    'stock',p.stock,'available_stock',LEAST(p.stock,coalesce((
      SELECT min(CASE WHEN c.enabled THEN floor(c.stock::numeric / link.quantity)::integer ELSE 0 END)
      FROM berry_private.turnitin_plan_components link
      JOIN berry_private.turnitin_plans c ON c.tenant_id=link.tenant_id AND c.code=link.component_code
      WHERE link.tenant_id=p.tenant_id AND link.bundle_code=p.code
    ),p.stock)),
    'enabled',p.enabled,'turnaround_minutes',p.turnaround_minutes)
    ORDER BY p.code),'[]'::jsonb) INTO x
  FROM berry_private.turnitin_plans p WHERE p.tenant_id=p_tenant;
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
 SELECT * INTO ord FROM public.orders WHERE tenant_id=p_tenant AND user_id=p_user
   AND status IN ('pending','waiting','waiting_approval') ORDER BY created_at,id LIMIT 1;
 IF FOUND THEN RAISE EXCEPTION 'existing unpaid order must be resolved first'; END IF;
 SELECT * INTO job FROM berry_private.turnitin_jobs WHERE tenant_id=p_tenant AND user_id=p_user
   AND state IN ('awaiting_upload','processing','delivering') ORDER BY updated_at DESC LIMIT 1;
 IF FOUND THEN RAISE EXCEPTION 'previous report not finished'; END IF;
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

CREATE OR REPLACE FUNCTION public.berry_turnitin_approve(
 p_tenant uuid,p_order_id text,p_admin bigint
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE j berry_private.turnitin_jobs%ROWTYPE; price numeric; component record;
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
 -- Every bundle consumes one of its own stock AND one of each included service.
 -- All decrements roll back if any component is missing or sold out.
 FOR component IN
   SELECT component_code,quantity FROM berry_private.turnitin_plan_components
   WHERE tenant_id=p_tenant AND bundle_code=j.plan_code ORDER BY component_code
 LOOP
   UPDATE berry_private.turnitin_plans SET stock=stock-component.quantity,updated_at=now()
   WHERE tenant_id=p_tenant AND code=component.component_code
     AND stock>=component.quantity AND enabled=true AND price_myr>0;
   IF NOT FOUND THEN RAISE EXCEPTION 'bundle component out of stock: refund or contact customer'; END IF;
 END LOOP;
 UPDATE public.orders SET status='completed',updated_at=now()
   WHERE id=p_order_id AND tenant_id=p_tenant AND status='waiting_approval';
 IF NOT FOUND THEN RAISE EXCEPTION 'order payment state invalid'; END IF;
 UPDATE berry_private.turnitin_jobs SET state='awaiting_upload',updated_at=now() WHERE order_id=p_order_id;
 RETURN jsonb_build_object('order_id',p_order_id,'user_id',j.user_id,
                           'plan',j.plan_code,'state','awaiting_upload','already_approved',false);
END $$;

CREATE OR REPLACE FUNCTION public.berry_turnitin_processing(p_tenant uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE v jsonb;
BEGIN
 IF current_user NOT IN ('service_role','postgres') THEN RAISE EXCEPTION 'server only' USING ERRCODE='42501'; END IF;
 SELECT coalesce(jsonb_agg(jsonb_build_object('order_id',x.order_id,'user_id',x.user_id,
   'plan',x.plan_code,'submitted_at',x.submitted_at,'progress_message_id',x.progress_message_id,
   'last_display_percent',x.last_display_percent) ORDER BY x.submitted_at),'[]'::jsonb)
 INTO v FROM (SELECT * FROM berry_private.turnitin_jobs
    WHERE tenant_id=p_tenant AND state='processing' ORDER BY submitted_at LIMIT 100) x;
 RETURN v;
END $$;

-- A bundle must have both PDFs before any report is sent to the customer.
CREATE OR REPLACE FUNCTION public.berry_turnitin_delivery_stage(
 p_tenant uuid,p_order_id text,p_admin bigint,p_file_id text
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE j berry_private.turnitin_jobs%ROWTYPE;
BEGIN
 IF current_user NOT IN ('service_role','postgres') THEN RAISE EXCEPTION 'server only' USING ERRCODE='42501'; END IF;
 IF p_admin IS NULL OR p_admin<=0 OR p_file_id IS NULL OR length(p_file_id) NOT BETWEEN 5 AND 512
 THEN RAISE EXCEPTION 'invalid report'; END IF;
 SELECT * INTO j FROM berry_private.turnitin_jobs
 WHERE tenant_id=p_tenant AND order_id=p_order_id FOR UPDATE;
 IF NOT FOUND OR j.state<>'processing' OR j.assignment_file_id IS NULL OR
    NOT EXISTS(SELECT 1 FROM berry_private.turnitin_plan_components
      WHERE tenant_id=p_tenant AND bundle_code=j.plan_code)
 THEN RAISE EXCEPTION 'bundle delivery not allowed'; END IF;
 IF j.staged_report_file_id IS NULL THEN
   UPDATE berry_private.turnitin_jobs SET staged_report_file_id=p_file_id,updated_at=now()
   WHERE tenant_id=p_tenant AND order_id=p_order_id;
   RETURN jsonb_build_object('staged',true);
 END IF;
 IF j.staged_report_file_id=p_file_id THEN RAISE EXCEPTION 'second report must differ from first'; END IF;
 RETURN jsonb_build_object('staged',false);
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
 IF EXISTS(SELECT 1 FROM berry_private.turnitin_plan_components
     WHERE tenant_id=p_tenant AND bundle_code=j.plan_code)
   AND j.staged_report_file_id IS NULL
 THEN RAISE EXCEPTION 'first bundle report missing'; END IF;
 UPDATE berry_private.turnitin_jobs SET state='delivering',updated_at=now() WHERE order_id=p_order_id;
 RETURN jsonb_build_object('order_id',p_order_id,'user_id',j.user_id,'plan',j.plan_code,
   'progress_message_id',j.progress_message_id,'staged_report_file_id',j.staged_report_file_id);
END $$;

CREATE OR REPLACE FUNCTION public.berry_turnitin_admin_edit(
 p_tenant uuid,p_code text,p_payload jsonb,p_key uuid,p_actor text
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE p berry_private.turnitin_plans%ROWTYPE; existing berry_private.turnitin_admin_edits%ROWTYPE;
        new_title text; new_desc text; new_price numeric; new_stock integer;
        new_enabled boolean; new_minutes integer;
BEGIN
 IF current_user NOT IN ('service_role','postgres') THEN RAISE EXCEPTION 'server only' USING ERRCODE='42501'; END IF;
 IF p_tenant IS NULL OR p_code IS NULL OR NOT EXISTS (
      SELECT 1 FROM berry_private.turnitin_plans WHERE tenant_id=p_tenant AND code=p_code)
    OR p_key IS NULL OR p_actor IS NULL OR length(p_actor) NOT BETWEEN 1 AND 100
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
    OR new_stock IS NULL OR new_stock<0 OR new_stock>100000 OR new_enabled IS NULL
    OR new_minutes IS NULL OR new_minutes NOT BETWEEN 1 AND 1440
    OR (new_enabled AND (new_price<=0 OR new_stock=0))
 THEN RAISE EXCEPTION 'invalid plan configuration'; END IF;
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
COMMIT;
