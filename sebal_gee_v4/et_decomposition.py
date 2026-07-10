"""
SEBAL-GEE v4 — ET Decomposition (mode="pysebal")
===================================================
Bug'lanishni komponentlarga ajratish va qo'shimcha analitikalar.

Hisoblash tartibi:
  1. ETref_24   — FAO-56 Penman-Monteith reference ET (grass)
  2. ETpot_24   — Potensial ET (haqiqiy o'simlik uchun)
  3. Advection Factor
  4. kc, kc_max — ekin koeffitsientlari
  5. ET_deficit — suv tanqisligi
  6. E/T Separation — evaporatsiya vs transpiratsiya
  7. T_deficit, beneficial_fraction

Kerakli inputlar:
  - SEBAL natijasi: ET_24, EVAP_FRAC, RN, G0, H, LAMBDA_E, RN24
  - Surface props: NDVI, LAI, ALBEDO, Z0M, LST
  - ERA5: AIR_TEMP, PRESSURE, wind, dewpoint
  - config parametrlari

Manba: FAO-56 (Allen et al. 1998),
"""

import ee
from . import config as cfg


# ==============================================================
# CONSTANTS
# ==============================================================

SIGMA = cfg.STEFAN_BOLTZMANN      # 5.67e-8 W/m²/K⁴
CP = cfg.CP_AIR                   # 1004 J/kg/K
LAMBDA_V = cfg.LAMBDA_V           # 2.45e6 J/kg
K_VK = cfg.VON_KARMAN             # 0.41


# ==============================================================
# 1. VAPOR PRESSURE — ERA5 dan
# ==============================================================

def compute_vapor_pressure(image):
    """
    Saturatsiya va haqiqiy bug' bosimi hisoblash.

    esat = 0.6108 × exp(17.27 × T / (T + 237.3))  [kPa]
    eact = 0.6108 × exp(17.27 × Td / (Td + 237.3)) [kPa]
    VPD  = esat - eact [kPa]

    T  — ERA5 air temperature (K → °C)
    Td — ERA5 dewpoint temperature (K → °C)

    slope_es = 4098 × esat / (T + 237.3)²  [kPa/°C]
    """
    ta_k = image.select('AIR_TEMP')
    ta_c = ta_k.subtract(273.15)

    # Dewpoint — ERA5 dan
    # Agar DEWPOINT band bo'lmasa, RH dan hisoblash kerak
    # Hozircha ERA5 dewpoint bor deb faraz qilamiz
    td_k = image.select('DEWPOINT')
    td_c = td_k.subtract(273.15)

    # Saturatsiya bug' bosimi (kPa)
    esat = ta_c.multiply(17.27).divide(ta_c.add(237.3)).exp().multiply(0.6108)

    # Haqiqiy bug' bosimi (kPa)
    eact = td_c.multiply(17.27).divide(td_c.add(237.3)).exp().multiply(0.6108)

    # VPD
    vpd = esat.subtract(eact).max(0.01).rename('VPD')

    # Slope of saturation vapor pressure curve (kPa/°C)
    slope_es = (esat.multiply(4098.0)
                .divide(ta_c.add(237.3).pow(2))
                .rename('SLOPE_ES'))

    # Psychrometric constant γ = cₚ × P / (ε × λ)
    # ε = 0.622, P in kPa
    pressure_kpa = image.select('PRESSURE').divide(1000.0)
    psychro = pressure_kpa.multiply(0.000665).rename('PSYCHRO')

    image = image.addBands(esat.rename('ESAT'))
    image = image.addBands(eact.rename('EACT'))
    image = image.addBands(vpd)
    image = image.addBands(slope_es)
    image = image.addBands(psychro)

    return image


# ==============================================================
# 2. ETref_24 — FAO-56 Penman-Monteith Reference ET
# ==============================================================

def compute_etref(image):
    """
    FAO-56 grass reference ET (mm/day).

    ETref = [0.408 × Δ × (Rn24 - G24) + γ × 900/(Ta+273) × u₂ × VPD]
            / [Δ + γ × (1 + 0.34 × u₂)]

    G24 ≈ 0 (kunlik uchun)
    u₂ — 2m balandlikdagi shamol tezligi
    Rn24 — 24 soatlik sof radiatsiya (W/m² → MJ/m²/day)

    Source: Allen et al. (1998) FAO Irrigation & Drainage Paper 56
    """
    rn24 = image.select('RN24')
    slope_es = image.select('SLOPE_ES')
    psychro = image.select('PSYCHRO')
    vpd = image.select('VPD')
    ta_c = image.select('AIR_TEMP').subtract(273.15)

    # Wind speed — ERA5 10m → 2m
    # u₂ = u₁₀ × 4.87 / ln(67.8 × 10 - 5.42)
    # u₂ = u₁₀ × 4.87 / 6.536 ≈ u₁₀ × 0.745
    wind_2m = image.select('WIND_SPEED_10M').multiply(0.745).max(0.5)

    # Rn24 W/m² → MJ/m²/day
    rn24_mj = rn24.multiply(0.0864)  # × 86400 / 1e6

    # G24 ≈ 0 kunlik uchun
    # FAO-56 formulasi
    numerator_rad = slope_es.multiply(0.408).multiply(rn24_mj)
    numerator_wind = (psychro.multiply(900.0)
                      .divide(ta_c.add(273.0))
                      .multiply(wind_2m)
                      .multiply(vpd))

    denominator = (slope_es
                   .add(psychro.multiply(wind_2m.multiply(0.34).add(1.0))))

    etref = (numerator_rad.add(numerator_wind)
             .divide(denominator)
             .max(0)
             .rename('ETREF_24'))

    return image.addBands(etref)


