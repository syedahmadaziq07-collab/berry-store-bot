-- PROPOSED STAGING-ONLY migration. DO NOT auto-apply.
-- Requires operator-reviewed provider evidence before binding an ambiguous submission.
-- This changes only the existing function body, not wallets, tables, or budgets.
BEGIN;
DO $migration$
DECLARE
  original text;
  needle text := $old$ELSIF j.state='submitting' THEN
      j.state:='queued'; j.provider_request_id:=v;$old$;
  replacement text := $new$ELSIF j.state='submitting' THEN
      j.state:='queued'; j.provider_request_id:=v;
    ELSIF j.state='submission_unknown'
      AND p_payload->>'recovery_mode'='operator_verified'
      AND p_payload->>'recovery_request_hash'=j.request_hash
      AND char_length(trim(coalesce(p_payload->>'recovery_evidence',''))) BETWEEN 20 AND 500
      AND j.provider_request_id IS NULL THEN
      -- Manual operator verification required; never retry the original POST.
      j.state:='queued'; j.provider_request_id:=v;$new$;
BEGIN
  SELECT pg_get_functiondef(p.oid) INTO original
  FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
  WHERE n.nspname='public' AND p.proname='berry_video_job'
    AND pg_get_function_identity_arguments(p.oid) LIKE 'p_tenant uuid, p_job uuid, p_action text, p_payload jsonb%';
  IF original IS NULL OR length(original)-length(replace(original,needle,'')) <> length(needle)
    OR position(replacement IN original)>0 THEN
    RAISE EXCEPTION 'expected staging function contract mismatch; abort';
  END IF;
  -- Preserve all existing service-role checks, locks, budget reservations,
  -- queue URL validation, wallet rules and other state transitions.
  EXECUTE replace(original, needle, replacement);
END $migration$;
COMMIT;
