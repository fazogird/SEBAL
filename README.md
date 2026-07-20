# SEBAL-GEE v4 — Evapotranspiration Pipeline

Google Earth Engine (Python API) asosida qurilgan, Landsat 8/9 va HLS (Harmonized Landsat Sentinel-2) ma'lumotlaridan foydalanadigan SEBAL (Surface Energy Balance Algorithm for Land) evapotranspiratsiya (ET) hisoblash pipeline'i. Bastiaanssen (1998) original formulasiga asoslangan, ERA5-Land reanalysis va SMAP tuproq namligi ma'lumotlari bilan integratsiyalashgan.

> Rabbim O'zi qo'llasin!

---

## Mundarija

1. [Umumiy arxitektura](#umumiy-arxitektura)
2. [Ishga tushirish](#ishga-tushirish)
3. [To'liq chaqiruv zanjiri](#toliq-chaqiruv-zanjiri)
4. [Modul-modul: formulalar va konstantalar](#modul-modul-formulalar-va-konstantalar)
5. [Rejimlar: `SEBAL_B` / `pysebal` / `yangiliklar`](#rejimlar-sebal_b--pysebal--yangiliklar)
6. [Qo'shimcha quyi-tizimlar](#qoshimcha-quyi-tizimlar)
7. [Hududга-bog'liq kalibratsiya (REGION_PRESETS)](#hududга-bogliq-kalibratsiya-region_presets)
8. [Ma'lum cheklovlar va ochiq masalalar](#malum-cheklovlar-va-ochiq-masalalar)
9. [O'zgartirishlar jurnali](#ozgartirishlar-jurnali-2026-07--bug-fix-va-yaxshilanishlar)
10. [Manbalar](#manbalar)

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
    mode='pysebal',              # 'SEBAL_B' | 'pysebal' | 'yangiliklar'
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
│    ├─ compute_lai            (L=0.1 SAVI'dan — z₀m'dan OLDIN)
│    ├─ compute_z0m            (0.018 × LAI)
│    └─ compute_transmissivity
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
                          mode='SEBAL_B' → daily_et.compute_monthly_et()
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

SAVI(0.1) = 1.1 × (NIR − Red) / (NIR + Red + 0.1)              L = 0.1  [SEBAL_ID]
LAI = −ln((0.69 − SAVI) / 0.59) / 0.91     [SAVI < 0.687]      cap 6.0

z₀m = 0.018 × LAI                          [SEBAL_ID; Tasumi 2003]
      clamp(0.005, 1.0)                    z0m_min 0.005 (Table 4.11)
z₀h = z₀m / exp(kB⁻¹)                      kB⁻¹ = 2.3

# Shamol ekstrapolyatsiyasi uchun ALOHIDA z₀m (vegetatsiya balandligidan):
h        = 2.0 × (NDVI − 0.20) / (0.85 − 0.20)
z₀m,wind = 0.123 × h                       [Brutsaert 1982]

τsw = 0.75 + 2×10⁻⁵ × elevation            [Allen et al. 2007]
```

> **Eslatma:** eski Gediz `z₀m = exp(−5.809 + 5.62×SAVI)` (Bastiaanssen 2001)
> va umumiy `L=0.5` li SAVI konfigda zaxira sifatida qoldi, lekin ishlatilmaydi.

### 3. `radiation.py`

```
K↓ = (ERA5_SSRD / 3600) × (τsw / 0.75)

L↓  (rejimga bog'liq):
  mode='yangiliklar'      → L↓ = ERA5_STRD / 3600           [o'lchangan]
  mode ∈ {SEBAL_B,pysebal}→ L↓ = 1.08 × σ × [−ln(τsw)]^0.265 × Tref⁴
                             Tref = cold anchor yuza harorati (cropland p10 LST;
                             cold_mask yo'q bo'lsa ERA5 AIR_TEMP mediana zaxira)
                             τsw ∈ [0.01, 0.99]              [Tasumi 2003]

L↑ = ε₀ × σ × T₀⁴                          σ = 5.67×10⁻⁸ W/m²/K⁴

Rn = (1 − α)×K↓ + L↓ − L↑ − (1 − ε₀)×L↓    [Bastiaanssen F.5]

G₀ = Rn × (T₀−273.15)/α × (0.0038α + 0.0074α²) × (1 − 0.978×NDVI⁴)
     [Simplified Bastiaanssen 2000]
     Suv piksellar / NDVI < 0 → G₀ = 0.5 × Rn
     clamp: G₀ ∈ [−0.10×Rn, 0.50×Rn]

Rn−G₀ = mavjud energiya (H va λE ga taqsimlanadi)
```

### 4. `energy_balance.py` — SEBAL'ning yuragi

**Anchor pixel tanlash** (ikki-zonali, ESA WorldCover v200):
- **Cold** = cropland (class 40): NDVI yuqori, LST past → H ≈ 0
- **Hot** = bare/sparse (60) + shrubland (20): doim quruq → λE ≈ 0
  *(hot ekindan EMAS — sug'orilgan mavsumda ekin ham transpiratsiya qiladi)*
- Tanlash: beton kaskad (`cimec/plan_a/plan_b/pysebal`) → ROI fallback →
  `default` persentil kafolati. `anchor_method` bilan boshqariladi.

**Shamol va ishqalanish tezligi** (per-piksel z₀m):
```
u_200 = u_10 × ln(200/z₀m,wind) / ln(10/z₀m,wind)       z₀m,wind = 0.123×h
u*    = k × u_200 / ln(200/z₀m)                          k = 0.41; z₀m=0.018·LAI
        clamp min 0.02
rah_neutral = ln(z₂_rah/z₁) / (k×u*) = ln(0.2/0.1)/(k·u*)   clamp min 1.0
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

Barqarorlik tuzatmalari z₁=0.1m va z₂=2.0m da (rah'ning 0.2m dan BOSHQA!):

Nobarqaror (L < 0), Paulson (1970):
  x = (1 − 16z/L)^0.25
  ψm = 2ln((1+x)/2) + ln((1+x²)/2) − 2·arctan(x) + π/2
  ψh(z) = 2ln((1+x²)/2);   psi_h = ψh(2.0) − ψh(0.1)

Barqaror (L > 0), Webb (1970):
  ψm = −5×2.0/L;   ψh = −5×(2.0−0.1)/L
```

**Iteratsiya — ikki siklli** (`config.py` `ITERATION`: `max_iter=15`,
`tol_rel=0.01` = 1% nisbiy): (A) hot-piksel skalyarlarida sof-Python sikl
konvergensiyagacha → `c4_i, c5_i, N_A`; (B) aynan `N_A` raster qadam
(`getInfo`siz). Har qadam ψ va u* Dhungel (2016) damping bilan so'ndiriladi.
Batafsil — O'zgartirishlar jurnali #6, #7.

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
λ    = (2.501 − 0.00236 × (LST − 273)) × 10⁶    [J/kg, haroratga bog'liq; Tasumi 3.48]
ET₂₄ = Λ × Rn24 × 86400 / λ                                            [mm/kun]
```

**Oylik ekstrapolyatsiya:** Λ, albedo, τsw, **LST** — Landsat sahnalar orasida
**chiziqli interpolyatsiya** (LST → haroratga bog'liq λ uchun); Rs24 — ERA5'dan
har kun uchun alohida (interpolyatsiyasiz). `ET_MONTHLY = Σ ET_kun`.

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

## Rejimlar: `SEBAL_B` / `pysebal` / `yangiliklar`

| | `mode='SEBAL_B'` | `mode='pysebal'` |
|---|---|---|
| Fayl | `daily_et.py` | `monthly_analytics.py` |
| Asosiy ET | `ET_24 / ET_MONTHLY` | `ET_24 / ET_MONTHLY` — **bir xil formula** |
| L↓ | empirik (Tref, Tasumi) | empirik (Tref, Tasumi) |
| Qo'shimcha chiqish | Yo'q | `ETREF, ETPOT, DEFICIT, TACT, EACT, KC, Biomass, Sug'orish klassi` |
| Interpolyatsiya | Chiziqli (butun-tasvir) | Chiziqli (butun-tasvir), **10+ band** |

> `mode='maqola'` — eski nom, endi **`SEBAL_B`** deb ataladi (O'zgartirishlar
> jurnali #14). Ikkala rejimda ham **oylik ET yig'indisining asosiy formulasi
> bir xil** — farq faqat `pysebal` qo'shimcha dekompozitsiya bandlarini
> (ETref, ETpot, T/E ajratish va h.k.) hisoblashida.

**L↓ rejim varianti:** `mode='yangiliklar'` — L↓ uchun o'lchangan ERA5 STRD
ishlatiladi (empirik formula o'rniga). Qolgan hamma narsa `SEBAL_B` bilan bir xil.

---

## Qo'shimcha quyi-tizimlar

| Modul | Vazifasi |
|---|---|
| `hls_s30_etrf.py` | Sentinel-2 (HLS S30) spektral indekslar orqali ETrF regressiyasi, oylik ET'ni 30m piksel darajasida "to'ldirish" |
| `viirs_downscaling.py` | VIIRS (500m) → 30m downscaling, kunlik ET gap-filling |
| `monthly_analytics.py` | `pysebal` rejimidagi to'liq oylik dekompozitsiya |
| `validation.py` | OpenET (7 model: DisALEXI, eeMETRIC, geeSEBAL, PT-JPL, SIMS, SSEBop, Ensemble) bilan solishtirish — R², RMSE, NSE, MBE, MAE |

---

## Hududга-bog'liq kalibratsiya (REGION_PRESETS)

Model **global**, lekin ba'zi parametrlar hududга/ekinга bog'liq. SEBAL'ning
kuchi shундаki — **anchor kalibratsiyasi (`dT = c4·Ts + c5`) energiya balansini
HAR SAHNA uchun avtomatik rostlaydi**, shu sabab `Rn`, `H`, `EF` katta darajада
o'z-o'zini kalibrlaydi. Faqat **yuza-parametr formulalari** va **iqlim
konstantalari** avtomatik moslashmaydi — ularni joy o'zgarganда qo'lда
sozlaysiz.

> **⚠️ `config.py` `REGION_PRESETS` — FAQAT MA'LUMOTNOMA.** Pipeline kodi uni
> O'QIMAYDI; qo'shilishi hozirgi natijalarga ta'sir qilmaydi. `'idaho'` preset —
> hozirgi aktiv konfiguratsiyaning aynan nusxasi. Boshqa hududга o'tish uchun
> tegishli qiymatni **qo'lда** aktiv config kalitiga ko'chiring (avtomatik wiring
> ATAYLAB yo'q — natijalar tasodifan o'zgarmasligi uchun). O'qish:
> `cfg.get_region_preset('idaho')`.

### 1. HECH QACHON o'zgartirmang — universal fizika
`STEFAN_BOLTZMANN`, `VON_KARMAN`, `GRAVITY`, `CP_AIR`, `GSC`, λ formulasi,
Monin–Obukhov / Paulson–Webb barqarorlik, FAO-56 Penman–Monteith tuzilishi.

### 2. HUDUD / IQLIM o'zgарganда

| Parametr | Config joyi | Nimaga bog'liq | Manba |
|---|---|---|---|
| `rn24_constant = 110` | `DAILY_ET` | Iqlim — Rn24 net-uzun-to'lqin proksi; arid ≈100–140 | De Bruin 1987 |
| Albedo koeffitsientlari | `OLMEDO_COEFFICIENTS` | Atmosfera — Kimberly, Idaho (SMARTS) | Olmedo 2016 |
| `TRANSMISSIVITY['base']=0.75` | `TRANSMISSIVITY` | Iqlim — nam hududда pastroq | Allen 2007 |
| Anchor land-cover klasslari | `ANCHOR_LANDCOVER` | Landshaft (pastда) | ESA WorldCover |
| `crs` | run_sebal.py | UTM zonasi (Idaho 32611, Gediz 32635) | — |

> `overpass_hour_utc` ([config.py](sebal_gee_v4/config.py)) **hech qayerда
> ishlatilmaydi** (o'lik config — ERA5 haqiqiy sahna vaqtini oladi). O'zgartirish
> shart emas.

### 3. EKIN / o'simlik turi o'zgарganда

| Parametr | Config joyi | Nimaga bog'liq |
|---|---|---|
| `h_max = 2.0` | `WIND_ROUGHNESS` | **To'g'ridan-to'g'ri ekin:** bug'doy ~1m, makkajo'xori ~2–3m, bog' ~4m |
| `Z0M_LAI_COEF = 0.018` | `config.py` | Qoplam tuzilishi (dala ekini ~0.018; o'rmon/bog' boshqача) |
| `ndvi_min/max = 0.20/0.85` | `WIND_ROUGHNESS` | Yalang'och tuproq va to'liq qoplam NDVI |
| LAI `0.69, 0.59, 0.91` | `surface_props.compute_lai` | SAVI→LAI empirik, ekinга kalibrlangan |
| `SAVI_L_LAI=0.1`, `savi_L=0.5` | `config.py`, `ROUGHNESS` | Tuproq tuzatmasi (zichlik) |
| `LUEMAX = 2.5` | `biomass.py` | **⚠️ Eng ekinга bog'liq:** C3 (bug'doy 2.5) vs C4 (makkajo'xori ~4.0) |
| FPAR `1.257, -0.161`, T_opt, k_vpd | `MONTEITH`, `biomass.py` | Ekin fotosintez parametrlari |
| SMAP depletion `p = 0.4` | `soil_moisture.py` | FAO-56 — ekinга qarab 0.3–0.7 |

### z0m usuli — hudud tanlovi
Eski **Gediz (Turkey)** formulasi `z0m = exp(−5.809 + 5.62·SAVI)` config'да
`ROUGHNESS['z0m_a/z0m_b']` sifatida turibdi (hozir ishlatilmaydi). Hozirgi
aktiv usul — **SEBAL_ID** `z0m = 0.018·LAI` (dala ekinlari). Turkey/Gediz uchun
`turkey_gediz` preset Gediz koeffitsientlarini ko'rsatadi — lekin uni qo'llash
`compute_z0m`'га Gediz shoxini qo'shishни talab qiladi (hozir yo'q).

### "Ekin turini bilishim kerakmi?"
- **Faqat ET (`SEBAL_B`):** ekin xaritasi **shart emas** — anchor o'zi rostlaydi.
  Lekin `h_max` ni asosiy ekin balandligiga qo'ying va anchor klasslarini
  landshaftga moslang.
- **Biomassa / dekompozitsiya (`pysebal`):** ekin turi **SHART** — `LUEMAX`,
  FPAR, stress, depletion `p` ekinга kuchli bog'liq (`MONTEITH` config'да
  `TODO: Appendix A jadvali` deb belgilangan).

### Amaliy checklist: "Idaho → yangi hudud"
1. `ANCHOR_LANDCOVER` — cold/hot uchun to'g'ri ESA klasslar (bare tuproq bormi?)
2. `WIND_ROUGHNESS['h_max']` — asosiy ekin balandligi
3. `DAILY_ET['rn24_constant']` — iqlim (nam/quruq)
4. `TRANSMISSIVITY['base']` — nam iqlimда pasaytiring
5. z0m usuli — Turkey uchun Gediz, dala ekinlari uchun 0.018·LAI
6. (biomassa kerak bo'lsa) `biomass.LUEMAX` + ekin parametrlari
7. `crs` — UTM zonasi

---

## Ma'lum cheklovlar va ochiq masalalar

Loyihaning ichki auditida aniqlangan, hozircha tuzatilmagan yoki qisman hal qilingan joylar:

- `SOIL_HEAT_FLUX['ndvi_extinction']` konfiguratsiyada `0.978`, ko'p manbada standart qiymat `0.98`.
- `radiation.py`dagi `compute_rn24()` funksiyasi hech qayerda chaqirilmaydi — `daily_et.py` xuddi shu formulani mustaqil qayta hisoblaydi (duplikat kod).
- `ETrF` va `EVAP_FRAC` — bir xil formuladan (`λE/(Rn−G₀)`), faqat clamp chegarasi farqli (1.5 vs 1.0).
- ~~`et_decomposition.py`dagi `compute_etref()` — referens ET'ni SEBAL'ning o'z `RN24`sidan chiqaradi~~ **✅ HAL QILINDI** (O'zgartirishlar jurnali #10 — ASCE-EWRI `ref_et` ga o'tkazildi).
- Kunlik/oylik ET'da yuqori chegaraviy `.clamp()` yo'q, faqat `.max(0)` — g'ayrioddiy yuqori qiymatlarga qarshi QA filtri yo'q.
- ~~`energy_balance.py`da anchor tanlashda hudud bo'sh chiqsa — oxirgi fallback yo'q (silent failure)~~ **✅ HAL QILINDI** (O'zgartirishlar jurnali #8 — beton kaskad + `default` fallback + null-xavfsizlik).
- Interpolyatsiya mantig'i (`daily_et.py`, `monthly_analytics.py`, `hls_s30_etrf.py`) — uchta alohida, biroz farqli implementatsiya.

### ⚠️ `rah` `z2_rah=0.2` nomuvofiqligi — ATAYLAB saqlangan (2026-07 diagnostika)

`energy_balance.py` `rah` log hadi `ln(z2_rah/z1) = ln(0.2/0.1)` ishlatadi,
lekin **barqarorlik** tuzatmasi `ψh(z2)−ψh(z1)` esa `z2 = 2.0 m` gача
integrallanadi. Klassik SEBAL/METRIC'da (Allen et al. 2007; Tasumi 2003,
Eq. 3.34–3.43) `rah` **bitta juft** balandlik orasida: `z1=0.1`, `z2=2.0` —
ya'ni log hadida ham `z2=2.0` bo'lishi kerak. Demak hozirgi `z2_rah=0.2`
jismonan noto'g'ri.

**Diagnostika (July, tile P40/R30, 2025-07-10) topilmalari:**
- Hot anchor SOG'LOM: NDVI_hot=0.179 (bare), `hot_LST−cold_LST = 24.2 K`,
  `H_hot = Rn−G₀ = 377 W/m²`. Anchor tanlash muammo EMAS.
- `z2_rah=0.2` da `ln(0.2/0.1)=0.693` shu qadar kichikki, beqaror sharoitda
  `ψh > 0.693` bo'lganda `rah` numeratori manfiy → `rah` **clamp 1.0** ga
  uriladi → `dT_hot` **11 K → 0.4 K** ga qulaydi (`c4 ≈ 0.016`, juda yumshoq).
- Natijada cropland `EF = 0.88`, `ET_24 = 6.48 mm/kun` (July) — OpenET'ga
  yaqinroq.

**Nega TUZATILMADI:** `z2_rah=2.0` (kanonik) qilinsa `dT_hot ≈ 8–11 K`,
`c4` ~20 baravar tikroq → cropland `H` keskin oshadi → `EF` pasayadi →
**ET yanada kamayadi**, OpenET 6-model konvertidan **uzoqlashadi**. Ya'ni
hozirgi nomuvofiq formula tasodifan advektsiyaga qisman kompensatsiya beryapti.
Iyul–sentyabr kamomadining haqiqiy sababi **advektsiya/oazis effekti**
(sug'orilgan maydonda `λE > Rn−G₀`, `EF > 1` kerak) — klassik SEBAL buni bera
olmaydi (`EF ≤ 1`). Bu STRUKTURA masalasi; to'g'ri yechim — `rah` ni kanonik
`2.0` ga qaytarish BILAN BIRGA advektsiyani manbali usulda qo'shish (masalan
METRIC hot-piksel `λE≠0` yoki hisoblangan-ammo-qo'llanilmagan `ADV_FACTOR`).
Shu ish qilinmaguncha `z2_rah=0.2` vaqtincha qoldirildi (foydalanuvchi qarori).

---

## O'zgartirishlar jurnali (2026-07 — bug-fix va yaxshilanishlar)

Ushbu bosqichda pipeline to'liq ishga tushirildi va bir qator crash, timeout,
nomuvofiqlik hamda sifat masalalari hal qilindi. Har bir o'zgarish quyida:
**nima → qayerda → nega** tarzida keltirilgan.

### A. Crash / to'xtash xatolari

1. **`SUN_ELEVATION` mozaikada saqlanadi**
   `preprocessing.py` → `_best_per_date_factory()`, `mosaic_by_date()`.
   `daily.mosaic()` metadatani yo'qotardi; `copyProperties(...)` ro'yxatiga
   `'SUN_ELEVATION'` qo'shildi. **Nega:** tile mozaikasidan keyin
   `radiation.py` `ee.Number(image.get('SUN_ELEVATION'))` = null → *"Number.multiply:
   left null"* crash berardi.

2. **`SUN_ELEVATION` topilmasa — ATAYLAB to'xtaydi (fake YO'Q)**
   `radiation.py` → `compute_incoming_shortwave()`.
   Landsat sahnada `SUN_ELEVATION` bo'lmasa script to'xtaydi (default qiymat
   ishlatilmaydi). HLS'da `SZA` bandi ishlatiladi — o'sha (discard qilinadigan)
   shoxga xavfsiz o'rin egasi beriladi. **Nega:** maqsad — ishonchli, yuqori
   sifatli natija; yetishmagan ma'lumotni yashirmaslik.

3. **Anchor persentil / stat `.get()` — null-xavfsiz**
   `energy_balance.py` → `_pn()`, `_safe_num()` va barcha metodlar.
   `reduceRegion(percentile)` bo'sh zonada (a) kalitni umuman qaytarmaydi yoki
   (b) kalitni null qiymat bilan qaytaradi — ikkovi ham `ee.Number(null)` →
   *"Image.constant: value null"* / *"Dictionary does not contain key"* crash
   berardi. Endi sentinel (`_HI/_LO`) bilan mask bo'sh bo'ladi (metod
   "topilmadi" deb keyingisiga o'tadi).

4. **Bitta-persentil kalit nomi tuzatildi**
   `energy_balance.py` → `_anchor_cimec()`, `_anchor_pysebal()`.
   `ee.Reducer.percentile([80])` (BITTA qiymat) natija kaliti — band nomi
   (`'NDVI'`), `'NDVI_p80'` EMAS (`_pXX` faqat 2+ persentilda qo'shiladi).

### B. Timeout (Computation timed out) — arxitektura

5. **Cropland: vektor → RASTER mask**
   `energy_balance.py` → `compute_tile_cropland_zone()`.
   Ilgari 791k cropland piksel `reduceToVectors()+dissolve()` bilan ulkan
   murakkab ko'pburchakka aylanardi; `reduceRegion` o'sha geometriyada
   *"Computation timed out"* berardi. Endi **raster mask** qaytariladi,
   `reduceRegion` oddiy `roi` to'rtburchak + `updateMask` bilan ishlaydi.

6. **Sezuvchan issiqlik H — IKKI SIKLLI hisob (asosiy timeout yechimi)**
   `energy_balance.py` → `compute_sensible_heat_flux()`, `_stability_scalar()`.
   **Muammo:** coupled per-piksel iteratsiya + har qadam `getInfo` → GEE hisob
   grafi to'planib borardi (natija cache'lanmaydi), 7–9-iteratsiyaga borib
   interaktiv compute limitidan oshardi.
   **Yechim (klassik SEBAL "hot-pixel calibration"):**
   - **(A) skalyar sikl** — hot-piksel skalyar kirishlarini BIR MARTA olib
     (yagona `getInfo`), iteratsiyani sof Python'da (server chaqiruvisiz)
     konvergensiyagacha aylantiradi → har qadam `c4_i, c5_i` va konvergent `N_A`.
   - **(B) raster sikl** — aynan `N_A` qadam, `c4_i` KONSTANTA sifatida inject
     qilinadi (embedded `reduceRegion` yo'q → yengil graf), ichida `getInfo` YO'Q.
   - **Oxirida BITTA `getInfo`** — yakuniy hot-piksel `dT/rah/H` va `N_A` print.
   Natija: timeout butunlay yo'qoldi. Validatsiya: eski coupled usul bilan ET
   farqi **MAE ≤ 0.03 mm/kun**, p95|Δ| ≤ 0.11 mm/kun (arzimas).

7. **Monin–Obukhov iteratsiyasiga DAMPING (konvergensiya)**
   `energy_balance.py` (A va B sikllarda).
   `ψm, ψh` (va `u*`) ketma-ket IKKI iteratsiya o'rtachasi bilan so'ndiriladi —
   "pendulum" tebranishini bartaraf qiladi. **Manba:** Dhungel et al. (2016),
   *J. Appl. Remote Sens.* 10(2), 026033, DOI: 10.1117/1.JRS.10.026033.

### C. Anchor tanlash — "beton" kaskad

8. **Ko'p-metodli anchor kaskadi + diagnostika**
   `config.py` (`ANCHOR_METHODS`, `ANCHOR_CASCADE`), `energy_balance.py`
   (`select_anchor_pixels` dispatcher, `_anchor_cimec/_plan_a/_plan_b/_pysebal`,
   `_finalize_anchor`), `main.py`/`run_sebal.py` (`anchor_method` parametri).
   Tanlangan metod birinchi sinaladi → qolganlari → avval ekin zonasida, keyin
   butun ROI'da → hech biri chiqmasa `default` persentil fallback (KAFOLAT).
   Har qadam log'da: qaysi metod, qaysi zona, `dT/ΔT` yoki nega topilmadi.
   **Nega:** avvalgi "anchor topilmadi → silent failure" cheklovini yopadi.

9. **Anchor persentillari `scale=30`** (original aniqlik)
   Kaskad va default persentil/median `reduceRegion`lari 30m'ga qaytarildi
   (piksel-sanoq tekshiruvlari 100/120'da qoldi — bular persentil emas).

### D. Rejim / konfiguratsiya nomuvofiqliklari

10. **ETPOT — hamma joyda ASCE-EWRI alfalfa**
    `et_decomposition.py` → `compute_all()` endi `ref_et.compute_reference_ets_daily()`
    ishlatadi (eski Penman-Monteith aerodinamik `compute_etpot()` chaqirilmaydi).
    **Nega:** kunlik `ETPOT_24` va oylik `ETPOT_MONTHLY` bir xil formula bo'lishi.
    (Bu ilgarigi "compute_etref referens ET" cheklovini ham to'g'irlaydi.)

11. **`maqola` rejimida ham `ETREF_24`/`KC`**
    `main.py` → `process_tile()` (else shoxi).
    S30 ETrF va VIIRS(kc) qatlamlari maqola rejimida ham crashsiz ishlashi uchun
    har sahnaga `ETREF_24` (ASCE-EWRI grass) va `KC` qo'shiladi.

12. **VIIRS 30m fine-grid CRS — sozlanadigan**
    `main.py` → `run()` (`viirs_crs` parametri), `viirs_downscaling.DCFG`.
    Ilgari hardcoded `'EPSG:32642'` (faqat O'zbekiston UTM) edi — boshqa hududda
    (Idaho) noto'g'ri natija berardi. Berilmasa asosiy `crs`ga tushadi.

### E. Tozalash

13. **O'lik `getInfo` bloki olib tashlandi**
    `energy_balance.py` — H-iteratsiyada hech narsa qilmaydigan, har qadam
    ortiqcha server so'rovi yuboradigan `anchor_check` bloki o'chirildi.

### Config o'zgarishlari (`config.py`)
- `ANCHOR_METHODS`, `ANCHOR_CASCADE` (yangi) — anchor kaskad sozlamalari.
- `ITERATION`: `max_iter` 8 → **15**; yangi `tol_rel = 0.01` (1% NISBIY
  konvergensiya — mutlaq 0.1K o'rniga masshtabdan mustaqil).

---

## O'zgartirishlar jurnali (2026-07 — Tasumi tezisiga blok-ma-blok moslashtirish)

Iyuldan boshlab SEBAL ET OpenET 6-model konvertidan pastga chiqa boshladi.
Sababni topish uchun pipeline **Tasumi (2003) tezisi**dagi SEBAL_ID formulalari
bilan blok-ma-blok solishtirildi (Surface roughness, LAI, emissivity, shamol,
`rah`, barqarorlik, radiatsiya, Monin–Obukhov `L`, 24-soatlik ET). Aniqlangan
farqlar quyida tuzatildi. **Muhim printsip:** har bir formula MANBAGA asoslangan
— o'zboshimcha "fake" fallback yo'q.

### F. Rejim nomi va yangi rejim tizimi

14. **`maqola` → `SEBAL_B` deb qayta nomlandi**
    `main.py`, `run_sebal.py` (`mode='SEBAL_B'` — eski `'maqola'`),
    `config.py` band ro'yxati `DAILY_BANDS_MAQOLA → DAILY_BANDS_SEBAL_B`.
    **Nega:** rejim aslida Bastiaanssen (SEBAL_B) formulasi — "maqola" nomi
    chalkash edi. `pysebal` rejimi o'zgarmadi.

15. **L↓ (kirish uzun to'lqin) — REJIMGA BOG'LIQ tizim**
    `radiation.py` → `compute_incoming_longwave(image, mode, roi, cold_mask)`,
    `compute_all(..., mode, roi, cold_mask)`.
    - `mode='yangiliklar'` → `L↓ = ERA5_STRD / 3600` (o'lchangan, o'zgarmadi —
      **comment/o'chirilmadi**, saqlab qolindi).
    - `mode ∈ {SEBAL_B, pysebal}` → empirik formula (Tasumi/Bastiaanssen):
      ```
      L↓ = 1.08 × σ × [−ln(τsw)]^0.265 × Tref⁴          [W/m²]
      ```
      bu yerda `Tref` — **cold anchor** yuzasi harorati (cropland p10 LST;
      cold_mask bo'lmasa ERA5 `AIR_TEMP` mediana zaxira). `τsw` ∈ [0.01, 0.99].
    **Nega:** SEBAL_B/pysebal fizik jihatdan yaxlit bo'lishi uchun L↓ ham
    yuzadan (Tref) chiqarilishi kerak; ERA5 STRD faqat `yangiliklar` rejimi
    variantida qoldirildi.

16. **Yashirin issiqlik λ — HARORATGA BOG'LIQ**
    `daily_et.py` (`compute_daily_et`, `compute_monthly_et`),
    `monthly_analytics.py` (`compute_monthly_et`, `compute_monthly_et_components`).
    Konstanta `λ = 2.45×10⁶` o'rniga (Tasumi Eq. 3.48):
    ```
    λ = (2.501 − 0.00236 × (LST − 273)) × 10⁶          [J/kg]
    ```
    Buning uchun interpolyatsiya band ro'yxatiga `LST` qo'shildi; `ET = EF ×
    Rn24 × 86400 / λ` endi har piksel haroratiga mos λ ishlatadi.
    **Nega:** issiq pikselda λ ~2% kichik → ET yuqoriroq; fizik jihatdan aniq.

### G. SEBAL_ID yuza parametrlari (Tasumi Table 4.11, Bastiaanssen liniyasi — METRIC EMAS)

17. **z₀m — endi LAI'dan, SAVI-exp EMAS**
    `surface_props.py` → `compute_z0m()`, `config.py` `Z0M_LAI_COEF=0.018`.
    ```
    z₀m = 0.018 × LAI          clamp(0.005, 1.0)        [SEBAL_ID]
    z₀h = z₀m / exp(2.3)
    ```
    Eski Gediz `exp(−5.809 + 5.62×SAVI)` ishlatilmaydi (konfigda zaxira sifatida
    qoldi). `z0m_min`: **0.0002 → 0.005** (Tasumi Table 4.11, agriculture).
    **Nega:** SEBAL_ID standarti; juda kichik z₀m `rah` log hadini beqaror
    qilardi.

18. **LAI — L=0.1 li SAVI'dan**
    `surface_props.py` → `compute_lai()`, `config.py` `SAVI_L_LAI=0.1`.
    ```
    SAVI(0.1) = 1.1 × (NIR−Red) / (NIR+Red+0.1)
    LAI = −ln((0.69 − SAVI) / 0.59) / 0.91             cap 6.0
    ```
    Ilgari umumiy `L=0.5` li SAVI ishlatilardi. `compute_all` tartibi: LAI
    z₀m'dan OLDIN hisoblanadi (z₀m=0.018·LAI unga bog'liq).
    **Nega:** SEBAL_ID LAI'ni L=0.1 li SAVI orqali aniqlaydi.

19. **Shamol ekstrapolyatsiyasi uchun ALOHIDA z₀m**
    `surface_props.py`, `config.py` `WIND_ROUGHNESS`.
    10→200m shamol uchun z₀m vegetatsiya balandligidan (momentum z₀m=0.018·LAI
    dan boshqa):
    ```
    h = h_max × (NDVI − 0.20) / (0.85 − 0.20)          h_max = 2.0m
    z₀m,wind = 0.123 × h                                [Brutsaert 1982]
    ```
    `u*` hisobida u_200 uchun `z₀m,wind`, ishqalanish uchun momentum z₀m
    (=0.018·LAI) ishlatiladi.

### H. rah va barqarorlik — IKKI XIL z₂

20. **`rah` va stability uchun z₂ AJRATILDI**
    `energy_balance.py` → `compute_rah_neutral`, `_stability_corrections`,
    `_stability_scalar`; `config.py` `WIND` (`z1=0.1`, `z2_rah=0.2`, `z2=2.0`).
    ```
    rah (log had):     z₁ = 0.1m,  z₂_rah = 0.2m  → rah = ln(0.2/0.1)/(u*·k)
    stability (ψ):     z₁ = 0.1m,  z₂     = 2.0m  (L<0 va L>0 uchun ham)
    ```
    **Nega:** avval ikkovi ham xato bir xil z₂ ga o'rnatilgan edi. Tasumi
    tezisida `rah` log hadi 0.1→0.2m oralig'ida, ψ tuzatmalari esa 0.1→2.0m
    oralig'ida hisoblanadi — bular BOSHQA-BOSHQA. Bu METRIC emas, SEBAL_B usuli.

### I. Ikki-zonali anchor land-cover

21. **Cold = cropland, Hot = bare+shrub (ekindan EMAS)**
    `config.py` `ANCHOR_LANDCOVER = {'cold': (40,), 'hot': (60, 20)}`,
    `energy_balance.py` → `compute_tile_anchor_zones()` (cold_mask, hot_mask).
    ```
    cold = 40 (Cropland)             — sug'orilgan, nam → λE≈max, H≈0
    hot  = 60 (Bare/sparse) + 20 (Shrubland) — doim quruq → λE≈0, H≈max
    ```
    **Nega:** iyul–sentyabr to'liq sug'orilgan mavsumda "eng issiq ekin" ham
    aslida transpiratsiya qiladi (July hot NDVI≈0.29, λE≠0) → `dT_hot` oshib
    ketardi → ET past baholanardi. Hot anchorni doim quruq yuzadan (bare/shrub)
    olish bu tizimli xatoni yopadi. (30 Grassland ATAYLAB kiritilmadi — Idaho'da
    sug'orilgan yaylov ham 30-klass bo'lishi mumkin.)

---

## O'zgartirishlar jurnali (2026-07 — aniqlik va sifat tuzatishlari)

Kod-audit davomida aniqlangan raqamli guard, crash va ishonchsiz maska
masalalari. Har biri **"fake qiymat quymaslik"** printsipiга muvofiq tuzatildi.

### J. Raqamli guardlar — soxta qiymat o'rniga maskalash

22. **EF maxraji: `max(10)` → `gt(0)` maska**
    `energy_balance.py` → `compute_evaporative_fraction()`.
    Oldин `rn_g0.max(10)` — `Rn−G₀` kичик/manfiy joyга **soxta 10** quyardi
    (EF past bias). Endi `updateMask(rn_g0.gt(0))` — nofizik (≤0) piksel
    **nodata** bo'ladi. Cropland'ga ta'sir ≈ nol (`Rn−G₀≈400–600 ≫ 0`); faqat
    bulut/suv/soya degenerat piksellar maskalanadi. **Diagnostika:** EF/H/dT/ET
    aynan o'zgarmadi (0.882 / 54.4 / 0.128 / 6.48).

23. **ψ (barqarorlik) clamp: ±10 → ±5**
    `energy_balance.py` → `_stability_scalar()` (skalyar) va
    `_stability_corrections()` (raster) — ikkovида ham.
    ±10 manbали emas edi (ortiqcha); fizik ψm/ψh kunduzi (beqaror) **~0–5** dan
    oshmaydi. ±5 — konservativroq guard, kunduzgi natijaга ta'siri deyarли nol.

### K. Correctness / crash

24. **L↓ Tref `getInfo` crash tuzatildi + fallback diagnostikasi**
    `radiation.py` → `compute_incoming_longwave()`; `main.py` → `process_tile()`.
    `tref.get('LST')` (`tref` = `ee.Number`, `.get` yo'q) `map()` trace'ида
    crash berardi; bundan tashqari `map()` **ICHIDA** `getInfo`/`print` bo'lmaydi.
    Endi: xom percentil alohида `tref_lst` o'zgaruvchисида; Tref manbai
    (LST p10 vs ERA5 AIR_TEMP fallback) **xususiyat** (`LDOWN_TREF_SRC`) sifatида
    yoziladi; `main.py` sahna sikli (map'дан tashqарида) uni o'qib
    `"L↓ Tref: … = … K"` deb print qiladi. **Nega:** fallback ishlаганини ko'rish
    + ikki-siklли dizaynning "map ичида getInfo yo'q" qoidасига rioya.

### L. Ishonchsiz maskani olib tashlash

25. **G₀ QOR maskasi olib tashlandi**
    `radiation.py` → `compute_soil_heat_flux()`.
    `is_snow = (LST<4°C) AND (albedo>0.45)` → `G/Rn=0.5` quyardi. Ammo **albedo
    ham, LST ham piksel darajасида shubhали** → ishonchsiz detektsiya, xato joyга
    0.5 quyish xavfi. Olib tashlandi; **SUV** (`NDVI<0` → 0.5) ishonchли belgi
    sifatида qoldi. `clamp(0.0, 0.6)` o'z joyида.

### M. Reference / diagnostika (pipeline'ga ta'sirsiz)

26. **`REGION_PRESETS` (config.py)** — hududга/ekinга bog'liq kalibratsiya
    parametrlari bir joyга yig'ildi (`idaho`, `turkey_gediz`). **FAQAT
    MA'LUMOTNOMA:** pipeline o'qimaydi, natija o'zgarmaydi (batafsil:
    "Hududга-bog'liq kalibratsiya" bo'limi).

27. **`z2_rah=0.2` diagnostikasi** "Ma'lum cheklovlar" bo'limига qo'shildi.
    Hot anchor sog'lom (ΔT=24.2K), lekin `rah` log hadi (`ln(0.2/0.1)`) kичик →
    `rah` clamp 1.0 ga uriladi → `dT_hot` 11K→0.4K. Kanonik `z2_rah=2.0` esa ET
    ni PASAYTIRАДИ (advektsiya sababли) — shu bois **hozircha 0.2 qoldirildi**.

---

## Manbalar

- Bastiaanssen, W.G.M. et al. (1998). *A remote sensing surface energy balance algorithm for land (SEBAL)*. Journal of Hydrology.
- Bastiaanssen, W.G.M. (2000). *SEBAL-based sensible and latent heat fluxes in the irrigated Gediz Basin, Turkey*. Journal of Hydrology.
- Allen, R.G., Tasumi, M., Trezza, R. (2007). *Satellite-Based Energy Balance for Mapping Evapotranspiration with Internalized Calibration (METRIC)*. ASCE J. Irrig. Drain. Eng.
- Tasumi, M. (2003). *Progress in Operational Estimation of Regional Evapotranspiration Using Satellite Imagery*. PhD dissertation, University of Idaho. — SEBAL_ID formulalari: z₀m=0.018·LAI, L=0.1 SAVI'dan LAI, empirik L↓, ikki-xil z₂ (rah 0.2m / stability 2.0m), harroratga bog'liq λ (Eq. 3.48), Table 4.11 z₀m_min.
- Brutsaert, W. (1982). *Evaporation into the Atmosphere*. — shamol z₀m = 0.123×h.
- Dhungel, R., Allen, R.G., Trezza, R., Kilic, A. (2016). *Improving iterative surface energy balance convergence for remote sensing based flux calculation*. J. Applied Remote Sensing 10(2), 026033. DOI: 10.1117/1.JRS.10.026033. — H-iteratsiya damping (ψ va u* o'rtachalash).
- Allen, R.G. et al. (1998). *Crop Evapotranspiration — FAO Irrigation and Drainage Paper 56*.
- Huete, A.R. (1988). *A soil-adjusted vegetation index (SAVI)*. Remote Sensing of Environment.
- Van de Griend, A.A., Owe, M. (1992). *On the relationship between thermal emissivity and NDVI*.
- Olmedo, G. et al. (2016). R `water` package — broadband albedo coefficients.
- Paulson, C.A. (1970); Webb, E.K. (1970) — atmosfera barqarorlik tuzatmalari.
- De Bruin, H.A.R. (1987) — 24-soatlik net radiatsiya empirik konstanta.

---

*Ushbu README loyihaning `D:\Cloud_comp\Sebal\scripts` bosqichidagi manba kodidan (`sebal_gee_v4/` moduli) to'g'ridan-to'g'ri chiqarilgan — barcha formula va konstantalar kod ichidan tasdiqlangan.*
