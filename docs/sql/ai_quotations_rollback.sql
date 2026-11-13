-- Rollback for ai_quotations.sql (additive-only migration; safe: no
-- existing business tables or rows are touched; quotation records lost).
BEGIN;
DROP FUNCTION IF EXISTS public.berry_ai_quote_rate(uuid,bigint,int);
DROP FUNCTION IF EXISTS public.berry_ai_quote_cancel(uuid,bigint,uuid);
DROP FUNCTION IF EXISTS public.berry_ai_quote_get(uuid,bigint,uuid);
DROP FUNCTION IF EXISTS
 public.berry_ai_quote_create(uuid,bigint,uuid,text,int,jsonb,text,text,timestamptz);
DROP TABLE IF EXISTS berry_private.ai_quotations;
COMMIT;
