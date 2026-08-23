"""
SEBAL-GEE v4 — M9: Daily & Monthly ET
=======================================
Lahzali λE dan kunlik va oylik ET ga o'tish.

Daily mode:
  ET₂₄ = Λ × Rn24 / λ  (mm/day)
  Rn24 = (1 - α) × Rs24 - 110 × τsw  [De Bruin/Slob]

Monthly mode:
  1. Har Landsat sana uchun Λ hisoblash
  2. Sanalar orasida Λ ni lineer interpolyatsiya
  3. Har kun: ET_kun = Λ_interp × Rn24_kun / λ
  4. Oylik yig'indi: ET_month = Σ ET_kun

Kalit printsip: Λ (evaporative fraction) kunboyi va bir necha
hafta oralig'ida nisbatan barqaror — Bastiaanssen (1998),
Shuttleworth et al. (1989).

Input:  Image(s) with EVAP_FRAC + ERA5 daily radiation
Output: ET₂₄ (mm/day) yoki ET_monthly (mm/month)
"""

import ee
from . import config as cfg
from . import ref_et   # SEBAL_ID: kunlik alfalfa ETr24 (ETrF ekstrapolyatsiya)


# ==============================================================
# ETR24 — kunlik alfalfa referens ET (SEBAL_ID ETrF uchun)
# ==============================================================

GRIDMET = 'IDAHO_EPSCOR/GRIDMET'   # AQSh (CONUS) — ASCE etr/eto, 4 km


def get_daily_etr24(date, roi, dem, ref_type='alfalfa', utc_offset=0,
                    source='era5'):
    """
    Kunlik (24 soat) referens ET — SEBAL_ID: ET24 = ETrF · ETr24 (Eq 5.8).

    source='era5'    — ASCE-EWRI FAO-56 PM, ERA5-Land agregatsiyasidan (default).
    source='gridmet' — IDAHO_EPSCOR/GRIDMET tayyor `etr` (alfalfa) / `eto` (grass).
        ⚠️ FAQAT AQSh (CONUS) — boshqa hududda rasm yo'q (null) → ishlamaydi.
        Validatsiya (US-Ne1 2022, n=45): bizning ERA5 ETr24 GRIDMET'dan
        alfalfa uchun −9.3%, grass uchun −5.5% past chiqadi.

    MUHIM (era5): KALENDAR kun (yarim tundan) — overpass VAQTI emas. `utc_offset`
    bilan MAHALLIY standart kunga bog'lanadi (Manual App.5-A; DST qo'llanmaydi).
    """
    day = ee.Date(ee.Date(date).format('YYYY-MM-dd'))   # yarim tun (kalendar kun)

    if source == 'gridmet':
        band = 'etr' if ref_type == 'alfalfa' else 'eto'
        img = (ee.ImageCollection(GRIDMET)
               .filterDate(day, day.advance(1, 'day')).first())
        return ee.Image(img).select(band).rename('ETR24')

    # SOATLIK-YIG'INDI (kitob App.B) — kunlik-qadamdan aniqroq (Ne1 2022:
    # R² 0.801→0.830). Har soat kunduz/tun koeffitsientlari bilan ETr, 24 soat yig'indi.
    etr = ref_et.compute_etr24_hourly_sum(day, roi, ee.Image(dem),
                                          ref_type=ref_type, utc_offset=utc_offset)
    return etr.select('ETr').rename('ETR24')


# ==============================================================
# RS24 — 24-hour incoming solar radiation from ERA5
# ==============================================================

