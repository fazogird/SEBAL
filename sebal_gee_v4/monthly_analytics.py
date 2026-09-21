"""
SEBAL-GEE v4 — Monthly Analytics
==================================
Oylik ET, biomass va boshqa analitikalarni TO'G'RI hisoblash.

Usul: Λ/FPAR/LUE interpolyatsiya + ERA5 har kungi radiatsiya.
× 31 EMAS! Har kun alohida hisoblanadi.

Mantiq:
  1. Har kun, har piksel — vaqt bo'yicha ENG YAQIN YAROQLI Landsat sahna
     (daily_et._nearest_valid — sahnaning vakillik davri)
  2. ERA5 dan har kungi Rs24 (quyosh radiatsiyasi, mahalliy kun)
  3. Har kun: ET_kun, Biomass_kun hisoblash
  4. Oylik: yig'indi (ET, biomass) va o'rtacha (kc, NDVI, SM)

Input:  List of processed scene images (pysebal bands bo'lishi kerak)
Output: ee.Image — oylik bandlar
"""

import ee
import calendar
from . import config as cfg


# ==============================================================
# OYLIK ET — Λ interpolyatsiya + ERA5
# ==============================================================

def compute_monthly_et(scene_images, roi, year, month, utc_offset=0,
                       sloping_terrain=False):
    """
    Oylik ET (mm/month) — daily_et.compute_monthly_et SEBAL_B bilan AYNI mantiq.

    Har kun (eng yaqin YAROQLI sahna — vakillik davri):
      τ24 = Rs24/Ra24 ; Rn24 = (1 - α) × Rs24 - 110 × τ24
      ET_kun = Λ × Rn24 × 86400 / λ
    Λ, α, LST — o'sha sahnadan; Rs24 — ERA5, MAHALLIY kun (utc_offset).
    """
    from . import daily_et
    days = calendar.monthrange(year, month)[1]
    month_start = ee.Date.fromYMD(year, month, 1)
    spd = cfg.DAILY_ET['seconds_per_day']

    scene_col = ee.ImageCollection(scene_images)
    interp_bands = ['EVAP_FRAC', 'ALBEDO', 'LST'] + \
                   (['RA24_RATIO'] if sloping_terrain else [])

    def compute_day(day_offset):
        day_offset = ee.Number(day_offset)
        current_date = month_start.advance(day_offset, 'day')

        interp = daily_et._nearest_valid(scene_col.select(interp_bands), current_date)

        rs24 = daily_et.get_daily_solar_radiation(current_date, roi, utc_offset=utc_offset)
        rs24_s = (rs24.multiply(interp.select('RA24_RATIO'))     # qiya yuza Rs24
                  if sloping_terrain else rs24)
        albedo = interp.select('ALBEDO')
        evap_frac = interp.select('EVAP_FRAC')

        rn24, _ = daily_et.daily_rn24(albedo, rs24, daily_et.get_daily_ra24(current_date),
                                      rs24_surface=rs24_s)

        # λ haroratga bog'liq (Tasumi 3.48): (2.501-0.00236·(Ts-273.15))·10⁶
        lam = (interp.select('LST').subtract(273.15).multiply(-0.00236)
               .add(2.501).multiply(1e6))
        et_day = evap_frac.multiply(rn24).multiply(spd).divide(lam).max(0)
        return et_day

    day_offsets = ee.List.sequence(0, days - 1)
    daily_ets = ee.ImageCollection(day_offsets.map(compute_day))

    et_monthly = daily_ets.sum().rename('ET_MONTHLY')
    return et_monthly


# ==============================================================
# OYLIK BIOMASS — FPAR/LUE interpolyatsiya + ERA5 PAR
# ==============================================================

def compute_monthly_biomass(scene_images, roi, year, month, utc_offset=0,
                            sloping_terrain=False):
    """
    Oylik biomassa (kg DM/ha/month).

    Har kun:
      PAR_kun = Rs24(ERA5) × 0.48
      APAR_kun = FPAR_interp × PAR_kun
      Biomass_kun = APAR_kun(MJ) × LUE_interp × 10 × 2.0

    FPAR, LUE — eng yaqin YAROQLI sahnadan (vakillik davri)
    Rs24 — ERA5 dan har kun (MAHALLIY kun)
    """
    from . import daily_et
    days = calendar.monthrange(year, month)[1]
    month_start = ee.Date.fromYMD(year, month, 1)

    scene_col = ee.ImageCollection(scene_images)
    interp_bands = ['FPAR', 'LUE'] + (['RA24_RATIO'] if sloping_terrain else [])

    def compute_day(day_offset):
        day_offset = ee.Number(day_offset)
        current_date = month_start.advance(day_offset, 'day')

        interp = daily_et._nearest_valid(scene_col.select(interp_bands), current_date)

        rs24 = daily_et.get_daily_solar_radiation(current_date, roi, utc_offset=utc_offset)
        fpar = interp.select('FPAR')
        lue = interp.select('LUE')

        # PAR = Rs24 × 0.48 (W/m²); qiya yuza — Rs24 × RA24_RATIO (sahna RS24 kabi)
        if sloping_terrain:
            rs24 = rs24.multiply(interp.select('RA24_RATIO'))
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

