"""
SEBAL-GEE v4 — Monthly Analytics
==================================
Oylik ET, biomass va boshqa analitikalarni TO'G'RI hisoblash.

Usul: Λ/FPAR/LUE interpolyatsiya + ERA5 har kungi radiatsiya.
× 31 EMAS! Har kun alohida hisoblanadi.

Mantiq:
  1. Landsat sahnalar orasida parametrlarni interpolyatsiya
  2. ERA5 dan har kungi Rs24 (quyosh radiatsiyasi)
  3. Har kun: ET_kun, Biomass_kun hisoblash
  4. Oylik: yig'indi (ET, biomass) va o'rtacha (kc, NDVI, SM)

Input:  List of processed scene images (pysebal bands bo'lishi kerak)
Output: ee.Image — oylik bandlar
"""

import ee
import calendar
from . import config as cfg


# ==============================================================
# ERA5 KUNLIK RADIATSIYA
# ==============================================================

def _get_daily_rs24(date, roi):
    """ERA5 dan bitta kun uchun Rs24 (W/m²)."""
    day_start = ee.Date(date)
    day_end = day_start.advance(1, 'day')

    ssrd = (ee.ImageCollection(cfg.ERA5['collection'])
            .filterDate(day_start, day_end)
            .filterBounds(roi)
            .select(cfg.ERA5['bands']['ssrd'])
            .sum()
            .divide(cfg.DAILY_ET['seconds_per_day']))

    return ssrd.rename('RS24_DAILY')


# ==============================================================
# INTERPOLYATSIYA — eng yaqin Landsat sahnadan
# ==============================================================

# def _interpolate_bands(scene_collection, target_date, bands):
#     """
#     Landsat sanalar orasida lineer interpolyatsiya.
#     Bulut/NoData teshiklari composite mean bilan to'ldiriladi.
#     """
#     target_millis = target_date.millis()

#     before_col = (scene_collection
#                   .filter(ee.Filter.lte('system:time_start', target_millis))
#                   .sort('system:time_start', False))

#     after_col = (scene_collection
#                  .filter(ee.Filter.gte('system:time_start', target_millis))
#                  .sort('system:time_start', True))

#     has_before = before_col.size().gt(0)
#     has_after = after_col.size().gt(0)

#     # Oy ichidagi barcha mavjud sahnalar bo'yicha piksel-wise mean.
#     # Bulut teshiklarini to'ldirish uchun fallback.
#     default_img = scene_collection.select(bands).mean()

#     before_img = ee.Image(ee.Algorithms.If(
#         has_before,
#         ee.Image(before_col.select(bands).first()).unmask(default_img),
#         default_img
#     ))

#     after_img = ee.Image(ee.Algorithms.If(
#         has_after,
#         ee.Image(after_col.select(bands).first()).unmask(default_img),
#         default_img
#     ))

#     before_millis = ee.Number(ee.Algorithms.If(
#         has_before,
#         ee.Date(before_img.get('system:time_start')).millis(),
#         target_millis
#     ))

#     after_millis = ee.Number(ee.Algorithms.If(
#         has_after,
#         ee.Date(after_img.get('system:time_start')).millis(),
#         target_millis
#     ))

#     time_range = after_millis.subtract(before_millis).max(1)

#     weight = (ee.Number(target_millis)
#               .subtract(before_millis)
#               .divide(time_range)
#               .min(1)
#               .max(0))

#     interpolated = (before_img.multiply(ee.Image(1).subtract(weight))
#                     .add(after_img.multiply(weight)))

#     result = ee.Image(ee.Algorithms.If(
#         has_before.And(has_after),
#         interpolated,
#         ee.Algorithms.If(has_before, before_img, after_img)
#     ))

#     # Oxirgi himoya: qolgan NoData joylar ham composite bilan to'ladi
#     return ee.Image(result).unmask(default_img)

