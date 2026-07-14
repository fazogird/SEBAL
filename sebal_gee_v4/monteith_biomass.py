"""
SEBAL-GEE v4 — Monteith Light-Use-Efficiency Biomassa Modeli
================================================================
Maqoladagi Formula (1)-(12) — CROP TYPE TALAB QILMAYDIGAN qism.

Formula (13) (Y_act — yakuniy hosil) BU YERDA YO'Q — u harvest index
va namlik koeffitsienti (Appendix B, ekinga bog'liq) talab qiladi.
Bu modul faqat B_act^tot (jami quruq biomassa, kg/ha) gacha boradi.

Zanjir:
  NDVI → f (4) → APAR (1,3)
  SEBAL EVAP_FRAC → W (7)
  NDVI vaqt seriyasi + ERA5 harorat → Topt → T1 (8), T2 (9)
  ε'_generic × T1 × T2 × W → ε (6)
  Σ(APAR_i × ε_i) → B_act^tot (12)

MUHIM: bu — MAVSUMIY modul (bir nechta oy/sahna kerak), chunki Topt
NDVI vaqt seriyasidan (eng yuqori NDVI oyi) aniqlanadi — bitta sahnada
hisoblab bo'lmaydi.

Input:  list of monthly composite images (NDVI, RS24, EVAP_FRAC, va
        ERA5 T_MEAN bandlari bilan)
Output: B_ACT_TOT (kg/ha, mavsum jami quruq biomassa)
"""

import ee
from . import config as cfg


# ==============================================================
# PREPROCESSING — oylik ERA5 harorat agregatsiyasi
# ==============================================================

def get_monthly_mean_temp(year, month, roi):
    """
    Bitta oy uchun ERA5 o'rtacha havo harorati (°C).

    Topt (Formula 8) — "eng yuqori NDVI rivojlangan oydagi o'rtacha
    harorat" — shuning uchun har oy uchun bitta o'rtacha kerak.
    """
    import calendar
    days_in_month = calendar.monthrange(year, month)[1]
    month_start = ee.Date.fromYMD(year, month, 1)
    month_end = month_start.advance(days_in_month, 'day')

    t_mean = (ee.ImageCollection(cfg.ERA5['collection'])
              .filterDate(month_start, month_end)
              .filterBounds(roi)
              .select(cfg.ERA5['bands']['air_temp'])
              .mean()
              .subtract(273.15)
              .rename('T_MON'))

    return t_mean.set('year', year).set('month', month)


# ==============================================================
# CALCULATIONS — 1-qadam: PAR, f, APAR (Formula 1, 3, 4)
# ==============================================================

def compute_par_apar(image):
    """
    Formula (1): PAR = 0.48 × K↓24
    Formula (4): f = -0.161 + 1.257×NDVI  [NDVI < 0.13 → f=0]
    Formula (3): APAR = f × PAR

    K↓24 — ERA5 RS24 bandidan (Angstrom-Prescott/quyosh-soat formulasi
    (11) O'TKAZIB YUBORILDI — meteorologik stansiya kerak, ERA5 buni
    to'g'ridan-to'g'ri, bulutlilikni hisobga olib, aniqroq beradi).

    Kirish: image'da 'NDVI' va 'RS24' bandlari bo'lishi shart.
    Chiqish: PAR, F_APAR, APAR bandlari qo'shiladi.
    """
    mcfg = cfg.MONTEITH
    ndvi = image.select('NDVI')
    rs24 = image.select('RS24')   # W/m² — daily_et.py da hisoblangan

    # Formula (1)
    par = rs24.multiply(mcfg['par_fraction']).rename('PAR')

    # Formula (4) — f, chegaralar bilan
    f_raw = ndvi.multiply(mcfg['f_slope']).add(mcfg['f_intercept'])
    f_apar = (f_raw
              .where(ndvi.lt(mcfg['ndvi_bare_threshold']), 0)
              .where(ndvi.gt(mcfg['ndvi_full_threshold']), 1)
              .clamp(0, 1)
              .rename('F_APAR'))

    # Formula (3)
    apar = f_apar.multiply(par).rename('APAR')

    return image.addBands(par).addBands(f_apar).addBands(apar)


# ==============================================================
# CALCULATIONS — 2-qadam: Topt (NDVI vaqt seriyasidan)
# ==============================================================

