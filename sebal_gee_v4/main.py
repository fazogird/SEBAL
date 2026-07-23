"""
SEBAL-GEE v4 — Main Pipeline (Production)
===========================================
Ishlatish: run_sebal.py dan chaqiriladi.

Xususiyatlar:
  - Oylik: har produkt alohida TIF (True/False)
  - Kunlik: multi-band (1 fayl per sahna)
  - Tile-based: WRS path/row bo'yicha alohida ishlash
  - ROI: gaul, rectangle, shapefile, point
"""

import ee

from . import config as cfg
from . import preprocessing
from . import surface_props
from . import radiation
from . import energy_balance
from . import daily_et
from . import ref_et
from . import et_decomposition, soil_moisture, biomass, irrigation


# ==============================================================
# DAILY BAND SETS
# ==============================================================

DAILY_BANDS_SEBAL_B = [
    'ET_24', 'LAMBDA_E', 'H', 'RN', 'G0', 'EVAP_FRAC', 'NDVI', 'LST','LAI',
]

DAILY_BANDS_PYSEBAL = [
    'ET_24', 'ETREF_24', 'ETPOT_24', 'ET_DEFICIT',
    'KC', 'KC_MAX', 'ADV_FACTOR',
    'TACT_24', 'EACT_24', 'TPOT_24', 'T_DEFICIT',
    'BENEFICIAL_FRACTION', 'MOISTURE_STRESS',
    'TOP_SOIL_MOISTURE', 'ROOT_ZONE_MOISTURE', 'SM_WETNESS',
    'FPAR', 'APAR', 'LUE',
    'BIOMASS_PROD', 'WATER_PRODUCTIVITY', 'BIOMASS_DEFICIT',
    'IRRIGATION_CLASS', 'IRRIGATION_DEPTH',
    'NDVI', 'LST',
]


# ==============================================================
# WRS TILES — path/row aniqlash
# ==============================================================

def detect_wrs_tiles(roi, date_start, date_end, satellite='BOTH', cloud_max=20):
    """
    ROI ichidagi WRS path/row larni aniqlash.
    Qaysi tilelar mavjud ekanini ko'rsatadi.
    """
    collections = []
    if satellite in ('BOTH', 'L8'):
        collections.append('LANDSAT/LC08/C02/T1_L2')
    if satellite in ('BOTH', 'L9'):
        collections.append('LANDSAT/LC09/C02/T1_L2')

    tiles = set()
    for col_id in collections:
        col = (ee.ImageCollection(col_id)
               .filterBounds(roi)
               .filterDate(date_start, date_end)
               .filter(ee.Filter.lt('CLOUD_COVER', cloud_max)))

        props = col.aggregate_array('WRS_PATH').zip(
            col.aggregate_array('WRS_ROW')).distinct().getInfo()

        for p, r in props:
            tiles.add((p, r))

    return sorted(tiles)


def get_tile_geometry(path, row):
    """WRS path/row geometriyasini Landsat C2 dan olish."""
    tile = (ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
            .filter(ee.Filter.eq('WRS_PATH', path))
            .filter(ee.Filter.eq('WRS_ROW', row))
            .first()
            .geometry())
    return tile


def get_hls_tile_geometry(mgrs_tile, date_start='2024-01-01',
                          date_end='2027-01-01'):
    """
    HLS (MGRS) tile footprint geometriyasi — granula chegarasidan.
    Sana filtri SHART: butun arxivni stringContains bilan skanlamaslik
    uchun (aks holda "Computation timed out").
    """
    tid = mgrs_tile if mgrs_tile.startswith('T') else f'T{mgrs_tile}'
    img = (ee.ImageCollection(cfg.HLS_COLLECTION)
           .filterDate(date_start, date_end)
           .filter(ee.Filter.stringContains('system:index', tid))
           .first())
    return ee.Image(img).geometry()

# ==============================================================
# BITTA TILE NI ISHLASH
# ==============================================================

