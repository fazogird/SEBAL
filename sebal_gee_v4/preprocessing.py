"""
SEBAL-GEE v4 — M1: Preprocessing
=================================
Landsat 8/9 C2L2 tasvirlarini tozalash va tayyorlash.

Vazifalar:
  1. ImageCollection qurish (L8, L9 yoki ikkalasi)
  2. Cloud cover bo'yicha filtr
  3. QA_PIXEL bitmask — bulut, soya, qor, suv olib tashlash
  4. Scale factors qo'llash (SR → 0-1, ST → Kelvin)
  5. DEM va slope qo'shish
  6. ERA5 vaqtga moslashtirish

Input:  ROI, date_range, satellite config
Output: Toza ee.ImageCollection (har bir image tayyor)
"""

import ee
from . import config as cfg




# Config ga qo'shish
CROPLAND_COLLECTION = 'ESA/WorldCover/v200'
CROPLAND_CLASS = 40
CROP_CLOUD_MAX = 30  # ekin yerlar ustida max bulut %

# ==============================================================
# QA MASK — bulut, soya, qor olib tashlash
# ==============================================================

def apply_qa_mask(image):
    """
    QA_PIXEL band dan sifat maskasi yaratish.

    Olib tashlanadi:
      - Fill pixels (bit 0)
      - Dilated cloud (bit 1)
      - Cirrus (bit 2)
      - Cloud (bit 3)
      - Cloud shadow (bit 4)
      - Snow (bit 5)

    Suv (bit 7) — olib tashlanMAYDI, chunki SEBAL suv
    piksellarni G₀ = 0.5×Q* bilan ishlata oladi.
    Lekin alohida suv maskasi saqlanadi.
    """
    qa = image.select(cfg.BAND_NAMES['qa'])

    # Yomon piksellar maskasi — bularni OLIB TASHLAYMIZ
    bad_mask = (
        qa.bitwiseAnd(cfg.QA_BITMASK['fill'])
        .Or(qa.bitwiseAnd(cfg.QA_BITMASK['dilated_cloud']))
        .Or(qa.bitwiseAnd(cfg.QA_BITMASK['cirrus']))
        .Or(qa.bitwiseAnd(cfg.QA_BITMASK['cloud']))
        .Or(qa.bitwiseAnd(cfg.QA_BITMASK['cloud_shadow']))
        .Or(qa.bitwiseAnd(cfg.QA_BITMASK['snow']))
    )

    # Toza piksellar = bad_mask EMAS
    clear_mask = bad_mask.Not()

    # Suv maskasi — alohida band sifatida saqlaymiz
    water_mask = qa.bitwiseAnd(cfg.QA_BITMASK['water']).gt(0)

    return (image
            .updateMask(clear_mask)
            .addBands(water_mask.rename('WATER_MASK')))

# ==============================================================
# HLS QA MASK — Fmask
# ==============================================================
 
def apply_qa_mask_hls(image):
    '''HLS Fmask orqali bulut/soya/qor olib tashlash.'''
    fmask = image.select('Fmask')
 
    bad_mask = (
        fmask.bitwiseAnd(cfg.HLS_QA_BITMASK['cloud'])
        .Or(fmask.bitwiseAnd(cfg.HLS_QA_BITMASK['cloud_shadow']))
        .Or(fmask.bitwiseAnd(cfg.HLS_QA_BITMASK['adjacent']))
        .Or(fmask.bitwiseAnd(cfg.HLS_QA_BITMASK['snow']))
        .Or(fmask.bitwiseAnd(cfg.HLS_QA_BITMASK['cirrus']))
    )
 
    water_mask = fmask.bitwiseAnd(cfg.HLS_QA_BITMASK['water']).gt(0)
 
    return (image
            .updateMask(bad_mask.Not())
            .addBands(water_mask.rename('WATER_MASK')))
    
# ==============================================================
# HLS SCALE — SR tayyor, thermal Celsius → Kelvin
# ==============================================================
 
