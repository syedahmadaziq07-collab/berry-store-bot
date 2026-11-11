-- ISOLATED STAGING ONLY. Separate synthetic MYR wallets; no customer tables.
CREATE TABLE berry_private.staging_job_wallets (
 tenant_id uuid NOT NULL, user_id bigint NOT NULL CHECK(user_id>0),
 balance_cents bigint NOT NULL CHECK(balance_cents BETWEEN 0 AND 999999999999),
 PRIMARY KEY(tenant_id,user_id)
);
CREATE TABLE berry_private.staging_ai_jobs (
 tenant_id uuid NOT NULL, job_id uuid NOT NULL, user_id bigint NOT NULL,
 request_hash text NOT NULL CHECK(request_hash ~ '^[0-9a-f]{64}$'),
 quote jsonb NOT NULL CHECK(jsonb_typeof(quote)='object'),
 debit_cents bigint NOT NULL CHECK(debit_cents>0),
 state text NOT NULL CHECK(state IN ('reserved','submitting','submission_unknown','queued',
  'succeeded','delivering','delivery_unknown','delivered','refunded')),
 provider_request_id text, queue_status_url text, queue_result_url text, result_url text, delivery_id text,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant_id,job_id),
 FOREIGN KEY(tenant_id,user_id) REFERENCES berry_private.staging_job_wallets(tenant_id,user_id)
);
CREATE TABLE berry_private.staging_job_ledger (
 tenant_id uuid NOT NULL, job_id uuid NOT NULL, kind text NOT NULL CHECK(kind IN ('debit','refund')),
 amount_cents bigint NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(tenant_id,job_id,kind),
 FOREIGN KEY(tenant_id,job_id) REFERENCES berry_private.staging_ai_jobs(tenant_id,job_id),
 CHECK((kind='debit' AND amount_cents<0) OR (kind='refund' AND amount_cents>0))
);
CREATE INDEX staging_ai_jobs_recovery_idx ON berry_private.staging_ai_jobs(tenant_id,state,updated_at);
CREATE UNIQUE INDEX staging_ai_jobs_provider_request_idx ON berry_private.staging_ai_jobs(tenant_id,provider_request_id)
 WHERE provider_request_id IS NOT NULL;
ALTER TABLE berry_private.staging_job_wallets ENABLE ROW LEVEL SECURITY;
ALTER TABLE berry_private.staging_ai_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE berry_private.staging_job_ledger ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON berry_private.staging_job_wallets,berry_private.staging_ai_jobs,berry_private.staging_job_ledger FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON berry_private.staging_job_wallets,berry_private.staging_ai_jobs TO service_role;
GRANT SELECT,INSERT ON berry_private.staging_job_ledger TO service_role;

-- All writes below share one DB transaction. Role is the trusted staging worker.
-- No function here authorizes paid inference or verifies provider invoice costs.
CREATE FUNCTION public.berry_staging_job(
 p_tenant uuid,p_job uuid,p_action text,p_payload jsonb DEFAULT '{}'::jsonb
) RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE j berry_private.staging_ai_jobs%ROWTYPE; q jsonb; u bigint; d bigint; c bigint;
 h text; did_claim boolean := false; v text;
