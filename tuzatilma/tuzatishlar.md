# SEBAL-GEE v4 — bajarilgan tuzatishlar jurnali

Faqat kodda **haqiqatan bajarilgan** o'zgarishlar (oldin / keyin / GEE sinovi). Tekshiruvlar va takliflar — chatda.
Kod: `D:\Cloud_comp\Sebal\scripts\sebal_gee_v4`. Raqamlar suhbatdagi raqamlar bilan bir xil (tushib qolgan raqamlar — kod o'zgarmagan tekshiruvlar).

| # | Sana | Nima qilindi | Holat | Fayllar |
|---|---|---|---|---|
| 00 | 2026-09-17 | `tile_roi.geometry()` xato qatori olib tashlandi | ✅ commit 69d0ca4 | main.py |
| 01 | 2026-09-17 | `mosaic_same_date` / `best_per_date` → `_mosaic_same_date` (preprocessingdan keyin, UTM/property saqlanadi) | ✅ commit qilinmagan | preprocessing.py, main.py |
| 04 | 2026-09-17 | `tiles` + `process_by_tile=False` → aniq `ValueError` | ✅ commit qilinmagan | main.py |
| 06 | 2026-09-17 | Kolleksiya xronologik tartibi (`sort`) | ✅ commit qilinmagan | preprocessing.py |
| 07 | 2026-09-17 | SAVI bitta marta, yagona `cfg.SAVI_L` | ✅ commit qilinmagan | config.py, surface_props.py, hls_s30_etrf.py |
| 08 | 2026-09-17 | `info['scene_dates']` — sahna ↔ sana indeksi (VIIRS/S30) | ✅ commit qilinmagan | main.py |
| 09 | 2026-09-17 | Raster export: verguldan keyin 2 xona (`EXPORT_DECIMALS`) | ✅ commit qilinmagan | config.py, main.py |
| 10 | 2026-09-17 | Albedo `olmedo_brdf` — DEFAULT | ✅ commit qilinmagan | config.py, surface_props.py, main.py |
| 11 | 2026-09-17 | SR_B1 scale → preprocessing (Landsat + HLS) | ✅ commit qilinmagan | config.py, preprocessing.py, surface_props.py |
| 12 | 2026-09-17 | HLS cloud precheck `contains()` | ✅ commit qilinmagan | preprocessing.py |
| 13 | 2026-09-17 | Z0M_WIND NDVI chegaralari: skalyar → sahna p20/p80 | ✅ commit qilinmagan | config.py, surface_props.py, main.py |

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
