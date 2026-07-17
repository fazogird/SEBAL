"""
SEBAL-GEE v4 — Run Script
===========================
python run_sebal.py
"""

import ee
from sebal_gee_v4 import main
from sebal_gee_v4 import ee_utils
ee_utils.install_getinfo_retry()   # 429 "Too many concurrent" da avtomatik retry
ee.Initialize(project="carbon-science-461016-q2")    # "carbon-science-461016-q2","ee-chexovant11"



# ==============================================================
# QASHQADARYO — 2026 Mart
# ==============================================================

# result = main.run(
#     # ROI
#     roi_type='gaul',
#     name='Kashkadarya',
#     level=1,

#     # Sana
#     date_start='2026-03-01',
#     date_end='2026-03-31',

#     # Mode
#     mode='pysebal',        # 'maqola' yoki 'pysebal'
#     satellite='BOTH',
#     cloud_max=20,

#     # ---- TILE SOZLAMALARI ----
#     process_by_tile=True,                   # True = har tile alohida
#     tiles=[(156, 32), (156, 33)],           # qo'lda tanlash
#     # tiles=None,                           # None = avtomatik aniqlash

#     # ---- KUNLIK ----
#     export_daily=True,      # har sahna multi-band TIF

#     # ---- OYLIK (har biri alohida TIF) ----
#     export_monthly=True,
#     save_et=True,           # ET mm/month
#     save_biomass=True,      # Biomass kg/ha/month
#     save_etref=True,        # ETref mm/month
#     save_tact=True,         # Transpiratsiya mm/month
#     save_eact=True,         # Evaporatsiya mm/month

#     # ---- EXPORT ----
#     folder='SEBAL_Kashkadarya_2026',
#     scale=30,
#     crs='EPSG:32642',
# )


## ==============================================================
# IDAHO — VALIDATSIYA
# ==============================================================

# main.run(
#     roi_type='rectangle',
#     bounds=[-114.24, 43.03, -114.14, 43.13],
#     date_start='2024-07-01', date_end='2024-07-31',
#     mode='pysebal',
#     export_daily=True, export_monthly=True,
#     save_et=True, save_biomass=True,
#     save_etref=True, save_tact=True, save_eact=True,
#     validate=True,
#     folder='SEBAL_Idaho_Validation', crs='EPSG:32611',
# )


# ==============================================================
# QASHQADARYO — 2026 Mart
# ==============================================================
# main.run(
#     roi_type='gaul', name='Kashkadarya', level=1,
#     date_start='2026-03-01', date_end='2026-03-31',
#     mode='pysebal',
#     satellite='BOTH', cloud_max=30,

#     process_by_tile=True,
#     tiles=[(155, 33), (156, 33)],

#     export_daily=True, export_monthly=True,
#     save_et=True, save_biomass=True,
#     save_etref=True, save_tact=True, save_eact=True,

#     validate=False,     # O'zbekiston — OpenET ishlamaydi
#     folder='SEBAL_testtststs_2026-03',
#     scale=30, crs='EPSG:32642',
# )
# ==============================================================
# QASHQADARYO — 2026 Aprel
# ==============================================================
# main.run(
#     roi_type='gaul',
#     name='Kashkadarya',
#     level=1,

#     date_start='2026-03-01',
#     date_end='2026-05-01',

#     mode='pysebal',
#     satellite='BOTH',
#     cloud_max=70,

#     process_by_tile=True,
#     tiles=[(155, 33), (156, 33)],

#     export_daily=True,
#     export_monthly=True,

#     save_et=True,
#     save_biomass=True,
#     save_etref=True,
#     save_tact=True,
#     save_eact=True,

#     validate=False,
#     folder='SEBAL_Qashqadaryo_ET_2026',
#     scale=30,
#     crs='EPSG:32642',
# )
# ==============================================================
# QASHQADARYO — 2026 Aprel
# ==============================================================
# main.run(
#     roi_type='gaul', name='Kashkadarya', level=1,
#     date_start='2026-04-01', date_end='2026-04-30',
#     mode='pysebal',
#     satellite='BOTH', cloud_max=30,

#     process_by_tile=True,
#     tiles=[(155, 33), (156, 33)],

#     export_daily=True, export_monthly=True,
#     save_et=True, save_biomass=True,
#     save_etref=True, save_tact=True, save_eact=True,

#     validate=False,
#     folder='SEBAL_Qash_2026-04',
#     scale=30, crs='EPSG:32642',
# )

