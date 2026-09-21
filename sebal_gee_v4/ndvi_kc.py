# -*- coding: utf-8 -*-
"""
SEBAL_Milliy_Kc — NDVI-langan FAO-56 QO'SH koeffitsient (Kcb + Ke) upscaling.

Oylik ET energiya-balans SOLAR_FRAC dan EMAS, quyidagicha quriladi (anchor'ga
bog'liq EMAS — shu sabab barqaror):

    ET_kun = (Kcb(NDVI) + Ke(topsoil suv balansi)) × ETo_kun          [FAO-56]
      Kcb  = clamp(a·NDVI + b, 0, kcb_max)          — kanopiy transpiratsiya
      fc   = clamp((NDVI-bare)/(full-bare), 0, 1)    — kanopiy qoplami
      few  = 1 − fc                                  — ochiq/ho'l tuproq ulushi
      Ke   = clamp(Kr·(Kcmax−Kcb), 0, few·Kcmax)·ke_scale
      Kr   = 1 (De≤REW) yoki (TEW−De)/(TEW−REW)      — tuproq quruqlik omili
    De — kunlik topsoil depletion (CHIRPS yog'in bilan ho'llanadi).

Kalibratsiya (Bushland lizimetr 2021 oylik, proto_ndvi_kc.py): R²=0.85, MBE≈0,
RMSE=25.2 — OpenET Ensemble bilan teng. Koeffitsientlar cfg.MILLIY_KC da.

NDVI Landsat sahnalardan (image_list, 'NDVI' band) kunlik LINEER interpolyatsiya.
ETo — grass referens (get_daily_etr24 ref_type='grass'); Bushland=GRIDMET, boshqa
hudud=ERA5. SEBAL energiya balansi ISHLATILMAYDI (faqat NDVI kerak).
"""
import calendar
import ee

from . import config as cfg
from . import daily_et
from . import water_balance as wb


def _ndvi_interp(coll, date):
    """
    NDVI — HAR PIKSEL uchun vaqt bo'yicha eng yaqin YAROQLI oldingi/keyingi sahna
    orasida LINEER interpolyatsiya; bir tomon bo'sh (oralig'dan tashqari yoki piksel u
    tomonda doim bulutli) → mavjud tomon qiymati (ushlab turadi).
    Oldin TASVIR darajasida (before.first()/after.first()): o'sha sahnada bulutli piksel
    shu kuni NDVI'siz qolardi va kunlik iterate'da maska butun OY oxirigacha saqlanardi
    (oylik ET/AW o'sha pikselda bo'sh). Ikkala sahna ham yaroqli pikselda natija AYNAN
    oldingidek (bir xil vaqt og'irligi).
    """
    t = ee.Number(ee.Date(date).millis())

    def with_t(im):
        nd = ee.Image(im).select('NDVI')
        tt = (ee.Image.constant(ee.Image(im).get('system:time_start')).toDouble()
              .updateMask(nd.mask()).rename('t'))
        return nd.addBands(tt)

    sc = coll.map(with_t)
    before = sc.filter(ee.Filter.lte('system:time_start', t))
    after = sc.filter(ee.Filter.gte('system:time_start', t))
    z = ee.Image.constant(0).updateMask(ee.Image.constant(0))
    empty = z.rename('NDVI').addBands(z.rename('t'))
    b = ee.Image(ee.Algorithms.If(before.size().gt(0), before.qualityMosaic('t'), empty))
    a = ee.Image(ee.Algorithms.If(
        after.size().gt(0),
        after.map(lambda im: im.addBands(im.select('t').multiply(-1).rename('nt')))
             .qualityMosaic('nt'),
        empty))
    bv, bt = b.select('NDVI'), b.select('t')
    av, at = a.select('NDVI'), a.select('t')
    tdi = ee.Image.constant(t).toDouble()               # ee.Number − Image mumkin emas
    w = tdi.subtract(bt).divide(at.subtract(bt).max(1)).clamp(0, 1)
    out = bv.multiply(ee.Image(1).subtract(w)).add(av.multiply(w))
    out = out.unmask(bv).unmask(av)                     # bir tomonlama — mavjud tomon
    proj = ee.Image(coll.first()).select('NDVI').projection()
    return out.rename('NDVI').setDefaultProjection(proj)


