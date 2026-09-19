"""
SEBAL-GEE v4 — M2: Surface Properties
=======================================
Satellite ma'lumotlaridan yer yuzasi parametrlarini hisoblash.

Formulalar:
  - NDVI:        (B5-B4)/(B5+B4)
  - SAVI:        ((B5-B4)/(B5+B4+L)) × (1+L), L = cfg.SAVI_L   [Huete 1988]
  - Albedo:      Olmedo (2016) 6 band + quyosh balandligi (BRDF) tuzatishi
  - Emissivity:  Bastiaanssen F.6 + edge cases
  - z₀m:         exp(-5.809 + 5.62×SAVI) [Gediz]
  - τsw:         0.75 + 2×10⁻⁵ × elevation [Allen 2007]

Input:  Preprocessed ee.Image (SR scaled, LST, DEM)
Output: Image with surface property bands added
"""

import ee
from . import config as cfg

# Ekin-spetsifik z0m uchun ekin turi (h = f(LAI) → z0m = 0.123·h). None → default
# per-piksel z0m = Z0M_LAI_COEF·LAI (o'zgarmaydi). main.run(crop_type=…) FAQAT
# CSV/tadqiqot rejimida buni o'rnatadi (nuqta ekin turi ma'lum). cfg.CROP_H_LAI.
CROP_TYPE = None


# ==============================================================
# NDVI — Normalized Difference Vegetation Index
# ==============================================================

def compute_ndvi(image):
    """
    NDVI = (NIR - Red) / (NIR + Red)

    L8/9: NIR = SR_B5, Red = SR_B4
    Qiymat: -1 dan +1 gacha
    """
    # 1. Kanallarni float ko'rinishida tanlash
    nir = image.select(cfg.BAND_NAMES['nir']).float()
    red = image.select(cfg.BAND_NAMES['red']).float()

    # 2. Maxrajni hisoblash
    denominator = nir.add(red)

    # 3. Optimal chegara / Maskalash:
    # Maxraj 0 yoki undan kichik bo'lgan (anomal) piksellarni butunlay o'chirib tashlaymiz (mask)
    # Bu orqali bo'lish amali faqat musbat va real maxrajlar uchun bajariladi
    ndvi = nir.subtract(red).divide(denominator).rename('NDVI')
    
    # Faqat maxraj > 0 bo'lgan piksellarni qoldiramiz va explicit clamp qilamiz
    ndvi_optimized = ndvi.updateMask(denominator.gt(0)).clamp(-1, 1)

    return image.addBands(ndvi_optimized)


# ==============================================================
# SAVI — Soil Adjusted Vegetation Index
# ==============================================================

def compute_savi(image):
    """
    SAVI = ((NIR - Red) / (NIR + Red + L)) × (1 + L)

    L = cfg.SAVI_L (YAGONA manba, default 0.1 — SEBAL_ID/Tasumi).

    NDVI dan farqi: tuproq fon ta'sirini kamaytiradi.
    Siyrak o'simliklarda (cho'l, quruq dalalar) NDVI dan aniqroq.
    SAVI shu yerda BIR MARTA hisoblanadi; LAI (compute_lai) shu bandni oladi.
    """
    nir = image.select(cfg.BAND_NAMES['nir'])
    red = image.select(cfg.BAND_NAMES['red'])
    L = cfg.SAVI_L

    savi = (nir.subtract(red)
            .divide(nir.add(red).add(L))
            .multiply(1.0 + L)
            .rename('SAVI'))

    return image.addBands(savi)

# ==============================================================
# LAI — Leaf Area Index (qo'shimcha, optional)
# ==============================================================

