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


# ==============================================================
# TILE-DARAJASIDA CROPLAND ZONASI — bir marta hisoblanadi
# ==============================================================

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

# def select_anchor_pixels(image, roi):
#     """
#     Cold va hot anchor piksellarni avtomatik tanlash.

#     Bastiaanssen (1998) p.206:
#       Cold: NDVI top 5%, LST bottom 20%, albedo < 0.20
#       Hot:  NDVI bottom 10%, LST top 5%, albedo > 0.18

#     Jarayon:
#       1. Sifat maskasi (slope < 5°, valid piksellar)
#       2. Percentile hisoblash
#       3. Kandidatlarni filtr
#       4. Median qiymat olish (outlier himoyasi)

#     Returns
#     -------
#     dict : cold_lst, hot_lst, hot_h, hot_dta, c4, c5
#     """
#     acfg = cfg.ANCHOR

#     ndvi = image.select('NDVI')
#     lst = image.select('LST')
#     albedo = image.select('ALBEDO')
#     slope = image.select('SLOPE')
   
   
#     # ---- 1. Tekis yer maskasi (slope < 5°) ----
#     flat_mask = slope.lt(acfg['slope_max'])
#     valid = image.mask().reduce(ee.Reducer.allNonZero())

#     base_mask = flat_mask.And(valid)
    
#     try:
#         anchor_px = base_mask.reduceRegion(
#             reducer=ee.Reducer.count(),
#             geometry=roi,
#             scale=120,
#             maxPixels=1e9,
#             bestEffort=True
#         ).getInfo()

#         print(f"  🌾 Anchor cropland mask pixel count: {anchor_px}")
#     except Exception as e:
#         print(f"  ⚠️ Anchor cropland diagnostika xato: {e}")

#     if cfg.ANCHOR_USE_CROPLAND:
#         cropland_mask = get_anchor_cropland_mask(image, roi)
#         base_mask = base_mask.And(cropland_mask)

#     masked_ndvi = ndvi.updateMask(base_mask)
#     masked_lst = lst.updateMask(base_mask)

#     # ---- 2. Percentile hisoblash ----
#     ndvi_stats = masked_ndvi.reduceRegion(
#         reducer=ee.Reducer.percentile(
#             [acfg['hot_ndvi_percentile'], acfg['cold_ndvi_percentile']]
#         ),
#         geometry=roi,
#         scale=30,
#         maxPixels=1e9,
#         bestEffort=True
#     )

#     lst_stats = masked_lst.reduceRegion(
#         reducer=ee.Reducer.percentile(
#             [acfg['cold_lst_percentile'], acfg['hot_lst_percentile']]
#         ),
#         geometry=roi,
#         scale=30,
#         maxPixels=1e9,
#         bestEffort=True
#     )

#     ndvi_p_hot = ee.Number(ndvi_stats.get(
#         f'NDVI_p{acfg["hot_ndvi_percentile"]}'))
#     ndvi_p_cold = ee.Number(ndvi_stats.get(
#         f'NDVI_p{acfg["cold_ndvi_percentile"]}'))
#     lst_p_cold = ee.Number(lst_stats.get(
#         f'LST_p{acfg["cold_lst_percentile"]}'))
#     lst_p_hot = ee.Number(lst_stats.get(
#         f'LST_p{acfg["hot_lst_percentile"]}'))

#     # ---- Anchor maskasi bo'sh bo'lganda himoya (HLS/bulutli sahna) ----
#     # Qattiq shartlar (NDVI + LST + albedo) ba'zan 0 nomzod beradi →
#     # median null → ee.Number(null) butun grafni buzadi
#     # ("Number.subtract/multiply: left null"). Bo'sh bo'lsa, faqat LST
#     # percentil asosidagi zaxira maskaga o'tamiz (base_mask non-empty
#     # bo'lsa har doim non-empty).
#     def _ensure_nonempty(mask, fallback):
#         mask = mask.rename('M')
#         cnt = mask.reduceRegion(
#             reducer=ee.Reducer.sum(), geometry=roi, scale=120,
#             maxPixels=1e9, bestEffort=True).get('M')
#         cnt = ee.Number(ee.Algorithms.If(cnt, cnt, 0))
#         return ee.Image(ee.Algorithms.If(cnt.gt(0), mask, fallback.rename('M')))

#     # ---- 3. Cold pixel kandidatlar ----
#     cold_mask = (
#         base_mask
#         .And(ndvi.gte(ndvi_p_cold))
#         .And(lst.lte(lst_p_cold))
#         .And(albedo.lt(acfg['cold_albedo_max']))
#     )
#     cold_fallback = base_mask.And(lst.lte(lst_p_cold))
#     cold_mask = _ensure_nonempty(cold_mask, cold_fallback)