def compute_topt(monthly_images_with_temp, roi):
    """
    Topt — eng yuqori NDVI/LAI rivojlangan oydagi o'rtacha harorat.

    Usul: har bir piksel uchun, qaysi oyda NDVI eng baland bo'lsa,
    o'sha oyning T_MON qiymatini olamiz (qualityMosaic — GEE
    idiomatik, bitta operatsiyada per-pixel argmax).

    Parameters
    ----------
    monthly_images_with_temp : list of ee.Image
        Har biri NDVI va T_MON bandlariga ega bo'lishi shart
        (T_MON — get_monthly_mean_temp() dan).

    Returns
    -------
    ee.Image : TOPT (°C)
    """
    col = ee.ImageCollection(monthly_images_with_temp)

    # NDVI eng baland bo'lgan oyni "g'olib" qilib, o'sha oyning
    # BARCHA bandlarini (shu jumladan T_MON) tanlaydi — per pixel
    peak_ndvi_month = col.qualityMosaic('NDVI')

    topt = peak_ndvi_month.select('T_MON').rename('TOPT')
    return topt


# ==============================================================
# CALCULATIONS — 3-qadam: T1, T2 (Formula 8, 9 — Field et al. 1995)
# ==============================================================

def compute_t1(topt_image):
    """
    Formula (8): T1 = 0.8 + 0.02×Topt - 0.0005×Topt²

    Butun mavsum uchun BITTA qiymat (Topt piksel bo'yicha fiksativ,
    oydan-oyga o'zgarmaydi).
    """
    mcfg = cfg.MONTEITH
    t1 = (ee.Image(mcfg['t1_a'])
          .add(topt_image.multiply(mcfg['t1_b']))
          .subtract(topt_image.pow(2).multiply(mcfg['t1_c'])))
    return t1.clamp(0, 1).rename('T1')


def compute_t2(topt_image, t_mon_image):
    """
    Formula (9): T2 — sigmoid, Tmon Topt'dan qanchalik chetlashganini
    jazolaydi (arid/semi-arid hududlar uchun muhim).

    T2 = 1/(1+exp(0.2·Topt-10-Tmon)) × 1/(1+exp(0.3·(-Topt-10+Tmon)))

    Har oy uchun alohida (Tmon o'zgaradi).
    """
    mcfg = cfg.MONTEITH

    term1_exp = (topt_image.multiply(mcfg['t2_k1'])
                 .subtract(mcfg['t2_offset1'])
                 .subtract(t_mon_image))
    part1 = ee.Image(1.0).divide(term1_exp.exp().add(1.0))

    term2_exp = (topt_image.multiply(-1)
                 .subtract(mcfg['t2_offset2'])
                 .add(t_mon_image)
                 .multiply(mcfg['t2_k2']))
    part2 = ee.Image(1.0).divide(term2_exp.exp().add(1.0))

    t2 = part1.multiply(part2).clamp(0, 1).rename('T2')
    return t2


# ==============================================================
# CALCULATIONS — 4-qadam: ε (Formula 6) va biomassa increment
# ==============================================================

def compute_epsilon(t1, t2, evap_frac):
    """
    Formula (6): ε = ε'_generic × T1 × T2 × W

    W = Λ = EVAP_FRAC — to'g'ridan-to'g'ri SEBAL'dan (Formula 7,
    qayta hisoblash shart emas, band allaqachon mavjud).

    ⚠️ ε'_generic — VAQTINCHA umumiy qiymat (config.MONTEITH).
    Crop type kelganda — bu yerga ekinga bog'liq lookup qo'shiladi.
    """
    eps_max = cfg.MONTEITH['epsilon_max_generic']
    epsilon = (ee.Image(eps_max)
               .multiply(t1)
               .multiply(t2)
               .multiply(evap_frac)
               .rename('EPSILON'))
    return epsilon


def compute_biomass_increment(apar, epsilon, days_in_interval):
    """
    Bitta interval (oy) uchun biomassa qo'shilishi (Σ ichidagi bitta had).

    APAR (W/m²) → MJ/m²/interval: ×0.0864×kun_soni
    B_increment (g/m²) = APAR_MJ × ε (g/MJ)
    → kg/ha ga: ×10
    """
    apar_mj_interval = apar.multiply(0.0864).multiply(days_in_interval)
    b_increment_g = apar_mj_interval.multiply(epsilon)
    b_increment_kg_ha = b_increment_g.multiply(10.0).rename('B_INCREMENT')
    return b_increment_kg_ha


