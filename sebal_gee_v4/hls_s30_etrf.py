"""
SEBAL-GEE v4 — HLS S30 ETrF regression downscaling
====================================================
L30 (Landsat/HLS) SEBAL ET ni HLS **S30** (Sentinel-2, 30 m) tasvirlari
yordamida oy ichida kunlik ETrF time-series ga aylantiradi.

S30 ham, L30 ham 30 m → downscaling/weight/reduceResolution KERAK EMAS.
To'g'ridan-to'g'ri regressiya: ETrF ~ S30 indekslari.

MANTIQ
------
  1. L30 anchor → ETrF = ET24 / ETREF_24.
  2. HLS S30 (shu tile, sana, L30 filtrlari).
  3. Har anchor → eng yaqin S30 (±N kun) → indekslar.
  4. Regressiya: ETrF ~ f(indeks), FAQAT data-present pikseldan (dropNulls).
     Modellar: ndvi | ndvi2 | multi | multi6.
  5. Tenglama BUTUN tile S30 ga → har S30 kun ETrF.
  6. 2+ anchor → vaqt bo'yicha blend.
  7. PER-PIXEL temporal inter/ekstrapolyatsiya.
  8. ET_daily = ETrF × ETREF_24_daily; oylik = Σ. Per-tile.
  9. Diagnostika (R²/N/eng yaqin S30) + ixtiyoriy hold-out + cropland mask.

SEBAL fizikasi O'ZGARMAYDI.
"""

import ee
import numpy as np

from . import config as cfg
from . import preprocessing
from .viirs_downscaling import (
    DCFG, samples_to_numpy, _date_ord, _days_in_range, _daily_etref,
)


# ==============================================================
# KONFIGURATSIYA
# ==============================================================

HLSS30 = 'NASA/HLS/HLSS30/v002'

# S30 (Sentinel-2) bandlar
S30_B = {
    'blue': 'B2', 'green': 'B3', 'red': 'B4',
    'nir': 'B8A', 'swir1': 'B11', 'swir2': 'B12', 'qa': 'Fmask',
}

ETRF = {'etrf_max': 1.5, 'eps': 0.05}

# Har model uchun dizayn-matritsa hadlari (intercept har doim qo'shiladi).
# 'NDVI2' = NDVI². Boshqalar — indeks bandining o'zi.
S30_TERMS = {
    'ndvi':   ['NDVI'],
    'ndvi2':  ['NDVI', 'NDVI2'],
    'multi':  ['NDVI', 'EVI2', 'NDWI'],
    'multi6': ['NDVI', 'SAVI', 'NDWI', 'LSWI', 'Albedo_idx'],
}
MODELS = tuple(S30_TERMS.keys())

# Anchor↔S30 juftligi uchun maksimal kun farqi (undan uzoq → tashlanadi)
MAX_PAIR_DAYS = 10


# ==============================================================
# 1. S30 kolleksiyasi (L30 dagi filtrlar bilan)
# ==============================================================

def get_s30_collection(tile_roi, start, end, cloud_max=70, mgrs_tile=None):
    """HLS S30 — L30 dagi xuddi shu filtrlar (bounds/date/cloud/MGRS/crop)."""
    col = (ee.ImageCollection(HLSS30)
           .filterBounds(tile_roi)
           .filterDate(start, ee.Date(end).advance(1, 'day'))
           .filter(ee.Filter.lt('CLOUD_COVERAGE', cloud_max)))
    if mgrs_tile is not None:
        tid = mgrs_tile if mgrs_tile.startswith('T') else f'T{mgrs_tile}'
        col = col.filter(ee.Filter.stringContains('system:index', tid))
    col = preprocessing.filter_by_crop_cloud_hls(col, tile_roi,
                                                 cfg.CROP_CLOUD_MAX)
    return col


# ==============================================================
# 2. S30 bulut maskasi (Fmask)
# ==============================================================

def mask_s30(img, qa_mode='lenient'):
    """HLS S30 Fmask bulut/soya/qor maskasi (L30 mantig'i)."""
    f = img.select(S30_B['qa'])
    cloud = f.bitwiseAnd(cfg.HLS_QA_BITMASK['cloud']).gt(0)
    shadow = f.bitwiseAnd(cfg.HLS_QA_BITMASK['cloud_shadow']).gt(0)
    if qa_mode == 'strict':
        adjacent = f.bitwiseAnd(cfg.HLS_QA_BITMASK['adjacent']).gt(0)
        cirrus = f.bitwiseAnd(cfg.HLS_QA_BITMASK['cirrus']).gt(0)
        snow = f.bitwiseAnd(cfg.HLS_QA_BITMASK['snow']).gt(0)
        bad = cloud.Or(shadow).Or(adjacent).Or(cirrus).Or(snow)
    else:
        bad = cloud.Or(shadow)
    return img.updateMask(bad.Not())