# ==============================================================
# 3. ETpot_24 — Potential ET (haqiqiy o'simlik uchun)
# ==============================================================

def compute_etpot(image):
    """
    Potensial ET — o'simlik suvga to'yingan sharoitda.

    Penman-Monteith bilan, lekin:
    - rs_min (minimal stomatal resistance) ishlatiladi
    - rah PM (Penman-Monteith) uchun alohida hisoblanadi
    - dT = 4°C (potensial sharoit uchun standart)

    rs_min = 100 / LAI (s/m) — minimal o'simlik qarshiligi
    LAI < 0.5 → rs_min = 200 (yalang'och tuproq)

    ETpot > ETact bo'lishi kerak (aks holda ETact ishlatiladi)
    """
    rn24 = image.select('RN24')
    slope_es = image.select('SLOPE_ES')
    psychro = image.select('PSYCHRO')
    vpd = image.select('VPD')
    ta_c = image.select('AIR_TEMP').subtract(273.15)
    rho_air = image.select('RHO_AIR')
    lai = image.select('LAI')
    z0m = image.select('Z0M')

    # Rn24 → MJ/m²/day
    rn24_mj = rn24.multiply(0.0864)

    # Minimal surface resistance (s/m)
    rs_min = ee.Image(100.0).divide(lai.max(0.5))
    rs_min = rs_min.min(500.0).max(20.0)

    # Aerodynamic resistance for PM — dT=4°C (potensial)
    wind_2m = image.select('WIND_SPEED_10M').multiply(0.745).max(0.5)
    rah_pot = (ee.Image(208.0).divide(wind_2m)).max(25.0)

    # PM formula bilan ETpot
    numerator_rad = slope_es.multiply(0.408).multiply(rn24_mj)

    # VPD termi — rah_pot bilan
    numerator_aero = (rho_air.multiply(CP)
                      .multiply(vpd)
                      .divide(rah_pot)
                      .multiply(86400.0)  # s → day
                      .divide(1e6)  # J → MJ
                      .divide(LAMBDA_V / 1e6))

    denominator = (slope_es
                   .add(psychro.multiply(
                       ee.Image(1.0).add(rs_min.divide(rah_pot)))))

    etpot = (numerator_rad.add(numerator_aero)
             .divide(denominator)
             .max(0)
             .rename('ETPOT_24'))

    # ETpot ≥ ETact bo'lishi kerak
    eta = image.select('ET_24')
    etpot = etpot.max(eta)

    return image.addBands(etpot).addBands(rs_min.rename('RS_MIN'))


# ==============================================================
# 4. ADVECTION FACTOR
# ==============================================================

def compute_advection_factor(image):
    """
    Adveksiya omili — issiq quruq havo ta'siri.

    AF = 1 + 0.985 × [exp((esat-eact) × 0.08) - 1] × EF

    esat-eact > 6 kPa bo'lganda adveksiya kuchli.
    EF (evaporative fraction) yuqori bo'lganda ta'sir katta.

    AF oralig'i: 1.0 (adveksiya yo'q) — 1.5 (kuchli adveksiya)
    """
    vpd = image.select('VPD')
    ef = image.select('EVAP_FRAC')

    af = (vpd.multiply(0.08).exp()
          .subtract(1.0)
          .multiply(0.985)
          .add(1.0)
          .multiply(ef)
          .max(1.0)  # AF ≥ 1 har doim
          .min(1.5)  # AF ≤ 1.5 fizik limit
          .rename('ADV_FACTOR'))

    return image.addBands(af)


# ==============================================================
# 5. CROP COEFFICIENTS — kc, kc_max
# ==============================================================

def compute_crop_coefficients(image):
    """
    Ekin koeffitsientlari.

    kc = ETact / ETref   — haqiqiy ekin koeffitsienti
    kc_max = ETpot / ETref — maksimal (suvga to'yingan)

    kc < 1.0 → ekin stress da yoki siyrak
    kc ≈ 1.0 → reference ga teng (yaxshi sug'orilgan)
    kc > 1.0 → ekin reference dan ko'p bug'latadi (baland ekinlar)

    ET_deficit = ETpot - ETact — suv tanqisligi (mm/day)
    """
    eta = image.select('ET_24')
    etpot = image.select('ETPOT_24')
    etref = image.select('ETREF_24')

    # Division by zero himoyasi
    etref_safe = etref.max(0.5)

    kc = (eta.divide(etref_safe)
          .clamp(0, 2.5)
          .rename('KC'))

    kc_max = (etpot.divide(etref_safe)
              .clamp(0, 2.5)
              .rename('KC_MAX'))

    # ET deficit (mm/day) — suvga bo'lgan ehtiyoj
    et_deficit = (etpot.subtract(eta)
                  .max(0)
                  .rename('ET_DEFICIT'))

    image = image.addBands(kc)
    image = image.addBands(kc_max)
    image = image.addBands(et_deficit)

    return image


