-- EPHEMERAL POSTGRES CI ONLY; never execute on Supabase.
CREATE SCHEMA berry_private;
CREATE TABLE berry_private.ai_video_jobs (
 tenant_id uuid NOT NULL,job_id uuid NOT NULL,user_id bigint NOT NULL,
 request_hash text NOT NULL,arguments jsonb NOT NULL,quote jsonb NOT NULL,
 debit_cents bigint NOT NULL,state text NOT NULL,budget_id uuid,
 budget_reserved_cents bigint,provider_request_id text,
 queue_status_url text,queue_result_url text,result_url text,delivery_id text,
 created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),
 submission_tags jsonb,last_recovery_scan_at timestamptz,
 PRIMARY KEY(tenant_id,job_id));
CREATE TABLE berry_private.ai_video_test_budgets (
 tenant_id uuid NOT NULL,budget_id uuid NOT NULL,test_user_id bigint NOT NULL,
 max_cost_cents bigint NOT NULL CHECK(max_cost_cents BETWEEN 1 AND 500),
 max_generations integer NOT NULL CHECK(max_generations BETWEEN 1 AND 5),
 reserved_cost_cents bigint NOT NULL DEFAULT 0 CHECK(reserved_cost_cents>=0),
 reserved_generations integer NOT NULL DEFAULT 0 CHECK(reserved_generations>=0),
 expires_at timestamptz NOT NULL,
 CHECK(reserved_cost_cents<=max_cost_cents),
 CHECK(reserved_generations<=max_generations),
 PRIMARY KEY(tenant_id,budget_id));
CREATE TABLE berry_private.ai_video_job_events (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,tenant_id uuid NOT NULL,
 job_id uuid NOT NULL,action text NOT NULL,state text NOT NULL,
 evidence jsonb NOT NULL DEFAULT '{}'::jsonb,created_at timestamptz NOT NULL DEFAULT now());
-- Fake wallet dependency is explicitly inert and must never be called by these tests.
CREATE FUNCTION public.ai_wallet_apply_transaction(uuid,bigint,numeric,text,text,text,text)
RETURNS jsonb LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'wallet fixture forbidden'; END $$;
