"""
SEBAL-GEE v4 — Irrigation Classification (mode="pysebal")
===========================================================
Sug'orish ehtiyojini klassifikatsiya qilish.

Klasslar:
  0 = Kerak emas (suv yetarli)
  1 = Ehtimol kerak (kuzatish)
  2 = Sug'orish kerak (stress boshlangan)
  3 = Darhol sug'orish kerak (kuchli stress)

Asoslanishi:
  - moisture_stress = ETact / ETpot
  - ET_deficit = ETpot - ETact
  - Tuproq namligi vs stress trigger
  - NDVI holati

Source: pySEBAL v3.8, FAO-56 irrigation scheduling
"""

import ee
from . import config as cfg


# ==============================================================
# IRRIGATION THRESHOLDS
# ==============================================================

IRRIGATION_THRESHOLDS = {
    'stress_none': 0.85,       # ms > 0.85 → stress yo'q
    'stress_mild': 0.65,       # 0.65 < ms < 0.85 → engil stress
    'stress_moderate': 0.45,   # 0.45 < ms < 0.65 → o'rtacha stress
    # ms < 0.45 → kuchli stress

    'deficit_low': 1.0,        # ET_deficit < 1 mm/day → past
    'deficit_high': 3.0,       # ET_deficit > 3 mm/day → yuqori

    'ndvi_bare': 0.15,         # NDVI < 0.15 → yalang'och tuproq
}


# ==============================================================
# 1. IRRIGATION NEEDS CLASSIFICATION
# ==============================================================

def classify_irrigation(image):
    """
    Sug'orish ehtiyoji klassifikatsiyasi.

    Mantiq (FAO-56 asosida):
      moisture_stress > 0.85 → Klass 0 (kerak emas)
      moisture_stress 0.65-0.85 → Klass 1 (ehtimol)
      moisture_stress 0.45-0.65 → Klass 2 (kerak)
      moisture_stress < 0.45 → Klass 3 (darhol)

    Qo'shimcha shartlar:
      - NDVI < 0.15 → 0 (yalang'och tuproq — ekin yo'q)
      - Suv piksellar → 0
      - ET_deficit ham hisobga olinadi

    Natija: 0-3 qiymatli klassifikatsiya xaritasi
    """
    th = IRRIGATION_THRESHOLDS

    ms = image.select('MOISTURE_STRESS')
    et_deficit = image.select('ET_DEFICIT')
    ndvi = image.select('NDVI')

    # Asosiy klassifikatsiya — moisture stress bo'yicha
    irr_class = (
        ee.Image(3)                                          # default: darhol
        .where(ms.gte(th['stress_moderate']), 2)             # o'rtacha
        .where(ms.gte(th['stress_mild']), 1)                 # engil
        .where(ms.gte(th['stress_none']), 0)                 # kerak emas
    )

    # ET deficit bilan tuzatma
    # Agar ms o'rtacha lekin deficit katta → klass ko'tarish
    irr_class = irr_class.where(
        irr_class.eq(2).And(et_deficit.gt(th['deficit_high'])),
        3  # darhol
    )

    # Agar ms engil lekin deficit juda past → klass tushirish
    irr_class = irr_class.where(
        irr_class.eq(1).And(et_deficit.lt(th['deficit_low'])),
        0  # kerak emas
    )

    # Yalang'och tuproq / suv → 0 (sug'orish ahamiyatsiz)
    irr_class = irr_class.where(ndvi.lt(th['ndvi_bare']), 0)

    irr_class = irr_class.rename('IRRIGATION_CLASS')

    return image.addBands(irr_class)


# ==============================================================
# 2. IRRIGATION DEPTH — qancha suv kerak
# ==============================================================

# def compute_irrigation_depth(image):
#     """
#     Sug'orish me'yori — qancha suv berish kerak (mm).

#     Sodda yondashuv:
#       irr_depth = ET_deficit × days_ahead
#       days_ahead = 7 (bir haftalik rejalashtirish)

