# -*- coding: utf-8 -*-
"""
ILDIZ-ZONA SUV BALANSI — GEE RASTER (per-piksel, oylik). AWnet ni water-balansdan
(ΣInet — sug'orish-rejali) hisoblaydi. root_zone_balance.py (skalyar, 5/5 test)
mantig'ining AYNAN GEE porti.

Kunlik (birlashgan iterate):
  • ETa_day = (Kcb + Ke)·ETo   — Kc modeli (per-crop, senescence, topsoil De balansi)
  • Root-zona:  x = Dr + ETa − (P − RO) − CR;  x<0→DP=−x,Dr_bef=0; else DP=0,Dr_bef=x
                RAW=p·TAW;  Dr_bef≥RAW → Inet=Dr_bef, Dr→0 (sug'or); else Inet=0
  CR = 0 (kapillyar ko'tarilish — hozircha; sizot dataseti keyin).

Chiqish (OYLIK, mm raster):
  AWNET_SIM, AWGROSS_SIM(=/eff), AVAILABLE_WATER(=TAW−Dr), DP_MONTHLY,
  N_IRRIG (sug'orish soni), TAW, ET_MONTHLY.
CUirr/AW(eski, consumptive_use) TEGILMAYDI — bu ALOHIDA, water-balans AW.
"""
import calendar
import ee

from . import config as cfg
from . import daily_et
from . import water_balance as wb
from . import consumptive_use as cu
from . import crop_kc_table as ckt
from .ndvi_kc import _ndvi_interp

CR = 0.0        # kapillyar ko'tarilish (hozircha 0)


