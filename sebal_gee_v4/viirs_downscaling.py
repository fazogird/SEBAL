"""
SEBAL-GEE v4 — VIIRS vegetation-predictor ET downscaling
=========================================================
Landsat/HLS SEBAL natijasini VIIRS VNP09GA (I1/I2/I3) vegetation
predictorlari yordamida oy ichida KUNLIK 30 m ET time-series ga
aylantiradi. Oylik ET = kunlik ET_24 yig'indisi.

QAT'IY QOIDALAR
---------------
  • Mavjud SEBAL mantig'i (Rn, G, H, LE, EVAP_FRAC, ET_24) O'ZGARMAYDI.
  • VIIRS orqali noldan SEBAL/ET hisoblanmaydi.
  • VIIRS LST ISHLATILMAYDI.
  • VIIRS faqat VNP09GA I1(Red)/I2(NIR)/I3(SWIR1) dan NDVI/EVI2/NDWI
    predictor sifatida ishlatiladi.
  • Predictorlar mavjud SEBAL target (Lambda yoki KC) bilan REGRESSIYA
    orqali bog'lanadi; clear VIIRS kunlarda coarse target baholanadi va
    Landsat 30 m weight bilan downscale qilinadi.

IKKI REJIM (downscale_mode)
---------------------------
  lambda : target = EVAP_FRAC (SEBAL-consistent)
           ET_24_d = Lambda_30_d × RN24_d × (86400/λ)
  kc     : target = KC (= ET_24/ETREF_24, METRIC-like)
           ET_24_d = KC_30_d × ETREF_24_d

REGRESSIYA: client-side numpy lstsq (halol R²/RMSE), server-side qo'llash.
Modellar: ndvi | ndvi2 | multi.
"""

import datetime as _dt

import ee
import numpy as np

from . import config as cfg
from . import daily_et
from . import monthly_analytics as ma


# ==============================================================
# KONFIGURATSIYA
# ==============================================================

VNP09GA = 'NASA/VIIRS/002/VNP09GA'

VBANDS = {
    'red':   'I1',   # 0.640 µm
    'nir':   'I2',   # 0.865 µm
    'swir1': 'I3',   # 1.61 µm
    'qf1':   'QF1',
    'qf2':   'QF2',
    'qf7':   'QF7',
}

DCFG = {
    'epsilon':     0.001,   # weight maxraji uchun
    'lambda_min':  0.0,
    'lambda_max':  1.2,
    'kc_min':      0.0,
    'kc_max':      1.3,
    'weight_min':  0.2,
    'weight_max':  5.0,
    'max_samples': 3000,    # regressiya namunasi (coarse piksellar)
    'sample_seed': 42,
    'rho_w':       1000.0,
    # 30 m target proyeksiyasi (reduceResolution uchun shart).
    # SEBAL qayta ishlovdan keyin proyeksiya yo'qoladi → aniq deklaratsiya.
    # Sirdaryo/Qashqadaryo = UTM zona 42 = EPSG:32642.
    'fine_crs':    'EPSG:32642',
    'fine_scale':  30,
    'tile_scale':  8,       # reduceRegion/sample xotira bo'lish (4-16)
    # Anchor kuni VIIRS bulutli bo'lsa ham predictor olish uchun ±N kunlik
    # median kompozit (vegetatsiya sekin o'zgaradi).
    'predictor_window': 4,
}

# daily ET konversiyasi — MAVJUD pipeline bilan AYNAN bir xil
# (daily_et.py: conversion = seconds_per_day / LAMBDA_V)
ET_CONV = cfg.DAILY_ET['seconds_per_day'] / cfg.LAMBDA_V

MODELS = ('ndvi', 'ndvi2', 'multi')


# ==============================================================
# 0b. ANCHOR MATERIALIZATSIYA (xotira yechimi — MAJBURIY bosqich)
# ==============================================================
# Jonli SEBAL EVAP_FRAC/KC tasviri butun energiya-balans + anchor
# hisob zanjirini olib yuradi. Uni VIIRS gridiga reduceResolution /
# sample qilish har joyda SEBAL'ni qaytadan hisoblab "User memory limit
# exceeded" beradi. Shuning uchun anchor target + yordamchi bandlarni
# avval ASSETga eksport qilamiz, keyin o'qib ishlatamiz (arzon, qayta
# hisoblamaydi). Bu yagona ishonchli yo'l.

ANCHOR_BANDS = ['EVAP_FRAC', 'KC', 'ET_24', 'ETREF_24', 'RN24',
                'ALBEDO', 'TAU_SW', 'NDVI']


def export_anchor_to_asset(anchor_image, date, roi, asset_folder,
                           scale=30, crs='EPSG:32642'):
    """
    Bitta anchor SEBAL natijasini ASSETga eksport (materializatsiya).
    asset_folder: masalan 'projects/<proj>/assets/viirs_anchors'
    Returns: (task, asset_id)
    """
    avail = anchor_image.bandNames().getInfo()
    bands = [b for b in ANCHOR_BANDS if b in avail]
    asset_id = f"{asset_folder}/anchor_{date.replace('-', '')}"
    task = ee.batch.Export.image.toAsset(
        image=anchor_image.select(bands).toFloat(),
        description=f"anchor_{date.replace('-', '')}",
        assetId=asset_id, region=roi, scale=scale, crs=crs,
        maxPixels=1e13)
    task.start()
    return task, asset_id