def _interpolate_bands(scene_collection, target_date, bands):
    """
    Ikkita eng yaqin Landsat sana orasida — MIDPOINT (o'rtacha) qiymat.
    Bulut/NoData teshiklari composite mean bilan to'ldiriladi.

    daily_et.py dagi _interpolate_lambda() bilan BIR XIL mantiq
    (izchillik uchun) — chiziqli og'irlik EMAS, pog'onali:

    Agar target_date barcha tasvirlardan OLDIN bo'lsa:
      -- eng yaqin (birinchi) tasvirning qiymati (ekstrapolyatsiya)
    Agar target_date barcha tasvirlardan KEYIN bo'lsa:
      -- eng yaqin (oxirgi) tasvirning qiymati (ekstrapolyatsiya)
    Aks holda:
      -- oldingi va keyingi sahna orasidagi BARCHA kunlarga bitta xil
         qiymat: (before + after) / 2
    """
    target_millis = target_date.millis()

    before_col = (scene_collection
                  .filter(ee.Filter.lte('system:time_start', target_millis))
                  .sort('system:time_start', False))

    after_col = (scene_collection
                 .filter(ee.Filter.gte('system:time_start', target_millis))
                 .sort('system:time_start', True))

    has_before = before_col.size().gt(0)
    has_after = after_col.size().gt(0)

    # Oy ichidagi barcha mavjud sahnalar bo'yicha piksel-wise mean.
    # Bulut teshiklarini to'ldirish uchun fallback.
    default_img = scene_collection.select(bands).mean()

    before_img = ee.Image(ee.Algorithms.If(
        has_before,
        ee.Image(before_col.select(bands).first()).unmask(default_img),
        default_img
    ))

    after_img = ee.Image(ee.Algorithms.If(
        has_after,
        ee.Image(after_col.select(bands).first()).unmask(default_img),
        default_img
    ))

    # O'rtacha (midpoint) qiymat: ikki sahna orasidagi BARCHA kunlarga
    # bir xil qiymat beriladi (chiziqli og'irlik EMAS)
    interpolated = (before_img.add(after_img)).multiply(0.5)

    result = ee.Image(ee.Algorithms.If(
        has_before.And(has_after),
        interpolated,
        ee.Algorithms.If(has_before, before_img, after_img)
    ))

    # Oxirgi himoya: qolgan NoData joylar ham composite bilan to'ladi
    return ee.Image(result).unmask(default_img)


# ==============================================================
# OYLIK ET — Λ interpolyatsiya + ERA5
# ==============================================================

def compute_monthly_et(scene_images, roi, year, month):
    """
    Oylik ET (mm/month) — to'g'ri interpolyatsiya.

    Har kun:
      Rn24 = (1 - α) × Rs24 - 110 × τsw
      ET_kun = Λ × Rn24 × 86400 / λ

    Λ, α, τsw — Landsat orasida interpolyatsiya
    Rs24 — ERA5 dan har kun alohida
    """
    days = calendar.monthrange(year, month)[1]
    month_start = ee.Date.fromYMD(year, month, 1)
    conversion = cfg.DAILY_ET['seconds_per_day'] / cfg.LAMBDA_V

    scene_col = ee.ImageCollection(scene_images)
    interp_bands = ['EVAP_FRAC', 'ALBEDO', 'TAU_SW']

    def compute_day(day_offset):
        day_offset = ee.Number(day_offset)
        current_date = month_start.advance(day_offset, 'day')

        interp = _interpolate_bands(scene_col, current_date, interp_bands)

        rs24 = _get_daily_rs24(current_date, roi)
        albedo = interp.select('ALBEDO')
        tau_sw = interp.select('TAU_SW')
        evap_frac = interp.select('EVAP_FRAC')

        rn24 = ((ee.Image(1.0).subtract(albedo)).multiply(rs24)
                .subtract(ee.Image(cfg.DAILY_ET['rn24_constant']).multiply(tau_sw))
                .max(0))

        et_day = evap_frac.multiply(rn24).multiply(conversion).max(0)
        return et_day

    day_offsets = ee.List.sequence(0, days - 1)
    daily_ets = ee.ImageCollection(day_offsets.map(compute_day))

    et_monthly = daily_ets.sum().rename('ET_MONTHLY')
    return et_monthly


# ==============================================================
# OYLIK BIOMASS — FPAR/LUE interpolyatsiya + ERA5 PAR
# ==============================================================

