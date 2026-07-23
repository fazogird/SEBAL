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

def compute_emissivity(image, mode='SEBAL_B'):
    """
    Termal emissivitet.

    mode='SEBAL_ID' — Tasumi (2003) Eq. (4.28), LAI-asosli (NDVI > 0):
        ε₀ = 0.95 + 0.01 × LAI     (LAI < 3 uchun o'rinli)
        LAI ≥ 3                    → ε₀ = 0.98
        suv va qor                → ε₀ = 0.985  (konstanta)
      (LAI band OLDIN hisoblangan bo'lishi kerak — compute_all tartibi buni ta'minlaydi.)

    mode boshqa (SEBAL_B) — Bastiaanssen (1998) Formula 6:
        ε₀ = 1.009 + 0.047 × ln(NDVI)   [NDVI: 0.16–0.74]
        NDVI < 0         → ε₀ = 0.985  (suv)
        0 ≤ NDVI < 0.16  → ε₀ = 0.960  (yalang'och tuproq)
        NDVI > 0.74      → ε₀ = 0.985  (zich o'simlik)

    Source: SEBAL_ID — Tasumi (2003) Eq. 4.28; SEBAL_B — Van de Griend & Owe
    (1992), Bastiaanssen (1998) Eq.6.
    """
    ndvi = image.select('NDVI')

    # ---- SEBAL_ID: Eq. (4.28) LAI-asosli ----
    if mode == 'SEBAL_ID':
        eid = cfg.EMISSIVITY_ID
        lai = image.select('LAI')
        emissivity = (
            ee.Image(eid['water_snow'])      # default: suv/qor (0.985); NDVI<0 shu yerda
            .where(ndvi.gt(0).And(lai.lt(eid['lai_max'])),
                   lai.multiply(eid['b']).add(eid['a']))   # 0.95 + 0.01·LAI (LAI<3)
            .where(lai.gte(eid['lai_max']),
                   eid['dense'])             # LAI ≥ 3 → 0.98
            .rename('EMISSIVITY')
        )
        return image.addBands(emissivity)

    # ---- SEBAL_B: Bastiaanssen F.6 (NDVI-asosli) ----
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
    Momentum roughness length — SEBAL_ID (Tasumi & Allen 2003; Bastiaanssen liniyasi).

    Per-piksel u* uchun:   z₀m = 0.018 × LAI   (LAI compute_lai'dan, L=0.1 SAVI)
    Shamol ekstrapolyatsiyasi (10→200m) uchun ALOHIDA z₀m:
        h        = h_max × (NDVI-NDVI_min)/(NDVI_max-NDVI_min)   [ekin balandligi]
        z₀m,wind = 0.123 × h                                     [Brutsaert 1982]

    (Eski Gediz SAVI-exp formulasi olib tashlandi.)
    z₀h = z₀m / exp(kB⁻¹).
    """
    rcfg = cfg.ROUGHNESS

    # ---- Per-piksel z₀m = 0.018 × LAI ----
    # MAX chegara YO'Q: LAI ≤ 6 → z₀m ≤ 0.108 m (ekin uchun fizik: z₀m ≈ 0.1·h).
    # Eski z0m_max=1.0 hech qachon faollashmasdi (Gediz SAVI-exp formulasidan
    # qolgan o'lik qoldiq edi) — olib tashlandi. MIN 0.005 qoladi: u ln(200/z₀m)
    # domenini himoya qiladi (LAI < 0.28 bo'lgan yalang'och piksellarda).
    lai = image.select('LAI')
    z0m = (lai.multiply(cfg.Z0M_LAI_COEF)
           .max(rcfg['z0m_min'])
           .rename('Z0M'))

    z0h = (z0m.divide(ee.Number(rcfg['kB_inv']).exp())
           .rename('Z0H'))

    # ---- Shamol z₀m,wind = 0.123 × h(NDVI) ----
    wc = cfg.WIND_ROUGHNESS
    ndvi = image.select('NDVI')
    h = (ndvi.subtract(wc['ndvi_min'])
         .divide(wc['ndvi_max'] - wc['ndvi_min'])
         .clamp(0.0, 1.0)
         .multiply(wc['h_max']))
    z0m_wind = (h.multiply(wc['z0m_coef'])
                .max(wc['z0m_min'])
                .rename('Z0M_WIND'))

    return image.addBands(z0m).addBands(z0h).addBands(z0m_wind)


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
    LAI — SEBAL_ID (yangi SEBAL), L=0.1 li SAVI'dan.

    SAVI(0.1) = (1+0.1)×(NIR-Red)/(NIR+Red+0.1)
    LAI = -ln((0.69 - SAVI) / 0.59) / 0.91

    MUHIM: SEBAL_ID LAI uchun SAVI L=0.1 ishlatiladi (umumiy SAVI L=0.5 EMAS).
    z₀m = 0.018×LAI shu LAI'dan hisoblanadi (compute_z0m).
    SAVI ≥ 0.687 → LAI = 6.0 (maks);  SAVI < 0.1 → LAI = 0.
    """
    nir = image.select(cfg.BAND_NAMES['nir'])
    red = image.select(cfg.BAND_NAMES['red'])
    L = cfg.SAVI_L_LAI   # 0.1

    savi = (nir.subtract(red)
            .divide(nir.add(red).add(L))
            .multiply(1.0 + L)
            .rename('SAVI_LAI'))

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

def compute_all(image, mode='SEBAL_B'):
    """
    Barcha yer yuzasi parametrlarini ketma-ket hisoblash.

    Input:  Preprocessed image (SR, LST, DEM, ERA5)
    Output: Image + NDVI, SAVI, ALBEDO, LAI, EMISSIVITY, Z0M, Z0H, TAU_SW bands

    Tartib muhim — LAI → z₀m (0.018·LAI) VA (SEBAL_ID) LAI → emissivity (Eq.4.28),
    shuning uchun compute_lai emissivity'dan OLDIN chaqiriladi.
    """
    image = compute_ndvi(image)
    image = compute_savi(image)
    image = compute_albedo(image)
    image = compute_lai(image)             # OLDIN: z₀m VA SEBAL_ID emissivity LAI'ga bog'liq
    image = compute_emissivity(image, mode) # SEBAL_ID → Eq.4.28 (LAI); SEBAL_B → F.6 (NDVI)
    image = compute_z0m(image)             # 0.018·LAI + z₀m,wind(NDVI)
    image = compute_transmissivity(image)

    return image
