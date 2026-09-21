"""
SEBAL-GEE v4 — M9: Daily & Monthly ET
=======================================
Lahzali λE dan kunlik va oylik ET ga o'tish.

Kunlik (sahna kuni):
  SEBAL_B / pysebal : ET₂₄ = Λ × Rn24 × 86400 / λ
                      Rn24 = (1 − α)·Rs24 − 110·τ24,  τ24 = Rs24 / Ra24  [de Bruin 1987;
                      Bastiaanssen 2000] — Rs24 ERA5 (mahalliy kun), Ra24 FAO-56 Eq 21
  SEBAL_ID          : ET₂₄ = ETrF_inst × ETr24   (Tasumi 2003, Eq 5.6–5.8)
  SEBAL_Milliy      : ET₂₄ = ET_inst × Rs24·86400 / SSRD_inst — LOYIHAGA XOS quyosh
                      masshtablash (kitobdan emas)

Oylik (Σ kunlar):
  Har kun — VAQT BO'YICHA ENG YAQIN sahna (sahnaning vakillik davri; chegara —
  qo'shni sahnalar o'rtasi; Tasumi Eq 5.9 / Bastiaanssen 2002), PIKSEL bo'yicha
  eng yaqin YAROQLI sahna (bulutli piksel mavsum o'rtachasi bilan to'ldirilmaydi):
    SEBAL_B : EF, ALBEDO, LST (λ) o'sha sahnadan; Rn24 — o'sha kunning Rs24/Ra24
    SEBAL_ID: ETrF o'sha sahnadan × o'sha kunning ETr24
    Milliy  : SOLAR_FRAC o'sha sahnadan × o'sha kunning Rs24
  QC: kundan eng yaqin sahnagacha maks masofa > DAILY_ET['max_scene_gap_days'] → ogohlantirish.

Kalit printsip: Λ (evaporative fraction) kunboyi va bir necha
hafta oralig'ida nisbatan barqaror — Bastiaanssen (1998),
Shuttleworth et al. (1989).

Input:  Image(s) with EVAP_FRAC + ERA5 daily radiation
Output: ET₂₄ (mm/day) yoki ET_monthly (mm/month)
"""

import math
import ee
from . import config as cfg
from . import ref_et   # SEBAL_ID: kunlik alfalfa ETr24 (ETrF ekstrapolyatsiya)


# ==============================================================
# ETR24 — kunlik alfalfa referens ET (SEBAL_ID ETrF uchun)
# ==============================================================

GRIDMET = 'IDAHO_EPSCOR/GRIDMET'   # AQSh (CONUS) — ASCE etr/eto, 4 km


def get_daily_etr24(date, roi, dem, ref_type='alfalfa', utc_offset=0,
                    source='era5'):
    """
    Kunlik (24 soat) referens ET — SEBAL_ID: ET24 = ETrF · ETr24 (Eq 5.8).

    source='era5'    — ASCE-EWRI FAO-56 PM, ERA5-Land agregatsiyasidan (default).
    source='gridmet' — IDAHO_EPSCOR/GRIDMET tayyor `etr` (alfalfa) / `eto` (grass).
        ⚠️ FAQAT AQSh (CONUS) — boshqa hududda rasm yo'q (null) → ishlamaydi.
        Validatsiya (US-Ne1 2022, n=45): bizning ERA5 ETr24 GRIDMET'dan
        alfalfa uchun −9.3%, grass uchun −5.5% past chiqadi.

    MUHIM (era5): KALENDAR kun (yarim tundan) — overpass VAQTI emas. `utc_offset`
    bilan MAHALLIY standart kunga bog'lanadi (Manual App.5-A; DST qo'llanmaydi).
    """
    day = ee.Date(ee.Date(date).format('YYYY-MM-dd'))   # yarim tun (kalendar kun)

    if source == 'gridmet':
        band = 'etr' if ref_type == 'alfalfa' else 'eto'
        img = (ee.ImageCollection(GRIDMET)
               .filterDate(day, day.advance(1, 'day')).first())
        return ee.Image(img).select(band).rename('ETR24')

    # SOATLIK-YIG'INDI (kitob App.B) — kunlik-qadamdan aniqroq (Ne1 2022:
    # R² 0.801→0.830). Har soat kunduz/tun koeffitsientlari bilan ETr, 24 soat yig'indi.
    etr = ref_et.compute_etr24_hourly_sum(day, roi, ee.Image(dem),
                                          ref_type=ref_type, utc_offset=utc_offset)
    return etr.select('ETr').rename('ETR24')