def load_anchor_from_asset(asset_id, date):
    """Eksport qilingan anchor assetni anchor dict sifatida yuklash."""
    return {'image': ee.Image(asset_id), 'date': date}


# ==============================================================
# 1. VIIRS VNP09GA olish
# ==============================================================

def get_viirs_vnp09ga(date, roi):
    """Bitta kun uchun VNP09GA tasviri (yo'q bo'lsa None)."""
    d = ee.Date(date)
    col = (ee.ImageCollection(VNP09GA)
           .filterDate(d, d.advance(1, 'day'))
           .filterBounds(roi))
    return ee.Image(col.first())


# ==============================================================
# 2. Bulut maskasi (QA)
# ==============================================================

def mask_viirs_vnp09ga(img, qa_mode='lenient'):
    """
    VNP09GA QF bitlari bilan bulut/soya/qor maskasi.

    strict  : bulut(>=2) + soya + qor + sirrus + bulutga yondosh → tashlash
    lenient : faqat aniq bulut(==3) + soya → tashlash (ko'p kun qoladi)
    """
    qf1 = img.select(VBANDS['qf1'])
    qf2 = img.select(VBANDS['qf2'])

    cloud_state = qf1.rightShift(2).bitwiseAnd(3)   # 0..3
    shadow = qf2.rightShift(3).bitwiseAnd(1)

    if qa_mode == 'strict':
        snow    = qf2.rightShift(5).bitwiseAnd(1)
        cirrus1 = qf2.rightShift(6).bitwiseAnd(1)
        cirrus2 = qf2.rightShift(7).bitwiseAnd(1)
        qf7 = img.select(VBANDS['qf7'])
        adjacent = qf7.rightShift(1).bitwiseAnd(1)
        bad = (cloud_state.gte(2)
               .Or(shadow).Or(snow).Or(cirrus1).Or(cirrus2).Or(adjacent))
    else:  # lenient
        bad = cloud_state.gte(3).Or(shadow)

    return img.updateMask(bad.Not())


# ==============================================================
# 3. Vegetation predictorlar (faqat I1/I2/I3)
# ==============================================================

def compute_viirs_predictors(img):
    """
    NDVI, EVI2, NDWI — VNP09GA I1/I2/I3 dan.
      NDVI = (NIR - Red)/(NIR + Red)
      EVI2 = 2.5(NIR - Red)/(NIR + 2.4·Red + 1)
      NDWI = (NIR - SWIR1)/(NIR + SWIR1)   (LSWI)
    """
    red = img.select(VBANDS['red'])
    nir = img.select(VBANDS['nir'])
    swir = img.select(VBANDS['swir1'])

    ndvi = nir.subtract(red).divide(nir.add(red)).rename('NDVI')
    evi2 = (nir.subtract(red).multiply(2.5)
            .divide(nir.add(red.multiply(2.4)).add(1.0))).rename('EVI2')
    ndwi = nir.subtract(swir).divide(nir.add(swir)).rename('NDWI')

    return ndvi.addBands(evi2).addBands(ndwi)


# ==============================================================
# 4. VIIRS proyeksiya
# ==============================================================

def get_viirs_projection(img):
    """I1 (500 m) gridi — aggregate/reproject uchun."""
    return img.select(VBANDS['red']).projection()


def clear_viirs_predictors(date, roi, viirs_projection, qa_mode='lenient',
                           window_days=None):
    """
    ±window_days oynadagi bulutsiz predictor median kompoziti.

    Anchor kuni (yoki istalgan kun) VIIRS bulutli bo'lsa ham, yaqin
    kunlardagi toza kuzatuvlardan NDVI/EVI2/NDWI tiklanadi (vegetatsiya
    sekin o'zgaradi). Bu regressiya juftliklarini yo'qotmaslik uchun.
    """
    if window_days is None:
        window_days = DCFG['predictor_window']
    d = ee.Date(date)
    col = (ee.ImageCollection(VNP09GA)
           .filterDate(d.advance(-window_days, 'day'),
                       d.advance(window_days + 1, 'day'))
           .filterBounds(roi)
           .map(lambda im: compute_viirs_predictors(
               mask_viirs_vnp09ga(im, qa_mode))))
    # 500 m gridda median, keyin bilinear → 30 m da silliq qo'llash uchun
    return col.median().reproject(crs=viirs_projection).resample('bilinear')


# ==============================================================
# TILE-SCALE DOWNSCALING (asset YO'Q, reduceResolution YO'Q)
# ==============================================================
# Optimizatsiya: weight reduceResolution o'rniga regressiya bashoratidan
# olinadi → og'ir agregatsiya yo'q, portlamaydi, tile ichida ishlaydi.
#   W = Λ_30_landsat / predict(VIIRS_NDVI_anchor)
#   Λ_30_kun = predict(VIIRS_NDVI_kun) × W
# Anchor kuni: Λ_30 aniq Landsat'ga teng (mukammal rekonstruksiya).


