"""
SEBAL-GEE v4 — CONSUMPTIVE USE (istalgan rejim; ETa — rejimning kunlik ET seriyasi)
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
  - θ_FC/θ_WP: Saxton-Rawls (2006), SoilGrids 2.0 sand/clay 0–5/5–15 sm (RASTER)
  - ETa: rejimning kunlik ET seriyasi (daily_et.daily_et_series; Kc_ETo → Kc model)
  - ETr: ASCE-EWRI kunlik referens ET (daily_et.get_daily_etr24)
"""

import ee
from . import config as cfg
from . import water_balance as wb
from . import daily_et


# ==============================================================
# 1. TUPROQ SUV PARAMETRLARI (RASTER)
# ==============================================================

# _saxton_fc_wp_raster (Saxton-Rawls 2006 pedotransfer) OLIB TASHLANDI (#95):
# FC/WP endi water_balance.soil_fc_wp_rew() — HiHydroSoil v2 (loyiha bo'yicha yagona
# tuproq manbai). Saxton AQSh tuproqlarida kalibrlangan va HiHydroSoil bilan farqi
# katta edi (WP +30 %, FC +9…+14 %).


def soil_water_params(roi):
    """
    TAW (ildiz-zona jami mavjud suv, mm) va CN (Curve Number) RASTERlari.

    TAW = 1000·(FC − WP)·Zr.
      • FC/WP — YAGONA manba (#95): HiHydroSoil v2 (water_balance.soil_fc_wp_rew),
        hot piksel balansi va Kc_ETo/AW bilan AYNI. Qum/gil (SoilGrids) faqat CN
        gidrologik guruhi uchun qoladi (tuproq gidravlikasi uchun emas).
      • Zr — cfg.CROP_ASSETS berilgan bo'lsa PER-CROP (crop_kc_table zr_max, FAO
        Table 22); aks holda cu['root_depth'] konstanta. (Oldin har doim 1.0 KONSTANTA
        edi → TAW noto'g'ri; endi ekin ildiz chuqurligiga qarab.)
    CN gidrologik guruh: sand>50%→A, clay>40%→C, else B.
    """
    # CN gidrologik guruhi uchun qum/gil (SoilGrids 2.0; g/kg → %, 0-10sm ≈ (0-5+5-15)/2)
    sgS = ee.Image('projects/soilgrids-isric/sand_mean')
    sgC = ee.Image('projects/soilgrids-isric/clay_mean')
    sand = sgS.select('sand_0-5cm_mean').add(sgS.select('sand_5-15cm_mean')).multiply(0.05)
    clay = sgC.select('clay_0-5cm_mean').add(sgC.select('clay_5-15cm_mean')).multiply(0.05)
    from . import water_balance as _wb
    fc, wp, _ = _wb.soil_fc_wp_rew()          # #95: FC/WP — HiHydroSoil (yagona manba)
    cu = cfg.CONSUMPTIVE_USE

    # PER-CROP ildiz chuqurligi Zr (crop asset) yoki konstanta fallback
    ca = getattr(cfg, 'CROP_ASSETS', None)
    if ca:
        from . import crop_kc_table as ckt
        crop = ee.ImageCollection([ee.Image(a) for a in ca]).mosaic()
        codes, zr, _p = ckt.zr_arrays()
        zr_img = crop.remap(codes, zr, cu['root_depth'])       # kod→zr_max (m)
    else:
        zr_img = ee.Image(cu['root_depth'])

    taw = (fc.subtract(wp).multiply(1000.0).multiply(zr_img)
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
    wb.check_chirps_month(year, month)          # yog'in yo'q kun → xato (soxta 0 emas)
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
        # Yog'in — CHIRPS kunlik rasmi (oy boshida check_chirps_month bilan HAR kun
        # borligi tekshirilgan; soxta 0 va unmask(0) YO'Q).
        P = ee.Image(p_img)

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
