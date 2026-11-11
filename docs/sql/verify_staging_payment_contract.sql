-- Isolated staging ONLY. Actual existing MYR wallet/top-up RPCs; dummy orders.
BEGIN;
SELECT set_config('request.jwt.claims','{"role":"service_role"}',true);
DO $$
DECLARE t uuid:=gen_random_uuid(); k uuid:=gen_random_uuid(); k2 uuid:=gen_random_uuid();
 r jsonb; r2 jsonb; oid text; b numeric; n bigint; rejected boolean;
BEGIN
 INSERT INTO public.tenants(id) VALUES(t);
 r:=public.berry_create_topup_order(t,900000004,'starter',k,'BT'||upper(substr(replace(gen_random_uuid()::text,'-',''),1,24)),'fixture');
 oid:=r->'order'->>'id';
 r2:=public.berry_create_topup_order(t,900000004,'starter',k,'BT'||upper(substr(replace(gen_random_uuid()::text,'-',''),1,24)),'fixture');
 IF r2->'order'->>'id'<>oid OR r2->>'replayed'<>'true' THEN RAISE EXCEPTION 'checkout replay mismatch'; END IF;
 r2:=public.berry_create_topup_order(t,900000004,'creator',k2,'BT'||upper(substr(replace(gen_random_uuid()::text,'-',''),1,24)),'fixture');
 IF r2->'order'->>'id'<>oid OR r2->>'created'<>'false' THEN RAISE EXCEPTION 'multiple active orders'; END IF;
 rejected:=false;
 BEGIN PERFORM public.berry_create_topup_order(t,900000005,'starter',k,'BT'||upper(substr(replace(gen_random_uuid()::text,'-',''),1,24)),'other');
 EXCEPTION WHEN raise_exception THEN IF SQLERRM='checkout idempotency conflict' THEN rejected:=true; ELSE RAISE; END IF; END;
 IF NOT rejected THEN RAISE EXCEPTION 'checkout ownership conflict accepted'; END IF;
 -- Receipt presence alone never bypasses the explicit approval operation.
 rejected:=false;
 BEGIN PERFORM public.berry_approve_topup_order(t,oid,900000099);
 EXCEPTION WHEN raise_exception THEN IF SQLERRM='Order not awaiting receipt approval' THEN rejected:=true; ELSE RAISE; END IF; END;
 IF NOT rejected THEN RAISE EXCEPTION 'unpaid order credited'; END IF;
 UPDATE public.orders SET status='waiting_approval',receipt_file_id='fixture:receipt-only' WHERE tenant_id=t AND id=oid;
 -- Unauthorized claim cannot approve even when it has an otherwise valid order ID.
 PERFORM set_config('request.jwt.claims','{"role":"anon"}',true);
 rejected:=false;
 BEGIN PERFORM public.berry_approve_topup_order(t,oid,900000099);
 EXCEPTION WHEN raise_exception THEN IF SQLERRM='Unauthorized' THEN rejected:=true; ELSE RAISE; END IF; END;
 IF NOT rejected THEN RAISE EXCEPTION 'unauthorized approval'; END IF;
 PERFORM set_config('request.jwt.claims','{"role":"service_role"}',true);
 PERFORM public.berry_approve_topup_order(t,oid,900000099);
 r:=public.berry_approve_topup_order(t,oid,900000099);
 IF r->>'already_completed'<>'true' THEN RAISE EXCEPTION 'duplicate approval not recognized'; END IF;
 SELECT balance INTO b FROM public.ai_wallets WHERE tenant_id=t AND user_id=900000004;
 SELECT count(*) INTO n FROM public.ai_wallet_transactions WHERE tenant_id=t;
 IF b<>5 OR n<>1 THEN RAISE EXCEPTION 'duplicate topup credit'; END IF;
 -- Closed callback replay must return the completed original order, not create a new QR checkout.
 r:=public.berry_create_topup_order(t,900000004,'starter',k,'BT'||upper(substr(replace(gen_random_uuid()::text,'-',''),1,24)),'fixture');
 IF r->'order'->>'id'<>oid OR r->'order'->>'status'<>'completed' THEN RAISE EXCEPTION 'closed order replay reopened'; END IF;
 PERFORM public.ai_wallet_apply_transaction(t,900000004,-1.06,'debit','fixture:debit','fixture:job-1');
 PERFORM public.ai_wallet_apply_transaction(t,900000004,-1.06,'debit','fixture:debit','fixture:job-1');
 SELECT balance INTO b FROM public.ai_wallets WHERE tenant_id=t AND user_id=900000004;
 IF b<>3.94 THEN RAISE EXCEPTION 'MYR debit replay charged twice'; END IF;
 rejected:=false;
 BEGIN PERFORM public.ai_wallet_apply_transaction(t,900000004,-1.06,'debit','fixture:debit','fixture:other-job');
 EXCEPTION WHEN raise_exception THEN IF SQLERRM='Idempotency key already used for a different operation' THEN rejected:=true; ELSE RAISE; END IF; END;
 IF NOT rejected THEN RAISE EXCEPTION 'ledger reference conflict accepted'; END IF;
 rejected:=false;
 BEGIN PERFORM public.ai_wallet_apply_transaction(t,900000004,-1.0504,'debit','fixture:subcent','fixture:job-2');
 EXCEPTION WHEN raise_exception THEN IF SQLERRM='Invalid MYR amount' THEN rejected:=true; ELSE RAISE; END IF; END;
 IF NOT rejected THEN RAISE EXCEPTION 'subcent debit accepted'; END IF;
 rejected:=false;
 BEGIN PERFORM public.ai_wallet_apply_transaction(t,900000004,-999,'debit','fixture:overspend','fixture:job-3');
 EXCEPTION WHEN raise_exception THEN IF SQLERRM='Insufficient wallet balance' THEN rejected:=true; ELSE RAISE; END IF; END;
 IF NOT rejected THEN RAISE EXCEPTION 'MYR overspend accepted'; END IF;
 PERFORM public.ai_wallet_apply_transaction(t,900000004,1.06,'refund','fixture:refund','fixture:job-1');
 PERFORM public.ai_wallet_apply_transaction(t,900000004,1.06,'refund','fixture:refund','fixture:job-1');
 SELECT balance INTO b FROM public.ai_wallets WHERE tenant_id=t AND user_id=900000004;
 SELECT count(*) INTO n FROM public.ai_wallet_transactions WHERE tenant_id=t;
 IF b<>5 OR n<>3 THEN RAISE EXCEPTION 'MYR refund replay or ledger mismatch'; END IF;
 IF b<>(SELECT sum(amount) FROM public.ai_wallet_transactions WHERE tenant_id=t) THEN RAISE EXCEPTION 'MYR reconciliation failed'; END IF;
 IF has_function_privilege('anon','public.berry_create_topup_order(uuid,bigint,text,uuid,text,text)','EXECUTE')
 OR has_function_privilege('authenticated','public.berry_approve_topup_order(uuid,text,bigint)','EXECUTE') THEN
  RAISE EXCEPTION 'public payment execution allowed'; END IF;
END $$;
SELECT 'PASS: atomic checkout, stable replay, ownership, receipt/approval gate, unauthorized denial, credit-once, closed replay, MYR debit/refund, reference conflict, cent precision, overspend, reconciliation' AS evidence;
ROLLBACK;