def _kc_model(image_list, roi, year, month, utc_offset=0, etr24_source='era5',
              crop_assets=None):
    """
    Kc modelining umumiy sozlamasi va BIR KUNLIK qadami — oylik ET (compute_monthly_et_kc)
    va kunlik seriya (daily_et_series_kc → CUirr/Prz) AYNI qadamni ishlatadi.
    Qaytaradi: dict(days, month_start, TEW, day_step, crop_mask) —
      day_step(d, De) → (De_new, T, E)  [mm].
    """
    kc = cfg.MILLIY_KC
    if crop_assets is None:                      # main.run cfg.CROP_ASSETS orqali beradi
        crop_assets = getattr(cfg, 'CROP_ASSETS', None)
    days = calendar.monthrange(year, month)[1]
    month_start = ee.Date.fromYMD(year, month, 1)
    wb.check_chirps_month(year, month)          # yog'in yo'q kun → xato (soxta 0 emas)
    ndvi_coll = ee.ImageCollection(image_list).select('NDVI')
    dem = ee.Image(image_list[0]).select('DEM')

    # TEW/REW — PER-PIKSEL (bitta universal qiymat EMAS): SoilGrids 2.0 qum/gil
    # (global, O'zbekiston ham) → Saxton-Rawls FC/WP → topsoil bug'lanish qatlami.
    #   TEW = 1000·(FC − 0.5·WP)·Ze  (FAO-56 Eq.7.1, Ze=0.10 m)
    #   REW = 0.15·loy% + 2 (2…11 mm; gil ko'p → REW yuqori).
    from . import consumptive_use as _cu
    _ze = 0.10
    # Tuproq: SoilGrids 2.0 (ISRIC, 2020, 250m, global — O'zbekiston ham).
    # OpenLandMap(2018)dan yangi/aniqroq. Topsoil 0-10sm ≈ (0-5 + 5-15)/2. g/kg → % (/10).
    _sgS = ee.Image('projects/soilgrids-isric/sand_mean')
    _sgC = ee.Image('projects/soilgrids-isric/clay_mean')
    _sand = (_sgS.select('sand_0-5cm_mean').add(_sgS.select('sand_5-15cm_mean'))
             .multiply(0.05))                    # (a+b)/2/10 = *0.05  → %
    _clay = (_sgC.select('clay_0-5cm_mean').add(_sgC.select('clay_5-15cm_mean'))
             .multiply(0.05))
    _fc, _wp = _cu._saxton_fc_wp_raster(_sand, _clay)
    # ─────────────────────────────────────────────────────────────────────────
    # 🔖 KELAJAK OPTIMIZATSIYA (eslatma — hozir ishlatilmaydi, aniqlik uchun keyin):
    #   1) SHO'RLANISH: O'zbekiston (Orol bo'yi) sho'r tuproqda osmotik stress ET'ni
    #      pasaytiradi. Dataset: "Global Soil Salinity Maps (1986-2016)". Keyin Kcb/ET
    #      ga sho'rlanish-stress omili qo'shsak — sho'r hududlarда aniqlik oshadi.
    #   2) HiHydroSoil v2.0 (250m, 2020, global): FC/WP/Ksat ni TO'G'RIDAN-TO'G'RI
    #      beradi (Saxton pedotransfersiz). Agar AW (applied water) yoki ildiz-zona
    #      suv balansi uchun aniq FC/WP kerak bo'lsa — SoilGrids+Saxton o'rniga/bilan
    #      shu yerdan olamiz. Manba: gee-community-catalog → HiHydroSoil v2.0.
    # ─────────────────────────────────────────────────────────────────────────
    TEW = _fc.subtract(_wp.multiply(0.5)).multiply(1000.0 * _ze).max(1.0)   # ee.Image, mm
    REW = _clay.multiply(0.15).add(2.0).clamp(2.0, 11.0).min(TEW)           # ee.Image, mm
    KCMAX = float(kc['kc_max']); KE_SCALE = float(kc['ke_scale'])
    A = float(kc['kcb_a']); B = float(kc['kcb_b']); KCB_MAX = float(kc['kcb_max'])
    NB = float(kc['ndvi_bare']); NF = float(kc['ndvi_full'])
    SEN_ON = bool(kc.get('senescence', False))
    SEN_LEN = float(kc.get('sen_len_days', 60.0))
    KCB_END = float(kc.get('kcb_end_frac', 0.45))

    # ---- PER-CROP: crop-code raster(lar) → remap kod→koeffitsient (har piksel) ----
    #   Kcb = kcb_max · clamp((NDVI−NB)/(NF−NB),0,1)  [SIMS/FAO, per-crop kcb_max]
    #   senescence per-piksel (sen_len, kcb_end); beda/ozuqa sen=off.
    #   kod=0 (baliqxovuz/issiqxona/ekin emas) → chiqish maskalanadi.
    PER_CROP = bool(crop_assets)
    if PER_CROP:
        from . import crop_kc_table as _ckt
        _crop = (ee.ImageCollection([ee.Image(a) for a in crop_assets]).mosaic()
                 .rename('crop'))
        _codes, _kmax, _kend, _slen, _son = _ckt.coeff_arrays()
        KCBMAX_IMG = _crop.remap(_codes, _kmax, 0.0)      # kod→kcb_max (0=ekin emas)
        KEND_IMG = _crop.remap(_codes, _kend, 0.5)
        SLEN_IMG = _crop.remap(_codes, _slen, 60.0)
        SON_IMG = _crop.remap(_codes, _son, 0.0)          # 1/0 senescence bayrog'i
        CROP_MASK = _crop.gt(0)
        NB = float(_ckt.NDVI_BARE); NF = float(_ckt.NDVI_FULL)
        KCMAX = float(_ckt.KC_MAX); KE_SCALE = float(_ckt.KE_SCALE)

    # Senescence uchun: cho'qqi NDVI VAQTI (per-piksel argmax) — qualityMosaic
    # NDVI max bo'lgan sahnadan 't' (system:time_start, millis) bandini oladi.
    # DIQQAT: FAQAT NDVI+t tanlanadi — butun image (K_DOWN/LST har sahnada turli
    # Float-diapazon) qo'yilsa GEE "homogeneous collection emas" xatosi beradi.
    def _add_t(im):
        im = ee.Image(im)
        ndvi = im.select('NDVI').toFloat()
        t = ee.Image.constant(ee.Number(im.get('system:time_start'))).toFloat().rename('t')
        return ndvi.addBands(t)
    t_peak = (ee.ImageCollection([_add_t(im) for im in image_list])
              .qualityMosaic('NDVI').select('t'))

    def day_step(d, De):
        ndvi = _ndvi_interp(ndvi_coll, d)
        days_after = (ee.Image.constant(d.millis()).subtract(t_peak)
                      .divide(86400000.0).max(0.0))       # cho'qqidan keyingi kunlar
        if PER_CROP:
            # Kcb = kcb_max(piksel) · fc(NDVI)  [SIMS/FAO, per-crop kcb_max]
            _fcn = ndvi.subtract(NB).divide(NF - NB).clamp(0.0, 1.0)
            kcb = KCBMAX_IMG.multiply(_fcn)
            sen = ee.Image(1.0).subtract(
                ee.Image(1.0).subtract(KEND_IMG)
                .multiply(days_after.divide(SLEN_IMG).min(1.0)))
            sen = sen.where(SON_IMG.lt(0.5), 1.0)          # sen=off ekin → sen=1
            kcb = kcb.multiply(sen)
        else:
            kcb = ndvi.multiply(A).add(B).clamp(0.0, KCB_MAX)
            if SEN_ON:                                      # cho'qqidan keyin Kcb pasayadi
                sen = ee.Image(1.0).subtract(
                    ee.Image(1.0 - KCB_END).multiply(days_after.divide(SEN_LEN).min(1.0)))
                kcb = kcb.multiply(sen)
        fc = ndvi.subtract(NB).divide(NF - NB).clamp(0.0, 1.0)
        few = ee.Image(1.0).subtract(fc)

        eto = (daily_et.get_daily_etr24(d, roi, dem, ref_type=kc['ref_type'],
                                        utc_offset=utc_offset, source=etr24_source)
               .rename('ETO'))

        p_img = (ee.ImageCollection(wb.CHIRPS)
                 .filterDate(d, d.advance(1, 'day'))
                 .select('precipitation').first())
        # Yog'in — CHIRPS kunlik rasmi (oy boshida check_chirps_month bilan HAR kun
        # borligi tekshirilgan; soxta 0 va unmask(0) YO'Q).
        P = ee.Image(p_img)

        # topsoil ho'llash (infiltratsiya) → depletion kamayadi
        De2 = De.subtract(P).max(0.0)
        # Kr: De2≤REW → 1;  aks holda (TEW−De2)/(TEW−REW)   [TEW/REW per-piksel]
        # Asos — De2 (Landsat grid/mask), ee.Image(1.0) EMAS (u WGS84 1° va maskasiz)
        Kr = (De2.multiply(0).add(1.0).where(De2.gt(REW),
              TEW.subtract(De2).divide(TEW.subtract(REW))).clamp(0.0, 1.0))
        ke = (Kr.multiply(ee.Image(KCMAX).subtract(kcb))
              .min(few.multiply(KCMAX)).max(0.0).multiply(KE_SCALE))

        E = ke.multiply(eto)                 # tuproq bug'lanishi (mm)
        T = kcb.multiply(eto)                # transpiratsiya (mm)
        De_new = De2.add(E).min(TEW).rename('De')
        return De_new, T, E

    return {'days': days, 'month_start': month_start, 'TEW': TEW, 'day_step': day_step,
            'crop_mask': CROP_MASK if PER_CROP else None, 'n_scenes': ndvi_coll.size()}


