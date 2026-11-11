-- Berry AI Studio Wallet foundation (MYR)
-- Run once in Supabase SQL Editor BEFORE merging the bot/dashboard changes.
-- Never execute this on the wrong Supabase project. Back up your database first.
-- Only the server-side SUPABASE_SERVICE_KEY can read wallets or call the ledger RPC.
-- NO payment gateway or automatic top-up is enabled by this migration.

CREATE TABLE IF NOT EXISTS public.ai_wallets (
    tenant_id UUID NOT NULL REFERENCES public.tenants(id),
    user_id BIGINT NOT NULL CHECK (user_id > 0),
    currency TEXT NOT NULL DEFAULT 'MYR' CHECK (currency = 'MYR'),
    balance NUMERIC(12,2) NOT NULL DEFAULT 0 CHECK (balance >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, user_id)
);

CREATE TABLE IF NOT EXISTS public.ai_wallet_transactions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tenant_id UUID NOT NULL REFERENCES public.tenants(id),
    user_id BIGINT NOT NULL CHECK (user_id > 0),
    kind TEXT NOT NULL CHECK (kind IN ('topup', 'debit', 'refund', 'adjustment')),
    amount NUMERIC(12,2) NOT NULL CHECK (amount <> 0),
    balance_after NUMERIC(12,2) NOT NULL CHECK (balance_after >= 0),
    reference TEXT,
    idempotency_key TEXT NOT NULL CHECK (length(trim(idempotency_key)) > 0),
    note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ai_wallet_transactions_wallet_fkey
      FOREIGN KEY (tenant_id, user_id)
      REFERENCES public.ai_wallets (tenant_id, user_id),
    CONSTRAINT ai_wallet_transactions_idempotency UNIQUE (tenant_id, idempotency_key),
    CONSTRAINT ai_wallet_transactions_amount_direction CHECK (
        (kind IN ('topup', 'refund') AND amount > 0) OR
        (kind = 'debit' AND amount < 0) OR
        (kind = 'adjustment')
    )
);

CREATE INDEX IF NOT EXISTS ai_wallet_transactions_user_recent_idx
    ON public.ai_wallet_transactions (tenant_id, user_id, created_at DESC, id DESC);

ALTER TABLE public.ai_wallets ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.ai_wallet_transactions ENABLE ROW LEVEL SECURITY;

-- No anonymous or authenticated direct table access; Telegram identity is verified by the bot.
REVOKE ALL ON TABLE public.ai_wallets, public.ai_wallet_transactions FROM PUBLIC, anon, authenticated;
GRANT SELECT ON TABLE public.ai_wallets, public.ai_wallet_transactions TO service_role;
REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER
ON public.ai_wallets, public.ai_wallet_transactions FROM service_role;
REVOKE USAGE, UPDATE ON SEQUENCE public.ai_wallet_transactions_id_seq FROM service_role;

-- Only server-side trusted code may mutate a wallet, via ONE atomic ledger operation.
-- Never call this RPC from a browser or Telegram client.
CREATE OR REPLACE FUNCTION public.ai_wallet_apply_transaction(
    p_tenant_id UUID,
    p_user_id BIGINT,
    p_amount NUMERIC,
    p_kind TEXT,
    p_idempotency_key TEXT,
    p_reference TEXT DEFAULT NULL,
    p_note TEXT DEFAULT NULL
)
RETURNS TABLE (transaction_id BIGINT, new_balance NUMERIC)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $$
DECLARE
    v_current NUMERIC(12,2);
    v_after NUMERIC(12,2);
    v_existing public.ai_wallet_transactions%ROWTYPE;
    v_transaction_id BIGINT;
BEGIN
    IF auth.role() IS DISTINCT FROM 'service_role' THEN
        RAISE EXCEPTION 'Unauthorized wallet operation';
    END IF;
    IF p_tenant_id IS NULL OR p_user_id IS NULL OR p_user_id <= 0 THEN
        RAISE EXCEPTION 'Invalid tenant or user';
    END IF;
    IF p_amount IS NULL OR p_amount = 0
       OR p_amount <> round(p_amount, 2)
       OR abs(p_amount) > 9999999999.99 THEN
        RAISE EXCEPTION 'Invalid MYR amount';
    END IF;
    IF p_idempotency_key IS NULL OR trim(p_idempotency_key) = '' THEN
        RAISE EXCEPTION 'Missing idempotency key';
    END IF;
    IF p_kind NOT IN ('topup','debit','refund','adjustment')
       OR (p_kind IN ('topup','refund') AND p_amount <= 0)
       OR (p_kind = 'debit' AND p_amount >= 0) THEN
        RAISE EXCEPTION 'Invalid wallet transaction type or direction';
    END IF;

    INSERT INTO public.ai_wallets(tenant_id, user_id)
    VALUES (p_tenant_id, p_user_id)
    ON CONFLICT (tenant_id, user_id) DO NOTHING;

    SELECT balance INTO v_current
      FROM public.ai_wallets
     WHERE tenant_id = p_tenant_id AND user_id = p_user_id
     FOR UPDATE;

    -- Acquiring the per-wallet lock BEFORE checking idempotency serializes retries.
    SELECT * INTO v_existing
      FROM public.ai_wallet_transactions
     WHERE tenant_id = p_tenant_id AND idempotency_key = p_idempotency_key;

    IF FOUND THEN
        IF v_existing.user_id <> p_user_id OR v_existing.amount <> p_amount
           OR v_existing.kind <> p_kind THEN
            RAISE EXCEPTION 'Idempotency key already used for a different operation';
        END IF;
        transaction_id := v_existing.id;
        new_balance := v_existing.balance_after;
        RETURN NEXT;
        RETURN;
    END IF;

    v_after := v_current + p_amount;
    IF v_after < 0 THEN
        RAISE EXCEPTION 'Insufficient wallet balance';
    END IF;
    IF v_after > 9999999999.99 THEN
        RAISE EXCEPTION 'Wallet limit exceeded';
    END IF;

    UPDATE public.ai_wallets
       SET balance = v_after, updated_at = now()
     WHERE tenant_id = p_tenant_id AND user_id = p_user_id;

    INSERT INTO public.ai_wallet_transactions(
        tenant_id, user_id, kind, amount, balance_after,
        reference, idempotency_key, note
    ) VALUES (
        p_tenant_id, p_user_id, p_kind, p_amount, v_after,
        p_reference, p_idempotency_key, p_note
    ) RETURNING id INTO v_transaction_id;

    transaction_id := v_transaction_id;
    new_balance := v_after;
    RETURN NEXT;
END;
$$;

REVOKE ALL ON FUNCTION public.ai_wallet_apply_transaction(
    UUID, BIGINT, NUMERIC, TEXT, TEXT, TEXT, TEXT
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.ai_wallet_apply_transaction(
    UUID, BIGINT, NUMERIC, TEXT, TEXT, TEXT, TEXT
) TO service_role;
