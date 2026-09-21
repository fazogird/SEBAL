"""
SEBAL-GEE v4 — M5-M8: Energy Balance (SEBAL yuragi)
=====================================================
Bu modul SEBAL algoritmining eng muhim qismi:

  M5: Anchor pixel selection (cold/hot)
  M6: Wind & momentum (ERA5 → u*)
  M7: Sensible heat flux H (δTa + Monin-Obukhov iteratsiya)
  M8: Latent heat flux λE = Q* - G₀ - H

Bastiaanssen (1998) Formulalar: F.24-32
Gediz (2001): F.5-12

Input:  Image with surface properties + radiation
Output: Image with H, lambda_E, ETrF bands
"""

import ee
from . import config as cfg
from . import ref_et   # SEBAL_ID: instant alfalfa ETr (cold/hot λET)

class SceneQCError(Exception):
    """Sahna fizik sifat tekshiruvidan o'tmadi (kalibratsiya buzilgan) —
    main.process_tile uni sababi bilan rad etadi va hisobotga yozadi."""


# Anchor tanlash masshtabi (m) — BARCHA rejimlarda 100 m (user qarori 2026-09-19).
# Landsat TIRS termal native 100 m; 30 m LST — interpolyatsiya (30 m dagi "eng
# sovuq/issiq" piksel ko'pincha interpolyatsiya/chekka artefakti). Sinov (Samarqand,
# SEBAL_Milliy): 07-11 da 30 m cold anchor Ta-anomaliya pikseli edi (dT_cold −9.4 K,
# rah 220 s/m), 100 m da normal (−1.4 K); ekinzor ET farqi −0.6…−3.9 % (07-11: −13 %);
# 25–40 % tez. ET rasteri 30 m da qoladi — 100 m faqat anchor tanlash va namunasi.
ANCHOR_SCALE = 100

# Cold (ho'l) anchor referens-ET fraksiyasi: λET_cold = COLD_ETRF · ETr_inst.
# Tasumi/SEBAL_ID default 1.05 (sug'oriladigan to'liq-qoplama ekin advektsiyada
# alfalfa-referensdan biroz ko'p transpiratsiya qiladi). METRIC amaliyoti ba'zan
# 0.85 gacha tushiradi (daily ET ortiqcha-baholashni kamaytiradi — Allen METRIC).
# main.run(cold_etrf=…) buni override qiladi (default 1.05 → SEBAL_ID o'zgarmaydi).
# SEBAL_Milliy'da ground-truth kalibratsiya uchun sinaladi.
COLD_ETRF = 1.05


# ==============================================================
# TILE-DARAJASIDA CROPLAND ZONASI — bir marta hisoblanadi
# ==============================================================

def analysis_proj(image):
    """
    Yagona TAHLIL GRIDI — Landsat/HLS reflektiv (NDVI) proyeksiyasi (UTM 30 m).
    Anchor va CSV reduksiyalari shu gridda (crs ANIQ beriladi). reduceRegion'da
    crs berilmasa birinchi bandning default proyeksiyasi olinadi — hisoblangan
    bandlarda u buzilishi mumkin (SMW LST — ERA5 0.25°, ee.Image(konstanta).where
    — WGS84 1°). Barcha rejimlar (SEBAL_B, SEBAL_ID, SEBAL_Milliy) AYNI gridda.
    """
    return image.select('NDVI').projection()


def _landcover_mask(classes):
    """ESA WorldCover'dan berilgan klasslar uchun 0/1 mask (10 m, masklamagan)."""
    wc = ee.ImageCollection(cfg.CROPLAND_COLLECTION).first().select('Map')
    m = wc.eq(classes[0])
    for c in classes[1:]:
        m = m.Or(wc.eq(c))
    return m


