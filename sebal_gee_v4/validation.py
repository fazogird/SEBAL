"""
SEBAL-GEE v4 — Validation: OpenET Comparison
===============================================
Bizning SEBAL natijalarini OpenET ning 7 ta modeli bilan solishtirish.

OpenET modellari (GEE da mavjud):
  1. DisALEXI   — Atmosphere-Land Exchange Inverse
  2. eeMETRIC   — Mapping ET with Internalized Calibration
  3. geeSEBAL   — Google Earth Engine SEBAL
  4. PT-JPL     — Priestley-Taylor Jet Propulsion Lab
  5. SIMS       — Satellite Irrigation Management Support
  6. SSEBop     — Operational Simplified Surface Energy Balance
  7. ENSEMBLE   — 7 model o'rtachasi

Solishtirish usuli:
  - Random sampling (1000-5000 nuqta)
  - Pixel-by-pixel statistika
  - R², RMSE, NSE, MBE, MAE

Input:  SEBAL natija image + sana + ROI
Output: Statistika jadvali + scatter data (CSV)
"""

import ee
import math


# ==============================================================
# OpenET Collection IDs
# ==============================================================
OPENET_COLLECTIONS = {
    'ENSEMBLE':  'projects/openet/assets/ensemble/conus/gridmet/monthly/v2_1',
    'DisALEXI':  'projects/openet/assets/disalexi/conus/gridmet/monthly/v2_1',
    'eeMETRIC':  'projects/openet/assets/eemetric/conus/gridmet/monthly/v2_1',
    'geeSEBAL':  'projects/openet/assets/geesebal/conus/gridmet/monthly/v2_1',
    'PT_JPL':    'projects/openet/assets/ptjpl/conus/gridmet/monthly/v2_1',
    'SIMS':      'projects/openet/assets/sims/conus/gridmet/monthly/v2_1',
    'SSEBop':    'projects/openet/assets/ssebop/conus/gridmet/monthly/v2_1',
}
# Eski (XATO):
OPENET_BAND = 'et'

# Yangi (TO'G'RI):
OPENET_BAND = 'et_ensemble_mad'


# ==============================================================
# OpenET ma'lumotlarini olish
# ==============================================================

def get_openet_monthly(roi, year, month, models=None):
    """
    OpenET dan oylik ET olish — barcha yoki tanlangan modellar.

    OpenET qiymatlari: mm/month (oylik jami).

    Parameters
    ----------
    roi : ee.Geometry
    year : int
    month : int
    models : list, optional
        Model nomlari. None = hammasi.

    Returns
    -------
    ee.Image : har model alohida band sifatida
    """
    if models is None:
        models = list(OPENET_COLLECTIONS.keys())

    date_start = ee.Date.fromYMD(year, month, 1)
    if month == 12:
        date_end = ee.Date.fromYMD(year + 1, 1, 1)
    else:
        date_end = ee.Date.fromYMD(year, month + 1, 1)

    result = None

    for model_name in models:
        collection_id = OPENET_COLLECTIONS.get(model_name)
        if collection_id is None:
            print(f"  ⚠️  '{model_name}' topilmadi, o'tkazildi")
            continue

        try:
            col = (ee.ImageCollection(collection_id)
                   .filterDate(date_start, date_end)
                   .filterBounds(roi)
                   .first())

            # Har model o'z band nomiga ega — birinchi bandni olish
            first_band = col.bandNames().get(0)
            img = col.select([first_band]).rename(f'ET_{model_name}')

            if result is None:
                result = img
            else:
                result = result.addBands(img)
        except Exception:
            print(f"  ⚠️  {model_name} yuklanmadi")

    return result


def get_openet_daily_mean(roi, year, month, models=None):
    """
    OpenET oylik qiymatni kunlik o'rtachaga aylantirish.

    ET_daily = ET_monthly / days_in_month  (mm/day)

    Bizning SEBAL kunlik natija bilan solishtirishga moslashtirish.
    """
    import calendar
    days = calendar.monthrange(year, month)[1]

    monthly = get_openet_monthly(roi, year, month, models)

    if monthly is None:
        return None

    daily_mean = monthly.divide(days)

    return daily_mean


