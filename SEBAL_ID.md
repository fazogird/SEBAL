# SEBAL_ID — bosqichma-bosqich to'liq tavsif

**Manba:** Tasumi (2003), *Progress in operational estimation of regional
evapotranspiration using satellite imagery*, University of Idaho.
SEBAL_B (Bastiaanssen 1998) ustiga qurilgan, **mode='SEBAL_ID'** bilan yoqiladi.
SEBAL_B kodi **hech qayerda o'zgarmagan** — barcha farq `if mode=='SEBAL_ID'` shoxida.

> **SEBAL_B → SEBAL_ID farqlari (6 ta):**
> 1. L↓ — Eq 4.13 (boshqa koeffitsientlar)
> 2. Emissivity — Eq 4.28 (LAI-asosli)
> 3. Cold piksel — dT≠0 (ET_cp = 1.05·ETr)
> 4. Hot piksel — FAO-56 suv balansi (λE≠0 bo'lishi mumkin)
> 5. Instant→kunlik/oylik — **ETrF** (EF emas)
> 6. anchor_mode — **point_anchor** majburiy
> 7. *(ixtiyoriy)* Appendix I — kunlik ETrF tuzatish (`etrf_water_balance=True`)

---

## 0-BOSQICH — Kirish ma'lumotlari

### 0.1 Landsat (asosiy raster)
| Element | Qiymat |
|---|---|
| Kolleksiya | `LANDSAT/LC08/C02/T1_L2`, `LANDSAT/LC09/C02/T1_L2` |
| Bandlar | SR_B2..B7 (ko'k→SWIR2), ST_B10 (termal), QA_PIXEL, QA_RADSAT |
| SR masshtab | `SR = DN × 0.0000275 − 0.2` → 0–1 reflektans |
| LST masshtab | `LST = DN × 0.00341802 + 149.0` → Kelvin |

**Bulut maskasi** — QA_PIXEL bitlari: fill(0), dilated_cloud(1), cirrus(2),
cloud(3), cloud_shadow(4), snow(5), water(7).

**Bulut prechecki:** ROI (yoki `cloud_roi`) ustida bulut % hisoblanadi;
`CROP_CLOUD_MAX = 30%` dan katta bo'lsa sahna **tashlab yuboriladi**.

### 0.2 ERA5-Land (meteorologiya, **overpass vaqtiga interpolyatsiya**)
`ECMWF/ERA5_LAND/HOURLY` →
| Band | Manba | Birlik | Vaqt konvensiyasi |
|---|---|---|---|
| `WIND_SPEED_10M` | √(u10² + v10²) | m/s | **INSTANT** — yorliq vaqtida |
| `AIR_TEMP` | temperature_2m | K | **INSTANT** |
| `DEWPOINT` | dewpoint_temperature_2m | K | **INSTANT** |
| `PRESSURE` | surface_pressure | Pa | **INSTANT** |
| `SSRD` | surface_solar_radiation_downwards_**hourly** | J/m² | **AKKUM** — `[T−1h, T]` |
| `STRD` | surface_thermal_radiation_downwards_hourly | J/m² | **AKKUM** — `[T−1h, T]` |

⭐ **SEBAL Manual App.5-B:** ob-havo overpass vaqtiga **chiziqli interpolyatsiya**
qilinadi (±1 soatlik o'rtacha EMAS). Ikki guruh **alohida og'irlik** oladi:
```
t_op = overpass, yarim tundan kasrli soat (UTC)
INSTANT:  yorliqlar floor(t_op), +1;   w = t_op − floor(t_op)
AKKUM:    markazlar T−0.5 → yorliq a = floor(t_op−0.5)+1;  w = t_op − (a−0.5)
qiymat = V(a)·(1−w) + V(a+1)·w
```
**ERA5 konvensiyasi empirik tasdiqlangan** (quyosh chiqishi testi 2022-07-14:
quyosh 11:57 UTC da chiqadi, `SSRD@11:00 = 0`, `SSRD@12:00` kichik nolmas →
yorliq **davr OXIRI**, `Flag_period = 0`).

Misol (overpass 17:06 UTC): eski ±1h o'rtacha `SSRD=866.4, T2m=31.59, u=5.50`
→ yangi interp `SSRD=876.2, T2m=31.04, u=5.33` (manual hisobi bilan aynan mos).

### 0.3 DEM va yer qoplami
- `USGS/SRTMGL1_003` → `DEM` (m), undan `SLOPE` (daraja)
- `ESA/WorldCover/v200` → anchor zonalari (pastda)

---

## 1-BOSQICH — Yer yuzasi parametrlari (`surface_props.compute_all`)

⚠️ **SEBAL_ID da tartib o'zgargan:** NDVI → SAVI → ALBEDO → **LAI** → **EMISSIVITY** → Z0M → TAU_SW
(LAI emissivity'dan **oldin**, chunki Eq 4.28 LAI'ga bog'liq).

### 1.1 NDVI
```
NDVI = (B5 − B4) / (B5 + B4)
```

### 1.2 SAVI (umumiy, L=0.5 — Huete 1988)
```
SAVI = (B5 − B4)/(B5 + B4 + 0.5) × 1.5
```

### 1.3 ALBEDO — Olmedo (2016)
```
α = 0.246·B2 + 0.146·B3 + 0.191·B4 + 0.304·B5 + 0.105·B6 + 0.008·B7
```
**clamp: [0.0, 0.80]**  · offset yo'q (Liang'dan farqli)

### 1.4 LAI — SEBAL_ID (SAVI L=**0.1**, umumiy SAVI EMAS)
```
SAVI₀.₁ = (B5 − B4)/(B5 + B4 + 0.1) × 1.1
LAI     = −ln((0.69 − SAVI₀.₁)/0.59) / 0.91
```
| Shart | LAI |
|---|---|
| SAVI < 0.1 | 0 |
| 0.1 ≤ SAVI < 0.687 | formula |
| SAVI ≥ 0.687 | 6.0 |

**clamp: [0, 6]**

### 1.5 EMISSIVITY — ⭐ Eq 4.28 (SEBAL_ID)
```
NDVI > 0  va  LAI < 3  →  ε₀ = 0.95 + 0.01 × LAI
LAI ≥ 3               →  ε₀ = 0.98
NDVI ≤ 0 (suv/qor)    →  ε₀ = 0.985
```
*(SEBAL_B: ε₀ = 1.009 + 0.047·ln(NDVI), NDVI 0.16–0.74; suv 0.985, tuproq 0.960)*

### 1.6 Sirt g'adir-budurligi
```
z₀m      = 0.018 × LAI                      MIN 0.005 (MAX YO'Q)   ← u* uchun
z₀h      = z₀m / exp(2.3)                   (kB⁻¹ = 2.3)
h        = 2.0 × (NDVI − 0.20)/(0.85 − 0.20)   [ekin balandligi, m]
z₀m,wind = 0.123 × h                        [Brutsaert 1982]  ← shamol 10→200m uchun
```

### 1.7 Atmosfera o'tkazuvchanligi — Allen (2007)
```
τsw = 0.75 + 2×10⁻⁵ × DEM
```
> **z₀m MAX chegara olib tashlandi:** LAI ≤ 6 → z₀m ≤ **0.108 m** (ekin uchun fizik:
> z₀m ≈ 0.1·h). Eski `z0m_max = 1.0` hech qachon faollashmasdi — u eski Gediz
> SAVI-eksponensial formulasidan qolgan o'lik qoldiq edi. **MIN 0.005 qoladi**
> (`ln(200/z₀m)` domenini himoya qiladi).

---

## 2-BOSQICH — Radiatsiya (`radiation.compute_all`)

### 2.1 Tushuvchi qisqa to'lqin K↓
```
K↓ = Gsc × cos(θ) × dr × τsw
Gsc = 1367 W/m²
cos(θ) = sin(SUN_ELEVATION)        [Landsat metadata]
dr = 1 + 0.033·cos(2π·DOY/365)
```

### 2.2 Tushuvchi uzun to'lqin L↓ — ⭐ Eq 4.13 (SEBAL_ID)
```
L↓ = 0.85 × σ × [−ln(τsw)]^0.09 × Tref⁴
σ = 5.67×10⁻⁸ W/m²/K⁴
```
- **Tref** = cold zona (cropland) LST ning **p10** persentili
  (bo'sh/bulutli bo'lsa → ERA5 `AIR_TEMP` medianasi, fallback log'da chiqadi)
- Koeffitsientlar: Allen et al. (2000) "RAPID", Kimberly Idaho
- **`.max(0)`**
- *(SEBAL_B: `1.08 · σ · [−ln τsw]^0.265 · Tref⁴` — Eq 3.13, Bastiaanssen 1995)*

### 2.3 Ko'tariluvchi uzun to'lqin L↑
```
L↑ = ε₀ × σ × LST⁴
```

### 2.4 Sof radiatsiya Rn
```
Rn = (1 − α)·K↓  +  [ L↓ − L↑ − (1 − ε₀)·L↓ ]
```
**Clamp YO'Q** — faqat QA bayrog'i: `RN_QA_FLAG = (Rn < 100) or (Rn > 700)`
(qiymat o'zgartirilmaydi, statistika uchun belgilanadi)

### 2.5 Tuproq issiqlik oqimi G₀ — Bastiaanssen (2000) Eq 24
```
G/Rn = Ts[°C] × (0.0038 + 0.0074·α) × (1 − 0.98·NDVI⁴)
```
- Suv (NDVI < 0) → **G/Rn = 0.5**
- Qor maskasi **olib tashlangan** (albedo+LST ishonchsiz edi)
- **clamp: G/Rn ∈ [0, 0.6]**  (manual Table 2: kuzatilgan oraliq 0.04–0.6)
```
G₀ = Rn × (G/Rn)
```

### 2.6 Mavjud energiya
```
RN_G0 = Rn − G₀
```

---

## 3-BOSQICH — Shamol va aerodinamik qarshilik

```
u₂₀₀ = u₁₀ × ln(200/z₀m,wind) / ln(10/z₀m,wind)          [neytral log profil]
u*   = k × u₂₀₀ / ln(200/z₀m)          k = 0.41           max(0.02)
rah  = ln(z₂/z₁) / (k·u*) = ln(2.0/0.1)/(k·u*) = ln(20)/(k·u*)   max(1.0)
```
✅ **z2_rah = z2 = 2.0 m** (kanonik SEBAL/METRIC; z1 = 0.1 m).
(2026-07-24: z2_rah 0.2→2.0. Audit — Ne1 2022: 2.0 da rah 11–18 s/m, dT 1.4–5.1 K
= FIZIK; 0.2 esa rah'ni 1.0 clampga tushirardi. Bog'liq: `rah-z2-advection-finding`.
⚠️ Yakka o'zi 2.0 o'sish mavsumida ET ni kam baholaydi — advektsiya manbada kerak.)

---

## 4-BOSQICH — Instant referens ET (⭐ SEBAL_ID)

`ref_et.compute_instant_etr` — **ASCE-EWRI soatlik Penman-Monteith (alfalfa)**,
FAO-56. Bu K↓ dan EMAS, haqiqiy quyosh radiatsiyasidan (SSRD).

```
T   = AIR_TEMP − 273.15                       [°C]
P   = PRESSURE / 1000                          [kPa]
u₂  = WIND_SPEED_10M × 4.87/ln(67.8·10 − 5.42) ≈ ×0.748   [m/s]
ea  = 0.6108·exp(17.27·Td/(Td+237.3))          [kPa]   Td = DEWPOINT−273.15
es  = 0.6108·exp(17.27·T/(T+237.3))            [kPa]
Δ   = 4098·es/(T+237.3)²                       [kPa/°C]
γ   = 0.000665·P                               [kPa/°C]
Rs  = SSRD / 10⁶                               [MJ/m²/soat]
```
**Soatlik radiatsiya:**
```
Ra  = (12·60/π)·Gsc·dr·[(ω₂−ω₁)sinφ sinδ + cosφ cosδ (sinω₂ − sinω₁)]   max(0)
      Gsc = 0.0820 MJ/m²/min;  ω — quyosh burchagi (FAO-56 Eq 31, Sc Eq 32)
      ω₁,ω₂ = ω ∓ π/24  (quyosh botish burchagi ws bilan kesiladi)
Rso = (0.75 + 2×10⁻⁵·z)·Ra
Rns = (1 − 0.23)·Rs                            [albedo 0.23 — FIKSATIV referens]
fcd = 1.35·clamp(Rs/Rso, 0.3, 1.0) − 0.35      (kecha Rs<0.01 → fcd = 1.0)
Rnl = 2.042×10⁻¹⁰ · T_K⁴ · (0.34 − 0.14√ea) · fcd
Rn  = Rns − Rnl
G   = 0.04·Rn   (kunduzi, alfalfa;  kecha 0.20·Rn)
```
**PM tenglamasi (alfalfa, kunduz):**
```
              0.408·Δ·(Rn−G) + γ·(66/(T+273))·u₂·(es−ea)
ETR_INST = ────────────────────────────────────────────      [mm/soat]   max(0)
                      Δ + γ·(1 + 0.25·u₂)
Cn = 66, Cd = 0.25   (alfalfa soatlik kunduz)
```
> `ref_type='grass'` bo'lsa: Cn = 37, Cd = 0.24, G = 0.1·Rn.

---

## 5-BOSQICH — Anchor tanlash (⭐ point_anchor MAJBURIY)

### 5.1 Land-cover zonalari (ESA WorldCover v200)
| Anchor | Klass |
|---|---|
| cold | **40** (Cropland) — sug'orilgan, nam |
| hot | **60** (Bare/sparse) + **20** (Shrubland) — doim quruq |

*(30 Grassland ataylab yo'q — sug'orilgan yaylovni hot deb olish xavfi)*

### 5.2 Umumiy filtr
```
slope < 5°   VA   barcha bandlar valid
```

### 5.3 Kaskad — metod KANDIDAT to'plamini topadi (bitta piksel EMAS)
`cimec → plan_a → plan_b → pysebal → default` — avval land-cover zonasida, keyin
butun ROI'da; hech biri chiqmasa `default` persentil. Har metod **kandidat band-
oralig'ini** (mask) qaytaradi, persentil bilan CHEKLANGAN:

| Metod | Cold kandidat | Hot kandidat |
|---|---|---|
| **cimec** (1-chi) | NDVI≥p80 guruh, LST **p5–p40** | NDVI≤p10 (NDVI>0.02, alb>0.12), LST **p60–p95** |
| plan_a | LAI≥3, alb 0.20–0.25, LST 284–295K | LAI<0.4, NDVI 0.05–0.3, LST 302–311K |
| plan_b | NDVI≥p95, LST p5–p15/p20 | NDVI≤p10, LST p80/p85–**p95** |
| pysebal | NDVI yuqori, LST < o'rtacha−std | NDVI past, LST > o'rtacha+std *(yuqori chegara YO'Q)* |
| default | Cropland: NDVI≥p95, LST≤p20 | Bare+shrub: NDVI≤p10, LST≥p95 |

🔑 cimec/plan_b hot kandidati **p95 bilan cheklangan** → eng issiq **top 5% ATAYLAB
chiqarilgan** (kitob: "avoid extreme temperatures"). **Qabul:** `(LST_hot−LST_cold) ≥ 1.0 K`.

### 5.4 point_anchor — kandidatlardan bitta piksel (band ICHIDA ekstremal)
SEBAL_ID `process_tile` da **avtomatik** `point_anchor` (cold/hot dT va hot suv
balansi **ayni bir pikselga** tayanishi uchun):
```
cold = kandidat ICHIDAgi eng SOVUQ → Reducer.min(2): 'min'=LST, 'min1'=RN_G0
hot  = kandidat ICHIDAgi eng ISSIQ → Reducer.max(2): 'max'=LST, 'max1'=RN_G0
       (avval RN_G0-valid piksellarga cheklanadi → null bo'lmaydi)
```

### 5.5 ⚠️ point_anchor mutlaq sahna-ekstremalini OLMAYDI (empirik, 2026-07-24)
Nomiga qaramay, `point` **butun sahnaning** eng issiq/sovuq pikselini EMAS, balki
**cimec kandidat kamari ichidagi** chekkani oladi — metod ekstremallarni oldindan
chiqargan. Ne1 2022-07-14 o'lchovi:

| | point oladi | sahna mutlaq | farq |
|---|---|---|---|
| **hot** | 315.0 K (kandidat max, ≈p95) | 320.7 K (ROI max) | **−5.7 K** (top ~5–8% chiqarilgan) |
| **cold** | 300.6 K (to'liq-qoplama ekin eng sovug'i) | 279.7 K (zona min) | **+20.9 K** (bulut/suv/soya chekkasi chiqarilgan) |

→ Anchor tanlash ekstremalni OLMAYDI; yelka-mavsumi oshirib yuborish **anchordan emas**
(ETrF/siyrak qoplama). **Istisno:** kaskad `pysebal`ga tushsa (hot yuqori chegara ochiq)
→ haqiqiy max olinishi mumkin; lekin cimec deyarli doim ishlaydi.

---

## 6-BOSQICH — Cold va hot piksel λET (⭐ SEBAL_ID yuragi)

```
λ = 2.45×10⁶ J/kg
ETr_cold = median(ETR_INST) cold mask ustida        [mm/soat]
ETr_hot  = median(ETR_INST) hot mask ustida         [mm/soat]
```

### 6.1 Cold piksel — ET_cp = 1.05·ETr
```
λET_cold = 1.05 × ETr_cold × λ / 3600               [W/m²]
H_cold   = RN_G0_cold − λET_cold
```
> **1.05 nima uchun?** Eng sovuq pikselda ET referens alfalfadan 5% ko'p bo'lishi
> mumkin: (a) yangi sug'orilgan nam barg/tuproq, (b) boshqa ekin (masalan makka —
> aerodinamik qarshiligi kichikroq), (c) fiziologik/anatomik farqlar.

### 6.2 Hot piksel — FAO-56 suv balansi (Eq 5.1–5.5)
```
λET_hot = ETrF_hot × ETr_hot × λ / 3600
H_hot   = RN_G0_hot − λET_hot
```
**ETrF_hot qanday topiladi** (`water_balance.hot_pixel_etrf`):

1. **Bitta nuqta:** hot kandidatlar (`hot_mask`) ichidan **eng issiq** piksel va
   uning **lon/lat** koordinatasi (`Reducer.max(3)`: LST, lon, lat).
   ⚠️ Yog'in **lokal** — butun ROI o'rtachasi EMAS.
2. **Tuproq** (shu nuqtada): θ_FC, θ_WP — **Saxton & Rawls (2006)** pedotransfer,
   OpenLandMap **sand/clay** (%) dan UZLUKSIZ (2026-07-24; oldin tekstura-klass→Table5.1):
   ```
   WP = t15 + (0.14·t15 − 0.02),   t15 = f(S, C, OM)     [clamp 0.02–0.35]
   FC = t33 + (1.283·t33² − 0.374·t33 − 0.015),  t33 = f(S, C, OM)  [clamp 0.10–0.50]
   TEW = 1000 × (θ_FC − 0.5·θ_WP) × Ze        Ze = 0.10 m
   TEW = max(TEW, REW + 1)                     [TEW > REW kafolati]
   ```
   REW — tekstura-klassdan (FAO-56 **Table 19**); sand/clay yo'q bo'lsa → tekstura
   Table 5.1 fallback. **NEGA:** HWSD2 (global) da θFC/θWP alohida YO'Q (faqat AWC +
   tekstura); Saxton haqiqiy tarkibdan uzluksiz θ beradi, global (AQSh + O'zbekiston).
   Misol (Ne1): tekstura #8 "silt loam" FC0.29 → Saxton S15/C27 = silty clay loam FC0.35.
3. **30 kunlik kunlik balans** (shu nuqtada, `getRegion` bilan bitta so'rovda):
   - P: **CHIRPS DAILY** (`UCSB-CHG/CHIRPS/DAILY`)
   - ETr: kunlik alfalfa PM
   ```
   De boshlang'ich = TEW  (quruq)
   har kun:
       Kr = 1                          agar De ≤ REW          [Stage 1]
       Kr = (TEW−De)/(TEW−REW)         agar De > REW          [Stage 2]  clamp[0,1]
       E  = Kr × 1.05 × ETr
       De = clamp(De − P + E, 0, TEW)                          [RO = 0]
   ```
4. **Natija:** `ETrF_hot = Kr × 1.05`
   → yaqinda yomg'ir yo'q bo'lsa De=TEW → Kr=0 → **ETrF_hot=0** (klassik quruq hot)

---

## 7-BOSQICH — Sezuvchan issiqlik H (ikki uchli iteratsiya)

### 7.1 Skalyar iteratsiya (sof Python, server chaqiruvi yo'q)
`max_iter=15`, `min_iter=2`, **nisbiy tolerantlik 1%** (dT_hot va rah_hot uchun)

```
har iteratsiyada:
   dT_cold = H_cold × rah_cold / (ρ_cold × cp)         cp = 1004 J/kg/K
   dT_hot  = H_hot  × rah_hot  / (ρ_hot  × cp)
   ────────── chiziqli kalibratsiya (Fig 5.2) ──────────
   c4 = (dT_hot − dT_cold) / (Ts_hot − Ts_cold)
   c5 = dT_cold − c4 × Ts_cold
   ────────── Monin-Obukhov (cold VA hot alohida) ──────
   L   = − ρ·cp·u*³·Ts / (k·g·H)        g = 9.81      clamp ±10⁶
   ψ   = Paulson (1970):
         L<0:  x = (1 − 16z/L)^0.25
               ψm = 2ln((1+x)/2) + ln((1+x²)/2) − 2arctan(x) + π/2
               ψh = 2ln((1+x²)/2)
         L>0:  ψm = ψh = −5z/L
         **clamp ψ: ±5**
   Dhungel (2016) damping: oxirgi ikki ψ va u* o'rtachasi
   u*  = k·u₂₀₀/(ln(200/z₀m) − ψm)       max(0.02)
   rah = (ln(2.0/0.1) − ψh)/(k·u*)       max(1.0)
```
⚠️ **SEBAL_B da faqat hot iteratsiya qilinadi** (dT_cold ≡ 0, c5 = −c4·Ts_cold).
**SEBAL_ID da ikkalasi ham** iteratsiya qilinadi.

### 7.2 Raster bosqich (server-side, aynan N_A qadam)
```
dT = c4 × LST + c5
   XAVFSIZLIK 1: clamp [min(dT_cold,dT_hot), max(dT_cold,dT_hot)] ± 20% margin
   XAVFSIZLIK 2: Ta = LST − dT,  Ta ∈ [ERA5_AIR_TEMP − 15K, +15K],  dT = LST − Ta
H  = ρ · cp · dT / rah
   XAVFSIZLIK 3: clamp [−100, RN_G0]        (λE ≥ 0 kafolati)
```

---

## 8-BOSQICH — λE va instant ET

```
λE        = Rn − G₀ − H                            max(0)
EVAP_FRAC = λE / (Rn − G₀)     faqat Rn−G₀ > 0 da   clamp [0, 1]
                                (aks holda MASKALANADI — soxta qiymat yo'q)
λ_hv      = (2.501 − 0.00236·(LST − 273)) × 10⁶    [J/kg]  Tasumi Eq 3.48
ET_inst   = λE × 3600 / λ_hv                       [mm/soat]
```

---

## 9-BOSQICH — Instant → Kunlik (⭐ Eq 5.6–5.8)

```
ETrF_inst = ET_inst / ETR_INST          clamp [0, 1.05]
```
> **Nega 1.05?** Cold piksel `1.05·ETr` ga bog'langan → ETrF ning fizik maksimumi 1.05.

```
ETr24 = Σ(24 SOATLIK ASCE PM alfalfa)  — SOATLIK-YIG'INDI (kitob App.B)
        har soat: Cn = 66 ; Cd = 0.25 (kunduz) / 1.7 (tun) ; G = 0.04/0.20·Rn
        MAHALLIY STANDART kalendar kun (`utc_offset`, App.5-A; DST YO'Q)
        ⚠️ overpass VAQTI emas; ⚠️ UTC kun ham emas — MAHALLIY kun
────────────────────────────────────────
ET_24 = ETrF_inst × ETr24               [mm/kun]   max(0)
```
> **2026-07-24: kunlik-qadam (Cn=1600/Cd=0.38) → SOATLIK-YIG'INDI ga o'tildi.**
> Kitob (Tasumi App.B) aynan *"summing the hourly values"* deydi. Validatsiya
> (Ne1 2022 oylik, SEBAL_ID): R² **0.801→0.830**, MBE +18.6→**+15.2**, RMSE 31.8→**28.2**.
> Kod: `ref_et.compute_etr24_hourly_sum` (`get_daily_etr24` va `compute_etref_daily`
> shuni chaqiradi). Narxi: kun × 24 soat ERA5 (sekinroq, lekin aniqroq).
> **Mahalliy kun nima uchun muhim** (SEBAL Manual App.5-A): ASCE kunlik ETr
> mahalliy yarim tundan yarim tungacha aniqlangan. UTC kuni Nebraska (−6) uchun
> = mahalliy 18:00→18:00 → `T_max/T_min` oynasi siljiydi → **ETr ~7% xato**.
> `Rs` esa oynadan qariyb mustaqil (28.74 vs 28.81 MJ = 0.2%).
> ```
> mahalliy 00:00 = UTC (00:00 − utc_offset)
> utc_offset = round(zona markazi boylami / 15)   ← App.5-A
> ```
> Avtomatik `round(lon/15)`: Nebraska −96.5° → **−6** ✓ (Central = −90/15 = −6).
> ⚠️ **O'zbekiston: avtomatik +4 beradi, ASLIDA UZT = +5** → qo'lda `utc_offset=5`.
> **DST hech qachon qo'llanmaydi** ("winter standard time" — manual talabi).
*(SEBAL_B: `ET_24 = EF × Rn24 × 86400/λ_hv`, `Rn24 = (1−α)·Rs24 − 110·τsw`)*

**Gipoteza:** ETrF kunduzi barqaror (EF emas) — advektiv muhitda (Idaho, Nebraska)
ETr umumiy bug'lanish energiyasining Rn−G dan yaxshiroq indeksi.

---

## 10-BOSQICH — Kunlik → Oylik (⭐ Eq 5.9–5.10)

### 10.1 Standart (`etrf_water_balance=False`, default)
```
oyning har kuni d uchun:
    ETrF(d)  = ENG YAQIN sahnaning ETRF_INST i        ← Eq 5.9
    ETr24(d) = shu kunning kunlik referens ET si
    ET_day(d) = ETrF(d) × ETr24(d)                     max(0)
ET_MONTHLY = Σ ET_day
```
> **Eq 5.9:** *"every image represents a period of about 16 days, with 8 days
> before and 8 days after"* → masalan 8 va 24 mart sahnalari bo'lsa:
> **1–16 mart → 8-mart ETrF; 16–31 mart → 24-mart ETrF.** O'rtachalash YO'Q.
> Bulutli piksel → kolleksiya o'rtachasi bilan `unmask`.

*(SEBAL_B: `_interpolate_lambda` — ikki sahna **o'rtachasi** (midpoint), EF bo'yicha)*

### 10.2 Appendix I (`etrf_water_balance=True`, ixtiyoriy)
Kunlik ETrF ni yog'in namligiga qarab tuzatadi.

**Har sahna uchun ajratish (I.9–I.11):**
```
ETrF_basal(LAI) = LAI–ETrF PASTKI O'RAM
                  (LAI 0.5 qadamli binlar, har binda p5 persentil,
                   monoton o'suvchi, clamp [0.15, 1.05])
h    = 2.0 × clamp((NDVI−0.15)/0.70, 0, 1)          max 0.05     [m]
fc   = ((basal − 0.15)/(ETrF_max − 0.15))^(1/(1+0.5h))   clamp [0,1]   (Eq I.12)
few  = 1 − fc                                        clamp [0.01, 1]  (Eq I.3)
ETrF_max = max(basal, 1.05)                                           (Eq I.4)
Ke    = min(ETrF − basal, few × ETrF_max)            max 0            (Eq I.2/I.9)
basal = ETrF − Ke                                    clamp [0.15,1.05]
Kr    = Ke / (ETrF_max − basal)                      clamp [0,1]      (Eq I.10)
De₀   = TEW − Kr×(TEW − REW);  agar Kr≈1 → De₀ = 0.5×REW              (Eq I.11)
        clamp [0, TEW]
```
**Kunlik forward sweep (per-piksel):**
```
TEW — Saxton-Rawls θFC/θWP (OpenLandMap sand/clay); REW — tekstura (Table 19), Ze = 0.10
har kun:
    (sahna kuni bo'lsa → De = o'sha sahnaning De₀, partition yangilanadi)
    Kr = 1 agar De ≤ REW,  aks holda (TEW−De)/(TEW−REW)    clamp[0,1]
    Ke = min(Kr×(ETrF_max − basal), few×ETrF_max)          max 0
    ETrF_adj = basal + Ke                                             (Eq I.1)
    ET_day   = ETrF_adj × ETr24(d)                          max(0)
    De = clamp(De + Ke×ETr24/few − P,  0,  TEW)                       (Eq I.7)
         P = CHIRPS shu kun;  RO = 0;  sug'orish YO'Q
ET_MONTHLY = Σ ET_day
```
> **Qachon foydali:** yalang'och/siyrak yuzalar (cho'l, bo'sh dala) — yog'in ETrF ni
> keskin oshiradi. **Zich qoplamada ta'siri ~nol** (few kichik → Ke kichik).

---

## Barcha konstantalar (yig'ma)

| Konstanta | Qiymat | Qayerda |
|---|---|---|
| σ (Stefan-Boltzmann) | 5.67×10⁻⁸ W/m²/K⁴ | L↓, L↑ |
| k (Von Karman) | 0.41 | u*, rah |
| g | 9.81 m/s² | Monin-Obukhov L |
| cp (havo) | 1004 J/kg/K | dT, H |
| λ (yashirin issiqlik) | 2.45×10⁶ J/kg | λET_cold/hot |
| λ_hv (haroratga bog'liq) | (2.501−0.00236·Ts)×10⁶ | ET_inst, ET_24 |
| Gsc | 1367 W/m² (K↓) · 0.0820 MJ/m²/min (Ra) | radiatsiya |
| **L↓ koeff. (Eq 4.13)** | **0.85, 0.09** | SEBAL_ID L↓ |
| **Emissivity (Eq 4.28)** | **0.95, 0.01, LAI=3, 0.98, 0.985** | SEBAL_ID ε₀ |
| **Cold piksel** | **1.05 × ETr** | SEBAL_ID anchor |
| **ETrF_max** | **1.05** | clamp, Appendix I |
| Albedo (Olmedo) | 0.246/0.146/0.191/0.304/0.105/0.008 | α |
| G₀ | 0.0038, 0.0074, 0.98, suv 0.5 | G/Rn |
| z₀m | 0.018×LAI | u* |
| z₀m,wind | 0.123×h, h_max=2.0 | shamol |
| τsw | 0.75 + 2×10⁻⁵·z | atmosfera |
| kB⁻¹ | 2.3 | z₀h |
| z1 / z2_rah / z2 | 0.1 / 2.0 / 2.0 m | rah / stability (kanonik) |
| z_blending | 200 m | u₂₀₀ |
| ASCE alfalfa (soatlik) | Cn=66, Cd=0.25, G=0.04Rn | ETR_INST |
| ASCE alfalfa (soatlik→ETr24) | Cn=66, Cd=0.25/1.7, G=0.04/0.2·Rn, Σ24soat | ETr24 |
| ASCE albedo | 0.23 (fiksativ) | referens Rn |
| Ze (bug'lanuvchi qatlam) | 0.10 m | TEW |
| Suv balansi oynasi | 30 kun | De |

## Barcha clamp/cheklovlar (yig'ma)

| Parametr | Clamp | Sabab |
|---|---|---|
| ALBEDO | [0, 0.80] | fizik |
| LAI | [0, 6] | fizik maksimum |
| z₀m | **MIN 0.005 (max YO'Q)** | log domeni; LAI≤6 → z₀m≤0.108 |
| G/Rn | [0, 0.6] | manual Table 2 |
| Rn | **clamp yo'q** (QA flag) | qiymat buzilmasin |
| L↓ | max(0) | fizik |
| u* | max(0.02) | raqamiy barqarorlik |
| rah | max(1.0) | fizik minimum |
| ψ (stability) | ±5 | ekstremal L dan himoya |
| L (Monin-Obukhov) | ±10⁶ | raqamiy |
| dT (raster) | [dT_cold, dT_hot] ± 20% | ekstrapolyatsiya portlamasin |
| Ta | ERA5 AIR_TEMP ± 15 K | QA |
| H | [−100, RN_G0] | λE ≥ 0 kafolati |
| λE | max(0) | fizik |
| EVAP_FRAC | [0,1], Rn−G₀≤0 → **mask** | soxta qiymat yo'q |
| **ETrF_inst** | **[0, 1.05]** | cold anchor 1.05·ETr |
| ETrF_basal | [0.15, 1.05] | Appendix I |
| few | [0.01, 1] | Appendix I |
| Kr | [0, 1] | FAO-56 |
| De | [0, TEW] | FAO-56 |
| ET_24 / ET_day | max(0) | fizik |

---

## Ishlatish

```python
main.run_polygons(
    polygon_asset=...,
    mode='SEBAL_ID',
    etrf_water_balance=False,   # True → Appendix I (kunlik ETrF tuzatish)
    ref_type='alfalfa',         # 'grass' — sinov uchun
    utc_offset=None,            # None → avtomatik round(lon/15); O'zb uchun 5 bering
    etr24_source='era5',        # 'gridmet' — AQSh uchun (ETr aniqroq)
    sloping_terrain=False,      # True → tog'/qiya yuza tuzatishlari
    anchor_method='cascade',    # anchor_mode point_anchor'ga AVTOMATIK o'tadi
)
```

---

## Qiya yuzalar (`sloping_terrain=True`)

**Barcha rejimlarda** ishlaydi — to'liq tavsif: [README.md § 33](README.md).
SEBAL_ID ga xos qismi — **Eq 5.17–5.19** (`C_rad`):
```
C_rad  = [sinφ_quyosh/cosθ_pixel] × [Ra24_pixel/Ra24_flat]     clamp [0.5, 2.0]
ETrF24 = C_rad · ETrF_inst
ET24   = ETrF24 · ETr24
```
Instant holat sutkani ifodalamaydi (ertalab JSh qiyalik ko'p oladi, kechqurun kam)
→ "ETrF kunduzi barqaror" farazi qiyalikda buziladi. `C_rad` buni tuzatadi.
`(K_B+K_D)` nisbatlarda qisqargani uchun **sof geometriya** — `K_t`/`W`/`P` kerak emas.

*(SEBAL_B da esa ekvivalenti `Rs24 × Ra24_ratio` → `Rn24` orqali.)*

**Yangi fayllar:** `water_balance.py` (hot piksel), `etrf_water_balance.py` (Appendix I).
**O'zgargan:** `config.py`, `radiation.py`, `surface_props.py`, `energy_balance.py`,
`ref_et.py`, `daily_et.py`, `preprocessing.py`, `main.py`.

---

## Validatsiya (US-Ne1, Mead NE — sug'oriladigan makka, 2022, 50.2 ga polygon)

| Model | R² | MBE | MAE | RMSE |
|---|---|---|---|---|
| SEBAL_B | **0.894** | **−18.4** | **27.1** | **29.1** |
| SEBAL_ID (alfalfa) | 0.880 | +31.6 | 33.8 | 39.9 |
| SEBAL_ID (grass)¹ | 0.892 | +22.6 | 24.5 | 29.8 |
| SEBAL_ID + Appendix I¹ | 0.677 | +53.3 | 53.3 | 62.6 |

¹ *vaqt tuzatishidan OLDINGI o'lchov — qayta o'lchanmagan.*

**Ma'lum cheklovlar:**
- **Pik oyda a'lo:** Iyul SEBAL_ID 164 vs EC 156 (+5%).
- **Yelka mavsumida oshirib yuboradi:** May 97 vs 41, Sen 176 vs 106. Sababi — siyrak
  qoplamada va kichik cold–hot ΔT da `ETrF_inst` yuqori chiqadi, ustiga bahorgi
  yuqori `ETr24` ga ko'payadi. **Hal qilinmagan.**
- **Appendix I bu saytda yomonlashtiradi** (yalang'ochda `Ke` potensialga yaqinlashadi);
  u kitobda ham "deserts, bare soils" uchun mo'ljallangan.
- Overpass (instant λE) darajasida SEBAL_ID ≈ SEBAL_B (R² 0.771 vs 0.753) — demak
  muammo **ekstrapolyatsiya bosqichida**, instant energiya balansida emas.

---

## APPENDIX — Formula ro'yxati: raster kirishdan oylik ET gacha (clamplar bilan)

SEBAL_ID zanjirining **48 formulasi** va **~20 clampi**, tartib bo'yicha. Global
konstantalar: σ=5.67e-8, k=0.41, cₚ=1004 J/kg/K, Gsc=1367 W/m², z₀m_min=0.005,
ETrF_max=1.05. (Manba: kod — `surface_props / radiation / energy_balance /
ref_et / water_balance / daily_et`.)

### A. Yer yuzasi parametrlari (`surface_props.py`)
| # | Formula | Clamp |
|---|---|---|
| F1 | NDVI = (B5−B4)/(B5+B4) | — |
| F2 | SAVI = 1.5·(B5−B4)/(B5+B4+0.5) | — |
| F3 | Albedo = 0.246·B2+0.146·B3+0.191·B4+0.304·B5+0.105·B6+0.008·B7 | **[0, 0.80]** |
| F4 | SAVI_L = 1.1·(B5−B4)/(B5+B4+0.1)  *(LAI uchun, L=0.1)* | — |
| F5 | LAI = −ln((0.69−SAVI_L)/0.59)/0.91 | SAVI_L≥0.687→6; <0.1→0; **[0, 6]** |
| F6 | ε₀ (Eq 4.28): NDVI>0 & LAI<3 → 0.95+0.01·LAI ; LAI≥3 → 0.98 ; NDVI≤0 → 0.985 | — |
| F7 | z₀m = 0.018·LAI | **min 0.005** (max YO'Q) |
| F8 | z₀h = z₀m / e^2.3 | — |
| F9 | h = h_max·clamp((NDVI−NDVI_min)/(NDVI_max−NDVI_min),0,1) ; z₀m,wind = 0.123·h | **min 0.001** |
| F10 | τsw = 0.75 + 2e-5·z(DEM) | — |

### B. Radiatsiya (`radiation.py`)
| # | Formula | Clamp |
|---|---|---|
| F11 | cosθ = sin(SUN_ELEVATION) *(yassi); qiya → Duffie-Beckman* | — |
| F12 | dr = 1 + 0.033·cos(2π·DOY/365) | — |
| F13 | K↓ = Gsc·cosθ·dr·τsw | **max 0** |
| F14 | L↓ (Eq 4.13) = 0.85·(−ln τsw)^0.09·σ·T_ref⁴ *(T_ref=cropland LST p10)* | **max 0** |
| F15 | L↑ = ε₀·σ·T₀⁴ | — |
| F16 | Rn = (1−α)·K↓ + L↓ − L↑ − (1−ε₀)·L↓ | QA-flag <100/>700 |
| F17 | G/Rn = Ts°C·(0.0038+0.0074·α)·(1−0.98·NDVI⁴) ; NDVI<0→0.5 | **[0, 0.6]** |
| F18 | G0 = Rn·(G/Rn) | — |

### C. Shamol & momentum (`energy_balance.py`)
| # | Formula | Clamp |
|---|---|---|
| F19 | u₂₀₀ = u₁₀·ln(200/z₀m,w)/ln(10/z₀m,w) | — |
| F20 | u* = k·u₂₀₀/ln(200/z₀m) | **max 0.02** |
| F21 | rah_neytral = ln(z₂/z₁)/(k·u*) = **ln(20)**/(k·u*) | **max 1.0** |
| F22 | ρ_air = P/(R·T) | — |

### D. Anchor kalibratsiyasi — SEBAL_ID ikki-anchor
| # | Formula | Clamp |
|---|---|---|
| F23 | ETr_inst = [0.408·Δ·(Rn−G)+γ·(66/T)·u₂·(es−ea)]/[Δ+γ·(1+0.25·u₂)] *(ASCE soatlik alfalfa)* | **max 0**; (es−ea) max 0 |
| F24 | TEW = 1000·(θ_FC−0.5·θ_WP)·0.10 ; De≤REW→Kr=1 ; De>REW→Kr=(TEW−De)/(TEW−REW) | **De [0, TEW]** |
| F25 | ETrF_hot = Kr·1.05 | — |
| F26 | λET_cold = 1.05·ETr_cold·λ/3600 | — |
| F27 | λET_hot = ETrF_hot·ETr_hot·λ/3600 | — |
| F28 | H_hot = (Rn−G0)_hot − λET_hot ; H_cold = (Rn−G0)_cold − λET_cold | — |
| F29 | dTa_hot = H_hot·rah_hot/(ρ·cp) ; dTa_cold = H_cold·rah_cold/(ρ·cp) *(SEBAL_B: dTa_cold=0)* | — |
| F30 | c4 = (dTa_hot−dTa_cold)/(Ts_hot−Ts_cold) | — |
| F31 | c5 = dTa_cold − c4·Ts_cold | — |

### E. Sezilarli issiqlik H — piksel iteratsiyasi (Monin-Obukhov)
| # | Formula | Clamp |
|---|---|---|
| F32 | dT(x,y) = c4·Ts + c5 | **[dTa_cold, dTa_hot] ± 0.2·oraliq** |
| F33 | Ta = Ts − dT | **ERA5 AIR_TEMP ± 15 K** |
| F34 | H = ρ·cp·dT/rah | **−100 ≤ H ≤ (Rn−G0)** |
| F35 | L_MO = −ρ·cp·u*³·Ts/(k·g·H) | **[−1e6, 1e6]** |
| F36 | ψm, ψh (barqarorlik) → u* = k·u₂₀₀/(ln(200/z₀m)−ψm) | **max 0.02** |
| F37 | rah = (ln(z₂/z₁)−ψh)/(k·u*) *(N iter, Dhungel damping)* | **max 1.0** |

### F. Lahzali oqimlar → kunlik ET
| # | Formula | Clamp |
|---|---|---|
| F38 | λE = Rn − G0 − H | **max 0** |
| F39 | λ_hv = (2.501−0.00236·(Ts−273))·10⁶ J/kg | — |
| F40 | ET_inst = λE·3600/λ_hv  (mm/soat) | — |
| F41 | ETrF_inst = ET_inst/ETr_inst | **[0, 1.05]** (ETr_inst max 0.01) |
| F42 | Rs24 = Σ(ERA5 SSRD, 24 soat)/86400 | — |
| F43 | Rn24 = (1−α)·Rs24 − 110·τsw | **max 0** |
| F44 | ETr24 = Σ(24 soatlik ASCE alfalfa PM), kun/tun koeff. (yoki GRIDMET) | **max 0**/soat |
| F45 | ET24 = ETrF_inst·ETr24  *(Eq 5.8)* | **max 0** |

### G. Oylik ET (`compute_monthly_et`, SEBAL_ID)
| # | Formula | Clamp |
|---|---|---|
| F46 | ETrF_interp = **eng yaqin sahna** ETrF_inst  *(Eq 5.9 — o'rtachalash YO'Q)* | — |
| F47 | ET_kun = ETrF_interp · ETr24(shu kun) | **max 0** |
| F48 | **ET_oy = Σ(kun=1..N) ET_kun**  (mm/oy) | — |

**Eng ta'sirli clamplar:** F34 (H: −100…Rn−G0), F41 (ETrF: 0…1.05),
F32 (dT anchor oraliq), F21/F37 (rah: ln(20)/(k·u*), max 1.0).

---

## Lizimetr validatsiya — CSV zonal-stat rejimi (`export_csv=True`)

Bushland (Texas) **tarozili lizimetri** bilan solishtirish uchun (paxta = O'zbekiston,
oltin standart — energiya balansi konstruksiya bo'yicha yopiq, closure gap YO'Q).

**Nega raster emas, CSV?** GEE **lazy** — `monthly=compute_monthly_et(...)` raster
EMAS, RETSEPT; piksel faqat trigger'да hisoblanadi. Butun tile'da interaktiv
`reduceRegion.getInfo()` → **"Too many concurrent aggregations"** (oylik = 30 kun ×
12 sahna anchor). Yechim — **BATCH table export** (limit yuqori).

```python
lys_parcels = main.parcels_from_points({          # 210×210m markazда → −30m ichki
    'NE': [-102.0955385, 35.18816985], 'SE': [-102.0955390, 35.18612583],  # drip
    'NW': [-102.0978919, 35.18817119], 'SW': [-102.0979121, 35.18613288]})  # sprinkler
main.run(
    roi_type='gaul', name='Texas', level=1,
    date_start='2021-03-01', date_end='2021-11-01',
    mode='SEBAL_ID', utc_offset=-6,               # Texas panhandle = CST (avto -7 xato!)
    process_by_tile=True, tiles=[(30, 36)],
    export_daily=False, export_monthly=False,
    export_csv=True, csv_region=lys_parcels,      # ← CSV rejimi
    folder='SEBAL_Bushland_CSV_2021', crs='EPSG:32613')
```

**Chiqish (Drive, kichik CSV):** `SEBAL_csv_scene_P30_R36` (har sahna: ET_inst, ET_24,
**Rn, G, H, LST, albedo, LE** + NDVI, LAI, u\*, rah, dT, EF — mean+median) va
`SEBAL_csv_monthly_P30_R36` (ET_MONTHLY, mean+median). Lizimetr o'lchaydigan bandlar
(Rn, G, LST, albedo) → **komponent-bo'yicha** solishtiruv.

**⚡ Tezlik — FAQAT `export_csv=True` rejimida** (oddiy raster rejim o'zgarmagan):
| | oddiy raster | export_csv (lizimetr) |
|---|---|---|
| Bulut precheck | butun ROI/tile | **parcel ustida** (tez + to'g'ri) |
| Anchor scale | 30m | **100m** (`ANCHOR_SCALE`; termal native → sifat o'zgarmas, ~10× tez) |

**Validatsiya (2021, instant/daily overpass, 4 lizimetr):** instant λE R²≈0.68
MBE≈−0.04 (energiya balansi QIYA EMAS ✅); daily R²≈0.78. Oylik esa siyrak
sun'iy-yo'ldosh qamrovi + tez fenologiya (may-iyun yashillanish o'tkazib yuboriladi)
sababli ekstrapolyatsiyada zaif — bu SEBAL fizikasi emas. Bog'liq: `bushland-lysimeter`.
