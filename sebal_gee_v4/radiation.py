"""
SEBAL-GEE v4 — M3+M4: Radiation & Soil Heat Flux
===================================================
Net radiatsiya va tuproq issiqlik oqimini hisoblash.

M3 — Net Radiation Q* (Bastiaanssen F.5):
  Q* = (1 - α)×K↓ + L↓ - L↑ - (1 - ε₀)×L↓

M4 — Soil Heat Flux G₀ (Simplified Bastiaanssen 2000):
  G₀ = Q* × (T₀-273.15)/α × (0.0038α + 0.0074α²) × (1 - 0.98×NDVI⁴)  [config.SOIL_HEAT_FLUX]

Input:  Image with surface properties + ERA5
Output: Image with Rn, G0 bands added
"""
import math
import ee
from . import config as cfg


# ==============================================================
# INCOMING SHORTWAVE RADIATION K↓
# ==============================================================


def compute_incoming_shortwave(image, sloping_terrain=False):
    """
    Tushuvchi qisqa to'lqin radiatsiyasi K↓ (W/m²) — clear-sky astronomik formula.

    Rs↓ = Gsc × cos(θ) × dr × τsw     [Bastiaanssen manual, Eq. 12]

    Gsc — quyosh doimiysi (1367 W/m², cfg.GSC)
    cos(θ) = cos(SZA) — PER-PIKSEL SZA bandidan (preprocessing: Landsat — mos C2 L1
             sahna, topilmasa astronomik; HLS — o'z SZA bandi)
    dr — Yer-Quyosh masofasi tuzatmasi (DOY dan)
    τsw — Allen (2007) DEM-based transmissivitet (surface_props.py da hisoblangan)

    """
    # cosθ — PER-PIKSEL (oldin Landsat'da sahna markazidagi bitta SUN_ELEVATION:
    # yozda ±1 %, qishda −5.5…+3.7 % K↓ xatosi sahna chetlarida). SZA bandi
    # preprocessing'da HAR Landsat/HLS tasvirga qo'shiladi; yo'q bo'lsa select
    # xato beradi — fake qiymat ISHLATILMAYDI.
    cos_theta = image.select('SZA').multiply(math.pi / 180).cos()

    # QIYA YUZA (Tasumi Eq 5.12-5.13): cosθ qiyalik+ekspozitsiyadan (AYNI SZA/SAA
    # bandlaridan), keyin gorizontal ekvivalentga (÷cos s). Yassi yuzada bu
    # cos(SZA) ga teng — ya'ni sloping_terrain=False bilan mos.
    if sloping_terrain:
        from . import sloping_terrain as slt
        cos_theta = slt.cos_theta_instant(image)

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
# Ya'ni surface_thermal_radiation_downwards_hourly bandi — bu GEE tomonidan allaqachon ketma-ket soatlar orasidagi farq sifatida hisoblangan, xom kumulyativ qiymat emas. 
# Shuning uchun kodingizdagi strd.divide(3600.0) — to'g'ri, qo'shimcha differensiatsiya kerak emas (bu — ResearchGate forumlarida CDS API orqali xom ma'lumot olganlar duch kelayotgan chalkashlik,
# GEE'da bu muammo yo'q, chunki GEE jamoasi buni oldindan hal qilib qo'ygan).
# 2. ERA5'ning longwave aniqligi — mustaqil validatsiya
# Wang et al. (2021), ScienceDirect — "Does ERA5 outperform satellite products in estimating atmospheric downward longwave radiation at the surface?" — 46 ta BSRN va 9 ta GTMBA yer stansiyasi bilan solishtirib,
# ERA5'ning quruqlik yuzasidagi downward longwave radiation (DLR) aniqligi CERES sun'iy yo'ldosh mahsulotidan yuqoriroq ekanini ko'rsatgan. Bu — ERA5 STRD'ning o'zi mustaqil ravishda yaxshi validatsiyadan o'tgan degani.
# 3. To'g'ridan-to'g'ri metodologik prezedent — SEBAL/SEBI oilasida ERA5 ishlatilishi
#
# Laipelt et al. (2021), ISPRS Journal of Photogrammetry and Remote Sensing — "Long-term monitoring of evapotranspiration using the SEBAL algorithm and Google Earth Engine cloud computing" (geeSEBAL). 
# Bu — sizning pipeline'ingizga eng yaqin, haqiqiy nashr etilgan, GEE'da ishlaydigan SEBAL implementatsiyasi, meteorologik input sifatida ERA5-Landdan foydalanadi va 10 ta eddy-covariance flux-tower bilan solishtirilgan (RMSD = 0.67 mm/kun).
# Bu — sizning "nega ERA5" degan savolingizga eng kuchli, to'g'ridan-to'g'ri javob beruvchi manba.
# geeSSEBI (2025), MDPI Remote Sensing, DOI: 10.3390/rs17030395 — bundan ham aniqrog'i: bu maqola aynan sizning kodingizdagi kabi — ERA5-Land hourly shortwave VA longwave'ni 3600'ga bo'lish orqali instantaneous qiymatga o'tkazadi. 
# Ya'ni siz ishlatgan texnik usul — nafaqat to'g'ri, balki 2025-yilgi retsenziyadan o'tgan nashrda aynan shu tarzda qo'llangan.
#
# Xulosa — yozishingiz mumkin bo'lgan asoslash
#
# "Bastiaanssen (1995) empirik εₐ=0.85×(-lnτsw)^0.09 formulasi Idaho alfalfa dalalari uchun kalibrlangan bo'lib, muallifning o'zi ta'kidlaganidek boshqa iqlim mintaqasi (G'arbiy Misr) uchun butunlay farqli koeffitsientlar (1.08, 0.265) talab qiladi — 
# demak bu formula mahalliy kalibratsiyasiz Markaziy Osiyoga ko'chirib bo'lmaydi. Shu sababli ushbu pipeline'da ERA5-Land reanalysis (STRD bandi) ishlatiladi — bu yondashuv GEE-asosli SEBAL implementatsiyalarida standart amaliyot hisoblanadi 
# (Laipelt et al., 2021; geeSSEBI, 2025) va ERA5'ning downward longwave radiation aniqligi mustaqil validatsiyalarda quruqlik yuzasida sun'iy yo'ldosh mahsulotlaridan (CERES) yuqori ekani ko'rsatilgan (Wang et al., 2021)."
#

