# Ringkasan Konteks Manufakturing — Feri

**Tanggal ringkasan:** 29 Oktober 2026  
**Pembaruan terakhir:** 29 Oktober 2026 — keputusan terbaru tentang saran bahan, transfer dapur ke Packing, MO perakitan, dan DO.  
**Status:** ringkasan hasil diskusi dan acuan kelanjutan; bukan spesifikasi implementasi final.  
**Narasumber dan pengambil keputusan:** Feri.

## 1. Tujuan dan cara memakai dokumen ini

Dokumen ini menyimpan konteks rancangan modul manufakturing untuk ditambahkan ke aplikasi inventori yang sudah ada. Odoo 19 digunakan sebagai referensi alur; kemampuan standar Odoo dan kemampuan aplikasi inventori yang dimiliki Feri harus dibedakan.

Isi dokumen dipisahkan antara keputusan Feri, contoh atau usulan, dan hal yang masih perlu dicocokkan. Jika ada penjelasan lama yang bertentangan dengan koreksi terbaru Feri, gunakan koreksi terbaru.

Pembahasan saat ini berfokus pada **manufakturing dan hubungan yang diperlukan dengan inventori**. RO, SO, gudang Packing, dan transfer dibahas sebagai sumber kebutuhan atau titik integrasi. Pengembangan penjualan POS dan pembahasan konsinyasi belum termasuk lingkup saat ini. Sementara itu, konsinyasi masih ditangani melalui PO ke supplier.

Belum ada implementasi atau perubahan kode yang dilakukan dalam pembahasan ini.

## 2. Gambaran lokasi dan alur barang

| Lokasi | Peran dalam konteks manufakturing |
|---|---|
| Gudang Central | Titik masuk bahan dari supplier dan sumber pengiriman bahan untuk dapur. |
| Dapur | Gudang yang dapat mengubah bahan baku menjadi produk jadi atau setengah jadi. Setiap produk memiliki dapur pembuat yang ditentukan pada master produk. |
| Gudang Packing | Menerima RO toko, mengonsolidasikan kebutuhan, menerima hasil dapur, dan menyiapkan barang atau paket untuk tujuan pengiriman. |
| Toko | Mengirim RO ke Gudang Packing dan menerima barang dari Packing. Penjualan POS tidak menjadi pembahasan modul manufakturing saat ini. |
| Customer | Kebutuhannya dicatat melalui Sales Order (SO); kebutuhan produk yang diproduksi bersama dapat digabung dengan kebutuhan dari RO toko. |

Alur dasar: **RO toko ke Packing dan kebutuhan SO → konsolidasi per SKU → MO/WO per produk di dapur → rekap bahan per dapur → permintaan dan transfer bahan Central ke dapur → produksi → transfer langsung hasil dapur ke Packing → MO perakitan paket bila diperlukan → DO SO dan DO toko.**

Tambahan batas integrasi yang sudah disampaikan:

- Antar dapur dapat melakukan transfer internal.
- Produk supplier untuk isi paket dibeli melalui PO dan dapat dikirim langsung ke Packing, tanpa melalui Central.
- Dapur dan Packing berada dalam satu area. **Transfer Dapur → Packing satu langkah:** ketika transfer dicatat, stok dapur berkurang dan stok Packing langsung bertambah sejumlah yang dikirim. Tidak ada stok transit atau penerimaan terpisah untuk alur ini.
- Packing merakit produk dari beberapa dapur dan supplier menjadi paket menggunakan MO perakitan khusus dengan BOM paket, tanpa WO.
- Barang yang masuk Packing dapat berada di sana sementara pada hari yang sama, tetapi **tidak boleh menginap di Packing**. Ini adalah ketentuan operasional/SOP. Barang yang secara fisik belum keluar tidak boleh dihilangkan dari catatan stok hanya agar laporan terlihat nol.

## 3. Prinsip sistem dan SOP

### Aturan yang harus dijaga sistem

