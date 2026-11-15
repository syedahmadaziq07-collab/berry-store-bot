-- Berry Store Main Browse Shop V4 copy, approved 2026-11-15.
-- Copy and three variant labels only. Does NOT change price, stock, duration,
-- product status, order history, or payment settings. Safe to re-run.
-- All 13 products and 17 variants have an explicit 7-day access warranty.
BEGIN;

UPDATE public.products
SET description = CASE id
    WHEN 1 THEN $copy$🎬 Edit video dengan CapCut Pro untuk content, assignment dan kerja harian.
📧 Pilihan akaun Private; email disediakan mengikut pakej.
✨ Pilih tempoh akses yang sesuai pada varian di bawah.
🛡️ Warranty 7 hari untuk masalah akses.$copy$
    WHEN 2 THEN $copy$🎨 Design poster, slide presentation, resume dan macam-macam lagi dengan Canva.
✨ Ada pilihan Pro dan Education; tempoh akses ikut varian yang dipilih.
📩 Maklumat penggunaan akan diberikan selepas order diproses.
🛡️ Warranty 7 hari untuk masalah akses.$copy$
    WHEN 3 THEN $copy$🤖 Gemini AI untuk bantu idea, penulisan, ulang kaji dan tugasan.
📩 Aktif melalui link jemputan ke email yang layak.
⚠️ Pastikan email sudah keluar daripada team lama dan belum melebihi had jemputan.
✨ Pilih tempoh akses pada varian di bawah.
🛡️ Warranty 7 hari untuk masalah akses.$copy$
    WHEN 4 THEN $copy$💬 Pilihan akses ChatGPT untuk belajar, menulis, coding dan kerja kreatif.
✨ Pilih Plus, Business atau GO mengikut keperluan dan stok.
📩 Kaedah akses (akaun disediakan / jemputan) ikut varian pilihan.
🛡️ Warranty 7 hari untuk masalah akses.$copy$
    WHEN 5 THEN $copy$🗂️ Notion AI Business Plan untuk susun nota, projek, tugasan dan kerja dalam satu workspace.
🤖 Fungsi AI membantu merancang, merumus dan mengolah kandungan mengikut akses pakej.
📆 Tempoh akses: 1 bulan (tidak diperbaharui secara automatik).
🛡️ Warranty 7 hari untuk masalah akses.$copy$
    WHEN 6 THEN $copy$🪟 Microsoft Office untuk kerja dan pembelajaran.
📚 Termasuk Microsoft Word, Excel, PowerPoint dan aplikasi berkaitan Microsoft Office yang disertakan dalam pakej.
✍️ Sesuai untuk assignment, laporan, spreadsheet dan presentation.
♾️ Tempoh pakej: Lifetime seperti dinyatakan dalam listing.
🛡️ Warranty 7 hari untuk masalah akses.$copy$
    WHEN 7 THEN $copy$📸 Lightroom Premium untuk edit gambar, warna dan hasilkan visual yang lebih kemas.
👥 Jenis akses: Sharing.
📆 Tempoh: 1 bulan (tidak diperbaharui secara automatik).
🛡️ Warranty 7 hari untuk masalah akses.$copy$
    WHEN 8 THEN $copy$▶️ YouTube Premium untuk pengalaman menonton dan dengar muzik mengikut akses pakej.
🔐 Jenis akaun: Private, maksimum 3 peranti.
📩 Aktif melalui jemputan; gunakan email yang belum melanggan YouTube Premium.
📆 Tempoh: 1 bulan (tidak diperbaharui secara automatik).
🛡️ Warranty 7 hari untuk masalah akses.$copy$
    WHEN 9 THEN $copy$🍿 Netflix Original 4K Premium untuk movie dan siri kegemaran.
📺 Pilih jenis akses Sharing, Private atau Semi Private mengikut varian.
✨ Kualiti tontonan bergantung pada kandungan, pelan dan peranti.
📆 Tempoh: 1 bulan (tidak diperbaharui secara automatik).
🛡️ Warranty 7 hari untuk masalah akses.$copy$
    WHEN 10 THEN $copy$🤖 Bot Auto Order untuk urus tempahan pelanggan dengan lebih tersusun.
📦 Pakej merangkumi bot Telegram, dashboard urus produk, database Supabase dan web untuk jalankan bot.
📆 Tempoh pakej: 1 bulan.
💬 Detail setup dan serahan akan diselaraskan dengan admin.
🛡️ Warranty 7 hari untuk masalah fungsi yang dibekalkan.$copy$
    WHEN 13 THEN $copy$📣 Bot Auto Promote untuk bantu urus aktiviti promosi secara automatik.
📆 Tempoh pakej: 1 bulan.
💬 Semak cara penggunaan dan tetapan dengan admin selepas tempahan.
🛡️ Warranty 7 hari untuk masalah fungsi yang dibekalkan.$copy$
    WHEN 16 THEN $copy$📲 App yang kau cari tak ada dalam senarai?
💬 PM @berryrc dan beritahu nama aplikasi serta pakej yang kau nak.
💰 Admin akan sahkan ketersediaan dan harga sebelum tempahan sebenar.
⚠️ Varian “test” hanyalah contoh; jangan checkout varian itu untuk pembelian sebenar.
🛡️ Warranty 7 hari selepas akses sebenar diserahkan.$copy$
    WHEN 26 THEN $copy$📑 Semakan dokumen Turnitin untuk tugasan dan laporan.
