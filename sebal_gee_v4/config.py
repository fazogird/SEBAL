"""
SEBAL-GEE v4 — Global ET Pipeline Configuration
=================================================
Bastiaanssen (1998) original formulation, adapted for:
  - Landsat 8/9 Collection 2 Level 2
  - ERA5 / ERA5-Land meteorological data
  - Google Earth Engine Python API

All formula decisions locked:
  - Albedo:     Olmedo (2016) coefficients for OLI
  - G0:         Simplified Bastiaanssen (2000)
  - z0m:        SAVI-based (Gediz, Bastiaanssen 2001)
  - τsw:        Allen (2007) elevation-based
  - Anchor:     Automated percentile (Bastiaanssen p.206)
  - δTa:        Linear T0 relationship (F.30)
  - ET24:       Evaporative fraction method
  - Rn24:       De Bruin/Slob formula

Rabbim O'zi qo'llasin!
"""

import ee

# ==============================================================
# 1. PHYSICAL CONSTANTS
# ==============================================================

STEFAN_BOLTZMANN = 5.67e-8      # σ (W/m²/K⁴)
VON_KARMAN = 0.41               # k — Von Karman constant
GRAVITY = 9.81                  # g (m/s²)
CP_AIR = 1004.0                 # cₚ — specific heat of air (J/kg/K)
LAMBDA_V = 2.45e6               # λ — latent heat of vaporization (J/kg)
RHO_AIR_SEA_LEVEL = 1.225       # ρₐ standard (kg/m³), recalculated per scene
GSC = 1367.0                    # Solar constant (W/m²)
# Config ga qo'shish
CROPLAND_COLLECTION = 'ESA/WorldCover/v200'
CROPLAND_CLASS = 40
CROP_CLOUD_MAX = 30  # ekin yerlar ustida max bulut %
ANCHOR_USE_CROPLAND = True  # Anchor pixel tanlashda faqat ekin yerlarni ko'rib chiqish (True/False)
# ==============================================================
# 2. LANDSAT 8/9 COLLECTION 2 LEVEL 2
# ==============================================================

# GEE collection IDs
LANDSAT_COLLECTIONS = {
    'L8': 'LANDSAT/LC08/C02/T1_L2',
    'L9': 'LANDSAT/LC09/C02/T1_L2',
}

# Band mapping — L8 va L9 bir xil band nomlari
BAND_NAMES = {
    'blue':   'SR_B2',
    'green':  'SR_B3',
    'red':    'SR_B4',
    'nir':    'SR_B5',
    'swir1':  'SR_B6',
    'swir2':  'SR_B7',
    'thermal': 'ST_B10',
    'qa':     'QA_PIXEL',
    'radsat': 'QA_RADSAT',
}

# Scale factors — C2L2 raw DN → physical units
SCALE_FACTORS = {
    'sr_mult':  0.0000275,   # Surface reflectance multiplicative
    'sr_add':  -0.2,         # Surface reflectance additive
    'st_mult':  0.00341802,  # Surface temperature multiplicative (→ Kelvin)
    'st_add':   149.0,       # Surface temperature additive
}

# QA_PIXEL bitmask — cloud/shadow/snow/water detection
QA_BITMASK = {
    'fill':         1 << 0,   # bit 0
    'dilated_cloud': 1 << 1,  # bit 1
    'cirrus':       1 << 2,   # bit 2
    'cloud':        1 << 3,   # bit 3
    'cloud_shadow': 1 << 4,   # bit 4
    'snow':         1 << 5,   # bit 5
    'water':        1 << 7,   # bit 7
}



# ==============================================================
# 3. ALBEDO — Olmedo (2016) Coefficients
# ==============================================================
# Source: R `water` package (Olmedo et al.)
# Calculated using SMARTS for Kimberly, Idaho
# Direct Normal Irradiance weighting
# Applied to: C2L2 Surface Reflectance (scaled 0–1)
# Formula: α = Σ(wᵢ × Bᵢ), no offset

OLMEDO_COEFFICIENTS = {
    'SR_B2': 0.246,   # Blue
    'SR_B3': 0.146,   # Green
    'SR_B4': 0.191,   # Red
    'SR_B5': 0.304,   # NIR
    'SR_B6': 0.105,   # SWIR1
    'SR_B7': 0.008,   # SWIR2
}