1. **Transaksi stok tidak boleh membuat stok menjadi minus.** Pengecekan dilakukan pada stok gudang/lokasi sumber yang relevan ketika transaksi pengurangan dibukukan.
2. **Pelaksanaan produksi di dapur mengacu pada jam 20.00–10.00 keesokan harinya.** Ini aturan waktu produksi, bukan larangan memasukkan data setelah pukul 10.00. Perakitan paket di Packing merupakan proses tersendiri yang dapat dilakukan kapan saja selama komponennya tersedia.

Pembuatan atau penyiapan MO dan WO dapur bisa dilakukan sebelum shift produksi dan selama shift berlangsung. MO/WO tambahan untuk kebutuhan produksi lain pernah dinyatakan memungkinkan; itu tidak berarti membuat MO susulan untuk mengganti hasil kurang dari WO yang sudah selesai.

Pencatatan mengikuti SOP. Misalnya, produksi fisik selesai pukul 09.55 dan hasil dicatat pukul 10.05: pencatatan tidak ditolak hanya karena sudah lewat jam 10.00. Stok tetap diperiksa ketika transaksi pengurangan dibukukan.

### Aturan operasional yang ditangani melalui SOP

- Admin Sales memahami kapasitas produksi dan mempunyai SOP untuk menangani order yang melebihi kapasitas.
- Sistem tidak perlu otomatis memecah MO atau menambahkan pembatasan order/kapasitas yang belum diminta.
- Toko memasukkan RO setiap hari untuk kebutuhan dua hari ke depan; contoh RO tanggal 3 untuk ketersediaan di toko tanggal 5.
- Batas penerimaan RO toko adalah pukul 07.00; dalam rencana yang ditutup tersebut tidak diasumsikan ada permintaan tambahan dari toko.
- SO masih dapat diterima H−1 sampai pukul 15.00.
- WO yang sudah disiapkan direncanakan diterima dapur sebelum pukul 20.00. Tambahan MO/WO untuk kebutuhan lain dapat disiapkan sebelum atau selama shift, sesuai keterangan Feri dan alur yang nanti disepakati.
- Target operasional: kekurangan bahan sudah **terkirim ke gudang produksi** sebelum pukul 16.00. Belum dipastikan apakah kata “terkirim” mensyaratkan barang sudah diterima secara fisik di dapur pada jam tersebut.
- Packing memiliki tiga sesi pengiriman setiap hari; jamnya dinamis dan dapat diubah. Setiap hari ada jadwal pengiriman ke seluruh toko; tidak disimpulkan bahwa setiap toko harus menerima barang pada ketiga sesi.
- Jadwal pengiriman tidak otomatis melompat ke hari berikutnya dari tanggal kirim yang dipilih.
- Tanggal order, tanggal produksi, dan tanggal kirim penting untuk perencanaan dan pencatatan. Pada awal diskusi disebut tanggal order berbeda dari tanggal produksi dan tanggal kirim. Penjelasan terbaru Feri menempatkan aturan waktu lainnya dalam SOP; jangan menjadikan perbedaan tanggal itu sebagai pengunci sistem baru. Penamaan tanggal operasional shift malam masih perlu diselaraskan jika diperlukan.

## 4. Permintaan toko, SO, dan konsolidasi produksi

1. Setiap toko mengajukan **RO kepada Gudang Packing**, bukan kepada dapur. Satu RO dapat berisi beberapa SKU.
2. Packing mengumpulkan RO toko yang menjadi satu rencana produksi.
3. Kebutuhan SO customer untuk SKU yang dibuat bersama digabung ke rekap SKU yang sama.
4. Rekap dikelompokkan per SKU. Untuk satu kelompok kebutuhan yang diproduksi bersama, hasilnya **satu MO per SKU**.
5. Sumber kebutuhan tiap toko/RO dan SO harus tetap dapat diketahui meskipun jumlahnya dikonsolidasikan. Penggabungan jumlah tidak menghapus rincian asal kebutuhan.
6. Admin menyiapkan MO dan WO produksi dapur secara manual. Sistem mengenali dapur pembuat dari master produk dan mengisi BOM produk secara otomatis; petugas tidak perlu memilih BOM.
7. Produk yang dibeli langsung dari supplier untuk isi paket mengikuti PO supplier, bukan MO dapur.

