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
import math
import ee
from . import config as cfg


# ==============================================================
# INCOMING SHORTWAVE RADIATION K↓
# ==============================================================

# Taxminiy assume qiligan mantig'im
# def compute_incoming_shortwave(image):
#     """
#     Kirib keluvchi quyosh radiatsiyasi K↓ (W/m²).

#     2 ta usul — biri ERA5 dan, biri hisoblash:

#     Usul 1 (default): ERA5 ssrd — to'g'ridan-to'g'ri
#     Usul 2 (fallback): K↓ = Gsc × cos(θ) × dr × τsw

#     Biz ERA5 ni ishlatamiz chunki:
#       - Har soat uchun mavjud
#       - Bulutlilikni hisobga oladi
#       - Global coverage

#     Lekin ERA5 resolution past (0.1° ≈ 11km), shuning uchun
#     τsw orqali DEM-based tuzatma qo'shamiz.
#     """
#     # ERA5 ssrd — hourly accumulated (J/m²) → W/m² ga o'girish
#     # ERA5-Land hourly: qiymat = shu soatdagi yig'indi (J/m²)
#     # W/m² = J/m² / 3600s
#     ssrd = image.select('SSRD').divide(3600.0)

#     # τsw orqali lokal tuzatma
#     # ERA5 keng maydon o'rtacha beradi, lekin balandlik farqi bor
#     # Lokal τsw dan tuzatamiz
#     tau_sw = image.select('TAU_SW')

#     # ERA5 τsw ni taxminan hisoblash (o'rtacha balandlik uchun)
#     # va lokal τsw bilan nisbat qilamiz
#     # Bu sodda yondashuv — murakkab topografik tuzatma emas
#     k_down = ssrd.multiply(tau_sw.divide(0.75)).rename('K_DOWN')

#     # Xavfsizlik: K↓ ≥ 0
#     k_down = k_down.max(0)

#     return image.addBands(k_down)

def compute_incoming_shortwave(image):
    """
    Tushuvchi qisqa to'lqin radiatsiyasi K↓ (W/m²) — clear-sky astronomik formula.

    Rs↓ = Gsc × cos(θ) × dr × τsw     [Bastiaanssen manual, Eq. 12]

    Gsc — quyosh doimiysi (1367 W/m², cfg.GSC)
    cos(θ) — Landsat SUN_ELEVATION metadata'sidan (scene-level, HLS uchun SZA band)
    dr — Yer-Quyosh masofasi tuzatmasi (DOY dan)
    τsw — Allen (2007) DEM-based transmissivitet (surface_props.py da hisoblangan)

    """
    band_names = image.bandNames()
    has_sza = band_names.contains('SZA')

    # Server-side shart — ee.Algorithms.If bilan
    cos_theta_hls = image.select('SZA').multiply(math.pi / 180).cos()
    # SUN_ELEVATION — Landsat sahna metadatasi (mosaic uni preprocessing'da
    # copyProperties bilan SAQLAYDI). Landsat sahnada TOPILMASA — script
    # ATAYLAB to'xtaydi (ee.Number(null).multiply → xato). Fake qiymat
    # ISHLATILMAYDI: maqsad ishonchli, yuqori sifatli natija.
    #
    # HLS'da esa SZA bandi ishlatiladi va SUN_ELEVATION property yo'q; shu
    # bois FAQAT SZA mavjud bo'lganda (ya'ni bu shox discard qilinadigan
    # HLS holatida) crashning oldini olish uchun o'rin egasi (90°) beriladi
    # — bu qiymat chiqishga umuman kirmaydi (ee.Algorithms.If SZA shoxini
    # tanlaydi).
    sun_elev = ee.Number(ee.Algorithms.If(
        has_sza,
        ee.Algorithms.If(image.get('SUN_ELEVATION'),
                         image.get('SUN_ELEVATION'), 90),
        image.get('SUN_ELEVATION')))
    cos_theta_landsat = ee.Image.constant(
        sun_elev.multiply(math.pi / 180).sin()
    )
    cos_theta = ee.Image(
        ee.Algorithms.If(has_sza, cos_theta_hls, cos_theta_landsat)
    )

    # 2. dr — Yer-Quyosh masofasi (FAO-56 / Bastiaanssen)
    date = ee.Date(image.get('system:time_start'))
    doy = date.getRelative('day', 'year').add(1)
    dr = doy.multiply(2 * math.pi / 365).cos().multiply(0.033).add(1)

    # 3. tau_sw — allaqachon surface_props.py da hisoblangan (TAU_SW band)
    tau_sw = image.select('TAU_SW')

    # 4. K_DOWN = Gsc × cos(theta) × dr × tau_sw
    k_down = (
        cos_theta
        .multiply(cfg.GSC)
        .multiply(dr)
        .multiply(tau_sw)
        .max(0)        
        .rename('K_DOWN')
    )

    return image.addBands(k_down)


