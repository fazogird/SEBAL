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


# ==============================================================
# TILE-DARAJASIDA CROPLAND ZONASI — bir marta hisoblanadi
# ==============================================================

def _landcover_mask(classes):
    """ESA WorldCover'dan berilgan klasslar uchun 0/1 mask (masklamagan)."""
    wc = ee.ImageCollection('ESA/WorldCover/v200').first().select('Map')
    m = wc.eq(classes[0])
    for c in classes[1:]:
        m = m.Or(wc.eq(c))
    return m


def compute_tile_anchor_zones(tile_roi, min_pixel_count=20):
    """
    ESA WorldCover'dan COLD va HOT anchor RASTER zonalarini ajratadi —
    TILE uchun BIR MARTA (klassik SEBAL: cold va hot AYRIM land-cover).

      cold = cfg.ANCHOR_LANDCOVER['cold']  (40 Cropland) — sug'orilgan, nam
      hot  = cfg.ANCHOR_LANDCOVER['hot']   (60 Bare + 20 Shrub) — doim quruq

    MUHIM: hot cropland'dan EMAS — to'liq sug'orilgan mavsumda (iyul-sentyabr)
    cropland ichidagi "eng issiq" piksel ham transpiratsiya qiladi (lambdaE!=0)
    -> dT_hot oshadi -> ET past baholanadi (kuzatilgan +44% iyul biasining sababi).

    Returns
    -------
    (cold_mask, hot_mask) : (ee.Image yoki None, ee.Image yoki None)
        Har biri selfMask (1=zona, qolgani masked). Shu zonada
        <min_pixel_count piksel bo'lsa -> None (chaqiruvchi ROI'ga tushadi).
    """
    cold_r = _landcover_mask(cfg.ANCHOR_LANDCOVER['cold'])
    hot_r = _landcover_mask(cfg.ANCHOR_LANDCOVER['hot'])

    counts = ee.Dictionary({
        'cold': cold_r.reduceRegion(
            ee.Reducer.sum(), tile_roi, 100, maxPixels=1e10,
            bestEffort=True).get('Map', 0),
        'hot': hot_r.reduceRegion(
            ee.Reducer.sum(), tile_roi, 100, maxPixels=1e10,
            bestEffort=True).get('Map', 0),
    }).getInfo()
    cold_px = counts.get('cold') or 0
    hot_px = counts.get('hot') or 0

    print(f"  Cold(cropland {cfg.ANCHOR_LANDCOVER['cold']}) px: {cold_px:.0f}"
          f"  |  Hot(bare+shrub {cfg.ANCHOR_LANDCOVER['hot']}) px: {hot_px:.0f}")

    cold_mask = (cold_r.selfMask().rename('COLD_LC')
                 if cold_px >= min_pixel_count else None)
    hot_mask = (hot_r.selfMask().rename('HOT_LC')
                if hot_px >= min_pixel_count else None)
    if cold_mask is None:
        print(f"  ! Cold zona <{min_pixel_count} px -> cold cheklovsiz (ROI)")
    if hot_mask is None:
        print(f"  ! Hot zona <{min_pixel_count} px -> hot cheklovsiz (ROI)")

    return cold_mask, hot_mask


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

