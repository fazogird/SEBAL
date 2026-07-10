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
    'z0m_a': -5.809,         # intercept coefficient
    'z0m_b':  5.62,          # SAVI coefficient
    'savi_L': 0.5,           # soil adjustment factor (Huete 1988)
    'kB_inv': 2.3,           # kB⁻¹ = ln(z₀m/z₀h) — Bastiaanssen standard
    'z0m_min': 0.0002,       # minimum roughness (bare soil/water)
    'z0m_max': 1.0,          # maximum roughness (tall vegetation)
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
    'z0m_weather': 0.12,     # weather station roughness (grass, m)
    'z1': 2.0,               # rah upper integration height (m)
    'z2': 0.1,               # rah lower integration height (m)
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

# ==============================================================
# 10. SENSIBLE HEAT FLUX — Monin-Obukhov Iteration
# ==============================================================

ITERATION = {
    'max_iter': 5,           # H-rah iteratsiya soni
    'convergence': 0.01,     # H o'zgarish chegarasi (W/m²)
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
    'overpass_hour_utc': 10,  # Landsat taxminiy o'tish vaqti ~10:00-10:30 UTC
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
    'cloud_max_percent': 60,       # maximum cloud cover %
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