def get_daily_solar_radiation(date, roi, utc_offset=0):
    """
    ERA5 dan 24 soatlik quyosh radiatsiyasi olish.

    Rs24 = ERA5 ssrd ni 24 soatga yig'ib, o'rtacha W/m² ga o'girish.

    ERA5-Land hourly: har soatdagi accumulated qiymat (J/m²).
    24 soat yig'indisi / 86400 = o'rtacha W/m²

    Parameters
    ----------
    date : ee.Date
        Sana
    roi : ee.Geometry
        Hudud

    Returns
    -------
    ee.Image : Rs24 (W/m²)
    """
    # Mahalliy standart kalendar kun (App.5-A) — utc_offset=0 → eski UTC kun
    day_start = ee.Date(date).advance(-utc_offset, 'hour')
    day_end = day_start.advance(1, 'day')

    ssrd_band = cfg.ERA5['bands']['ssrd']

    daily_ssrd = (ee.ImageCollection(cfg.ERA5['collection'])
                  .filterDate(day_start, day_end)
                  .filterBounds(roi)
                  .select(ssrd_band)
                  .sum())  # 24 soat yig'indisi (J/m²)

    # J/m² → W/m² (o'rtacha)
    rs24 = (daily_ssrd
            .divide(cfg.DAILY_ET['seconds_per_day'])
            .rename('RS24'))

    return rs24


# ==============================================================
# ET₂₄ — Kunlik ET (bitta sana uchun)
# ==============================================================

def utc_offset_from_roi(roi):
    """
    ROI markazidan MAHALLIY STANDART vaqt zonasi offseti (soat, butun son).

    SEBAL Manual App.5-A: korreksiya = (vaqt zonasi MARKAZI boylami)/15.
    Zona markazlari 15° ga karrali (−90 Central, −105 Mountain, ...), shuning
    uchun sayt boylamini 15 ga bo'lib YAXLITLASH zona markazini beradi.
    DST HECH QACHON qo'llanmaydi (qishki standart vaqt).

    ⚠️ Bu TAXMIN — ba'zi davlatlarda zona quyosh vaqtidan siljigan
    (masalan O'zbekiston: lon≈65 → −taxmin +4, ASLIDA UZT = +5).
    Aniq qiymatni `utc_offset=` bilan qo'lda bering.
    """
    lon = ee.Number(ee.Geometry(roi).centroid(1).coordinates().get(0)).getInfo()
    return int(round(lon / 15.0))


