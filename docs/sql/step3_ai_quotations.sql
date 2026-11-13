-- STEP 3 additive migration: server-only durable AI quotations.
-- Apply only to the verified production Supabase project after PR review.
-- No wallet, order, product or tenant rows are modified.
create table if not exists public.ai_quotations (
  quote_id text primary key,
  tenant_id uuid not null,
  customer_id bigint not null check (customer_id > 0),
  idempotency_key text,
  document jsonb not null,
  integrity text not null check (integrity ~ '^[0-9a-f]{64}$'),
  state text not null default 'active' check (state in ('active','cancelled')),
  expires_at_epoch bigint not null,
  created_at timestamptz not null default now(),
  constraint ai_quotations_doc_integrity check (document->>'integrity' = integrity),
  constraint ai_quotations_doc_identity check (
    document->>'quote_id' = quote_id and
    document->>'tenant_id' = tenant_id::text and
    (document->>'customer_id')::bigint = customer_id
  ),
  constraint ai_quotations_quote_id_safe check (quote_id ~ '^[A-Za-z0-9_-]{8,128}$')
);
create unique index if not exists ai_quotations_idempotency_key_unique
  on public.ai_quotations (tenant_id, customer_id, idempotency_key)
  where idempotency_key is not null;
create index if not exists ai_quotations_expiry_idx
  on public.ai_quotations (expires_at_epoch);
alter table public.ai_quotations enable row level security;
revoke all on public.ai_quotations from public, anon, authenticated;
grant select, insert, update on public.ai_quotations to service_role;
-- Deliberately no anon/authenticated policy; service-role server only.
-- Rollback (ONLY if verified table is empty and after owner approval):
-- drop table public.ai_quotations;