#     # Cold pixel — LST median (eng barqaror qiymat)
#     cold_lst = (lst.updateMask(cold_mask)
#                 .reduceRegion(
#                     reducer=ee.Reducer.median(),
#                     geometry=roi,
#                     scale=30,
#                     maxPixels=1e9,
#                     bestEffort=True
#                 ).get('LST'))
#     cold_lst = ee.Number(cold_lst)

#     # ---- 4. Hot pixel kandidatlar ----
#     hot_mask = (
#         base_mask
#         .And(ndvi.lte(ndvi_p_hot))
#         .And(lst.gte(lst_p_hot))
#         .And(albedo.gt(acfg['hot_albedo_min']))
#     )
#     hot_fallback = base_mask.And(lst.gte(lst_p_hot))
#     hot_mask = _ensure_nonempty(hot_mask, hot_fallback)

#     # Hot pixel — LST va (Q*-G₀) median
#     hot_stats = (image.select(['LST', 'RN_G0'])
#                  .updateMask(hot_mask)
#                  .reduceRegion(
#                      reducer=ee.Reducer.median(),
#                      geometry=roi,
#                      scale=30,
#                      maxPixels=1e9,
#                      bestEffort=True
#                  ))
#     hot_lst = ee.Number(hot_stats.get('LST'))
#     hot_rn_g0 = ee.Number(hot_stats.get('RN_G0'))

#     # ---- 5. Anchor ma'lumotlarni qaytarish ----
#     # hot_mask va cold_mask ham kerak — iteratsiyada hot pixel dagi
#     # rah qiymatini FAQAT hot piksellardan olish uchun.
#     # Bu oldingi bug edi: butun tasvir mediani olinayotgan edi.

#     anchors = {
#         'cold_lst': cold_lst,
#         'hot_lst': hot_lst,
#         'hot_rn_g0': hot_rn_g0,
#         'hot_mask': hot_mask,
#         'cold_mask': cold_mask,
#     }

#     return anchors

def _select_anchor_default(image, roi, cropland_mask=None):
    """
    Klassik persentil anchor tanlash — RASTER cropland mask bilan.

    cropland_mask : ee.Image yoki None
        1=cropland raster mask (updateMask uchun). Berilsa — anchor faqat
        ekin piksellaridan qidiriladi. reduceRegion HAR DOIM oddiy `roi`
        to'rtburchak ustida ishlaydi (murakkab vektor YO'Q → tez).
        None → butun roi (cropland cheklovisiz).
    """
    acfg = cfg.ANCHOR

    ndvi = image.select('NDVI')
    lst = image.select('LST')
    albedo = image.select('ALBEDO')
    slope = image.select('SLOPE')

    # ---- 1. Piksel VALIDLIGI — bulut, qism, slope ----
    flat_mask = slope.lt(acfg['slope_max'])
    valid = image.mask().reduce(ee.Reducer.allNonZero())
    base_flat = flat_mask.And(valid)

    # ---- 2. Cropland cheklovi — RASTER mask (geometriya emas!) ----
    if cropland_mask is not None:
        base_crop = base_flat.And(cropland_mask.gt(0))
    else:
        base_crop = base_flat

    # Shu sahnada cropland zonasida yetarli valid piksel bormi (bulut?)
    px = base_crop.rename('M').reduceRegion(
        reducer=ee.Reducer.sum(), geometry=roi, scale=120,
        maxPixels=1e9, bestEffort=True).get('M', 0)
    px = ee.Number(ee.Algorithms.If(px, px, 0))
    # <20 bo'lsa cropland cheklovini olib tashlaymiz (butun roi, shu sahna)
    base_mask = ee.Image(ee.Algorithms.If(px.gt(20), base_crop, base_flat))

    # reduceRegion geometriyasi HAR DOIM oddiy roi (tez)
    search_geom = roi

    masked_ndvi = ndvi.updateMask(base_mask)
    masked_lst = lst.updateMask(base_mask)

    # ---- 3. Percentile — roi ustida, scale=30 (original aniqlik) ----
    ndvi_stats = masked_ndvi.reduceRegion(
        reducer=ee.Reducer.percentile(
            [acfg['hot_ndvi_percentile'], acfg['cold_ndvi_percentile']]),
        geometry=search_geom, scale=30, maxPixels=1e9, bestEffort=True,
        tileScale=4)

    lst_stats = masked_lst.reduceRegion(
        reducer=ee.Reducer.percentile(
            [acfg['cold_lst_percentile'], acfg['hot_lst_percentile']]),
        geometry=search_geom, scale=30, maxPixels=1e9, bestEffort=True,
        tileScale=4)

    # Kalit yo'q (bo'sh zona) bo'lsa sentinel → mask bo'sh bo'ladi (crash emas).
    ndvi_p_hot = ee.Number(ndvi_stats.get(
        f'NDVI_p{acfg["hot_ndvi_percentile"]}', _LO))     # lte → bo'sh
    ndvi_p_cold = ee.Number(ndvi_stats.get(
        f'NDVI_p{acfg["cold_ndvi_percentile"]}', _HI))    # gte → bo'sh
    lst_p_cold = ee.Number(lst_stats.get(
        f'LST_p{acfg["cold_lst_percentile"]}', _LO))      # lte → bo'sh
    lst_p_hot = ee.Number(lst_stats.get(
        f'LST_p{acfg["hot_lst_percentile"]}', _HI))       # gte → bo'sh

    def _ensure_nonempty(mask, fallback):
        mask = mask.rename('M')
        cnt = mask.reduceRegion(
            reducer=ee.Reducer.sum(), geometry=search_geom, scale=120,
            maxPixels=1e9, bestEffort=True).get('M', 0)
        cnt = ee.Number(ee.Algorithms.If(cnt, cnt, 0))
        return ee.Image(ee.Algorithms.If(cnt.gt(0), mask, fallback.rename('M')))

    cold_mask = (base_mask.And(ndvi.gte(ndvi_p_cold))
                 .And(lst.lte(lst_p_cold))
                 .And(albedo.lt(acfg['cold_albedo_max'])))
    cold_fallback = base_mask.And(lst.lte(lst_p_cold))
    cold_mask = _ensure_nonempty(cold_mask, cold_fallback)

    cold_lst = ee.Number(lst.updateMask(cold_mask).reduceRegion(
        reducer=ee.Reducer.median(), geometry=search_geom, scale=30,
        maxPixels=1e9, bestEffort=True, tileScale=4).get('LST', -999))

    hot_mask = (base_mask.And(ndvi.lte(ndvi_p_hot))
                .And(lst.gte(lst_p_hot))
                .And(albedo.gt(acfg['hot_albedo_min'])))
    hot_fallback = base_mask.And(lst.gte(lst_p_hot))
    hot_mask = _ensure_nonempty(hot_mask, hot_fallback)

    hot_stats = image.select(['LST', 'RN_G0']).updateMask(hot_mask).reduceRegion(
        reducer=ee.Reducer.median(), geometry=search_geom, scale=30,
        maxPixels=1e9, bestEffort=True, tileScale=4)
    hot_lst = ee.Number(hot_stats.get('LST', -999))
    hot_rn_g0 = ee.Number(hot_stats.get('RN_G0', -999))

    # ---- YAKUNIY, HAQIQIY tekshiruv ----
    # LST har doim Kelvin (>200); sentinel -999 → valid=0 (crash emas, toza skip).
    anchors_valid = ee.Number(ee.Algorithms.If(
        cold_lst.gt(200).And(hot_lst.gt(200)), 1, 0))

    return {
        'cold_lst': cold_lst,
        'hot_lst': hot_lst,
        'hot_rn_g0': hot_rn_g0,
        'hot_mask': hot_mask,
        'cold_mask': cold_mask,
        'valid': anchors_valid, 
    }


