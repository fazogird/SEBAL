"""
SEBAL-GEE v4 — M2: Surface Properties
=======================================
Satellite ma'lumotlaridan yer yuzasi parametrlarini hisoblash.

Formulalar:
  - NDVI:        (B5-B4)/(B5+B4)
  - SAVI:        ((B5-B4)/(B5+B4+0.5)) × 1.5   [Huete 1988]
  - Albedo:      Olmedo (2016) — 6 band weighted sum
  - Emissivity:  Bastiaanssen F.6 + edge cases
  - z₀m:         exp(-5.809 + 5.62×SAVI) [Gediz]
  - τsw:         0.75 + 2×10⁻⁵ × elevation [Allen 2007]

Input:  Preprocessed ee.Image (SR scaled, LST, DEM)
Output: Image with surface property bands added
"""

import ee
from . import config as cfg


# ==============================================================
# NDVI — Normalized Difference Vegetation Index
# ==============================================================

def compute_ndvi(image):
    """
    NDVI = (NIR - Red) / (NIR + Red)

    L8/9: NIR = SR_B5, Red = SR_B4
    Qiymat: -1 dan +1 gacha
    """
    nir = image.select(cfg.BAND_NAMES['nir'])
    red = image.select(cfg.BAND_NAMES['red'])

    ndvi = nir.subtract(red).divide(nir.add(red)).rename('NDVI')

    return image.addBands(ndvi)


# ==============================================================
# SAVI — Soil Adjusted Vegetation Index
# ==============================================================

def compute_savi(image):
    """
    SAVI = ((NIR - Red) / (NIR + Red + L)) × (1 + L)

    L = 0.5 (Huete 1988)

    NDVI dan farqi: tuproq fon ta'sirini kamaytiradi.
    Siyrak o'simliklarda (cho'l, quruq dalalar) NDVI dan aniqroq.
    z₀m hisoblashda SAVI ishlatamiz.
    """
    nir = image.select(cfg.BAND_NAMES['nir'])
    red = image.select(cfg.BAND_NAMES['red'])
    L = cfg.ROUGHNESS['savi_L']  # 0.5

    savi = (nir.subtract(red)
            .divide(nir.add(red).add(L))
            .multiply(1.0 + L)
            .rename('SAVI'))

    return image.addBands(savi)


# ==============================================================
# ALBEDO — Olmedo (2016) Broadband
# ==============================================================

def compute_albedo(image):
    """
    Broadband albedo — Olmedo (2016) coefficients.

    α = 0.246×B2 + 0.146×B3 + 0.191×B4 + 0.304×B5 + 0.105×B6 + 0.008×B7

    Source: R `water` package, SMARTS model, Kimberly-Idaho calibration.
    No offset constant (Liang uses -0.0018, Olmedo does not).
    Input: C2L2 Surface Reflectance (already scaled 0–1 in preprocessing).
    """
    coeffs = cfg.OLMEDO_COEFFICIENTS

    # Har band × koeffitsient, keyin yig'indi
    albedo = (image.select(list(coeffs.keys()))
              .multiply(list(coeffs.values()))
              .reduce(ee.Reducer.sum())
              .rename('ALBEDO'))

    # Albedo 0–1 oralig'iga clamp (xavfsizlik)
    albedo = albedo.clamp(0.0, 0.80)

    return image.addBands(albedo)


# ==============================================================
# EMISSIVITY — Bastiaanssen F.6 + edge cases
# ==============================================================

def compute_emissivity(image):
    """
    Termal emissivitet — Bastiaanssen (1998) Formula 6.

    ε₀ = 1.009 + 0.047 × ln(NDVI)   [NDVI: 0.16–0.74]

    Edge cases:
      NDVI < 0         → ε₀ = 0.985  (suv)
      0 ≤ NDVI < 0.16  → ε₀ = 0.960  (yalang'och tuproq)
      NDVI > 0.74      → ε₀ = 0.985  (zich o'simlik)

    Source: Van de Griend & Owe (1992), Bastiaanssen (1998) Eq.6
    """
    ndvi = image.select('NDVI')
    ecfg = cfg.EMISSIVITY

    # Formula diapazoni: 0.16 ≤ NDVI ≤ 0.74
    # ln(NDVI) — NDVI > 0 bo'lgandagina ishlaydi
    ndvi_safe = ndvi.max(0.001)  # ln(0) dan himoya
    emiss_formula = ndvi_safe.log().multiply(ecfg['b']).add(ecfg['a'])

    # Edge cases — conditional
    emissivity = (
        ee.Image(ecfg['water'])         # default: suv (0.985)
        .where(ndvi.gte(0).And(ndvi.lt(ecfg['ndvi_min'])),
               ecfg['bare_soil'])       # tuproq (0.960)
        .where(ndvi.gte(ecfg['ndvi_min']).And(ndvi.lte(ecfg['ndvi_max'])),
               emiss_formula)           # formula diapazoni
        .where(ndvi.gt(ecfg['ndvi_max']),
               ecfg['dense_veg'])       # zich o'simlik (0.985)
        .rename('EMISSIVITY')
    )

    return image.addBands(emissivity)