Contoh: RO seluruh toko membutuhkan 100 Produk A dan kebutuhan SO yang diproduksi bersama membutuhkan 100 Produk A. Rekap menghasilkan **satu MO Produk A berjumlah 200**, bukan satu MO per toko dan satu MO lain per SO.

Kelompok perencanaan dibuat untuk kebutuhan yang memang dikerjakan bersama. Jangan mengartikan satu MO per SKU sebagai satu MO untuk seluruh riwayat atau seluruh periode.

## 5. MO, WO, dan BOM untuk produksi dapur

- Satu MO produksi dapur berisi satu SKU produk untuk sejumlah unit produk tersebut. MO perakitan paket di Packing dibahas tersendiri pada bagian 10.
- Satu WO menjadi acuan **sekali produksi** untuk satu produk. Tidak ada rangkaian WO bertingkat untuk membuat produk tersebut.
- Produk A dibuat di dapur yang tercatat untuk Produk A; Produk B di dapur yang tercatat untuk Produk B.
- BOM terpasang otomatis saat produk dipilih pada MO.
- Bahan untuk satu WO dihitung berdasarkan **jumlah permintaan WO dan BOM**, bukan otomatis disesuaikan dengan jumlah hasil baik yang akhirnya diperoleh.
- Admin membuat/menyiapkan MO dan WO secara manual. Mekanisme teknis WO perlu dicocokkan dengan Odoo: jika BOM memuat operasi, Odoo mengisi daftar operasi/WO pada MO secara otomatis. Ini berbeda dari keputusan apakah petugas tetap secara manual menyiapkan atau menerbitkan WO.
- Produksi menggunakan acuan **manufaktur satu langkah**: tidak diperlukan dokumen transfer terpisah untuk mengambil komponen dari gudang dapur ke lokasi proses di dalam dapur. Ini tidak menghapus transfer Central → dapur atau dapur → Packing.
- Dalam rancangan aplikasi ini, saat produksi selesai dicatat, pemakaian bahan dibukukan dan hasil produk masuk stok dapur. Pencatatan harus menjaga stok tidak minus.

### Produk setengah jadi

- Produk setengah jadi memiliki buffer dan rencana produksinya sendiri.
- MO/WO produk setengah jadi dibuat manual oleh Admin Produksi, **tidak otomatis dibuat sebagai MO/WO turunan** karena MO produk jadi dibuat.
- Kebutuhan produk jadi yang sudah direncanakan dapat menjadi informasi untuk proyeksi dan saran pengisian buffer produk setengah jadi.
- Kekurangan komponen yang dibuat di dapur sendiri tidak otomatis berarti permintaan ke Central; sumber komponen dan penanganannya perlu dicocokkan dengan master serta alur antar dapur.

## 6. Hasil produksi: kurang, sesuai, atau lebih

Contoh satu WO meminta **100 roti**. Misalkan BOM untuk jumlah itu membutuhkan 10 kg tepung.

| Hasil baik yang dicatat | Bahan berdasarkan WO | Penafsiran hasil | Stok produk baik bertambah |
|---:|---:|---|---:|
| 95 | 10 kg tepung | 5 dianggap rusak | 95 |
| 100 | 10 kg tepung | Sesuai WO | 100 |
| 105 | 10 kg tepung | 5 kelebihan produksi | 105 |