# ==============================================================
# 4. EMISSIVITY — Van de Griend & Owe (1992)
# ==============================================================
# Bastiaanssen F.6: ε₀ = 1.009 + 0.047 × ln(NDVI)
# Valid range: NDVI 0.16–0.74

EMISSIVITY = {
    'a': 1.009,
    'b': 0.047,
    'ndvi_min': 0.16,        # formula qo'llaniladigan minimum
    'ndvi_max': 0.74,        # formula qo'llaniladigan maksimum
    'water': 0.985,          # NDVI < 0 (suv)
    'bare_soil': 0.960,      # 0 ≤ NDVI < 0.16 (yalang'och tuproq)
    'dense_veg': 0.985,      # NDVI > 0.74 (zich o'simlik)
}

# SEBAL_ID (Tasumi 2003) — Eq. (4.28): LAI-asosli emissivity (surface_props.
# compute_emissivity, faqat mode='SEBAL_ID').
#   NDVI > 0, LAI < 3  → ε₀ = 0.95 + 0.01 × LAI
#   LAI ≥ 3            → ε₀ = 0.98
#   suv va qor        → ε₀ = 0.985  (konstanta)
EMISSIVITY_ID = {
    'a': 0.95,               # ε₀ = 0.95 + 0.01·LAI  (NDVI>0, LAI<3)
    'b': 0.01,
    'lai_max': 3.0,          # LAI ≥ 3 chegarasi
    'dense': 0.98,           # LAI ≥ 3 (zich o'simlik)
    'water_snow': 0.985,     # suv va qor (NDVI < 0)
}

# ==============================================================
# 5. SOIL HEAT FLUX — Simplified Bastiaanssen (2000)
# ==============================================================
# G₀ = Q* × (T₀ - 273.15) / α × (0.0038α + 0.0074α²) × (1 - 0.978 × NDVI⁴)
# Suv uchun: G₀ = 0.5 × Q*

SOIL_HEAT_FLUX = {
    'c1': 0.0038,
    'c2': 0.0074,
    'ndvi_extinction': 0.978,
    'ndvi_power': 4,
    'water_fraction': 0.5,   # suv piksellar uchun G₀/Q* nisbati
}

# ==============================================================
# 6. ROUGHNESS LENGTH z₀m — SAVI-based (Gediz)
# ==============================================================
# z₀m = exp(a + b × SAVI)
# Source: Bastiaanssen et al. (2001) Gediz basin
# SAVI = ((NIR - Red) / (NIR + Red + L)) × (1 + L)

ROUGHNESS = {
    'z0m_a': -5.809,         # intercept coefficient (eski Gediz — endi ishlatilmaydi)
    'z0m_b':  5.62,          # SAVI coefficient (eski Gediz)
    'savi_L': 0.5,           # soil adjustment factor (Huete 1988) — SAVI (umumiy)
    'kB_inv': 2.3,           # kB⁻¹ = ln(z₀m/z₀h) — Bastiaanssen standard
    'z0m_min': 0.005,        # min roughness — SEBAL_ID agriculture (Tasumi Table 4.11)
    'z0m_max': 1.0,          # maximum roughness (tall vegetation)
}

# ── SEBAL_ID (yangi SEBAL) z₀m va LAI — Bastiaanssen liniyasi, METRIC EMAS ──
# Per-piksel momentum roughness — LAI dan (Gediz SAVI-exp o'rniga):
#   z₀m = 0.018 × LAI
# LAI esa L=0.1 li SAVI dan (SEBAL_ID; umumiy SAVI L=0.5 emas):
#   SAVI(0.1) = 1.1×(NIR-Red)/(NIR+Red+0.1),  LAI = -ln((0.69-SAVI)/0.59)/0.91
Z0M_LAI_COEF = 0.018
SAVI_L_LAI = 0.1

# Shamol ekstrapolyatsiyasi (10→200m) uchun z₀m — vegetatsiya balandligidan:
#   h = h_max × (NDVI-NDVI_min)/(NDVI_max-NDVI_min),  z₀m,wind = 0.123 × h  [Brutsaert 1982]
WIND_ROUGHNESS = {
    'z0m_coef': 0.123,
    'h_max':    2.0,         # maks ekin balandligi (m)
    'ndvi_min': 0.20,        # yalang'och tuproq
    'ndvi_max': 0.85,        # to'liq qoplam
    'z0m_min':  0.001,       # ln himoyasi (juda kichik z₀m'dan)
}

