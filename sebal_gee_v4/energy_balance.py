"""
SEBAL-GEE v4 — M5-M8: Energy Balance (SEBAL yuragi)
=====================================================
Bu modul SEBAL algoritmining eng muhim qismi:

  M5: Anchor pixel selection (cold/hot)
  M6: Wind & momentum (ERA5 → u*)
  M7: Sensible heat flux H (δTa + Monin-Obukhov iteratsiya)
  M8: Latent heat flux λE = Q* - G₀ - H

Bastiaanssen (1998) Formulalar: F.24-32
Gediz (2001): F.5-12

Input:  Image with surface properties + radiation
Output: Image with H, lambda_E, ETrF bands
"""

import ee
from . import config as cfg


# ==============================================================
# M5: ANCHOR PIXEL SELECTION
# ==============================================================

def select_anchor_pixels(image, roi):
    """
    Cold va hot anchor piksellarni avtomatik tanlash.

    Bastiaanssen (1998) p.206:
      Cold: NDVI top 5%, LST bottom 20%, albedo < 0.20
      Hot:  NDVI bottom 10%, LST top 5%, albedo > 0.18

    Jarayon:
      1. Sifat maskasi (slope < 5°, valid piksellar)
      2. Percentile hisoblash
      3. Kandidatlarni filtr
      4. Median qiymat olish (outlier himoyasi)

    Returns
    -------
    dict : cold_lst, hot_lst, hot_h, hot_dta, c4, c5
    """
    acfg = cfg.ANCHOR

    ndvi = image.select('NDVI')
    lst = image.select('LST')
    albedo = image.select('ALBEDO')
    slope = image.select('SLOPE')
    rn_g0 = image.select('RN_G0')

    # ---- 1. Tekis yer maskasi (slope < 5°) ----
    # flat_mask = slope.lt(acfg['slope_max'])
    # valid = image.mask().reduce(ee.Reducer.allNonZero())
    # base_mask = flat_mask.And(valid)
    
    flat_mask = slope.lt(acfg['slope_max'])
    valid = image.mask().reduce(ee.Reducer.allNonZero())

    base_mask = flat_mask.And(valid)
    
    try:
        anchor_px = base_mask.reduceRegion(
            reducer=ee.Reducer.count(),
            geometry=roi,
            scale=120,
            maxPixels=1e9,
            bestEffort=True
        ).getInfo()

        print(f"  🌾 Anchor cropland mask pixel count: {anchor_px}")
    except Exception as e:
        print(f"  ⚠️ Anchor cropland diagnostika xato: {e}")

    if cfg.ANCHOR_USE_CROPLAND:
        cropland_mask = get_anchor_cropland_mask(image, roi)
        base_mask = base_mask.And(cropland_mask)

    masked_ndvi = ndvi.updateMask(base_mask)
    masked_lst = lst.updateMask(base_mask)

    # ---- 2. Percentile hisoblash ----
    ndvi_stats = masked_ndvi.reduceRegion(
        reducer=ee.Reducer.percentile(
            [acfg['hot_ndvi_percentile'], acfg['cold_ndvi_percentile']]
        ),
        geometry=roi,
        scale=30,
        maxPixels=1e9,
        bestEffort=True
    )

    lst_stats = masked_lst.reduceRegion(
        reducer=ee.Reducer.percentile(
            [acfg['cold_lst_percentile'], acfg['hot_lst_percentile']]
        ),
        geometry=roi,
        scale=30,
        maxPixels=1e9,
        bestEffort=True
    )

    ndvi_p_hot = ee.Number(ndvi_stats.get(
        f'NDVI_p{acfg["hot_ndvi_percentile"]}'))
    ndvi_p_cold = ee.Number(ndvi_stats.get(
        f'NDVI_p{acfg["cold_ndvi_percentile"]}'))
    lst_p_cold = ee.Number(lst_stats.get(
        f'LST_p{acfg["cold_lst_percentile"]}'))
    lst_p_hot = ee.Number(lst_stats.get(
        f'LST_p{acfg["hot_lst_percentile"]}'))

    # ---- Anchor maskasi bo'sh bo'lganda himoya (HLS/bulutli sahna) ----
    # Qattiq shartlar (NDVI + LST + albedo) ba'zan 0 nomzod beradi →
    # median null → ee.Number(null) butun grafni buzadi
    # ("Number.subtract/multiply: left null"). Bo'sh bo'lsa, faqat LST
    # percentil asosidagi zaxira maskaga o'tamiz (base_mask non-empty
    # bo'lsa har doim non-empty).
    def _ensure_nonempty(mask, fallback):
        mask = mask.rename('M')
        cnt = mask.reduceRegion(
            reducer=ee.Reducer.sum(), geometry=roi, scale=120,
            maxPixels=1e9, bestEffort=True).get('M')
        cnt = ee.Number(ee.Algorithms.If(cnt, cnt, 0))
        return ee.Image(ee.Algorithms.If(cnt.gt(0), mask, fallback.rename('M')))

    # ---- 3. Cold pixel kandidatlar ----
    cold_mask = (
        base_mask
        .And(ndvi.gte(ndvi_p_cold))
        .And(lst.lte(lst_p_cold))
        .And(albedo.lt(acfg['cold_albedo_max']))
    )
    cold_fallback = base_mask.And(lst.lte(lst_p_cold))
    cold_mask = _ensure_nonempty(cold_mask, cold_fallback)

    # Cold pixel — LST median (eng barqaror qiymat)
    cold_lst = (lst.updateMask(cold_mask)
                .reduceRegion(
                    reducer=ee.Reducer.median(),
                    geometry=roi,
                    scale=30,
                    maxPixels=1e9,
                    bestEffort=True
                ).get('LST'))
    cold_lst = ee.Number(cold_lst)

    # ---- 4. Hot pixel kandidatlar ----
    hot_mask = (
        base_mask
        .And(ndvi.lte(ndvi_p_hot))
        .And(lst.gte(lst_p_hot))
        .And(albedo.gt(acfg['hot_albedo_min']))
    )
    hot_fallback = base_mask.And(lst.gte(lst_p_hot))
    hot_mask = _ensure_nonempty(hot_mask, hot_fallback)

    # Hot pixel — LST va (Q*-G₀) median
    hot_stats = (image.select(['LST', 'RN_G0'])
                 .updateMask(hot_mask)
                 .reduceRegion(
                     reducer=ee.Reducer.median(),
                     geometry=roi,
                     scale=30,
                     maxPixels=1e9,
                     bestEffort=True
                 ))
    hot_lst = ee.Number(hot_stats.get('LST'))
    hot_rn_g0 = ee.Number(hot_stats.get('RN_G0'))

    # ---- 5. Anchor ma'lumotlarni qaytarish ----
    # hot_mask va cold_mask ham kerak — iteratsiyada hot pixel dagi
    # rah qiymatini FAQAT hot piksellardan olish uchun.
    # Bu oldingi bug edi: butun tasvir mediani olinayotgan edi.

    anchors = {
        'cold_lst': cold_lst,
        'hot_lst': hot_lst,
        'hot_rn_g0': hot_rn_g0,
        'hot_mask': hot_mask,
        'cold_mask': cold_mask,
    }

    return anchors


