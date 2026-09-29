# sharpening/ — LST keskinlashtirish (DMS) va "Landsat o'zini-o'zi tekshirish" sinovi

Pipeline'ga (`sebal_gee_v4`) tegilmaydi. Bu papka — alohida sinov va modul.

## Fayllar
- `dms.py` — DMS (Data Mining Sharpener), GEE.
- `selftest_lst.py` — sinov. Landsat LST'ni 70 m / 1 km ga yig'adi, qayta 30 m ga keskinlashtiradi va asl bilan solishtiradi.
- `selftest_summary.py` — kunlar bo'yicha xulosa jadvali.
- `selftest_lst_results.csv` — natijalar.

## Mualliflik va litsenziya
`dms.py` OpenET `openet-landsat-lst` loyihasining `openet/lst/model.py` fayli asosida yozilgan.
- Manba: https://github.com/Open-ET/openet-landsat-lst
- Mualliflar: Yanghui Kang, Yun Yang.
- Litsenziya: Apache-2.0 — repoda LICENSE fayli yo'q, lekin `pyproject.toml`'da e'lon qilingan.
- Asl koddan farqlar `dms.py` sarlavhasida sanab o'tilgan (Apache-2.0, 4(b)).
- Usul manbalari: Gao va boshq. 2012; Xue va boshq. 2020; Liu va boshq. 2026.

Apache-2.0 matni (4(a) talabi): [../LICENSES/Apache-2.0.txt](../LICENSES/Apache-2.0.txt); qarang [../THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md).

## OpenET kodida topilgan nozik xato (2026-09-27)
Asl kodda lokal regressiya natijasi (`reduceNeighborhood`) to'g'ridan-to'g'ri 30 m gridga `reproject` qilinadi. Shunda GEE regressiyani 30 m gridda bajaradi:
- oyna radiusi "10 dag'al piksel" o'rniga 10 × 30 m bo'lib qoladi;
- Landsat'da (100 m) bu faqat oynani kichraytiradi;
- 1 km da regressiya yechilmay, natija deyarli butunlay bo'sh chiqadi.

Bizda natija avval dag'al gridga qotiriladi.