# ==============================================================
# 7. ATMOSPHERIC TRANSMISSIVITY — Allen (2007)
# ==============================================================
# τsw = 0.75 + 2 × 10⁻⁵ × elevation

TRANSMISSIVITY = {
    'base': 0.75,
    'elev_coeff': 2e-5,
}

# ==============================================================
# 8. WIND & MOMENTUM
# ==============================================================
# ERA5 10m wind → 200m extrapolation → per-pixel u* disaggregation

WIND = {
    'z_ref_era5': 10.0,      # ERA5 wind measurement height (m)
    'z_blending': 200.0,     # blending height (Allen/METRIC standard)
    'z0m_weather': 0.12,     # (eski — endi shamol z₀m WIND_ROUGHNESS'dan)
    # SEBAL_B (Bastiaanssen; Tasumi tezisi) — IKKI XIL z2:
    #   rah uchun:        z1=0.1m, z2_rah=0.2m → rah = ln(0.2/0.1)/(u*·k) = ln(2)
    #   stability (ψ) uchun: z1=0.1m, z2=2.0m (L<0 va L>0 uchun ham)
    # Bular BOSHQA-BOSHQA — chalkashtirmaslik.
    'z1':     0.1,           # past balandlik (rah + stability, umumiy)
    'z2_rah': 0.2,           # rah LOG hadi uchun yuqori balandlik
    'z2':     2.0,           # STABILITY (Monin-Obukhov ψ) yuqori balandligi
}

# ==============================================================
# 9. ANCHOR PIXEL SELECTION — Automated Percentile
# ==============================================================
# Based on Bastiaanssen (1998) p.206
# Cold: high NDVI + low LST → H ≈ 0
# Hot:  low NDVI + high LST → λE ≈ 0

ANCHOR = {
    # Cold pixel thresholds
    'cold_ndvi_percentile': 95,     # NDVI top 5%
    'cold_lst_percentile':  20,     # LST bottom 20% (5% juda xavfli — soya)
    'cold_albedo_max':      0.20,   # yashil o'simlik albedosi past

    # Hot pixel thresholds
    'hot_ndvi_percentile':  10,     # NDVI bottom 10%
    'hot_lst_percentile':   95,     # LST top 5%
    'hot_albedo_min':       0.18,   # yalang'och tuproq (urban emas)

    # Umumiy filtrlar
    'slope_max':            5.0,    # gradient < 5° (tekis yer)
    'min_candidates':       50,     # minimum piksel soni

    # Selection method
    'method': 'median',             # 'median' yoki 'mean' — outlier himoyasi
}

# ── ANCHOR KASKAD (beton) — bir nechta metod ketma-ket ──────────
# Anchor tanlash strategiyasi. run_sebal.py da `anchor_method` bilan
# tanlanadi:
#   'default' → hozirgi persentil + yumshoq fallback (bitta so'rov, tez)
#   'cimec' | 'plan_a' | 'plan_b' | 'pysebal' → shu metod BIRINCHI sinaladi,
#       keyin qolganlari; avval ekin zonasida, keyin butun ROI'da;
#       hech biri chiqmasa — 'default' persentil fallback (KAFOLAT).
#   'cascade' → cimec'dan boshlab to'liq zanjir.
ANCHOR_METHODS = ('default', 'cimec', 'plan_a', 'plan_b', 'pysebal', 'cascade')

ANCHOR_CASCADE = {
    'ts_gap_min': 3.0,   # plan_b: issiq-sovuq LST farqi (K) yetarli deb hisoblash chegarasi
    'min_dt':     1.0,   # anchorni qabul qilish uchun minimal (hot_LST - cold_LST), K
}

# ── ANCHOR REJIMI — kandidatlardan QIYMAT olish qadami ──────────
# MUHIM: anchor_method (cimec/plan_a/plan_b/pysebal/default) o'zgarmaydi —
# u kandidat piksellarni topadi. anchor_mode faqat o'sha kandidatlardan
# skalyar (cold_lst, hot_lst, hot_rn_g0) ni QANDAY olishni belgilaydi:
#   'median_anchor' (default) → kandidatlar bo'yicha MEDIAN (hozirgi holat).
#   'point_anchor' → kandidatlar hammasi to'g'ri, ICHIDAN BITTA ekstremal:
#       cold = eng SOVUQ (min LST), hot = eng ISSIQ (max LST) va Rn−G₀ AYNI
#       o'sha hot pikseldan (izchil juft). Kitobdagi qo'l-anchorga yaqin.
ANCHOR_MODES = ('median_anchor', 'point_anchor')