def apply_scale_factors_hls(image):
    '''HLS bandlarni Landsat formatiga moslashtirish.'''
    # Optik — allaqachon 0-1, faqat Landsat nomlariga rename
    sr = (image.select(
              ['B2',    'B3',     'B4',    'B5',    'B6',     'B7'])
          .rename(['SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B6', 'SR_B7'])
          .clamp(0.001, 1.0))
 
    # Thermal — Celsius → Kelvin
    lst = (image.select('B10')
           .add(273.15)
           .rename('LST'))
 
    return (image
            .addBands(sr, overwrite=True)
            .addBands(lst))


# ==============================================================
# SCALE FACTORS — raw DN → physical units
# ==============================================================

def apply_scale_factors(image):
    """
    C2L2 scale factors qo'llash.

    SR bands (B2-B7): DN × 0.0000275 - 0.2 → reflectance (0–1)
    ST band (B10):    DN × 0.00341802 + 149.0 → Kelvin

    SR qiymatlari 0–1 oralig'iga clamp qilinadi.
    """
    sr_bands = [
        cfg.BAND_NAMES['blue'],
        cfg.BAND_NAMES['green'],
        cfg.BAND_NAMES['red'],
        cfg.BAND_NAMES['nir'],
        cfg.BAND_NAMES['swir1'],
        cfg.BAND_NAMES['swir2'],
    ]

    st_band = cfg.BAND_NAMES['thermal']

    # Surface Reflectance — scale va clamp
    sr_scaled = (image.select(sr_bands)
                 .multiply(cfg.SCALE_FACTORS['sr_mult'])
                 .add(cfg.SCALE_FACTORS['sr_add'])
                 .clamp(0.0, 1.0))

    # Surface Temperature — Kelvin ga
    st_scaled = (image.select(st_band)
                 .multiply(cfg.SCALE_FACTORS['st_mult'])
                 .add(cfg.SCALE_FACTORS['st_add'])
                 .rename('LST'))

    # Asl bandlarni yangilangan qiymatlarga almashtirish
    # QA va boshqa bandlar saqlanadi
    return (image
            .addBands(sr_scaled, overwrite=True)
            .addBands(st_scaled))


# ==============================================================
# DEM & SLOPE — SRTM 30m
# ==============================================================

def add_terrain(image, roi):
    """
    Har bir tasvirga DEM va slope qo'shish.

    DEM:   τsw hisoblash uchun (Allen 2007)
    Slope: Anchor pixel filtrida (slope < 5°)

    CRS tekshiruvi: DEM Landsat bilan bir xil proeksiyada
    reprojekt qilinadi — oldingi z₀m bug'ining oldini olish!
    """
    dem = (ee.Image(cfg.DEM['collection'])
           .select(cfg.DEM['band'])
           .rename('DEM'))

    # Landsat tasvirning CRS ini olish
    landsat_crs = image.select(cfg.BAND_NAMES['red']).projection()

    # DEM ni Landsat CRS ga reproject qilish
    # BU MUHIM — oldingi z₀m bug' CRS mismatch sababli edi!
    dem_aligned = dem.reproject(crs=landsat_crs, scale=30)

    # Slope hisoblash (degrees)
    slope = ee.Terrain.slope(dem_aligned).rename('SLOPE')

    return image.addBands(dem_aligned).addBands(slope)


# ==============================================================
# ERA5 METEOROLOGICAL DATA
# ==============================================================