# ==============================================================
# RS24 — 24-hour incoming solar radiation from ERA5
# ==============================================================

def get_daily_solar_radiation(date, roi, utc_offset=0):
    """
    ERA5 dan 24 soatlik quyosh radiatsiyasi olish.

    Rs24 = ERA5 ssrd ni 24 soatga yig'ib, o'rtacha W/m² ga o'girish.

    ERA5-Land hourly: har soatdagi accumulated qiymat (J/m²).
    24 soat yig'indisi / 86400 = o'rtacha W/m²

    Parameters
    ----------
    date : ee.Date
        Sana
    roi : ee.Geometry
        Hudud

    Returns
    -------
    ee.Image : Rs24 (W/m²)
    """
    # Mahalliy standart kalendar kun (App.5-A) — utc_offset=0 → eski UTC kun.
    # Avval YARIM TUNGA qirqiladi (get_daily_etr24 bilan bir xil): sahna uchun date =
    # overpass vaqti (masalan 17:20 UTC) — qirqilmasa 24 soatlik oyna overpassdan
    # boshlanardi (Bushland UTC−6: sahna Rs24 −10…+10 %; Samarqand ~0 %).
    day_start = ee.Date(ee.Date(date).format('YYYY-MM-dd')).advance(-utc_offset, 'hour')
    day_end = day_start.advance(1, 'day')

    ssrd_band = cfg.ERA5['bands']['ssrd']

    daily_ssrd = (ee.ImageCollection(cfg.ERA5['collection'])
                  .filterDate(day_start, day_end)
                  .filterBounds(roi)
                  .select(ssrd_band)
                  .sum())  # 24 soat yig'indisi (J/m²)

    # J/m² → W/m² (o'rtacha)
    rs24 = (daily_ssrd
            .divide(cfg.DAILY_ET['seconds_per_day'])
            .rename('RS24'))

    return rs24


def get_daily_ra24(date):
    """
    Kunlik atmosfera tashqarisi radiatsiyasi Ra24 (W/m², sutka o'rtachasi) — FAO-56
    Eq 21, piksel kengligi bo'yicha; Rs24 bilan AYNI kalendar kun (sana yarim tunga
    qirqiladi, get_daily_solar_radiation / get_daily_etr24 kabi).
    """
    day = ee.Date(ee.Date(date).format('YYYY-MM-dd'))
    doy = ee.Number(day.getRelative('day', 'year')).add(1)
    calc = ref_et.RefETCalculator()
    dr, dec = calc._dr_decl(doy)
    lat = ee.Image.pixelLonLat().select('latitude').multiply(math.pi / 180.0)
    ra = calc.Ra_daily(lat, doy, dr, dec)                        # MJ/m²/kun
    return ra.multiply(1e6 / cfg.DAILY_ET['seconds_per_day']).rename('RA24')


def daily_rn24(albedo, rs24, ra24, rs24_surface=None):
    """
    Kunlik sof radiatsiya (SEBAL, de Bruin 1987; Bastiaanssen 2000):
        Rn24 = (1 − α)·Rs24 − 110·τ24,   τ24 = Rs24 / Ra24
    τ24 — O'SHA KUNNING haqiqiy o'tkazuvchanligi (ERA5 Rs24 / astronomik Ra24).
    Ochiq osmon TAU_SW (0.75 + 2·10⁻⁵·z) EMAS — u ERA5 real Rs24 bilan aralashtirilsa
    bulutli kunlarda Rn24 110·(τ_ochiq − τ24) ga kam chiqardi.
    rs24_surface — qiya yuza: (1 − α) hadidagi Rs24 (τ24 gorizontal Rs24 dan).
    Qaytaradi: (Rn24 'RN24', τ24 'TAU24').
    """
    tau24 = rs24.divide(ra24.max(1e-6)).clamp(0, 1).rename('TAU24')
    rs_s = rs24 if rs24_surface is None else rs24_surface
    rn24 = (albedo.multiply(-1).add(1.0).multiply(rs_s)
            .subtract(tau24.multiply(cfg.DAILY_ET['rn24_constant']))
            .max(0).rename('RN24'))
    return rn24, tau24