# ── ANCHOR LAND-COVER ZONALARI (ESA WorldCover v200) ────────────
# Cold va hot anchor AYRIM land-cover zonalaridan qidiriladi (klassik
# SEBAL/METRIC). MUHIM: hot anchor cropland'dan EMAS — aks holda to'liq
# sug'orilgan mavsumda (iyul–sentyabr) "eng issiq ekin" ham aslida
# transpiratsiya qiladi → λE≠0 → dT_hot oshib ketadi → ET past baholanadi.
#   cold = 40 (Cropland)         — sug'orilgan, nam, to'liq ET (λE≈max, H≈0)
#   hot  = 60 (Bare/sparse) + 20 (Shrubland) — doim quruq (λE≈0, H≈max)
#     (30 Grassland ATAYLAB kiritilmadi — Idaho'da sug'orilgan yaylov ham
#      30-klass bo'lib, nam pikselni hot deb olish xavfi bor.)
# ESA WorldCover: 10 daraxt, 20 buta, 30 o't, 40 ekin, 50 qurilma,
#   60 yalang'och, 70 qor, 80 suv, 90 nam yer, 95 mangr, 100 moss.
ANCHOR_LANDCOVER = {
    'cold': (40,),        # Cropland
    'hot':  (60, 20),     # Bare/sparse + Shrubland
}
# ==============================================================
# 10. SENSIBLE HEAT FLUX — Monin-Obukhov Iteration
# ==============================================================

ITERATION = {
    'max_iter': 15,        # xavfsizlik chegarasi (Dhungel 2016 damping bilan
                           #  yaqinlashish uchun joy — neytral start uzoq)
    'min_iter': 2,         # kamida shuncha iteratsiyadan keyin to'xtashga ruxsat
                            # (juda erta "yolg'on konvergensiya"dan himoya)
    # NISBIY konvergensiya: |dT_hot(i) - dT_hot(i-1)| / dT_hot < tol_rel.
    # Mutlaq 0.1K o'rniga foizli — bahorda kichik dT, yozda katta dT'ga
    # BIR XIL mos (masshtabdan mustaqil). LST aniqligi ~0.5K bo'lgani uchun
    # 1% (~0.05-0.2K) fizik jihatdan mazmunli; standart SEBAL/METRIC amaliyoti.
    'tol_rel': 0.01,       # 1% nisbiy tolerantlik (dT_hot va rah_hot uchun)
    'tol_dt': 0.01,        # (eski, mutlaq — endi ishlatilmaydi)
    'tol_rah': 0.1,        # (eski, mutlaq — endi ishlatilmaydi)
}

# ==============================================================
# 11. DAILY ET — Evaporative Fraction Method
# ==============================================================
# ET₂₄ = Λ × Rn24 / λ × 86400 × 1000  (mm/day)
# Rn24 = (1 - α) × Rs24 - 110 × τsw (De Bruin/Slob)

DAILY_ET = {
    'rn24_constant': 110.0,  # De Bruin (1987) empirik konstanta (W/m²)
    'seconds_per_day': 86400,
}

# ==============================================================
# 12. ERA5 DATA SOURCES
# ==============================================================

ERA5 = {
    'collection': 'ECMWF/ERA5_LAND/HOURLY',
    'bands': {
        'u_wind':   'u_component_of_wind_10m',
        'v_wind':   'v_component_of_wind_10m',
        'air_temp': 'temperature_2m',
        'dewpoint': 'dewpoint_temperature_2m',
        'pressure': 'surface_pressure',
        'ssrd':     'surface_solar_radiation_downwards_hourly',
        'strd':     'surface_thermal_radiation_downwards_hourly',
    },
    # ERA5 soat bilan ishlaydi — Landsat overpass vaqtiga moslashtirish
    'overpass_hour_utc': 11,  # Landsat taxminiy o'tish vaqti ~11:00-11:30 UTC
}

