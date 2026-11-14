-- Berry Store anonymous support sessions: service-role only, no message content.
create table if not exists public.berry_support_sessions (
  tenant_id uuid not null,
  user_id bigint not null check (user_id > 0),
  status text not null default 'open' check (status in ('open','closed')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  closed_at timestamptz,
  primary key (tenant_id, user_id)
);
alter table public.berry_support_sessions enable row level security;
revoke all on public.berry_support_sessions from public, anon, authenticated;
grant select, insert, update on public.berry_support_sessions to service_role;
-- No policies for anon/authenticated. Only bot backend's service role may access.