def get_era5_for_image(image, roi):
    """
    Landsat tasvir sanasiga mos ERA5 ma'lumotlarini olish.

    ERA5 hourly — Landsat overpass vaqtiga eng yaqin soatni tanlaymiz.

    MUHIM: system:time_start ALLAQACHON haqiqiy UTC vaqtni o'z ichiga
    oladi. Idaho uchun ~17:30 UTC, O'zbekiston uchun ~05:30 UTC.
    Hardcoded soat ISHLATMAYMIZ — image ning o'z vaqtidan ±1 soat.

    Returns: ee.Image with ERA5 bands added
    """
    # Landsat tasvir sanasi va vaqtini olish
    # Bu ALLAQACHON to'g'ri UTC vaqt — 2024-07-07T17:30:00Z
    date = ee.Date(image.get('system:time_start'))

    # ── SEBAL Manual, Appendix 5 (B qism): instant ob-havo overpass vaqtiga
    #    CHIZIQLI INTERPOLYATSIYA qilinadi (±1 soatlik o'rtacha EMAS).
    #    ERA5 vaqt konvensiyasi (empirik tasdiqlangan, quyosh chiqishi testi):
    #      • INSTANT bandlar (T2m, dewpoint, bosim, u/v shamol) — yorliq vaqtida
    #        AYNI QIYMAT   → Flag_period = 1 (nuqtaviy)
    #      • AKKUMULYATIV (ssrd/strd _hourly) — yorliq `T` = [T−1h, T] oralig'i
    #        → effektiv markazi T−0.5h   → Flag_period = 0 (davr OXIRI)
    #    Shuning uchun ikki guruh ALOHIDA og'irlik bilan interpolyatsiya qilinadi.
    day0 = ee.Date(date.format('YYYY-MM-dd'))
    t_h = date.difference(day0, 'hour')        # yarim tundan soat (kasrli), UTC

    col = (ee.ImageCollection(cfg.ERA5['collection']).filterBounds(roi))

    def _at(h):
        """h — day0 dan soat (ee.Number); shu yorliqli ERA5 rasmi."""
        s = day0.advance(h, 'hour')
        return ee.Image(col.filterDate(s, s.advance(1, 'hour')).first())

    def _lerp(h1, w):
        """h1 va h1+1 yorliqlari orasida chiziqli interpolyatsiya (og'irlik w)."""
        a = _at(h1)
        b = _at(ee.Number(h1).add(1))
        return (a.multiply(ee.Number(1).subtract(w))
                .add(b.multiply(ee.Number(w))))

    # INSTANT: yorliqlar floor(t), floor(t)+1;  og'irlik = kasr qism
    h_inst = t_h.floor()
    era5_inst = _lerp(h_inst, t_h.subtract(h_inst))

    # AKKUMULYATIV: markazlar T−0.5 → t ni qamrovchi juftlik
    h_acc = t_h.subtract(0.5).floor().add(1)
    era5_acc = _lerp(h_acc, t_h.subtract(h_acc.subtract(0.5)))

    # ---- INSTANT bandlar (era5_inst dan) ----
    u_wind = era5_inst.select(cfg.ERA5['bands']['u_wind'])
    v_wind = era5_inst.select(cfg.ERA5['bands']['v_wind'])
    wind_speed = (u_wind.pow(2).add(v_wind.pow(2))
                  .sqrt()
                  .rename('WIND_SPEED_10M'))

    # Air temperature (K)
    air_temp = era5_inst.select(cfg.ERA5['bands']['air_temp']).rename('AIR_TEMP')

    # Surface pressure (Pa)
    pressure = era5_inst.select(cfg.ERA5['bands']['pressure']).rename('PRESSURE')

    # Dewpoint temperature (K)
    dewpoint = era5_inst.select(cfg.ERA5['bands']['dewpoint']).rename('DEWPOINT')

    # ---- AKKUMULYATIV bandlar (era5_acc dan — markazi T−0.5h) ----
    # ssrd/strd _hourly: J/m² (bir soatlik yig'indi)
    ssrd = era5_acc.select(cfg.ERA5['bands']['ssrd']).rename('SSRD')
    strd = era5_acc.select(cfg.ERA5['bands']['strd']).rename('STRD')

    # Bitta image ga birlashtirish
    era5_combined = (wind_speed
                        .addBands(air_temp)
                        .addBands(pressure)
                        .addBands(ssrd)
                        .addBands(strd)
                        .addBands(dewpoint))

    return image.addBands(era5_combined)


