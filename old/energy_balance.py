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
    flat_mask = slope.lt(acfg['slope_max'])
    valid = image.mask().reduce(ee.Reducer.allNonZero())
    base_mask = flat_mask.And(valid)

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

    # ---- 3. Cold pixel kandidatlar ----
    cold_mask = (
        base_mask
        .And(ndvi.gte(ndvi_p_cold))
        .And(lst.lte(lst_p_cold))
        .And(albedo.lt(acfg['cold_albedo_max']))
    )

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

    # ---- 5. δTa koeffitsientlarni hisoblash (F.30) ----
    # Cold pixel: H = 0 → δTa = 0
    # Hot pixel:  H = Q* - G₀ → δTa kerak (rah bilan birga iteratsiyada)
    #
    # Dastlabki (neytral) δTa:
    #   Hot pixel uchun taxminiy rah kerak — bu M7 da iteratsiyada
    #   aniqlanadi. Shu yerda faqat LST qiymatlarni qaytaramiz.

    anchors = {
        'cold_lst': cold_lst,
        'hot_lst': hot_lst,
        'hot_rn_g0': hot_rn_g0,
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

    SEBAL ning eng muhim qismi!

    Jarayon (har iteratsiyada):
      1. δTa lineer koeffitsientlarni hisoblash (c₄, c₅)
         Hot pixel: δTa_hot = H_hot × rah_hot / (ρₐ × cₚ)
         Cold pixel: δTa_cold = 0
         → c₄ = δTa_hot / (T_hot - T_cold)
         → c₅ = -c₄ × T_cold

      2. Har piksel uchun δTa hisoblash
         δTa(x,y) = c₄ × T₀(x,y) + c₅

      3. H(x,y) = ρₐ × cₚ × δTa / rah

      4. Monin-Obukhov uzunligi L hisoblash
         L = -ρₐ × cₚ × u*³ × T₀ / (k × g × H)

      5. Barqarorlik tuzatmalari ψm, ψh hisoblash

      6. u* va rah yangilash

      7. → Qayta 1-bosqichga

    Odatda 3-5 iteratsiya yetarli.
    """
    cold_lst = anchors['cold_lst']
    hot_lst = anchors['hot_lst']
    hot_rn_g0 = anchors['hot_rn_g0']

    lst = image.select('LST')
    rho_air = image.select('RHO_AIR')
    u_200 = image.select('U_200')
    z0m = image.select('Z0M')

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

    # ---- ITERATSIYA ----
    max_iter = cfg.ITERATION['max_iter']

    for i in range(max_iter):

        # --- 1. Hot pixel dagi rah qiymatini olish ---
        hot_rah = rah.reduceRegion(
            reducer=ee.Reducer.median(),
            geometry=roi,
            scale=30,
            maxPixels=1e9,
            bestEffort=True
        ).get('RAH')
        hot_rah = ee.Number(hot_rah)

        # Hot pixel uchun ρₐ
        hot_rho = rho_air.reduceRegion(
            reducer=ee.Reducer.median(),
            geometry=roi,
            scale=30,
            maxPixels=1e9,
            bestEffort=True
        ).get('RHO_AIR')
        hot_rho = ee.Number(hot_rho)

        # --- 2. δTa koeffitsientlar (F.30) ---
        # Hot: δTa_hot = H_hot × rah_hot / (ρₐ × cₚ)
        # H_hot = Q* - G₀ (hot pixel da λE = 0)
        dta_hot = hot_rn_g0.multiply(hot_rah).divide(hot_rho.multiply(cp))

        # Cold: δTa_cold = 0
        # Lineer koeffitsientlar:
        #   c₄ = (dta_hot - 0) / (T_hot - T_cold)
        #   c₅ = -c₄ × T_cold
        c4 = dta_hot.divide(hot_lst.subtract(cold_lst))
        c5 = c4.multiply(cold_lst).multiply(-1)

        # --- 3. Har piksel uchun δTa va H ---
        dta = lst.multiply(c4).add(c5).rename('DTA')

        h = (rho_air.multiply(cp)
             .multiply(dta)
             .divide(rah)
             .rename('H'))

        # --- 4. Monin-Obukhov uzunligi L ---
        # L = -(ρₐ × cₚ × u*³ × T₀) / (k × g × H)
        # H = 0 bo'lganda L → ∞ (neytral) — himoya kerak
        h_safe = h.where(h.abs().lt(1.0), ee.Image(1.0))

        L_mo = (rho_air.multiply(cp)
                .multiply(ustar.pow(3))
                .multiply(lst)
                .divide(ee.Image(k * g).multiply(h_safe))
                .multiply(-1)
                .rename('L_MO'))

        # L ni oqilona oralig'iga cheklash
        L_mo = L_mo.clamp(-1e6, 1e6)

        # --- 5. Barqarorlik tuzatmalari ψm va ψh ---
        # Paulson (1970) formulalari
        # Nobarqaror (L < 0): konvektiv
        # Barqaror (L > 0): barqaror stratifikatsiya

        psi_m_200, psi_h = _stability_corrections(L_mo, z_blend, z1, z2)

        # --- 6. u* va rah yangilash ---
        ustar = (ee.Image(k).multiply(u_200)
                 .divide(ee.Image(z_blend).divide(z0m).log().subtract(psi_m_200))
                 .rename('USTAR'))
        ustar = ustar.max(0.02)

        rah = (ee.Image(z1 / z2).log().subtract(psi_h)
               .divide(ustar.multiply(k))
               .rename('RAH'))
        rah = rah.max(1.0)

    # Iteratsiya tugadi — yakuniy H
    image = image.addBands(dta, overwrite=True)
    image = image.addBands(h, overwrite=True)
    image = image.addBands(ustar, overwrite=True)
    image = image.addBands(rah, overwrite=True)
    image = image.addBands(L_mo, overwrite=True)

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

    # --- Barqaror (L > 0) ---
    psi_m_200_stable = ee.Image(-5.0 * z_blend).divide(L_mo)
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
# ETrF — ET Reference Fraction
# ==============================================================

def compute_etrf(image):
    """
    ET reference fraction — instantaneous.

    ETrF = λE / λE_ref

    λE_ref = cold pixel dagi λE = Q* - G₀ (H=0)

    ETrF oralig'i:
      0.0 — to'liq quruq
      1.0 — reference ET ga teng (yaxshi sug'orilgan)
      >1.0 — adveksiya (issiq havodan qo'shimcha energiya)
      Odatda 0–1.4 oraliq
    """
    lambda_e = image.select('LAMBDA_E')
    rn_g0 = image.select('RN_G0')

    # Cold pixel dagi λE ≈ Q* - G₀ (maksimal bug'lanish)
    # Bu allaqachon RN_G0 band da bor
    # ETrF = λE / (Q* - G₀)  bu aslida Λ (evaporative fraction)
    # Lekin ETrF kontekstida cold pixel RN_G0 ning o'rtachasiga
    # nisbatan hisoblanadi

    # Sodda versiya: ETrF ≈ Λ = λE / (Q* - G₀)
    rn_g0_safe = rn_g0.max(10)  # division by zero himoyasi

    etrf = (lambda_e.divide(rn_g0_safe)
            .clamp(0, 1.5)
            .rename('ETrF'))

    return image.addBands(etrf)


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
    image = compute_etrf(image)
    image = compute_evaporative_fraction(image)

    return image
