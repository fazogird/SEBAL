"""
SEBAL-GEE v4 — M3+M4: Radiation & Soil Heat Flux
===================================================
Net radiatsiya va tuproq issiqlik oqimini hisoblash.

M3 — Net Radiation Q* (Bastiaanssen F.5):
  Q* = (1 - α)×K↓ + L↓ - L↑ - (1 - ε₀)×L↓

M4 — Soil Heat Flux G₀ (Simplified Bastiaanssen 2000):
  G₀ = Q* × (T₀-273.15)/α × (0.0038α + 0.0074α²) × (1 - 0.978×NDVI⁴)

Input:  Image with surface properties + ERA5
Output: Image with Rn, G0 bands added
"""

import ee
from . import config as cfg


# ==============================================================
# INCOMING SHORTWAVE RADIATION K↓
# ==============================================================

def compute_incoming_shortwave(image):
    """
    Kirib keluvchi quyosh radiatsiyasi K↓ (W/m²).

    2 ta usul — biri ERA5 dan, biri hisoblash:

    Usul 1 (default): ERA5 ssrd — to'g'ridan-to'g'ri
    Usul 2 (fallback): K↓ = Gsc × cos(θ) × dr × τsw

    Biz ERA5 ni ishlatamiz chunki:
      - Har soat uchun mavjud
      - Bulutlilikni hisobga oladi
      - Global coverage

    Lekin ERA5 resolution past (0.1° ≈ 11km), shuning uchun
    τsw orqali DEM-based tuzatma qo'shamiz.
    """
    # ERA5 ssrd — hourly accumulated (J/m²) → W/m² ga o'girish
    # ERA5-Land hourly: qiymat = shu soatdagi yig'indi (J/m²)
    # W/m² = J/m² / 3600s
    ssrd = image.select('SSRD').divide(3600.0)

    # τsw orqali lokal tuzatma
    # ERA5 keng maydon o'rtacha beradi, lekin balandlik farqi bor
    # Lokal τsw dan tuzatamiz
    tau_sw = image.select('TAU_SW')

    # ERA5 τsw ni taxminan hisoblash (o'rtacha balandlik uchun)
    # va lokal τsw bilan nisbat qilamiz
    # Bu sodda yondashuv — murakkab topografik tuzatma emas
    k_down = ssrd.multiply(tau_sw.divide(0.75)).rename('K_DOWN')

    # Xavfsizlik: K↓ ≥ 0
    k_down = k_down.max(0)

    return image.addBands(k_down)


# ==============================================================
# INCOMING LONGWAVE RADIATION L↓
# ==============================================================

def compute_incoming_longwave(image):
    """
    Tushuvchi uzun to'lqin radiatsiyasi L↓ (W/m²).

    2 ta usul:

    Usul 1: ERA5 strd dan to'g'ridan-to'g'ri
    Usul 2: ε'atm × σ × Ta⁴

    Biz ERA5 ni ishlatamiz (usul 1) — aniqroq, chunki
    atmosfera profili to'liq hisobga olingan.
    """
    # ERA5 strd — hourly accumulated (J/m²) → W/m²
    strd = image.select('STRD').divide(3600.0)

    l_down = strd.rename('L_DOWN')

    # Xavfsizlik: L↓ > 0
    l_down = l_down.max(0)

    return image.addBands(l_down)


# ==============================================================
# OUTGOING LONGWAVE RADIATION L↑
# ==============================================================

def compute_outgoing_longwave(image):
    """
    Ko'tariluvchi uzun to'lqin radiatsiyasi L↑ (W/m²).

    L↑ = ε₀ × σ × T₀⁴

    Stefan-Boltzmann qonuni.
    ε₀ — surface_props.py da hisoblangan
    T₀ — LST (Kelvin)
    """
    emissivity = image.select('EMISSIVITY')
    lst = image.select('LST')
    sigma = cfg.STEFAN_BOLTZMANN

    l_up = (emissivity
            .multiply(sigma)
            .multiply(lst.pow(4))
            .rename('L_UP'))

    return image.addBands(l_up)