# ==============================================================
# INCOMING LONGWAVE RADIATION L↓
# ==============================================================
# A. ERA5 longwave (Usul 1) uchun ilmiy asos — real manbalar bilan
# Qidiruv qildim, taxmin qilmadim. Uchta mustahkam, tekshirilishi mumkin bo'lgan asos bor:
# 1. GEE'ning o'zi — texnik asos (metodologik xato yo'qligini tasdiqlaydi)
# Google Earth Engine'ning rasmiy ECMWF/ERA5_LAND/HOURLY katalog sahifasida aniq yozilgan:
#
# "Accumulated variables are reset daily at midnight, and Earth Engine provides 19 hourly bands by computing the difference between consecutive forecast steps."
#
# Ya'ni surface_thermal_radiation_downwards_hourly bandi — bu GEE tomonidan allaqachon ketma-ket soatlar orasidagi farq sifatida hisoblangan, xom kumulyativ qiymat emas. Shuning uchun kodingizdagi strd.divide(3600.0) — to'g'ri, qo'shimcha differensiatsiya kerak emas (bu — ResearchGate forumlarida CDS API orqali xom ma'lumot olganlar duch kelayotgan chalkashlik, GEE'da bu muammo yo'q, chunki GEE jamoasi buni oldindan hal qilib qo'ygan).
# 2. ERA5'ning longwave aniqligi — mustaqil validatsiya
# Wang et al. (2021), ScienceDirect — "Does ERA5 outperform satellite products in estimating atmospheric downward longwave radiation at the surface?" — 46 ta BSRN va 9 ta GTMBA yer stansiyasi bilan solishtirib, ERA5'ning quruqlik yuzasidagi downward longwave radiation (DLR) aniqligi CERES sun'iy yo'ldosh mahsulotidan yuqoriroq ekanini ko'rsatgan. Bu — ERA5 STRD'ning o'zi mustaqil ravishda yaxshi validatsiyadan o'tgan degani.
# 3. To'g'ridan-to'g'ri metodologik prezedent — SEBAL/SEBI oilasida ERA5 ishlatilishi
#
# Laipelt et al. (2021), ISPRS Journal of Photogrammetry and Remote Sensing — "Long-term monitoring of evapotranspiration using the SEBAL algorithm and Google Earth Engine cloud computing" (geeSEBAL). Bu — sizning pipeline'ingizga eng yaqin, haqiqiy nashr etilgan, GEE'da ishlaydigan SEBAL implementatsiyasi, meteorologik input sifatida ERA5-Landdan foydalanadi va 10 ta eddy-covariance flux-tower bilan solishtirilgan (RMSD = 0.67 mm/kun). Bu — sizning "nega ERA5" degan savolingizga eng kuchli, to'g'ridan-to'g'ri javob beruvchi manba.
# geeSSEBI (2025), MDPI Remote Sensing, DOI: 10.3390/rs17030395 — bundan ham aniqrog'i: bu maqola aynan sizning kodingizdagi kabi — ERA5-Land hourly shortwave VA longwave'ni 3600'ga bo'lish orqali instantaneous qiymatga o'tkazadi. Ya'ni siz ishlatgan texnik usul — nafaqat to'g'ri, balki 2025-yilgi retsenziyadan o'tgan nashrda aynan shu tarzda qo'llangan.
#
# Xulosa — yozishingiz mumkin bo'lgan asoslash
#
# "Bastiaanssen (1995) empirik εₐ=0.85×(-lnτsw)^0.09 formulasi Idaho alfalfa dalalari uchun kalibrlangan bo'lib, muallifning o'zi ta'kidlaganidek boshqa iqlim mintaqasi (G'arbiy Misr) uchun butunlay farqli koeffitsientlar (1.08, 0.265) talab qiladi — demak bu formula mahalliy kalibratsiyasiz Markaziy Osiyoga ko'chirib bo'lmaydi. Shu sababli ushbu pipeline'da ERA5-Land reanalysis (STRD bandi) ishlatiladi — bu yondashuv GEE-asosli SEBAL implementatsiyalarida standart amaliyot hisoblanadi (Laipelt et al., 2021; geeSSEBI, 2025) va ERA5'ning downward longwave radiation aniqligi mustaqil validatsiyalarda quruqlik yuzasida sun'iy yo'ldosh mahsulotlaridan (CERES) yuqori ekani ko'rsatilgan (Wang et al., 2021)."
#

