# Berry Store STEP 3 — Automatic FX & Environment Readiness (2026-11-14)

Branch: `feat/step3-auto-fx-and-env-audit-20261114` (dari main `01399d7`).

## Punca akar punca "FX rate missing/invalid"
1. FX manual env (3 var) wajib di-set oleh pemilik secara berulang → tidak
   pernah dikonfigurasi → fail-closed.
2. `TelegramQuoteFlow` menahan satu `FXRate` **beku selamanya** selepas bina
   pertama — quote baharu tidak pernah melihat kadar terkini.
3. `MAX_FX_AGE_SECONDS = 6h` — salah untuk kadar **rujukan harian**.

## Betulan (commit ini)
1. **`fx_rate_provider.py` (baharu)** — auto-retrieval USD/MYR:
   - Sumber: `https://api.frankfurter.dev/v2/rate/usd/myr` (rujukan
     bank-pusat/mid-market, berdokumen, **tiada kunci API**).
   - Kadar `Decimal`; skema `{base,date,rates.MYR}` disahkan ketat.
   - Kesegaran: tarikh terbitan → timestamp penerbitan 16:00 MYT
     (dikepang supaya tidak pernah masa depan); tetingkap **4 hari**
     (hujung minggu + 1 cuti); kadar lapuk → fail-closed.
   - Cache 30 min + tetapan semasa; **had belanjakan-fetch** (≤10/5 min);
     timeout 10s; cubaan semula terkawal ×2; thread-safe (kunci).
   - **Tidak pernah** `timestamp = time.time()` menyamar kadar lama.
2. **`telegram_quote_flow.py`** — kini `fx_provider` boleh dipanggil:
   **setiap quotation** mendapat snapshot FX segar; quote yang dicipta
   membekukan snapshot sendiri (diuji).
3. **`bot.py _quote_flow`** — auto FX sebagai lalai; manual env kekal
   sebagai pilihan pemilik; gagal-tutup kekal untuk kos-op/kunci.
4. **`ai_pricing_engine.py`** — `MAX_FX_AGE_SECONDS = 4 * 86400`
     (selari dasar kadar harian).
5. **`ai_env_audit.py` + `/quoteenv`** (admin-sahaja) — laporan
   kesediaan persekitaran `PRESENT/MISSING/INVALID/UNVERIFIED`
   **tanpa sebarang nilai rahsia** (diuji untuk ketiadaan nilai rahsia).

## Ujian (semua LULUS; suite penuh 332 ujian, 0 ralat bukan-Windows)
- `test_fx_rate_provider.py` 11/11 — segar, lapuk, masa-depan, timeout,
  skema tidak sah, pasangan mata wang salah, hujung-minggu, cache+TTL
  tetapan semasa, konkuren thread-safe, Decimal, validasi pembina.
- `test_fresh_fx_per_quote.py` 3/3 — FX segar setiap quote; snapshot beku
  berbeza; provider gagal/None → gagal-tutup.
- `test_ai_env_audit.py` 8/8 — termasuk "tiada nilai rahsia dalam laporan".
- Regresi: quotation 26/26, UI 6/6, integrasi prod OK.