# ==============================================================
# ROUGHNESS LENGTH z₀m — SAVI-based (Gediz)
# ==============================================================

def compute_z0m(image):
    """
    Momentum roughness length — SAVI asosida.

    z₀m = exp(-5.809 + 5.62 × SAVI)

    Source: Bastiaanssen et al. (2001), Gediz basin, Turkey.
    Paxta va uzum dalalarida kalibrlangan.

    Clamp: z₀m_min=0.0002m (suv/tuproq) — z₀m_max=1.0m (baland daraxtlar)

    z₀h = z₀m / exp(kB⁻¹)  [kB⁻¹ = 2.3, Bastiaanssen standard]

    MUHIM: SAVI va DEM bir xil CRS da bo'lishi kerak!
    Preprocessing modulida DEM reproject qilingan — shu yerda
    qo'shimcha tekshiruv yo'q.
    """
    savi = image.select('SAVI')
    rcfg = cfg.ROUGHNESS

    # z₀m = exp(a + b × SAVI)
    z0m = (savi.multiply(rcfg['z0m_b'])
           .add(rcfg['z0m_a'])
           .exp()
           .clamp(rcfg['z0m_min'], rcfg['z0m_max'])
           .rename('Z0M'))

    # z₀h = z₀m / exp(kB⁻¹)
    z0h = (z0m.divide(ee.Number(rcfg['kB_inv']).exp())
           .rename('Z0H'))

    return image.addBands(z0m).addBands(z0h)


# ==============================================================
# ATMOSPHERIC TRANSMISSIVITY — Allen (2007)
# ==============================================================

def compute_transmissivity(image):
    """
    Qisqa to'lqin atmosfera o'tkazuvchanligi.

    τsw = 0.75 + 2 × 10⁻⁵ × elevation

    Source: Allen et al. (2007) METRIC.
    DEM: SRTM 30m (preprocessing da qo'shilgan).
    """
    dem = image.select('DEM')
    tcfg = cfg.TRANSMISSIVITY

    tau_sw = (dem.multiply(tcfg['elev_coeff'])
              .add(tcfg['base'])
              .rename('TAU_SW'))

    return image.addBands(tau_sw)


# ==============================================================
# LAI — Leaf Area Index (qo'shimcha, optional)
# ==============================================================

def compute_lai(image):
    """
    LAI — SAVI dan empirik hisoblash.

    LAI = -ln((0.69 - SAVI) / 0.59) / 0.91

    Source: Allen et al. (2007) METRIC.
    SAVI > 0.687 → LAI = 6.0 (maksimum)
    SAVI < 0.1   → LAI = 0.0

    Bu optional — z₀m ni SAVI dan hisoblaganimiz uchun
    LAI alohida kerak emas, lekin validatsiya uchun foydali.
    """
    savi = image.select('SAVI')

    # LAI formula — SAVI 0.1–0.687 oralig'ida
    lai_formula = (ee.Image(0.69).subtract(savi)
                   .divide(0.59)
                   .log().multiply(-1.0)
                   .divide(0.91))

    lai = (ee.Image(0.0)
           .where(savi.gte(0.1).And(savi.lt(0.687)), lai_formula)
           .where(savi.gte(0.687), 6.0)
           .clamp(0.0, 6.0)
           .rename('LAI'))

    return image.addBands(lai)


# ==============================================================
# MAIN: Compute all surface properties
# ==============================================================

def compute_all(image):
    """
    Barcha yer yuzasi parametrlarini ketma-ket hisoblash.

    Input:  Preprocessed image (SR, LST, DEM, ERA5)
    Output: Image + NDVI, SAVI, ALBEDO, EMISSIVITY, Z0M, Z0H,
            TAU_SW, LAI bands

    Tartib muhim — SAVI → z₀m, NDVI → emissivity
    """
    image = compute_ndvi(image)
    image = compute_savi(image)
    image = compute_albedo(image)
    image = compute_emissivity(image)
    image = compute_z0m(image)
    image = compute_transmissivity(image)
    image = compute_lai(image)

    return image