def _utm_projection(roi, scale):
    """roi markazining UTM zonasi (metrli grid) — ulush rasmi shu gridda quriladi."""
    lon, lat = roi.centroid(100).coordinates().getInfo()
    zone = int((lon + 180) // 6) + 1
    epsg = (32600 if lat >= 0 else 32700) + zone
    return ee.Projection(f'EPSG:{epsg}').atScale(scale)


def _landcover_fraction(classes, proj):
    """
    Anchor masshtabidagi piksel ICHIDAGI sinf ULUSHI (0..1): 10 m WorldCover
    0/1 maskasi → reduceResolution(mean) → proj (UTM, ANCHOR_SCALE).
    Eng yaqin piksel (nearest) EMAS — 100 m pikselning markazidagi bitta 10 m
    piksel emas, butun piksel tarkibi hisobga olinadi.
    """
    return (_landcover_mask(classes).toFloat()
            .reduceResolution(ee.Reducer.mean(), maxPixels=1024)
            .reproject(proj))


def compute_tile_anchor_zones(tile_roi, min_pixel_count=None):
    """
    ESA WorldCover'dan COLD va HOT anchor zonalarining SINF ULUSHI rasmlari —
    TILE uchun BIR MARTA (klassik SEBAL: cold va hot AYRIM land-cover).

      cold = cfg.ANCHOR_LANDCOVER['cold']  (40 Cropland) — sug'orilgan, nam
      hot  = cfg.ANCHOR_LANDCOVER['hot']   (60 Bare + 20 Shrub) — doim quruq

    MUHIM: hot cropland'dan EMAS — to'liq sug'orilgan mavsumda (iyul-sentyabr)
    cropland ichidagi "eng issiq" piksel ham transpiratsiya qiladi (lambdaE!=0)
    -> dT_hot oshadi -> ET past baholanadi (kuzatilgan +44% iyul biasining sababi).

    Zona ANCHOR_SCALE pikselidagi sinf ulushi bo'yicha: sahnada ulush ≥ 0.80 →
    yetmasa 0.70 → 0.60 → ROI (_purity_zones, cfg.ANCHOR_LANDCOVER['purity_steps']).

    Returns
    -------
    (cold_zone, hot_zone) : (ee.Image yoki None, ee.Image yoki None)
        Har biri ulush rasmi (0..1, 'COLD_FRAC'/'HOT_FRAC'). Tile'da eng past
        bosqichda ham <min_pixel_count piksel bo'lsa -> None (cheklovsiz ROI).
    """
    lc = cfg.ANCHOR_LANDCOVER
    if min_pixel_count is None:
        min_pixel_count = cfg.ANCHOR['min_candidates']
    steps = tuple(lc['purity_steps'])
    proj = _utm_projection(tile_roi, ANCHOR_SCALE)
    cold_f = _landcover_fraction(lc['cold'], proj).rename('COLD_FRAC')
    hot_f = _landcover_fraction(lc['hot'], proj).rename('HOT_FRAC')

    # Tile darajasida har bosqich uchun piksel soni (ANCHOR_SCALE gridida)
    stats = {}
    for tag, f in (('cold', cold_f), ('hot', hot_f)):
        for thr in steps:
            stats[f'{tag}_{thr:.2f}'] = f.gte(thr).rename('c').reduceRegion(
                ee.Reducer.sum(), tile_roi, ANCHOR_SCALE, maxPixels=1e10,
                bestEffort=True, tileScale=4).get('c')
    counts = ee.Dictionary(stats).getInfo()

    def _fmt(tag):
        return '  '.join(f"≥{thr:.2f}: {(counts.get(f'{tag}_{thr:.2f}') or 0):.0f}"
                         for thr in steps)
    print(f"  Cold (cropland {lc['cold']}) ulush px @{ANCHOR_SCALE}m | {_fmt('cold')}")
    print(f"  Hot (bare+shrub {lc['hot']}) ulush px @{ANCHOR_SCALE}m | {_fmt('hot')}")

    low = f'{min(steps):.2f}'
    cold_zone = cold_f if (counts.get(f'cold_{low}') or 0) >= min_pixel_count else None
    hot_zone = hot_f if (counts.get(f'hot_{low}') or 0) >= min_pixel_count else None
    if cold_zone is None:
        print(f"  ! Cold zona (ulush ≥{low}) <{min_pixel_count} px -> cold cheklovsiz (ROI)")
    if hot_zone is None:
        print(f"  ! Hot zona (ulush ≥{low}) <{min_pixel_count} px -> hot cheklovsiz (ROI)")

    return cold_zone, hot_zone


def _purity_zones(base_flat, cold_zone, hot_zone, roi, proj):
    """
    Sahna uchun cold va hot anchor zonalari: base_flat ∧ (sinf ulushi ≥ thr).
    thr = 0.80 → nomzod yetmasa 0.70 → 0.60 → ROI (base_flat, cheklovsiz).
    "Yetarli" = valid zona piksellari soni ≥ cfg.ANCHOR['min_candidates']
    (100 m da sanaladi; tile darajasidagi compute_tile_anchor_zones bilan bir xil ≥).

    Chegara sahna uchun BIR MARTA client-side tanlanadi (bitta getInfo): keyingi
    GEE so'rovlariga ichma-ich If-hisoblar kirmaydi (grafik yengil, tez).

    Returns (cold_base, cold_thr, hot_base, hot_thr) — thr float; 0.0 = ROI.
    """
    lc = cfg.ANCHOR_LANDCOVER
    steps = sorted(lc['purity_steps'], reverse=True)      # 0.80, 0.70, 0.60
    bands = []
    for tag, frac in (('c', cold_zone), ('h', hot_zone)):
        if frac is None:
            continue
        for k, thr in enumerate(steps):
            bands.append(base_flat.And(frac.gte(thr)).rename(f'{tag}{k}'))
    counts = {}
    if bands:
        counts = ee.Image.cat(bands).reduceRegion(
            ee.Reducer.sum(), roi, crs=proj, scale=100, maxPixels=1e9,
            bestEffort=True, tileScale=4).getInfo()

    def _pick(tag, frac):
        if frac is None:
            return base_flat, 0.0
        for k, thr in enumerate(steps):
            if (counts.get(f'{tag}{k}') or 0) >= cfg.ANCHOR['min_candidates']:
                return base_flat.And(frac.gte(thr)), float(thr)
        return base_flat, 0.0

    cold_base, cold_thr = _pick('c', cold_zone)
    hot_base, hot_thr = _pick('h', hot_zone)
    return cold_base, cold_thr, hot_base, hot_thr


def compute_tile_cropland_zone(tile_roi, min_pixel_count=20):
    """
    Tile va ESA WorldCover cropland (class 40) kesishmasini GEOMETRIYA
    sifatida ajratib oladi — har sahnada emas, TILE uchun BIR MARTA.

    Bu — 'select_anchor_pixels()'dagi reduceRegion'larni butun
    185x185km tile o'rniga faqat cropland zonasida ishlatish imkonini
    beradi: tezroq, va agar cropland umuman yo'q bo'lsa — buni
    sahnalar siklidan OLDIN, aniq bilib olamiz.

    Returns
    -------
    (geometry, is_viable) : (ee.Geometry yoki None, bool)
        is_viable=False bo'lsa — bu tile'da cropland yetarli emas,
        chaqiruvchi kod cropland cheklovisiz davom etishi kerak.
    """
    cropland_raster = (
        ee.ImageCollection('ESA/WorldCover/v200').first()
        .select('Map').eq(40)
    )

    # Piksel sonini tekshiramiz (tez, coarse scale)
    px_count = cropland_raster.reduceRegion(
        reducer=ee.Reducer.sum(), geometry=tile_roi, scale=100,
        maxPixels=1e10, bestEffort=True
    ).get('Map')
    px_count = ee.Number(ee.Algorithms.If(px_count, px_count, 0)).getInfo()

    print(f"  🌾 Tile ichidagi cropland piksel soni (~100m): {px_count:.0f}")

    if px_count < min_pixel_count:
        print(f"  ⚠️  Cropland yetarli emas (<{min_pixel_count} piksel) — "
              f"bu tile uchun cropland cheklovi O'CHIRILADI")
        return None, False

    # Cropland pikselларini vektorga aylantirib, bitta geometriya qilamiz
    # Raster mask — 1=cropland, qolgani masked. VEKTORLASH YO'Q
    # (reduceToVectors + dissolve murakkab ko'pburchak → "timed out" edi).
    cropland_mask = cropland_raster.selfMask().rename('CROPLAND')
    print("  ✅ Cropland mask tayyor (raster, tile ichida)")

    return cropland_mask, True


# ==============================================================
# M5: ANCHOR PIXEL SELECTION
# ==============================================================

def _anchor_default(image, geom, base, diag=None):
    """
    'default' — klassik persentil metod (kaskadda plan_b dan keyin, pysebal dan oldin):
      cold: NDVI ≥ p{cold_ndvi_percentile} ∧ LST ≤ p{cold_lst_percentile} ∧ albedo < cold_albedo_max
      hot : NDVI ≤ p{hot_ndvi_percentile} ∧ LST ≥ p{hot_lst_percentile} ∧ albedo > hot_albedo_min
    (persentillar `base` — zona — ichida). Qat'iy nomzod yo'q bo'lsa ZAXIRA: faqat
    LST sharti (NDVI/albedo tashlanadi) — zaxira SAQLANADI, lekin ishlatilgani
    `diag` (cold_strict_n / hot_strict_n) orqali _finalize_anchor'da LOGLANADI va
    sahna QC'ga yoziladi (oldin jim edi).
    """
    acfg = cfg.ANCHOR
    ndvi = image.select('NDVI')
    lst = image.select('LST')
    albedo = image.select('ALBEDO')
    kw = dict(crs=analysis_proj(image), scale=ANCHOR_SCALE, maxPixels=1e9,
              bestEffort=True, tileScale=4)

    # DIQQAT: bitta percentile so'ralsa kalit = band nomi ('NDVI'/'LST').
    ndvi_p_cold = _pn(ndvi.updateMask(base).reduceRegion(
        ee.Reducer.percentile([acfg['cold_ndvi_percentile']]), geom, **kw), 'NDVI', _HI)
    lst_p_cold = _pn(lst.updateMask(base).reduceRegion(
        ee.Reducer.percentile([acfg['cold_lst_percentile']]), geom, **kw), 'LST', _LO)
    ndvi_p_hot = _pn(ndvi.updateMask(base).reduceRegion(
        ee.Reducer.percentile([acfg['hot_ndvi_percentile']]), geom, **kw), 'NDVI', _LO)
    lst_p_hot = _pn(lst.updateMask(base).reduceRegion(
        ee.Reducer.percentile([acfg['hot_lst_percentile']]), geom, **kw), 'LST', _HI)

    cold_strict = (base.And(ndvi.gte(ndvi_p_cold)).And(lst.lte(lst_p_cold))
                   .And(albedo.lt(acfg['cold_albedo_max'])))
    cold_fb = base.And(lst.lte(lst_p_cold))                  # zaxira: faqat LST
    hot_strict = (base.And(ndvi.lte(ndvi_p_hot)).And(lst.gte(lst_p_hot))
                  .And(albedo.gt(acfg['hot_albedo_min'])))
    hot_fb = base.And(lst.gte(lst_p_hot))                    # zaxira: faqat LST

    def _n(m):
        v = m.rename('M').reduceRegion(ee.Reducer.sum(), geom, **kw).get('M')
        return ee.Number(ee.Algorithms.If(ee.Algorithms.IsEqual(v, None), 0, v))
    n_cold, n_hot = _n(cold_strict), _n(hot_strict)
    if diag is not None:
        diag.update({'cold_strict_n': n_cold, 'hot_strict_n': n_hot})
    cold_mask = ee.Image(ee.Algorithms.If(n_cold.gt(0), cold_strict, cold_fb))
    hot_mask = ee.Image(ee.Algorithms.If(n_hot.gt(0), hot_strict, hot_fb))
    return cold_mask, hot_mask


# ==============================================================
# M5b: ANCHOR KASKAD (beton) — ko'p metodli, diagnostikali
# ==============================================================

_CANON_ORDER = ('cimec', 'plan_a', 'plan_b', 'default', 'pysebal')   # user tartibi (2026-09-19)

def _base_mask(image):
    """Tekis (slope<5°) VA valid (bulutsiz) piksellar maskasi."""
    slope = image.select('SLOPE')
    flat = slope.lt(cfg.ANCHOR['slope_max'])
    valid = image.mask().reduce(ee.Reducer.allNonZero())
    return flat.And(valid)


# Sentinel'lar: kalit YO'Q bo'lsa (reduceRegion bo'sh dictionary qaytarsa)
# maskani BO'SH qilish uchun. gte(_HI) hech qachon rost emas; lte(_LO) ham.
_HI = 1e6
_LO = -1e6


def _pn(d, key, sentinel):
    """
    reduceRegion dictionary'dan persentil/statni XAVFSIZ olish.

    IKKI xavf bor:
      1. Kalit YO'Q (bo'sh dictionary) → d.get(key) default'siz "Dictionary
         does not contain key" xatosi. → default beramiz.
      2. Kalit BOR, lekin qiymat NULL (bo'sh zonada percentile) →
         ee.Number(null).gte(...) → "Image.constant: value null" xatosi.
         → ee.Algorithms.If bilan null'ni sentinel'ga almashtiramiz.
    sentinel — _HI yoki _LO; natijada mask bo'sh bo'ladi → metod
    'topilmadi' deb keyingisiga o'tadi (crash emas). Sentinel — "qiymat yo'q"
    belgisi, fizik qiymat EMAS: u hech qachon anchor LST/NDVI sifatida ishlatilmaydi.
    DIQQAT: null IsEqual bilan tekshiriladi — If(v, v, …) 0.0 ni ham "yo'q" deb
    olardi (haqiqiy 0 qiymat sentinel'ga aylanib ketardi).
    """
    v = d.get(key, sentinel)
    return ee.Number(ee.Algorithms.If(ee.Algorithms.IsEqual(v, None), sentinel, v))


# ---- METOD 1: CIMEC (strict, NDVI-guruhli LST persentili) ----
def _anchor_cimec(image, geom, base):
    ndvi = image.select('NDVI')
    ts = image.select('LST')
    alb = image.select('ALBEDO')

    # Cold: yuqori NDVI (p80) guruhida eng sovuq (p5..p40)
    # DIQQAT: bitta percentile so'ralsa kalit = band nomi ('NDVI'), '_p80' EMAS.
    nperc = ndvi.updateMask(base).reduceRegion(
        ee.Reducer.percentile([80]), geom, crs=analysis_proj(image), scale=ANCHOR_SCALE,
        maxPixels=1e9, bestEffort=True, tileScale=4)
    ndvi_p80 = _pn(nperc, 'NDVI', _HI)              # gte → yo'q/null bo'lsa bo'sh
    high_ndvi = base.And(ndvi.gte(ndvi_p80))
    tsg = ts.updateMask(high_ndvi).reduceRegion(
        ee.Reducer.percentile([5, 40]), geom, crs=analysis_proj(image), scale=ANCHOR_SCALE,
        maxPixels=1e9, bestEffort=True, tileScale=4)
    cold_lo = _pn(tsg, 'LST_p5', _HI)               # gte → bo'sh
    cold_hi = _pn(tsg, 'LST_p40', _LO)              # lte → bo'sh
    cold_mask = high_ndvi.And(ts.gte(cold_lo)).And(ts.lte(cold_hi))

    # Hot: past NDVI (p10, o'simlik bor lekin siyrak) guruhida eng issiq
    nperc2 = ndvi.updateMask(base).reduceRegion(
        ee.Reducer.percentile([10]), geom, crs=analysis_proj(image), scale=ANCHOR_SCALE,
        maxPixels=1e9, bestEffort=True, tileScale=4)
    ndvi_p10 = _pn(nperc2, 'NDVI', _LO)             # bitta percentile → kalit 'NDVI'
    low_ndvi = base.And(ndvi.lte(ndvi_p10)).And(ndvi.gt(0.02)).And(alb.gt(0.12))
    tsd = ts.updateMask(low_ndvi).reduceRegion(
        ee.Reducer.percentile([60, 95]), geom, crs=analysis_proj(image), scale=ANCHOR_SCALE,
        maxPixels=1e9, bestEffort=True, tileScale=4)
    hot_lo = _pn(tsd, 'LST_p60', _HI)               # gte → bo'sh
    hot_hi = _pn(tsd, 'LST_p95', _LO)               # lte → bo'sh
    hot_mask = low_ndvi.And(ts.gte(hot_lo)).And(ts.lte(hot_hi))
    return cold_mask, hot_mask


# ---- METOD 2: PLAN A (klassik SEBAL, fizik chegaralar) ----
def _anchor_plan_a(image, geom, base):
    lai = image.select('LAI')
    alb = image.select('ALBEDO')
    ts = image.select('LST')
    ndvi = image.select('NDVI')
    cold_mask = (base.And(lai.gte(3.0))
                 .And(alb.gt(0.20)).And(alb.lt(0.25))
                 .And(ts.gte(284)).And(ts.lte(295)))
    hot_mask = (base.And(lai.lt(0.4))
                .And(ndvi.gt(0.05)).And(ndvi.lt(0.3))
                .And(ts.gte(302)).And(ts.lte(311)))
    return cold_mask, hot_mask


# ---- METOD 3: PLAN B (persentil + LST-gap sifat sharti) ----
def _anchor_plan_b(image, geom, base):
    gap = cfg.ANCHOR_CASCADE['ts_gap_min']
    ndvi = image.select('NDVI')
    ts = image.select('LST')
    alb = image.select('ALBEDO')

    nperc = ndvi.updateMask(base).reduceRegion(
        ee.Reducer.percentile([10, 95]), geom, crs=analysis_proj(image), scale=ANCHOR_SCALE,
        maxPixels=1e9, bestEffort=True, tileScale=4)
    ndvi_p95 = _pn(nperc, 'NDVI_p95', _HI)   # gte → yo'q bo'lsa bo'sh
    ndvi_p10 = _pn(nperc, 'NDVI_p10', _LO)   # lte → yo'q bo'lsa bo'sh

    tperc = ts.updateMask(base).reduceRegion(
        ee.Reducer.percentile([5, 15, 20, 80, 85, 95]), geom, crs=analysis_proj(image), scale=ANCHOR_SCALE,
        maxPixels=1e9, bestEffort=True, tileScale=4)
    ts_p05 = _pn(tperc, 'LST_p5', _HI)       # cold gte → bo'sh
    ts_p15 = _pn(tperc, 'LST_p15', _LO)      # cold lte chegarasi → bo'sh
    ts_p20 = _pn(tperc, 'LST_p20', _LO)
    ts_p80 = _pn(tperc, 'LST_p80', _HI)      # hot gte chegarasi → bo'sh
    ts_p85 = _pn(tperc, 'LST_p85', _HI)
    ts_p95 = _pn(tperc, 'LST_p95', _LO)      # hot lte → bo'sh

    gap_ok = ts_p85.subtract(ts_p15).gte(gap)
    cold_hi = ee.Number(ee.Algorithms.If(gap_ok, ts_p15, ts_p20))
    hot_lo = ee.Number(ee.Algorithms.If(gap_ok, ts_p85, ts_p80))

    cold_mask = (base.And(ndvi.gte(ndvi_p95))
                 .And(ts.gte(ts_p05)).And(ts.lte(cold_hi)))
    hot_mask = (base.And(ndvi.lte(ndvi_p10)).And(ndvi.gt(0.02))
                .And(ts.gte(hot_lo)).And(ts.lte(ts_p95)).And(alb.gt(0.12)))
    return cold_mask, hot_mask


# ---- METOD 4: pySEBAL (statistik; statistika bo'lmasa — topilmadi, soxta qiymat YO'Q) ----
def _anchor_pysebal(image, geom, base):
    """
    Statistika (NDVI max/std, LST mean/std, NDVI p10) sahnadan olinadi. Biror
    statistika chiqmasa, maska BO'SH bo'ladi (sentinel _HI/_LO) → metod
    'topilmadi' → kaskad keyingi metodga o'tadi. Oldingi 0.7 / 0.05 / 295 K /
    305 K / 2.0 / 0.1 default qiymatlari OLIB TASHLANDI.
    """
    ndvi = image.select('NDVI')
    ts = image.select('LST')
    alb = image.select('ALBEDO')

    ns = ndvi.updateMask(base).reduceRegion(
        ee.Reducer.max().combine(ee.Reducer.stdDev(), sharedInputs=True),
        geom, crs=analysis_proj(image), scale=ANCHOR_SCALE, maxPixels=1e9, bestEffort=True, tileScale=4)
    ndvi_max = _pn(ns, 'NDVI_max', _HI)        # gte(max − …) → yo'q bo'lsa bo'sh
    ndvi_std = _pn(ns, 'NDVI_stdDev', _LO)     # max − 0.1·(−1e6) → chegara +∞ → bo'sh
    cold_veg = base.And(ndvi.gte(ndvi_max.subtract(ndvi_std.multiply(0.1))))
    cs = ts.updateMask(cold_veg).reduceRegion(
        ee.Reducer.mean().combine(ee.Reducer.stdDev(), sharedInputs=True),
        geom, crs=analysis_proj(image), scale=ANCHOR_SCALE, maxPixels=1e9, bestEffort=True, tileScale=4)
    cold_mean = _pn(cs, 'LST_mean', _LO)       # lte(mean − std) → yo'q bo'lsa bo'sh
    cold_std = _pn(cs, 'LST_stdDev', _HI)
    cold_mask = cold_veg.And(ts.lte(cold_mean.subtract(cold_std)))

    np_ = ndvi.updateMask(base).reduceRegion(
        ee.Reducer.percentile([10]), geom, crs=analysis_proj(image), scale=ANCHOR_SCALE,
        maxPixels=1e9, bestEffort=True, tileScale=4)
    p10 = _pn(np_, 'NDVI', _LO)                # bitta percentile → kalit 'NDVI'
    # 0.05 pastki chegara FAQAT haqiqiy qiymatga (sentinel'ga emas)
    ndvi_p10 = ee.Number(ee.Algorithms.If(p10.gt(_LO), p10.max(0.05), p10))
    hot_ndvi = (base.And(ndvi.gte(ndvi_p10.multiply(0.5)))
                .And(ndvi.lte(ndvi_p10)).And(ndvi.gt(0.02)).And(alb.gt(0.12)))
    hs = ts.updateMask(hot_ndvi).reduceRegion(
        ee.Reducer.mean().combine(ee.Reducer.stdDev(), sharedInputs=True),
        geom, crs=analysis_proj(image), scale=ANCHOR_SCALE, maxPixels=1e9, bestEffort=True, tileScale=4)
    hot_mean = _pn(hs, 'LST_mean', _HI)        # gte(mean + std) → yo'q bo'lsa bo'sh
    hot_std = _pn(hs, 'LST_stdDev', _HI)
    hot_mask = hot_ndvi.And(ts.gte(hot_mean.add(hot_std)))
    return cold_mask, hot_mask


# LST oralig'i bir tomondan CHEGARASIZ metodlar (point_anchor da _trim_tails).
_UNBOUNDED_METHODS = ('default', 'pysebal')

_ANCHOR_METHODS = {
    'cimec': _anchor_cimec,
    'default': _anchor_default,
    'plan_a': _anchor_plan_a,
    'plan_b': _anchor_plan_b,
    'pysebal': _anchor_pysebal,
}


def _cascade_order(method):
    """Tanlangan metod birinchi, qolganlari kanonik tartibda."""
    if method in _CANON_ORDER:
        return (method,) + tuple(m for m in _CANON_ORDER if m != method)
    return _CANON_ORDER   # 'cascade' yoki noma'lum → to'liq zanjir


def _extreme_pixel(image, mask, geom, which, carry=()):
    """
    Nomzodlar ichidan BITTA ekstremal LST pikseli (which='min' | 'max') — DETERMINISTIK.

    Landsat termal kanali 100 m (30 m ga qayta namunalangan), DN kvantlangan →
    bir nechta nomzod AYNAN bir xil LST ga ega bo'lishi mumkin (2023-08-20: 2 ta
    hot piksel, 14 km oraliq, Rn−G₀ 309.9 vs 250.2 W/m²). Reducer.max(n)/min(n)
    tenglikda ixtiyoriy pikselni qaytaradi va (lazy ifoda bo'lgani uchun) HAR
    so'rovda boshqasini tanlashi mumkin edi — bitta sahnada suv balansi bir
    pikselda, energiya balansi boshqasida hisoblanardi. Shu sabab ikki bosqich:
      1) ekstremal LST QIYMATI (deterministik son);
      2) shu qiymatli piksellar ichidan geometrik kalit maksimumi
         (kenglik, keyin uzunlik) — faqat tenglikni hal qiladi, fizikaga tegmaydi.
    Grid: tahlil gridi (analysis_proj — Landsat NDVI proyeksiyasi), ANCHOR_SCALE —
    ikkala bosqichda AYNI.
    Qaytaradi: (lst ee.Number, [carry ee.Number...], [lon, lat] ee.List).
    Bo'sh maska → lst = -999 (valid-tekshiruvi ushlaydi), nuqta [None, None].
    """
    lst = image.select('LST')
    kw = dict(crs=analysis_proj(image), scale=ANCHOR_SCALE, maxPixels=1e9,
              bestEffort=True, tileScale=4)
    red = ee.Reducer.max() if which == 'max' else ee.Reducer.min()
    ext = lst.updateMask(mask).reduceRegion(red, geom, **kw).get('LST')
    ext = ee.Number(ee.Algorithms.If(ee.Algorithms.IsEqual(ext, None), -999, ext))
    tie = mask.And(lst.eq(ext))
    ll = ee.Image.pixelLonLat()
    key = (ll.select('latitude').add(90).multiply(1e6)
           .add(ll.select('longitude').add(180).divide(1e3))).rename('KEY')
    stack = key.addBands(ll).addBands(lst)
    if carry:
        stack = stack.addBands(image.select(list(carry)))
    d = stack.updateMask(tie).reduceRegion(ee.Reducer.max(4 + len(carry)), geom, **kw)
    # 'max'=KEY, 'max1'=lon, 'max2'=lat, 'max3'=LST, 'max4'…=carry (AYNI piksel)
    vals = [ee.Number(d.get(f'max{4 + i}', -999)) for i in range(len(carry))]
    return (ee.Number(d.get('max3', -999)), vals,
            ee.List([d.get('max1'), d.get('max2')]))


def _trim_tails(image, geom, cold_mask, hot_mask):
    """
    point_anchor uchun: LST oralig'i CHEGARASIZ nomzodlar (default: cold ≤ p20 /
    hot ≥ p95; pysebal: cold ≤ o'rt−std / hot ≥ o'rt+std) ichidan eng chetdagi
    cfg.ANCHOR['point_trim_pct'] % tashlanadi: cold LST ≥ p{q}, hot LST ≤ p{100−q}
    (NOMZODLAR ichidagi persentil). Aks holda point = absolyut eng sovuq/issiq —
    default'ning o'z izohi ("p5 juda xavfli — soya") ga zid chetdagi piksel
    (2023-10-07 default: cold albedo 0.11, Rn−G₀ 522 vs nomzodlar 434 W/m²).
    Nomzodlar ta'rifi o'zgarmaydi. cimec/plan_a/plan_b oralig'i ikki tomondan
    chegaralangan — ularga qo'llanmaydi.
    """
    q = cfg.ANCHOR['point_trim_pct']
    lst = image.select('LST')
    kw = dict(crs=analysis_proj(image), scale=ANCHOR_SCALE, maxPixels=1e9,
              bestEffort=True, tileScale=4)
    pc = _pn(lst.updateMask(cold_mask).reduceRegion(
        ee.Reducer.percentile([q]), geom, **kw), 'LST', _HI)            # yo'q → bo'sh
    ph = _pn(lst.updateMask(hot_mask).reduceRegion(
        ee.Reducer.percentile([100 - q]), geom, **kw), 'LST', _LO)      # yo'q → bo'sh
    return cold_mask.And(lst.gte(pc)), hot_mask.And(lst.lte(ph))


def _reduce_anchor_values(image, geom, cold_mask, hot_mask,
                          anchor_mode='median_anchor', need_rn=True):
    """
    cold/hot mask'dan anchor SKALYARlarini (cold_lst, hot_lst, hot_rn_g0) oladi.

    anchor_method (cimec/plan_a/... — kandidat ZONANI topadi) O'ZGARMAYDI; bu
    faqat o'sha kandidatlardan QIYMAT olish qadamini belgilaydi:
      'median_anchor' (default) — kandidatlar bo'yicha MEDIAN (hozirgi; shovqin
          kamaytirilgan, (LST,Rn−G₀) juftligi band-bo'yicha alohida).
      'point_anchor' — kandidatlar hammasi to'g'ri, ICHIDAN BITTA ekstremal (n=1):
          cold = eng SOVUQ (min LST); hot = eng ISSIQ (max LST) va Rn−G₀ AYNI
          o'sha hot pikseldan (ee.Reducer.max(2): 'max'=LST, 'max1'=Rn−G₀ —
          izchil juft). Kitobdagi qo'l-anchor mantiqiga eng yaqin.
    Bo'sh mask → sentinel -999 (valid-tekshiruvi skip qiladi).
    need_rn=False — Rn−G₀ hali hisoblanmagan (empirik L↓, 1-bosqich): faqat LST
    (point: min/max LST pikseli; median: median). cold/hot Rn−G₀ = None.
    """
    lst = image.select('LST')
    if not need_rn:
        if anchor_mode == 'point_anchor':
            # eng SOVUQ / eng ISSIQ piksel — deterministik (_extreme_pixel)
            cold_lst, _, cold_pt = _extreme_pixel(image, cold_mask, geom, 'min')
            hot_lst, _, hot_pt = _extreme_pixel(image, hot_mask, geom, 'max')
            return cold_lst, None, hot_lst, None, cold_pt, hot_pt
        cold_lst = ee.Number(lst.updateMask(cold_mask).reduceRegion(
            ee.Reducer.median(), geom, crs=analysis_proj(image), scale=ANCHOR_SCALE, maxPixels=1e9, bestEffort=True,
            tileScale=4).get('LST', -999))
        hot_lst = ee.Number(lst.updateMask(hot_mask).reduceRegion(
            ee.Reducer.median(), geom, crs=analysis_proj(image), scale=ANCHOR_SCALE, maxPixels=1e9, bestEffort=True,
            tileScale=4).get('LST', -999))
        return cold_lst, None, hot_lst, None, None, None

    rn_g0 = image.select('RN_G0')
    if anchor_mode == 'point_anchor':
        # cold = eng SOVUQ, hot = eng ISSIQ piksel — deterministik (_extreme_pixel);
        # LST, Rn−G₀ va lon/lat AYNI o'sha pikseldan. Nomzodlar RN_G0-valid
        # piksellarga cheklanadi (eng issiq piksel RN_G0-masked bo'lsa Rn−G₀ null
        # bo'lmasin); umuman valid piksel bo'lmasa → sentinel -999.
        rn_ok = rn_g0.mask()
        cold_lst, (cold_rn_g0,), cold_pt = _extreme_pixel(
            image, cold_mask.And(rn_ok), geom, 'min', carry=('RN_G0',))
        hot_lst, (hot_rn_g0,), hot_pt = _extreme_pixel(
            image, hot_mask.And(rn_ok), geom, 'max', carry=('RN_G0',))
    else:  # 'median_anchor' (default — hozirgi bilan aynan bir xil natija)
        cold_stats = image.select(['LST', 'RN_G0']).updateMask(cold_mask).reduceRegion(
            ee.Reducer.median(), geom, crs=analysis_proj(image), scale=ANCHOR_SCALE, maxPixels=1e9,
            bestEffort=True, tileScale=4)
        cold_lst = ee.Number(cold_stats.get('LST', -999))
        cold_rn_g0 = ee.Number(cold_stats.get('RN_G0', -999))   # SEBAL_ID: cold H uchun
        hot_stats = image.select(['LST', 'RN_G0']).updateMask(hot_mask).reduceRegion(
            ee.Reducer.median(), geom, crs=analysis_proj(image), scale=ANCHOR_SCALE, maxPixels=1e9,
            bestEffort=True, tileScale=4)
        hot_lst = ee.Number(hot_stats.get('LST', -999))
        hot_rn_g0 = ee.Number(hot_stats.get('RN_G0', -999))
        cold_pt = hot_pt = None                                # median — bitta nuqta yo'q
    return cold_lst, cold_rn_g0, hot_lst, hot_rn_g0, cold_pt, hot_pt


def _anchor_sample(image, anchors, roi, bands, sides=('cold', 'hot')):
    """
    Anchor skalyarlari — anchors['anchor_mode'] ga QAT'IY mos (butun pipeline
    bitta rejimda; aralash emas):
      'point_anchor'  → AYNAN anchor pikseli (anchors['cold_point'/'hot_point']),
      'median_anchor' → cold/hot nomzod maskalari MEDIANI.
    Reduksiya anchor tanlangan AYNI gridda (analysis_proj, ANCHOR_SCALE) bo'ladi. (Oldin har band alohida reduce qilinardi — har biri o'z
    default proyeksiyasida; maska boshqa gridga qayta namunalanardi.) Point rejimda
    qaytgan 'LST' anchor LST ga teng bo'lishi shart (chaqiruvchi tekshiradi).
    Qaytaradi: ee.Dictionary {side: {band: qiymat}} (server-side, lazy).
    """
    img = image.select(['LST'] + [b for b in bands if b != 'LST'])
    proj = analysis_proj(image)                 # anchor tanlangan AYNI (tahlil) grid
    mode = anchors.get('anchor_mode')
    if mode == 'point_anchor':
        out = {}
        for side in sides:
            pt = anchors.get(f'{side}_point')
            if pt is None:
                raise ValueError(f"point_anchor: anchors['{side}_point'] yo'q.")
            out[side] = img.reduceRegion(ee.Reducer.first(), ee.Geometry.Point(ee.List(pt)),
                                         crs=proj, scale=ANCHOR_SCALE)
        return ee.Dictionary(out)
    if mode == 'median_anchor':
        return ee.Dictionary({
            side: img.updateMask(anchors[f'{side}_mask']).reduceRegion(
                ee.Reducer.median(), roi, crs=proj, scale=ANCHOR_SCALE, maxPixels=1e9,
                bestEffort=True, tileScale=4)
            for side in sides})
    raise ValueError(f"anchors['anchor_mode'] noma'lum: {mode!r} "
                     f"('point_anchor' yoki 'median_anchor').")


def _finalize_anchor(image, geom, cold_mask, hot_mask, method, zone, verbose,
                     anchor_mode='median_anchor', need_rn=True,
                     cold_purity=None, hot_purity=None, extra=None):
    """
    cold/hot mask'dan anchor qiymatlarini (_reduce_anchor_values — median yoki
    ekstremal point) oladi, VALIDlikni bitta getInfo bilan client-side
    tekshiradi. Ikkalasi ham topilib, ΔT yetarli bo'lsa — anchor dict qaytaradi;
    aks holda None (keyingi metodga o'tiladi).
    """
    # cold/hot skalyar — median (default) yoki bitta ekstremal piksel.
    # Bo'sh mask → sentinel -999; keyin >-900 tekshiruvi.
    cold_lst, cold_rn_g0, hot_lst, hot_rn_g0, cold_pt, hot_pt = _reduce_anchor_values(
        image, geom, cold_mask, hot_mask, anchor_mode, need_rn)

    def _nz(v):                       # null → -999 (IsEqual: 0 qiymat "yo'q" emas)
        return ee.Algorithms.If(ee.Algorithms.IsEqual(v, None), -999, v)
    extra = extra or {}
    probe = ee.List([
        _nz(cold_lst), _nz(hot_lst),
        _nz(hot_rn_g0) if need_rn else 0,
        _nz(cold_rn_g0) if need_rn else 0,     # cold Rn−G₀ ham (hot bilan simmetrik)
        extra.get('cold_strict_n', -1), extra.get('hot_strict_n', -1),   # default zaxira
    ]).getInfo()
    c, h, hr, cr = probe[0], probe[1], probe[2], probe[3]
    acfg = cfg.ANCHOR
    fb = []
    if probe[4] == 0:
        fb.append(f"cold (NDVI ≥ p{acfg['cold_ndvi_percentile']} ∧ albedo < "
                  f"{acfg['cold_albedo_max']} nomzodi yo'q → faqat LST ≤ p{acfg['cold_lst_percentile']})")
    if probe[5] == 0:
        fb.append(f"hot (NDVI ≤ p{acfg['hot_ndvi_percentile']} ∧ albedo > "
                  f"{acfg['hot_albedo_min']} nomzodi yo'q → faqat LST ≥ p{acfg['hot_lst_percentile']})")
    note = f"{method} zaxirasi ({zone}): " + '; '.join(fb) if fb else None
    if note and verbose:
        print(f"    ⚠️ {note}")

    min_dt = cfg.ANCHOR['min_dt']
    ok = (None not in (c, h, hr, cr)
          and c > -900 and h > -900 and hr > -900 and cr > -900 and (h - c) >= min_dt)

    if ok:
        if verbose:
            print(f"    ✅ Anchor topildi: metod={method}, zona={zone} | "
                  f"cold={c:.1f}K  hot={h:.1f}K  ΔT={h - c:.1f}K")
        return {
            'cold_lst': cold_lst, 'hot_lst': hot_lst, 'hot_rn_g0': hot_rn_g0,
            'cold_rn_g0': cold_rn_g0,   # SEBAL_ID: cold piksel H_cp uchun
            'hot_mask': hot_mask, 'cold_mask': cold_mask,
            'valid': ee.Number(1), 'method': method, 'zone': zone,
            'cold_zone_purity': cold_purity if cold_purity is not None else 0.0,
            'hot_zone_purity': hot_purity if hot_purity is not None else 0.0,
            'cold_point': cold_pt, 'hot_point': hot_pt,
            'anchor_mode': anchor_mode,
            'note': note,                # default zaxirasi ishlatilgan bo'lsa (QC'ga)
        }

    if verbose:
        reason = ('cold/hot bo\'sh' if (c is None or h is None or c <= -900 or h <= -900)
                  else f'ΔT={h - c:.1f}K < {min_dt}K' if (h - c) < min_dt
                  else 'anchor Rn−G₀ yo\'q')
        print(f"    ↪ metod={method} ({zone}) → topilmadi ({reason}), keyingisi…")
    return None


def select_anchor_pixels(image, roi, cold_zone=None, hot_zone=None,
                         method='cimec', verbose=True,
                         anchor_mode='median_anchor', need_rn=True, hot_soil=False,
                         exclude=None, cold_full_cover=False):
    """
    Anchor tanlash DISPATCHER (beton kaskad).

    cold_zone / hot_zone : ee.Image (sinf ulushi 0..1, compute_tile_anchor_zones)
      yoki None. Zona: ulush ≥0.80 → 0.70 → 0.60 → ROI (_purity_zones).
      reduceRegion HAR DOIM oddiy `roi` ustida ishlaydi.
    need_rn : False — empirik L↓ rejimi 1-bosqichi (Rn−G₀ hali yo'q); anchor
      zona/LST tanlanadi, Rn−G₀ qiymatlari finalize_anchor_values'da olinadi.

    method (kaskad tartibi _CANON_ORDER: cimec → plan_a → plan_b → default → pysebal):
      'cimec' (main default) | 'cascade' → to'liq tartib cimec'dan;
      'plan_a'|'plan_b'|'default'|'pysebal' → shu metod birinchi, keyin qolganlari
      kanonik tartibda. Avval land-cover zonasida (lc), so'ng ROI'da.
    Biror metod topmasa — keyingisiga o'tiladi. Hech biri topmasa — valid=0 va
    'fail_reason' (sahna sababi bilan rad etiladi; alohida zaxira YO'Q).
    'default' ning ichki zaxirasi (NDVI/albedo sharti bo'yicha nomzod yo'q →
    faqat LST) saqlanadi va LOGLANADI (anchors['note'] → sahna QC).
    Har qadam va metod almashinuvi print qilinadi.

    exclude : {(metod, zona), …} — o'tkazib yuboriladigan qadamlar (main: anchor
      topilgan, lekin fizik QC'dan o'tmagan metod/zona → kaskad KEYINGISIDAN davom).

    hot_soil : True (SEBAL_ID oilasi) — hot nomzodlar FAQAT tuproq xaritasida
      θ_FC, θ_WP, tekstura bor piksellar (water_balance.soil_valid_mask). Hot
      pikselda suv balansi hisoblanadi — u tuproq bo'lishi shart (shahar/suv emas).
      Barcha bosqichlarda (lc, ROI) qo'llanadi.

    cold_full_cover : True (SEBAL_ID oilasi) — λET_cold = 1.05·ETr faqat to'liq qoplamali
      pikselga (METRIC). 1-o'tish: har metodning cold nomzodlari LAI ≥ cfg.ANCHOR
      ['cold_lai_min'] bilan cheklanadi (butun kaskad, lc → ROI). Hech biri topmasa —
      SAHNA TASHLANMAYDI: 2-o'tish cheklovsiz (oldingi) kaskad, zona nomi '…-LAI<4',
      anchors['note'] → QC ogohlantirishi (1.05·ETr qisman qoplamaga berilgan bo'lishi mumkin).
    """
    hot_soil_mask = None
    if hot_soil:
        from . import water_balance
        hot_soil_mask = water_balance.soil_valid_mask()
    exclude = set(exclude or ())

    base_flat = _base_mask(image)             # tekis + valid
    order = _cascade_order(method)

    # AYRIM zonalar: cold=cropland, hot=bare+shrub — ULUSH ≥0.80 → 0.70 → 0.60 → ROI.
    cold_base, cold_purity, hot_base, hot_purity = _purity_zones(
        base_flat, cold_zone, hot_zone, roi, analysis_proj(image))
    hot_flat = base_flat
    if hot_soil_mask is not None:            # hot — faqat tuproq ma'lumoti bor piksel
        hot_base = hot_base.And(hot_soil_mask)
        hot_flat = base_flat.And(hot_soil_mask)

    def _cascade(cold_extra, sfx):
        """
        Kaskad: 1) land-cover zonalari (cold_mask cold_base'dan, hot_mask hot_base'dan),
        2) ROI (cheklovsiz) — bulutli kunlarda zona bo'sh bo'lsa zaxira. Metod ikki marta
        chaqiriladi — keraksiz yarmi (lazy) baholanmaydi. cold_extra — cold nomzodlarga
        qo'shimcha maska (to'liq qoplama), metod chegaralaridan KEYIN; sfx — zona nomi qo'shimchasi.
        """
        for zone, c_base, h_base, c_pur, h_pur in (('lc', cold_base, hot_base, cold_purity, hot_purity),
                                                   ('ROI', base_flat, hot_flat, None, None)):
            z = zone + sfx
            for m in order:
                if (m, z) in exclude:          # fizik QC'dan o'tmagan — keyingisi
                    continue
                dc, dh = {}, {}                # default: qat'iy nomzodlar soni (zaxira logi)
                cm, _ = _call_method(m, image, roi, c_base, dc)
                _, hm = _call_method(m, image, roi, h_base, dh)
                if cold_extra is not None:
                    cm = cm.And(cold_extra)
                if m in _UNBOUNDED_METHODS and anchor_mode == 'point_anchor':
                    cm, hm = _trim_tails(image, roi, cm, hm)
                extra = ({'cold_strict_n': dc['cold_strict_n'], 'hot_strict_n': dh['hot_strict_n']}
                         if m == 'default' else None)
                res = _finalize_anchor(image, roi, cm, hm, m, z, verbose, anchor_mode,
                                       need_rn, c_pur, h_pur, extra=extra)
                if res is not None:
                    return res
        return None

    if cold_full_cover:
        lai_min = cfg.ANCHOR['cold_lai_min']
        # 1-o'tish: cold — faqat to'liq qoplama (λET_cold = 1.05·ETr farazi uchun)
        res = _cascade(image.select('LAI').gte(lai_min), '')
        if res is not None:
            return res
        # 2-o'tish: to'liq qoplamali nomzod yo'q — sahna TASHLANMAYDI, oldingi (cheklovsiz)
        # kaskad; QC ogohlantirishi (user qarori 2026-09-21)
        flag = (f"cold: to'liq qoplamali (LAI ≥ {lai_min:g}) nomzod topilmadi → cheklovsiz "
                f"cold piksel (1.05·ETr qisman qoplamaga berilgan bo'lishi mumkin)")
        if verbose:
            print(f"    ⚠️ {flag}")
        res = _cascade(None, f'-LAI<{lai_min:g}')
        if res is not None:
            res['note'] = f"{res['note']}; {flag}" if res.get('note') else flag
            return res
    else:
        res = _cascade(None, '')
        if res is not None:
            return res

    why = f"anchor: barcha metodlar ({' → '.join(order)}) lc va ROI da topilmadi"
    if verbose:
        print(f"    ❌ {why}")
    return {'valid': ee.Number(0), 'cold_lst': ee.Number(-999), 'hot_lst': ee.Number(-999),
            'cold_rn_g0': None, 'hot_rn_g0': None, 'cold_mask': None, 'hot_mask': None,
            'cold_point': None, 'hot_point': None, 'anchor_mode': anchor_mode,
            'cold_zone_purity': cold_purity, 'hot_zone_purity': hot_purity,
            'method': None, 'zone': None, 'note': None, 'fail_reason': why}


def _call_method(m, image, geom, base, diag):
    """Kaskad metodini chaqirish; 'default' ga zaxira-logi uchun diag uzatiladi."""
    if m == 'default':
        return _anchor_default(image, geom, base, diag)
    return _ANCHOR_METHODS[m](image, geom, base)


def materialize_anchors(anchors, extra=None):
    """
    Anchor skalyarlari (LST, Rn−G₀, valid) va nuqtalarini BIR getInfo bilan
    hisoblab, klient KONSTANTALARIGA aylantiradi. Sabab: ular lazy server
    ifodasi — har getInfo/eksportda reduceRegion QAYTA baholanadi (sekin va
    tenglik holatida boshqa piksel tanlanishi mumkin edi). Maskalar o'zgarmaydi.
    extra — shu getInfo'ga qo'shib olinadigan boshqa lazy qiymatlar (masalan Tref).
    Qaytaradi: (yangi anchors dict, {kalit: klient qiymat} — anchor + extra).
    """
    num_keys = ('valid', 'cold_lst', 'hot_lst', 'cold_rn_g0', 'hot_rn_g0')
    pt_keys = ('cold_point', 'hot_point')
    d = {k: anchors[k] for k in num_keys + pt_keys if anchors.get(k) is not None}
    d.update(extra or {})
    info = ee.Dictionary(d).getInfo()
    out = dict(anchors)
    for k in num_keys:
        if k in info and info[k] is not None:
            out[k] = ee.Number(info[k])
    for k in pt_keys:
        if k in info:
            out[k] = info[k]          # [lon, lat] (python) yoki [None, None]
    return out, info


def finalize_anchor_values(image, roi, anchors, anchor_mode='median_anchor'):
    """
    Empirik L↓ rejimi 2-bosqichi: 1-bosqichda (need_rn=False) tanlangan AYNI
    cold/hot nomzod maskalaridan anchor qiymatlarini (LST, Rn−G₀) radiatsiya
    to'liq hisoblangan rasmdan qayta oladi. Zona/metod o'zgarmaydi.
    """
    cold_lst, cold_rn_g0, hot_lst, hot_rn_g0, cold_pt, hot_pt = _reduce_anchor_values(
        image, roi, anchors['cold_mask'], anchors['hot_mask'], anchor_mode, True)
    valid = ee.Number(ee.Algorithms.If(
        cold_lst.gt(200).And(hot_lst.gt(200))
        .And(hot_rn_g0.gt(-900)).And(cold_rn_g0.gt(-900))
        .And(hot_lst.subtract(cold_lst).gte(cfg.ANCHOR['min_dt'])), 1, 0))
    out = dict(anchors)
    out.update({'cold_lst': cold_lst, 'hot_lst': hot_lst,
                'hot_rn_g0': hot_rn_g0, 'cold_rn_g0': cold_rn_g0, 'valid': valid,
                'cold_point': cold_pt, 'hot_point': hot_pt, 'anchor_mode': anchor_mode})
    return out


def cold_anchor_surface_temp(image, image_anchor, anchors, roi,
                             anchor_mode='median_anchor'):
    """
    Empirik L↓ Tref — COLD ANCHOR pikselning ASL (radiatsion) LST'i (K).
      point_anchor  → anchor tanlagan AYNI piksel (image_anchor LST minimumi)
                      dagi asl LST (qiya yuzada image_anchor = LST_DEM).
      median_anchor → cold nomzod piksellarning asl LST mediani (anchor qiymati
                      bilan bir xil ta'rif).
    Butun maydon statistikasi EMAS. Topilmasa null qaytadi — chaqiruvchi to'xtaydi.
    """
    cm = anchors.get('cold_mask')
    if cm is None:                                     # anchor topilmagan — Tref yo'q
        return None
    proj = analysis_proj(image_anchor)                 # anchor tanlangan AYNI (tahlil) grid
    if anchor_mode == 'point_anchor':
        # AYNAN anchors['cold_point'] pikseli (deterministik tanlangan) — asl LST
        pt = anchors.get('cold_point')
        if pt is None:
            return None
        return image.select('LST').reduceRegion(
            ee.Reducer.first(), ee.Geometry.Point(ee.List(pt)),
            crs=proj, scale=ANCHOR_SCALE).get('LST')
    d = image.select('LST').updateMask(cm).reduceRegion(
        ee.Reducer.median(), roi, crs=proj, scale=ANCHOR_SCALE, maxPixels=1e9,
        bestEffort=True, tileScale=4)
    return d.get('LST')


# ==============================================================
# M6: WIND & MOMENTUM
# ==============================================================

def compute_friction_velocity(image, sloping_terrain=False, z_ws=0.0):
    """
    Ishqalanish tezligi u*(x,y) — ERA5 wind dan.

    Jarayon:
      1. ERA5 10m wind → 200m (blending height) extrapolyatsiya
      2. 200m wind → har piksel uchun u*(x,y) disaggregatsiya

    Formula (Allen/METRIC):
      u_200 = u_10 × ln(200/z0m_ws) / ln(10/z0m_ws)
      u*(x,y) = k × u_200 / ln(200/z0m(x,y))

    Dastlabki hisob — neytral sharoit (ψm = 0).
    Iteratsiyada ψm qo'shiladi.
    """
    wcfg = cfg.WIND

    wind_10 = image.select('WIND_SPEED_10M')
    z0m = image.select('Z0M')             # 0.018·LAI — u* uchun
    z0m_wind = image.select('Z0M_WIND')   # 0.123·h(NDVI) — shamol ekstrapolyatsiyasi

    z_ref = wcfg['z_ref_era5']       # 10m
    z_blend = wcfg['z_blending']     # 200m
    k = cfg.VON_KARMAN               # 0.41

    # 1. 10m → 200m extrapolyatsiya (neytral, log profile).
    #    z₀m,wind = 0.123·h(NDVI) — PER-PIKSEL (uniform-blending farazidan chetlashadi;
    #    foydalanuvchi tanlovi bilan). u_200 = u_10 × ln(200/z₀m,w)/ln(10/z₀m,w)
    u_200 = wind_10.multiply(
        ee.Image(z_blend).divide(z0m_wind).log().divide(
            ee.Image(z_ref).divide(z0m_wind).log()
        )
    ).rename('U_200')

    # ---- QIYA YUZA (Tasumi Eq 5.20-5.23) ----
    # z₀m_adj = (1+(s−5)/20)·z₀m  [s≥5°];  u200_adj = (1+0.1(z−z_ws)/1000)·u200
    # App. K: ET bularga JUDA KAM sezgir, lekin to'liqlik uchun qo'llanadi.
    if sloping_terrain:
        from . import sloping_terrain as slt
        z0m = slt.adjust_z0m(image, z0m)
        u_200 = slt.adjust_u200(image, u_200, z_ws).rename('U_200')

    # 2. u*(x,y) — har piksel uchun lokal z₀m dan
    # u* = k × u_200 / ln(200 / z₀m)
    ustar = (u_200.multiply(k)
             .divide(ee.Image(z_blend).divide(z0m).log())
             .rename('USTAR'))

    # u* minimum — juda past shamolda raqamiy beqarorlik
    ustar = ustar.max(0.02)

    return image.addBands(u_200).addBands(ustar)


def compute_rah_neutral(image):
    """
    Aerodinamik qarshilik — neytral sharoit (1-iteratsiya).

    rah = ln(z2_rah/z1) / (k × u*)   [z1 = 0.1 m, z2_rah = 2.0 m → ln(20); cfg.WIND]

    z2_rah va stability ψ ning z2 — ikkalasi 2.0 m (2026-07-24 dan; oldin z2_rah 0.2 edi).

    Bu faqat boshlang'ich qiymat — iteratsiyada ψh bilan tuzatiladi.
    """
    wcfg = cfg.WIND
    k = cfg.VON_KARMAN

    ustar = image.select('USTAR')

    ln_ratio = ee.Number(wcfg['z2_rah'] / wcfg['z1']).log()   # ln(2.0/0.1) = ln(20)

    rah = (ee.Image(ln_ratio)
           .divide(ustar.multiply(k))
           .rename('RAH'))

    # rah minimum (juda past qarshilik fizik emas)
    rah = rah.max(1.0)

    return image.addBands(rah)


# ==============================================================
# M7: SENSIBLE HEAT FLUX — Monin-Obukhov Iteration
# ==============================================================

def _stability_scalar(L, z_blend, z1, z2):
    """
    Paulson (1970) barqarorlik tuzatmalari — SOF PYTHON (skalyar).
    _stability_corrections (server ee.Image) ning aynan mos nusxasi;
    A skalyar sikl uchun (server chaqiruvi YO'Q, mahalliy hisob).
    """
    import math
    if L < 0:   # nobarqaror
        x200 = max(1.0 - 16.0 * z_blend / L, 0.001) ** 0.25
        psi_m = (2.0 * math.log((1.0 + x200) / 2.0)
                 + math.log((1.0 + x200 ** 2) / 2.0)
                 - 2.0 * math.atan(x200) + math.pi / 2.0)
        x_z1 = max(1.0 - 16.0 * z1 / L, 0.001) ** 0.25   # z1=0.1 (past)
        x_z2 = max(1.0 - 16.0 * z2 / L, 0.001) ** 0.25   # z2=2.0 (stability)
        psi_h_z1 = 2.0 * math.log((1.0 + x_z1 ** 2) / 2.0)
        psi_h_z2 = 2.0 * math.log((1.0 + x_z2 ** 2) / 2.0)
        psi_h = psi_h_z2 - psi_h_z1        # ψh(z2) - ψh(z1)
    else:       # barqaror (L > 0): ψm z=2m (Allen 2007), ψh=-5(z2-z1)/L
        psi_m = -5.0 * 2.0 / L
        psi_h = -5.0 * (z2 - z1) / L
    # ψ clamp ±5: fizik ψm/ψh kunduzi (beqaror) ~0–5 dan oshmaydi; ±10 manbali
    # emas edi (ortiqcha). ±5 — fizik jihatdan yetarli, konservativroq guard.
    psi_m = max(min(psi_m, 5.0), -5.0)
    psi_h = max(min(psi_h, 5.0), -5.0)
    return psi_m, psi_h


def compute_sensible_heat_flux(image, anchors, roi, mode='SEBAL_B',
                               lambda_et_cold=0.0, lambda_et_hot=0.0, qc=None):
    """
    Sezuvchan issiqlik oqimi H — iterativ hisoblash.
    Bastiaanssen (1998) original SEBAL yondashuvi (F.24-32).

    ASOSIY FARAZ:
      SEBAL_B (klassik, o'zgarmagan):
        Cold pixel: δTa_cold = 0  (H_cold = 0 — yaxshi sug'orilgan
                     maydonda butun mavjud energiya ET'ga sarflanadi)
        Hot pixel:  δTa_hot = H_hot × rah_hot / (ρₐ × cₚ)
                     H_hot = Q* - G₀  (hot pikselda λE = 0)

      SEBAL_ID (Tasumi 2003 — ikkala uch NOLMAS, ikkalasi iteratsiya qilinadi):
        Cold pixel: H_cp = Rn_cp − G_cp − λET_cp,  λET_cp = 1.05·ETr
                     δTa_cold = H_cp × rah_cp / (ρ · cₚ)
        Hot pixel:  H_hp = Rn_hp − G_hp − λET_hp,  λET_hp = ETrF_hot·ETr
                     (λET_hp suv balansidan; hozircha 0 → SEBAL_B hot bilan bir xil)
                     δTa_hot = H_hp × rah_hp / (ρ · cₚ)
        Chiziqli: c4 = (δTa_hot − δTa_cold)/(Ts_hot − Ts_cold),
                  c5 = δTa_cold − c4·Ts_cold.
      lambda_et_cold, lambda_et_hot — client skalyar [W/m²] (SEBAL_ID uchun).

    Konvergensiya mezoni — SEBAL Manual, Appendix 8:
      "This iterative process is repeated until the successive
       values for dThot and rah at the 'hot' pixel have stabilized."
      Ya'ni H o'zgarishi EMAS, balki hot pikseldagi dT va rah
      stabillashishi tekshiriladi (mutlaq tolerantlik + min_iter).

    Qo'shilgan raqamli xavfsizlik choralari (SEBAL fizikasini
    o'zgartirmaydi, faqat ekstremal/degenerativ holatlardan himoya
    qiladi):
      - dT'ni [cold_dT, hot_dT] ± 20% margin oralig'iga cheklash
        (chiziqli ekstrapolyatsiyaning cheksiz o'sib ketishidan himoya)
      - H ≤ (Rn−G0) (λE ≥ 0 kafolati). Pastki chegara YO'Q.
    OLIB TASHLANGAN (kitobda yo'q): Ta = LST − dT ni ERA5 AIR_TEMP ± 15 K ga
    cheklash (1-iteratsiyada neytral dT katta → raster yo'lini burardi) va
    H ≥ −100 (advektsiyada cold anchor H −242 W/m² gacha). Ta endi faqat QC
    diagnostikasi (qiymatlarga tegmaydi): anchor Ta vs ERA5 va |Ta−Ta_ERA5| > 15 K
    piksellar ulushi → sahna QC CSV.

    Odatda 3-5 iteratsiyada stabillashadi (max_iter=8 — faqat
    xavfsizlik chegarasi).
    """
    cold_lst = anchors['cold_lst']
    hot_lst = anchors['hot_lst']
    hot_rn_g0 = anchors['hot_rn_g0']
    cold_rn_g0 = anchors.get('cold_rn_g0')   # SEBAL_ID: cold H_cp uchun (hot'dan zaxira YO'Q)
    is_id = cfg.is_id_mode(mode)

    lst = image.select('LST')
    rho_air = image.select('RHO_AIR')
    u_200 = image.select('U_200')
    z0m = image.select('Z0M')
    rn_g0 = image.select('RN_G0')          # Rn - G0, H chegarasi uchun
    air_temp_era5 = image.select('AIR_TEMP')  # Ta QC diagnostikasi uchun (qiymatga tegmaydi)

    wcfg = cfg.WIND
    k = cfg.VON_KARMAN
    g = cfg.GRAVITY
    cp = cfg.CP_AIR
    z_blend = wcfg['z_blending']
    z1 = wcfg['z1']            # past balandlik (rah + stability)
    z2_rah = wcfg['z2_rah']    # rah LOG hadi (2.0 m, cfg.WIND)
    z2 = wcfg['z2']            # STABILITY ψ yuqori balandligi (2.0m)

    max_iter = cfg.ITERATION['max_iter']
    min_iter = cfg.ITERATION['min_iter']
    tol_rel = cfg.ITERATION['tol_rel']   # 1% nisbiy konvergensiya

    # ==========================================================
    # ANCHOR SKALYARLARINI BIR MARTA OLISH (yagona getInfo)
    # ==========================================================
    # u200, z0m, ρ — anchors['anchor_mode'] da (point → AYNAN anchor pikseli,
    # median → nomzodlar mediani), LST/Rn−G₀ bilan AYNI rejim va AYNI grid
    # (_anchor_sample). Keyin (A) iteratsiya sof Python'da, server chaqiruvisiz.
    a_mode = anchors.get('anchor_mode')
    sides = ('cold', 'hot') if is_id else ('hot',)
    stats = ee.Dictionary({
        's': _anchor_sample(image, anchors, roi, ['U_200', 'Z0M', 'RHO_AIR'], sides),
        'hot_lst': hot_lst, 'cold_lst': cold_lst,
        'hot_rn_g0': hot_rn_g0, 'cold_rn_g0': cold_rn_g0,
    }).getInfo()

    import math
    hlst = stats.get('hot_lst')
    clst = stats.get('cold_lst')
    # ---- ΔT HIMOYASI: c4 = (dT_hot − dT_cold)/(T_hot − T_cold) ----
    # T_hot = T_cold → nolga bo'lish; T_hot < T_cold → c4 ishorasi teskari.
    # Chegara anchor tanlashdagi bilan BITTA: cfg.ANCHOR['min_dt'].
    min_dt = cfg.ANCHOR['min_dt']
    if hlst is None or clst is None or hlst < 200 or clst < 200:
        raise SceneQCError(f"anchor LST topilmadi (cold {clst}, hot {hlst})")
    if not (hlst - clst) >= min_dt:
        raise SceneQCError(f"anchor ΔT = T_hot − T_cold = {hlst - clst:.2f} K < {min_dt} K "
                           f"(cold {clst:.2f} K, hot {hlst:.2f} K)")

    # Anchor Rn−G₀ — hot (har doim), cold (SEBAL_ID oilasi) BO'LISHI SHART
    for side in sides:
        v = stats.get(f'{side}_rn_g0')
        if v is None or v <= -900:
            raise SceneQCError(f"{side} anchor Rn−G₀ topilmadi")

    smp = stats['s']
    for side in sides:
        miss = [b for b in ('U_200', 'Z0M', 'RHO_AIR') if smp[side].get(b) is None]
        if miss:
            raise RuntimeError(f"{side} anchor ({a_mode}) da {', '.join(miss)} topilmadi — "
                               f"default qiymat ishlatilmaydi.")
    if a_mode == 'point_anchor':
        # Grid tekshiruvi: namuna AYNAN anchor pikselidanmi (LST teng bo'lishi shart)
        for side, t in (('hot', hlst), ('cold', clst)):
            if side in smp and abs(smp[side]['LST'] - t) > 1e-3:
                msg = (f"{side} anchor namunasi LST {smp[side]['LST']:.3f} ≠ anchor LST "
                       f"{t:.3f} K — namuna boshqa pikseldan (grid nomuvofiq)")
                print(f"  ⚠️ OGOHLANTIRISH: {msg}")
                if qc is not None:
                    qc.setdefault('warnings', []).append(msg)

    u200_h = smp['hot']['U_200']
    z0m_h = max(smp['hot']['Z0M'], cfg.ROUGHNESS['z0m_min'])   # log domeni himoyasi
    rho_h = smp['hot']['RHO_AIR']
    # H_hot = Rn−G₀ − λET_hot (SEBAL_B: λET_hot=0 → H_hot=Rn−G₀, o'zgarmagan)
    H_hot = stats['hot_rn_g0'] - lambda_et_hot

    # SEBAL_ID: cold piksel skalyarlari + H_cold = Rn−G₀_cp − λET_cp
    if is_id:
        u200_c = smp['cold']['U_200']
        z0m_c = max(smp['cold']['Z0M'], cfg.ROUGHNESS['z0m_min'])
        rho_c = smp['cold']['RHO_AIR']
        H_cold = stats['cold_rn_g0'] - lambda_et_cold
    else:
        u200_c = z0m_c = rho_c = None
        H_cold = 0.0

    # ==========================================================
    # (A) SKALYAR ITERATSIYA — sof Python (server chaqiruvi YO'Q).
    #     rah_hot ni o'z-o'ziga mos topib, har iteratsiya c4/c5 ni yozadi.
    #     Skalyar bo'lgani uchun bir zumda ishlaydi — graf o'smaydi.
    # ==========================================================
    ln_zb_z0m = math.log(z_blend / z0m_h)
    ln_z2_z1 = math.log(z2_rah / z1)   # 

    ustar_h = max(k * u200_h / ln_zb_z0m, 0.02)          # neytral boshlang'ich
    rah_h = max(ln_z2_z1 / (k * ustar_h), 1.0)

    # SEBAL_ID: cold piksel parallel iteratsiyasi (δTa_cold ≠ 0)
    if is_id:
        ln_zb_z0m_cold = math.log(z_blend / z0m_c)
        ustar_cold = max(k * u200_c / ln_zb_z0m_cold, 0.02)
        rah_cold = max(ln_z2_z1 / (k * ustar_cold), 1.0)
        prev_psi_m_cold = prev_psi_h_cold = prev_ustar_cold = None

    c4_list, c5_list, dta_list, dtac_list = [], [], [], []
    prev_dt = prev_rah = prev_rah_c = None
    prev_psi_m = prev_psi_h = prev_ustar = None
    converged_at = None
    hot_ok = cold_ok = False

    for i in range(max_iter):
        # δTa_hot = H_hot·rah_hot/(ρ·cp)
        dta_hot = H_hot * rah_h / (rho_h * cp)
        # δTa_cold: SEBAL_B → 0; SEBAL_ID → H_cp·rah_cp/(ρ·cp)
        dta_cold = (H_cold * rah_cold / (rho_c * cp)) if is_id else 0.0
        c4 = (dta_hot - dta_cold) / (hlst - clst)     # chiziqli kalibratsiya
        c5 = dta_cold - c4 * clst
        c4_list.append(c4)
        c5_list.append(c5)
        dta_list.append(dta_hot)
        dtac_list.append(dta_cold)

        # Konvergensiya (SEBAL Manual App.8): dT_hot va rah_hot stabillashishi.
        # NISBIY (1%): masshtabdan mustaqil (kichik/katta dT'ga bir xil mos).
        # SEBAL_ID: cold uchi ham (δTa_cold ≠ 0) stabillashishi SHART — aks holda
        # c4/c5 yaqinlashmagan dT_cold bilan qoladi (2023-12-10: to'xtaganda
        # dT_cold 3.14 K, yaqinlashgan ≈2.71 K). H_cold, ρ_c o'zgarmas → dT_cold ∝
        # rah_cold, shuning uchun rah_cold nisbiy o'zgarishi = dT_cold nisbiy
        # o'zgarishi (dT_cold ≈ 0 bo'lganda ham ishlaydi).
        if prev_dt is not None and (i + 1) >= min_iter:
            hot_ok = (abs(dta_hot - prev_dt) < tol_rel * abs(dta_hot)
                      and abs(rah_h - prev_rah) < tol_rel * abs(rah_h))
            cold_ok = (not is_id) or abs(rah_cold - prev_rah_c) < tol_rel * abs(rah_cold)
            if hot_ok and cold_ok:
                converged_at = i + 1
                print(f"  ✅ (A) Konvergensiya {i+1}-iteratsiyada: "
                      f"dT_hot={dta_hot:.4f} K, rah_hot={rah_h:.3f} s/m"
                      + (f", dT_cold={dta_cold:.4f} K, rah_cold={rah_cold:.3f} s/m"
                         if is_id else ""))
                break

        prev_dt, prev_rah = dta_hot, rah_h
        if is_id:
            prev_rah_c = rah_cold

        # ---- Hot piksel Monin-Obukhov stability ----
        h_safe = H_hot if abs(H_hot) >= 1.0 else 1.0
        L_h = -rho_h * cp * ustar_h ** 3 * hlst / (k * g * h_safe)
        L_h = max(min(L_h, 1e6), -1e6)

        psi_m_cand, psi_h_cand = _stability_scalar(L_h, z_blend, z1, z2)

        # Dhungel et al. (2016) damping — ketma-ket ikki ψ (va u*) o'rtachasi.
        # DOI: 10.1117/1.JRS.10.026033 ("averaging the last two calculations
        # for the three psi terms" + "averaging the u* ...").
        if prev_psi_m is not None:
            psi_m = 0.5 * (prev_psi_m + psi_m_cand)
            psi_h = 0.5 * (prev_psi_h + psi_h_cand)
        else:
            psi_m, psi_h = psi_m_cand, psi_h_cand
        prev_psi_m, prev_psi_h = psi_m_cand, psi_h_cand

        ustar_cand = max(k * u200_h / (ln_zb_z0m - psi_m), 0.02)
        if prev_ustar is not None:
            ustar_h = 0.5 * (prev_ustar + ustar_cand)
        else:
            ustar_h = ustar_cand
        prev_ustar = ustar_cand

        rah_h = max((ln_z2_z1 - psi_h) / (k * ustar_h), 1.0)

        # ---- Cold piksel Monin-Obukhov stability (SEBAL_ID) ----
        if is_id:
            hc_safe = (H_cold if abs(H_cold) >= 1.0
                       else (1.0 if H_cold >= 0 else -1.0))
            L_c = -rho_c * cp * ustar_cold ** 3 * clst / (k * g * hc_safe)
            L_c = max(min(L_c, 1e6), -1e6)
            psi_m_cc, psi_h_cc = _stability_scalar(L_c, z_blend, z1, z2)
            if prev_psi_m_cold is not None:
                psi_m_cold = 0.5 * (prev_psi_m_cold + psi_m_cc)
                psi_h_cold = 0.5 * (prev_psi_h_cold + psi_h_cc)
            else:
                psi_m_cold, psi_h_cold = psi_m_cc, psi_h_cc
            prev_psi_m_cold, prev_psi_h_cold = psi_m_cc, psi_h_cc
            ustar_cold_cand = max(k * u200_c / (ln_zb_z0m_cold - psi_m_cold), 0.02)
            if prev_ustar_cold is not None:
                ustar_cold = 0.5 * (prev_ustar_cold + ustar_cold_cand)
            else:
                ustar_cold = ustar_cold_cand
            prev_ustar_cold = ustar_cold_cand
            rah_cold = max((ln_z2_z1 - psi_h_cold) / (k * ustar_cold), 1.0)

    N_A = converged_at if converged_at is not None else max_iter

    # ---- FIZIK SIFAT TEKSHIRUVI (kalibratsiya) — buzilsa sahna RAD ETILADI ----
    #   H_hot > 0 (hot pikselda sezuvchan issiqlik bor) va dT_hot > dT_cold
    #   (dT–Ts qiyaligi c4 > 0). Buzilsa EF butun sahnada teskari/1 bo'ladi
    #   (2023-03-13: dT_hot −2.4 K, EF = 1.00 hamma joyda).
    dT_h, dT_c = dta_list[N_A - 1], dtac_list[N_A - 1]
    if qc is not None:
        qc.update({'dT_hot': dT_h, 'dT_cold': dT_c, 'H_hot': H_hot, 'H_cold': H_cold})
    fails = []
    if not H_hot > 0:
        fails.append(f"H_hot = {H_hot:.1f} W/m² ≤ 0")
    if not dT_h > dT_c:
        fails.append(f"dT_hot = {dT_h:.2f} K ≤ dT_cold = {dT_c:.2f} K")
    if fails:
        raise SceneQCError("fizik kalibratsiya buzilgan: " + "; ".join(fails))
    if converged_at is None:
        side = ' va '.join(n for n, ok in (('hot', hot_ok), ('cold', cold_ok)) if not ok)
        msg = (f"(A) {max_iter} iteratsiyada {side} uchi yaqinlashmadi — "
               f"eng so'nggi qiymat bilan davom etadi")
        print(f"  ⚠️ {msg}")
        if qc is not None:
            qc.setdefault('warnings', []).append(msg)

    # ==========================================================
    # (B) RASTER ITERATSIYA — server-side, aynan N_A qadam, getInfo YO'Q.
    #     Har qadam c4_i/c5_i KONSTANTA sifatida inject qilinadi (embedded
    #     reduceRegion yo'q → yengil graf, timeout yo'q). B konvergensiyani
    #     TEKSHIRMAYDI: hot piksel eng og'ir holat — u N_A da konvergent
    #     bo'lsa, sovuqroq piksellar undan tezroq → hammasi konvergent.
    # ==========================================================
    ustar = image.select('USTAR')     # neytral init
    rah = image.select('RAH')
    prev_psi_m_img = prev_psi_h_img = prev_ustar_img = None
    dta = h = L_mo = None

    for i in range(N_A):
        c4_i = ee.Number(c4_list[i])
        c5_i = ee.Number(c5_list[i])
        dta_hot_i = dta_list[i]        # client skalyar (clamp chegaralari uchun)
        # SEBAL_B: pastki uch = 0 (dTa_cold=0); SEBAL_ID: dTa_cold (nolmas)
        dta_cold_i = dtac_list[i] if is_id else 0.0

        # Har piksel δTa
        dta_raw = lst.multiply(c4_i).add(c5_i)

        # XAVFSIZLIK 1: [dTa_cold, dTa_hot] ± 20% margin (chegaralar — client skalyar)
        dt_lower = min(dta_cold_i, dta_hot_i)
        dt_upper = max(dta_cold_i, dta_hot_i)
        margin = (dt_upper - dt_lower) * 0.2
        dta = dta_raw.clamp(dt_lower - margin, dt_upper + margin).rename('DTA')

        # (Ta = T0 − dT ni ERA5 AIR_TEMP ± 15 K ga cheklash OLIB TASHLANDI — kitobda
        #  yo'q; 1-iteratsiyada neytral dT katta bo'lib, raster yo'lini skalyardan
        #  ajratardi: 2023-11-16 hot H 153.7 vs maqsad 171.5. Endi faqat QC.)

        # H = ρ·cp·δTa/rah  →  XAVFSIZLIK 2: H ≤ Rn−G₀ (λE ≥ 0). Pastki chegara YO'Q
        # (−100 olib tashlandi: advektsiyada cold anchor H −242 W/m², 2023-08-20).
        h_raw = rho_air.multiply(cp).multiply(dta).divide(rah)
        h = h_raw.min(rn_g0).rename('H')

        # Monin-Obukhov L
        h_safe = h.where(h.abs().lt(1.0), ee.Image(1.0))
        L_mo = (rho_air.multiply(cp).multiply(ustar.pow(3)).multiply(lst)
                .divide(ee.Image(k * g).multiply(h_safe))
                .multiply(-1).rename('L_MO'))
        L_mo = L_mo.clamp(-1e6, 1e6)

        # Oxirgi qadam: H aynan shu rah/u* bilan hisoblandi → RAH/USTAR bandlari SHU
        # qiymatda qoladi (H = ρ·cp·DTA/RAH izchil; ANCHOR_RAH_HOT ham). Oldin sikl
        # keyingi qadam uchun u*/rah ni yana yangilardi → bandlar H'dan bir qadam oldinda.
        if i == N_A - 1:
            break

        # ψ (Dhungel damping — A bilan bir xil mantiq)
        psi_m_calc, psi_h_calc = _stability_corrections(L_mo, z_blend, z1, z2)
        if prev_psi_m_img is not None:
            psi_m_200 = prev_psi_m_img.add(psi_m_calc).multiply(0.5)
            psi_h = prev_psi_h_img.add(psi_h_calc).multiply(0.5)
        else:
            psi_m_200, psi_h = psi_m_calc, psi_h_calc
        prev_psi_m_img, prev_psi_h_img = psi_m_calc, psi_h_calc

        # u* (damped) va rah — keyingi qadam uchun
        ustar_calc = (ee.Image(k).multiply(u_200)
                      .divide(ee.Image(z_blend).divide(z0m).log()
                              .subtract(psi_m_200))
                      .rename('USTAR')).max(0.02)
        if prev_ustar_img is not None:
            ustar = prev_ustar_img.add(ustar_calc).multiply(0.5).rename('USTAR')
        else:
            ustar = ustar_calc
        prev_ustar_img = ustar_calc

        rah = (ee.Image(z2_rah / z1).log().subtract(psi_h)
               .divide(ustar.multiply(k)).rename('RAH')).max(1.0)

    # Yakuniy bandlar
    image = image.addBands(dta, overwrite=True)
    image = image.addBands(h, overwrite=True)
    image = image.addBands(ustar, overwrite=True)
    image = image.addBands(rah, overwrite=True)
    image = image.addBands(L_mo, overwrite=True)
    image = image.set('h_converged_iter', N_A)

    # ── OXIRGI natija — BITTA getInfo (B sikl ICHIDA emas) ──
    # Yakuniy raster H/dT/rah ni hot pikseldan bir marta o'qib, qiymatlar
    # va nechada konvergent bo'lganini (N_A) ko'rsatamiz.
    # anchor rejimida (point → AYNAN anchor pikseli; median → nomzodlar mediani)
    # Ta QC (qiymatlarga TEGMAYDI): Ta = LST − dT (yakuniy) vs ERA5 AIR_TEMP —
    # anchorlarda va sahna bo'yicha |Ta − Ta_ERA5| > 15 K piksellar ulushi (90 m).
    ta_out = (lst.subtract(image.select('DTA')).subtract(air_temp_era5).abs()
              .gt(15).rename('OUT15'))
    req = ee.Dictionary({
        'a': _anchor_sample(image, anchors, roi,
                            ['DTA', 'RAH', 'H', 'ALBEDO', 'NDVI', 'LAI', 'WIND_SPEED_10M',
                             'AIR_TEMP']),
        'out15': ta_out.reduceRegion(ee.Reducer.mean(), roi, crs=analysis_proj(image),
                                     scale=90, maxPixels=1e9,
                                     bestEffort=True, tileScale=4).get('OUT15'),
    }).getInfo()
    fin_all = req['a']
    fin, fin_c = fin_all['hot'], fin_all['cold']
    ta_qc = {}
    for side, v in (('hot', fin), ('cold', fin_c)):
        if v.get('LST') is not None and v.get('DTA') is not None:
            ta_qc[f'Ta_{side}'] = v['LST'] - v['DTA']
            ta_qc[f'Ta_era5_{side}'] = v.get('AIR_TEMP')
    if req.get('out15') is not None:
        ta_qc['pct_Ta_out15'] = 100.0 * req['out15']
    if fin_c.get('LAI') is not None:
        ta_qc['cold_LAI'] = fin_c['LAI']      # to'liq qoplama (cfg.ANCHOR['cold_lai_min']) QC
    if qc is not None:
        qc.update(ta_qc)
    # Cold anchor Ta ↔ ERA5 — farq katta bo'lsa OGOHLANTIRISH (rad etish EMAS)
    if ta_qc.get('Ta_cold') is not None and ta_qc.get('Ta_era5_cold') is not None:
        d_ta = ta_qc['Ta_cold'] - ta_qc['Ta_era5_cold']
        thr = cfg.ANCHOR['cold_ta_warn']
        if abs(d_ta) > thr:
            msg = (f"cold anchor Ta {ta_qc['Ta_cold']:.1f} K − ERA5 {ta_qc['Ta_era5_cold']:.1f} K "
                   f"= {d_ta:+.1f} K (|farq| > {thr} K) — cold kalibratsiya shubhali")
            print(f"    ⚠️ OGOHLANTIRISH: {msg}")
            if qc is not None:
                qc.setdefault('warnings', []).append(msg)

    def _fmt(x):
        return f"{x:.3f}" if isinstance(x, (int, float)) else str(x)
    print(f"  ✅ (B) Raster {N_A} qadam ({a_mode}) | hot: dT={_fmt(fin.get('DTA'))} K, "
          f"rah={_fmt(fin.get('RAH'))} s/m, H={_fmt(fin.get('H'))} W/m² (maqsad {H_hot:.1f})"
          + (f" | cold: dT={_fmt(fin_c.get('DTA'))} K, rah={_fmt(fin_c.get('RAH'))} s/m, "
             f"H={_fmt(fin_c.get('H'))} W/m² (maqsad {H_cold:.1f})" if is_id else "")
          + f" | N konvergent = {N_A}")

    def _t(k):
        v = ta_qc.get(k)
        return f"{v:.2f}" if isinstance(v, (int, float)) else '—'
    print(f"  🌡️ Ta QC (qiymatga tegmaydi): hot Ta {_t('Ta_hot')} K (ERA5 {_t('Ta_era5_hot')}), "
          f"cold Ta {_t('Ta_cold')} K (ERA5 {_t('Ta_era5_cold')}) | |Ta−Ta_ERA5| > 15 K: "
          f"{_t('pct_Ta_out15')} % piksel")

    # ── ANCHOR TASHXIS (sahna PROPERTY sifatida — CSV export uchun) ──
    # Tanlangan cold/hot piksel FIZIK xususiyatlari: LST, albedo, NDVI, shamol +
    # motor natijasi dT_hot/rah_hot/H_hot. Bu fizika'ga TEGMAYDI — anchor
    # tanlashni QC qilish va oyма-oy fizik oynalarni (LST/albedo/shamol/NDVI)
    # ground-truth'ga qarab sozlash uchun. albedo/ndvi/shamol — anchor rejimida
    # (point → anchor pikseli, median → nomzodlar mediani; oldin mask MEAN edi).
    def _pv(x):
        return x if isinstance(x, (int, float)) else -999

    image = (image
             .set('ANCHOR_COLD_LST', _pv(stats.get('cold_lst')))
             .set('ANCHOR_HOT_LST', _pv(stats.get('hot_lst')))
             .set('ANCHOR_DT_HOT', _pv(fin.get('DTA')))
             .set('ANCHOR_RAH_HOT', _pv(fin.get('RAH')))
             .set('ANCHOR_H_HOT', _pv(fin.get('H')))
             .set('ANCHOR_COLD_ALBEDO', _pv(fin_c.get('ALBEDO')))
             .set('ANCHOR_HOT_ALBEDO', _pv(fin.get('ALBEDO')))
             .set('ANCHOR_COLD_NDVI', _pv(fin_c.get('NDVI')))
             .set('ANCHOR_HOT_NDVI', _pv(fin.get('NDVI')))
             .set('ANCHOR_COLD_WIND', _pv(fin_c.get('WIND_SPEED_10M')))
             .set('ANCHOR_HOT_WIND', _pv(fin.get('WIND_SPEED_10M'))))

    return image


def _stability_corrections(L_mo, z_blend, z1, z2):
    """
    Paulson (1970) barqarorlik tuzatmalari.

    Nobarqaror (L < 0):
      x = (1 - 16×z/L)^0.25
      ψm = 2×ln((1+x)/2) + ln((1+x²)/2) - 2×arctan(x) + π/2
      ψh = 2×ln((1+x²)/2)

    Barqaror (L > 0):
      ψm = ψh = -5 × z/L

    Returns: psi_m_200, psi_h (z1/z2 orasida)
    """
    import math

    # --- Nobarqaror (L < 0) ---
    # z_blend (200m) uchun x_200 — ψm(200) uchun
    x_200 = (ee.Image(1.0)
             .subtract(ee.Image(16.0 * z_blend).divide(L_mo))
             .max(0.001)  # manfiy bo'lmasligi uchun
             .pow(0.25))

    psi_m_200_unstable = (
        x_200.add(1).divide(2).log().multiply(2)
        .add(x_200.pow(2).add(1).divide(2).log())
        .subtract(x_200.atan().multiply(2))
        .add(math.pi / 2)
    )

    # z1 (0.1m, past) va z2 (2.0m, stability) uchun x — ψh uchun (Eq. 3.36-3.40)
    x_z1 = (ee.Image(1.0).subtract(ee.Image(16.0 * z1).divide(L_mo))
            .max(0.001).pow(0.25))
    x_z2 = (ee.Image(1.0).subtract(ee.Image(16.0 * z2).divide(L_mo))
            .max(0.001).pow(0.25))
    psi_h_z1 = x_z1.pow(2).add(1).divide(2).log().multiply(2)
    psi_h_z2 = x_z2.pow(2).add(1).divide(2).log().multiply(2)

    # rah = [ln(z2/z1) - ψh(z2) + ψh(z1)]/(u*k)  →  psi_h = ψh(z2) - ψh(z1)
    psi_h_unstable = psi_h_z2.subtract(psi_h_z1)

    # --- Barqaror (L > 0), Eq. 3.41-3.42 ---
    # Allen et al. (2007): STABLE'da ψm uchun z=2m ishlatiladi (200m emas —
    # raqamli beqarorlikdan himoya). ψh = -5(z2-z1)/L (yupqa qatlam).
    psi_m_200_stable = ee.Image(-5.0 * 2.0).divide(L_mo)
    psi_h_stable = ee.Image(-5.0 * (z2 - z1)).divide(L_mo)

    # --- Shartli tanlash ---
    is_unstable = L_mo.lt(0)

    # ψ clamp ±5 (skalyar _stability_scalar bilan bir xil): fizik ψ kunduzi
    # ~0–5; ±10 manbali emas edi. ±5 konservativroq, kunduzgi natijaga ta'siri kam.
    psi_m_200 = (psi_m_200_unstable.where(is_unstable.Not(), psi_m_200_stable)
                 .clamp(-5, 5))

    psi_h = (psi_h_unstable.where(is_unstable.Not(), psi_h_stable)
             .clamp(-5, 5))

    return psi_m_200, psi_h


# ==============================================================
# M8: LATENT HEAT FLUX λE — Energy Balance Residual
# ==============================================================

def compute_latent_heat_flux(image):
    """
    Yashirin issiqlik oqimi — Bastiaanssen F.32.

    λE = Q* - G₀ - H  (W/m²)

    Bu SEBAL ning yakuniy natijasi (lahzali).
    Salbiy λE fizik emas — 0 ga clamp qilinadi.
    (Kechqurun kondensatsiya bo'lishi mumkin, lekin Landsat
     faqat kunduzi o'tadi)
    """
    rn = image.select('RN')
    g0 = image.select('G0')
    h = image.select('H')

    lambda_e = (rn.subtract(g0).subtract(h)
                .max(0)
                .rename('LAMBDA_E'))

    return image.addBands(lambda_e)


# ==============================================================
# EVAPORATIVE FRACTION Λ
# ==============================================================

def compute_evaporative_fraction(image):
    """
    Bug'lanish ulushi — Bastiaanssen (1998), Gediz F.2.

    Λ = λE / (Q* - G₀)

    Λ xususiyatlari:
      - Kunboyi deyarli barqaror (10:00–15:00)
      - 0 (to'liq quruq) dan 1 (to'liq ho'l) gacha
      - Monthly extrapolation uchun kalit parametr

    Bu ETrF bilan deyarli bir xil, lekin semantik farq bor:
      - ETrF: reference ET ga nisbat
      - Λ: mavjud energiyaga nisbat
    """
    lambda_e = image.select('LAMBDA_E')
    rn_g0 = image.select('RN_G0')

    # Nofizik (Rn−G₀ ≤ 0) piksellar — tush payti bo'lmasligi kerak (bulut/suv/
    # soya/xato). Soxta maxraj (max(10)) quyish o'rniga ularni MASKALAYMIZ →
    # EVAP_FRAC o'sha yerda nodata (fake qiymat emas). Cropland'ga ta'sir ≈ nol
    # (Rn−G₀ ≈ 400–600 W/m² ≫ 0). Kichik musbat maxrajni .clamp(0,1) ushlaydi.
    rn_g0_pos = rn_g0.updateMask(rn_g0.gt(0))

    evap_frac = (lambda_e.divide(rn_g0_pos)
                 .clamp(0, 1.0)
                 .rename('EVAP_FRAC'))

    return image.addBands(evap_frac)


# ==============================================================
# MAIN: Full energy balance
# ==============================================================

def anchor_etr_inst(image, roi, anchors):
    """
    SEBAL_ID oilasi (SEBAL_ID, SEBAL_Milliy): cold va hot anchordagi instant ETr
    (ETR_INST, mm/soat) → λET_cold = COLD_ETRF·ETr_c, λET_hot = ETrF_hot·ETr_h.
    anchors['anchor_mode'] da olinadi (_anchor_sample): point → AYNAN anchor
    pikseli (LST/Rn−G₀ olingan o'sha piksel), median → nomzodlar mediani —
    ikkalasi ham anchor gridida (ANCHOR_SCALE). Oldin maska mediani 100 m da
    olinardi: kichik maska (masalan pysebal cold) 100 m da bo'sh → null → run to'xtardi.
    Biror tomonda ETr chiqmasa — RuntimeError (sahna sanasi va sababi bilan);
    default qiymat YO'Q.
    """
    vals = _anchor_sample(image, anchors, roi, ['ETR_INST']).getInfo()
    etr_c, etr_h = vals['cold'].get('ETR_INST'), vals['hot'].get('ETR_INST')
    missing = [side for side, v in (('cold', etr_c), ('hot', etr_h)) if v is None]
    if missing:
        date = ee.Date(image.get('system:time_start')).format('YYYY-MM-dd').getInfo()
        raise RuntimeError(
            f"{date}: {' va '.join(missing)} anchorda ({anchors.get('anchor_mode')}) instant ETr "
            f"(ETR_INST) topilmadi — λET_{'/'.join(missing)} hisoblab bo'lmaydi. "
            f"Default 0 ishlatilmaydi. Tekshiring: ERA5 meteo (AIR_TEMP, DEWPOINT, "
            f"WIND_SPEED_10M, SSRD) anchor pikselida bormi.")
    return etr_c, etr_h


def compute_all(image, roi, cold_zone=None, hot_zone=None, anchors=None,
                anchor_method='cimec', anchor_mode='median_anchor',
                mode='SEBAL_B', etrf_hot=None,
                sloping_terrain=False, z_ws=0.0, qc=None, etr24_source='era5'):
    """
    To'liq energiya balansini hisoblash.

    Tartib:
      1. Wind & momentum (u*, u_200)
      2. Neytral rah
      3. Anchor pixel selection
      4. H iteratsiya (Monin-Obukhov)
      5. λE = Q* - G₀ - H
      6. ETrF, Λ

    Input:  Image with surface properties + radiation
    Output: Image with H, LAMBDA_E, ETrF, EVAP_FRAC bands

    mode='SEBAL_ID' — cold piksel dTa≠0 (ET_cp=1.05·ETr) va hot piksel
      dTa (ET_hp=ETrF_hot·ETr). ETr instant alfalfa (FAO-56 PM). etrf_hot —
      hot piksel suv balansi koeffitsienti (default 0 → SEBAL_B hot bilan bir xil;
      keyingi bosqichda water_balance beradi).

    Anchor pixel tanlash ROI kerak — shuning uchun
    bu funksiya map() ichida emas, alohida chaqiriladi.
    """
    # ---- QIYA YUZA (Tasumi Eq 5.11): dT uchun Ts ni DEM ga moslash ----
    # Ts_dem = Ts + 0.0065·z. FAQAT anchor tanlash va dT–Ts munosabatida;
    # radiatsiya (L↑, G₀) ALLAQACHON asl Ts bilan hisoblangan (radiation.py),
    # va oxirida LST asl holiga qaytariladi (daily_et λ_hv asl Ts talab qiladi).
    lst_actual = image.select('LST')
    if sloping_terrain:
        from . import sloping_terrain as slt
        image = image.addBands(slt.lst_dem(image), overwrite=True)

    # M6: Wind & momentum
    image = compute_friction_velocity(image, sloping_terrain=sloping_terrain,
                                      z_ws=z_ws)
    image = compute_rah_neutral(image)

    # M5: Anchor selection
    if anchors is None:
        anchors = select_anchor_pixels(image, roi, cold_zone=cold_zone,
                                       hot_zone=hot_zone, method=anchor_method,
                                       anchor_mode=anchor_mode,
                                       hot_soil=cfg.is_id_mode(mode),
                                       cold_full_cover=cfg.is_id_mode(mode))
        anchors, _ = materialize_anchors(anchors)

    # ---- SEBAL_ID: instant alfalfa ETr → cold/hot λET skalyarlari ----
    lambda_et_cold = lambda_et_hot = 0.0
    if cfg.is_id_mode(mode):
        from . import water_balance
        image = ref_et.compute_instant_etr(image)     # ETR_INST band (mm/soat)
        LAMBDA = 2.45e6                                 # bug'lanish yashirin issiqligi [J/kg]
        # Hot piksel suv balansi → ETrF_hot — anchor tanlagan AYNAN o'sha pikselda
        if etrf_hot is None:
            if anchors.get('hot_point') is None:
                raise ValueError(f"{mode}: hot suv balansi uchun anchor nuqtasi kerak "
                                 f"(anchor_mode='point_anchor').")
            hot_lonlat = ee.List(anchors['hot_point']).getInfo()
            if hot_lonlat is None or None in hot_lonlat:
                raise RuntimeError(f"{mode}: hot anchor koordinatasi topilmadi.")
            wbr = water_balance.hot_pixel_etrf(
                image, roi, hot_lonlat, (analysis_proj(image), ANCHOR_SCALE),
                etr24_source=etr24_source)   # ETr24 usuli; kun — UTC (CHIRPS bilan AYNI)
            etrf_hot = wbr['etrf_hot']
            if qc is not None:
                qc.update(wbr)
            if etrf_hot > cfg.HOT_WB['etrf_warn']:
                msg = (f"ETrF_hot = {etrf_hot:.3f} > {cfg.HOT_WB['etrf_warn']} "
                       f"(P {wbr['P_sum']:.1f} mm / {wbr['window']} kun) — nam tasvir ehtimoli")
                print(f"    ⚠️ OGOHLANTIRISH: {msg}")
                if qc is not None:
                    qc.setdefault('warnings', []).append(msg)
        # ETr topilmasa XATO — λET_cold/λET_hot jimgina 0 deb olinmaydi.
        etr_c, etr_h = anchor_etr_inst(image, roi, anchors)
        # λET_cp = COLD_ETRF·ETr; λET_hp = ETrF_hot·ETr  (W/m² = mm/soat · λ / 3600)
        lambda_et_cold = COLD_ETRF * etr_c * LAMBDA / 3600.0
        lambda_et_hot = etrf_hot * etr_h * LAMBDA / 3600.0

    # M7: Sensible heat flux (iterativ)
    image = compute_sensible_heat_flux(image, anchors, roi, mode=mode,
                                       lambda_et_cold=lambda_et_cold,
                                       lambda_et_hot=lambda_et_hot, qc=qc)

    # Qiya yuza: LST ni ASL holiga qaytarish (dT bosqichi tugadi).
    # λE = Rn−G₀−H bo'lgani uchun bu λE ga ta'sir qilmaydi, lekin keyingi
    # bosqichlar (daily_et λ_hv = f(LST)) asl haroratni talab qiladi.
    if sloping_terrain:
        image = image.addBands(lst_actual, overwrite=True)

    # M8: Latent heat flux
    image = compute_latent_heat_flux(image)
    image = compute_evaporative_fraction(image)

    return image

def get_anchor_cropland_mask(image, roi):
    """
    Anchor tanlash uchun cropland mask.
    Faqat ESA WorldCover class 40 — cropland.
    """
    proj = analysis_proj(image)

    cropland = (
        ee.ImageCollection(cfg.CROPLAND_COLLECTION)
        .first()
        .select('Map')
        .eq(cfg.CROPLAND_CLASS)
        .rename('ANCHOR_CROPLAND')
        .clip(roi)
        .reproject(crs=proj, scale=30)
    )

    valid_lst = image.select('LST').mask()

    return cropland.updateMask(valid_lst)