def compute_monthly_biomass(scene_images, roi, year, month):
    """
    Oylik biomassa (kg DM/ha/month).

    Har kun:
      PAR_kun = Rs24(ERA5) × 0.48
      APAR_kun = FPAR_interp × PAR_kun
      Biomass_kun = APAR_kun(MJ) × LUE_interp × 10 × 2.0

    FPAR, LUE — Landsat orasida interpolyatsiya
    Rs24 — ERA5 dan har kun
    """
    days = calendar.monthrange(year, month)[1]
    month_start = ee.Date.fromYMD(year, month, 1)

    scene_col = ee.ImageCollection(scene_images)
    interp_bands = ['FPAR', 'LUE']

    def compute_day(day_offset):
        day_offset = ee.Number(day_offset)
        current_date = month_start.advance(day_offset, 'day')

        interp = _interpolate_bands(scene_col, current_date, interp_bands)

        rs24 = _get_daily_rs24(current_date, roi)
        fpar = interp.select('FPAR')
        lue = interp.select('LUE')

        # PAR = Rs24 × 0.48 (W/m²)
        par = rs24.multiply(0.48)

        # APAR = FPAR × PAR (W/m²)
        apar = fpar.multiply(par)

        # APAR W/m² → MJ/m²/day
        apar_mj = apar.multiply(0.0864)

        # Biomass = APAR(MJ) × LUE(gC/MJ) × 10(g/m²→kg/ha) × 2(C→DM)
        biomass_day = apar_mj.multiply(lue).multiply(10.0).multiply(2.0).max(0)

        return biomass_day

    day_offsets = ee.List.sequence(0, days - 1)
    daily_bio = ee.ImageCollection(day_offsets.map(compute_day))

    biomass_monthly = daily_bio.sum().rename('BIOMASS_MONTHLY')
    return biomass_monthly


# ==============================================================
# OYLIK ET DECOMPOSITION — ETref, ETpot, deficit, T/E
# ==============================================================

def compute_monthly_et_components(scene_images, roi, year, month):
    """
    Oylik ET komponentlari.

    ETREF_24, ETPOT_24 — endi HAR KALENDAR KUN uchun to'g'ridan-to'g'ri
    ref_et.py (ASCE-EWRI FAO-PM) orqali hisoblanadi — Landsat sahnadan
    interpolyatsiya/scaling QILINMAYDI (chunki bu sof meteorologik
    miqdor, har kuni aniq hisoblash mumkin).

    TACT_24, EACT_24 — hali ham Landsat sahnalardan interpolyatsiya
    (chunki bular LAI/canopy-ga bog'liq, faqat Landsat orqali biladi),
    radiatsiya nisbati bilan masshtablanadi.
    """
    from . import ref_et

    days = calendar.monthrange(year, month)[1]
    month_start = ee.Date.fromYMD(year, month, 1)
    conversion = cfg.DAILY_ET['seconds_per_day'] / cfg.LAMBDA_V

    scene_col = ee.ImageCollection(scene_images)

    scene_rn24_mean = (scene_col.select('RN24').mean().max(1))

    # ETREF_24/ETPOT_24 ENDI shu ro'yxatda YO'Q — Landsat'dan
    # interpolyatsiya qilinmaydi, alohida, to'g'ridan-to'g'ri hisoblanadi
    interp_bands = ['EVAP_FRAC', 'ALBEDO', 'TAU_SW',
                    'TACT_24', 'EACT_24', 'KC', 'BENEFICIAL_FRACTION']

    def compute_day(day_offset):
        day_offset = ee.Number(day_offset)
        current_date = month_start.advance(day_offset, 'day')

        interp = _interpolate_bands(scene_col, current_date, interp_bands)
        rs24 = _get_daily_rs24(current_date, roi)

        albedo = interp.select('ALBEDO')
        tau_sw = interp.select('TAU_SW')
        rn24_actual = ((ee.Image(1.0).subtract(albedo)).multiply(rs24)
                       .subtract(ee.Image(cfg.DAILY_ET['rn24_constant']).multiply(tau_sw))
                       .max(0))

        rad_ratio = rn24_actual.divide(scene_rn24_mean).clamp(0, 1.5)

        # ET (haqiqiy) — Landsat/SEBAL asosli, o'zgarmadi
        et_day = (interp.select('EVAP_FRAC')
                  .multiply(rn24_actual).multiply(conversion).max(0))

        # ETREF, ETPOT — ENDI to'g'ridan-to'g'ri, mustaqil, aniq hisob
        refs = ref_et.compute_reference_ets_for_date(current_date, roi)
        etref_day = refs.select('ETREF_24')
        etpot_day = refs.select('ETPOT_24')

        deficit_day = etpot_day.subtract(et_day).max(0)

        # TACT, EACT — hali ham Landsat-interpolyatsiya (LAI-bog'liq)
        tact_day = interp.select('TACT_24').multiply(rad_ratio)
        eact_day = et_day.subtract(tact_day).max(0)

        return (et_day.rename('ET')
                .addBands(etref_day.rename('ETREF'))
                .addBands(etpot_day.rename('ETPOT'))
                .addBands(deficit_day.rename('DEFICIT'))
                .addBands(tact_day.rename('TACT'))
                .addBands(eact_day.rename('EACT')))

    day_offsets = ee.List.sequence(0, days - 1)
    daily_comp = ee.ImageCollection(day_offsets.map(compute_day))

    monthly = daily_comp.sum()

    return (monthly.select('ET').rename('ET_MONTHLY')
            .addBands(monthly.select('ETREF').rename('ETREF_MONTHLY'))
            .addBands(monthly.select('ETPOT').rename('ETPOT_MONTHLY'))
            .addBands(monthly.select('DEFICIT').rename('DEFICIT_MONTHLY'))
            .addBands(monthly.select('TACT').rename('TACT_MONTHLY'))
            .addBands(monthly.select('EACT').rename('EACT_MONTHLY')))