def build_regression_samples_30m(anchors, tile_roi, target_mode,
                                 qa_mode='lenient', sample_scale=100):
    """
    Regressiya namunalari — 30 m nuqtalardan (reduceResolution YO'Q).
    Faqat target (ET/Λ) MAVJUD bo'lgan joydan namuna olinadi (dropNulls).

    Har nuqtada: Landsat target_30 + VIIRS predictor (anchor ±window).
    """
    tband = _target_band(target_mode)
    fcs = []
    for a in anchors:
        vproj = a['vproj']
        preds = clear_viirs_predictors(a['date'], tile_roi, vproj, qa_mode)
        target30 = a['image'].select(tband).rename('target')
        stack = preds.addBands(target30)
        fc = stack.sample(
            region=tile_roi, scale=sample_scale,
            numPixels=DCFG['max_samples'], seed=DCFG['sample_seed'],
            dropNulls=True, geometries=False, tileScale=DCFG['tile_scale'])
        fcs.append(fc)
    merged = fcs[0]
    for fc in fcs[1:]:
        merged = merged.merge(fc)
    return merged


def weight_from_prediction(landsat_target_30, predictors_anchor,
                           regression_model, model_name, target_mode):
    """
    W = target_30_landsat / predict(VIIRS_predictor_anchor).
    reduceResolution YO'Q. Anchor kuni Λ_30 = Landsat (mukammal).
    """
    lo, hi = ((DCFG['lambda_min'], DCFG['lambda_max']) if target_mode == 'lambda'
              else (DCFG['kc_min'], DCFG['kc_max']))
    pred = predict_coarse_target(predictors_anchor, regression_model,
                                 model_name, target_mode)
    denom = pred.max(DCFG['epsilon'])
    # Landsat MAVJUD joyda 30 m detal; Landsat yo'q (bulut/chet) joyda
    # W=1 → butun tile qoplanadi (faqat regressiya bashorati, blokli).
    return (landsat_target_30.clamp(lo, hi).divide(denom)
            .clamp(DCFG['weight_min'], DCFG['weight_max'])
            .unmask(1).rename('W'))


# ==============================================================
# 5. 30 m → VIIRS grid agregatsiya
# ==============================================================

def aggregate_to_viirs_grid(fine_img, viirs_projection):
    """
    mean(fine) har VIIRS pikseli ichida (block-constant coarse).

    reduceResolution kirish tasvirining aniq proyeksiyasini talab qiladi.
    SEBAL natijasi (EVAP_FRAC/KC) qayta ishlovdan keyin proyeksiyasini
    yo'qotishi mumkin, shuning uchun 30 m proyeksiyani aniq deklaratsiya
    qilamiz (setDefaultProjection — resampling qilmaydi, faqat metadata).
    """
    fixed = fine_img.setDefaultProjection(
        crs=DCFG['fine_crs'], scale=DCFG['fine_scale'])
    return (fixed
            .reduceResolution(reducer=ee.Reducer.mean(), maxPixels=4096)
            .reproject(crs=viirs_projection))


# ==============================================================
# 6. Training namunalari (anchor kunlari)
# ==============================================================

def _target_band(mode):
    return 'EVAP_FRAC' if mode == 'lambda' else 'KC'


def build_training_samples(anchors, roi, viirs_projection, target_mode,
                           qa_mode='lenient'):
    """
    Har anchor uchun: target_coarse + VIIRS predictor_coarse stack →
    coarse piksellardan namuna oladi.

    anchors : list of dict {'image': ee.Image(SEBAL scene), 'date': 'YYYY-MM-DD'}
    Returns : merged ee.FeatureCollection (NDVI, EVI2, NDWI, target)
    """
    tband = _target_band(target_mode)
    scale = viirs_projection.nominalScale()
    fcs = []

    for a in anchors:
        target30 = a['image'].select(tband)
        target_coarse = aggregate_to_viirs_grid(target30, viirs_projection)

        # Anchor kuni atrofidagi bulutsiz predictor kompoziti
        preds = clear_viirs_predictors(a['date'], roi, viirs_projection, qa_mode)

        stack = preds.addBands(target_coarse.rename('target'))
        fc = stack.sample(
            region=roi, scale=scale,
            projection=viirs_projection,
            numPixels=DCFG['max_samples'],
            seed=DCFG['sample_seed'],
            dropNulls=True, geometries=False,
            tileScale=DCFG['tile_scale'])
        fc = fc.map(lambda f: f.set('anchor_date', a['date']))
        fcs.append(fc)

    merged = fcs[0]
    for fc in fcs[1:]:
        merged = merged.merge(fc)
    return merged


def samples_to_numpy(fc):
    """FeatureCollection → numpy dict (client-side getInfo)."""
    data = fc.reduceColumns(
        reducer=ee.Reducer.toList().repeat(4),
        selectors=['NDVI', 'EVI2', 'NDWI', 'target']).get('list').getInfo()
    return {
        'NDVI':   np.array(data[0], dtype=float),
        'EVI2':   np.array(data[1], dtype=float),
        'NDWI':   np.array(data[2], dtype=float),
        'target': np.array(data[3], dtype=float),
    }