# ==============================================================
# Random sampling
# ==============================================================

def sample_points(sebal_image, openet_image, roi,
                  n_points=2000, scale=30, seed=42):
    """
    SEBAL va OpenET ni bir xil nuqtalarda namuna olish.

    Random stratified sampling:
    - ROI ichida random nuqtalar
    - Ikki rastrdan qiymat olish
    - Null qiymatlarni olib tashlash

    Parameters
    ----------
    sebal_image : ee.Image
        Bizning ET_24 band
    openet_image : ee.Image
        OpenET modellar bandlari
    roi : ee.Geometry
    n_points : int
    scale : int
    seed : int

    Returns
    -------
    list of dict : har nuqta uchun {lon, lat, ET_SEBAL, ET_model1, ...}
    """
    # Ikki rastrni birlashtirish
    combined = (sebal_image.select('ET_24').rename('ET_SEBAL')
                .addBands(openet_image))

    # Random nuqtalar generatsiya
    points = ee.FeatureCollection.randomPoints(
        region=roi,
        points=n_points,
        seed=seed
    )

    # Nuqtalarda qiymat olish
    sampled = combined.sampleRegions(
        collection=points,
        scale=scale,
        geometries=True
    )

    # Null filter — ikkalasida ham qiymat bor bo'lsin
    sampled = sampled.filter(ee.Filter.notNull(['ET_SEBAL']))

    return sampled


# ==============================================================
# Statistika hisoblash
# ==============================================================

def compute_statistics(sampled_data, sebal_band='ET_SEBAL',
                       openet_band='ET_ENSEMBLE'):
    """
    R², RMSE, NSE, MBE, MAE hisoblash.

    GEE server-side hisoblash — katta datasetlar uchun samarali.

    Parameters
    ----------
    sampled_data : ee.FeatureCollection
    sebal_band : str
    openet_band : str

    Returns
    -------
    dict : r2, rmse, nse, mbe, mae, n, mean_sebal, mean_openet
    """
    # Null filtr
    valid = sampled_data.filter(
        ee.Filter.And(
            ee.Filter.notNull([sebal_band]),
            ee.Filter.notNull([openet_band])
        )
    )

    n = valid.size()

    # O'rtacha qiymatlar
    mean_sebal = valid.aggregate_mean(sebal_band)
    mean_openet = valid.aggregate_mean(openet_band)

    # Pearson R — ee.Reducer.pearsonsCorrelation
    correlation = valid.reduceColumns(
        reducer=ee.Reducer.pearsonsCorrelation(),
        selectors=[sebal_band, openet_band]
    )
    r = ee.Number(correlation.get('correlation'))
    r2 = r.pow(2)

    # RMSE, MBE, MAE — custom hisob
    def add_errors(feature):
        sebal_val = ee.Number(feature.get(sebal_band))
        openet_val = ee.Number(feature.get(openet_band))
        diff = sebal_val.subtract(openet_val)
        sq_diff = diff.pow(2)
        abs_diff = diff.abs()
        return feature.set({
            'diff': diff,
            'sq_diff': sq_diff,
            'abs_diff': abs_diff,
        })

    with_errors = valid.map(add_errors)

    mbe = with_errors.aggregate_mean('diff')
    mse = with_errors.aggregate_mean('sq_diff')
    mae = with_errors.aggregate_mean('abs_diff')
    rmse = mse.sqrt()

    # NSE = 1 - Σ(Si-Oi)² / Σ(Oi-Omean)²
    def add_obs_dev(feature):
        openet_val = ee.Number(feature.get(openet_band))
        dev = openet_val.subtract(mean_openet).pow(2)
        return feature.set('obs_dev', dev)

    with_dev = valid.map(add_obs_dev)
    ss_obs = with_dev.aggregate_sum('obs_dev')
    ss_err = with_errors.aggregate_sum('sq_diff')
    nse = ee.Number(1).subtract(ss_err.divide(ss_obs.max(0.001)))

    return {
        'r2': r2,
        'rmse': rmse,
        'nse': nse,
        'mbe': mbe,
        'mae': mae,
        'n': n,
        'mean_sebal': mean_sebal,
        'mean_openet': mean_openet,
    }


