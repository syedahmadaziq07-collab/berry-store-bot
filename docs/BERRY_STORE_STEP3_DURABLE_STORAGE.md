# Berry Store STEP 3 — Durable Quotation Storage (Production Finalization)

Branch: `feat/step3-durable-quotation-20261114` (dari main `6709a3d`).

## Migrasi Supabase (additive; MENUNGGU kelulusan pemilik)
- **`docs/sql/ai_quotations.sql`** — jadual `berry_private.ai_quotations`
  (UUID quote_id, tenant FK, customer, product, mapping_revision, payload
  JSONB beku, integrity HMAC, state, idempotency_key, rate counters,
  expires/created) + 4 RPC service-role-sahaja:
  - `berry_ai_quote_create` — idempotent-atomik (FOR UPDATE; tiada quote pendua)
  - `berry_ai_quote_get` — pemilikan dikuatkuasakan dalam RPC
  - `berry_ai_quote_cancel` — atomik dengan FOR UPDATE
  - `berry_ai_quote_rate` — rate-limit tahan lama per-(tenant,customer,minit)
  - RLS ON; REVOKE anon/authenticated; GRANT service_role sahaja.
- **`docs/sql/ai_quotations_rollback.sql`** — drop fungsi → jadual (selamat).
- **Tiada jadual sedia ada diubah** (orders/ai_wallets/ai_wallet_transactions/products).

## Kod
- **`ai_quote_store.py`** (baharu) — `SupabaseQuoteStore` (produksi, RPC
  service-role, gagal-tutup bila DB turun) + `InMemoryQuoteStore` (ujian).
- **`ai_quotation_service.py`** (refactor) — `QuotationService(signing_key, store)`:
  quote ditulis ke storan **tahan lama SEBELUM** dipulangkan; kunci
  penandatanganan **tiada fallback BOT_TOKEN**; idempotent-tidak-menghidupkan-semula
  quote cancelled/expired; tamper/expiry/cancel dikuatkuasakan; HMAC canonical.
- **`bot.py`** — `_quote_flow` membina `SupabaseQuoteStore` (SUPABASE_URL +
  SERVICE_KEY + TENANT_ID); FX kini memerlukan `BERRY_AI_FX_SOURCE` +
  `BERRY_AI_FX_SOURCE_TIMESTAMP` (tiada timestamp masa-aplikasi); buffer FX
  `BERRY_AI_FX_BUFFER`; gagal-tutup jika konfigurasi tidak lengkap.

## Env baharu (pemilik perlu set selepas kelulusan)
```
BERRY_QUOTE_SIGNING_KEY        # ≥16 aksara — dedicated secret, BUKAN token bot
BERRY_AI_FX_MYR_PER_USD        # kadar terverifikasi
BERRY_AI_FX_SOURCE             # sumber boleh diaudit (cth: "bnm-er" + tarikh)
BERRY_AI_FX_SOURCE_TIMESTAMP   # unix seconds kadar diterbitkan (bukan masa app)
BERRY_AI_FX_BUFFER             # pecahan (lalai "0.02")
BERRY_AI_PAYMENT_FEE_FRACTION  # pecahan fi gateway terverifikasi
BERRY_AI_FIXED_COST_MYR        # kos tetap terverifikasi
BERRY_QUOTE_FLOW_ENABLED=true  # pengaktifan akhir
```

## Ujian (25/25 LULUS)
Termasuk baharu: **quote bertahan restart** (dua instance store), duplicate
idempotency, **DB gagal-tutup** (rate/create/get), konfigurasi store wajib,
konkuren kunci-sama → satu quote.