# ==============================================================
# 13. DEM
# ==============================================================

DEM = {
    'collection': 'USGS/SRTMGL1_003',
    'band': 'elevation',
}

# ==============================================================
# 14. ROI SOURCES — FAO GAUL Administrative Boundaries
# ==============================================================

GAUL = {
    'level0': 'FAO/GAUL/2015/level0',   # davlat
    'level1': 'FAO/GAUL/2015/level1',   # viloyat/state
    'level2': 'FAO/GAUL/2015/level2',   # tuman/county
    'name_field_l0': 'ADM0_NAME',
    'name_field_l1': 'ADM1_NAME',
    'name_field_l2': 'ADM2_NAME',
}

# ==============================================================
# 15. PIPELINE CONFIGURATION — default values
# ==============================================================

PIPELINE = {
    'satellite': 'BOTH',           # 'L8', 'L9', 'BOTH'
    'cloud_max_percent': 70,       # maximum cloud cover %
    'et_mode': 'monthly',          # 'daily' yoki 'monthly'
    'interpolation': 'linear',     # Λ interpolyatsiya: 'linear', 'nearest'

    'export_scale': 30,            # GeoTIFF resolution (m)
    'export_crs': 'EPSG:4326',    # default CRS (UTM avtomatik ham bo'lishi mumkin)
    'export_to': 'Drive',          # 'Drive' yoki 'Asset'
    'export_folder': 'SEBAL_Output',

    # Daily mode output bands
    'daily_bands': [
        'ET_24',        # mm/day
        'ETrF',         # ET fraction
        'LAMBDA_E',     # W/m² — instantaneous
        'H',            # W/m² — instantaneous
        'RN',           # W/m² — instantaneous
        'G0',           # W/m² — instantaneous
        'NDVI',
        'LST',          # Kelvin
    ],

    # Monthly mode output
    'monthly_bands': [
        'ET_monthly',   # mm/month
    ],
}

# ==============================================================
# 17. MONTEITH BIOMASS — Formula (1)-(12), crop-type'siz
# ==============================================================

MONTEITH = {
    'par_fraction': 0.48,       # Formula (1): PAR = 0.48 × K↓24
    'f_slope': 1.257,           # Formula (4): f = -0.161 + 1.257×NDVI
    'f_intercept': -0.161,
    'ndvi_bare_threshold': 0.13,  # NDVI < 0.13 → f = 0 (yalang'och tuproq)
    'ndvi_full_threshold': 0.92,  # NDVI > 0.92 → f = 1 (to'liq qoplam)

    # ⚠️ VAQTINCHA — ekin turi jadvali (Appendix A) hali yo'q.
    # Bu — GENERIK (umumiy C3 ekinlar o'rtachasi) qiymat, sizning
    # biomass.py dagi LUEMAX=2.5 bilan bir xil mantiq.
    # Crop type xaritasi kelganda — FAQAT shu qatorni ekinga bog'liq
    # lookup jadvaliga almashtirasiz, qolgan hammasi tayyor turadi.
    'epsilon_max_generic': 2.5,   # g/MJ — TODO: Appendix A jadvali bilan almashtiring

    # Formula (8): T1 = 0.8 + 0.02×Topt - 0.0005×Topt²
    't1_a': 0.8, 't1_b': 0.02, 't1_c': 0.0005,

    # Formula (9): T2 sigmoid parametrlari
    't2_k1': 0.2, 't2_offset1': 10.0,
    't2_k2': 0.3, 't2_offset2': 10.0,
}




# ==============================================================
# HELPER: ROI builder
# ==============================================================