def process_tile(roi, date_start, date_end, mode, satellite, cloud_max,
                 tile_label='', anchor_method='default',
                 anchor_mode='median_anchor',
                 cloud_roi=None, cloud_use_cropland=True,
                 ref_type='alfalfa', utc_offset=None, etr24_source='era5',
                 sloping_terrain=False):
    """
    Bitta ROI/tile uchun SEBAL pipeline.
    Returns: list of processed scene images
    """
    prefix = f"  [{tile_label}]" if tile_label else "  "

    # SEBAL_ID: anchor BITTA NUQTA bo'lishi shart (cold/hot dT hamda hot suv
    # balansi AYNI bir pikselga tayanadi — izchillik). Metod (cimec/plan/…)
    # kandidatlarni topadi, point_anchor ulardan bittasini oladi.
    if mode == 'SEBAL_ID' and anchor_mode != 'point_anchor':
        print(f"{prefix} ℹ️ SEBAL_ID → anchor_mode='point_anchor' (bitta nuqta) majburiy")
        anchor_mode = 'point_anchor'

    # Mahalliy standart vaqt zonasi (SEBAL Manual App.5-A; DST YO'Q).
    # Kunlik oyna (Rs24 / ETr24) shu offsetga ko'ra mahalliy kunga bog'lanadi.
    if utc_offset is None:
        utc_offset = daily_et.utc_offset_from_roi(roi)
        print(f"{prefix} 🕒 utc_offset avtomatik = {utc_offset:+d} soat "
              f"(zona markazi ≈ boylam/15; aniq bo'lmasa qo'lda bering)")

    # QIYA YUZA rejimi (Tasumi Ch.V): z_ws — "ob-havo stansiyasi" balandligi
    # (ERA5 uchun ROI o'rtacha balandligi; App.K: shamol ta'siri past)
    z_ws = 0.0
    if sloping_terrain:
        from . import sloping_terrain as slt
        dem_ref = ee.Image(cfg.DEM['collection']).select(cfg.DEM['band'])
        z_ws = slt.mean_elevation(dem_ref, roi)
        print(f"{prefix} ⛰️ sloping_terrain=True | z_ws (ROI o'rtacha) = {z_ws:.0f} m")
    # Tile label bo'lsa: P156_R032 kabi qiymatdan path/row ajratamiz
    if tile_label:
        is_hls = satellite == 'HLS'
        if is_hls:
            # HLS: tile_label = 'T42TVK'
            mgrs_tile = tile_label
            path_num = None
            row_num = None
        else:
            # Landsat: tile_label = 'P155_R33'
            mgrs_tile = None
            path_num = int(tile_label.split('_')[0].replace('P', ''))
            row_num = int(tile_label.split('_')[1].replace('R', ''))
    else:
        mgrs_tile = None
        path_num = None
        row_num = None
 
    collection = preprocessing.build_collection(
        roi=roi, date_start=date_start, date_end=date_end,
        satellite=satellite, cloud_max=cloud_max,
        mosaic_same_date=not bool(tile_label),
        wrs_path=path_num, wrs_row=row_num,
        mgrs_tile=mgrs_tile,
        cloud_roi=cloud_roi, cloud_use_cropland=cloud_use_cropland)
    info = preprocessing.collection_info(collection)

    if tile_label:
        print(
            f"{prefix} Filtrlangan: "
            f"Path={path_num} Row={row_num} → {info['image_count']} tasvir"
        )

    print(f"{prefix} Tasvirlar: {info['image_count']} | {info['dates']}")

    if info['image_count'] == 0:
        print(f"{prefix} ⚠️ Tasvir yo'q, o'tkazildi")
        return [], info

    # Surface props (mode → SEBAL_ID emissivity Eq.4.28 uchun)
    collection = collection.map(lambda im: surface_props.compute_all(im, mode))

    # ---- Anchor zonalari — TILE uchun BIR MARTA (cold=cropland, hot=bare+shrub) ----
    # (radiation'dan OLDIN — SEBAL_B L↓ Tref cold_mask'ga bog'liq.)
    cold_mask, hot_mask = energy_balance.compute_tile_anchor_zones(roi)

    # Radiation — mode L↓ usulini tanlaydi (SEBAL_B empirik Tref, yangiliklar ERA5)
    collection = collection.map(
        lambda im: radiation.compute_all(im, mode, roi, cold_mask,
                                         sloping_terrain=sloping_terrain))

    # Energy balance — har sahna alohida
    image_list = collection.toList(collection.size())
    n = info['image_count']

    scene_images = []

    for i in range(n):
        print(f"{prefix} Sahna {i + 1}/{n}...")

        img = ee.Image(image_list.get(i))

        # ---- L↓ Tref manbai (SEBAL_B/pysebal empirik) — fallback ishladimi? ----
        # radiation.compute_incoming_longwave xususiyat sifatida yozib qo'ygan;
        # bu yerda (map'dan tashqarida) bir marta o'qib print qilamiz.
        _tref_src = img.get('LDOWN_TREF_SRC').getInfo()
        if _tref_src is not None:
            _tref_val = img.get('LDOWN_TREF').getInfo()
            print(f"{prefix}   L↓ Tref: {_tref_src} = {_tref_val:.2f} K")

        # ---- Anchor tekshiruvi — YIQILISHDAN OLDIN ----
        # QIYA YUZA: anchor AYNI Ts maydonidan tanlanishi SHART — dT–Ts
        # munosabati LST_DEM bilan qurilgani uchun (energy_balance.compute_all
        # ichida). Aks holda cold/hot skalyarlari asl LST da, raster dT esa
        # LST_DEM da bo'lib, c5 (kesma) 0.0065·z ga siljib ketadi.
        img_anchor = img
        if sloping_terrain:
            from . import sloping_terrain as _slt
            img_anchor = img.addBands(_slt.lst_dem(img), overwrite=True)
        anchors = energy_balance.select_anchor_pixels(
            img_anchor, roi, cold_mask=cold_mask, hot_mask=hot_mask,
            method=anchor_method, anchor_mode=anchor_mode)

        if not anchors['valid'].getInfo():
            print(f"{prefix} ❌ Sahna {i + 1}/{n}: anchor topilmadi — "
                  f"O'TKAZIB YUBORILADI")
            continue   # bu sahna scene_images ga QO'SHILMAYDI

        img = energy_balance.compute_all(
            img, roi, cold_mask=cold_mask, hot_mask=hot_mask, anchors=anchors,
            mode=mode, sloping_terrain=sloping_terrain, z_ws=z_ws)
        img = daily_et.compute_daily_et(img, roi, mode=mode, ref_type=ref_type,
                                        utc_offset=utc_offset,
                                        etr24_source=etr24_source,
                                        sloping_terrain=sloping_terrain)

        if mode == 'pysebal':
            img = et_decomposition.compute_all(img, roi)
            img = soil_moisture.compute_all(img)
            img = biomass.compute_all(img)
            img = irrigation.compute_all(img)
        else:
            # 'SEBAL_B' rejimida ham S30 ETrF va VIIRS(kc) ishlashi uchun
            # ETREF_24 (grass, ASCE-EWRI) va KC har sahnaga qo'shiladi.
            # pysebal'da bularni et_decomposition allaqachon beradi.

            img = ref_et.compute_etref_daily(img, roi, utc_offset=utc_offset)
            kc = (img.select('ET_24')
                  .divide(img.select('ETREF_24').max(0.5))
                  .clamp(0, 2.5).rename('KC'))
            img = img.addBands(kc)

        scene_images.append(img)

    info['utc_offset'] = utc_offset   # oylik hisob shu offsetni ishlatishi uchun
    info['sloping_terrain'] = sloping_terrain
    return scene_images, info


