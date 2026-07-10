# """  
# SEBAL-GEE v4 — Soil Moisture (mode="pysebal")
# ===============================================
# Tuproq namligi va stress koeffitsientlarini hisoblash.

# Inputlar:
#   - SEBAL: ET_24, EVAP_FRAC, ETPOT_24
#   - Surface: LAI, NDVI, vegt_cover
#   - Tuproq bazasi: OpenLandMap/SoilGrids (GEE da)

# Tuproq parametrlari:
#   - θ_sat — saturatsiya namligi (cm³/cm³)
#   - θ_fc  — dala sig'imi (field capacity, -33 kPa)
#   - θ_wp  — so'lish nuqtasi (wilting point, -1500 kPa)
#   - θ_res — qoldiq namlik (residual)

# Source: pySEBAL v3.8, FAO-56
# """

# import ee
# from . import config as cfg


# # ==============================================================
# # SOIL DATA SOURCES (GEE)
# # ==============================================================

# SOIL_COLLECTIONS = {
#     'fc_top':  'OpenLandMap/SOL/SOL_WATERCONTENT-33KPA_USDA-4B1C_M/v01',
#     'wp_top':  'OpenLandMap/SOL/SOL_WATERCONTENT-1500KPA_USDA-4B1C_M/v01',
#     'sand':    'OpenLandMap/SOL/SOL_SAND-WFRACTION_USDA-3A1A1A_M/v02',
#     'clay':    'OpenLandMap/SOL/SOL_CLAY-WFRACTION_USDA-3A1A1A_M/v02',
# }

# # Chuqurlik bandlari: b0=0cm, b10=10cm, b30=30cm, b60=60cm, b100=100cm
# DEPTH_BANDS = {
#     'top': 'b0',     # 0 cm — yuza
#     'sub': 'b30',    # 30 cm — ildiz zonasi
# }


# # ==============================================================
# # 1. TUPROQ PARAMETRLARINI OLISH
# # ==============================================================

# def get_soil_properties(image):
#     """
#     SoilGrids/OpenLandMap dan tuproq parametrlarini olish.

#     θ_fc  — field capacity (% vol → fraction)
#     θ_wp  — wilting point (% vol → fraction)
#     θ_sat — saturatsiya (pedotransfer: θ_sat ≈ 0.332 + 0.0007251×clay - 0.000151×sand)

#     Top soil (0-30 cm) va sub soil (30-100 cm) alohida.
#     """
#     # Field capacity — top va sub
#     fc_img = ee.Image(SOIL_COLLECTIONS['fc_top'])
#     theta_fc_top = (fc_img.select(DEPTH_BANDS['top'])
#                     .divide(100.0)  # % → fraction
#                     .rename('THETA_FC_TOP'))
#     theta_fc_sub = (fc_img.select(DEPTH_BANDS['sub'])
#                     .divide(100.0)
#                     .rename('THETA_FC_SUB'))

#     # Wilting point
#     wp_img = ee.Image(SOIL_COLLECTIONS['wp_top'])
#     theta_wp_top = (wp_img.select(DEPTH_BANDS['top'])
#                     .divide(100.0)
#                     .rename('THETA_WP_TOP'))
#     theta_wp_sub = (wp_img.select(DEPTH_BANDS['sub'])
#                     .divide(100.0)
#                     .rename('THETA_WP_SUB'))

#     # Saturatsiya — pedotransfer function dan
#     sand = ee.Image(SOIL_COLLECTIONS['sand']).select(DEPTH_BANDS['top']).divide(10.0)
#     clay = ee.Image(SOIL_COLLECTIONS['clay']).select(DEPTH_BANDS['top']).divide(10.0)

#     # Saxton & Rawls (2006) simplified
#     theta_sat_top = (ee.Image(0.332)
#                      .add(clay.multiply(0.0007251))
#                      .subtract(sand.multiply(0.000151))
#                      .clamp(0.35, 0.55)
#                      .rename('THETA_SAT_TOP'))

#     sand_sub = ee.Image(SOIL_COLLECTIONS['sand']).select(DEPTH_BANDS['sub']).divide(10.0)
#     clay_sub = ee.Image(SOIL_COLLECTIONS['clay']).select(DEPTH_BANDS['sub']).divide(10.0)

