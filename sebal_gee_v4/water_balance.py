"""
SEBAL-GEE v4 — HOT PIKSEL SUV BALANSI (FAO-56)  [faqat SEBAL_ID]
================================================================
Tasumi (2003) Eq. 5.1-5.5 + FAO-56 (Allen et al. 1998) yalang'och tuproq
bug'lanish modeli. Hot pikselda yaqinda yog'gan yomg'irdan qoldiq bug'lanishni
hisobga oladi:

    ET_hot = ETrF_hot · ETr,   ETrF_hot = Ke_hot = Kr · ETrF_max   (ETrF_max=1.05)

    TEW = 1000·(θ_FC − 0.5·θ_WP)·Ze   [mm]  (5.3)
    Stage 1 (De ≤ REW):  Kr = 1
    Stage 2 (De > REW):  Kr = (TEW − De)/(TEW − REW)                 (5.4)
    Kunlik balans: De,i = De,i-1 − (P_i − RO_i) + E_i,  E_i = Ke·ETr  (5.5)
                   0 ≤ De,i ≤ TEW

Ma'lumot manbalari (foydalanuvchi tanlovi):
  - Yog'in P: CHIRPS DAILY (UCSB-CHG/CHIRPS/DAILY, mm/kun)
  - Tuproq θ_FC, θ_WP, REW: OpenLandMap USDA tekstura klassi → Table 5.1
  - Ze = 0.10 m, RO = 0

Chiqish: ETrF_hot (client skalyar) — energy_balance.compute_all uni λET_hp ga
o'giradi (λET_hp = ETrF_hot·ETr_inst·λ/3600).
"""

import ee
import math
from datetime import datetime, timezone
from . import ref_et

CHIRPS = 'UCSB-CHG/CHIRPS/DAILY'
TEXTURE = 'OpenLandMap/SOL/SOL_TEXTURE-CLASS_USDA-TT_M/v02'   # band 'b0' (0 sm), 1-12
SAND = 'OpenLandMap/SOL/SOL_SAND-WFRACTION_USDA-3A1A1A_M/v02'  # band 'b0', % (w)
CLAY = 'OpenLandMap/SOL/SOL_CLAY-WFRACTION_USDA-3A1A1A_M/v02'  # band 'b0', % (w)

# USDA tekstura klassi (1-12) → (θ_FC, θ_WP, REW mm) — FAO-56 Table 5.1 (Allen 1998)
# o'rta qiymatlari. Table 5.1 da yo'q klasslar (sandy clay, clay loam, sandy clay
# loam) eng yaqin turdan taxminlangan.
_SOIL = {
    1:  (0.36, 0.22, 10.0),   # Clay
    2:  (0.36, 0.23, 10.0),   # Silty clay
    3:  (0.30, 0.19, 9.0),    # Sandy clay   (taxmin)
    4:  (0.32, 0.16, 9.5),    # Clay loam    (taxmin ~silt clay loam)
    5:  (0.335, 0.205, 9.5),  # Silty clay loam
    6:  (0.24, 0.14, 8.5),    # Sandy clay loam (taxmin)
    7:  (0.25, 0.12, 9.0),    # Loam
    8:  (0.29, 0.15, 9.5),    # Silt loam
    9:  (0.23, 0.11, 8.0),    # Sandy loam
    10: (0.32, 0.17, 9.5),    # Silt
    11: (0.15, 0.065, 6.0),   # Loamy sand
    12: (0.12, 0.045, 4.5),   # Sand
}
_SOIL_DEFAULT = (0.25, 0.12, 9.0)   # Loam — tekstura topilmasa


def _saxton_fc_wp(sand_pct, clay_pct, om_pct=2.0):
    """
    θ_FC (33 kPa) va θ_WP (1500 kPa) — Saxton & Rawls (2006) pedotransfer.

    Kirish: sand/clay OG'IRLIK % (OpenLandMap b0), om — organik modda % (default 2).
    Chiqish: (FC, WP) hajmiy nam [m³/m³].

    NEGA: tekstura-klass (12 diskret) o'rniga HAQIQIY sand/clay tarkibidan
    UZLUKSIZ, har-piksel θ. Global (AQSh + O'zbekiston). HWSD2 da θFC/θWP alohida
    YO'Q (faqat AWC+tekstura) → bu usul tanlandi. REW esa tekstura-klassdan (Table 19).
    """
    S = sand_pct / 100.0
    C = clay_pct / 100.0
    OM = om_pct
    t15 = (-0.024 * S + 0.487 * C + 0.006 * OM + 0.005 * (S * OM)
           - 0.013 * (C * OM) + 0.068 * (S * C) + 0.031)
    WP = t15 + (0.14 * t15 - 0.02)
    t33 = (-0.251 * S + 0.195 * C + 0.011 * OM + 0.006 * (S * OM)
           - 0.027 * (C * OM) + 0.452 * (S * C) + 0.299)
    FC = t33 + (1.283 * t33 ** 2 - 0.374 * t33 - 0.015)
    # fizik chegara (nofizik pedotransfer chiqishidan himoya)
    FC = min(max(FC, 0.10), 0.50)
    WP = min(max(WP, 0.02), 0.35)
    if WP >= FC:                    # WP < FC kafolati
        WP = FC - 0.03
    return FC, WP