# ==============================================================
# 7. Regressiya fit (client-side numpy — halol metrikalar)
# ==============================================================

def _design_matrix(s, model_name):
    """X (dizayn matritsasi) va ustun nomlari."""
    ndvi = s['NDVI']
    if model_name == 'ndvi':
        X = np.column_stack([np.ones_like(ndvi), ndvi])
        names = ['a', 'b_NDVI']
    elif model_name == 'ndvi2':
        X = np.column_stack([np.ones_like(ndvi), ndvi, ndvi**2])
        names = ['a', 'b_NDVI', 'c_NDVI2']
    elif model_name == 'multi':
        X = np.column_stack([np.ones_like(ndvi), ndvi, s['EVI2'], s['NDWI']])
        names = ['a', 'b_NDVI', 'c_EVI2', 'd_NDWI']
    else:
        raise ValueError(f"Noma'lum model: {model_name}")
    return X, names


def fit_viirs_regression(samples_np, model_name):
    """
    numpy least squares fit. Returns dict:
      coeffs (dict), R2, RMSE, MAE, Bias, N, model_name
    R² SOXTALASHTIRILMAYDI — haqiqiy kuzatuvdan hisoblanadi.
    """
    s = samples_np
    y = s['target']
    X, names = _design_matrix(s, model_name)

    # NaN/inf tozalash
    ok = np.isfinite(y) & np.all(np.isfinite(X), axis=1)
    X, y = X[ok], y[ok]
    n = int(len(y))
    if n < X.shape[1] + 1:
        return {'model_name': model_name, 'N': n, 'error': 'sample yetarli emas'}

    beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ beta
    resid = y - pred

    ss_res = float(np.sum(resid**2))
    ss_tot = float(np.sum((y - y.mean())**2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float('nan')
    rmse = float(np.sqrt(np.mean(resid**2)))
    mae = float(np.mean(np.abs(resid)))
    bias = float(np.mean(resid))

    return {
        'model_name': model_name,
        'coeffs': {names[i]: float(beta[i]) for i in range(len(names))},
        'R2': r2, 'RMSE': rmse, 'MAE': mae, 'Bias': bias, 'N': n,
    }


# ==============================================================
# 8. Coarse target bashorati (server-side)
# ==============================================================

def predict_coarse_target(viirs_predictors, regression_model, model_name,
                          target_mode):
    """
    Regressiya koeffitsientlarini VIIRS predictor tasviriga qo'llab,
    coarse target (Lambda yoki KC) baholaydi. Server-side ee.Image.
    """
    c = regression_model['coeffs']
    ndvi = viirs_predictors.select('NDVI')

    pred = ee.Image.constant(c['a'])
    pred = pred.add(ndvi.multiply(c['b_NDVI']))
    if model_name == 'ndvi2':
        pred = pred.add(ndvi.pow(2).multiply(c['c_NDVI2']))
    elif model_name == 'multi':
        pred = pred.add(viirs_predictors.select('EVI2').multiply(c['c_EVI2']))
        pred = pred.add(viirs_predictors.select('NDWI').multiply(c['d_NDWI']))

    lo, hi = ((DCFG['lambda_min'], DCFG['lambda_max']) if target_mode == 'lambda'
              else (DCFG['kc_min'], DCFG['kc_max']))
    return pred.clamp(lo, hi).rename('target_coarse')


# ==============================================================
# 9. Fazoviy weight (anchor 30 m)
# ==============================================================

def build_spatial_weight(target_30m, viirs_projection, target_mode):
    """
    W = target_30 / mean(target_30 over VIIRS pixel)
    mean(W) har VIIRS pikseli ichida ≈ 1.
    """
    lo, hi = ((DCFG['lambda_min'], DCFG['lambda_max']) if target_mode == 'lambda'
              else (DCFG['kc_min'], DCFG['kc_max']))
    t30 = target_30m.clamp(lo, hi).rename('t')

    coarse = aggregate_to_viirs_grid(t30, viirs_projection)
    safe = coarse.max(DCFG['epsilon'])

    return (t30.divide(safe)
            .clamp(DCFG['weight_min'], DCFG['weight_max'])
            .rename('W'))


# ==============================================================
# 10. Weight temporal interpolatsiya (ikki anchor)
# ==============================================================

def blend_weights(before_weight, before_date, after_weight, after_date,
                  target_date):
    """W_d = (1-α)·W_before + α·W_after."""
    ta = ee.Date(before_date).millis()
    tb = ee.Date(after_date).millis()
    td = ee.Date(target_date).millis()
    alpha = (ee.Number(td).subtract(ta)
             .divide(ee.Number(tb).subtract(ta).max(1)).clamp(0, 1))
    return (before_weight.multiply(ee.Image(1).subtract(alpha))
            .add(after_weight.multiply(alpha)).rename('W'))


# ==============================================================
# 11. Coarse target → 30 m downscale
# ==============================================================

def downscale_target_to_30m(coarse_target, weight, viirs_projection,
                            enforce_conservation=True):
    """
    target_30 = coarse_target × W.
    Conservation: mean(target_30 over VIIRS) ≈ coarse_target.
    """
    ct = coarse_target.reproject(crs=viirs_projection)
    t30 = ct.multiply(weight).rename('target_30')

    if enforce_conservation:
        back = aggregate_to_viirs_grid(t30, viirs_projection).max(1e-6)
        corr = ct.divide(back)
        t30 = t30.multiply(corr).rename('target_30')
    return t30


# ==============================================================
# 12. Daily ET — Lambda mode
# ==============================================================

def daily_rn24(date, roi, albedo, tau_sw):
    """
    Daily RN24 — MAVJUD SEBAL formulasi bilan AYNAN bir xil
    (daily_et.py / monthly_analytics): Rn24 = (1-α)·Rs24 - 110·τsw.
    albedo/τsw anchorlardan interpolyatsiya qilinadi.
    """
    rs24 = ma._get_daily_rs24(date, roi)
    rn24 = ((ee.Image(1.0).subtract(albedo)).multiply(rs24)
            .subtract(ee.Image(cfg.DAILY_ET['rn24_constant']).multiply(tau_sw))
            .max(0).rename('RN24'))
    return rn24


def compute_daily_et_lambda_mode(lambda_30m, rn24_minus_g24):
    """ET_24 = Λ × (Rn24-G24) × (86400/λ).  G24≈0 → RN24."""
    return (lambda_30m.multiply(rn24_minus_g24)
            .multiply(ET_CONV).max(0).rename('ET_24'))


# ==============================================================
# 13. Daily ET — KC mode
# ==============================================================

def compute_daily_et_kc_mode(kc_30m, etref24):
    """ET_24 = KC × ETREF_24."""
    return kc_30m.multiply(etref24).max(0).rename('ET_24')


# ==============================================================
# 14. Conservation metrikalar (diagnostika)
# ==============================================================

def compute_conservation_metrics(target_30, coarse_target, roi,
                                 viirs_projection, stats_scale=1000):
    """mean(target_30 over VIIRS) vs coarse_target — xato statistikasi."""
    back = aggregate_to_viirs_grid(target_30, viirs_projection)
    err = back.subtract(coarse_target.reproject(crs=viirs_projection)).rename('e')
    return err.reduceRegion(
        reducer=(ee.Reducer.mean()
                 .combine(ee.Reducer.stdDev(), sharedInputs=True)
                 .combine(ee.Reducer.minMax(), sharedInputs=True)),
        geometry=roi, scale=stats_scale, maxPixels=1e9, bestEffort=True)


# ==============================================================
# 15. Anchorlardan albedo/τsw interpolyatsiya (Lambda mode ET uchun)
# ==============================================================

def interp_radiation_bands(anchor_images, target_date):
    """albedo va τsw ni anchorlar orasidan interpolyatsiya (reuse)."""
    col = ee.ImageCollection([a['image'] for a in anchor_images])
    interp = ma._interpolate_bands(col, ee.Date(target_date),
                                   ['ALBEDO', 'TAU_SW'])
    return interp.select('ALBEDO'), interp.select('TAU_SW')


# ==============================================================
# 16. Bitta kun uchun 30 m target (clear / interp)
# ==============================================================

def downscaled_target_for_day(date, roi, anchors, weight_provider,
                              regression_model, model_name, target_mode,
                              viirs_projection, qa_mode='lenient'):
    """
    Bitta VIIRS clear kun uchun 30 m target (Lambda yoki KC).
    weight_provider: funksiya(date) -> 30 m weight (anchor yoki blend).
    Returns: ee.Image('target_30') yoki None (VIIRS yo'q bo'lsa).
    """
    # Bulutsiz predictor (kun bulutli bo'lsa ±window kompozitidan)
    preds = clear_viirs_predictors(date, roi, viirs_projection, qa_mode)

    coarse = predict_coarse_target(preds, regression_model, model_name,
                                   target_mode)
    weight = weight_provider(date)
    return downscale_target_to_30m(coarse, weight, viirs_projection)


# ==============================================================
# 17. Oylik ET yig'indisi
# ==============================================================

def build_monthly_et_sum(daily_et_images):
    """ET_month = Σ ET_24_d (har kun)."""
    return ee.ImageCollection(daily_et_images).sum().rename('ET_MONTHLY')


# ==============================================================
# 18. Hold-out validatsiya
# ==============================================================

def validate_holdout(anchors, holdout_idx, roi, viirs_projection,
                     model_name, target_mode, qa_mode='lenient'):
    """
    Bitta anchorni yashirib, qolganlaridan model qurib, yashirilgan
    sanada 30 m target bashorat qilinadi va REAL SEBAL bilan solishtiriladi.
    Returns dict: RMSE, MAE, Bias, Pearson_r, R2, slope, intercept, N.
    """
    train = [a for i, a in enumerate(anchors) if i != holdout_idx]
    hold = anchors[holdout_idx]
    if len(train) < 1:
        return {'error': 'train uchun anchor yo\'q'}

    # Train regressiya
    fc = build_training_samples(train, roi, viirs_projection, target_mode, qa_mode)
    snp = samples_to_numpy(fc)
    reg = fit_viirs_regression(snp, model_name)
    if 'coeffs' not in reg:
        return reg

    # Weight: eng yaqin train anchordan
    tband = _target_band(target_mode)
    nearest = min(train, key=lambda a: abs(
        ee.Date(a['date']).millis().getInfo()
        - ee.Date(hold['date']).millis().getInfo()))
    weight = build_spatial_weight(nearest['image'].select(tband),
                                  viirs_projection, target_mode)

    # Bashorat (holdout sana VIIRS predictorlari bilan)
    pred30 = downscaled_target_for_day(
        hold['date'], roi, train, lambda d: weight, reg, model_name,
        target_mode, viirs_projection, qa_mode)

    real30 = hold['image'].select(tband).rename('target_30')

    # Piksel namunalari (30 m) → numpy
    stack = pred30.rename('pred').addBands(real30.rename('real'))
    samp = stack.sample(region=roi, scale=100, numPixels=DCFG['max_samples'],
                        seed=DCFG['sample_seed'], dropNulls=True,
                        geometries=False, tileScale=DCFG['tile_scale'])
    arr = samp.reduceColumns(ee.Reducer.toList().repeat(2),
                             ['pred', 'real']).get('list').getInfo()
    p = np.array(arr[0], dtype=float)
    r = np.array(arr[1], dtype=float)
    ok = np.isfinite(p) & np.isfinite(r)
    p, r = p[ok], r[ok]
    n = int(len(p))
    if n < 3:
        return {'holdout_date': hold['date'], 'N': n, 'error': 'namuna kam'}

    resid = p - r
    rmse = float(np.sqrt(np.mean(resid**2)))
    mae = float(np.mean(np.abs(resid)))
    bias = float(np.mean(resid))
    pear = float(np.corrcoef(p, r)[0, 1])
    slope, intercept = np.polyfit(r, p, 1)
    ss_res = float(np.sum((r - p)**2))
    ss_tot = float(np.sum((r - r.mean())**2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float('nan')

    return {
        'holdout_date': hold['date'], 'downscale_mode': target_mode,
        'viirs_model': model_name, 'RMSE': rmse, 'MAE': mae, 'Bias': bias,
        'Pearson_r': pear, 'R2': r2, 'slope': float(slope),
        'intercept': float(intercept), 'N': n,
    }


# ==============================================================
# 19. TEMPORAL GAP FILL
# ==============================================================

def fill_temporal_gaps(source_collection, target_date, method='linear'):
    """
    source_collection: clear kunlardagi 'target_30' tasvirlari
    (har birida system:time_start). target_date uchun target_30 ni
    vaqt bo'yicha to'ldiradi.
      linear  : eng yaqin oldingi/keyingi orasida lineer interpolyatsiya
      nearest : eng yaqin kuzatuv
    """
    td = ee.Date(target_date).millis()
    col = source_collection

    before = (col.filter(ee.Filter.lte('system:time_start', td))
              .sort('system:time_start', False))
    after = (col.filter(ee.Filter.gte('system:time_start', td))
             .sort('system:time_start', True))

    has_b = before.size().gt(0)
    has_a = after.size().gt(0)
    default_img = col.mean()

    b_img = ee.Image(ee.Algorithms.If(has_b, before.first(), default_img))
    a_img = ee.Image(ee.Algorithms.If(has_a, after.first(), default_img))

    if method == 'nearest':
        # td ga qaysi yaqin
        b_t = ee.Number(ee.Algorithms.If(
            has_b, b_img.get('system:time_start'), td))
        a_t = ee.Number(ee.Algorithms.If(
            has_a, a_img.get('system:time_start'), td))
        pick_b = ee.Number(td).subtract(b_t).abs().lte(
            a_t.subtract(td).abs())
        result = ee.Image(ee.Algorithms.If(pick_b, b_img, a_img))
        return ee.Image(result).rename('target_30')

    # linear
    b_t = ee.Number(ee.Algorithms.If(has_b, b_img.get('system:time_start'), td))
    a_t = ee.Number(ee.Algorithms.If(has_a, a_img.get('system:time_start'), td))
    rng = a_t.subtract(b_t).max(1)
    w = ee.Number(td).subtract(b_t).divide(rng).min(1).max(0)
    interp = b_img.multiply(ee.Image(1).subtract(w)).add(a_img.multiply(w))
    result = ee.Image(ee.Algorithms.If(
        has_b.And(has_a), interp,
        ee.Algorithms.If(has_b, b_img, a_img)))
    return ee.Image(result).rename('target_30')


# ==============================================================
# 20. KUNLIK DOWNSCALED KOLLEKSIYA + OYLIK ET
# ==============================================================

def _date_ord(date_str):
    """'YYYY-MM-DD' → kun tartibi (getInfo SIZ, sof Python)."""
    return _dt.datetime.strptime(date_str, '%Y-%m-%d').toordinal()


def _days_in_range(start, end):
    """[start, end] — sof Python sana ro'yxati (getInfo YO'Q).
    end QO'SHILADI (oyning oxirgi kuni ham)."""
    s = _dt.datetime.strptime(start, '%Y-%m-%d')
    e = _dt.datetime.strptime(end, '%Y-%m-%d')
    return [(s + _dt.timedelta(days=i)).strftime('%Y-%m-%d')
            for i in range((e - s).days + 1)]


def viirs_available_dates(start, end, roi):
    """Oy ichida VNP09GA mavjud sanalar — BITTA getInfo, qolgani Python."""
    col = (ee.ImageCollection(VNP09GA)
           .filterDate(start, ee.Date(end).advance(1, 'day'))
           .filterBounds(roi))
    millis = col.aggregate_array('system:time_start').getInfo()
    if not millis:
        return []
    # millis → sana: sof Python (getInfo YO'Q)
    return sorted({_dt.datetime.utcfromtimestamp(m / 1000).strftime('%Y-%m-%d')
                   for m in millis})


def _weight_provider(anchors, viirs_projection, target_mode):
    """Sana → 30 m weight (1 anchor: nearest; 2+: blend)."""
    tband = _target_band(target_mode)
    weights = [{
        'date': a['date'],
        'millis': ee.Date(a['date']).millis().getInfo(),
        'w': build_spatial_weight(a['image'].select(tband),
                                  viirs_projection, target_mode),
    } for a in anchors]
    weights.sort(key=lambda x: x['millis'])

    def provider(date):
        td = ee.Date(date).millis().getInfo()
        before = [w for w in weights if w['millis'] <= td]
        after = [w for w in weights if w['millis'] >= td]
        if before and after and before[-1] is not after[0]:
            b, a = before[-1], after[0]
            if b['date'] == a['date']:
                return b['w']
            return blend_weights(b['w'], b['date'], a['w'], a['date'], date)
        return (before[-1]['w'] if before else after[0]['w'])

    return provider


def build_daily_viirs_downscaled_collection(
        start, end, roi, anchors, regression_model, model_name, target_mode,
        viirs_projection, qa_mode='lenient', temporal_fill='linear'):
    """
    Oy ichidagi HAR KUN uchun 30 m target → daily ET.

    1. Clear VIIRS kunlarda target_30 (regressiya+weight+downscale).
    2. Bo'sh kunlar fill_temporal_gaps bilan to'ldiriladi.
    3. Har kun daily ET (lambda yoki kc mode).
    Returns: list[ee.Image('ET_24')] (har kun, time_start bilan)
    """
    provider = _weight_provider(anchors, viirs_projection, target_mode)
    avail = viirs_available_dates(start, end, roi)

    # 1. Clear kunlardagi target_30 manba kolleksiyasi
    source = []
    for d in avail:
        t30 = downscaled_target_for_day(
            d, roi, anchors, provider, regression_model, model_name,
            target_mode, viirs_projection, qa_mode)
        source.append(t30.set('system:time_start', ee.Date(d).millis()))
    source_col = ee.ImageCollection(source)

    # 2-3. Har kun target_30 (interp) → daily ET
    all_days = _days_in_range(start, end)
    daily_et_imgs = []
    for d in all_days:
        t30 = fill_temporal_gaps(source_col, d, temporal_fill)

        if target_mode == 'lambda':
            albedo, tau = interp_radiation_bands(anchors, d)
            rn24 = daily_rn24(d, roi, albedo, tau)
            et = compute_daily_et_lambda_mode(t30, rn24)
        else:  # kc
            etref = _daily_etref(anchors, d, roi)
            et = compute_daily_et_kc_mode(t30, etref)

        daily_et_imgs.append(et.set('system:time_start', ee.Date(d).millis())
                             .set('date', d))
    return daily_et_imgs


# def _daily_etref(anchors, date, roi):
#     """KC mode uchun kunlik ETREF_24 — anchorlardan interpolyatsiya +
#     ERA5 radiatsiya nisbati (monthly_analytics mantig'iga mos)."""
#     col = ee.ImageCollection([a['image'] for a in anchors])
#     interp = ma._interpolate_bands(col, ee.Date(date), ['ETREF_24', 'RN24'])
#     etref_scene = interp.select('ETREF_24')
#     rn_scene = interp.select('RN24').max(1)
#     rs24 = ma._get_daily_rs24(date, roi)
#     rad_ratio = rs24.divide(rn_scene).clamp(0, 1.5)
#     return etref_scene.multiply(rad_ratio).rename('ETREF_24')

def _daily_etref(anchors, date, roi):
    """
    KC mode uchun kunlik ETREF_24 — anchorlardan interpolyatsiya +
    ERA5 radiatsiya nisbati.

    TUZATILDI: avval Rs24 (xom quyosh radiatsiyasi) to'g'ridan-to'g'ri
    Rn24 (neto radiatsiya)ga bo'linardi — bular boshqa-boshqa fizik
    miqdorlar. Endi monthly_analytics.py bilan AYNAN bir xil mantiq:
    avval bugungi Rn24 albedo/tau_sw bilan qayta tiklanadi, keyin
    Rn24(bugun)/Rn24(sahna o'rtacha) nisbati olinadi.
    """
    col = ee.ImageCollection([a['image'] for a in anchors])
    interp = ma._interpolate_bands(
        col, ee.Date(date), ['ETREF_24', 'RN24', 'ALBEDO', 'TAU_SW'])

    etref_scene = interp.select('ETREF_24')
    rn_scene = interp.select('RN24').max(1)
    albedo = interp.select('ALBEDO')
    tau_sw = interp.select('TAU_SW')

    rs24 = ma._get_daily_rs24(date, roi)

    # Bugungi Rn24 — monthly_analytics.py bilan bir xil formula
    rn24_actual = (
        (ee.Image(1.0).subtract(albedo)).multiply(rs24)
        .subtract(ee.Image(cfg.DAILY_ET['rn24_constant']).multiply(tau_sw))
        .max(0)
    )

    rad_ratio = rn24_actual.divide(rn_scene).clamp(0, 1.5)
    return etref_scene.multiply(rad_ratio).rename('ETREF_24')


# ==============================================================
# ASOSIY: TILE uchun oylik ET (VIIRS bilan, asset/reduceResolution YO'Q)
# ==============================================================

def build_tile_monthly_et_viirs(scene_images, info, tile_roi, start, end,
                                target_mode='lambda', model_name='ndvi',
                                qa_mode='lenient', temporal_fill='linear'):
    """
    Bitta TILE uchun VIIRS-kuchaytirilgan oylik ET.

    Oqim (portlashsiz, asset'siz, tile ichida):
      1. Anchor (Landsat/HLS sahnalar) → regressiya (faqat ET bor joydan).
      2. Weight = Λ_30_landsat / predict(VIIRS_anchor)  [reduceResolution YO'Q].
      3. Har VIIRS clear kun: Λ_30 = predict(VIIRS_kun) × W (bilinear 30 m).
      4. NaN (bulutli) joylar ±window NDVI kompoziti + temporal fill bilan.
      5. Har kun ET_24 (SEBAL formulasi), oylik = Σ.

    Returns: ee.Image('ET_MONTHLY') — export uchun (tile_roi ga kesilgan).
    """
    tband = _target_band(target_mode)

    # VIIRS gridi (tile ustidagi bitta tasvirdan)
    vproj = get_viirs_projection(get_viirs_vnp09ga(start, tile_roi))

    anchors = [{'image': ee.Image(s), 'date': info['dates'][i], 'vproj': vproj}
               for i, s in enumerate(scene_images)]

    # 1. Regressiya (30 m namunalar, faqat target bor joyda)
    fc = build_regression_samples_30m(anchors, tile_roi, target_mode, qa_mode)
    snp = samples_to_numpy(fc)
    reg = fit_viirs_regression(snp, model_name)
    if 'coeffs' not in reg:
        raise RuntimeError(f"VIIRS regressiya fit bo'lmadi: {reg}")
    print(f"    VIIRS regressiya [{model_name}]: R2={reg['R2']:.3f} "
          f"RMSE={reg['RMSE']:.3f} N={reg['N']}")

    # 2. Har anchor uchun weight (prediction-based). Sana taqqoslash —
    #    sof Python (getInfo YO'Q → 429 "concurrent aggregations" oldini oladi).
    weights = []
    for a in anchors:
        preds_a = clear_viirs_predictors(a['date'], tile_roi, vproj, qa_mode)
        w = weight_from_prediction(a['image'].select(tband), preds_a,
                                   reg, model_name, target_mode)
        weights.append({'date': a['date'], 'ord': _date_ord(a['date']), 'w': w})
    weights.sort(key=lambda x: x['ord'])

    def weight_for(date):
        td = _date_ord(date)
        before = [w for w in weights if w['ord'] <= td]
        after = [w for w in weights if w['ord'] >= td]
        if before and after and before[-1]['date'] != after[0]['date']:
            b, a = before[-1], after[0]
            return blend_weights(b['w'], b['date'], a['w'], a['date'], date)
        return (before[-1]['w'] if before else after[0]['w'])

    # 3. Har VIIRS clear kun: Λ_30 = predict × W
    avail = viirs_available_dates(start, end, tile_roi)
    print(f"    VIIRS clear kunlar: {len(avail)}")
    source = []
    for d in avail:
        preds_d = clear_viirs_predictors(d, tile_roi, vproj, qa_mode)
        lam_d = predict_coarse_target(preds_d, reg, model_name, target_mode)
        lam30 = lam_d.multiply(weight_for(d)).rename('target_30')
        source.append(lam30.set('system:time_start', ee.Date(d).millis()))
    source_col = ee.ImageCollection(source)

    # 4-5. Har kun: temporal fill → daily ET → oylik sum
    daily_et_imgs = []
    for d in _days_in_range(start, end):
        lam = fill_temporal_gaps(source_col, d, temporal_fill)
        if target_mode == 'lambda':
            albedo, tau = interp_radiation_bands(anchors, d)
            rn24 = daily_rn24(d, tile_roi, albedo, tau)
            et = compute_daily_et_lambda_mode(lam, rn24)
        else:
            etref = _daily_etref(anchors, d, tile_roi)
            et = compute_daily_et_kc_mode(lam, etref)
        daily_et_imgs.append(et.set('system:time_start', ee.Date(d).millis()))

    monthly = ee.ImageCollection(daily_et_imgs).sum().rename('ET_MONTHLY')
    return monthly.clip(tile_roi).set('viirs_r2', reg['R2'],
                                      'viirs_model', model_name)