def compute_incoming_longwave(image, mode='yangiliklar', roi=None, cold_mask=None):
    """
    Tushuvchi uzun to'lqin radiatsiyasi L↓ (W/m²) — atmosferadan yerga.

    MODE-ga bog'liq (ikki usul — ikkalasi ham SAQLANGAN):
      'yangiliklar'          → ERA5-Land STRD/3600 (reanalysis)  [pastda, o'chirilmagan]
      'SEBAL_B' / boshqa      → empirik (Bastiaanssen 1995; Tasumi Eq. 3.13):
          L↓ = 1.08 · σ · [-ln(τsw)]^0.265 · Tref^4
          Tref = cold (well-watered) referens SURFACE temp — cropland'ning eng
          sovuq (past LST, p10) piksellari (cold anchor mantig'i).

    2 ta usul mavjud (pySEBAL/METRIC an'anasi):

      Usul 1 (TANLANGAN): ERA5-Land STRD — to'g'ridan-to'g'ri reanalysis
      Usul 2 (rad qilingan): L↓ = εₐ × σ × Ta⁴
          εₐ = 0.85 × (-ln τsw)^0.09   [Bastiaanssen 1995, Idaho alfalfa]

    NEGA USUL 1 (ERA5) TANLANDI, USUL 2 EMAS:
      - Bastiaanssen (1995) koeffitsientlari (0.85, 0.09) — bu Idaho uchun
        kalibrlangan qiymat. Muallifning o'zi qayd etganidek, G'arbiy Misr
        uchun koeffitsientlar butunlay boshqacha (1.08, 0.265) — demak
        formula mahalliy kalibratsiyasiz Markaziy Osiyoga ko'chirilmaydi.
      - Usul 2'da butun sahna uchun BITTA T_cold (yoki Ta) ishlatiladi —
        atmosferaning haqiqiy fazoviy (namlik, bulut) o'zgaruvchanligini
        umuman hisobga olmaydi.
      - ERA5-Land downward longwave radiation — mustaqil validatsiyada
        quruqlik yuzasida CERES sun'iy yo'ldosh mahsulotidan aniqroq
        chiqqan (Wang et al., 2021, ScienceDirect).
      - ERA5-Land'ni meteorologik forcing sifatida ishlatish — GEE-asosli
        SEBAL/SEBI oilasidagi qabul qilingan amaliyot (geeSEBAL — Laipelt
        et al. 2021, ISPRS J. Photogramm.; geeSSEBI — 2025, MDPI RS,
        DOI:10.3390/rs17030395 — ikkalasi ham xuddi shu texnika: ERA5-Land
        hourly SW/LW ni 3600ga bo'lib instantaneous qiymat olish).

    ERA5-Land hourly bandlari (GEE rasmiy hujjati bo'yicha) — kumulyativ
    XOM qiymat emas, GEE jamoasi tomonidan ketma-ket forecast step'lar
    orasidagi FARQ sifatida oldindan hisoblab qo'yilgan. Shuning uchun
    qo'shimcha differensiatsiya (soatlar orasini ayirish) kerak emas —
    to'g'ridan-to'g'ri /3600 qilish yetarli.

    CLAMP HAQIDA: bu yerga qattiq (200-500) clamp QO'YILMAYDI — chunki
    L_DOWN manbai ERA5 (tashqi, sifat nazoratidan o'tgan reanalysis),
    Landsat LST'dagi kabi piksel darajasidagi termal xato xavfi yo'q
    (solishtiring: L_UP'da clamp bor, chunki u LST^4 dan hisoblanadi).
    Faqat fizik minimum himoyasi (.max(0)) qoldiriladi.
    """
    sigma = cfg.STEFAN_BOLTZMANN

    # ---- 'yangiliklar' MODE: ERA5-Land STRD/3600 (O'CHIRILMAGAN) ----
    if mode == 'yangiliklar':
        # ERA5 strd — hourly accumulated (J/m²) → W/m²
        strd = image.select('STRD').divide(3600.0)
        l_down = strd.rename('L_DOWN').max(0)
        return image.addBands(l_down)

    # ---- SEBAL_B (va boshqa): empirik Bastiaanssen 1995 (Tasumi 3.13) ----
    # L↓ = 1.08 · σ · [-ln(τsw)]^0.265 · Tref^4
    tau_sw = image.select('TAU_SW') #.clamp(0.01, 0.99)
    lst = image.select('LST')

    # Tref — cold (well-watered) referens SURFACE temp: cropland'ning past-
    # percentil (p10) LST. (Referens: "Tref approximated from surface temp of
    # a water/well-watered pixel".)
    base = lst.mask()
    if cold_mask is not None:
        base = base.And(cold_mask.gt(0))
    tref_lst = lst.updateMask(base).reduceRegion(
        ee.Reducer.percentile([10]), roi, 100, maxPixels=1e9,
        bestEffort=True, tileScale=4).get('LST')
    # fallback (bo'sh zona): ERA5 AIR_TEMP median
    tref_fb = image.select('AIR_TEMP').reduceRegion(
        ee.Reducer.median(), roi, 1000, maxPixels=1e9,
        bestEffort=True).get('AIR_TEMP', 293.0)
    # tref_lst null bo'lsa (cold zona bo'sh/bulutli) → ERA5 AIR_TEMP fallback
    tref = ee.Number(ee.Algorithms.If(tref_lst, tref_lst, tref_fb))

    # Tref manbai — LST p10 (cold anchor) yoki ERA5 AIR_TEMP fallback?
    # DIQQAT: bu funksiya collection.map() ICHIDA ishlaydi — shu yerda
    # getInfo/print QILIB BO'LMAYDI (map trace'da ishlamaydi, crash beradi).
    # Manbani XUSUSIYAT sifatida yozamiz; main.py sahna sikli (map'dan tashqarida)
    # uni bir marta o'qib PRINT qiladi ("fallback ishladimi yo LST dan olindimi").
    tref_src = ee.Algorithms.If(tref_lst,
                                'LST p10 (cold anchor)',
                                "ERA5 AIR_TEMP fallback (bo'sh/bulutli cold zona)")

    emiss_a = tau_sw.log().multiply(-1).pow(0.265).multiply(1.08)   # εa
    l_down = (emiss_a.multiply(sigma)
              .multiply(ee.Image.constant(tref).pow(4))
              .rename('L_DOWN').max(0))

    return (image.addBands(l_down)
            .set('LDOWN_TREF_SRC', tref_src)
            .set('LDOWN_TREF', tref))


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
        #    .clamp(200, 700) bu kerak emas hozircha 
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
    
    # Hard clamp EMAS — QA flag: manual bo'yicha odatiy oraliqdan
    # chetga chiqqan piksellarni BELGILAYDI, qiymatni O'ZGARTIRMAYDI.
    # Bu keyinchalik statistikada (masalan reduceRegion bilan) necha
    # foiz piksel "shubhali" ekanini tekshirish uchun foydali.
    rn_out_of_range = rn.lt(100).Or(rn.gt(700)).rename('RN_QA_FLAG')

    return image.addBands(rn).addBands(rn_out_of_range)