- Hasil kurang dari WO **dianggap rusak** berdasarkan selisih yang dihitung.
- Hasil lebih dari WO dicatat sebagai **kelebihan produksi**.
- WO sekali jalan. Tidak ada backorder, produksi susulan, atau MO pengganti untuk menutup kekurangan hasil WO.
- Selisih yang dianggap rusak tidak boleh dikurangkan lagi dari jumlah produk baik yang dicatat. Angka tersebut adalah hasil perhitungan berdasarkan WO, dan tidak otomatis membuktikan jumlah fisik barang rusak yang terpisah.
- Pemakaian berdasarkan BOM adalah asumsi pembukuan yang disepakati. Jika penggunaan fisik ternyata tidak sesuai BOM, sistem tidak otomatis mengetahui selisih fisik tersebut; penanganannya mengikuti SOP.
- Sisa permintaan yang tidak terpenuhi karena hasil kurang tidak otomatis menjadi MO baru.

## 7. Stok minimum dan saran kebutuhan bahan

- **Setiap barang memiliki pengaturan stok minimum per gudang.**
- Nilai untuk barang yang sama dapat berbeda antara satu gudang dan gudang lain.
- Petugas dapat mengubah nilai minimum; nilainya dinamis.
- Sistem memberi saran jumlah bahan yang perlu diminta. Admin Produksi boleh mengubah saran tersebut, dan jumlah yang diminta petugas menjadi dasar picking serta pengiriman.
- Pengisian buffer dapat diminta tanpa menunggu atau dipicu oleh WO.
- Stok boleh berada di bawah nilai minimum; nilai minimum tidak menjadi pengunci baru. Stok aktual tidak boleh minus.

Untuk kebutuhan produksi, sistem menggabungkan kebutuhan BOM dari seluruh MO yang relevan pada satu dapur dan membandingkannya dengan stok dapur, tanpa menghitung stok yang sama berulang kali.

**Saran dasar yang disetujui:** untuk setiap barang pada satu dapur, jumlah awal yang disarankan adalah kebutuhan bahan yang direkap dari WO ditambah stok minimum, dikurangi stok tersedia, dengan hasil paling rendah nol. Contoh: kebutuhan WO 15 kg, stok tersedia 7 kg, minimum 5 kg → **saran 13 kg**. Jika dipakai semua sesuai rencana, tersisa 5 kg.

Angka 13 kg adalah **saran, bukan jumlah wajib atau stok yang dikunci**. Admin dapat mengubah permintaan, dan stok minimum tetap boleh dipakai sampai nol. Contoh ini mengasumsikan tidak ada barang masuk dalam perjalanan atau kebutuhan dan komitmen lain; perlakuan faktor-faktor tersebut dan periode proyeksi belum ditetapkan.

Bahan setengah jadi tetap menggunakan rencana buffer dan MO manualnya sendiri; jangan mengaktifkan aturan yang otomatis membuat MO setengah jadi sebagai anak dari MO produk jadi.

## 8. Rekap kebutuhan bahan dan transfer Central → dapur

Untuk satu dapur dan satu kelompok MO yang direncanakan:

1. Sistem membaca kebutuhan bahan dari BOM setiap MO sesuai kuantitas WO.
2. Bahan yang sama dari berbagai MO dijumlahkan.
3. Sistem menampilkan stok, minimum, kebutuhan, dan saran kekurangan untuk membantu Admin Produksi.
4. Admin Produksi dapat mengubah jumlah yang diminta dan membuat **satu permintaan multi-SKU** untuk dapur tersebut.
5. Petugas Gudang Central menyiapkan transfer dan membuat **picking list berdasarkan permintaan tersebut**, berisi seluruh bahan untuk dapur itu.
6. Petugas mengambil barang berdasarkan picking list dan mengirimnya melalui **satu transfer yang berisi beberapa SKU**.
7. Dapur menerima transfer; stok tujuan bertambah menurut pencatatan penerimaan.

