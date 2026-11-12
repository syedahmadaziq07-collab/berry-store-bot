-- Isolated staging only until production approval. Additive; no job/ledger state changes.
BEGIN;
ALTER TABLE berry_private.ai_video_jobs ADD COLUMN last_recovery_scan_at timestamptz;
CREATE OR REPLACE FUNCTION public.berry_video_recoverable_jobs(p_tenant uuid,p_limit int DEFAULT 20)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
DECLARE result jsonb;
BEGIN
 IF current_user NOT IN ('service_role','postgres') OR
  coalesce(current_setting('request.jwt.claims',true),'{}')::jsonb->>'role' IS DISTINCT FROM 'service_role' THEN
  RAISE EXCEPTION 'server role required' USING ERRCODE='42501'; END IF;
 IF p_tenant IS NULL OR p_limit IS NULL OR p_limit NOT BETWEEN 1 AND 20 THEN
  RAISE EXCEPTION 'invalid recovery scope'; END IF;
 -- Rotate examined candidates even if cost/identity gates hold them. Scan is not a submit claim.
 WITH candidates AS (
  SELECT tenant_id,job_id FROM berry_private.ai_video_jobs
  WHERE tenant_id=p_tenant AND state IN ('reserved','queued','succeeded')
  ORDER BY last_recovery_scan_at ASC NULLS FIRST,updated_at,job_id
  LIMIT p_limit FOR UPDATE SKIP LOCKED
 ), scanned AS (
  UPDATE berry_private.ai_video_jobs j SET last_recovery_scan_at=clock_timestamp()
  FROM candidates c WHERE j.tenant_id=c.tenant_id AND j.job_id=c.job_id
  RETURNING j.job_id,j.state,j.arguments
 ) SELECT coalesce(jsonb_agg(jsonb_build_object('job_id',job_id,'state',state,'arguments',arguments)),'[]'::jsonb)
 INTO result FROM scanned;
 RETURN result;
END $$;
REVOKE ALL ON FUNCTION public.berry_video_recoverable_jobs(uuid,int) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.berry_video_recoverable_jobs(uuid,int) TO service_role;
COMMIT;
