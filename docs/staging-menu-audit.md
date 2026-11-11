# Berry Store Gemini — audit menu dan keputusan ujian

Tarikh: 11 November 2026 (Malaysia). **Keputusan keseluruhan: FAIL / belum memenuhi definition of done.** Pembaikan kod telah dideploy ke staging; integrasi data sebenar dan browser E2E selepas login masih BLOCKED. PASS pada kawalan akses tidak bermaksud fungsi kedai sudah connected.

Staging: https://berry-gemini-admin-staging.onrender.com/dashboard
PR draft: https://github.com/syedahmadaziq07-collab/berry-store-bot/pull/25
Commit aplikasi diuji/dideploy: `baefec7efd58dcfdc7822b8217d1e29f845c3fcc`
Render deploy: `dep-dbq3uc3bc2fs73csa1l0` — status `live` disahkan.

## PASS/FAIL mengikut menu

Semua baris HTTP di bawah diuji pada **staging**, tanpa cookie admin. HTML 200 bermaksud shell React/login tersedia pada pautan menu tersebut. API 401 bermaksud permintaan tanpa login ditolak. Paparan data selepas login tidak diuji dan tidak dianggap PASS.

| Menu | Shell HTTP | API tanpa login | Browser E2E selepas login | Integrasi / fungsi yang masih belum disahkan |
|---|---|---|---|---|
| Overview | PASS 200 | PASS 401 | BLOCKED | Supabase tenant, analytics dan jumlah sebenar |
| Shop / products / categories / variants | PASS 200 | PASS 401 | BLOCKED | Bacaan produk sebenar, kategori, CRUD dan transaksi variant |
| Orders | PASS 200 | PASS 401 | BLOCKED | Senarai sebenar, resit, approval/rejection, penghantaran dan duplicate processing |
| Credentials & Auto | PASS 200 | PASS 401 | BLOCKED | Metadata inventori sebenar, import/delete dan delivery; credential tidak didedahkan |
| Customers | PASS 200 | PASS 401 | BLOCKED | Senarai sebenar dan kemas kini notes/status |
| Berry AI Studio | PASS 200 | PASS 401 | BLOCKED | Jadual tools, provider dan tetapan sebenar |
| AI Model Catalog | PASS 200 | PASS 401 | BLOCKED | Katalog models, pricing dan provider health |
| AI Wallets & Ledger | PASS 200 | PASS 401 | BLOCKED | Baki/lejar sebenar, pelarasan atomic dan payment flow |
| Bot Control Center | PASS 200 | PASS 401 | BLOCKED | Settings sebenar, perubahan settings dan kesan pada bot |
| Broadcast Campaign | PASS 200 | PASS 401 | BLOCKED | History dan queue belum diimplementasi; tiada mesej dihantar |
| Referrals & Vouchers | PASS 200 | PASS 401 | BLOCKED | Referral sebenar, ganjaran lejar dan voucher API |
| System Monitoring | PASS 200 | PASS 401 | BLOCKED | Health selepas login dan audit production/shared store |

**12 pautan menu dan 14 endpoint guard** diperiksa. Respons, masa semakan dan nama bundle sebenar direkodkan dalam `staging-menu-public-results.json`. Reproduce dengan:

```bash
python scripts/staging_public_audit.py --output docs/staging-menu-public-results.json
```

Script dikunci kepada origin staging di atas, tidak membawa credentials dan tidak menghubungi production.

## Ujian browser sebenar yang dijalankan

| Senario | Keputusan | Bukti |
|---|---|---|
| Buka halaman login staging | PASS | Tajuk Berry Store, logo asal dan borang login dipaparkan |
| Show password | PASS | Jenis input bertukar kepada `text`; butang bertukar kepada Hide password |
| Hide password | PASS | Butang kembali kepada Show password |
| Submit borang kosong | PASS | Mesej “Sila masukkan kata laluan admin” dipaparkan |
| Login admin berjaya dalam sesi audit ini | BLOCKED | Tiada session/credential admin staging yang tersedia |
| Navigation dan fungsi menu selepas login | BLOCKED | Tidak dilaksanakan; bukan PASS berdasarkan source atau mock |
| Mobile browser E2E | NOT RUN | Tidak diuji pada viewport mobile |

Screenshot browser sebenar: `evidence/login-empty-validation.jpg`. Cubaan screenshot full-page pertama timeout; screenshot viewport berikutnya berjaya. Satu cubaan locator selepas toggle password timeout; keadaan DOM berikutnya mengesahkan toggle itu sebenarnya berjaya. Tiada credential dimasukkan atau dipaparkan.

## Pembaikan yang telah dilaksanakan