def compute_daily_et(image, roi, mode='SEBAL_B', ref_type='alfalfa', utc_offset=0,
                     etr24_source='era5', sloping_terrain=False):
    """
    Kunlik ET hisoblash — bitta Landsat sahna uchun.

    SEBAL_B (EF o'z-o'zini saqlash — Bastiaanssen 1998):
      ET₂₄ = Λ × Rn24 × 86400 / λ    (Rn24 = (1-α)·Rs24 − 110·τsw)

    SEBAL_ID (ETrF o'z-o'zini saqlash — Tasumi 2003, Eq 5.6–5.8):
      ETrF_inst = ET_inst / ETr_inst  (overpass)
      ET₂₄ = ETrF_inst × ETr24        (ETr24 = kunlik alfalfa referens ET)
      Advektiv muhitda (Idaho) ETr Rn−G'dan yaxshiroq umumiy bug'lanish indeksi.

    λ = harorat bog'liq (Tasumi 3.48). 1 kg/m² = 1 mm.
    Returns: Image with ET_24 (+ SEBAL_B: RN24; SEBAL_ID: ETRF_INST, ETR24) bands.
    """
    date = ee.Date(image.get('system:time_start'))
    evap_frac = image.select('EVAP_FRAC')
    albedo = image.select('ALBEDO')
    tau_sw = image.select('TAU_SW')

    # 1. Rs24 — ERA5 dan (mahalliy standart kun)
    rs24 = get_daily_solar_radiation(date, roi, utc_offset=utc_offset)
    # QIYA YUZA: sutkalik radiatsiya qiyalik/ekspozitsiyaga qarab o'zgaradi.
    # Koeffitsientlar SAHNA BANDI sifatida saqlanadi ('RA24_RATIO', 'C_RAD') —
    # oylik hisobda ular ETrF bilan birga interpolyatsiya qilinadi.
    if sloping_terrain:
        from . import sloping_terrain as slt
        ra_ratio = slt.ra24_ratio(image)               # band 'RA24_RATIO'
        image = image.addBands(ra_ratio)
        if not cfg.is_id_mode(mode):
            rs24 = rs24.multiply(ra_ratio).rename('RS24')   # SEBAL_B: Rn24 orqali
    image = image.addBands(rs24)

    # 2. Rn24 — De Bruin/Slob
    rn24 = ((ee.Image(1.0).subtract(albedo)).multiply(rs24)
            .subtract(ee.Image(cfg.DAILY_ET['rn24_constant']).multiply(tau_sw))
            .max(0)
            .rename('RN24'))

    image = image.addBands(rn24)

    # λ HAROTARGA BOG'LIQ (Tasumi Eq. 3.48): (2.501 − 0.00236·(Ts−273))·10⁶ J/kg
    lam = (image.select('LST').subtract(273.0).multiply(-0.00236)
           .add(2.501).multiply(1e6).rename('LAMBDA_HV'))
    spd = cfg.DAILY_ET['seconds_per_day']

    # Lahzali ET (mm/soat)
    et_inst = (image.select('LAMBDA_E').multiply(3600.0).divide(lam)
               .rename('ET_INST_MM_HR'))
    image = image.addBands(et_inst)

    if cfg.is_id_mode(mode):
        # ETrF_inst = ET_inst / ETr_inst (ikkalasi mm/soat)
        # ref_type — EKSTRAPOLYATSIYA referensi (alfalfa default, grass sinov uchun).
        # DIQQAT: cold anchor (ET_cp=1.05·ETr) HAR DOIM ALFALFA da qoladi
        # (kitobning fizik ta'rifi) — u energy_balance'da 'ETR_INST' dan olinadi.
        if ref_type == 'alfalfa':
            etr_inst = image.select('ETR_INST').max(0.01)   # 0 ga bo'linishdan himoya
        else:
            etr_inst = (ref_et.compute_instant_etr(
                image, ref_type=ref_type, band_name='ETR_INST_REF')
                .select('ETR_INST_REF').max(0.01))
        etrf_inst = (et_inst.divide(etr_inst)
                     .clamp(0, 1.05)         # ET_cold=1.05·ETr → fizik chegara 1.05
                     .rename('ETRF_INST'))
        # ETr24 — kunlik referens ET (ref_type bo'yicha)
        etr24 = get_daily_etr24(date, roi, image.select('DEM'),
                                ref_type=ref_type, utc_offset=utc_offset,
                                source=etr24_source)
        # QIYA YUZA (Eq 5.17-5.19): ETrF24 = C_rad · ETrF_inst
        etrf24 = etrf_inst
        image = image.addBands(etrf_inst).addBands(etr24)
        if sloping_terrain:
            from . import sloping_terrain as slt
            c_rad = slt.c_radiation(image)             # band 'C_RAD'
            image = image.addBands(c_rad)
            etrf24 = etrf_inst.multiply(c_rad).rename('ETRF24')

        if mode == 'SEBAL_Milliy':
            # SOLAR upscaling: ET₂₄ = ET_inst · (Rs24_jami / Rs_inst) = ET_inst·eff.soat.
            # Referens-ETrF (self-preservation) o'rniga SOLAR shakl — diurnal
            # over-baholashni fizik yechadi. Bushland lizimetr: daily MBE +0.88→
            # +0.17, R²↑; solar shakl ekin ET diurnaliga mos (~9.25 eff.soat vs
            # referens ~10.9). Rs24=get_daily_solar_radiation (ERA5 SSRD kunlik
            # o'rt W/m²), Rs_inst=SSRD (ERA5 overpass soati, J/m²) — izchil ERA5.
            rs24 = get_daily_solar_radiation(date, roi, utc_offset)       # W/m² o'rt
            ssrd = image.select('SSRD').max(1e4)                          # J/m² (overpass soati)
            solar_frac = et_inst.divide(ssrd).rename('SOLAR_FRAC')        # monthly interp uchun
            eff_hr = rs24.multiply(cfg.DAILY_ET['seconds_per_day']).divide(ssrd)  # eff.soat
            et_24 = et_inst.multiply(eff_hr).max(0).rename('ET_24')
            image = image.addBands(solar_frac).addBands(et_24)
        else:
            # SEBAL_ID: ET₂₄ = ETrF24 · ETr24  (Tasumi Eq 5.8 / 5.19)
            et_24 = etrf24.multiply(etr24).max(0).rename('ET_24')
            image = image.addBands(et_24)
    else:
        # SEBAL_B: ET₂₄ = EF × Rn24 × 86400 / λ
        et_24 = (evap_frac.multiply(rn24).multiply(spd).divide(lam)
                 .max(0).rename('ET_24'))
        image = image.addBands(et_24)

    return image


