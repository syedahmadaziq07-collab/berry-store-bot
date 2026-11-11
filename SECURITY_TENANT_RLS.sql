-- Applied to active Supabase Berry Store database on 2026-11-11.
-- Security hardening, not a new feature.
-- IMPORTANT: This changes privileges for ALL tenants in the shared Supabase project.
-- Review with any other connected storefronts before re-running or extending this policy.
BEGIN;
ALTER TABLE public.tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.rental_payments ENABLE ROW LEVEL SECURITY;

-- Neither public role can read private tenancy records or modify rental state.
REVOKE ALL PRIVILEGES ON TABLE public.tenants, public.rental_payments
  FROM PUBLIC, anon, authenticated;

-- Compatibility only: the existing Berry Store bot uses the anon Supabase key
-- for these five, nonsecret fields during tenant validation.
GRANT SELECT (id, status, rent_end, name, bot_username)
  ON TABLE public.tenants TO anon, authenticated;

CREATE POLICY tenant_public_status_read
ON public.tenants FOR SELECT
TO anon, authenticated
USING (true);

-- No policies for rental_payments; service_role retains privileged access.
COMMIT;

-- SECURITY FOLLOW-UP
-- Change bot.py tenant-status reads to server-side service role and confirm
-- SUPABASE_SERVICE_KEY exists on all deployed bots. Then remove the public
-- read policy and the five public column-level grants completely.