# ==============================================================
# M6: WIND & MOMENTUM
# ==============================================================

def compute_friction_velocity(image):
    """
    Ishqalanish tezligi u*(x,y) — ERA5 wind dan.

    Jarayon:
      1. ERA5 10m wind → 200m (blending height) extrapolyatsiya
      2. 200m wind → har piksel uchun u*(x,y) disaggregatsiya

    Formula (Allen/METRIC):
      u_200 = u_10 × ln(200/z0m_ws) / ln(10/z0m_ws)
      u*(x,y) = k × u_200 / ln(200/z0m(x,y))

    Dastlabki hisob — neytral sharoit (ψm = 0).
    Iteratsiyada ψm qo'shiladi.
    """
    wcfg = cfg.WIND

    wind_10 = image.select('WIND_SPEED_10M')
    z0m = image.select('Z0M')

    z_ref = wcfg['z_ref_era5']       # 10m
    z_blend = wcfg['z_blending']     # 200m
    z0m_ws = wcfg['z0m_weather']     # 0.12m (grass)
    k = cfg.VON_KARMAN               # 0.41

    # 1. 10m → 200m extrapolyatsiya (neytral, log profile)
    u_200 = wind_10.multiply(
        ee.Number(z_blend / z0m_ws).log().divide(
            ee.Number(z_ref / z0m_ws).log()
        )
    ).rename('U_200')

    # 2. u*(x,y) — har piksel uchun lokal z₀m dan
    # u* = k × u_200 / ln(200 / z₀m)
    ustar = (u_200.multiply(k)
             .divide(ee.Image(z_blend).divide(z0m).log())
             .rename('USTAR'))

    # u* minimum — juda past shamolda raqamiy beqarorlik
    ustar = ustar.max(0.02)

    return image.addBands(u_200).addBands(ustar)


