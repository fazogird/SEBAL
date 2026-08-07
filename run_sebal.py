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
# POLYGON ET — AmeriFlux US-NSb (sug'oriladigan paxta, CA) validatsiya
# ==============================================================
# main.run() EMAS — polygon rejimi uchun main.run_polygons() ishlatiladi.
# Tile QO'LDA kiritilmaydi — avtomat aniqlanadi (bu sayt uchun P43_R35).
# Har polygonga ET_2024_04..08 (oylik) + ET_<sana> (har Landsat sahna) zonal
# (mean) yoziladi → GEE asset + Drive CSV (+ ixtiyoriy oylik ET GeoTIFF).
# SEBAL hisob-kitob zanjiri O'ZGARMAGAN.
#
# ⚠️ ESLATMA: 'flux_poly' — SIYRAK dala (2024 NDVI ~0.32). Zich paxta towerdan
#    JANUBDA (NDVI ~0.71, lat ~36.3315-36.3340). To'g'ri footprint uchun o'sha
#    janubiy dalaga polygon chizib, quyidagi polygon_asset ni almashtiring.

# result = main.run_polygons(
#     polygon_asset='projects/ee-chexovant11/assets/flux_poly',  # public (Anyone read)
#     date_start='2024-04-01', date_end='2024-09-01',
#     months=(4, 5, 6, 7, 8), year=2024,
#     mode='SEBAL_B', satellite='BOTH', cloud_max=70,
#     calib_buffer_m=15000,      # kalibratsiya ROI = polygon + ~15 km (cold+hot anchor)
#     inner_buffer_m=-30,        # dala chetidagi aralash pikselni chiqarish
#     anchor_method='cascade', anchor_mode='median_anchor',
#     out_asset='projects/carbon-science-461016-q2/assets/us_nsb_ET_2024',
#     out_folder='SEBAL_Polygon', crs='EPSG:32610',   # SJV → UTM 10N
#     export_rasters=True,       # oylik ET GeoTIFF ham (Drive'dan yuklab ko'rish uchun)
# )


# ==============================================================
# POLYGON ET — AmeriFlux US-Ne1 (Mead, NE — sug'oriladigan makka)
# ==============================================================
# Faqat DALA kerak (butun tile emas) → main.run_polygons() ishlatiladi.
# Kalibratsiya avtomatik keng ROI'da (polygon + 15 km, cold+hot anchor),
# natija FAQAT polygon bo'yicha zonal (mean) → asset + CSV.
# Nebraska: WRS ≈ P28_R31, UTM 14N = EPSG:32614.
#
# Polygon: (A) tower koord + bufer doira (tez, dala chegarasi taxminiy), yoki
#          (B) qo'lda chizib asset qilib, polygon_asset='projects/.../assets/ne1_poly'.

# import ee  # (tepada import qilingan)
# ne1_field = ee.Geometry.Point([-96.4766, 41.1651]).buffer(350)  # (A) 350 m doira
#
# result = main.run_polygons(
#     polygon_asset=ne1_field,          # (A) ee.Geometry — yoki (B) asset ID string
#     date_start='2024-05-01', date_end='2024-10-01',
#     months=(5, 6, 7, 8, 9), year=2024,
#     mode='SEBAL_B', satellite='BOTH', cloud_max=70,
#     calib_buffer_m=15000,     # kalibratsiya ROI = dala + 15 km (cold+hot anchor)
#     inner_buffer_m=0,         # kichik doira uchun 0 (eroziya qilmaydi); katta dala uchun -30
#     anchor_method='cascade', anchor_mode='median_anchor',
#     out_asset='projects/carbon-science-461016-q2/assets/us_ne1_ET_2024',
#     out_folder='SEBAL_Polygon_Ne1', crs='EPSG:32614',   # Nebraska → UTM 14N
#     export_rasters=False,     # True → oylik ET GeoTIFF ham (dala atrofi clip)
# )


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
#     mode='pysebal',        # 'SEBAL_B' yoki 'pysebal'
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
# main.run(
#     roi_type='gaul', name='Idaho', level=1,
#     date_start='2025-03-01', date_end='2025-11-01',
#     mode='SEBAL_B', satellite='BOTH', cloud_max=70,
#     process_by_tile=True,
#     tiles=[(40, 30)],
#     export_daily=False, export_monthly=True,
#     save_et=True, save_biomass=False,
#     save_etref=False, save_tact=False, save_eact=False,
#     validate=False,
#     folder='SEBAL_B_Idaho_2025',
#     scale=30, crs='EPSG:32611',

