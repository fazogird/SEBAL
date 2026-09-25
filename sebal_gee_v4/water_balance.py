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
  - θ_FC (33 kPa) va θ_WP (1500 kPa): BITTA mahsulot — HiHydroSoil v2.0 (0–5 va 5–15 sm
    qatlamlar o'rtachasi); θ_FC = van Genuchten θ(33 kPa) o'sha mahsulot parametrlaridan,
    θ_WP = WCpF4.2 → FC > WP kafolatli
  - REW: OpenLandMap USDA tekstura klassi → FAO-56 Table 5.1 (_SOIL, 3-ustun)
  - ETr kunlik: daily_et.get_daily_etr24 (alfalfa, 24 soatlik yig'indi — sahnaning ETr24
    bilan AYNI usul), lekin UTC kun (00–24 UTC) — CHIRPS DAILY kuni bilan AYNI (siljishsiz)
  - Ze, ETrF_max, oynalar — config.HOT_WB; RO = 0
Tuproq qiymati topilmasa — XATO; FC ≤ WP yoki TEW ≤ REW — anchor QC xatosi (SceneQCError →
kaskad keyingi anchorni sinaydi; soxta TEW ishlatilmaydi).

Boshlang'ich holat: De har doim [0, TEW] ichida (0 — nam, TEW — quruq). Shuning uchun
istalgan kundan boshlangan ikki chegaraviy yurish (De₀ = 0 va De₀ = TEW) haqiqiy holatni
o'rab oladi. Overpass'dan orqaga KUNMA-KUN uzaytiriladi; ikki chegara birinchi marta
≤ conv_tol bo'lganda — holat aniqlangan (natija — o'rtachasi). Kuchli yomg'ir
(P ≥ TEW + 1.05·ETr) kitob tartibida ikkala chegarani aniq 0 ga tushiradi; quruq davrda
ikkalasi 0 ga intiladi. max_lookback (21) kunda birlashmasa → HOT_WB_UNCERTAIN (anchor QC
xatosi; soxta/zaxira qiymat YO'Q).

Chiqish: dict (etrf_hot, De, Kr, TEW, REW, FC, WP, P_sum, window, converged, …) —
energy_balance.compute_all ETrF_hot ni λET_hp ga o'giradi, qolganini sahna QC ga yozadi.
"""

import ee
from datetime import datetime, timedelta, timezone
from . import config as cfg
from . import daily_et

CHIRPS = 'UCSB-CHG/CHIRPS/DAILY'
TEXTURE = 'OpenLandMap/SOL/SOL_TEXTURE-CLASS_USDA-TT_M/v02'   # band 'b0' (0 sm), 1-12

# USDA tekstura klassi (1-12) → (θ_FC, θ_WP, REW mm) — FAO-56 Table 5.1 (Allen 1998)
# o'rta qiymatlari. Table 5.1 da yo'q klasslar (sandy clay, clay loam, sandy clay
# loam) eng yaqin turdan taxminlangan. Hot suv balansi FAQAT REW (3-ustun) ni oladi
# (θ_FC/θ_WP — HiHydroSoil xaritasidan); θ_FC/θ_WP ustunlari va _SOIL_DEFAULT —
# etrf_water_balance (Appendix I) uchun.
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


def _hhs_layer(name, layer):
    """HiHydroSoil v2 qatlami (masalan 'wcsat', '0-5cm') — xom qiymat (×10⁻⁴ masshtabsiz)."""
    col = ee.ImageCollection(cfg.HOT_WB['hhs_base'] + name)
    return ee.Image(col.filter(ee.Filter.stringContains('system:index', layer)).first()).select([0])


def _vg_theta(layer, kpa):
    """
    van Genuchten θ(h) [m³/m³] — HiHydroSoil v2 o'z parametrlari (θs, θr, α [1/sm], n):
        θ(h) = θr + (θs − θr) / [1 + (α·h)^n]^(1 − 1/n),  h = kPa·10.197 [sm suv ustuni]
    Tekshirilgan: shu parametrlar mahsulotning o'z WCpF2 / WCpF4.2 qiymatlarini qaytaradi
    (Samarqand: θ(10 kPa) 0.394 vs WCpF2 0.395; θ(1500 kPa) 0.138 vs WCpF4.2 0.137).
    """
    k = cfg.HOT_WB['hhs_scale']
    ts = _hhs_layer('wcsat', layer).multiply(k)
    tr = _hhs_layer('wcres', layer).multiply(k)
    a = _hhs_layer('alpha', layer).multiply(k)
    n = _hhs_layer('N', layer).multiply(k)
    h = kpa * 10.197
    se = a.multiply(h).pow(n).add(1).pow(ee.Image(1).subtract(ee.Image(1).divide(n)).multiply(-1))
    return tr.add(ts.subtract(tr).multiply(se))


def _soil_stack():
    """
    Tuproq xaritalari (FIZIK birlikda, m³/m³): 'fc' — HiHydroSoil v2 van Genuchten θ(33 kPa),
    'wp' — HiHydroSoil v2 WCpF4.2 (ikkalasi 0–5 va 5–15 sm qatlamlar o'rtachasi — BITTA
    mahsulot → FC > WP), 'tex' — OpenLandMap USDA tekstura (REW uchun).
    _soil_at_point VA soil_valid_mask AYNI shu manbadan.
    """
    hw = cfg.HOT_WB
    fc_img = ee.ImageCollection([_vg_theta(lay, hw['fc_kpa'])
                                 for lay in hw['hhs_layers']]).mean()
    wp_col = ee.ImageCollection(hw['wp_collection'])
    wp_img = (ee.ImageCollection([
        ee.Image(wp_col.filter(ee.Filter.stringContains('system:index', lay)).first())
        for lay in hw['wp_layers']]).mean()).select([0]).multiply(hw['wp_scale'])
    return (fc_img.rename('fc').addBands(wp_img.rename('wp'))
            .addBands(ee.Image(TEXTURE).select('b0').rename('tex')))


def soil_fc_wp_rew():
    """
    LOYIHA BO'YICHA YAGONA tuproq manbai (2026-09-25, user qarori):
      fc, wp — HiHydroSoil v2 (van Genuchten θ(33 kPa) va WCpF4.2; 0–5 va 5–15 sm
               o'rtachasi) — hot piksel balansi bilan AYNI;
      rew    — FAO-56 Table 5.1 (USDA tekstura klassi, OpenLandMap) — REW ni na
               Saxton, na HiHydroSoil beradi, jadval yagona manba.
    Oldin CUirr / AW / Kc_ETo SoilGrids+Saxton FC/WP va REW = 0.15·loy+2 (manbasiz)
    ishlatardi — bitta piksel uchun ikki xil tuproq edi.
    Ma'lumot yo'q piksel MASKALANADI (soxta qiymat YO'Q).
    """
    st = _soil_stack()
    classes = sorted(_SOIL)
    rew = st.select('tex').remap(classes, [_SOIL[c][2] for c in classes],
                                 _SOIL_DEFAULT[2]).toFloat().rename('REW')
    return st.select('fc'), st.select('wp'), rew


def soil_valid_mask():
    """
    1 — θ_FC, θ_WP va tekstura (FAO-56 Table 5.1 dagi klass) BOR hamda fizik izchil
    (θ_FC > θ_WP, TEW > REW) piksel, aks holda 0. SEBAL_ID oilasida hot anchor NOMZODLARI
    shu bilan cheklanadi: hot piksel tuproq bo'lishi kerak (shahar/suv — tuproq
    xaritalarida ma'lumot yo'q; 2023-03-21 CIMEC hot pikseli 53% qurilgan 250 m katakda
    edi → θ_WP yo'q → run to'xtardi).
    """
    st = _soil_stack()
    classes = sorted(_SOIL)
    tex_ok = st.select('tex').remap(classes, [1] * len(classes), 0)
    rew = st.select('tex').remap(classes, [_SOIL[c][2] for c in classes])
    tew = (st.select('fc').subtract(st.select('wp').multiply(0.5))
           .multiply(1000.0 * cfg.HOT_WB['ze']))
    phys_ok = st.select('fc').gt(st.select('wp')).And(tew.gt(rew))
    return (st.mask().reduce(ee.Reducer.allNonZero()).And(tex_ok).And(phys_ok)
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
    missing = [n for n, v in (('θ_FC (HiHydroSoil VG 33 kPa)', fc), ('θ_WP (HiHydroSoil pF4.2)', wp),
                              ('tekstura (REW uchun)', tex)) if v is None]
    tex_class = int(round(tex)) if tex is not None else None
    if not missing and tex_class not in _SOIL:
        missing.append(f'tekstura klassi {tex_class} (Table 19 da yo\'q)')
    if missing:
        raise RuntimeError(
            f"Hot piksel tuprog'i topilmadi: {', '.join(missing)} — default tuproq ishlatilmaydi.")
    FC, WP = fc, wp                     # _soil_stack allaqachon m³/m³
    REW = _SOIL[tex_class][2]
    return FC, WP, REW, tex_class


def hot_pixel_etrf(image, roi, hot_lonlat, grid, etr24_source='era5', verbose=True):
    """
    Hot piksel ETrF_hot = Kr·ETrF_max — FAO-56 kunlik suv balansidan (Tasumi 2003
    Eq. 5.1-5.5), anchor tanlagan AYNAN o'sha hot pikselda.

    hot_lonlat — [lon, lat] (energy_balance anchor'idagi 'hot_point', client).
    grid — (proj, scale): anchor tanlangan grid (tuproq AYNAN o'sha pikseldan).
    etr24_source — kunlik ETr manbasi (sahnaning ETr24 bilan AYNI). Kun — UTC (CHIRPS kabi).
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
    if not (FC > WP and TEW > REW):                     # Kr formulasi TEW > REW talab qiladi
        # Soxta TEW (oldin REW + 1) EMAS — bu hot piksel tuprog'i yaroqsiz → anchor QC
        # xatosi: kaskad keyingi (metod, zona) ni sinaydi. (soil_valid_mask bunday
        # piksellarni nomzodlardan allaqachon chiqaradi — bu himoya.)
        from .energy_balance import SceneQCError
        raise SceneQCError(f"hot piksel tuprog'i fizik emas: FC {FC:.3f}, WP {WP:.3f}, "
                           f"TEW {TEW:.1f} mm, REW {REW:.1f} mm (FC > WP va TEW > REW kerak)")

    # --- 2. Kunlik P (CHIRPS) va ETr (alfalfa FAO-56 PM) — shu nuqtada, oyna bo'lib ---
    p_by_day, etr_by_day = {}, {}

    def _etr_img(day):
        # Usul sahnaning ETr24 bilan AYNI: alfalfa, 24 soatlik ASCE PM yig'indisi (kitob
        # App.B). KUN — UTC (utc_offset=0): yog'in CHIRPS DAILY 00–24 UTC (GEE time_start/
        # time_end tasdiqlangan) va uni mahalliy kunga bo'lib bo'lmaydi → P va ETr AYNI
        # kunda, siljishsiz. Balans overpass UTC kunidan OLDINGI kunlar bilan tugaydi:
        # Samarqand — overpass'dan ~6 soat oldin (05:00 mahalliy), AQSh — ~17 soat oldin.
        etr = daily_et.get_daily_etr24(day, roi, dem, ref_type='alfalfa',
                                       utc_offset=0, source=etr24_source)
        return etr.rename('ETr').set('system:time_start', day.millis())

    def _fetch(n_from, n_to):
        """[day0 − n_from, day0 − n_to) UTC kunlari (n_from > n_to ≥ 0): P va ETr."""
        start, end = day0.advance(-n_from, 'day'), day0.advance(-n_to, 'day')
        rows = (ee.ImageCollection(hw['precip_collection']).filterDate(start, end)
                .select(hw['precip_band']).getRegion(hot_pt, 5000)).getInfo()
        for r in rows[1:]:
            d = datetime.fromtimestamp(r[3] / 1000, tz=timezone.utc).strftime('%Y-%m-%d')
            if r[4] is None:
                raise RuntimeError(f"Hot piksel yog'ini ({hw['precip_collection']}) {d} kuni yo'q.")
            p_by_day[d] = r[4]
        days = ee.List.sequence(n_to + 1, n_from).map(
            lambda k: day0.advance(ee.Number(k).multiply(-1), 'day'))
        rws = (ee.ImageCollection(days.map(lambda d: _etr_img(ee.Date(d))))
               .getRegion(hot_pt, 100)).getInfo()
        for r in rws[1:]:
            d = datetime.fromtimestamp(r[3] / 1000, tz=timezone.utc).strftime('%Y-%m-%d')
            if r[4] is None:
                raise RuntimeError(f"Hot piksel ETr ({etr24_source} ETr24) {d} kuni yo'q.")
            etr_by_day[d] = r[4]

    def _kr(De):
        return 1.0 if De <= REW else max(0.0, min(1.0, (TEW - De) / (TEW - REW)))

    def _run(days, de0):
        """Tasumi Eq 5.5 (kitob tartibi): E_i = Kr(De_{i−1})·1.05·ETr_i; RO = 0."""
        De = de0
        for d in days:
            E = _kr(De) * etrf_max * etr_by_day[d]           # E_i = Ke·ETr, Ke = Kr·1.05
            De = max(0.0, min(TEW, De - p_by_day[d] + E))   # RO = 0 (user qarori 2026-09-21)
        return De, _kr(De), _kr(De) * etrf_max

    # --- 3. Boshlang'ich holat: kunma-kun orqaga, ikki chegara birlashguncha ---
    max_lb, chunk = int(hw['max_lookback']), int(hw['fetch_chunk'])
    fetched, k_used = 0, None
    while fetched < max_lb and k_used is None:
        n = min(fetched + chunk, max_lb)
        _fetch(n, fetched)
        for k in range(fetched + 1, n + 1):                  # k — orqaga necha kun
            days = [(day0_py - timedelta(days=j)).strftime('%Y-%m-%d') for j in range(k, 0, -1)]
            missing = [d for d in days if d not in p_by_day or d not in etr_by_day]
            if missing:
                raise RuntimeError(f"Hot suv balansi: kunlar to'liq emas (P/ETr yo'q: {missing[:3]}).")
            De_w, Kr_w, e_wet = _run(days, 0.0)
            De_d, Kr_d, e_dry = _run(days, TEW)
            if abs(e_wet - e_dry) <= tol:
                k_used = k
                break
        fetched = n
    if k_used is None:
        from .energy_balance import SceneQCError
        raise SceneQCError(
            f"HOT_WB_UNCERTAIN: {max_lb} kun orqaga ham boshlang'ich holat aniqlanmadi "
            f"(De₀=0 → ETrF_hot {e_wet:.3f}, De₀=TEW → {e_dry:.3f}; farq > {tol}) — "
            f"hot piksel namligi noma'lum")
    # Oynadagi oxirgi kuchli yomg'ir (kitob tartibida De → aniq 0) — QC uchun
    wet_reset = next((d for d in reversed(days)
                      if p_by_day[d] >= TEW + etrf_max * etr_by_day[d]), None)

    etrf_hot = 0.5 * (e_wet + e_dry)
    res = {'etrf_hot': etrf_hot, 'De': 0.5 * (De_w + De_d), 'Kr': 0.5 * (Kr_w + Kr_d),
           'TEW': TEW, 'REW': REW, 'FC': FC, 'WP': WP, 'tex': tex_class,
           'P_sum': sum(p_by_day[d] for d in days), 'window': k_used, 'converged': True,
           'etrf_wet_start': e_wet, 'etrf_dry_start': e_dry, 'wet_reset': wet_reset,
           'lon': lon, 'lat': lat}
    if verbose:
        print(f"    💧 Hot suv balansi @({lat:.4f},{lon:.4f}): FC={FC:.3f} WP={WP:.3f} "
              f"TEW={TEW:.1f} REW={REW:.1f} | holat {k_used} kunda aniqlandi, P={res['P_sum']:.1f} mm"
              f"{f', kuchli yomgir {wet_reset}' if wet_reset else ''} | De={res['De']:.1f} "
              f"Kr={res['Kr']:.3f} → ETrF_hot={etrf_hot:.3f} (nam {e_wet:.3f} / quruq {e_dry:.3f})")
    return res