# ==============================================================
# AIR DENSITY — barometrik formula
# ==============================================================

def add_air_density(image):
    """
    Havo zichligini hisoblash.

    ρₐ = P / (R_specific × T)

    P — ERA5 surface pressure (Pa)
    T — ERA5 air temperature (K)
    R_specific = 287.058 J/(kg·K)
    """
    R_SPECIFIC = 287.058  # J/(kg·K)

    pressure = image.select('PRESSURE')
    air_temp = image.select('AIR_TEMP')

    rho_air = pressure.divide(air_temp.multiply(R_SPECIFIC)).rename('RHO_AIR')

    return image.addBands(rho_air)


# ==============================================================
# MAIN: Build clean ImageCollection
# ==============================================================

# ==============================================================
# COLLECTION BUILDER — Landsat yoki HLS
# ==============================================================

def _best_per_date_factory(collection):
    """
    Berilgan kolleksiya uchun 'per-date mosaic' funksiyasi yaratadi.
    
    Bir kunda bir nechta tile bo'lsa — birlashtirib bitta image qiladi,
    lekin BIRINCHI tile ning REAL UTC overpass vaqtini saqlaydi.
    Bu ERA5 ni to'g'ri yuklash uchun MUHIM.
    """
    def best_per_date(date_str):
        date = ee.Date(date_str)
        daily = collection.filterDate(date, date.advance(1, 'day'))
        # ⭐ REAL UTC overpass vaqti (NOT date.millis() = 00:00)
        actual_time = ee.Image(daily.first()).get('system:time_start')
        return (daily.mosaic()
                .set('system:time_start', actual_time)
                .copyProperties(daily.first(),
                                ['CLOUD_COVERAGE', 'CLOUD_COVER',
                                 'WRS_PATH', 'WRS_ROW', 'SUN_ELEVATION']))
    return best_per_date


