# Berry Store — Production Release Candidate (main)

Branch: `feat/prod-ai-studio-integration-20261112` (from `main` @ 409567c).
Render production service: berry-store-bot-1 (`python bot.py`), auto-deploy OFF.

**Status: RELEASE CANDIDATE — pending review; NOT deployed.**

## Audit findings on main (409567c)
1. **CRITICAL startup bug (owner directive #5, CONFIRMED):** bot.py ran an
   import-time block calling Telegram `/close` and
   `deleteWebhook?drop_pending_updates=true` on EVERY start — silently
   discarding queued customer messages — plus raw `print` of API errors that
   can embed the bot token. `main()` also called
   `delete_webhook(drop_pending_updates=True)` and
   `run_polling(drop_pending_updates=True)`.
2. AI Studio customer-facing features: only Shop/Home/wallet-balance/
   transactions/topup-preview/templates/guide menus are live; every AI
   generation feature (image/video/transform/voice/enhance/storyboard etc.)
   is a "belum tersedia" placeholder. Wallet is read-only. Checkout flag
   `BERRY_TOPUP_CHECKOUT_ENABLED` defaults OFF; no production checkout RPC.

## Changes in this candidate
1. **Startup safety fix:** removed the entire import-time early-token block;
   `delete_webhook(drop_pending_updates=False)` once in main();
   `run_polling(drop_pending_updates=False)`. Customer messages queued during
   downtime are now preserved. No import-time network calls remain.
2. **S01 wallet display fix:** exact Decimal conversion preserves fractional
   credits (RM4.99 → 6,237.5) — display only, MYR accounting untouched.
3. **Disabled-by-default AI Image Studio wiring:** gated entry
   (`ai_image_prompt` callback) requiring literal env
   `BERRY_IMAGE_STUDIO_ENABLED=true` + `BERRY_IMAGE_STUDIO_TEST_USER_ID`;
   `_image_flow` only reads `bot_data` and never constructs a worker/store;
   the underlying `TelegramImageFlow.confirm` still requires
   `allow_external` + `budget_id` which no production configuration supplies.
   Includes reviewed STEP 3 modules (image flow, sendPhoto delivery, offer
   builder) and their dependencies (staging_job_worker, video_myr_worker,
   fal_provider) — all inert at import.
4. Tests: `test_prod_ai_studio_integration.py` (13 cases: AST-verified
   pending-update preservation, flags default-off, gated entry, wallet
   display, uuid5 idempotency) + carried-over image suites 20/20.
   topup/payment suites 12+5 OK (unchanged contracts).
   CI: `.github/workflows/prod-ai-studio-integration.yml`.

## Payment/top-up audit (directive #7)
`BERRY_TOPUP_CHECKOUT_ENABLED` gate + `TENANT_ID` + `SUPABASE_SERVICE_KEY`
required; `checkout_ai_topup` shows "belum aktif" when disabled; plan screens
are previews only. No payment collection, wallet mutation, or crediting is
activated by this branch. The production checkout RPC does not exist on main;
no migrations are included or applied.

## Rollback plan
- Auto-deploy is OFF: a deploy happens only after explicit owner action.
- Rollback = redeploy previous commit `409567c` on Render (no DB schema change
  exists in this candidate — zero migration risk).
- Post-deploy smoke tests: (1) `/start` responds; (2) Render logs show no
  import-time Telegram calls and `delete_webhook` once with
  `drop_pending_updates=False`; (3) My Wallet shows fractional credits
  correctly; (4) `/healthz` and dashboard 200; (5) queued customer messages
  received during downtime are processed (not dropped).

## Final review (PR #78 @ 199f737) — 2026-11-12

### TUGAS 2 — Semakan kod akhir: KESELURUHAN LULUS
| Semakan | Hasil | Bukti |
|---|---|---|
| Permulaan tidak buang update beratur | ✅ | `delete_webhook(drop_pending_updates=False)` + `run_polling(drop_pending_updates=False)`; blok import-time dibuang sepenuhnya; diuji AST |
| Tiada panggilan rangkaian import-time | ✅ | diff menunjukkan hanya pembuangan blok `_EARLY_TOKEN`; tiada import httpx awal kekal |
| Tiada polling pendua | ✅ | `build_app()` tunggal dalam main loop sedia ada; tiada handler baru ditambah ke senarai pemproses |
| Tiada penjanaan AI pelanggan | ✅ | pintu masuk imej gated berkala; tiada laluan confirm aktif; placeholder "belum tersedia" untuk semua ciri AI |
| AI Image dilumpuhkan secara lalai | ✅ | `BERRY_IMAGE_STUDIO_ENABLED` perlu literal "true" + test user id; lalai = mesej "belum tersedia" |
| Tiada permintaan fal berbayar | ✅ | tiada konfigurasi `FAL_KEY` dalam wiring; fal_provider tidak pernah dipanggil oleh bot.py |
| Tiada debit/kredit dompet | ✅ | tiada fungsi wallet-write ditambah; dompet kekal baca-sahaja |
| Tiada pengaktifan top-up automatik | ✅ | `BERRY_TOPUP_CHECKOUT_ENABLED` lalai OFF (uji 5/5 lulus) |
| Tiada migrasi DB tidak dibenarkan | ✅ | tiada fail SQL dalam diff |
| Tiada rahsia dalam log | ✅ | cetakan ralat awal dibuang; `_safe_error` sedia ada kekal; tiada nilai rahsia dicetak |
| Keserasian kedai/pesanan/dompet/bayaran/admin | ✅ | 113 ujian; 0 kegagalan logik (31 ralat = kunci fail Windows `state.db` semasa teardown sahaja — ujian pra-wujud, bukan regresi; CI Ubuntu bersih) |

### TUGAS 3 — Integrasi bot sebenar
- Menu AI Studio: `show_ai_studio_section` tidak diubah (selain label dompet);
  semua menu sedia ada berfungsi.
- Pemroutingan callback: `ai_image_prompt` ditambah sebagai elseif **selepas**
  `ai_studio:` startswith — tiada konflik (nilai sepadan tepat, bukan awalan).
- Paparan dompet Decimal: betul (uji 6/6 + 4 AST).
- Ciri dilumpuhkan memaparkan respons selamat "belum tersedia / tiada caj".

### TUGAS 1 & CI
- Tempatan: 13/13 integrasi + 20/20 imej + 12 topup + 5 payment-gates +
  113 penuh (0 kegagalan logik) LULUS.
- GitHub: 5 LULUS + AI Model Mapping CI **sedang berjalan** — CI belum
  boleh diisytiharkan LULUS sepenuhnya sehingga selesai (lihat blok di bawah).

### TUGAS 4 — Fail yang dideploy (12)
`bot.py` · `fal_provider.py` · `staging_job_worker.py` · `video_myr_worker.py`
· `telegram_image_flow.py` · `telegram_image_delivery.py`
· `telegram_image_offer_builder.py` · `tests/` (4 fail ujian — tidak
dideploy runtime) · `.github/workflows/prod-ai-studio-integration.yml` ·
`docs/BERRY_STORE_PROD_RC.md`.
Render: service `berry-store-bot-1`, start `python bot.py`, branch main,
auto-deploy OFF. Persekitaran: hanya nama variable disemak — nilai TIDAK
dibaca/dicetak. Risiko khas pengeluaran: (1) kelakuan poll pertama selepas
redeploy akan memproses sebarang update beratur (dikehendaki); (2) tiada.

## PR #78 @ 00f5674+ — Penghalang harga STEP 2 SELESAI (jawapan Fasa B.1–B.3)

**Skema API harga fal.ai DISELESAIKAN** daripada dokumentasi rasmi
(https://fal.ai/docs/documentation/model-apis/pricing.md):
- Endpoint: `GET https://api.fal.ai/v1/models/pricing?endpoint_id=<id>`
- Auth: `Authorization: Key $FAL_KEY`
- Respons: `{"prices":[{"endpoint_id","unit_price","unit","currency"}],
  "next_cursor","has_more"}` — unit: image/megapixel/second/video/request;
  mata wang USD; ralat pelayan & masa giliran percuma.

**Pelaksanaan baru:** `fal_pricing.py` + `tests/test_fal_pricing.py` (11/11):
- `VerifiedFalPricing.exact_price()` — menerima harga sahaja dari dokumen
  sah (endpoint_id padanan tepat, unit_price nombor positif, unit dikenali,
  currency USD). Model tiada, bukan-200, redirect, JSON cacat, harga bukan
  nombor → `PricingUnavailable` (TIDAK PERMENJADI kos andaian).
- `cost_bound_myr_cents()` — sempadan kos MYR integer-sen (siling) daripada
  harga USD × kadar FX pelayan × bilangan unit; FX tidak disimpulkan.
- `verified_quote_credits()` — rantai penuh STEP 2: kos all-in disahkan →
  polisi `berry_credit_pricing` (ronde atas kredit penuh) → sepadan unit
  25-kredit (RM0.02) RPC dompet → **marjin minimum RM1 diuatkuasakan**;
  marjin tak cukup → tolak.
- `berry_credit_pricing.py` dibawa ke main (polisi tulen; tiada efek runtime).
- CI: ujian harga ditambah pada workflow PR #78.
- Verifikasi baca-sahaja sebenar kekal pintu pemilik: probe sedia laksana
  apabila kunci diberi; tiada panggilan dibuat dalam keluaran ini.

Status pintu STEP 2 selepas ini: harga-skema **SELESAI (kod+ujian)**;
entitlement & E2E sebenar kekal TERSEKAT kelulusan pemilik (perlu bacaan
akaun disahkan & E2E terkawal). Marjin RM1: MEKANISME SELESAI; nilai
sebenar bergantung pada bacaan harga sebenar + kadar FX pelayan.

## Remaining blockers (unchanged)
- Real AI generation: requires STEP 2 operational gates (pricing, entitlement,
  margin, E2E) and owner approval — all features stay disabled.
- Payment activation: owner bank-evidence reconciliation for disputed orders.
- Production DB migrations: none included; any future migration needs
  explicit approval.