def compute_lai(image):
    """
    LAI — SEBAL_ID (yangi SEBAL), 'SAVI' bandidan (compute_savi, L = cfg.SAVI_L).

    LAI = -ln((0.69 - SAVI) / 0.59) / 0.91

    SAVI QAYTA hisoblanmaydi — compute_savi oldin chaqirilgan bo'lishi SHART
    (compute_all tartibi). 'SAVI' band yo'q bo'lsa GEE xato beradi (jimgina emas).
    z₀m = 0.018×LAI shu LAI'dan hisoblanadi (compute_z0m).
    SAVI ≥ 0.687 → LAI = 6.0 (maks);  SAVI < 0.1 → LAI = 0.
    ⚠️ Formula koeffitsientlari ma'lum L uchun moslangan (config.SAVI_L izohi).
    """
    savi = image.select('SAVI')

    lai_formula = (ee.Image(0.69).subtract(savi)
                   .divide(0.59)
                   .log().multiply(-1.0)
                   .divide(0.91))

    # Asos — SAVI (Landsat UTM 30 m), ee.Image(0.0) EMAS: ee.Image(konstanta).where(…)
    # natijasi konstantaning proyeksiyasini (WGS84 1°) oladi → LAI, Z0M, Z0H 1° edi.
    # SAVI yo'q piksel — LAI ham yo'q (oldin soxta 0).
    lai = (savi.multiply(0)
           .where(savi.gte(0.1).And(savi.lt(0.687)), lai_formula)
           .where(savi.gte(0.687), 6.0)
           .clamp(0.0, 6.0)
           .rename('LAI'))

    return image.addBands(lai)
# ==============================================================
# ALBEDO — Olmedo (2016) Broadband
# ==============================================================

# Production 'ALBEDO' bandini qaysi usul beradi. main.run(albedo_method=) o'rnatadi.
#   'olmedo_brdf' (DEFAULT) → cfg.OLMEDO_COEFFICIENTS − (0.001464·θ_elev − 0.079103)
#   'config' → cfg.OLMEDO_COEFFICIENTS, BRDF tuzatishsiz (2026-09-17 gacha default)
#   'olmedo'|'liang'|'ke'|'tasumi'|'avg3' → foydalanuvchi koeffitsientlari (pastda).
# ⚠️ DIQQAT: 'olmedo' (foydalanuvchi, ofsetli) ≠ 'config' (cfg, ofsetsiz) — BOSHQA
#    koeffitsientlar. Har run'da ALB_* diagnostika bandlari ham qo'shiladi.
ALBEDO_METHOD = 'olmedo_brdf'


def _sun_elevation(image):
    """
    Quyosh balandligi θ_elev (gradus) — albedo BRDF tuzatishi uchun.
      Landsat: SUN_ELEVATION sahna metama'lumoti (skalyar).
      HLS:     90 − SZA band.
    Metama'lumot yo'q bo'lsa GEE xato beradi — fake qiymat ISHLATILMAYDI.
    """
    has_sza = image.bandNames().contains('SZA')
    return ee.Image(ee.Algorithms.If(
        has_sza,
        ee.Image(90).subtract(image.select('SZA')),
        ee.Image.constant(ee.Number(image.get('SUN_ELEVATION')))
    )).rename('SUN_ELEV')


def _albedo_variants(image):
    """
    Broadband-albedo usullari — production tanlovi + ALB_* diagnostika.
      olmedo_brdf : cfg.OLMEDO_COEFFICIENTS (ofsetsiz) − (slope·θ_elev − intercept)
      olmedo|liang|ke|tasumi|avg3 : foydalanuvchi koeffitsientlari
    Coastal (B_UB) = SR_B1 — preprocessing'da (Landsat va HLS) reflektansga
    o'tkazilgan, shu yerda qayta scale QILINMAYDI.
    """
    b = image.select('SR_B2'); g = image.select('SR_B3'); r = image.select('SR_B4')
    nir = image.select('SR_B5'); s1 = image.select('SR_B6'); s2 = image.select('SR_B7')
    ub = image.select(cfg.BAND_NAMES['coastal'])

    # α = 0.246·B + 0.146·G + 0.191·R + 0.304·NIR + 0.105·SWIR1 + 0.008·SWIR2
    oc = cfg.OLMEDO_COEFFICIENTS
    a_olmedo_cfg = (b.multiply(oc['SR_B2']).add(g.multiply(oc['SR_B3']))
                    .add(r.multiply(oc['SR_B4'])).add(nir.multiply(oc['SR_B5']))
                    .add(s1.multiply(oc['SR_B6'])).add(s2.multiply(oc['SR_B7'])))
    # α_final = α − (0.001464·θ_elev − 0.079103)
    brdf = (_sun_elevation(image).multiply(cfg.ALBEDO_BRDF['slope'])
            .subtract(cfg.ALBEDO_BRDF['intercept']))
    a_olmedo_brdf = a_olmedo_cfg.subtract(brdf)
    a_olmedo = (b.multiply(0.4739).add(g.multiply(-0.4372)).add(r.multiply(0.1652))
                .add(nir.multiply(0.2831)).add(s1.multiply(0.1072))
                .add(s2.multiply(0.1029)).add(0.0366))
    a_liang = (b.multiply(0.356).add(r.multiply(0.130)).add(nir.multiply(0.373))
               .add(s1.multiply(0.085)).add(s2.multiply(0.072)).subtract(0.0018))
    a_ke = (ub.multiply(0.130).add(b.multiply(0.115)).add(g.multiply(0.143))
            .add(r.multiply(0.180)).add(nir.multiply(0.281)).add(s1.multiply(0.108))
            .add(s2.multiply(0.042)))
    a_tasumi = (b.multiply(0.300).add(g.multiply(0.277)).add(r.multiply(0.233))
                .add(nir.multiply(0.143)).add(s1.multiply(0.036)).add(s2.multiply(0.012)))
    a_avg3 = a_olmedo.add(a_liang).add(a_ke).divide(3)
    return {'olmedo_brdf': a_olmedo_brdf,
            'olmedo': a_olmedo, 'liang': a_liang, 'ke': a_ke,
            'tasumi': a_tasumi, 'avg3': a_avg3}