def hot_pixel_etrf(image, roi, hot_mask, window_days=30, ze=0.10,
                   etrf_max=1.05, verbose=True):
    """
    Hot piksel uchun ETrF_hot ni (Kr·ETrF_max) FAO-56 kunlik suv balansidan
    hisoblaydi. Client skalyar qaytaradi.

    MUHIM: suv balansi BITTA NUQTA uchun — metod (cimec/plan/…) topgan hot
    kandidatlar (hot_mask) ICHIDAN eng issig'i (= eng quruq, point_anchor
    mantig'i). Yog'in LOKAL: o'sha nuqtaning CHIRPS tarixidan (butun ROI
    o'rtachasi EMAS — yomg'ir fazoviy o'zgaruvchan).

    image — overpass sahnasi (system:time_start, LST, DEM bandlari bilan).
    hot_mask — metod topgan hot kandidat piksellar (anchors['hot_mask']).
    """
    date = ee.Date(image.get('system:time_start'))
    day0 = ee.Date(date.format('YYYY-MM-dd'))      # overpass kuni 00:00 UTC
    start = day0.advance(-window_days, 'day')
    dem = image.select('DEM')

    # --- 1. Hot piksel BITTA NUQTASI: kandidatlar (hot_mask) ichidan eng
    #        issig'i (max LST) + uning KOORDINATASI (max(3): LST, lon, lat). ---
    ll = ee.Image.pixelLonLat()
    loc = (image.select('LST').updateMask(hot_mask).addBands(ll)
           .reduceRegion(ee.Reducer.max(3), roi, 30, maxPixels=1e9,
                         bestEffort=True, tileScale=4)).getInfo()
    lon = loc.get('max1'); lat = loc.get('max2')   # max=LST, max1=lon, max2=lat
    if lon is None or lat is None:
        if verbose:
            print("    💧 Hot suv balansi: hot piksel topilmadi → ETrF_hot=0")
        return 0.0
    hot_pt = ee.Geometry.Point([lon, lat])

    # --- 2. Tuproq SHU NUQTADA: sand/clay → Saxton-Rawls θFC/θWP (uzluksiz);
    #        REW tekstura-klassdan (FAO-56 Table 19). Bitta reduceRegion. ---
    soil_img = (ee.Image(SAND).select('b0').rename('sand')
                .addBands(ee.Image(CLAY).select('b0').rename('clay'))
                .addBands(ee.Image(TEXTURE).select('b0').rename('tex')))
    s = soil_img.reduceRegion(ee.Reducer.first(), hot_pt, 250,
                              maxPixels=1e9).getInfo()
    sand = s.get('sand'); clay = s.get('clay'); tex = s.get('tex')
    tex_class = int(round(tex)) if (tex is not None and tex >= 1) else -1
    _, _, REW = _SOIL.get(tex_class, _SOIL_DEFAULT)       # REW — tekstura (Table 19)
    if sand is not None and clay is not None:
        FC, WP = _saxton_fc_wp(sand, clay)               # uzluksiz pedotransfer
        soil_src = f"Saxton(S{sand:.0f}/C{clay:.0f})"
    else:                                                 # fallback: tekstura Table 5.1
        FC, WP, REW = _SOIL.get(tex_class, _SOIL_DEFAULT)
        soil_src = f"tex#{tex_class}"
    TEW = max(1000.0 * (FC - 0.5 * WP) * ze, REW + 1.0)   # TEW>REW kafolati

    # --- 3. Kunlik P (CHIRPS) SHU NUQTADA — bitta getRegion (vaqt qatori) ---
    p_rows = (ee.ImageCollection(CHIRPS).filterDate(start, day0)
              .select('precipitation').getRegion(hot_pt, 5000)).getInfo()
    p_by_day = {}
    for r in p_rows[1:]:
        d_str = datetime.fromtimestamp(r[3] / 1000, tz=timezone.utc).strftime('%Y-%m-%d')
        p_by_day[d_str] = r[4] if r[4] is not None else 0.0

    # --- 4. Kunlik ETr (alfalfa FAO-56 PM) SHU NUQTADA — bitta getRegion ---
    def _etr_img(d):
        day = start.advance(ee.Number(d), 'day')
        met = ref_et.get_daily_era5_aggregate(day, roi)
        etr = (ref_et.RefETCalculator(ref_type='alfalfa')
               .calculate(met, dem, mode='daily').select('ETr'))
        return etr.set('system:time_start', day.millis())
    etr_col = ee.ImageCollection(ee.List.sequence(0, window_days - 1).map(_etr_img))
    e_rows = etr_col.getRegion(hot_pt, 100).getInfo()
    etr_by_day = {}
    for r in e_rows[1:]:
        d_str = datetime.fromtimestamp(r[3] / 1000, tz=timezone.utc).strftime('%Y-%m-%d')
        etr_by_day[d_str] = r[4] if r[4] is not None else 0.0

    # --- 5. FAO-56 kunlik balans (Python skalyar), oyna kunlari tartibida ---
    De = TEW      # boshlang'ich: quruq (oyna ichida yomg'ir bo'lsa tushadi)
    for d_str in sorted(set(p_by_day) | set(etr_by_day)):
        p = p_by_day.get(d_str, 0.0)
        etr = etr_by_day.get(d_str, 0.0)
        Kr = 1.0 if De <= REW else max(0.0, min(1.0, (TEW - De) / (TEW - REW)))
        E = Kr * etrf_max * etr            # E_i = Ke·ETr
        De = De - (p - 0.0) + E            # RO = 0
        De = max(0.0, min(TEW, De))

    # --- Overpass kuni ETrF_hot (kirish De = oyna oxiridagi depletion) ---
    Kr = 1.0 if De <= REW else max(0.0, min(1.0, (TEW - De) / (TEW - REW)))
    etrf_hot = Kr * etrf_max

    if verbose:
        print(f"    💧 Hot suv balansi @({lat:.3f},{lon:.3f}): {soil_src} "
              f"FC={FC:.2f} WP={WP:.2f} TEW={TEW:.1f} REW={REW:.1f} | De={De:.1f} "
              f"Kr={Kr:.3f} → ETrF_hot={etrf_hot:.3f}")

    return etrf_hot