def build_collection(roi, date_start, date_end, satellite='BOTH',
                     cloud_max=None, mosaic_same_date=True,
                     wrs_path=None, wrs_row=None,
                     mgrs_tile=None, cloud_roi=None, cloud_use_cropland=True):
    '''
    Landsat yoki HLS ImageCollection qurish.

    satellite: 'L8', 'L9', 'BOTH', 'HLS'
    wrs_path/wrs_row: Landsat tile filter
    mgrs_tile: HLS tile filter (masalan 'T42TVK')
    '''
    if cloud_max is None:
        cloud_max = cfg.PIPELINE['cloud_max_percent']

    # ── HLS REJIM ──────────────────────────────────────
    if satellite == 'HLS':
        merged = (ee.ImageCollection(cfg.HLS_COLLECTION)
                  .filterBounds(roi)
                  .filterDate(date_start, date_end)
                  .filter(ee.Filter.lt('CLOUD_COVERAGE', cloud_max)))

        # MGRS tile filtr
        if mgrs_tile is not None:
            tile_id = mgrs_tile if mgrs_tile.startswith('T') else f'T{mgrs_tile}'
            merged = merged.filter(
                ee.Filter.stringContains('system:index', tile_id))

        # Cropland cloud precheck
        merged = filter_by_crop_cloud_hls(merged, roi, cfg.CROP_CLOUD_MAX)

        # Sana bo'yicha mosaic (per-date)
        if mgrs_tile is not None:
            distinct_dates = (merged
                .aggregate_array('system:time_start')
                .map(lambda t: ee.Date(t).format('YYYY-MM-dd'))
                .distinct())
            best_per_date = _best_per_date_factory(merged)
            merged = ee.ImageCollection(distinct_dates.map(best_per_date))

        # HLS preprocessing
        def preprocess_hls(image):
            processed = apply_qa_mask_hls(image)
            processed = apply_scale_factors_hls(processed)
            processed = add_terrain(processed, roi)
            processed = get_era5_for_image(processed, roi)
            processed = add_air_density(processed)
            return processed

        clean_collection = merged.map(preprocess_hls)
        return clean_collection

    # ── LANDSAT REJIM ────────────────────
    if satellite == 'BOTH':
        collections = ['L8', 'L9']
    else:
        collections = [satellite]

    merged = None
    for sat_key in collections:
        collection_id = cfg.LANDSAT_COLLECTIONS[sat_key]
        col = (ee.ImageCollection(collection_id)
               .filterBounds(roi)
               .filterDate(date_start, date_end)
               .filter(ee.Filter.lt('CLOUD_COVER', cloud_max)))
        if merged is None:
            merged = col
        else:
            merged = merged.merge(col)

    # WRS filtr
    if wrs_path is not None:
        merged = merged.filter(ee.Filter.eq('WRS_PATH', wrs_path))
    if wrs_row is not None:
        merged = merged.filter(ee.Filter.eq('WRS_ROW', wrs_row))

    # Cloud precheck — default keng ROI cropland; polygon rejimida cloud_roi=dala
    cloud_geom = cloud_roi if cloud_roi is not None else roi
    cloud_scale = 100 if cloud_use_cropland else 30
    merged = filter_by_crop_cloud(merged, cloud_geom, cfg.CROP_CLOUD_MAX,
                                  cloud_use_cropland, cloud_scale)

    # Sana bo'yicha mosaic (per-date) — Landsat
    if wrs_path is not None:
        distinct_dates = (merged
            .aggregate_array('system:time_start')
            .map(lambda t: ee.Date(t).format('YYYY-MM-dd'))
            .distinct())
        best_per_date = _best_per_date_factory(merged)   # ⭐ shu yerda yaratiladi
        merged = ee.ImageCollection(distinct_dates.map(best_per_date))

    # Landsat preprocessing
    def preprocess_image(image):
        processed = apply_qa_mask(image)
        processed = apply_scale_factors(processed)
        processed = add_terrain(processed, roi)
        processed = get_era5_for_image(processed, roi)
        processed = add_air_density(processed)
        return processed

    clean_collection = merged.map(preprocess_image)

    # ERA5 dan keyingi mosaic — bir kunda bir nechta path yoki tile bo'lsa
    if mosaic_same_date:
        distinct_dates = (clean_collection
                          .aggregate_array('system:time_start')
                          .map(lambda t: ee.Date(t).format('YYYY-MM-dd'))
                          .distinct())

        def mosaic_by_date(date_str):
            date = ee.Date(date_str)
            daily = clean_collection.filterDate(date, date.advance(1, 'day'))
            # ⭐ REAL vaqt — kelajak xavfsizligi uchun
            actual_time = ee.Image(daily.first()).get('system:time_start')
            return (daily.mosaic()
                    .set('system:time_start', actual_time)
                    .copyProperties(daily.first(),
                                    ['CLOUD_COVERAGE', 'CLOUD_COVER',
                                     'SUN_ELEVATION']))

        clean_collection = ee.ImageCollection(
            distinct_dates.map(mosaic_by_date))

    return clean_collection

# def build_collection(roi, date_start, date_end, satellite='BOTH',
#                      cloud_max=None, mosaic_same_date=True,
#                      wrs_path=None, wrs_row=None,
#                      mgrs_tile=None):
#     '''
#     Landsat yoki HLS ImageCollection qurish.
 
#     satellite: 'L8', 'L9', 'BOTH', 'HLS'
#     wrs_path/wrs_row: Landsat tile filter
#     mgrs_tile: HLS tile filter (masalan 'T42TVK')
#     '''
#     if cloud_max is None:
#         cloud_max = cfg.PIPELINE['cloud_max_percent']
 
