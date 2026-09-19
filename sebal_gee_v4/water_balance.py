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

Ma'lumot manbalari (foydalanuvchi tanlovi) — HAMMASI anchor tanlagan AYNAN o'sha
hot pikselda (koordinatasi anchor'dan keladi):
  - Yog'in P: CHIRPS DAILY (UCSB-CHG/CHIRPS/DAILY, mm/kun)
  - θ_FC (33 kPa): OpenLandMap SOL_WATERCONTENT-33KPA (0 va 10 sm qatlam o'rtachasi)
  - θ_WP (1500 kPa): HiHydroSoil v2.0 WCpF4.2 (0–5 va 5–15 sm qatlam o'rtachasi)
  - REW: OpenLandMap USDA tekstura klassi → FAO-56 Table 19 (_SOIL)
  - Ze, ETrF_max, oynalar — config.HOT_WB; RO = 0
Tuproq qiymati topilmasa — XATO (default tuproq ishlatilmaydi).

Boshlang'ich holat: balans ikki marta — De₀ = 0 (nam) va De₀ = TEW (quruq) —
yuritiladi; overpass kuniga natijalar farqi ≤ tol bo'lmasa oyna uzaytiriladi
(config.HOT_WB['windows'], masalan 14 → 30 → 60 kun).

Chiqish: dict (etrf_hot, De, Kr, TEW, REW, FC, WP, P_sum, window, converged, …) —
energy_balance.compute_all ETrF_hot ni λET_hp ga o'giradi, qolganini sahna QC ga yozadi.
"""

import ee
from datetime import datetime, timedelta, timezone
from . import config as cfg
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


def check_chirps_month(year, month):
    """
    CHIRPS DAILY — oyning HAR kuni rasmi borligini tekshiradi (klient, BITTA getInfo).
    Kun yo'q → RuntimeError (sanalari bilan). Kunlik suv balanslari (consumptive_use,
    ndvi_kc, root_zone_water) bu tekshiruvdan keyin yog'inni to'g'ridan-to'g'ri oladi
    (oldin yo'q kun jimgina P = 0 edi).
    """
    import calendar
    days = calendar.monthrange(year, month)[1]
    start = ee.Date.fromYMD(year, month, 1)
    got = set(ee.ImageCollection(CHIRPS).filterDate(start, start.advance(days, 'day'))
              .aggregate_array('system:time_start')
              .map(lambda t: ee.Date(t).format('YYYY-MM-dd')).getInfo())
    missing = [f'{year}-{month:02d}-{d:02d}' for d in range(1, days + 1)
               if f'{year}-{month:02d}-{d:02d}' not in got]
    if missing:
        raise RuntimeError(
            f"CHIRPS DAILY yog'ini {year}-{month:02d} da {len(missing)} kun yo'q "
            f"({', '.join(missing[:5])}{' …' if len(missing) > 5 else ''}) — "
            f"default 0 ishlatilmaydi.")


def _soil_stack():
    """
    Tuproq xaritalari (xom, masshtablanmagan): 'fc' — OpenLandMap 33 kPa (qatlamlar
    o'rtachasi), 'wp' — HiHydroSoil v2 WCpF4.2 (qatlamlar o'rtachasi), 'tex' —
    OpenLandMap USDA tekstura. _soil_at_point VA soil_valid_mask AYNI shu manbadan.
    """
    hw = cfg.HOT_WB
    fc_img = ee.Image(hw['fc_asset']).select(list(hw['fc_bands'])).reduce(ee.Reducer.mean())
    wp_col = ee.ImageCollection(hw['wp_collection'])
    wp_img = (ee.ImageCollection([
        ee.Image(wp_col.filter(ee.Filter.stringContains('system:index', lay)).first())
        for lay in hw['wp_layers']]).mean())
    return (fc_img.rename('fc').addBands(wp_img.select([0]).rename('wp'))
            .addBands(ee.Image(TEXTURE).select('b0').rename('tex')))


def soil_valid_mask():
    """
    1 — θ_FC, θ_WP va tekstura (FAO-56 Table 19 dagi klass) BOR piksel, aks holda 0.
    SEBAL_ID oilasida hot anchor NOMZODLARI shu bilan cheklanadi: hot piksel tuproq
    bo'lishi kerak (shahar/suv — tuproq xaritalarida ma'lumot yo'q; 2023-03-21 CIMEC
    hot pikseli 53% qurilgan 250 m katakda edi → θ_WP yo'q → run to'xtardi).
    """
    st = _soil_stack()
    classes = sorted(_SOIL)
    tex_ok = st.select('tex').remap(classes, [1] * len(classes), 0)
    return (st.mask().reduce(ee.Reducer.allNonZero()).And(tex_ok)
            .unmask(0).rename('SOIL_OK'))


def _soil_at_point(pt, proj, scale):
    """
    Hot piksel nuqtasida tuproq: θ_FC (33 kPa), θ_WP (1500 kPa), REW.
    Qatlamlar Ze ≈ 0.10 m ga mos (0–10 sm). Biror qiymat yo'q → RuntimeError.
    Namuna ANCHOR gridida (proj, scale) — AYNAN anchor pikseli; nomzodlar maskasi
    (soil_valid_mask) ham shu gridda baholangan → mos. (Oldin 250 m OpenLandMap
    gridida olinardi: WP/tekstura o'sha katak MARKAZIDAN — boshqa katak bo'lishi mumkin.)
    """
    hw = cfg.HOT_WB
    s = (_soil_stack()
         .reduceRegion(ee.Reducer.first(), pt, crs=proj, scale=scale)).getInfo()
    fc, wp, tex = s.get('fc'), s.get('wp'), s.get('tex')
    missing = [n for n, v in (('θ_FC (OpenLandMap 33 kPa)', fc), ('θ_WP (HiHydroSoil pF4.2)', wp),
                              ('tekstura (REW uchun)', tex)) if v is None]
    tex_class = int(round(tex)) if tex is not None else None
    if not missing and tex_class not in _SOIL:
        missing.append(f'tekstura klassi {tex_class} (Table 19 da yo\'q)')
    if missing:
        raise RuntimeError(
            f"Hot piksel tuprog'i topilmadi: {', '.join(missing)} — default tuproq ishlatilmaydi.")
    FC = fc * hw['fc_scale']
    WP = wp * hw['wp_scale']
    REW = _SOIL[tex_class][2]
    return FC, WP, REW, tex_class


def hot_pixel_etrf(image, roi, hot_lonlat, grid, verbose=True):
    """
    Hot piksel ETrF_hot = Kr·ETrF_max — FAO-56 kunlik suv balansidan (Tasumi 2003
    Eq. 5.1-5.5), anchor tanlagan AYNAN o'sha hot pikselda.

    hot_lonlat — [lon, lat] (energy_balance anchor'idagi 'hot_point', client).
    grid — (proj, scale): anchor tanlangan grid (tuproq AYNAN o'sha pikseldan).
    Qaytaradi: dict — etrf_hot, De, Kr, TEW, REW, FC, WP, P_sum, window,
    converged, etrf_wet_start, etrf_dry_start, lon, lat.
    """
    hw = cfg.HOT_WB
    ze, etrf_max, tol = hw['ze'], hw['etrf_max'], hw['conv_tol']
    lon, lat = float(hot_lonlat[0]), float(hot_lonlat[1])
    hot_pt = ee.Geometry.Point([lon, lat])
    date = ee.Date(image.get('system:time_start'))
    day0_str = date.format('YYYY-MM-dd').getInfo()
    day0 = ee.Date(day0_str)                       # overpass kuni 00:00 UTC
    day0_py = datetime.strptime(day0_str, '%Y-%m-%d')
    dem = image.select('DEM')

    # --- 1. Tuproq — AYNAN shu nuqtada (OpenLandMap 33 kPa, HiHydroSoil pF4.2) ---
    FC, WP, REW, tex_class = _soil_at_point(hot_pt, *grid)
    TEW = 1000.0 * (FC - 0.5 * WP) * ze
    tew_note = ''
    if TEW <= REW:                                      # Kr formulasi TEW > REW talab qiladi
        tew_note = f' (TEW {TEW:.1f} ≤ REW {REW:.1f} → TEW = REW + 1)'
        print(f"    ⚠️ Hot suv balansi: TEW {TEW:.1f} ≤ REW {REW:.1f} — TEW = REW + 1 olindi")
        TEW = REW + 1.0

    # --- 2. Kunlik P (CHIRPS) va ETr (alfalfa FAO-56 PM) — shu nuqtada, oyna bo'lib ---
    p_by_day, etr_by_day = {}, {}

    def _etr_img(day):
        met = ref_et.get_daily_era5_aggregate(day, roi)
        etr = (ref_et.RefETCalculator(ref_type='alfalfa')
               .calculate(met, dem, mode='daily').select('ETr'))
        return etr.set('system:time_start', day.millis())

    def _fetch(n_from, n_to):
        """[day0 − n_from, day0 − n_to) kunlari (n_from > n_to ≥ 0)."""
        start, end = day0.advance(-n_from, 'day'), day0.advance(-n_to, 'day')
        rows = (ee.ImageCollection(hw['precip_collection']).filterDate(start, end)
                .select(hw['precip_band']).getRegion(hot_pt, 5000)).getInfo()
        for r in rows[1:]:
            d = datetime.fromtimestamp(r[3] / 1000, tz=timezone.utc).strftime('%Y-%m-%d')
            if r[4] is None:
                raise RuntimeError(f"Hot piksel yog'ini ({hw['precip_collection']}) {d} kuni yo'q.")
            p_by_day[d] = r[4]
        # ETr — "User memory limit" bo'lmasligi uchun 5 kunlik bo'laklar
        CHUNK = 5
        for c0 in range(n_to, n_from, CHUNK):
            c1 = min(c0 + CHUNK, n_from)
            days = ee.List.sequence(c0 + 1, c1).map(
                lambda k: day0.advance(ee.Number(k).multiply(-1), 'day'))
            rws = (ee.ImageCollection(days.map(lambda d: _etr_img(ee.Date(d))))
                   .getRegion(hot_pt, 100)).getInfo()
            for r in rws[1:]:
                d = datetime.fromtimestamp(r[3] / 1000, tz=timezone.utc).strftime('%Y-%m-%d')
                if r[4] is None:
                    raise RuntimeError(f"Hot piksel ETr (ERA5 FAO-56) {d} kuni yo'q.")
                etr_by_day[d] = r[4]

    def _run(days, de0):
        De = de0
        for d in days:
            Kr = 1.0 if De <= REW else max(0.0, min(1.0, (TEW - De) / (TEW - REW)))
            E = Kr * etrf_max * etr_by_day[d]          # E_i = Ke·ETr
            De = max(0.0, min(TEW, De - p_by_day[d] + E))   # RO = 0
        Kr = 1.0 if De <= REW else max(0.0, min(1.0, (TEW - De) / (TEW - REW)))
        return De, Kr, Kr * etrf_max

    # --- 3. Boshlang'ich holatdan yaqinlashish: De₀=0 va De₀=TEW; oyna uzayadi ---
    fetched = 0
    for w in hw['windows']:
        _fetch(w, fetched)
        fetched = w
        w_start = (day0_py - timedelta(days=w)).strftime('%Y-%m-%d')
        days = sorted(d for d in p_by_day if d >= w_start)
        missing = [d for d in days if d not in etr_by_day]
        if missing or len(days) != w:
            raise RuntimeError(f"Hot suv balansi: {w} kunlik oynada kunlar to'liq emas "
                               f"(P {len(days)}/{w}, ETr yo'q: {missing[:3]}).")
        De_w, Kr_w, e_wet = _run(days, 0.0)
        De_d, Kr_d, e_dry = _run(days, TEW)
        converged = abs(e_wet - e_dry) <= tol
        if converged:
            break
    if not converged:
        print(f"    ⚠️ Hot suv balansi {w} kunda ham yaqinlashmadi: De₀=0 → {e_wet:.3f}, "
              f"De₀=TEW → {e_dry:.3f} (quruq boshlanish natijasi olindi)")

    res = {'etrf_hot': e_dry, 'De': De_d, 'Kr': Kr_d, 'TEW': TEW, 'REW': REW,
           'FC': FC, 'WP': WP, 'tex': tex_class, 'P_sum': sum(p_by_day[d] for d in days),
           'window': w, 'converged': converged, 'etrf_wet_start': e_wet,
           'etrf_dry_start': e_dry, 'lon': lon, 'lat': lat}
    if verbose:
        print(f"    💧 Hot suv balansi @({lat:.4f},{lon:.4f}): FC={FC:.3f} WP={WP:.3f} "
              f"TEW={TEW:.1f}{tew_note} REW={REW:.1f} | oyna {w} kun, P={res['P_sum']:.1f} mm | "
              f"De={De_d:.1f} Kr={Kr_d:.3f} → ETrF_hot={e_dry:.3f} "
              f"({'yaqinlashdi' if converged else 'YAQINLASHMADI'}: nam-start {e_wet:.3f})")
    return res