# ==============================================================
# NET RADIATION Q* — Bastiaanssen F.5
# ==============================================================

def compute_net_radiation(image):
    """
    Sof radiatsiya — energiya balansining birinchi qadami.

    Q* = (1 - α) × K↓ + L↓ - L↑ - (1 - ε₀) × L↓

    Oxirgi term (1-ε₀)×L↓ = yer yuzasidan qaytgan uzun to'lqin.
    Bu ko'pincha e'tibordan chetda qoladi — lekin past emissivitetli
    yuzalarda (quruq tuproq, qum) muhim bo'ladi.

    Natija: Rn (W/m²) — musbat qiymat = energiya yer yuzasiga tomon
    """
    albedo = image.select('ALBEDO')
    emissivity = image.select('EMISSIVITY')
    k_down = image.select('K_DOWN')
    l_down = image.select('L_DOWN')
    l_up = image.select('L_UP')

    # Qisqa to'lqin: (1 - α) × K↓
    rns = (ee.Image(1.0).subtract(albedo)).multiply(k_down)

    # Uzun to'lqin: L↓ - L↑ - (1 - ε₀) × L↓
    rnl = (l_down
           .subtract(l_up)
           .subtract(
               ee.Image(1.0).subtract(emissivity).multiply(l_down)
           ))

    # Q* = Rns + Rnl
    rn = rns.add(rnl).rename('RN')

    return image.addBands(rn)


# ==============================================================
# SOIL HEAT FLUX G₀ — Simplified Bastiaanssen (2000)
# ==============================================================

def compute_soil_heat_flux(image):
    """
    Tuproq issiqlik oqimi — Bastiaanssen (2000) soddalashtirilgan.

    G₀ = Q* × (T₀ - 273.15) / α × (0.0038α + 0.0074α²) × (1 - 0.978 × NDVI⁴)

    Komponentlar:
      - T₀/α termi: issiq va yorug' yuzalarda G₀ katta
      - 0.0038α + 0.0074α²: albedo ta'siri
      - (1 - 0.978×NDVI⁴): o'simlik ekstinksiyasi — zich
        o'simlikda G₀ kichik (soya ta'siri)

    Maxsus holatlar:
      - Suv piksellar: G₀ = 0.5 × Q*
      - NDVI < 0: G₀ = 0.5 × Q* (suv deb qabul qilish)

    Natija: G0 (W/m²) — musbat = yer yuzasidan tuproqqa
    """
    rn = image.select('RN')
    lst = image.select('LST')
    albedo = image.select('ALBEDO')
    ndvi = image.select('NDVI')
    water_mask = image.select('WATER_MASK')

    gcfg = cfg.SOIL_HEAT_FLUX

    # T₀ ni Celsius ga (formula shuni talab qiladi)
    t_celsius = lst.subtract(273.15)

    # Albedo termlari
    albedo_term = (albedo.multiply(gcfg['c1'])
                   .add(albedo.pow(2).multiply(gcfg['c2'])))

    # NDVI⁴ ekstinksiya
    ndvi_term = (ee.Image(1.0)
                 .subtract(
                     ndvi.pow(gcfg['ndvi_power'])
                     .multiply(gcfg['ndvi_extinction'])
                 ))

    # To'liq G₀ formulasi
    # G₀ = Rn × (Ts/α) × albedo_term × ndvi_term
    # Albedo = 0 bo'lganda division by zero — himoya
    albedo_safe = albedo.max(0.01)

    g0 = (rn
          .multiply(t_celsius.divide(albedo_safe))
          .multiply(albedo_term)
          .multiply(ndvi_term))

    # Suv piksellar uchun: G₀ = 0.5 × Q*
    g0_water = rn.multiply(gcfg['water_fraction'])
    g0 = g0.where(water_mask.eq(1), g0_water)

    # NDVI < 0 (suv belgilari) ham suv sifatida
    g0 = g0.where(ndvi.lt(0), g0_water)

    # G₀ ni oqilona oralig'iga cheklash
    # G₀ odatda Rn ning 5-50% oralig'ida
    g0 = g0.min(rn.multiply(0.50)).max(rn.multiply(-0.10))

    g0 = g0.rename('G0')

    return image.addBands(g0)