#     # ── HLS REJIM ──────────────────────────────────────
#     if satellite == 'HLS':
#         merged = (ee.ImageCollection(cfg.HLS_COLLECTION)
#                   .filterBounds(roi)
#                   .filterDate(date_start, date_end)
#                   .filter(ee.Filter.lt('CLOUD_COVERAGE', cloud_max)))
 
#         # MGRS tile filtr
#         if mgrs_tile is not None:
#             tile_id = mgrs_tile if mgrs_tile.startswith('T') else f'T{mgrs_tile}'
#             merged = merged.filter(
#                 ee.Filter.stringContains('system:index', tile_id))
 
#         # Cropland cloud precheck
#         merged = filter_by_crop_cloud_hls(merged, roi, cfg.CROP_CLOUD_MAX)
 
#         # Sana bo'yicha eng yaxshi
#         if mgrs_tile is not None:
#             distinct_dates = (merged
#                 .aggregate_array('system:time_start')
#                 .map(lambda t: ee.Date(t).format('YYYY-MM-dd'))
#                 .distinct())
 
#             def best_per_date(date_str):
#                 date = ee.Date(date_str)
#                 daily = merged.filterDate(date, date.advance(1, 'day'))
#                 # ⭐ REAL UTC overpass vaqtini saqlash (ERA5 to'g'ri yuklash uchun)
#                 actual_time = ee.Image(daily.first()).get('system:time_start')
#                 return (daily.mosaic()
#                         .set('system:time_start', actual_time)
#                         .copyProperties(daily.first(), ['CLOUD_COVERAGE']))
 
#             merged = ee.ImageCollection(distinct_dates.map(best_per_date))
 
#         # HLS preprocessing
#         def preprocess_hls(image):
#             processed = apply_qa_mask_hls(image)
#             processed = apply_scale_factors_hls(processed)
#             processed = add_terrain(processed, roi)
#             processed = get_era5_for_image(processed, roi)
#             processed = add_air_density(processed)
#             return processed
 
#         clean_collection = merged.map(preprocess_hls)
#         return clean_collection
 
#     # ── LANDSAT REJIM (o'zgarmagan) ────────────────────
#     if satellite == 'BOTH':
#         collections = ['L8', 'L9']
#     else:
#         collections = [satellite]
 
#     merged = None
#     for sat_key in collections:
#         collection_id = cfg.LANDSAT_COLLECTIONS[sat_key]
#         col = (ee.ImageCollection(collection_id)
#                .filterBounds(roi)
#                .filterDate(date_start, date_end)
#                .filter(ee.Filter.lt('CLOUD_COVER', cloud_max)))
#         if merged is None:
#             merged = col
#         else:
#             merged = merged.merge(col)
 
#     # WRS filtr
#     if wrs_path is not None:
#         merged = merged.filter(ee.Filter.eq('WRS_PATH', wrs_path))
#     if wrs_row is not None:
#         merged = merged.filter(ee.Filter.eq('WRS_ROW', wrs_row))
 
#     # Cropland cloud precheck
#     merged = filter_by_crop_cloud(merged, roi, cfg.CROP_CLOUD_MAX)
 
#     # Sana bo'yicha eng yaxshi
#     if wrs_path is not None:
#         distinct_dates = (merged
#             .aggregate_array('system:time_start')
#             .map(lambda t: ee.Date(t).format('YYYY-MM-dd'))
#             .distinct())
 
#         # def best_per_date1(date_str):
#         #     date = ee.Date(date_str)
#         #     daily = merged.filterDate(date, date.advance(1, 'day'))
#         #     return daily.sort('CLOUD_COVER').first()
 
#         merged = ee.ImageCollection(distinct_dates.map(best_per_date))
 
#     # Landsat preprocessing
#     def preprocess_image(image):
#         processed = apply_qa_mask(image)
#         processed = apply_scale_factors(processed)
#         processed = add_terrain(processed, roi)
#         processed = get_era5_for_image(processed, roi)
#         processed = add_air_density(processed)
#         return processed
 