# ==============================================================
# SEBAL_Milliy — KUNLIK ET SERIYASI (CUirr suv balansi uchun)
# ==============================================================

def daily_et_series(image_list, roi, year, month, mode='SEBAL_Milliy',
                    ref_type='alfalfa', utc_offset=0, etr24_source='era5',
                    sloping_terrain=False):
    """
    Oyning har kuni uchun kunlik ET (mm/kun) — ee.List(ee.Image). BARCHA rejim.

    compute_monthly_et'ning kunlik qadami (compute_day_et) bilan AYNAN bir xil
    mantiq: SEBAL_Milliy → SOLAR_FRAC×Rs24; SEBAL_ID → ETRF_INST×ETr24;
    SEBAL_B/pysebal → EF×Rn24/λ. consumptive_use shu seriyani ildiz-zona suv
    balansini haydash uchun ishlatadi (ET va Prz bir xil kunlik ET'dan).

    Returns: (ee.List of ee.Image, days_in_month:int, month_start:ee.Date)
    """
    import calendar
    days = calendar.monthrange(year, month)[1]
    month_start = ee.Date.fromYMD(year, month, 1)

    if mode == 'SEBAL_Milliy':
        bands = ['SOLAR_FRAC']
    elif cfg.is_id_mode(mode):
        bands = ['ETRF_INST'] + (['C_RAD'] if sloping_terrain else [])
    else:
        bands = ['EVAP_FRAC', 'ALBEDO', 'TAU_SW', 'LST'] + \
                (['RA24_RATIO'] if sloping_terrain else [])
    coll = ee.ImageCollection(image_list).select(bands)
    dem_img = (ee.Image(image_list[0]).select('DEM')
               if cfg.is_id_mode(mode) else None)

    def _day(off):
        off = ee.Number(off)
        d = month_start.advance(off, 'day')
        if mode == 'SEBAL_Milliy':
            interp = _nearest_scene(coll, d)
            rs24 = get_daily_solar_radiation(d, roi, utc_offset=utc_offset)
            return (interp.select('SOLAR_FRAC').multiply(rs24)
                    .multiply(cfg.DAILY_ET['seconds_per_day']).max(0).rename('ET_DAY'))
        elif cfg.is_id_mode(mode):
            interp = _nearest_scene(coll, d)
            etrf = interp.select('ETRF_INST')
            if sloping_terrain:
                etrf = etrf.multiply(interp.select('C_RAD'))
            etr24 = get_daily_etr24(d, roi, dem_img, ref_type=ref_type,
                                    utc_offset=utc_offset, source=etr24_source)
            return etrf.multiply(etr24).max(0).rename('ET_DAY')
        else:
            interp = _interpolate_lambda(coll, d)
            rs24 = get_daily_solar_radiation(d, roi, utc_offset=utc_offset)
            if sloping_terrain:
                rs24 = rs24.multiply(interp.select('RA24_RATIO'))
            rn24 = ((ee.Image(1.0).subtract(interp.select('ALBEDO'))).multiply(rs24)
                    .subtract(ee.Image(cfg.DAILY_ET['rn24_constant'])
                              .multiply(interp.select('TAU_SW'))).max(0))
            lam = (interp.select('LST').subtract(273.0).multiply(-0.00236)
                   .add(2.501).multiply(1e6))
            return (interp.select('EVAP_FRAC').multiply(rn24)
                    .multiply(cfg.DAILY_ET['seconds_per_day']).divide(lam)
                    .max(0).rename('ET_DAY'))

    return ee.List.sequence(0, days - 1).map(_day), days, month_start


