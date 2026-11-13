-- STEP 3 — durable quotation storage (additive-only, backward-compatible).
-- Apply ONLY after owner approval. No existing tables are modified.
-- Production schema is not yet present: create it with restricted access.
CREATE SCHEMA IF NOT EXISTS berry_private;
REVOKE ALL ON SCHEMA berry_private FROM PUBLIC;
GRANT USAGE ON SCHEMA berry_private TO service_role;

CREATE TABLE berry_private.ai_quotations (
  quote_id uuid NOT NULL,
  tenant_id uuid NOT NULL REFERENCES public.tenants(id),
  customer_id bigint NOT NULL CHECK(customer_id > 0),
  product_key text NOT NULL,
  mapping_revision integer NOT NULL,
  payload jsonb NOT NULL,          -- frozen signed quote document
  integrity text NOT NULL,
  state text NOT NULL DEFAULT 'active'
    CHECK(state IN ('active','cancelled')),
  idempotency_key text,
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY(quote_id)
);
CREATE UNIQUE INDEX ai_quotations_idem_idx ON berry_private.ai_quotations
  (tenant_id, customer_id, idempotency_key)
  WHERE idempotency_key IS NOT NULL;
CREATE INDEX ai_quotations_owner_idx ON berry_private.ai_quotations
  (tenant_id, customer_id, created_at);
ALTER TABLE berry_private.ai_quotations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON berry_private.ai_quotations FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON berry_private.ai_quotations TO service_role;

-- Durable per-minute rate counts kept separately from actual quotations.
CREATE TABLE berry_private.ai_quote_rate_limits (
 tenant_id uuid NOT NULL REFERENCES public.tenants(id),
 customer_id bigint NOT NULL CHECK(customer_id > 0),
 window_start timestamptz NOT NULL,
 request_count integer NOT NULL CHECK(request_count > 0),
 PRIMARY KEY (tenant_id, customer_id, window_start)
);
ALTER TABLE berry_private.ai_quote_rate_limits ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON berry_private.ai_quote_rate_limits FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON berry_private.ai_quote_rate_limits TO service_role;

-- Atomic idempotent create: ON CONFLICT handles concurrent first inserts.
CREATE FUNCTION public.berry_ai_quote_create(p_tenant uuid, p_customer bigint,
  p_quote uuid, p_product text, p_mapping int, p_payload jsonb,
  p_integrity text, p_idempotency text, p_expires timestamptz)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE existing berry_private.ai_quotations%ROWTYPE;
BEGIN
 IF current_user NOT IN ('service_role','postgres') OR
  coalesce(current_setting('request.jwt.claims',true),'{}')::jsonb->>'role'
    IS DISTINCT FROM 'service_role' THEN
  RAISE EXCEPTION 'server role required' USING ERRCODE='42501'; END IF;
 INSERT INTO berry_private.ai_quotations(quote_id, tenant_id, customer_id,
   product_key, mapping_revision, payload, integrity, idempotency_key,
   expires_at)
 VALUES(p_quote, p_tenant, p_customer, p_product, p_mapping,
        p_payload, p_integrity, p_idempotency, p_expires)
 ON CONFLICT (tenant_id, customer_id, idempotency_key)
   WHERE idempotency_key IS NOT NULL
 DO NOTHING;
 IF FOUND THEN RETURN jsonb_build_object('duplicate', false); END IF;
 -- A concurrent insert has won the unique index race. This statement sees
 -- the committed row after the ON CONFLICT wait under READ COMMITTED.
 SELECT * INTO existing FROM berry_private.ai_quotations
 WHERE tenant_id=p_tenant AND customer_id=p_customer
   AND idempotency_key=p_idempotency;
 IF existing.quote_id IS NULL THEN
  RAISE EXCEPTION 'idempotent quotation lookup failed';
 END IF;
 RETURN jsonb_build_object('duplicate', true, 'state', existing.state,
   'expires_at', existing.expires_at, 'payload', existing.payload,
   'integrity', existing.integrity);
END $;
REVOKE ALL ON FUNCTION
 public.berry_ai_quote_create(uuid,bigint,uuid,text,int,jsonb,text,text,timestamptz)
 FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION
 public.berry_ai_quote_create(uuid,bigint,uuid,text,int,jsonb,text,text,timestamptz)
 TO service_role;