# def compute_monthly_et_components(scene_images, roi, year, month):
#     """
#     Oylik ET komponentlari — interpolyatsiya + ERA5.

#     YIG'INDI (mm/month):
#       ETref, ETpot, ET_deficit, Tact, Eact

#     Har kun ETref ni ERA5 dan hisoblash kerak (wind, temp, VPD).
#     Soddalashtirilgan: ETref_kun = ETref_interp × (Rs24_kun / Rs24_scene)
#     """
#     days = calendar.monthrange(year, month)[1]
#     month_start = ee.Date.fromYMD(year, month, 1)
#     conversion = cfg.DAILY_ET['seconds_per_day'] / cfg.LAMBDA_V

#     scene_col = ee.ImageCollection(scene_images)

#     # Scene sahnalardan o'rtacha Rs24 (radiatsiya ratio uchun)
#     scene_rs24_mean = (scene_col.select('RN24')
#                        .mean()
#                        .max(1))

#     interp_bands = ['EVAP_FRAC', 'ALBEDO', 'TAU_SW',
#                     'ETREF_24', 'ETPOT_24', 'ET_DEFICIT',
#                     'TACT_24', 'EACT_24', 'KC', 'BENEFICIAL_FRACTION']

#     def compute_day(day_offset):
#         day_offset = ee.Number(day_offset)
#         current_date = month_start.advance(day_offset, 'day')

#         interp = _interpolate_bands(scene_col, current_date, interp_bands)
#         rs24 = _get_daily_rs24(current_date, roi)

#         # Radiatsiya nisbati — bulutsiz vs haqiqiy kun
#         albedo = interp.select('ALBEDO')
#         tau_sw = interp.select('TAU_SW')
#         rn24_actual = ((ee.Image(1.0).subtract(albedo)).multiply(rs24)
#                        .subtract(ee.Image(cfg.DAILY_ET['rn24_constant']).multiply(tau_sw))
#                        .max(0))

#         rad_ratio = rn24_actual.divide(scene_rs24_mean).clamp(0, 1.5)

#         # ET komponentlar — radiatsiya bilan masshtablash
#         et_day = (interp.select('EVAP_FRAC')
#                   .multiply(rn24_actual).multiply(conversion).max(0))
#         etref_day = interp.select('ETREF_24').multiply(rad_ratio)
#         etpot_day = interp.select('ETPOT_24').multiply(rad_ratio)
#         deficit_day = etpot_day.subtract(et_day).max(0)
#         tact_day = interp.select('TACT_24').multiply(rad_ratio)
#         eact_day = et_day.subtract(tact_day).max(0)

#         return (et_day.rename('ET')
#                 .addBands(etref_day.rename('ETREF'))
#                 .addBands(etpot_day.rename('ETPOT'))
#                 .addBands(deficit_day.rename('DEFICIT'))
#                 .addBands(tact_day.rename('TACT'))
#                 .addBands(eact_day.rename('EACT')))

#     day_offsets = ee.List.sequence(0, days - 1)
#     daily_comp = ee.ImageCollection(day_offsets.map(compute_day))

#     # Yig'indi
#     monthly = daily_comp.sum()

