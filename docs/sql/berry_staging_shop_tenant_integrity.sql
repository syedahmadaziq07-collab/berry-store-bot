-- Isolated staging fixture only. Prevent cross-tenant/product relations.
ALTER TABLE public.products ADD CONSTRAINT fixture_products_tenant_id_unique UNIQUE(tenant_id,id);
ALTER TABLE public.product_variants ADD CONSTRAINT fixture_variants_tenant_product_unique UNIQUE(tenant_id,id,product_id);
ALTER TABLE public.product_variants ADD CONSTRAINT fixture_variant_product_tenant_fk
 FOREIGN KEY(tenant_id,product_id) REFERENCES public.products(tenant_id,id);
ALTER TABLE public.credentials ADD CONSTRAINT fixture_credential_product_tenant_fk
 FOREIGN KEY(tenant_id,product_id) REFERENCES public.products(tenant_id,id);
ALTER TABLE public.credentials ADD CONSTRAINT fixture_credential_variant_tenant_fk
 FOREIGN KEY(tenant_id,variant_id,product_id) REFERENCES public.product_variants(tenant_id,id,product_id);
ALTER TABLE public.orders ADD CONSTRAINT fixture_order_product_tenant_fk
 FOREIGN KEY(tenant_id,product_id) REFERENCES public.products(tenant_id,id);
ALTER TABLE public.orders ADD CONSTRAINT fixture_order_variant_tenant_fk
 FOREIGN KEY(tenant_id,variant_id,product_id) REFERENCES public.product_variants(tenant_id,id,product_id);
ALTER TABLE public.orders ADD CONSTRAINT fixture_order_variant_requires_product CHECK(variant_id IS NULL OR product_id IS NOT NULL);