def month_scene_qc(image_list, year, month):
    """
    Oylik QC (klient, BITTA getInfo): (shu oydagi sahnalar soni, oyning biror kunidan
    eng yaqin sahnagacha MAKS masofa, kun). Masofa > DAILY_ET['max_scene_gap_days']
    → OGOHLANTIRISH (o'sha kunlar uzoq sahna qiymati bilan hisoblanadi). Sahna
    darajasida — pikselning bulut maskasi hisobga olinmaydi.
    """
    import calendar
    from datetime import datetime, timezone
    ts = ee.List([ee.Image(im).get('system:time_start') for im in image_list]).getInfo()
    days = calendar.monthrange(year, month)[1]
    t_days = [t / 86400000.0 for t in ts]
    d0 = datetime(year, month, 1, tzinfo=timezone.utc).timestamp() / 86400.0
    gap = max(min(abs(d0 + k - s) for s in t_days) for k in range(days))
    n_in = sum(1 for s in t_days if d0 <= s < d0 + days)
    thr = cfg.DAILY_ET['max_scene_gap_days']
    if gap > thr:
        print(f"    ⚠️ {year}-{month:02d}: kundan eng yaqin sahnagacha maks {gap:.1f} kun "
              f"(> {thr}) — shu kunlar uzoq sahna qiymati bilan hisoblanadi")
    return n_in, round(gap, 1)


# ==============================================================
# ET₂₄ — Kunlik ET (bitta sana uchun)
# ==============================================================

def utc_offset_from_roi(roi):
    """
    ROI markazidan MAHALLIY STANDART vaqt zonasi offseti (soat, butun son).

    SEBAL Manual App.5-A: korreksiya = (vaqt zonasi MARKAZI boylami)/15.
    Zona markazlari 15° ga karrali (−90 Central, −105 Mountain, ...), shuning
    uchun sayt boylamini 15 ga bo'lib YAXLITLASH zona markazini beradi.
    DST HECH QACHON qo'llanmaydi (qishki standart vaqt).

    ⚠️ Bu TAXMIN — ba'zi davlatlarda zona quyosh vaqtidan siljigan
    (masalan O'zbekiston: lon≈65 → −taxmin +4, ASLIDA UZT = +5).
    Aniq qiymatni `utc_offset=` bilan qo'lda bering.
    """
    lon = ee.Number(ee.Geometry(roi).centroid(1).coordinates().get(0)).getInfo()
    return int(round(lon / 15.0))