1. Kegagalan network pada satu module tidak lagi menggagalkan semua module lain. Setiap module mempunyai status ready/loading/error dan validasi respons sendiri.
2. Menu yang datanya gagal tidak memaparkan array kosong atau baki sifar sebagai data sah. Paparan lama disembunyikan semasa refresh dan respons refresh terdahulu tidak boleh menimpa respons baharu.
3. Refresh mempunyai cancellation dan had masa 25 saat. Respons 401 mengembalikan pengguna kepada login.
4. Menu menyokong pautan `/dashboard/<menu>`, serta history Back/Forward. Pemilihan AI Model Catalog membuka tab model, bukan tab tools.
5. Bacaan orders disusun paling terkini dahulu. Timestamp tanpa timezone dianggap UTC dan dihantar kepada browser dengan offset yang jelas. Tarikh database tidak sah menghasilkan ralat 503, bukannya crash 500.
6. Eksport CSV mengekod setiap cell dan melindungi input teks yang menyerupai formula spreadsheet. Download menggunakan Blob URL.
7. Butang salin credential dimatikan apabila backend hanya memberikan metadata bertopeng. Status penggunaan inventori tidak lagi digambarkan sebagai bukti penghantaran Telegram.
8. Client mengekalkan idempotency key untuk payload sama selepas keputusan network/5xx yang tidak pasti. Tiada automatic retry ditambah. Registry ini dalam memori sahaja; ia bukan bukti exactly-once atau pengganti lejar/outbox database.
9. Respons RPC catalog mesti mengesahkan `status=committed` sebelum diterima sebagai berjaya. Network failure dan respons tidak sah menghasilkan ralat yang jelas dan tidak mendedahkan service key.
10. Konfigurasi URL Supabase ditolak jika mengandungi credentials, path, query, fragment atau port tambahan. Health admin menyediakan boolean konfigurasi tenant/service key tanpa nilainya.

## Keputusan automated tests

| Pemeriksaan | Keputusan | Had bukti |
|---|---|---|
| TypeScript `tsc --noEmit` | PASS | Kod frontend |
| React production build | PASS | Bundle dibina dan turut dibina oleh Render Docker |
| Frontend tests | PASS — 16/16 | Unit tests module loader, routing, CSV, idempotency dan business logic |
| Python tests | PASS — 53/53 | Runtime Flask/security/adapter dan regression checks |
| Python syntax | PASS | admin_app.py, bot.py dan script audit; bot tidak diimport/dijalankan |
| npm audit production dependencies | PASS | 0 advisory dilaporkan pada semakan ini |
| GitHub Actions pada commit aplikasi di atas | PASS — 4 workflow | Termasuk frontend build dan Python runtime tests |
| Authenticated Supabase read/write live tests | BLOCKED | Credentials/tenant sah dan kelulusan khusus bacaan production belum tersedia |
| Telegram integration live tests | BLOCKED | Token/identity dan akses ujian belum tersedia; tiada polling, broadcast atau delivery diuji |

Log suite: `evidence/python-menu-audit-tests.txt` dan `evidence/frontend-menu-audit-tests.txt`. Inventori 29 route declarations daripada source: `evidence/admin-route-inventory.json`.

**Penting:** unit tests menggunakan fixture/MockTransport yang dinyatakan sebagai test-only. Tiada fixture dimasukkan ke backend runtime atau staging. Kejayaan ujian ini bukan bukti bahawa Supabase atau Telegram live sudah connected.

## Kegagalan fungsi yang diketahui daripada audit source

- Selain catalog adapter, kebanyakan write routes masih menuju kepada handler 501 (unimplemented). Semua business writes juga dikunci oleh middleware jika database tidak ditandakan isolated.
- Catalog RPC yang disediakan masih belum diaplikasikan/dijalankan pada database ujian. Category, variant, customer notes/status, credential import/delivery, AI config, wallet adjustment dan bot settings writes belum lengkap.
- Broadcast history dan AI provider health secara sengaja memberikan 501; ia bukan sejarah kosong atau provider yang berjaya diuji.
- Admin session, rate limit dan audit SQLite masih berada pada filesystem ephemeral staging. Persistent/shared store masih diperlukan untuk production.
- Penemuan schema/policy production dalam laporan sesi terdahulu belum diuji semula dalam audit ini. Jangan anggap masalah itu sudah selesai.

## Halangan akses dan keputusan keselamatan

Sesi browser daripada handoff lama tidak wujud dalam sesi semasa. Credential ujian staging sementara daripada sesi awal juga tidak tersedia. Tiada auth bypass, password reset, session injection atau auth weakening dilakukan untuk memaksa browser masuk.

Automatic approval review menolak pemeriksaan endpoint **orders production** kerana ia boleh membaca data pelanggan/pesanan persendirian, sedangkan kelulusan khusus untuk bacaan production belum jelas. Tiada percubaan laluan alternatif untuk memintas penolakan itu dilakukan. Semua pemeriksaan HTTP selepas itu dihadkan kepada staging tanpa authentication.

Untuk menyambung, perlukan kelulusan jelas bagi **bacaan sahaja data production untuk staging**, diikuti akses admin staging/Render melalui borang selamat serta konfigurasi server yang sah. Kelulusan read-only tidak meliputi perubahan baki, approval pesanan, penghantaran credential, broadcast atau migration production.

## Status release dan rollback

PR #25 kekal draft dan tidak dimerge. Hanya staging dideploy. Tiada production configuration, database, wallet atau bot diubah. Tiada transaksi wang, mesej broadcast atau credential delivery dijalankan.

Jika perlu rollback perubahan audit ini, redeploy staging kepada aplikasi terdahulu `ab154583429b3778b68ba5faad4c967289c9f0f3` (atau suspend staging). Jangan ubah production dan jangan menjalankan `bot.py` sebagai fallback staging. Tiada migration database diaplikasikan dalam audit ini.

**Production approval belum diminta kerana kriteria readiness belum dipenuhi.**
