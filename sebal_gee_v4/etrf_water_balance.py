"""
SEBAL-GEE v4 — Appendix I: KUNLIK ETrF TUZATISH (per-piksel suv balansi)
========================================================================
Tasumi (2003) Appendix I — faqat SEBAL_ID, `etrf_water_balance=True` da.

Standart usul (Eq 5.9) ETrF ni tasvirlar orasida BARQAROR ushlaydi. Bu modul
ETrF ni HAR KUNI yog'in (CHIRPS) namligiga qarab tuzatadi:

    ETrF_adj = ETrF_basal + Ke                     (I.1)
    Ke = Kr·(ETrF_max − ETrF_basal) ≤ few·ETrF_max (I.2)
    ETrF_max = max(1.05, ETrF_basal)               (I.4)
    few = 1 − fc                                    (I.3)
    De,i = De,i-1 − (P−RO) + E_i/few,  E_i=Ke·ETr   (I.7)  [faqat yog'in, sug'orish yo'q]
    Kr: De≤REW→1; De>REW→(TEW−De)/(TEW−REW)         (5.4)

Tasvir vaqtida ETrF → ETrF_basal + Ke ajratish (Initial Inputs, I.9-I.11):
  - ETrF_basal(LAI) = LAI–ETrF PASTKI O'RAM (LAI-bin p5 persentil).
  - Ke = min(ETrF−basal, few·ETrF_max); basal = ETrF−Ke; Kr = Ke/(ETrF_max−basal).
  - Boshlang'ich De = TEW − Kr·(TEW−REW);  Kr≈1 → De = 0.5·REW.

Tuproq (TEW/REW): OpenLandMap USDA tekstura → Table 5.1 (water_balance._SOIL).
Ze=0.10, RO=0, sug'orish YO'Q (kitobdagidek — ma'lumot yo'q).
"""

import ee
from . import config as cfg
from . import ref_et
from . import daily_et
from .water_balance import _SOIL, _SOIL_DEFAULT, TEXTURE, CHIRPS

ETRF_MIN = 0.15          # quruq yalang'och tuproq ETrF (Eq I.12)
ETRF_MAX_FLOOR = 1.05    # yog'indan keyingi maks ETrF (Eq I.4)
LAI_BIN = 0.5            # LAI bin qadami
LAI_MAX = 6.0
BASAL_PCTL = 5           # pastki o'ram uchun persentil


# ==============================================================
# TUPROQ RASTERLARI (per-piksel TEW/REW)
# ==============================================================

def _soil_rasters(ze=0.10):
    """OpenLandMap USDA tekstura → per-piksel FC, WP, REW, TEW (Table 5.1)."""
    tex = ee.Image(TEXTURE).select('b0')
    classes = list(range(1, 13))
    fc = tex.remap(classes, [_SOIL[c][0] for c in classes], _SOIL_DEFAULT[0]).toFloat()
    wp = tex.remap(classes, [_SOIL[c][1] for c in classes], _SOIL_DEFAULT[1]).toFloat()
    rew = tex.remap(classes, [_SOIL[c][2] for c in classes], _SOIL_DEFAULT[2]).toFloat()
    tew = fc.subtract(wp.multiply(0.5)).multiply(1000.0 * ze)
    tew = tew.max(rew.add(1.0))     # TEW > REW kafolati
    return rew.rename('REW'), tew.rename('TEW')


# ==============================================================
# fc / few (Eq I.12, I.3)
# ==============================================================

def _fc_few(image):
    """
    fc (o'simlik qoplami) Eq I.12 dan; few = 1 − fc (yog'indan keyin).
    h — o'rtacha o'simlik balandligi (NDVI'dan). few ∈ [0.01, 1].
    """
    ndvi = image.select('NDVI')
    # o'simlik balandligi h (m) — NDVI'dan (ekin ~0..2 m)
    h = ndvi.subtract(0.15).divide(0.70).clamp(0, 1).multiply(2.0).max(0.05)
    # basal kerak — bu funksiya partition ichida basal bilan chaqiriladi;
    # bu yerda faqat h qaytaramiz, fc basal bilan hisoblanadi.
    return h