def compute_daily_et(image, roi, mode='SEBAL_B', ref_type='alfalfa', utc_offset=0,
                     etr24_source='era5', sloping_terrain=False):
    """
    Kunlik ET hisoblash — bitta Landsat sahna uchun.

    SEBAL_B (EF o'z-o'zini saqlash — Bastiaanssen 1998):
      ET₂₄ = Λ × Rn24 × 86400 / λ    (Rn24 = (1-α)·Rs24 − 110·τ24, τ24 = Rs24/Ra24)

    SEBAL_ID (ETrF o'z-o'zini saqlash — Tasumi 2003, Eq 5.6–5.8):
      ETrF_inst = ET_inst / ETr_inst  (overpass)
      ET₂₄ = ETrF_inst × ETr24        (ETr24 = kunlik alfalfa referens ET)
      Advektiv muhitda (Idaho) ETr Rn−G'dan yaxshiroq umumiy bug'lanish indeksi.

    SEBAL_Milliy — loyihaga xos quyosh masshtablash (kitobdan emas):
      ET₂₄ = ET_inst × Rs24·86400 / SSRD_inst.

    λ = harorat bog'liq (Tasumi 3.48). 1 kg/m² = 1 mm.
    Returns: Image with ET_24 (+ RN24, TAU24; SEBAL_ID: ETRF_INST, ETR24) bands.
    """
    date = ee.Date(image.get('system:time_start'))
    evap_frac = image.select('EVAP_FRAC')
    albedo = image.select('ALBEDO')

    # 1. Rs24 — ERA5 dan (mahalliy standart kun); Ra24 — o'sha kun (τ24 uchun)
    rs24 = get_daily_solar_radiation(date, roi, utc_offset=utc_offset)
    rs24_h = rs24                                      # gorizontal (τ24 uchun)
    ra24 = get_daily_ra24(date)
    # QIYA YUZA: sutkalik radiatsiya qiyalik/ekspozitsiyaga qarab o'zgaradi.
    # Koeffitsientlar SAHNA BANDI sifatida saqlanadi ('RA24_RATIO', 'C_RAD') —
    # oylik hisobda ular ETrF bilan birga interpolyatsiya qilinadi.
    if sloping_terrain:
        from . import sloping_terrain as slt
        ra_ratio = slt.ra24_ratio(image)               # band 'RA24_RATIO'
        image = image.addBands(ra_ratio)
        if not cfg.is_id_mode(mode):
            rs24 = rs24.multiply(ra_ratio).rename('RS24')   # SEBAL_B: Rn24 orqali
    image = image.addBands(rs24)

    # 2. Rn24 — de Bruin: (1−α)·Rs24 − 110·τ24, τ24 = Rs24/Ra24 (o'sha kun)
    rn24, tau24 = daily_rn24(albedo, rs24_h, ra24, rs24_surface=rs24)

    image = image.addBands(rn24).addBands(tau24)

    # λ HAROTARGA BOG'LIQ (Tasumi Eq. 3.48): (2.501 − 0.00236·(Ts−273.15))·10⁶ J/kg
    lam = (image.select('LST').subtract(273.15).multiply(-0.00236)
           .add(2.501).multiply(1e6).rename('LAMBDA_HV'))
    spd = cfg.DAILY_ET['seconds_per_day']

    # Lahzali ET (mm/soat)
    et_inst = (image.select('LAMBDA_E').multiply(3600.0).divide(lam)
               .rename('ET_INST_MM_HR'))
    image = image.addBands(et_inst)

    if cfg.is_id_mode(mode):
        # ETrF_inst = ET_inst / ETr_inst (ikkalasi mm/soat)
        # ref_type — EKSTRAPOLYATSIYA referensi (alfalfa default, grass sinov uchun).
        # DIQQAT: cold anchor (ET_cp=1.05·ETr) HAR DOIM ALFALFA da qoladi
        # (kitobning fizik ta'rifi) — u energy_balance'da 'ETR_INST' dan olinadi.
        if ref_type == 'alfalfa':
            etr_inst = image.select('ETR_INST').max(0.01)   # 0 ga bo'linishdan himoya
        else:
            etr_inst = (ref_et.compute_instant_etr(
                image, ref_type=ref_type, band_name='ETR_INST_REF')
                .select('ETR_INST_REF').max(0.01))
        # ETRF_RAW — CHEKLANMAGAN ET_inst/ETr_inst (QC/diagnostika). SEBAL_ID ET_24
        # 1.05 da cheklangan ETRF_INST bilan; SEBAL_Milliy ET_24 esa xom ET_inst dan
        # (cheklanmaydi — user qarori (b)), shuning uchun ikkalasida ham QC (main._daily_qc).
        etrf_raw = et_inst.divide(etr_inst).rename('ETRF_RAW')
        etrf_inst = (etrf_raw.clamp(0, 1.05)   # ET_cold=1.05·ETr → fizik chegara 1.05
                     .rename('ETRF_INST'))
        # ETr24 — kunlik referens ET (ref_type bo'yicha)
        etr24 = get_daily_etr24(date, roi, image.select('DEM'),
                                ref_type=ref_type, utc_offset=utc_offset,
                                source=etr24_source)
        # QIYA YUZA (Eq 5.17-5.19): ETrF24 = C_rad · ETrF_inst
        etrf24 = etrf_inst
        image = image.addBands(etrf_inst).addBands(etrf_raw).addBands(etr24)
        if sloping_terrain:
            from . import sloping_terrain as slt
            c_rad = slt.c_radiation(image)             # band 'C_RAD'
            image = image.addBands(c_rad)
            etrf24 = etrf_inst.multiply(c_rad).rename('ETRF24')

        if mode == 'SEBAL_Milliy':
            # SOLAR upscaling: ET₂₄ = ET_inst · (Rs24_jami / Rs_inst) = ET_inst·eff.soat.
            # Referens-ETrF (self-preservation) o'rniga SOLAR shakl — diurnal
            # over-baholashni fizik yechadi. Bushland lizimetr: daily MBE +0.88→
            # +0.17, R²↑; solar shakl ekin ET diurnaliga mos (~9.25 eff.soat vs
            # referens ~10.9). Rs24=get_daily_solar_radiation (ERA5 SSRD kunlik
            # o'rt W/m²), Rs_inst=SSRD (ERA5 overpass soati, J/m²) — izchil ERA5.
            rs24 = get_daily_solar_radiation(date, roi, utc_offset)       # W/m² o'rt
            ssrd = image.select('SSRD').max(1e4)                          # J/m² (overpass soati)
            solar_frac = et_inst.divide(ssrd).rename('SOLAR_FRAC')        # monthly interp uchun
            eff_hr = rs24.multiply(cfg.DAILY_ET['seconds_per_day']).divide(ssrd)  # eff.soat
            et_24 = et_inst.multiply(eff_hr)
            if sloping_terrain:
                # QIYA YUZA (Tasumi Eq 5.17): ET_inst qiyalikning OVERPASS soatidagi
                # radiatsiyasini olgan; eff_hr = Rs24/SSRD esa TEKIS yuza nisbati →
                # C_rad = (Rso_inst_flat/Rso_inst_px)·(Rso24_px/Rso24_flat) uni piksel
                # geometriyasiga o'tkazadi (SEBAL_ID: ETrF24 = C_rad·ETrF_inst bilan bir xil).
                et_24 = et_24.multiply(c_rad)
            et_24 = et_24.max(0).rename('ET_24')
            image = image.addBands(solar_frac).addBands(et_24)
        else:
            # SEBAL_ID: ET₂₄ = ETrF24 · ETr24  (Tasumi Eq 5.8 / 5.19)
            et_24 = etrf24.multiply(etr24).max(0).rename('ET_24')
            image = image.addBands(et_24)
    else:
        # SEBAL_B: ET₂₄ = EF × Rn24 × 86400 / λ
        et_24 = (evap_frac.multiply(rn24).multiply(spd).divide(lam)
                 .max(0).rename('ET_24'))
        image = image.addBands(et_24)

    return image


