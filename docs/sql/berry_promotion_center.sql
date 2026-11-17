-- Berry Store Promotion Center (server-only; never expose service keys in JS).
-- Apply once to the Berry Store production Supabase project before deploying UI.
CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.promotion_destinations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id),
  name text NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
  kind text NOT NULL CHECK (kind IN ('telegram_group','telegram_channel','google_form')),
  target_url text NOT NULL CHECK (length(target_url) BETWEEN 10 AND 2048),
  telegram_chat_id text,
  form_email text,
  form_message_entry text,
  form_email_entry text,
  form_fixed_fields jsonb NOT NULL DEFAULT '{}'::jsonb,
  posting_permitted boolean NOT NULL DEFAULT false,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS promotion_destinations_tenant_idx ON public.promotion_destinations(tenant_id, active, created_at);

CREATE TABLE IF NOT EXISTS public.promotion_threads_accounts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id),
  provider_user_id text NOT NULL,
  username text NOT NULL,
  encrypted_token text NOT NULL,
  active boolean NOT NULL DEFAULT true,
  expires_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id,provider_user_id)
);

CREATE TABLE IF NOT EXISTS public.promotion_templates (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id),
  name text NOT NULL CHECK (length(name) BETWEEN 1 AND 120),
  message text NOT NULL CHECK (length(message) BETWEEN 1 AND 1800),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.promotion_campaigns (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id),
  title text NOT NULL CHECK (length(title) BETWEEN 1 AND 120),
  message text NOT NULL CHECK (length(message) BETWEEN 1 AND 1800),
  scheduled_for timestamptz NOT NULL DEFAULT now(),
  state text NOT NULL DEFAULT 'queued'
    CHECK (state IN ('queued','running','completed','cancelled')),
  created_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz
);
CREATE INDEX IF NOT EXISTS promotion_campaigns_due_idx ON public.promotion_campaigns(tenant_id,state,scheduled_for);

CREATE TABLE IF NOT EXISTS public.promotion_deliveries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES public.tenants(id),
  campaign_id uuid NOT NULL REFERENCES public.promotion_campaigns(id),
  destination_id uuid REFERENCES public.promotion_destinations(id),
  threads_account_id uuid REFERENCES public.promotion_threads_accounts(id),
  state text NOT NULL DEFAULT 'queued'
    CHECK (state IN ('queued','processing','sent','manual','failed','unknown','skipped')),
  attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count BETWEEN 0 AND 5),
  message_override text CHECK (message_override IS NULL OR length(message_override) BETWEEN 1 AND 500),
  external_id text,
  error_message text,
  sent_at timestamptz,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (num_nonnulls(destination_id,threads_account_id) = 1),
  UNIQUE(campaign_id,destination_id),
  UNIQUE(campaign_id,threads_account_id)
);
CREATE INDEX IF NOT EXISTS promotion_deliveries_campaign_idx ON public.promotion_deliveries(tenant_id,campaign_id,state);

-- Strictly backend-only. The service role is used after the dashboard secret
-- is checked and the tenant is always injected by the server.
ALTER TABLE public.promotion_destinations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.promotion_threads_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.promotion_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.promotion_campaigns ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.promotion_deliveries ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.promotion_destinations, public.promotion_threads_accounts,
  public.promotion_templates, public.promotion_campaigns, public.promotion_deliveries
  FROM PUBLIC, anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.promotion_destinations,
  public.promotion_threads_accounts, public.promotion_templates,
  public.promotion_campaigns, public.promotion_deliveries TO service_role;

-- Verify no RLS policies grant public access:
-- SELECT tablename, policyname FROM pg_policies WHERE tablename LIKE 'promotion_%';
