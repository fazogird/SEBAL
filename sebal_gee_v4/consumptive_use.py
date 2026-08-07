"""
SEBAL-GEE v4 — CONSUMPTIVE USE (faqat mode='SEBAL_Milliy')
==========================================================
Sug'orish suvi iste'moli (CUirr), effektiv yog'in (Prz) va net sug'orish talabi
(NIWR) — OpenET / ET Demands metodologiyasi (Allen et al. 1998 FAO-56;
USDA 1998 Curve Number).

    Prz   = P - Runoff - DeepPerc      (effektiv yog'in — ildiz zonasida qolgan)
    CUirr = ETa - Prz                  (sug'orishdan iste'mol qilingan suv)
    NIWR  = ETc - Prz                  (ETc = Kc_max·ETr — net talab)

Kunlik FAO-56 ildiz-zona suv balansi (server-side, oy kunlari bo'yicha iteratsiya):
    RO_i   = (P_i - 0.2S)² / (P_i + 0.8S),   S = 25400/CN - 254
    I_i    = P_i - RO_i
    Dr'    = Dr - I_i + ETa_i
    DP_i   = max(0, -Dr'),   Dr_new = clamp(Dr', 0, TAW)
    Prz_i  = I_i - DP_i

Manba tuproq/yog'in — GLOBAL (O'zbekistonga ham ishlaydi, empirik-ofsetsiz):
  - Yog'in P: CHIRPS DAILY (water_balance.CHIRPS)
  - θ_FC/θ_WP: Saxton-Rawls (2006), OpenLandMap sand/clay (RASTER)
  - ETa: SEBAL_Milliy kunlik ET (daily_et.daily_et_series)
  - ETr: ASCE-EWRI kunlik referens ET (daily_et.get_daily_etr24)
"""

import ee
from . import config as cfg
from . import water_balance as wb
from . import daily_et


# ==============================================================
# 1. TUPROQ SUV PARAMETRLARI (RASTER)
# ==============================================================

def _saxton_fc_wp_raster(sand, clay, om=2.0):
    """
    θ_FC (33 kPa) va θ_WP (1500 kPa) — Saxton & Rawls (2006) pedotransfer, RASTER.

    Kirish: sand, clay — OG'IRLIK % (ee.Image, OpenLandMap b0), om — organik modda %.
    Chiqish: (FC, WP) hajmiy nam [m³/m³] ee.Image. water_balance._saxton_fc_wp
    (point skalyar) ning AYNAN RASTER nusxasi.
    """
    S = sand.divide(100.0)
    C = clay.divide(100.0)
    OM = float(om)
    # θ1500 (WP)
    t15 = (S.multiply(-0.024).add(C.multiply(0.487)).add(0.006 * OM)
           .add(S.multiply(0.005 * OM)).subtract(C.multiply(0.013 * OM))
           .add(S.multiply(C).multiply(0.068)).add(0.031))
    wp = t15.add(t15.multiply(0.14).subtract(0.02))
    # θ33 (FC)
    t33 = (S.multiply(-0.251).add(C.multiply(0.195)).add(0.011 * OM)
           .add(S.multiply(0.006 * OM)).subtract(C.multiply(0.027 * OM))
           .add(S.multiply(C).multiply(0.452)).add(0.299))
    fc = t33.add(t33.pow(2).multiply(1.283).subtract(t33.multiply(0.374)).subtract(0.015))
    # fizik chegara (nofizik pedotransfer chiqishidan himoya) + WP < FC
    fc = fc.clamp(0.10, 0.50)
    wp = wp.clamp(0.02, 0.35).min(fc.subtract(0.03))
    return fc, wp


