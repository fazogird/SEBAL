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
| 14 | 2026-09-17 | Anchor zonalari: eng yaqin piksel → sinf ULUSHI (0.80 → 0.70 → 0.60 → ROI) | ✅ commit qilinmagan | config.py, energy_balance.py, main.py |
| 15 | 2026-09-17 | SMW LST: ERA5 TCWV vaqtga interpolyatsiya + TIRS10 K1/K2 sensor bo'yicha (L8 ≠ L9) | ✅ commit qilinmagan | config.py, radiation.py |
| 16 | 2026-09-17 | Empirik L↓ Tref = cold anchor LST (p10 va 293 K olib tashlandi); L↓ konstantalari mode bo'yicha | ✅ commit qilinmagan | config.py, radiation.py, energy_balance.py, main.py |
| 17 | 2026-09-18 | SEBAL_ID oilasi: anchor ETr topilmasa 0 emas — xato bilan to'xtaydi | ✅ commit qilinmagan | energy_balance.py |
| 18 | 2026-09-18 | pysebal anchor metodi: soxta default qiymatlar olib tashlandi; `_pn` 0 ni null deb olmaydi | ✅ commit qilinmagan | energy_balance.py |

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