# ==============================================================
# MAIN: To'liq validatsiya
# ==============================================================

def validate(sebal_image, roi, year, month, n_points=2000):
    """
    SEBAL vs OpenET to'liq validatsiya.

    Parameters
    ----------
    sebal_image : ee.Image
        Bizning SEBAL natijasi (ET_24 band bo'lishi kerak)
    roi : ee.Geometry
    year : int
    month : int
    n_points : int
        Sampling nuqtalar soni

    Returns
    -------
    dict : har model uchun statistika
    """
    print(f"\n[Validation] SEBAL vs OpenET — {year}-{month:02d}")
    print(f"[Validation] Sampling: {n_points} nuqta")

    # 1. OpenET olish (kunlik o'rtacha — SEBAL bilan mos)
    print("[Validation] OpenET yuklanmoqda...")
    openet = get_openet_daily_mean(roi, year, month)

    if openet is None:
        print("❌ OpenET ma'lumot topilmadi!")
        return None

    openet_bands = openet.bandNames().getInfo()
    print(f"[Validation] OpenET modellar: {openet_bands}")

    # 2. Sampling
    print("[Validation] Random sampling...")
    sampled = sample_points(sebal_image, openet, roi,
                            n_points=n_points)

    actual_n = sampled.size().getInfo()
    print(f"[Validation] Valid nuqtalar: {actual_n}")

    if actual_n < 50:
        print("⚠️  Juda kam nuqta — natijalar ishonchsiz!")

    # 3. Har model uchun statistika
    print("\n" + "="*70)
    print(f"{'Model':<12} {'R²':>6} {'RMSE':>8} {'NSE':>8} "
          f"{'MBE':>8} {'MAE':>8} {'SEBAL':>8} {'OpenET':>8}")
    print("-"*70)

    results = {}
    for band_name in openet_bands:
        model_name = band_name.replace('ET_', '')
        try:
            stats = compute_statistics(sampled, 'ET_SEBAL', band_name)

            # Server → client
            stats_info = {k: v.getInfo() if hasattr(v, 'getInfo') else v
                         for k, v in stats.items()}

            results[model_name] = stats_info

            print(f"{model_name:<12} "
                  f"{stats_info['r2']:>6.3f} "
                  f"{stats_info['rmse']:>8.3f} "
                  f"{stats_info['nse']:>8.3f} "
                  f"{stats_info['mbe']:>8.3f} "
                  f"{stats_info['mae']:>8.3f} "
                  f"{stats_info['mean_sebal']:>8.2f} "
                  f"{stats_info['mean_openet']:>8.2f}")
        except Exception as e:
            print(f"{model_name:<12} ❌ Xato: {e}")

    print("="*70)

    # 4. Eng yaxshi model
    if results:
        best_r2 = max(results.items(), key=lambda x: x[1].get('r2', 0))
        best_rmse = min(results.items(), key=lambda x: x[1].get('rmse', 999))

        print(f"\n📊 Eng yuqori R²:   {best_r2[0]} (R²={best_r2[1]['r2']:.3f})")
        print(f"📊 Eng past RMSE:  {best_rmse[0]} (RMSE={best_rmse[1]['rmse']:.3f} mm/day)")

    return results


def export_scatter_csv(sampled, roi, folder='SEBAL_Output',
                       filename='validation_scatter'):
    """
    Scatter plot uchun CSV export.

    GEE → Google Drive CSV sifatida.
    Keyin Python/Excel da scatter plot chizish mumkin.
    """
    task = ee.batch.Export.table.toDrive(
        collection=sampled,
        description=filename,
        folder=folder,
        fileNamePrefix=filename,
        fileFormat='CSV'
    )
    task.start()
    print(f"✅ CSV export: {folder}/{filename}.csv")
    print(f"   Task ID: {task.id}")
    return task