# ==============================================================
# SAMARQAND — 2026
# ==============================================================
# ---- MART ----
# main.run(
#     roi_type='gaul', name='Samarkand', level=1,
#     date_start='2026-03-01', date_end='2026-03-31',
#     mode='pysebal', satellite='BOTH', cloud_max=70,
#     process_by_tile=True,
#     tiles=[(156, 32), (155, 32), (155, 33)],
#     export_daily=True, export_monthly=True,
#     save_et=True, save_biomass=True,
#     save_etref=True, save_tact=True, save_eact=True,
#     validate=False,
#     folder='SEBAL_Samarqand_2026',
#     scale=30, crs='EPSG:32642',
# )

# # ---- APREL ----
# main.run(
#     roi_type='gaul', name='Samarkand', level=1,
#     date_start='2026-04-01', date_end='2026-04-30',
#     mode='pysebal', satellite='BOTH', cloud_max=70,
#     process_by_tile=True,
#     tiles=[(156, 32), (155, 32), (155, 33)],
#     export_daily=True, export_monthly=True,
#     save_et=True, save_biomass=True,
#     save_etref=True, save_tact=True, save_eact=True,
#     validate=False,
#     folder='SEBAL_Samarqand_2026',
#     scale=30, crs='EPSG:32642',
# )

# ==============================================================
# SAMARQAND — 2026 Mart + Aprel + May
# ==============================================================
# main.run(
#     roi_type='gaul', name='Samarkand', level=1,
#     date_start='2026-05-01', date_end='2026-05-31',
#     mode='pysebal', satellite='BOTH', cloud_max=70,
#     process_by_tile=True,
#     tiles=[(156, 32), (155, 32), (155, 33)],
#     export_daily=False, export_monthly=True,
#     save_et=True, save_biomass=True,
#     save_etref=True, save_tact=True, save_eact=True,
#     validate=False,
#     folder='SEBAL_May_Samarqand_2026',
#     scale=30, crs='EPSG:32642',
# )

# ==============================================================
# FARG'ONA — 2026 Mart + Aprel + May
# ==============================================================
# main.run(
#     roi_type='gaul', name='Fergana', level=1,
#     date_start='2026-05-01', date_end='2026-05-31',
#     mode='pysebal', satellite='BOTH', cloud_max=70,
#     process_by_tile=True,
#     tiles=[(153, 32), (152, 32)],
#     export_daily=True, export_monthly=True,
#     save_et=True, save_biomass=True,
#     save_etref=True, save_tact=True, save_eact=True,
#     validate=False,
#     folder='SEBAL_May_Fargona_2026',
#     scale=30, crs='EPSG:32642',
# )

# ==============================================================
# Qashqadaryo — 2026 Mart + Aprel + May
# ==============================================================
# main.run(
#     roi_type='gaul', name='Kashkadarya', level=1,
#     date_start='2026-05-01', date_end='2026-05-31',
#     mode='pysebal', satellite='BOTH', cloud_max=70,
#     process_by_tile=True,
#     tiles=[(156, 33), (155, 33)],
#     export_daily=False, export_monthly=True,
#     save_et=True, save_biomass=True,
#     save_etref=True, save_tact=True, save_eact=True,
#     validate=False,
#     folder='SEBAL_May_Qashqadaryo_2026',
#     scale=30, crs='EPSG:32642',
# )

# # ==============================================================
# # Idaho — 2026 Mart + Aprel
# # ==============================================================
main.run(
    roi_type='gaul', name='Idaho', level=1,
    date_start='2025-03-01', date_end='2025-11-01',
    mode='pysebal', satellite='BOTH', cloud_max=70,
    process_by_tile=True,
    tiles=[(40, 30)],
    export_daily=False, export_monthly=True,
    save_et=True, save_biomass=True,
    save_etref=True, save_tact=True, save_eact=True,
    validate=False,
    folder='SEBAL_Idaho_covergent_2025',
    scale=30, crs='EPSG:32611',

    # ---- ANCHOR TANLASH (beton kaskad) ----
    # 'default'  | 'cimec' | 'plan_a' | 'plan_b' | 'pysebal' | 'cascade'
    # Nomlangan metod birinchi sinaladi, keyin qolganlari (ekin→ROI),
    # hech biri chiqmasa 'default' fallback. Har qadam log'da chiqadi.
    anchor_method='cascade',

    # ---- VIIRS DOWNSCALING (ixtiyoriy, 500m) ----
    use_viirs=False,          # True → oylik ET VIIRS bilan kuchaytiriladi
    viirs_mode='lambda',     # 'lambda' (EVAP_FRAC) yoki 'kc' (KC)
    viirs_model='multi',     # 'ndvi' | 'ndvi2' | 'multi'
    viirs_qa='lenient',      # 'lenient' | 'strict'
    viirs_fill='linear',     # 'linear' | 'nearest'
    viirs_crs='EPSG:32611',  # 30m fine grid CRS — Idaho = UTM 11N.
    #                         None qoldirsangiz avtomatik `crs`ga tushadi.
)