# ==============================================================
# 3. S30 indekslar (NDVI, EVI2, SAVI, NDWI, LSWI, Albedo_idx)
# ==============================================================

def s30_indices(img):
    """
    Regressiya predictorlari — S30 (B2/B3/B4/B8A/B11/B12) dan.
      NDVI = (NIR-RED)/(NIR+RED)
      EVI2 = 2.5(NIR-RED)/(NIR+2.4·RED+1)
      SAVI = 1.5(NIR-RED)/(NIR+RED+0.5)            (Huete 1988)
      NDWI = (GREEN-NIR)/(GREEN+NIR)               (McFeeters 1996, suv)
      LSWI = (NIR-SWIR1)/(NIR+SWIR1)               (Xiao 2004, o'simlik namligi)
      Albedo_idx = Tasumi (2008) sodda albedo
    """
    blue = img.select(S30_B['blue'])
    green = img.select(S30_B['green'])
    red = img.select(S30_B['red'])
    nir = img.select(S30_B['nir'])
    sw1 = img.select(S30_B['swir1'])
    sw2 = img.select(S30_B['swir2'])

    ndvi = nir.subtract(red).divide(nir.add(red)).clamp(-1, 1).rename('NDVI')
    evi2 = (nir.subtract(red).multiply(2.5)
            .divide(nir.add(red.multiply(2.4)).add(1.0))).rename('EVI2')
    savi = (nir.subtract(red).multiply(1.5)
            .divide(nir.add(red).add(0.5))).clamp(-1, 1).rename('SAVI')
    ndwi = green.subtract(nir).divide(green.add(nir)).clamp(-1, 1).rename('NDWI')
    lswi = nir.subtract(sw1).divide(nir.add(sw1)).clamp(-1, 1).rename('LSWI')
    albedo = (blue.multiply(0.254).add(green.multiply(0.149))
              .add(red.multiply(0.147)).add(nir.multiply(0.311))
              .add(sw1.multiply(0.103)).add(sw2.multiply(0.036))
              .clamp(0.05, 0.60).rename('Albedo_idx'))

    return (ndvi.addBands(evi2).addBands(savi)
            .addBands(ndwi).addBands(lswi).addBands(albedo))


def s30_day_indices(s30_col, date, qa_mode='lenient'):
    """Bitta kun uchun maskalangan S30 mozaikasi → indekslar."""
    d = ee.Date(date)
    daily = (s30_col.filterDate(d, d.advance(1, 'day'))
             .map(lambda im: mask_s30(im, qa_mode)).mosaic())
    return s30_indices(daily)


# ==============================================================
# 4. ETrF (anchor) va sana yordamchilari
# ==============================================================

def compute_etrf(anchor_image):
    """ETrF = ET24 / ETREF_24 (o'sha kungi), nolga bo'linish himoyasi."""
    et24 = anchor_image.select('ET_24')
    etref = anchor_image.select('ETREF_24').max(ETRF['eps'])
    return et24.divide(etref).clamp(0, ETRF['etrf_max']).rename('target')


def s30_available_dates(s30_col):
    """S30 mavjud sanalar — BITTA getInfo, qolgani Python."""
    import datetime as _dt
    millis = s30_col.aggregate_array('system:time_start').getInfo()
    if not millis:
        return []
    return sorted({_dt.datetime.utcfromtimestamp(m / 1000).strftime('%Y-%m-%d')
                   for m in millis})


def _closest_date(target, candidates):
    to = _date_ord(target)
    return min(candidates, key=lambda d: abs(_date_ord(d) - to))


# ==============================================================
# 5. MODEL-DRIVEN regressiya (numpy lstsq, halol metrikalar)
# ==============================================================

def _model_raw_bands(model_name):
    """Model uchun S30 dan o'qiladigan XOM indeks bandlari."""
    raw = []
    for t in S30_TERMS[model_name]:
        b = 'NDVI' if t == 'NDVI2' else t
        if b not in raw:
            raw.append(b)
    return raw