Contoh: dua MO di Dapur A membutuhkan total tepung 15 kg dan gula 2 kg. Stok yang tersedia 7 kg tepung dan 1 kg gula. Kekurangan dasar adalah 8 kg tepung dan 1 kg gula sebelum mempertimbangkan buffer. Jika minimum tepung 5 kg dan tidak ada faktor lain, saran tepung adalah **13 kg**. Jika admin mengubah permintaan tepung menjadi 10 kg, picking list mengikuti **10 kg yang diminta**, bukan kembali ke saran awal 13 kg.

Ketika stok Central tidak cukup, kondisi kekurangan harus terlihat. Sistem tidak boleh mengirim lebih dari stok yang dapat dibukukan tanpa menjadi minus. Cara menangani kekurangan dan pengecualian mengikuti SOP dan belum dirinci.

Jika kebutuhan baru muncul setelah transfer sudah dikirim, buffer dapur dapat membantu. Mekanisme penanganan kekurangan di luar transfer yang sudah selesai belum ditetapkan; jangan diam-diam mengubah dokumen yang sudah dikirim.

## 9. Prioritas hasil produksi dan batas integrasi ke Packing

- Hasil produksi ditransfer langsung dari Dapur ke Packing dalam satu langkah. Contoh: Dapur mengirim 150 unit; saat transfer dicatat, stok dapur berkurang 150 dan stok Packing bertambah 150, tanpa tahap penerimaan atau stok transit. Aturan ini khusus untuk Dapur → Packing dan tidak otomatis mengubah proses Central → dapur.
- SO diprioritaskan dalam pemenuhan dari Packing. Jika hasil produksi tidak cukup, kebutuhan toko yang menerima sisa setelah SO.
- Contoh untuk satu SKU dan tanpa stok tambahan: SO meminta 100, RO toko total 100, hasil baik 150. SO dipenuhi 100; tersisa 50 untuk toko.
- Sistem memberi saran pembagian sisa kepada toko **secara proporsional berdasarkan RO**. Petugas dapat mengubah saran selama pembagian tidak melebihi stok yang tersedia.
- Misalnya RO Toko A 40 dan Toko B 60, dari sisa 50 sistem menyarankan 20 dan 30. Petugas dapat mengubahnya, contohnya 35 dan 15.
- Alokasi adalah rencana, bukan otomatis pergerakan stok. Ketika pengiriman dibukukan, stok aktual diperiksa kembali agar tidak minus.
- **DO SO dapat dibuat langsung saat SO dikonfirmasi.** DO dicetak di Packing ketika barang siap. Kuantitas setiap produk atau SKU paket pada DO SO harus sesuai dengan kuantitas pada SO; contoh SO 10 Paket P → DO 10 Paket P.
- DO untuk SO disiapkan terlebih dahulu, lalu DO pengiriman ke toko dibuat berdasarkan sisa barang dan alokasi yang ditetapkan petugas. Urutan yang disampaikan adalah pembuatan dokumen; urutan pengiriman fisik belum dirinci.
- Membuat atau mencetak DO bukan pengiriman fisik dan tidak dengan sendirinya mengurangi stok. Saat pengiriman dibukukan, stok Packing harus cukup; penanganan SO yang belum siap mengikuti SOP. Reservasi, jika digunakan, berbeda dari pergerakan fisik dan dapat memengaruhi stok tersedia.
- Metode pembulatan dan penanganan sisa pembulatan untuk barang per buah belum ditetapkan.
- Prioritas antarsesama SO ketika stok bahkan tidak mencukupi total SO belum ditetapkan.

## 10. MO perakitan paket di Packing tanpa WO