# ==============================================================
# SOIL HEAT FLUX G₀ — Bastiaanssen (2000), SEBAL Manual Eq. 24
# ==============================================================

def compute_soil_heat_flux(image):
    """
    Tuproq issiqlik oqimi — Bastiaanssen (2000).

    G/Rn = (Ts/α) × (0.0038α + 0.0074α²) × (1 - 0.98×NDVI⁴)   [Eq. 24]

    Ts — surface temperature (°C, LST dan)
    α  — surface albedo
    NDVI — Normalized Difference Vegetation Index

    Manual formulasi Kimberly, Idaho'dagi sug'oriladigan ekinlarga yaxshi
    mos kelishi tasdiqlangan (Tasumi & Allen, 2002, pers. commun.), lekin
    manual o'zi ogohlantiradi: "One must understand the area of interest
    in order to evaluate the accuracy of Equation (24)... Values of G
    should be checked against actual measurements on the ground."

    MAXSUS HOLATLAR (manual bo'yicha, midday qiymatlar):
      - NDVI < 0                    → suv          → G/Rn = 0.5
      - Ts < 4°C  VA  α > 0.45      → qor           → G/Rn = 0.5

    Diqqat: bu qoidalar QA_PIXEL WATER_MASK bandiga BOG'LIQ EMAS — manual
    faqat spektral/termal xususiyatlar (NDVI, Ts, albedo) orqali
    aniqlashni belgilaydi. Chuqur/tiniq suv havzalari uchun G/Rn murakkab
    (0.5 dan farqli bo'lishi mumkin — erta yozda sovuqroq ko'l, kuzda
    issiqroq ko'l); loyqa/sayoz suv uchun 0.5 dan kichikroq bo'ladi
    (qisqa to'lqin radiatsiyasi sirt yaqinida ko'proq yutiladi). Bu
    nuance'lar hozircha soddalashtirilgan (barcha suv = 0.5) — agar
    loyihada muhim ko'l/suv omborlari bo'lsa, alohida tekshirish kerak
    (manual Appendix 10).

    Sanity-check uchun manual Table 2 (G/Rn taxminiy oralig'i):
      Chuqur tiniq suv:  0.5      Qor:          0.5
      Cho'l:              0.2–0.4  Yalang tuproq: 0.2–0.4
      Ekin maydoni:       0.05–0.15  Zich alfalfa: 0.04
      Tosh/qoya:          0.2–0.6

    Natija: G0 (W/m²), G_RATIO (G/Rn, dimensionless)
    """
    rn = image.select('RN')
    lst = image.select('LST')
    albedo = image.select('ALBEDO')
    ndvi = image.select('NDVI')

    # Ts — Celsius (formula shuni talab qiladi)
    t_celsius = lst.subtract(273.15)

    # G/Rn = (Ts/α) × (0.0038α + 0.0074α²)
    #      = Ts × (0.0038 + 0.0074α)   [algebraik soddalashtirish, α bekor bo'ladi]
    g_ratio = t_celsius.multiply(albedo.multiply(0.0074).add(0.0038))

    # × (1 - 0.98×NDVI⁴)   — manual konstantasi 0.98 (0.978 EMAS)
    veg_extinction = ee.Image(1.0).subtract(ndvi.pow(4).multiply(0.98))
    g_ratio = g_ratio.multiply(veg_extinction)

    # ---- Maxsus holat: SUV (NDVI<0) → G/Rn ≈ 0.5 ----
    # QOR maskasi OLIB TASHLANDI: u albedo>0.45 VA LST<4°C ga tayanardi, lekin
    # albedo ham, LST ham piksel darajasida noaniq (shubhali) → ishonchsiz
    # detektsiya, xato 0.5 quyish xavfi. Suv (NDVI<0) esa ishonchli belgi.
    is_water = ndvi.lt(0)

    g_ratio = g_ratio.where(is_water, 0.5)

    # G/Rn fizik jihatdan mantiqiy oraliqqa cheklash
    # (manual Table 2: 0.04 dan 0.6 gacha kuzatilgan qiymatlar)
    g_ratio = g_ratio.clamp(0.0, 0.6).rename('G_RATIO')

    # G = Rn × (G/Rn)
    g0 = rn.multiply(g_ratio).rename('G0')

    return image.addBands(g0).addBands(g_ratio)

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
# MAIN: Compute all radiation components
# ==============================================================

def compute_all(image, mode='yangiliklar', roi=None, cold_mask=None):
    """
    Barcha radiatsiya va tuproq issiqlik oqimini hisoblash.

    mode → L↓ usulini tanlaydi (compute_incoming_longwave):
      'yangiliklar' → ERA5 STRD; boshqa (SEBAL_B/pysebal) → empirik (Tref).
    roi, cold_mask → SEBAL_B L↓ Tref (cold referens LST) uchun.

    Input:  Image with surface properties
    Output: Image + K_DOWN, L_DOWN, L_UP, RN, G0, RN_G0 bands
    """
    image = compute_incoming_shortwave(image)
    image = compute_incoming_longwave(image, mode, roi, cold_mask)
    image = compute_outgoing_longwave(image)
    image = compute_net_radiation(image)
    image = compute_soil_heat_flux(image)
    image = compute_net_available_energy(image)

    return image