def _build_design(model_name, cols):
    """cols: {band: np.array}. → X (dizayn matritsa), nomlar."""
    n = len(next(iter(cols.values())))
    X = [np.ones(n)]
    names = ['intercept']
    for t in S30_TERMS[model_name]:
        if t == 'NDVI2':
            X.append(cols['NDVI'] ** 2)
        else:
            X.append(cols[t])
        names.append(t)
    return np.column_stack(X), names


def fit_s30_regression(cols, model_name):
    """
    numpy least squares. Returns dict: coeffs, R2, RMSE, MAE, Bias, N.
    R² SOXTALASHTIRILMAYDI.
    """
    y = cols['target']
    X, names = _build_design(model_name, cols)
    ok = np.isfinite(y) & np.all(np.isfinite(X), axis=1)
    X, y = X[ok], y[ok]
    n = int(len(y))
    if n < X.shape[1] + 1:
        return {'model_name': model_name, 'N': n, 'error': 'namuna kam'}

    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    return {
        'model_name': model_name,
        'coeffs': {names[i]: float(beta[i]) for i in range(len(names))},
        'R2': (1 - ss_res / ss_tot) if ss_tot > 0 else float('nan'),
        'RMSE': float(np.sqrt(np.mean(resid ** 2))),
        'MAE': float(np.mean(np.abs(resid))),
        'Bias': float(np.mean(resid)),
        'N': n,
    }


def predict_etrf(indices_img, reg, model_name):
    """Regressiya tenglamasini S30 indekslariga qo'llab ETrF (30 m)."""
    c = reg['coeffs']
    p = ee.Image.constant(c['intercept'])
    for t in S30_TERMS[model_name]:
        if t == 'NDVI2':
            p = p.add(indices_img.select('NDVI').pow(2).multiply(c[t]))
        else:
            p = p.add(indices_img.select(t).multiply(c[t]))
    return p.clamp(0, ETRF['etrf_max']).rename('target_30')


def fit_anchor(anchor_image, s30_col, anchor_date, s30_dates, tile_roi,
               model_name, qa_mode='lenient', sample_scale=30):
    """
    Anchor ETrF ~ eng yaqin S30 regressiyasi.
    Returns: (reg, closest_s30_date, days_diff)
    """
    cd = _closest_date(anchor_date, s30_dates)
    days_diff = abs(_date_ord(anchor_date) - _date_ord(cd))
    idx = s30_day_indices(s30_col, cd, qa_mode)
    etrf = compute_etrf(anchor_image)

    bands = _model_raw_bands(model_name)
    stack = idx.select(bands).addBands(etrf)
    fc = stack.sample(
        region=tile_roi, scale=sample_scale,
        numPixels=DCFG['max_samples'], seed=DCFG['sample_seed'],
        dropNulls=True, geometries=False, tileScale=DCFG['tile_scale'])
    cols = _read_cols(fc, bands + ['target'])
    reg = fit_s30_regression(cols, model_name)
    return reg, cd, days_diff


def _read_cols(fc, names):
    """FeatureCollection → {name: np.array} (bitta getInfo)."""
    data = fc.reduceColumns(
        ee.Reducer.toList().repeat(len(names)), names).get('list').getInfo()
    return {names[i]: np.array(data[i], dtype=float) for i in range(len(names))}


# ==============================================================
# 6. PER-PIXEL temporal inter/ekstrapolyatsiya
# ==============================================================

def _empty_like():
    """To'liq maskalangan 2-bandli (target_30, t) tasvir."""
    z = ee.Image.constant(0).updateMask(ee.Image.constant(0))
    return z.rename('target_30').addBands(z.rename('t'))


