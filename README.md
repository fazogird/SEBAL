# SEBAL-GEE v4 — Evapotranspiration Pipeline

Google Earth Engine (Python API) asosida qurilgan, Landsat 8/9 va HLS (Harmonized Landsat Sentinel-2) ma'lumotlaridan foydalanadigan SEBAL (Surface Energy Balance Algorithm for Land) evapotranspiratsiya (ET) hisoblash pipeline'i. Bastiaanssen (1998) original formulasiga asoslangan, ERA5-Land reanalysis va SMAP tuproq namligi ma'lumotlari bilan integratsiyalashgan.

> Rabbim O'zi qo'llasin!

---

## Mundarija

1. [Umumiy arxitektura](#umumiy-arxitektura)
2. [Ishga tushirish](#ishga-tushirish)
3. [To'liq chaqiruv zanjiri](#toliq-chaqiruv-zanjiri)
4. [Modul-modul: formulalar va konstantalar](#modul-modul-formulalar-va-konstantalar)
5. [Ikkita rejim: `maqola` vs `pysebal`](#ikkita-rejim-maqola-vs-pysebal)
6. [Qo'shimcha quyi-tizimlar](#qoshimcha-quyi-tizimlar)
7. [Ma'lum cheklovlar va ochiq masalalar](#malum-cheklovlar-va-ochiq-masalalar)
8. [Manbalar](#manbalar)

---

## Umumiy arxitektura

```
run_sebal.py
    │
    ├─ ee.Initialize()
    ├─ ee_utils.install_getinfo_retry()   ← 429/500/503 xatolarga qarshi avtomatik retry
    │
    └─ main.run(...)
         │
         └─ [har bir tile uchun] process_tile()
              │
              ├─ 1. preprocessing   — tozalash, scale, ERA5, DEM
              ├─ 2. surface_props   — NDVI, SAVI, Albedo, Emissivity, z₀m, LAI
              ├─ 3. radiation       — K↓, L↓, L↑, Rn, G₀
              ├─ 4. energy_balance  — anchor pixel, u*, H (Monin-Obukhov), λE, ETrF
              ├─ 5. daily_et        — Rs24, Rn24, ET₂₄ (kunlik)
              │
              └─ 6. [faqat mode='pysebal']
                     et_decomposition → soil_moisture → biomass → irrigation
         │
         └─ Export: kunlik / oylik (monthly_analytics YOKI daily_et)
                     + ixtiyoriy: VIIRS downscaling, HLS S30 ETrF regressiya, OpenET validatsiya
```

**Loyihaning yadrosi** — energiya balansi tenglamasi:

```
Rn = G₀ + H + λE
```

qayerda `Rn` — sof radiatsiya, `G₀` — tuproq issiqlik oqimi, `H` — sezuvchan issiqlik oqimi, `λE` — yashirin issiqlik oqimi (bug'lanishga sarflanadigan energiya). SEBAL `λE`ni **qoldiq had** sifatida hisoblaydi: `λE = Rn - G₀ - H`.

---

## Ishga tushirish

```python
from sebal_gee_v4 import main
from sebal_gee_v4 import ee_utils

ee_utils.install_getinfo_retry()

main.run(
    roi_type='gaul', name='Kashkadarya', level=1,
    date_start='2026-05-01', date_end='2026-05-31',
    mode='pysebal',              # 'maqola' yoki 'pysebal'
    satellite='HLS',             # 'L8' | 'L9' | 'BOTH' | 'HLS'
    cloud_max=70,
    process_by_tile=True,
    tiles=['T41SPC', 'T41SPD'],  # HLS uchun MGRS, Landsat uchun (path,row)
    export_daily=False,
    export_monthly=True,
    save_et=True, save_biomass=True,
    save_etref=True, save_tact=True, save_eact=True,
    folder='SEBAL_Output',
    scale=30, crs='EPSG:32642',
)
```

### Kirish ma'lumotlari

| Manba | Nima uchun | Kolleksiya ID |
|---|---|---|
| Landsat 8/9 C2L2 | Optik/termal SR, ST | `LANDSAT/LC08\|LC09/C02/T1_L2` |
| HLS L30 | Alternativ optik/termal (Celsius) | `NASA/HLS/HLSL30/v002` |
| ERA5-Land Hourly | Shamol, harorat, bosim, radiatsiya | `ECMWF/ERA5_LAND/HOURLY` |
| SRTM | DEM, slope | `USGS/SRTMGL1_003` |
| SMAP L4 | Tuproq namligi (pysebal rejimida) | `NASA/SMAP/SPL4SMGP/008` |
| ESA WorldCover | Anchor pixel uchun ekin maskasi | `ESA/WorldCover/v200` |

---

## To'liq chaqiruv zanjiri

```
process_tile(roi, date_start, date_end, mode, satellite, cloud_max)
│
├─ preprocessing.build_collection()
│    ├─ apply_qa_mask() / apply_qa_mask_hls()      — bulut/soya/qor/qism filtri
│    ├─ apply_scale_factors() / apply_scale_factors_hls()
│    ├─ add_terrain(roi)                            — DEM + slope, Landsat CRS'ga reproject
│    ├─ get_era5_for_image(roi)                      — overpass ±1 soat oyna, .mean()
│    └─ add_air_density()
│
├─ collection.map(surface_props.compute_all)
│    ├─ compute_ndvi
│    ├─ compute_savi
│    ├─ compute_albedo
│    ├─ compute_emissivity
│    ├─ compute_z0m
│    ├─ compute_transmissivity
│    └─ compute_lai
│
├─ collection.map(radiation.compute_all)
│    ├─ compute_incoming_shortwave      (K↓)
│    ├─ compute_incoming_longwave       (L↓)
│    ├─ compute_outgoing_longwave       (L↑)
│    ├─ compute_net_radiation           (Rn)
│    ├─ compute_soil_heat_flux          (G₀)
│    └─ compute_net_available_energy   (Rn−G₀)
│
├─ [har sahna, alohida] energy_balance.compute_all(img, roi)
│    ├─ select_anchor_pixels            (cold/hot)
│    ├─ compute_friction_velocity       (u*)
│    ├─ compute_rah_neutral             (rah, neytral)
│    ├─ compute_sensible_heat_flux      (H — Monin-Obukhov iteratsiya)
│    ├─ compute_latent_heat_flux        (λE)
│    └─ compute_etrf / compute_evaporative_fraction
│
├─ daily_et.compute_daily_et(img, roi)
│    ├─ get_daily_solar_radiation       (Rs24, ERA5)
│    └─ Rn24 → ET₂₄
│
└─ [faqat mode == 'pysebal']
     ├─ et_decomposition.compute_all(img)
     │    ├─ compute_vapor_pressure
     │    ├─ compute_etref
     │    ├─ compute_etpot
     │    ├─ compute_advection_factor
     │    ├─ compute_crop_coefficients   (KC, KC_MAX, ET_DEFICIT)
     │    └─ compute_et_separation       (Tact, Eact)
     ├─ soil_moisture.compute_all(img)   — SMAP
     ├─ biomass.compute_all(img)         — FPAR → APAR → LUE → Biomass
     └─ irrigation.compute_all(img)      — sug'orish klassi
```

Keyin `main.run()` darajasida:

```
_export_daily()        — agar export_daily=True
_export_monthly()      — mode='pysebal' → monthly_analytics.compute_all_monthly()
                          mode='maqola'  → daily_et.compute_monthly_et()
_viirs_export_month()  — agar use_viirs=True (ixtiyoriy)
_s30_export_month()    — agar use_s30_etrf=True (ixtiyoriy)
validation.validate()  — agar validate=True (OpenET bilan solishtirish)
```

---

## Modul-modul: formulalar va konstantalar

### 1. `preprocessing.py`

```
SR      = DN × 0.0000275 − 0.2                    (clamp 0–1)
LST     = DN × 0.00341802 + 149.0                 [Kelvin]  — Landsat C2L2
LST_HLS = B10 + 273.15                            [Kelvin]  — HLS (B10 Celsius'da beriladi)
Wind_speed(10m) = √(u_wind² + v_wind²)
ρₐ = P / (287.058 × T)                            [R_specific = 287.058 J/(kg·K)]
```

ERA5 oynasi: Landsat overpass vaqtidan **±1 soat**, shu oraliqning o'rtachasi (`.mean()`) olinadi.

QA_PIXEL bitmask (Landsat): fill (bit 0), dilated cloud (bit 1), cirrus (bit 2), cloud (bit 3), cloud shadow (bit 4), snow (bit 5) — olib tashlanadi. Suv (bit 7) — saqlanadi, alohida maska sifatida.

### 2. `surface_props.py`

```
NDVI   = (NIR − Red) / (NIR + Red)
SAVI   = ((NIR − Red) / (NIR + Red + L)) × (1 + L)              L = 0.5  [Huete 1988]

Albedo = 0.246×B2 + 0.146×B3 + 0.191×B4 + 0.304×B5
         + 0.105×B6 + 0.008×B7                                  [Olmedo 2016]
         clamp(0.0, 0.70)

ε₀ = 1.009 + 0.047 × ln(NDVI)              [0.16 ≤ NDVI ≤ 0.74, Van de Griend & Owe 1992]
     NDVI < 0            → ε₀ = 0.985  (suv)
     0 ≤ NDVI < 0.16     → ε₀ = 0.960  (yalang'och tuproq)
     NDVI > 0.74         → ε₀ = 0.985  (zich o'simlik)

z₀m = exp(−5.809 + 5.62 × SAVI)            [Bastiaanssen et al. 2001, Gediz]
      clamp(0.0002, 1.0)
z₀h = z₀m / exp(kB⁻¹)                      kB⁻¹ = 2.3

τsw = 0.75 + 2×10⁻⁵ × elevation            [Allen et al. 2007]

LAI = −ln((0.69 − SAVI) / 0.59) / 0.91     [0.1 ≤ SAVI < 0.687]
      SAVI ≥ 0.687 → LAI = 6.0
```

### 3. `radiation.py`

```
K↓ = (ERA5_SSRD / 3600) × (τsw / 0.75)
L↓ = ERA5_STRD / 3600
L↑ = ε₀ × σ × T₀⁴                          σ = 5.67×10⁻⁸ W/m²/K⁴

Rn = (1 − α)×K↓ + L↓ − L↑ − (1 − ε₀)×L↓    [Bastiaanssen F.5]

G₀ = Rn × (T₀−273.15)/α × (0.0038α + 0.0074α²) × (1 − 0.978×NDVI⁴)
     [Simplified Bastiaanssen 2000]
     Suv piksellar / NDVI < 0 → G₀ = 0.5 × Rn
     clamp: G₀ ∈ [−0.10×Rn, 0.50×Rn]

Rn−G₀ = mavjud energiya (H va λE ga taqsimlanadi)
```

### 4. `energy_balance.py` — SEBAL'ning yuragi

**Anchor pixel tanlash** (Bastiaanssen 1998, p.206):
- Cold: NDVI top 5%, LST bottom 20%, albedo < 0.20, slope < 5°
- Hot: NDVI bottom 10%, LST top 5%, albedo ≥ 0.18, slope < 5°
- Ixtiyoriy: faqat ESA WorldCover cropland (class 40) ustida

**Shamol va ishqalanish tezligi:**
```
u_200 = u_10 × ln(200/0.12) / ln(10/0.12)              [z0m_weather = 0.12m, grass]
u*    = k × u_200 / ln(200/z0m)                          k = 0.41 (Von Karman)
        clamp min 0.02
rah_neutral = ln(2.0/0.1) / (k×u*)                       clamp min 1.0
```

**δTa kalibratsiya (F.30):**
```
dTa_hot  = H_hot × rah_hot / (ρ×cp)          cp = 1004 J/(kg·K)
dTa_cold = 0
c4 = dTa_hot / (T_hot − T_cold)
c5 = −c4 × T_cold
dTa(x,y) = c4 × T₀(x,y) + c5
```

**Sezuvchan issiqlik oqimi va Monin-Obukhov iteratsiyasi:**
```
H = ρ × cp × dTa / rah

L_MO = −ρ × cp × u*³ × T₀ / (k × g × H)        g = 9.81 m/s²

Nobarqaror (L < 0), Paulson (1970):
  x = (1 − 16z/L)^0.25
  ψm = 2ln((1+x)/2) + ln((1+x²)/2) − 2·arctan(x) + π/2
  ψh = 2ln((1+x²)/2)

Barqaror (L > 0), Webb (1970):
  ψm = ψh = −5z/L
```

Iteratsiya 5 marta takrorlanadi (`max_iter=5`), har safar `u*` va `rah` yangilanadi.

**Yakuniy oqimlar:**
```
λE = Rn − G₀ − H

ETrF        = λE / (Rn−G₀)     clamp(0, 1.5)
EVAP_FRAC Λ = λE / (Rn−G₀)     clamp(0, 1.0)
```

### 5. `daily_et.py`

```
Rs24 = ERA5_SSRD.sum(24 soat) / 86400          [W/m², o'rtacha]
Rn24 = (1 − α) × Rs24 − 110 × τsw               [110 = De Bruin 1987 konstanta]
ET₂₄ = Λ × Rn24 × 86400 / λ                      λ = 2.45×10⁶ J/kg   [mm/kun]
```

**Oylik ekstrapolyatsiya:** Λ, albedo, τsw — Landsat sahnalar orasida **chiziqli interpolyatsiya**; Rs24 — ERA5'dan har kun uchun alohida (interpolyatsiyasiz). `ET_MONTHLY = Σ ET_kun`.

### 6. `et_decomposition.py` (faqat `pysebal` rejimida)

```
esat = 0.6108 × exp(17.27×T / (T+237.3))                    [kPa]
eact = 0.6108 × exp(17.27×Td / (Td+237.3))                  [kPa]
Δ    = 4098 × esat / (T+237.3)²                                [kPa/°C]
γ    = P(kPa) × 0.000665                                       [psychrometric constant]
u₂   = u₁₀ × 0.745                                              [10m → 2m, FAO-56]

ETref = [0.408×Δ×Rn24 + γ×900/(Ta+273)×u₂×VPD] / [Δ + γ×(1+0.34×u₂)]
        [FAO-56 Penman-Monteith, Allen et al. 1998]

rs_min  = 100 / max(LAI, 0.5)
rah_pot = max(208/u₂, 25)

Advection Factor = 1 + 0.985 × [exp(VPD×0.08) − 1] × EF

KC     = ET₂₄ / ETREF_24         clamp(0, 2.5)
KC_MAX = ETPOT_24 / ETREF_24     clamp(0, 2.5)

Tpot = (1 − exp(−0.6×LAI)) × ETpot        [k_ext = 0.6, Beer-Lambert]
Tact = clamp(ET₂₄/ETpot, 0, 1) × Tpot
Eact = ET₂₄ − Tact
```

### 7. `soil_moisture.py` (faqat `pysebal` rejimida)

SMAP L4'dan Landsat overpass vaqtiga **eng yaqin** (±3 soat) o'lchov olinadi (o'rtacha emas).

```
stress = wetness / 0.4     clamp(0, 1)      [FAO-56 depletion trigger p=0.4]
```

### 8. `biomass.py` (faqat `pysebal` rejimida)

```
FPAR = 1.257 × NDVI − 0.161                    [Bastiaanssen & Ali 2003]
PAR  = 0.48 × Rs24
APAR = FPAR × PAR

heat_stress  = 1 − ((Ta−25)/(25−5))²          clamp(0.05, 1.0)   [T_opt=25°C, T_cold=5°C]
vapor_stress = 1 − 0.2 × VPD                    clamp(0.05, 1.0)   [k_vpd=0.2 kPa⁻¹]

LUE = 2.5 × heat_stress × vapor_stress × moisture_stress   [LUEmax=2.5 gC/MJ, C3 o'rtacha]

Biomass = APAR × 0.0864 × LUE × 10 × 2.0        [kg quruq modda / ha / kun]
```

### 9. `irrigation.py` (faqat `pysebal` rejimida)

```
Sug'orish klassi (moisture_stress bo'yicha):
  > 0.85        → 0 (kerak emas)
  0.65 – 0.85   → 1 (ehtimol)
  0.45 – 0.65   → 2 (kerak)
  < 0.45        → 3 (darhol)
  NDVI < 0.15   → 0 (ekin yo'q — yalang'och tuproq)

Sug'orish chuqurligi (mm) = max(0.5 − wetness, 0) × 300.0
```

---

## Ikkita rejim: `maqola` vs `pysebal`

| | `mode='maqola'` | `mode='pysebal'` |
|---|---|---|
| Fayl | `daily_et.py` | `monthly_analytics.py` |
| Asosiy ET | `ET_24 / ET_MONTHLY` | `ET_24 / ET_MONTHLY` — **bir xil formula** |
| Qo'shimcha chiqish | Yo'q | `ETREF, ETPOT, DEFICIT, TACT, EACT, KC, Biomass, Sug'orish klassi` |
| Interpolyatsiya | Chiziqli (butun-tasvir) | Chiziqli (butun-tasvir), **10 ta band** |

Ikkala rejimda ham **oylik ET yig'indisining asosiy formulasi bir xil** — farq faqat `pysebal` rejimi qo'shimcha 7 ta dekompozitsiya bandini (ETref, ETpot, T/E ajratish va h.k.) hisoblashida.

---

## Qo'shimcha quyi-tizimlar

| Modul | Vazifasi |
|---|---|
| `hls_s30_etrf.py` | Sentinel-2 (HLS S30) spektral indekslar orqali ETrF regressiyasi, oylik ET'ni 30m piksel darajasida "to'ldirish" |
| `viirs_downscaling.py` | VIIRS (500m) → 30m downscaling, kunlik ET gap-filling |
| `monthly_analytics.py` | `pysebal` rejimidagi to'liq oylik dekompozitsiya |
| `validation.py` | OpenET (7 model: DisALEXI, eeMETRIC, geeSEBAL, PT-JPL, SIMS, SSEBop, Ensemble) bilan solishtirish — R², RMSE, NSE, MBE, MAE |

---

## Ma'lum cheklovlar va ochiq masalalar

Loyihaning ichki auditida aniqlangan, hozircha tuzatilmagan yoki qisman hal qilingan joylar:

- `SOIL_HEAT_FLUX['ndvi_extinction']` konfiguratsiyada `0.978`, ko'p manbada standart qiymat `0.98`.
- `radiation.py`dagi `compute_rn24()` funksiyasi hech qayerda chaqirilmaydi — `daily_et.py` xuddi shu formulani mustaqil qayta hisoblaydi (duplikat kod).
- `ETrF` va `EVAP_FRAC` — bir xil formuladan (`λE/(Rn−G₀)`), faqat clamp chegarasi farqli (1.5 vs 1.0).
- `et_decomposition.py`dagi `compute_etref()` — referens ET'ni SEBAL'ning o'z (kuzatilgan albedo bilan hisoblangan) `RN24`sidan chiqaradi; klassik FAO-56 referens ET meteorologik, yer yuzasidan mustaqil bo'lishi kerak.
- Kunlik/oylik ET'da yuqori chegaraviy `.clamp()` yo'q, faqat `.max(0)` — g'ayrioddiy yuqori qiymatlarga qarshi QA filtri yo'q.
- `energy_balance.py`da anchor pixel tanlashda ESA WorldCover cropland maskasi ishlatilganda, agar hudud butunlay bo'sh chiqsa — oxirgi fallback yo'q (potensial "silent failure").
- Interpolyatsiya mantig'i (`daily_et.py`, `monthly_analytics.py`, `hls_s30_etrf.py`) — uchta alohida, biroz farqli implementatsiya.

---

## Manbalar

- Bastiaanssen, W.G.M. et al. (1998). *A remote sensing surface energy balance algorithm for land (SEBAL)*. Journal of Hydrology.
- Bastiaanssen, W.G.M. (2000). *SEBAL-based sensible and latent heat fluxes in the irrigated Gediz Basin, Turkey*. Journal of Hydrology.
- Allen, R.G., Tasumi, M., Trezza, R. (2007). *Satellite-Based Energy Balance for Mapping Evapotranspiration with Internalized Calibration (METRIC)*. ASCE J. Irrig. Drain. Eng.
- Allen, R.G. et al. (1998). *Crop Evapotranspiration — FAO Irrigation and Drainage Paper 56*.
- Huete, A.R. (1988). *A soil-adjusted vegetation index (SAVI)*. Remote Sensing of Environment.
- Van de Griend, A.A., Owe, M. (1992). *On the relationship between thermal emissivity and NDVI*.
- Olmedo, G. et al. (2016). R `water` package — broadband albedo coefficients.
- Paulson, C.A. (1970); Webb, E.K. (1970) — atmosfera barqarorlik tuzatmalari.
- De Bruin, H.A.R. (1987) — 24-soatlik net radiatsiya empirik konstanta.

---

*Ushbu README loyihaning `scripts_v3` bosqichidagi manba kodidan (`sebal_gee_v4/` moduli) to'g'ridan-to'g'ri chiqarilgan — barcha formula va konstantalar kod ichidan tasdiqlangan.*
