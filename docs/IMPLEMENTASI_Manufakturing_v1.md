# Implementasi manufaktur v1

Implementasi pada aplikasi inventori yang ada, mengacu pada [PRD](PRD_Manufakturing_v1.md) dan [ERD logis](ERD_Manufakturing_v1.md). Odoo 19 tetap menjadi referensi proses. Ini bukan addon yang dipasang pada server Odoo.

## Yang tersedia

| Area | Perilaku |
|---|---|
| Master produk | Jenis pemenuhan, dapur pembuat, BOM utama dan kelipatan saran alokasi disimpan pada produk. Petugas MO memilih produk; dapur/BOM terisi otomatis. |
| Minimum | Nilai per barang–gudang, dapat diubah petugas sesuai akses. Nilai lama Central/cabang tetap menjadi nilai awal sampai gudang tersebut diberi pengaturan sendiri. Minimum boleh dihabiskan sampai nol. |
| RO dan SO | Form input RO toko ke Packing dan SO customer, draft/konfirmasi, tanggal order/kirim, referensi eksternal, beberapa SKU, serta harga per SKU SO. Konfirmasi SO membentuk DO dengan kuantitas dan SKU yang sama. |
| Konsolidasi | Admin memilih RO/SO dengan tanggal kirim yang sama untuk dikerjakan bersama. Komponen paket diturunkan dari BOM; setiap sumber tetap terlacak. |
| MO/WO dapur | Tombol pembuatan MO dari rekap menghasilkan satu MO per SKU, dengan satu WO. Tidak dibuat otomatis saat order dicatat. MO manual tersedia untuk buffer. Setengah jadi tidak memicu MO turunan. |
| Hasil | Bahan dapur dikonsumsi berdasarkan kuantitas WO dan snapshot BOM. Hasil baik aktual masuk dapur; selisih kurang/rusak dan lebih dicatat, termasuk hasil baik nol. Tidak ada backorder. |
| Waktu | Waktu fisik mulai/selesai dapur berada dalam satu shift 20.00–10.00. Waktu input boleh berbeda. MO Packing tidak dibatasi jam dapur. |
| Bahan | Kebutuhan semua MO aktif pada rekap/dapur dijumlahkan sekali. Petugas mengubah saran dan menyimpan satu permintaan beberapa SKU; Central menyiapkan satu picking list dan satu transfer. Permintaan buffer dapat tanpa rekap. |
| Transfer | Dapur → Packing langsung diterima sejumlah yang dikirim, tanpa transit. Central → dapur tetap memiliki tahap kirim/terima. Antar dapur tetap menggunakan transfer inventori. |
| Supplier | PO memiliki tujuan Central/Packing; cetak PO dan penerimaan mengikuti tujuan itu. PO lama tanpa tujuan tetap mengacu Central. |
| Paket | MO perakitan memakai BOM normal, tanpa WO, mengurangi komponen dan menambah SKU paket di Packing. Konsumsi mengikuti paket yang benar-benar dirakit. |
| Alokasi | SO dilindungi terlebih dahulu, termasuk komponen paket yang belum dirakit. Sisa dibagi proporsional ke RO; petugas dapat mengubahnya. Pemeriksaan diulang saat membuat DO dan mengirim. |
| DO dan jadwal | DO SO terbentuk saat konfirmasi. DO toko dibentuk dari alokasi sesudah DO SO. Cetak tidak mengurangi stok; kirim mengurangi stok. DO toko terhubung ke transfer dan penerimaan toko. Tiga sesi serta jadwal setiap toko dapat diatur per tanggal tanpa pergeseran hari otomatis. |

## Mulai menggunakan

1. Masuk sebagai Admin. Pastikan master gudang, dapur, produk, satuan dan BOM benar.
2. Buka **Konfigurasi produksi → Pengaturan Packing & waktu**. Pilih Packing dan zona waktu; default formulir `Asia/Jakarta`. Tinjau tiga jam sesi awal sebelum menyimpan.
3. Pada setiap produk yang dibuat, pilih dapur dan BOM utama. Produk paket menggunakan jenis **Paket Packing**, dengan BOM yang tidak menunjuk dapur. Produk setengah jadi menggunakan jenis **Setengah jadi**.
4. Atur minimum produk per gudang dan lingkup gudang pengguna. Label peran baru: **Admin / petugas produksi**, **Admin Sales**, **Petugas Packing**, **Petugas toko**. Peran lama tetap tersedia.
5. Buka **Manufaktur & Packing**. Input dan konfirmasi RO/SO, konsolidasikan pada tab Rekap, lalu tekan **Buat MO / WO dapur**.
6. Dari **Bahan dapur**, pilih rekap/dapur, hitung saran, ubah jumlah, lalu simpan permintaan. Central membuat picking/transfer, mencetak picking list dan mengirim. Dapur mencatat penerimaan.
7. Catat hasil WO beserta waktu pelaksanaan fisik. Kirim hasil ke Packing. Untuk paket, buat MO perakitan dari rekap atau MO manual lalu catat hasil perakitan.
8. Tinjau DO SO, hitung alokasi toko dan buat DO toko. Atur jadwal harian, cetak DO dan catat pengiriman. Penerimaan toko menyelesaikan transfer terkait.