#     return (monthly.select('ET').rename('ET_MONTHLY')
#             .addBands(monthly.select('ETREF').rename('ETREF_MONTHLY'))
#             .addBands(monthly.select('ETPOT').rename('ETPOT_MONTHLY'))
#             .addBands(monthly.select('DEFICIT').rename('DEFICIT_MONTHLY'))
#             .addBands(monthly.select('TACT').rename('TACT_MONTHLY'))
#             .addBands(monthly.select('EACT').rename('EACT_MONTHLY')))


# ==============================================================
# OYLIK O'RTACHA BANDLAR
# ==============================================================

def compute_monthly_averages(scene_images):
    """
    O'rtacha olinadigan bandlar.
    Faqat mavjud bandlar hisoblanadi.
    Yo'q bandlar tashlab ketiladi.
    """
    col = ee.ImageCollection(scene_images)

    requested_avg_bands = [
        'KC', 'KC_MAX', 'EVAP_FRAC', 'BENEFICIAL_FRACTION',
        'TOP_SOIL_MOISTURE', 'ROOT_ZONE_MOISTURE', 'SM_WETNESS',
        'FPAR', 'LUE', 'WATER_PRODUCTIVITY', 'NDVI', 'LAI'
    ]

    first_img = ee.Image(scene_images[0])
    try:
        available_bands = first_img.bandNames().getInfo()
    except Exception as e:
        print(f"  ⚠️ Monthly average: bandlar aniqlanmadi: {e}")
        available_bands = []

    existing_avg_bands = [
        b for b in requested_avg_bands if b in available_bands
    ]

    missing_avg_bands = [
        b for b in requested_avg_bands if b not in available_bands
    ]

    if missing_avg_bands:
        print(f"    ⚠️ Monthly average: bandlar topilmadi: {missing_avg_bands}")

    monthly_parts = []

    if existing_avg_bands:
        monthly_avg = col.select(existing_avg_bands).mean()
        monthly_parts.append(monthly_avg)
    else:
        print("    ⚠️ Monthly average: o'rtacha hisoblash uchun band yo'q.")

    if 'IRRIGATION_CLASS' in available_bands:
        irr_class = col.select(['IRRIGATION_CLASS']).max()
        monthly_parts.append(irr_class)
    else:
        print("    ⚠️ IRRIGATION_CLASS topilmadi, tashlab ketildi.")

    if not monthly_parts:
        print("    ❌ Monthly averages bo'sh. Empty image qaytarildi.")
        return ee.Image([])

    result = monthly_parts[0]
    for part in monthly_parts[1:]:
        result = result.addBands(part)

    return result


# ==============================================================
# MAIN: To'liq oylik hisoblash
# ==============================================================

def compute_all_monthly(scene_images, roi, year, month):
    """
    Barcha oylik analitikalarni hisoblash.

    Input:  Processed scene images (pysebal bandlar bilan)
    Output: ee.Image with monthly bands:

    YIG'INDI bandlar (mm/month yoki kg/ha/month):
      ET_MONTHLY, ETREF_MONTHLY, ETPOT_MONTHLY,
      DEFICIT_MONTHLY, TACT_MONTHLY, EACT_MONTHLY,
      BIOMASS_MONTHLY

    O'RTACHA bandlar:
      KC, KC_MAX, EVAP_FRAC, BENEFICIAL_FRACTION,
      TOP_SOIL_MOISTURE, ROOT_ZONE_MOISTURE, SM_WETNESS,
      FPAR, LUE, WATER_PRODUCTIVITY, NDVI, LAI

    MAKSIMUM:
      IRRIGATION_CLASS
    """
    print(f"    [{year}-{month:02d}] ET komponentlar (interpolyatsiya)...")
    et_components = compute_monthly_et_components(
        scene_images, roi, year, month)

    print(f"    [{year}-{month:02d}] Biomassa (interpolyatsiya)...")
    biomass = compute_monthly_biomass(scene_images, roi, year, month)

    print(f"    [{year}-{month:02d}] O'rtacha bandlar...")
    averages = compute_monthly_averages(scene_images)

    # Birlashtirish
    monthly = (et_components
               .addBands(biomass)
               .addBands(averages))

    # Metadata
    days = calendar.monthrange(year, month)[1]
    monthly = (monthly
               .set('year', year)
               .set('month', month)
               .set('days_in_month', days)
               .set('n_scenes', len(scene_images)))

    return monthly