# ==============================================================
# MONTHLY EXTRAPOLATION
# ==============================================================

def compute_monthly_et(image_list, roi, year, month, mode='SEBAL_B',
                       etrf_water_balance=False, ref_type='alfalfa',
                       utc_offset=0, etr24_source='era5', sloping_terrain=False):
    """
    Oylik ET hisoblash — Λ interpolyatsiya + ERA5 kunlik radiatsiya.

    Jarayon:
      1. Oydagi barcha Landsat sahnalardan Λ va albedo olish
      2. Sanalar orasida Λ ni lineer interpolyatsiya
      3. Oyning har kuni uchun:
         - Λ_interp = interpolated evaporative fraction
         - Rs24 = ERA5 dan shu kungi quyosh radiatsiyasi
         - Rn24 = (1-α)×Rs24 - 110×τsw
         - ET_kun = Λ_interp × Rn24 × conversion
      4. Oylik yig'indi: ET_month = Σ ET_kun

    Parameters
    ----------
    image_list : list of ee.Image
        SEBAL natijasi bo'lgan tasvirlar (EVAP_FRAC, ALBEDO, TAU_SW)
    roi : ee.Geometry
    year : int
    month : int

    Returns
    -------
    ee.Image : ET_monthly (mm/month)
    """
    import calendar

    # SEBAL_Milliy_Kc: NDVI-langan FAO-56 qo'sh koeffitsient (Kcb+Ke) upscaling
    # (energiya-balans SOLAR_FRAC EMAS — anchor'ga bog'liq bo'lmagan alohida rejim)
    if cfg.is_kc_mode(mode):
        from . import ndvi_kc
        return ndvi_kc.compute_monthly_et_kc(
            image_list, roi, year, month, utc_offset=utc_offset,
            etr24_source=etr24_source)

    # SEBAL_ID + Appendix I: kunlik ETrF tuzatish (per-piksel suv balansi)
    if cfg.is_id_mode(mode) and etrf_water_balance:
        from . import etrf_water_balance as ewb
        dem_img = ee.Image(image_list[0]).select('DEM')
        return ewb.monthly_et_adjusted(image_list, roi, year, month, dem_img,
                                       ref_type=ref_type, utc_offset=utc_offset,
                                       etr24_source=etr24_source)

    days_in_month = calendar.monthrange(year, month)[1]
    month_start = ee.Date.fromYMD(year, month, 1)

    # ---- 1. Landsat sanalar va Λ qiymatlarini olish ----
    # Har bir image dan: sana, Λ, albedo, τsw
    # Bu server-side ishlashi uchun ImageCollection ga o'giramiz

    # SEBAL_ID: ETrF interpolyatsiya (Eq 5.9); SEBAL_B: EF interpolyatsiya
    # QIYA YUZA: koeffitsientlar sahna bandi sifatida ETrF/EF bilan birga
    # interpolyatsiya qilinadi (ular sahnaning o'z vaqti/geometriyasiga tegishli)
    if cfg.is_id_mode(mode):
        # SEBAL_Milliy: SOLAR_FRAC interpolyatsiya (solar upscaling); SEBAL_ID: ETRF_INST
        if mode == 'SEBAL_Milliy':
            bands = ['SOLAR_FRAC']
        else:
            bands = ['ETRF_INST'] + (['C_RAD'] if sloping_terrain else [])
        interp_collection = ee.ImageCollection(image_list).select(bands)
        dem_img = ee.Image(image_list[0]).select('DEM')
    else:
        bands = ['EVAP_FRAC', 'ALBEDO', 'TAU_SW', 'LST'] + \
                (['RA24_RATIO'] if sloping_terrain else [])
        interp_collection = ee.ImageCollection(image_list).select(bands)
        dem_img = None
    lambda_collection = interp_collection

    # Agar oyda bitta ham tasvir bo'lmasa — None qaytarish
    count = lambda_collection.size()

    # ---- 2. Har kun uchun interpolyatsiya va ET hisoblash ----
    def compute_day_et(day_offset):
        """Bitta kun uchun ET hisoblash."""
        day_offset = ee.Number(day_offset)
        current_date = month_start.advance(day_offset, 'day')

        if mode == 'SEBAL_Milliy':
            # SOLAR upscaling monthly: SOLAR_FRAC (=ET_inst/SSRD) ENG YAQIN sahnadan,
            # × o'sha kunning Rs24 jami (get_daily_solar_radiation × 86400).
            interp = _nearest_scene(lambda_collection, current_date)
            solar_frac = interp.select('SOLAR_FRAC')
            rs24 = get_daily_solar_radiation(current_date, roi, utc_offset=utc_offset)
            et_day = (solar_frac.multiply(rs24)
                      .multiply(cfg.DAILY_ET['seconds_per_day']).max(0))
        elif cfg.is_id_mode(mode):
            # Eq 5.9: har tasvir ±8 kunni ifodalaydi → ENG YAQIN sahna hukmron
            # (o'rtachalash YO'Q — SEBAL_B ning midpoint usulidan farqli)
            interp = _nearest_scene(lambda_collection, current_date)
            etrf_interp = interp.select('ETRF_INST')
            # QIYA YUZA (Eq 5.18): ETrF24 = C_rad · ETrF_inst
            if sloping_terrain:
                etrf_interp = etrf_interp.multiply(interp.select('C_RAD'))
            etr24 = get_daily_etr24(current_date, roi, dem_img,
                                    ref_type=ref_type, utc_offset=utc_offset,
                                    source=etr24_source)
            et_day = etrf_interp.multiply(etr24).max(0)
        else:
            # SEBAL_B — o'zgarmagan: ikki sahna o'rtachasi (midpoint)
            interp = _interpolate_lambda(lambda_collection, current_date)
            # SEBAL_B: ET_kun = EF_interp × Rn24 × 86400 / λ
            rs24 = get_daily_solar_radiation(current_date, roi, utc_offset=utc_offset)
            if sloping_terrain:
                rs24 = rs24.multiply(interp.select('RA24_RATIO'))
            albedo_interp = interp.select('ALBEDO')
            tau_sw = interp.select('TAU_SW')
            rn24 = ((ee.Image(1.0).subtract(albedo_interp)).multiply(rs24)
                    .subtract(
                        ee.Image(cfg.DAILY_ET['rn24_constant']).multiply(tau_sw))
                    .max(0))
            evap_frac = interp.select('EVAP_FRAC')
            lam = (interp.select('LST').subtract(273.0).multiply(-0.00236)
                   .add(2.501).multiply(1e6))
            spd = cfg.DAILY_ET['seconds_per_day']
            et_day = (evap_frac.multiply(rn24).multiply(spd).divide(lam).max(0))

        return et_day

    # Oyning har kuni uchun ET hisoblash
    day_offsets = ee.List.sequence(0, days_in_month - 1)
    daily_et_images = day_offsets.map(compute_day_et)

    # Oylik yig'indi
    et_monthly = (ee.ImageCollection(daily_et_images)
                  .sum()
                  .rename('ET_MONTHLY'))

    # Metadata qo'shish
    et_monthly = (et_monthly
                  .set('year', year)
                  .set('month', month)
                  .set('days_in_month', days_in_month)
                  .set('n_landsat_scenes', count))

    return et_monthly