RO/SO pada versi ini adalah input baru dalam aplikasi ini. Belum ada sinkronisasi ke aplikasi sales lain, POS, atau repository ERP lain. Kolom referensi eksternal adalah penanda manual, bukan mekanisme sinkronisasi.

## Pilihan teknis yang terlihat oleh petugas

- **Saran bahan:** kebutuhan WO + minimum − stok bebas dari reservasi aktif, paling kecil nol. Stok fisik, reservasi, dan barang dalam perjalanan ditampilkan terpisah. Barang dalam perjalanan belum otomatis mengurangi saran. Jumlah akhir tetap pilihan petugas. Ini penyelesaian awal atas detail saran yang masih terbuka pada PRD, bukan larangan tambahan.
- **Pembulatan alokasi:** kelipatan default 1 satuan dasar, dapat diubah pada master produk (misalnya 0,0001 kg). Saran memakai pembagian proporsional dengan sisa pembulatan terbesar; nilai sama diurutkan berdasarkan baris sumber. Jumlah saran tidak melebihi persediaan. Petugas tetap dapat mengubah jumlah akhir.
- **Prioritas SO:** seluruh DO SO yang belum dikirim dari Packing dipertimbangkan. Sistem tidak membagi otomatis kekurangan antar SO. Jika jumlah untuk satu DO SO belum tersedia, DO tetap menunggu dan Admin Sales menangani melalui SOP.
- **Snapshot BOM:** MO menyimpan kebutuhan dalam satuan dasar sehingga perubahan master BOM tidak mengubah konsumsi MO yang sudah dibuat. BOM paket SO dibekukan pada konfirmasi untuk menjaga kebutuhan komponen dan DO konsisten.
- **Batch/ED:** mekanisme penerimaan supplier yang sudah ada dipertahankan. Pada pencatatan hasil manufaktur baru, nomor batch awal adalah nomor MO dan ED dapat dikosongkan; histori batch lama tidak dihapus atau dihitung ulang. Stok tanpa ED ditampilkan sebagai belum diisi, bukan dianggap kedaluwarsa.
- **Pencatatan:** jam mulai/selesai adalah waktu pelaksanaan fisik yang diinput petugas; server memvalidasi rentang shift. Sistem tidak mengobservasi produksi fisik secara langsung. Cutoff RO/SO, kapasitas, target bahan sebelum 16.00, dan larangan stok Packing menginap tetap mengikuti SOP.
- **Paket bertingkat** belum disediakan. Contoh paket A/B/C dari dapur dan D supplier ditangani; bahan setengah jadi tetap melalui buffer dan produksi manualnya.

## Penyimpanan dan integritas

Tidak ada migrasi ke tabel SQL baru. Database tetap memakai `app_state` berisi JSON dengan nomor versi, dan tabel akun yang sudah ada.

| ERD logis | Representasi implementasi |
|---|---|
| Produk, gudang, dapur, BOM | `products`, `warehouses`, `kitchens`, `boms` yang sudah ada. Relasi produksi: `products[].manufacturing`. |
| Minimum barang–gudang | `products[].minimumByWarehouse[warehouseId]`. Nilai yang belum diisi memakai nilai lama sebagai fallback. |
| Order / baris sumber | `manufacturing.orders[].lines[]`, dengan tipe RO/SO dan referensi sumber. |
| Kelompok rencana / kebutuhan | `manufacturing.plans[].requirements[]`, ditautkan ke `orderId` dan `orderLineId`. |
| MO / WO / hasil / konsumsi | `productions[]` bertanda `manufacturingVersion: 1`; WO ada dalam `workOrder`, BOM dalam `bomSnapshot`, sumber dalam `sources`, konsumsi dalam `ingredientsUsed`. MO Packing tidak memiliki WO. |
| Permintaan bahan / picking | `manufacturing.requests[]` beserta `lines` dan tautan `transferId`. Picking memakai kuantitas permintaan akhir. |
| Transfer / stok / gerakan | `transfers`, `batches`, `movements`, `reservations` yang sama dengan inventori. Tidak ada saldo manufaktur kedua. |
| Alokasi / DO / jadwal | `manufacturing.allocations`, `manufacturing.deliveries`, `manufacturing.schedules`. |
| Transaksi logis | Satu perintah server + satu pembaruan versi database. Semua pergerakan satu perintah berhasil bersama atau tidak tersimpan sama sekali. |

