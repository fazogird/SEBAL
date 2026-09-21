# SEBAL-GEE v4 — bajarilgan tuzatishlar jurnali

Faqat kodda **haqiqatan bajarilgan** o'zgarishlar (oldin / keyin / GEE sinovi). Tekshiruvlar va takliflar — chatda.
Kod: `D:\Cloud_comp\Sebal\scripts\sebal_gee_v4`. Raqamlar suhbatdagi raqamlar bilan bir xil (tushib qolgan raqamlar — kod o'zgarmagan tekshiruvlar).

| # | Sana | Nima qilindi | Holat | Fayllar |
|---|---|---|---|---|
| 00 | 2026-09-17 | `tile_roi.geometry()` xato qatori olib tashlandi | ✅ commit 69d0ca4 | main.py |
| 01 | 2026-09-17 | `mosaic_same_date` / `best_per_date` → `_mosaic_same_date` (preprocessingdan keyin, UTM/property saqlanadi) | ✅ commit 22d96df | preprocessing.py, main.py |
| 04 | 2026-09-17 | `tiles` + `process_by_tile=False` → aniq `ValueError` | ✅ commit 22d96df | main.py |
| 06 | 2026-09-17 | Kolleksiya xronologik tartibi (`sort`) | ✅ commit 22d96df | preprocessing.py |
| 07 | 2026-09-17 | SAVI bitta marta, yagona `cfg.SAVI_L` | ✅ commit 22d96df | config.py, surface_props.py, hls_s30_etrf.py |
| 08 | 2026-09-17 | `info['scene_dates']` — sahna ↔ sana indeksi (VIIRS/S30) | ✅ commit 22d96df | main.py |
| 09 | 2026-09-17 | Raster export: verguldan keyin 2 xona (`EXPORT_DECIMALS`) | ✅ commit 22d96df | config.py, main.py |
| 10 | 2026-09-17 | Albedo `olmedo_brdf` — DEFAULT | ✅ commit 22d96df | config.py, surface_props.py, main.py |
| 11 | 2026-09-17 | SR_B1 scale → preprocessing (Landsat + HLS) | ✅ commit 22d96df | config.py, preprocessing.py, surface_props.py |
| 12 | 2026-09-17 | HLS cloud precheck `contains()` | ✅ commit 22d96df | preprocessing.py |
| 13 | 2026-09-17 | Z0M_WIND NDVI chegaralari: skalyar → sahna p20/p80 | ✅ commit 22d96df | config.py, surface_props.py, main.py |
| 14 | 2026-09-17 | Anchor zonalari: eng yaqin piksel → sinf ULUSHI (0.80 → 0.70 → 0.60 → ROI) | ✅ commit cd8d764 | config.py, energy_balance.py, main.py |
| 15 | 2026-09-17 | SMW LST: ERA5 TCWV vaqtga interpolyatsiya + TIRS10 K1/K2 sensor bo'yicha (L8 ≠ L9) | ✅ commit cd8d764 | config.py, radiation.py |
| 16 | 2026-09-17 | Empirik L↓ Tref = cold anchor LST (p10 va 293 K olib tashlandi); L↓ konstantalari mode bo'yicha | ✅ commit cd8d764 | config.py, radiation.py, energy_balance.py, main.py |
| 17 | 2026-09-18 | SEBAL_ID oilasi: anchor ETr topilmasa 0 emas — xato bilan to'xtaydi | ✅ commit cd8d764 | energy_balance.py |
| 18 | 2026-09-18 | pysebal anchor metodi: soxta default qiymatlar olib tashlandi; `_pn` 0 ni null deb olmaydi | ✅ commit cd8d764 | energy_balance.py |
| 19 | 2026-09-18 | G₀ suv: NDVI<0 YOKI QA suv biti (WATER_MASK) | ↪ #22 bilan almashtirildi | radiation.py, config.py |
| 20 | 2026-09-18 | G₀ koeffitsientlari config.SOIL_HEAT_FLUX dan | ✅ commit 0e170ab | radiation.py, config.py |
| 21 | 2026-09-18 | Anchor zona chegarasi: yagona cfg.ANCHOR['min_candidates'], ikkala joyda ≥ | ✅ commit 0e170ab | energy_balance.py, config.py |
| 22 | 2026-09-18 | G₀ suv: avval QA suv (WATER_MASK), bo'lmasa NDVI<0 | ✅ commit 0e170ab | radiation.py |
| 23 | 2026-09-18 | Anchor ΔT = hot−cold ≥ 5 K — barcha metodlarda (default ham), sababli xabar | ✅ commit 0e170ab | config.py, energy_balance.py, main.py |
| 24 | 2026-09-18 | Hot suv balansi: AYNAN anchor hot pikselida; tuproq xaritadan (OpenLandMap 33 kPa, HiHydroSoil pF4.2); boshlang'ich holatdan yaqinlashish (14→30→60 kun) | ✅ commit 0e170ab | water_balance.py, energy_balance.py, config.py |
| 25 | 2026-09-18 | Sahna fizik QC (H_hot > 0, dT_hot > dT_cold) → rad etish; ETrF_hot > 0.35 → ogohlantirish; sahna hisoboti + CSV; oyda yaroqli sahna qolmasa to'xtash | ✅ commit 0e170ab | energy_balance.py, main.py, config.py |
| 26 | 2026-09-18 | Anchor metodi DEFAULT = 'cimec' (cimec → plan_a → plan_b → pysebal → 'default' fallback) | ✅ commit 0e170ab | main.py, energy_balance.py |
| 27 | 2026-09-18 | Anchor skalyarlari BITTA rejimda (point → aynan anchor pikseli, median → nomzodlar mediani): u200/z0m/ρ, instant ETr, yakuniy tashxis, ANCHOR_*; anchor gridida | ✅ commit 0e170ab | energy_balance.py |
| 28 | 2026-09-18 | Point anchor DETERMINISTIK (teng LST'li piksellar) + anchor qiymatlari bir marta hisoblanadi (bitta sahnada bitta piksel) | ✅ commit 0e170ab | energy_balance.py, main.py |
| 29 | 2026-09-18 | SEBAL_ID oilasi: skalyar iteratsiya hot VA cold yaqinlashganda to'xtaydi | ✅ commit 0e170ab | energy_balance.py |
| 30 | 2026-09-18 | compute_sensible_heat_flux ichida ΔT himoyasi (T_hot − T_cold ≥ cfg.ANCHOR['min_dt']) | ✅ commit 0e170ab | energy_balance.py |
| 31 | 2026-09-19 | SEBAL_ID oilasi: hot nomzodlar FAQAT tuproq ma'lumoti (θ_FC, θ_WP, tekstura) bor piksellar; tuproq anchor gridida olinadi | ✅ commit 0e170ab | water_balance.py, energy_balance.py, main.py |
| 32 | 2026-09-19 | Ta = LST − dT ni ERA5 ± 15 K ga cheklash hisobdan olib tashlandi → faqat Ta QC diagnostikasi (CSV) | ✅ commit 0e170ab | energy_balance.py, main.py |
| 33 | 2026-09-19 | H ≥ −100 pastki chegarasi olib tashlandi (H ≤ Rn−G₀ qoladi) | ✅ commit 0e170ab | energy_balance.py |
| 34 | 2026-09-19 | SMW LST Landsat Tb gridida (LST, L_UP, DTA, G_RATIO — ERA5 0.25° emas, Landsat UTM 30 m) | ✅ commit 0e170ab | radiation.py |
| 35 | 2026-09-19 | LAI va EMISSIVITY (→ Z0M, Z0H) Landsat gridida (ee.Image(konstanta).where o'rniga Landsat band asos) | ✅ commit 0e170ab | surface_props.py |
| 36 | 2026-09-19 | Yagona tahlil gridi analysis_proj (Landsat NDVI) — barcha anchor va CSV reduksiyalarida crs aniq | ✅ commit 0e170ab | energy_balance.py, main.py |
| 37 | 2026-09-19 | Sahna QC: grid (6 band proyeksiyasi = Landsat gridi) + SMW TPW (min/max, klasslar soni) | ✅ commit 0e170ab | main.py, radiation.py |
| 38 | 2026-09-19 | Cold anchor Ta QC ogohlantirishi: \|Ta_cold − Ta_ERA5\| > 5 K (cfg.ANCHOR['cold_ta_warn']) | ✅ commit 3667e04 | config.py, energy_balance.py |
| 39 | 2026-09-19 | Konstanta asosli `where` (Kr ×2, sug'orish klassi) → Landsat band asos; CHIRPS yog'ini yo'q kun → xato (soxta P = 0 va unmask(0) olib tashlandi) | ✅ commit 3667e04 | water_balance.py, consumptive_use.py, ndvi_kc.py, root_zone_water.py, irrigation.py |
| 40 | 2026-09-19 | Anchor valid: cold_rn_g0 ham hot kabi tekshiriladi; cold → hot Rn−G₀ zaxirasi olib tashlandi | ✅ commit 3667e04 | energy_balance.py, main.py |
| 41 | 2026-09-19 | Rs24 (get_daily_solar_radiation): mahalliy kalendar kun — sana yarim tunga qirqiladi | ✅ commit 3667e04 | daily_et.py |
| 42 | 2026-09-19 | λ = (2.501 − 0.00236·(Ts − 273.15))·10⁶ — 273.0 → 273.15 | ✅ commit 3667e04 | daily_et.py, monthly_analytics.py |
| 43 | 2026-09-19 | ANCHOR_SCALE = 100 m — BARCHA rejimlarda (oldin ROI 30 m / CSV-tile 100 m) | ✅ commit 3667e04 | energy_balance.py, main.py |
| 44 | 2026-09-19 | point_anchor: default va pysebal (chegarasiz LST dumlari) — nomzodlarning eng chetdagi 5 % i tashlanadi | ✅ commit 3667e04 | energy_balance.py, config.py |
| 45 | 2026-09-19 | Anchor kaskadi: cimec → plan_a → plan_b → default → pysebal (default kaskad ichida); default zaxirasi LOGLANADI (QC); hech biri topmasa — sahna sababi bilan rad | ✅ commit 7efafb2 | energy_balance.py, main.py |
| 46 | 2026-09-19 | Anchor fizik QC'dan o'tmasa — kaskad KEYINGI metoddan davom etadi (metod/zona chetlanadi); urinishlar QC'ga yoziladi | ✅ commit 7efafb2 | main.py, energy_balance.py |
| 47 | 2026-09-19 | Kunlik Rn24: τ24 = Rs24/Ra24 (o'sha kun) — ochiq osmon TAU_SW o'rniga (SEBAL_B, pysebal, VIIRS); TAU_SW interpolyatsiyadan chiqarildi | ✅ commit 59372e2 | daily_et.py, monthly_analytics.py, viirs_downscaling.py, config.py |
| 48 | 2026-09-19 | Oylik: sahnaning vakillik davri — har piksel uchun vaqt bo'yicha eng yaqin YAROQLI sahna (SEBAL_B midpoint va mavsum o'rtachasi bilan to'ldirish olib tashlandi) | ✅ commit 59372e2 | daily_et.py, monthly_analytics.py |
| 49 | 2026-09-19 | Oylik QC: max_gap_days (> 8 kun ogohlantirish); n_landsat_scenes — shu oydagi sahnalar; pysebal Rs24 mahalliy kun; CSV oylik qatorlariga QC | ✅ commit 59372e2 | daily_et.py, monthly_analytics.py, main.py, config.py |
| 50 | 2026-09-19 | validate: har rejim o'z oylik usulida (oldin barcha rejimlar pysebal uslubida) | ✅ commit 59372e2 | main.py |
| 51 | 2026-09-19 | biomass APAR: Rs24 to'g'ridan-to'g'ri RS24 bandidan (Rn24 ni TAU_SW bilan teskari yechish olib tashlandi) | ✅ commit 59372e2 | biomass.py |
| 52 | 2026-09-19 | CSV sahna bandlari `csv_bands` dan (oldin qattiq yozilgan 20 band, `csv_bands` e'tiborsiz); yo'q band logda; bir bandli guruhda ustun nomi `<band>_mean` | ✅ commit 847f22e | main.py |
| 53 | 2026-09-19 | `run(csv_monthly=True)` — CSV oylik (MONTHLY_ET) alohida flag bilan (`export_monthly` faqat RASTER) | ✅ commit 847f22e | main.py, run_flux_validation.py |
| 54 | 2026-09-19 | Tayl xatosi yutilmaydi: turi+sababi qayd, kutilmagan xatoda traceback, run oxirida ro'yxat, natijada `status`/`failed_tiles`/`empty_tiles`/`tile_warnings`; flux-validatsiya "qisman" sanaydi | ✅ commit 847f22e | main.py, run_flux_validation.py |
| 55 | 2026-09-19 | VIIRS: Rs24 MAHALLIY kalendar kun (utc_offset) — oldin UTC kun (`ma._get_daily_rs24`) | ✅ commit 847f22e | viirs_downscaling.py, main.py |
| 56 | 2026-09-19 | ETr24 soatlik yig'indi: Ra/Rso davri SSRD bilan bir xil — ERA5 akkumulyativ yorliq T = [T−1, T] (oldin [T, T+1], 1 soat kechikkan) | ✅ commit qilinmagan | ref_et.py |
| 57 | 2026-09-19 | Instant ETr: Ra oynasi overpass markazida [t−0.5, t+0.5] (oldin butun soat [floor(t), floor(t)+1]) | ✅ commit qilinmagan | ref_et.py |
| 58 | 2026-09-19 | pysebal ETREF_24/ETPOT_24 (sahna + oylik): MAHALLIY kun + soatlik yig'indi (oldin UTC kun + kunlik-qadam) — boshqa rejimlar bilan bir xil | ✅ commit qilinmagan | ref_et.py, et_decomposition.py, main.py, monthly_analytics.py |
| 59 | 2026-09-19 | `get_daily_era5_aggregate`: sana yarim tunga qirqiladi (vaqtli sana berilsa oyna overpassdan boshlanmasin) | ✅ commit qilinmagan | ref_et.py |
| 60 | 2026-09-19 | pysebal oylik T/E: TACT = f_T·ET_kun (f_T = BENEFICIAL_FRACTION = TACT_24/ET_24), EACT = ET − TACT — mavsum o'rtacha RN24 bilan masshtab olib tashlandi (T + E = ET) | ✅ commit qilinmagan | monthly_analytics.py |
| 61 | 2026-09-19 | `run(sloping_terrain=False)` — qiya yuza sahna, oylik (barcha rejim, pysebal ham), CSV, CUirr, validate'ga uzatiladi; VIIRS/S30/Kc_ETo oylikda yo'qligi logda | ✅ commit qilinmagan | main.py, monthly_analytics.py |
| 62 | 2026-09-19 | SEBAL_Milliy qiya yuza: ET_24 = ET_inst·(Rs24/SSRD)·C_rad (kunlik, oylik, CUirr seriyasi) | ✅ commit qilinmagan | daily_et.py |
| 63 | 2026-09-19 | ETRF_RAW bandi (cheklanmagan ET_inst/ETr_inst) + QC: ekinzorda ETrF_raw > 1.10 ulushi > 1 % → ogohlantirish (Milliy 1.05 ga cheklanMAYDI — user qarori (b)) | ✅ commit qilinmagan | daily_et.py, main.py |
| 64 | 2026-09-19 | QC: C_RAD / RA24_RATIO [0.5, 2.0] chegarasidagi ROI piksellari > 1 % → ogohlantirish (ETrF24 qayta clamp QILINMAYDI) | ✅ commit qilinmagan | main.py |
| 65 | 2026-09-19 | VIIRS/S30: ALBEDO eng yaqin yaroqli sahna; kunlik ETREF bevosita (grass soatlik yig'indi, mahalliy kun) — proksi o'rniga; VIIRS target per-piksel vaqt to'ldirish; S30 utc_offset (#55 qoldig'i) | ✅ commit qilinmagan | viirs_downscaling.py, hls_s30_etrf.py |
| 66 | 2026-09-19 | S30 `interp_temporal_per_pixel`: `ee.Number − Image` runtime xatosi (S30 oylik HECH QACHON ishlamagan) → Image konstanta | ✅ commit qilinmagan | hls_s30_etrf.py |
| 67 | 2026-09-21 | O'lik kod olib tashlandi: `monthly_analytics._get_daily_rs24` (UTC kun Rs24), `_interpolate_bands` (midpoint + mavsum o'rtachasi) va uning izohdagi eski nusxasi; VIIRS'dagi ishlatilmaydigan `monthly_analytics` importi | ✅ commit qilinmagan | monthly_analytics.py, viirs_downscaling.py |

---

## #00 — `tile_roi.geometry().type().getInfo()` (main.py)

- **Oldin:** `main.py` da `tile_roi = roi.intersection(...)` dan keyin
  `tile_roi.geometry().type().getInfo()` qatori bor edi.
- **Muammo:** `ee.Geometry` da `.geometry()` metodi yo'q → `AttributeError` →
  `except` → `tile_roi = roi`. Natija: HAR tile o'z chegarasida emas, BUTUN ROI da
  hisoblanardi (logda "⚠️ Tile geometriya topilmadi → ROI ishlatiladi").
- **Keyin:** qator va izohi olib tashlandi. Commit `69d0ca4`.

---

## #01 — `mosaic_same_date` / `best_per_date`

### 1. Muammo

"Bir kunda tushgan tasvirlarni bitta tasvirga birlashtirish" kodda **ikki joyda, ikki nom bilan** yozilgan edi:

| | A blok: `best_per_date` | B blok: `mosaic_by_date` |
|---|---|---|
| Joyi (eski) | preprocessing.py 413-420 (Landsat), 362-369 (HLS) | preprocessing.py 434-452 |
| Qachon | TILE rejimi (`wrs_path` / `mgrs_tile` berilganda) | ROI rejimi (`mosaic_same_date=not bool(tile_label)`) |
| Preprocessingdan | OLDIN | KEYIN |

Kamchiliklar:
1. A blok tile rejimida **hech narsani birlashtirmasdi** (P155/R32, L8+L9, 2023-24: 82 tasvir = 82 unikal sana).
2. `ee.ImageCollection.mosaic()` natijasi (1 ta tasvirdan ham): proyeksiya **EPSG:32642 (UTM 30 m) → EPSG:4326 (1°)**, footprint **cheksiz**, property **94 → 7-8**.
3. A blok preprocessingdan OLDIN bo'lgani uchun `add_terrain()` DEM ni Landsat UTM gridiga emas, EPSG:4326 gridiga reproject qilardi → `add_terrain` izohidagi "DEM Landsat CRS da bo'lishi SHART — oldingi z₀m bug" himoyasi jimgina buzilardi, SLOPE o'zgarardi.
4. B blok ham proyeksiya/footprint/property ni yo'qotardi va 1 tasvirli sanalarda ham behuda mosaic qilardi.
5. `best_per_date` nomi chalg'ituvchi — "eng yaxshi" sahnani tanlamaydi, oddiy mosaic. Bitta mantiq ikki nusxada.

`distinct()` — tasvirlarni **o'chirmaydi**: sana MATNLARI ro'yxatidagi takrorlarni olib tashlaydi → unikal sanalar; keyin har sana uchun o'sha kunning barcha tasvirlari `mosaic()` qilinadi. Bu qism to'g'ri edi.

### 2. Oldin (commit 69d0ca4)

```python
# preprocessing.py — factory
def _best_per_date_factory(collection):
    def best_per_date(date_str):
        date = ee.Date(date_str)
        daily = collection.filterDate(date, date.advance(1, 'day'))
        actual_time = ee.Image(daily.first()).get('system:time_start')
        return (daily.mosaic()
                .set('system:time_start', actual_time)
                .copyProperties(daily.first(),
                                ['CLOUD_COVERAGE', 'CLOUD_COVER',
                                 'WRS_PATH', 'WRS_ROW', 'SUN_ELEVATION']))
    return best_per_date

# HLS — preprocessingdan OLDIN
        if mgrs_tile is not None:
            distinct_dates = (merged.aggregate_array('system:time_start')
                .map(lambda t: ee.Date(t).format('YYYY-MM-dd')).distinct())
            best_per_date = _best_per_date_factory(merged)
            merged = ee.ImageCollection(distinct_dates.map(best_per_date))
        ...
        clean_collection = merged.map(preprocess_hls)
        return clean_collection

# Landsat — preprocessingdan OLDIN (A blok)
    if wrs_path is not None:
        distinct_dates = (merged.aggregate_array('system:time_start')
            .map(lambda t: ee.Date(t).format('YYYY-MM-dd')).distinct())
        best_per_date = _best_per_date_factory(merged)
        merged = ee.ImageCollection(distinct_dates.map(best_per_date))

# Landsat — preprocessingdan KEYIN (B blok)
    if mosaic_same_date:
        distinct_dates = (clean_collection.aggregate_array('system:time_start')
                          .map(lambda t: ee.Date(t).format('YYYY-MM-dd')).distinct())
        def mosaic_by_date(date_str):
            date = ee.Date(date_str)
            daily = clean_collection.filterDate(date, date.advance(1, 'day'))
            actual_time = ee.Image(daily.first()).get('system:time_start')
            return (daily.mosaic()
                    .set('system:time_start', actual_time)
                    .copyProperties(daily.first(),
                                    ['CLOUD_COVERAGE', 'CLOUD_COVER', 'SUN_ELEVATION']))
        clean_collection = ee.ImageCollection(distinct_dates.map(mosaic_by_date))
```

```python
# main.py:170
        mosaic_same_date=not bool(tile_label),
```

### 3. Keyin — nima qilindi

**(a)** `_best_per_date_factory` **o'chirildi**. O'rniga bitta funksiya — `preprocessing.py` 311-353:

```python
def _mosaic_same_date(collection):
    dates = (collection.aggregate_array('system:time_start')
             .map(lambda t: ee.Date(t).format('YYYY-MM-dd'))
             .distinct())

    def per_date(date_str):
        date = ee.Date(date_str)
        daily = collection.filterDate(date, date.advance(1, 'day'))
        first = ee.Image(daily.first())
        merged = (daily.mosaic()
                  .setDefaultProjection(
                      first.select(cfg.BAND_NAMES['red']).projection())
                  .copyProperties(first)
                  .set({'system:time_start': first.get('system:time_start'),
                        'system:index': first.get('system:index'),
                        'system:footprint': daily.geometry()}))
        return ee.Algorithms.If(daily.size().gt(1), merged, first)

    return ee.ImageCollection(dates.map(per_date))
```

- sanada **1 ta** tasvir → **o'zgarishsiz** qaytadi (UTM, footprint, 94 property)
- sanada **>1** tasvir → mosaic; birinchi tasvirdan **tiklanadi**: UTM proyeksiya, BARCHA property, real UTC vaqt, footprint (kun tasvirlari birlashmasi)

**(b)** Landsat A blok (preprocessingdan OLDIN) — **o'chirildi**.
**(c)** HLS A blok — **o'chirildi**; o'rniga preprocessingdan KEYIN (`preprocessing.py` 398-399):
```python
        if mosaic_same_date:
            clean_collection = _mosaic_same_date(clean_collection)
```
**(d)** Landsat B blok → bitta chaqiruv (`preprocessing.py` 444-445), xuddi shunday.
**(e)** `main.py:170`:
```python
        mosaic_same_date=True,   # 1 tasvirli sanaga tegmaydi (tile rejimida ham xavfsiz)
```

Endi birlashtirish HAMMA rejimda FAQAT preprocessingdan KEYIN: QA mask har sahnaga alohida (overlap'da bulutli piksel ikkinchi sahnadan to'ldiriladi), DEM har sahnaning o'z UTM gridida, ERA5 har sahnaning o'z vaqtida.

**O'zgarmagan:** `build_collection()` imzosi; diag skriptlar (`mosaic_same_date=False`); filtrlar, cloud precheck, QA mask, scale factors, ERA5, ρₐ.

**Xulq-atvor o'zgarishi (HLS ROI rejimi):** oldin HLS ROI rejimida (mgrs_tile=None) umuman mosaic yo'q edi — nuqta 2 tile overlap'ida bo'lsa bir sanada 2 ta sahna qolardi (Qashqadaryo nuqtasi: T41SQD + T42STJ, 2023 da 85 sana). Endi bitta sanaga bitta tasvir.

### 4. GEE sinovi — oldin / keyin (haqiqiy `build_collection`)

Skript: `scratchpad/test_mosaic_after.py` (OLDIN = git HEAD 69d0ca4). Oraliq 2023-06-01..2023-09-01.

**(i) TILE rejimi — P155/R32, Samarqand (66.95E 39.65N, 5 km bufer), L8+L9**

| Ko'rsatkich | OLDIN | KEYIN |
|---|---|---|
| tasvir / sana | 11 / 11 | 11 / 11 |
| SR_B4 CRS / scale | EPSG:4326 / 111 319 m | EPSG:32642 / 30 m |
| DEM CRS | EPSG:4326 | EPSG:32642 |
| property soni | 8 | 94 |
| SPACECRAFT_ID / SUN_AZIMUTH | None / None | LANDSAT_9 / 132.03 |
| SUN_ELEVATION | 65.32 | 65.32 |
| footprint | Infinity | 36 651 km² |
| overpass vaqti | 06:10:45 | 06:10:45 |
| SR_B4 o'rtacha | 0.177450 | 0.177476 |
| LST o'rtacha | 316.301 K | 316.300 K |
| DEM o'rtacha | 716.76 m | 716.78 m |
| SLOPE o'rtacha | 3.588° | **3.445°** |

**(ii) ROI rejimi — 156/R31 + 156/R32 bir kunda (66.95E 40.45N, 30 km bufer), L8, sana 2023-07-02**

| Ko'rsatkich | OLDIN | KEYIN |
|---|---|---|
| tasvir / sana | 10 / 10 | 10 / 10 |
| SR_B4 / DEM CRS | EPSG:4326 | EPSG:32642 |
| property soni | 6 | 94 |
| footprint | Infinity | 73 102 km² |
| overpass vaqti | 06:16:41 | 06:16:41 |
| SR_B4 / LST o'rtacha | 0.182459 / 327.887 K | 0.182459 / 327.885 K |
| DEM, faqat sahna pikseli | 1005.04 m | 1005.39 m |
| SLOPE, faqat sahna pikseli | 12.593° | 12.593° |

- "Butun ROI" DEM o'rtachasi 866 → 792 m bo'lib ko'rinadi: OLDIN footprint cheksiz → DEM sahnadan TASHQARIDA ham hisoblanardi; KEYIN footprint sahna bilan cheklangan. Sahna ichida (SR/LST bor joyda) DEM/SLOPE bir xil. Tashqaridagi piksellar SEBAL da baribir maskalanadi.
- OLDIN EPSG:4326 30 m gridda piksel E-W bo'yicha 30·cos(lat) m → `reduceRegion` piksel SONI ~1/cos(40°) ≈ 1.32× ko'p (SR valid 1 597 840 vs 1 214 067). O'rtacha/persentilga ta'sir yo'q; piksel SONIGA tayanadigan chegaralar (`min_candidates`, "<20 valid piksel") endi haqiqiy piksel bo'yicha.

### 5. `best_per_date` — nima qilindi

- **O'chirildi** (factory ham). O'rniga `_mosaic_same_date()` — nomi qilgan ishiga mos.
- "Sifat" tomoni: eski funksiya hech qachon "eng yaxshi" sahnani tanlamagan. Yangi tartibda QA mask mosaic'dan OLDIN har sahnaga qo'llanadi → overlap'da bir sahnadagi bulutli piksel ikkinchisidan to'ldiriladi — bu haqiqiy sifat yutug'i.
- Bulut bo'yicha tartiblash (`sort('CLOUD_COVER')`) qo'shilmadi: bir o'tish sahnalari overlap'da amalda bir xil (156/31 vs 156/32: ST farqi 0.06 K, SR 0.00002).

### 6. Natijaga ta'sir

| Nima | Ta'sir |
|---|---|
| SR, LST, overpass vaqti, SUN_ELEVATION | o'zgarmaydi |
| DEM / SLOPE | Landsat UTM gridida (tile rejimi, Samarqand: SLOPE 3.59° → 3.44°) |
| anchor filtri (slope<5°) | nomzodlar biroz o'zgarishi mumkin |
| `sloping_terrain=True` | slope/aspect to'g'ri gridda |
| piksel sonlari | 4326 grid oshirishi (~1.32×) yo'qoldi |
| ROI bo'yicha ERA5 o'rtachalari (AIR_TEMP, RHO_AIR) | ROI rejimida endi ROI ∩ sahna maydonida |
| HLS ROI rejimi | overlap'da bir sanaga 1 tasvir (oldin 2) |
| Kunlik / oylik ET (mm) | **o'lchanmadi** (to'liq run kerak) |

---

## #04 — `tiles` + `process_by_tile=False` → aniq xato

- **Muammo:** `process_by_tile=False` bo'lsa `tiles` hech qayerga uzatilmasdi — ROI ga tekkan BARCHA path/row olinardi, ogohlantirishsiz.
- **User qarori:** B variant — xavfsizroq, skript aniq xato bilan to'xtaydi.

**Oldin** (`main.py` `run()` boshida hech qanday tekshiruv yo'q):
```python
    """
    roi = cfg.build_roi(roi_type, **roi_kwargs)
```

**Keyin** (`main.py` `run()` boshida, `build_roi` dan OLDIN — hech qanday GEE so'rovi ketmasdan):
```python
      tiles=[...],               process_by_tile=False → XATO (ValueError)
    """
    # tiles faqat tile rejimida ishlatiladi. ROI rejimida build_collection
    # filterBounds(roi) bilan ROI ga tekkan BARCHA path/row ni oladi — tiles
    # jimgina e'tiborsiz qolardi. Chalkashlik bo'lmasin: aniq to'xtatamiz.
    if tiles is not None and not process_by_tile:
        raise ValueError(
            f"tiles faqat process_by_tile=True bilan ishlaydi "
            f"(berildi: tiles={tiles}, process_by_tile=False). "
            f"Aniq tile'lar kerak → process_by_tile=True; "
            f"ROI ga tekkan barcha tile'lar kerak → tiles=None.")

    roi = cfg.build_roi(roi_type, **roi_kwargs)
```
(docstring'ga ham qator qo'shildi.)

**Sinov** (`scratchpad/test_tiles_guard.py`; `roi_type` ataylab noto'g'ri — tekshiruvdan o'tsa `build_roi` da to'xtaydi, hisob boshlanmaydi):

| Kombinatsiya | Natija |
|---|---|
| `tiles=[(156,31),(156,32)]`, `process_by_tile=False` | ✅ **guard to'xtatdi**: `ValueError: tiles faqat process_by_tile=True bilan ishlaydi ...` |
| `tiles=[(30,36)]`, `process_by_tile=True` | ✅ guard o'tkazdi (keyingi qadam: `roi_type '__yoq__' noto'g'ri`) |
| `tiles=None`, `process_by_tile=False` | ✅ guard o'tkazdi (keyingi qadam: `roi_type '__yoq__' noto'g'ri`) |

**Mavjud chaqiruvlarga ta'sir:** `run_sebal.py` dagi barcha `tiles=` chaqiruvlari (faol 477-478 va izohdagi 13 ta) `process_by_tile=True` bilan → hech biri buzilmaydi.

**Eslatma:** overlap'dagi nuqta uchun "ROI rejimi + aniq 2 row" endi to'g'ridan-to'g'ri qilinmaydi; ROI rejimi (`tiles=None`) ROI ga tekkan barcha row'larni oladi va bir sanadagilarini mosaic qiladi (#01).

---

## #06 — Kolleksiya xronologik tartibi (`sort('system:time_start')`)

`build_collection` kolleksiyani vaqt bo'yicha **saralamaydi**; `process_tile` `collection.toList()` tartibida aylanadi.

GEE sinovi (P155/R32, 2023-05..08, L8+L9) — `info['dates']` tartibi:
```
2023-05-08 L8, 05-24 L8, 06-09 L8, 07-11 L8, 07-27 L8, 08-12 L8, 08-28 L8,
2023-06-01 L9, 06-17 L9, 07-03 L9, 07-19 L9, 08-04 L9, 08-20 L9      → xronologik EMAS
```
Sabab: `merge(L8, L9)` avval barcha L8, keyin barcha L9. Natijaga ta'sir yo'q (interpolyatsiyalar o'zi saralaydi) — sahna sikli, log va kunlik export tartibi uchun.

**Bajarildi:** `preprocessing.py` `build_collection` — ikkala `return` (HLS va Landsat):
```python
# OLDIN
        return clean_collection            # HLS
    return clean_collection                # Landsat
# KEYIN
        return clean_collection.sort('system:time_start')
    return clean_collection.sort('system:time_start')
```
GEE sinovi (P155/R32, 2023-05..08): `2023-05-08, 05-24, 06-01, 06-09, 06-17, 07-03, 07-11, 07-19, 07-27, 08-04, 08-12, 08-20, 08-28` → **xronologik: True** (oldin avval L8 hammasi, keyin L9).

---

## #07 — SAVI bitta marta, yagona `cfg.SAVI_L`

Oldingi holat (SAVI ikki marta hisoblanardi):

| Nima | Qayerda | L | Natija | Kim ishlatadi |
|---|---|---|---|---|
| `compute_savi` → band `SAVI` | surface_props.py 60-79 | `cfg.ROUGHNESS['savi_L']` = **0.5** | band | **faqat export/diagnostika** (`main.py:588`, test skriptlar). Hisobda hech qayerda ishlatilmaydi |
| `compute_lai` ichida `SAVI_LAI` | surface_props.py 85-116 | `cfg.SAVI_L_LAI` = **0.1** | faqat LAI uchun (band emas) | LAI → z₀m (0.018·LAI), SEBAL_ID emissivity, energy_balance, et_decomposition, etrf_water_balance |
| S30 `SAVI` | hls_s30_etrf.py 125 | qattiq **0.5** | regressiya predictori | faqat `use_s30_etrf=True`, `s30_model='multi6'` |
| `REGION_PRESETS['idaho']['SAVI_L_LAI']` | config.py 625 | 0.1 | ma'lumot uchun, ulanmagan | — |

L ning LAI ga ta'siri (GEE, NDVI>0.5 piksellar, P155/R32, 5 km) — `config.SAVI_L` izohidagi ogohlantirish asosi:

| L | SAVI | LAI (bir xil formula) |
|---|---|---|
| 0.1 (hozirgi LAI) | 0.520 | **1.537** |
| 0.5 (hozirgi SAVI band) | 0.393 | 0.780 |
| 1.0 | 0.337 | 0.578 |

⚠️ LAI formulasi (0.69, 0.59, 0.91; chegaralar 0.1 / 0.687) ma'lum L uchun moslangan. L ni o'zgartirish LAI ni keskin o'zgartiradi (0.1 → 1.0 da −62%) → z₀m, emissivity, u*, rah, H, ET zanjiri o'zgaradi.

**Bajarildi:**

| Fayl | Oldin | Keyin |
|---|---|---|
| config.py | `ROUGHNESS['savi_L'] = 0.5` va `SAVI_L_LAI = 0.1` | **`SAVI_L = 0.1`** (yagona; izohda LAI ta'siri ogohlantirishi); eski ikki kalit o'chirildi |
| config.py REGION_PRESETS | `'SAVI_L_LAI': 0.1` | `'SAVI_L': 0.1` |
| surface_props.compute_savi | `L = cfg.ROUGHNESS['savi_L']  # 0.5` | `L = cfg.SAVI_L` |
| surface_props.compute_lai | SAVI ni L=0.1 bilan QAYTA hisoblardi (`SAVI_LAI`) | `savi = image.select('SAVI')` — qayta hisob yo'q |
| hls_s30_etrf.s30_indices | `(nir-red)*1.5 / (nir+red+0.5)` | `L = cfg.SAVI_L`; `(nir-red)*(1+L) / (nir+red+L)` |

`'SAVI'` band nomi saqlandi → `main.py` export ro'yxati va test skriptlar buzilmaydi. Loyihada `savi_L` / `SAVI_L_LAI` ga boshqa murojaat yo'q (grep).

GEE sinovi (`scratchpad/test_batch2.py`, P155/R32, 2023-05-08, 5 km; OLDIN = HEAD surface_props):

| Tekshiruv | Natija |
|---|---|
| L=0.1: LAI yangi − LAI oldin (max abs) | **0** |
| L=0.1: Z0M, EMISSIVITY farqi (max abs) | **0**, **0** |
| L=0.1: SAVI − qo'lda hisoblangan L=0.1 (max abs) | **0** |
| SAVI band o'rtacha | 0.151 (L=0.5, oldin) → **0.198** (L=0.1, endi) |
| L=1.0: SAVI va LAI − qo'lda (max abs) | **0**, **0** (o'rtacha SAVI 0.130, LAI 0.080) |
| L=1.0: S30 SAVI − qo'lda (max abs) | **0** |

---

## #08 — Sahna ↔ sana indeksi: `info['scene_dates']`

**Oldin** (`main.py`):
```python
    scene_images = []
    for i in range(n):
        ...
            continue   # anchor topilmadi → scene_images ga QO'SHILMAYDI (info['dates'] o'zgarmaydi)
        ...
        scene_images.append(img)
    info['utc_offset'] = utc_offset

    # _viirs_export_month va _s30_export_month:
    idx = [i for i, d in enumerate(info['dates']) if d[:7] == month_key]
    m_scenes = [scenes[i] for i in idx]
    m_info = {'dates': [info['dates'][i] for i in idx]}
```
**Keyin:**
```python
    scene_images = []
    scene_dates = []   # FAQAT saqlangan sahnalar sanasi (scene_images bilan indeksma-indeks)
    for i in range(n):
        ...
        scene_images.append(img)
        scene_dates.append(info['dates'][i])
    info['scene_dates'] = scene_dates
    info['utc_offset'] = utc_offset

    # _viirs_export_month va _s30_export_month:
    idx = [i for i, d in enumerate(info['scene_dates']) if d[:7] == month_key]
    m_scenes = [scenes[i] for i in idx]
    m_info = {'dates': [info['scene_dates'][i] for i in idx]}
```
- `viirs_downscaling.py` va `hls_s30_etrf.py` `m_info` ni oladi → ular ham to'g'ri juftlanadi (o'zgartirish shart emas).
- `info['dates']` (oylar ro'yxati uchun) o'zgarmadi → qaysi oylar export qilinishi o'zgarmaydi.

Sinov (Python simulyatsiya — 3 sahna, 06-17 anchor topilmay o'tkazildi):
```
OLDIN  2023-06: [('2023-06-01','IMG_06-01'), ('2023-06-17','IMG_07-03')]   <- noto'g'ri juft
OLDIN  2023-07: IndexError: list index out of range
KEYIN  2023-06: [('2023-06-01','IMG_06-01')]
KEYIN  2023-07: [('2023-07-03','IMG_07-03')]
```

---

## #09 — Raster export: verguldan keyin 2 xona

User: "2.45 yoki 3.13 — 2 ta son yetarli, uzun bo'lib ketmasin".

**config.py** (PIPELINE dan keyin, yangi):
```python
EXPORT_DECIMALS = 2
EXPORT_DECIMALS_BY_BAND = {}     # masalan {'EMISSIVITY': 4, 'Z0M': 4, 'ALBEDO': 3, 'TAU_SW': 3}
```
**main.py** — yangi `_round_export(img)`: `x*10^d → round → /10^d → float32`; override bo'lsa band bo'yicha. FAQAT eksport nusxasi — oraliq hisob to'liq aniqlikda.

6 ta raster export nuqtasi:

| Qator (yangi) | Oldin | Keyin |
|---|---|---|
| 351 kunlik | `img.select(existing_bands).toFloat()` | `_round_export(img.select(existing_bands))` |
| 397 VIIRS oylik | `monthly.toFloat()` | `_round_export(monthly)` |
| 442 S30 oylik | `monthly.toFloat()` | `_round_export(monthly)` |
| 566 ET+CU/AW | `combined.select(out_bands).toFloat().clip(roi)` | `_round_export(combined.select(out_bands)).clip(roi)` |
| 591 oylik mahsulot | `prod_image.toFloat().clip(roi)` | `_round_export(prod_image).clip(roi)` |
| 1450 polygon oylik | `img.toFloat()` | `_round_export(img)` |

CSV (table) exportlar o'zgarmadi.

GEE sinovi (bitta nuqta, P155/R32, 2023-05-08):

| Band | Asl | `EXPORT_DECIMALS=2` | override {EMISSIVITY:4, Z0M:4} |
|---|---|---|---|
| ALBEDO | 0.159597 | 0.16 | 0.16 |
| NDVI | 0.266007 | 0.27 | 0.27 |
| LST | 306.70059 | 306.70 | 306.70 |
| LAI | 0.290160 | 0.29 | 0.29 |
| EMISSIVITY | 0.952902 | **0.95** | 0.9529 |
| Z0M | 0.005223 | **0.01** | 0.0052 |

Band nomlari va tartibi saqlanadi, tur float32 (float32 da 0.16 = 0.1599999964 — format tabiati, GIS 0.16 ko'rsatadi).

Diqqat — 2 xonada ma'lumot yo'qolishi (5 km, noyob qiymatlar soni):

| Band | Asl | 2 xona | Izoh |
|---|---|---|---|
| ALBEDO | 72 141 | 67 | 0.01 qadam |
| EMISSIVITY | 57 640 | **5** | diapazon 0.95–0.985 → faqat 0.95…0.99 |
| Z0M | 22 636 | **11** | min 0.005 → **0.01** (2x xato) |

Faqat EKSPORT qilingan rasterlarga ta'sir qiladi; ET hisobiga emas. Kerak bo'lsa `EXPORT_DECIMALS_BY_BAND` bilan oshiriladi (default bo'sh — user qarori).

---

## #10 — Albedo `olmedo_brdf` (DEFAULT)

User qarori:
```
α       = 0.246·B + 0.146·G + 0.191·R + 0.304·NIR + 0.105·SWIR1 + 0.008·SWIR2
α_final = α − (0.001464 · θ_elev − 0.079103)
```
Koeffitsientlar = mavjud `cfg.OLMEDO_COEFFICIENTS` ('config' usuli) — faqat BRDF tuzatishi qo'shildi.

| Fayl | Oldin | Keyin |
|---|---|---|
| config.py | — | `ALBEDO_BRDF = {'slope': 0.001464, 'intercept': 0.079103}` |
| surface_props.py | `ALBEDO_METHOD = 'config'` | `ALBEDO_METHOD = 'olmedo_brdf'` |
| surface_props.py | — | `_sun_elevation(image)`: Landsat `SUN_ELEVATION` (sahna), HLS `90 − SZA`; yo'q bo'lsa **to'xtaydi** |
| surface_props._albedo_variants | 5 usul | + `olmedo_brdf` → diag band `ALB_OLMEDO_BRDF` |
| main.run | `albedo_method='config'`; faqat farqli bo'lsa print | `albedo_method='olmedo_brdf'`; har doim print |
| main.py CSV band ro'yxati | `ALB_OLMEDO, ALB_LIANG, ...` | `ALB_OLMEDO_BRDF, ALB_OLMEDO, ALB_LIANG, ...` |

`'config'` usuli saqlandi (`albedo_method='config'` → eski natija). `run_sebal.py` va boshqa skriptlar `albedo_method` bermaydi → yangi default qo'llanadi.

Yangi kod:
```python
def _sun_elevation(image):
    has_sza = image.bandNames().contains('SZA')
    return ee.Image(ee.Algorithms.If(
        has_sza,
        ee.Image(90).subtract(image.select('SZA')),
        ee.Image.constant(ee.Number(image.get('SUN_ELEVATION')))
    )).rename('SUN_ELEV')

# _albedo_variants ichida:
    oc = cfg.OLMEDO_COEFFICIENTS
    a_olmedo_cfg = (b*oc['SR_B2'] + g*oc['SR_B3'] + r*oc['SR_B4']
                    + nir*oc['SR_B5'] + s1*oc['SR_B6'] + s2*oc['SR_B7'])
    brdf = _sun_elevation(image)*slope - intercept
    a_olmedo_brdf = a_olmedo_cfg - brdf
```

GEE sinovi (P155/R32, 2023-05-08, SUN_ELEVATION = 61.368°, 5 km):

| Tekshiruv | Natija |
|---|---|
| Kutilgan farq −(0.001464·61.368 − 0.079103) | −0.010739 |
| ALBEDO o'rtacha: oldin ('config') → keyin | 0.185211 → **0.174472** (farq −0.010739 ✅) |
| ALBEDO − ALB_OLMEDO_BRDF (max abs) | **0** |
| SUN_ELEVATION yo'q (property'siz rasm) | **to'xtadi** ✅ `Image.constant: Parameter 'value' is required and may not be null` |
| HLS 90−SZA (2023-06-01, 65.8E 38.9N) | SZA 24.53° → θ_elev **65.47°** (Landsat SUN_ELEVATION 66.05°) → SZA gradusda ✅ |

Tuzatish kattaligi: θ_elev 30° → +0.035; 54° → 0; 61° → −0.011; 70° → −0.024 (yozda albedo pasayadi, qishda oshadi).

---

## #11 — SR_B1 (coastal) scale → preprocessing (Landsat + HLS)

User: "SR_B1 ni barcha rasterlar tuzatiladigan joyga qo'yish kerak va o'sha yerdan chaqirish kerak (preprocessing.py)"; "HLS L30 va Landsat 8/9 B1 bir xilmi — HLS da ham hisoblasin".

### HLS L30 B1 va Landsat 8/9 SR_B1 bir xilmi?

Bir xil OLI coastal aerosol bandi (0.43–0.45 µm). HLS L30: yuzaki reflektans + BRDF (nadir) normalizatsiya, MGRS 30 m gridi; GEE da **allaqachon reflektans** (double, −3.2768…3.2767 = int16 × 0.0001) — Landsat C2L2 kabi DN emas.

GEE sinovi (65.8E 38.9N, 1.5 km, ikkala mahsulotda ham toza piksel):

| Sana | Band | C2L2 SR | HLS L30 | HLS − C2 |
|---|---|---|---|---|
| 2023-05-31 | B1 | 0.0916 | 0.0935 | +0.0019 |
| 2023-05-31 | B5 | 0.3186 | 0.3254 | +0.0068 |
| 2023-06-01 | B1 | 0.0999 | 0.0972 | −0.0026 |
| 2023-06-01 | B5 | 0.3429 | 0.3336 | −0.0093 |
| 2023-06-08 | B1 | 0.0943 | 0.0965 | +0.0021 |
| 2023-06-16 | B1 | 0.0937 | 0.0957 | +0.0020 |

B1 farqi ±0.002–0.003 (~2–3 %), B2–B7 bilan bir xil belgi va naqsh (BRDF normalizatsiyasi, path'ga qarab + yoki −) → B1 ni HLS da ishlatish to'g'ri.

### Oldin
```python
# config.py BAND_NAMES — 'coastal' yo'q
# preprocessing.apply_scale_factors: sr_bands = [blue, green, red, nir, swir1, swir2]   (SR_B1 xom DN qolardi)
# preprocessing.apply_scale_factors_hls:
    sr = (image.select(['B2','B3','B4','B5','B6','B7'])
          .rename(['SR_B2','SR_B3','SR_B4','SR_B5','SR_B6','SR_B7']).clamp(0.001, 1.0))
# surface_props._albedo_variants:
    ub = (image.select('SR_B1').multiply(cfg.SCALE_FACTORS['sr_mult'])
          .add(cfg.SCALE_FACTORS['sr_add']).clamp(-0.199972, 1.602213))
```
### Keyin
```python
# config.py
BAND_NAMES     = {'coastal': 'SR_B1', 'blue': 'SR_B2', ...}
HLS_BAND_NAMES = {'coastal': 'B1',    'blue': 'B2',    ...}
# preprocessing.apply_scale_factors:
    sr_bands = [cfg.BAND_NAMES['coastal'], blue, green, red, nir, swir1, swir2]   # hammasi bir xil scale+clamp
# preprocessing.apply_scale_factors_hls:
    sr = (image.select(['B1','B2','B3','B4','B5','B6','B7'])
          .rename(['SR_B1','SR_B2','SR_B3','SR_B4','SR_B5','SR_B6','SR_B7']).clamp(0.001, 1.0))
# surface_props._albedo_variants:
    ub = image.select(cfg.BAND_NAMES['coastal'])      # tayyor reflektans, qayta scale YO'Q
```
HLS clamp (0.001, 1.0) — mavjud HLS konvensiyasi, B1 ham shunga kirdi. Landsat SR_B1 — boshqa SR bandlari bilan bir xil C2 diapazoni (−0.199972, 1.602213).

### GEE sinovi

**Landsat** (L9 2023-06-01, 1.5 km) — OLDIN (HEAD preprocessing + surface_props) vs KEYIN:

| Tekshiruv | Natija |
|---|---|
| SR_B1 o'rtacha | oldin **10903.9** (xom DN) → keyin **0.0999** (reflektans, float32) |
| ALB_OLMEDO, ALB_LIANG, ALB_TASUMI max abs farq | 0, 0, 0 |
| ALB_KE, ALB_AVG3 max abs farq | 9.7e-10, 3.2e-10 (float32 yuvarlash — amalda 0) |

**HLS** (T41SQD 2023-06-01, to'liq preprocessing zanjiri + `compute_all`) — endi **ishlaydi**; bir xil sana Landsat 9 bilan (ikkalasida toza piksel):

| Band | HLS L30 | Landsat 9 | farq |
|---|---|---|---|
| SR_B1 | 0.0972 | 0.0999 | −0.0026 |
| ALBEDO (= ALB_OLMEDO_BRDF) | 0.2142 | 0.2198 | −0.0056 |
| ALB_OLMEDO | 0.2072 | 0.2116 | −0.0044 |
| ALB_LIANG | 0.2384 | 0.2450 | −0.0066 |
| ALB_KE | 0.2273 | 0.2336 | −0.0063 |
| ALB_TASUMI | 0.1946 | 0.2001 | −0.0055 |
| ALB_AVG3 | 0.2243 | 0.2301 | −0.0058 |
| θ_elev | 65.47° (90−SZA) | 66.05° (SUN_ELEVATION) | |

HLS albedo Landsat dan 0.004–0.007 past — SR farqi (BRDF normalizatsiya) bilan izchil.

Eslatma: bu sinovda HLS `build_collection` sahnani cloud precheck xatosi tufayli rad etdi (#12 da tuzatildi); shuning uchun HLS preprocessing zanjiri qo'lda chaqirildi.

---

## #12 — HLS cloud precheck: toza (0 %) sahna 100 % bo'lib qolardi → `contains()`

**Oldin** (`preprocessing.add_crop_cloud_pct_hls`):
```python
    crop_cloud_pct = crop_bad.reduceRegion(...).get('Fmask')
    crop_cloud_pct = ee.Number(
        ee.Algorithms.If(crop_cloud_pct, crop_cloud_pct, 1)     # 0 → "yo'q" → 1 → 100%
    )
```
**Keyin:**
```python
    d = crop_bad.reduceRegion(...)
    # contains() bilan — Landsat add_crop_cloud_pct kabi. Kalit yoki qiymat yo'q → 1 (100%).
    crop_cloud_pct = ee.Number(ee.Algorithms.If(
        d.contains('Fmask'),
        ee.Algorithms.If(ee.Algorithms.IsEqual(d.get('Fmask'), None), 1, d.get('Fmask')),
        1))
```

GEE sinovi (HLSL30 T41SQD, 65.8E 38.9N, 3 km):

| Holat | Oldin | Keyin |
|---|---|---|
| Toza sahna 2023-06-01 (CLOUD_COVERAGE=0) | crop_cloud_pct = **100** → skip | **0** ✅ |
| `build_collection(satellite='HLS', mgrs_tile='T41SQD')` 2023-06-01 | 0 tasvir | **1 tasvir** ✅ |
| Bulutli sahna (CLOUD_COVERAGE=66) | — | 1.98 (3 km ekin ustida — son qaytadi, 1 ga tushib ketmaydi) |

---

## #13 — Z0M_WIND: NDVI min/max skalyar → sahna p20 / p80

User qarori: "sahna uchun p20 va p80 min va max — realroq; min 0 bo'lib ketmasin". NDVI o'zi o'zgarmaydi (clamp ±1 — metodologiya).

**Oldin** (`config.WIND_ROUGHNESS`, `surface_props.compute_z0m(image)`):
```python
WIND_ROUGHNESS = {'z0m_coef': 0.123, 'h_max': 2.0,
                  'ndvi_min': 0.20, 'ndvi_max': 0.85, 'z0m_min': 0.001}

    h = (ndvi.subtract(wc['ndvi_min'])
         .divide(wc['ndvi_max'] - wc['ndvi_min'])
         .clamp(0.0, 1.0).multiply(wc['h_max']))
    z0m_wind = h.multiply(wc['z0m_coef']).max(wc['z0m_min']).rename('Z0M_WIND')
```
**Keyin:**
```python
WIND_ROUGHNESS = {
    'z0m_coef': 0.123, 'h_max': 2.0,
    'ndvi_pct_min': 20,        # NDVI_min = sahna p20
    'ndvi_pct_max': 80,        # NDVI_max = sahna p80
    'ndvi_min_floor': 0.05,    # NDVI_min bundan past bo'lmaydi (0 ga tushib ketmasin)
    'ndvi_min_span': 0.10,     # NDVI_max ≥ NDVI_min + 0.10 (0 ga bo'lishdan himoya)
    'pct_scale': 100,          # persentil masshtabi (m)
    'z0m_min': 0.001,
}

def compute_z0m(image, roi=None):
    ...
    region = roi if roi is not None else image.geometry()
    pct = ndvi.reduceRegion(ee.Reducer.percentile([p_lo, p_hi]), region,
                            wc['pct_scale'], maxPixels=1e9, bestEffort=True, tileScale=4)
    ndvi_lo = ee.Number(pct.get(f'NDVI_p{p_lo}')).max(wc['ndvi_min_floor'])
    ndvi_hi = ee.Number(pct.get(f'NDVI_p{p_hi}')).max(ndvi_lo.add(wc['ndvi_min_span']))
    h = ndvi.subtract(ndvi_lo).divide(ndvi_hi.subtract(ndvi_lo)).clamp(0, 1).multiply(wc['h_max'])
    z0m_wind = h.multiply(wc['z0m_coef']).max(wc['z0m_min']).rename('Z0M_WIND')
    return (image.addBands(z0m).addBands(z0h).addBands(z0m_wind)
            .set({'Z0MW_NDVI_MIN': ndvi_lo, 'Z0MW_NDVI_MAX': ndvi_hi}))
```
- `surface_props.compute_all(image, mode, roi=None)` → `compute_z0m(image, roi)`.
- `main.py` `process_tile`: `surface_props.compute_all(im, mode, roi)` — persentil **ishlov hududi** (tile_roi yoki ROI) bo'yicha.
- Sahnada NDVI yo'q bo'lsa (null) GEE xato beradi — soxta qiymat yo'q.
- `REGION_PRESETS`: `wind_ndvi_min/max` → `wind_ndvi_pct: (20, 80)` (ma'lumotnoma).
- `Z0M` (u* uchun, 0.018·LAI) o'zgarmadi — faqat `Z0M_WIND` (ERA5 10 m → 200 m shamol).

GEE sinovi (`scratchpad/test_z0m_p20p80.py`, P155/R32, Samarqand 20 km, haqiqiy `compute_all`; OLDIN = skalyar 0.20/0.85 formulasi):

| Sana | NDVI_min (p20) | NDVI_max (p80) | z0 p50 oldin → keyin | h_max ga yetgan piksel oldin → keyin | u200/u10 p50 oldin → keyin | NDVI=0.40 piksel z0 oldin → keyin |
|---|---|---|---|---|---|---|
| 2023-03-21 | 0.160 | 0.559 | 0.050 → **0.107** | 2.3 % → **21.3 %** | 1.565 → 1.659 | 0.076 → 0.148 |
| 2023-07-11 | 0.168 | 0.512 | 0.035 → **0.089** | 0.1 % → **21.8 %** | 1.530 → 1.634 | 0.076 → 0.166 |
| 2023-10-15 | 0.164 | 0.429 | 0.029 → **0.103** | 0.1 % → **22.7 %** | 1.511 → 1.653 | 0.076 → 0.219 |

`roi=None` (butun tasvir footprint'i) bilan persentillar boshqacha: mart 0.180/0.539, iyul 0.133/0.383, oktabr 0.118/0.320 — natija persentil hisoblanadigan hududga bog'liq.

---

## #14 — Anchor zonalari: eng yaqin piksel → sinf ULUSHI (0.80 → 0.70 → 0.60 → ROI)

User qarori: "categorical mask → fractional purity mask; cold ≥ 0.80, hot ≥ 0.80; nomzod yetmasa 0.70 → 0.60 → ROI fallback".

**Muammo (oldin):** 10 m WorldCover 0/1 maskasi anchor masshtabida (30 / 100 m) eng yaqin piksel bilan olinardi. Samarqand 30 km, GEE:

| Zona | Masshtab | Zona piksellarida haqiqiy sinf ulushi (o'rt.) | Ulushi < 50 % bo'lganlar |
|---|---|---|---|
| cold (40) | 100 m | 0.87 | 8.0 % |
| hot (60+20) | 100 m | **0.62** | **36.4 %** |

**Oldin** (`energy_balance.py`):
```python
def compute_tile_anchor_zones(tile_roi, min_pixel_count=20):
    cold_r = _landcover_mask(cfg.ANCHOR_LANDCOVER['cold'])      # 10 m 0/1
    hot_r = _landcover_mask(cfg.ANCHOR_LANDCOVER['hot'])
    ...
    cold_mask = cold_r.selfMask().rename('COLD_LC') if cold_px >= min_pixel_count else None

# _select_anchor_default ichida:
    def _zone_base(lc):
        b = base_flat.And(lc.gt(0))                               # nearest sampling
        px = ... reduceRegion(sum, roi, 100) ...
        return ee.Image(ee.Algorithms.If(px.gt(20), b, base_flat))
# select_anchor_pixels (kaskad): cold_base = base_flat.And(cold_mask.gt(0))
```
**Keyin:**
```python
# config.py
ANCHOR_LANDCOVER = {'cold': (40,), 'hot': (60, 20),
                    'purity_steps': (0.80, 0.70, 0.60), 'min_pixels': 20}

# energy_balance.py
def _landcover_fraction(classes, proj):          # 10 m 0/1 → reduceResolution(mean) → UTM @ANCHOR_SCALE
    return (_landcover_mask(classes).toFloat()
            .reduceResolution(ee.Reducer.mean(), maxPixels=1024).reproject(proj))

def compute_tile_anchor_zones(tile_roi, min_pixel_count=None):
    # → (cold_zone, hot_zone): ulush rasmlari 'COLD_FRAC'/'HOT_FRAC' (0..1)
    # tile darajasida har bosqich (≥0.80/0.70/0.60) piksel soni print qilinadi

def _purity_zones(base_flat, cold_zone, hot_zone, roi):
    # sahna uchun: base_flat ∧ ulush≥0.80 soni > min_pixels ? → 0.70 → 0.60 → ROI
    # chegara BIR getInfo bilan client-side tanlanadi (keyingi so'rov grafiga If kirmaydi)
    return cold_base, cold_thr, hot_base, hot_thr     # thr float, 0.0 = ROI
```
- `_select_anchor_default` va kaskad (`select_anchor_pixels`) ikkalasi ham `_purity_zones` dan foydalanadi.
- Anchor dict'ga `cold_zone_purity` / `hot_zone_purity` qo'shildi; `main.py` har sahnada chiqaradi: `anchor zona: cold ulush ≥0.80 | hot ulush ≥0.80` (ROI bo'lsa "ROI (zona yetmadi)").
- Argument nomlari: `cold_mask/hot_mask` → `cold_zone/hot_zone` (`select_anchor_pixels`, `energy_balance.compute_all`, `main.py`).
- Ulush rasmi grid'i: ROI markazining UTM zonasi, `ANCHOR_SCALE` (30 yoki 100 m).

GEE sinovi — tile darajasida piksel soni:

| Hudud | Zona | Oldin (nearest 0/1) | ≥0.80 | ≥0.70 | ≥0.60 |
|---|---|---|---|---|---|
| Samarqand 30 km @100 m | cold | 185 911 | 106 217 | 118 390 | 129 821 |
| Samarqand 30 km @100 m | hot | 7 844 | 1 812 | 2 494 | 3 343 |
| Butun tile P155/R32 @100 m | cold | — | 611 322 | 675 761 | 735 714 |
| Butun tile P155/R32 @100 m | hot | — | 38 544 | 54 790 | 74 168 |

Tile zonasini hisoblash vaqti: 30 km @100 m 7 s, @30 m 5 s, butun tile @100 m 31 s (tile uchun bir marta). End-to-end sinovlarda (Samarqand 20 km, 2023-07, 3 sahna, barcha rejim) har sahnada cold va hot zona **≥ 0.80** bilan topildi.

---

## #15 — SMW LST: ERA5 TCWV vaqtga interpolyatsiya + TIRS10 K1/K2 sensor bo'yicha

**Muammo (oldin):**
1. `filterDate(t−1h, t+1h).first()` — eng yaqin soat emas, doim `floor(t)` soati. Overpass daqiqalari (GEE, 2023): Samarqand :11, Buxoro :17–:23, Toshkent :04, Bushland :20–:26 → tasodifan eng yaqin; **Xorazm :35 / :41, Farg'ona–Andijon :52 → eng yaqin EMAS** (52 daqiqa uzoq soat). Bushland 2021-07-09 da TPW bin almashib, LST −0.26 K (max −1.74 K).
2. Planck K1/K2 har ikki sensorga L8 qiymati (774.8853, 1321.0789). L9 metadata: K1 = 799.0284, K2 = 1329.2405 → L9 da Tb +0.13…+0.33 K issiq.
Ikkala muammo `add_lst_footprint_diagnostics` (WATER_VAPOR) da ham bor edi (TCWV).

**Oldin** (`radiation.py`):
```python
_TIRS10_K1, _TIRS10_K2 = 774.8853, 1321.0789
...
    tb = l10.expression('K2 / log(K1 / L + 1.0)', {'K1': _TIRS10_K1, 'K2': _TIRS10_K2, 'L': l10})
    tcwv = (ee.ImageCollection('ECMWF/ERA5/HOURLY').select('total_column_water_vapour')
            .filterDate(t.advance(-1, 'hour'), t.advance(1, 'hour')).first())
    tpw_cm = ee.Image(tcwv).divide(10.0)
```
**Keyin:**
```python
# config.py
TIRS10_PLANCK = {'LANDSAT_8': (774.8853, 1321.0789), 'LANDSAT_9': (799.0284, 1329.2405)}

# radiation.py
def _era5_tcwv_cm(image):      # instant o'zgaruvchi: floor(t) va floor(t)+1 soat, og'irlik = kasr qism
    ...
    tcwv = _at(h0).multiply(1 - w).add(_at(h0 + 1).multiply(w))
    return tcwv.divide(10.0)

def _tirs10_planck(image):     # SPACECRAFT_ID bo'yicha; ro'yxatda yo'q / property yo'q → GEE xato
    kk = ee.List(ee.Dictionary(cfg.TIRS10_PLANCK).get(image.get('SPACECRAFT_ID')))

# compute_lst_smw:
    k1, k2 = _tirs10_planck(image)
    tb = l10.expression('K2 / log(K1 / L + 1.0)', {'K1': ee.Image.constant(k1), 'K2': ee.Image.constant(k2), 'L': l10})
    tpw_cm = _era5_tcwv_cm(image)
# add_lst_footprint_diagnostics:
    wv = _era5_tcwv_cm(image).rename('WATER_VAPOR')
```

GEE sinovi (20 km, LST yangi − eski, `compute_lst_smw`):

| Sahna | Sensor | TPW eski (first) → yangi (interp), cm | LST farqi o'rt. [min, max] |
|---|---|---|---|
| Samarqand 2023-06-01 06:10 | L9 | 0.731 → 0.733 | **−0.317 K** [−0.43, −0.23] |
| Samarqand 2023-07-11 06:10 | L8 | 0.939 → 0.942 | 0.000 |
| Farg'ona 2023-07-14 05:52 | L9 | 2.114 → 2.117 | **−0.340 K** [−0.48, −0.16] |
| Farg'ona 2023-07-22 05:52 | L8 | 2.400 → 2.349 | 0.000 (bin almashmadi) |
| `SPACECRAFT_ID` yo'q rasm | — | — | **to'xtadi** ✅ |

End-to-end SEBAL_Milliy (Samarqand, 2023-07): L8 sahnasi (07-11) aynan bir xil; L9 sahnalari (07-03, 07-19) L↑ −2.3 W/m², ET24 +0.01 mm.

---

## #16 — Empirik L↓: Tref = cold anchor LST (p10 va 293 K olib tashlandi); L↓ konstantalari mode bo'yicha

User qarori: "Tref faqat o'sha yaxshi sug'orilgan piksel qiymati olinsin, butun maydonniki emas"; "293 kabi default qo'ymasin, topilmasa to'xtasin"; "boshqa rejim/konstanta/vaziyatlarni ham inobatga ol".

**Muammo (oldin):** SEBAL_ID / SEBAL_B / pysebal da L↓ = c1·σ·[−ln τsw]^c2·Tref⁴, Tref = butun cropland zonasining **LST p10** (anchor emas). Zona bo'sh bo'lsa ERA5 AIR_TEMP mediani, u ham bo'lmasa **293 K**. Radiatsiya anchor tanlashdan oldin hisoblangani uchun haqiqiy cold anchor ishlatilmagan. L↓ koeffitsientlari `mode == 'SEBAL_ID'` bo'lmasa har qanday mode uchun (1.08, 0.265) — noma'lum mode ham jimgina shu.

**Oldin** (`radiation.py`, `main.py`):
```python
def compute_incoming_longwave(image, mode='yangiliklar', roi=None, cold_mask=None):
    if mode == 'yangiliklar' or mode == 'SEBAL_Milliy': ... ERA5 STRD
    base = lst.mask().And(cold_mask.gt(0))
    tref_lst = lst.updateMask(base).reduceRegion(ee.Reducer.percentile([10]), roi, 100, ...).get('LST')
    tref_fb = image.select('AIR_TEMP').reduceRegion(ee.Reducer.median(), roi, 1000, ...).get('AIR_TEMP', 293.0)
    tref = ee.Number(ee.Algorithms.If(tref_lst, tref_lst, tref_fb))
    c_mult, c_pow = (0.85, 0.09) if mode == 'SEBAL_ID' else (1.08, 0.265)

# main.py process_tile
    collection = collection.map(lambda im: radiation.compute_all(im, mode, roi, cold_mask, sloping_terrain=...))
    for i in range(n):
        anchors = energy_balance.select_anchor_pixels(img_anchor, roi, cold_mask=cold_mask, hot_mask=hot_mask, ...)
```
**Keyin:**
```python
# config.py
LDOWN_ERA5_MODES = ('yangiliklar', 'SEBAL_Milliy')
LDOWN_EMPIRICAL = {'SEBAL_ID': (0.85, 0.09), 'SEBAL_B': (1.08, 0.265), 'pysebal': (1.08, 0.265)}
def ldown_is_empirical(mode):      # noma'lum mode → ValueError

# radiation.py
def compute_incoming_longwave(image, mode='yangiliklar', tref=None):
    if mode in cfg.LDOWN_ERA5_MODES: ... ERA5 STRD (o'zgarmagan)
    if mode not in cfg.LDOWN_EMPIRICAL: raise ValueError(...)
    if tref is None: raise ValueError("... Tref (cold anchor LST) SHART — default harorat ishlatilmaydi")
    c_mult, c_pow = cfg.LDOWN_EMPIRICAL[mode]
    ...  return image.addBands(l_down).set('LDOWN_TREF', tref)
def compute_pre_longwave(image, mode, sloping_terrain)   # SMW (Milliy) + K↓ — L↓ ga bog'liq emas
def compute_longwave_balance(image, mode, tref=None)     # L↓, L↑, Rn, G₀, Rn−G₀
def compute_all(image, mode, tref=None, sloping_terrain=False)   # ikkalasi birga

# energy_balance.py
select_anchor_pixels(..., need_rn=True)       # need_rn=False: zona/LST tanlanadi, Rn−G₀ hali yo'q
finalize_anchor_values(image, roi, anchors, anchor_mode)   # AYNI maskalardan LST + Rn−G₀
cold_anchor_surface_temp(image, image_anchor, anchors, roi, anchor_mode)
    # point_anchor: anchor tanlagan AYNI piksel (image_anchor LST min) dagi ASL LST (min(2))
    # median_anchor: cold nomzodlarning asl LST mediani

# main.py process_tile
    ldown_empirical = cfg.ldown_is_empirical(mode)
    ERA5 rejim   → map: radiation.compute_all(im, mode, sloping_terrain)          (oldingidek)
    Empirik rejim → map: radiation.compute_pre_longwave(im, mode, sloping_terrain)
      har sahna: 1) select_anchor_pixels(need_rn=False)
                 2) Tref = cold_anchor_surface_temp(...)  (getInfo; None → RuntimeError, sahna/tile to'xtaydi)
                 3) img = radiation.compute_longwave_balance(img, mode, tref)
                 4) anchors = finalize_anchor_values(...)  (valid emas → sahna o'tkaziladi)
                 5) 1- va 4-bosqich cold LST farqi > 0.01 K bo'lsa ogohlantirish
```
Qamrab olingan holatlar: `SEBAL_ID`, `SEBAL_B`, `pysebal` (empirik); `SEBAL_Milliy`, `yangiliklar`, `Kc_ETo`/`SEBAL_Milliy_Kc` (→ Milliy) — ERA5, o'zgarmagan; `point_anchor` va `median_anchor`; `default` va kaskad (`cimec`/`plan_a`/`plan_b`/`pysebal`) anchor metodlari; `sloping_terrain=True` (anchor LST_DEM da, Tref ASL LST da).

GEE sinovi — birlik darajasi:

| Holat | Natija |
|---|---|
| `ldown_is_empirical`: SEBAL_B / SEBAL_ID / pysebal | True |
| `ldown_is_empirical`: SEBAL_Milliy / yangiliklar | False |
| `ldown_is_empirical('Kc_ETo')`, noma'lum mode | ValueError ✅ (process_tile Kc ni avval Milliy'ga o'giradi) |
| `compute_incoming_longwave(mode='SEBAL_ID')` Tref'siz | ValueError ✅ |

GEE sinovi — end-to-end `process_tile` (Samarqand 20 km, 2023-07-01..20; OLDIN = HEAD 22d96df):

| Rejim | Sana | Tref oldin (p10) → keyin | cold anchor (keyin) | L↓ oldin → keyin | Rn | ET24 oldin → keyin |
|---|---|---|---|---|---|---|
| SEBAL_ID point | 07-03 | 310.19 → **303.19** | 303.19 | 396.3 → 361.8 | 582.9 → 549.9 | 5.72 → 5.86 |
| SEBAL_ID point | 07-11 | 312.56 → **305.55** | 305.55 | 408.6 → 373.1 | 569.9 → 536.0 | 4.77 → 4.84 |
| SEBAL_ID point | 07-19 | 308.19 → **301.88** | 301.88 | 386.2 → 355.6 | 579.1 → 549.8 | 5.80 → 5.88 |
| SEBAL_B median | 07-03 | 310.19 → **308.47** | 308.47 | 400.0 → 391.2 | 586.4 → 578.1 | 4.26 → 4.24 |
| SEBAL_B median | 07-11 | 312.56 → **310.84** | 310.84 | 412.4 → 403.4 | 573.4 → 564.7 | 5.41 → 5.41 |
| SEBAL_B median | 07-19 | 308.19 → **306.86** | 306.86 | 389.8 → 383.1 | 582.5 → 576.1 | 4.27 → 4.22 |
| pysebal median | 07-11 | 312.56 → **310.84** | 310.84 | 412.4 → 403.4 | 573.4 → 564.7 | 5.41 → 5.41 |
| SEBAL_ID + sloping | 07-03 | 310.19 → **303.19** | 308.01 (LST_DEM) | 396.3 → 361.8 | 582.2 → 549.2 | 5.22 → 5.18 |
| SEBAL_ID + sloping | 07-11 | 312.56 → **305.55** | 310.19 (LST_DEM) | 408.6 → 373.1 | 568.9 → 535.0 | 4.41 → 4.44 |
| SEBAL_ID + sloping | 07-19 | 308.19 → **301.88** | 306.78 (LST_DEM) | 386.2 → 355.6 | 578.0 → 548.7 | 5.38 → 5.31 |
| SEBAL_ID cimec (kaskad) | 07-03 | 310.19 → **306.82** | 306.82 | 396.3 → 379.4 | 582.9 → 566.7 | 5.77 → 6.32 |
| SEBAL_ID cimec (kaskad) | 07-11 | 312.56 → **308.94** | 308.94 | 408.6 → 390.0 | 569.9 → 552.1 | 4.68 → 4.75 |
| SEBAL_ID cimec (kaskad) | 07-19 | 308.19 → **305.07** | 305.07 | 386.2 → 370.8 | 579.1 → 564.4 | 6.29 → 5.42 |
| SEBAL_Milliy (ERA5) | 07-03 / 07-11 / 07-19 | — | — | 364.0 / 355.7 / 378.6 (o'zgarmadi) | ±2.3 | 4.50→4.51 / 3.69→3.69 / 4.57→4.58 |

(o'rtachalar ROI bo'yicha, 300 m; L↓/Rn W/m², ET24 mm/kun)

- Barcha empirik rejimlarda **Tref = cold anchor LST** (point: aynan o'sha piksel; median: nomzodlar mediani).
- `sloping_terrain`: Tref = ASL LST (303.19 K), anchor esa LST_DEM (308.01 K) — farq 4.8 K ≈ 0.0065·z (z ≈ 740 m).
- SEBAL_ID da L↓ −30…−35 W/m² (ERA5 STRD bilan solishtirish: shu hududda 355.7–378.6).
- Hech bir sahnada "1-bosqich ≠ yakuniy cold LST" ogohlantirishi chiqmadi.
- cimec kaskadida 07-03 (+0.55) va 07-19 (−0.87 mm) katta farq: hot anchor biroz o'zgargan (07-19: dT_hot 4.20 → 4.96) — #14 ulush zonalari va L↓ birga ta'sir qiladi.
- Ishlash vaqti (bir vaqtda parallel testlar — shovqinli): SEBAL_ID 67 → 79 s, pysebal 43 → 82 s, sloping 132 → 302 s — har sahnaga qo'shimcha getInfo (zona ulushi, Tref, yakuniy anchor).

---

## #17 — SEBAL_ID oilasi: anchor ETr topilmasa 0 emas — xato bilan to'xtaydi

User qarori: "0 default qiymat olmasin; natija chiqmasa muammoni aytib to'xtasin".

Qayerda: `energy_balance.compute_all` — SEBAL_ID oilasi (SEBAL_ID, **SEBAL_Milliy** — hozirgi asosiy rejim): λET_cold = COLD_ETRF·ETr_c, λET_hot = ETrF_hot·ETr_h.

**Oldin:**
```python
        vals = ee.Dictionary({
            'etr_c': etr.updateMask(cm).reduceRegion(...).get('ETR_INST', 0),
            'etr_h': etr.updateMask(hm).reduceRegion(...).get('ETR_INST', 0),
        }).getInfo()
        etr_c = vals['etr_c'] or 0.0          # null → 0 → λET_cold = 0 (jimgina)
        etr_h = vals['etr_h'] or 0.0
```
**Keyin:**
```python
def anchor_etr_inst(image, roi, cold_mask, hot_mask):
    vals = ee.Dictionary({
        'etr_c': etr.updateMask(cold_mask).reduceRegion(...).get('ETR_INST'),   # default yo'q
        'etr_h': etr.updateMask(hot_mask).reduceRegion(...).get('ETR_INST'),
    }).getInfo()
    missing = [side for side, k in (('cold', 'etr_c'), ('hot', 'etr_h')) if vals.get(k) is None]
    if missing:
        raise RuntimeError(f"{date}: {missing} anchor nomzodlarida instant ETr (ETR_INST) topilmadi — "
                           f"λET_... hisoblab bo'lmaydi. Default 0 ishlatilmaydi. Tekshiring: ERA5 meteo ...")
    return vals['etr_c'], vals['etr_h']

# compute_all ichida:
        etr_c, etr_h = anchor_etr_inst(image, roi, cm, hm)
```
Eslatma: `run()` tile rejimida har tile `try/except` ichida — xato matni chiqadi va o'sha tile to'xtaydi (keyingi tile davom etadi); ROI rejimida run to'xtaydi.

GEE sinovi (Samarqand 20 km, 2023-07-11, SEBAL_ID):

| Holat | Natija |
|---|---|
| Oddiy anchor maskalari | ETr cold 0.841, hot 0.823 mm/soat (oldingi bilan bir xil yo'l) |
| Bo'sh cold maska | **RuntimeError** ✅ `2023-07-11: cold anchor nomzodlarida instant ETr (ETR_INST) topilmadi — λET_cold hisoblab bo'lmaydi. Default 0 ishlatilmaydi. ...` |

---

## #18 — pysebal anchor metodi: soxta default qiymatlar olib tashlandi; `_pn` 0 ni null deb olmaydi

User qarori: "soxta qiymatlarni qo'yma, tuzat".

**Oldin** (`energy_balance._anchor_pysebal`, kaskadning 4-metodi):
```python
    ndvi_max = _safe_num(ns, 'NDVI_max', 0.7)
    ndvi_std = _safe_num(ns, 'NDVI_stdDev', 0.05)
    cold_mean = _safe_num(cs, 'LST_mean', 295.0)
    cold_std = _safe_num(cs, 'LST_stdDev', 2.0)
    ndvi_p10 = _safe_num(np_, 'NDVI', 0.1).max(0.05)
    hot_mean = _safe_num(hs, 'LST_mean', 305.0)
    hot_std = _safe_num(hs, 'LST_stdDev', 2.0)

def _safe_num(d, key, default):
    v = d.get(key, default)
    return ee.Number(ee.Algorithms.If(v, v, default))      # 0 ham "yo'q" → default

def _pn(d, key, sentinel):
    v = d.get(key, sentinel)
    return ee.Number(ee.Algorithms.If(v, v, sentinel))     # 0 ham "yo'q" → sentinel
```
**Keyin:**
```python
    ndvi_max = _pn(ns, 'NDVI_max', _HI)        # yo'q → maska bo'sh → metod "topilmadi"
    ndvi_std = _pn(ns, 'NDVI_stdDev', _LO)
    cold_mean = _pn(cs, 'LST_mean', _LO)
    cold_std = _pn(cs, 'LST_stdDev', _HI)
    p10 = _pn(np_, 'NDVI', _LO)
    ndvi_p10 = ee.Number(ee.Algorithms.If(p10.gt(_LO), p10.max(0.05), p10))   # 0.05 chegara faqat haqiqiy qiymatga
    hot_mean = _pn(hs, 'LST_mean', _HI)
    hot_std = _pn(hs, 'LST_stdDev', _HI)

def _pn(d, key, sentinel):
    v = d.get(key, sentinel)
    return ee.Number(ee.Algorithms.If(ee.Algorithms.IsEqual(v, None), sentinel, v))   # faqat null → sentinel
```
- Statistika chiqmasa maska **bo'sh** bo'ladi (sentinel ±1e6 — "qiymat yo'q" belgisi, anchor qiymati sifatida ishlatilmaydi) → metod "topilmadi" → kaskad keyingi metodga o'tadi. Fizik default (295 K, 305 K, 0.7 …) YO'Q.
- `_safe_num` o'chirildi (boshqa joyda ishlatilmagan).
- `_pn` endi faqat null ni sentinel qiladi — cimec va plan_b ham shu funksiyani ishlatadi; haqiqiy 0.0 qiymat endi saqlanadi.

GEE sinovi:

| Tekshiruv | Oldin | Keyin |
|---|---|---|
| `_pn`: qiymat 0 | sentinel | **0** ✅ |
| `_pn`: null / kalit yo'q | sentinel | sentinel (−1e6 / +1e6) |
| pysebal, Samarqand 20 km 2023-07-11: cold nomzodlar | **0 ta** (cold LST = None → metod topilmasdi) | **1 ta**, LST 307.04 K |
| pysebal: hot nomzodlar / hot LST | 18 715 / 329.154 K | 18 715 / 329.154 K |
| pysebal, bo'sh base | 0 / 0 | 0 / 0 |

Oldin cold nomzodlar bo'sh chiqishining sababi: NDVI eng yuqori guruhida bitta piksel qolgan, uning LST_stdDev = 0; `If(0, 0, 2.0)` bu 0 ni "yo'q" deb olib **2.0 K** qo'ygan → `LST ≤ mean − 2.0` → bo'sh maska. Ya'ni soxta default haqiqiy sahnada pysebal metodini ishdan chiqarib qo'ygan.

---

## #19 — G₀ suv: NDVI < 0 YOKI QA suv biti (WATER_MASK)

User qarori: "C variant — NDVI<0 YOKI QA suv; QA ishlasin".

**Muammo (oldin):** `is_water = ndvi.lt(0)`. Preprocessing'da Landsat QA_PIXEL bit 7 / HLS Fmask bit 5 dan `WATER_MASK` bandi yasalardi, lekin hech qayerda ishlatilmasdi. GEE (2023-07-11): NDVI<0 piksellarning 98.8 % i QA suv bilan mos, lekin QA suv bo'lib NDVI ≥ 0 bo'lgan piksellar (loyqa/sayoz/qirg'oq; Kattaqo'rg'on 2 598 px, 97 % i JRC tarixida suv) G/Rn ≈ 0.14 olardi.

**Oldin** (`radiation.compute_soil_heat_flux`):
```python
    is_water = ndvi.lt(0)
    g_ratio = g_ratio.where(is_water, 0.5)
```
**Keyin:**
```python
    is_water = ndvi.lt(0).Or(image.select('WATER_MASK').eq(1))    # WATER_MASK yo'q → GEE xato
    g_ratio = g_ratio.where(is_water, gcfg['water_fraction'])
```

GEE sinovi (2023-07, OLDIN = HEAD cd8d764):

| Hudud | Suv piksellari oldin → keyin | Quruqlikda max \|ΔG\| | Qo'shilgan suvda G/Rn | Qo'shilgan suvda G (W/m²) | ROI o'rtacha G |
|---|---|---|---|---|---|
| Kattaqo'rg'on 15 km | 39 074 → 41 672 (+2 598) | 0 | 0.142 → 0.500 | 104 → 369 | 129.7 → 130.6 |
| Samarqand 20 km | 6 188 → 6 678 (+490) | 0 | 0.155 → 0.500 | 109 → 355 | 118.4 → 118.5 |
| `WATER_MASK` bandi yo'q rasm | — | — | — | — | **to'xtadi** ✅ |

Shahar tomlari (NDVI<0, JRC bo'yicha hech qachon suv bo'lmagan; Samarqand 1 504 px) — oldingidek suv qoidasida qoladi (user qarori: ekin ET siga tegishli emas).

---

## #20 — G₀ koeffitsientlari config.SOIL_HEAT_FLUX dan

**Muammo (oldin):** `config.SOIL_HEAT_FLUX` (c1 0.0038, c2 0.0074, ndvi_extinction **0.978**, ndvi_power 4, water_fraction 0.5) hech qayerda o'qilmasdi; `radiation.py` 0.0038 / 0.0074 / **0.98** / 4 / 0.5 va clamp 0.0 / 0.6 ni qattiq yozgan edi.

| Parametr | config (oldin) | kod (oldin) | endi (config, kod shu yerdan o'qiydi) |
|---|---|---|---|
| c1 | 0.0038 | 0.0038 | 0.0038 |
| c2 | 0.0074 | 0.0074 | 0.0074 |
| ndvi_extinction | **0.978** | **0.98** | **0.98** (SEBAL manual Eq. 24; ishlab turgan qiymat saqlandi) |
| ndvi_power | 4 | 4 | 4 |
| water_fraction | 0.5 | 0.5 | 0.5 |
| ratio_min / ratio_max | — | 0.0 / 0.6 (qattiq) | 0.0 / 0.6 (config'ga qo'shildi) |

**Keyin** (`radiation.compute_soil_heat_flux`):
```python
    gcfg = cfg.SOIL_HEAT_FLUX
    g_ratio = t_celsius.multiply(albedo.multiply(gcfg['c2']).add(gcfg['c1']))
    veg_extinction = ee.Image(1.0).subtract(ndvi.pow(gcfg['ndvi_power']).multiply(gcfg['ndvi_extinction']))
    ...
    g_ratio = g_ratio.clamp(gcfg['ratio_min'], gcfg['ratio_max']).rename('G_RATIO')
```
Izohlardagi 0.978 ham 0.98 ga to'g'rilandi (config.py, radiation.py modul izohi). Sinov: quruqlik piksellarida G oldingi bilan **aynan bir xil** (max |ΔG| = 0, #19 jadvali).

---

## #21 — Anchor zona chegarasi: yagona `cfg.ANCHOR['min_candidates']`, ikkala joyda ≥

**Muammo (oldin):** zona "yetarli" chegarasi `cfg.ANCHOR_LANDCOVER['min_pixels']` (20) dan olinardi; `cfg.ANCHOR['min_candidates']` (20, user sozlagan) hech qayerda ishlatilmasdi. Tile darajasida `>=`, sahna darajasida `>`.

**Oldin:**
```python
# compute_tile_anchor_zones
        min_pixel_count = lc['min_pixels']
    cold_zone = cold_f if (counts.get(...) or 0) >= min_pixel_count else None
# _purity_zones
            if (counts.get(f'{tag}{k}') or 0) > lc['min_pixels']:
```
**Keyin:**
```python
# compute_tile_anchor_zones
        min_pixel_count = cfg.ANCHOR['min_candidates']
    cold_zone = cold_f if (counts.get(...) or 0) >= min_pixel_count else None
# _purity_zones
            if (counts.get(f'{tag}{k}') or 0) >= cfg.ANCHOR['min_candidates']:
```
`ANCHOR_LANDCOVER['min_pixels']` o'chirildi; `ANCHOR['min_candidates']` izohi: "valid zona piksellari soni ≥ shu (100 m da sanaladi)". Natija faqat zona pikseli aynan 20 ta bo'lganda o'zgaradi.

---

## #22 — G₀ suv: avval QA suv (WATER_MASK), bo'lmasa NDVI < 0

User qarori: "ikkalasi ham ishlashi kerak emas — avval water_mask dan qilsin, agar u bo'lmasa NDVI dan". #19 dagi "NDVI<0 YOKI QA" birlashmasi shu bilan almashtirildi.

**Oldin (#19):**
```python
    is_water = ndvi.lt(0).Or(image.select('WATER_MASK').eq(1))    # WATER_MASK yo'q → xato
```
**Keyin:**
```python
    ndvi_water = ndvi.lt(0)
    is_water = ee.Image(ee.Algorithms.If(
        image.bandNames().contains('WATER_MASK'),
        image.select('WATER_MASK').eq(1).unmask(ndvi_water),   # QA; pikselda qiymat yo'q → NDVI
        ndvi_water))                                           # band yo'q → NDVI < 0
```
- Landsat: QA_PIXEL bit 7; HLS: Fmask bit 5 (ikkalasi ham preprocessing'da `WATER_MASK`).
- NDVI<0 bo'lgan, lekin QA suv demagan piksellar (asosan shahar tomlari) endi suv emas.

GEE sinovi (2023-07, G₀ valid piksellarda; OLDIN = HEAD cd8d764, faqat NDVI<0):

| Hudud | Suv (G/Rn = 0.5) oldin → keyin | Qo'shildi (QA suv, NDVI ≥ 0) | Chiqdi (NDVI < 0, QA suv emas) | ROI o'rtacha G |
|---|---|---|---|---|
| Kattaqo'rg'on 15 km | 50 911 → 53 700 | +3 408 (G 104 → 369 W/m²) | −619 (G 319 → 108) | 129.7 → 130.5 |
| Samarqand 20 km | 8 064 → 4 608 | +638 (G 109 → 355) | −4 094 (G 291 → 112) | 118.4 → 118.1 |
| `WATER_MASK` bandi yo'q rasm | NDVI<0 ishlatildi | — | — | HEAD bilan max \|ΔG\| = **0** ✅ |

---

## #23 — Anchor ΔT = hot_LST − cold_LST ≥ 5 K — barcha metodlarda

User qarori: "ΔT tekshiruvi barcha metodlarda, 5 K".

**Oldin:** faqat kaskad metodlarda (`_finalize_anchor`) `(h − c) >= cfg.ANCHOR_CASCADE['min_dt']` (1.0 K). Production `default` metodida va `finalize_anchor_values` da ΔT tekshiruvi **yo'q** edi (faqat LST > 200 K). Rad etilganda xabar: "anchor topilmadi" (sababsiz).

**Keyin:**
```python
# config.py
ANCHOR = {..., 'min_dt': 5.0, ...}            # ANCHOR_CASCADE['min_dt'] olib tashlandi (yagona manba)

# energy_balance._select_anchor_default va finalize_anchor_values
    ok = (cold_lst.gt(200).And(hot_lst.gt(200))
          .And(hot_lst.subtract(cold_lst).gte(cfg.ANCHOR['min_dt'])))
# energy_balance._finalize_anchor (kaskad)
    min_dt = cfg.ANCHOR['min_dt']

# main.py — rad etish sababi bilan:
#   ❌ Sahna 1/1: anchor yaroqsiz — ΔT = 25.9 K < 50.0 K (cold 305.7 K, hot 331.5 K) — O'TKAZIB YUBORILADI
#   ❌ Sahna 1/1: anchor yaroqsiz — cold/hot nomzod topilmadi — O'TKAZIB YUBORILADI
```
5 K asosi: ~3 × LST noaniqligi (C2 ST / SMW ≈ 1.5 K).

GEE sinovi:

| Holat | Natija |
|---|---|
| Samarqand 2023 (24 sahna), ΔT | 8.7 … 27.6 K — 5 K chegarasi bironta sahnani tushirmaydi |
| `min_dt = 50` (sun'iy), 2023-07-11 | ❌ `ΔT = 25.9 K < 50.0 K (cold 305.7 K, hot 331.5 K)` — sahna o'tkazildi ✅ |
| `min_dt = 5`, SEBAL_ID cimec, 2023-07-11 | ✅ anchor topildi, ΔT = 19.5 K |

---

## #24 — Hot suv balansi: aynan anchor hot pikselida, tuproq xaritadan, yaqinlashish tekshiruvi

User qarori: "aynan o'sha piksel qil"; "Saxton emas, aynan o'sha pikselning tuproq ma'lumotlarini kiritish kerak"; "bos" (boshlang'ich holatdan yaqinlashish).

**Muammo (oldin):**
1. `hot_pixel_etrf` hot nuqtani o'zi QAYTA tanlardi (hot_mask ichida max LST, 100 m, Rn−G₀ cheklovisiz). ROI rejimida (ANCHOR_SCALE 30 m) anchor pikselidan 46–74 m narida (2023-03-13: LST 303.07 vs 300.30 K).
2. θ_FC/θ_WP — Saxton-Rawls pedotransferi (sand/clay dan); tekstura topilmasa `_SOIL_DEFAULT`.
3. Oyna 14 kun, De₀ = TEW (quruq) — oldingi yomg'ir hisobga olinmasligi mumkin.
4. Yog'in/ETr kuni bo'lmasa jimgina 0.0.

**Keyin:**
```python
# energy_balance._reduce_anchor_values (point_anchor): LST, Rn−G₀ + lon/lat AYNI pikseldan
    hot_stats = (image.select(['LST', 'RN_G0']).addBands(ee.Image.pixelLonLat())
                 .updateMask(hot_mask).updateMask(rn_g0.mask())
                 .reduceRegion(ee.Reducer.max(4), geom, ANCHOR_SCALE, ...))
    hot_pt = ee.List([hot_stats.get('max2'), hot_stats.get('max3')])     # anchors['hot_point']
# energy_balance.compute_all (SEBAL_ID oilasi):
    hot_lonlat = ee.List(anchors['hot_point']).getInfo()
    wbr = water_balance.hot_pixel_etrf(image, roi, hot_lonlat)          # dict

# water_balance._soil_at_point — nuqtadagi xarita qiymatlari (Saxton EMAS):
#   θ_FC  = OpenLandMap SOL_WATERCONTENT-33KPA (b0, b10 o'rtachasi) × 0.01
#   θ_WP  = HiHydroSoil v2.0 WCpF4.2 (0–5, 5–15 sm o'rtachasi) × 0.0001
#   REW   = OpenLandMap tekstura → FAO-56 Table 19
#   biror qiymat yo'q → RuntimeError (default tuproq YO'Q)
# water_balance.hot_pixel_etrf — yaqinlashish:
    for w in cfg.HOT_WB['windows']:            # (14, 30, 60)
        _fetch(w, fetched)                     # faqat yangi kunlar olinadi
        e_wet = _run(days, De0=0)[2];  e_dry = _run(days, De0=TEW)[2]
        if abs(e_wet - e_dry) <= cfg.HOT_WB['conv_tol']:  break   # 0.02
#   yog'in / ETr kuni yo'q → RuntimeError (oldin jimgina 0)
```
Yangi config: `HOT_WB` (ze, etrf_max, windows, conv_tol, etrf_warn, fc_asset/bands/scale, wp_collection/layers/scale, precip_collection/band). `_saxton_fc_wp` water_balance'dan olib tashlandi (consumptive_use / ndvi_kc / root_zone_water o'z raster versiyasini ishlatadi — o'zgarmagan).

Nuqtadagi tuproq (GEE, 250 m): FC (33 kPa) 0.225–0.270, WP (1500 kPa) 0.127–0.144; oldingi Saxton FC 0.28 / WP 0.14. HiHydroSoil'ning o'z FC si (pF2 = 10 kPa) 0.40 — FAO-56 33 kPa ta'rifiga mos emas, shuning uchun FC OpenLandMap'dan.

---

## #25 — Sahna fizik QC, ogohlantirish, hisobot va oy bo'yicha to'xtash

User qarori: "bos"; "oyda yaroqli sahna qolmasa to'xtash — ha, faqat tashlab ketilgani sababi bilan yozilsin".

**Keyin:**
```python
# energy_balance.compute_sensible_heat_flux — skalyar iteratsiyadan keyin:
    if not H_hot > 0:        fails.append(f"H_hot = {H_hot:.1f} W/m² ≤ 0")
    if not dT_hot > dT_cold: fails.append(f"dT_hot = {dT_h:.2f} K ≤ dT_cold = {dT_c:.2f} K")
    if fails: raise SceneQCError("fizik kalibratsiya buzilgan: " + "; ".join(fails))
# energy_balance.compute_all — ETrF_hot > cfg.HOT_WB['etrf_warn'] (0.35) → OGOHLANTIRISH (rad etish emas)
# main.process_tile:
#   - har sahna uchun qc dict (sana, status, sabab, cold/hot LST, ΔT, ETrF_hot, P, oyna, De, Kr,
#     TEW, REW, FC, WP, dT_hot, dT_cold, H_hot, H_cold, lon, lat)
#   - anchor ΔT, anchor Rn−G₀, SceneQCError → "RAD ETILDI" + sabab, sahna o'tkaziladi
#   - sahnalar tugagach, eksportdan OLDIN: jadval (print) + scene_qc_{mode}_{ROI|tile}_{sana1}_{sana2}.csv
#   - biror oyda yaroqli sahna qolmasa → RuntimeError (eksport boshlanmaydi), rad etilganlar sababi bilan
```

GEE sinovi (Samarqand 20 km, ROI rejimi, `process_tile`):

| Sinov | Natija |
|---|---|
| 2023-03-13, SEBAL_Milliy | ETrF_hot 1.050 (P 17.2 mm / 14 kun, De 7.0 < REW 9) → ⚠️ ogohlantirish; **RAD ETILDI**: `H_hot = −17.6 W/m² ≤ 0; dT_hot = −5.10 K ≤ dT_cold = 2.40 K`; mart bo'sh → **to'xtadi** ("Yaroqli sahna qolmagan oy(lar): 2023-03 — eksport boshlanmadi") ✅ |
| 2023-03-13 + 03-21 | 03-21: oyna 14 → **30 kun** (yaqinlashish uchun), ETrF_hot 0.060; **RAD ETILDI**: `dT_hot = 2.44 K ≤ dT_cold = 2.68 K`; mart bo'sh → to'xtadi |
| 2023-10-15 | ETrF_hot 0.257 (P 5.2 mm, 14 kun), dT_hot 3.56 > dT_cold 1.60 → **OK** |
| 2023-12-10 | oyna **30 kun**, ETrF_hot 0.337; **RAD ETILDI**: `dT_hot = 2.86 K ≤ dT_cold = 3.14 K`; dekabr bo'sh → to'xtadi |
| 2023-07-11, SEBAL_ID (empirik L↓) | Tref = 305.55 K; ETrF_hot 0.000 (P 0 mm); dT_hot 4.39 > dT_cold 0.54 → **OK** |

CSV namunasi (`scene_qc_SEBAL_Milliy_ROI_2023-03-13_2023-03-14.csv`):
```
sana,status,sabab,cold_LST,hot_LST,dT_LST,etrf_hot,P_sum,window,converged,De,Kr,TEW,REW,FC,WP,dT_hot,dT_cold,H_hot,H_cold,lon,lat
2023-03-13,RAD ETILDI,fizik kalibratsiya buzilgan: H_hot = -17.6 W/m² ≤ 0; dT_hot = -5.10 K ≤ dT_cold = 2.40 K,287.3851,303.0744,15.6894,1.0500,17.1851,14,True,6.9895,1.0000,19.8125,9.0000,0.2700,0.1438,-5.0991,2.4044,-17.5895,133.9203,67.0488,39.6784
```

To'liq yil sinovi (Samarqand 20 km, SEBAL_Milliy, 2023-01-01 → 2024-01-01, bulut ≤ 70): kolleksiyada 24 sahna (yanvar, fevral, aprel — sahna yo'q), **20 OK, 4 RAD ETILDI**, → **to'xtadi**: "Yaroqli sahna qolmagan oy(lar): 2023-03, 2023-12 — eksport boshlanmadi".

| Sana | ETrF_hot | dT_hot / dT_cold (K) | H_hot / H_cold (W/m²) | Sabab |
|---|---|---|---|---|
| 2023-03-13 | 1.050 | −5.10 / 2.40 | −17.6 / 133.9 | H_hot ≤ 0; dT_hot ≤ dT_cold (nam tasvir) |
| 2023-03-21 | 0.060 | 2.44 / 2.68 | 286.4 / 134.2 | dT_hot ≤ dT_cold |
| 2023-10-07 | 0.000 | 4.28 / 4.59 | 259.7 / 301.3 | dT_hot ≤ dT_cold |
| 2023-12-10 | 0.337 | 2.86 / 3.14 | 170.3 / 136.4 | dT_hot ≤ dT_cold |

OK sahnalarda H_cold −235 … +113 W/m²; rad etilganlarda 134 … 301 W/m². Oktyabr 10-15 hisobiga saqlandi (ETrF_hot 0.257).

---

## #26 — Anchor metodi: DEFAULT 'cimec'

User qarori: "cimec qil va birinchi cimec ishlasin, bu bo'lmasa birma-bir qolgan metodlar orqali topilsin".

**Oldin:** `main.run(anchor_method='default')`, `process_tile(anchor_method='default')`, `select_anchor_pixels(method='default')`, `compute_all(anchor_method='default')` — klassik persentil (`_select_anchor_default`), CIMEC umuman sinalmasdi. (`run_sebal.py` o'zi `anchor_method='cascade'` beradi — u yerda CIMEC allaqachon birinchi edi.)

**Keyin:** to'rttala joyda default `'cimec'`. Tartib (`_cascade_order`): cimec → plan_a → plan_b → pysebal, avval land-cover zonada (`lc`), keyin ROI'da; hech biri chiqmasa `'default'` persentil fallback. `'cascade'` bilan aynan bir xil tartib. Mexanizm o'zgarmagan — faqat default qiymat.

GEE sinovi (Samarqand 20 km, `point_anchor`, rad etilgan sahnalar; `default` natijalari — yillik run'dan):

| Sahna | SEBAL_Milliy default | SEBAL_Milliy cimec | SEBAL_ID default | SEBAL_ID cimec |
|---|---|---|---|---|
| 03-13 | RAD (nam) | RAD (nam): dT_hot 0.16 ≤ 2.71 | RAD (nam) | ❌ to'xtadi: pysebal cold ETr topilmadi |
| 03-21 | RAD 2.44 ≤ 2.68 | ❌ to'xtadi: hot pikselda θ_WP (HiHydroSoil) yo'q | RAD 2.37 ≤ 3.02 | RAD 2.84 ≤ 2.99 |
| 10-07 | RAD 4.28 ≤ 4.59 | **OK 4.41 > 3.93** | RAD 3.93 ≤ 4.40 | RAD 4.27 ≤ 4.29 |
| 12-10 | RAD 2.86 ≤ 3.14 | ❌ to'xtadi: cimec ΔT 4.2 K → … → pysebal cold ETr topilmadi | RAD 2.68 ≤ 3.19 | ❌ to'xtadi: pysebal cold ETr topilmadi |

Kaskadda topilgan ikki to'xtash (tuzatilmagan, ochiq): (1) `anchor_etr_inst` cold ETr'ni maska medianasi sifatida 100 m da oladi — pysebal cold maskasi kichik → 100 m da bo'sh → RuntimeError, butun run to'xtaydi; (2) CIMEC hot pikselida HiHydroSoil θ_WP yo'q → RuntimeError (#24 qoidasi), butun run to'xtaydi.

---

## #27 — Anchor skalyarlari bitta rejimda: point → aynan anchor pikseli, median → nomzodlar mediani

User qarori: "ETr'ni anchor nuqtasidan oladigan qil"; "agar point bo'lsa pipeline'dagi bari point bo'lsin, median bo'lsa bari median — buni fix qil".

**Muammo (oldin):** `point_anchor` rejimida LST va Rn−G₀ aynan anchor pikselidan, lekin qolganlari nomzod MASKASI bo'yicha:

| Qiymat | Oldin | Joyi |
|---|---|---|
| u200, z0m, ρ (hot, SEBAL_ID'da cold ham) | maska MEDIANI, har band ALOHIDA reduce (o'z default gridida) | `compute_sensible_heat_flux` |
| instant ETr (cold, hot) | maska MEDIANI, **100 m** | `anchor_etr_inst` |
| yakuniy tashxis dT/rah/H (`fin`) | hot maska MEDIANI, 100 m | `compute_sensible_heat_flux` oxiri |
| `ANCHOR_*` albedo/NDVI/shamol | maska MEAN | xuddi shu |

Oqibat: (1) kichik maska (pysebal cold) 100 m da bo'sh → `ETR_INST` null → RuntimeError → **butun run to'xtardi** (Milliy/ID 12-10, ID 03-13); (2) anchor pikselida raster H maqsaddan farq qilardi (11-16 hot 160.0 vs 174.6; 10-15 cold 66.8 vs 76.1).

**Keyin:** yagona yordamchi `_anchor_sample(image, anchors, roi, bands, sides)` — `anchors['anchor_mode']` ga QAT'IY mos:
```python
img = image.select(['LST'] + bands)
proj = image.select('LST').projection()          # anchor tanlangan AYNI grid
if mode == 'point_anchor':                       # AYNAN anchor pikseli
    img.reduceRegion(ee.Reducer.first(), ee.Geometry.Point(anchors['cold_point'/'hot_point']),
                     crs=proj, scale=ANCHOR_SCALE)
elif mode == 'median_anchor':                    # nomzodlar mediani, AYNI grid
    img.updateMask(anchors['cold_mask'/'hot_mask']).reduceRegion(ee.Reducer.median(), roi,
                     crs=proj, scale=ANCHOR_SCALE, ...)
else: raise ValueError                            # rejim noma'lum — aralash yo'q
```
- anchors dict'ga `'anchor_mode'` qo'shildi (`_select_anchor_default`, `_finalize_anchor`, `finalize_anchor_values`).
- `compute_sensible_heat_flux`: u200/z0m/ρ → `_anchor_sample(['U_200','Z0M','RHO_AIR'])`; `-999` default olib tashlandi — topilmasa RuntimeError. Point rejimda grid tekshiruvi: namunadagi LST ≠ anchor LST → OGOHLANTIRISH (QC CSV'ga).
- `anchor_etr_inst(image, roi, anchors)` → `_anchor_sample(['ETR_INST'])` (100 m mask mediani o'rniga).
- `fin` va `ANCHOR_COLD/HOT_ALBEDO/NDVI/WIND` → `_anchor_sample` (klient qiymat). (B) qatorida endi hot va cold: raster qiymati va MAQSAD.

GEE sinovi (Samarqand 20 km, CIMEC kaskad):

| Sinov | Oldin | Keyin |
|---|---|---|
| SEBAL_Milliy 12-10 (pysebal) | "cold anchor nomzodlarida ETR_INST topilmadi" → run to'xtadi | fizik QC gacha yetdi → RAD `dT_hot 2.41 ≤ dT_cold 3.10` |
| SEBAL_ID 12-10 / 03-13 (pysebal) | run to'xtadi | RAD `2.56 ≤ 3.07` / nam tasvir RAD `1.09 ≤ 4.38` |
| Anchor pikselida raster H / maqsad (W/m²) | 11-16 hot 160.0/174.6; 10-15 cold 66.8/76.1 | Milliy 07-11: hot 270.03/270.0, cold −46.65/−46.6; Milliy 10-07: 264.62/264.6, 158.67/158.7; ID 07-11: 342.80/342.8, −16.14/−16.1; SEBAL_B 07-11 (point): 343.76/343.8 |
| SEBAL_B `median_anchor` 07-11 | — | ishlaydi (median rejimda maqsad bitta piksel emas — tenglik kutilmaydi) |
| Grid tekshiruvi (point) | — | barcha sinovda namuna LST = anchor LST (ogohlantirish yo'q) |

Qolgan farq (bu tuzatishga TEGISHLI EMAS, ochiq, simulyatsiya bilan tasdiqlangan): 11-16 hot 153.7/171.5 — Ta ±15 K cheklovi 1-iteratsiyada (neytral dT_hot 47.3 K → Ta 252 K < 279 K) raster yo'lini buradi; 08-20 cold −100/−242.4 — H ≥ −100 cheklovi.

---

## #28 — Point anchor deterministik + anchor qiymatlari bir marta hisoblanadi

**Muammo (oldin):** 2023-08-20 da hot nomzodlar ichida LST = 323.2867 K bo'lgan **2 ta piksel** (14 km oraliq; termal DN kvantlangan, yalang'och tuproq emissivligi bir xil, TCWV bitta ERA5 katagidan): A (66.9259, 39.7208) Rn−G₀ 309.93; B (66.7857, 39.5956) Rn−G₀ 250.22. `Reducer.max(4)` tenglikda ixtiyoriy pikselni qaytaradi, anchor qiymatlari esa **lazy** ifoda — har getInfo'da qayta hisoblanadi. Natija: bitta sahnaning o'zida suv balansi B pikselida, energiya balansi A da (H_hot maqsad 309.9, raster 250.2); boshqa run'da H_hot 250.2 (run-to-run farq).

**Keyin:**
```python
def _extreme_pixel(image, mask, geom, which, carry=()):
    kw = dict(crs=lst.projection(), scale=ANCHOR_SCALE, ...)      # ikkala bosqich AYNI grid
    ext = lst.updateMask(mask).reduceRegion(max|min, geom, **kw).get('LST')   # 1) qiymat
    tie = mask.And(lst.eq(ext))                                    # 2) shu qiymatli piksellar
    key = (lat + 90)·1e6 + (lon + 180)/1e3                         #    geometrik kalit (yagona)
    key.addBands(lonlat).addBands(LST).addBands(carry).updateMask(tie).reduceRegion(max(n))
# _reduce_anchor_values (point): cold = _extreme_pixel(..., 'min', carry=('RN_G0',)),
#                                 hot  = _extreme_pixel(..., 'max', carry=('RN_G0',))

def materialize_anchors(anchors, extra=None):   # BITTA getInfo → klient konstantalari
    # valid, cold/hot_lst, cold/hot_rn_g0 → ee.Number(qiymat); cold/hot_point → [lon, lat]
# main.process_tile: tanlashdan keyin va finalize_anchor_values'dan keyin chaqiriladi
# (Tref ham shu getInfo'da); compute_all(anchors=None) ham chaqiradi.
# cold_anchor_surface_temp (point): Tref = AYNAN anchors['cold_point'] pikselidagi asl LST.
```
Tenglikni hal qilish faqat geometrik (fizikaga tegmaydi); tenglik bo'lmasa natija oldingi bilan aynan bir xil (07-11, 11-16, 12-10 — o'zgarmadi).

GEE sinovi:

| Sinov | Natija |
|---|---|
| 08-20, ikki alohida run | ikkalasida hot = A (39.7208, 66.9259): suv balansi va energiya balansi AYNI pikselda; H_hot 309.93, raster 309.929 = maqsad ✅ |
| SEBAL_ID 07-11 (empirik L↓, 2 bosqich) | Tref 308.94 K; cold raster −16.14 / maqsad −16.1 ✅ (oldin tenglikda boshqa piksel: −12.07 / −13.8) |

---

## #29 — SEBAL_ID oilasi: iteratsiya hot VA cold yaqinlashganda to'xtaydi

**Oldin:** sikl faqat hot (dT_hot, rah_hot) stabillashishini tekshirardi; cold (δTa_cold ≠ 0) yaqinlashmagan qiymat bilan qolardi.

**Keyin:**
```python
hot_ok  = |ΔdT_hot| < tol·|dT_hot|  and  |Δrah_hot| < tol·rah_hot
cold_ok = (not is_id) or |Δrah_cold| < tol·rah_cold    # H_cold, ρ_c o'zgarmas → dT_cold ∝ rah_cold
if hot_ok and cold_ok: break
# max_iter da yaqinlashmasa — qaysi uch (hot/cold) ekani OGOHLANTIRISH va QC CSV'ga yoziladi
```
Dalil (offline, kod sikli nusxasi, median kirishlar): 12-10 — cold 3.46, 3.14, 2.53, 2.51, 2.74 … ≈2.71; eski sikl 5-iteratsiyada **3.14** bilan to'xtardi. 07-11: 1.36 → 1.18.
GEE: iteratsiya soni endi cold'ni ham hisobga oladi (10-07: 10, ID 07-11: 7, 12-10: 7); (B) raster qadamlari soni shunga teng (max 15).

---

## #30 — compute_sensible_heat_flux ichida ΔT himoyasi

**Oldin:** `c4 = (dT_hot − dT_cold)/(T_hot − T_cold)` — tekshiruvsiz (T_hot = T_cold → nolga bo'lish, T_hot < T_cold → c4 ishorasi teskari). Himoya faqat yuqorida (anchor tanlash) edi; `compute_all(anchors=None)` yo'li `valid` ni tekshirmasdi.

**Keyin:** skalyarlar olingandan so'ng: anchor LST yo'q/<200 K yoki `T_hot − T_cold < cfg.ANCHOR['min_dt']` (5 K, anchor tanlashdagi bilan BITTA chegara) → `SceneQCError` (sahna sababi bilan rad etiladi).

GEE sinovi (07-11, sun'iy T_hot = T_cold): `❌ anchor ΔT = T_hot − T_cold = 0.00 K < 5.0 K (cold 308.31 K, hot 308.31 K)` — nolga bo'lish xatosi yo'q, sahna QC hisobotida ✅

---

## #31 — SEBAL_ID oilasi: hot nomzodlar faqat tuproq ma'lumoti bor piksellar

User qarori: "ha shunday qilamiz" (hot piksel shahardagi bo'sh yer emas, tuproq bo'lishi kerak; soxta qiymat yo'q).

**Muammo (oldin):** 2023-03-21, SEBAL_Milliy + CIMEC: hot piksel (67.0143, 39.6943) — 30 m da bo'sh yer (WorldCover 60), lekin 250 m katakning **53 %** i qurilgan (Samarqand shahri) → HiHydroSoil θ_WP yo'q → `RuntimeError: Hot piksel tuprog'i topilmadi` → butun run to'xtardi.

Tekshiruv (GEE): muammo HiHydroSoil nuqsoni EMAS — tuproq bazalari shahar katagida ma'lumot bermaydi:

| Manba | O'sha nuqtada |
|---|---|
| HiHydroSoil v2 WCpF4.2 / WCpF2 | yo'q |
| SoilGrids (ISRIC) qum/gil | yo'q |
| HWSD v2 (sat-io) | shahar birligi (HWSD2_ID 7001): AWC yo'q, BULK −9; umuman θ_WP bermaydi (faqat AWC, ~1 km) |
| OpenLandMap 33 kPa | bor (0.26) — lekin GEE'da 1500 kPa (WP) qatlami yo'q |

ROI (20 km): 250 m kataklardan qurilgan qismi > 50 % — **61 %** ida WP yo'q; < 10 % — atigi **1.2 %** ida.

**Keyin:**
```python
# water_balance.py — BITTA manba, ikki foydalanish
def _soil_stack():            # fc (OLM 33 kPa), wp (HiHydroSoil pF4.2), tex (OLM tekstura) — xom
def soil_valid_mask():        # 1 — fc, wp, tex bor VA tekstura FAO-56 Table 19 da; aks holda 0
def _soil_at_point(pt, proj, scale):   # namuna ANCHOR gridida — aynan anchor pikseli
    _soil_stack().reduceRegion(ee.Reducer.first(), pt, crs=proj, scale=scale)
    # (oldin 250 m OpenLandMap gridida: WP/tekstura o'sha katak MARKAZIDAN — boshqa katak bo'lishi mumkin edi)
def hot_pixel_etrf(image, roi, hot_lonlat, grid, ...)   # grid = (LST proyeksiyasi, ANCHOR_SCALE)

# energy_balance.select_anchor_pixels(..., hot_soil=False)
#   hot_soil=True → hot_base ∧ soil_valid_mask  (lc zona), hot_flat = base_flat ∧ soil (ROI bosqichi),
#                   'default' fallback ham (_select_anchor_default(..., hot_soil_mask))
# main.process_tile va compute_all: hot_soil = cfg.is_id_mode(mode)   (SEBAL_B/pysebal — o'zgarmaydi)
```

GEE sinovi (Samarqand 20 km, point_anchor, CIMEC kaskad):

| Sahna | Oldin | Keyin |
|---|---|---|
| Milliy 03-21 | run to'xtadi (θ_WP yo'q) | hot (67.0383, 39.7517): FC 0.305, WP 0.143, oyna 30 kun, P 24.2 mm, ETrF_hot 0.117 → **OK** (dT_hot 3.33 > dT_cold 2.63) — mart qutqarildi |
| Milliy 07-11 | hot 327.9 K | hot 330.9 K (tuproq piksel), OK |
| Milliy 12-10 (pysebal) | RAD | hot tuproq pikselda, oyna 60 kun, P 46.7 mm, ETrF_hot 0.496 (nam) → RAD `2.20 ≤ 3.10` |
| Milliy 10-07 | OK | OK |

---

## #32 — Ta = LST − dT ni ERA5 ± 15 K ga cheklash olib tashlandi; faqat QC diagnostika

User qarori: "ha, faqat ±15 ni ol, lekin Ta ni qanday tekshiramiz — ishonch hosil qilish kerak".

**Oldin** (`compute_sensible_heat_flux` (B) raster sikli):
```python
ta_img = lst.subtract(dta)
ta_img = ta_img.where(ta_img.lt(air_temp_era5.subtract(15)), air_temp_era5.subtract(15))
ta_img = ta_img.where(ta_img.gt(air_temp_era5.add(15)), air_temp_era5.add(15))
dta = lst.subtract(ta_img).rename('DTA')
```
Dalil (GEE + offline simulyatsiya, GEE natijasini aniq takrorlaydi): 2023-11-16 — 1-iteratsiyada neytral dT_hot 47.3 K → Ta 252 K < 279 K → cheklov raster yo'lini skalyardan ajratdi → hot H 153.7 vs maqsad 171.5 (−10 %); cheklovsiz simulyatsiya 171.51. Yozda oxirgi qadamda ROI piksellarining 16–20 % ida (ekin 8–12 %) dT majburan oshirilgan (ET_inst −0.04…−0.10 mm/soat).

**Keyin:** cheklov olib tashlandi (dT ±20 % va H ≤ Rn−G₀ himoyalari qoladi). Ta faqat QC (qiymatlarga TEGMAYDI), `fin` bilan BITTA getInfo:
```python
ta_out = (lst − DTA − AIR_TEMP).abs().gt(15)             # sahna: |Ta − Ta_ERA5| > 15 K
qc: Ta_hot, Ta_era5_hot, Ta_cold, Ta_era5_cold (anchor rejimida), pct_Ta_out15 (90 m, ROI)
# sahna QC CSV'ga ustunlar qo'shildi; log: "🌡️ Ta QC (qiymatga tegmaydi): …"
```

Anchor pikselida raster H / maqsad (W/m²) — endi hamma sinovda aniq:

| Sahna | Hot | Cold |
|---|---|---|
| Milliy 11-16 | 173.89 / 173.9 (oldin 153.7 / 171.5) | 78.35 / 78.3 (oldin 73.8 / 78.3) |
| Milliy 03-21 | 339.77 / 339.8 | 156.75 / 156.7 |
| Milliy 07-11 | 279.40 / 279.4 | −46.65 / −46.6 |
| Milliy 10-07 | 254.49 / 254.5 | 158.67 / 158.7 |
| ID 07-11 / 10-07 | 299.60 / 299.6; 255.84 / 255.8 | −16.14 / −16.1; 130.97 / 131.0 |
| SEBAL_B 07-11 | 343.76 / 343.8 | — |

Ta QC (qiymatlarga tegmaydi):

| Sahna | hot Ta / ERA5 (K) | cold Ta / ERA5 (K) | \|Ta−Ta_ERA5\| > 15 K |
|---|---|---|---|
| Milliy 03-21 | 300.06 / 289.41 | 289.65 / 289.18 | 0.05 % |
| Milliy 07-11 | 326.53 / 308.57 | **318.49 / 308.32** | 29.47 % |
| Milliy 08-20 | 319.01 / 306.33 | 309.70 / 306.66 | 5.20 % |
| Milliy 10-07 | 302.81 / 290.09 | 289.93 / 290.81 | 0.09 % |
| Milliy 11-16 | 297.56 / 294.10 | 289.63 / 291.62 | 0.00 % |
| ID 07-11 | 326.86 / 308.57 | 310.27 / 308.32 | 15.79 % |
| ID 10-07 | 304.67 / 290.09 | 291.10 / 290.47 | 0.38 % |
| SEBAL_B 07-11 | 323.09 / 309.12 | 308.94 / 308.32 | 11.41 % |

---

## #33 — H ≥ −100 pastki chegarasi olib tashlandi

User qarori: "H ≥ −100 ni ham ol — men o'zim qo'yganman".

**Oldin:** `h = h_raw.min(rn_g0).max(-100).rename('H')` — 2023-08-20 cold anchor maqsad H −242.4, raster −100.0 (cold λET 142 W/m² kam).

**Keyin:** `h = h_raw.min(rn_g0).rename('H')` (λE ≥ 0 kafolati qoladi). Pastdan chegaralovchi qolgan himoya: dT ∈ [dT_cold, dT_hot] ± 20 % (cold'dan sovuqroq piksellarda ekstrapolyatsiya 20 % bilan cheklanadi). Keyingi bosqichlar: SEBAL_ID ETRF_INST clamp [0, 1.05]; SEBAL_B EF clamp [0, 1]; SEBAL_Milliy ET_24 = ET_inst·eff.soat — ETrF cheklovi yo'q (faqat dT margin).

GEE sinovi: Milliy 08-20 cold raster **−242.44 / maqsad −242.4** ✅ (oldin −100.0).

---

## #34–#37 — Proyeksiya: butun hisob zanjiri Landsat UTM 30 m gridida

User qarori: "bos, hammasini qil" (GPT taklifi bilan birga ko'rib chiqilgan reja: 1–4; RN qayta tartiblash va TPW algoritmi — qilinmaydi).

**Muammo (GEE bilan o'lchangan, 2023-07-11, barcha bandlar):**

| Band | SEBAL_Milliy (oldin) | SEBAL_ID (oldin) |
|---|---|---|
| LST, L_UP, DTA, G_RATIO | **EPSG:4326 0.25°** (ERA5 TCWV'dan) | UTM 30 m |
| LAI, EMISSIVITY, Z0M, Z0H | **EPSG:4326 1°** | **EPSG:4326 1°** |
| qolganlari (RN, G0, H, ET_24, ERA5 meteo …) | UTM 30 m | UTM 30 m |

Qoida (GEE sinovi): `ee.Image(1).subtract(NDVI)` → UTM (binar amalda konstanta proyeksiyani buzmaydi), `ee.Image(0).where(NDVI>0.3, 1)` → WGS84 1° (where konstanta proyeksiyasini oladi). Shuning uchun RN (konstanta bilan boshlansa ham) UTM edi — qayta tartiblash kerak emas.

Oqibat: `reduceRegion`'da crs berilmasa birinchi bandning default proyeksiyasi olinadi → SEBAL_Milliy anchor gridi 4326@30 m (piksel 30×23 m): ROI'da **1 795 766** piksel vs Landsat **1 380 904** (1.30×), noyob LST qiymatlari soni bir xil (1 205 079 vs 1 204 789) → Landsat piksellarining ~30 % i ikki marta (median og'irligi, nomzodlar soni buzilgan, sun'iy tengliklar). Yadro sinovi: 3×3 yadro SO'ROV gridida ishlaydi (0.25° proyeksiyali tasvir UTM'da so'ralsa 3×3 o'rtachasi UTM bilan AYNAN teng — 0.27273; crs'siz — 0.27934) → CSV/LST-diag crs'siz bo'lsa 90×69 m footprint.

**#34 — SMW LST** (`radiation.compute_lst_smw`):
```python
# Oldin:  lst = a.multiply(tb).divide(eps).add(b.divide(eps)).add(c)      # 'a' — ERA5 0.25°
# Keyin:  lst = tb.multiply(a).divide(eps).add(b.divide(eps)).add(c)      # Tb — Landsat UTM 30 m
SMW_TPW_STEP = 0.6; SMW_TPW_NBIN = 10     # Ermida klasslari — konstanta sifatida (algoritm o'zgarmagan)
```
Qiymat o'zgarmaydi (a·Tb = Tb·a).

**#35 — LAI va EMISSIVITY** (`surface_props`):
```python
# Oldin:  lai = ee.Image(0.0).where(...)                 → WGS84 1°
# Keyin:  lai = savi.multiply(0).where(...)               → Landsat UTM (Z0M, Z0H ham)
# Oldin:  emissivity = ee.Image(0.985).where(...)         (SEBAL_ID/Milliy va SEBAL_B shoxlari)
# Keyin:  emissivity = ndvi.multiply(0).add(0.985).where(...)
```
Valid piksellarda qiymat o'zgarmaydi; SAVI/NDVI yo'q piksellarda endi LAI/EMISSIVITY ham yo'q (oldin soxta 0 / 0.985) — ET qamrovi o'zgarmaydi (ET SR bandlarini talab qiladi).

**#36 — Yagona tahlil gridi** `energy_balance.analysis_proj(image) = image.select('NDVI').projection()`:
- barcha anchor reduksiyalari `crs=analysis_proj(image)`: persentillar (`_select_anchor_default`, `_anchor_cimec`, `_anchor_plan_b`, `_anchor_pysebal` — 18 ta), `_ensure_nonempty`, `_purity_zones` (100 m sanash), median `_reduce_anchor_values`, `_extreme_pixel`, `_anchor_sample`, Tref (`cold_anchor_surface_temp`), tuproq namunasi (hot_pixel_etrf grid), Ta QC ulushi;
- CSV: `_export_zonal_csv` (`reduceRegions(..., crs=grid)`, grid = birinchi sahna Landsat gridi), `_export_lst_diag_csv` (har sahna o'z gridi — 3×3/5×5/PSF = 90×90/150×150 m), `run_polygons` `_zonal_add(..., crs=grid)`.
- Tile darajasidagi zonalar (`compute_tile_anchor_zones`, `_utm_projection`) — o'zgarmagan (sahnadan oldin quriladi).

**#37 — Sahna QC** (`main._grid_tpw_qc`, BITTA getInfo, qiymatlarga tegmaydi):
- LST, LAI, EMISSIVITY, L_UP, DTA, RN proyeksiyasi = NDVI (crs + transform); farq → OGOHLANTIRISH; CSV: `grid`, `grid_ok`.
- SEBAL_Milliy: ROI'da ERA5 TCWV min/max → TPW klasslari; > 1 klass → OGOHLANTIRISH ("~1.4 K LST pog'onasi"); CSV: `TPW_min`, `TPW_max`, `TPW_bin_min`, `TPW_bin_max`, `n_TPW_bins`.

GEE sinovi:

| Sinov | Natija |
|---|---|
| SEBAL_Milliy 07-11, barcha 71 band proyeksiyasi | hammasi EPSG:32642 30 m (LST, L_UP, DTA, G_RATIO, LAI, EMISSIVITY, Z0M, Z0H ham); 1° da faqat kunlik ERA5 referenslari RS24, ETR24, ETREF_24 qoldi |
| SEBAL_ID 07-11 (regressiya) | oldingi bilan AYNAN: dT_hot 4.5885, dT_cold −1.3291, H 299.5983 / −16.1363, Ta QC 15.79 % |
| SEBAL_B 07-11 (regressiya) | AYNAN: dT_hot 5.3370, H_hot 343.7553, Ta QC 11.41 % |
| CSV zonal (`reduceRegions`, 150 m parcel, 0.25° default proyeksiyali tasvir) | crs'siz: **48 piksel**, o'rtacha 0.0902 (dublikatlar); `crs=Landsat`: **30 piksel**, 0.0869 = asl Landsat bilan AYNAN (farq ~4 %) |
| Grid QC | barcha qabul qilingan sahnalarda `EPSG:32642 30m ok=True` |
| TPW QC | 07-11: 0.846–1.049 sm, 1 klass; 08-20: 1.260–1.388 sm, 1 klass; **11-16: 0.599–0.796 sm → 2 klass (0–1) → OGOHLANTIRISH** |
| SEBAL_Milliy anchorlari (grid o'zgardi) | 07-11 OK (hot 331.1 K, cold H −44.5, raster = maqsad); 08-20 OK (cold H −256.5 = maqsad); 11-16 OK; **03-21 RAD** (`dT_hot 2.01 ≤ dT_cold 2.63`; yangi hot piksel rah_hot 6.7 s/m) — 4326 gridida (#31 sinovi) OK chiqqan edi |

---

## #38 — Cold anchor Ta QC ogohlantirishi (chegara 5 K)

User qarori: "ogohlantirish chegarasini o'zing qo'y".

**Ma'nosi:** Ta = LST − dT — SEBAL hisoblagan, yuza ustidagi havo harorati. Cold anchor — yaxshi sug'orilgan to'liq qoplamali ekin; uning ustidagi havo oddiy 2 m havo haroratiga (ERA5) yaqin bo'lishi kerak. Farq katta bo'lsa — cold kalibratsiya shubhali (masalan, juda barqaror qatlam, rah_cold juda katta). Qiymatlarga TEGMAYDI, sahnani rad ETMAYDI — faqat OGOHLANTIRISH (QC CSV `status`/`sabab`).

**Chegara 5 K** (`cfg.ANCHOR['cold_ta_warn']`): 8 sinov sahnasida cold farqi −2.0…+1.9 K; ERA5 T2m xatosi ~1–2 K, LST ~1.5 K; anomaliya (Milliy 2023-07-11) +9.4 K.

```python
# energy_balance.compute_sensible_heat_flux — Ta QC dan keyin:
d_ta = Ta_cold − Ta_era5_cold
if abs(d_ta) > cfg.ANCHOR['cold_ta_warn']:  → qc['warnings'] += "cold anchor Ta … = +9.3 K (|farq| > 5.0 K) — cold kalibratsiya shubhali"
```

GEE sinovi: Milliy 07-11 → `OGOHLANTIRISH: cold anchor Ta 317.7 K − ERA5 308.3 K = +9.3 K` (rah_cold 220 s/m); Milliy 08-20 → farq +1.9 K → OK.

---

## #39 — Konstanta asosli `where` va soxta yog'in (P = 0) olib tashlandi

User qarori: "bos" (3-band).

**Oldin:**
```python
# irrigation.classify_irrigation
irr_class = ee.Image(3).where(ms.gte(...), 2)...         # MOISTURE_STRESS yo'q pikselda ham "3 — darhol"; WGS84 1°
# ndvi_kc.compute_monthly_et_kc, root_zone_water.compute_awnet (kunlik iterate)
Kr = ee.Image(1.0).where(De2.gt(REW), ...)                # De2 yo'q pikselda Kr = 1; WGS84 1°
# consumptive_use, ndvi_kc, root_zone_water
P = ee.Image(ee.Algorithms.If(p_img, p_img, ee.Image(0.0))).unmask(0.0)   # CHIRPS kuni yo'q → P = 0 (jimgina)
```
**Keyin:**
```python
irr_class = ms.multiply(0).add(3).where(...)...toInt()   # asos — MOISTURE_STRESS (grid + mask)
Kr = De2.multiply(0).add(1.0).where(De2.gt(REW), ...)    # asos — De2
wb.check_chirps_month(year, month)   # oy boshida: CHIRPS DAILY HAR kun bormi (bitta getInfo); yo'q → RuntimeError
P = ee.Image(p_img)                  # soxta 0 ham, unmask(0) ham yo'q
```
Eslatma: binar amallar (`ee.Image(1.0).subtract(x)` va h.k.) tegilmadi — GEE sinovi: ular x ning proyeksiyasini oladi (zararsiz).

GEE sinovi: `check_chirps_month(2023, 7)` → OK; `check_chirps_month(2026, 9)` → `CHIRPS DAILY yog'ini 2026-09 da 30 kun yo'q (2026-09-01, …) — default 0 ishlatilmaydi.`
- `IRRIGATION_CLASS` (pysebal, 2023-07-11): EPSG:32642 30 m, int; klasslar 0/1/2/3 — oldin WGS84 1°.
- `ndvi_kc.compute_monthly_et_kc` (2023-07, Samarqand): xatosiz, ET_MONTHLY 93.6 mm (3 km o'rtacha).
- `root_zone_water.compute_awnet` (2023-07): xatosiz, ET_MONTHLY 122.9 mm, AW 77.9 mm.

---

## #40 — Anchor valid: cold_rn_g0 hot bilan simmetrik

User qarori: "bos" (4-band).

**Oldin:** `valid` uch joyda faqat `hot_rn_g0 > −900` ni tekshirardi (`_select_anchor_default`, `_finalize_anchor`, `finalize_anchor_values`); `compute_sensible_heat_flux` da `cold_rn_g0 = anchors.get('cold_rn_g0', hot_rn_g0)` — cold yo'q bo'lsa hot pikselning Rn−G₀ si olinardi (soxta zaxira).

**Keyin:** need_rn bo'lganda uch joyda ham `hot_rn_g0 > −900 VA cold_rn_g0 > −900`; `_finalize_anchor` probe — null `IsEqual` bilan; zaxira olib tashlandi; `compute_sensible_heat_flux` — hot (har doim) va cold (SEBAL_ID oilasi) Rn−G₀ yo'q → `SceneQCError("… anchor Rn−G₀ topilmadi")`; `main` rad etish sababi aniq: ΔT / Rn−G₀ (cold/hot) / nomzod yo'q.

GEE sinovi (07-11, sun'iy `cold_rn_g0 = −999`): `❌ Sahna 2023-07-11: cold anchor Rn−G₀ topilmadi — O'TKAZIB YUBORILADI` ✅

---

## #41 — Rs24: mahalliy kalendar kun (yarim tundan)

User qarori: "bos" (8-band).

**Oldin:** `day_start = ee.Date(date).advance(-utc_offset, 'hour')` — sahna uchun `date` = overpass vaqti → 24 soatlik oyna overpassdan boshlanardi (`get_daily_etr24` esa yarim tunga qirqadi — mos emas). Oylik sikllar (yarim tun sanasi) to'g'ri edi; xato faqat sahna ET_24 da (Milliy: ET_24 ∝ Rs24; SEBAL_B: Rn24 orqali).

**Keyin:** `day_start = ee.Date(ee.Date(date).format('YYYY-MM-dd')).advance(-utc_offset, 'hour')`

GEE sinovi (sahna Rs24, oldin → keyin):

| Joy | Oldin: xato | Keyin |
|---|---|---|
| Bushland (UTC−6), 2021-06-23 … 08-26 (5 sahna) | −1.3, −2.7, **+10.2**, −3.6, **−10.0** % | 0.0 % (hammasi) |
| Samarqand (UTC+5), 2023 (5 sahna) | ~0 % | 0.0 % |

Bushland/AmeriFlux kunlik (sahna) validatsiyasi shu xatoni o'z ichiga olgan.

---

## #42 — λ formulasida 273.15

User qarori: "bos" (9-band). `daily_et.py` (3 joy), `monthly_analytics.py` (2 joy): `LST.subtract(273.0)` → `LST.subtract(273.15)` (kodning qolgan qismi bilan izchil). Ta'siri: λ ga +354 J/kg (~0.015 %) — ET ga amalda sezilmaydi.

---

## #43 — ANCHOR_SCALE = 100 m, barcha rejimlarda

User qarori: "bos, 100 m qil".

**Oldin:** `energy_balance.ANCHOR_SCALE = 30`; `main.run` uni CSV yoki `process_by_tile` rejimida 100 ga o'zgartirardi → bir xil sahna rejimga qarab turli anchor (2023-07-11: ekinzor ET farqi 13 %).

**Keyin:** `ANCHOR_SCALE = 100` (yagona konstanta); `main.run` dagi almashtirish olib tashlandi (faqat log: "anchor 100 m da"). ET rasteri 30 m da qoladi — 100 m faqat anchor tanlash, nuqta namunasi, tuproq namunasi va zonalar uchun.

Asos (GEE sinovi, SEBAL_Milliy, Samarqand 20 km ROI, 30 m vs 100 m):

| Sahna | Vaqt 30 / 100 m | Ekinzor ET_24: 30 m → 100 m |
|---|---|---|
| 07-11 | 41 / 32 s | 5.850 → 5.086 mm/kun (**−13.1 %**) |
| 08-20 | 37 / 27 s | 5.958 → 5.925 (−0.6 %) |
| 10-15 | 54 / 35 s | 1.744 → 1.677 (−3.9 %) |
| 05-16 | 87 / 51 s | 3.960 → 3.900 (−1.5 %) |

07-11 dagi katta farq: 30 m da cold anchor — Ta-anomaliya pikseli (dT_cold −9.4 K, rah_cold 220 s/m, Ta ERA5'dan +9.3 K); 100 m da cold normal (dT_cold −1.4 K, Ta +1.8 K). Landsat TIRS native 100 m; 30 m LST — interpolyatsiya.

---

## #44 — point_anchor: default va pysebal dumlari chegaralanadi (5 %)

User qarori: "chegaralarni ham tuzat" (har metod o'z ta'rifida qoladi — faqat ICHKI nomuvofiqlik).

**Muammo (oldin):** point_anchor = nomzodlarning eng sovug'i/eng issig'i. cimec (cold p5–p40, hot p60–p95), plan_b (p5–p15/p85–p95), plan_a (qat'iy oynalar) — LST oralig'i ikki tomondan chegaralangan → point chetdagi 5 % ni chetlaydi. Lekin:
- `default`: cold = LST ≤ p20 (config izohi: "p5 juda xavfli — soya"), hot = LST ≥ p95 → point = absolyut eng sovuq/issiq, ya'ni izohning o'zi xavfli degan piksel (2023-10-07: cold albedo 0.11, Rn−G₀ 522 vs nomzodlar 434 W/m²);
- `pysebal`: cold ≤ o'rt−std, hot ≥ o'rt+std — statistik metod, point esa chegarasiz dumdan eng chetdagi piksel.

**Keyin:**
```python
def _trim_tails(image, geom, cold_mask, hot_mask):      # faqat point_anchor
    q = cfg.ANCHOR['point_trim_pct']                      # 5
    pc = LST.updateMask(cold_mask).percentile(q)          # NOMZODLAR ichida
    ph = LST.updateMask(hot_mask).percentile(100 − q)
    return cold_mask ∧ (LST ≥ pc), hot_mask ∧ (LST ≤ ph)
# _select_anchor_default (point_anchor) va kaskadda _UNBOUNDED_METHODS = ('pysebal',) — lc va ROI bosqichlarida
```
Nomzodlar ta'rifi o'zgarmaydi; cimec/plan_a/plan_b ga tegilmaydi; median_anchor rejimi o'zgarmaydi.

GEE sinovi (100 m, SEBAL_Milliy):

| Sahna | Oldin | Keyin |
|---|---|---|
| 10-07, `default` | cold albedo 0.110, Rn−G₀ 522 → RAD (`3.93 ≤ 4.40`, 30 m) | cold albedo 0.179, Rn−G₀ 453 → qabul (dT_hot 4.33 > dT_cold 3.99) |
| 12-10, kaskad → pysebal | RAD (`2.20 ≤ 3.10`) | cold NDVI 0.887, albedo 0.226 → qabul (dT_hot 2.37 > dT_cold 2.18) |
| 03-21, cimec (100 m) | RAD (`2.01 ≤ 2.63`, 30 m) | qabul (dT_hot 3.54 > dT_cold 2.56), raster = maqsad |
| 07-11, 08-20, 10-15 (cimec, 100 m) | — | qabul; anchor pikselida raster H = maqsad (291.6/−7.5; 248.7/−276.0; 252.3/90.8) |

Kuzatuv: 07-11 (100 m) cold juda barqaror qatlamda (rah_cold 197 s/m) — cold iteratsiyasi 15 qadamda yaqinlashmadi → OGOHLANTIRISH (#29 mexanizmi); raster yopilishi baribir aniq.

To'liq yil sinovi (#38–#44 kodi, 100 m, SEBAL_Milliy, Samarqand 20 km, 2023): **to'xtamadi** — 24 sahna, **23 qabul**, 1 rad (03-13 nam tasvir: H_hot −37.1, dT_hot −11.30 ≤ 2.29). Mart (03-21) va dekabr (12-10) endi yaroqli sahnaga ega (oldingi yillik run'larda ikkalasi bo'sh edi). Ogohlantirishlar: cold Ta > 5 K — 06-01 (**+14.4 K**, |ΔTa| > 15 K piksellar 98 %), 06-09 (+6.1 K), 08-04 (+5.4 K); 07-11 — cold iteratsiyasi 15 qadamda yaqinlashmadi; TPW 2 klass — 10 sahna.

---

## #45 — Anchor kaskadi: cimec → plan_a → plan_b → default → pysebal; default zaxirasi loglanadi

User qarori: "logga chiqar, tashlab ketma"; "default rejimida turmasin — boshidan cimec, a, b, default, keyin pysebal shu tartibda; birida topilmasa boshqasiga o'tsin".

**Oldin:**
- `_CANON_ORDER = (cimec, plan_a, plan_b, pysebal)`; `default` — alohida funksiya (`_select_anchor_default`): `anchor_method='default'` bo'lsa kaskadsiz yolg'iz ishlardi, aks holda barcha metodlar (lc + ROI) yiqilgandan keyin so'nggi zaxira;
- default ichida: qat'iy nomzod (NDVI + albedo + LST) yo'q bo'lsa — JIM zaxira (faqat LST sharti), hech qayerda ko'rinmasdi.

**Keyin:**
```python
_CANON_ORDER = ('cimec', 'plan_a', 'plan_b', 'default', 'pysebal')
def _anchor_default(image, geom, base, diag=None):   # boshqa metodlar kabi (cold_mask, hot_mask)
    ... qat'iy nomzodlar soni n_cold/n_hot → diag; n = 0 → zaxira (faqat LST) — SAQLANADI
# kaskad (lc, keyin ROI): har metod → _finalize_anchor(..., extra=diag)
#   zaxira ishlatilsa: "⚠️ default zaxirasi (lc): cold (NDVI ≥ p95 ∧ albedo < 0.20 nomzodi yo'q → faqat LST ≤ p20)"
#   → anchors['note'] → sahna QC warnings (CSV sabab, status OGOHLANTIRISH)
# hech biri topmasa: valid=0, fail_reason = "anchor: barcha metodlar (cimec → … → pysebal) lc va ROI da topilmadi"
_UNBOUNDED_METHODS = ('default', 'pysebal')     # point_anchor: 5 % kesish (#44)
# main: QC CSV'ga 'anchor' ustuni (metod/zona); log: "anchor: cimec/lc | zona: …"
```
`_select_anchor_default` olib tashlandi; `anchor_method` — kaskadning birinchi metodi (main default 'cimec' → to'liq tartib).

GEE sinovi (SEBAL_Milliy, 100 m, point):

| Sinov | Natija |
|---|---|
| 07-11, kaskad | cimec/lc (o'zgarmadi) |
| 12-10, kaskad | cimec (ΔT 3.8) → plan_a (bo'sh) → plan_b (ΔT 3.4) → **default/lc topdi** → fizik QC: RAD (`2.37 ≤ 2.53`). Oldingi tartibda pysebal (#44) qabul qilingan edi |
| 07-11, `default`, sun'iy cold_albedo_max = 0 | `⚠️ default zaxirasi (lc): cold (… nomzodi yo'q → faqat LST ≤ p20)` → CSV `OGOHLANTIRISH` (zaxira pikselida cold Ta ham +16.4 K) |
| 07-11, sun'iy min_dt = 100 | 10 urinish (5 metod × lc/ROI) → `❌ anchor: barcha metodlar (cimec → plan_a → plan_b → default → pysebal) lc va ROI da topilmadi` → sahna shu sabab bilan rad |

---

## #46 — Anchor fizik QC'dan o'tmasa, kaskad keyingi metoddan davom etadi

User qarori: "ha qo'sh, keyingi metodni sinasin".

**Oldin:** kaskad faqat "nomzod topilmadi" (bo'sh maska, ΔT < 5 K, Rn−G₀ yo'q) holatida keyingi metodga o'tardi. Metod anchor topib, u energiya balansida fizik QC'dan o'tmasa (`SceneQCError`: H_hot ≤ 0, dT_hot ≤ dT_cold, ΔT himoyasi, anchor Rn−G₀ yo'q) — sahna darhol rad etilardi (2023-12-10: default/lc → RAD, pysebal sinalmasdi).

**Keyin** (`main.process_tile`):
```python
img_pre = img; tried = []
while True:
    att = {}                                  # shu urinish QC maydonlari
    img = img_pre                             # L↓ / energiya balansidan OLDINGI toza tasvir
    anchors = select_anchor_pixels(..., exclude={(metod, zona) for tried})
    ... (materialize, Tref/L↓/finalize — avvalgidek)
    try:   img = compute_all(..., qc=att)
    except SceneQCError as e:
        tried.append((metod, zona, str(e)));  print("↪ metod/zona: … — keyingi metod sinaladi");  continue
    qc.update(att);  if tried: qc warnings += "fizik QC'dan o'tmagan anchor: …";  break
# hech biri qolmasa: RAD — "anchor: barcha metodlar … topilmadi; fizik QC'dan o'tmagan anchor: …"
```
`energy_balance.select_anchor_pixels(..., exclude=…)` — chetlangan (metod, zona) qadamlarini o'tkazib yuboradi.

GEE sinovi (SEBAL_Milliy, 100 m, point):

| Sahna | Natija |
|---|---|
| 12-10 | default/lc: `dT_hot 2.37 ≤ dT_cold 2.53` → keyingisi → **pysebal/lc qabul** (dT_hot 2.37 > dT_cold 2.18); CSV: `anchor=pysebal/lc`, sabab: "fizik QC'dan o'tmagan anchor: default/lc (…)" |
| 07-11 | cimec/lc — o'zgarmadi |
| 03-13 (nam tasvir) | 6 ta topilgan anchor ham fizik QC'dan o'tmadi: cimec/lc, default/lc, pysebal/lc, cimec/ROI, default/ROI, pysebal/ROI (H_hot ≤ 0 yoki dT_hot ≤ dT_cold) → RAD, sababi hammasi ro'yxati bilan |

To'liq yil sinovi (commit 7efafb2 kodi, SEBAL_Milliy, Samarqand 20 km, 2023): **to'xtamadi** — 24 sahna, 23 qabul, 1 rad (03-13 nam tasvir: 6 ta anchor ham fizik QC'dan o'tmadi). Anchor: 22 sahna cimec/lc; 12-10 — default/lc fizik QC'dan o'tmadi → pysebal/lc qabul. Barcha oylar (mart–dekabr, sahnasi bor) yaroqli.

---

## #47–#51 — Lahzalikdan kunlik va oylik ET'ga o'tish (upscaling) tuzatildi

User qarori: "Bismillah, ha bos" (reja A–F + validate; GPT tahlili bilan birga ko'rib chiqilgan).

**Muammolar (oldin):**

| # | Joy | Oldin | Muammo |
|---|---|---|---|
| A | SEBAL_B / pysebal / VIIRS kunlik Rn24 | `(1−α)·Rs24 − 110·TAU_SW`, TAU_SW = 0.75 + 2·10⁻⁵·z | ERA5 REAL Rs24 bilan OCHIQ OSMON τ aralashgan; formula (de Bruin 1987; Bastiaanssen 2000) kunlik τ24 = Rs24/Ra24 ni talab qiladi. Qishda (1−α)Rs24 ≈ 81 < 84 W/m² → Rn24 ≈ 0 → ET ≈ 0 |
| A | Oylik interpolyatsiya ro'yxati | `[EVAP_FRAC, ALBEDO, TAU_SW, LST]` | TAU_SW vaqtga bog'liq emas — interpolyatsiyasi ma'nosiz |
| B | SEBAL_B / pysebal oylik | `_interpolate_lambda`: (oldingi + keyingi)/2 — sahnalar orasidagi BARCHA kunlarga | na chiziqli, na vakillik davri; sahnadan keyingi kundanoq o'rtachaga sakraydi |
| C | Barcha modellar (B, ID, Milliy, CUirr seriyasi) | eng yaqin sahnada bulutli piksel → `collection.mean()` (BUTUN DAVR o'rtachasi) | vaqt mazmuni yo'qoladi |
| D/E | Metadata | `n_landsat_scenes` = butun davrdagi sahnalar; bo'shliq QC yo'q | |
| — | pysebal oylik (monthly_analytics) | Rs24 — UTC kun | mahalliy kun emas (#41 ning nusxasi) |
| G | `validate=True` | barcha rejimlar uchun `monthly_analytics` (pysebal uslubi) | ID/Milliy begona usul bilan tekshirilardi |
| #51 | `biomass.compute_apar` (pysebal) | Rs24 = (RN24 + 110·TAU_SW)/(1−α) (teskari yechim) | RN24 τ24 bilan (#47) → teskari yechim mos emas; haqiqiy RS24 bandi bor |

**Keyin:**
```python
# daily_et.py
def get_daily_ra24(date):          # FAO-56 Eq 21, piksel kengligi, AYNI kalendar kun → W/m²
def daily_rn24(albedo, rs24, ra24, rs24_surface=None):
    tau24 = (rs24 / ra24).clamp(0, 1)                      # KUNLIK o'tkazuvchanlik
    rn24  = (1 − α)·rs24_surface − 110·tau24               # qiya yuza: τ24 gorizontal Rs24 dan
    return rn24 ('RN24'), tau24 ('TAU24')
def _nearest_valid(collection, date):   # sahnaning vakillik davri, PIKSEL bo'yicha eng yaqin YAROQLI sahna
    q = −|t_sahna − t_kun| (bandlar umumiy maskasi bilan) → qualityMosaic('QNEAR') → bitta sahnaning barcha bandlari
def month_scene_qc(image_list, year, month):   # (shu oydagi sahnalar, maks masofa kun); > 8 → ⚠️
# compute_daily_et: RN24, TAU24 bandlari yangi formula bilan (barcha rejim; ET faqat SEBAL_B'da RN24 dan)
# compute_monthly_et / daily_et_series: SEBAL_B → [EVAP_FRAC, ALBEDO, LST] _nearest_valid + daily_rn24;
#   SEBAL_ID → ETRF_INST _nearest_valid; SEBAL_Milliy → SOLAR_FRAC _nearest_valid;
#   metadata: n_landsat_scenes (shu oy), max_gap_days
# monthly_analytics (pysebal): ET/biomassa/komponentlar — _nearest_valid + daily_rn24 + Rs24 MAHALLIY kun (utc_offset)
# viirs_downscaling: faqat Rn24 → daily_et.daily_rn24 (τ24); o'z anchor-interpolyatsiya usuli o'zgarmagan
# main: validate → daily_et.compute_monthly_et(mode=mode); CSV oylik qatorlariga n_landsat_scenes, max_gap_days
# biomass.compute_apar: rs24 = image.select('RS24')
```
Config: `DAILY_ET['max_scene_gap_days'] = 8` (Tasumi Eq 5.9: har sahna ≈ ±8 kun). SEBAL_Milliy — hujjatlarda "loyihaga xos quyosh masshtablash" (kitobdan emas).

**GEE sinovlari** (Samarqand 20 km, point, 100 m anchor):

Ra24 mustaqil tekshiruv (FAO-56 Eq 21, Python): 2023-07-11 **475.8 = 475.8** W/m²; 12-10 161.7 = 161.7; 03-21 334.8 = 334.8. Sahna kunlarida τ24 = 0.729 / 0.628 / 0.645 (ochiq osmon 0.764).

Oylik ET, ekinzor o'rtachasi — eski kod (`7efafb2` nusxasi) va yangi, AYNI sozlama:

| Rejim, oy | Eski | Yangi | Farq |
|---|---|---|---|
| SEBAL_B, 2023-07 | 148.8 mm | 157.2 mm | +5.6 % |
| SEBAL_B, 2023-12 | **2.5 mm** | 12.8 mm | qishki Rn24 ≈ 0 tuzatildi |
| pysebal, 2023-07 / 12 | 148.8 / 2.5 | 157.2 / 12.8 | SEBAL_B bilan bir xil |
| SEBAL_ID, 2023-07 | 211.04 | 211.04 | o'zgarmadi (ROI sahnalarida bulutli piksel yo'q) |
| SEBAL_Milliy, 2023-07 / 12 | 165.08 / 30.39 | 165.08 / 30.39 | o'zgarmadi |
| SEBAL_B sahna 07-11 ET_24 | 6.03 | 6.14 mm/kun | +1.9 % (τ24 0.729) |

Metadata / QC: iyul `n_landsat_scenes` 5 → **4** (shu oydagi), `max_gap_days` 3.7; dekabr 2 → **1**, `max_gap_days` **20.7** → `⚠️ 2023-12: kundan eng yaqin sahnagacha maks 20.7 kun (> 8)`.

pysebal 12-10 sahna (ekinzor o'rtachasi), eski → yangi: RN24 2.1 → 16.1 W/m²; ET_24 **0.066 → 0.50 mm/kun** (EF 0.886 — namlangan qishki ekin; dekabr ETo ~0.8–1 mm/kun); LUE 0.031 → 0.249 (namlik stressi ET orqali); PAR 49.36 → 48.91 = 0.48·RS24 (aniq). Oylik biomassa dekabr: 36.7 → 121.9 kg/ha (asosan sahna ET_24/LUE tuzatilishidan; bir xil sahnalarda oylik funksiyaning o'zi: 132.2 → 121.9, −7.8 % — 1–9 dekabr endi 12-10 sahnasidan).

GEE'da sinalmagan: VIIRS yo'li (use_viirs=False, faqat kompilyatsiya), validate (OpenET — faqat AQSh).

---

## #52–#55 — CSV bandlari/oylik flag, tayl xatolari, VIIRS Rs24 kuni

User qarori: "P1 … ha buni tuzat biz istagan bandlarni chiqaradigan qil / P2 … buni ham qo'sh / P3 … buni ham tuzat / P8 … tegilma / VIIRS'da Rs24 … buni ham tuzat agar muammo xatolik bo'lsa".
P8 (Kc modeli De har oy qayta boshlanishi) — TEGILMADI (hot piksel water balance bilan alohida).

### #52 — CSV sahna bandlari `csv_bands` dan

**Oldin** (`_export_zonal_csv`):
```python
SCENE_GROUPS = {
    'INST':           ['ET_INST_MM_HR', 'LAMBDA_E', 'ETRF_INST', 'EVAP_FRAC', 'SOLAR_FRAC', 'ETR_INST'],
    'DAILY_ET':       ['ET_24'],
    'INST_KOMPONENT': ['RN', 'G0', 'H', 'ALBEDO', 'LST', 'NDVI', 'AIR_TEMP',
                       'USTAR', 'RAH', 'DTA', 'LAI', 'TAU_SW', 'EMISSIVITY'],
}   # `bands` parametri (run(csv_bands=…) / CSV_LYS_BANDS) umuman ishlatilmasdi
```
Muammo: `csv_bands` berilsa ham har doim o'sha 20 band chiqardi; CSV_LYS_BANDS'dagi 21 band (ALB_*, K_DOWN, L_DOWN, L_UP, RN_G0, G_RATIO, SAVI, U_200, L_MO, Z0M, Z0M_WIND, RHO_AIR, SLOPE, WIND_SPEED_10M, RN24, ETR24 …) HECH QACHON chiqmasdi.

**Keyin:**
```python
INST_SET  = ('ET_INST_MM_HR', 'LAMBDA_E', 'ETRF_INST', 'EVAP_FRAC', 'SOLAR_FRAC', 'ETR_INST')
DAILY_SET = ('ET_24',)
req = list(dict.fromkeys(bands))                          # tartib saqlanadi, takror yo'q
avail = set(ee.Image(scenes[0]).bandNames().getInfo())
missing = [b for b in req if b not in avail]              # → "⚠️ CSV: so'ralgan bandlar sahnada yo'q — chiqmaydi: [...]"
use = [b for b in req if b in avail]
SCENE_GROUPS = {'INST': [b in INST_SET], 'DAILY_ET': [b in DAILY_SET], 'INST_KOMPONENT': [qolganlari]}
SCENE_GROUPS = {k: v for k, v in SCENE_GROUPS.items() if v}   # bo'sh guruh fayli chiqmaydi
# _reduce: bitta bandli guruhda reducer.setOutputs(['<band>_mean', '<band>_median'])
#   (GEE bir bandli reduceRegions'da ustunlarni band nomisiz 'mean'/'median' beradi);
#   DAILY_ET va MONTHLY_ET — plain_single=True: eski 'mean'/'median' format saqlanadi
#   (flux_compare_full.load_model_simple shunday o'qiydi).
```
Fayl nomlari (INST / DAILY_ET / INST_KOMPONENT / MONTHLY_ET) o'zgarmadi. `CSV_LYS_BANDS` ga `RS24`, `TAU24` qo'shildi (#47 Rn24 komponentlari).

GEE sinovi (Samarqand 2023-07-11, SEBAL_Milliy, 2 parcel; `Export.table.toDrive` ushlab qolindi — Drive'ga hech narsa ketmadi, ustunlar kolleksiyadan o'qildi):

| `csv_bands` | Natija |
|---|---|
| None (CSV_LYS_BANDS) | 43 band: INST 6, DAILY_ET 1 (`mean`/`median` — oldingidek), INST_KOMPONENT **36** (oldin 13) |
| `['ET_24','K_DOWN','ALB_LIANG','TAU24','YOQ_BAND']` | `⚠️ … chiqmaydi: ['YOQ_BAND']`; DAILY_ET 1 + INST_KOMPONENT 3 (ALB_LIANG, K_DOWN, TAU24); INST fayli yo'q |
| `['ET_24','LAMBDA_E','K_DOWN']` | INST → `LAMBDA_E_mean/_median`, INST_KOMPONENT → `K_DOWN_mean/_median` (tuzatishsiz `mean`/`median` bo'lardi); DAILY_ET → `mean`/`median` |

DAILY_ET 1-qator: A parcel, ET_24 mean 3.86 / median 3.90 mm/kun. GEE tekshiruvi: 1 bandli `reduceRegions` → `['mean','median']`, 2 bandli → `['LAMBDA_E_mean', …]`, `setOutputs` → `LAMBDA_E_mean`.

### #53 — `csv_monthly` flag

**Oldin:** CSV rejimida oylik ET (`compute_monthly_et` + MONTHLY_ET CSV) `export_monthly=False` bo'lsa ham HAR DOIM hisoblanardi — o'chirish imkoni yo'q edi.
**Keyin:** `run(..., csv_monthly=True)` → `_export_zonal_csv(..., csv_monthly=…)`. `False` → `⏭️  CSV MONTHLY o'tkazildi (csv_monthly=False)`, oylik hisob ham, eksport ham yo'q. Standart `True` — eski xulq (run_flux_validation `csv_monthly=True` ni aniq beradi; flux_compare_full MONTHLY_ET CSV'ni o'qiydi). `export_monthly` — faqat RASTER oylik (docstring'da).
Sinov: yuqoridagi 2- va 3-holat — MONTHLY_ET task yaratilmadi; 1-holatda MONTHLY_ET 1-qator: mean 112.4 mm, `n_landsat_scenes` 1, `max_gap_days` 19.7 (sinov atigi 1 sahna bilan).

### #54 — Tayl xatolari yutilmaydi

**Oldin:**
```python
except Exception as e:
    print(f"  ⚠️ {tile_label} qayta ishlashda xato ({e}) → tayl o'tkazib yuborildi")
    continue
...
print(f"  ✅ Tayyor! {len(all_tasks)} ta export task")
return {'tasks': all_tasks}
```
Muammo: xato turi yo'q, traceback yo'q, oxirida "✅ Tayyor!" — qaysi tayl natijasiz qolgani ko'rinmasdi; run_flux_validation uni "muvaffaqiyatli" sanardi.

**Keyin:**
```python
failed_tiles.append({'tile': tile_label, 'error': f"{type(e).__name__}: {e}"})
print(f"  ❌ TAYL {tile_label} O'TKAZIB YUBORILDI — {err}")
if not isinstance(e, RuntimeError): print(traceback.format_exc())   # kutilmagan xato
# bo'sh tayl → empty_tiles; tayl geometriyasi topilmasa → tile_warnings
# XULOSA: ro'yxatlar + status 'OK' | 'QISMAN'
return {'tasks', 'status', 'failed_tiles', 'empty_tiles', 'tile_warnings'}
```
run_flux_validation: `✅ N to'liq | ⚠️ N qisman (tayl xatosi) | ❌ N xato` + har birining sababi.

Sinov (`process_tile` soxta: P155_R32 → RuntimeError, P154_R33 → TypeError, P154_R32 → bo'sh): `❌ TAYL P155_R32 O'TKAZIB YUBORILDI — RuntimeError: …`; P154_R33 — TypeError + to'liq traceback; `⏭️  P154_R32: yaroqli sahna yo'q`; `⚠️ QISMAN tayyor!`; qaytgan: `status 'QISMAN'`, `failed_tiles` 2 ta, `empty_tiles ['P154_R32']`.

### #55 — VIIRS: Rs24 mahalliy kun

**Oldin:** `viirs_downscaling.daily_rn24` va `_daily_etref` → `ma._get_daily_rs24(date, roi)` — UTC kalendar kun. Quvurning qolgan qismi (compute_daily_et, oylik, pysebal #41/#49) mahalliy kun (utc_offset) ishlatadi → VIIRS yo'li boshqa kun bilan.
**Keyin:** `daily_et.get_daily_solar_radiation(date, roi, utc_offset=…)`; `utc_offset` `build_tile_monthly_et_viirs` (info['utc_offset']) va `build_daily_viirs_downscaled_collection(…, utc_offset=0)` orqali uzatiladi; `main._viirs_export_month` / `_s30_export_month` `m_info` ga `utc_offset` qo'shildi.

GEE sinovi (albedo 0.20, nuqta), Rs24 / Rn24 UTC kun → mahalliy kun:

| Joy | Kun | Rs24 W/m² | Rn24 W/m² |
|---|---|---|---|
| Samarqand (UTC+5) | 07-10 … 07-12, 12-10 | aynan bir xil | aynan bir xil |
| Bushland (UTC−6) | 2023-07-10 | 272.9 → 274.7 (+0.7 %) | 155.2 → 156.2 |
| Bushland | 2023-07-11 | 328.3 → 332.4 (+1.2 %) | 186.6 → 188.9 |
| Bushland | 2023-07-12 | 320.3 → 313.4 (−2.1 %) | 182.0 → 178.0 |
| Bushland | 2023-12-10 | 138.4 → 138.4 | 32.1 → 32.1 |

Samarqandda oyna faqat tungi soatlarga suriladi (mahalliy yarim tun = 19:00 UTC) → farq 0. G'arbiy yarim sharda (AQSh flux stansiyalari) kunlik ±2 % gacha. VIIRS to'liq oylik yo'li GEE'da hali ishga tushirilmagan (faqat shu funksiya).

`ma._get_daily_rs24` endi hech qayerda chaqirilmaydi (faqat izohlarda) — olib tashlanmadi.

---

## #56–#59 — Vaqt oynalari: ERA5 soatlik Ra davri, instant ETr, pysebal referens ET kuni

User qarori: "T1, T2, T3, T5 — shularni tuzat hozir" (vaqt auditi: T4 — hot piksel suv balansi — alohida; C1–C6 — keyin).

**Asos (GEE, Samarqand 2023-07-11 ochiq kun):** ERA5-Land `surface_solar_radiation_downwards_hourly` yorlig'i T qaysi soatni qamraydi — Rs/Ra (soatlik transmissivlik):

| UTC soat | 01 | 03 | 05 | 07 | 09 | 11 | 13 | 15 |
|---|---|---|---|---|---|---|---|---|
| Ra davri [T−1, T] | 0.36 | 0.64 | 0.74 | 0.78 | 0.78 | 0.75 | 0.66 | 0.41 |
| Ra davri [T, T+1] (joriy kod) | 0.07 | 0.44 | 0.64 | 0.75 | 0.84 | 0.92 | 1.12 | — (14: 1.88) |

[T−1, T] — ochiq kunda simmetrik (fizik); [T, T+1] — 1 dan oshadi (fizik emas). Bu `preprocessing.get_era5_for_image` dagi konvensiya bilan bir xil ("akkumulyativ yorliq T = [T−1h, T]").

### #56 (T1) — ETr24 soatlik yig'indida Ra/Rso davri

**Oldin** (`compute_etr24_hourly_sum.to_etr`):
```python
d = ee.Date(img.get('system:time_start'))
hour = ee.Number(d.get('hour'))
Ra = calc.Ra_hourly(lat, lon, doy, hour, dr, dec)     # davr [T, T+1] — SSRD esa [T−1, T]
```
**Keyin:**
```python
d = ee.Date(img.get('system:time_start')).advance(-1, 'hour')   # davr boshi T−1
doy = d.getRelative('day','year') + 1; hour = d.get('hour')
Ra = calc.Ra_hourly(lat, lon, doy, hour, dr, dec)     # davr [T−1, T] = SSRD davri
```
Rso (demak Rs/Rso → fcd → Rnl) endi Rs bilan AYNI soat uchun. `_omega_mid_hour` docstring: `hour` — davr BOSHI. Ta'sir: ETr24 (SEBAL_ID), ETREF_24 (grass, KC), ETPOT_24, Kc-model ETo.

### #57 (T2) — instant ETr (overpass)

**Oldin:** `hour = date.get('hour')` → Ra davri [floor(t), floor(t)+1]; SSRD esa overpass t markazidagi 1 soatga interpolyatsiya qilingan.
**Keyin:** `t_h = date.difference(yarim tun, 'hour')` (kasrli) → `Ra_hourly(..., t_h − 0.5, ...)` → davr [t−0.5, t+0.5] = SSRD davri. Ta'sir: ETR_INST → SEBAL_ID oilasi cold/hot λET, ETRF_INST.

### #58 (T3) — pysebal ETREF_24 / ETPOT_24

**Oldin:** sahnada `compute_reference_ets_daily(image, roi)` va oylikda `compute_reference_ets_for_date(date, roi)` → `get_daily_era5_aggregate(day)` — `utc_offset` YO'Q (UTC kun) + kunlik-qadam formulasi (Tmax/Tmin). Boshqa rejimlar (ETr24, ETREF_24 → KC) — mahalliy kun + 24 soatlik yig'indi (kitob App.B).
**Keyin:**
```python
def _reference_ets_hourly(day_start, roi, dem, utc_offset):
    ETREF_24 = compute_etr24_hourly_sum(day, roi, dem, 'grass',   utc_offset)
    ETPOT_24 = compute_etr24_hourly_sum(day, roi, dem, 'alfalfa', utc_offset)
compute_reference_ets_daily(image, roi, utc_offset=0)       # sahna
compute_reference_ets_for_date(date, roi, utc_offset=0)     # oylik (har kun)
# et_decomposition.compute_all(img, roi, utc_offset) ← main.process_tile (pysebal)
# monthly_analytics.compute_monthly_et_components → compute_reference_ets_for_date(..., utc_offset)
```
(`compute_reference_ets_daily2`, `et_decomposition.compute_etref` — chaqirilmaydi, lekin `utc_offset` uzatiladigan qilindi.)

### #59 (T5) — `get_daily_era5_aggregate` yarim tun

**Oldin:** `day_start = ee.Date(date).advance(-utc_offset, 'hour')` — vaqtli sana berilsa oyna overpassdan boshlanardi. **Keyin:** `ee.Date(ee.Date(date).format('YYYY-MM-dd')).advance(-utc_offset, 'hour')`. Hozirgi chaqiriqlar (CUirr, hot WB) yarim tun beradi → ularning natijasi o'zgarmaydi; himoya.

### GEE sinovlari — eski (HEAD `847f22e` nusxasi) va yangi kod, AYNI so'rov

ETr24 (alfalfa) va ETo24 (grass) — #56; pysebal ETREF_24 / ETPOT_24 — #58 (mm/kun, nuqta):

| Joy, kun | ETr24 | ETo24 | pysebal ETREF_24 | pysebal ETPOT_24 |
|---|---|---|---|---|
| Samarqand 04-10 | 5.66 → 5.71 (+0.8 %) | 4.31 → 4.35 | 3.84 → 4.35 (+13 %) | 4.91 → 5.71 (+16 %) |
| Samarqand 07-11 | 9.39 → 9.40 (+0.1 %) | 7.45 → 7.46 | 7.19 → 7.46 (+3.7 %) | 9.17 → 9.40 (+2.5 %) |
| Samarqand 12-10 | 1.32 → 1.38 (+4.8 %) | 1.10 → 1.16 | 0.77 → 1.16 (+49 %) | 1.14 → 1.38 (+21 %) |
| Bushland 07-09 | 5.09 → 5.11 | 4.04 → 4.06 | 5.64 → 4.06 (**−28 %**) | 7.69 → 5.11 (−34 %) |
| Bushland 07-12 | 11.53 → 11.53 | 8.66 → 8.66 | 10.01 → 8.66 (−13 %) | 14.32 → 11.53 (−20 %) |
| Bushland 12-10 | 3.90 → 3.93 (+0.9 %) | 2.61 → 2.64 | 2.91 → 2.64 (−9 %) | 4.76 → 3.93 (−17 %) |
| **Iyul jami**, Samarqand | 316.8 → 318.4 (+0.5 %) | — | 233.8 → 240.5 (+2.9 %) | 310.0 → 318.4 (+2.7 %) |
| **Iyul jami**, Bushland | 337.2 → 336.5 (−0.2 %) | — | 267.6 → 251.5 (−6.0 %) | 371.5 → 336.5 (−9.4 %) |

Yangi pysebal ETREF_24 = ETo24, ETPOT_24 = ETr24 (aynan) — rejimlar endi bir xil referens ET ishlatadi. Qishki farq katta: soatlik yig'indida Ra davri tuzatilishi (#56) past quyoshda ko'proq sezilarli (+4.8 %); pysebal'da qo'shimcha UTC kun (Samarqand = mahalliy 05:00→05:00) va kunlik-qadam formulasi.

Instant ETR_INST (#57), overpass nuqtasi: Samarqand (t = 6.18 UTC, 3 sahna) −0.3 %; Bushland (t = 17.33–17.44 UTC) 0.0 … −0.1 %.

`get_daily_era5_aggregate` (#59), Samarqand 07-11, UTC+5: yarim tun bilan T_min 21.74 °C; `'2023-07-11T06:11'` bilan eski 23.85 °C (siljigan oyna) → yangi 21.74 °C (aynan).

pysebal to'liq zanjir (Samarqand 20 km, 2023-07-11, ekinzor o'rtachasi) — sahna: ET_24 6.1415 → 6.1415 (o'zgarmadi), ETREF_24 7.19 → 7.47 (+3.8 %), ETPOT_24 9.20 → 9.43 (+2.6 %), MOISTURE_STRESS 0.671 → 0.652, LUE 0.0738 → 0.0713, BIOMASS_PROD 8.35 → 8.05 kg/ha/kun (−3.6 %), KC 0.856 → 0.823; oylik iyul: ET_MONTHLY 178.67 → 178.67, ETREF 231.2 → 238.6 (+3.2 %), ETPOT 306.4 → 315.7 (+3.0 %), DEFICIT 127.7 → 137.1 (+7.3 %), TACT/EACT o'zgarmadi.

---

## #60–#66 — C guruhi: pysebal T/E, qiya yuza ulanishi, Milliy C_rad, ETRF_RAW/C_RAD QC, VIIRS/S30

User qarorlari: C2 → **(b)** (Milliy'ni 1.05 ga cheklamaslik, ETRF_RAW + QC); "qolgan hammasini tuzat, ogohlantirishlarni o'zing kerakli raqamni qo'y, logda ogohlantirsin". GPT fikri bilan birga ko'rib chiqilgan (C1: qayta clamp yo'q; C6: target chiziqli to'ldiriladi, TAU_SW allaqachon #47 da olib tashlangan).

### #60 (C5) — pysebal oylik TACT/EACT

**Oldin** (`monthly_analytics.compute_monthly_et_components`):
```python
scene_rn24_mean = scene_col.select('RN24').mean().max(1)      # BUTUN mavsum sahnalari
rad_ratio = rn24_actual.divide(scene_rn24_mean).clamp(0, 1.5)
tact_day = interp.select('TACT_24').multiply(rad_ratio)
eact_day = et_day.subtract(tact_day).max(0)                   # T > ET bo'lsa E = 0, T + E ≠ ET
```
**Keyin:**
```python
tact_day = interp.select('BENEFICIAL_FRACTION').multiply(et_day)   # f_T = TACT_24/ET_24 (0–1), AYNI sahna
eact_day = et_day.subtract(tact_day)                               # T + E = ET
```
`BENEFICIAL_FRACTION` sahnada allaqachon bor edi (et_decomposition) va interpolyatsiya ro'yxatida edi.

GEE (Samarqand 20 km, pysebal, point, ekinzor o'rtachasi, mm/oy):

| Sinov | Oy | ET | T eski → yangi | E eski → yangi | |T+E−ET| eski (o'rt / maks) | T > ET piksel (eski) |
|---|---|---|---|---|---|---|
| sahnalar may–avg (12 ta), eski kod vs yangi kod | 2023-05 | 142.6 | 54.4 → 54.1 | 88.2 → 88.4 | 0.004 / 2.1 | 0 % |
| — " — | 2023-07 | 157.8 | 58.4 → 57.5 | 99.4 → 100.3 | 0.010 / 5.3 | 0 % |
| sahnalar may–okt (20 ta), eski formula qayta tuzilgan | 2023-04 | 115.6 | 57.9 → 49.2 (−15 %) | 58.2 → 66.5 | 0.47 / 36.9 | 3.4 % |
| — " — | 2023-07 | 157.8 | 68.9 → 57.5 (−17 %) | 89.0 → 100.3 | 0.17 / 22.3 | 0.2 % |
| — " — | 2023-10 | 50.7 | **6.7 → 14.4 (+115 %)** | 44.0 → 36.3 | 0 / 0 | 0 % |

Yangi kodda |T+E−ET| = 0 (barcha oylar). Eski formula T ni mavsum o'rtacha Rn24 ga bog'lardi: yozda oshirar, kuzda ikki barobar kamaytirardi; xato mavsum qanchalik uzun bo'lsa shuncha katta. ET o'zgarmaydi.

### #61 (C4) — `run(sloping_terrain=…)` ulanishi

**Oldin:** `run()` da parametr yo'q → tayl va ROI yo'lidagi `process_tile`, `_export_monthly` (4 joy), CSV `compute_monthly_et`, validate — hammasi `False`; faqat `run_polygons` ulangan edi.
**Keyin:** `run(sloping_terrain=False)` → `process_tile` (2), `_export_monthly` (4), `_export_zonal_csv` (→ `compute_monthly_et`, `consumptive_use.compute_all`), validate. pysebal oylik (`compute_all_monthly` → ET/komponentlar/biomassa) ham: `RA24_RATIO` eng yaqin sahnadan, `Rs24_qiya = Rs24·RA24_RATIO` (sahna RS24 bilan bir xil). VIIRS / S30 / Kc_ETo oylik yo'llarida kunlik qiyalik tuzatishi yo'q → `⚠️ OGOHLANTIRISH` logda.
Sinov (soxta `process_tile`/`_export_*`/`compute_monthly_et`, kwarg ushlab qolindi): True/False — tayl yo'lida 4 chaqiriq, ROI yo'lida 3 chaqiriq, hammasi to'g'ri qiymat; Kc_ETo + slope → ogohlantirish chiqdi. Standart `False` — hozirgi natijalar o'zgarmaydi.

### #62 (C3) — SEBAL_Milliy qiya yuza

**Oldin:** `ET_24 = ET_inst × Rs24/SSRD` (tekis yuza nisbati) — `C_RAD` hisoblanardi, lekin Milliy'da ishlatilmasdi.
**Keyin:** `ET_24 = ET_inst × Rs24/SSRD × C_rad` (compute_daily_et); oylik/CUirr seriyasida `SOLAR_FRAC × C_RAD × Rs24`. Asos: ET_inst·(Rs24/Rs_inst)_piksel = ET_inst·(Rs24/SSRD)_tekis·C_rad, C_rad = (Rso_inst_flat/Rso_inst_px)·(Rso24_px/Rso24_flat) — SEBAL_ID'dagi ETrF24 = C_rad·ETrF_inst bilan bir xil; ikki marta hisoblash yo'q.

GEE (Zarafshon tizmasi etagi, 66.95°E 39.45°N, 12 km, 2023-07-11, SEBAL_Milliy, sloping_terrain=True):

| Hudud | Qiyalik o'rt | C_RAD o'rt (min–max) | ET_24 C_rad'siz → bilan | Iyul oylik |
|---|---|---|---|---|
| butun ROI | 11.7° | 1.040 (0.79–2.00) | 1.811 → 1.877 mm/kun | 63.2 → 65.8 mm (+4.1 %) |
| ekinzor | 2.2° | 1.003 (0.91–1.13) | 4.570 → 4.579 (+0.2 %) | — |
| qiyalik > 10° | 19.4° | 1.078 (0.79–2.00) | 0.612 → 0.735 (+20 %) | 30.0 → 34.9 mm (+16.5 %) |

### #63 (C2, variant b) — ETRF_RAW + QC

**Keyin** (compute_daily_et, SEBAL_ID oilasi): `ETRF_RAW = ET_inst/ETr_inst` (cheklanmagan) bandi; `ETRF_INST = ETRF_RAW.clamp(0, 1.05)` — SEBAL_ID ET_24 undan (o'zgarmadi); SEBAL_Milliy ET_24 xom ET_inst dan (o'zgarmadi — cheklanmaydi). `ETRF_RAW` → `CSV_LYS_BANDS` (INST fayli).
QC `main._daily_qc` (BITTA getInfo, 90 m, ekinzor): `pct_etrf_gt110`, `etrf_raw_p99` → QC CSV. **Chegara:** `ETRF_RAW_WARN = 1.10`, `ETRF_RAW_WARN_PCT = 1.0 %` (cold anchor 1.05 — undan 5 % yuqori piksel ekinzorning 1 %idan ko'p bo'lsa sahna nam yoki cold anchor issiq bo'lishi mumkin).
GEE (Samarqand, iyul, SEBAL_Milliy): 07-03 0.09 % (p99 1.027), 07-11 0.02 % (1.019), 07-19 0.93 % (1.098), 07-27 0.62 % (1.082) — chegaradan past, ogohlantirish yo'q. 07-03 sahna: ETRF_RAW maks 1.085 vs ETRF_INST maks 1.050.

### #64 (C1) — C_RAD / RA24_RATIO clamp QC

ETrF24 = ETrF_inst × C_rad dan keyin qayta clamp **qo'yilmadi** (ETr24 tekis yuza uchun — quyoshli qiyalikda ETrF24 > 1.05 fizik). QC: `pct_crad_lo`, `pct_crad_hi` — `C_RAD` (SEBAL_ID oilasi) yoki `RA24_RATIO` (SEBAL_B, pysebal) [0.5, 2.0] chegarasidagi ROI piksellari. **Chegara:** `CRAD_CLAMP_WARN_PCT = 1.0 %`.
GEE (Zarafshon etagi, 07-11): SEBAL_Milliy C_RAD ≥ 2.0 — 0.14 %, ≤ 0.5 — 0 %; SEBAL_B RA24_RATIO — 0 % / 0 % → ogohlantirish yo'q. Chegaralar vaqtincha 0.5 % / 0.1 % ga pasaytirilganda ikkala ogohlantirish logda va QC CSV'da to'g'ri chiqdi.
(Sinov paytida topilgan o'z xatoyim tuzatildi: yagona `mean` reduktor kalitlari `LO`/`HI`, `LO_mean` emas — QC ustunlari bo'sh chiqqan edi.)

### #65 (C6) — VIIRS / S30

| Joy | Oldin | Keyin |
|---|---|---|
| `interp_radiation_bands` (VIIRS Lambda ALBEDO) | `ma._interpolate_bands`: (oldingi+keyingi)/2, bulutli piksel → mavsum o'rtachasi | `daily_et._nearest_valid` (eng yaqin yaroqli sahna) |
| `_daily_etref` (VIIRS KC, S30) | sahna ETREF_24 × Rn24(kun)/Rn24(sahna), clamp 1.5 (proksi; midpoint + mavsum o'rtachasi) | `daily_et.get_daily_etr24(ref_type='grass', utc_offset)` — o'sha kun, soatlik yig'indi, mahalliy kun (sahna ETREF_24 bilan AYNI usul) |
| `fill_temporal_gaps` (VIIRS target) | tasvir darajasida `before.first()/after.first()` — o'sha tasvirda maskali piksel shu kuni BO'SH | piksel darajasida (qualityMosaic; S30 `interp_temporal_per_pixel` mantig'i) |
| S30 `_daily_etref(anchors, day, tile_roi)` | `utc_offset` yo'q → Rs24/ETREF UTC kun (#55 da o'tkazib yuborilgan) | `utc_offset=info['utc_offset']` |

GEE: per-piksel to'ldirish (sintetik: 07-01 chap yarmi maskali = 1, 07-09 = 5, kun 07-05) — chap: eski **bo'sh** → yangi 5; o'ng: 3 → 3.
ETREF (Samarqand ekinzor, mm/kun) eski proksi → yangi: 07-03 (sahna kuni) 7.535 → 7.535 = sahna ETREF_24; 07-05 7.10 → 6.67 (−6.2 %); 07-20 8.23 → 7.96 (−3.3 %); 07-28 6.50 → 6.47.
ALBEDO 07-20 (ekinzor): 0.1683 → 0.1693.
**VIIRS oylik — birinchi to'liq runtime** (iyul 2023, 4 sahna, ndvi modeli, ekinzor): kc 168.5 mm, lambda 185.9 mm; standart SEBAL_Milliy oylik 161.7 mm (VIIRS yo'llari o'z kunlik usuli bilan: Λ×Rn24 / KC×ETo).

### #66 — S30 `interp_temporal_per_pixel` runtime xatosi

**Oldin:** `td = ee.Number(...)`; `td.subtract(bt)` (bt — Image) → GEE: *"Number.subtract, argument 'right': Invalid type. Expected type: Number. Actual type: Image"* — `linear` ham, `nearest` ham HAR DOIM xato → S30 oylik ET hech qachon hisoblanmagan. (Yangi VIIRS per-piksel funksiyasida ham shu ifoda bor edi — sinovda ushlandi.)
**Keyin:** `tdi = ee.Image.constant(td).toDouble()`; `tdi.subtract(bt)`. Sinov (sintetik, kun 07-05): linear 3, nearest 1 (to'g'ri).

Eslatma: `monthly_analytics._interpolate_bands` va `_get_daily_rs24` endi hech qayerda chaqirilmaydi (o'lik kod — olib tashlanmadi).

### #67 — O'lik kod olib tashlandi

User: "ha olib tashla ishlatilmasa". Tekshiruv (`grep` butun loyiha, worktree'siz): ikkala funksiya faqat ta'rifda va izohlarda uchraydi — hech qayerda chaqirilmaydi.
Olib tashlandi (`monthly_analytics.py`, 150 qator): `_get_daily_rs24` (ERA5 Rs24, UTC kun — #55 dan keyin ishlatilmaydi), `_interpolate_bands` (midpoint + bulutli piksel → mavsum o'rtachasi — #48/#65 dan keyin ishlatilmaydi) va uning izohga olingan eski nusxasi; modul docstring'i yangilandi ("eng yaqin yaroqli sahna"). `viirs_downscaling.py`: `from . import monthly_analytics as ma` (endi ishlatilmaydi) olib tashlandi.
Sinov: `py_compile` barcha modullar; gee_env'da `main`, `viirs_downscaling`, `hls_s30_etrf`, `monthly_analytics` import OK; VIIRS `fill_temporal_gaps` sintetik sinovi (chap 5, o'ng 3) — o'zgarmadi.

