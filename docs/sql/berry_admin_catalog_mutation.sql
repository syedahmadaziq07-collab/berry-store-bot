-- REVIEW DRAFT: apply ONLY to an isolated staging database after schema review.
-- Not applied to the existing production project by this change.
BEGIN;
CREATE TABLE IF NOT EXISTS public.berry_admin_mutations (
  tenant_id uuid NOT NULL REFERENCES public.tenants(id),
  idempotency_key uuid NOT NULL,
  request_hash text NOT NULL,
  result jsonb NOT NULL,
  actor text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, idempotency_key)
);
ALTER TABLE public.berry_admin_mutations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.berry_admin_mutations FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT ON public.berry_admin_mutations TO service_role;

CREATE OR REPLACE FUNCTION public.berry_admin_catalog_mutation(
  p_tenant uuid, p_operation text, p_id text, p_payload jsonb, p_actor text, p_key uuid
) RETURNS jsonb
LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $$
DECLARE
  v_hash text;
  v_previous public.berry_admin_mutations%ROWTYPE;
  v_product public.products%ROWTYPE;
  v_result jsonb;
BEGIN
  IF current_user NOT IN ('service_role', 'postgres') THEN
    RAISE EXCEPTION 'server role required' USING ERRCODE = '42501';
  END IF;
  IF p_tenant IS NULL OR p_key IS NULL OR p_actor IS DISTINCT FROM 'admin'
     OR jsonb_typeof(p_payload) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION 'invalid mutation identity or payload';
  END IF;
  IF p_operation NOT IN ('product_create','product_update','product_archive','product_stock') THEN
    RAISE EXCEPTION 'operation not allowlisted';
  END IF;
  IF EXISTS (SELECT 1 FROM jsonb_object_keys(p_payload) AS k(key)
             WHERE key NOT IN ('name','description','price','stock','duration','is_active','auto_delivery')) THEN
    RAISE EXCEPTION 'payload fields not allowlisted';
  END IF;
  IF p_operation <> 'product_create' AND (p_id IS NULL OR p_id !~ '^[1-9][0-9]{0,9}$') THEN
    RAISE EXCEPTION 'invalid product id';
  END IF;
  v_hash := encode(sha256(convert_to(jsonb_build_object('operation',p_operation,'id',p_id,'payload',p_payload)::text, 'UTF8')), 'hex');
  -- Same tenant/key cannot be processed concurrently. Hash collisions only serialize work.
  PERFORM pg_advisory_xact_lock(hashtextextended(p_tenant::text || ':' || p_key::text, 0));
  SELECT * INTO v_previous FROM public.berry_admin_mutations
    WHERE tenant_id=p_tenant AND idempotency_key=p_key;
  IF FOUND THEN
    IF v_previous.request_hash <> v_hash THEN
      RAISE EXCEPTION 'idempotency key reused for a different request';
    END IF;
    RETURN v_previous.result;
  END IF;
  IF p_operation IN ('product_create','product_update') THEN
    IF char_length(trim(p_payload->>'name')) NOT BETWEEN 1 AND 200
       OR p_payload->>'name' IS NULL OR p_payload->>'price' IS NULL
       OR (p_payload->>'price')::numeric NOT BETWEEN 0 AND 1000000
       OR (p_payload->>'price')::numeric <> round((p_payload->>'price')::numeric,2) THEN
      RAISE EXCEPTION 'invalid product name or price';
    END IF;
  END IF;
  IF p_payload ? 'stock' AND (
      jsonb_typeof(p_payload->'stock') <> 'number'
      OR p_payload->>'stock' !~ '^[0-9]+$'
      OR (p_payload->>'stock')::numeric NOT BETWEEN 0 AND 1000000) THEN
    RAISE EXCEPTION 'invalid stock';
  END IF;
  IF p_operation = 'product_stock' AND NOT p_payload ? 'stock' THEN
    RAISE EXCEPTION 'stock is required';
  END IF;
  IF p_operation = 'product_create' THEN
    INSERT INTO public.products(tenant_id,name,description,price,stock,duration,is_active,auto_delivery,status)
    VALUES(p_tenant,trim(p_payload->>'name'),coalesce(p_payload->>'description',''),
      (p_payload->>'price')::numeric,coalesce((p_payload->>'stock')::integer,0),
      coalesce(p_payload->>'duration',''),coalesce((p_payload->>'is_active')::boolean,true),
      coalesce((p_payload->>'auto_delivery')::boolean,false),'active') RETURNING * INTO v_product;
  ELSE
    SELECT * INTO v_product FROM public.products
      WHERE tenant_id=p_tenant AND id=p_id::integer FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'product not found'; END IF;
    IF p_operation = 'product_archive' THEN
      UPDATE public.products SET status='archived',is_active=false
        WHERE tenant_id=p_tenant AND id=p_id::integer RETURNING * INTO v_product;
    ELSIF p_operation = 'product_stock' THEN
      UPDATE public.products SET stock=(p_payload->>'stock')::integer
        WHERE tenant_id=p_tenant AND id=p_id::integer RETURNING * INTO v_product;
    ELSE
      UPDATE public.products SET name=trim(p_payload->>'name'),
        description=coalesce(p_payload->>'description',description),price=(p_payload->>'price')::numeric,
        stock=coalesce((p_payload->>'stock')::integer,stock),duration=coalesce(p_payload->>'duration',duration),
        is_active=coalesce((p_payload->>'is_active')::boolean,is_active),
        auto_delivery=coalesce((p_payload->>'auto_delivery')::boolean,auto_delivery)
        WHERE tenant_id=p_tenant AND id=p_id::integer RETURNING * INTO v_product;
    END IF;
  END IF;
  v_result := jsonb_build_object('id',v_product.id,'operation',p_operation,'status','committed');
  -- Result/audit and mutation commit atomically. No credential secrets are recorded.
  INSERT INTO public.berry_admin_mutations(tenant_id,idempotency_key,request_hash,result,actor)
    VALUES(p_tenant,p_key,v_hash,v_result,p_actor);
  RETURN v_result;
END;
$$;
REVOKE ALL ON FUNCTION public.berry_admin_catalog_mutation(uuid,text,text,jsonb,text,uuid) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.berry_admin_catalog_mutation(uuid,text,text,jsonb,text,uuid) TO service_role;
COMMIT;