Perintah manufaktur memvalidasi stok, role dan lingkup gudang di server. Pembaruan memakai compare-and-swap pada versi database yang sama dengan inventori. Konflik mengembalikan HTTP 409; pengguna memuat ulang sebelum mencoba lagi. Permintaan dengan ID yang sama dapat diulang setelah gangguan jaringan tanpa membukukan stok dua kali.

`PUT /api/state` lama juga diperiksa agar stok tidak negatif atau lebih kecil dari reservasi aktif, dan perubahan jumlah per produk/gudang sesuai penambahan catatan pergerakan. Histori pergerakan tidak boleh diubah melalui jalur ini. Jalur itu tidak boleh mengubah dokumen manufaktur, konfigurasi produksinya, maupun transfer yang dikelola perintah manufaktur. Pengaturan ulang data tetap merupakan tindakan Admin tersendiri yang disengaja melalui layar reset yang sudah ada; bukan bagian proses produksi.

Riwayat `productions` lama tetap ada di **Riwayat lama**. Jadwal lama yang belum selesai dan belum mencatat konsumsi dapat diadopsi menjadi MO/WO melalui tombol yang disediakan; catatan lama tetap ditautkan. Produksi selesai lama tidak dihitung ulang. Migrasi browser tidak lagi menyuntikkan produk, BOM atau gudang demo ke data operasional yang sudah ada.

## API

Sesi login/cookie aplikasi tetap digunakan. Perintah selalu menyertakan versi dari `GET /api/state`.

```json
{
  "version": 12,
  "requestId": "UUID-unik-untuk-satu-tindakan",
  "action": "create_mo",
  "data": {
    "productId": 11,
    "qty": 100,
    "productionDate": "2026-10-30",
    "deliveryDate": "2026-10-31"
  }
}
```

- `POST /api/manufacturing/commands`: perubahan bisnis. Respons berisi `version`, `data`, `result`, dan `replayed`.
- `POST /api/manufacturing/preview`: saran tanpa pembukuan; action `material_preview` atau `allocation_preview`.
- Nama perintah lengkap berada pada `COMMANDS` di `app/manufacturing.py`. Input tambahan seperti jumlah hasil, waktu fisik, baris permintaan dan alokasi mengikuti formulir UI serta contoh pada tests.

## Menjalankan pembaruan

Dari direktori checkout repository pada server:

```bash
git pull --ff-only origin main
docker compose up -d --build app
docker compose logs --tail=50 app
```

Compose tetap memakai volume MariaDB yang sama. Pembaruan ini tidak menjalankan reset data, tidak memanggil `down -v`, dan tidak memindahkan akun. Dockerfile menyalin modul server baru dan memasang basis data zona waktu Python.

## Pengujian

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-test.txt
.venv/bin/python -m playwright install chromium
.venv/bin/pytest -q
```

Hasil verifikasi lokal: **41 pengujian lulus**, termasuk tiga skenario browser Chromium. Pemeriksaan sintaks Python/JavaScript dan whitespace diff juga lulus.

Pengujian mencakup:

- Dua MO satu dapur menghasilkan satu kebutuhan gabungan; 15 + 5 − 7 memberi saran 13; perubahan petugas masuk ke transfer beberapa SKU.
- WO 100 dengan hasil 95, 105, dan 0; penggunaan bahan tetap; tidak ada backorder; minimum dapat dihabiskan ke nol.
- Pergantian BOM setelah MO dibuat, konversi satuan, produksi setengah jadi tanpa turunan, shift lintas tengah malam, pencatatan terlambat.
- Paket P100 dari A/B/C/D, A hanya tersedia150 untuk kebutuhan SO100 dan RO100; prioritas komponen SO, perakitan, alokasi20/30 yang diubah35/15, DO dan penerimaan toko.
- Transaksi dua pengguna pada versi sama, dua MO berebut bahan yang sama, rollback ketika bahan kedua kurang, dan pengulangan request setelah jawaban jaringan hilang.
- Larangan perubahan dokumen manufaktur lewat state mentah, stok negatif/nonfinite, serta akses gudang/role.
- Browser Chromium: konfigurasi produk, MO, hasil, transfer langsung, RO/SO, rekap, alokasi, DO, PO supplier langsung ke Packing, dan halaman inventori lama; tampilan desktop dan lebar390px.

Tes database lokal memakai SQLite melalui SQLAlchemy; deployment Docker/MariaDB dan uji penerimaan petugas pada instalasi operasional belum dijalankan. Tidak ada data dari instalasi operasional yang dipakai dalam tes. POS, akuntansi rinci, konsinyasi khusus dan spesial MO dari Central tetap di luar versi ini.