# ==============================================================
# SEBAL_Milliy — KUNLIK ET SERIYASI (CUirr suv balansi uchun)
# ==============================================================

def daily_et_series(image_list, roi, year, month, mode='SEBAL_Milliy',
                    ref_type='alfalfa', utc_offset=0, etr24_source='era5',
                    sloping_terrain=False):
    """
    Oyning har kuni uchun kunlik ET (mm/kun) — ee.List(ee.Image). BARCHA rejim.

    compute_monthly_et'ning kunlik qadami (compute_day_et) bilan AYNAN bir xil
    mantiq: SEBAL_Milliy → SOLAR_FRAC×Rs24; SEBAL_ID → ETRF_INST×ETr24;
    SEBAL_B/pysebal → EF×Rn24/λ. consumptive_use shu seriyani ildiz-zona suv
    balansini haydash uchun ishlatadi (ET va Prz bir xil kunlik ET'dan).

    Returns: (ee.List of ee.Image, days_in_month:int, month_start:ee.Date)
    """
    import calendar
    days = calendar.monthrange(year, month)[1]
    month_start = ee.Date.fromYMD(year, month, 1)

    if mode == 'SEBAL_Milliy':
        bands = ['SOLAR_FRAC'] + (['C_RAD'] if sloping_terrain else [])
    elif cfg.is_id_mode(mode):
        bands = ['ETRF_INST'] + (['C_RAD'] if sloping_terrain else [])
    else:
        bands = ['EVAP_FRAC', 'ALBEDO', 'LST'] + \
                (['RA24_RATIO'] if sloping_terrain else [])
    coll = ee.ImageCollection(image_list).select(bands)
    dem_img = (ee.Image(image_list[0]).select('DEM')
               if cfg.is_id_mode(mode) else None)

    def _day(off):
        off = ee.Number(off)
        d = month_start.advance(off, 'day')
        if mode == 'SEBAL_Milliy':
            interp = _nearest_valid(coll, d)
            rs24 = get_daily_solar_radiation(d, roi, utc_offset=utc_offset)
            sf = interp.select('SOLAR_FRAC')
            if sloping_terrain:                       # qiya yuza: × C_rad (Eq 5.17)
                sf = sf.multiply(interp.select('C_RAD'))
            return (sf.multiply(rs24)
                    .multiply(cfg.DAILY_ET['seconds_per_day']).max(0).rename('ET_DAY'))
        elif cfg.is_id_mode(mode):
            interp = _nearest_valid(coll, d)
            etrf = interp.select('ETRF_INST')
            if sloping_terrain:
                etrf = etrf.multiply(interp.select('C_RAD'))
            etr24 = get_daily_etr24(d, roi, dem_img, ref_type=ref_type,
                                    utc_offset=utc_offset, source=etr24_source)
            return etrf.multiply(etr24).max(0).rename('ET_DAY')
        else:
            interp = _nearest_valid(coll, d)
            rs24 = get_daily_solar_radiation(d, roi, utc_offset=utc_offset)
            rs24_s = (rs24.multiply(interp.select('RA24_RATIO'))
                      if sloping_terrain else rs24)
            rn24, _ = daily_rn24(interp.select('ALBEDO'), rs24, get_daily_ra24(d),
                                 rs24_surface=rs24_s)
            lam = (interp.select('LST').subtract(273.15).multiply(-0.00236)
                   .add(2.501).multiply(1e6))
            return (interp.select('EVAP_FRAC').multiply(rn24)
                    .multiply(cfg.DAILY_ET['seconds_per_day']).divide(lam)
                    .max(0).rename('ET_DAY'))

    return ee.List.sequence(0, days - 1).map(_day), days, month_start


