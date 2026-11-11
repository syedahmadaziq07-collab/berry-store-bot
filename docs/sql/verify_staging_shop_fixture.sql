BEGIN;
DO $$ DECLARE t uuid:=gen_random_uuid(); p integer; v integer; n bigint; BEGIN
 INSERT INTO public.tenants(id) VALUES(t);
 INSERT INTO public.products(tenant_id,name,price,stock) VALUES(t,'Synthetic fixture only',5,2) RETURNING id INTO p;
 INSERT INTO public.product_variants(tenant_id,product_id,variant_name,price,stock) VALUES(t,p,'Fixture month',5,2) RETURNING id INTO v;
 INSERT INTO public.users(tenant_id,id,username,first_name) VALUES(t,900000006,'fixture','Synthetic');
 INSERT INTO public.credentials(tenant_id,product_id,variant_id) VALUES(t,p,v);
 INSERT INTO public.categories(tenant_id,name) VALUES(t,'Fixture');
 INSERT INTO public.bot_settings(tenant_id,key,value) VALUES(t,'maintenance_mode','true');
 INSERT INTO public.orders(id,tenant_id,user_id,product_id,variant_id,product_name,quantity,amount,status)
 VALUES('fixture-'||gen_random_uuid()::text,t,900000006,p,v,'Synthetic fixture only',1,5,'pending');
 SELECT count(*) INTO n FROM public.products a JOIN public.product_variants b ON b.product_id=a.id AND b.tenant_id=a.tenant_id
 JOIN public.credentials c ON c.product_id=a.id AND c.variant_id=b.id AND c.tenant_id=a.tenant_id WHERE a.tenant_id=t;
 IF n<>1 THEN RAISE EXCEPTION 'fixture relations failed'; END IF;
 IF has_table_privilege('anon','public.products','SELECT') OR has_table_privilege('authenticated','public.credentials','SELECT') THEN
  RAISE EXCEPTION 'fixture exposed'; END IF;
END $$;
SELECT 'PASS: isolated shop relations and denied public access; all fixture data rolled back' AS evidence;
ROLLBACK;