# ==============================================================
# NET AVAILABLE ENERGY (Q* - G₀)
# ==============================================================

def compute_net_available_energy(image):
    """
    Mavjud energiya = Q* - G₀

    Bu qiymat H va λE ga taqsimlanadi.
    Anchor pixel tanlashda va Λ hisoblashda ishlatiladi.
    """
    rn = image.select('RN')
    g0 = image.select('G0')

    rn_g0 = rn.subtract(g0).rename('RN_G0')

    return image.addBands(rn_g0)


# ==============================================================
# 24-HOUR NET RADIATION — De Bruin/Slob Formula
# ==============================================================

def compute_rn24(image):
    """
    24 soatlik sof radiatsiya — kunlik ET hisoblash uchun.

    Rn24 = (1 - α) × Rs24 - 110 × τsw

    Rs24: 24 soatlik quyosh radiatsiyasi (W/m²)
          ERA5 ssrd ni 24 soatga yig'ib, o'rtacha olamiz.
          Bu funksiya lahzali image da emas, daily_et.py da
          chaqiriladi — ERA5 24-soatlik integrali bilan.

    110: De Bruin (1987) empirik konstanta (W/m²)
         Uzun to'lqin radiatsiya balansini ifodalaydi.

    τsw: atmosfera o'tkazuvchanligi (Allen 2007, DEM-based)

    Bu funksiya lahzali tasvirga Rn24 qo'shadi —
    lekin Rs24 ni tashqaridan berish kerak (daily_et.py da).
    """
    albedo = image.select('ALBEDO')
    tau_sw = image.select('TAU_SW')

    # Rs24 — ERA5 dan 24 soatlik o'rtacha sifatida beriladi
    # Bu yerda image da 'RS24' band bor deb faraz qilamiz
    # (daily_et.py uni qo'shadi)
    rs24 = image.select('RS24')

    rn24 = ((ee.Image(1.0).subtract(albedo)).multiply(rs24)
            .subtract(ee.Image(cfg.DAILY_ET['rn24_constant']).multiply(tau_sw))
            .rename('RN24'))

    # Rn24 ≥ 0 (tungi salbiy radiatsiya hisobga olinmagan)
    rn24 = rn24.max(0)

    return image.addBands(rn24)


# ==============================================================
# MAIN: Compute all radiation components
# ==============================================================

def compute_all(image):
    """
    Barcha radiatsiya va tuproq issiqlik oqimini hisoblash.

    Tartib muhim:
      1. K↓ (incoming shortwave)
      2. L↓ (incoming longwave)
      3. L↑ (outgoing longwave) — LST va ε₀ kerak
      4. Q* (net radiation) — K↓, L↓, L↑, α kerak
      5. G₀ (soil heat flux) — Q*, T₀, α, NDVI kerak
      6. Rn-G₀ (net available energy)

    Rn24 bu yerda hisoblanMAYDI — daily_et.py da Rs24 bilan birga.

    Input:  Image with surface properties
    Output: Image + K_DOWN, L_DOWN, L_UP, RN, G0, RN_G0 bands
    """
    image = compute_incoming_shortwave(image)
    image = compute_incoming_longwave(image)
    image = compute_outgoing_longwave(image)
    image = compute_net_radiation(image)
    image = compute_soil_heat_flux(image)
    image = compute_net_available_energy(image)

    return image