# ==============================================================
# MONTHLY EXTRAPOLATION
# ==============================================================

def compute_monthly_et(image_list, roi, year, month, mode='SEBAL_B',
                       etrf_water_balance=False, ref_type='alfalfa',
                       utc_offset=0, etr24_source='era5', sloping_terrain=False):
    """
    Oylik ET (mm/oy) = Σ kunlik ET. Har kun — VAQT BO'YICHA ENG YAQIN sahna
    (vakillik davri; piksel bo'yicha eng yaqin YAROQLI sahna — _nearest_valid):
      SEBAL_B / pysebal: EF, ALBEDO, LST (λ) o'sha sahnadan;
                         Rn24 = (1−α)·Rs24 − 110·τ24, τ24 = Rs24/Ra24 (o'sha kun, ERA5);
                         ET_kun = EF × Rn24 × 86400 / λ
      SEBAL_ID : ET_kun = ETrF × ETr24 (Tasumi Eq 5.9)
      SEBAL_Milliy : ET_kun = SOLAR_FRAC × Rs24 × 86400 (loyihaga xos)
    Metadata: n_landsat_scenes (SHU oydagi sahnalar), max_gap_days (QC).

    Parameters
    ----------
    image_list : list of ee.Image
        SEBAL natijasi bo'lgan tasvirlar (SEBAL_B: EVAP_FRAC, ALBEDO, LST;
        SEBAL_ID: ETRF_INST; SEBAL_Milliy: SOLAR_FRAC)
    roi : ee.Geometry
    year : int
    month : int

    Returns
    -------
    ee.Image : ET_monthly (mm/month)
    """
    import calendar

    # SEBAL_Milliy_Kc: NDVI-langan FAO-56 qo'sh koeffitsient (Kcb+Ke) upscaling
    # (energiya-balans SOLAR_FRAC EMAS — anchor'ga bog'liq bo'lmagan alohida rejim)
    if cfg.is_kc_mode(mode):
        from . import ndvi_kc
        return ndvi_kc.compute_monthly_et_kc(
            image_list, roi, year, month, utc_offset=utc_offset,
            etr24_source=etr24_source)

    # SEBAL_ID + Appendix I: kunlik ETrF tuzatish (per-piksel suv balansi)
    if cfg.is_id_mode(mode) and etrf_water_balance:
        from . import etrf_water_balance as ewb
        dem_img = ee.Image(image_list[0]).select('DEM')
        return ewb.monthly_et_adjusted(image_list, roi, year, month, dem_img,
                                       ref_type=ref_type, utc_offset=utc_offset,
                                       etr24_source=etr24_source)

    days_in_month = calendar.monthrange(year, month)[1]
    month_start = ee.Date.fromYMD(year, month, 1)
    n_in_month, max_gap = month_scene_qc(image_list, year, month)   # QC (klient)

    # ---- 1. Landsat sanalar va Λ qiymatlarini olish ----
    # Har bir image dan: sana, Λ, albedo, τsw
    # Bu server-side ishlashi uchun ImageCollection ga o'giramiz

    # SEBAL_ID: ETrF interpolyatsiya (Eq 5.9); SEBAL_B: EF interpolyatsiya
    # QIYA YUZA: koeffitsientlar sahna bandi sifatida ETrF/EF bilan birga
    # interpolyatsiya qilinadi (ular sahnaning o'z vaqti/geometriyasiga tegishli)
    if cfg.is_id_mode(mode):
        # SEBAL_Milliy: SOLAR_FRAC interpolyatsiya (solar upscaling); SEBAL_ID: ETRF_INST
        if mode == 'SEBAL_Milliy':
            bands = ['SOLAR_FRAC'] + (['C_RAD'] if sloping_terrain else [])
        else:
            bands = ['ETRF_INST'] + (['C_RAD'] if sloping_terrain else [])
        interp_collection = ee.ImageCollection(image_list).select(bands)
        dem_img = ee.Image(image_list[0]).select('DEM')
    else:
        # TAU_SW EMAS (u vaqtga bog'liq emas; kunlik τ24 = Rs24/Ra24 har kun hisoblanadi)
        bands = ['EVAP_FRAC', 'ALBEDO', 'LST'] + \
                (['RA24_RATIO'] if sloping_terrain else [])
        interp_collection = ee.ImageCollection(image_list).select(bands)
        dem_img = None
    lambda_collection = interp_collection

    # ---- 2. Har kun uchun interpolyatsiya va ET hisoblash ----
    def compute_day_et(day_offset):
        """Bitta kun uchun ET hisoblash."""
        day_offset = ee.Number(day_offset)
        current_date = month_start.advance(day_offset, 'day')

        if mode == 'SEBAL_Milliy':
            # SOLAR upscaling monthly: SOLAR_FRAC (=ET_inst/SSRD) ENG YAQIN sahnadan,
            # × o'sha kunning Rs24 jami (get_daily_solar_radiation × 86400).
            interp = _nearest_valid(lambda_collection, current_date)
            solar_frac = interp.select('SOLAR_FRAC')
            if sloping_terrain:                       # qiya yuza: × C_rad (Eq 5.17)
                solar_frac = solar_frac.multiply(interp.select('C_RAD'))
            rs24 = get_daily_solar_radiation(current_date, roi, utc_offset=utc_offset)
            et_day = (solar_frac.multiply(rs24)
                      .multiply(cfg.DAILY_ET['seconds_per_day']).max(0))
        elif cfg.is_id_mode(mode):
            # Eq 5.9: har tasvir ±8 kunni ifodalaydi → ENG YAQIN sahna hukmron
            interp = _nearest_valid(lambda_collection, current_date)
            etrf_interp = interp.select('ETRF_INST')
            # QIYA YUZA (Eq 5.18): ETrF24 = C_rad · ETrF_inst
            if sloping_terrain:
                etrf_interp = etrf_interp.multiply(interp.select('C_RAD'))
            etr24 = get_daily_etr24(current_date, roi, dem_img,
                                    ref_type=ref_type, utc_offset=utc_offset,
                                    source=etr24_source)
            et_day = etrf_interp.multiply(etr24).max(0)
        else:
            # SEBAL_B / pysebal: sahnaning vakillik davri (eng yaqin sahna) — EF,
            # ALBEDO, LST AYNI sahnadan (oldin (oldingi+keyingi)/2 midpoint edi).
            interp = _nearest_valid(lambda_collection, current_date)
            # SEBAL_B: ET_kun = EF × Rn24 × 86400 / λ
            rs24 = get_daily_solar_radiation(current_date, roi, utc_offset=utc_offset)
            rs24_s = (rs24.multiply(interp.select('RA24_RATIO'))
                      if sloping_terrain else rs24)
            rn24, _ = daily_rn24(interp.select('ALBEDO'), rs24,
                                 get_daily_ra24(current_date), rs24_surface=rs24_s)
            evap_frac = interp.select('EVAP_FRAC')
            lam = (interp.select('LST').subtract(273.15).multiply(-0.00236)
                   .add(2.501).multiply(1e6))
            spd = cfg.DAILY_ET['seconds_per_day']
            et_day = (evap_frac.multiply(rn24).multiply(spd).divide(lam).max(0))

        return et_day

    # Oyning har kuni uchun ET hisoblash
    day_offsets = ee.List.sequence(0, days_in_month - 1)
    daily_et_images = day_offsets.map(compute_day_et)

    # Oylik yig'indi
    et_monthly = (ee.ImageCollection(daily_et_images)
                  .sum()
                  .rename('ET_MONTHLY'))

    # Metadata qo'shish
    et_monthly = (et_monthly
                  .set('year', year)
                  .set('month', month)
                  .set('days_in_month', days_in_month)
                  .set('n_landsat_scenes', n_in_month)     # SHU oydagi sahnalar
                  .set('max_gap_days', max_gap))           # QC: eng yaqin sahnagacha maks kun

    return et_monthly


