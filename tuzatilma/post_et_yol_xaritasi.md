# Post-ET yo'l xaritasi — ET'dan keyingi mahsulotlar

Yangilangan: 2026-10-03. Maqsad — adashmaslik: qayerdamiz, nima qilmoqchimiz, muammo nimada, qanday yechim kelishilgan, keyingi qadam nima.

- Qarorlarni faqat user qabul qiladi. Bu faylda kelishilganlar va ochiq savollar yozilgan.
- Kodga hali hech narsa yozilmagan — hammasi dizayn bosqichida.
- Boshqa fayllar:
  - `tuzatishlar.md` — faqat bajarilgan kod o'zgarishlari;
  - `ochiq_masalalar.md` — post-ET qarorlari jadvalining asl yozuvi.

---

## 1. Qayerdamiz

- **SEBAL ET tayyor.** Kod tekshiruvi #00–#97 bajarilgan va commit qilingan (`tuzatishlar.md`).
  - Rejimlar: SEBAL_Milliy, SEBAL_ID, SEBAL_B, pysebal, Kc_ETo.
  - Sahnasiz kun: har piksel uchun eng yaqin yaroqli sahnaning ulushi (rejimga qarab SOLAR_FRAC, ETrF yoki EF) × o'sha kunning qiymati (Rs24, ETr24 yoki Rn24).
  - Oylik yig'indi — `ET_MONTHLY` (`daily_et.py`).
- **Saqlangan holat — `sebal_v6` (2026-09-26):** git tegi `sebal_v6` (commit 66994f2) va to'liq arxiv `D:\Cloud_comp\Sebal\backups\sebal_v6_2026-09-26.zip`. v6'ni qaytarish:
  - alohida papkaga, joriy ishga tegmasdan: `git worktree add ../sebal_v6 sebal_v6`;
  - yoki arxivni ochish — `sebal_v6/` papkasi, ichida hamma fayllar.
