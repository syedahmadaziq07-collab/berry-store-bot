-- Proposed rollback for the staging-only recovery transition; DO NOT auto-apply.
BEGIN;
DO $rollback$
DECLARE
  original text;
  needle text := $new$ELSIF j.state='submitting' THEN
      j.state:='queued'; j.provider_request_id:=v;
    ELSIF j.state='submission_unknown'
      AND p_payload->>'recovery_mode'='operator_verified'
      AND p_payload->>'recovery_request_hash'=j.request_hash
      AND char_length(trim(coalesce(p_payload->>'recovery_evidence',''))) BETWEEN 20 AND 500
      AND j.provider_request_id IS NULL THEN
      -- Manual operator verification required; never retry the original POST.
      j.state:='queued'; j.provider_request_id:=v;$new$;
  replacement text := $old$ELSIF j.state='submitting' THEN
      j.state:='queued'; j.provider_request_id:=v;$old$;
BEGIN
  SELECT pg_get_functiondef(p.oid) INTO original
  FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
  WHERE n.nspname='public' AND p.proname='berry_video_job';
  IF original IS NULL OR length(original)-length(replace(original,needle,'')) <> length(needle) THEN
    RAISE EXCEPTION 'expected migration fingerprint missing; abort rollback';
  END IF;
  EXECUTE replace(original,needle,replacement);
END $rollback$;
COMMIT;