def compute_rah_neutral(image):
    """
    Aerodinamik qarshilik — neytral sharoit (1-iteratsiya).

    rah = ln(z₁/z₂) / (k × u*)

    z₁ = 2.0m  (yuqori integratsiya chegarasi)
    z₂ = 0.1m  (pastki integratsiya chegarasi)

    Bu faqat boshlang'ich qiymat — iteratsiyada ψh bilan tuzatiladi.
    """
    wcfg = cfg.WIND
    k = cfg.VON_KARMAN

    ustar = image.select('USTAR')

    ln_ratio = ee.Number(wcfg['z1'] / wcfg['z2']).log()

    rah = (ee.Image(ln_ratio)
           .divide(ustar.multiply(k))
           .rename('RAH'))

    # rah minimum (juda past qarshilik fizik emas)
    rah = rah.max(1.0)

    return image.addBands(rah)


# ==============================================================
# M7: SENSIBLE HEAT FLUX — Monin-Obukhov Iteration
# ==============================================================

def compute_sensible_heat_flux(image, anchors, roi):
    """
    Sezuvchan issiqlik oqimi H — iterativ hisoblash.
    Bastiaanssen (1998) original SEBAL yondashuvi (F.24-32).

    ASOSIY FARAZ (klassik SEBAL, o'zgarmagan):
      Cold pixel: δTa_cold = 0  (H_cold = 0 — yaxshi sug'orilgan
                   maydonda butun mavjud energiya ET'ga sarflanadi)
      Hot pixel:  δTa_hot = H_hot × rah_hot / (ρₐ × cₚ)
                   H_hot = Q* - G₀  (hot pikselda λE = 0)

    Konvergensiya mezoni — SEBAL Manual, Appendix 8:
      "This iterative process is repeated until the successive
       values for dThot and rah at the 'hot' pixel have stabilized."
      Ya'ni H o'zgarishi EMAS, balki hot pikseldagi dT va rah
      stabillashishi tekshiriladi (mutlaq tolerantlik + min_iter).

    Qo'shilgan raqamli xavfsizlik choralari (SEBAL fizikasini
    o'zgartirmaydi, faqat ekstremal/degenerativ holatlardan himoya
    qiladi):
      - dT'ni [cold_dT, hot_dT] ± 20% margin oralig'iga cheklash
        (chiziqli ekstrapolyatsiyaning cheksiz o'sib ketishidan himoya)
      - Ta (hisoblangan havo harorati)ni ERA5 AIR_TEMP ± 15K bilan
        solishtirib, chetga chiqqan qiymatlarni tuzatish (QA)
      - H'ni fizik chegaraga cheklash: -100 ≤ H ≤ (Rn-G0)
        (λE ≥ 0 kafolati, L_MO'ga buzuq H kirishining oldini olish)

    Odatda 3-5 iteratsiyada stabillashadi (max_iter=8 — faqat
    xavfsizlik chegarasi).
    """
    cold_lst = anchors['cold_lst']
    hot_lst = anchors['hot_lst']
    hot_rn_g0 = anchors['hot_rn_g0']
    hot_mask = anchors['hot_mask']

    lst = image.select('LST')
    rho_air = image.select('RHO_AIR')
    u_200 = image.select('U_200')
    z0m = image.select('Z0M')
    rn_g0 = image.select('RN_G0')          # Rn - G0, H chegarasi uchun
    air_temp_era5 = image.select('AIR_TEMP')  # Ta sanity-check uchun


    wcfg = cfg.WIND
    k = cfg.VON_KARMAN
    g = cfg.GRAVITY
    cp = cfg.CP_AIR
    z_blend = wcfg['z_blending']
    z1 = wcfg['z1']
    z2 = wcfg['z2']

    # Boshlang'ich u* va rah (neytral — allaqachon hisoblangan)
    ustar = image.select('USTAR')
    rah = image.select('RAH')

    # Hot pixel dagi ρₐ — bir marta olish yetarli (iteratsiyada o'zgarmaydi)
    hot_rho = ee.Number(
        rho_air.updateMask(hot_mask)
        .reduceRegion(
            reducer=ee.Reducer.median(),
            geometry=roi, scale=30,
            maxPixels=1e9, bestEffort=True
        ).get('RHO_AIR'))

    max_iter = cfg.ITERATION['max_iter']
    min_iter = cfg.ITERATION['min_iter']
    tol_dt = cfg.ITERATION['tol_dt']
    tol_rah = cfg.ITERATION['tol_rah']

    prev_dt_hot = None
    prev_rah_hot = None
    converged_at = None

    for i in range(max_iter):

        # --- 1. Hot pixel dagi rah — FAQAT hot piksellardan ---
        hot_rah = ee.Number(
            rah.updateMask(hot_mask)
            .reduceRegion(
                reducer=ee.Reducer.median(),
                geometry=roi, scale=30,
                maxPixels=1e9, bestEffort=True
            ).get('RAH'))

        # --- 2. δTa_hot — Bastiaanssen F.30, H_hot = Q*-G₀ (hot pikselda λE=0) ---
        dta_hot = hot_rn_g0.multiply(hot_rah).divide(hot_rho.multiply(cp))

        # --- 3. Chiziqli kalibratsiya: cold dT=0, hot dT=dta_hot ---
        c4 = dta_hot.divide(hot_lst.subtract(cold_lst))
        c5 = c4.multiply(cold_lst).multiply(-1)

        # --- 4. Har piksel uchun δTa ---
        dta_raw = lst.multiply(c4).add(c5)

        # ── XAVFSIZLIK 1: dT'ni [0, dta_hot] ± 20% margin'ga cheklash ──
        # (cold_dT=0 va hot_dT=dta_hot orasidagi "fizik kutilgan" oraliq)
        dt_lower = ee.Number(0).min(dta_hot)
        dt_upper = ee.Number(0).max(dta_hot)
        margin = dt_upper.subtract(dt_lower).multiply(0.2)
        dta = dta_raw.clamp(
            dt_lower.subtract(margin),
            dt_upper.add(margin)
        ).rename('DTA')

        # ── XAVFSIZLIK 2: Ta = T0 - dT, ERA5 AIR_TEMP ± 15K bilan QA ──
        ta_img = lst.subtract(dta)
        ta_min = air_temp_era5.subtract(15)
        ta_max = air_temp_era5.add(15)
        ta_img = ta_img.where(ta_img.lt(ta_min), ta_min)
        ta_img = ta_img.where(ta_img.gt(ta_max), ta_max)
        # Ta tuzatilgan bo'lsa, dT ham mos ravishda qayta hisoblanadi
        # (T0 o'zgarmaydi, faqat Ta chegaralanganda dT ta'sirlanadi)
        dta = lst.subtract(ta_img).rename('DTA')

        # --- 5. H = ρₐ × cₚ × δTa / rah ---
        h_raw = (rho_air.multiply(cp)
                 .multiply(dta)
                 .divide(rah))

        # ── XAVFSIZLIK 3: H ni fizik chegaraga cheklash ──
        # H ≤ Rn-G0 (λE≥0 kafolati), H ≥ -100 W/m² (haddan tashqari
        # manfiy H'dan himoya — L_MO hisobini buzmasligi uchun)
        h = h_raw.min(rn_g0).max(-100).rename('H')

        # --- Diagnostika: hot pixeldagi dT/rah — konvergensiya uchun ---
        hot_check = (image.select([]).addBands(dta).addBands(rah)
                     .updateMask(hot_mask)
                     .reduceRegion(
                         reducer=ee.Reducer.median(),
                         geometry=roi, scale=30,
                         maxPixels=1e9, bestEffort=True))
        dt_hot_val = hot_check.get('DTA').getInfo()
        rah_hot_val = hot_check.get('RAH').getInfo()

        # ── KONVERGENSIYA — SEBAL Manual Appendix 8 ──
        if (prev_dt_hot is not None and prev_rah_hot is not None
                and (i + 1) >= min_iter):
            if (abs(dt_hot_val - prev_dt_hot) < tol_dt and
                    abs(rah_hot_val - prev_rah_hot) < tol_rah):
                converged_at = i + 1
                print(f"  ✅ Konvergensiya {i+1}-iteratsiyada: "
                      f"dT_hot={dt_hot_val:.4f} K, "
                      f"rah_hot={rah_hot_val:.3f} s/m")
                break

        prev_dt_hot = dt_hot_val
        prev_rah_hot = rah_hot_val
        print(f"  iter {i+1}: dT_hot={dt_hot_val:.4f} K, "
              f"rah_hot={rah_hot_val:.3f} s/m")

        # --- 6. Monin-Obukhov uzunligi L ---
        h_safe = h.where(h.abs().lt(1.0), ee.Image(1.0))
        L_mo = (rho_air.multiply(cp)
                .multiply(ustar.pow(3))
                .multiply(lst)
                .divide(ee.Image(k * g).multiply(h_safe))
                .multiply(-1)
                .rename('L_MO'))
        L_mo = L_mo.clamp(-1e6, 1e6)

        # --- 7. Barqarorlik tuzatmalari ψm, ψh (Paulson/Webb) ---
        psi_m_200, psi_h = _stability_corrections(L_mo, z_blend, z1, z2)

        # --- 8. u* va rah yangilash — KEYINGI iteratsiya uchun ---
        ustar = (ee.Image(k).multiply(u_200)
                 .divide(ee.Image(z_blend).divide(z0m).log().subtract(psi_m_200))
                 .rename('USTAR'))
        ustar = ustar.max(0.02)

        rah = (ee.Image(z1 / z2).log().subtract(psi_h)
               .divide(ustar.multiply(k))
               .rename('RAH'))
        rah = rah.max(1.0)

    else:
        print(f"  ⚠️ {max_iter} iteratsiyada konvergensiya topilmadi — "
              f"eng so'nggi H bilan davom etadi")

    # Yakuniy bandlar
    image = image.addBands(dta, overwrite=True)
    image = image.addBands(h, overwrite=True)
    image = image.addBands(ustar, overwrite=True)
    image = image.addBands(rah, overwrite=True)
    image = image.addBands(L_mo, overwrite=True)

    image = image.set('h_converged_iter',
                       converged_at if converged_at is not None else -1)

    return image


