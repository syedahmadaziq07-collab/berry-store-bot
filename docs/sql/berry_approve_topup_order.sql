-- REVIEW ONLY. DO NOT APPLY TO PRODUCTION UNTIL STAGING TESTS PASS.
-- Atomic Berry Credits top-up approval. Existing wallet stores MYR, not credits.
-- One order row is locked; wallet transaction and order completion share a DB transaction.
create or replace function public.berry_approve_topup_order(
  p_tenant_id uuid, p_order_id text, p_admin_id bigint
) returns jsonb
language plpgsql security definer set search_path = ''
as $$
declare
  o public.orders%rowtype;
  plan text;
  expected numeric(12,2);
  credit_count integer;
  tx record;
  already boolean := false;
begin
  if current_user <> 'service_role' then
    raise exception 'Unauthorized';
  end if;
  if p_tenant_id is null or p_admin_id is null or p_admin_id <= 0
     or p_order_id !~ '^BT[0-9A-F]{24}$' then
    raise exception 'Invalid request';
  end if;
  select * into o from public.orders
   where id = p_order_id and tenant_id = p_tenant_id
   for update;
  if not found then raise exception 'Order not found'; end if;
  if o.product_id is not null or o.quantity <> 1 or o.user_id is null or o.user_id <= 0 then
    raise exception 'Invalid top-up order';
  end if;
  plan := replace(o.product_name, 'Berry Credits Top Up: ', '');
  if o.product_name <> 'Berry Credits Top Up: ' || plan then
    raise exception 'Invalid top-up product';
  end if;
  case plan
    when 'starter' then expected := 5; credit_count := 6250;
    when 'creator' then expected := 10; credit_count := 12500;
    when 'pro' then expected := 20; credit_count := 25000;
    when 'studio' then expected := 50; credit_count := 62500;
    else raise exception 'Invalid plan';
  end case;
  if o.amount is distinct from expected then raise exception 'Invalid price'; end if;
  if o.status = 'completed' then
    already := true;
    if not exists (
      select 1 from public.ai_wallet_transactions t
      where t.tenant_id=p_tenant_id and t.user_id=o.user_id
        and t.idempotency_key='berry-topup:'||o.id and t.kind='topup'
        and t.amount=expected and t.reference=o.id
    ) then
      raise exception 'Completed order missing wallet transaction';
    end if;
  elsif o.status = 'waiting_approval' and o.receipt_file_id is not null then
    -- The wallet RPC is idempotent and runs in the SAME transaction.
    select * into tx from public.ai_wallet_apply_transaction(
      p_tenant_id, o.user_id, expected, 'topup', 'berry-topup:'||o.id,
      o.id, 'Berry Credits plan: '||plan||' ('||credit_count||' credits)'
    );
    update public.orders set status='completed', approved_by=p_admin_id,
      updated_at=now() where id=o.id and tenant_id=p_tenant_id
        and status='waiting_approval';
    if not found then raise exception 'Concurrent order state change'; end if;
  else
    raise exception 'Order not awaiting receipt approval';
  end if;
  return jsonb_build_object('order_id',o.id,'user_id',o.user_id,
    'amount',expected,'credits',credit_count,'already_completed',already);
end; $$;
revoke all on function public.berry_approve_topup_order(uuid,text,bigint) from public, anon, authenticated;
grant execute on function public.berry_approve_topup_order(uuid,text,bigint) to service_role;