#     # ---- ANCHOR TANLASH (beton kaskad) ----
#     # 'default'  | 'cimec' | 'plan_a' | 'plan_b' | 'pysebal' | 'cascade'
#     # Nomlangan metod birinchi sinaladi, keyin qolganlari (ekin→ROI),
#     # hech biri chiqmasa 'default' fallback. Har qadam log'da chiqadi.
#     anchor_method='cascade',

#     # ---- VIIRS DOWNSCALING (ixtiyoriy, 500m) ----
#     use_viirs=False,          # True → oylik ET VIIRS bilan kuchaytiriladi
#     viirs_mode='lambda',     # 'lambda' (EVAP_FRAC) yoki 'kc' (KC)
#     viirs_model='multi',     # 'ndvi' | 'ndvi2' | 'multi'
#     viirs_qa='lenient',      # 'lenient' | 'strict'
#     viirs_fill='linear',     # 'linear' | 'nearest'
#     viirs_crs='EPSG:32611',  # 30m fine grid CRS — Idaho = UTM 11N.
#     #                         None qoldirsangiz avtomatik `crs`ga tushadi.
# )

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
#     mode='pysebal',  ## 'SEBAL_B' yoki 'pysebal'
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

# # ==============================================================
# # Idaho — 2026 Mart + Aprel
# # ==============================================================
# main.run(
#     roi_type='gaul', name='Nebraska', level=1,
#     date_start='2022-03-01', date_end='2022-11-01',
#     mode='SEBAL_B', satellite='BOTH', cloud_max=70,
#     process_by_tile=True,
#     tiles=[(28, 31)],
#     export_daily=False, export_monthly=True,
#     save_et=True, save_biomass=False,
#     save_etref=False, save_tact=False, save_eact=False,
#     validate=False,
#     folder='SEBAL_B_Nebraska_2025',
#     scale=30, crs='EPSG:32611',

#     # ---- ANCHOR TANLASH (beton kaskad) ----
#     # 'default'  | 'cimec' | 'plan_a' | 'plan_b' | 'pysebal' | 'cascade'
#     # Nomlangan metod birinchi sinaladi, keyin qolganlari (ekin→ROI),
#     # hech biri chiqmasa 'default' fallback. Har qadam log'da chiqadi.
#     anchor_method='cascade',

#     # ---- VIIRS DOWNSCALING (ixtiyoriy, 500m) ----
#     use_viirs=False,          # True → oylik ET VIIRS bilan kuchaytiriladi
#     viirs_mode='lambda',     # 'lambda' (EVAP_FRAC) yoki 'kc' (KC)
#     viirs_model='multi',     # 'ndvi' | 'ndvi2' | 'multi'
#     viirs_qa='lenient',      # 'lenient' | 'strict'
#     viirs_fill='linear',     # 'linear' | 'nearest'
#     viirs_crs='EPSG:32611',  # 30m fine grid CRS — Idaho = UTM 11N.
#     #                         None qoldirsangiz avtomatik `crs`ga tushadi.
# )

# 4 lizimetr DALASI (210×210m markazda → −30m ichki = ~150×150m yadro).
# LZ markerlari (KMZ): NE=LZ6, SE=LZ1 (drip); NW=LZ4, SW=LZ3 (sprinkler).
lys_parcels = main.parcels_from_points({
    'NE': [-102.0955385, 35.18816985],
    'SE': [-102.0955390, 35.18612583],
    'NW': [-102.0978919, 35.18817119],
    'SW': [-102.0979121, 35.18613288],
}, size_m=210, inner_buffer_m=-30)

# main.run(
#     roi_type='gaul', name='Texas', level=1,          # Texas (Bushland shtati)
#     date_start='2021-03-01', date_end='2021-04-01',  # 2021 (lizimetr yili), mart–oktabr
#     mode='SEBAL_Milliy', satellite='BOTH', cloud_max=70, # SEBAL_Milliy: ERA5 L↓ + SMW LST + Solar daily
#     cold_etrf=1.05,                                   # default (0.85 test yomonroq: bias↓ lekin R²↓)
#     utc_offset=-6,                                    # Texas panhandle = Central Time (CST); lizimetr ham CST
#     process_by_tile=True,
#     tiles=[(30, 36)],                                 # Bushland tile (P30/R36)