def _stability_corrections(L_mo, z_blend, z1, z2):
    """
    Paulson (1970) barqarorlik tuzatmalari.

    Nobarqaror (L < 0):
      x = (1 - 16×z/L)^0.25
      ψm = 2×ln((1+x)/2) + ln((1+x²)/2) - 2×arctan(x) + π/2
      ψh = 2×ln((1+x²)/2)

    Barqaror (L > 0):
      ψm = ψh = -5 × z/L

    Returns: psi_m_200, psi_h (z1/z2 orasida)
    """
    import math

    # --- Nobarqaror (L < 0) ---
    # z_blend (200m) uchun x_200
    x_200 = (ee.Image(1.0)
             .subtract(ee.Image(16.0 * z_blend).divide(L_mo))
             .max(0.001)  # manfiy bo'lmasligi uchun
             .pow(0.25))

    psi_m_200_unstable = (
        x_200.add(1).divide(2).log().multiply(2)
        .add(x_200.pow(2).add(1).divide(2).log())
        .subtract(x_200.atan().multiply(2))
        .add(math.pi / 2)
    )

    # z1 (2m) uchun x_2
    x_2 = (ee.Image(1.0)
           .subtract(ee.Image(16.0 * z1).divide(L_mo))
           .max(0.001)
           .pow(0.25))

    psi_h_2_unstable = x_2.pow(2).add(1).divide(2).log().multiply(2)

    # z2 (0.1m) uchun
    x_01 = (ee.Image(1.0)
            .subtract(ee.Image(16.0 * z2).divide(L_mo))
            .max(0.001)
            .pow(0.25))

    psi_h_01_unstable = x_01.pow(2).add(1).divide(2).log().multiply(2)

    # ψh = ψh(z1) - ψh(z2) — ikki balandlik orasidagi farq
    psi_h_unstable = psi_h_2_unstable.subtract(psi_h_01_unstable)

    # --- Barqaror (L > 0), Eq. 38-39 ---
    # MUHIM: Allen et al. (2007, ASCE) ga ko'ra, bandning nomi "200m" bo'lsa
    # ham, STABLE sharoitda formulada ATAYLAB z=2m ishlatiladi (200m emas),
    # chunki barqaror chegara qatlami juda yupqa va 200m ishlatilsa
    # raqamli beqarorlik (numerical instability) paydo bo'ladi.
    psi_m_200_stable = ee.Image(-5.0 * z1).divide(L_mo)   # z1 = 2.0m (config.WIND)
    psi_h_stable = (ee.Image(-5.0 * z1).divide(L_mo)
                    .subtract(ee.Image(-5.0 * z2).divide(L_mo)))

    # --- Shartli tanlash ---
    is_unstable = L_mo.lt(0)

    psi_m_200 = (psi_m_200_unstable.where(is_unstable.Not(), psi_m_200_stable)
                 .clamp(-10, 10))

    psi_h = (psi_h_unstable.where(is_unstable.Not(), psi_h_stable)
             .clamp(-10, 10))

    return psi_m_200, psi_h