def interp_temporal_per_pixel(source_col, target_date, method='linear'):
    """
    HAR PIKSEL uchun vaqt bo'yicha inter/ekstrapolyatsiya.

    qualityMosaic orqali har piksel uchun ENG YAQIN valid oldingi/keyingi
    kuzatuv (vaqt bandi bilan) olinadi → image-level emas, piksel-level.
      linear  : oldingi va keyingi orasida lineer
      nearest : eng yaqin
    Bo'sh tomonlar (oy chetida) mavjud tomon bilan to'ladi (ekstrapolyatsiya).
    """
    td = ee.Number(ee.Date(target_date).millis())

    def with_t(img):
        t = (ee.Image.constant(img.get('system:time_start')).toDouble()
             .updateMask(img.select('target_30').mask()).rename('t'))
        return img.addBands(t)

    sc = source_col.map(with_t)
    before = sc.filter(ee.Filter.lte('system:time_start', td))
    after = sc.filter(ee.Filter.gte('system:time_start', td))

    # per-pixel: eng so'nggi valid (max t) / eng yaqin keyingi (max -t)
    b = ee.Image(ee.Algorithms.If(before.size().gt(0),
                                  before.qualityMosaic('t'), _empty_like()))
    after_n = after.map(lambda im: im.addBands(
        im.select('t').multiply(-1).rename('nt')))
    a = ee.Image(ee.Algorithms.If(after.size().gt(0),
                                  after_n.qualityMosaic('nt'), _empty_like()))

    bv, bt = b.select('target_30'), b.select('t')
    av, at = a.select('target_30'), a.select('t')

    if method == 'nearest':
        pick_b = td.subtract(bt).abs().lte(at.subtract(td).abs())
        out = bv.where(pick_b.Not(), av)
    else:  # linear
        w = td.subtract(bt).divide(at.subtract(bt).max(1)).clamp(0, 1)
        out = bv.multiply(ee.Image(1).subtract(w)).add(av.multiply(w))

    # Bir tomonlama (ekstrapolyatsiya): bo'sh joyni mavjud tomon to'ldiradi
    out = out.unmask(bv).unmask(av)
    return out.rename('target_30')


# ==============================================================
# 7. ASOSIY: TILE uchun oylik ET
# ==============================================================

def build_tile_monthly_etrf_s30(scenes, info, tile_roi, start, end,
                                model_name='ndvi', qa_mode='lenient',
                                temporal_fill='linear', cloud_max=70,
                                mgrs_tile=None, max_pair_days=MAX_PAIR_DAYS,
                                cropland_only=False):
    """
    Bitta TILE uchun S30-ETrF oylik ET.
    Returns: (ee.Image('ET_MONTHLY'), diag_rows[list[dict]])
    """
    anchors = [{'image': ee.Image(s), 'date': info['dates'][i],
                'ord': _date_ord(info['dates'][i])}
               for i, s in enumerate(scenes)]

    s30_col = get_s30_collection(tile_roi, start, end, cloud_max, mgrs_tile)
    s30_dates = s30_available_dates(s30_col)
    print(f"    S30 clear kunlar: {len(s30_dates)}")
    if not s30_dates:
        raise RuntimeError("S30 tasvir topilmadi")

    # Har anchor → regressiya (±N kun oynasi, past R²/uzoq juftlik flag)
    regs, diag = [], []
    for a in anchors:
        reg, cd, dd = fit_anchor(a['image'], s30_col, a['date'], s30_dates,
                                 tile_roi, model_name, qa_mode)
        ok = ('coeffs' in reg)
        far = dd > max_pair_days
        diag.append({'anchor_date': a['date'], 'closest_s30': cd,
                     'days_diff': dd, 'model': model_name,
                     'R2': reg.get('R2'), 'RMSE': reg.get('RMSE'),
                     'N': reg.get('N'),
                     'used': ok and not far})
        if not ok:
            print(f"    ⚠️ {a['date']}: fit yo'q ({reg.get('error')})")
            continue
        flag = ' [UZOQ→tashlandi]' if far else ''
        print(f"    [{a['date']}→S30 {cd} Δ{dd}k] {model_name}: "
              f"R2={reg['R2']:.3f} N={reg['N']}{flag}")
        if not far:
            regs.append({'date': a['date'], 'ord': a['ord'], 'reg': reg})

    if not regs:  # hammasi uzoq bo'lsa — eng yaqinini baribir ishlatamiz
        best = min((d for d in diag if d['R2'] is not None),
                   key=lambda d: d['days_diff'], default=None)
        if best is None:
            raise RuntimeError("Hech bir anchor uchun regressiya bo'lmadi")
        a = next(x for x in anchors if x['date'] == best['anchor_date'])
        reg, cd, dd = fit_anchor(a['image'], s30_col, a['date'], s30_dates,
                                 tile_roi, model_name, qa_mode)
        regs.append({'date': a['date'], 'ord': a['ord'], 'reg': reg})
    regs.sort(key=lambda r: r['ord'])

    # Har S30 kun → ETrF (2+ anchor → vaqt blend)
    def etrf_for_day(date, idx):
        do = _date_ord(date)
        before = [r for r in regs if r['ord'] <= do]
        after = [r for r in regs if r['ord'] >= do]
        if before and after and before[-1]['date'] != after[0]['date']:
            b, a = before[-1], after[0]
            pa = predict_etrf(idx, b['reg'], model_name)
            pb = predict_etrf(idx, a['reg'], model_name)
            alpha = (do - b['ord']) / (a['ord'] - b['ord'])
            return pa.multiply(1 - alpha).add(pb.multiply(alpha))
        r = before[-1] if before else after[0]
        return predict_etrf(idx, r['reg'], model_name)

    source = []
    for d in s30_dates:
        idx_d = s30_day_indices(s30_col, d, qa_mode)
        etrf_d = etrf_for_day(d, idx_d).rename('target_30')
        source.append(etrf_d.set('system:time_start', ee.Date(d).millis()))
    source_col = ee.ImageCollection(source)

    # Har kun: per-pixel ETrF × ETREF_24_daily → ET; oylik = Σ
    daily_et = []
    for day in _days_in_range(start, end):
        etrf = interp_temporal_per_pixel(source_col, day, temporal_fill)
        etref24 = _daily_etref(anchors, day, tile_roi)
        et = etrf.multiply(etref24).max(0).rename('ET_24')
        daily_et.append(et.set('system:time_start', ee.Date(day).millis()))

    monthly = ee.ImageCollection(daily_et).sum().rename('ET_MONTHLY')
    if cropland_only:
        monthly = monthly.updateMask(preprocessing.get_cropland_mask())
    monthly = monthly.clip(tile_roi).set('s30_model', model_name,
                                         's30_anchors', len(regs))
    return monthly, diag


