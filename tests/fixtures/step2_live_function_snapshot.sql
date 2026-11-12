-- Read-only staging function definition snapshot for EPHEMERAL POSTGRES ONLY.
CREATE OR REPLACE FUNCTION public.berry_video_job(p_tenant uuid, p_job uuid, p_action text, p_payload jsonb DEFAULT '{}'::jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
DECLARE j berry_private.ai_video_jobs%ROWTYPE; q jsonb; u bigint; d bigint; c bigint;
 h text; did_claim boolean := false; v text;
BEGIN
 IF current_user NOT IN ('service_role','postgres') OR
    coalesce(current_setting('request.jwt.claims',true),'{}')::jsonb->>'role' IS DISTINCT FROM 'service_role' THEN
  RAISE EXCEPTION 'server role required' USING ERRCODE='42501';
 END IF;
 IF p_tenant IS NULL OR p_job IS NULL OR p_action IS NULL OR p_payload IS NULL
    OR jsonb_typeof(p_payload)<>'object' THEN RAISE EXCEPTION 'invalid job request'; END IF;
 IF p_action NOT IN ('reserve','get','claim_submit','queued','submission_unknown','succeed',
   'refund_before_submit','provider_failed','claim_delivery','delivered','delivery_unknown') THEN
  RAISE EXCEPTION 'invalid job action';
 END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(
  'berry-video-job:'||p_tenant::text||':'||p_job::text,0));
 SELECT * INTO j FROM berry_private.ai_video_jobs WHERE tenant_id=p_tenant AND job_id=p_job FOR UPDATE;
 IF p_action='reserve' THEN
  u := (p_payload->>'user_id')::bigint; q := p_payload->'quote';
  h := p_payload->>'request_hash'; d := (q->>'debit_cents')::bigint; c := (q->>'all_in_cost_cents')::bigint;
  IF u IS NULL OR u<=0 OR q IS NULL OR jsonb_typeof(q)<>'object'
   OR jsonb_typeof(p_payload->'arguments') IS DISTINCT FROM 'object'
   OR pg_column_size(p_payload->'arguments')>65536
   OR h IS NULL OR h !~ '^[0-9a-f]{64}$' OR d IS NULL OR c IS NULL
   OR c<0 OR d<=0 OR d>999999999999 OR d%2<>0 OR d-c<100
   OR (q->>'credits')::bigint IS DISTINCT FROM d*1250/100
   OR q->>'tool_key' IS NULL OR q->>'tool_key'<>'video'
   OR q->>'provider_model_id' IS NULL OR char_length(q->>'provider_model_id') NOT BETWEEN 3 AND 256
   OR q->>'cost_reference' IS NULL OR char_length(trim(q->>'cost_reference')) NOT BETWEEN 1 AND 200
   OR (q->>'mapping_revision')::bigint IS NULL OR (q->>'mapping_revision')::bigint<=0
   THEN RAISE EXCEPTION 'invalid quote or minimum margin'; END IF;
  IF j.job_id IS NOT NULL THEN
   IF j.user_id<>u OR j.request_hash<>h OR j.quote<>q OR j.arguments<>p_payload->'arguments' THEN RAISE EXCEPTION 'idempotency conflict'; END IF;
  ELSE
   PERFORM public.ai_wallet_apply_transaction(p_tenant,u,-(d::numeric/100),'debit',
    'video:debit:'||p_job::text,p_job::text,'AI Video reservation');
   INSERT INTO berry_private.ai_video_jobs(tenant_id,job_id,user_id,request_hash,arguments,quote,debit_cents,state)
    VALUES(p_tenant,p_job,u,h,p_payload->'arguments',q,d,'reserved') RETURNING * INTO j;
   INSERT INTO berry_private.ai_video_job_events(tenant_id,job_id,action,state)
    VALUES(p_tenant,p_job,'reserve','reserved');
  END IF;
 ELSE
  IF j.job_id IS NULL THEN RAISE EXCEPTION 'unknown job'; END IF;
  CASE p_action
   WHEN 'get' THEN NULL;
   WHEN 'claim_submit' THEN
    IF j.state='reserved' THEN
     -- Reserve worst-case ALL-IN MYR cost before outbound POST. Unknown outcomes keep it consumed.
     IF (j.quote->>'all_in_cost_cents')::bigint<=0 THEN RAISE EXCEPTION 'positive verified cost bound required'; END IF;
     UPDATE berry_private.ai_video_test_budgets
      SET reserved_cost_cents=reserved_cost_cents+(j.quote->>'all_in_cost_cents')::bigint,
          reserved_generations=reserved_generations+1
      WHERE tenant_id=p_tenant AND budget_id=(p_payload->>'budget_id')::uuid
       AND test_user_id=j.user_id AND expires_at>now()
       AND reserved_generations<max_generations
       AND reserved_cost_cents+(j.quote->>'all_in_cost_cents')::bigint<=max_cost_cents;
     IF NOT FOUND THEN RAISE EXCEPTION 'approved test budget unavailable or exhausted'; END IF;
     j.budget_id:=(p_payload->>'budget_id')::uuid;
     j.budget_reserved_cents:=(j.quote->>'all_in_cost_cents')::bigint;
     j.submission_tags:=jsonb_build_object('berry_job',p_job::text,'berry_hash',j.request_hash,'berry_tenant',p_tenant::text);
     j.state:='submitting'; did_claim:=true;
    END IF;
   WHEN 'queued' THEN
    v:=p_payload->>'provider_request_id';
    IF v IS NULL OR char_length(v) NOT BETWEEN 1 AND 256 OR v !~ '^[A-Za-z0-9_-]+$' THEN RAISE EXCEPTION 'invalid provider request'; END IF;
    IF p_payload->>'queue_status_url' IS NULL OR p_payload->>'queue_result_url' IS NULL
      OR p_payload->>'queue_status_url' !~ '^https://queue[.]fal[.]run/[A-Za-z0-9_./-]+$'
      OR p_payload->>'queue_result_url' !~ '^https://queue[.]fal[.]run/[A-Za-z0-9_./-]+$'
      OR p_payload->>'queue_result_url'<>'https://queue.fal.run/'||split_part(j.quote->>'provider_model_id','/',1)||'/'||split_part(j.quote->>'provider_model_id','/',2)||'/requests/'||v
      OR p_payload->>'queue_status_url'<>(p_payload->>'queue_result_url')||'/status'
      THEN RAISE EXCEPTION 'invalid queue recovery URLs'; END IF;
    IF j.state IN ('queued','succeeded','delivering','delivery_unknown','delivered') AND j.provider_request_id=v
      AND j.queue_status_url=p_payload->>'queue_status_url' AND j.queue_result_url=p_payload->>'queue_result_url' THEN NULL;
    ELSIF j.state='submitting' THEN
      j.state:='queued'; j.provider_request_id:=v;
      j.queue_status_url:=p_payload->>'queue_status_url'; j.queue_result_url:=p_payload->>'queue_result_url';
    ELSE RAISE EXCEPTION 'invalid queued transition'; END IF;
   WHEN 'submission_unknown' THEN
    IF j.state='submitting' THEN j.state:='submission_unknown';
    ELSIF j.state<>'submission_unknown' THEN RAISE EXCEPTION 'invalid unknown submission transition'; END IF;
   WHEN 'succeed' THEN
    v:=p_payload->>'result_url';
    IF v IS NULL OR v !~ '^https://[A-Za-z0-9]' OR char_length(v)>4096 THEN RAISE EXCEPTION 'invalid result URL'; END IF;
    IF p_payload->>'provider_request_id' IS DISTINCT FROM j.provider_request_id
      OR j.provider_request_id IS NULL THEN RAISE EXCEPTION 'provider request mismatch'; END IF;
    IF j.state IN ('succeeded','delivering','delivery_unknown','delivered') AND j.result_url=v THEN NULL;
    ELSIF j.state='queued' THEN j.state:='succeeded'; j.result_url:=v;
    ELSE RAISE EXCEPTION 'invalid success transition'; END IF;
   WHEN 'refund_before_submit','provider_failed' THEN
    IF j.state='refunded' THEN
     IF p_action='provider_failed' AND p_payload->>'provider_request_id' IS DISTINCT FROM j.provider_request_id THEN
      RAISE EXCEPTION 'provider request mismatch'; END IF;
    ELSIF (p_action='refund_before_submit' AND j.state='reserved')
       OR (p_action='provider_failed' AND j.state='queued'
           AND p_payload->>'provider_request_id'=j.provider_request_id
           AND char_length(trim(coalesce(p_payload->>'failure_evidence',''))) BETWEEN 1 AND 500) THEN
     PERFORM public.ai_wallet_apply_transaction(p_tenant,j.user_id,j.debit_cents::numeric/100,'refund',
      'video:refund:'||p_job::text,p_job::text,'AI Video definitive refund');
     j.state:='refunded';
    ELSE RAISE EXCEPTION 'refund forbidden for ambiguous or completed job'; END IF;
   WHEN 'claim_delivery' THEN
    IF j.state='succeeded' THEN j.state:='delivering'; did_claim:=true; END IF;
   WHEN 'delivered' THEN
    v:=p_payload->>'delivery_id';
    IF v IS NULL OR v !~ '^[0-9]{1,30}$' THEN RAISE EXCEPTION 'invalid delivery id'; END IF;
    IF j.state='delivered' AND j.delivery_id=v THEN NULL;
    ELSIF j.state='delivering' THEN j.state:='delivered'; j.delivery_id:=v;
    ELSE RAISE EXCEPTION 'invalid delivered transition'; END IF;
   WHEN 'delivery_unknown' THEN
    IF j.state='delivering' THEN j.state:='delivery_unknown';
    ELSIF j.state<>'delivery_unknown' THEN RAISE EXCEPTION 'invalid delivery unknown transition'; END IF;
   ELSE RAISE EXCEPTION 'unsupported action';
  END CASE;
  IF p_action<>'get' AND (p_action NOT IN ('claim_submit','claim_delivery') OR did_claim) THEN
   UPDATE berry_private.ai_video_jobs SET state=j.state,submission_tags=j.submission_tags,budget_id=j.budget_id,budget_reserved_cents=j.budget_reserved_cents,provider_request_id=j.provider_request_id,
   queue_status_url=j.queue_status_url,queue_result_url=j.queue_result_url,
   result_url=j.result_url,delivery_id=j.delivery_id,updated_at=now()
   WHERE tenant_id=p_tenant AND job_id=p_job;
   INSERT INTO berry_private.ai_video_job_events(tenant_id,job_id,action,state,evidence)
    VALUES(p_tenant,p_job,p_action,j.state,jsonb_strip_nulls(jsonb_build_object(
     'provider_request_id',j.provider_request_id,'delivery_id',j.delivery_id,
     'submission_tags',j.submission_tags,'budget_id',j.budget_id,'budget_reserved_cents',j.budget_reserved_cents,
     'failure_evidence',p_payload->>'failure_evidence')));
  END IF;
 END IF;
 RETURN jsonb_build_object('job_id',j.job_id,'user_id',j.user_id,'state',j.state,'quote',j.quote,
  'arguments',j.arguments,'request_hash',j.request_hash,'provider_request_id',j.provider_request_id,
  'queue_status_url',j.queue_status_url,'queue_result_url',j.queue_result_url,
  'submission_tags',j.submission_tags,'budget_id',j.budget_id,'budget_reserved_cents',j.budget_reserved_cents,'result_url',j.result_url,'delivery_id',j.delivery_id,'claimed',did_claim);
END $function$