#     Aniqroq (tuproq namligi bilan):
#       irr_depth = (θ_fc - θ_actual) × root_depth × 1000
#       root_depth ≈ 0.3 + 0.5 × (LAI/6)  (m)

#     Natija: mm (sug'orish uchun kerakli suv miqdori)
#     """
#     et_deficit = image.select('ET_DEFICIT')
#     root_sm = image.select('ROOT_ZONE_MOISTURE')
#     theta_fc = image.select('THETA_FC_SUB')
#     lai = image.select('LAI')

#     # Ildiz chuqurligi (m)
#     root_depth = (lai.divide(6.0)
#                   .multiply(0.5)
#                   .add(0.3)
#                   .clamp(0.3, 1.2))

#     # Tuproq namlik defitsiti (mm)
#     sm_deficit = (theta_fc.subtract(root_sm)
#                   .max(0)
#                   .multiply(root_depth)
#                   .multiply(1000.0))  # m³/m³ × m × 1000 = mm

#     # ET-based (haftalik)
#     et_based = et_deficit.multiply(7.0)

#     # Ikkalasining maksimumi
#     irr_depth = sm_deficit.max(et_based).max(0).rename('IRRIGATION_DEPTH')

#     return image.addBands(irr_depth)


def compute_irrigation_depth(image):
    wetness = image.select('SM_WETNESS')
    et_deficit = image.select('ET_DEFICIT')
    
    sm_depth = (ee.Image(0.5).subtract(wetness)
                .max(0).multiply(300.0))
    et_depth = et_deficit.multiply(7.0)
    
    irr_depth = sm_depth.max(et_depth).max(0).rename('IRRIGATION_DEPTH')
    return image.addBands(irr_depth)

# ==============================================================
# 3. IRRIGATION EFFICIENCY INDICATOR
# ==============================================================

# def compute_irrigation_efficiency(image):
#     """
#     Sug'orish samaradorligi ko'rsatkichi.

#     eff = beneficial_fraction × (1 - deep_perc_fraction)

#     beneficial_fraction = Tact / ETact (allaqachon hisoblangan)
#     deep_perc_fraction ≈ max(0, (θ - θ_fc) / (θ_sat - θ_fc))

#     Yuqori eff → suv samarali ishlatilmoqda
#     Past eff → suv isrof bo'lmoqda (evaporatsiya yoki chuqur sizish)
#     """
#     beneficial = image.select('BENEFICIAL_FRACTION')
#     root_sm = image.select('ROOT_ZONE_MOISTURE')
#     theta_fc = image.select('THETA_FC_SUB')
#     theta_sat = image.select('THETA_SAT_SUB')

#     # Deep percolation fraction
#     deep_perc = (root_sm.subtract(theta_fc)
#                  .divide(theta_sat.subtract(theta_fc).max(0.01))
#                  .clamp(0, 1.0))

#     # Efficiency
#     irr_eff = (beneficial
#                .multiply(ee.Image(1.0).subtract(deep_perc))
#                .clamp(0, 1.0)
#                .rename('IRRIGATION_EFFICIENCY'))

#     return image.addBands(irr_eff)

def compute_irrigation_efficiency(image):
    beneficial = image.select('BENEFICIAL_FRACTION')
    wetness = image.select('SM_WETNESS')
    
    over_saturation = wetness.subtract(0.85).max(0).divide(0.15).clamp(0, 1)
    
    irr_eff = (beneficial
               .multiply(ee.Image(1.0).subtract(over_saturation))
               .clamp(0, 1.0)
               .rename('IRRIGATION_EFFICIENCY'))
    return image.addBands(irr_eff)


# ==============================================================
# MAIN
# ==============================================================

def compute_all(image):
    """
    Barcha irrigation analitikalarini hisoblash.

    Yangi bandlar:
      IRRIGATION_CLASS (0-3),
      IRRIGATION_DEPTH (mm),
      IRRIGATION_EFFICIENCY (0-1)
    """
    image = classify_irrigation(image)
    image = compute_irrigation_depth(image)
    image = compute_irrigation_efficiency(image)

    return image