# ==============================================================
# M8: LATENT HEAT FLUX λE — Energy Balance Residual
# ==============================================================

def compute_latent_heat_flux(image):
    """
    Yashirin issiqlik oqimi — Bastiaanssen F.32.

    λE = Q* - G₀ - H  (W/m²)

    Bu SEBAL ning yakuniy natijasi (lahzali).
    Salbiy λE fizik emas — 0 ga clamp qilinadi.
    (Kechqurun kondensatsiya bo'lishi mumkin, lekin Landsat
     faqat kunduzi o'tadi)
    """
    rn = image.select('RN')
    g0 = image.select('G0')
    h = image.select('H')

    lambda_e = (rn.subtract(g0).subtract(h)
                .max(0)
                .rename('LAMBDA_E'))

    return image.addBands(lambda_e)


# ==============================================================
# EVAPORATIVE FRACTION Λ
# ==============================================================

def compute_evaporative_fraction(image):
    """
    Bug'lanish ulushi — Bastiaanssen (1998), Gediz F.2.

    Λ = λE / (Q* - G₀)

    Λ xususiyatlari:
      - Kunboyi deyarli barqaror (10:00–15:00)
      - 0 (to'liq quruq) dan 1 (to'liq ho'l) gacha
      - Monthly extrapolation uchun kalit parametr

    Bu ETrF bilan deyarli bir xil, lekin semantik farq bor:
      - ETrF: reference ET ga nisbat
      - Λ: mavjud energiyaga nisbat
    """
    lambda_e = image.select('LAMBDA_E')
    rn_g0 = image.select('RN_G0')

    rn_g0_safe = rn_g0.max(10)

    evap_frac = (lambda_e.divide(rn_g0_safe)
                 .clamp(0, 1.0)
                 .rename('EVAP_FRAC'))

    return image.addBands(evap_frac)