- Produk paket dicatat sebagai **SKU paket utuh**, dengan harga jual paket sendiri; harga jual paket tidak ditentukan dengan menjumlahkan harga jual tiap komponen.
- Feri menyetujui penggunaan **MO sederhana khusus perakitan di Packing dengan BOM paket, tanpa WO**. Ini menggantikan keputusan awal yang tidak menggunakan MO untuk perakitan. MO ini terpisah dari MO/WO produksi dapur.
- Perakitan dapat dilakukan kapan saja selama seluruh komponen yang diperlukan tersedia secara fisik di Gudang Packing; jam produksi dapur 20.00–10.00 tidak membatasi perakitan Packing.
- Saat MO perakitan selesai dicatat, stok komponen berkurang dan stok SKU paket bertambah. Semua pengurangan harus memenuhi aturan stok tidak boleh minus.
- Contoh: 10 paket, masing-masing berisi satu A, B, C, dan D, membutuhkan 10 dari setiap komponen dan menghasilkan 10 SKU paket.
- Produk A, B, dan C dapat berasal dari dapur. Produk D dalam contoh dibeli melalui PO dan dikirim supplier langsung ke Packing.
- BOM normal Odoo 19 digunakan sebagai acuan. BOM perakitan tidak memerlukan operasi/WO untuk pilihan alur ini. Kecocokan konfigurasi dan integrasinya dengan aplikasi masih perlu diuji; jangan mengasumsikan SO otomatis membuat MO perakitan atau MO turunan.

Kebutuhan paket berasal dari RO atau SO. Jangan menganggap paket atau komponen sudah tersedia di Packing saat permintaan dibuat. Kebutuhannya harus diterjemahkan ke rencana produk dapur dan produk supplier, lalu komponen fisik diterima sebelum perakitan.

## 11. Contoh terpadu

**Asumsi ilustrasi:** SO membutuhkan 100 Paket P, tiap paket berisi satu A, B, C, dan D. RO seluruh toko membutuhkan total 100 Produk A. Tidak ada stok produk jadi lain yang tersedia untuk rencana contoh ini.

| Produk | RO toko | Isi SO | Total rencana | Sumber |
|---|---:|---:|---:|---|
| A | 100 | 100 | 200 | Dapur sesuai master |
| B | 0 | 100 | 100 | Dapur sesuai master |
| C | 0 | 100 | 100 | Dapur sesuai master |
| D | 0 | 100 | 100 | Supplier melalui PO, langsung ke Packing |

1. Packing merekap A sehingga admin menyiapkan satu MO A untuk 200, dan menyiapkan MO terpisah untuk B dan C.
2. MO yang memakai dapur sama direkap kebutuhan bahannya. Admin Produksi mengajukan permintaan; Central membuat picking list dan satu transfer multi-SKU per dapur untuk kelompok rekap tersebut.
3. Misalnya WO A selesai dengan 150 hasil baik. Bahan tetap berdasarkan WO A sejumlah 200 dan 50 dianggap rusak. Tidak dibuat MO susulan.
4. A ditransfer langsung dari dapur ke Packing. Jika B, C, dan D masing-masing juga sudah tersedia 100 di Packing, MO perakitan tanpa WO memakai 100 A, B, C, dan D untuk menghasilkan 100 Paket P. DO SO berisi 100 Paket P sesuai SO dan dicetak di Packing ketika siap.
5. Sisa 50 A dapat dibagikan ke toko secara proporsional sesuai RO dan dapat diubah oleh petugas, selama tidak menyebabkan stok minus. DO toko disiapkan setelah DO SO.

Ini ilustrasi alur, bukan catatan bahwa stok memang sudah ada di Packing saat pesanan dibuat.

## 12. Kesesuaian Odoo 19 yang sudah ditemukan

