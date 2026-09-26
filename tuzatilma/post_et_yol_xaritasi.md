# Post-ET yo'l xaritasi — ET'dan keyingi mahsulotlar

Yangilangan: 2026-09-26. Maqsad — adashmaslik: qayerdamiz, nima qilmoqchimiz, muammo nimada, qanday yechim kelishilgan, keyingi qadam nima.

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

## 7. Ish tartibi

Tartib ishlarning bir-biriga bog'liqligiga qarab yozilgan; user o'zgartirishi mumkin.

### A. Ma'lumot — termal kuzatuvni ko'paytirish (user: "avval data")
1. **HLS optik (L30 + S30)** — keskinlashtirish uchun prediktor; NDVI, LAI, albedo.
2. **ECOSTRESS LST:** vaqt filtri, QA, bulut → 70 m → DMS bilan 30 m.
3. **VIIRS LST** → DMS bilan 30 m.
4. **Anchor strategiyasi** — keskinlashtirilgan sahnalar uchun.
5. **Tekshiruv** — har manba qo'shilgandan keyin ET yer ma'lumoti bilan solishtiriladi.

Qo'shish tartibi (taklif; 9-bo'lim, 1-savol): V1 Landsat → V2 +ECOSTRESS → V3 +VIIRS → V4 kunlik birlashtirish.

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

## 9. Ochiq savollar (user qarori kutilmoqda)

**Ma'lumot (A):**
1. Qo'shish tartibi V1 → V2 → V3 → V4 shundaymi?
2. Chiqish grid'i 30 m bo'ladimi?
3. ECOSTRESS uchun vaqt filtri — qaysi soatlar oralig'i (masalan, 10:00–15:00)?
4. VIIRS: GEE'dagi 1 km VNP21A1D'mi yoki 375 m LST'ni o'zimiz ishlab chiqaramizmi?
5. Keskinlashtirilgan sahnada anchor qayerda tanlanadi: native rezolyutsiyada, Landsat sahnasiga bog'lab yoki 30 m LST'da?
6. Sentinel-3 SLSTR qo'shiladimi?
7. Tekshiruv Bushland 2021 lizimetri bilan bo'ladimi (kunlik ET, zaxira o'zgarishi, 2 va 6 sm dagi namlik)?

**Dvigatel (B):**

8. Dvigatel qayerda ishlaydi: GEE'da (piksel bo'yicha) yoki lokal (GEE'dan eksport qilingan kiritmalar bilan)?
9. Hisob davri: kalendar yilmi yoki suv yili (1-okt – 30-sen)?
10. Namlik operatori: pySEBAL, EFSOIL, FAO-56 Ks — qaysilari sinaladi?
11. Tuzatish usuli: bitta K koeffitsientimi yoki ansambl (EnKF)?
12. Hodisa detektori: faqat Sentinel-1'mi yoki Sentinel-1 + SWIR?
13. Hodisa topilganda sug'orish miqdori qancha deb olinadi: FC gacha to'ldiriladimi yoki sug'orish usuliga xos me'yor olinadimi?
14. Ekin ma'lumoti bo'lmagan dalada Z qanday olinadi?

**Grid va kunlik birlashtirish (V4 uchun; 2026-09-26 qo'shildi):**

15. Asos grid: HLS/MGRS (UTM, 30 m, 109.8 km tile), Landsat grid'i yoki bitta milliy grid?
16. SEBAL kalibratsiya (anchor) hududi qanday bo'ladi? Uch variant:
    - har MGRS tile alohida;
    - qat'iy kalibratsiya zonalari (bir nechta tile bloki yoki iqlim/relyef zonalari);
    - tile bo'yicha kalibratsiya + qo'shni tile'lar bilan silliqlash.

    Talablar va dalillar:
    - Hudud foydalanuvchi ROI'siga bog'liq bo'lmasligi kerak, aks holda bir dala ikki xil ET oladi.
    - Hudud ichida ob-havo bir xil bo'lishi kerak.
    - Long va boshq. 2011 (JGR): SEBAL anchor tanlashga va hudud o'lchamiga juda sezgir.
    - Chok kattaligini MGRS tile'larning ustma-ust tasmasida (9.8 km) o'lchash mumkin.
    - Kuzatuv tile'ning kamida qancha qismini qoplashi kerak — shu savolning bir qismi.
17. Bir kunda bir nechta termal kuzatuv bo'lsa: ustuvorlik (Landsat > ECOSTRESS > VIIRS), oddiy o'rtacha (Liu 2026) yoki xatoga qarab og'irlikli o'rtacha? Birlashtirish kunlik ET darajasida bo'ladi, LST darajasida emas.
18. Landsat kunlarida optik kirish: C2 L2 SR (hozirgi, Bushland'da tekshirilgan) yoki HLS L30 (hamma kun bir xil seriya)? HLS allaqachon BRDF bo'yicha normallashtirilgan, `olmedo_brdf` albedo ham BRDF tuzatadi — ikki marta tuzatish bo'lmasligi kerak.
19. Birlashtirilgan kirish ma'lumotini GEE'da asset sifatida saqlaymizmi yoki har safar kod bilan hisoblaymizmi?
20. Suomi NPP'dan keyin VIIRS uchun manba: NOAA-20/21 LST'ni (VJ121A1D, VJ221A1D) GEE'ga o'zimiz yuklaymizmi yoki boshqa yo'l tanlaymizmi? Bu savol `viirs_downscaling.py` (VNP09GA) ga ham tegishli.
21. Inventarizatsiya uchun pilot MGRS tile qaysi bo'ladi va qaysi yillar olinadi?

## 10. Keyinga qoldirilganlar (esdan chiqmasin)

- **Ekin xaritasi kelgach** — ekin bosqichlari bo'yicha ildiz chuqurligi Z(t) qo'yiladi. Ogohlantirish: yil bo'yi Zmax olinsa, yomg'irli mavsumda zaxira oshib ketadi va ETPR yuqori baholanishi mumkin. Buni Z(t) sezgirlik testi ko'rsatadi.
- **Quduq ma'lumotlari kelgach** — ETGW ikki yo'l bilan topiladi:
  - quduqdagi sizot chuqurligi + kapillyar ko'tarilish formulasi (Liu va boshq. 2006);
  - SEBAL bilan sug'orilmaydigan joy va paytni aniqlash.
- **q:** oddiy chelak va van Genuchten natijalari keskin farq qilsa — Ksat va tuproq parametrlarining sezgirligi tekshiriladi.
- **Yaqinlashish chegaralari** (masalan, 1 mm va 0.01) — qat'iy belgilanmaydi, sezgirlik testi bilan tanlanadi.

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