def soil_water_params(roi):
    """
    TAW (ildiz-zona jami mavjud suv, mm) va CN (Curve Number) RASTERlari.

    TAW = 1000·(FC - WP)·Zr.  CN gidrologik guruh: sand>50%->A, clay>40%->C, else B.
    """
    # clip YO'Q: tuproq global; CU extenti updateMask(ET) bilan aynan ET'ga tenglashadi
    # (clip(roi) qilsak CU viloyatga kesilib, ET'dan kichik shaklda chiqadi).
    sand = ee.Image(wb.SAND).select('b0')
    clay = ee.Image(wb.CLAY).select('b0')
    fc, wp = _saxton_fc_wp_raster(sand, clay)
    cu = cfg.CONSUMPTIVE_USE

    taw = (fc.subtract(wp).multiply(1000.0).multiply(cu['root_depth'])
           .max(1.0).rename('TAW'))

    cn = (ee.Image(cu['cn_b'])
          .where(sand.gt(50), cu['cn_a'])
          .where(clay.gt(40), cu['cn_c'])
          .rename('CN'))
    return taw, cn


# ==============================================================
# 2. EFFEKTIV YOG'IN (Prz) — kunlik FAO-56 + CN balans
# ==============================================================

def effective_precip_monthly(image_list, roi, year, month, mode='SEBAL_Milliy',
                             ref_type='alfalfa', utc_offset=0,
                             etr24_source='era5', sloping_terrain=False):
    """
    Oylik effektiv yog'in Prz (mm/oy) + qo'shimcha Runoff/DeepPerc rasterlari.

    Kunlik ildiz-zona suv balansi (rejimga mos kunlik ET bilan haydaladi).
    Returns: (PRZ, RUNOFF_MONTHLY, DEEPPERC_MONTHLY) — hammasi ee.Image (mm/oy).
    """
    et_list, days, month_start = daily_et.daily_et_series(
        image_list, roi, year, month, mode=mode, ref_type=ref_type,
        utc_offset=utc_offset, etr24_source=etr24_source,
        sloping_terrain=sloping_terrain)
    taw, cn = soil_water_params(roi)
    S = ee.Image(25400.0).divide(cn).subtract(254.0).max(1.0)   # potensial retention (mm)
    Ia = S.multiply(0.2)                                          # boshlang'ich yo'qotish
    cu = cfg.CONSUMPTIVE_USE

    init = (taw.multiply(cu['dr_init_frac']).rename('Dr')
            .addBands(ee.Image(0.0).rename('Prz'))
            .addBands(ee.Image(0.0).rename('RO'))
            .addBands(ee.Image(0.0).rename('DP')))

    def _step(off, acc):
        acc = ee.Image(acc)
        off = ee.Number(off)
        Dr = acc.select('Dr')
        d = month_start.advance(off, 'day')

        p_img = (ee.ImageCollection(wb.CHIRPS)
                 .filterDate(d, d.advance(1, 'day'))
                 .select('precipitation').first())
        # clip YO'Q (CHIRPS global) — extent updateMask(ET) bilan ET'ga tenglashadi
        P = ee.Image(ee.Algorithms.If(p_img, p_img, ee.Image(0.0))).unmask(0.0)

        eta = ee.Image(et_list.get(off))

        # USDA-SCS Curve Number runoff (P > Ia bo'lganda)
        ro = (P.subtract(Ia).max(0.0).pow(2)
              .divide(P.add(S.multiply(0.8)).max(0.01)))
        infil = P.subtract(ro)                       # infiltratsiya

        drp = Dr.subtract(infil).add(eta)            # yangilangan depletion
        dp = drp.multiply(-1.0).max(0.0)             # Dr<0 → chuqur perkolatsiya
        dr_new = drp.max(0.0).min(taw)
        prz_i = infil.subtract(dp)                   # effektiv yog'in (shu kun)

        return (dr_new.rename('Dr')
                .addBands(acc.select('Prz').add(prz_i).rename('Prz'))
                .addBands(acc.select('RO').add(ro).rename('RO'))
                .addBands(acc.select('DP').add(dp).rename('DP')))

    res = ee.Image(ee.List.sequence(0, days - 1).iterate(_step, init))
    return (res.select('Prz').max(0.0).rename('PRZ'),
            res.select('RO').rename('RUNOFF_MONTHLY'),
            res.select('DP').rename('DEEPPERC_MONTHLY'))


# ==============================================================
# 3. CUirr / NIWR
# ==============================================================