def _fc_from_basal(basal, h):
    """fc = ((basal−ETRF_MIN)/(ETRF_MAX−ETRF_MIN))^(1/(1+0.5h))  (Eq I.12).
    ee.Image.constant ISHLATILMAYDI (1° proyeksiya → null)."""
    etrf_max = basal.max(ETRF_MAX_FLOOR)
    ratio = (basal.subtract(ETRF_MIN)
             .divide(etrf_max.subtract(ETRF_MIN)).clamp(0.0, 1.0))
    expo = h.multiply(0.5).add(1.0).pow(-1)        # 1/(1+0.5h)
    fc = ratio.pow(expo).clamp(0.0, 1.0)
    few = fc.multiply(-1).add(1.0).clamp(0.01, 1.0)
    return fc, few


# ==============================================================
# ETrF_basal EGRI (LAI–ETrF pastki o'ram, per-piksel)
# ==============================================================

def etrf_basal_raster(image, roi):
    """
    ETrF_basal(LAI) — LAI-bin bo'yicha ETRF_INST past persentili (p5) = pastki
    o'ram. Monoton o'suvchi qilib, per-piksel LAI'ga interpolyatsiya qilinadi.
    """
    lai = image.select('LAI')
    etrf = image.select('ETRF_INST')
    laibin = lai.divide(LAI_BIN).floor().toInt().rename('BIN')

    grouped = (etrf.addBands(laibin).reduceRegion(
        reducer=ee.Reducer.percentile([BASAL_PCTL]).group(groupField=1, groupName='bin'),
        geometry=roi, scale=60, maxPixels=1e9, bestEffort=True, tileScale=4
    ).get('groups')).getInfo()

    # bin index → p5 qiymat
    pkey = f'p{BASAL_PCTL}'
    by_bin = {int(g['bin']): g.get(pkey) for g in (grouped or [])
              if g.get('bin') is not None and g.get(pkey) is not None}

    n_bins = int(LAI_MAX / LAI_BIN) + 1
    vals = []
    last = ETRF_MIN
    for b in range(n_bins):
        v = by_bin.get(b, None)
        if v is None:
            v = last
        v = max(ETRF_MIN, min(v, ETRF_MAX_FLOOR))
        v = max(v, last)          # monoton o'suvchi (pastki o'ram)
        vals.append(v); last = v

    # Per-piksel basal = kesma-kesma chiziqli interpolyatsiya
    # (LAI proyeksiyasidan boshlaymiz — ee.Image.constant 1° default proyeksiyasi
    #  30m reduceRegion bilan mos kelmaydi → null)
    basal = lai.multiply(0).add(vals[0]).toFloat()
    for b in range(n_bins - 1):
        lo_lai = b * LAI_BIN
        hi_lai = (b + 1) * LAI_BIN
        frac = lai.subtract(lo_lai).divide(LAI_BIN).clamp(0, 1)
        seg = frac.multiply(vals[b + 1] - vals[b]).add(vals[b])
        basal = basal.where(lai.gte(lo_lai).And(lai.lt(hi_lai)), seg)
    basal = basal.where(lai.gte((n_bins - 1) * LAI_BIN), vals[-1])
    return basal.clamp(ETRF_MIN, ETRF_MAX_FLOOR).rename('ETRF_BASAL')


# ==============================================================
# TASVIR VAQTIDA AJRATISH (I.9-I.11)
# ==============================================================

def partition(image, roi, rew, tew):
    """
    ETRF_INST → {basal, etrf_max, few, De_init} per-piksel (Initial Inputs).
    """
    etrf = image.select('ETRF_INST')
    basal0 = etrf_basal_raster(image, roi)          # I.1-step1 (pastki o'ram)
    h = _fc_few(image)
    _, few = _fc_from_basal(basal0, h)
    etrf_max = basal0.max(ETRF_MAX_FLOOR)           # I.4

    # Ke boshlang'ich (I.9) + cheklov few·ETrF_max (I.2)
    ke = etrf.subtract(basal0).max(0).min(few.multiply(etrf_max))
    # basal qayta (I: ETrF_basal = ETrF − Ke)
    basal = etrf.subtract(ke).clamp(ETRF_MIN, ETRF_MAX_FLOOR)
    etrf_max = basal.max(ETRF_MAX_FLOOR)

    # Kr = Ke/(ETrF_max − basal)  (I.10)
    denom = etrf_max.subtract(basal).max(1e-3)
    kr = ke.divide(denom).clamp(0, 1)

    # Boshlang'ich De (I.11): De = TEW − Kr·(TEW−REW); Kr≈1 → 0.5·REW
    de = tew.subtract(kr.multiply(tew.subtract(rew)))
    de = de.where(kr.gte(0.999), rew.multiply(0.5))
    de = de.max(0).min(tew)

    return {'basal': basal.rename('ETRF_BASAL'),
            'etrf_max': etrf_max.rename('ETRF_MAX'),
            'few': few.rename('FEW'),
            'de_init': de.rename('DE_INIT')}