# ==============================================================
# SIRDARYO — HLS bilan
# ==============================================================
# main.run(
#     roi_type='gaul', name='Sirdarya', level=1,
#     date_start='2026-06-01', date_end='2026-06-30',
#     mode='pysebal',
#     satellite='HLS',              # ← HLS!
#     cloud_max=70,
#     process_by_tile=True,
#     tiles=['T42TVK', 'T42TVL'],   # ← MGRS tilelar (string!)
#     export_daily=True, export_monthly=True,
#     save_et=True, save_biomass=True,
#     save_etref=True, save_tact=True, save_eact=True,
#     validate=False,
#     folder='SEBAL_HLS_Sirdaryo_test_2026',
#     scale=30, crs='EPSG:32642',
#      # ---- VIIRS DOWNSCALING (ixtiyoriy, 500m) ----
#     use_viirs=False,       # True → oylik ET VIIRS bilan kuchaytiriladi
#     viirs_mode='lambda',    # 'lambda' (EVAP_FRAC) yoki 'kc' (KC)
#     viirs_model='multi',    # 'ndvi' | 'ndvi2' | 'multi'
#     viirs_qa='lenient',     # 'lenient' | 'strict'
#     viirs_fill='linear',    # 'linear' | 'nearest'

# #     # ---- HLS S30 ETrF REGRESSIYA (ixtiyoriy, 30m — tavsiya) ----
#     use_s30_etrf=False,      # True → oylik ET HLS S30 ETrF regressiya bilan
#     s30_model='multi6',    # 'ndvi'|'ndvi2'|'multi'|'multi6'(NDVI+SAVI+NDWI+LSWI+Albedo)
#     s30_qa='lenient',       # 'lenient' | 'strict'
#     s30_fill='linear',      # 'linear' | 'nearest' (per-pixel)
#     s30_cropland_only=False, # True → yakuniy ET faqat ekin maydoniga
#     s30_validate=False,     # True → hold-out validatsiya CSV
# )

# ==============================================================
# QASHQADARYO — 2026 May, HLS
# ==============================================================
# main.run(
#     roi_type='gaul', name='Kashkadarya', level=1,
#     date_start='2026-05-01', date_end='2026-05-31',
#     mode='pysebal',  ## 'maqola' yoki 'pysebal'
#     satellite='HLS',
#     cloud_max=70,
#     process_by_tile=True,
#     tiles=[
#         'T41SPC', 'T41SPD',
#         'T41SQC', 'T41SQD',
#         'T42STH', 'T42STJ',
#         'T42SUH', 'T42SUJ',
#     ],
#     export_daily=False, export_monthly=True,
#     save_et=True, save_biomass=True,
#     save_etref=True, save_tact=True, save_eact=True,
#     validate=False,
#     folder='SEBAL_HLS_Qashqadaryo_2026-05',
#     scale=30, crs='EPSG:32642',

#     # ---- VIIRS DOWNSCALING (ixtiyoriy, 500m) ----
#     use_viirs=False,       # True → oylik ET VIIRS bilan kuchaytiriladi
#     viirs_mode='lambda',    # 'lambda' (EVAP_FRAC) yoki 'kc' (KC)
#     viirs_model='multi',    # 'ndvi' | 'ndvi2' | 'multi'
#     viirs_qa='lenient',     # 'lenient' | 'strict'
#     viirs_fill='linear',    # 'linear' | 'nearest'

#     # ---- HLS S30 ETrF REGRESSIYA (ixtiyoriy, 30m — tavsiya) ----
#     use_s30_etrf=False,      # True → oylik ET HLS S30 ETrF regressiya bilan
#     s30_model='multi6',    # 'ndvi'|'ndvi2'|'multi'|'multi6'(NDVI+SAVI+NDWI+LSWI+Albedo)
#     s30_qa='lenient',       # 'lenient' | 'strict'
#     s30_fill='linear',      # 'linear' | 'nearest' (per-pixel)
#     s30_cropland_only=False, # True → yakuniy ET faqat ekin maydoniga
#     s30_validate=False,     # True → hold-out validatsiya CSV
# )
