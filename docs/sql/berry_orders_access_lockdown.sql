-- DEPLOY ONLY AFTER STAGING TESTS AND BOT SERVICE-ROLE MIGRATION.
-- The legacy orders RLS policy allows anon to update payment statuses.
-- The bot now uses its server-side SUPABASE_SERVICE_KEY for all orders REST operations.
begin;
drop policy if exists allow_all on public.orders;
revoke all privileges on table public.orders from anon, authenticated, public;
grant select, insert, update, delete on table public.orders to service_role;
alter table public.orders enable row level security;
commit;