def _etr_monthly(image_list, roi, year, month, utc_offset=0, ref_type='alfalfa'):
    """
    Oylik referens ET (mm/oy) = kunlik ASCE-EWRI ETr yig'indisi.

    KUNLIK-TIMESTEP: ERA5 DAILY agregatidan (get_daily_era5_aggregate +
    RefETCalculator mode='daily') — soatlik-yig'indidan (24×) YENGILROQ, GEE
    "timed out" xavfini kamaytiradi. NIWR (coarse suv-menejment produkti) uchun
    kunlik-timestep aniqligi yetarli.
    """
    import calendar
    from . import ref_et
    days = calendar.monthrange(year, month)[1]
    month_start = ee.Date.fromYMD(year, month, 1)
    # ⚠️ TEZLASHTIRISH: DEM ni ~1km ga dag'allashtiramiz → ETr calc 30m emas, ~1km
    # da ketadi (31 kun × 36M piksel → ~34k). ETr fazoviy SILLIQ (ERA5 ~11km) va NIWR
    # baribir Prz (CHIRPS ~5km) bilan cheklangan → 1km yetarli. Eksportda 30m ga qayta.
    dem0 = ee.Image(image_list[0]).select('DEM')
    dem = dem0.reproject(dem0.projection().atScale(1000))
    calc = ref_et.RefETCalculator(ref_type=ref_type)

    def _etr(off):
        d = ee.Date(month_start.advance(ee.Number(off), 'day'))
        day = ee.Date(d.format('YYYY-MM-dd'))          # mahalliy kalendar kun
        met = ref_et.get_daily_era5_aggregate(day, roi, utc_offset=utc_offset)
        return calc.calculate(met, dem, mode='daily').select('ETr')

    return ee.ImageCollection(ee.List.sequence(0, days - 1).map(_etr)).sum()


def compute_all(et_monthly, image_list, roi, year, month, mode='SEBAL_Milliy',
                utc_offset=0, ref_type='alfalfa', etr24_source='era5',
                sloping_terrain=False, with_niwr=False):
    """
    CUirr + AW (+ Prz/Runoff/DeepPerc; with_niwr → NIWR/ETPOT) oylik rasterlari.

    Kirish: et_monthly — ET_MONTHLY (mm/oy, ETa — rejim natijasidan).
    with_niwr=False (default) — NIWR va uning OG'IR ETr'i UMUMAN hisoblanmaydi
      (asosiy tezlashuv). CUirr/AW faqat Prz suv balansiga tayanadi.
    Chiqish bandlari: CUIRR, AW, PRZ, RUNOFF_MONTHLY, DEEPPERC_MONTHLY
      (+ with_niwr: NIWR, ETPOT_MONTHLY).
    """
    prz, runoff, deepperc = effective_precip_monthly(
        image_list, roi, year, month, mode=mode, ref_type=ref_type,
        utc_offset=utc_offset, etr24_source=etr24_source,
        sloping_terrain=sloping_terrain)

    cuirr = et_monthly.subtract(prz).max(0.0).rename('CUIRR')

    # AW (Applied Water) = CUirr / Efficiency — quvur/kanaldan berilgan suv.
    # ⚠️ VAQTINCHA generik efficiency (butun tile bir xil); keyin optimallashtiriladi.
    eff = cfg.CONSUMPTIVE_USE['irrigation_efficiency']
    aw = cuirr.divide(eff).rename('AW')

    out = (cuirr.addBands(aw).addBands(prz)
           .addBands(runoff).addBands(deepperc))

    if with_niwr:
        # NIWR = ETc − Prz (ETc = Kc_max·ETr). ETr OG'IR — faqat kerak bo'lsa.
        etr_month = _etr_monthly(image_list, roi, year, month,
                                 utc_offset=utc_offset, ref_type=ref_type)
        etpot_month = (etr_month.multiply(cfg.CONSUMPTIVE_USE['kc_max'])
                       .rename('ETPOT_MONTHLY'))
        niwr = etpot_month.subtract(prz).max(0.0).rename('NIWR')
        out = out.addBands(niwr).addBands(etpot_month)

    # SHAPE moslash: CU bandlari ET (ETa) bilan AYNAN bir xil footprint bo'lsin.
    return out.updateMask(et_monthly.mask())