# ==============================================================
# OUTPUT — Formula (12): mavsumiy yig'indi
# ==============================================================

def compute_seasonal_biomass(monthly_increment_images):
    """
    Formula (12): B_act^tot = Σ(ε_i × APAR_i)

    Parameters
    ----------
    monthly_increment_images : list of ee.Image
        Har biri 'B_INCREMENT' bandiga ega (compute_biomass_increment dan)

    Returns
    -------
    ee.Image : B_ACT_TOT (kg/ha, mavsum jami)
    """
    col = ee.ImageCollection(monthly_increment_images)
    b_tot = col.select('B_INCREMENT').sum().rename('B_ACT_TOT')
    return b_tot


# ==============================================================
# ORCHESTRATION — hammasini birlashtirish
# ==============================================================

def compute_all_monteith(monthly_scene_images, year, months, roi):
    """
    To'liq zanjir: Formula (1),(3),(4),(6)[generic],(7),(8),(9),(10)→(12).

    Parameters
    ----------
    monthly_scene_images : list of ee.Image
        Har biri NDVI, RS24, EVAP_FRAC bandlariga ega (SEBAL pipeline
        natijasi — bitta oy uchun bitta vakillik tasvir/kompozit).
    year : int
    months : list of int
        Qaysi oylar mavsumga kiradi (masalan [4,5,6,7,8,9] — apr-sen)
    roi : ee.Geometry

    Returns
    -------
    dict:
      'b_act_tot': ee.Image — Formula (12) natijasi (kg/ha)
      'topt': ee.Image — diagnostika
      'monthly_epsilon': list — har oy uchun ε (diagnostika)
    """
    # 1. Har oy uchun T_MON qo'shish
    images_with_temp = []
    for img, m in zip(monthly_scene_images, months):
        t_mon = get_monthly_mean_temp(year, m, roi)
        images_with_temp.append(img.addBands(t_mon))

    # 2. PAR, f, APAR — har oy
    images_with_apar = [compute_par_apar(img) for img in images_with_temp]

    # 3. Topt — butun mavsum bo'yicha, bitta marta
    topt = compute_topt(images_with_apar, roi)

    # 4. T1 — bitta marta (Topt'ga bog'liq, oyga bog'liq emas)
    t1 = compute_t1(topt)

    # 5. Har oy: T2, ε, biomassa increment
    increments = []
    monthly_epsilons = []
    import calendar
    for img, m in zip(images_with_apar, months):
        t_mon = img.select('T_MON')
        t2 = compute_t2(topt, t_mon)
        evap_frac = img.select('EVAP_FRAC')
        epsilon = compute_epsilon(t1, t2, evap_frac)
        monthly_epsilons.append(epsilon)

        days = calendar.monthrange(year, m)[1]
        b_inc = compute_biomass_increment(img.select('APAR'), epsilon, days)
        increments.append(b_inc)

    # 6. Formula (12) — yig'indi
    b_act_tot = compute_seasonal_biomass(increments)

    return {
        'b_act_tot': b_act_tot,
        'topt': topt,
        't1': t1,
        'monthly_epsilon': monthly_epsilons,
    }


# ==============================================================
# TODO — Formula (13), crop type kelganda
# ==============================================================

def compute_yield(b_act_tot, harvest_index, moisture_content):
    """
    Formula (13): Y_act = h_ind × B_act^tot / (1 - m_oi)

    ⚠️ HALI ISHLATILMAYDI — h_ind va m_oi Appendix B (ekinga bog'liq)
    jadvalidan kelishi kerak. Crop type xaritasi tayyor bo'lganda:

        harvest_index = crop_type_map.remap(crop_ids, h_ind_values)
        moisture_content = crop_type_map.remap(crop_ids, m_oi_values)
        yield_img = compute_yield(b_act_tot, harvest_index, moisture_content)

    Hozircha bu funksiya faqat FORMULA sifatida tayyor turadi.
    """
    return (b_act_tot.multiply(harvest_index)
            .divide(ee.Image(1.0).subtract(moisture_content))
            .rename('Y_ACT'))