# ==============================================================
# OYLIK ET — kunlik tuzatilgan ETrF (forward sweep)
# ==============================================================

def _kr(de, rew, tew):
    """Kr = De≤REW→1; else (TEW−De)/(TEW−REW)."""
    kr2 = tew.subtract(de).divide(tew.subtract(rew).max(1e-3)).clamp(0, 1)
    return kr2.where(de.lte(rew), 1.0)


def monthly_et_adjusted(image_list, roi, year, month, dem, ze=0.10,
                        ref_type='alfalfa', utc_offset=0, etr24_source='era5'):
    """
    Oylik ET — Appendix I (kunlik ETrF tuzatish). Har tasvir uchun partition,
    kunma-kun De ni CHIRPS yog'in bilan yangilab, ETrF_adj·ETr24 yig'indisi.
    """
    import calendar
    days_in_month = calendar.monthrange(year, month)[1]
    month_start = ee.Date.fromYMD(year, month, 1)

    rew, tew = _soil_rasters(ze)
    chirps = ee.ImageCollection(CHIRPS)

    # Sanalar (client-side) — partition FAQAT shu oyga tegishli sahnalar uchun
    # (aks holda mavsumdagi barcha sahna uchun getInfo → juda sekin)
    all_ms = ee.List([ee.Image(im).get('system:time_start')
                      for im in image_list]).getInfo()
    all_day = [int(t // 86400000) for t in all_ms]
    d_lo = _day_index(year, month, 1) - 20
    d_hi = _day_index(year, month, days_in_month) + 20
    keep = [i for i, d in enumerate(all_day) if d_lo <= d <= d_hi]
    if not keep:      # oyga yaqin sahna yo'q → eng yaqinini olamiz
        mid = _day_index(year, month, max(1, days_in_month // 2))
        keep = [min(range(len(all_day)), key=lambda i: abs(all_day[i] - mid))]
    image_list = [image_list[i] for i in keep]
    dates_day = [all_day[i] for i in keep]

    parts = [partition(ee.Image(im), roi, rew, tew) for im in image_list]

    # Forward sweep — Python sikli, ee image zanjiri (getInfo yo'q)
    cur = 0
    de = parts[0]['de_init']
    et_days = []   # kunlik ET rasterlari (oxirida ImageCollection.sum)

    for off in range(days_in_month):
        day = month_start.advance(off, 'day')
        # Governing tasvir: shu kunda tasvir bo'lsa unga o'tamiz + De reset
        # (client-side kun indeksi bilan solishtiramiz — getInfo YO'Q)
        this_day = _day_index(year, month, off + 1)
        for idx, dd in enumerate(dates_day):
            if dd == this_day:
                cur = idx
                de = parts[idx]['de_init']

        p = parts[cur]
        basal, emax, few = p['basal'], p['etrf_max'], p['few']

        etr24 = daily_et.get_daily_etr24(day, roi, dem, ref_type=ref_type,
                                         utc_offset=utc_offset,
                                         source=etr24_source)
        pr = (chirps.filterDate(day, day.advance(1, 'day')).sum()
              .select('precipitation').rename('P'))
        pr = pr.unmask(0)

        kr = _kr(de, rew, tew)
        ke = kr.multiply(emax.subtract(basal)).max(0).min(few.multiply(emax))
        etrf_adj = basal.add(ke)
        et_day = etrf_adj.multiply(etr24).max(0)
        et_days.append(et_day)

        # De yangilash (I.7): De = De + Ke·ETr/few − P, [0, TEW]
        de = (de.add(ke.multiply(etr24).divide(few)).subtract(pr)
              .max(0)).min(tew)

    et_monthly = ee.ImageCollection(et_days).sum().rename('ET_MONTHLY').set(
        'year', year).set('month', month).set(
        'days_in_month', days_in_month).set('n_landsat_scenes', len(image_list))
    return et_monthly


def _day_index(year, month, day):
    """UTC kun indeksi (1970-01-01 dan)."""
    from datetime import date
    return (date(year, month, day) - date(1970, 1, 1)).days
