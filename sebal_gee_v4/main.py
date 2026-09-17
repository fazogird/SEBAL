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
               .filter(ee.Filter.lte('CLOUD_COVER', cloud_max))) # Agar ≤20% bulsa

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
    Returns:
    tuple: (list of processed ee.Image objects, info dict)
    """
    prefix = f"  [{tile_label}]" if tile_label else "  "

    # SEBAL_Milliy_Kc: sahna bosqichi AYNAN SEBAL_Milliy kabi (NDVI + barcha band
    # kerak). Oylik ET esa Kc-quruvchi (cfg.is_kc_mode) bilan alohida quriladi —
    # u main.run'dagi ASL mode bilan compute_monthly_et'ga boradi. Shu sabab bu
    # yerda (faqat sahna ishlab chiqarish uchun) mode'ni Milliy'ga normallashtiramiz.
    if cfg.is_kc_mode(mode):
        print(f"{prefix} ℹ️ SEBAL_Milliy_Kc → sahnalar SEBAL_Milliy kabi, "
              f"oylik ET = NDVI-langan FAO-56 Kc")
        mode = 'SEBAL_Milliy'

    # SEBAL_ID: anchor BITTA NUQTA bo'lishi shart (cold/hot dT hamda hot suv
    # balansi AYNI bir pikselga tayanadi — izchillik). Metod (cimec/plan/…)
    # kandidatlarni topadi, point_anchor ulardan bittasini oladi.
    if cfg.is_id_mode(mode) and anchor_mode != 'point_anchor':
        print(f"{prefix} ℹ️ {mode} → anchor_mode='point_anchor' (bitta nuqta) majburiy")
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

        # ---- L↓ Tref manbai (FAQAT empirik L↓: SEBAL_B/pysebal) ----
        # radiation.compute_incoming_longwave xususiyat sifatida yozib qo'ygan.
        # ⚠️ SEBAL_Milliy/'yangiliklar' → ERA5 L↓ (property YO'Q) → bu getInfo BEHUDA
        # va katta tile'da interaktiv "User memory limit exceeded" beradi — SKIP.
        if mode not in ('SEBAL_Milliy', 'yangiliklar'):
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
                   sloping_terrain=False, save_cuirr=False,
                   save_prz=False, save_niwr=False, save_aw=False,
                   dr_init_img=None):
    """
    Oylik rasterlar — har produkt ALOHIDA TIF.
    True/False bilan tanlash mumkin. save_aw → ildiz-zona water-balans AW bandlari.
    dr_init_img — oldingi oy oxiridagi Dr rasteri (mavsumiy-uzluksiz AW uchun).
    Qaytaradi: (tasks, dr_end_img) — dr_end_img keyingi oyga uzatiladi (save_aw'siz None).
    Barcha rasterlar ROI ga (tile ∩ viloyat) CLIP qilinadi — bo'sh qism saqlanmaydi.
    """
    from . import monthly_analytics
    tasks = []
    dr_end_img = None

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
        return tasks, dr_end_img

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

    # CUirr / Peffec(Prz) / NIWR / AW — save_cuirr=True bo'lsa ISTALGAN rejimda.
    # ⚠️ BITTA ko'p-bandli TIF sifatida eksport qilinadi (alohida EMAS): shunda
    # umumiy og'ir suv balansi (Prz) va ETr BIR MARTA hisoblanadi — 4 alohida task
    # har biri Prz'ni qaytadan hisoblab, NIWR (+31 kun ETr) 2 soat ketardi.
    if save_cuirr or save_aw:
        try:
            combined = monthly.select('ET_MONTHLY')
            out_bands = ['ET_MONTHLY'] if save_et else []
            if save_cuirr:
                from . import consumptive_use
                cu = consumptive_use.compute_all(
                    monthly.select('ET_MONTHLY'), scene_images, roi, year, month,
                    mode=mode, utc_offset=utc_offset, ref_type=ref_type,
                    sloping_terrain=sloping_terrain, with_niwr=save_niwr)
                bn = cu.bandNames()                      # AW → AW_CUirr (CUirr/eff)
                cu = cu.select(bn, bn.map(lambda b: ee.Algorithms.If(
                    ee.String(b).equals('AW'), 'AW_CUirr', b)))
                combined = combined.addBands(cu)
                out_bands += ['CUIRR', 'AW_CUirr']
                if save_prz:
                    out_bands.append('PRZ')
                if save_niwr:
                    out_bands.append('NIWR')
            if save_aw:
                from . import root_zone_water
                awimg = root_zone_water.compute_awnet(
                    scene_images, roi, year, month, utc_offset=utc_offset,
                    dr_init_img=dr_init_img)   # None → har oy RAW dan (sug'orish talabi)
                # dr_end_img = awimg.select('DR_END')  # ZANJIR O'CHIQ (grafik "too complex")
                # Mavsumiy-uzluksiz kerak bo'lsa: yuqoridagi qatorni yoqib, dr_carry uzatiladi.
                combined = combined.addBands(awimg.select(
                    ['AW', 'AW_Eff', 'AVAILABLE_WATER', 'DP_MONTHLY', 'N_IRRIG', 'TAW']))
                out_bands += ['AW', 'AW_Eff', 'AVAILABLE_WATER', 'DP_MONTHLY',
                              'N_IRRIG', 'TAW']
            cu_name = f'SEBAL_monthly_ETCU_{month_str}{prefix}'
            cu_task = ee.batch.Export.image.toDrive(
                image=combined.select(out_bands).toFloat().clip(roi),
                description=cu_name, folder=folder, fileNamePrefix=cu_name,
                region=roi, scale=scale, crs=crs, maxPixels=1e13,
                fileFormat='GeoTIFF')
            cu_task.start(); tasks.append(cu_task.id)
            print(f"  ⚡ ET+CU/AW birlashgan → {cu_name} @ {scale}m | bandlar: {out_bands}")
            products = [p for p in products if p[1] != 'ET_MONTHLY']
        except Exception as e:
            print(f"  ⚠️ CU/AW bloki: {e}")

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
                image=prod_image.toFloat().clip(roi),
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

    return tasks, dr_end_img


# ==============================================================
# CSV ZONAL-STAT EXPORT (batch table — raster EMAS, qiymat)
# ==============================================================
# Lizimetr/parcel ustida mean+median → CSV. BATCH bo'lgani uchun interaktiv
# limitlar (5-daqiqa, "too many concurrent aggregations") YO'Q. Anchor sahnaga
# allaqachon "pishirilgan" (process_tile getInfo), shuning uchun bu yengil.

# Lizimetr bilan solishtiriladigan + SEBAL diagnostika bandlari.
# (Lizimetr o'lchaydi: Rn, G, LE→ET, LST(yuza harorat), albedo(Rs'dan), H.
#  SEBAL diagnostika: NDVI, LAI, u*, rah, dT, EF.)
CSV_LYS_BANDS = [
    # --- yakuniy / oqim ---
    'ET_24', 'ET_INST_MM_HR', 'ETRF_INST', 'LAMBDA_E', 'EVAP_FRAC',
    'RN', 'G0', 'H', 'RN_G0', 'G_RATIO',
    # --- yuza / radiometriya ---
    'LST', 'ALBEDO', 'NDVI', 'SAVI', 'LAI', 'EMISSIVITY',
    # --- 5 albedo usuli (diagnostika — qaysi oyда qaysi usul lizimetrga mos) ---
    'ALB_OLMEDO', 'ALB_LIANG', 'ALB_KE', 'ALB_TASUMI', 'ALB_AVG3',
    # --- radiatsiya komponentlari (Rn xatosini ajratish: vs lizimetr Rs/LWdn/LWup) ---
    'K_DOWN', 'L_DOWN', 'L_UP', 'TAU_SW',
    # --- aerodinamika / H motori ---
    'DTA', 'RAH', 'USTAR', 'U_200', 'L_MO', 'Z0M', 'Z0M_WIND', 'RHO_AIR', 'SLOPE',
    # --- meteo (ERA5) — mustaqil tekshirish (#7) ---
    'WIND_SPEED_10M', 'AIR_TEMP',
    # --- kunlik / referens (mavjud bo'lsa; _reduce yo'qini o'tkazib yuboradi) ---
    'RN24', 'SOLAR_FRAC', 'ETR_INST', 'ETR24',
]

# Anchor tashxis (sahna PROPERTY'lari — energy_balance yozib qo'ygan). Per-piksel
# EMAS: butun tile uchun bitta (tanlangan cold/hot piksel xususiyatlari + motor).
CSV_ANCHOR_PROPS = [
    'ANCHOR_COLD_LST', 'ANCHOR_HOT_LST', 'ANCHOR_DT_HOT', 'ANCHOR_RAH_HOT',
    'ANCHOR_H_HOT', 'ANCHOR_COLD_ALBEDO', 'ANCHOR_HOT_ALBEDO',
    'ANCHOR_COLD_NDVI', 'ANCHOR_HOT_NDVI', 'ANCHOR_COLD_WIND', 'ANCHOR_HOT_WIND',
]


def parcels_from_points(points, size_m=210, inner_buffer_m=-30):
    """
    {nom: [lon, lat]} → ee.FeatureCollection: har nuqta markazida size_m kvadrat,
    ichki bufer bilan (chekka/yo'l chiqarilgan). 'name' xususiyati saqlanadi.
    Masalan lizimetr: 210×210m dala → −30m → ~150×150m yadro.
    """
    feats = []
    for nom, lonlat in points.items():
        g = ee.Geometry.Point([lonlat[0], lonlat[1]]).buffer(size_m / 2.0).bounds()
        if inner_buffer_m:
            g = g.buffer(inner_buffer_m)
        feats.append(ee.Feature(g, {'name': nom}))
    return ee.FeatureCollection(feats)


def _export_zonal_csv(scenes, info, roi, region_fc, bands, folder,
                      tile_label, mode, utc_offset, scale=30, save_cuirr=False,
                      save_aw=False):
    """
    region_fc (parcel) ustida MEAN+MEDIAN zonal-stat → BATCH table CSV.
      • per-scene CSV: har sahna, instant+daily bandlar (date bilan)
      • per-month CSV: har oy, ET_MONTHLY (+ save_cuirr → Peffec/CUirr/NIWR)
    Raster export EMAS — faqat qiymatlar (kichik CSV → Drive).
    """
    reducer = ee.Reducer.mean().combine(ee.Reducer.median(), sharedInputs=True)
    prefix = f'_{tile_label}' if tile_label else ''
    tasks = []

    def _reduce(img, band_list, tags):
        # faqat MAVJUD bandlarni tanlaymiz (yo'q band select'ni buzmasin)
        sel = img.bandNames().filter(ee.Filter.inList('item', ee.List(band_list)))
        red = img.select(sel).reduceRegions(
            collection=region_fc, reducer=reducer, scale=scale)
        for k, v in tags.items():
            red = red.map(lambda f, kk=k, vv=v: f.set(kk, vv))
        return red

    # --- PER-SCENE (instant + daily bir CSV'da; ular ayni sahnaning bandlari) ---
    # Har qatorga sahna ANCHOR property'lari ham qo'shiladi (tanlangan cold/hot
    # piksel xususiyatlari — anchor tanlashni QC + fizik oyna sozlash uchun).
    # ALOHIDA fayllar (aniq nomlar): INST (ET-lahzalik) | DAILY_ET | INST_KOMPONENT.
    # Fayl nomiga PAPKA (model+hudud+yil) + tur + tayl → GEE Tasks/Drive'da UNIKAL.
    SCENE_GROUPS = {
        'INST':           ['ET_INST_MM_HR', 'LAMBDA_E', 'ETRF_INST', 'EVAP_FRAC',
                           'SOLAR_FRAC', 'ETR_INST'],
        'DAILY_ET':       ['ET_24'],
        'INST_KOMPONENT': ['RN', 'G0', 'H', 'ALBEDO', 'LST', 'NDVI', 'AIR_TEMP',
                           'USTAR', 'RAH', 'DTA', 'LAI', 'TAU_SW', 'EMISSIVITY'],
    }
    # SEBAL_Milliy_Kc: sahna bandlari SEBAL_Milliy bilan AYNAN bir xil (nusxa) →
    # scene/lstdiag fayllarni CHIQARMAYMIZ; Kc'dan faqat MONTHLY_ET noyob.
    if cfg.is_kc_mode(mode):
        SCENE_GROUPS = {}
    for gname, gbands in SCENE_GROUPS.items():
        sfcs = []
        for s in scenes:
            img = ee.Image(s)
            date = ee.Date(img.get('system:time_start')).format('YYYY-MM-dd')
            tags = {'date': date}
            if gname == 'INST_KOMPONENT':          # anchor QC props faqat komponent CSV'ga
                for p in CSV_ANCHOR_PROPS:
                    tags[p] = img.get(p)
            sfcs.append(_reduce(img, gbands, tags))
        gfc = ee.FeatureCollection(sfcs).flatten()
        tg = ee.batch.Export.table.toDrive(
            collection=gfc, description=f'{folder}_{gname}{prefix}',
            folder=folder, fileNamePrefix=f'{folder}_{gname}{prefix}', fileFormat='CSV')
        tg.start(); tasks.append(tg)
        print(f"  📄 CSV {gname} → {folder}_{gname}{prefix}")

    # --- LST FOOTPRINT DIAGNOSTIKA (parcel MARKAZIDA, nuqta namuna) ---
    # compute_lst_smw O'ZGARMAYDI; hech qanday tuzatish yo'q. PSF/neighborhood/
    # WV/QA bandlari L0–L3 footprint validatsiya testi uchun (ayrim CSV).
    # Kc'da SKIP (sahna = Milliy nusxasi).
    if not cfg.is_kc_mode(mode):
        _export_lst_diag_csv(scenes, region_fc, folder, tile_label, scale)

    # --- PER-MONTH (ET_MONTHLY + save_cuirr → Peffec/CUirr; save_aw → water-balans AW) ---
    mon_bands = ['ET_MONTHLY']
    if save_cuirr:
        mon_bands += ['PRZ', 'CUIRR', 'NIWR', 'AW_CU', 'ETPOT_MONTHLY',
                      'RUNOFF_MONTHLY', 'DEEPPERC_MONTHLY']       # AW_CU = CUirr/eff (eski)
    if save_aw:
        mon_bands += ['AW', 'AW_Eff', 'AVAILABLE_WATER', 'DP_MONTHLY',
                      'N_IRRIG', 'TAW']                            # water-balans (yangi)
    scene_months = sorted({d[:7] for d in info.get('dates', [])})
    month_fcs = []
    for mk in scene_months:
        yr, mo = int(mk[:4]), int(mk[5:7])
        monthly = daily_et.compute_monthly_et(scenes, roi, yr, mo, mode=mode,
                                              utc_offset=utc_offset)
        if monthly is None:
            continue
        if save_cuirr:
            # CUirr / Peffec(Prz) / NIWR (kunlik FAO-56 + CN). AW → AW_CU (water-balans
            # AW bilan to'qnashmasin).
            from . import consumptive_use
            cu = consumptive_use.compute_all(
                monthly.select('ET_MONTHLY'), scenes, roi, yr, mo,
                mode=mode, utc_offset=utc_offset)
            bn = cu.bandNames()
            cu = cu.select(bn, bn.map(lambda b: ee.Algorithms.If(
                ee.String(b).equals('AW'), 'AW_CU', b)))
            monthly = monthly.addBands(cu)
        if save_aw:
            # Ildiz-zona water-balans AW (root_zone_water) — per-crop (cfg.CROP_ASSETS)
            from . import root_zone_water
            awimg = root_zone_water.compute_awnet(
                scenes, roi, yr, mo, utc_offset=utc_offset)
            monthly = monthly.addBands(awimg.select(
                ['AW', 'AW_Eff', 'AVAILABLE_WATER', 'DP_MONTHLY', 'N_IRRIG', 'TAW']))
        month_fcs.append(_reduce(monthly, mon_bands, {'year': yr, 'month': mo}))
    if month_fcs:
        month_fc = ee.FeatureCollection(month_fcs).flatten()
        t2 = ee.batch.Export.table.toDrive(
            collection=month_fc, description=f'{folder}_MONTHLY_ET{prefix}',
            folder=folder, fileNamePrefix=f'{folder}_MONTHLY_ET{prefix}', fileFormat='CSV')
        t2.start(); tasks.append(t2)
        print(f"  📄 CSV MONTHLY_ET → {folder}_MONTHLY_ET{prefix} (mean+median)")
    return tasks


# LST footprint tashxis bandlari uchun CSV band ro'yxati (radiation.
# add_lst_footprint_diagnostics chiqaradi + mavjud EMISSIVITY/TAU_SW/RN/H/G0/ET_24).
CSV_LSTDIAG_BANDS = [
    'LST', 'LST_raw_center', 'LST_mean_3x3', 'LST_median_3x3', 'LST_mean_5x5',
    'LST_p10_5x5', 'LST_std_5x5', 'LST_psf_weighted',
    'NDVI', 'NDVI_mean_5x5', 'NDVI_std_5x5', 'ALBEDO', 'ALBEDO_std_5x5',
    'DIST_EDGE', 'ST_QA', 'EMISSIVITY', 'TAU_SW', 'WATER_VAPOR',
    'RN', 'H', 'G0', 'ET_24',
]


def _export_lst_diag_csv(scenes, region_fc, folder, tile_label, scale=30):
    """
    LST footprint TASHXIS CSV — parcel MARKAZIDA (nuqta) namuna.

    compute_lst_smw O'ZGARMAYDI; hech qanday tuzatish/ofset qo'llanmaydi. Har
    sahna uchun neighborhood (3×3/5×5), PSF-vaznli radiance-footprint, WV, ST_QA
    va boshqa tashxis bandlari parcel MARKAZIY nuqtasida (ee.Reducer.first)
    namuna olinadi — bu 30 m piksel/PSF footprintni lizimetr nuqtasiga
    moslashtiradi (parcel o'rtachasi emas). L0–L3 variant testi uchun.
    """
    from . import radiation

    # parcel → markaziy NUQTA (footprint piksel/PSF markazi)
    pts = region_fc.map(lambda f: f.setGeometry(f.geometry().centroid(1)))
    prefix = f'_{tile_label}' if tile_label else ''

    fcs = []
    for s in scenes:
        img = radiation.add_lst_footprint_diagnostics(ee.Image(s), scale)
        date = ee.Date(img.get('system:time_start')).format('YYYY-MM-dd')
        sel = img.bandNames().filter(
            ee.Filter.inList('item', ee.List(CSV_LSTDIAG_BANDS)))
        red = img.select(sel).reduceRegions(
            collection=pts, reducer=ee.Reducer.first(), scale=scale)
        red = red.map(lambda f, dd=date: f.set('date', dd))
        fcs.append(red)

    fc = ee.FeatureCollection(fcs).flatten()
    t = ee.batch.Export.table.toDrive(
        collection=fc, description=f'{folder}_lstdiag{prefix}',
        folder=folder, fileNamePrefix=f'{folder}_lstdiag{prefix}',
        fileFormat='CSV')
    t.start()
    print(f"  📄 CSV LST-diag (footprint/PSF/neighborhood, nuqta) → "
          f"{folder}_lstdiag{prefix}")
    return [t]


# ==============================================================
# MAIN RUN
# ==============================================================

def run(roi_type='gaul', date_start=None, date_end=None,
        mode='SEBAL_B', satellite='BOTH', cloud_max=70, validate=False,
        utc_offset=None,   # mahalliy standart soat (None=avto boylam/15). Siyosiy
        #   vaqt zonasi boylamdan farq qilsa QO'LDA bering: mas. Texas panhandle
        #   Central Time = -6 (avto -7 beradi — El Paso'dan tashqari xato).

        # Export sozlamalari
        export_daily=True,
        export_monthly=True,

        # CSV ZONAL-STAT (raster emas — parcel/lizimetr ustida mean+median → CSV)
        export_csv=False,     # True → csv_region ustida qiymatlarni CSV qiladi (batch)
        csv_region=None,      # ee.FeatureCollection ('name' xususiyatli parcellar).
        #                       main.parcels_from_points({'NE':[lon,lat],...}) yordamchisi bor.
        csv_bands=None,       # None → CSV_LYS_BANDS (lizimetr bilan solishtiriladiganlar)
        csv_scale=30,
        cloud_roi=None,       # bulut precheck hududi. None + export_csv → avtomatik
        #   csv_region (parcel) ustida (TEZ, faqat lizimetr uchun). Oddiy raster
        #   rejimda None qoladi → butun ROI (butun tile kerak). Qo'lda ham berish mumkin.

        # Oylik produktlar (True/False)
        save_et=True,
        save_biomass=True,
        save_etref=True,
        save_tact=True,
        save_eact=True,
        # CUirr / Peffec(Prz) / NIWR (sug'orish suvi iste'moli) — True bo'lsa
        # ISTALGAN rejimda ishlaydi (ETa shu rejim ET_MONTHLY'sidan). Kunlik
        # FAO-56 + Curve Number; NIWR ETr = ERA5 daily kunlik-timestep (yengil).
        save_cuirr=False,
        # save_aw — ILDIZ-ZONA water-balans AW (root_zone_water): AW/AW_Eff/
        # AVAILABLE_WATER/DP_MONTHLY/N_IRRIG/TAW bandlarini qo'shadi (CUirr'dan
        # ALOHIDA, fizik water-balans). SEBAL_Milliy_Kc + crop_assets bilan per-crop.
        save_aw=False,
        # CU eksporti DEFAULT: faqat CUirr + AW (30m = `scale`). Peffec(PRZ) va
        # NIWR ni ALOHIDA yoqish (default O'CHIQ). ⚠️ save_niwr=True bo'lsa OG'IR
        # ETr (31 kun) hisoblanadi — sekinlashtiradi; kerak bo'lmasa False qoldiring.
        save_prz=False,
        save_niwr=False,

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

        # Cold anchor referens-ET fraksiyasi (λET_cold = cold_etrf·ETr_inst).
        # Default 1.05 (Tasumi/SEBAL_ID). SEBAL_Milliy ground-truth test uchun
        # 0.85 (METRIC) kabi qiymatlar sinaladi. SEBAL_ID default'da o'zgarmaydi.
        cold_etrf=1.05,

        # Ekin-spetsifik z0m (h=f(LAI) → z0m=0.123·h; Tasumi/Wright R²0.98-0.99).
        # FAQAT export_csv rejimida (tadqiqot nuqtasi ekin turi ma'lum) qo'llanadi.
        # None → default z0m=0.018·LAI. Qiymatlar: cfg.CROP_H_LAI kalitlari
        # ('alfalfa','corn','potato','beans_beet_peas','spring_wheat','winter_wheat','default').
        crop_type=None,

        # Broadband albedo usuli — production 'ALBEDO' bandini tanlaydi:
        #   'config' (DEFAULT, o'zgarmagan) → cfg.OLMEDO_COEFFICIENTS (ofsetsiz)
        #   'olmedo'|'liang'|'ke'|'tasumi'|'avg3' → foydalanuvchi koeffitsientlari.
        # ⚠️ 'olmedo'(foydalanuvchi,ofsetli) ≠ 'config'(cfg). Har run'da 5 usul
        # ALB_* diagnostika bandi CSV'ga chiqadi (qaysi oyда qaysi usul lizimetrга mos).
        albedo_method='config',

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

        # PER-CROP Kc (SEBAL_Milliy_Kc): crop-code raster asset(lar) ro'yxati →
        # har piksel o'z ekinining FAO-56 koeffitsienti. None → bitta Kc (Bushland).
        crop_assets=None,

        **roi_kwargs):
    """
    SEBAL-GEE v4 production pipeline.

    Tile parametrlari:
      tiles=None, process_by_tile=False → ROI bo'yicha ishlash (kichik hududlar)
      tiles=None, process_by_tile=True  → avtomatik tile aniqlash
      tiles=[(156,32),(156,33)], process_by_tile=True → faqat shu tilelar
    """
    roi = cfg.build_roi(roi_type, **roi_kwargs)
    cfg.CROP_ASSETS = crop_assets      # PER-CROP Kc: ndvi_kc cfg.CROP_ASSETS'ni o'qiydi

    # BULUT PRECHECK HUDUDI: CSV/lizimetr rejimida FAQAT parcel ustida (tez +
    # to'g'ri — bizga Bushland ustida bulutsizlik kerak, butun shtat emas).
    # Oddiy raster rejimda cloud_roi=None → butun ROI (butun tile kerak).
    _cloud_use_cropland = True
    _csv_mode = export_csv and csv_region is not None
    if cloud_roi is None and _csv_mode:
        cloud_roi = csv_region.geometry()   # parcellar birlashgan geometriyasi (reduceRegion uchun)
        _cloud_use_cropland = False
        print("  ☁️  export_csv → bulut precheck LOKAL (csv_region parcellari; tez)")

    # ANCHOR masshtabi: CSV/lizimetr YOKI tile-asosli (katta 185km tile) rejimda 100m —
    # butun tile ~10× tez + interaktiv "User memory limit" xavfi kamayadi. Landsat
    # termal native 100m → anchor sifati yo'qolmaydi. Kichik ROI (rectangle) → 30m.
    energy_balance.ANCHOR_SCALE = 100 if (_csv_mode or process_by_tile) else 30
    if energy_balance.ANCHOR_SCALE == 100:
        print("  ⚡ anchor 100m da (katta tile — tez + xotira yengil; termal native res)")

    # Cold anchor ETrF (λET_cold = cold_etrf·ETr) — SEBAL_ID default 1.05
    energy_balance.COLD_ETRF = cold_etrf
    if cold_etrf != 1.05:
        print(f"  🧊 cold anchor ETrF = {cold_etrf} (default 1.05 dan farqli)")

    # Broadband albedo usuli — production 'ALBEDO' (default 'config' = o'zgarmagan).
    # 5 usul ALB_* diagnostika bandi har doim CSV'ga chiqadi (usuldan qat'i nazar).
    surface_props.ALBEDO_METHOD = albedo_method
    if albedo_method != 'config':
        print(f"  🎨 albedo usuli = '{albedo_method}' (production ALBEDO; default 'config' dan farqli)")

    # Ekin-spetsifik z0m — FAQAT export_csv rejimida (nuqta ekin turi ma'lum).
    # Boshqa rejimda None (default z0m=0.018·LAI), chunki butun tile ekin turi noma'lum.
    surface_props.CROP_TYPE = crop_type if (_csv_mode and crop_type) else None
    if surface_props.CROP_TYPE:
        print(f"  🌱 ekin-spetsifik z0m: crop_type='{surface_props.CROP_TYPE}' "
              f"(h=f(LAI) → z0m=0.123·h; faqat CSV rejimi)")

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

            # Chekka/bo'sh tayl (nuqtasiz yoki anchor topilmagan) BUTUN runни
            # buzmasin — o'sha taylni o'tkazib, keyingisiga o'tamiz.
            try:
                scenes, info = process_tile(
                    tile_roi, date_start, date_end, mode,
                    satellite, cloud_max, tile_label,
                    anchor_method=anchor_method, anchor_mode=anchor_mode,
                    utc_offset=utc_offset,
                    cloud_roi=cloud_roi, cloud_use_cropland=_cloud_use_cropland)
            except Exception as e:
                print(f"  ⚠️ {tile_label} qayta ishlashda xato ({e}) → tayl o'tkazib yuborildi")
                continue

            if not scenes:
                continue

            # CSV zonal-stat (parcel/lizimetr ustida mean+median → batch CSV)
            if export_csv and csv_region is not None:
                ctasks = _export_zonal_csv(
                    scenes, info, tile_roi, csv_region,
                    csv_bands or CSV_LYS_BANDS, folder, tile_label, mode,
                    info.get('utc_offset', 0), csv_scale, save_cuirr=save_cuirr,
                    save_aw=save_aw)
                all_tasks.extend(ctasks)

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
                dr_carry = None   # oylararo Dr uzatish (mavsumiy-uzluksiz AW)

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
                        month_tasks, dr_carry = _export_monthly(
                            scenes, tile_roi, current_year, current_month,
                            mode, folder, scale, crs, tile_label,
                            False, save_biomass, save_etref, save_tact, save_eact,
                            utc_offset=info.get('utc_offset', 0),
                            save_cuirr=save_cuirr, save_prz=save_prz,
                            save_niwr=save_niwr, save_aw=save_aw,
                            dr_init_img=dr_carry)
                    elif use_viirs:
                        _viirs_export_month(
                            scenes, info, tile_roi, current_year,
                            current_month, month_key, folder, scale, crs,
                            tile_label, viirs_mode, viirs_model, viirs_qa,
                            viirs_fill, tasks)
                        month_tasks, dr_carry = _export_monthly(
                            scenes, tile_roi, current_year, current_month,
                            mode, folder, scale, crs, tile_label,
                            False,  # save_et=False → VIIRS ET ishlatiladi
                            save_biomass, save_etref, save_tact, save_eact,
                            utc_offset=info.get('utc_offset', 0),
                            save_cuirr=save_cuirr, save_prz=save_prz,
                            save_niwr=save_niwr, save_aw=save_aw,
                            dr_init_img=dr_carry)
                    else:
                        month_tasks, dr_carry = _export_monthly(
                            scenes, tile_roi, current_year, current_month,
                            mode, folder, scale, crs, tile_label,
                            save_et, save_biomass, save_etref,
                            save_tact, save_eact,
                            utc_offset=info.get('utc_offset', 0),
                            save_cuirr=save_cuirr, save_prz=save_prz,
                            save_niwr=save_niwr, save_aw=save_aw,
                            dr_init_img=dr_carry)

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
            anchor_mode=anchor_mode, utc_offset=utc_offset,
            cloud_roi=cloud_roi, cloud_use_cropland=_cloud_use_cropland)

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
                dr_carry = None   # oylararo Dr uzatish (mavsumiy-uzluksiz AW)

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

                    month_tasks, dr_carry = _export_monthly(
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
                        utc_offset=info.get('utc_offset', 0),
                        save_cuirr=save_cuirr, save_prz=save_prz,
                        save_niwr=save_niwr, save_aw=save_aw,
                        dr_init_img=dr_carry
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