#     theta_sat_sub = (ee.Image(0.332)
#                      .add(clay_sub.multiply(0.0007251))
#                      .subtract(sand_sub.multiply(0.000151))
#                      .clamp(0.35, 0.55)
#                      .rename('THETA_SAT_SUB'))

#     # Residual moisture ≈ 0.5 × wilting point
#     theta_res_top = theta_wp_top.multiply(0.5).rename('THETA_RES_TOP')
#     theta_res_sub = theta_wp_sub.multiply(0.5).rename('THETA_RES_SUB')

#     image = (image
#              .addBands(theta_fc_top).addBands(theta_fc_sub)
#              .addBands(theta_wp_top).addBands(theta_wp_sub)
#              .addBands(theta_sat_top).addBands(theta_sat_sub)
#              .addBands(theta_res_top).addBands(theta_res_sub))

#     return image


# # ==============================================================
# # 2. VEGETATION COVER
# # ==============================================================

# def compute_vegetation_cover(image):
#     """
#     O'simlik qoplami (fraction).

#     vegt_cover = 1 - (NDVI_max - NDVI)² / (NDVI_max - NDVI_min)²

#     Soddalashtirilgan: vegt_cover ≈ NDVI (normalized 0-1)
#     """
#     ndvi = image.select('NDVI')

#     vegt_cover = (ndvi.subtract(0.1)
#                   .divide(0.7)  # 0.1-0.8 oraliq → 0-1
#                   .clamp(0, 1.0)
#                   .rename('VEGT_COVER'))

#     return image.addBands(vegt_cover)


# # ==============================================================
# # 3. SOIL MOISTURE ESTIMATION
# # ==============================================================

# def compute_soil_moisture(image):
#     """
#     Tuproq namligini ET va EF dan baholash.

#     Yondashuv (pySEBAL):
#       1. Effective saturation: Se = (θ - θ_res) / (θ_sat - θ_res)
#       2. ET / ETpot ≈ f(Se) — teskari munosabat
#       3. Se dan θ ni tiklash

#     Top soil moisture:
#       Se_top = EF ^ (1 / depletion_factor)
#       θ_top = Se_top × (θ_sat - θ_res) + θ_res

#     Root zone moisture:
#       Se_rz = polynomial(moisture_stress)
#       θ_rz = Se_rz × (θ_fc - θ_res) + θ_res

#     depletion_factor = 0.4 (FAO-56 default, ko'p ekinlar uchun)
#     """
#     ef = image.select('EVAP_FRAC')
#     moisture_stress = image.select('MOISTURE_STRESS')
#     vegt_cover = image.select('VEGT_COVER')

#     theta_sat_top = image.select('THETA_SAT_TOP')
#     theta_res_top = image.select('THETA_RES_TOP')
#     theta_fc_sub = image.select('THETA_FC_SUB')
#     theta_res_sub = image.select('THETA_RES_SUB')
#     theta_wp_sub = image.select('THETA_WP_SUB')

#     # ---- Top soil moisture ----
#     depl_factor = 0.4
#     se_top = ef.pow(1.0 / depl_factor).clamp(0, 1.0)

#     top_sm = (se_top
#               .multiply(theta_sat_top.subtract(theta_res_top))
#               .add(theta_res_top)
#               .rename('TOP_SOIL_MOISTURE'))

#     # ---- Root zone moisture ----
#     # Polynomial (pySEBAL): Se = 2.23×ms³ - 3.35×ms² + 1.98×ms + 0.07
#     ms = moisture_stress
#     se_rz = (ms.pow(3).multiply(2.23)
#              .add(ms.pow(2).multiply(-3.35))
#              .add(ms.multiply(1.98))
#              .add(0.07)
#              .clamp(0, 1.0))

#     root_sm = (se_rz
#                .multiply(theta_fc_sub.subtract(theta_res_sub))
#                .add(theta_res_sub)
#                .rename('ROOT_ZONE_MOISTURE'))

#     # ---- SM stress trigger ----
#     # Stress boshlanadigan namlik darajasi (FAO-56)
#     # p = depletion_factor → θ_trigger = θ_fc - p × (θ_fc - θ_wp)
#     sm_trigger = (theta_fc_sub
#                   .subtract(
#                       theta_fc_sub.subtract(theta_wp_sub)
#                       .multiply(depl_factor))
#                   .rename('SM_STRESS_TRIGGER'))