-- Ownership-checked read.
CREATE FUNCTION public.berry_ai_quote_get(p_tenant uuid, p_customer bigint,
  p_quote uuid) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER
 SET search_path='' AS $$
DECLARE q berry_private.ai_quotations%ROWTYPE;
BEGIN
 IF current_user NOT IN ('service_role','postgres') OR
  coalesce(current_setting('request.jwt.claims',true),'{}')::jsonb->>'role'
    IS DISTINCT FROM 'service_role' THEN
  RAISE EXCEPTION 'server role required' USING ERRCODE='42501'; END IF;
 SELECT * INTO q FROM berry_private.ai_quotations
  WHERE quote_id=p_quote AND tenant_id=p_tenant AND customer_id=p_customer;
 IF q.quote_id IS NULL THEN RAISE EXCEPTION 'quotation not found'; END IF;
 RETURN jsonb_build_object('state', q.state, 'expires_at', q.expires_at,
   'payload', q.payload, 'integrity', q.integrity);
END $$;
REVOKE ALL ON FUNCTION public.berry_ai_quote_get(uuid,bigint,uuid)
 FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.berry_ai_quote_get(uuid,bigint,uuid)
 TO service_role;

-- Atomic ownership-checked cancel.
CREATE FUNCTION public.berry_ai_quote_cancel(p_tenant uuid, p_customer bigint,
  p_quote uuid) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER
 SET search_path='' AS $$
DECLARE q berry_private.ai_quotations%ROWTYPE;
BEGIN
 IF current_user NOT IN ('service_role','postgres') OR
  coalesce(current_setting('request.jwt.claims',true),'{}')::jsonb->>'role'
    IS DISTINCT FROM 'service_role' THEN
  RAISE EXCEPTION 'server role required' USING ERRCODE='42501'; END IF;
 SELECT * INTO q FROM berry_private.ai_quotations
  WHERE quote_id=p_quote AND tenant_id=p_tenant AND customer_id=p_customer
  FOR UPDATE;
 IF q.quote_id IS NULL THEN RAISE EXCEPTION 'quotation not found'; END IF;
 UPDATE berry_private.ai_quotations SET state='cancelled'
  WHERE quote_id=p_quote;
 RETURN jsonb_build_object('state', 'cancelled', 'payload', q.payload,
   'integrity', q.integrity);
END $$;
REVOKE ALL ON FUNCTION public.berry_ai_quote_cancel(uuid,bigint,uuid)
 FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.berry_ai_quote_cancel(uuid,bigint,uuid)
 TO service_role;

-- One atomic UPSERT per (tenant, customer, minute). No fake quote rows.
CREATE FUNCTION public.berry_ai_quote_rate(p_tenant uuid, p_customer bigint,
  p_limit int) RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER
 SET search_path='' AS $$
DECLARE cnt int;
BEGIN
 IF current_user NOT IN ('service_role','postgres') OR
  coalesce(current_setting('request.jwt.claims',true),'{}')::jsonb->>'role'
    IS DISTINCT FROM 'service_role' THEN
  RAISE EXCEPTION 'server role required' USING ERRCODE='42501'; END IF;
 IF p_limit IS NULL OR p_limit < 1 THEN
  RAISE EXCEPTION 'invalid quotation rate limit';
 END IF;
 INSERT INTO berry_private.ai_quote_rate_limits
   (tenant_id, customer_id, window_start, request_count)
 VALUES (p_tenant, p_customer, date_trunc('minute', now()), 1)
 ON CONFLICT (tenant_id, customer_id, window_start)
 DO UPDATE SET request_count=berry_private.ai_quote_rate_limits.request_count + 1
 RETURNING request_count INTO cnt;
 RETURN cnt <= p_limit;
END $$;
REVOKE ALL ON FUNCTION public.berry_ai_quote_rate(uuid,bigint,int)
 FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.berry_ai_quote_rate(uuid,bigint,int)
 TO service_role;

-- Rollback (separate file: docs/sql/ai_quotations_rollback.sql) drops
-- functions first, then the table. Additive-only; no business data touched.

