"""
SEBAL-GEE v4 — Main Orchestrator
==================================
To'liq pipeline ni boshqarish.

Ishlatish:
  from sebal_gee_v4 import main

  # 1. Daily mode — faqat Landsat o'tgan kunlar
  main.run(
      roi_type='gaul', name='Idaho', level=1,
      date_start='2024-06-01', date_end='2024-09-30',
      et_mode='daily'
  )

  # 2. Monthly mode — Λ interpolyatsiya bilan har oy
  main.run(
      roi_type='rectangle', bounds=[-114.5, 42.0, -113.0, 43.5],
      date_start='2024-06-01', date_end='2024-09-30',
      et_mode='monthly'
  )

Pipeline:
  Input → Preprocessing → Surface Props → Radiation →
  Energy Balance → Daily/Monthly ET → Export
"""

import ee
from . import config as cfg
from . import preprocessing
from . import surface_props
from . import radiation
from . import energy_balance
from . import daily_et


# ==============================================================
# MAIN RUN
# ==============================================================

def run(roi_type='gaul', date_start=None, date_end=None,
        et_mode=None, satellite=None, cloud_max=None,
        export_to=None, export_folder=None, export_scale=None,
        export_crs=None, **roi_kwargs):
    """
    SEBAL-GEE v4 to'liq pipeline.

    Parameters
    ----------
    roi_type : str
        'rectangle', 'point', 'shapefile', 'gaul'
    date_start : str
        'YYYY-MM-DD'
    date_end : str
        'YYYY-MM-DD'
    et_mode : str
        'daily' yoki 'monthly'
    satellite : str
        'L8', 'L9', 'BOTH'
    cloud_max : int
        Max cloud cover %
    export_to : str
        'Drive' yoki 'Asset'
    export_folder : str
        Google Drive papka nomi
    export_scale : int
        Export resolution (m)
    export_crs : str
        Coordinate reference system
    **roi_kwargs :
        ROI parametrlari (bounds, coords, name, level, etc.)

    Returns
    -------
    dict : task_ids, image_count, dates
    """
    # ---- Config defaults ----
    et_mode = et_mode or cfg.PIPELINE['et_mode']
    satellite = satellite or cfg.PIPELINE['satellite']
    cloud_max = cloud_max or cfg.PIPELINE['cloud_max_percent']
    export_to = export_to or cfg.PIPELINE['export_to']
    export_folder = export_folder or cfg.PIPELINE['export_folder']
    export_scale = export_scale or cfg.PIPELINE['export_scale']
    export_crs = export_crs or cfg.PIPELINE['export_crs']

    # ---- ROI ----
    roi = cfg.build_roi(roi_type, **roi_kwargs)
    print(f"[SEBAL] ROI: {roi_type}")
    print(f"[SEBAL] Sana: {date_start} → {date_end}")
    print(f"[SEBAL] Mode: {et_mode} | Satellite: {satellite}")

    # ---- 1. PREPROCESSING — toza collection qurish ----
    print("[SEBAL] M1: Preprocessing...")
    collection = preprocessing.build_collection(
        roi=roi,
        date_start=date_start,
        date_end=date_end,
        satellite=satellite,
        cloud_max=cloud_max
    )

    info = preprocessing.collection_info(collection)
    print(f"[SEBAL] Topildi: {info['image_count']} ta cloud-free tasvir")
    print(f"[SEBAL] Sanalar: {info['dates']}")

    if info['image_count'] == 0:
        print("[SEBAL] XATO: Hech qanday toza tasvir topilmadi!")
        return {'error': 'No clean images found', 'task_ids': []}

    # ---- 2. SURFACE PROPERTIES ----
    print("[SEBAL] M2: Surface properties (NDVI, SAVI, albedo, ε₀, z₀m)...")
    collection = collection.map(surface_props.compute_all)

    # ---- 3. RADIATION ----
    print("[SEBAL] M3+M4: Radiation (Q*, G₀)...")
    collection = collection.map(radiation.compute_all)

    # ---- 4. ENERGY BALANCE (har sahna alohida) ----
    # energy_balance.compute_all() ichida reduceRegion() bor —
    # ee.ImageCollection.map() ichida ishlamaydi.
    # Shuning uchun image listga o'girib, birma-bir ishlashimiz kerak.
    print("[SEBAL] M5-M8: Energy balance (anchor, wind, H, λE)...")
    image_list = collection.toList(collection.size())
    n_images = info['image_count']

    processed_images = []
    for i in range(n_images):
        print(f"  → Sahna {i+1}/{n_images} ishlanmoqda...")
        img = ee.Image(image_list.get(i))
        img = energy_balance.compute_all(img, roi)
        processed_images.append(img)

    # ---- 5. DAILY ET ----
    print("[SEBAL] M9: ET hisoblash...")
    et_images = []
    for img in processed_images:
        img = daily_et.compute_daily_et(img, roi)
        et_images.append(img)

    # ---- 6. MODE-BASED OUTPUT ----
    task_ids = []

    if et_mode == 'daily':
        task_ids = _export_daily(et_images, roi, export_to,
                                 export_folder, export_scale, export_crs)

    elif et_mode == 'monthly':
        task_ids = _export_monthly(et_images, roi, date_start, date_end,
                                   export_to, export_folder,
                                   export_scale, export_crs)

    print(f"[SEBAL] Tayyor! {len(task_ids)} ta export task ishga tushdi.")
    return {
        'task_ids': task_ids,
        'image_count': n_images,
        'dates': info['dates'],
        'mode': et_mode,
    }