def _select_anchor_default(image, roi, cold_lc=None, hot_lc=None,
                           anchor_mode='median_anchor'):
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

    # ---- 2. AYRIM zonalar: cold=cropland_lc, hot=bare+shrub_lc (raster) ----
    def _zone_base(lc):
        if lc is None:
            return base_flat
        b = base_flat.And(lc.gt(0))
        px = ee.Number(b.rename('M').reduceRegion(
            ee.Reducer.sum(), roi, 120, maxPixels=1e9,
            bestEffort=True).get('M', 0))
        px = ee.Number(ee.Algorithms.If(px, px, 0))
        # <20 valid piksel (bulut) bo'lsa shu sahnada cheklovsiz (butun roi)
        return ee.Image(ee.Algorithms.If(px.gt(20), b, base_flat))

    cold_base = _zone_base(cold_lc)
    hot_base = _zone_base(hot_lc)
    search_geom = roi   # reduceRegion HAR DOIM oddiy roi (tez)

    # ---- 3. Percentile — cold cold_base'dan, hot hot_base'dan (scale=30) ----
    # DIQQAT: bitta percentile so'ralsa kalit = band nomi ('NDVI'/'LST').
    cold_np = ndvi.updateMask(cold_base).reduceRegion(
        ee.Reducer.percentile([acfg['cold_ndvi_percentile']]),
        search_geom, 30, maxPixels=1e9, bestEffort=True, tileScale=4)
    cold_tp = lst.updateMask(cold_base).reduceRegion(
        ee.Reducer.percentile([acfg['cold_lst_percentile']]),
        search_geom, 30, maxPixels=1e9, bestEffort=True, tileScale=4)
    hot_np = ndvi.updateMask(hot_base).reduceRegion(
        ee.Reducer.percentile([acfg['hot_ndvi_percentile']]),
        search_geom, 30, maxPixels=1e9, bestEffort=True, tileScale=4)
    hot_tp = lst.updateMask(hot_base).reduceRegion(
        ee.Reducer.percentile([acfg['hot_lst_percentile']]),
        search_geom, 30, maxPixels=1e9, bestEffort=True, tileScale=4)

    ndvi_p_cold = ee.Number(cold_np.get('NDVI', _HI))   # gte -> yo'q bo'lsa bo'sh
    lst_p_cold = ee.Number(cold_tp.get('LST', _LO))     # lte -> bo'sh
    ndvi_p_hot = ee.Number(hot_np.get('NDVI', _LO))     # lte -> bo'sh
    lst_p_hot = ee.Number(hot_tp.get('LST', _HI))       # gte -> bo'sh

    def _ensure_nonempty(mask, fallback):
        mask = mask.rename('M')
        cnt = mask.reduceRegion(
            reducer=ee.Reducer.sum(), geometry=search_geom, scale=120,
            maxPixels=1e9, bestEffort=True).get('M', 0)
        cnt = ee.Number(ee.Algorithms.If(cnt, cnt, 0))
        return ee.Image(ee.Algorithms.If(cnt.gt(0), mask, fallback.rename('M')))

    # Cold — cold_base (cropland) ichida: yuqori NDVI + past LST
    cold_mask = (cold_base.And(ndvi.gte(ndvi_p_cold))
                 .And(lst.lte(lst_p_cold))
                 .And(albedo.lt(acfg['cold_albedo_max'])))
    cold_fallback = cold_base.And(lst.lte(lst_p_cold))
    cold_mask = _ensure_nonempty(cold_mask, cold_fallback)

    # Hot — hot_base (bare+shrub) ichida: past NDVI + yuqori LST
    hot_mask = (hot_base.And(ndvi.lte(ndvi_p_hot))
                .And(lst.gte(lst_p_hot))
                .And(albedo.gt(acfg['hot_albedo_min'])))
    hot_fallback = hot_base.And(lst.gte(lst_p_hot))
    hot_mask = _ensure_nonempty(hot_mask, hot_fallback)

    # cold/hot skalyar — median (default) yoki bitta ekstremal piksel
    cold_lst, cold_rn_g0, hot_lst, hot_rn_g0 = _reduce_anchor_values(
        image, search_geom, cold_mask, hot_mask, anchor_mode)

    # ---- YAKUNIY, HAQIQIY tekshiruv ----
    # LST har doim Kelvin (>200); hot_rn_g0 fizik jihatdan musbat (yuzlab W/m²).
    # sentinel/null (-999 yoki masked) → valid=0 (crash emas, toza skip).
    # (point rejimda eng issiq piksel RN_G0-masked bo'lsa hot_rn_g0 null
    #  bo'lishi mumkin — shu yerda ushlanadi; _finalize_anchor'da allaqachon bor.)
    anchors_valid = ee.Number(ee.Algorithms.If(
        cold_lst.gt(200).And(hot_lst.gt(200)).And(hot_rn_g0.gt(-900)), 1, 0))

    return {
        'cold_lst': cold_lst,
        'hot_lst': hot_lst,
        'hot_rn_g0': hot_rn_g0,
        'cold_rn_g0': cold_rn_g0,   # SEBAL_ID: cold piksel H_cp uchun
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


def _reduce_anchor_values(image, geom, cold_mask, hot_mask,
                          anchor_mode='median_anchor'):
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
    """
    lst = image.select('LST')
    rn_g0 = image.select('RN_G0')
    if anchor_mode == 'point_anchor':
        # cold = eng SOVUQ (min LST) piksel; uning Rn−G₀ AYNI o'sha pikseldan
        # (min(2): 'min'=LST, 'min1'=Rn−G₀). RN_G0-valid pikselларга cheklanadi.
        cold_stats = (image.select(['LST', 'RN_G0'])
                      .updateMask(cold_mask).updateMask(rn_g0.mask())
                      .reduceRegion(ee.Reducer.min(2), geom, 30, maxPixels=1e9,
                                    bestEffort=True, tileScale=4))
        cold_lst = ee.Number(cold_stats.get('min', -999))
        cold_rn_g0 = ee.Number(cold_stats.get('min1', -999))
        # DIQQAT: max(2) absolyut eng issiq LST pikselni oladi va agar o'sha
        # pikselda RN_G0 masked bo'lsa 'max1'=null qaytaradi (test bilan
        # tasdiqlangan). Shuning uchun avval RN_G0-VALID pikselларga cheklaymiz —
        # shunda eng issiq RN_G0-valid piksel olinadi, hot_rn_g0 null BO'LMAYDI
        # (izchil juft). Umuman valid piksel bo'lmasa → key yo'q → sentinel -999.
        hot_stats = (image.select(['LST', 'RN_G0'])
                     .updateMask(hot_mask).updateMask(rn_g0.mask())
                     .reduceRegion(ee.Reducer.max(2), geom, 30, maxPixels=1e9,
                                   bestEffort=True, tileScale=4))
        hot_lst = ee.Number(hot_stats.get('max', -999))       # eng issiq LST
        hot_rn_g0 = ee.Number(hot_stats.get('max1', -999))    # o'sha pikselning Rn−G₀
    else:  # 'median_anchor' (default — hozirgi bilan aynan bir xil natija)
        cold_stats = image.select(['LST', 'RN_G0']).updateMask(cold_mask).reduceRegion(
            ee.Reducer.median(), geom, 30, maxPixels=1e9,
            bestEffort=True, tileScale=4)
        cold_lst = ee.Number(cold_stats.get('LST', -999))
        cold_rn_g0 = ee.Number(cold_stats.get('RN_G0', -999))   # SEBAL_ID: cold H uchun
        hot_stats = image.select(['LST', 'RN_G0']).updateMask(hot_mask).reduceRegion(
            ee.Reducer.median(), geom, 30, maxPixels=1e9,
            bestEffort=True, tileScale=4)
        hot_lst = ee.Number(hot_stats.get('LST', -999))
        hot_rn_g0 = ee.Number(hot_stats.get('RN_G0', -999))
    return cold_lst, cold_rn_g0, hot_lst, hot_rn_g0


def _finalize_anchor(image, geom, cold_mask, hot_mask, method, zone, verbose,
                     anchor_mode='median_anchor'):
    """
    cold/hot mask'dan anchor qiymatlarini (_reduce_anchor_values — median yoki
    ekstremal point) oladi, VALIDlikni bitta getInfo bilan client-side
    tekshiradi. Ikkalasi ham topilib, ΔT yetarli bo'lsa — anchor dict qaytaradi;
    aks holda None (keyingi metodga o'tiladi).
    """
    # cold/hot skalyar — median (default) yoki bitta ekstremal piksel.
    # Bo'sh mask → sentinel -999; keyin >-900 tekshiruvi.
    cold_lst, cold_rn_g0, hot_lst, hot_rn_g0 = _reduce_anchor_values(
        image, geom, cold_mask, hot_mask, anchor_mode)

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
            'cold_rn_g0': cold_rn_g0,   # SEBAL_ID: cold piksel H_cp uchun
            'hot_mask': hot_mask, 'cold_mask': cold_mask,
            'valid': ee.Number(1), 'method': method, 'zone': zone,
        }

    if verbose:
        reason = ('cold/hot bo\'sh' if (c <= -900 or h <= -900)
                  else f'ΔT={h - c:.1f}K < {min_dt}K')
        print(f"    ↪ metod={method} ({zone}) → topilmadi ({reason}), keyingisi…")
    return None


def select_anchor_pixels(image, roi, cold_mask=None, hot_mask=None,
                         method='default', verbose=True,
                         anchor_mode='median_anchor'):
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
        return _select_anchor_default(image, roi, cold_mask, hot_mask, anchor_mode)

    base_flat = _base_mask(image)             # tekis + valid
    order = _cascade_order(method)

    # AYRIM zonalar: cold=cropland, hot=bare+shrub (updateMask base'ga kiritiladi).
    cold_base = (base_flat.And(cold_mask.gt(0))
                 if cold_mask is not None else base_flat)
    hot_base = (base_flat.And(hot_mask.gt(0))
                if hot_mask is not None else base_flat)

    # 1) Land-cover zonalari: cold_mask cold_base'dan, hot_mask hot_base'dan.
    #    Metod ikki marta chaqiriladi — keraksiz yarmi (lazy) baholanmaydi.
    for m in order:
        cm, _ = _ANCHOR_METHODS[m](image, roi, cold_base)
        _, hm = _ANCHOR_METHODS[m](image, roi, hot_base)
        res = _finalize_anchor(image, roi, cm, hm, m, 'lc', verbose, anchor_mode)
        if res is not None:
            return res

    # 2) ROI (cheklovsiz) — bulutli kunlarda zona bo'sh bo'lsa zaxira.
    for m in order:
        cm, hm = _ANCHOR_METHODS[m](image, roi, base_flat)
        res = _finalize_anchor(image, roi, cm, hm, m, 'ROI', verbose, anchor_mode)
        if res is not None:
            return res

    if verbose:
        print("    ! Barcha metod bo'sh — 'default' persentil fallback")
    return _select_anchor_default(image, roi, cold_mask, hot_mask, anchor_mode)


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

    rah = ln(z2_rah/z1) / (k × u*)   [SEBAL_B: z1=0.1m, z2_rah=0.2m → ln(2)]

    DIQQAT: rah uchun z2_rah=0.2m; stability ψ uchun ALOHIDA z2=2.0m (boshqa).

    Bu faqat boshlang'ich qiymat — iteratsiyada ψh bilan tuzatiladi.
    """
    wcfg = cfg.WIND
    k = cfg.VON_KARMAN

    ustar = image.select('USTAR')

    ln_ratio = ee.Number(wcfg['z2_rah'] / wcfg['z1']).log()   # ln(0.2/0.1)=ln(2)

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
                               lambda_et_cold=0.0, lambda_et_hot=0.0):
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
    cold_mask = anchors['cold_mask']
    cold_rn_g0 = anchors.get('cold_rn_g0', hot_rn_g0)   # SEBAL_ID: cold H_cp uchun
    is_id = (mode == 'SEBAL_ID')

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
    z1 = wcfg['z1']            # past balandlik (rah + stability)
    z2_rah = wcfg['z2_rah']    # rah LOG hadi (0.2m)
    z2 = wcfg['z2']            # STABILITY ψ yuqori balandligi (2.0m)

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
    stats_d = {
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
    }
    if is_id:
        # SEBAL_ID: cold piksel rah_cp uchun cold-mask skalyarlari + cold Rn−G₀
        stats_d.update({
            'u200_c': u_200.updateMask(cold_mask).reduceRegion(
                ee.Reducer.median(), roi, 30, maxPixels=1e9,
                bestEffort=True, tileScale=4).get('U_200', -999),
            'z0m_c': z0m.updateMask(cold_mask).reduceRegion(
                ee.Reducer.median(), roi, 30, maxPixels=1e9,
                bestEffort=True, tileScale=4).get('Z0M', -999),
            'rho_c': rho_air.updateMask(cold_mask).reduceRegion(
                ee.Reducer.median(), roi, 30, maxPixels=1e9,
                bestEffort=True, tileScale=4).get('RHO_AIR', -999),
            'cold_rn_g0': cold_rn_g0,
        })
    stats = ee.Dictionary(stats_d).getInfo()

    import math
    u200_h = stats['u200']
    z0m_h = max(stats['z0m'], cfg.ROUGHNESS['z0m_min'])   # log domeni himoyasi
    rho_h = stats['rho']
    hlst = stats['hot_lst']
    clst = stats['cold_lst']
    # H_hot = Rn−G₀ − λET_hot (SEBAL_B: λET_hot=0 → H_hot=Rn−G₀, o'zgarmagan)
    H_hot = stats['hot_rn_g0'] - lambda_et_hot

    # SEBAL_ID: cold piksel skalyarlari + H_cold = Rn−G₀_cp − λET_cp
    if is_id:
        u200_c = stats['u200_c']
        z0m_c = max(stats['z0m_c'], cfg.ROUGHNESS['z0m_min'])
        rho_c = stats['rho_c']
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
    ln_z2_z1 = math.log(z2_rah / z1)   # rah log hadi: ln(0.2/0.1)=ln(2)

    ustar_h = max(k * u200_h / ln_zb_z0m, 0.02)          # neytral boshlang'ich
    rah_h = max(ln_z2_z1 / (k * ustar_h), 1.0)

    # SEBAL_ID: cold piksel parallel iteratsiyasi (δTa_cold ≠ 0)
    if is_id:
        ln_zb_z0m_cold = math.log(z_blend / z0m_c)
        ustar_cold = max(k * u200_c / ln_zb_z0m_cold, 0.02)
        rah_cold = max(ln_z2_z1 / (k * ustar_cold), 1.0)
        prev_psi_m_cold = prev_psi_h_cold = prev_ustar_cold = None

    c4_list, c5_list, dta_list, dtac_list = [], [], [], []
    prev_dt = prev_rah = None
    prev_psi_m = prev_psi_h = prev_ustar = None
    converged_at = None

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
        if (prev_dt is not None and (i + 1) >= min_iter
                and abs(dta_hot - prev_dt) < tol_rel * abs(dta_hot)
                and abs(rah_h - prev_rah) < tol_rel * abs(rah_h)):
            converged_at = i + 1
            print(f"  ✅ (A) Konvergensiya {i+1}-iteratsiyada: "
                  f"dT_hot={dta_hot:.4f} K, rah_hot={rah_h:.3f} s/m"
                  + (f", dT_cold={dta_cold:.4f} K" if is_id else ""))
            break

        prev_dt, prev_rah = dta_hot, rah_h

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
        # SEBAL_B: pastki uch = 0 (dTa_cold=0); SEBAL_ID: dTa_cold (nolmas)
        dta_cold_i = dtac_list[i] if is_id else 0.0

        # Har piksel δTa
        dta_raw = lst.multiply(c4_i).add(c5_i)

        # XAVFSIZLIK 1: [dTa_cold, dTa_hot] ± 20% margin (chegaralar — client skalyar)
        dt_lower = min(dta_cold_i, dta_hot_i)
        dt_upper = max(dta_cold_i, dta_hot_i)
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