#     clean_collection = merged.map(preprocess_image)
 
#     if mosaic_same_date:
#         distinct_dates = (clean_collection
#                           .aggregate_array('system:time_start')
#                           .map(lambda t: ee.Date(t).format('YYYY-MM-dd'))
#                           .distinct())
 
#         def mosaic_by_date(date_str):
#             date = ee.Date(date_str)
#             daily = clean_collection.filterDate(date, date.advance(1, 'day'))
#             mosaic = daily.mosaic()
#             return mosaic.set('system:time_start', date.millis())
 
#         clean_collection = ee.ImageCollection(
#             distinct_dates.map(mosaic_by_date))
 
#     return clean_collection

# # ==============================================================
# UTILITY: Collection info
# ==============================================================

def collection_info(collection):
    """
    Collection haqida qisqacha ma'lumot.

    Returns: dict with count, dates, satellites
    """
    # Bitta getInfo() bilan ikkala qiymatni olish (so'rovlar sonini kamaytiradi)
    info = ee.Dictionary({
        'count': collection.size(),
        'dates': (collection.aggregate_array('system:time_start')
                  .map(lambda t: ee.Date(t).format('YYYY-MM-dd'))),
    }).getInfo()

    return {
        'image_count': info['count'],
        'dates': info['dates'],
    }
    
def get_cropland_mask():
    """ESA WorldCover 2021: Map == 40 cropland."""
    worldcover = ee.ImageCollection(CROPLAND_COLLECTION).first()
    cropland = worldcover.select('Map').eq(CROPLAND_CLASS).rename('CROPLAND')
    return cropland


def filter_by_crop_cloud(collection, roi, max_pct, use_cropland=True, scale=100):
    """
    `roi` ustidagi bulut % bo'yicha precheck — har sahna KETMA-KET.

    use_cropland / scale → add_crop_cloud_pct ga uzatiladi. Polygon rejimida
    use_cropland=False (dala ustida tekshiruv), scale=30.

    Server-side variant (map + filter) GEE da barcha sahnalarning
    reduceRegion larini parallel ishlatib, "Too many concurrent
    aggregations" xatosini beradi. Bu yerda har sahna uchun bitta
    so'rov yuboriladi, METRIC dagi kabi.
    """
    ids = collection.aggregate_array('system:index').getInfo()
    if not ids:
        return collection.filter(ee.Filter.inList('system:index', ['__none__']))

    good_ids = []
    for img_id in ids:
        img = collection.filter(ee.Filter.eq('system:index', img_id)).first()
        pct = ee.Number(
            add_crop_cloud_pct(img, roi, use_cropland, scale)
            .get('crop_cloud_pct')).getInfo()
        if pct < max_pct:
            print(f"    ✅ Cloud precheck OK: {pct:.1f}% "
                  f"(cropland, limit={max_pct}%)  [{img_id}]")
            good_ids.append(img_id)
        else:
            print(f"    ⚠️  Cloud precheck FAIL: {pct:.1f}% "
                  f"(cropland, limit={max_pct}%) → skip  [{img_id}]")

    if not good_ids:
        good_ids = ['__none__']   # bo'sh ro'yxat — hech narsa o'tmaydi
    return collection.filter(ee.Filter.inList('system:index', good_ids))

def filter_by_crop_cloud_hls(collection, roi, max_pct):
    '''HLS uchun cropland ustidagi bulut filtri.'''
        # Bo'sh collection tekshiruvi
    n_total = collection.size().getInfo()
    if n_total == 0:
        print(f"      ⚠️ HLS tasvir topilmadi — skip")
        return ee.ImageCollection([])
    
    cropland = get_cropland_mask()
    image_list = collection.toList(collection.size())
    n = image_list.size().getInfo()
 
    keep = []
    for i in range(n):
        img = ee.Image(image_list.get(i))
        try:
            pct = add_crop_cloud_pct_hls(img, roi).get('crop_cloud_pct')
            pct_val = ee.Number(pct).getInfo()
            if pct_val <= max_pct:
                keep.append(img)
                d = ee.Date(img.get('system:time_start')).format('YYYY-MM-dd').getInfo()
                print(f"      ✅ {d}: ekin bulut {pct_val:.1f}%")
            else:
                d = ee.Date(img.get('system:time_start')).format('YYYY-MM-dd').getInfo()
                print(f"      ⚠️ {d}: ekin bulut {pct_val:.1f}% > {max_pct}% → skip")
        except:
            keep.append(img)
 
    if not keep:
        return ee.ImageCollection([])
    return ee.ImageCollection(keep)