def build_roi(roi_type, **kwargs):
    """
    ROI yaratish — 4 ta usul.

    Parameters
    ----------
    roi_type : str
        'rectangle', 'point', 'shapefile', 'gaul'
    kwargs :
        rectangle: bounds=[lon_min, lat_min, lon_max, lat_max]
        point:     coords=[lon, lat], buffer_m=50000
        shapefile: asset_id='users/name/asset'
        gaul:      level=0|1|2, name='Idaho'

    Returns
    -------
    ee.Geometry
    """
    if roi_type == 'rectangle':
        return ee.Geometry.Rectangle(kwargs['bounds'])

    elif roi_type == 'point':
        return (ee.Geometry.Point(kwargs['coords'])
                .buffer(kwargs.get('buffer_m', 50000)))

    elif roi_type == 'shapefile':
        fc = ee.FeatureCollection(kwargs['asset_id'])
        return fc.geometry()

    elif roi_type == 'gaul':
        level = kwargs.get('level', 1)
        name = kwargs['name']
        collection_key = f'level{level}'
        name_field = f'name_field_l{level}'
        fc = (ee.FeatureCollection(GAUL[collection_key])
              .filter(ee.Filter.eq(GAUL[name_field], name)))
        return fc.geometry()

    else:
        raise ValueError(
            f"roi_type '{roi_type}' noto'g'ri. "
            f"Variantlar: 'rectangle', 'point', 'shapefile', 'gaul'"
        )



# ==============================================================
# 16. HLS — Harmonized Landsat Sentinel-2
# ==============================================================
HLS_COLLECTION = 'NASA/HLS/HLSL30/v002'
HLS_BAND_NAMES = {
    'blue':    'B2',
    'green':   'B3',
    'red':     'B4',
    'nir':     'B5',
    'swir1':   'B6',
    'swir2':   'B7',
    'thermal': 'B10',
    'qa':      'Fmask',
}
HLS_QA_BITMASK = {
    'cirrus':       1 << 0,
    'cloud':        1 << 1,
    'adjacent':     1 << 2,
    'cloud_shadow': 1 << 3,
    'snow':         1 << 4,
    'water':        1 << 5,
}


# ==============================================================
# 18. REGION PRESETS — hududга/ekinга bog'liq kalibratsiya (MA'LUMOTNOMA)
# ==============================================================
# ⚠️ MUHIM: Bu tuzilma FAQAT MA'LUMOTNOMA — pipeline kodi uni O'QIMAYDI.
#    Uni qo'shish hozirgi natijalarga UMUMAN ta'sir qilmaydi. Aktiv qiymatlar
#    yuqoridagi ROUGHNESS / WIND_ROUGHNESS / TRANSMISSIVITY / DAILY_ET /
#    ANCHOR_LANDCOVER / OLMEDO_COEFFICIENTS bloklaridan olinadi (o'zgarmagan).
#
#    SEBAL'ning anchor kalibratsiyasi (dT=c4·Ts+c5) energiya balansini HAR
#    SAHNA uchun avtomatik rostlaydi — shu sabab ko'p narsa o'z-o'zidan
#    kalibrlanadi. Quyidagilar esa AVTOMATIK moslashmaydigan, hududга/ekinга
#    bog'liq qo'lda sozlanadigan parametrlar (ma'lumot uchun bir joyга yig'ilgan).
#
#    QANDAY QO'LLASH (kelajakda, IXTIYORIY): tegishli qiymatni yuqoridagi
#    aktiv config kalitiga QO'LDA ko'chiring (masalan turkey_gediz uchun
#    DAILY_ET['rn24_constant'] ni o'zgartiring). Avtomatik wiring ATAYLAB
#    qo'shilmagan — natijalar tasodifan o'zgarib ketmasligi uchun.
#
# Manbalar: SEBAL_ID z0m (Tasumi 2003), Gediz z0m (Bastiaanssen 2001, Turkey),
#           De Bruin 1987 (rn24), Olmedo 2016 (albedo), Allen 2007 (τsw).

