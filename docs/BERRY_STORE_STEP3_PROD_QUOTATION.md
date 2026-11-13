# Berry Store STEP 3 — Production Quotation & Dynamic Pricing

Branch: `feat/step3-production-quotation-20261114` (dari main `d84d4c0`,
menggabung kerja awal PR `step3-minimax-staging-offer-builder` tanpa pendua).

**Status: ENGINEERING COMPLETE — CI pending; MENUNGGU merge/deploy pemilik.**

## A. Komponen
1. **`ai_product_catalog.py`** — produk AI versi-bertenaga pertama:
   MiniMax H3 Max Turbo Text-to-Video (10s/480P/balanced/16:9|9:16/safety/MP4).
   `product_id` unik, mapping model tepat, hanya 2 input pelanggan dibenarkan
   (product_key + aspect ratio daripada enum); model/harga TIDAK boleh diubah
   pelanggan; nyahaktif tanpa padam sejarah; katalog revision=1.
2. **`ai_pricing_engine.py`** — enjin harga dinamik (semua Decimal):
   rate = max(kadar live terverifikasi, lantai standard 0.025 USD/s) ×
   11s perancangan × FX(+buffer); + kos operasi; + RM1; ÷(1−fi gateway);
   siling RM0.02; kredit sejajar unit 25 (1250 kredit/RM). FX mesti
   terverifikasi (sumber+timestamp, TTL 6j); kos op mesti konfigurasi
   diluluskan; GAGAL-TUTUP jika ada input hilang/tamat tempoh.
3. **`ai_quotation_service.py`** — quotation beku: ID unik, HMAC
   integriti-tamper-evident, terikat (tenant, customer, produk, parameter,
   prompt-hash), luput 10 minit, idempotency-key, rate-limit 6/minit,
   pembatalan tanpa sentuh dompet, `customer_view()` menapis kos dalaman.
4. **`telegram_quote_flow.py` + pendawaian `bot.py`** — alur gated:
   `BERRY_QUOTE_FLOW_ENABLED=true` + env FX/kos-ops/kunci-tandatangan;
   rute callback `ai_quote_menu`/`ai_quote_ratio:` + peringkat prompt teks
   dalam `handle_message` (tidak-menghalang, dilindungi try/except).
   **Tiada debit dompet, tiada POST provider, tiada penjanaan berbayar.**

## B. Formulasi
- `total_cost = rate×11×FX(1+buffer) + fixed_ops`
- `selling = ceil_RM0.02((total_cost + 1.00)/(1−gateway_fee))`
- `credits = ceil(selling×1250)` sejajar 25; `debit_cents` siling.
- Guard: `debit_cents − total_cost_cents ≥ 100` (margin anggaran ≥ RM1;
  margin bersih sebenar perlu rekonsiliasi bil — dibezakan dalam output).

## C. Ujian (semua LULUS tempatan)
- `test_step3_quotation.py` 18/18 — katalog sah/tidak-sah, lantai standard
  mengatasi promo, kenaikan kadar live menaikkan harga, unit/harga hilang
  ditolak, FX tamat/tempoh/tanpa-sumber ditolak, buffer FX, kos-op hilang
  gagal-tutup, detik perancangan < tempoh ditolak, quota beku + tamper
  dikesan + luput + renti-tenant + renti-pelanggan + idempotency +
  rate-limit + pembatalan + tiada debit/POST semasa quotation.
- `test_step3_minimax_offer.py` + `test_minimax_retail_guard.py` (sedia ada)
  lulus tanpa perubahan — penggunaan semula, bukan pendua.
- `test_prod_ai_studio_integration.py` 30/30 — regresi pengeluaran OK.

## D. CI
`.github/workflows/step3-quotation.yml` — compile + 3 suite + regresi.

## E. Keselamatan
Rahsia pelayan-sahaja; tiada kunci dalam log/balasan; HMAC quote;
rate-limit; integriti; fail-closed; tiada migrasi DB (katalog/in-memory —
tiada perubahan pada jadual sedia ada); dompet/RLS tidak disentuh.

## F. Bendera (semua lalai OFF)
`BERRY_QUOTE_FLOW_ENABLED`, `BERRY_AI_FX_MYR_PER_USD`,
`BERRY_AI_PAYMENT_FEE_FRACTION`, `BERRY_AI_FIXED_COST_MYR`,
`BERRY_QUOTE_SIGNING_KEY`.