def compute_monthly_et_kc(image_list, roi, year, month, utc_offset=0,
                          etr24_source='era5', crop_assets=None, **_ignore):
    """
    Oylik ET (mm/oy) — NDVI-langan FAO-56 qo'sh koeffitsient.
    Kunlik holatli suv balansi (ee.List.iterate): De topsoil depletion.
    Transpiratsiya (Kcb) + tuproq bug'lanishi (Ke) bir kunda hisoblanadi (_kc_model).

    crop_assets — None: bitta (paxta-kalibrlangan) Kc butun ROI'ga (Bushland).
      List of asset ID (crop-code raster): PER-CROP — har piksel o'z ekinining
      kcb_max/kcb_end_frac/sen_len (crop_kc_table, FAO-56). kod=0 → maska.
    """
    m = _kc_model(image_list, roi, year, month, utc_offset, etr24_source, crop_assets)
    init = ee.Image(m['TEW']).rename('De').addBands(ee.Image(0.0).rename('ET'))

    def _step(off, acc):
        acc = ee.Image(acc)
        d = m['month_start'].advance(ee.Number(off), 'day')
        De_new, T, E = m['day_step'](d, acc.select('De'))
        return De_new.addBands(acc.select('ET').add(T).add(E).rename('ET'))

    res = ee.Image(ee.List.sequence(0, m['days'] - 1).iterate(_step, init))
    et_monthly = res.select('ET').max(0.0).rename('ET_MONTHLY')
    if m['crop_mask'] is not None:
        et_monthly = et_monthly.updateMask(m['crop_mask'])     # faqat ekin piksellari
    return (et_monthly
            .set('year', year).set('month', month)
            .set('days_in_month', m['days'])
            .set('n_landsat_scenes', m['n_scenes']))