# def _interpolate_lambda(lambda_collection, target_date):
#     """
#     Lineer interpolyatsiya — ikkita eng yaqin Landsat sana orasida.

#     Agar target_date barcha tasvirlardan OLDIN bo'lsa:
#       → eng yaqin (birinchi) tasvirning Λ sini olish
#     Agar target_date barcha tasvirlardan KEYIN bo'lsa:
#       → eng yaqin (oxirgi) tasvirning Λ sini olish
#     Aks holda:
#       → oldingi va keyingi orasida lineer interpolyatsiya

#     weight = (target - before) / (after - before)
#     Λ_interp = Λ_before × (1 - weight) + Λ_after × weight
#     """
#     target_millis = target_date.millis()

#     # Oldingi tasvir (target_date dan oldin yoki teng)
#     before_col = (lambda_collection
#                   .filter(ee.Filter.lte('system:time_start', target_millis))
#                   .sort('system:time_start', False))  # eng yaqini birinchi

#     # Keyingi tasvir (target_date dan keyin yoki teng)
#     after_col = (lambda_collection
#                  .filter(ee.Filter.gte('system:time_start', target_millis))
#                  .sort('system:time_start', True))  # eng yaqini birinchi

#     # Oldingi bor-yo'qligini tekshirish
#     has_before = before_col.size().gt(0)
#     has_after = after_col.size().gt(0)