def compute_incoming_longwave(image, mode='yangiliklar', tref=None):
    """
    Tushuvchi uzun to'lqin radiatsiyasi L↓ (W/m²) — atmosferadan yerga.

    MODE-ga bog'liq (usullar — barchasi SAQLANGAN):
      'yangiliklar'          → ERA5-Land STRD/3600 (reanalysis)  [pastda, o'chirilmagan]
      'SEBAL_ID'             → Eq. (4.13) — Tasumi (2003); koeffitsientlar
          Allen et al. (2000) tomonidan Kimberly (Idaho) yaqinidagi "RAPID"
          tadqiqot ma'lumotlaridan ishlab chiqilgan:
              R_L↓ = 0.85 · σ · [-ln(τsw)]^0.09 · Tref^4
          bu yerda Tref — referens nuqtadagi (odatda yaxshi sug'orilgan piksel,
          yer va havo harorati o'xshash bo'lgan joy) yer yuzasi harorati.
      'SEBAL_B' / 'pysebal'   → empirik (Bastiaanssen 1995; Tasumi Eq. 3.13):
          L↓ = 1.08 · σ · [-ln(τsw)]^0.265 · Tref^4
      Koeffitsientlar va rejimlar ro'yxati: config.LDOWN_EMPIRICAL / LDOWN_ERA5_MODES.
      Empirik Tref = COLD ANCHOR pikselning asl LST'i (point_anchor: o'sha bitta
      piksel; median_anchor: cold nomzodlar mediani) — butun maydon statistikasi
      EMAS. Anchor tanlangandan keyin main.py beradi
      (energy_balance.cold_anchor_surface_temp). Tref berilmasa — XATO
      (default harorat ishlatilmaydi). Noma'lum mode — XATO.

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

    # ---- ERA5-Land STRD/3600 L↓ ----
    #   'yangiliklar'  — asl ERA5 rejimi
    #   'SEBAL_Milliy' — SEBAL_ID oilasi, lekin L↓ ERA5 (Bushland validatsiya:
    #                    ERA5 R²=0.97/RMSE 13.7 >> Bastiaanssen R²=0.72/RMSE 44.9)
    if mode in cfg.LDOWN_ERA5_MODES:
        # ERA5 strd — hourly accumulated (J/m²) → W/m²
        strd = image.select('STRD').divide(3600.0)
        l_down = strd.rename('L_DOWN').max(0)
        return image.addBands(l_down)

    # ---- Empirik L↓ = c1 · σ · [-ln(τsw)]^c2 · Tref^4 ----
    if mode not in cfg.LDOWN_EMPIRICAL:
        raise ValueError(
            f"compute_incoming_longwave: noma'lum mode='{mode}'. ERA5: "
            f"{cfg.LDOWN_ERA5_MODES}; empirik: {tuple(cfg.LDOWN_EMPIRICAL)}")
    if tref is None:
        raise ValueError(
            f"compute_incoming_longwave(mode='{mode}'): empirik L↓ uchun Tref "
            f"(cold anchor LST, K) berilishi SHART — default harorat ishlatilmaydi.")

    c_mult, c_pow = cfg.LDOWN_EMPIRICAL[mode]
    tref = ee.Number(tref)
    tau_sw = image.select('TAU_SW')
    emiss_a = tau_sw.log().multiply(-1).pow(c_pow).multiply(c_mult)   # εa
    l_down = (emiss_a.multiply(sigma)
              .multiply(ee.Image.constant(tref).pow(4))
              .rename('L_DOWN').max(0))

    return image.addBands(l_down).set('LDOWN_TREF', tref)


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
      - SUV → G/Rn = 0.5. Suv manbasi (ustuvorlik bilan):
          1) sun'iy yo'ldosh QA suv biti — 'WATER_MASK' (Landsat QA_PIXEL bit 7 /
             HLS Fmask bit 5). Loyqa/sayoz/qirg'oq suvini ham topadi, shahar
             tomlarini (NDVI<0) suv demaydi.
          2) 'WATER_MASK' bandi yo'q bo'lsa yoki pikselda qiymati yo'q bo'lsa —
             NDVI < 0 (manual qoidasi).
      - Qor maskasi ishlatilmaydi (pastda).

    Koeffitsientlar — config.SOIL_HEAT_FLUX (c1, c2, ndvi_extinction,
    ndvi_power, water_fraction, ratio_min, ratio_max).
    Chuqur/tiniq suv havzalari uchun G/Rn murakkab
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

    gcfg = cfg.SOIL_HEAT_FLUX

    # G/Rn = (Ts/α) × (c1·α + c2·α²)
    #      = Ts × (c1 + c2·α)   [algebraik soddalashtirish, α bekor bo'ladi]
    g_ratio = t_celsius.multiply(albedo.multiply(gcfg['c2']).add(gcfg['c1']))

    # × (1 - k×NDVI^n)   — manual: k = 0.98, n = 4
    veg_extinction = ee.Image(1.0).subtract(
        ndvi.pow(gcfg['ndvi_power']).multiply(gcfg['ndvi_extinction']))
    g_ratio = g_ratio.multiply(veg_extinction)

    # ---- Maxsus holat: SUV → G/Rn = water_fraction ----
    # Suv: avval QA suv biti (WATER_MASK); band yoki piksel qiymati yo'q bo'lsa
    # NDVI < 0 (manual). QOR maskasi OLIB TASHLANDI: u albedo>0.45 VA LST<4°C
    # ga tayanardi — piksel darajasida ishonchsiz detektsiya.
    ndvi_water = ndvi.lt(0)
    is_water = ee.Image(ee.Algorithms.If(
        image.bandNames().contains('WATER_MASK'),
        image.select('WATER_MASK').eq(1).unmask(ndvi_water),
        ndvi_water))

    g_ratio = g_ratio.where(is_water, gcfg['water_fraction'])

    # G/Rn fizik jihatdan mantiqiy oraliqqa cheklash (manual Table 2: 0.04 … 0.6)
    g_ratio = g_ratio.clamp(gcfg['ratio_min'], gcfg['ratio_max']).rename('G_RATIO')

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
# ERMIDA SMW LST — faqat SEBAL_Milliy (C2L2 ST band o'rniga)
# ==============================================================
# Ermida et al. (2020), Remote Sensing, doi:10.3390/rs12091471 — Statistical
# Mono-Window: LST = A·Tb/ε + B/ε + C. Tb = at-sensor brightness temp (K2/ln(K1/L10+1));
# ε = bizning EMISSIVITY (Tasumi LAI); A,B,C — L8 TIRS10 koeffitsientlari, TPW (ERA5
# total column water vapour) bin bo'yicha (bin = min(floor(TPW_cm/0.6),9)).
#
# NEGA (Bushland lizimetr validatsiya, 2026-07-27): C2L2 ST band nadir IRT'dan +6.2K
# issiq (R²0.837) — bu USGS tan olgan C2 ST vegetatsiya-moslash anomaliyasi (Malakar
# 2018; ASTER GED baza NDVI o'zgargan sug'oriladigan yarim-quruq dalada xato) va
# single-channel suv-bug'i sezgirligi. SMW (bizning ε bilan): +4.8K, R²0.894, RMSE
# 7.25→5.61 va anchor-buzuvchi LAI-bog'liqlikni −38% kamaytiradi. Qoldiq ~4.8K asosan
# nuqta-vs-footprint (sovuq lizimetr mikro-uchastka) — anchor yutadi, majburan tuzatilmaydi.
# L9 TIRS-2 uchun ham L8 koeffitsienti ishlatiladi (farq <0.1K).
_SMW_L8 = {
    'A': [0.9751, 1.0090, 1.0541, 1.1282, 1.1987,
          1.3205, 1.4540, 1.6350, 1.5468, 1.9403],
    'B': [-205.8929, -232.2750, -253.1943, -279.4212, -307.4497,
          -348.0228, -393.1718, -451.0790, -429.5095, -547.2681],
    'C': [212.7173, 230.5698, 238.9548, 244.0772, 251.8341,
          257.2740, 263.5599, 268.9405, 275.0895, 277.9953],
}
# TIRS10 Planck K1/K2 — config.TIRS10_PLANCK (SPACECRAFT_ID bo'yicha: L8 va L9 BOSHQA).


def _era5_tcwv_cm(image):
    """
    ERA5 total column water vapour (TPW, cm) — overpass vaqtiga CHIZIQLI
    interpolyatsiya. TCWV INSTANT o'zgaruvchi: yorliqlar floor(t) va floor(t)+1,
    og'irlik = soatning kasr qismi (preprocessing.get_era5_for_image dagi instant
    bandlar bilan bir xil). Oldingi filterDate(t±1h).first() doim floor(t) soatni
    olardi (overpass :52 da — 52 daqiqa uzoqdagi soat). Soat topilmasa GEE xato beradi.
    """
    t = ee.Date(image.get('system:time_start'))
    day0 = ee.Date(t.format('YYYY-MM-dd'))
    t_h = t.difference(day0, 'hour')
    h0 = t_h.floor()
    w = t_h.subtract(h0)
    col = ee.ImageCollection('ECMWF/ERA5/HOURLY').select('total_column_water_vapour')

    def _at(h):
        start = day0.advance(h, 'hour')
        return ee.Image(col.filterDate(start, start.advance(1, 'hour')).first())

    tcwv = (_at(h0).multiply(ee.Number(1).subtract(w))
            .add(_at(h0.add(1)).multiply(w)))
    return tcwv.divide(10.0)                              # kg/m² (mm) → cm


def _tirs10_planck(image):
    """(K1, K2) — SPACECRAFT_ID bo'yicha config.TIRS10_PLANCK dan; yo'q → GEE xato."""
    kk = ee.List(ee.Dictionary(cfg.TIRS10_PLANCK).get(image.get('SPACECRAFT_ID')))
    return ee.Number(kk.get(0)), ee.Number(kk.get(1))


# SMW TPW klasslari (Ermida 2020): kenglik 0.6 sm, 10 klass (0…9) — algoritm O'ZGARMAYDI.
SMW_TPW_STEP = 0.6
SMW_TPW_NBIN = 10


def compute_lst_smw(image):
    """Ermida (2020) SMW LST — SEBAL_Milliy uchun 'LST' bandini qayta yozadi.

    LST = A·Tb/ε + B/ε + C ; Tb = K2/ln(K1/L10+1) ; ε = EMISSIVITY (bizning);
    A,B,C — TPW (ERA5 TCWV, cm) bin bo'yicha L8 TIRS10 koeffitsientlari.
    Kirish: image'da ST_TRAD (C2L2 thermal radiance) va EMISSIVITY bo'lishi shart.
    """
    # 1) Brightness temperature Tb — ST_TRAD (C2L2 thermal radiance, ×0.001 → W/m²/sr/µm)
    #    K1/K2 — sensorga mos (L8 ≠ L9), SPACECRAFT_ID bo'yicha.
    l10 = image.select('ST_TRAD').multiply(0.001)
    k1, k2 = _tirs10_planck(image)
    tb = l10.expression('K2 / log(K1 / L + 1.0)',
                        {'K1': ee.Image.constant(k1), 'K2': ee.Image.constant(k2),
                         'L': l10})
    eps = image.select('EMISSIVITY')

    # 2) TPW (cm) — to'liq ERA5 hourly TCWV (ERA5-Land'da YO'Q), overpass vaqtiga interpolyatsiya
    tpw_cm = _era5_tcwv_cm(image)
    pos = tpw_cm.divide(SMW_TPW_STEP).floor().min(SMW_TPW_NBIN - 1).max(0).toInt()

    # 3) TPW bin → A,B,C (remap) → .resample('bilinear') — Ermida ORIGINAL GEE kodi
    #    (sofiaermida/Landsat_SMW_LST, modules/SMWalgorithm.js):
    #      var A_img = image.remap(A_lookup.get(0), A_lookup.get(1),0.0,'TPWpos').resample('bilinear');
    #    Klass diskret qoladi (0.6 sm, 10 ta); faqat koeffitsient RASTRLARI ERA5 katak
    #    markazlari orasida bilinear → katak chegarasida A/B/C (va LST) sakramaydi.
    #    Oldin nearest: klass chegarasida hot pikselda +2…3 K LST pog'onasi
    #    (Samarqand 2023: 21 sahnadan 10 tasida ROI ichida 2 klass). TCWV'ning o'zi
    #    silliqlanmaydi, A(TPW) uzluksiz formulasi yo'q — asl algoritmdagidek.
    idx = list(range(10))
    a = pos.remap(idx, _SMW_L8['A']).resample('bilinear')
    b = pos.remap(idx, _SMW_L8['B']).resample('bilinear')
    c = pos.remap(idx, _SMW_L8['C']).resample('bilinear')

    # 4) LST = A·Tb/ε + B/ε + C
    #    Tb (Landsat UTM 30 m) BIRINCHI operand — natija Landsat gridini meros oladi.
    #    (Oldin a·Tb: 'a' ERA5 TCWV (0.25°) dan → LST, L_UP, DTA, G_RATIO default
    #    proyeksiyasi EPSG:4326 0.25° edi; anchor gridi 4326@30 m (30×23 m piksel,
    #    Landsat piksellarining ~30 % i ikki marta). Qiymat o'zgarmaydi: a·Tb = Tb·a.)
    lst = (tb.multiply(a).divide(eps)
           .add(b.divide(eps))
           .add(c)
           .rename('LST'))
    return image.addBands(lst, overwrite=True)


# ==============================================================
# LST FOOTPRINT DIAGNOSTIKA — validatsiya MASSHTABI uchun (compute_lst_smw'ni
# UMUMAN o'zgartirmaydi; 'LST' bandi xom retrieval bo'lib qoladi). Hech qanday
# tuzatish/ofset QO'LLANMAYDI — faqat qo'shimcha tashxis bandlari. Bular parcel
# MARKAZIDA (nuqta) namuna olish uchun mo'ljallangan: sun'iy yo'ldosh termal
# radiometrining fazoviy javobi (PSF) eng sovuq pikselni emas, footprint ichidagi
# radiatsiyaning integrallashgan javobini ko'radi — shuning uchun PSF-vaznli
# footprint RADIANCE fazosida (L=ε·σ·T⁴), keyin qayta ekvivalent haroratga.
# ==============================================================

# Soddalashtirilgan PSF (mukammal TIRS 2D PSF emas) — markazga katta vazn.
# DIQQAT: shunchaki VAZNLAR (list) — kernel funksiya ICHIDA quriladi. Modul
# darajasida ee.Kernel.fixed(...) YOZMA: u import paytida (ee.Initialize'dan
# OLDIN) ishga tushib "Earth Engine not initialized" xatosini beradi.
_PSF_WEIGHTS = [[1, 2, 1], [2, 4, 2], [1, 2, 1]]


def add_lst_footprint_diagnostics(image, scale=30):
    """LST footprint/neighborhood TASHXIS bandlarini QO'SHADI (xom LST o'zgarmaydi).

    Qo'shiladigan bandlar (nuqtada namuna olinganda markaziy piksel = tegishli stat):
      LST_raw_center, LST_mean_3x3, LST_median_3x3, LST_mean_5x5, LST_p10_5x5,
      LST_std_5x5, LST_psf_weighted (radiance-fazo 1-2-1 kernel),
      NDVI_mean_5x5, NDVI_std_5x5, ALBEDO_std_5x5, DIST_EDGE (dala chetigacha, m),
      ST_QA (K, C2L2 noaniqlik), WATER_VAPOR (ERA5 TPW, cm).
    Mavjud EMISSIVITY, TAU_SW, RN, H, G0, ET_24 bandlari export'da to'g'ridan olinadi.

    ⚠️ HECH QANDAY tuzatish yo'q — 'LST' bandi xom SMW retrieval bo'lib qoladi.
    """
    sigma = cfg.STEFAN_BOLTZMANN
    lst = image.select('LST')
    ndvi = image.select('NDVI')
    alb = image.select('ALBEDO')
    eps = image.select('EMISSIVITY')

    k3 = ee.Kernel.square(radius=1, units='pixels')   # 3×3
    k5 = ee.Kernel.square(radius=2, units='pixels')   # 5×5

    lst_center = lst.rename('LST_raw_center')
    lst_m3 = lst.reduceNeighborhood(ee.Reducer.mean(), k3).rename('LST_mean_3x3')
    lst_md3 = lst.reduceNeighborhood(ee.Reducer.median(), k3).rename('LST_median_3x3')
    lst_m5 = lst.reduceNeighborhood(ee.Reducer.mean(), k5).rename('LST_mean_5x5')
    lst_p10 = lst.reduceNeighborhood(
        ee.Reducer.percentile([10]), k5).rename('LST_p10_5x5')
    lst_sd5 = lst.reduceNeighborhood(ee.Reducer.stdDev(), k5).rename('LST_std_5x5')

    # PSF-vaznli footprint — RADIANCE fazosida (nochiziqli L=ε·σ·T⁴), emissivlik
    # bilan, keyin qayta ekvivalent radiometrik haroratga: T = (Lw/(εw·σ))^0.25.
    psf = ee.Kernel.fixed(3, 3, _PSF_WEIGHTS, normalize=True)   # LAZY (import emas)
    rad = eps.multiply(sigma).multiply(lst.pow(4))
    rad_w = rad.convolve(psf)
    eps_w = eps.convolve(psf)
    lst_psf = (rad_w.divide(eps_w.multiply(sigma))
               .pow(0.25).rename('LST_psf_weighted'))

    ndvi_m5 = ndvi.reduceNeighborhood(ee.Reducer.mean(), k5).rename('NDVI_mean_5x5')
    ndvi_sd5 = ndvi.reduceNeighborhood(ee.Reducer.stdDev(), k5).rename('NDVI_std_5x5')
    alb_sd5 = alb.reduceNeighborhood(ee.Reducer.stdDev(), k5).rename('ALBEDO_std_5x5')

    # Dala chetigacha masofa (m) — ESA WorldCover cropland (40) chetigacha
    # (piksel aralashuvi/chekka effektlarini tekshirish uchun).
    crop = (ee.ImageCollection('ESA/WorldCover/v200').first()
            .select('Map').eq(40))
    dist_edge = (crop.fastDistanceTransform(128).sqrt()
                 .multiply(ee.Image.pixelArea().sqrt())
                 .rename('DIST_EDGE'))

    # ST_QA — C2L2 sirt-harorat noaniqligi (K, ×0.01). Mavjud bo'lsa, aks holda -1.
    has_qa = image.bandNames().contains('ST_QA')
    st_qa = ee.Image(ee.Algorithms.If(
        has_qa, image.select('ST_QA').multiply(0.01),
        ee.Image.constant(-1))).rename('ST_QA')

    # WATER_VAPOR — SMW bilan AYNAN bir xil ERA5 TCWV (TPW, cm, vaqtga interpolyatsiya)
    wv = _era5_tcwv_cm(image).rename('WATER_VAPOR')

    return image.addBands([
        lst_center, lst_m3, lst_md3, lst_m5, lst_p10, lst_sd5, lst_psf,
        ndvi_m5, ndvi_sd5, alb_sd5, dist_edge, st_qa, wv,
    ])


# ==============================================================
# MAIN: Compute all radiation components
# ==============================================================

def compute_pre_longwave(image, mode='yangiliklar', sloping_terrain=False):
    """
    1-bosqich — L↓ ga BOG'LIQ BO'LMAGAN qism (anchor tanlashdan OLDIN ham xavfsiz):
      SEBAL_Milliy → Ermida SMW LST ('LST' ustiga yoziladi); K↓.
    """
    # SEBAL_Milliy: C2L2 ST band o'rniga Ermida SMW LST (vegetatsiya-anomaliyasidan
    # mustaqil). L↑, G₀, anchor, dT — hammasi shu tuzatilgan LST'ni ishlatadi.
    if mode == 'SEBAL_Milliy':
        image = compute_lst_smw(image)
    return compute_incoming_shortwave(image, sloping_terrain=sloping_terrain)


def compute_longwave_balance(image, mode='yangiliklar', tref=None):
    """
    2-bosqich — L↓, L↑, Rn, G₀, Rn−G₀.
      ERA5 rejimlari (config.LDOWN_ERA5_MODES): tref kerak emas.
      Empirik rejimlar (config.LDOWN_EMPIRICAL): tref = cold anchor LST (K) SHART.
    """
    image = compute_incoming_longwave(image, mode, tref)
    image = compute_outgoing_longwave(image)
    image = compute_net_radiation(image)
    image = compute_soil_heat_flux(image)
    image = compute_net_available_energy(image)
    return image


def compute_all(image, mode='yangiliklar', tref=None, sloping_terrain=False):
    """
    Barcha radiatsiya va tuproq issiqlik oqimi (1- + 2-bosqich birga).

    mode → L↓ usuli (config.LDOWN_*): ERA5 STRD yoki empirik (Tref = cold anchor LST).
    Empirik rejimda tref berilmasa XATO — main.py bu rejimlarda 1-bosqichni map()
    da, 2-bosqichni anchor tanlangandan keyin sahna siklida chaqiradi.
    sloping_terrain → K↓ uchun qiyalik/ekspozitsiyali cosθ (Tasumi Eq 5.12-5.13).

    Input:  Image with surface properties
    Output: Image + K_DOWN, L_DOWN, L_UP, RN, G0, RN_G0 bands
    """
    image = compute_pre_longwave(image, mode, sloping_terrain=sloping_terrain)
    return compute_longwave_balance(image, mode, tref)
