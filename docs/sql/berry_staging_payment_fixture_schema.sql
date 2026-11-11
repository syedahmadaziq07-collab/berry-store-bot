-- ONLY for the isolated cirsdvkfkvypprnmyykk staging database.
-- Minimal contract fixture for the existing wallet/top-up SQL, not a production schema clone.
CREATE TABLE public.tenants (id uuid PRIMARY KEY);
CREATE TABLE public.orders (
 id text PRIMARY KEY, tenant_id uuid NOT NULL REFERENCES public.tenants(id),
 user_id bigint NOT NULL CHECK(user_id>0), username text NOT NULL DEFAULT '',
 product_id integer, product_name text NOT NULL, quantity integer NOT NULL,
 amount numeric(12,2) NOT NULL, status text NOT NULL,
 receipt_file_id text, approved_by bigint,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX staging_orders_tenant_user_status ON public.orders(tenant_id,user_id,status);
ALTER TABLE public.tenants ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.orders ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.tenants,public.orders FROM PUBLIC,anon,authenticated;
GRANT SELECT ON public.tenants TO service_role;
GRANT SELECT,INSERT,UPDATE ON public.orders TO service_role;