def compute_all(image, roi, cold_mask=None, hot_mask=None, anchors=None,
                anchor_method='default', anchor_mode='median_anchor',
                mode='SEBAL_B', etrf_hot=None,
                sloping_terrain=False, z_ws=0.0):
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
        anchors = select_anchor_pixels(image, roi, cold_mask=cold_mask,
                                       hot_mask=hot_mask, method=anchor_method,
                                       anchor_mode=anchor_mode)

    # ---- SEBAL_ID: instant alfalfa ETr → cold/hot λET skalyarlari ----
    lambda_et_cold = lambda_et_hot = 0.0
    if mode == 'SEBAL_ID':
        from . import water_balance
        image = ref_et.compute_instant_etr(image)     # ETR_INST band (mm/soat)
        LAMBDA = 2.45e6                                 # bug'lanish yashirin issiqligi [J/kg]
        cm = anchors['cold_mask']; hm = anchors['hot_mask']
        # Hot piksel suv balansi → ETrF_hot (0 = to'liq quruq hot; klassik SEBAL)
        if etrf_hot is None:
            etrf_hot = water_balance.hot_pixel_etrf(image, roi, hm)
        etr = image.select('ETR_INST')
        vals = ee.Dictionary({
            'etr_c': etr.updateMask(cm).reduceRegion(
                ee.Reducer.median(), roi, 100, maxPixels=1e9,
                bestEffort=True, tileScale=4).get('ETR_INST', 0),
            'etr_h': etr.updateMask(hm).reduceRegion(
                ee.Reducer.median(), roi, 100, maxPixels=1e9,
                bestEffort=True, tileScale=4).get('ETR_INST', 0),
        }).getInfo()
        etr_c = vals['etr_c'] or 0.0
        etr_h = vals['etr_h'] or 0.0
        # λET_cp = 1.05·ETr; λET_hp = ETrF_hot·ETr  (W/m² = mm/soat · λ / 3600)
        lambda_et_cold = 1.05 * etr_c * LAMBDA / 3600.0
        lambda_et_hot = etrf_hot * etr_h * LAMBDA / 3600.0

    # M7: Sensible heat flux (iterativ)
    image = compute_sensible_heat_flux(image, anchors, roi, mode=mode,
                                       lambda_et_cold=lambda_et_cold,
                                       lambda_et_hot=lambda_et_hot)

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
