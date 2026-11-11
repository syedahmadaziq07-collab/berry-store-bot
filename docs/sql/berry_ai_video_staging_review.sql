-- REVIEW ONLY: DO NOT APPLY TO THE PRODUCTION SUPABASE PROJECT.
-- Deploy only to an isolated staging Supabase project after security review.
-- The existing wallet RPC ai_wallet_apply_transaction is assumed to exist.
-- All calls require a service_role JWT, never a browser-side key.
BEGIN;

CREATE TABLE IF NOT EXISTS public.berry_ai_video_jobs (
  job_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  user_id bigint NOT NULL CHECK (user_id > 0),
  chat_id bigint NOT NULL,
  idempotency_key uuid NOT NULL,
  display_name text NOT NULL,
  provider_model_id text NOT NULL,
  prompt text NOT NULL,
  photo_file_id text NOT NULL,
  duration text NOT NULL CHECK (duration IN ('5','8')),
  resolution text NOT NULL DEFAULT '720p' CHECK (resolution = '720p'),
  credits_cost integer NOT NULL CHECK (credits_cost BETWEEN 25 AND 1000000 AND credits_cost % 25 = 0),
  amount_myr numeric(12,2) NOT NULL CHECK (amount_myr > 0),
  status text NOT NULL DEFAULT 'reserved'
    CHECK (status IN ('reserved','submitting','submission_unknown','queued','running',
                     'rendered','delivering','delivered','failed')),
  provider_request_id text,
  provider_status_url text,
  provider_response_url text,
  video_url text,
  telegram_message_id bigint,
  failure_reason text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT berry_ai_video_job_idempotency UNIQUE (tenant_id, idempotency_key),
  CONSTRAINT berry_ai_video_provider_request UNIQUE (tenant_id, provider_request_id)
);
CREATE INDEX IF NOT EXISTS berry_ai_video_jobs_owner_idx
  ON public.berry_ai_video_jobs (tenant_id, user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS berry_ai_video_jobs_status_idx
  ON public.berry_ai_video_jobs (tenant_id, status, updated_at);

ALTER TABLE public.berry_ai_video_jobs ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.berry_ai_video_jobs FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON public.berry_ai_video_jobs TO service_role;

-- An authenticated service_role request can reserve a job AND debit the
-- existing wallet in one PostgREST transaction. A failed debit rolls back
-- the reservation automatically. Idempotent retry returns existing job
-- WITHOUT creating a second charge or resubmitting to fal.ai.
CREATE OR REPLACE FUNCTION public.berry_ai_video_reserve(
  p_tenant uuid, p_user bigint, p_chat bigint, p_idempotency uuid,
  p_display text, p_model text, p_prompt text, p_photo_file_id text,
  p_duration text, p_credits integer
) RETURNS TABLE(job_id uuid, job_status text, newly_reserved boolean)
LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $$
DECLARE
  v_id uuid;
  v_existing public.berry_ai_video_jobs%ROWTYPE;
  v_amount numeric(12,2);
BEGIN
  IF current_setting('request.jwt.claim.role', true) IS DISTINCT FROM 'service_role' THEN
    RAISE EXCEPTION 'Unauthorized';
  END IF;
  IF p_tenant IS NULL OR p_user <= 0 OR p_chat IS NULL OR p_idempotency IS NULL
     OR p_display IS NULL OR length(btrim(p_display)) NOT BETWEEN 1 AND 64
     OR p_model IS DISTINCT FROM 'fal-ai/pixverse/v3.5/image-to-video'
     OR p_duration NOT IN ('5','8')
     OR p_prompt IS NULL OR octet_length(p_prompt) NOT BETWEEN 1 AND 2048
     OR p_photo_file_id IS NULL OR length(p_photo_file_id) NOT BETWEEN 1 AND 300
     OR p_credits IS NULL OR p_credits < 25 OR p_credits > 1000000
     OR p_credits % 25 <> 0
  THEN
     RAISE EXCEPTION 'Invalid AI video job configuration';
  END IF;
  v_amount := p_credits::numeric / 1250;
  INSERT INTO public.berry_ai_video_jobs(
    tenant_id,user_id,chat_id,idempotency_key,display_name,provider_model_id,
    prompt,photo_file_id,duration,credits_cost,amount_myr
  ) VALUES (
    p_tenant,p_user,p_chat,p_idempotency,p_display,p_model,
    p_prompt,p_photo_file_id,p_duration,p_credits,v_amount
  ) ON CONFLICT (tenant_id,idempotency_key) DO NOTHING
  RETURNING public.berry_ai_video_jobs.job_id INTO v_id;

  IF v_id IS NULL THEN
    SELECT * INTO v_existing FROM public.berry_ai_video_jobs
    WHERE tenant_id=p_tenant AND idempotency_key=p_idempotency FOR UPDATE;
    IF NOT FOUND OR v_existing.user_id IS DISTINCT FROM p_user
       OR v_existing.chat_id IS DISTINCT FROM p_chat
       OR v_existing.display_name IS DISTINCT FROM p_display
       OR v_existing.provider_model_id IS DISTINCT FROM p_model
       OR v_existing.prompt IS DISTINCT FROM p_prompt
       OR v_existing.photo_file_id IS DISTINCT FROM p_photo_file_id
       OR v_existing.duration IS DISTINCT FROM p_duration
       OR v_existing.credits_cost IS DISTINCT FROM p_credits THEN
      RAISE EXCEPTION 'Idempotency key reused with different job data';
    END IF;
    job_id := v_existing.job_id;
    job_status := v_existing.status;
    newly_reserved := false;
    RETURN NEXT; RETURN;
  END IF;

  -- Service-role-only idempotent wallet RPC. This is part of the same SQL tx.
  PERFORM public.ai_wallet_apply_transaction(
    p_tenant, p_user, -v_amount, 'debit',
    'berry-video-debit:' || v_id::text, v_id::text,
    'Berry AI Video job reservation'
  );
  job_id := v_id;
  job_status := 'reserved';
  newly_reserved := true;
  RETURN NEXT;
END; $$;

-- Exactly one worker can claim a job for first external submission.
-- An interrupted 'submitting' job MUST be manually reconciled; never blindly
-- re-claim and potentially pay the provider twice.
CREATE OR REPLACE FUNCTION public.berry_ai_video_claim_submit(p_job uuid, p_tenant uuid)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $$
DECLARE v_count integer;
BEGIN
  IF current_setting('request.jwt.claim.role', true) IS DISTINCT FROM 'service_role' THEN
    RAISE EXCEPTION 'Unauthorized';
  END IF;
  UPDATE public.berry_ai_video_jobs
    SET status='submitting', updated_at=now()
    WHERE job_id=p_job AND tenant_id=p_tenant AND status='reserved';
  GET DIAGNOSTICS v_count = ROW_COUNT;
  RETURN v_count=1;
END; $$;

CREATE OR REPLACE FUNCTION public.berry_ai_video_record_submit(
 p_job uuid, p_tenant uuid, p_request text, p_status_url text, p_response_url text
) RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $$
DECLARE v_count integer;
BEGIN
  IF current_setting('request.jwt.claim.role', true) IS DISTINCT FROM 'service_role' THEN
    RAISE EXCEPTION 'Unauthorized';
  END IF;
  IF p_request IS NULL OR length(p_request) NOT BETWEEN 30 AND 60
      OR p_status_url NOT LIKE 'https://queue.fal.run/%'
      OR p_response_url NOT LIKE 'https://queue.fal.run/%' THEN
    RAISE EXCEPTION 'Invalid provider request metadata';
  END IF;
  UPDATE public.berry_ai_video_jobs
    SET status='queued',provider_request_id=p_request,
      provider_status_url=p_status_url,provider_response_url=p_response_url,
      updated_at=now()
    WHERE job_id=p_job AND tenant_id=p_tenant AND status='submitting';
  GET DIAGNOSTICS v_count = ROW_COUNT;
  RETURN v_count=1;
END; $$;

CREATE OR REPLACE FUNCTION public.berry_ai_video_record_render(
 p_job uuid, p_tenant uuid, p_video_url text
) RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $$
DECLARE v_count integer;
BEGIN
  IF current_setting('request.jwt.claim.role', true) IS DISTINCT FROM 'service_role' THEN
    RAISE EXCEPTION 'Unauthorized';
  END IF;
  IF p_video_url IS NULL OR p_video_url NOT LIKE 'https://%' THEN
    RAISE EXCEPTION 'Invalid result URL';
  END IF;
  UPDATE public.berry_ai_video_jobs SET status='rendered',video_url=p_video_url,updated_at=now()
    WHERE job_id=p_job AND tenant_id=p_tenant AND status IN ('queued','running');
  GET DIAGNOSTICS v_count = ROW_COUNT;
  RETURN v_count=1;
END; $$;

-- Delivery may not be retried automatically once 'delivering': Telegram's
-- sendVideo has no idempotency key; manual reconciliation avoids duplicates.
CREATE OR REPLACE FUNCTION public.berry_ai_video_claim_delivery(p_job uuid, p_tenant uuid)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $$
DECLARE v_count integer;
BEGIN
  IF current_setting('request.jwt.claim.role', true) IS DISTINCT FROM 'service_role' THEN
    RAISE EXCEPTION 'Unauthorized';
  END IF;
  UPDATE public.berry_ai_video_jobs SET status='delivering',updated_at=now()
    WHERE job_id=p_job AND tenant_id=p_tenant AND status='rendered';
  GET DIAGNOSTICS v_count = ROW_COUNT;
  RETURN v_count=1;
END; $$;

CREATE OR REPLACE FUNCTION public.berry_ai_video_mark_delivered(
 p_job uuid, p_tenant uuid, p_telegram_message_id bigint
) RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $$
DECLARE v_count integer;
BEGIN
  IF current_setting('request.jwt.claim.role', true) IS DISTINCT FROM 'service_role' THEN
    RAISE EXCEPTION 'Unauthorized';
  END IF;
  IF p_telegram_message_id IS NULL OR p_telegram_message_id <= 0 THEN
    RAISE EXCEPTION 'Invalid Telegram message id';
  END IF;
  UPDATE public.berry_ai_video_jobs
    SET status='delivered',telegram_message_id=p_telegram_message_id,updated_at=now()
    WHERE job_id=p_job AND tenant_id=p_tenant AND status='delivering';
  GET DIAGNOSTICS v_count = ROW_COUNT;
  RETURN v_count=1;
END; $$;

-- Refund only after definitive provider rejection/failure, as confirmed by a
-- trusted server-side worker. Never refund after unknown submission or timeout.
CREATE OR REPLACE FUNCTION public.berry_ai_video_fail_and_refund(
 p_job uuid, p_tenant uuid, p_reason text
) RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path = ''
AS $$
DECLARE v_job public.berry_ai_video_jobs%ROWTYPE;
BEGIN
  IF current_setting('request.jwt.claim.role', true) IS DISTINCT FROM 'service_role' THEN
    RAISE EXCEPTION 'Unauthorized';
  END IF;
  SELECT * INTO v_job FROM public.berry_ai_video_jobs
   WHERE job_id=p_job AND tenant_id=p_tenant FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'Job does not exist'; END IF;
  IF v_job.status='failed' THEN RETURN false; END IF;
  IF v_job.status NOT IN ('reserved','queued','running') THEN
    RAISE EXCEPTION 'Refund requires confirmed failure and reconciled status';
  END IF;
  PERFORM public.ai_wallet_apply_transaction(
    v_job.tenant_id,v_job.user_id,v_job.amount_myr,'refund',
    'berry-video-refund:' || v_job.job_id::text,v_job.job_id::text,
    'AI video failed after verified provider rejection'
  );
  UPDATE public.berry_ai_video_jobs
    SET status='failed',failure_reason=left(coalesce(p_reason,'confirmed failure'),160),
        updated_at=now()
    WHERE job_id=p_job AND tenant_id=p_tenant;
  RETURN true;
END; $$;

REVOKE ALL ON FUNCTION public.berry_ai_video_reserve(uuid,bigint,bigint,uuid,text,text,text,text,text,integer)
  FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.berry_ai_video_claim_submit(uuid,uuid) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.berry_ai_video_record_submit(uuid,uuid,text,text,text) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.berry_ai_video_record_render(uuid,uuid,text) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.berry_ai_video_claim_delivery(uuid,uuid) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.berry_ai_video_mark_delivered(uuid,uuid,bigint) FROM PUBLIC,anon,authenticated;
REVOKE ALL ON FUNCTION public.berry_ai_video_fail_and_refund(uuid,uuid,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.berry_ai_video_reserve(uuid,bigint,bigint,uuid,text,text,text,text,text,integer) TO service_role;
GRANT EXECUTE ON FUNCTION public.berry_ai_video_claim_submit(uuid,uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.berry_ai_video_record_submit(uuid,uuid,text,text,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.berry_ai_video_record_render(uuid,uuid,text) TO service_role;
GRANT EXECUTE ON FUNCTION public.berry_ai_video_claim_delivery(uuid,uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.berry_ai_video_mark_delivered(uuid,uuid,bigint) TO service_role;
GRANT EXECUTE ON FUNCTION public.berry_ai_video_fail_and_refund(uuid,uuid,text) TO service_role;
COMMIT;