# ==============================================================
# EXPORT — Daily Mode
# ==============================================================

def _export_daily(et_images, roi, export_to, folder, scale, crs):
    """
    Daily mode — har Landsat sana uchun multiband GeoTIFF.

    Bandlar: ET_24, ETrF, LAMBDA_E, H, RN, G0, NDVI, LST
    """
    task_ids = []
    band_names = cfg.PIPELINE['daily_bands']

    for img in et_images:
        date_str = (ee.Date(img.get('system:time_start'))
                    .format('YYYY-MM-dd')
                    .getInfo())

        # Kerakli bandlarni tanlash
        export_image = img.select([
            'ET_24', 'ETrF', 'LAMBDA_E', 'H', 'RN', 'G0', 'NDVI', 'LST'
        ])

        file_name = f'ET_daily_{date_str}'

        task = _start_export(export_image, file_name, roi,
                             export_to, folder, scale, crs)
        task_ids.append(task.id)
        print(f"  → Export: {file_name}")

    return task_ids


# ==============================================================
# EXPORT — Monthly Mode
# ==============================================================

def _export_monthly(et_images, roi, date_start, date_end,
                    export_to, folder, scale, crs):
    """
    Monthly mode — oylik ET (mm/month) GeoTIFF.

    Jarayon:
      1. Har oy uchun oydagi tasvirlarni ajratish
      2. Λ interpolyatsiya + ERA5 kunlik radiatsiya
      3. Oylik yig'indi
      4. Mavsumiy jami
    """
    from datetime import datetime, timedelta

    start = datetime.strptime(date_start, '%Y-%m-%d')
    end = datetime.strptime(date_end, '%Y-%m-%d')

    task_ids = []
    monthly_images = []

    # Har oy uchun
    current = start.replace(day=1)
    while current <= end:
        year = current.year
        month = current.month

        # Shu oydagi tasvirlarni topish
        month_start_ms = ee.Date.fromYMD(year, month, 1).millis()
        if month == 12:
            month_end_ms = ee.Date.fromYMD(year + 1, 1, 1).millis()
        else:
            month_end_ms = ee.Date.fromYMD(year, month + 1, 1).millis()

        month_images = []
        for img in et_images:
            img_time = img.get('system:time_start')
            # Server-side filtr — client-side loop ichida
            month_images.append(img)

        # Agar tasvirlar bo'lsa — oylik ET hisoblash
        if len(month_images) > 0:
            print(f"  → {year}-{month:02d}: {len(month_images)} ta tasvir bilan oylik ET...")

            et_monthly = daily_et.compute_monthly_et(
                month_images, roi, year, month
            )
            monthly_images.append(et_monthly)

            file_name = f'ET_monthly_{year}-{month:02d}'
            task = _start_export(et_monthly, file_name, roi,
                                 export_to, folder, scale, crs)
            task_ids.append(task.id)
            print(f"  → Export: {file_name}")

        # Keyingi oy
        if month == 12:
            current = current.replace(year=year + 1, month=1)
        else:
            current = current.replace(month=month + 1)

    # Mavsumiy jami
    if len(monthly_images) > 1:
        print("  → Mavsumiy jami hisoblanmoqda...")
        seasonal = daily_et.compute_seasonal_stats(monthly_images)

        task = _start_export(seasonal['total'],
                             'ET_seasonal_total', roi,
                             export_to, folder, scale, crs)
        task_ids.append(task.id)

        task = _start_export(seasonal['mean_daily'],
                             'ET_seasonal_mean_daily', roi,
                             export_to, folder, scale, crs)
        task_ids.append(task.id)

    return task_ids