# ==============================================================
# EXPORT — kunlik
# ==============================================================

def _export_daily(scene_images, roi, mode, folder, scale, crs,
                 tile_label=''):
    """Kunlik rasterlar — multi-band, har sahna alohida fayl."""
    bands = DAILY_BANDS_PYSEBAL if mode == 'pysebal' else DAILY_BANDS_SEBAL_B
    tasks = []

    for i, img in enumerate(scene_images):

        # GEE cache — tezlashtirish
        try:
            st = (img.select(['ET_24', 'NDVI'])
                  .reduceRegion(ee.Reducer.minMax(), roi, 1000,
                               maxPixels=1e8, bestEffort=True).getInfo())
            et_min = st.get('ET_24_min', 0)
            et_max = st.get('ET_24_max', 0)
            ndvi_max = st.get('NDVI_max', 0)
            print(f"  📊 ET: {et_min:.1f}-{et_max:.1f} mm/day | NDVI max: {ndvi_max:.2f}")
        except:
            pass
        d = (ee.Date(img.get('system:time_start'))
             .format('YYYY-MM-dd').getInfo())

        name = f'SEBAL_day_{d}'
        if tile_label:
            name = f'SEBAL_day_{d}_{tile_label}'
        available_bands = img.bandNames().getInfo()
        existing_bands = [b for b in bands if b in available_bands]
        missing_bands = [b for b in bands if b not in available_bands]

        if missing_bands:
            print(f"⚠️ Quyidagi bandlar topilmadi va export qilinmaydi: {missing_bands}")

        if not existing_bands:
            print("❌ Export bekor qilindi: so‘ralgan bandlardan hech biri image ichida yo‘q.")
            return None

        task = ee.batch.Export.image.toDrive(
            image=img.select(existing_bands).toFloat(),
            description=name, folder=folder, fileNamePrefix=name,
            region=roi, scale=scale, crs=crs,
            maxPixels=1e13, fileFormat='GeoTIFF')
        
        task.start()
        if task is not None:
            tasks.append(task)
        print(f"  ✅ {name} ({len(existing_bands)} band)")

    return tasks


# ==============================================================
# EXPORT — oylik (har produkt ALOHIDA raster)
# ==============================================================
 
def _viirs_export_month(scenes, info, tile_roi, year, month, month_key,
                        folder, scale, crs, tile_label,
                        viirs_mode, viirs_model, viirs_qa, viirs_fill, tasks):
    """
    Bitta oy uchun VIIRS-kuchaytirilgan oylik ET (tile ichida) → export.
    SEBAL o'zgarmaydi; faqat oylik ET ni VIIRS daily seriyasidan quradi.
    """
    import calendar
    from . import viirs_downscaling as vds

    days = calendar.monthrange(year, month)[1]
    m_start = f'{year}-{month:02d}-01'
    m_end = f'{year}-{month:02d}-{days:02d}'

    # Shu oydagi anchor sahnalar
    idx = [i for i, d in enumerate(info['dates']) if d[:7] == month_key]
    m_scenes = [scenes[i] for i in idx]
    m_info = {'dates': [info['dates'][i] for i in idx]}
    if not m_scenes:
        print(f"  ⚠️ VIIRS {month_key}: anchor yo'q")
        return

    try:
        monthly = vds.build_tile_monthly_et_viirs(
            m_scenes, m_info, tile_roi, m_start, m_end,
            viirs_mode, viirs_model, viirs_qa, viirs_fill)
        suffix = f'_{tile_label}' if tile_label else ''
        name = f'SEBAL_VIIRS_ET_{month_key}{suffix}'
        task = ee.batch.Export.image.toDrive(
            image=monthly.toFloat(), description=name, folder=folder,
            fileNamePrefix=name, region=tile_roi, scale=scale, crs=crs,
            maxPixels=1e13, fileFormat='GeoTIFF')
        task.start()
        tasks.append(task.id)
        print(f"  ✅ VIIRS ET {month_key} export boshlandi")
    except Exception as e:
        print(f"  ⚠️ VIIRS ET {month_key}: {e}")


