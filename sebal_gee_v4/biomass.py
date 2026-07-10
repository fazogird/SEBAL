"""
SEBAL-GEE v4 — Biomass & Water Productivity (mode="pysebal")
=============================================================
Quruq modda hosildorligi va suv unumdorligi.

Zanjir:
  NDVI → FPAR → APAR = FPAR × PAR
  Stress (heat, vapor, moisture) → LUE = LUEmax × stresslar
  Biomass = APAR × LUE × 0.864
  Water_Productivity = Biomass / (ET × 10)

Source: Monteith (1972), pySEBAL v3.8, Bastiaanssen & Ali (2003)
"""

import ee
from . import config as cfg


# ==============================================================
# BIOMASS CONSTANTS
# ==============================================================

LUEMAX = 2.5          # g C / MJ PAR — max light use efficiency
                      # O'simlik turiga qarab: 1.5-3.5
                      # 2.5 = o'rtacha (C3 ekinlar)
PAR_FRACTION = 0.48   # PAR = 0.48 × total solar radiation
C_TO_DM = 2.0         # karbon → quruq modda konversiya (×2)
MJ_CONVERT = 0.864    # W/m²/day → MJ/m²/day (×0.0864) × 10 (g→kg/ha)


# ==============================================================
# 1. FPAR — Fraction of Photosynthetically Active Radiation
# ==============================================================

def compute_fpar(image):
    """
    FPAR — o'simlik yutgan fotosintez radiatsiyasi ulushi.

    FPAR = f(NDVI) — lineer bog'liqlik:
    FPAR = 1.257 × NDVI - 0.161

    Source: Bastiaanssen & Ali (2003)
    Oraliq: 0 (yalang'och tuproq) — 0.95 (zich o'simlik)
    """
    ndvi = image.select('NDVI')

    fpar = (ndvi.multiply(1.257)
            .subtract(0.161)
            .clamp(0, 0.95)
            .rename('FPAR'))

    return image.addBands(fpar)


# ==============================================================
# 2. APAR — Absorbed PAR
# ==============================================================

def compute_apar(image):
    """
    APAR — o'simlik tomonidan yutilgan fotosintez radiatsiyasi.

    APAR = FPAR × PAR  (W/m²)
    PAR = 0.48 × Rs24  (quyosh radiatsiyasining 48% i)

    Rs24 — ERA5 kunlik quyosh radiatsiyasi (allaqachon RN24 bilan birga)
    Biz K_DOWN (lahzali) ni ishlatamiz — kunlik o'rtachaga moslash
    """
    fpar = image.select('FPAR')
    rn24 = image.select('RN24')
    albedo = image.select('ALBEDO')
    tau_sw = image.select('TAU_SW')

    # Rs24 ni RN24 dan tiklash:
    # Rn24 = (1-α)×Rs24 - 110×τsw → Rs24 = (Rn24 + 110×τsw) / (1-α)
    albedo_safe = albedo.max(0.05)
    rs24 = (rn24.add(ee.Image(110.0).multiply(tau_sw))
            .divide(ee.Image(1.0).subtract(albedo_safe))
            .max(0))

    par = rs24.multiply(PAR_FRACTION)  # W/m²
    apar = fpar.multiply(par).rename('APAR')

    return image.addBands(par.rename('PAR')).addBands(apar)


# ==============================================================
# 3. STRESS FACTORS — LUE ni kamaytiruvchi omillar
# ==============================================================

def compute_stress_factors(image):
    """
    3 ta stress omili — LUE ni kamaytiradi.

    1. Heat stress (issiqlik):
       f_heat = 1 - ((LST - T_opt) / (T_opt - T_cold))²
       T_opt = 25°C (optimal harorat)
       T_cold = 5°C

    2. Vapor stress (quruq havo):
       f_vapor = 1 - VPD × k_vpd
       k_vpd = 0.2 (kPa⁻¹)

    3. Moisture stress:
       f_moisture = ETact / ETpot (allaqachon hisoblangan)

    Har bir factor: 0 (to'liq stress) — 1 (stress yo'q)
    """
    # lst = image.select('LST').subtract(273.15)  # Kelvin → Celsius
    
    # AIR_TEMP ishlatamiz — LST emas!
    # LST tuproq yuzasi temp (55°C cho'lda), Ta havo temp (35°C)
    # MODIS GPP ham Ta ishlatadi
    lst = image.select('AIR_TEMP').subtract(273.15)
    
    vpd = image.select('VPD')
    moisture_stress = image.select('MOISTURE_STRESS')

    # Heat stress
    t_opt = 25.0
    t_cold = 5.0
    heat_stress = (lst.subtract(t_opt)
                   .divide(t_opt - t_cold)
                   .pow(2)
                   .multiply(-1).add(1)
                   .clamp(0.05, 1.0)
                   .rename('HEAT_STRESS'))

    # Vapor stress
    k_vpd = 0.2
    vapor_stress = (vpd.multiply(k_vpd)
                    .multiply(-1).add(1)
                    .clamp(0.05, 1.0)
                    .rename('VAPOR_STRESS'))

    image = image.addBands(heat_stress)
    image = image.addBands(vapor_stress)

    return image


