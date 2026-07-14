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


# ==============================================================
# DAILY BAND SETS
# ==============================================================

DAILY_BANDS_MAQOLA = [
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
                 tile_label=''):
    """
    Bitta ROI/tile uchun SEBAL pipeline.
    Returns: list of processed scene images
    """
    prefix = f"  [{tile_label}]" if tile_label else "  "

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
        mgrs_tile=mgrs_tile)
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

    # Surface props + radiation
    collection = collection.map(surface_props.compute_all)
    collection = collection.map(radiation.compute_all)

    # Energy balance — har sahna alohida
    image_list = collection.toList(collection.size())
    n = info['image_count']

    scene_images = []

    for i in range(n):
        print(f"{prefix} Sahna {i + 1}/{n}...")

        img = ee.Image(image_list.get(i))
        img = energy_balance.compute_all(img, roi)
        img = daily_et.compute_daily_et(img, roi)

        if mode == 'pysebal':
            from . import et_decomposition, soil_moisture, biomass, irrigation

            img = et_decomposition.compute_all(image=img, roi=roi)
            img = soil_moisture.compute_all(img)
            img = biomass.compute_all(img)
            img = irrigation.compute_all(img)

        scene_images.append(img)

    return scene_images, info


# ==============================================================
# EXPORT — kunlik
# ==============================================================

def _export_daily(scene_images, info, roi, mode, folder, scale, crs,
                 tile_label=''):
    """Kunlik rasterlar — multi-band, har sahna alohida fayl."""
    bands = DAILY_BANDS_PYSEBAL if mode == 'pysebal' else DAILY_BANDS_MAQOLA
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
    except Exception as e:
        print(f"  ⚠️ S30 ET {month_key}: {e}")


def _export_monthly(scene_images, roi, year, month, mode,
                   folder, scale, crs, tile_label='',
                   save_et=True, save_biomass=True,
                   save_etref=True, save_tact=True, save_eact=True):
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
            scene_images, roi, year, month)

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
        mode='maqola', satellite='BOTH', cloud_max=20, validate=False,

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

        # Export sozlamalari
        folder='SEBAL_Output',
        scale=30,
        crs='EPSG:4326',

        # VIIRS downscaling (ixtiyoriy qatlam — SEBAL o'zgarmaydi)
        use_viirs=True,            # True → oylik ET VIIRS bilan kuchaytiriladi
        viirs_mode='lambda',        # 'lambda' (EVAP_FRAC) yoki 'kc' (KC)
        viirs_model='ndvi',         # 'ndvi' | 'ndvi2' | 'multi'
        viirs_qa='lenient',         # 'lenient' | 'strict'
        viirs_fill='linear',        # 'linear' | 'nearest'

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

    print(f"\n{'='*60}")
    print(f"  SEBAL-GEE v4 | Mode: {mode}")
    print(f"  ROI: {roi_type} | {date_start} → {date_end}")
    print(f"  Tile mode: {process_by_tile}")
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
                satellite, cloud_max, tile_label)

            if not scenes:
                continue

            if export_daily:
                tasks = _export_daily(scenes, info, tile_roi, mode,
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
                            False, save_biomass, save_etref, save_tact, save_eact)
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
                            save_biomass, save_etref, save_tact, save_eact)
                    else:
                        month_tasks = _export_monthly(
                            scenes, tile_roi, current_year, current_month,
                            mode, folder, scale, crs, tile_label,
                            save_et, save_biomass, save_etref,
                            save_tact, save_eact)

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
            satellite, cloud_max)

        if scenes:
            if export_daily:
                tasks = _export_daily(scenes, info, roi, mode,
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
                        save_eact
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
    print(f"  🔗 https://code.earthengine.google.com/tasks")
    print(f"{'='*60}")

    return {'tasks': all_tasks}