BEGIN
 IF current_user NOT IN ('service_role','postgres') THEN
  RAISE EXCEPTION 'server role required' USING ERRCODE='42501';
 END IF;
 IF p_tenant IS NULL OR p_job IS NULL OR p_action IS NULL OR p_payload IS NULL
    OR jsonb_typeof(p_payload)<>'object' THEN RAISE EXCEPTION 'invalid job request'; END IF;
 IF p_action NOT IN ('reserve','get','claim_submit','queued','submission_unknown','succeed',
   'refund_before_submit','provider_failed','claim_delivery','delivered','delivery_unknown') THEN
  RAISE EXCEPTION 'invalid job action';
 END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(
  'berry-staging-job:'||p_tenant::text||':'||p_job::text,0));
 SELECT * INTO j FROM berry_private.staging_ai_jobs WHERE tenant_id=p_tenant AND job_id=p_job FOR UPDATE;
 IF p_action='reserve' THEN
  u := (p_payload->>'user_id')::bigint; q := p_payload->'quote';
  h := p_payload->>'request_hash'; d := (q->>'debit_cents')::bigint; c := (q->>'all_in_cost_cents')::bigint;
  IF u IS NULL OR u<=0 OR q IS NULL OR jsonb_typeof(q)<>'object'
   OR h IS NULL OR h !~ '^[0-9a-f]{64}$' OR d IS NULL OR c IS NULL
   OR c<0 OR d<=0 OR d>999999999999 OR d%2<>0 OR d-c<100
   OR (q->>'credits')::bigint IS DISTINCT FROM d*1250/100
   OR q->>'tool_key' IS NULL OR q->>'tool_key' NOT IN ('image','video')
   OR q->>'provider_model_id' IS NULL OR char_length(q->>'provider_model_id') NOT BETWEEN 3 AND 256
   OR q->>'cost_reference' IS NULL OR char_length(trim(q->>'cost_reference')) NOT BETWEEN 1 AND 200
   OR (q->>'mapping_revision')::bigint IS NULL OR (q->>'mapping_revision')::bigint<=0
   THEN RAISE EXCEPTION 'invalid quote or minimum margin'; END IF;
  IF j.job_id IS NOT NULL THEN
   IF j.user_id<>u OR j.request_hash<>h OR j.quote<>q THEN RAISE EXCEPTION 'idempotency conflict'; END IF;
  ELSE
   UPDATE berry_private.staging_job_wallets SET balance_cents=balance_cents-d
    WHERE tenant_id=p_tenant AND user_id=u AND balance_cents>=d;
   IF NOT FOUND THEN RAISE EXCEPTION 'insufficient balance'; END IF;
   INSERT INTO berry_private.staging_ai_jobs(tenant_id,job_id,user_id,request_hash,quote,debit_cents,state)
    VALUES(p_tenant,p_job,u,h,q,d,'reserved') RETURNING * INTO j;
   INSERT INTO berry_private.staging_job_ledger(tenant_id,job_id,kind,amount_cents)
    VALUES(p_tenant,p_job,'debit',-d);
  END IF;
 ELSE
  IF j.job_id IS NULL THEN RAISE EXCEPTION 'unknown job'; END IF;
  CASE p_action
   WHEN 'get' THEN NULL;
   WHEN 'claim_submit' THEN
    IF j.state='reserved' THEN j.state:='submitting'; did_claim:=true; END IF;
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
    IF j.state='refunded' THEN NULL;
    ELSIF (p_action='refund_before_submit' AND j.state='reserved')
       OR (p_action='provider_failed' AND j.state='queued'
           AND p_payload->>'provider_request_id'=j.provider_request_id) THEN
     UPDATE berry_private.staging_job_wallets SET balance_cents=balance_cents+j.debit_cents
      WHERE tenant_id=p_tenant AND user_id=j.user_id;
     IF NOT FOUND THEN RAISE EXCEPTION 'wallet missing'; END IF;
     INSERT INTO berry_private.staging_job_ledger(tenant_id,job_id,kind,amount_cents)
      VALUES(p_tenant,p_job,'refund',j.debit_cents);
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
   UPDATE berry_private.staging_ai_jobs SET state=j.state,provider_request_id=j.provider_request_id,
   queue_status_url=j.queue_status_url,queue_result_url=j.queue_result_url,
   result_url=j.result_url,delivery_id=j.delivery_id,updated_at=now()
   WHERE tenant_id=p_tenant AND job_id=p_job;
  END IF;
 END IF;
 RETURN jsonb_build_object('job_id',j.job_id,'user_id',j.user_id,'state',j.state,'quote',j.quote,
  'request_hash',j.request_hash,'provider_request_id',j.provider_request_id,
  'queue_status_url',j.queue_status_url,'queue_result_url',j.queue_result_url,
  'result_url',j.result_url,'delivery_id',j.delivery_id,'claimed',did_claim);
END $$;
REVOKE ALL ON FUNCTION public.berry_staging_job(uuid,uuid,text,jsonb) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.berry_staging_job(uuid,uuid,text,jsonb) TO service_role;
