-- REVIEW ONLY. Apply to a SEPARATE ISOLATED STAGING Supabase project.
-- DO NOT apply to the Berry Store production-linked project.
-- SQL access goes via service_role-only RPC, never client-side Data API.
BEGIN;
CREATE SCHEMA IF NOT EXISTS berry_private;
REVOKE ALL ON SCHEMA berry_private FROM PUBLIC, anon, authenticated;
GRANT USAGE ON SCHEMA berry_private TO service_role;

CREATE TABLE IF NOT EXISTS berry_private.ai_model_mappings (
    tenant_id uuid PRIMARY KEY,
    payload jsonb NOT NULL DEFAULT '[]'::jsonb,
    revision bigint NOT NULL DEFAULT 1 CHECK (revision > 0),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT berry_ai_mapping_array CHECK (jsonb_typeof(payload) = 'array')
);
ALTER TABLE berry_private.ai_model_mappings ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON berry_private.ai_model_mappings FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON berry_private.ai_model_mappings TO service_role;

CREATE TABLE IF NOT EXISTS berry_private.ai_model_mapping_requests (
    tenant_id uuid NOT NULL,
    idempotency_key uuid NOT NULL,
    payload_hash text NOT NULL,
    result jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(tenant_id, idempotency_key)
);
ALTER TABLE berry_private.ai_model_mapping_requests ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON berry_private.ai_model_mapping_requests FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT ON berry_private.ai_model_mapping_requests TO service_role;

CREATE OR REPLACE FUNCTION public.berry_ai_model_mappings_get(p_tenant uuid)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $$
DECLARE v_payload jsonb; v_revision bigint;
BEGIN
    IF current_user <> 'service_role' OR p_tenant IS NULL THEN
        RAISE EXCEPTION 'service_role required' USING ERRCODE = '42501';
    END IF;
    SELECT payload, revision INTO v_payload, v_revision
      FROM berry_private.ai_model_mappings WHERE tenant_id = p_tenant;
    RETURN jsonb_build_object('mappings', coalesce(v_payload, '[]'::jsonb),
                              'revision', coalesce(v_revision, 0));
END;
$$;

CREATE OR REPLACE FUNCTION public.berry_ai_model_mappings_put(
    p_tenant uuid, p_payload jsonb, p_key uuid, p_expected_revision bigint
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $$
DECLARE
    v_hash text;
    v_old_hash text;
    v_old_result jsonb;
    v_current bigint;
    v_result jsonb;
BEGIN
    IF current_user <> 'service_role' THEN
        RAISE EXCEPTION 'service_role required' USING ERRCODE = '42501';
    END IF;
    IF p_tenant IS NULL OR p_key IS NULL OR p_expected_revision IS NULL
       OR p_expected_revision < 0 OR jsonb_typeof(p_payload) <> 'array'
       OR jsonb_array_length(p_payload) > 6 THEN
        RAISE EXCEPTION 'invalid mapping request' USING ERRCODE = '22023';
    END IF;
    v_hash := encode(sha256(convert_to(
        jsonb_build_object('payload', p_payload, 'expected_revision', p_expected_revision)::text,
        'UTF8')), 'hex');
    PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(
        p_tenant::text || ':' || p_key::text, 0));
    SELECT payload_hash, result INTO v_old_hash, v_old_result
      FROM berry_private.ai_model_mapping_requests
      WHERE tenant_id = p_tenant AND idempotency_key = p_key;
    IF FOUND THEN
        IF v_hash <> v_old_hash THEN
            RAISE EXCEPTION 'idempotency conflict' USING ERRCODE = '23505';
        END IF;
        RETURN v_old_result;
    END IF;
    -- Serialize changes to a single tenant even with different request keys.
    PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(
        'berry-mapping:' || p_tenant::text, 0));
    SELECT revision INTO v_current
      FROM berry_private.ai_model_mappings WHERE tenant_id=p_tenant FOR UPDATE;
    IF coalesce(v_current, 0) <> p_expected_revision THEN
        RAISE EXCEPTION 'stale mapping revision' USING ERRCODE = '40001';
    END IF;
    INSERT INTO berry_private.ai_model_mappings(tenant_id,payload,revision)
      VALUES(p_tenant,p_payload,p_expected_revision + 1)
      ON CONFLICT(tenant_id) DO UPDATE
      SET payload=excluded.payload, revision=excluded.revision, updated_at=now();
    v_result := jsonb_build_object('mappings', p_payload, 'revision', p_expected_revision + 1);
    INSERT INTO berry_private.ai_model_mapping_requests
      (tenant_id,idempotency_key,payload_hash,result)
      VALUES (p_tenant,p_key,v_hash,v_result);
    RETURN v_result;
END;
$$;
REVOKE ALL ON FUNCTION public.berry_ai_model_mappings_get(uuid) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.berry_ai_model_mappings_put(uuid,jsonb,uuid,bigint) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.berry_ai_model_mappings_get(uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.berry_ai_model_mappings_put(uuid,jsonb,uuid,bigint) TO service_role;
COMMIT;