def add_crop_cloud_pct_hls(image, roi):
    '''HLS Fmask orqali cropland ustidagi bulut foizi.'''
    fmask = image.select('Fmask')
 
    bad = (fmask.bitwiseAnd(cfg.HLS_QA_BITMASK['cloud'])
           .Or(fmask.bitwiseAnd(cfg.HLS_QA_BITMASK['cloud_shadow']))
           .Or(fmask.bitwiseAnd(cfg.HLS_QA_BITMASK['adjacent'])))
 
    cropland = get_cropland_mask()
    crop_bad = bad.updateMask(cropland).unmask(0)
 
    crop_cloud_pct = crop_bad.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=roi,
        scale=120,
        maxPixels=1e8,
        bestEffort=True
    ).get('Fmask')
 
    crop_cloud_pct = ee.Number(
        ee.Algorithms.If(crop_cloud_pct, crop_cloud_pct, 1)
    )
 
    return image.set('crop_cloud_pct', crop_cloud_pct.multiply(100))

def add_crop_cloud_pct(image, roi, use_cropland=True, scale=100):
    """
    QA_PIXEL orqali `roi` ustidagi yomon (bulut/soya/qor/fill) piksel foizini
    hisoblaydi (image property: crop_cloud_pct). Masklamaydi.

    use_cropland=True  (default) → faqat ESA cropland ustida (keng ROI uchun).
    use_cropland=False → butun `roi` ustida cropland maskasiz — POLYGON rejimi
      uchun: bulut tekshiruvi aynan dala (footprint polygon) ustida bo'ladi.
      (Keng kalibratsiya ROI'da bulut bo'lsa ham, dala toza sahna qoladi.)
    """
    qa = image.select(cfg.BAND_NAMES['qa'])

    bad_mask = (
        qa.bitwiseAnd(cfg.QA_BITMASK['fill'])
        .Or(qa.bitwiseAnd(cfg.QA_BITMASK['dilated_cloud']))
        .Or(qa.bitwiseAnd(cfg.QA_BITMASK['cirrus']))
        .Or(qa.bitwiseAnd(cfg.QA_BITMASK['cloud']))
        .Or(qa.bitwiseAnd(cfg.QA_BITMASK['cloud_shadow']))
        .Or(qa.bitwiseAnd(cfg.QA_BITMASK['snow']))
    ).gt(0).rename('CLD')

    if use_cropland:
        bad = bad_mask.updateMask(get_cropland_mask().clip(roi))
    else:
        bad = bad_mask

    d = bad.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=roi,
        scale=scale,
        maxPixels=1e8,
        bestEffort=True
    )

    # Null-guard: kalit BOR bo'lsa qiymatni olamiz (0.0 = to'liq toza — VALID!),
    # kalit YO'Q bo'lsa (bo'sh hudud) → fallback 1 (=100%). DIQQAT: eski
    # If(pct,pct,1) 0.0 ni ham FALSY deb 100% qilardi — kichik toza dala uchun
    # xato edi; .contains() bilan 0.0 to'g'ri saqlanadi.
    crop_cloud_pct = ee.Number(
        ee.Algorithms.If(d.contains('CLD'), d.get('CLD'), 1)
    )

    return image.set('crop_cloud_pct', crop_cloud_pct.multiply(100))