- **Keyingi versiyalar** (git tegi + `D:\Cloud_comp\Sebal\backups\` dagi to'liq arxiv; natija fayllari faqat arxivda):
  - `sebal_v7` (2026-09-29) — ko'p sensorli yo'l (LHLSVIIRSECO) va hudud → tile → ekin rejasi;
  - `sebal_v8` (2026-10-03) — ko'p sensorli yo'l tuzatishlari (`tuzatishlar.md` #98–#103), k = 1, Bushland lizimetri bilan tekshiruv.
- **Ko'p sensorli yo'l ishlaydi va yer ma'lumoti (Bushland lizimetri) bilan tekshirildi (2026-10-03):** yangi rejim eski Landsat rejimidan aniqroq; VIIRS ishni yaxshiladi; qolgan xato — SEBAL_Milliy modelining o'zida. Natijalar — 7-A bo'limida.
- **Hozirgi post-ET kodi soddalashtirilgan:** `consumptive_use.py` (CUIRR, PRZ, NIWR, AW = CUirr / samaradorlik) va `root_zone_water.py`. Yangi dizayn ularga tayanmaydi (user qarori).
- **O'rganilgan manbalar** — 11-bo'limda.

## 2. Nima qilmoqchimiz
Biz sebal ET dan keyingi mahsuloga suv istemoli suv sarfi o'simlikka tegishli mahsulotlar... kabi mahsulot tayyorlamoqchimiz !
Bu uchun bizga Hydrosat IDC va ochiqmanba dagi suullardna fodyalanib AW ni ETAW   kabilarni topmoqchimiz 

Asosiy mahsulotlar va ular orasidagi bog'liqlik:

```text
ET (SEBAL — bor)
 ├─ ETPR = ET'ning yomg'irdan kelgan qismi
 ├─ ETGW = ET'ning sizot suvidan kelgan qismi
 └─ ETAW = ET − ETPR − ETGW   (ET'ning sug'orish suvidan kelgan qismi)

AW = dalaga berilgan sug'orish suvi
```

- AW va ETAW — boshqa-boshqa narsa. AW — dalaga kirgan suv, ETAW — uning bug'langan qismi. Qolgani oqib ketadi, pastga sizib ketadi yoki tuproqda qoladi.
- Boshqa mahsulotlar (biomassa, hosil va h.k.) katalogda, ularni user tanlaydi: https://claude.ai/artifact/PVsVN8BMZMmYPB8wwnqBVk

## 3. Kelishilgan formulalar

Kunlik ildiz zonasi balansi (IDC Eq 1 asosida; ET SEBAL'dan olinadi):

```text
S(t+1) = S(t) + P + AW − ET − R − q          S = 1000 · θ · Z   (mm)
  ⇒  AW = ET + R + q + ΔS − P                (Hydrosat formulasi; CR = 0)
```

| Had | Qanday topiladi | Ma'lumot |
|---|---|---|
| ET | SEBAL, kunlik | bor |
| P — yog'in | CHIRPS | bor |
| R — yuza oqimi | IDC Eq 5–7: SCS-CN; tuproq qancha ho'l bo'lsa, oqim shuncha ko'p | CN — tuproqning gidrologik guruhi (HiHydroSoil) |
| q — perkolatsiya | IDC Eq 13: van Genuchten–Mualem. Oddiy chelak (FC dan oshgan suv ketadi) — QA uchun | HiHydroSoil: ksat, alpha, N, wcsat, wcres |
| Z — ildiz chuqurligi | dala ekinining Zmax qiymati, yil davomida o'zgarmas | `crop_kc_table.py` |
| Boshlang'ich θ | ikki chegara: ikkita hisob θ₀ = WP va θ₀ = FC dan boshlanadi, natijalari bir-biriga yaqinlashguncha yuritiladi | yaqinlashish chegaralari sezgirlik bilan tanlanadi |
| CR, ETGW — sizot suvi | quduq ma'lumoti kelguncha 0, bayroq bilan | — |
| ETPR | ikki ssenariy parallel: (1) faqat yomg'ir balansi; (2) IDC, sug'orish qoidasi bilan. Bu "noaniqlik konverti", haqiqiy min/max emas | — |

R va q formulalari:

```text
R:  Smax = 25400/CN − 254
    θ > θFC/2 bo'lsa:  Scn = Smax · [1 − (θ − θFC/2) / (θs − θFC/2)]
    R — SCS-CN tenglamasi Scn bilan (IDC Eq 5–7)

q:  q = Ks · Se^0.5 · [1 − (1 − Se^(1/m))^m]²,   m = 1 − 1/n   (IDC Eq 13)
```

HiHydroSoil bo'yicha eslatma: hozirgi kod faqat 0–5 va 5–15 sm qatlamlarini oladi. Ildiz zonasi (paxtada 1.4 m gacha) uchun chuqurroq qatlamlar kerak. GEE'da qaysi chuqurliklar borligini tekshirish kerak.

## 4. Asosiy muammo — ildiz zonasi namligi (θ) yo'q

- **Hammasi θ'ga bog'liq:** R, q, ΔS va ETPR'dagi α. θ bo'lmasa, AW va ETPR ishonchsiz chiqadi.
- **Aylana:** θ'ni suv balansidan hisoblash uchun AW kerak, AW esa biz izlayotgan narsaning o'zi.
- **Termal kuzatuv siyrak:** Landsat 8–16 kunda bir marta keladi, bulut bo'lsa yanada kam. Ikki sahna orasidagi sug'orish ko'rinmay qolishi mumkin.
- **Yuza namligi yetmaydi:** Sentinel-1, optik SWIR va SMAP faqat 0–5 sm'ni ko'radi.
  - Bizga esa ildiz zonasi namligi kerak (Bastiaanssen aytgan tushuncha) — yuzadan ildiz tubigacha, paxtada 1.4 m gacha.
  - Buning ustiga SMAP pikseli 9 km, unda alohida dala ko'rinmaydi.
- **Hydrosat θ'ni o'lchamaydi, hisoblaydi.** Blogida ham shunday: "satellite images and crop models".
  - Kunlik ET (10 m) uchun bir nechta sun'iy yo'ldoshning termal ma'lumotini birlashtiradi.
  - Bulutli kunlarda ET suv balansidan olinadi.
  - θ va ildiz chuqurligi har yili oldingi suv yillari ma'lumotidan boshlanadi.
  - To'liq algoritmi ochiq emas.

## 5. Kelishilgan yechim (user: "ha shunday qilamiz", 2026-09-26)

```text
IDC suv balansi (kunlik, 3-bo'limdagi qarorlar bilan)
   ↑ namlanish hodisasi      ← Sentinel-1 / SWIR  (yomg'ir yoki sug'orish; vaqti)
   ↑ namlikni tuzatish (K)   ← termal SEBAL: EF yoki ET/ETpot → θ (faqat stress bo'lsa aniq)
   ↑ zaxira qoida            ← hodisa topilmasa-yu, model quruq desa → sug'orish qo'shiladi
   ↓
θ(t), S(t) → R, q, ΔS → AW (manbasi bilan: hodisa / qoida / tuzatish) va ETPR ssenariylari
```

- **Suv balansi (IDC)** — asosiy dvigatel. Kuzatuvlar orasidagi kunlarni to'ldiradi.
- **Termal (SEBAL)** — θ'ni tuzatadi: `θ_yangi = θ_model + K · (θ_kuzatuv − θ_model)`.
  - Ekin stressda bo'lgandagina aniq ishlaydi. Stress bo'lmasa ET = ETpot bo'ladi va termaldan θ ko'rinmaydi.
  - θ_kuzatuv uchun nomzodlar: pySEBAL (eksponensial), EFSOIL (chiziqli), FAO-56 Ks teskari hisobi.
- **Sentinel-1 / SWIR** — faqat "namlanish bo'ldi" signali.
  - O'sha kuni CHIRPS yomg'ir ko'rsatsa — yomg'ir, aks holda — sug'orish.
  - Signal faqat vaqtni beradi, miqdorni emas (miqdor — ochiq savol).
- **SWI va SMAR** (yuza namligidan ildiz zonasiga o'tish formulalari) sxemaga kirmagan.

## 6. Nega avval ma'lumot kerak

Namlikni tuzatish (K) faqat termal kuzatuv bor kunlarda ishlaydi, Landsat'ning o'zi esa kam. Shuning uchun sun'iy yo'ldosh ma'lumotini ko'paytiramiz (user qarori).

| Manba | Vazifasi | GEE'da | Muammo |
|---|---|---|---|
| Landsat 8/9 C2 L2 ST | asosiy termal + optik | bor | termal 100 m (30 m ga resample qilingan) |
| ECOSTRESS L2T LSTE V2 | qo'shimcha termal, 70 m | `NASA/ECOSTRESS/L2T_LSTE/V2` | ISS orbitasida — o'tish soati har kuni boshqa; geolokatsiya QA; bulut |
| VIIRS LST | deyarli kunlik termal | faqat `NASA/VIIRS/002/VNP21A1D`: 1 km, kunduzgi kuzatuvlar o'rtachasi | 375 m LST GEE'da yo'q; 1 km → 30 m — ~33 marta kichraytirish |
| HLS L30/S30 | optik 30 m (NDVI, LAI, albedo); keskinlashtirish uchun prediktor | bor | L30 B10 — yorqinlik harorati, LST emas; S30: `filterBounds` antimeridian xatosi, yo'l oxirigacha sinalmagan |
| Sentinel-3 SLSTR | termal ~1 km, ~10:00 da o'tadi | tekshirilmagan | — |

- **Dalil:** Liu va boshq. 2026 (RSE, GEE) Landsat, ECOSTRESS va VIIRS'ni birga ishlatgan (DMS keskinlashtirish, HLS bilan). MAE kamaygan: kunlik −8.6 %, haftalik −14.4 %, oylik −16.4 %. Lekin u yerda ET modeli DisALEXI, SEBAL emas.
- **Bizdagi xavf:**
  - keskinlashtirilgan LST'ning xatosi 1–2 K;
  - SEBAL anchorlari LST'ga juda sezgir — A4 testida 0.1 K farq ET'ni ±20 % o'zgartirgan.
  - Shuning uchun keskinlashtirilgan sahnalarda anchor qayerda tanlanishini alohida hal qilish kerak.
- **Bizning `viirs_downscaling.py`** VIIRS'ning faqat reflektans bandlarini (VNP09GA) ishlatadi. Termal VIIRS — yangi yo'l.

### GEE'da tekshirilgan raqamlar (2026-09-26, Samarqand nuqtasi 66.96°E 39.65°N)

Gridlar:

| Ma'lumot | Proyeksiya | Piksel | Piksel chegarasi (x) |
|---|---|---|---|
| Landsat C2 L2 (P155 R32) | UTM 42N | 30 m | 233085 — 15 m ga siljigan |
| HLS L30 (T42SUJ) | UTM 42N | 30 m | 300000 — 30 m ga karrali |
| ECOSTRESS L2T (T42SUJ) | UTM 42N | 70 m | HLS bilan aynan bir xil tile va boshlanish nuqtasi |
| VIIRS VNP21A1D | MODIS sinusoidal | 927 m | — |
| Bizning UZ eksport (`crs='EPSG:32642'`, 30 m) | UTM 42N | 30 m | 30 m ga karrali — HLS bilan bir xil |

- Landsat va HLS gridlari yarim pikselga (15 m) siljigan; Liu 2026 ham shuni aytgan.
- `EPSG:4326` + 30 m: Samarqandda piksel ~23 m × 30 m bo'ladi.
- GEE'dagi ECOSTRESS L2T'da faqat tizim xususiyatlari bor: kun/tun belgisi ham, geolokatsiya QA ham yo'q.
- HLS S30 `filterBounds` Samarqand nuqtasi uchun T01FBF (antimeridian) tile'ni qaytardi — xato tasdiqlandi.
- **Qayta namunalash (Landsat → MGRS):**
  - CRS bir xil (UTM 42N), lekin piksel chegaralari x va y bo'yicha 15 m farq qiladi. Har MGRS pikseli 4 ta Landsat pikselining choragini qoplaydi.
  - nearest usuli qiymatni ~15–21 m naridagi pikseldan oladi; bilinear 4 pikselni o'rtachalaydi.
  - Ta'siri kichik: Landsat termali asli 100 m; 30 m optikada faqat dala chetlari o'zgaradi.
  - Qoida: faqat bir marta qilinadi; uzluksiz bandlar — bilinear, QA/maska — nearest.
- **Suomi NPP ma'lumotlari 2026-11-01 dan to'xtaydi** (NASA/NOAA e'loni; o'rniga NOAA-21/20).
  - GEE'dagi yagona VIIRS LST (VNP21A1D) Suomi NPP'dan; NOAA-20/21 LST GEE katalogida yo'q.
  - Bizning `viirs_downscaling.py` (VNP09GA) ham Suomi NPP'dan.
- **375 m VIIRS LST** faqat VNP21IMG_NRT ko'rinishida bor: tezkor mahsulot, 2023-10-10 dan, swath L2, GEE'da yo'q. Liu 2026'dagi 375 m LST — mualliflarning o'z retrieval'i.

### Pilot inventarizatsiya — T42SUJ, 2019–2026 (2026-09-26)

- Fayllar: `inventory/` — `inventory_t42suj.py` (GEE, faqat o'qish), `inventory_summary.py`, `inventory_T42SUJ.csv` (har kuzatuv bo'yicha).
- Tile ichida ekin maydoni (ESA WorldCover) — 20.7%.
- Jadvaldagi raqam: aprel–sentabrda o'rtacha bitta ekin pikseli nechta bulutsiz termal kuzatuv olgani.
- Ustunlar:
  - ECOSTRESS — faqat kunduzgi (9–17) va ko'rish burchagi ≤25°;
  - VIIRS — ko'rish burchagi ≤40°;
  - birlashma — pastki chegara (har kun uchun eng katta ulush olingan).
  - Filtr chegaralari vaqtinchalik, qaror user'da.

| Yil | Landsat | L + ECOSTRESS | L + E + VIIRS | ECOSTRESS (tun ham) | VIIRS (hammasi) | HLS S30 (optik) |
|---|---|---|---|---|---|---|
| 2019 | 10.0 | 14.7 | 75.7 | 14.4 | 142.9 | 28.0 |
| 2020 | 9.3 | 16.0 | 77.0 | 14.9 | 139.1 | 25.1 |
| 2021 | 11.3 | 11.4 | 86.0 | 2.5 | 159.9 | 29.7 |
| 2022 | 21.4 | 21.5 | 84.5 | 3.7 | 136.0 | 28.0 |
| 2023 | 22.1 | 24.3 | 92.5 | 13.9 | 151.9 | 29.0 |
| 2024 | 22.3 | 24.0 | 82.6 | 10.7 | 125.4 | 30.5 |
| 2025 | 22.9 | 24.1 | 95.6 | 11.5 | 156.3 | 37.7 |
| 2026 | 18.5 | 20.5 | 81.8 | 11.7 | 122.0 | 8.1 |

- **Landsat:** 2019–2021 da faqat Landsat 8 — ~10; 2022 dan Landsat 8+9 — ~22.
- **ECOSTRESS:** 2019–2020 da Landsat'ga +5–7 kuzatuv qo'shadi, 2021–2026 da +0–2. Aprel–sentabrdagi 211 kuzatuvning 149 tasi (~70%) 9–17 oralig'idan tashqarida.
- **VIIRS:** asosiy chastota manbai (L+E+V 76–96 kun — mavsumning 41–52%). Lekin:
  - ko'rish burchagi medianasi 38°, har 4 kunning birida >56°;
  - o'tish vaqti 11:42–14:00;
  - Suomi NPP 2026-11-01 da to'xtaydi.
- **HLS S30 2026-yil maydan:** tasvirlar tile'ning atigi ~4% ini qoplaydi (oldin 100%). Sababi noma'lum — tekshirish kerak.

**ECOSTRESS — T42SUJ ustidan qachon tasvir beradi (2018-07…2026-09, 371 tasvir):**
- **Tekshirildi:**
  - tasvir nomidagi vaqt `system:time_start` bilan bir xil;
  - kun/tun LST bilan tasdiqlandi (yozda tungi ~289 K, kunduzgi ~311 K).
- **O'tish vaqti har kuni ~25 daqiqaga erta siljiydi.** ISS orbitasi quyosh-sinxron emas, shuning uchun to'liq 24 soatlik aylanish ~58 kunni oladi.
  - Kunduzgi (9–17) tasvirlar "deraza" bo'lib keladi: taxminan har 7 haftada (median 49 kun), har biri 1–2 hafta davom etadi.
  - Deraza ichida vaqt tushdan keyindan (~16–17) ertalabga (~9) siljiydi.
  - Aprel–sentabrda odatda ~4 deraza: aprel boshi, may oxiri–iyun, iyul oxiri–avgust, sentabr oxiri.
- **Yillar bo'yicha:**

  | Yil | Jami | Kunduzgi | Yaroqli |
  |---|---|---|---|
  | 2019 | 64 | 28 | 14 |
  | 2020 | 61 | 29 | 14 |
  | 2021 | 20 | 6 | 1 |
  | 2022 | 22 | 9 | 3 |
  | 2023 | 56 | 15 | 6 |
  | 2024 | 50 | 11 | 4 |
  | 2025 | 48 | 10 | 3 |
  | 2026 (sentabrgacha) | 46 | 8 | 2 |

  Yaroqli = kunduzgi, ko'rish burchagi ≤25°, ekin maydonining ≥30% bulutsiz.
- **Nega kam:**
  - ECOSTRESS har o'tishda tasvir olmaydi (ma'lumot hajmi va ustuvorlik tartibi);
  - 2021-06-22 da xotira nosozligi bo'lgan (NASA ECOSTRESS FAQ);
  - 2023 dan tungi tasvirlar ko'paygan (2026: 46 tadan 26 tasi 0–6 da) — sababi manbalarda yo'q;
  - tasvirlarning yarmi tile'ning <30% ini qoplaydi;
  - bulut asosiy sabab emas: kunduzgi tasvirlarda bulutli ulush medianasi 11%.
- Grafik: `inventory/ECOSTRESS_T42SUJ_vaqt.png`; skriptlar: `inventory/eco_*.py`.

Bulutsiz kuzatuv kunlari (aprel–sentabr):

| Sensor | Samarqand 2023 | Kun vaqti (mahalliy quyosh) |
|---|---|---|
| Landsat 8/9 | 19 | 10:38 |
| HLS S30 (faqat optik) | 29 | 10:44 |
| ECOSTRESS, jami | 11 | 9 tasi tun yoki tong (03:29–08:23, 21:47) |
| ECOSTRESS, kunduz 9–17 va ko'rish burchagi ≤25° | 2 | 12:30, 13:50 |
| VIIRS VNP21A1D | 149 | 11:42–13:54; ko'rish burchagi ≤30° — 55 kun, >40° — 70 kun |

- ECOSTRESS kunduzgi (9–17, ≤25°), Samarqand: 2019 — 6, 2020 — 7, 2021 — 0, 2022 — 1, 2023 — 2, 2024 — 3, 2025 — 0.
- ECOSTRESS kunduzgi, Bushland: 2020 — 16, 2021 — 17. ECOSTRESS'ning Bushland'dagi foydasi O'zbekistonga ko'chmaydi.
- Bir kunda ustma-ust (Samarqand 2023): Landsat + VIIRS — 19 Landsat kunining 14 tasida; Landsat + ECOSTRESS (kunduz) — 1 kun (29-sentabr); uchalasi — o'sha 1 kun.

### Qashqadaryo tile'lari — maydon va Landsat qoplami (2026-09-28)

- Skript: `inventory/qashqadaryo_tiles.py` (metadata + 100 m reduceRegion). Natijalar: `inventory/qashqadaryo_tiles.csv`, `qashqadaryo_tiles_qoplash.csv`, `qashqadaryo_hls_2025.csv`.
- 8 ta tile ikki UTM zonada (41 va 42).
  - Qo'shni tile'lar ~9% ustma-ust tushadi.
  - Zona chegarasida esa: T41SQC ∩ T42STH = 77%, T41SQD ∩ T42STJ = 82% — deyarli bir xil joy.
- Har tile'ni 2 ta Landsat path qoplaydi. Qoplam har (tile, path) juftligi uchun doimiy, tasodifiy emas (HLS L30 2025, `SPATIAL_COVERAGE` medianasi; ekin qoplami — shu path'ning eng katta granulasi bo'yicha):

  | Tile | 1-path: maydon / ekin, % | 2-path: maydon / ekin, % | Qashqadaryo ichidagi ekin, km² |
  |---|---|---|---|
  | T41SPC | 156: 100 / 100 | 157: 40 / 27 | 457 |
  | T41SPD | 156: 92 / 94 | 157: 61 / 31 | 1124 |
  | T41SQC | 155: 80 / 68 | 156: 71 / 89 | 2212 |
  | T41SQD | 155: 62 / 71 | 156: 90 / 89 | 4419 |
  | T42STH | 155: 98 / 93 | 156: 49 / 71 | 1789 |
  | T42STJ | 155: 79 / 87 | 156: 74 / 74 | 4304 |
  | T42SUH | 154: 70 / 89 | 155: 81 / 41 | 126 |
  | T42SUJ | 154: 47 / 19 | 155: 98 / 100 | 814 |

  - T41SQC, T42STJ va T42SUH bitta o'tishda hech qachon ≥90% qoplanmaydi.
- **HLS S30:** T42SUJ'da 2025 yildagi 147 granuladan 69 tasi tile'ning atigi 3–4% ini qoplaydi ("tasma"), 78 tasi ≥90% ini. Qolgan 7 tile'da bunday tasma yo'q (T41SPD'da bitta). Qoplam qoidasi bo'lmasa, tasma bulutsiz bo'lsa filtrdan o'tib ketadi.
- **Esri 10 m LULC** GEE'da bor (sat-io community katalogi). Qashqadaryo uchun 2017–2025 yillari mavjud, yuklash shart emas.

## 7. Ish tartibi

Tartib ishlarning bir-biriga bog'liqligiga qarab yozilgan; user o'zgartirishi mumkin.

### A. Ma'lumot — termal kuzatuvni ko'paytirish (user: "avval data")
1. **HLS optik (L30 + S30)** — keskinlashtirish uchun prediktor; NDVI, LAI, albedo.
2. **ECOSTRESS LST:** vaqt filtri, QA, bulut → 70 m → DMS bilan 30 m.
3. **VIIRS LST** → DMS bilan 30 m.
4. **Anchor strategiyasi** — keskinlashtirilgan sahnalar uchun.
5. **Tekshiruv** — har manba qo'shilgandan keyin ET yer ma'lumoti bilan solishtiriladi.

Qo'shish tartibi — qaror: Landsat → ECOSTRESS → VIIRS, optik HLS (S30 + L30) (8-bo'lim).

**Downscaling sinovi — BAJARILDI (2026-09-27, `sharpening/`, natija `sharpening/README.md`).**
- **Qarorlar:**
  - DMS OpenET asosida yozildi (user: "OpenET mos kelsa shu");
  - OpenET kodidagi xato tuzatildi: lokal regressiya 30 m gridda bajarilayotgan edi.
- **4 kun, 100 m da:**
  - ECOSTRESS 70 m — oddiy bilinear ham Landsat bilan bir xil (RMSE 0.2 K), DMS foyda bermaydi.
  - VIIRS 1 km — bilinear ham, DMS ham SEBAL anchorlari uchun yaroqsiz: sovuq nomzod +3.4 / −2.1 K, issiq–sovuq kontrasti 1–5.5 K ga buziladi.
- **Ochiq savol (24):** VIIRS SEBAL'ga qanday kiradi? (9-bo'lim)

**Sensorlararo sinov — BAJARILDI (2026-09-27, `sharpening/README.md`).** Landsat LST asos, o'sha kungi haqiqiy ECOSTRESS (4 juft) va VIIRS (12 kun).
- **ECOSTRESS LST:** R² 0.71, RMSEu 2.1 K. Downscaling usullari farq qilmadi. Issiq–sovuq farqi har doim 3.4–6.1 K kichik.
- **VIIRS LST:**
  - 1 km da Landsat bilan yaxshi mos: R² 0.79, bitta anomal kunsiz 0.67–0.97.
  - 30 m da eng yaxshi usul — faqat Random Forest: RMSEu 3.0 K, R² 0.68; zich ekinda R² 0.26.
  - TsHARP ishlamaydi.
- **SEBAL_Milliy, ECOSTRESS vs Landsat (4 kun):**
  - fazoviy naqsh mos (3 kunda R² 0.78–0.85);
  - o'rtacha ET darajasi beqaror: −45%..+8%;
  - piksel xatosi ~1–1.4 mm/kun.
- **SEBAL_Milliy, VIIRS vs Landsat (6 kun, 2026-09-27):**
  - bilinear VIIRS: ET +13% (+1..+31%), R² 0.71; siyrak ekinda +56% — naqsh siqiladi;
  - RF bilan keskinlashtirilgan VIIRS (6 kun, 2026-09-28): ET +16% (+0..+26%), RMSE 1.02 mm/kun, R² 0.82 (bilinearda 0.71);
  - xulosa: RF naqshni yaxshilaydi, lekin VIIRS'dan hisoblangan SEBAL ET Landsat'nikidan doimiy yuqori (~+15%). Bu vaqtga bog'liq sistematik og'ish, uni Landsat–VIIRS juftlari (8 yilda 180 ta) bilan kalibrlash mumkin bo'lishi mumkin;
  - takrorlanuvchanlik masalasi: cheklangan GEE rejimida anchor usuli o'zgarib ketdi (2020-08-03) — kvota tiklangach tekshirish kerak.
- **T1 hold-out sinovi (2026-09-28, 2 juft):**
  - hozirgi usul (eng yaqin sahna F o'zgarmas) 16 kunda −4..+55% xato beradi;
  - VIIRS termali eskirgan optika bilan kam yordam beradi;
  - yangi optika bilan xato keskin kamayadi: mavsum oxirida +55% → +16%, RMSE 1.45 → 0.85.
  - Xulosa: kundalik ET uchun L30+S30 optikasi zarur; VIIRS'ning qo'shimcha foydasini P3 (faqat optika) bilan o'lchash kerak.
- **T-A pilot (2026-09-28, 10 kun, `sharpening/README.md`):**
  - umumiy k = 0.92 → og'ish +10.9% dan +2.1% ga tushdi (LOO); kunlik qoldiq −12.5..+12.8%;
  - oktabr kuni (2022-10-12) +66% — kechki mavsum juftlari ko'proq kerak;
  - NDVI'ga bog'liqlik kichik (±4%);
  - ETrF bilan kunlikka o'tkazish og'ishni tushuntirmaydi;
  - VIIRS optikadan tashqari foyda beradi: 1 juftda T-A RMSE 1.07, faqat optika 1.92, hozirgi usul 1.61;
  - cheklov: Landsat kunlarida VIIRS ko'rish burchagi doim ~25°, shuning uchun burchak ta'sirini kalibrlash juftlaridan o'lchab bo'lmaydi.
- **User taklifi (2026-09-28):** VIIRS har kuni + L30/S30 optikasi (bulut filtri bilan). Taklif qilingan qoida: piksel bo'yicha ±2 kun ichidagi eng yaqin HLS; bir xil yaqinlikda L30 (bulut niqobi yaxshiroq), S30 bo'shliqni to'ldiradi.
- **Ochiq savol (25):** ECOSTRESS va VIIRS ET'si kunlik birlashmaga qanday kiradi? Variantlar:
  - faqat vaqt oynasi (Landsat soatiga yaqin o'tishlar);
  - naqsh sifatida — daraja eng yaqin Landsat sahnasiga moslanadi;
  - ko'proq juftlik yig'ib, qayta baholash.

**Ko'p sensorli yo'l sinovi — BAJARILDI (2026-09-30 – 2026-10-03, SEBAL_Milliy).**
1. **VIIRS daraja koeffitsienti k** — T42SUJ ∩ Qashqadaryo 2025, 11 ta bir kunlik Landsat + VIIRS juft:
   - xom VIIRS ET Landsat bilan deyarli bir xil: bias −1.5% (7690 ta 1 km blok), RMSD 0.65 mm/kun, r 0.90;
   - juftlar k 0.73…1.28 — tarqoqlik, oylik trend yo'q (median 1.026);
   - k = 0.92 VIIRS'ni −9.4% pasaytirardi → **k = 1** (user qarori, 2026-10-02; 8-bo'lim).
2. **Cold anchor, VIIRS va Landsat** — muammo tasdiqlanmadi:
   - VIIRS cold anchor LST Landsat'nikidan +0.34 K (umumiy siljish olinganda −0.11 K);
   - RF sovuq dumni qisqartirmagan (nisbat 1.04), issiq dumni 6% qisqartirgan;
   - VIIRS ~2 soat kech o'tadi (mahalliy quyosh vaqti 12:38 va 10:40) — SOLAR_FRAC bilan kunlikka o'tkazishda farq qilmaydi.
3. **Sirdaryo, 2025 iyul, oylik raster** — yangi rejim (k = 0.92) va eski Landsat rejimi (BOTH), T42TVK (viloyat ekinining 82%):
   - yangi 155.2, eski 133.7 mm/oy → **+21.5 mm (+16%)**, RMSD 28 mm, r 0.94; farq g'arbda kattaroq;
   - Sirdaryo'da yer ma'lumoti (GT) yo'q — qaysi biri to'g'riligini aytib bo'lmaydi. Xulosa faqat shu: Landsat to'g'ri deb olinsa, yangi rejim baland;
   - qolgan Sirdaryo hisoblari (k = 1 bilan qayta, farqni ajratish) to'xtatildi — user: GEE kvotasi bekorga ketmasin.
4. **Bushland 2021 lizimetri (GT)** — ikkala rejim bitta tile'da (T13SGU ∩ Texas), may–oktabr, 4 lizimetr, oylik:

   | Variant | MBE | RMSE, mm/kun | r² |
   |---|---|---|---|
   | Eski Landsat rejimi (faqat WRS 30/36 — user qarori) | −39% | 1.96 | 0.53 |
   | Yangi rejim, faqat Landsat kunlari | −7% | 1.20 | 0.53 |
   | Yangi rejim + VIIRS, k = 1 | +4% | 1.19 | 0.56 |
   | Yangi rejim + VIIRS, k = 0.92 (solishtirish uchun) | −1.5% | 1.15 | 0.61 |

   - Eski rejim may–iyunda ET ≈ 0 beradi, iyul–avgustda −30…−38%.
   - Yangi rejimning yutug'i kalibratsiyadan: H3 anchor, tile ∩ hudud ekini, ikkala path sanalari birga (9 o'rniga 14 Landsat sahna). VIIRS'dan emas.
   - Sahna kunlarida Landsat va VIIRS xatosi har oyda bir xil belgida: model past ET paytida (may, iyun, oktabr) oshirib, cho'qqida (avgust) kamaytirib baholaydi — bu modelning o'z xatosi. Avgust va sentabrda VIIRS kunlari Landsat kunlaridan ham yaqinroq (−8% va −32%; −2% va −10%).
   - VIIRS'ga xos kichik ta'sir: 1 km da qo'shni dalalar aralashadi (10-20 kuni Landsat sharq va g'arb lizimetrlarni ajratdi, VIIRS ajratmadi).
   - Lokal oylik hisob pipeline'ning o'z oylik CSV'i bilan bir xil (farq < 1 mm/oy).
5. **Xulosa (user, 2026-10-03):** VIIRS ishimizni yaxshiladi. Qolgan xato VIIRS yoki Landsat ma'lumotidan emas — SEBAL_Milliy modelining o'zidan. Model xatosi va ma'lumot xatosi alohida baholanadi (8-bo'lim).
6. Yo'lda topilib tuzatilgan xatolar — `tuzatishlar.md` #98–#103.
7. Skriptlar va natija fayllari: `validation_result/viirs_k/`, `validation_result/bushland_viirs/`, `validation_result/sirdaryo_2025_07/` (har birida `skriptlar/`). Gitda yo'q — `sebal_v8` arxivida.

Sinov tuzilishi (tarix uchun):
- Sinov qadamlari:
  1. Landsat LST'ni 70 m va 1 km ga yig'ish (ECOSTRESS va VIIRS'ni taqlid qilish).
  2. HLS yordamida DMS bilan qayta 30 m ga keskinlashtirish.
  3. Asl Landsat bilan solishtirish: LST xatosi va SEBAL ET farqi.
- Solishtiriladigan anchor strategiyalari:
  - anchor keskinlashtirilgan LST'dan;
  - anchor asl (dag'al) LST'dan;
  - keskinlashtirishsiz, ET downscaling.
- Adabiyot:
  - DMS (Gao 2012, Xue 2020): ECOSTRESS → 30 m, RMSEu 1.2–1.8 K; VIIRS 375 m → 30 m, RMSEu 1.3–1.7 K. Bizda VIIRS 1 km, shuning uchun xato kattaroq bo'lishi kutiladi.
  - GEE-DMS (Liu 2026): mahalliy OLS (25 piksel oyna) + global Random Forest; EC box ECOSTRESS 270 m, VIIRS 780 m; kod: github.com/Open-ET/openet-landsat-lst (litsenziya hali tekshirilmagan).

### B. Suv balansi dvigateli
1. **Dizayn hujjati** — kodsiz: tenglamalar, belgilar, kiritmalar. User tasdiqlaydi.
2. **Prototip:**
   - S, R, q;
   - boshlang'ich holat — ikki chegara usuli;
   - ETPR ikki ssenariysi;
   - kunlik balans yopilishi testi.

   Mavjud kodga faqat user ruxsati bilan tegiladi.
3. **Namlik operatorlarini sinash** (θ_kuzatuv).
4. **Tuzatish (K), hodisa detektori, zaxira qoida.**
5. **Natijalar:** AW (manbasi bilan), ETPR ssenariylari, ETAW, noaniqlik.

### C. O'zbekiston hududida qo'llash
- Hududni user tanlaydi.
- Kerakli ma'lumotlar:
  - ekin xaritasi va quduqlar (user topadi);
  - sug'orish usuli;
  - suv yetkazib berish hajmlari (AW'ni tekshirish uchun).

## 8. Qabul qilingan qarorlar

| Mavzu | Qaror |
|---|---|
| Sahnasiz kun ET | hozirgi usul (`daily_et.py`: eng yaqin yaroqli sahna) |
| ETPR | ikki ssenariy parallel ("noaniqlik konverti", haqiqiy min/max emas) |
| Yog'in P | faqat CHIRPS |
| Ildiz chuqurligi Z | Zmax, yil davomida o'zgarmas |
| Oqim R | IDC: namlikka bog'liq SCS-CN |
| Perkolatsiya q | van Genuchten–Mualem; oddiy chelak — QA uchun |
| Boshlang'ich holat | ikki chegara (θ₀ = WP va θ₀ = FC); yaqinlashish chegaralari sezgirlik bilan tanlanadi |
| ETGW | quduq ma'lumoti kelguncha 0, bayroq bilan |
| AW | AW = ET + R + q + ΔS − P |
| θ | 5-bo'limdagi sxema |
| Sun'iy yo'ldosh ma'lumoti | ko'paytiriladi: ECOSTRESS, VIIRS, HLS |
| Asos grid (2026-09-26) | HLS/MGRS, 30 m, UTM (har tile o'z zonasida). Landsat WRS-2 endi hisob hududi emas, faqat metadata |
| Pilot (2026-09-26) | tile T42SUJ (Samarqand), 2019–2026 — avval ma'lumot inventarizatsiyasi |
| VIIRS ko'rish burchagi (2026-09-28) | hozircha ≤40°. Keyinroq boshqa chegaralar (masalan 30°, 50°) MBE/RMSE bilan sinaladi: yaxshiroq bo'lsa almashtiriladi, bo'lmasa 40° qoladi |
| Asosiy g'oya (2026-09-28, user) | Landsat 8+9 (BOTH) asosiy tarmoq bo'lib qoladi. Sahnalar orasidagi kunlar VIIRS tarmog'i bilan to'ldiriladi (VIIRS LST + HLS L30/S30 optika → SEBAL VIIRS vaqtida). Termal kuzatuv bo'lmagan kunlar suv balansi bilan to'ldiriladi — Hydrosat kabi |
| Sensorlar tartibi (2026-09-26) | Landsat → ECOSTRESS → VIIRS; optik — HLS (S30 + L30). Bitta MGRS tile ichida uchala termal sensor ishlatiladi. ECOSTRESS tashlanmaydi: kam bo'lsa ham, ba'zi kunlarda foyda beradi |
| Hisob va eksport (2026-09-28, user) | Oraliq natija asset'ga yozilmaydi. Downscaling GEE grafi ichida, LST kerak bo'lgan joyda hisoblanadi. Faqat yakuniy natija Drive'ga eksport qilinadi |
| VIIRS bulut filtri (2026-09-28, user) | Landsat bilan bir xil qoida: WorldCover ekin maydoni ustida yomon piksellar ulushi < `CROP_CLOUD_MAX` (hozir 30%, `config.py`). Oylar bo'yicha cheklov yo'q |
| VIIRS sahnasi optikasi (2026-09-28, user) | Downscaling qaysi HLS tasvir (L30 yoki S30) bilan qilingan bo'lsa, SEBAL'ning optik bandlari ham aynan o'sha tasvirdan olinadi |
| VIIRS ET darajasi (2026-09-28, user) | Xom ET_V ham, tuzatilgan k·ET_V ham saqlanadi (k = 1 — 2026-10-02, user qarori: 11 ta bir kunlik juft, xom VIIRS bias −1.5%, r 0.90). Faqat koeffitsientga ko'paytirish yetarli aniqlik bermaydi |
| Albedo sinovi (2026-09-28, user) | Olmedo BRDF tuzatishsiz va BRDF tuzatishli (`olmedo_brdf`) solishtiriladi — ET'ga ta'siri ko'riladi |
| Tile va anchor (2026-09-28, user) | Anchor MGRS tile bo'yicha tanlanadi. Har tile o'z pikseliga ega: ustma-ust qismda piksel bitta tile'ga tegishli. 2026-09-29 da aniqlashtirildi — «Anchor hududi» va «Tile'lar va egalik» qatorlari |
| Ekin xaritasi (2026-09-28, user) | Esri 10 m LULC (sat-io), har yil o'z yili (2026 uchun 2025); ekin = 5 (Crops). Ekin bo'lmagan qism maskalanmaydi — SEBAL butun tile'da ishlaydi, bulut qoidasi faqat ekin ustida. Chiqishga `CROP_MASK` bandi qo'shiladi (hisobi og'ir bo'lmasa) |
| Bulut filtri (2026-09-28, user) | Hamma sensor uchun bir xil: (1) dastlabki — sahna yoki tile buluti < 80%; (2) tasvir ko'rgan ekin ustida bulut ≤ 20%; (3) tasvir tile ekinining kamida 10% ini ko'rishi shart (S30 tasmalari chiqadi). Bulutli piksel har doim maskalanadi |
| VIIRS sifat maskasi (2026-09-28, user) | QC 0–1-bitlar = 0 va 4–5-bitlar (bulut bayrog'i) = 0; ko'rish burchagi ≤ 40° |
| VIIRS + HLS (2026-09-28, user) | Piksel faqat HLS'da ham, VIIRS'da ham toza bo'lsa olinadi |
| Kunlik va oylik (2026-09-28, user) | Har piksel uchun ustuvorlik: Landsat > ECOSTRESS > VIIRS. Landsat yetib bormagan yoki bulutli ekin keyingi manbadan olinadi. Termal kuzatuvsiz kun — hozir eng yaqin sahna, keyin suv balansi. Oylik ET = kunlik ET'lar yig'indisi |
| Landsat tarmog'i (2026-09-28, user) | Landsat Collection 2 Level-2 qoladi (HLS L30 emas). Bir kunlik qatorlar birlashtiriladi |
| Tadqiqot tile'i (2026-09-28, user) | T42SUJ. Birinchi mahsulot — 2025 aprel–oktabr kalendari (qaysi kun SEBAL, qaysi kun suv balansi) |
| Anchor hududi (2026-09-29, user) | Anchor viloyat ekinidan olinadi: tile ∩ viloyat (z0m persentillari va sahna QC ham shu hududda). Tile boshqa viloyatni (masalan, Samarqand, Buxoro) qoplasa ham anchor u yerga ketmaydi. Dalil: tuzatishdan oldin Qashqadaryo sinovida (T42SUJ, 2025-04-10/11) 6 anchor nuqtadan 3 tasi Samarqandga tushgan. VIIRS RF downscaling o'qitishi butun tile'da qoladi |
| Tile'lar va egalik (2026-09-29, user) | Har viloyat uchun bir xil avtomatik qoida (`plan_tiles`): (1) viloyat tile'lari HLS granulalaridan topiladi (`tiles=None`; ro'yxat berilsa ham shu qoida bilan tekshiriladi); (2) tile'ning to'liq footprint'ida viloyat ekini < 100 km² bo'lsa, tile tushiriladi — anchor ishonchsiz; (3) ustma-ustlik: tile'lar viloyat ekini ko'pligi bo'yicha tartiblanadi — birinchisi butun, keyingisi faqat qoplanmagan qismni oladi ("bittasi butun, qolgani kesik"); kichik kesik qismlar ham hisoblanadi; (4) anchor — tile'ning butun footprint'i ∩ viloyat ekinidan, eksport — faqat tile egaligida. Qashqadaryo: 8 tile avtomatik topildi (qo'lda berilgani bilan bir xil), T41SQD butun, 6 tasi kesik, T42SUH (10 km²) tushirildi, ekin qoplami 99.8%. Samarqand: 10 tile topildi, 5 tasi ishlanadi, 99.9% |
| Ko'p sensorli yo'l bahosi (2026-10-03, user) | Bushland lizimetri (GT) bo'yicha yangi rejim eski Landsat rejimidan aniqroq (oylik bias −39% → −7%, VIIRS bilan +4%). VIIRS qoldiriladi — ishni yaxshiladi. Qolgan xato SEBAL_Milliy modelining o'zida; model xatosi va ma'lumot xatosi alohida baholanadi. GT bo'lmagan hududda (Sirdaryo) rejimlar aniqlik bo'yicha solishtirilmaydi — faqat farq ko'rsatiladi (7-A) |

## 9. Ochiq savollar (user qarori kutilmoqda)

**Ma'lumot (A):**
1. ~~Qo'shish tartibi~~ — **qaror: Landsat → ECOSTRESS → VIIRS, optik HLS (S30 + L30)** (8-bo'lim).
2. Chiqish grid'i 30 m bo'ladimi?
3. ECOSTRESS uchun vaqt filtri — qaysi soatlar oralig'i (masalan, 10:00–15:00)?
4. VIIRS: GEE'dagi 1 km VNP21A1D'mi yoki 375 m LST'ni o'zimiz ishlab chiqaramizmi?
5. Keskinlashtirilgan sahnada anchor qayerda tanlanadi: native rezolyutsiyada, Landsat sahnasiga bog'lab yoki 30 m LST'da?
6. Sentinel-3 SLSTR qo'shiladimi?
7. ~~Tekshiruv Bushland 2021 lizimetri bilan bo'ladimi?~~ — **ET bo'yicha bajarildi (2026-10-03, 7-A).** Zaxira o'zgarishi va 2/6 sm dagi namlik — suv balansi bosqichida.

**Dvigatel (B):**

8. Dvigatel qayerda ishlaydi: GEE'da (piksel bo'yicha) yoki lokal (GEE'dan eksport qilingan kiritmalar bilan)?
9. Hisob davri: kalendar yilmi yoki suv yili (1-okt – 30-sen)?
10. Namlik operatori: pySEBAL, EFSOIL, FAO-56 Ks — qaysilari sinaladi?
11. Tuzatish usuli: bitta K koeffitsientimi yoki ansambl (EnKF)?
12. Hodisa detektori: faqat Sentinel-1'mi yoki Sentinel-1 + SWIR?
13. Hodisa topilganda sug'orish miqdori qancha deb olinadi: FC gacha to'ldiriladimi yoki sug'orish usuliga xos me'yor olinadimi?
14. Ekin ma'lumoti bo'lmagan dalada Z qanday olinadi?

**Grid va kunlik birlashtirish (V4 uchun; 2026-09-26 qo'shildi):**

15. ~~Asos grid~~ — **qaror: HLS/MGRS 30 m** (8-bo'lim).
16. ~~SEBAL kalibratsiya (anchor) hududi qanday bo'ladi?~~ — **qaror: MGRS tile bo'yicha; chok chiqsa qayta ko'riladi** (8- va 10-bo'lim). **2026-09-29 aniqlashtirildi: anchor tile ∩ viloyat ekinidan** (8-bo'lim, «Anchor hududi»). Uch variant edi:
    - har MGRS tile alohida;
    - qat'iy kalibratsiya zonalari (bir nechta tile bloki yoki iqlim/relyef zonalari);
    - tile bo'yicha kalibratsiya + qo'shni tile'lar bilan silliqlash.

    Talablar va dalillar:
    - Hudud foydalanuvchi ROI'siga bog'liq bo'lmasligi kerak, aks holda bir dala ikki xil ET oladi.
    - Hudud ichida ob-havo bir xil bo'lishi kerak.
    - Long va boshq. 2011 (JGR): SEBAL anchor tanlashga va hudud o'lchamiga juda sezgir.
    - Chok kattaligini MGRS tile'larning ustma-ust tasmasida (9.8 km) o'lchash mumkin.
    - Kuzatuv tile'ning kamida qancha qismini qoplashi kerak — shu savolning bir qismi.
17. ~~Bir kunda bir nechta termal kuzatuv bo'lsa~~ — **qaror: piksel bo'yicha ustuvorlik Landsat > ECOSTRESS > VIIRS, kunlik ET darajasida** (8-bo'lim).
18. ~~Landsat kunlarida optik kirish: C2 L2 SR yoki HLS L30?~~ — **qaror: C2 L2 qoladi** (8-bo'lim).
19. ~~Birlashtirilgan kirish ma'lumotini GEE'da asset sifatida saqlaymizmi yoki har safar kod bilan hisoblaymizmi?~~ — **qaror: asset yo'q, har safar kod bilan (GEE lazy); faqat yakuniy natija Drive'ga** (8-bo'lim).
20. Suomi NPP'dan keyin VIIRS uchun manba: NOAA-20/21 LST'ni (VJ121A1D, VJ221A1D) GEE'ga o'zimiz yuklaymizmi yoki boshqa yo'l tanlaymizmi? Bu savol `viirs_downscaling.py` (VNP09GA) ga ham tegishli. (2026-10-02, user: hozircha qoldirildi.)
21. ~~Pilot tile~~ — **qaror: T42SUJ, 2019–2026** (8-bo'lim).
22. **Tungi ET qanday hisobga olinadi?** (2026-09-26)
    - Bushland 2021 lizimetri (15 daqiqalik, NE/SE, quruq kunlar): tungi (Rn < 0) ET kunlik ET'ning 4–12% ini tashkil qiladi — iyul ~4%, avgust 5–7%, sentabr 9–12%; bir kechada 0.2–0.6 mm.
    - SEBAL_Milliy kunlik ET = `SOLAR_FRAC × Rs24`. Tunda Rs = 0, shuning uchun tungi ET avtomatik 0 bo'lib qoladi.
    - SEBAL_ID esa `ETrF × ETr24` bilan hisoblaydi; ETr24 soatlik yig'indi bo'lgani uchun tungi soatlarni ham qamraydi.
    - Tungi ET SEBAL'ning o'zidan (tungi LST bilan) topilmaydi: kechasi energiya balansi qoldig'i ishonchsiz va anchorlar ishlamaydi.
    - Skript: `inventory/bushland_tungi_et.py`.
24. **VIIRS SEBAL'ga qanday kiradi?** (2026-09-27, downscaling sinovidan keyin) — **amalda hal bo'ldi (2026-10-03):** VIIRS LST RF bilan 30 m ga keltiriladi va SEBAL VIIRS vaqtida hisoblanadi (LHLSVIIRSECO, 8-bo'lim «Asosiy g'oya»). Bushland lizimetri bilan tekshirildi (7-A).
    - 30 m ga keltirilgan VIIRS LST anchorlar uchun yaroqsiz chiqdi.
    - Variantlar:
      - VIIRS'ni faqat vaqt signali sifatida ishlatish: 1 km da EF/ETrF o'zgarishini hisoblab, Landsat 30 m naqshiga o'tkazish (sinov kerak);
      - hozirgi yo'l — VIIRS'dan faqat vegetatsiya indekslari (`viirs_downscaling.py`), termal yo'q;
      - DMS'ni 1 km uchun yaxshilashga urinish.
    - ECOSTRESS uchun asosiy savol endi rezolyutsiya emas: o'tish vaqti, geolokatsiya va kalibrovka — haqiqiy 2023-09-29 sinovi kerak.
23. **Tungi LST'ni namlik (θ) indikatori sifatida ishlatamizmi?** Kunduz–tun LST farqi termal inersiyani ko'rsatadi.
    - ECOSTRESS'da kunduz–tun juftlari kam.
    - VIIRS'da har kuni ikki kuzatuv bor (~13:30 va ~01:30; VNP21A1N GEE'da mavjud), lekin aniqligi 1 km va Suomi NPP 2026-11-01 da to'xtaydi.
26. ~~**VIIRS ET darajasini qanday moslaymiz?**~~ — **qaror: (a) mustaqil VIIRS-SEBAL + bir kunlik juftlar; k = 1 (2026-10-02, 7-A va 8-bo'lim).** Savol edi (2026-09-28):
    - T1 nisbat usuli 30 m naqshni eski Landsat sahnasida qotirib qo'yadi; user uni asosiy yo'l sifatida qabul qilmadi.
    - Variantlar:
      - (a) mustaqil VIIRS-SEBAL + bir kunlik Landsat–VIIRS juftlaridan kalibrlash (k = median(ET_L/ET_V), keyin qoldiq tahlili);
      - T1 — faqat QA va zaxira sifatida;
      - VIIRS termalisiz: Landsat + HLS optika + suv balansi.
    - SEBAL'da sensorlar orasida umumiy daraja asosi yo'q (DisALEXI'da ALEXI bor), shuning uchun kalibrlash zarur.
    - Hisob hajmi: hamma juftlar (113–180) × 2 SEBAL + RF kvotaga sig'maydi → stratifikatsiyalangan tanlama kerak.
27. ~~**Tile qoplami qoidasi**~~ — **qaror: tasvir tile ekinining ≥ 10% ini ko'rsin, ko'rgan ekin ustida bulut ≤ 20%** (8-bo'lim). Savol edi (2026-09-28):
    - Hozirgi bulut foizi faqat tasvir qoplagan qismdan hisoblanadi. Tile ekin maydonining qancha qismi qoplangani alohida tekshirilmaydi.
    - Savol: eng kam qoplam qancha bo'ladi (masalan, 30%)? Yoki chegara qo'yilmaydi va kichik qoplamdagi anchor sifati sinov bilan tekshiriladi?
28. ~~**Ustma-ust tile'larda piksel kimniki**~~ — **qaror: har tile o'z pikseliga ega** (8-bo'lim). **2026-09-29: bittasi butun, qolgani kesik** — tile'lar viloyat ekini ko'pligi bo'yicha tartiblanadi (8-bo'lim, «Tile'lar va egalik»). Savol edi (2026-09-28):
    - Viloyat mahsulotida bitta piksel ikki tile'dan ikki xil ET oladi; UTM zona chegarasida ustma-ust tushish 77–82%.
    - Taklif (MGRS qoidasi): piksel o'z UTM zonasidagi va o'z 100 km kvadratidagi tile'ga tegishli. Anchor hisobi esa butun tile bo'yicha qoladi. Tanlanmadi (2026-09-29): ikkala tile ham 66°E da kesilardi, chok Qarshi ekin massivi o'rtasidan o'tardi.

**Ko'p sensorli yo'l sinovidan chiqqan savollar (2026-10-02 – 10-03):**

29. **Eng yaqin sahna va UTC vaqti.**
    - `daily_et._nearest_valid` sahnagacha masofani kunning UTC 00:00 idan o'lchaydi.
    - UTC−6 (Texas) da Landsat (~17:20 UTC) keyingi kunga yaqinroq chiqadi — oylik hisobda sahna 1 kunga siljiydi.
    - O'zbekistonda (UTC+5) muammo yo'q.
    - Savol: mahalliy kun o'rtasidan o'lchanadigan qilib tuzatilsinmi?
30. **Sahna xatosi eski Landsat yo'lida.** Yangi yo'lda bitta sahna xatosi endi tile'ni to'xtatmaydi (`tuzatishlar.md` #100). Eski yo'lga (`main.process_tile`) ham shu qo'shilsinmi?
31. **Eski yo'l: sahnasiz WRS tile.** Sirdaryo BOTH sinovida sahnasi qolmagan P155 tile'lari "Collection.toList: count must be positive" bilan yiqildi. Bunday tile bo'sh deb o'tkazib yuborilsinmi?
32. **VIIRS 1 km aralashuvi.** Qo'shni dalalar ajralmaydi (Bushland 2021-10-20). Keyinroq ko'riladimi?

## 10. Keyinga qoldirilganlar (esdan chiqmasin)

- **Ekin xaritasi kelgach** — ekin bosqichlari bo'yicha ildiz chuqurligi Z(t) qo'yiladi. Ogohlantirish: yil bo'yi Zmax olinsa, yomg'irli mavsumda zaxira oshib ketadi va ETPR yuqori baholanishi mumkin. Buni Z(t) sezgirlik testi ko'rsatadi.
- **Quduq ma'lumotlari kelgach** — ETGW ikki yo'l bilan topiladi:
  - quduqdagi sizot chuqurligi + kapillyar ko'tarilish formulasi (Liu va boshq. 2006);
  - SEBAL bilan sug'orilmaydigan joy va paytni aniqlash.
- **q:** oddiy chelak va van Genuchten natijalari keskin farq qilsa — Ksat va tuproq parametrlarining sezgirligi tekshiriladi.
- **Yaqinlashish chegaralari** (masalan, 1 mm va 0.01) — qat'iy belgilanmaydi, sezgirlik testi bilan tanlanadi.
- **Anchor — tile ∩ viloyat ekini** (user qarori, 2026-09-28; 2026-09-29 aniqlashtirildi — avval butun MGRS tile edi). Bitta Landsat o'tishi bir nechta tile'da har xil anchor bilan hisoblanadi. Agar natijada tile egaligi chegaralarida ET choki chiqsa, masala qayta ko'tariladi.
- **Anchor sinflari — Esri LULC bo'yicha** (user qarori, 2026-09-28). Hali boshlanmagan — anchor qismiga kelganda shu asosda ishlanadi.
  - Cold — Esri 5 (Crops).
  - Hot — H3:
    - avval Esri 5 ichida NDVI eng past (yalang'och, bo'sh qoldirilgan) dalalar — CIMEC (Allen 2013) va geeSEBAL (Laipelt 2021) usuli;
    - nomzod yetmasa, Esri 8 (Bare ground) istisnolar bilan: qiyalik (tog' va tog' etagi), albedo oralig'i (sho'rxok, tosh), dalaga yaqinlik, balandlik farqi.
  - Hot uchun hech qachon olinmaydigan sinflar: 7, 1, 2, 4, 9, 10, 11.
  - Sinov: T42SUJ'da hozirgi zona, H1 va H2 solishtiriladi; ixtiyoriy — Bushland lizimetri.
- **SEBAL_Milliy modelining o'z xatosi** (user, 2026-10-03). Bushland'da model past ET paytida (mavsum boshi va oxiri) oshirib, cho'qqida kamaytirib baholaydi. Bu Landsat kunlarida ham bor, VIIRS'ga bog'liq emas (7-A). Tuzatish ishi Landsat kunlarida olib boriladi; qachon boshlash — user qarori.
- **Piksel darajasida ishlash — keyin** (2026-09-28). Hozir asosiy arxitektura tile bo'yicha: har tile o'z pikseliga ega, ustma-ustlikdan iloji boricha qochiladi. Keyinchalik tile emas, piksel darajasida yurganda pikselning qaysi tile'ga tegishliligi yo'qoladi — shuni hisobga olish kerak.

## 11. Manbalar

Asosiy papka: `E:\My_projects\hydrosat`.

**Hydrosat / Madera:**
- `1.-GSA-Committee-Packet.pdf` — Hydrosat ilovasi; ETAW formulalari 69–70-betlarda;
- `Responses-to-Grower-Questions-from-Hydrosat.pdf`;
- `Madera-SEBAL-Root-Zonev-7-pp-pdf.pdf`;
- `5-022.06_WY_2022_Madera_Subbasin_Joint_GSP_Appendices_G-H.pdf` — VPP 2022 yakuniy hisoboti, H ilovasi;
- `Madera_County_GSA_Remote_Sensing_Workshop_20220608.pdf`;
- `250127_VPP_Grower_Workshop.pdf`;
- `Synthetic-Daily-20-Meter-Surface-Temperature-...pdf` — Hydrosat'ning kunlik 20 m LST mahsuloti.

**IDC:** `idc-2025.0.243/` — DWR hujjati.

**Sharhlar:**
- Bastiaanssen 2026 (Irrigation and Drainage);
- SWEO — Hessels, Davids va Bastiaanssen 2022.

**Termal ma'lumotlarni birlashtirish** (`data_sharpening/`):
- Liu va boshq. 2026 (RSE);
- Xue va boshq. 2020 (RSE) — ECOSTRESS va VIIRS LST'ni HLS bilan keskinlashtirish;
- Xue va boshq. 2021 (Remote Sensing) — HLS va keskinlashtirilgan VIIRS bilan kunlik ET;
- Pierrat va boshq. 2025 (WRR) — ECOSTRESS C2 ET mahsulotlarini baholash.

**Namlik** (`moisture/`):
- Kisekka va boshq. 2022 (Irrigation Science). Annotatsiyasiga ko'ra: pySEBAL va EFSOIL hamma nuqtada ishonchli natija bermagan; Random Forest joydagi sensorlar ma'lumoti bilan o'qitilganda yaxshi ishlagan.

**Sizot suvi** (`sizot-suvi/`):
- Forkutsa 2009 — Xorazm; paxta ETa'sining 399 mm gachasi sizot suvidan;
- Liu va boshq. 2006 — parametrik kapillyar ko'tarilish (CR);
- Cholpankulov 2008 — Farg'ona;
- Awan va Tischbein 2014 — Xorazm, HYDRUS.

**Internet:**
- Ibrakhimov 2007 — Xorazm GME, 2000 dan ortiq quduq;
- HESS 2024 — Ebro, sug'orishni hisoblash usullarini solishtirish;
- GEE katalogi — ECOSTRESS L2T LSTE V2, VNP21A1D, SMAP SPL4SMGP.
