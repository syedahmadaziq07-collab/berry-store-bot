BEGIN;
DO $$ DECLARE a uuid:=gen_random_uuid(); b uuid:=gen_random_uuid(); p integer; v integer; rejected boolean; BEGIN
 INSERT INTO public.tenants(id) VALUES(a),(b);
 INSERT INTO public.products(tenant_id,name,price) VALUES(a,'Tenant fixture',1) RETURNING id INTO p;
 INSERT INTO public.product_variants(tenant_id,product_id,variant_name,price) VALUES(a,p,'Fixture',1) RETURNING id INTO v;
 rejected:=false;
 BEGIN INSERT INTO public.product_variants(tenant_id,product_id,variant_name,price) VALUES(b,p,'Cross tenant',1);
 EXCEPTION WHEN foreign_key_violation THEN rejected:=true; END;
 IF NOT rejected THEN RAISE EXCEPTION 'cross tenant variant accepted'; END IF;
 rejected:=false;
 BEGIN INSERT INTO public.credentials(tenant_id,product_id,variant_id) VALUES(b,p,v);
 EXCEPTION WHEN foreign_key_violation THEN rejected:=true; END;
 IF NOT rejected THEN RAISE EXCEPTION 'cross tenant credential accepted'; END IF;
 rejected:=false;
 BEGIN INSERT INTO public.orders(id,tenant_id,user_id,product_id,variant_id,product_name,quantity,amount,status)
 VALUES('fixture-'||gen_random_uuid()::text,b,900000008,p,v,'Cross tenant',1,1,'pending');
 EXCEPTION WHEN foreign_key_violation THEN rejected:=true; END;
 IF NOT rejected THEN RAISE EXCEPTION 'cross tenant order accepted'; END IF;
END $$;
SELECT 'PASS: cross-tenant variant, credential and order references rejected' AS evidence;
ROLLBACK;