# ==============================================================
# M5b: ANCHOR KASKAD (beton) — ko'p metodli, diagnostikali
# ==============================================================
#
# select_anchor_pixels() — DISPATCHER:
#   method='default' → yuqoridagi _select_anchor_default (o'zgarmagan).
#   aks holda → kaskad: tanlangan metod BIRINCHI, keyin qolganlari;
#   avval ekin zonasida, keyin butun ROI'da; hech biri chiqmasa —
#   'default' persentil fallback (KAFOLAT). Har qadam LOG qilinadi.
#
# Har metod (image, geom, base_mask) → (cold_mask, hot_mask) IMAGE qaytaradi.
# base_mask = tekis yer (slope<5°) VA valid (bulutsiz) piksellar.

_CANON_ORDER = ('cimec', 'plan_a', 'plan_b', 'pysebal')


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
    'topilmadi' deb keyingisiga o'tadi (crash emas).
    """
    v = d.get(key, sentinel)
    return ee.Number(ee.Algorithms.If(v, v, sentinel))


def _safe_num(d, key, default):
    """Dictionary'dan sonni null/yo'q-himoya bilan olish (default qiymatli)."""
    v = d.get(key, default)
    return ee.Number(ee.Algorithms.If(v, v, default))


# ---- METOD 1: CIMEC (strict, NDVI-guruhli LST persentili) ----
def _anchor_cimec(image, geom, base):
    ndvi = image.select('NDVI')
    ts = image.select('LST')
    alb = image.select('ALBEDO')

    # Cold: yuqori NDVI (p80) guruhida eng sovuq (p5..p40)
    # DIQQAT: bitta percentile so'ralsa kalit = band nomi ('NDVI'), '_p80' EMAS.
    nperc = ndvi.updateMask(base).reduceRegion(
        ee.Reducer.percentile([80]), geom, 30,
        maxPixels=1e9, bestEffort=True, tileScale=4)
    ndvi_p80 = _pn(nperc, 'NDVI', _HI)              # gte → yo'q/null bo'lsa bo'sh
    high_ndvi = base.And(ndvi.gte(ndvi_p80))
    tsg = ts.updateMask(high_ndvi).reduceRegion(
        ee.Reducer.percentile([5, 40]), geom, 30,
        maxPixels=1e9, bestEffort=True, tileScale=4)
    cold_lo = _pn(tsg, 'LST_p5', _HI)               # gte → bo'sh
    cold_hi = _pn(tsg, 'LST_p40', _LO)              # lte → bo'sh
    cold_mask = high_ndvi.And(ts.gte(cold_lo)).And(ts.lte(cold_hi))

    # Hot: past NDVI (p10, o'simlik bor lekin siyrak) guruhida eng issiq
    nperc2 = ndvi.updateMask(base).reduceRegion(
        ee.Reducer.percentile([10]), geom, 30,
        maxPixels=1e9, bestEffort=True, tileScale=4)
    ndvi_p10 = _pn(nperc2, 'NDVI', _LO)             # bitta percentile → kalit 'NDVI'
    low_ndvi = base.And(ndvi.lte(ndvi_p10)).And(ndvi.gt(0.02)).And(alb.gt(0.12))
    tsd = ts.updateMask(low_ndvi).reduceRegion(
        ee.Reducer.percentile([60, 95]), geom, 30,
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
        ee.Reducer.percentile([10, 95]), geom, 30,
        maxPixels=1e9, bestEffort=True, tileScale=4)
    ndvi_p95 = _pn(nperc, 'NDVI_p95', _HI)   # gte → yo'q bo'lsa bo'sh
    ndvi_p10 = _pn(nperc, 'NDVI_p10', _LO)   # lte → yo'q bo'lsa bo'sh

    tperc = ts.updateMask(base).reduceRegion(
        ee.Reducer.percentile([5, 15, 20, 80, 85, 95]), geom, 30,
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


# ---- METOD 4: pySEBAL (statistik, default qiymatli — eng bardoshli) ----
def _anchor_pysebal(image, geom, base):
    ndvi = image.select('NDVI')
    ts = image.select('LST')
    alb = image.select('ALBEDO')

    ns = ndvi.updateMask(base).reduceRegion(
        ee.Reducer.max().combine(ee.Reducer.stdDev(), sharedInputs=True),
        geom, 30, maxPixels=1e9, bestEffort=True, tileScale=4)
    ndvi_max = _safe_num(ns, 'NDVI_max', 0.7)
    ndvi_std = _safe_num(ns, 'NDVI_stdDev', 0.05)
    cold_veg = base.And(ndvi.gte(ndvi_max.subtract(ndvi_std.multiply(0.1))))
    cs = ts.updateMask(cold_veg).reduceRegion(
        ee.Reducer.mean().combine(ee.Reducer.stdDev(), sharedInputs=True),
        geom, 30, maxPixels=1e9, bestEffort=True, tileScale=4)
    cold_mean = _safe_num(cs, 'LST_mean', 295.0)
    cold_std = _safe_num(cs, 'LST_stdDev', 2.0)
    cold_mask = cold_veg.And(ts.lte(cold_mean.subtract(cold_std)))

    np_ = ndvi.updateMask(base).reduceRegion(
        ee.Reducer.percentile([10]), geom, 30,
        maxPixels=1e9, bestEffort=True, tileScale=4)
    ndvi_p10 = _safe_num(np_, 'NDVI', 0.1).max(0.05)   # bitta percentile → kalit 'NDVI'
    hot_ndvi = (base.And(ndvi.gte(ndvi_p10.multiply(0.5)))
                .And(ndvi.lte(ndvi_p10)).And(ndvi.gt(0.02)).And(alb.gt(0.12)))
    hs = ts.updateMask(hot_ndvi).reduceRegion(
        ee.Reducer.mean().combine(ee.Reducer.stdDev(), sharedInputs=True),
        geom, 30, maxPixels=1e9, bestEffort=True, tileScale=4)
    hot_mean = _safe_num(hs, 'LST_mean', 305.0)
    hot_std = _safe_num(hs, 'LST_stdDev', 2.0)
    hot_mask = hot_ndvi.And(ts.gte(hot_mean.add(hot_std)))
    return cold_mask, hot_mask


_ANCHOR_METHODS = {
    'cimec': _anchor_cimec,
    'plan_a': _anchor_plan_a,
    'plan_b': _anchor_plan_b,
    'pysebal': _anchor_pysebal,
}


def _cascade_order(method):
    """Tanlangan metod birinchi, qolganlari kanonik tartibda."""
    if method in _CANON_ORDER:
        return (method,) + tuple(m for m in _CANON_ORDER if m != method)
    return _CANON_ORDER   # 'cascade' yoki noma'lum → to'liq zanjir


def _finalize_anchor(image, geom, cold_mask, hot_mask, method, zone, verbose):
    """
    cold/hot mask'dan LST median'larni oladi, VALIDlikni bitta getInfo bilan
    client-side tekshiradi. Ikkalasi ham topilib, ΔT yetarli bo'lsa —
    anchor dict qaytaradi; aks holda None (keyingi metodga o'tiladi).
    """
    lst = image.select('LST')
    # mask BO'SH bo'lsa reduceRegion bo'sh dictionary qaytaradi → .get default'siz
    # crash beradi. Shuning uchun sentinel (-999) beramiz; keyin >-900 tekshiruvi.
    cold_lst = ee.Number(lst.updateMask(cold_mask).reduceRegion(
        ee.Reducer.median(), geom, 30, maxPixels=1e9, bestEffort=True).get('LST', -999))
    hot_stats = image.select(['LST', 'RN_G0']).updateMask(hot_mask).reduceRegion(
        ee.Reducer.median(), geom, 30, maxPixels=1e9, bestEffort=True)
    hot_lst = ee.Number(hot_stats.get('LST', -999))
    hot_rn_g0 = ee.Number(hot_stats.get('RN_G0', -999))

    probe = ee.List([
        ee.Algorithms.If(cold_lst, cold_lst, -999),
        ee.Algorithms.If(hot_lst, hot_lst, -999),
        ee.Algorithms.If(hot_rn_g0, hot_rn_g0, -999),
    ]).getInfo()
    c, h, hr = probe[0], probe[1], probe[2]

    min_dt = cfg.ANCHOR_CASCADE['min_dt']
    ok = (c is not None and h is not None and hr is not None
          and c > -900 and h > -900 and hr > -900 and (h - c) >= min_dt)

    if ok:
        if verbose:
            print(f"    ✅ Anchor topildi: metod={method}, zona={zone} | "
                  f"cold={c:.1f}K  hot={h:.1f}K  ΔT={h - c:.1f}K")
        return {
            'cold_lst': cold_lst, 'hot_lst': hot_lst, 'hot_rn_g0': hot_rn_g0,
            'hot_mask': hot_mask, 'cold_mask': cold_mask,
            'valid': ee.Number(1), 'method': method, 'zone': zone,
        }

    if verbose:
        reason = ('cold/hot bo\'sh' if (c <= -900 or h <= -900)
                  else f'ΔT={h - c:.1f}K < {min_dt}K')
        print(f"    ↪ metod={method} ({zone}) → topilmadi ({reason}), keyingisi…")
    return None


def select_anchor_pixels(image, roi, cropland_mask=None,
                         method='default', verbose=True):
    """
    Anchor tanlash DISPATCHER (beton kaskad).

    cropland_mask : ee.Image yoki None — 1=cropland RASTER mask (vektor EMAS).
      reduceRegion HAR DOIM oddiy `roi` to'rtburchak ustida ishlaydi;
      cropland cheklovi `base` maskaga updateMask orqali kiritiladi.

    method:
      'default' → klassik persentil + yumshoq fallback (eng tez).
      'cimec'|'plan_a'|'plan_b'|'pysebal' → shu metod birinchi, keyin
                  qolganlari; avval ekin zonasida (base∧cropland), so'ng ROI.
      'cascade' → cimec'dan boshlab to'liq zanjir.

    Kaskadda hech bir metod chiqmasa — 'default' fallback ishga tushadi.
    Har qadam va metod almashinuvi print qilinadi.
    """
    if method == 'default':
        return _select_anchor_default(image, roi, cropland_mask)

    base_flat = _base_mask(image)             # tekis + valid
    order = _cascade_order(method)

    # Zonalar: (nom, shu zona uchun base). reduceRegion geom = roi (tez).
    zones = []
    if cropland_mask is not None:
        zones.append(('cropland', base_flat.And(cropland_mask.gt(0))))
    zones.append(('ROI', base_flat))

    for zone_name, zbase in zones:
        for m in order:
            cold_mask, hot_mask = _ANCHOR_METHODS[m](image, roi, zbase)
            res = _finalize_anchor(image, roi, cold_mask, hot_mask,
                                   m, zone_name, verbose)
            if res is not None:
                return res

    if verbose:
        print("    ⚠️ Barcha metod bo'sh — 'default' persentil fallback")
    return _select_anchor_default(image, roi, cropland_mask)


# ==============================================================
# M6: WIND & MOMENTUM
# ==============================================================

def compute_friction_velocity(image):
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
    z0m = image.select('Z0M')

    z_ref = wcfg['z_ref_era5']       # 10m
    z_blend = wcfg['z_blending']     # 200m
    z0m_ws = wcfg['z0m_weather']     # 0.12m (grass)
    k = cfg.VON_KARMAN               # 0.41

    # 1. 10m → 200m extrapolyatsiya (neytral, log profile)
    u_200 = wind_10.multiply(
        ee.Number(z_blend / z0m_ws).log().divide(
            ee.Number(z_ref / z0m_ws).log()
        )
    ).rename('U_200')

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

    rah = ln(z₁/z₂) / (k × u*)

    z₁ = 2.0m  (yuqori integratsiya chegarasi)
    z₂ = 0.1m  (pastki integratsiya chegarasi)

    Bu faqat boshlang'ich qiymat — iteratsiyada ψh bilan tuzatiladi.
    """
    wcfg = cfg.WIND
    k = cfg.VON_KARMAN

    ustar = image.select('USTAR')

    ln_ratio = ee.Number(wcfg['z1'] / wcfg['z2']).log()

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
        x2 = max(1.0 - 16.0 * z1 / L, 0.001) ** 0.25
        psi_h2 = 2.0 * math.log((1.0 + x2 ** 2) / 2.0)
        x01 = max(1.0 - 16.0 * z2 / L, 0.001) ** 0.25
        psi_h01 = 2.0 * math.log((1.0 + x01 ** 2) / 2.0)
        psi_h = psi_h2 - psi_h01
    else:       # barqaror (L > 0) — z1 (Allen 2007)
        psi_m = -5.0 * z1 / L
        psi_h = (-5.0 * z1 / L) - (-5.0 * z2 / L)
    psi_m = max(min(psi_m, 10.0), -10.0)
    psi_h = max(min(psi_h, 10.0), -10.0)
    return psi_m, psi_h


def compute_sensible_heat_flux(image, anchors, roi):
    """
    Sezuvchan issiqlik oqimi H — iterativ hisoblash.
    Bastiaanssen (1998) original SEBAL yondashuvi (F.24-32).

    ASOSIY FARAZ (klassik SEBAL, o'zgarmagan):
      Cold pixel: δTa_cold = 0  (H_cold = 0 — yaxshi sug'orilgan
                   maydonda butun mavjud energiya ET'ga sarflanadi)
      Hot pixel:  δTa_hot = H_hot × rah_hot / (ρₐ × cₚ)
                   H_hot = Q* - G₀  (hot pikselda λE = 0)

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
      - Ta (hisoblangan havo harorati)ni ERA5 AIR_TEMP ± 15K bilan
        solishtirib, chetga chiqqan qiymatlarni tuzatish (QA)
      - H'ni fizik chegaraga cheklash: -100 ≤ H ≤ (Rn-G0)
        (λE ≥ 0 kafolati, L_MO'ga buzuq H kirishining oldini olish)

    Odatda 3-5 iteratsiyada stabillashadi (max_iter=8 — faqat
    xavfsizlik chegarasi).
    """
    cold_lst = anchors['cold_lst']
    hot_lst = anchors['hot_lst']
    hot_rn_g0 = anchors['hot_rn_g0']
    hot_mask = anchors['hot_mask']

    lst = image.select('LST')
    rho_air = image.select('RHO_AIR')
    u_200 = image.select('U_200')
    z0m = image.select('Z0M')
    rn_g0 = image.select('RN_G0')          # Rn - G0, H chegarasi uchun
    air_temp_era5 = image.select('AIR_TEMP')  # Ta sanity-check uchun

    wcfg = cfg.WIND
    k = cfg.VON_KARMAN
    g = cfg.GRAVITY
    cp = cfg.CP_AIR
    z_blend = wcfg['z_blending']
    z1 = wcfg['z1']
    z2 = wcfg['z2']

    max_iter = cfg.ITERATION['max_iter']
    min_iter = cfg.ITERATION['min_iter']
    tol_rel = cfg.ITERATION['tol_rel']   # 1% nisbiy konvergensiya

    # ==========================================================
    # HOT-PIKSEL SKALYARLARINI BIR MARTA OLISH (yagona getInfo)
    # ==========================================================
    # Iteratsiya faqat hot-piksel skalyar qiymatlari ustida boradi (klassik
    # SEBAL kalibratsiyasi). Butun rah(x,y) field'ni HAR iteratsiyada
    # baholash o'rniga — hot-piksel median kirishlarini BIR MARTA olamiz,
    # keyin (A) iteratsiya sof Python'da, server chaqiruvisiz ketadi.
    stats = ee.Dictionary({
        'u200': u_200.updateMask(hot_mask).reduceRegion(
            ee.Reducer.median(), roi, 30, maxPixels=1e9,
            bestEffort=True, tileScale=4).get('U_200', -999),
        'z0m': z0m.updateMask(hot_mask).reduceRegion(
            ee.Reducer.median(), roi, 30, maxPixels=1e9,
            bestEffort=True, tileScale=4).get('Z0M', -999),
        'rho': rho_air.updateMask(hot_mask).reduceRegion(
            ee.Reducer.median(), roi, 30, maxPixels=1e9,
            bestEffort=True, tileScale=4).get('RHO_AIR', -999),
        'hot_lst': hot_lst, 'cold_lst': cold_lst, 'hot_rn_g0': hot_rn_g0,
    }).getInfo()

    import math
    u200_h = stats['u200']
    z0m_h = max(stats['z0m'], cfg.ROUGHNESS['z0m_min'])   # log domeni himoyasi
    rho_h = stats['rho']
    hlst = stats['hot_lst']
    clst = stats['cold_lst']
    H_hot = stats['hot_rn_g0']

    # ==========================================================
    # (A) SKALYAR ITERATSIYA — sof Python (server chaqiruvi YO'Q).
    #     rah_hot ni o'z-o'ziga mos topib, har iteratsiya c4/c5 ni yozadi.
    #     Skalyar bo'lgani uchun bir zumda ishlaydi — graf o'smaydi.
    # ==========================================================
    ln_zb_z0m = math.log(z_blend / z0m_h)
    ln_z1_z2 = math.log(z1 / z2)

    ustar_h = max(k * u200_h / ln_zb_z0m, 0.02)          # neytral boshlang'ich
    rah_h = max(ln_z1_z2 / (k * ustar_h), 1.0)

    c4_list, c5_list, dta_list = [], [], []
    prev_dt = prev_rah = None
    prev_psi_m = prev_psi_h = prev_ustar = None
    converged_at = None

    for i in range(max_iter):
        # δTa_hot = H_hot·rah_hot/(ρ·cp);  H_hot=Q*-G₀ (hot pikselda λE=0)
        dta_hot = H_hot * rah_h / (rho_h * cp)
        c4 = dta_hot / (hlst - clst)     # chiziqli kalibratsiya
        c5 = -c4 * clst
        c4_list.append(c4)
        c5_list.append(c5)
        dta_list.append(dta_hot)

        # Konvergensiya (SEBAL Manual App.8): dT_hot va rah_hot stabillashishi.
        # NISBIY (1%): masshtabdan mustaqil (kichik/katta dT'ga bir xil mos).
        if (prev_dt is not None and (i + 1) >= min_iter
                and abs(dta_hot - prev_dt) < tol_rel * abs(dta_hot)
                and abs(rah_h - prev_rah) < tol_rel * abs(rah_h)):
            converged_at = i + 1
            print(f"  ✅ (A) Konvergensiya {i+1}-iteratsiyada: "
                  f"dT_hot={dta_hot:.4f} K, rah_hot={rah_h:.3f} s/m")
            break

        prev_dt, prev_rah = dta_hot, rah_h

        # Monin-Obukhov L (hot pikselda H=H_hot, u*=ustar_h)
        h_safe = H_hot if abs(H_hot) >= 1.0 else 1.0
        L_h = -rho_h * cp * ustar_h ** 3 * hlst / (k * g * h_safe)
        L_h = max(min(L_h, 1e6), -1e6)

        psi_m_c, psi_h_c = _stability_scalar(L_h, z_blend, z1, z2)

        # Dhungel et al. (2016) damping — ketma-ket ikki ψ (va u*) o'rtachasi.
        # DOI: 10.1117/1.JRS.10.026033 ("averaging the last two calculations
        # for the three psi terms" + "averaging the u* ...").
        if prev_psi_m is not None:
            psi_m = 0.5 * (prev_psi_m + psi_m_c)
            psi_h = 0.5 * (prev_psi_h + psi_h_c)
        else:
            psi_m, psi_h = psi_m_c, psi_h_c
        prev_psi_m, prev_psi_h = psi_m_c, psi_h_c

        ustar_c = max(k * u200_h / (ln_zb_z0m - psi_m), 0.02)
        if prev_ustar is not None:
            ustar_h = 0.5 * (prev_ustar + ustar_c)
        else:
            ustar_h = ustar_c
        prev_ustar = ustar_c

        rah_h = max((ln_z1_z2 - psi_h) / (k * ustar_h), 1.0)

    N_A = converged_at if converged_at is not None else max_iter
    if converged_at is None:
        print(f"  ⚠️ (A) {max_iter} iteratsiyada konvergent bo'lmadi — "
              f"eng so'nggi qiymat bilan davom etadi")

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

        # Har piksel δTa
        dta_raw = lst.multiply(c4_i).add(c5_i)

        # XAVFSIZLIK 1: [0, dta_hot] ± 20% margin (chegaralar — client skalyar)
        dt_lower = min(0.0, dta_hot_i)
        dt_upper = max(0.0, dta_hot_i)
        margin = (dt_upper - dt_lower) * 0.2
        dta = dta_raw.clamp(dt_lower - margin, dt_upper + margin).rename('DTA')

        # XAVFSIZLIK 2: Ta = T0 - dT, ERA5 AIR_TEMP ± 15K
        ta_img = lst.subtract(dta)
        ta_img = ta_img.where(ta_img.lt(air_temp_era5.subtract(15)),
                              air_temp_era5.subtract(15))
        ta_img = ta_img.where(ta_img.gt(air_temp_era5.add(15)),
                              air_temp_era5.add(15))
        dta = lst.subtract(ta_img).rename('DTA')

        # H = ρ·cp·δTa/rah  →  XAVFSIZLIK 3: -100 ≤ H ≤ Rn-G0
        h_raw = rho_air.multiply(cp).multiply(dta).divide(rah)
        h = h_raw.min(rn_g0).max(-100).rename('H')

        # Monin-Obukhov L
        h_safe = h.where(h.abs().lt(1.0), ee.Image(1.0))
        L_mo = (rho_air.multiply(cp).multiply(ustar.pow(3)).multiply(lst)
                .divide(ee.Image(k * g).multiply(h_safe))
                .multiply(-1).rename('L_MO'))
        L_mo = L_mo.clamp(-1e6, 1e6)

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

        rah = (ee.Image(z1 / z2).log().subtract(psi_h)
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
    fin = (image.select(['DTA', 'RAH', 'H']).updateMask(hot_mask)
           .reduceRegion(ee.Reducer.median(), roi, 100,
                         maxPixels=1e9, bestEffort=True, tileScale=4)).getInfo()

    def _fmt(x):
        return f"{x:.3f}" if isinstance(x, (int, float)) else str(x)
    print(f"  ✅ (B) Raster {N_A} qadam | hot: dT={_fmt(fin.get('DTA'))} K, "
          f"rah={_fmt(fin.get('RAH'))} s/m, H={_fmt(fin.get('H'))} W/m² "
          f"| N konvergent = {N_A}")

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
    # z_blend (200m) uchun x_200
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

    # z1 (2m) uchun x_2
    x_2 = (ee.Image(1.0)
           .subtract(ee.Image(16.0 * z1).divide(L_mo))
           .max(0.001)
           .pow(0.25))

    psi_h_2_unstable = x_2.pow(2).add(1).divide(2).log().multiply(2)

    # z2 (0.1m) uchun
    x_01 = (ee.Image(1.0)
            .subtract(ee.Image(16.0 * z2).divide(L_mo))
            .max(0.001)
            .pow(0.25))

    psi_h_01_unstable = x_01.pow(2).add(1).divide(2).log().multiply(2)

    # ψh = ψh(z1) - ψh(z2) — ikki balandlik orasidagi farq
    psi_h_unstable = psi_h_2_unstable.subtract(psi_h_01_unstable)

    # --- Barqaror (L > 0), Eq. 38-39 ---
    # MUHIM: Allen et al. (2007, ASCE) ga ko'ra, bandning nomi "200m" bo'lsa
    # ham, STABLE sharoitda formulada ATAYLAB z=2m ishlatiladi (200m emas),
    # chunki barqaror chegara qatlami juda yupqa va 200m ishlatilsa
    # raqamli beqarorlik (numerical instability) paydo bo'ladi.
    psi_m_200_stable = ee.Image(-5.0 * z1).divide(L_mo)   # z1 = 2.0m (config.WIND)
    psi_h_stable = (ee.Image(-5.0 * z1).divide(L_mo)
                    .subtract(ee.Image(-5.0 * z2).divide(L_mo)))

    # --- Shartli tanlash ---
    is_unstable = L_mo.lt(0)

    psi_m_200 = (psi_m_200_unstable.where(is_unstable.Not(), psi_m_200_stable)
                 .clamp(-10, 10))

    psi_h = (psi_h_unstable.where(is_unstable.Not(), psi_h_stable)
             .clamp(-10, 10))

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

    rn_g0_safe = rn_g0.max(10)

    evap_frac = (lambda_e.divide(rn_g0_safe)
                 .clamp(0, 1.0)
                 .rename('EVAP_FRAC'))

    return image.addBands(evap_frac)


# ==============================================================
# MAIN: Full energy balance
# ==============================================================

def compute_all(image, roi, cropland_mask=None, anchors=None,
                anchor_method='default'):
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

    Anchor pixel tanlash ROI kerak — shuning uchun
    bu funksiya map() ichida emas, alohida chaqiriladi.
    """
    # M6: Wind & momentum
    image = compute_friction_velocity(image)
    image = compute_rah_neutral(image)

    # M5: Anchor selection
    if anchors is None:
        anchors = select_anchor_pixels(image, roi, cropland_mask=cropland_mask,
                                       method=anchor_method)

    # M7: Sensible heat flux (iterativ)
    image = compute_sensible_heat_flux(image, anchors, roi)

    # M8: Latent heat flux
    image = compute_latent_heat_flux(image)
    image = compute_evaporative_fraction(image)

    return image

def get_anchor_cropland_mask(image, roi):
    """
    Anchor tanlash uchun cropland mask.
    Faqat ESA WorldCover class 40 — cropland.
    """
    proj = image.select('LST').projection()

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