#     # Default: to'liq collection ning o'rtachasi (fallback)
#     default_image = lambda_collection.mean()

#     # # Faqat oldingi bor
#     # before_image = ee.Image(ee.Algorithms.If(
#     #     has_before,
#     #     before_col.first(),
#     #     default_image
#     # ))
    
#     before_image = ee.Image(ee.Algorithms.If(
#     has_before,
#     ee.Image(before_col.first()).unmask(default_image),
#     default_image
#     ))

#     # # Faqat keyingi bor
#     # after_image = ee.Image(ee.Algorithms.If(
#     #     has_after,
#     #     after_col.first(),
#     #     default_image
#     # ))
    
#     after_image = ee.Image(ee.Algorithms.If(
#     has_after,
#     ee.Image(after_col.first()).unmask(default_image),
#     default_image
#     ))

#     # Ikkalasi ham bor — interpolyatsiya
#     before_millis = ee.Number(ee.Algorithms.If(
#         has_before,
#         ee.Date(before_image.get('system:time_start')).millis(),
#         target_millis
#     ))

#     after_millis = ee.Number(ee.Algorithms.If(
#         has_after,
#         ee.Date(after_image.get('system:time_start')).millis(),
#         target_millis
#     ))

#     # Weight hisoblash
#     time_range = after_millis.subtract(before_millis).max(1)  # div by 0 himoya
#     weight = target_millis.subtract(before_millis).divide(time_range).min(1).max(0)

#     # Lineer interpolyatsiya: Λ = before×(1-w) + after×w
#     interpolated = (before_image.multiply(ee.Image(1).subtract(weight))
#                     .add(after_image.multiply(weight)))

#     # Agar faqat bir tomoni bor bo'lsa — eng yaqinini olish
#     result = ee.Image(ee.Algorithms.If(
#         has_before.And(has_after),
#         interpolated,
#         ee.Algorithms.If(has_before, before_image, after_image)
#     ))

#     return result.unmask(default_image)

def _nearest_scene(collection, target_date):
    """
    SEBAL_ID (Tasumi Eq 5.9) — ENG YAQIN sahna (vaqt bo'yicha) hukmron.

    "every image represents a period of about 16 days, with 8 days before and
     8 days after the day of the processed image" → har kun o'ziga eng yaqin
    sahnaning ETrF sini oladi (O'RTACHALASH YO'Q).
    Masalan 8 va 24 mart sahnalari: 1–16 mart → 8-mart ETrF; 16–31 mart → 24-mart.
    """
    t = ee.Number(target_date.millis())

    def _dt(img):
        return img.set('dt', ee.Number(img.get('system:time_start'))
                       .subtract(t).abs())

    nearest = ee.Image(collection.map(_dt).sort('dt').first())
    return nearest.unmask(collection.mean())   # bulutli piksel → kolleksiya o'rtachasi