# ==============================================================
# 4. LUE — Light Use Efficiency
# ==============================================================

def compute_lue(image):
    """
    Nur foydalanish samaradorligi.

    LUE = LUEmax × f_heat × f_vapor × f_moisture  (g C / MJ PAR)

    LUEmax = 2.5 g C / MJ PAR (C3 ekinlar o'rtachasi)
    Stress omillari LUE ni kamaytiradi.
    """
    heat = image.select('HEAT_STRESS')
    vapor = image.select('VAPOR_STRESS')
    moisture = image.select('MOISTURE_STRESS')

    lue = (ee.Image(LUEMAX)
           .multiply(heat)
           .multiply(vapor)
           .multiply(moisture)
           .rename('LUE'))

    return image.addBands(lue)


# ==============================================================
# 5. BIOMASS PRODUCTION
# ==============================================================

def compute_biomass(image):
    """
    Quruq modda hosildorligi.

    Biomass = APAR × LUE × conversion  (kg/ha/day)

    Konversiya: W/m² × g_C/MJ × 0.864 × C_to_DM
    0.864 = 86400s / 1e6 × 10000 m²/ha / 1000 g/kg × correction
    C_to_DM = 2.0 (karbon → quruq modda)

    Soddalashtirilgan: Biomass = APAR × LUE × 0.864 × 2
    APAR (W/m²), LUE (g C / MJ), natija: kg DM / ha / day
    """
    apar = image.select('APAR')
    lue = image.select('LUE')

    # APAR W/m² → MJ/m²/day
    apar_mj = apar.multiply(0.0864)

    # Biomass (g C / m² / day)
    bio_c = apar_mj.multiply(lue)

    # g C → kg DM / ha / day
    # × C_TO_DM (2.0) × 10 (g/m² → kg/ha) / 1000 (g → kg) × 10000 (m² → ha)
    # = × 2.0 × 10 = × 20
    # Lekin: g/m² × 10 = kg/ha, × C_TO_DM = ×2
    biomass = (bio_c.multiply(10.0)  # g/m² → kg/ha
               .multiply(C_TO_DM)    # C → DM
               .max(0)
               .rename('BIOMASS_PROD'))

    return image.addBands(biomass)


# ==============================================================
# 6. WATER PRODUCTIVITY
# ==============================================================

def compute_water_productivity(image):
    """
    Suv unumdorligi — qancha suv → qancha hosil.

    WP = Biomass / (ET × 10)  (kg/m³)

    ET mm/day × 10 = m³/ha/day (1 mm = 10 m³/ha)
    WP oralig'i: 0.5-3.0 kg/m³ (ko'p ekinlar uchun)

    Biomass_deficit = Biomass_pot - Biomass_act
    Biomass_pot = APAR × LUEmax × conversion (stresssiz)
    """
    biomass = image.select('BIOMASS_PROD')
    et_24 = image.select('ET_24')
    apar = image.select('APAR')

    # Water productivity
    et_m3 = et_24.multiply(10.0).max(0.1)  # mm → m³/ha, div/0 himoya
    wp = (biomass.divide(et_m3)
          .clamp(0, 10.0)
          .rename('WATER_PRODUCTIVITY'))

    # Biomass potential (stresssiz)
    apar_mj = apar.multiply(0.0864)
    biomass_pot = (apar_mj.multiply(LUEMAX)
                   .multiply(10.0)
                   .multiply(C_TO_DM)
                   .max(0)
                   .rename('BIOMASS_POT'))

    # Biomass deficit
    bio_deficit = (biomass_pot.subtract(biomass)
                   .max(0)
                   .rename('BIOMASS_DEFICIT'))

    image = image.addBands(wp)
    image = image.addBands(biomass_pot)
    image = image.addBands(bio_deficit)

    return image


# ==============================================================
# MAIN
# ==============================================================

def compute_all(image):
    """
    Barcha biomassa va suv unumdorligi hisoblash.

    Yangi bandlar:
      FPAR, PAR, APAR,
      HEAT_STRESS, VAPOR_STRESS, LUE,
      BIOMASS_PROD, BIOMASS_POT, BIOMASS_DEFICIT,
      WATER_PRODUCTIVITY
    """
    image = compute_fpar(image)
    image = compute_apar(image)
    image = compute_stress_factors(image)
    image = compute_lue(image)
    image = compute_biomass(image)
    image = compute_water_productivity(image)

    return image