def daily_et_series_kc(image_list, roi, year, month, utc_offset=0, etr24_source='era5',
                       crop_assets=None):
    """
    Oyning har kuni uchun Kc-model ET (T + E, mm/kun) — ee.List(ee.Image 'ET_DAY').
    compute_monthly_et_kc bilan AYNI kunlik qadam (_kc_model.day_step) va AYNI De holati —
    Σ kunlar = ET_MONTHLY. daily_et.daily_et_series Kc_ETo rejimida shuni qaytaradi
    (CUirr/Prz suv balansi Kc ET bilan haydalsin — oldin SEBAL_B EF·Rn24 edi).
    Returns: (ee.List of ee.Image, days_in_month:int, month_start:ee.Date)
    """
    m = _kc_model(image_list, roi, year, month, utc_offset, etr24_source, crop_assets)
    init = ee.List([ee.Image(m['TEW']).rename('De'), ee.List([])])

    def _step(off, acc):
        acc = ee.List(acc)
        d = m['month_start'].advance(ee.Number(off), 'day')
        De_new, T, E = m['day_step'](d, ee.Image(acc.get(0)))
        et = T.add(E).max(0.0).rename('ET_DAY')
        if m['crop_mask'] is not None:
            et = et.updateMask(m['crop_mask'])
        return ee.List([De_new, ee.List(acc.get(1)).add(et)])

    res = ee.List(ee.List.sequence(0, m['days'] - 1).iterate(_step, init))
    return ee.List(res.get(1)), m['days'], m['month_start']