#     # ---- Total soil moisture ----
#     total_sm = (top_sm.multiply(ee.Image(1).subtract(vegt_cover))
#                 .add(root_sm.multiply(vegt_cover))
#                 .rename('TOTAL_SOIL_MOISTURE'))

#     image = (image
#              .addBands(top_sm)
#              .addBands(root_sm)
#              .addBands(sm_trigger)
#              .addBands(total_sm))

#     return image


# # ==============================================================
# # MAIN
# # ==============================================================

# def compute_all(image):
#     """
#     Barcha tuproq namligi analitikalarini hisoblash.

#     Yangi bandlar:
#       THETA_FC_TOP/SUB, THETA_WP_TOP/SUB, THETA_SAT_TOP/SUB, THETA_RES_TOP/SUB,
#       VEGT_COVER,
#       TOP_SOIL_MOISTURE, ROOT_ZONE_MOISTURE, SM_STRESS_TRIGGER, TOTAL_SOIL_MOISTURE
#     """
#     image = get_soil_properties(image)
#     image = compute_vegetation_cover(image)
#     image = compute_soil_moisture(image)

#     return image
  
  
"""
SEBAL-GEE v4 — Soil Moisture (SMAP-based)
===========================================
NASA SMAP L4 dan haqiqiy tuproq namligi olish.

Avvalgisi: ET/EF dan taxmin qilish (murakkab, noaniq)
Hozirgi:   SMAP haqiqiy o'lchov (sodda, aniq)

SMAP: 3 soatlik, 11km, 2015-hozir
"""

import ee
from . import config as cfg

SMAP_COLLECTION = 'NASA/SMAP/SPL4SMGP/008'


def get_smap_for_image(image, roi):
    """
    Landsat vaqtiga ENG YAQIN SMAP olish.
    O'rtacha EMAS — eng yaqin bitta o'lchov.
    SMAP har 3 soatda — eng ko'pi 1.5 soat farq bo'ladi.
    """
    date = ee.Date(image.get('system:time_start'))

    smap = (ee.ImageCollection(SMAP_COLLECTION)
            .filterDate(date.advance(-3, 'hour'), date.advance(3, 'hour'))
            .filterBounds(roi))

    # Eng yaqin vaqtdagi tasvirni olish (o'rtacha emas!)
    def add_time_diff(smap_img):
        diff = ee.Number(smap_img.get('system:time_start')).subtract(date.millis()).abs()
        return smap_img.set('time_diff', diff)

    closest = (smap.map(add_time_diff)
               .sort('time_diff')
               .first())

    top_sm = closest.select('sm_surface').rename('TOP_SOIL_MOISTURE')
    root_sm = closest.select('sm_rootzone').rename('ROOT_ZONE_MOISTURE')
    root_wetness = closest.select('sm_rootzone_wetness').rename('SM_WETNESS')

    image = image.addBands(top_sm)
    image = image.addBands(root_sm)
    image = image.addBands(root_wetness)

    return image


def compute_stress_from_smap(image):
    """
    SMAP wetness dan moisture stress hisoblash.

    SM_WETNESS: 0 = quruq, 1 = to'yingan
    Stress trigger: wetness < 0.4 → stress boshlanadi
    """
    wetness = image.select('SM_WETNESS')

    # Stress trigger — FAO-56 p = 0.4
    sm_trigger = ee.Image(0.4).rename('SM_STRESS_TRIGGER')

    # Moisture stress biomass uchun
    # stress = 0 (to'liq stress) — 1 (stress yo'q)
    # wetness < 0.4 → stress boshlanadi
    stress = (wetness.divide(0.4)
              .clamp(0, 1.0)
              .rename('MOISTURE_STRESS_SMAP'))

    image = image.addBands(sm_trigger)
    image = image.addBands(stress)

    return image


def compute_all(image):
    """SMAP tuproq namligi + stress."""
    roi_geom = image.geometry()
    image = get_smap_for_image(image, roi_geom)
    image = compute_stress_from_smap(image)
    return image  
  
  
  
