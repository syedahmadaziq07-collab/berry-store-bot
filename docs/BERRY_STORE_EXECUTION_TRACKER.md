# Berry Store — Execution Tracker (STEP 1–12)

Baseline: PR #78 merged to main (`ddf1929`), Render deploy
`dep-dbqts00u01pc73831rr0` LIVE (smoke belum disahkan).
Roadmap authority: STEP 1–STEP 2 didefinisikan dalam docs/soft-launch-progress.md
+ matriks audit STEP 1. **STEP 5–12 tidak didefinisikan dalam mana-mana
dokumen/PR/commit repositori — sumber hilang; tidak direka-reka.** Peta 7-fasa
admin-control-center wujud sebagai rujukan keselamatan (bukan langkah bernombor).

| STEP | Engineering | CI | Production deployed | Customer LIVE | Blocker |
|---|---|---|---|---|---|
| 1 Image/Video audit | PASS | PASS | — | — | tiada |
| 2 AI Video | PASS (bawa komponen teruji ke main: protokol no-retry, gate, rekonsiliasi operator, preflight, margin) | Menunggu CI branch | NO | NO | bacaan harga/entitlement akaun sebenar (pemilik); E2E terkawal; pengaktifan runtime |
| 3 AI Image | PASS (handlers gated, SQL PG16, offer builder) | CI lulus PR #77/#78 | NO (kod dalam main; runtime gated OFF) | NO | gate runtime + migrasi persetujuan (kelulusan) |
| 4 Shared | S01 PASS; S02–S05 Engineering N/A | — | — | — | S02: bukti bank pemilik; S03/S04: kelulusan migrasi pengeluaran; S05: kelulusan sesi log masuk |
| 5–12 | TIDAK DIDEFINISIKAN dalam sumber | — | — | — | sumber peta jalan hilang — pemilik perlu menyediakan takrifan |
| Pembaikan permulaan prod | PASS | PASS | Deploy LIVE (log belum disemak) | — | ujian asap Telegram pengeluaran belum disahkan |
| Paparan kredit tepat | PASS | PASS | Dalam main | — | verifikasi visual selepas asap |

## Log pelaksanaan
- `feat/prod-step2-completion-20261112` @ `7f05d92`: komponen STEP 2 teruji
  dari PR #76 ke main (28/28) + tracker.
- `feat/prod-step2-completion-20261112` @ `ca12b79`: `fal_pricing.py` +
  `berry_credit_pricing.py` (11/11) — skema API harga rasmi fal.
- `feat/prod-step2-completion-20261112` @ (kini): `production_model_catalog.py`
  (5/5) — katalog pengeluaran yang mengikat harga TERVERIFIKASI ke offer beku
  imej; gagal-tutup pada model tiada/tool salah/harga tak tersedia. CI diperluas.
- Ujian berkumpul: 28 step2 + 11 fal + 5 katalog + 13 prod-integrasi + 20 imej
  = 77 lulus tempatan (suite penuh 124; 31 = kunci fail Windows diketahui).
- `feat/prod-step2-completion-20261112` @ (kini): **D3 video generation
  engineering** — `telegram_video_flow.py` (persetujuan terkawal: harga beku,
  identiti ujian, pembatalan), `telegram_video_delivery.py` (sendVideo
  berasaskan pengesahan, redaksi token), `telegram_video_handlers.py`,
  `video_myr_worker.py` versi gate-no-retry terkini, `provider_readiness.py`
  + `step2_pricing_probe.py`. Suite: 26 video flow/delivery + 17 video worker
  + 10 rekonsiliasi + mocks + probe — semua LULUS.
- Ujian berkumpul: **220 ujian penuh, 189 lulus, 31 ralat = 0 ralat
  bukan-Windows** (kunci fail state.db yang diketahui — akan diverifikasi
  semula oleh CI Linux). CI diperluas dengan PTB 20.7 untuk suite video.
- Peta jalan STEP 5–12: tidak wujud dalam repositori — dilaporkan sebagai
  sumber hilang, tidak direka-reka; menunggu takrifan pemilik.