def _s30_export_month(scenes, info, tile_roi, year, month, month_key,
                      folder, scale, crs, tile_label,
                      s30_model, s30_qa, s30_fill, cloud_max, tasks,
                      s30_cropland_only=False, s30_validate=False):
    """
    Bitta oy uchun HLS S30 ETrF regressiya oylik ET (tile ichida) → export.
    ET_daily = ETrF × ETREF_24_daily. SEBAL o'zgarmaydi.
    Diagnostika CSV (har anchor R²/N/eng yaqin S30) ham yoziladi.
    """
    import calendar
    import csv
    from . import hls_s30_etrf as s30

    days = calendar.monthrange(year, month)[1]
    m_start = f'{year}-{month:02d}-01'
    m_end = f'{year}-{month:02d}-{days:02d}'

    idx = [i for i, d in enumerate(info['dates']) if d[:7] == month_key]
    m_scenes = [scenes[i] for i in idx]
    m_info = {'dates': [info['dates'][i] for i in idx]}
    if not m_scenes:
        print(f"  ⚠️ S30 {month_key}: anchor yo'q")
        return

    mgrs = tile_label if (tile_label and tile_label.startswith('T')) else None
    suffix = f'_{tile_label}' if tile_label else ''

    try:
        monthly, diag = s30.build_tile_monthly_etrf_s30(
            m_scenes, m_info, tile_roi, m_start, m_end,
            s30_model, s30_qa, s30_fill, cloud_max, mgrs,
            cropland_only=s30_cropland_only)

        name = f'SEBAL_S30_ET_{month_key}{suffix}'
        task = ee.batch.Export.image.toDrive(
            image=monthly.toFloat(), description=name, folder=folder,
            fileNamePrefix=name, region=tile_roi, scale=scale, crs=crs,
            maxPixels=1e13, fileFormat='GeoTIFF')
        task.start()
        tasks.append(task.id)
        print(f"  ✅ S30 ET {month_key} export boshlandi")

        # Diagnostika CSV (har anchor)
        if diag:
            cname = f'S30_diag_{month_key}{suffix}.csv'
            with open(cname, 'w', newline='', encoding='utf-8') as f:
                w = csv.DictWriter(f, fieldnames=list(diag[0].keys()))
                w.writeheader()
                w.writerows(diag)
            print(f"  💾 {cname}")

        # Hold-out validatsiya (ixtiyoriy, 2+ anchor)
        if s30_validate and len(m_scenes) >= 2:
            vrows = []
            for hi in range(len(m_scenes)):
                res = s30.validate_holdout_s30(
                    m_scenes, m_info, tile_roi, m_start, m_end, hi,
                    s30_model, s30_qa, cloud_max, mgrs)
                if 'RMSE' in res:
                    vrows.append(res)
                    print(f"    holdout {res['holdout_date']}: "
                          f"RMSE={res['RMSE']:.3f} R2={res['R2']:.3f}")
            if vrows:
                vname = f'S30_holdout_{month_key}{suffix}.csv'
                with open(vname, 'w', newline='', encoding='utf-8') as f:
                    w = csv.DictWriter(f, fieldnames=list(vrows[0].keys()))
                    w.writeheader()
                    w.writerows(vrows)
                print(f"  💾 {vname}")
    except (ee.EEException, OSError, csv.Error) as e:
        print(f"  ⚠️ S30 ET {month_key}: {e}")


def _export_monthly(scene_images, roi, year, month, mode,
                   folder, scale, crs, tile_label='',
                   save_et=True, save_biomass=True,
                   save_etref=True, save_tact=True, save_eact=True,
                   etrf_water_balance=False, ref_type='alfalfa', utc_offset=0,
                   sloping_terrain=False):
    """
    Oylik rasterlar — har produkt ALOHIDA TIF.
    True/False bilan tanlash mumkin.
    """
    from . import monthly_analytics
    tasks = []

    prefix = f'_{tile_label}' if tile_label else ''
    month_str = f'{year}-{month:02d}'

    print(f"  Oylik hisoblash {month_str}...")

    if mode == 'pysebal':
        monthly = monthly_analytics.compute_all_monthly(
            scene_images, roi, year, month)
    else:
        monthly = daily_et.compute_monthly_et(
            scene_images, roi, year, month, mode=mode,
            etrf_water_balance=etrf_water_balance,
            ref_type=ref_type, utc_offset=utc_offset,
            sloping_terrain=sloping_terrain)

    if monthly is None:
        print(f"  ❌ {month_str}: monthly image hosil bo‘lmadi.")
        return tasks

    products = []
    if save_et:
        products.append(('ET', 'ET_MONTHLY', 'mm/month'))
    if save_biomass and mode == 'pysebal':
        products.append(('Biomass', 'BIOMASS_MONTHLY', 'kg/ha/month'))
    if save_etref and mode == 'pysebal':
        products.append(('ETref', 'ETREF_MONTHLY', 'mm/month'))
    if save_tact and mode == 'pysebal':
        products.append(('Tact', 'TACT_MONTHLY', 'mm/month'))
    if save_eact and mode == 'pysebal':
        products.append(('Eact', 'EACT_MONTHLY', 'mm/month'))

    print(f"  📐 Export region: {roi.bounds().coordinates().getInfo()}")
    
    # DIQQAT: monthly image 19+ sahnaning to'liq hisob zanjirini o'z ichiga
    # oladi (har sahnada anchor reduceRegion lar bor). Unga interaktiv
    # getInfo()/bandNames()/reduceRegion qilish "Too many concurrent
    # aggregations" beradi. Shuning uchun diagnostika YO'Q — to'g'ridan
    # batch export qilinadi (batch tizimida limit yuqori).

    for prod_name, band_name, unit in products:
        try:
            prod_image = monthly.select(band_name)

            name = f'SEBAL_monthly_{prod_name}_{month_str}{prefix}'

            task = ee.batch.Export.image.toDrive(
                image=prod_image.toFloat(),
                description=name,
                folder=folder,
                fileNamePrefix=name,
                region=roi,
                scale=scale,
                crs=crs,
                maxPixels=1e13,
                fileFormat='GeoTIFF'
            )

            task.start()
            tasks.append(task.id)

            print(f"  ✅ {prod_name} export boshlandi")

        except Exception as e:
            print(f"  ⚠️ {prod_name}: {e}")

    return tasks


# ==============================================================
# MAIN RUN
# ==============================================================