def _nearest_valid(collection, target_date):
    """
    Sahnaning VAKILLIK DAVRI — har PIKSEL uchun vaqt bo'yicha ENG YAQIN YAROQLI sahna
    (Tasumi 2003 Eq 5.9: har sahna ±8 kunni ifodalaydi; chegara — qo'shni sahnalar
    o'rtasi, shuning uchun L8+L9 zichligiga avtomatik moslashadi).
    Sifat bandi = −|t_sahna − t_kun| (sahna bandlarining UMUMIY maskasi bilan) →
    qualityMosaic: har piksel eng yaqin YAROQLI sahnaning BARCHA bandlarini oladi
    (EF, ALBEDO, LST … — bitta sahnadan). Hech bir sahnada yaroqli bo'lmasa — piksel bo'sh.
    Oldin: eng yaqin sahna, bulutli piksel → BUTUN DAVR O'RTACHASI (collection.mean());
    SEBAL_B'da esa (oldingi + keyingi)/2 midpoint.
    """
    t = ee.Number(ee.Date(target_date).millis())
    bands = ee.Image(collection.first()).bandNames()

    def _q(img):
        dt = ee.Number(img.get('system:time_start')).subtract(t).abs()
        valid = img.mask().reduce(ee.Reducer.min())
        q = ee.Image.constant(dt.multiply(-1)).toDouble().rename('QNEAR').updateMask(valid)
        return img.addBands(q)

    proj = ee.Image(collection.first()).select(0).projection()
    return (collection.map(_q).qualityMosaic('QNEAR').select(bands)
            .setDefaultProjection(proj))


# ==============================================================
# SEASONAL SUMMARY
# ==============================================================

def compute_seasonal_stats(monthly_images):
    """
    Mavsumiy statistika — oylik ET lardan.

    Parameters
    ----------
    monthly_images : list of ee.Image
        Har biri ET_MONTHLY (mm/month)

    Returns
    -------
    dict with:
      - total: ee.Image — mavsumiy jami (mm)
      - mean_daily: ee.Image — o'rtacha kunlik (mm/day)
    """
    collection = ee.ImageCollection(monthly_images)

    total = collection.sum().rename('ET_SEASONAL_TOTAL')

    # Umumiy kunlar soni
    total_days = ee.Number(0)
    for img in monthly_images:
        total_days = total_days.add(ee.Number(img.get('days_in_month')))

    mean_daily = total.divide(total_days).rename('ET_SEASONAL_MEAN_DAILY')

    return {
        'total': total,
        'mean_daily': mean_daily,
    }