# ==============================================================
# 6. E/T SEPARATION — Evaporatsiya va Transpiratsiya
# ==============================================================

def compute_et_separation(image):
    """
    Bug'lanishni ikki komponentga ajratish:

    ET = E (tuproq evaporatsiyasi) + T (o'simlik transpiratsiyasi)

    Transpiratsiya (T):
      Tpot = (1 - exp(-k_ext × LAI)) × ETpot
      Tact = moisture_stress × Tpot
      (hozir moisture_stress = ETact/ETpot deb olamiz,
       keyinroq soil_moisture modulida aniqlashtramiz)

    Evaporatsiya (E):
      Eact = ETact - Tact

    k_ext = 0.6 — nur o'tkazmaslik koeffitsienti (extinction)

    Deficit va foydali fraktsiya:
      T_deficit = Tpot - Tact
      beneficial_fraction = Tact / ETact
    """
    eta = image.select('ET_24')
    etpot = image.select('ETPOT_24')
    lai = image.select('LAI')

    # Extinction coefficient
    k_ext = 0.6

    # Potensial transpiratsiya
    # Tpot = (1 - exp(-k × LAI)) × ETpot
    # Bu Beer-Lambert qonuniga asoslangan — LAI orqali qancha
    # nur o'simlikka tushadi
    canopy_fraction = (lai.multiply(-k_ext).exp()
                       .multiply(-1).add(1))  # 1 - exp(-k×LAI)

    tpot = canopy_fraction.multiply(etpot).rename('TPOT_24')

    # Moisture stress — sodda versiya
    # moisture_stress = ETact / ETpot (0-1)
    # Keyinroq soil_moisture.py da aniqroq hisoblanadi
    etpot_safe = etpot.max(0.1)
    moisture_stress = (eta.divide(etpot_safe)
                       .clamp(0, 1.0)
                       .rename('MOISTURE_STRESS'))

    # Haqiqiy transpiratsiya
    tact = (moisture_stress.multiply(tpot)
            .rename('TACT_24'))

    # Tact ETact dan katta bo'lmasligi kerak
    tact = tact.min(eta)

    # Haqiqiy evaporatsiya (qoldiq)
    eact = (eta.subtract(tact)
            .max(0)
            .rename('EACT_24'))

    # Transpiratsiya defitsiti
    t_deficit = (tpot.subtract(tact)
                 .max(0)
                 .rename('T_DEFICIT'))

    # Foydali fraktsiya (transpiratsiya / jami ET)
    # Transpiratsiya = "foydali" suv (o'simlik o'sishi uchun)
    # Evaporatsiya = "foydasiz" suv (tuproqdan yo'qoladi)
    eta_safe = eta.max(0.01)
    beneficial = (tact.divide(eta_safe)
                  .clamp(0, 1.0)
                  .rename('BENEFICIAL_FRACTION'))

    image = image.addBands(tpot)
    image = image.addBands(tact)
    image = image.addBands(eact)
    image = image.addBands(t_deficit)
    image = image.addBands(moisture_stress)
    image = image.addBands(beneficial)

    return image


# ==============================================================
# MAIN: Compute all ET decomposition
# ==============================================================

def compute_all(image):
    """
    Barcha ET decomposition analitikalarini hisoblash.

    Tartib muhim:
      1. Vapor pressure (esat, eact, VPD, psychro)
      2. ETref (FAO-56 reference)
      3. ETpot (potensial ET)
      4. Advection factor
      5. Crop coefficients (kc, kc_max, ET_deficit)
      6. E/T separation (Tact, Eact, T_deficit, beneficial)

    Input:  Image with SEBAL results + ERA5 + surface props
    Output: Image + 15 yangi band:
      ESAT, EACT, VPD, SLOPE_ES, PSYCHRO,
      ETREF_24, ETPOT_24, RS_MIN,
      ADV_FACTOR,
      KC, KC_MAX, ET_DEFICIT,
      TPOT_24, TACT_24, EACT_24, T_DEFICIT,
      MOISTURE_STRESS, BENEFICIAL_FRACTION

    Kerakli bandlar:
      RN24, ET_24, EVAP_FRAC, LAI, Z0M, LST,
      AIR_TEMP, DEWPOINT, PRESSURE, WIND_SPEED_10M, RHO_AIR
    """
    image = compute_vapor_pressure(image)
    image = compute_etref(image)
    image = compute_etpot(image)
    image = compute_advection_factor(image)
    image = compute_crop_coefficients(image)
    image = compute_et_separation(image)

    return image