def run(roi_type='gaul', date_start=None, date_end=None,
        mode='SEBAL_B', satellite='BOTH', cloud_max=70, validate=False,

        # Export sozlamalari
        export_daily=True,
        export_monthly=True,

        # Oylik produktlar (True/False)
        save_et=True,
        save_biomass=True,
        save_etref=True,
        save_tact=True,
        save_eact=True,

        # Tile sozlamalari
        tiles=None,          # [(156,32), (156,33)] yoki None=auto
        process_by_tile=False, # True=har tile alohida

        # Anchor tanlash strategiyasi (beton kaskad):
        #   'default' (hozirgi) | 'cimec' | 'plan_a' | 'plan_b' | 'pysebal'
        #   | 'cascade'. Nomlangan metod birinchi sinaladi, keyin qolganlari,
        #   avval ekin zonasida, so'ng ROI'da; hech biri chiqmasa 'default'
        #   fallback. Har qadam log'da chiqadi.
        anchor_method='default',
        # anchor_mode: kandidatlardan qiymat olish qadami (anchor_method'dan
        #   ALOHIDA emas — o'sha metod topgan kandidatlar ustida ishlaydi):
        #   'median_anchor' (default) = kandidatlar medianasi (hozirgi holat);
        #   'point_anchor' = kandidatlar ichidan BITTA ekstremal (hot=eng issiq,
        #   cold=eng sovuq; Rn−G₀ hot pikseldan). Natijaga sezilarli ta'sir qiladi.
        anchor_mode='median_anchor',

        # Export sozlamalari
        folder='SEBAL_Output',
        scale=30,
        crs='EPSG:4326',

        # VIIRS downscaling (ixtiyoriy qatlam — SEBAL o'zgarmaydi)
        use_viirs=False,            # True → oylik ET VIIRS bilan kuchaytiriladi
        viirs_mode='lambda',        # 'lambda' (EVAP_FRAC) yoki 'kc' (KC)
        viirs_model='ndvi',         # 'ndvi' | 'ndvi2' | 'multi'
        viirs_qa='lenient',         # 'lenient' | 'strict'
        viirs_fill='linear',        # 'linear' | 'nearest'
        viirs_crs=None,             # 30m fine grid CRS (aggregate/holdout uchun).
                                    # None → asosiy `crs` ishlatiladi (xavfsiz).
                                    # Har hudud uchun to'g'ri UTM zona bering,
                                    # masalan Idaho='EPSG:32611', UZB='EPSG:32642'.

        # HLS S30 ETrF regressiya (ixtiyoriy qatlam — SEBAL o'zgarmaydi)
        use_s30_etrf=False,         # True → oylik ET HLS S30 (30m) ETrF bilan
        s30_model='ndvi',           # 'ndvi'|'ndvi2'|'multi'|'multi6'
        s30_qa='lenient',           # 'lenient' | 'strict'
        s30_fill='linear',          # 'linear' | 'nearest'
        s30_cropland_only=False,    # True → yakuniy ET faqat ekin maydoniga
        s30_validate=False,         # True → hold-out validatsiya CSV

        **roi_kwargs):
    """
    SEBAL-GEE v4 production pipeline.

    Tile parametrlari:
      tiles=None, process_by_tile=False → ROI bo'yicha ishlash (kichik hududlar)
      tiles=None, process_by_tile=True  → avtomatik tile aniqlash
      tiles=[(156,32),(156,33)], process_by_tile=True → faqat shu tilelar
    """
    roi = cfg.build_roi(roi_type, **roi_kwargs)

    # VIIRS/S30 downscaling 30m fine-grid CRS. Berilmasa → asosiy export
    # `crs`. Bu ilgari viirs_downscaling.DCFG da hardcode ('EPSG:32642',
    # faqat O'zbekiston UTM) edi — boshqa hududda (masalan Idaho) noto'g'ri
    # natija berardi. Endi hudud CRS'i bilan sinxron.
    viirs_crs = viirs_crs or crs
    from . import viirs_downscaling as _vds
    _vds.DCFG['fine_crs'] = viirs_crs

    print(f"\n{'='*60}")
    print(f"  SEBAL-GEE v4 | Mode: {mode}")
    print(f"  ROI: {roi_type} | {date_start} → {date_end}")
    print(f"  Tile mode: {process_by_tile}")
    print(f"  VIIRS fine CRS: {viirs_crs}")
    print(f"  Anchor metod: {anchor_method}  | rejim: {anchor_mode}")
    print(f"{'='*60}")

    all_tasks = []

    # ---- TILE-BASED PROCESSING ----
    if process_by_tile:
        if tiles is None:
            print("\n  WRS tiles aniqlanmoqda...")
            tiles = detect_wrs_tiles(roi, date_start, date_end,
                                     satellite, cloud_max)

        print(f"  Topilgan tiles: {tiles}")

        for tile_item in tiles:
            # Tile format: Landsat = (155, 33), HLS = 'T42TVK' yoki ('T42TVK',)
            if isinstance(tile_item, str):
                # HLS: string formatda
                tile_label = tile_item
            elif isinstance(tile_item, tuple) and len(tile_item) == 2 and isinstance(tile_item[0], int):
                # Landsat: (path, row) formatda
                path, row = tile_item
                tile_label = f'P{path}_R{row}'
            elif isinstance(tile_item, tuple) and len(tile_item) == 1:
                # HLS: ('T42TVK',) formatda
                tile_label = tile_item[0]
            else:
                print(f"  ⚠️ Noma'lum tile format: {tile_item}")
                continue
 
            print(f"\\n{'='*60}")
            print(f"  TILE: {tile_label}")
            print(f"{'='*60}")

            # Tile geometriyasi — TILE CHEGARASIDA ishlash uchun.
            # HLS: MGRS granula footprint; Landsat: WRS path/row.
            # tile_roi = roi ∩ tile_geom → har tile o'z chegarasida.
            try:
                if satellite == 'HLS':
                    tile_geom = get_hls_tile_geometry(
                        tile_label, date_start, date_end)
                else:
                    tile_geom = get_tile_geometry(path, row)
                tile_roi = roi.intersection(tile_geom, ee.ErrorMargin(30))
            except Exception as e:
                print(f"  ⚠️ Tile geometriya topilmadi ({e}) → ROI ishlatiladi")
                tile_roi = roi

            scenes, info = process_tile(
                tile_roi, date_start, date_end, mode,
                satellite, cloud_max, tile_label,
                anchor_method=anchor_method, anchor_mode=anchor_mode)

            if not scenes:
                continue

            if export_daily:
                tasks = _export_daily(scenes, tile_roi, mode,
                                        folder, scale, crs, tile_label)
                all_tasks.extend(tasks)

            if export_monthly:
                from datetime import datetime
                # start_dt = datetime.strptime(date_start, '%Y-%m-%d')
                # tasks = _export_monthly(
                #     scenes, tile_roi, start_dt.year, start_dt.month,
                #     mode, folder, scale, crs, tile_label,
                #     save_et, save_biomass, save_etref, save_tact, save_eact)
                start_dt = datetime.strptime(date_start, '%Y-%m-%d')
                end_dt = datetime.strptime(date_end, '%Y-%m-%d')

                tasks = []

                # Faqat SAHNASI bor oylarni hisoblaymiz.
                # info['dates'] = ['2026-05-15', ...] (client-side).
                # Sahnasiz oy interpolyatsiyada bo'sh band beradi →
                # "Image.divide: Got 0 and 1" xatosi.
                scene_months = {d[:7] for d in info.get('dates', [])}

                current_year = start_dt.year
                current_month = start_dt.month

                while (current_year < end_dt.year) or (
                    current_year == end_dt.year and current_month <= end_dt.month
                ):
                    month_key = f'{current_year}-{current_month:02d}'
                    if month_key not in scene_months:
                        print(f"  ⏭️  {month_key}: sahna yo'q, oylik o'tkazildi")
                        if current_month == 12:
                            current_month = 1
                            current_year += 1
                        else:
                            current_month += 1
                        continue

                    # Oylik ET manbai: S30 ETrF > VIIRS > standart (lineer).
                    # Downscaling yoqilsa → standart ET o'rniga (save_et=False),
                    # boshqa produktlar (biomass/tact/eact/etref) standart yo'l.
                    if use_s30_etrf:
                        _s30_export_month(
                            scenes, info, tile_roi, current_year,
                            current_month, month_key, folder, scale, crs,
                            tile_label, s30_model, s30_qa, s30_fill,
                            cloud_max, tasks, s30_cropland_only, s30_validate)
                        month_tasks = _export_monthly(
                            scenes, tile_roi, current_year, current_month,
                            mode, folder, scale, crs, tile_label,
                            False, save_biomass, save_etref, save_tact, save_eact,
                            utc_offset=info.get('utc_offset', 0))
                    elif use_viirs:
                        _viirs_export_month(
                            scenes, info, tile_roi, current_year,
                            current_month, month_key, folder, scale, crs,
                            tile_label, viirs_mode, viirs_model, viirs_qa,
                            viirs_fill, tasks)
                        month_tasks = _export_monthly(
                            scenes, tile_roi, current_year, current_month,
                            mode, folder, scale, crs, tile_label,
                            False,  # save_et=False → VIIRS ET ishlatiladi
                            save_biomass, save_etref, save_tact, save_eact,
                            utc_offset=info.get('utc_offset', 0))
                    else:
                        month_tasks = _export_monthly(
                            scenes, tile_roi, current_year, current_month,
                            mode, folder, scale, crs, tile_label,
                            save_et, save_biomass, save_etref,
                            save_tact, save_eact,
                            utc_offset=info.get('utc_offset', 0))

                    tasks.extend(month_tasks)

                    if current_month == 12:
                        current_month = 1
                        current_year += 1
                    else:
                        current_month += 1
                all_tasks.extend(tasks)

    # ---- ROI-BASED PROCESSING (kichik hududlar) ----
    else:
        scenes, info = process_tile(
            roi, date_start, date_end, mode,
            satellite, cloud_max, anchor_method=anchor_method,
            anchor_mode=anchor_mode)

        if scenes:
            if export_daily:
                tasks = _export_daily(scenes, roi, mode,
                                        folder, scale, crs)
                all_tasks.extend(tasks)

            if export_monthly:
                from datetime import datetime
                start_dt = datetime.strptime(date_start, '%Y-%m-%d')
                end_dt = datetime.strptime(date_end, '%Y-%m-%d')

                tasks = []

                # Faqat SAHNASI bor oylar (yuqoridagi tile branch bilan bir xil).
                scene_months = {d[:7] for d in info.get('dates', [])}

                current_year = start_dt.year
                current_month = start_dt.month

                while (current_year < end_dt.year) or (
                    current_year == end_dt.year and current_month <= end_dt.month
                ):
                    month_key = f'{current_year}-{current_month:02d}'
                    if month_key not in scene_months:
                        print(f"  ⏭️  {month_key}: sahna yo'q, oylik o'tkazildi")
                        if current_month == 12:
                            current_month = 1
                            current_year += 1
                        else:
                            current_month += 1
                        continue

                    month_tasks = _export_monthly(
                        scenes,
                        roi,
                        current_year,
                        current_month,
                        mode,
                        folder,
                        scale,
                        crs,
                        '',
                        save_et,
                        save_biomass,
                        save_etref,
                        save_tact,
                        save_eact,
                        utc_offset=info.get('utc_offset', 0)
                    )

                    tasks.extend(month_tasks)

                    if current_month == 12:
                        current_month = 1
                        current_year += 1
                    else:
                        current_month += 1
                all_tasks.extend(tasks)
                
    if validate and scenes:
            print("\n  Validation: SEBAL vs OpenET (oylik)...")
            try:
                from . import validation
                from . import monthly_analytics
                from datetime import datetime
                start_dt = datetime.strptime(date_start, '%Y-%m-%d')
                
                # Oylik ET hisoblash
                monthly = monthly_analytics.compute_all_monthly(
                    scenes, roi, start_dt.year, start_dt.month)
                
                # OpenET oylik olish (mm/month)
                openet = validation.get_openet_monthly(
                    roi, start_dt.year, start_dt.month)
                
                # Sampling
                combined = (monthly.select('ET_MONTHLY').rename('ET_SEBAL')
                        .addBands(openet))
                points = ee.FeatureCollection.randomPoints(roi, 2000, seed=42)
                sampled = combined.sampleRegions(
                    collection=points, scale=30, geometries=True)
                sampled = sampled.filter(ee.Filter.notNull(['ET_SEBAL']))
                
                n = sampled.size().getInfo()
                print(f"  Valid nuqtalar: {n}")
                
                print(f"\n  {'Model':<12} {'R²':>6} {'RMSE':>8} {'MBE':>8} {'SEBAL':>8} {'OpenET':>8}")
                print(f"  {'-'*56}")
                
                for band in openet.bandNames().getInfo():
                    name = band.replace('ET_', '')
                    try:
                        st = validation.compute_statistics(sampled, 'ET_SEBAL', band)
                        si = {k: v.getInfo() if hasattr(v, 'getInfo') else v
                            for k, v in st.items()}
                        print(f"  {name:<12} {si['r2']:>6.3f} {si['rmse']:>8.1f} "
                            f"{si['mbe']:>8.1f} {si['mean_sebal']:>8.1f} "
                            f"{si['mean_openet']:>8.1f}")
                    except Exception as e:
                        print(f"  {name:<12} ❌ {e}")
            except Exception as e:
                print(f"  ⚠️ Validation: {e}")
    

    # ---- XULOSA ----
    print(f"\n{'='*60}")
    print(f"  ✅ Tayyor! {len(all_tasks)} ta export task")
    print(f"  📁 Drive → {folder}/")
    print("  🔗 https://code.earthengine.google.com/tasks")
    print(f"{'='*60}")
    return {'tasks': all_tasks}