def compute_monthly_et_components(scene_images, roi, year, month, utc_offset=0,
                                  sloping_terrain=False):
    """
    Oylik ET komponentlari.

    ETREF_24, ETPOT_24 — endi HAR KALENDAR KUN uchun to'g'ridan-to'g'ri
    ref_et.py (ASCE-EWRI FAO-PM) orqali hisoblanadi — Landsat sahnadan
    interpolyatsiya/scaling QILINMAYDI (chunki bu sof meteorologik
    miqdor, har kuni aniq hisoblash mumkin).

    TACT, EACT — sahnaning transpiratsiya ULUSHI f_T = TACT_24/ET_24
    (BENEFICIAL_FRACTION, 0–1; LAI/kanopiyga bog'liq — faqat Landsat biladi)
    eng yaqin sahnadan × o'sha kunning ET'i: TACT = f_T·ET, EACT = ET − TACT →
    har kuni T + E = ET (massa balansi).
    """
    from . import ref_et
    from . import daily_et

    days = calendar.monthrange(year, month)[1]
    month_start = ee.Date.fromYMD(year, month, 1)
    spd = cfg.DAILY_ET['seconds_per_day']

    scene_col = ee.ImageCollection(scene_images)

    # ETREF_24/ETPOT_24 ENDI shu ro'yxatda YO'Q — Landsat'dan
    # interpolyatsiya qilinmaydi, alohida, to'g'ridan-to'g'ri hisoblanadi
    interp_bands = ['EVAP_FRAC', 'ALBEDO', 'LST',
                    'TACT_24', 'EACT_24', 'KC', 'BENEFICIAL_FRACTION'] + \
                   (['RA24_RATIO'] if sloping_terrain else [])

    def compute_day(day_offset):
        day_offset = ee.Number(day_offset)
        current_date = month_start.advance(day_offset, 'day')

        interp = daily_et._nearest_valid(scene_col.select(interp_bands), current_date)
        rs24 = daily_et.get_daily_solar_radiation(current_date, roi, utc_offset=utc_offset)

        albedo = interp.select('ALBEDO')
        rs24_s = (rs24.multiply(interp.select('RA24_RATIO'))     # qiya yuza Rs24
                  if sloping_terrain else rs24)
        rn24_actual, _ = daily_et.daily_rn24(albedo, rs24,
                                             daily_et.get_daily_ra24(current_date),
                                             rs24_surface=rs24_s)

        # ET (haqiqiy) — λ haroratga bog'liq (Tasumi 3.48)
        lam = (interp.select('LST').subtract(273.15).multiply(-0.00236)
               .add(2.501).multiply(1e6))
        et_day = (interp.select('EVAP_FRAC')
                  .multiply(rn24_actual).multiply(spd).divide(lam).max(0))

        # ETREF, ETPOT — ENDI to'g'ridan-to'g'ri, mustaqil, aniq hisob
        refs = ref_et.compute_reference_ets_for_date(current_date, roi, utc_offset=utc_offset)
        etref_day = refs.select('ETREF_24')
        etpot_day = refs.select('ETPOT_24')

        deficit_day = etpot_day.subtract(et_day).max(0)

        # TACT = f_T × ET_kun (f_T = BENEFICIAL_FRACTION = TACT_24/ET_24, AYNI sahnadan);
        # EACT = ET − TACT → T + E = ET. Oldin: TACT_24 × Rn24_kun / (MAVSUM sahnalari
        # o'rtacha RN24), clamp 1.5 — yozda T > ET, E = 0 bo'lishi mumkin edi.
        tact_day = interp.select('BENEFICIAL_FRACTION').multiply(et_day)
        eact_day = et_day.subtract(tact_day)

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

def compute_all_monthly(scene_images, roi, year, month, utc_offset=0,
                        sloping_terrain=False):
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
    from . import daily_et
    n_in_month, max_gap = daily_et.month_scene_qc(scene_images, year, month)   # QC
    et_components = compute_monthly_et_components(
        scene_images, roi, year, month, utc_offset=utc_offset,
        sloping_terrain=sloping_terrain)

    print(f"    [{year}-{month:02d}] Biomassa (interpolyatsiya)...")
    biomass = compute_monthly_biomass(scene_images, roi, year, month, utc_offset=utc_offset,
                                      sloping_terrain=sloping_terrain)

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
               .set('n_scenes', n_in_month)            # SHU oydagi sahnalar
               .set('max_gap_days', max_gap))

    return monthly