| Topik | Temuan dan batas kepastian |
|---|---|
| Satu MO per SKU | Odoo mendukung MO untuk satu produk dan beberapa unit produk tersebut dengan BOM yang sama. |
| BOM otomatis dan WO | Odoo mengisi BOM saat produk dipilih; jika BOM memuat operasi, daftar operasi/WO pada MO juga dapat terisi. Cara memenuhi keinginan WO manual masih perlu dicocokkan. |
| Manufaktur satu langkah | Odoo mendukung satu langkah tanpa transfer pengambilan komponen terpisah di dalam gudang manufaktur. |
| Stok tidak minus | Dokumentasi Odoo menunjukkan stok negatif dapat terjadi dalam beberapa kondisi. Aturan larangan stok minus perlu dijaga secara khusus; jangan berasumsi sudah terjamin oleh standar. |
| Minimum dan saran | Odoo menyediakan aturan minimum–maksimum dan saran replenishment manual. Feri menetapkan saran dasar yang memasukkan kebutuhan WO dan stok minimum; hanya minimum yang diminta sebagai pengaturan petugas. Konfigurasi atau penyesuaian yang sesuai masih perlu diuji. |
| Transfer dan picking | Odoo mendukung transfer langsung antar lokasi dan pencetakan Picking Operations. Dapur → Packing menggunakan transfer langsung satu langkah. Rute pengisian antargudang Odoo dapat membuat dokumen kirim dan terima dengan transit; itu tidak digunakan untuk alur Dapur → Packing ini. Batch picking mengelompokkan beberapa transfer, yang belum tentu sama dengan satu dokumen transfer multi-SKU dari rekap beberapa MO. |
| SO dan MO otomatis | Rute MTO Odoo dapat otomatis membuat MO saat SO dikonfirmasi. Jangan menerapkannya secara membabi buta karena MO/WO produksi dapur dikendalikan manual dan digabung per SKU. |
| Paket dan perakitan | Kit Odoo menampilkan komponen pada DO. Feri memilih SKU paket utuh dan menyetujui MO perakitan Packing menggunakan BOM normal tanpa WO. Kesesuaian konfigurasi dan integrasi dengan aplikasi masih perlu diuji. |
| DO SO dan toko | Odoo dapat membuat DO saat SO dikonfirmasi; DO selanjutnya dicetak di Packing saat barang siap. Jumlah pada DO SO harus sesuai SO. DO toko disiapkan setelah DO SO; pengalokasian SO prioritas dan saran proporsional toko perlu dicocokkan dengan standar Odoo. |
| Produksi kurang | Odoo menyediakan backorder manufaktur, tetapi Feri memutuskan tidak memakai produksi susulan untuk kekurangan hasil WO. |

Kemampuan-kemampuan Odoo di atas adalah **referensi**, bukan bukti bahwa aplikasi inventori milik Feri sudah memiliki fitur yang sama. Kesesuaian alur lengkap perlu diuji pada implementasi yang akan digunakan.

## 13. Hal yang masih terbuka, tanpa menambah aturan yang tidak diperlukan

- **Rincian saran bahan dan buffer:** rumus dasar kebutuhan WO + minimum − stok tersedia sudah disetujui dengan saran paling rendah nol. Perlakuan stok dalam perjalanan, komitmen lain, dan periode proyeksi belum final. Petugas tetap dapat mengubah saran; minimum bukan stok yang dikunci.
- **Reservasi bahan:** belum diputuskan apakah dan kapan stok perlu dicadangkan untuk MO/WO. Reservasi berbeda dari pengurangan stok. Jangan menambahkan penguncian baru hanya karena ada fitur reservasi.
- **Mekanisme WO manual vs isian operasi dari BOM Odoo:** admin tetap mengendalikan MO/WO; cara teknisnya belum disepakati.
- **Tanggal operasional shift malam:** belum diputuskan apakah rekap shift 20.00 tanggal 4 sampai 10.00 tanggal 5 memakai label tanggal 4 atau 5. Aturan pencatatan tetap mengikuti SOP.
- **Peran pencatat hasil dan rincian status dokumen:** petugas yang memasukkan hasil serta bentuk status dapat ditentukan sesuai operasi, tanpa memaksakan pengunci tambahan.
- **BOM yang berubah atau lebih dari satu BOM berlaku:** cara menentukan BOM otomatis dan menjaga riwayat MO lama belum dirinci.
- **MO perakitan Packing:** BOM dan MO sederhana tanpa WO telah disetujui. Cara penyiapan dan integrasi MO perakitan dengan permintaan RO/SO serta kebutuhan komponen masih perlu dicocokkan, tanpa mengasumsikan MO dapur atau produk setengah jadi dibuat otomatis.
- **Pengiriman bahan yang tidak dapat dipenuhi sepenuhnya, atau kebutuhan muncul setelah transfer dikirim:** penanganan spesifik belum diputuskan; jangan membuat stok minus atau mengubah riwayat pengiriman diam-diam.
- **Hasil alokasi yang perlu pembulatan dan prioritas antarsesama SO:** belum ditetapkan.
- **Biaya produksi/HPP:** belum menjadi keputusan rinci dalam diskusi ini.

