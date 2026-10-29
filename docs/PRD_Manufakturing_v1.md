# PRD — Modul Manufakturing dan Integrasi Inventori

**Versi:** 1.0 — draf untuk ditinjau Feri  
**Tanggal:** 29 Oktober 2026  
**Acuan proses:** Odoo 19 dan keputusan diskusi Feri  
**Pasangan dokumen:** [ERD_Manufakturing_v1.md](ERD_Manufakturing_v1.md)  
**Ringkasan keputusan:** [Ringkasan konteks manufakturing](https://github.com/yussyakmal-dotcom/app-erp/blob/main/docs/Ringkasan_Konteks_Manufakturing_Feri_2026-10-29.md)

Dokumen ini menjelaskan kebutuhan produk dan batas integrasinya. ERD pasangannya adalah rancangan data logis untuk didiskusikan, bukan perintah migrasi database atau bukti bahwa fitur telah dibangun. Contoh perhitungan memakai asumsi yang disebutkan secara eksplisit.

## 1. Tujuan

Menghubungkan permintaan toko dan pesanan customer dengan produksi beberapa dapur, penyediaan bahan dari Gudang Central, perakitan paket di Packing, dan penyiapan dokumen pengiriman. Petugas tetap mengendalikan rencana dan dapat mengubah saran sistem. Sistem menjaga agar pembukuan pergerakan barang tidak membuat stok minus.

Hasil yang diharapkan:

1. Kebutuhan yang diproduksi bersama direkap menjadi satu MO per SKU, dengan asal RO toko dan SO tetap terlacak.
2. Kebutuhan bahan seluruh MO satu dapur direkap agar admin dapat membuat satu permintaan multi-SKU ke Central dan petugas Central mempunyai satu picking list untuk permintaan tersebut.
3. Satu WO dapur menjadi acuan satu kali produksi; konsumsi bahan mengacu kuantitas WO, sedangkan stok hasil bertambah sesuai hasil baik aktual.
4. Hasil dapur berpindah langsung ke Packing. Paket dirakit di Packing menggunakan BOM dan MO perakitan tanpa WO.
5. SO didahulukan; sisa untuk toko disarankan proporsional dan dapat diubah petugas.

Indikator yang dapat dipantau adalah pemenuhan SO dan RO, hasil baik dibanding jumlah WO, kekurangan/kelebihan produksi, serta selisih stok. **Stok minus harus nol**; target angka lain belum ditetapkan oleh Feri.

## 2. Cakupan dan batas

**Dalam cakupan:** master dapur, penunjukan dapur pada produk, BOM dapur dan paket, minimum stok per barang dan gudang, konsolidasi kebutuhan RO/SO, MO dan WO dapur, permintaan bahan dan picking Central, pencatatan hasil, transfer Dapur → Packing, MO perakitan, prioritas alokasi dan batas integrasi DO.

RO, SO, PO, transfer inventori, dan DO dibahas sepanjang dibutuhkan untuk proses ini. Produk supplier untuk komponen paket dibeli melalui PO dan dapat diterima langsung di Packing.

**Di luar pembahasan saat ini:** penjualan POS, desain proses konsinyasi, MO spesial dari Central, perhitungan HPP/akuntansi yang rinci, serta perubahan fungsi inventori lain yang tidak diperlukan. Konsinyasi sementara masih melalui PO supplier. Pengaturan batch/expired dan migrasi data lama tidak ditetapkan sebagai keputusan bisnis baru di dokumen ini.

Odoo 19 adalah **referensi alur**, bukan keputusan untuk mengganti aplikasi inventori yang ada dengan Odoo. Kecocokan fitur standar dan penyesuaian aplikasi harus dibedakan.

Istilah yang dipakai: **RO** = permintaan barang toko ke Packing; **SO** = Sales Order customer; **MO** = Manufacturing Order; **WO** = Work Order; **BOM** = daftar komponen dan kuantitas produk; **DO** = Delivery Order; **PO** = Purchase Order. RO pada dokumen ini berarti permintaan toko, bukan istilah *reordering rule* Odoo.

## 3. Kondisi aplikasi yang diperiksa

Pemeriksaan baca-saja dilakukan pada repository `yussyakmal-dotcom/app-erp`, branch `main`, pada 29 Oktober 2026. Ini adalah temuan dari kode yang diperiksa, bukan klaim mengenai data atau instalasi yang sedang berjalan.

| Temuan di kode | Implikasi terhadap kebutuhan |
|---|---|
| `app/static/index.html` sudah memiliki `kitchens`, `boms`, `productions`, serta fungsi membuat rencana, memulai, dan menyelesaikan produksi. | Gunakan fondasi yang relevan; jangan menganggap modul sudah memenuhi alur MO/WO yang disepakati. |
| Rencana produksi saat ini memilih BOM dan dapur; penyelesaian memakai `calculateBomRequirements(bom, actualQty, ...)`. | Perlu diubah: produk menentukan dapur/BOM dan bahan dihitung dari kuantitas WO, bukan hasil baik aktual. |
| Perhitungan minimum saat ini memakai `minCentral` atau `minBranch`. | Perlu pengaturan minimum berbeda untuk setiap pasangan barang–gudang. |
| Transfer yang ada memiliki beberapa SKU, picking/reservasi, pengiriman dan penerimaan; pembuatan draft memeriksa akses gudang asal. | Kebutuhan dapur harus dapat diajukan oleh Admin Produksi, lalu diproses Central. Transfer Dapur → Packing membutuhkan alur langsung satu langkah. |
| Data operasional disimpan dalam JSON ber-versi pada `app_state`; backend menerima `PUT /api/state` dengan optimistic locking. Validasi transaksi persediaan utama terlihat di sisi antarmuka. | ERD pada pasangan dokumen adalah model logis. Larangan stok minus dan perubahan stok harus dijaga secara atomik oleh jalur penulisan yang berwenang, termasuk ketika dua petugas bekerja bersamaan. |
| Proses produksi yang diperiksa meminta nomor batch dan tanggal kedaluwarsa, serta mengizinkan tujuan hasil dipilih. | Dampak terhadap data dan proses lama perlu dianalisis sebelum implementasi; jangan menambah aturan baru atau mengubah histori tanpa kesepakatan. Hasil produksi dapur untuk alur ini masuk dapur terlebih dahulu. |

Pada kode yang diperiksa belum ditemukan alur RO toko, SO dan DO yang dapat langsung dianggap memenuhi rancangan ini. Ketiganya diperlakukan sebagai sumber atau integrasi yang harus dipetakan ke sistem yang akan digunakan, bukan dianggap sudah tersedia.

## 4. Aktor dan lokasi

| Aktor | Tanggung jawab dalam alur |
|---|---|
| Petugas toko | Membuat RO berisi satu atau lebih SKU kepada Packing. |
| Admin Sales | Mencatat SO; memahami kapasitas dan menangani order berlebih melalui SOP. |
| Admin Produksi | Merekap kebutuhan, menyiapkan MO/WO dapur dan mengajukan permintaan bahan tiap dapur. |
| Petugas Central | Membuat picking list, mengambil bahan dan mengirim permintaan dapur. |
| Petugas dapur | Melaksanakan WO, mencatat hasil sesuai pembagian tugas, dan memindahkan hasil ke Packing. |
| Petugas Packing | Merakit paket, mencetak DO SO, menentukan alokasi toko dan membuat DO toko. |
| Petugas master data | Mengelola produk, dapur, BOM dan minimum per gudang sesuai kewenangan. |

Nama aktor adalah peran bisnis; pemetaan ke role akun aplikasi yang ada masih perlu ditentukan. Tidak ada proses persetujuan tambahan yang diwajibkan oleh PRD ini.

**Lokasi:** satu Central menerima bahan dari supplier dan memasok dapur; setiap dapur adalah gudang produksi; antar dapur dapat melakukan internal transfer; Packing menerima hasil dapur dan produk supplier langsung; toko menerima kiriman Packing. Dapur dan Packing berada dalam satu area untuk transfer langsung satu langkah.

## 5. Aturan yang disepakati

### 5.1 Aturan yang harus dijaga sistem

| ID | Aturan |
|---|---|
| BR-01 | Pergerakan stok tidak boleh membuat saldo sumber minus. Periksa ulang saat transaksi pengurangan dibukukan. Minimum bukan stok yang dikunci: stok boleh dipakai sampai nol. |
| BR-02 | Pelaksanaan produksi fisik di dapur mengacu pada pukul 20.00 sampai 10.00 keesokan harinya. Pembuatan MO/WO boleh sebelum dan selama shift; pencatatan hasil mengikuti SOP dan tidak otomatis ditolak karena dicatat setelah pukul 10.00. |
| BR-03 | Untuk kebutuhan yang dibuat bersama, satu MO produksi dapur per SKU dan satu WO sebagai acuan sekali produksi. Tidak ada WO bertingkat untuk produk tersebut. |
| BR-04 | Konsumsi bahan dihitung dari BOM dan kuantitas WO, bukan hasil baik aktual. Hasil kurang dianggap rusak; hasil lebih dicatat sebagai kelebihan. Tidak dibuat backorder/produksi susulan untuk kekurangan hasil WO. |
| BR-05 | SO diprioritaskan atas RO toko. Saran pembagian toko proporsional terhadap RO dan dapat diubah petugas, selama alokasi serta pembukuan tidak membuat stok minus. |
| BR-06 | Dapur → Packing langsung satu langkah: pada pencatatan transfer stok dapur berkurang dan stok Packing bertambah dengan kuantitas yang sama, tanpa transit atau penerimaan terpisah. |
| BR-07 | Paket adalah SKU utuh dengan harga paket sendiri. Packing menggunakan MO perakitan dengan BOM paket tanpa WO; perakitan dapat dilakukan kapan saja jika komponen tersedia. |
| BR-08 | DO SO dapat terbentuk saat SO dikonfirmasi, dengan kuantitas per produk/paket sesuai SO; dicetak di Packing saat barang siap. DO SO disiapkan lebih dahulu, kemudian DO toko. |

BR-02 membedakan **pelaksanaan fisik** dan **waktu input**. Rancangan teknis harus menjaga perbedaan ini; jangan membuat satu validasi waktu server yang otomatis menolak input hasil setelah 10.00.

### 5.2 Aturan operasional/SOP

- RO toko diajukan setiap hari untuk kebutuhan dua hari ke depan; contoh RO tanggal 3 untuk ketersediaan tanggal 5. Batas RO pukul 07.00; tidak diasumsikan ada tambahan dalam rencana yang sudah ditutup.
- SO masih diterima H−1 sampai pukul 15.00. Admin Sales menangani order yang melebihi kapasitas melalui SOP.
- WO direncanakan diterima dapur sebelum 20.00 dan kekurangan bahan ditargetkan terkirim ke dapur sebelum 16.00. Jangan menambahkan pengunci sistem baru atas waktu tersebut.
- Packing mempunyai tiga sesi pengiriman setiap hari; waktunya dapat diubah. Setiap hari ada jadwal ke semua toko, tanpa mengasumsikan semua toko menerima pada ketiga sesi. Jadwal tidak melompat dari tanggal kirim yang dipilih ke hari lain.
- Barang tidak menginap di Packing. Jika fisik belum keluar, stok tidak boleh dihapus atau dipalsukan agar tampak nol.
- Tanggal order, produksi dan kirim penting sebagai data perencanaan. Perbedaan tanggal dan penanganan pengecualian mengikuti SOP; tidak menjadi pengunci baru tanpa keputusan Feri.

## 6. Alur utama

1. Toko membuat RO ke **Packing**, bukan ke dapur. SO customer dicatat untuk pemenuhan pada hari yang direncanakan; DO SO dapat langsung terbentuk saat SO dikonfirmasi.
2. Packing merekap RO dan SO yang akan diproduksi bersama. Jika permintaan berupa paket, kebutuhan diturunkan dari BOM paket ke produk komponennya; produk belum diasumsikan ada di Packing.
3. Kebutuhan setiap SKU buatan dapur dikonsolidasikan. Admin membuat MO dan WO dapur secara manual; sistem mengenali dapur dan BOM dari master produk. Sumber tiap kebutuhan tetap dapat ditelusuri.
4. Semua MO satu dapur direkap bahan per SKU. Sistem menunjukkan stok, minimum dan saran; Admin Produksi mengubah jumlah jika perlu dan mengajukan satu permintaan multi-SKU untuk kelompok tersebut. Buffer juga dapat diminta tanpa WO.
5. Central menyiapkan **satu picking list berdasarkan jumlah yang diminta petugas**, lalu satu transfer multi-SKU ke dapur. Penerimaan dapur mengikuti alur transfer yang digunakan untuk Central → dapur.
6. Dapur menjalankan satu WO dalam jam produksi dan mencatat hasil baik. Sistem membukukan pemakaian berdasarkan WO dan menambah hasil aktual di dapur.
7. Dapur mentransfer hasil ke Packing satu langkah. Packing juga dapat menerima komponen supplier langsung melalui PO.
8. Bila semua komponen paket tersedia di Packing, petugas menjalankan MO perakitan dengan BOM paket tanpa WO. Komponen berkurang dan SKU paket utuh bertambah secara konsisten.
9. Kebutuhan SO diprioritaskan. DO SO yang sudah terbentuk dicetak ketika barang siap; kemudian DO toko disiapkan dari alokasi sisa. Pembuatan/cetak DO bukan pengurangan fisik stok; saat pengiriman dibukukan stok diperiksa kembali.

Perbedaan waktu RO dan SO di atas tidak memerintahkan sistem membuat MO susulan: rencana dapat disiapkan sesuai SOP dan konsolidasi berlaku untuk kebutuhan yang memang dibuat bersama.

## 7. Kebutuhan fungsional

| ID | Kebutuhan |
|---|---|
| FR-01 | Produk buatan dapur mempunyai dapur pembuat di master produk. Saat admin memilih produk pada MO dapur, sistem mengenali dapur dan BOM yang berlaku; petugas tidak memilih BOM. Penyelesaian jika lebih dari satu BOM berlaku belum ditetapkan. |
| FR-02 | BOM mencatat produk hasil, kuantitas hasil, satuan dan komponen. BOM paket dipakai MO perakitan Packing. Perubahan BOM tidak boleh diam-diam mengubah riwayat produksi yang telah dibukukan; mekanisme versi/snapshot merupakan rancangan yang perlu dicocokkan. |
| FR-03 | Nilai minimum diatur per barang per gudang dan dapat diubah petugas. Nilai barang yang sama boleh berbeda antar dapur. |
| FR-04 | Baca RO dan SO serta rincian SKU, kuantitas, tujuan dan tanggalnya. Rencana konsolidasi menyimpan hubungan ke sumber agar kebutuhan setiap toko/SO tetap diketahui. |
| FR-05 | Untuk setiap kelompok kebutuhan yang diproduksi bersama, rekap per SKU menjadi satu MO dapur, dengan kuantitas yang dapat ditelusuri ke sumber. Produk supplier untuk paket mengikuti PO, bukan MO dapur. |
| FR-06 | Admin menyiapkan MO dan satu WO produksi dapur secara manual. Sistem menampilkan kebutuhan BOM untuk kuantitas WO dan gudang dapur terkait. Pembuatan/penyiapan boleh sebelum dan selama shift. |
| FR-07 | Produk setengah jadi memiliki buffer dan rencana sendiri. MO/WO-nya dibuat manual dan tidak otomatis dibuat sebagai turunan MO produk jadi. |
| FR-08 | Rekap bahan dari seluruh MO relevan pada satu dapur per SKU, tanpa mengurangi stok dapur yang sama berulang kali. Tampilkan saran dan izinkan admin mengubah jumlah yang diminta. |
| FR-09 | Satu permintaan bahan dapur untuk satu kelompok rekap berisi beberapa SKU, disampaikan ke Central. Permintaan buffer dapat dibuat terpisah dari WO. |
| FR-10 | Petugas Central membuat satu picking list dari permintaan, sesuai jumlah yang diminta admin, dan menyiapkan satu transfer multi-SKU ke dapur. Stok Central tidak boleh minus saat dikirim. |
| FR-11 | Saat WO selesai dicatat, konsumsi bahan mengikuti jumlah WO dan BOM; hasil baik masuk stok dapur sesuai jumlah aktual. Tampilkan jumlah kurang yang dianggap rusak atau jumlah lebih. Tidak membuat backorder atau MO susulan untuk kekurangan WO. |
| FR-12 | Transfer hasil Dapur → Packing dilakukan satu langkah, dengan kuantitas masuk sama dengan kuantitas keluar. Tidak ada proses transit/penerimaan terpisah pada jalur ini. |
| FR-13 | Packing dapat membuat/menjalankan MO perakitan untuk SKU paket menggunakan BOM, tanpa WO dan di luar batas jam produksi dapur. Ketika selesai dibukukan, kurangi komponen dan tambah paket utuh dalam transaksi yang konsisten. |
| FR-14 | Prioritaskan SO. Setelah kebutuhan SO diperhitungkan, sarankan pembagian sisa kepada toko secara proporsional berdasarkan RO; petugas dapat mengubah saran. Tampilkan kuantitas tersedia dan asal kebutuhan. |
| FR-15 | Hubungkan DO SO dengan SO dan kuantitas yang sama; DO dapat terbentuk ketika SO dikonfirmasi dan dicetak di Packing ketika siap. DO toko dibuat setelah DO SO, berdasarkan hasil alokasi petugas. Jangan menganggap SO sudah terkirim hanya karena DO dibuat atau dicetak. |
| FR-16 | Catat sumber dan tujuan pergerakan, referensi dokumen, SKU, satuan, kuantitas, waktu dan petugas sesuai mekanisme audit aplikasi. Pembuatan rencana atau saran tidak dihitung sebagai pergerakan stok. |

### 7.1 Saran kebutuhan bahan

Rumus dasar yang disetujui Feri, **per SKU per dapur**, untuk contoh tanpa barang masuk dalam perjalanan atau kebutuhan/komitmen lain:

`saran = maksimum(0, total kebutuhan WO + stok minimum − stok tersedia)`

Contoh: kebutuhan 15 kg, minimum 5 kg, stok tersedia 7 kg → **saran 13 kg**. Petugas dapat mengubah angka tersebut. Bila petugas meminta 8 kg dan produksi memakai 15 kg, stok dapat menjadi 0; minimum tidak menghalangi pemakaian.

Perlakuan transfer dalam perjalanan, reservasi lain, horizon perencanaan dan pembulatan belum diputuskan. Tidak boleh mengklaim rumus ini telah menyelesaikan seluruh kondisi tersebut.

### 7.2 Pengurangan dan hasil produksi

Contoh WO 100 roti memakai 10 kg tepung berdasarkan BOM:

| Hasil baik aktual | Tepung dibukukan | Selisih | Stok roti baik masuk |
|---:|---:|---|---:|
| 95 | 10 kg | 5 dianggap rusak | 95 |
| 100 | 10 kg | Sesuai | 100 |
| 105 | 10 kg | 5 kelebihan produksi | 105 |

Selisih kurang merupakan hasil perhitungan, tidak otomatis bukti adanya persediaan fisik terpisah sebanyak barang rusak. Jangan mengurangi hasil baik 95 sekali lagi. Penggunaan fisik yang berbeda dari BOM tidak otomatis diketahui sistem; penanganannya mengikuti SOP.

## 8. Contoh terpadu

Asumsi tidak ada stok produk jadi tambahan untuk contoh ini. SO meminta **100 Paket P**, masing-masing berisi A, B, C dan D. RO seluruh toko meminta **100 Produk A**. A/B/C diproduksi di dapur sesuai master; D dibeli dari supplier langsung ke Packing.

| Produk | RO toko | Kebutuhan isi SO | Rekap | Sumber |
|---|---:|---:|---:|---|
| A | 100 | 100 | 200 | Dapur pembuat A |
| B | 0 | 100 | 100 | Dapur pembuat B |
| C | 0 | 100 | 100 | Dapur pembuat C |
| D | 0 | 100 | 100 | PO supplier ke Packing |

Admin menyiapkan satu MO A untuk 200, serta MO B dan C masing-masing untuk kebutuhannya. Jika dapurnya sama, kebutuhan bahan dari MO-MO tersebut direkap untuk satu permintaan Central pada kelompok itu. Anggap hasil baik A hanya 150: komponen WO A tetap dibukukan sesuai 200; 50 dianggap rusak dan tidak ada MO susulan.

Setelah A, B, C dan D **fisik tersedia di Packing**, MO perakitan tanpa WO memakai 100 tiap komponen untuk menghasilkan 100 Paket P. DO SO berisi 100 Paket P. Sisa 50 A untuk toko disarankan proporsional terhadap RO dan dapat diubah petugas; DO toko disiapkan setelah DO SO. Contoh ini tidak mengasumsikan paket sudah tersedia ketika SO dibuat.

## 9. Antarmuka dan laporan yang diperlukan

| Area | Informasi/tindakan utama |
|---|---|
| Master produk dan dapur | Produk, dapur pembuat, BOM yang berlaku, serta minimum per gudang yang dapat diubah. |
| Rekap kebutuhan | RO/SO sumber, SKU, tanggal yang relevan, kebutuhan paket dan komponennya, kelompok produksi dan MO per SKU. |
| MO/WO dapur | Produk, dapur, BOM otomatis, kuantitas WO, kebutuhan bahan, status, hasil baik, selisih kurang/lebih dan rujukan sumber. |
| Permintaan bahan | Dapur, daftar bahan, kebutuhan, stok, minimum, saran dan jumlah akhir yang diminta petugas. |
| Picking Central | Referensi permintaan, tujuan dapur, seluruh SKU dan kuantitas yang diminta untuk diambil. |
| Packing | Produk yang sudah masuk, MO perakitan paket, SO prioritas, saran/pengubahan alokasi toko, DO dan jadwal kirim. |
| Ketertelusuran | Dari RO/SO ke rekap, MO/WO, kebutuhan bahan, transfer, hasil, perakitan dan pengiriman yang berkaitan. |

Nama halaman, detail status, siapa yang memasukkan hasil dan hak akses aktual masih dapat disesuaikan dengan operasi; tabel ini bukan desain layar final.

## 10. Pencocokan dengan Odoo 19

| Topik | Temuan dokumentasi / kebutuhan pengujian |
|---|---|
| MO, BOM, satu langkah | Odoo mengisi BOM saat memilih produk dan mendukung manufaktur satu langkah. Jika BOM memiliki operasi, daftar WO dapat terisi. Pemetaan ke WO dapur manual dan tepat satu kali produksi perlu diuji. |
| Kekurangan hasil | Odoo memiliki proses backorder manufaktur; rancangan Feri tidak membuatnya untuk kekurangan hasil WO. Perhitungan bahan tetap berdasarkan WO awal juga harus diuji. |
| Minimum dan replenishment | Odoo mendukung aturan minimum–maksimum dan saran manual. Feri meminta pengaturan minimum per gudang dan rumus dasar di bagian 7.1; kesetaraan konfigurasi harus diuji. |
| Transfer | Odoo mendukung transfer internal langsung antar lokasi. Rute pengisian antargudang yang terdokumentasi dapat memakai pengiriman, transit dan penerimaan; jangan gunakan itu untuk Dapur → Packing satu langkah. |
| Paket | Kit standar Odoo menampilkan komponen di DO. Untuk SKU paket utuh, Feri menyetujui BOM normal dan MO perakitan tanpa WO; uji konfigurasi dan integrasi aplikasi. |
| SO dan DO | Odoo dapat membuat DO saat SO dikonfirmasi. Pastikan hasil akhir DO sesuai kuantitas SO dan alur pencetakan di Packing; jangan menganggap pembuatan DO sebagai pengiriman. |
| Alokasi | Odoo memiliki laporan alokasi MO terhadap SO; otomatisasi prioritas SO dan saran proporsional per RO toko belum terbukti sesuai kebutuhan ini dan perlu diuji/penyesuaian. |
| Stok minus | Dokumentasi Odoo menunjukkan stok negatif dapat terjadi. Larangan minus harus dijaga khusus dalam implementasi; tidak boleh diasumsikan otomatis terjamin. |

## 11. Integritas, keamanan, dan batas implementasi

1. Semua jalur yang mengurangi stok—pemakaian produksi, transfer, perakitan dan pengiriman—harus memeriksa saldo sumber pada saat pembukuan. Hasil tidak boleh minus, termasuk saat dua pengguna bekerja bersamaan.
2. Pembukuan konsumsi bahan dan hasil satu MO, atau pengurangan dan penambahan pada transfer langsung/perakitan, harus konsisten sebagai satu operasi; kegagalan tidak boleh meninggalkan separuh pembukuan.
3. Rekomendasi teknis untuk aplikasi yang diperiksa: validasi transaksi stok di server dan lindungi seluruh jalur penulisan agar penggantian JSON mentah tidak melewati aturan. JSON ber-versi dengan kontrol konkurensi atau penyimpanan lain dapat dipertimbangkan; ERD ini tidak memerintahkan migrasi ke tabel relasional.
4. Rencana, saran, pencetakan dan reservasi tidak sama dengan pengurangan stok fisik. Penanganan reservasi dan barang dalam perjalanan dalam rumus saran masih perlu dicocokkan.
5. Pertahankan data dan histori inventori yang ada. Penyesuaian format atau migrasi hanya dilakukan dengan strategi yang disepakati; histori konsumsi lama tidak otomatis dihitung ulang.
6. Akses mengikuti role dan gudang yang sesuai. Penambahan alur permintaan dari dapur perlu menghormati pemeriksaan hak gudang asal pada transfer Central yang sudah ada.

## 12. Kriteria penerimaan

| ID | Skenario | Hasil yang diharapkan |
|---|---|---|
| AC-01 | Toko membuat RO beberapa SKU. | RO ditujukan ke Packing; rincian toko, SKU, jumlah dan tanggal dapat direkap. |
| AC-02 | Kebutuhan A dari RO 100 dan SO 100 diproduksi bersama. | Satu MO dapur untuk A sejumlah 200 dengan tautan ke kedua sumber. |
| AC-03 | Admin memilih Produk A pada MO dapur. | Dapur dan BOM yang berlaku terisi dari master, tanpa pilihan BOM oleh petugas. |
| AC-04 | Dua MO dapur memerlukan tepung total 15 kg; stok 7 kg, minimum 5 kg; tidak ada faktor lain. | Sistem menyarankan 13 kg sekali untuk dapur tersebut. Admin boleh mengubahnya. |
| AC-05 | Admin meminta tepung 10 kg dan gula 2 kg setelah melihat saran. | Satu permintaan dan satu picking list Central berisi tepung 10 kg serta gula 2 kg. |
| AC-06 | Penggunaan buffer membuat stok tersisa 0. | Transaksi dapat dibukukan; minimum tidak menjadi pengunci. Transaksi yang membuat stok minus tidak dibukukan. |
| AC-07 | WO 100 roti, BOM 10 kg tepung, hasil baik 95. | Tepung berkurang 10 kg; roti baik bertambah 95; 5 dianggap rusak; WO selesai tanpa backorder/MO susulan. |
| AC-08 | WO sama menghasilkan 105 roti baik. | Bahan tetap untuk WO 100; stok bertambah 105 dan 5 dicatat sebagai kelebihan. |
| AC-09 | Produksi fisik dilakukan dalam shift, selesai 09.55 dan hasil diinput 10.05. | Input tidak otomatis ditolak karena jam input; stok tetap diperiksa pada pembukuan. |
| AC-10 | Dua pengguna berupaya mengurangi stok yang sama melebihi stok gabungan yang ada. | Operasi yang dibukukan tidak menghasilkan stok minus; konflik ditangani tanpa pembukuan ganda. |
| AC-11 | Dapur mentransfer 150 A ke Packing. | Stok dapur −150 dan Packing +150 dalam satu langkah; tidak ada penerimaan terpisah atau stok transit untuk jalur ini. |
| AC-12 | MO Packing 10 paket dengan BOM masing-masing 1 A/B/C/D; semua komponen tersedia. | Masing-masing komponen Packing berkurang 10 dan SKU paket bertambah 10; tanpa WO; bisa kapan saja. |
| AC-13 | Satu komponen paket tidak cukup saat MO perakitan hendak dibukukan. | Tidak terjadi pembukuan yang membuat stok komponen minus atau hasil paket tanpa konsumsi yang konsisten. |
| AC-14 | SO membutuhkan 100 A, RO toko total 100 A, tersedia 150 A. | SO diprioritaskan 100; 50 tersisa untuk toko. Untuk RO 40/60, saran awal 20/30. |
| AC-15 | Petugas mengubah saran toko 20/30 menjadi 35/15. | Perubahan dapat dicatat selama kuantitas total tidak melebihi ketersediaan. |
| AC-16 | SO 10 Paket P dikonfirmasi. | DO SO dapat langsung terbentuk dengan 10 Paket P; dicetak saat siap. DO toko dibuat setelah DO SO. |
| AC-17 | MO produk jadi membutuhkan produk setengah jadi. | Tidak otomatis dibuat MO/WO turunan; produksi setengah jadi mengikuti buffer dan rencana manualnya sendiri. |
| AC-18 | Barang masuk Packing pada hari kirim. | Barang fisik dan stok tercatat sesuai pergerakan; aturan tidak menginap ditangani melalui SOP, bukan dengan menghapus stok. |

## 13. Rencana kerja yang disarankan

1. **Cocokkan data dan alur yang ada:** produk/dapur/BOM, minimum, inventori dan transfer pada versi aplikasi yang akan digunakan; identifikasi sumber RO, SO, PO dan DO.
2. **Tetapkan pemetaan teknis:** cocokkan ERD logis dengan penyimpanan JSON dan API yang ada, atau rancang migrasi bila memang dipilih. Sepakati cara menjaga integritas stok pada semua jalur tulis.
3. **Susun dan uji integrasi inti:** master dan konsolidasi; permintaan bahan/picking; MO/WO dan hasil; transfer Packing; MO paket; alokasi dan DO. Tahap implementasi dan urutannya masih dapat disepakati.
4. **Uji bersama petugas:** jalankan skenario pada bagian 12, termasuk jumlah kurang/lebih, perubahan saran dan operasi bersamaan.

Detail stok dalam perjalanan/reservasi pada saran, pembulatan alokasi, sumber RO/SO/DO aktual, mekanisme WO manual terhadap operasi BOM Odoo, dan pemilihan BOM jika lebih dari satu tetap terbuka untuk pencocokan teknis. Jangan menjadikannya aturan penolakan baru secara sepihak.

## 14. Rujukan resmi Odoo 19

- [One-step manufacturing dan pengisian BOM](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/manufacturing/basic_setup/one_step_manufacturing.html)
- [BOM dan operasi](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/manufacturing/basic_setup/bill_configuration.html)
- [Manufacturing backorders](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/manufacturing/workflows/manufacturing_backorders.html)
- [Reordering rules](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/inventory/warehouses_storage/replenishment/reordering_rules.html)
- [Transfer internal langsung](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/barcode/operations/transfers_scratch.html)
- [Pengisian ulang antargudang dan transit](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/inventory/warehouses_storage/replenishment/resupply_warehouses.html)
- [Kit dan komponen pada DO](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/manufacturing/advanced_configuration/kit_shipping.html)
- [Alokasi hasil MO ke SO](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/manufacturing/reporting/allocation.html)
- [Stok negatif dan pergerakan stok](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/inventory/inventory_valuation/operations_valuation.html)


## Status implementasi awal

Implementasi awal tersedia dalam aplikasi inventori. Lihat [panduan implementasi manufaktur](IMPLEMENTASI_Manufakturing_v1.md) untuk pemetaan data nyata, fitur yang dibangun, pilihan awal atas detail teknis yang sebelumnya terbuka, cara menjalankan pembaruan, serta batas pengujian. Kriteria bisnis dalam PRD ini tetap menjadi acuan uji penerimaan petugas.