# ==============================================================
# 8. HOLD-OUT VALIDATSIYA (ixtiyoriy)
# ==============================================================

def validate_holdout_s30(scenes, info, tile_roi, start, end, holdout_idx,
                         model_name='ndvi', qa_mode='lenient', cloud_max=70,
                         mgrs_tile=None):
    """
    Bitta L30 anchorni yashirib, qolganlaridan + S30 dan bashorat qilib,
    yashirilgan kundagi REAL ETrF bilan solishtiradi.
    Returns dict: RMSE, MAE, Bias, Pearson_r, R2, slope, intercept, N.
    """
    anchors = [{'image': ee.Image(s), 'date': info['dates'][i],
                'ord': _date_ord(info['dates'][i])}
               for i, s in enumerate(scenes)]
    if len(anchors) < 2:
        return {'error': '2+ anchor kerak'}

    hold = anchors[holdout_idx]
    train = [a for i, a in enumerate(anchors) if i != holdout_idx]

    s30_col = get_s30_collection(tile_roi, start, end, cloud_max, mgrs_tile)
    s30_dates = s30_available_dates(s30_col)
    if not s30_dates:
        return {'error': 'S30 yo\'q'}

    # Train anchorlardan eng yaqin (vaqt bo'yicha) ni regressiya
    nearest = min(train, key=lambda a: abs(a['ord'] - hold['ord']))
    reg, cd, dd = fit_anchor(nearest['image'], s30_col, nearest['date'],
                             s30_dates, tile_roi, model_name, qa_mode)
    if 'coeffs' not in reg:
        return reg

    # Holdout kuni uchun bashorat (eng yaqin S30 indeks)
    hcd = _closest_date(hold['date'], s30_dates)
    idx = s30_day_indices(s30_col, hcd, qa_mode)
    pred = predict_etrf(idx, reg, model_name)
    real = compute_etrf(hold['image']).rename('target_30')

    stack = pred.rename('pred').addBands(real.rename('real'))
    fc = stack.sample(region=tile_roi, scale=30, numPixels=DCFG['max_samples'],
                      seed=DCFG['sample_seed'], dropNulls=True,
                      geometries=False, tileScale=DCFG['tile_scale'])
    cols = _read_cols(fc, ['pred', 'real'])
    p, r = cols['pred'], cols['real']
    ok = np.isfinite(p) & np.isfinite(r)
    p, r = p[ok], r[ok]
    n = int(len(p))
    if n < 3:
        return {'holdout_date': hold['date'], 'N': n, 'error': 'namuna kam'}

    resid = p - r
    slope, intercept = np.polyfit(r, p, 1)
    ss_res = float(np.sum((r - p) ** 2))
    ss_tot = float(np.sum((r - r.mean()) ** 2))
    return {
        'holdout_date': hold['date'], 'model': model_name, 'N': n,
        'RMSE': float(np.sqrt(np.mean(resid ** 2))),
        'MAE': float(np.mean(np.abs(resid))),
        'Bias': float(np.mean(resid)),
        'Pearson_r': float(np.corrcoef(p, r)[0, 1]),
        'R2': (1 - ss_res / ss_tot) if ss_tot > 0 else float('nan'),
        'slope': float(slope), 'intercept': float(intercept),
    }
