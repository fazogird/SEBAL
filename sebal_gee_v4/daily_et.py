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


# ==============================================================
# RS24 — 24-hour incoming solar radiation from ERA5
# ==============================================================

def get_daily_solar_radiation(date, roi):
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
    day_start = ee.Date(date)
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

def compute_daily_et(image, roi):
    """
    Kunlik ET hisoblash — bitta Landsat sahna uchun.

    Jarayon:
      1. Λ (evaporative fraction) — allaqachon hisoblangan
      2. Rs24 — ERA5 dan shu kungi 24 soatlik quyosh radiatsiyasi
      3. Rn24 = (1 - α) × Rs24 - 110 × τsw
      4. ET₂₄ = Λ × Rn24 × 86400 / (λ)  [mm/day]

    λ = 2.45 × 10⁶ J/kg (suvning bug'lanish issiqligi)
    1000 = kg/m³ → mm konversiya (1 kg/m² = 1 mm)

    Returns: Image with ET_24, RN24 bands added
    """
    date = ee.Date(image.get('system:time_start'))
    evap_frac = image.select('EVAP_FRAC')
    albedo = image.select('ALBEDO')
    tau_sw = image.select('TAU_SW')

    # 1. Rs24 — ERA5 dan
    rs24 = get_daily_solar_radiation(date, roi)
    image = image.addBands(rs24)

    # 2. Rn24 — De Bruin/Slob
    rn24 = ((ee.Image(1.0).subtract(albedo)).multiply(rs24)
            .subtract(ee.Image(cfg.DAILY_ET['rn24_constant']).multiply(tau_sw))
            .max(0)
            .rename('RN24'))

    image = image.addBands(rn24)

    # 3. ET₂₄ (mm/day) — SEBAL_B
    # λ HAROTARGA BOG'LIQ (Tasumi Eq. 3.48): (2.501 − 0.00236·(Ts−273))·10⁶ J/kg
    # (doimiy 2.45e6 EMAS — per-piksel LST'dan).
    lam = (image.select('LST').subtract(273.0).multiply(-0.00236)
           .add(2.501).multiply(1e6).rename('LAMBDA_HV'))
    spd = cfg.DAILY_ET['seconds_per_day']

    # Lahzali ET (mm/hour) — debug uchun
    et_inst = (image.select('LAMBDA_E').multiply(3600.0).divide(lam)
               .rename('ET_INST_MM_HR'))
    image = image.addBands(et_inst)

    # ET₂₄ = EF × Rn24 × 86400 / λ
    et_24 = (evap_frac.multiply(rn24).multiply(spd).divide(lam)
             .max(0).rename('ET_24'))
    image = image.addBands(et_24)

    return image


# ==============================================================
# MONTHLY EXTRAPOLATION
# ==============================================================

def compute_monthly_et(image_list, roi, year, month):
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

    days_in_month = calendar.monthrange(year, month)[1]
    month_start = ee.Date.fromYMD(year, month, 1)

    # ---- 1. Landsat sanalar va Λ qiymatlarini olish ----
    # Har bir image dan: sana, Λ, albedo, τsw
    # Bu server-side ishlashi uchun ImageCollection ga o'giramiz

    lambda_collection = ee.ImageCollection(image_list).select(
        ['EVAP_FRAC', 'ALBEDO', 'TAU_SW', 'LST']
    )

    # Agar oyda bitta ham tasvir bo'lmasa — None qaytarish
    count = lambda_collection.size()

    # ---- 2. Har kun uchun interpolyatsiya va ET hisoblash ----
    def compute_day_et(day_offset):
        """Bitta kun uchun ET hisoblash."""
        day_offset = ee.Number(day_offset)
        current_date = month_start.advance(day_offset, 'day')

        # Eng yaqin Landsat tasvirni topish va Λ ni olish
        # Lineer interpolyatsiya: oldingi va keyingi tasvir orasida
        lambda_interp = _interpolate_lambda(
            lambda_collection, current_date
        )

        # Rs24 — ERA5 dan
        rs24 = get_daily_solar_radiation(current_date, roi)

        # Rn24
        albedo_interp = lambda_interp.select('ALBEDO')
        tau_sw = lambda_interp.select('TAU_SW')

        rn24 = ((ee.Image(1.0).subtract(albedo_interp)).multiply(rs24)
                .subtract(
                    ee.Image(cfg.DAILY_ET['rn24_constant']).multiply(tau_sw)
                )
                .max(0))

        # ET_kun (mm/day) — λ haroratga bog'liq (Tasumi 3.48)
        evap_frac = lambda_interp.select('EVAP_FRAC')
        lam = (lambda_interp.select('LST').subtract(273.0).multiply(-0.00236)
               .add(2.501).multiply(1e6))
        spd = cfg.DAILY_ET['seconds_per_day']

        et_day = (evap_frac.multiply(rn24)
                  .multiply(spd).divide(lam)
                  .max(0))

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