## Sinov tuzilishi
- **Tile:** T42SUJ (MGRS, EPSG:32642, 30 m).
- **Haqiqat:** Landsat C2 L2 ST_B10, MGRS gridiga bilinear bilan o'tkazilgan.
- **Simulyatsiya:** nurlanish fazosida (Planck, 10.9 µm) 70 m (ECOSTRESS gridi) va 1 km (VIIRS o'rniga) ga yig'ish.
- **Variantlar:**
  - keskinlashtirishsiz — dag'al LST 30 m ga bilinear;
  - DMS (EC box: 70/270 m; 1000/2000 m).
- **Baholash:**
  - 30 m da;
  - 100 m da — Landsat termalining asl aniqligi va SEBAL anchor masshtabi (`ANCHOR_SCALE=100`).
- **Qatlamlar:** hamma quruqlik; ekin maydoni; sovuq nomzod (ekin, NDVI > 0.7); issiq nomzod (NDVI < 0.2).
- **Cheklov:** prediktor — o'sha kungi HLS L30 (eng yaxshi holat) va sensorlar orasida joylashuv siljishi yo'q. Haqiqiy ECOSTRESS/VIIRS kunlarida natija yomonroq bo'ladi.

## Natija — 4 kun, 2023 (05-08, 07-11, 08-12, 09-29), 100 m da

Jadvalda xato — keskinlashtirilgan LST minus haqiqat (K); qavsda kunlar oralig'i.

| Variant | Hamma quruqlik, RMSE | Sovuq nomzod, bias | Issiq nomzod, bias | Issiq–sovuq kontrasti xatosi |
|---|---|---|---|---|
| ECOSTRESS 70 m, bilinear | 0.20 | +0.25 (+0.21..+0.35) | −0.04 | −0.24..−0.40 |
| ECOSTRESS 70 m, DMS EC 70 | 0.35 | −0.14 (−0.22..−0.09) | +0.03 | +0.11..+0.26 |
| ECOSTRESS 70 m, DMS EC 270 | 0.82 | −0.25 | +0.04 | +0.09..+0.57 |
| VIIRS 1 km, bilinear | 2.59 | **+3.38 (+2.82..+4.53)** | −0.85 | **−3.5..−5.5** |
| VIIRS 1 km, DMS EC 1000 | 2.36 | **−2.12 (−3.00..−1.00)** | +0.29 | **+1.1..+3.4** |
| VIIRS 1 km, DMS EC 2000 | 2.52 | −2.17 | +0.24 | +1.2..+3.4 |

- **ECOSTRESS (70 m):** 100 m da oddiy bilinear Landsat bilan deyarli bir xil (0.2 K). DMS qo'shimcha foyda bermaydi. EC 270 m joylashuv siljishi bo'lmaganda natijani yomonlashtiradi.
- **VIIRS (1 km):** hech bir usul SEBAL anchorlari uchun yetarli aniqlik bermaydi. Sovuq nomzodlar bilinear bilan ~3.4 K issiq, DMS bilan ~2.1 K sovuq chiqadi. Issiq–sovuq kontrasti 1–5.5 K ga buziladi.
- **Cheklov:** eng yaxshi holat sinovi — prediktor o'sha kungi HLS L30, joylashuv siljishi yo'q. Haqiqiy kunlarda xato kattaroq bo'ladi.

## Sensorlararo sinov — haqiqiy ECOSTRESS / VIIRS LST vs o'sha kungi Landsat LST (`crosssensor_lst.py`)
Asos (haqiqat): Landsat C2 L2 ST. Qatlamlar: ekin maydoni; sovuq (ekin, NDVI>0.7); issiq (ekin, NDVI<0.2).

**ECOSTRESS** — 4 juft: 2019-08-17 09:08, 2020-08-03 13:23, 2023-09-29 13:52, 2024-04-08 09:52; Landsat 10:40.
- Sensor masshtabida (70 m, downscalingsiz), ekin maydonida: MBE −2.7 K, RMSEu 2.1 K, R² 0.71 (0.43..0.83).
- Downscaling usullari bir-biridan deyarli farq qilmadi: RMSEu ~2.0 K, R² ~0.7. TsHARP 30 m da yomonroq (R² 0.61).
- Har kuni ECOSTRESS'da issiq–sovuq farqi Landsat'dagidan 3.4–6.1 K kichik, ertalab ham, tushdan keyin ham.

**VIIRS** — 12 kun, ~12:40, ko'rish burchagi ~25°; UTM 1 km gridga bilinear bilan o'tkazilgan.
- Sensor masshtabida (1 km), ekin maydonida: MBE +1.0 K, RMSEu 1.56 K, R² 0.79. 2024-04-08 anomal (R² 0.05); usiz 0.67..0.97.
- 30 m da, ekin maydonida:

  | Usul | RMSEu | R² | Sovuq nomzodda MBE / R² |
  |---|---|---|---|
  | bilinear | 2.63 | 0.63 | +3.4 / 0.45 |
  | faqat RF | **2.99** | **0.68** | **−0.6 / 0.26** |
  | DMS | 3.22 | 0.60 | — |
  | faqat lokal | 3.96 | 0.50 | — |
  | TsHARP | 5.30 | 0.53 | −6.8 (ishlamaydi) |

## SEBAL_Milliy: ECOSTRESS LST vs Landsat LST (`sebal_eco_vs_landsat.py`)
- Pipeline o'zgarmagan. ECOSTRESS variantida o'sha kungi Landsat tasviriga ECOSTRESS LST'si, o'tish vaqti va o'sha vaqtdagi (astronomik) quyosh burchaklari qo'yilgan; SMW o'chirilgan.
- Ikkala variant ECOSTRESS yaroqli piksellarida hisoblangan.

| Kun | ECOSTRESS soati | Anchor ΔT, K (Landsat / ECOSTRESS) | Ekin ET, mm/kun (Landsat → ECOSTRESS) | MBE | RMSE | R² |
|---|---|---|---|---|---|---|
| 2019-08-17 | 09:08 | 13.3 / 7.7 | 3.80 → 3.40 | −10.6% | 1.08 | 0.78 |
| 2020-08-03 | 13:23 | 15.1 / 13.8 | 3.66 → 3.95 | +7.9% | 1.04 | 0.85 |
| 2023-09-29 | 13:52 | 14.5 / 9.9 | 2.95 → 1.62 | **−45.3%** | 1.42 | 0.80 |
| 2024-04-08 | 09:52 | 11.7 / 6.2 | 3.33 → 3.34 | +0.2% | 1.06 | 0.45 |

- **Fazoviy naqsh:** 3 kunda yaxshi mos (R² 0.78–0.85).
- **O'rtacha ET darajasi beqaror:** −45%..+8%.
- **Piksel xatosi:** ~1–1.4 mm/kun.

## SEBAL_Milliy: VIIRS LST vs Landsat LST (`sebal_viirs_vs_landsat.py`, `export_viirs_rf.py`)
- VIIRS vaqti: tile medianasi ~12:36–12:42; quyosh burchaklari shu vaqt uchun hisoblangan.
- Variantlar:
  - **VB** — 1 km → 30 m bilinear;
  - **VR** — RF bilan keskinlashtirilgan (asset).
- RF asset'lari GEE eksport navbatida qolgan (2026-09-27): faqat 2019-08-17 tayyor.

| Kun | Landsat ET | VB: ET, farq, RMSE, R² | VR (RF): ET, farq, RMSE, R² |
|---|---|---|---|
| 2019-08-17 | 3.08 | 3.12, +1.2%, 1.00, 0.76 | **3.09, +0.3%, 0.75, 0.85** |
| 2020-08-03 | 2.76 | 2.92, +5.8%, 1.18, 0.71 | — |
| 2023-05-24 | 4.12 | 4.50, +9.3%, 1.30, 0.58 | — |
| 2023-07-11 | 4.08 | 4.75, +16.5%, 1.63, 0.72 | — |
| 2023-08-28 | 3.46 | 3.97, +14.5%, 0.79, 0.86 | — |
| 2023-09-29 | 2.02 | 2.64, +30.6%, 1.12, 0.63 | — |

- **VB:** o'rtacha +13%, RMSE 1.17 mm/kun, R² 0.71. NDVI sinflari bo'yicha: siyrak (<0.3) +56%, o'rta +10%, zich (>0.6) −5% — bilinear ET farqlarini siqib, tekislab yuboradi.
  - Sovuq anchor Landsat'dagidan 2.7–4.8 K issiq, ΔT odatda kichik.
- **VR (1 kun):**
  - anchorlar Landsat bilan deyarli bir xil (sovuq +0.5 K, issiq +0.6 K);
  - ET farqi siyrakda −6.8%, o'rtada +2.0%, zichda +0.9%.

### VR (RF) — 6 kun to'liq (2026-09-28; yangi eksportsiz, `SKIP_VB=1`, `sebal_viirs_vs_landsat_rf.csv`)

| Kun | VB: farq / RMSE / R² | VR: farq / RMSE / R² |
|---|---|---|
| 2019-08-17 | +1.2% / 1.00 / 0.76 | +0.3% / 0.75 / 0.85 |
| 2020-08-03 | +5.8% / 1.18 / 0.71 | +16.2% / 0.94 / 0.89 * |
| 2023-05-24 | +9.3% / 1.30 / 0.58 | +19.2% / 1.22 / 0.73 |
| 2023-07-11 | +16.5% / 1.63 / 0.72 | +23.9% / 1.62 / 0.84 |
| 2023-08-28 | +14.5% / 0.79 / 0.86 | +9.3% / 0.66 / 0.90 |
| 2023-09-29 | +30.6% / 1.12 / 0.63 | +26.3% / 0.94 / 0.73 |
| **O'rtacha** | **+13.0% / 1.17 / 0.71** | **+15.9% / 1.02 / 0.82** |

- **RF naqshni yaxshilaydi** (R² 0.71 → 0.82, RMSE 1.17 → 1.02 mm/kun), lekin o'rtacha daraja og'ishini yo'qotmaydi.
- **VIIRS'dan hisoblangan SEBAL ET har doim yuqori** (+0..+31%). Ehtimoliy sabab — o'tish vaqti (12:40 va Landsat 10:40) va bug'lanish ulushini kun bo'yi doimiy deb olish taxmini. Og'ish keskinlashtirishdan emas.
- **NDVI sinflari bo'yicha (VR):** siyrak +34%, o'rta +14%, zich +7%.
- \* **Takrorlanuvchanlik:** 2020-08-03 da Landsat varianti cheklangan GEE rejimida `cimec`/`plan_a`/`plan_b` uchun "cold/hot bo'sh" oldi va `default` zaxirasiga o'tdi (ΔT 22.7 K). Normal rejimda bir kun oldin `cimec` topgan edi (ΔT 16.4 K). Bu kunning VR natijasini VB bilan to'g'ridan-to'g'ri solishtirib bo'lmaydi. Kvota tiklangach, takroriy sinov kerak.

## T1 sinovi — "daraja Landsat'dan, o'zgarish VIIRS'dan" (`t1_holdout.py`, ee-chexovant11, 2026-09-28)
t1 dagi Landsat-SEBAL bo'yicha t2 (16 kun keyin) bashorat qilinadi va t2 dagi haqiqiy Landsat-SEBAL bilan solishtiriladi (ekin maydoni).
- **P0** — hozirgi usul: SOLAR_FRAC(t1) o'zgarmas.
- **P1** — P0 × VIIRS o'zgarishi (1 km); optika t1 dan.
- **P2** — xuddi shunday, optika t2 dan.

| Juft | Haqiqiy F o'zgarishi | P0: farq / RMSE / R² | P1 | P2 |
|---|---|---|---|---|
| 24-may → 9-iyun | +8% | −4% / 1.61 / 0.62 | −7% / 1.67 / 0.59 | +13% / 1.63 / 0.67 |
| 13-sen → 29-sen | −33% | **+55%** / 1.45 / 0.64 | +47% / 1.26 / 0.70 | **+16% / 0.85 / 0.73** |

- 12-avgust → 28-avgust: 5 ta SEBAL bajarildi, lekin oxirgi namuna olish bosqichida GEE vaqt chegarasi (timeout).
- **Hozirgi usul (P0)** 16 kunlik oraliqda katta xato berishi mumkin: mavsum oxirida +55%.
- **Eskirgan optika bilan VIIRS termali (P1)** kam yordam beradi: nisbat medianasi 0.97 va 0.96, haqiqiy o'zgarish esa 1.08 va 0.67.
- **Yangi optika bilan (P2)** yaxshilanish katta. Mavsum oxirida RMSE 1.45 → 0.85; mavsum boshida zich ekinda farq −26% → −6%.
- **Xulosa (2026-09-28, keyin qisman tuzatildi):** P2 dagi yaxshilanish yangi optika va VIIRS termali birgalikda bergan natija. Pilotdagi P3 sinovi (pastda) faqat optika yetarli emasligini ko'rsatdi.

## T-A pilot — mustaqil VIIRS-SEBAL + Landsat bilan kalibrlash (`pilot_ta.py`, `pilot_ta_analyze.py`, ee-chexovant11, 2026-09-28)
- **Tanlama:** 10 kun (2019–2025, aprel–oktabr), har kunda Landsat-SEBAL va VIIRS-SEBAL (RF 30 m LST, o'sha kungi L30).
- **Nuqtalar:** ekin maydonidagi bir xil 5000 nuqta.
- **Hisob:** 10 ta eksport (12:00–13:00) va 20 ta SEBAL (13:00–13:11).

| Kun | ET_L | ET_V | k_d | Xom MBE | LOO bilan tuzatilgan MBE | R² |
|---|---|---|---|---|---|---|
| 2019-08-17 | 3.88 | 3.94 | 1.019 | −0.6% | −9.3% | 0.80 |
| 2020-08-03 | 4.19 | 4.97 | 0.862 | +16.8% | +9.2% | 0.87 |
| 2021-06-19 | 4.70 | 5.84 | 0.849 | +21.0% | +12.8% | 0.76 |
| 2022-10-12 | 2.00 | 3.47 | **0.585** | **+76.1%** | **+66.2%** | 0.64 |
| 2023-05-24 | 4.19 | 4.97 | 0.874 | +16.9% | +8.2% | 0.70 |
| 2023-06-09 | 5.62 | 5.60 | 0.996 | −0.3% | −9.4% | 0.74 |
| 2023-07-11 | 5.82 | 5.88 | 0.960 | +10.5% | +1.2% | 0.75 |
| 2023-09-29 | 2.71 | 3.29 | 0.876 | +18.9% | +9.9% | 0.64 |
| 2024-08-14 | 5.22 | 4.90 | 1.048 | −3.5% | −12.5% | 0.87 |
| 2025-04-11 | 4.24 | 4.32 | 0.971 | +2.3% | −7.0% | 0.77 |

- **Umumiy k:** 0.922 (kunlik k: median 0.918, 0.585–1.048, CV 14.7%). LOO bilan jami: MBE +10.9% → **+2.1%**, RMSE 1.05 → 0.98, R² 0.74.
- **Qoldiq (LOO dan keyin):**
  - NDVI bo'yicha kichik: <0.3 +3.7%, 0.3–0.6 +0.4%, >0.6 −2.7% → k(NDVI) hozircha kerak emas;
  - oy bo'yicha: aprel–avgust −6..+6%, sentabr +5.6%, **oktabr +61%** (bitta kun — tasodifmi yoki qonuniyatmi, hozircha noma'lum).
- **Ko'rish burchagi:** Landsat kunlarida VIIRS burchagi har doim ~24–26° (orbita geometriyasi). Kalibrlash juftlari 0–40° oraliqni qamramaydi, shuning uchun burchak ta'sirini bu usul bilan baholab bo'lmaydi.
- **Kunlikka o'tkazish usuli:** ETrF·ETr24 og'ishni tushuntirmaydi — bir xil usullar solishtirilganda ham ~+10%. Landsat'ning o'zida ikki usul orasidagi farq +13%.
- **P0/P3/T-A (2023-05-24 → 06-09, t2 dagi Landsat ET bashorati):**
  - P0 (hozirgi usul): −21.4%, RMSE 1.61, R² 0.57;
  - P3 (faqat optika, NDVI regressiyasi): −26.4%, RMSE 1.92, R² 0.42;
  - **T-A (VIIRS, k_LOO):** **−8.7%, RMSE 1.07, R² 0.72**.

  VIIRS termali optikadan tashqari aniq foyda berdi (1 juft).