#     # ---- RASTER OYLIK rejimi (butun tile bo'yicha TIF — CSV/point EMAS) ----
#     export_daily=False,
#     export_monthly=True,      # ← oylik raster: ET + Peffec/CUirr/NIWR (tile bo'yicha)
#     export_csv=False,         # ← CSV/point-zonal O'CHIRILDI

#     save_et=True, save_biomass=False,
#     save_etref=False, save_tact=False, save_eact=False,
#     save_cuirr=True,          # ← Peffec (samarali yog'in) + CUirr + NIWR oylik rasterlari
#     validate=False,
#     folder='SEBAL_Milliy_CUirr_Bushland_2021',        # Drive papka (raster: ET/Peffec/CUirr/NIWR)
#     scale=30, crs='EPSG:32613',                       # Texas panhandle = UTM 13N

#     # ---- ANCHOR TANLASH (beton kaskad) ----
#     # 'default' | 'cimec' | 'plan_a' | 'plan_b' | 'pysebal' | 'cascade'
#     anchor_method='cascade',

#     # ---- VIIRS DOWNSCALING (ixtiyoriy, 500m) ----
#     use_viirs=False,          # True → oylik ET VIIRS bilan kuchaytiriladi
#     viirs_mode='lambda',
#     viirs_model='multi',
#     viirs_qa='lenient',
#     viirs_fill='linear',
#     viirs_crs='EPSG:32613',   # ← 30m fine grid CRS — Texas panhandle = UTM 13N
# )



# ==============================================================
# SAMARQAND (O'zbekiston) — CUirr / AW raster (SEBAL_Milliy)
# ==============================================================
main.run(
    # ROI: yangi UZB asset chegarasidan (GAUL emas). name_field='region_nam'.
    roi_type='asset',
    asset_id='projects/ee-chexovant11/assets/uzb_admin1_2026',
    name='Samarqand',                                 # asset qiymati (uzbekcha)
    date_start='2026-03-01', date_end='2026-04-01',   # TEST: 1 oy (iyul, sug'orish piki).
    #                                                   To'liq mavsum: '2024-05-01'→'2024-10-01'
    mode='SEBAL_Milliy', satellite='BOTH', cloud_max=70, # SEBAL_Milliy: ERA5 L↓ + SMW LST + Solar
    cold_etrf=1.05,
    utc_offset=5,                                     # O'zbekiston = UTC+5 (UZT, DST YO'Q)
    process_by_tile=True,
    tiles=[(156,32),(155,32),(155,33)],                                # TEST: 1 tile. To'liq: [(156,32),(155,32),(155,33)]

    # ---- RASTER OYLIK rejimi (butun tile bo'yicha TIF) ----
    export_daily=False,
    export_monthly=True,      # ET + CU (Peffec/CUirr/NIWR/AW bitta ko'p-bandli fayl)
    export_csv=False,

    save_et=True, save_biomass=False,
    save_etref=False, save_tact=False, save_eact=False,
    save_cuirr=True,          # → SEBAL_monthly_CU_*.tif — DEFAULT faqat CUIRR + AW (30m)
    # save_prz=True,          # (ixtiyoriy) Peffec(PRZ) bandini ham qo'shadi
    # save_niwr=True,         # (ixtiyoriy) NIWR — LEKIN og'ir ETr hisoblanadi (sekin)
    validate=False,           # O'zbekistonda OpenET ishlamaydi
    folder='SEBAL_Milliy_ETCUirr_Samarqand_2026',       # Drive papka
    scale=30, crs='EPSG:32642',                       # O'zbekiston = UTM 42N
    # ⚠️ irrigation_efficiency=0.70 (config) — O'zbek furrow uchun ~0.55; keyin optimallash.

    # ---- ANCHOR TANLASH (beton kaskad) ----
    # 'default' | 'cimec' | 'plan_a' | 'plan_b' | 'pysebal' | 'cascade'
    anchor_method='cascade',

    # ---- VIIRS DOWNSCALING (ixtiyoriy, 500m) ----
    use_viirs=False,          # True → oylik ET VIIRS bilan kuchaytiriladi
    viirs_mode='lambda',
    viirs_model='multi',
    viirs_qa='lenient',
    viirs_fill='linear',
    viirs_crs='EPSG:32642',   # ← 30m fine grid CRS — O'zbekiston UTM 42N
)