📄 Varian Browse Shop ini untuk fail 50 halaman ke bawah; lihat harga pada butang varian.
🔎 Untuk pilihan Similarity, AI Checker dan pakej lain, buka menu Turnitin khas.
🛡️ Warranty 7 hari jika ada masalah pada laporan yang dibekalkan.$copy$
END
WHERE tenant_id = '92c1e5ca-8498-438f-b777-3dc1c3195c1b'
  AND id IN (1,2,3,4,5,6,7,8,9,10,13,16,26);

UPDATE public.product_variants AS v
SET variant_name = CASE v.id
    WHEN 6 THEN 'Pro Private 7 Days'
    WHEN 13 THEN 'Pro 1 Month'
    WHEN 8 THEN 'Gemini AI Plus 6 Months'
    ELSE v.variant_name
END,
description = CASE v.id
    WHEN 5 THEN $copy$📆 Akses CapCut Pro Private selama 1 bulan.
📧 Email akaun disediakan; akses private, tidak dikongsi.
🛡️ Warranty 7 hari untuk masalah akses.$copy$
    WHEN 6 THEN $copy$📆 Akses CapCut Pro Private selama 7 hari.
📧 Email akaun disediakan; akses private, tidak dikongsi.
🛡️ Warranty 7 hari untuk masalah akses.$copy$
    WHEN 13 THEN $copy$📆 Akses Canva Pro selama 1 bulan.
🎨 Sesuai untuk design, presentation dan bahan kreatif.
🛡️ Warranty 7 hari untuk masalah akses.$copy$
    WHEN 14 THEN $copy$♾️ Pilihan Canva Education Lifetime mengikut pakej.
🎓 Sesuai untuk bahan pembelajaran dan reka bentuk.
🛡️ Warranty 7 hari untuk masalah akses (bukan warranty seumur hidup).$copy$
    WHEN 7 THEN $copy$📆 Akses Gemini AI Pro selama 3 bulan.
📩 Aktivasi melalui link jemputan; email perlu keluar daripada team sebelumnya dan belum melebihi had jemputan.
🛡️ Warranty 7 hari untuk masalah akses.$copy$
    WHEN 8 THEN $copy$📆 Akses Gemini AI Plus selama 6 bulan.
📩 Aktivasi melalui link jemputan; email perlu keluar daripada team sebelumnya dan belum melebihi had jemputan.
🛡️ Warranty 7 hari untuk masalah akses.$copy$
    WHEN 15 THEN $copy$📆 Akses Gemini AI Pro selama 1 bulan.
📩 Aktivasi melalui link jemputan; email perlu keluar daripada team sebelumnya dan belum melebihi had jemputan.
🛡️ Warranty 7 hari untuk masalah akses.$copy$
    WHEN 1 THEN $copy$📆 ChatGPT Plus Private selama 1 bulan (non-renewable).
🔐 Akaun private disediakan; tidak berkongsi.
✨ Untuk belajar, penulisan dan kerja kreatif mengikut had pelan.
🛡️ Warranty 7 hari untuk masalah akses.$copy$
    WHEN 2 THEN $copy$📆 ChatGPT Business Private selama 1 bulan (non-renewable).
📩 Akses melalui jemputan ke email sendiri mengikut pakej; akaun private.
💼 Sesuai untuk tugasan profesional dan produktiviti.
🛡️ Warranty 7 hari untuk masalah akses.$copy$
    WHEN 12 THEN $copy$📆 ChatGPT Business (Head) selama 1 bulan (non-renewable).
👥 Boleh jemput sehingga 3 email ke workspace seperti pakej asal.
💻 Sesuai untuk coding dan kerja berpasukan.
🛡️ Warranty 7 hari untuk masalah akses.$copy$
    WHEN 24 THEN $copy$💬 ChatGPT GO Private — PM @berryrc atau Support dalam bot untuk pengesahan cara akses/email.
📩 Gunakan email sendiri jika diminta admin.
🛡️ Warranty 7 hari untuk masalah akses.$copy$
    WHEN 9 THEN $copy$🍿 Netflix Sharing selama 1 bulan (non-renewable).
👥 Akses berkongsi mengikut aturan pakej.
🛡️ Warranty 7 hari untuk masalah akses.$copy$
    WHEN 10 THEN $copy$🍿 Netflix Private selama 1 bulan (non-renewable).
🔐 Pilihan akses private mengikut aturan pakej.
🛡️ Warranty 7 hari untuk masalah akses.$copy$
    WHEN 11 THEN $copy$🍿 Netflix Semi Private selama 1 bulan (non-renewable).
👥 Pilihan semi-private mengikut aturan pakej.
🛡️ Warranty 7 hari untuk masalah akses.$copy$
    WHEN 19 THEN $copy$📣 Bot Auto Promote — pakej 1 bulan.
💬 Admin akan bantu semak konfigurasi dan cara penggunaan.
🛡️ Warranty 7 hari untuk masalah fungsi yang dibekalkan.$copy$
    WHEN 31 THEN $copy$⚠️ Varian “test” ialah placeholder, bukan pakej pembelian sebenar.
💬 PM @berryrc untuk pengesahan aplikasi, harga dan stok sebelum membeli.
🛡️ Warranty 7 hari untuk akses sebenar selepas diserahkan.$copy$
    WHEN 48 THEN $copy$📄 Satu semakan Turnitin bagi fail 50 halaman ke bawah.
💳 Harga varian Browse Shop: RM3.00 bagi setiap fail.
🔎 Untuk servis Turnitin terkini, lihat menu Turnitin khas.
🛡️ Warranty 7 hari jika ada masalah pada laporan.$copy$
END
FROM public.products AS p
WHERE p.id = v.product_id
  AND p.tenant_id = '92c1e5ca-8498-438f-b777-3dc1c3195c1b'
  AND v.id IN (1,2,5,6,7,8,9,10,11,12,13,14,15,19,24,31,48);

COMMIT;
