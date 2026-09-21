# Ochiq masalalar (hali qilinmagan) — esdan chiqmasligi uchun

Bajarilgan ishlar — `tuzatishlar.md`. Bu faylda faqat **qolgan / keyinga qoldirilgan** masalalar. Yangilangan: 2026-09-21.

## Keyinga qoldirilgan (user: "keyin")

| # | Masala | Joy | Izoh |
|---|---|---|---|
| B1 | AW: sukut `dr_init_frac=0.0` → Dr = 0 dan boshlanadi; hujjat va `main` izohida "RAW dan" deyilgan | `root_zone_water.compute_awnet`, `main._export_monthly` | AW oylik rejimda umuman yaroqsiz deb topilgan (xotira: aw-monthly-invalid) |
| B2 | Oylik eksportda xatolar yutiladi (`except → print`): CUirr/AW bloki va har mahsulot; run "OK" deb tugaydi | `main._export_monthly` | tayllar uchun #54 da tuzatilgan, bu yerda qolgan |
| B3 | CUirr ildiz-zona Dr har oy qayta boshlanadi (`dr_init_frac`) — P8 bilan bir xil turdagi | `consumptive_use.effective_precip_monthly` | |
| **B4** | **VIIRS lambda oylik ET standart SEBAL_Milliy'dan +15 % yuqori** (iyul 2023 Samarqand: VIIRS lambda 185.9, kc 168.5, standart 161.7 mm). VIIRS rejimdan qat'i nazar Λ×Rn24 bilan ishlaydi | `viirs_downscaling.build_tile_monthly_et_viirs` | sabab o'rganilmagan |
| **B5** | **S30 yo'li boshidan oxirigacha hech qachon ishga tushirilmagan** (#66 dagi Number−Image xatosi tuzatilgan, lekin to'liq sinov yo'q) | `hls_s30_etrf.build_tile_monthly_etrf_s30` | to'liq runtime sinovi kerak |
| P8 | Kc_ETo modelida topsoil De har oy TEW dan qayta boshlanadi | `ndvi_kc._kc_model`, `root_zone_water` | user: "alohida bosamiz" |
| A4 | Cold anchor sezgirligi: cold LST ~0.1 K siljisa point_anchor boshqa pikselni tanlaydi → sahna ET ±20 % (#70); cold Ta − ERA5 +8…+15 K | `energy_balance` (point_anchor) | takliflar chatda berilgan — qaror kutilmoqda |

## Qarorlar (yopilgan savollar)

- **RO (hot piksel suv balansi) = 0** — user qarori 2026-09-21 ("56 RO = 0"). Kodda: `water_balance.hot_pixel_etrf._run`.

## Past ustuvorlik / izchillik (qaror kerak bo'lsa)

- Tuproq uch xil manbadan: hot balans — HiHydroSoil (VG θ33 + WCpF4.2) + FAO REW jadvali; CUirr/AW/Kc_ETo — SoilGrids + Saxton, REW = 0.15·loy + 2; Appendix I (etrf_water_balance) — FAO jadvali (OpenLandMap tekstura).
- Kun tartibi: Kc modelida yomg'ir avval (De2 = De − P, keyin Kr), hot balansda kitob tartibi (Kr ← De(i−1)).
- CUirr, Kc_ETo, AW kunlik balanslarida yog'in CHIRPS UTC kuni, ET/ETo mahalliy kun (O'zbekistonda 5 soat). Hot balansda #74 da tuzatilgan.
- Kc_ETo: `n_landsat_scenes` butun davr sahnalari (oy emas), oylik bo'shliq QC yo'q.
- Global holat: albedo usuli, `COLD_ETRF`, `CROP_TYPE`, `CROP_ASSETS` faqat `run()` da o'rnatiladi va chaqiruvlar orasida qoladi (`run_polygons` o'rnatmaydi).
- Kunlik raster eksportda SEBAL_ID/Milliy uchun ETRF_INST, ETR24, SOLAR_FRAC bandlari yo'q.
- HLS (`satellite='HLS'`): LST = HLS B10 (TOA yorqinlik harorati, LST emas); SEBAL_Milliy SMW `ST_TRAD` talab qiladi — HLS bilan ishlamaydi.
- Instant K↓ ochiq osmon formulasi (ETr esa haqiqiy SSRD) — keyingi modelga qoldirilgan.