REGION_PRESETS = {
    # ── IDAHO — hozirgi AKTIV konfiguratsiyaning AYNAN nusxasi ──────────
    # (dala ekinlari, sug'oriladigan; SEBAL_ID z0m; ET + validatsiya OpenET)
    'idaho': {
        'description': "Idaho (AQSh) — sug'oriladigan dala ekinlari, SEBAL_ID",
        'crs': 'EPSG:32611',                 # UTM 11N
        # z0m usuli: SEBAL_ID  →  z0m = Z0M_LAI_COEF × LAI
        'z0m_method':       'sebal_id_lai',
        'Z0M_LAI_COEF':     0.018,           # config.Z0M_LAI_COEF
        'SAVI_L_LAI':       0.1,             # config.SAVI_L_LAI (LAI uchun SAVI L)
        'roughness_z0m_min': 0.005,          # config.ROUGHNESS['z0m_min']
        # Shamol z0m (vegetatsiya balandligi)
        'h_max':            2.0,             # WIND_ROUGHNESS['h_max'] — dala ekini
        'wind_ndvi_min':    0.20,            # WIND_ROUGHNESS['ndvi_min']
        'wind_ndvi_max':    0.85,            # WIND_ROUGHNESS['ndvi_max']
        # Radiatsiya / iqlim
        'transmissivity_base': 0.75,         # TRANSMISSIVITY['base'] (arid, ochiq osmon)
        'rn24_constant':    110.0,           # DAILY_ET['rn24_constant'] (De Bruin)
        # Anchor land-cover (ESA WorldCover v200 klasslari)
        'anchor_cold_classes': (40,),        # Cropland
        'anchor_hot_classes':  (60, 20),     # Bare/sparse + Shrubland
        # Biomassa (ekin turi)
        'lue_max':          2.5,             # biomass.LUEMAX / MONTEITH C3 o'rtacha
    },

    # ── TURKEY (Gediz havzasi) — SHABLON, mahalliy kalibratsiya kerak ──
    # ⚠️ Quyidagi qiymatlar BOSHLANG'ICH NUQTA. Faqat manbali (sourced)
    #    farqlar qat'iy: (1) Gediz z0m koeffitsientlari (Bastiaanssen 2001,
    #    aynan shu havza uchun), (2) UTM zonasi. Qolganlarини MAHALLIY
    #    ma'lumot bilan tekshiring — taxminiy qiymatga tayanmang.
    'turkey_gediz': {
        'description': "Turkey — Gediz havzasi (paxta/makkajo'xori); z0m Gediz SAVI",
        'crs': 'EPSG:32635',                 # UTM 35N (Gediz ~27–28°E)
        # z0m usuli: Gediz  →  z0m = exp(z0m_a + z0m_b × SAVI)
        # ⚠️ Bu usul hozircha compute_z0m'да WIRE QILINMAGAN (config'да
        #    ROUGHNESS['z0m_a/z0m_b'] zaxira sifatida turibdi). Qo'llash uchun
        #    surface_props.compute_z0m'га Gediz shoxini qo'shish kerak.
        'z0m_method':       'gediz_savi',
        'z0m_a':            -5.809,           # ROUGHNESS['z0m_a'] — Bastiaanssen 2001 Gediz
        'z0m_b':             5.62,            # ROUGHNESS['z0m_b'] — Gediz SAVI koeff
        'roughness_z0m_min': 0.005,
        # Shamol z0m — Gediz'да paxta/makkajo'xori ~1.5–2.5m (mahalliy tekshiring)
        'h_max':            2.0,             # ⚠️ asosiy ekin balandligiga moslang
        'wind_ndvi_min':    0.20,            # ⚠️ tuproq foniga qarab tekshiring
        'wind_ndvi_max':    0.85,
        # Radiatsiya / iqlim — Egey iqlimi (yozда quruq). Mahalliy kalibratsiya
        # bo'lmasa De Bruin standart 110 qoladi (taxminiy son o'ylab topmang).
        'transmissivity_base': 0.75,         # ⚠️ nam mavsumда pasaytiring
        'rn24_constant':    110.0,           # ⚠️ mahalliy ma'lumot bilan kalibrlang
        # Anchor land-cover — Gediz landshaftiга qarab (bare tuproq bormi?)
        'anchor_cold_classes': (40,),
        'anchor_hot_classes':  (60, 20),     # ⚠️ hududда bare kam bo'lsa qayta ko'ring
        # Biomassa — paxta (C3, ~2.5) yoki makkajo'xori (C4, ~4.0) ga qarab
        'lue_max':          2.5,             # ⚠️ ekin turiga qarab (C4 uchun ~4.0)
    },
}


def get_region_preset(name):
    """
    Hudud preset'ini QAYTARADI (faqat o'qish — nusxa). Hech qanday config
    qiymatini o'zgartirmaydi, pipeline'га ta'sir qilmaydi. Ma'lumotnoma uchun.

    >>> cfg.get_region_preset('idaho')['h_max']
    2.0
    """
    if name not in REGION_PRESETS:
        raise ValueError(
            f"REGION_PRESETS'да '{name}' yo'q. "
            f"Variantlar: {list(REGION_PRESETS.keys())}"
        )
    return dict(REGION_PRESETS[name])   # sayoz nusxa — asl o'zgarmaydi
