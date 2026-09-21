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
| A4 | Cold anchor sezgirligi: cold LST ~0.1 K siljisa point_anchor boshqa pikselni tanlaydi → sahna ET ±20 % (#70); cold Ta − ERA5 +8…+15 K | `energy_balance` (point_anchor) | **2026-09-21 user qarori: P0 (hozirgi) QOLADI.** Test natijalari pastda (A4 test). Asl sabab — cold fizikasi (A5) |
| A5 | Cold anchor dT_cold −10…−20 K (Ta +14…+16 K): H_cold manfiy × past shamolda barqaror qatlam rah kuchaytirishi | `energy_balance.compute_sensible_heat_flux` (cold iteratsiya) | qisman qoplama qismi TUZATILDI (#90, LAI ≥ 4). Ochiq: to'liq qoplama + past shamol (06-01: dT −10.8 K, Ta +14 K) — manbali yechim yo'q, QC ogohlantirishi. Diagnostika pastda (A5) |

### A4 test (2026-09-21) — cold anchor point variantlari (production kodi o'zgarmagan, monkeypatch)
Variantlar (hammasi haqiqiy BITTA piksel, hot o'zgarmagan): P0 hozirgi (CIMEC NDVI ≥ p80, LST p5…p40 → eng sovuq); P1c hozirgi nomzodlar → o'rtacha Ts'ga eng yaqin; P1 Allen 2013 nomzodlari (top 5 % NDVI → eng sovuq 20 %) → o'rtacha Ts'ga eng yaqin; P2 P1 + Allen albedo sharti; P3 Allen nomzodlari → min dT (Dhungel & Barber 2018); P4 Allen nomzodlari → dT medianasiga eng yaqin.

LST shovqini σ = 0.1 K (har 100 m piksel mustaqil, 6 realizatsiya) — sahna ET'sining eng katta sakrashi, %:

| | Samarqand 06-09 | Samarqand 07-11 | Bushland 07-09 | o'rt. CV |
|---|---|---|---|---|
| P0 | 6.0 | 26.9 | 13.0 | 3.6 % |
| P1c | 29.9 | 4.5 | 11.8 | 6.0 % |
| P1 | 12.7 | 10.5 | 10.6 | 5.9 % |
| P2 | 13.6 | 4.1 | 4.2 | 3.5 % |
| P3 | 4.2 | 1.4 | 7.5 | 2.4 % |
| P4 | 1.2 | 5.4 | 20.5 | 3.8 % |

Bushland 2021, 22 sahna, lizimetr (Catch Precip): RMSE / MBE — P0 1.65 / −35 %; P1c 1.52 / −15 %; P1 1.69 / −38 %; P2 1.60 / −31 %; P3 1.31 / −24 % (sahnalar: 7 yaxshi / 3 yomon; 08-26 siz 1.34 vs P0 1.42); P4 1.65 / −34 %. Cold Ta − ERA5: P0 Bushland +3.6 K, Samarqand 07-11 +0.6; P3 +4.7 / **+16.3** (ekstremal advektiv piksel, Samarqand ET +15…+27 %); P4 +3.3 / +2.9.

Xulosa: hech bir variant ikkala saytda va ikkala mezonda P0 dan ishonchli ustun emas. Nomzodlar orasida H_cold (−250…0 W/m²) va rah_cold (13…364 s/m) juda farq qiladi — NDVI/LST ularni nazorat qilmaydi (Dhungel & Barber 2018: bitta piksel tanlovi 5–20 % noaniqlik). Dala masshtabida LST'ning o'z shovqini ~4–5 % (anchorlar o'zgarmasa ham) — yo'qotib bo'lmaydi. Test skriptlari: scratchpad `a4_variants.py`, `a4_run.py`, `a4_analyze.py`.

### A5 diagnostikasi (2026-09-21) — dT_cold qaysi bosqichda tug'iladi
Production kodi, cold anchor pikseli (skalyar iteratsiya aynan nusxa, farq ≤ 0.002 K):

| | S 06-01 | S 07-27 | S 06-09 | S 08-04 | S 08-20 | S 07-11 | B 07-09 |
|---|---|---|---|---|---|---|---|
| LAI | 6.0 | 2.5 | 2.1 | 3.1 | 6.0 | 6.0 | 6.0 |
| Rn−G (W/m²) | 529 | 551 | 570 | 562 | 517 | 569 | 557 |
| λET/(Rn−G) | 1.11 | 1.22 | 1.10 | 1.30 | 1.53 | 1.00 | 1.25 |
| H_cold | −60 | −123 | −59 | −166 | −271 | −3 | −137 |
| u10 ERA5 (m/s) | 1.70 | 2.69 | 2.52 | 4.25 | 5.14 | 0.96 | 6.09 |
| rah neytral → yakuniy (s/m) | 44 → 193 | 31 → 69 | 34 → 50 | 19 → 23 | 14 → 16 | 77 → 93 | 12 → 13 |
| L Obukhov (m); ψm/ψh | 1.4; −5/−5 (clamp) | 4.2; −2.3 | 9.9; −1.0 | 23.6; −0.4 | 34.7; −0.3 | 21.9; −0.4 | 118.7; −0.1 |
| dT neytral → yakuniy (K) | −2.4 → −10.8 | −3.6 → −8.1 | −1.9 → −2.8 | −3.0 → −3.6 | −3.7 → −4.2 | −0.2 → −0.2 | −1.6 → −1.7 |
| Ta − ERA5 (K) | +14.0 | +5.7 | +6.1 | +3.0 | +1.5 | +0.6 | +4.9 |

Zanjir: radiatsiya normal → 1.05·ETr > Rn−G (H < 0) → past shamolda barqaror MO tuzatishi rah'ni ×2…×4.4 → dT −8…−11 K. 06-09 dagi Ta anomaliyasi dT'dan emas — cold LST ERA5 Ta dan +3.3 K issiq (LST − Ta faqat diagnostika: dT aerodinamik, ERA5 grid katta).

Cheng–Brutsaert 2005 (a 6.1, b 2.5, c 5.3, d 1.1; ψm z = 2 m, ψh z2−z1 — AYNI balandliklar) offline sinovi: 7 sahnaning HAMMASIDA |dT| KATTAROQ (06-01 −10.76 → −17.48; 07-27 −8.09 → −10.61; 06-09 −2.84 → −3.40) — CB05 koeffitsientlari BD'dan katta, joriy −5 clamp esa CB05 dan qattiqroq. Chegarasiz chiziqli: 06-01 −17.26 K (hozir faqat −5 clamp cheklaydi). **CB05 olinmaydi.**

## Qarorlar (yopilgan savollar)

- **A4 — cold anchor tanlash qoidasi: P0 (hozirgi) qoladi** — user qarori 2026-09-21 (test natijalari yuqorida).
- **A5 — 1.05·ETr faqat to'liq qoplamaga (LAI ≥ 4), topilmasa sahna tashlanmaydi (flag)** — user qarori 2026-09-21 (#90). Barqaror qatlam funksiyasi (CB05) — olinmaydi (sinov yuqorida).

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