def _interpolate_lambda(lambda_collection, target_date):
    """
    Ikkita eng yaqin Landsat sana orasida — MIDPOINT (o'rtacha) qiymat.
 
    Agar target_date barcha tasvirlardan OLDIN bo'lsa:
      -- eng yaqin (birinchi) tasvirning Lambda qiymatini olish (ekstrapolyatsiya)
    Agar target_date barcha tasvirlardan KEYIN bo'lsa:
      -- eng yaqin (oxirgi) tasvirning Lambda qiymatini olish (ekstrapolyatsiya)
    Aks holda:
      -- oldingi va keyingi sahna orasidagi BARCHA kunlarga bitta xil
         qiymat: (Lambda_before + Lambda_after) / 2 (pog'onali,
         chiziqli og'irlik EMAS -- vaqt masofasi hisobga olinmaydi)
 
    2/3/4+ ta sahna bo'lsa ham mantiq avtomatik moslashadi: har kun
    o'ziga eng yaqin oldingi va keyingi sahnani qidiradi, shu ikkisi
    orasida o'rtacha qiymat qo'llanadi (kesma-kesma pog'onali funksiya).
    """
    target_millis = target_date.millis()
 
    # Oldingi tasvir (target_date dan oldin yoki teng)
    before_col = (lambda_collection
                  .filter(ee.Filter.lte('system:time_start', target_millis))
                  .sort('system:time_start', False))  # eng yaqini birinchi
 
    # Keyingi tasvir (target_date dan keyin yoki teng)
    after_col = (lambda_collection
                 .filter(ee.Filter.gte('system:time_start', target_millis))
                 .sort('system:time_start', True))  # eng yaqini birinchi
 
    # Oldingi bor-yo'qligini tekshirish
    has_before = before_col.size().gt(0)
    has_after = after_col.size().gt(0)
 
    # Default: to'liq collection ning o'rtachasi (fallback)
    default_image = lambda_collection.mean()
 
    # # Faqat oldingi bor

    before_image = ee.Image(ee.Algorithms.If(
    has_before,
    ee.Image(before_col.first()).unmask(default_image),
    default_image
    ))
 
    # # Faqat keyingi bor
    # after_image = ee.Image(ee.Algorithms.If(
    #     has_after,
    #     after_col.first(),
    #     default_image
    # ))
    
    after_image = ee.Image(ee.Algorithms.If(
    has_after,
    ee.Image(after_col.first()).unmask(default_image),
    default_image
    ))
 
    # O'rtacha (midpoint) qiymat: Lambda = (before + after) / 2
    # Ikki sahna orasidagi BARCHA kunlarga bir xil qiymat beriladi
    # (chiziqli og'irlik EMAS -- pog'onali/qadam funksiyasi)
    interpolated = (before_image.add(after_image)).multiply(0.5)
 
    # Agar faqat bir tomoni bor bo'lsa — eng yaqinini olish
    result = ee.Image(ee.Algorithms.If(
        has_before.And(has_after),
        interpolated,
        ee.Algorithms.If(has_before, before_image, after_image)
    ))
 
    return result.unmask(default_image)
# ==============================================================
# SEASONAL SUMMARY
# ==============================================================

def compute_seasonal_stats(monthly_images):
    """
    Mavsumiy statistika — oylik ET lardan.

    Parameters
    ----------
    monthly_images : list of ee.Image
        Har biri ET_MONTHLY (mm/month)

    Returns
    -------
    dict with:
      - total: ee.Image — mavsumiy jami (mm)
      - mean_daily: ee.Image — o'rtacha kunlik (mm/day)
    """
    collection = ee.ImageCollection(monthly_images)

    total = collection.sum().rename('ET_SEASONAL_TOTAL')

    # Umumiy kunlar soni
    total_days = ee.Number(0)
    for img in monthly_images:
        total_days = total_days.add(ee.Number(img.get('days_in_month')))

    mean_daily = total.divide(total_days).rename('ET_SEASONAL_MEAN_DAILY')

    return {
        'total': total,
        'mean_daily': mean_daily,
    }