# ==============================================================
# EXPORT HELPER
# ==============================================================

def _start_export(image, file_name, roi, export_to, folder, scale, crs):
    """
    GEE export taskni boshlash.

    Parameters
    ----------
    image : ee.Image
    file_name : str
    roi : ee.Geometry
    export_to : str — 'Drive' yoki 'Asset'
    folder : str
    scale : int
    crs : str

    Returns
    -------
    ee.batch.Task
    """
    if export_to == 'Drive':
        task = ee.batch.Export.image.toDrive(
            image=image.toFloat(),
            description=file_name,
            folder=folder,
            fileNamePrefix=file_name,
            region=roi,
            scale=scale,
            crs=crs,
            maxPixels=1e13,
            fileFormat='GeoTIFF'
        )
    elif export_to == 'Asset':
        asset_id = f'projects/earthengine-legacy/assets/{folder}/{file_name}'
        task = ee.batch.Export.image.toAsset(
            image=image.toFloat(),
            description=file_name,
            assetId=asset_id,
            region=roi,
            scale=scale,
            crs=crs,
            maxPixels=1e13
        )
    else:
        raise ValueError(f"export_to '{export_to}' noto'g'ri. 'Drive' yoki 'Asset' bo'lsin.")

    task.start()
    return task


# ==============================================================
# QUICK RUN — tez sinash uchun
# ==============================================================

def quick_test(roi_type='gaul', name='Idaho', level=1,
               date_start='2024-07-01', date_end='2024-07-31'):
    """
    Tez sinash — bitta oy, daily mode.

    Natijani Drive ga eksport qilmaydi, faqat hisoblash.
    Thumbnail olish uchun ishlatiladi.

    Returns
    -------
    ee.Image : birinchi sahnaning to'liq natijasi
    """
    ee.Initialize()

    roi = cfg.build_roi(roi_type, name=name, level=level)

    # Preprocessing
    collection = preprocessing.build_collection(
        roi=roi, date_start=date_start, date_end=date_end,
        satellite='BOTH', cloud_max=20
    )

    info = preprocessing.collection_info(collection)
    print(f"Topildi: {info['image_count']} tasvir")

    if info['image_count'] == 0:
        print("Tasvir topilmadi!")
        return None

    # Birinchi tasvirni olish
    collection = collection.map(surface_props.compute_all)
    collection = collection.map(radiation.compute_all)

    first_image = ee.Image(collection.first())
    first_image = energy_balance.compute_all(first_image, roi)
    first_image = daily_et.compute_daily_et(first_image, roi)

    print("Birinchi sahna tayyor!")
    print("Bandlar:", first_image.bandNames().getInfo())

    return first_image