Jumlah MO yang melebihi kapasitas dan penanganan order sejenis ditangani Admin Sales melalui SOP; jangan mengangkatnya lagi sebagai keharusan sistem memecah MO atau menolak order, kecuali Feri meminta.

## 14. Di luar pembahasan saat ini / nanti

- **Penjualan POS dan konsinyasi:** belum masuk bahasan saat ini. Sementara konsinyasi masih melalui PO supplier.
- **MO spesial:** Feri menyebut kemungkinan fitur tambahan MO spesial dengan barang dari Gudang Central. Fitur itu untuk nanti; arti barang, dokumen, kondisi, dan alurnya belum dirancang. Jangan menjadikannya fitur saat ini atau menganggapnya sebagai backorder otomatis.
- Jangan menganggap contoh atau usulan dalam dokumen sebagai keputusan final.
- Jangan mengubah fungsi inventori lain, membuat implementasi, atau menambah aturan keras tanpa instruksi dan kesepakatan yang relevan.

## 15. Catatan aplikasi yang pernah dibaca

Arsip [inventori-docker .zip](https://chatgpt.com/library?file_id=libfile_22560ee174108191a262900c40d55737&account_id=personal) pernah diperiksa secara baca-saja. Pada arsip tersebut terlihat aplikasi inventori yang sudah memiliki master produk, stok multi-gudang, transfer multi-SKU, serta alur pengiriman dan penerimaan transfer. Pembuatan draft transfer terkait akses gudang sumber dan reservasi sementara.

Pada arsip yang diperiksa saat itu tidak ditemukan modul manufakturing MO/WO yang sudah jadi. **Versi aplikasi yang aktif sekarang bisa berbeda dari arsip tersebut** dan perlu diperiksa sebelum merancang integrasi atau melakukan perubahan. Jangan mengklaim fitur yang direncanakan sudah tersedia atau sudah diimplementasikan.

## 16. Referensi resmi Odoo 19

- [Manufaktur satu langkah dan pengisian BOM](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/manufacturing/basic_setup/one_step_manufacturing.html)
- [Split dan merge MO](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/manufacturing/workflows/split_merge.html)
- [Konfigurasi BOM dan operasi](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/manufacturing/basic_setup/bill_configuration.html)
- [Laporan stok dan reservasi](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/inventory/warehouses_storage/reporting/locations.html)
- [Reordering rules: minimum, maksimum, dan trigger manual](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/inventory/warehouses_storage/replenishment/reordering_rules.html)
- [Pengisian ulang antar gudang dan transit](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/inventory/warehouses_storage/replenishment/resupply_warehouses.html)
- [Transfer internal langsung antar lokasi](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/barcode/operations/transfers_scratch.html)
- [DO dibuat saat SO dikonfirmasi](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/manufacturing/reporting/allocation.html)
- [Mencetak Picking Operations](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/barcode/setup/operation_types.html)
- [Batch picking](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/inventory/shipping_receiving/picking_methods/batch.html)
- [Kit dan transfer komponennya](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/manufacturing/advanced_configuration/kit_shipping.html)
- [Pergerakan stok, konsumsi komponen, dan stok negatif](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/inventory/inventory_valuation/operations_valuation.html)
- [Alokasi hasil MO](https://www.odoo.com/documentation/19.0/applications/inventory_and_mrp/manufacturing/reporting/allocation.html)