def compute_albedo(image):
    """
    Broadband albedo — production 'ALBEDO' + 5 usul diagnostika bandi.

    Production 'ALBEDO' ni ALBEDO_METHOD tanlaydi:
      'olmedo_brdf' (default) → cfg.OLMEDO_COEFFICIENTS − (0.001464·θ_elev − 0.079103)
      'config' → cfg.OLMEDO_COEFFICIENTS (R `water`, ofsetsiz, BRDF tuzatishsiz)
      'olmedo'|'liang'|'ke'|'tasumi'|'avg3' → _albedo_variants (foydalanuvchi koeff.)
    Har doim ALB_OLMEDO_BRDF/ALB_OLMEDO/ALB_LIANG/ALB_KE/ALB_TASUMI/ALB_AVG3
    diagnostika bandlari ham qo'shiladi.
    Input: SR_B1..SR_B7 reflektans (preprocessing: Landsat C2L2 scale / HLS rename).
    """
    var = _albedo_variants(image)
    diag = [v.clamp(0.0, 1.0).rename('ALB_' + k.upper()) for k, v in var.items()]

    if ALBEDO_METHOD in var:
        albedo = var[ALBEDO_METHOD].clamp(0.0, 1.0).rename('ALBEDO')
    else:   # 'config' yoki noma'lum → hozirgi (o'zgarmagan)
        coeffs = cfg.OLMEDO_COEFFICIENTS
        albedo = (image.select(list(coeffs.keys()))
                  .multiply(list(coeffs.values()))
                  .reduce(ee.Reducer.sum())
                  .clamp(0.0, 1.0).rename('ALBEDO'))

    return image.addBands([albedo] + diag)


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

    # ---- SEBAL_ID (va SEBAL_Milliy): Eq. (4.28) LAI-asosli ----
    if cfg.is_id_mode(mode):
        eid = cfg.EMISSIVITY_ID
        lai = image.select('LAI')
        # Asos — NDVI (Landsat UTM 30 m), ee.Image(konstanta) EMAS (u WGS84 1° beradi).
        emissivity = (
            ndvi.multiply(0).add(eid['water_snow'])   # default: suv/qor (0.985); NDVI<0 shu yerda
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
        ndvi.multiply(0).add(ecfg['water'])   # default: suv (0.985); asos NDVI — Landsat grid
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

def compute_z0m(image, roi=None):
    """
    Momentum roughness length — SEBAL_ID (Tasumi & Allen 2003; Bastiaanssen liniyasi).

    Per-piksel u* uchun:   z₀m = 0.018 × LAI   (LAI compute_lai'dan, L = cfg.SAVI_L)
    Shamol ekstrapolyatsiyasi (10→200m) uchun ALOHIDA z₀m:
        h        = h_max × (NDVI-NDVI_min)/(NDVI_max-NDVI_min)   [ekin balandligi]
        z₀m,wind = 0.123 × h                                     [Brutsaert 1982]
    NDVI_min / NDVI_max — SAHNA persentillari (cfg.WIND_ROUGHNESS: p20 / p80),
    `roi` ichidagi NDVI dan (roi=None → tasvir footprint'i). NDVI_min ≥ floor,
    NDVI_max ≥ NDVI_min + span. Qiymatlar Z0MW_NDVI_MIN/MAX property'siga yoziladi.

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
    if CROP_TYPE is not None:
        # Ekin-spetsifik: h = a3·LAI³ + a2·LAI² + a1·LAI ; z0m = 0.123·h
        # (Tasumi/Wright, R² 0.98-0.99). Yalang pikselда LAI→0 → h→0 → z0m_min.
        a3, a2, a1 = cfg.CROP_H_LAI.get(CROP_TYPE, cfg.CROP_H_LAI['default'])
        h_crop = lai.expression(
            'a3*L*L*L + a2*L*L + a1*L',
            {'a3': a3, 'a2': a2, 'a1': a1, 'L': lai}).max(0)
        z0m = (h_crop.multiply(cfg.Z0M_HEIGHT_COEF)
               .max(rcfg['z0m_min'])
               .rename('Z0M'))
    else:
        z0m = (lai.multiply(cfg.Z0M_LAI_COEF)
               .max(rcfg['z0m_min'])
               .rename('Z0M'))

    z0h = (z0m.divide(ee.Number(rcfg['kB_inv']).exp())
           .rename('Z0H'))

    # ---- Shamol z₀m,wind = 0.123 × h(NDVI) — NDVI chegaralari SAHNADAN ----
    wc = cfg.WIND_ROUGHNESS
    ndvi = image.select('NDVI')
    region = roi if roi is not None else image.geometry()
    p_lo, p_hi = wc['ndvi_pct_min'], wc['ndvi_pct_max']
    pct = ndvi.reduceRegion(
        reducer=ee.Reducer.percentile([p_lo, p_hi]), geometry=region,
        scale=wc['pct_scale'], maxPixels=1e9, bestEffort=True, tileScale=4)
    # Sahnada NDVI yo'q bo'lsa (null) GEE xato beradi — soxta qiymat ishlatilmaydi.
    ndvi_lo = ee.Number(pct.get(f'NDVI_p{p_lo}')).max(wc['ndvi_min_floor'])
    ndvi_hi = ee.Number(pct.get(f'NDVI_p{p_hi}')).max(ndvi_lo.add(wc['ndvi_min_span']))

    h = (ndvi.subtract(ndvi_lo)
         .divide(ndvi_hi.subtract(ndvi_lo))
         .clamp(0.0, 1.0)
         .multiply(wc['h_max']))
    z0m_wind = (h.multiply(wc['z0m_coef'])
                .max(wc['z0m_min'])
                .rename('Z0M_WIND'))

    return (image.addBands(z0m).addBands(z0h).addBands(z0m_wind)
            .set({'Z0MW_NDVI_MIN': ndvi_lo, 'Z0MW_NDVI_MAX': ndvi_hi}))


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
    
    # MUHIM: Fizik chegarani explicit majburlash [0, 1]
    tau_sw_clamped = tau_sw.clamp(0, 1)

    return image.addBands(tau_sw_clamped)


# ==============================================================
# MAIN: Compute all surface properties
# ==============================================================

def compute_all(image, mode='SEBAL_B', roi=None):
    """
    Barcha yer yuzasi parametrlarini ketma-ket hisoblash.

    Input:  Preprocessed image (SR, LST, DEM, ERA5)
    Output: Image + NDVI, SAVI, ALBEDO, LAI, EMISSIVITY, Z0M, Z0H, TAU_SW bands

    Tartib muhim — LAI → z₀m (0.018·LAI) VA (SEBAL_ID) LAI → emissivity (Eq.4.28),
    shuning uchun compute_lai emissivity'dan OLDIN chaqiriladi.
    roi — Z0M_WIND NDVI persentillari hududi (None → tasvir footprint'i).
    """
    image = compute_ndvi(image)
    image = compute_savi(image)
    image = compute_albedo(image)
    image = compute_lai(image)             # OLDIN: z₀m VA SEBAL_ID emissivity LAI'ga bog'liq
    image = compute_emissivity(image, mode) # SEBAL_ID → Eq.4.28 (LAI); SEBAL_B → F.6 (NDVI)
    image = compute_z0m(image, roi)        # 0.018·LAI + z₀m,wind(NDVI, sahna p20/p80)
    image = compute_transmissivity(image)

    return image