# ==============================================================
# MAIN: Full energy balance
# ==============================================================

def compute_all(image, roi):
    """
    To'liq energiya balansini hisoblash.

    Tartib:
      1. Wind & momentum (u*, u_200)
      2. Neytral rah
      3. Anchor pixel selection
      4. H iteratsiya (Monin-Obukhov)
      5. λE = Q* - G₀ - H
      6. ETrF, Λ

    Input:  Image with surface properties + radiation
    Output: Image with H, LAMBDA_E, ETrF, EVAP_FRAC bands

    Anchor pixel tanlash ROI kerak — shuning uchun
    bu funksiya map() ichida emas, alohida chaqiriladi.
    """
    # M6: Wind & momentum
    image = compute_friction_velocity(image)
    image = compute_rah_neutral(image)

    # M5: Anchor selection
    anchors = select_anchor_pixels(image, roi)

    # M7: Sensible heat flux (iterativ)
    image = compute_sensible_heat_flux(image, anchors, roi)

    # M8: Latent heat flux
    image = compute_latent_heat_flux(image)
    image = compute_evaporative_fraction(image)

    return image

def get_anchor_cropland_mask(image, roi):
    """
    Anchor tanlash uchun cropland mask.
    Faqat ESA WorldCover class 40 — cropland.
    """
    proj = image.select('LST').projection()

    cropland = (
        ee.ImageCollection(cfg.CROPLAND_COLLECTION)
        .first()
        .select('Map')
        .eq(cfg.CROPLAND_CLASS)
        .rename('ANCHOR_CROPLAND')
        .clip(roi)
        .reproject(crs=proj, scale=30)
    )

    valid_lst = image.select('LST').mask()

    return cropland.updateMask(valid_lst)