# ==============================================================
# POLYGON-ASOSLI ET (zonal) — dala-darajasida validatsiya
# ==============================================================
# MUHIM: bu FAQAT orkestratsiya qatlami — SEBAL hisob-kitob zanjiri
# (process_tile → energy_balance/radiation/daily_et) UMUMAN o'zgarmaydi.
# Kalibratsiya kengroq hududda (polygon atrofida bufer, cold+hot anchor uchun);
# zonal extraktsiya esa polygon(lar) bo'yicha.


def _zonal_add(fc_in, image, prop_name, scale=30, reducer=None):
    """
    `image` (BITTA band) ni `fc_in` polygonlari bo'yicha reduce qilib (default
    mean), natijani to'g'ridan-to'g'ri `prop_name` atributi sifatida qo'shadi
    (Reducer.setOutputs — 'mean' oraliq nomisiz). Akkumulyatsiya: qaytgan FC
    oldingi barcha atributlarni saqlaydi, shuning uchun ketma-ket chaqiriladi.
    """
    reducer = (reducer or ee.Reducer.mean()).setOutputs([prop_name])
    return image.reduceRegions(
        collection=fc_in, reducer=reducer, scale=scale, tileScale=4)


def run_polygons(polygon_asset,
                 date_start='2024-04-01', date_end='2024-09-01',
                 mode='SEBAL_B', satellite='BOTH', cloud_max=70,
                 calib_buffer_m=15000, inner_buffer_m=-30,
                 anchor_method='cascade', anchor_mode='median_anchor',
                 out_asset=None, out_folder='SEBAL_Polygon',
                 crs='EPSG:32610', months=(4, 5, 6, 7, 8),
                 year=2024, export_rasters=False,
                 etrf_water_balance=False, ref_type='alfalfa', utc_offset=None,
                 etr24_source='era5', sloping_terrain=False):
    """
    Polygon(lar) bo'yicha SEBAL ET — zonal (mean).

    1 ta polygon bo'lsa bittasi, 100+ bo'lsa har biri uchun hisoblanadi.
    Har polygonga atribut: ET_{year}_{MM} (oylik mm) + ET_{YYYYMMDD} (har bulutsiz
    Landsat sahna kuni ET_24, mm/kun) + n_pixels, n_scenes. Natija GEE asset
    (out_asset berilsa) va Drive CSV sifatida export qilinadi.

    Parameters
    ----------
    polygon_asset : str | ee.FeatureCollection | ee.Geometry
        Polygon asset ID yoki FC/Geometry.
    calib_buffer_m : int
        Kalibratsiya ROI = polygon bounds + shu bufer (~cold+hot anchor uchun).
    inner_buffer_m : int
        Zonaldan oldin polygonga ichki bufer (chet aralash pikselni chiqarish).
        0 = to'liq polygon (fraksion vaznlash). Manfiy = eroziya.
    months : tuple
        Oylik ET hisoblanadigan oylar (default 2024 Apr–Aug).
    """
    # 1. Polygon FC
    if isinstance(polygon_asset, ee.Geometry):
        fc = ee.FeatureCollection([ee.Feature(polygon_asset)])
    else:
        fc = ee.FeatureCollection(polygon_asset)

    n_poly = fc.size().getInfo()
    print(f"\n{'='*60}")
    print(f"  POLYGON ET | polygonlar: {n_poly} | {date_start}..{date_end}")
    print(f"  Mode: {mode} | anchor: {anchor_method}/{anchor_mode}")
    print(f"{'='*60}")

    poly_geom = fc.geometry()

    # 2. Kalibratsiya ROI — polygon atrofida bufer (cold+hot anchor uchun kengroq)
    roi_calib = poly_geom.bounds().buffer(calib_buffer_m).bounds()

    # 3. Tile aniqlash — polygonni qamrab, eng ko'p bulutsiz sahnali path/row
    tiles = detect_wrs_tiles(poly_geom, date_start, date_end, satellite, cloud_max)
    if not tiles:
        print("  ❌ Polygon uchun Landsat tile topilmadi.")
        return {'tasks': []}
    best, best_n = None, -1
    for (p, r) in tiles:
        nn = (ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
              .filterBounds(poly_geom).filterDate(date_start, date_end)
              .filter(ee.Filter.eq('WRS_PATH', p))
              .filter(ee.Filter.eq('WRS_ROW', r))
              .filter(ee.Filter.lt('CLOUD_COVER', cloud_max)).size().getInfo())
        if nn > best_n:
            best_n, best = nn, (p, r)
    path, row = best
    tile_label = f'P{path}_R{row}'
    print(f"  Tile: {tile_label} ({best_n} bulutsiz L8 sahna)")

    # 4. SEBAL — MAVJUD pipeline (o'zgarmagan). MUHIM: cloud precheck DALA
    #    (polygon) ustida — keng kalibratsiya ROI'da bulut bo'lsa ham, dala
    #    toza sahnalar saqlanadi (aks holda SJV yozida ko'p clear sahna xato
    #    rad etiladi → paxta piki yo'qoladi → ET past baholanadi).
    scenes, info = process_tile(
        roi_calib, date_start, date_end, mode, satellite, cloud_max,
        tile_label=tile_label, anchor_method=anchor_method,
        anchor_mode=anchor_mode, ref_type=ref_type, utc_offset=utc_offset,
        etr24_source=etr24_source, sloping_terrain=sloping_terrain,
        cloud_roi=poly_geom, cloud_use_cropland=False)
    if not scenes:
        print("  ❌ Sahna yo'q — to'xtatildi.")
        return {'tasks': []}

    # sahna sanalari (bitta getInfo)
    scene_dates = ee.List(
        [ee.Image(s).date().format('YYYYMMdd') for s in scenes]).getInfo()

    # 5. Zonal geometriya — ichki bufer (chet piksel himoyasi) + poly_id
    work = fc.map(lambda f: f.set('poly_id', f.get('system:index')))
    if inner_buffer_m:
        work = work.map(
            lambda f: f.setGeometry(f.geometry().buffer(inner_buffer_m)))

    # 6. Oylik zonal (ET_{year}_{MM}) — akkumulyativ
    first_et = None
    for m in months:
        monthly = daily_et.compute_monthly_et(scenes, roi_calib, year, m, mode=mode,
                                              etrf_water_balance=etrf_water_balance,
                                              ref_type=ref_type,
                                              utc_offset=info['utc_offset'],
                                              etr24_source=etr24_source,
                                              sloping_terrain=sloping_terrain)
        et = monthly.select('ET_MONTHLY')
        if first_et is None:
            first_et = et
        work = _zonal_add(work, et, f'ET_{year}_{m:02d}')
        print(f"  ↪ oylik zonal: ET_{year}_{m:02d}")

    # 7. Per-sahna zonal (ET_{YYYYMMDD} — instant ET_24)
    for s, d in zip(scenes, scene_dates):
        work = _zonal_add(work, ee.Image(s).select('ET_24'), f'ET_{d}')
    print(f"  ↪ {len(scenes)} sahna zonal qo'shildi")

    # 8. QC — valid piksel soni (first oy ET_MONTHLY count) + sahna soni
    work = _zonal_add(work, first_et, 'n_pixels', reducer=ee.Reducer.count())
    work = work.map(lambda f: f.set('n_scenes', len(scenes)))

    # 9. Export — asset + CSV
    tasks = []
    stamp = f'{year}_{months[0]:02d}_{months[-1]:02d}'
    if out_asset:
        t = ee.batch.Export.table.toAsset(
            collection=work, description=f'polyET_{stamp}_asset',
            assetId=out_asset)
        t.start(); tasks.append(t.id)
        print(f"  ✅ Asset export → {out_asset}")
    t2 = ee.batch.Export.table.toDrive(
        collection=work, description=f'polyET_{stamp}_csv',
        folder=out_folder, fileFormat='CSV')
    t2.start(); tasks.append(t2.id)
    print(f"  ✅ CSV export → Drive/{out_folder}/")

    # 10. Ixtiyoriy — oylik ET raster (polygonga clip)
    if export_rasters:
        for m in months:
            monthly = daily_et.compute_monthly_et(scenes, roi_calib, year, m, mode=mode,
                                              etrf_water_balance=etrf_water_balance,
                                              ref_type=ref_type,
                                              utc_offset=info['utc_offset'],
                                              etr24_source=etr24_source,
                                              sloping_terrain=sloping_terrain)
            img = monthly.select('ET_MONTHLY').clip(poly_geom)
            name = f'polyET_raster_{year}-{m:02d}'
            tr = ee.batch.Export.image.toDrive(
                image=img.toFloat(), description=name, folder=out_folder,
                fileNamePrefix=name, region=poly_geom.bounds(), scale=30,
                crs=crs, maxPixels=1e13, fileFormat='GeoTIFF')
            tr.start(); tasks.append(tr.id)
        print(f"  ✅ {len(months)} oylik raster export (clip)")

    print(f"\n  ✅ Tayyor! {len(tasks)} export task")
    print("  🔗 https://code.earthengine.google.com/tasks")
    return {'tasks': tasks, 'scene_dates': scene_dates, 'tile': tile_label}