def compute_awnet(image_list, roi, year, month, utc_offset=0,
                  etr24_source='era5', crop_assets=None, dr_init_frac=0.0,
                  dr_init_img=None, start_at_raw=False):
    """
    Oylik water-balans AW (mm rasterlar). crop_assets None → cfg.CROP_ASSETS.
    Boshlang'ich Dr (prioritet):
      1) dr_init_img — oldingi OY oxiridagi Dr rasteri (mavsumiy-uzluksiz; ⚠️ oylar
         ustma-ust qo'yilib grafik "too complex" bo'lishi mumkin — ehtiyot bilan).
      2) dr_init_frac — Dr = frac·TAW (test/spin-up uchun).
      3) start_at_raw (DEFAULT) — Dr = RAW (sug'orish chegarasi). Bunda har OY
         MUSTAQIL hisoblanadi (kompoundingsiz, batch-barqaror) va AW = o'sha oyning
         SOF SUG'ORISH TALABI (≈ ET_oy − effektiv_yomg'in_oy) — viloyat suv-hisobi uchun.
    Chiqishda DR_END bandi bor (ixtiyoriy keyingi oyga uzatish uchun; eksport qilinmaydi).
    """
    if crop_assets is None:
        crop_assets = getattr(cfg, 'CROP_ASSETS', None)
    cfg.CROP_ASSETS = crop_assets     # soil_water_params per-crop Zr ni shundan o'qiydi
    kc = cfg.MILLIY_KC
    days = calendar.monthrange(year, month)[1]
    month_start = ee.Date.fromYMD(year, month, 1)
    ndvi_coll = ee.ImageCollection(image_list).select('NDVI')
    dem = ee.Image(image_list[0]).select('DEM')
    eff = float(cfg.CONSUMPTIVE_USE['irrigation_efficiency'])

    # --- Topsoil TEW/REW (Ke uchun) — SoilGrids 2.0 + Saxton ---
    ze = 0.10
    sgS = ee.Image('projects/soilgrids-isric/sand_mean')
    sgC = ee.Image('projects/soilgrids-isric/clay_mean')
    sand = sgS.select('sand_0-5cm_mean').add(sgS.select('sand_5-15cm_mean')).multiply(0.05)
    clay = sgC.select('clay_0-5cm_mean').add(sgC.select('clay_5-15cm_mean')).multiply(0.05)
    fc, wp = cu._saxton_fc_wp_raster(sand, clay)
    TEW = fc.subtract(wp.multiply(0.5)).multiply(1000.0 * ze).max(1.0)
    REW = clay.multiply(0.15).add(2.0).clamp(2.0, 11.0).min(TEW)

    # --- Root-zona TAW (per-crop Zr) + CN (RO uchun) ---
    TAW, CN = cu.soil_water_params(roi)
    S = ee.Image(25400.0).divide(CN).subtract(254.0).max(1.0)
    Ia = S.multiply(0.2)

    # --- Kc koeffitsientlar (per-crop yoki bitta cotton) + RAW (p·TAW) ---
    KCMAX = float(kc['kc_max']); KE_SCALE = float(kc['ke_scale'])
    NB = float(kc['ndvi_bare']); NF = float(kc['ndvi_full'])
    PER_CROP = bool(crop_assets)
    if PER_CROP:
        crop = ee.ImageCollection([ee.Image(a) for a in crop_assets]).mosaic()
        codes, kmax, kend, slen, son = ckt.coeff_arrays()
        KCBMAX = crop.remap(codes, kmax, 0.0)
        KEND = crop.remap(codes, kend, 0.5)
        SLEN = crop.remap(codes, slen, 60.0)
        SON = crop.remap(codes, son, 0.0)
        cds, _zr, pv = ckt.zr_arrays()
        RAW = crop.remap(cds, pv, 0.5).multiply(TAW)
        CROP_MASK = crop.gt(0)
        NB = float(ckt.NDVI_BARE); NF = float(ckt.NDVI_FULL)
        KCMAX = float(ckt.KC_MAX); KE_SCALE = float(ckt.KE_SCALE)
        A = B = KCB_MAX = SEN_LEN = KCB_END = None; SEN_ON = False
    else:
        A = float(kc['kcb_a']); B = float(kc['kcb_b']); KCB_MAX = float(kc['kcb_max'])
        SEN_ON = bool(kc.get('senescence', False))
        SEN_LEN = float(kc.get('sen_len_days', 60.0))
        KCB_END = float(kc.get('kcb_end_frac', 0.45))
        RAW = ee.Image(float(cfg.CONSUMPTIVE_USE.get('depletion_frac', 0.5))).multiply(TAW)
        CROP_MASK = ee.Image(1)

    # --- Senescence: cho'qqi NDVI vaqti ---
    def _add_t(im):
        im = ee.Image(im)
        return im.select('NDVI').toFloat().addBands(
            ee.Image.constant(ee.Number(im.get('system:time_start'))).toFloat().rename('t'))
    t_peak = (ee.ImageCollection([_add_t(im) for im in image_list])
              .qualityMosaic('NDVI').select('t'))

    # --- Boshlang'ich Dr (prioritet: img → frac → RAW) ---
    if dr_init_img is not None:
        Dr0 = ee.Image(dr_init_img).unmask(RAW).min(TAW).max(0.0).rename('Dr')
    elif dr_init_frac is not None:
        Dr0 = TAW.multiply(float(dr_init_frac)).rename('Dr')
    else:                                    # DEFAULT: RAW dan → oylik sug'orish talabi
        Dr0 = RAW.min(TAW).max(0.0).rename('Dr')

    # --- Birlashgan kunlik iterate: De (topsoil), Dr (root), ET, INET, DP, NIRR ---
    init = (ee.Image(TEW).rename('De')
            .addBands(Dr0)
            .addBands(ee.Image(0.0).rename('ET'))
            .addBands(ee.Image(0.0).rename('INET'))
            .addBands(ee.Image(0.0).rename('DP'))
            .addBands(ee.Image(0.0).rename('NIRR')))

    def _step(off, acc):
        acc = ee.Image(acc); off = ee.Number(off)
        De = acc.select('De'); Dr = acc.select('Dr')
        d = month_start.advance(off, 'day')

        ndvi = _ndvi_interp(ndvi_coll, d)
        days_after = (ee.Image.constant(d.millis()).subtract(t_peak)
                      .divide(86400000.0).max(0.0))
        if PER_CROP:
            fcn = ndvi.subtract(NB).divide(NF - NB).clamp(0.0, 1.0)
            kcb = KCBMAX.multiply(fcn)
            sen = ee.Image(1.0).subtract(
                ee.Image(1.0).subtract(KEND).multiply(days_after.divide(SLEN).min(1.0)))
            sen = sen.where(SON.lt(0.5), 1.0)
            kcb = kcb.multiply(sen)
        else:
            kcb = ndvi.multiply(A).add(B).clamp(0.0, KCB_MAX)
            if SEN_ON:
                sen = ee.Image(1.0).subtract(
                    ee.Image(1.0 - KCB_END).multiply(days_after.divide(SEN_LEN).min(1.0)))
                kcb = kcb.multiply(sen)
        fcov = ndvi.subtract(NB).divide(NF - NB).clamp(0.0, 1.0)
        few = ee.Image(1.0).subtract(fcov)

        eto = (daily_et.get_daily_etr24(d, roi, dem, ref_type=kc['ref_type'],
                                        utc_offset=utc_offset, source=etr24_source)
               .rename('ETO'))
        p_img = (ee.ImageCollection(wb.CHIRPS).filterDate(d, d.advance(1, 'day'))
                 .select('precipitation').first())
        P = ee.Image(ee.Algorithms.If(p_img, p_img, ee.Image(0.0))).unmask(0.0)

        # Ke — topsoil De balansi
        De2 = De.subtract(P).max(0.0)
        Kr = (ee.Image(1.0).where(De2.gt(REW),
              TEW.subtract(De2).divide(TEW.subtract(REW))).clamp(0.0, 1.0))
        ke = (Kr.multiply(ee.Image(KCMAX).subtract(kcb))
              .min(few.multiply(KCMAX)).max(0.0).multiply(KE_SCALE))
        E = ke.multiply(eto); T = kcb.multiply(eto)
        eta_day = T.add(E)
        De_new = De2.add(E).min(TEW).rename('De')

        # ROOT-ZONA balans (skalyar bilan AYNAN bir xil)
        RO = (P.subtract(Ia).max(0.0).pow(2)
              .divide(P.add(S.multiply(0.8)).max(0.01)))
        x = Dr.add(eta_day).subtract(P.subtract(RO)).subtract(CR)
        dp = x.multiply(-1.0).max(0.0)
        dr_before = x.max(0.0)
        fire = dr_before.gte(RAW)                       # 1 = sug'orish yonadi
        inet = dr_before.multiply(fire)
        dr_end = dr_before.multiply(fire.Not()).min(TAW).rename('Dr')

        return (De_new.addBands(dr_end)
                .addBands(acc.select('ET').add(eta_day).rename('ET'))
                .addBands(acc.select('INET').add(inet).rename('INET'))
                .addBands(acc.select('DP').add(dp).rename('DP'))
                .addBands(acc.select('NIRR').add(fire).rename('NIRR')))

    res = ee.Image(ee.List.sequence(0, days - 1).iterate(_step, init))
    awnet = res.select('INET').max(0.0).rename('AW')          # sof sug'orish (water-balans)
    out = (awnet
           .addBands(awnet.divide(eff).rename('AW_Eff'))       # yalpi (efficiency bilan)
           .addBands(TAW.subtract(res.select('Dr')).max(0.0).rename('AVAILABLE_WATER'))
           .addBands(res.select('DP').rename('DP_MONTHLY'))
           .addBands(res.select('NIRR').rename('N_IRRIG'))
           .addBands(TAW.rename('TAW'))
           .addBands(res.select('ET').max(0.0).rename('ET_MONTHLY'))
           .addBands(res.select('Dr').rename('DR_END')))   # keyingi oyga uzatish
    if PER_CROP:
        out = out.updateMask(CROP_MASK)
    return out.set('year', year).set('month', month).set('days_in_month', days)
