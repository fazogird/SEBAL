"""
SEBAL-GEE v4 — Reference ET (ASCE-EWRI Standardized Penman-Monteith)
========================================================================
Haqiqiy, to'liq ASCE-EWRI standart referens ET.

Bu modul faqat ETREF_24 (kunlik referens ET, grass) uchun ishlatiladi —
SEBAL'ning o'z ET_24/ETrF/EVAP_FRAC natijasiga TA'SIR QILMAYDI (ular sof
energiya balansidan hisoblanadi, main.py: "SEBAL o'zgarmaydi").

ETREF_24 quyi-tizimlar uchun kerak:
  - hls_s30_etrf.py: ETrF = ET24 / ETREF_24 (S30 regressiya target)
  - viirs_downscaling.py: KC = ET_24/ETREF_24, ET_24 = KC × ETREF_24
  - monthly_analytics.py: kunlar orasida interpolyatsiya

Source: ASCE-EWRI (2005) Standardized Reference Evapotranspiration
Equation; Allen et al. (1998) FAO-56.
"""

import ee
import math
from . import config as cfg


# ==============================================================
# ASCE-EWRI REFERENS ET KALKULYATORI
# ==============================================================

class RefETCalculator:
    """
    ASCE Standardized Penman-Monteith ETr/ETo hisoblash.

    Foydalanish:
        calc = RefETCalculator(ref_type='grass')
        result = calc.calculate(daily_met_img, dem, mode='daily')
        etref = result.select('ETr')   # mm/day

    Chiqish bandlari: es, Delta, Gamma, Ra, Rso, Rnl, Rn_ref, G_ref, ETr
    """

    Gsc = 0.0820        # Quyosh konstantasi [MJ m-2 min-1]
    albedo = 0.23        # Referens (grass/alfalfa) albedosi — FIKSATIV,
                          # haqiqiy kuzatilgan yer yuzasi albedosidan MUSTAQIL
    sigma_sb = 4.903e-9   # Stefan-Boltzmann [MJ K-4 m-2 day-1]

    def __init__(self, timezone_lon_deg=0.0, ref_type='grass'):
        self.Lz = ee.Number(timezone_lon_deg)
        self.ref_type = ref_type

        if ref_type == 'alfalfa':
            self.Cn_hr_day, self.Cn_hr_night = 66.0, 66.0
            self.Cd_hr_day, self.Cd_hr_night = 0.25, 1.7
            self.Cn_day, self.Cd_day = 1600.0, 0.38
        elif ref_type == 'grass':
            self.Cn_hr_day, self.Cn_hr_night = 37.0, 37.0
            self.Cd_hr_day, self.Cd_hr_night = 0.24, 0.96
            self.Cn_day, self.Cd_day = 900.0, 0.34
        else:
            raise ValueError(f"ref_type '{ref_type}' noto'g'ri")

    # ---- Yordamchi fizik funksiyalar ----

    @staticmethod
    def _esat(T_c):
        """To'yingan bug' bosimi [kPa]. FAO-56 Eq 11."""
        return T_c.expression(
            '0.6108 * exp((17.27 * T) / (T + 237.3))', {'T': T_c})

    @staticmethod
    def _delta_svp(T_c, es_kPa):
        """Bug' bosimi egri chizig'i nishabi [kPa/C]. FAO-56 Eq 13."""
        return es_kPa.multiply(4098).divide(T_c.add(237.3).pow(2))

    @staticmethod
    def _gamma(P_kPa):
        """Psixrometrik konstanta [kPa/C]. FAO-56 Eq 8."""
        return P_kPa.multiply(0.000665)

    # ---- Astronomiya (kunlik rejim uchun) ----

    @staticmethod
    def _doy(img):
        date = ee.Date(img.get('system:time_start'))
        return ee.Number(date.getRelative('day', 'year')).add(1)

    @staticmethod
    def _dr_decl(doy):
        pi = math.pi
        J = ee.Number(doy)
        dr = J.multiply(2 * pi / 365.0).cos().multiply(0.033).add(1.0)
        dec = J.multiply(2 * pi / 365.0).subtract(1.39).sin().multiply(0.409)
        return dr, dec

    def Ra_daily(self, lat_rad, doy, dr, dec):
        """Extraterrestrial Radiation Daily [MJ/m2/day]. FAO-56 Eq 21."""
        pi = math.pi
        ws = lat_rad.tan().multiply(-1).multiply(dec.tan()).acos()
        term1 = ws.multiply(lat_rad.sin()).multiply(dec.sin())
        term2 = lat_rad.cos().multiply(dec.cos()).multiply(ws.sin())
        return (term1.add(term2).multiply(dr)
                .multiply(24 * 60 / pi * self.Gsc))

    @staticmethod
    def Rso(Ra, z_m):
        """Clear Sky Radiation. FAO-56 Eq 37."""
        return z_m.multiply(2e-5).add(0.75).multiply(Ra)

    @staticmethod
    def Rnl_daily(Tmax_k, Tmin_k, ea_kPa, Rs, Rso):
        """Net Longwave Radiation Daily [MJ/m2/day]. FAO-56 Eq 39."""
        rs_rso = Rs.divide(Rso.max(1e-6)).clamp(0.3, 1.0)
        fcd = rs_rso.multiply(1.35).subtract(0.35)
        emiss = ea_kPa.sqrt().multiply(-0.14).add(0.34)
        tmean4 = Tmax_k.pow(4).add(Tmin_k.pow(4)).divide(2.0)
        sb = ee.Image.constant(4.901e-9)
        return sb.multiply(tmean4).multiply(emiss).multiply(fcd)

    def soil_heat_flux(self, Rn, mode):
        """Daily rejimda G = 0 (grass va alfalfa uchun ham, ASCE-EWRI)."""
        if mode == 'daily':
            return ee.Image.constant(0)
        if self.ref_type == 'grass':
            g_day, g_night = Rn.multiply(0.1), Rn.multiply(0.5)
        else:
            g_day, g_night = Rn.multiply(0.04), Rn.multiply(0.20)
        return g_day.where(Rn.lt(0), g_night)

    # ---- Soatlik astronomiya + radiatsiya (SEBAL_ID instant ETr uchun) ----
    #   Manba: D:\Cloud_comp\Idaho_project\script2\reference_et\penman_monteith.py
    #   (FAO-56 Eq. 28/31/32/39 soatlik). K_DOWN o'rniga haqiqiy PM Rs ishlatiladi.

    @staticmethod
    def _seasonal_correction(doy):
        """Mavsumiy vaqt tuzatmasi Sc [soat]. FAO-56 Eq 32."""
        pi = math.pi
        b = ee.Number(doy).subtract(81).multiply(2 * pi / 364.0)
        return (b.multiply(2).sin().multiply(0.1645)
                .subtract(b.cos().multiply(0.1255))
                .subtract(b.sin().multiply(0.025)))

    def _omega_mid_hour(self, lon_deg, doy, hour):
        """Quyosh soat burchagi omega [rad], soat o'rtasi. FAO-56 Eq 31.
        UTC + haqiqiy boylam (lon/15) orqali local solar vaqt."""
        pi = math.pi
        Sc = self._seasonal_correction(doy)
        t_mid = ee.Number(hour).add(0.5)
        sol_time = (ee.Image(lon_deg).multiply(1.0 / 15.0)
                    .add(t_mid).add(Sc).subtract(12))
        return sol_time.multiply(pi / 12.0)

    def Ra_hourly(self, lat_rad, lon_deg, doy, hour, dr, dec):
        """Extraterrestrial Radiation [MJ/m2/soat]. FAO-56 Eq 28."""
        pi = math.pi
        omega = self._omega_mid_hour(lon_deg, doy, hour)
        omega1 = omega.subtract(pi / 24.0)
        omega2 = omega.add(pi / 24.0)
        ws = lat_rad.tan().multiply(-1).multiply(dec.tan()).acos()
        omega1c = omega1.max(ws.multiply(-1)).min(ws)   # quyosh bor vaqt
        omega2c = omega2.max(ws.multiply(-1)).min(ws)
        term1 = (omega2c.subtract(omega1c)
                 .multiply(lat_rad.sin()).multiply(dec.sin()))
        term2 = (lat_rad.cos().multiply(dec.cos())
                 .multiply(omega2c.sin().subtract(omega1c.sin())))
        Ra = term1.add(term2).multiply(dr).multiply(12 * 60 / pi * self.Gsc)
        return Ra.max(0)   # tun → 0

    @staticmethod
    def Rnl_hourly(T_k, ea_kPa, Rs, Rso):
        """Net Longwave Radiation [MJ/m2/soat]. FAO-56 Eq 39 (soatlik).
        Kechada (Rs≈0) fcd=1.0, kunduzi haqiqiy bulutlilik nisbatidan."""
        Rso_safe = Rso.max(1e-6)
        rs_rso = Rs.divide(Rso_safe).clamp(0.3, 1.0)
        fcd_day = rs_rso.multiply(1.35).subtract(0.35)
        fcd_night = ee.Image.constant(1.0)
        is_day = Rs.gt(0.01)
        fcd = fcd_day.where(is_day.Not(), fcd_night)
        emiss = ea_kPa.sqrt().multiply(-0.14).add(0.34)
        sb = T_k.pow(4).multiply(2.042e-10)   # Stefan-Boltzmann soatlik (=4.901e-9/24)
        return sb.multiply(emiss).multiply(fcd)

    # ---- Asosiy hisoblash ----

    def calculate(self, img, dem, mode='daily'):
        """
        Kunlik ASCE-EWRI Penman-Monteith ETr/ETo.

        Kirish (img): T_air, T_max, T_min (°C), u2 (m/s), P_kPa, ea (kPa),
                       Rs (MJ/m²/day), system:time_start (kun sanasi).
        dem: balandlik (m) — Rso uchun.
        """
        img = ee.Image(img)
        dem = ee.Image(dem)

        ll = ee.Image.pixelLonLat()
        lat_rad = ll.select('latitude').multiply(math.pi / 180.0)

        doy = self._doy(img)
        dr, dec = self._dr_decl(doy)

        Ra = self.Ra_daily(lat_rad, doy, dr, dec)
        Rso_img = self.Rso(Ra, dem)

        T = img.select('T_air')
        u2 = img.select('u2')
        P = img.select('P_kPa')
        ea = img.select('ea')
        Rs = img.select('Rs')

        T_max_c = img.select('T_max')
        T_min_c = img.select('T_min')
        es = self._esat(T_max_c).add(self._esat(T_min_c)).divide(2).rename('es')
        Delta = self._delta_svp(T, self._esat(T)).rename('Delta')
        Gamma = self._gamma(P).rename('Gamma')

        # Rn — FIKSATIV referens albedo (0.23) bilan, kuzatilgan
        # yer yuzasi albedosidan MUSTAQIL (bu — SEBAL'ning o'z RN24'idan
        # asosiy farq: referens ET meteorologik bo'lishi shart)
        Rns = Rs.multiply(1.0 - self.albedo)
        Tmax_k = T_max_c.add(273.16)
        Tmin_k = T_min_c.add(273.16)
        Rnl = self.Rnl_daily(Tmax_k, Tmin_k, ea, Rs, Rso_img)
        Rn = Rns.subtract(Rnl).rename('Rn_ref')

        G = self.soil_heat_flux(Rn, mode).rename('G_ref')

        Cn, Cd = self.Cn_day, self.Cd_day
        num1 = Delta.multiply(Rn.subtract(G)).multiply(0.408)
        num2 = (Gamma.multiply(u2)
                .multiply(es.subtract(ea).max(0))
                .multiply(ee.Image.constant(Cn).divide(T.add(273.15))))
        den = Delta.add(Gamma.multiply(u2.multiply(Cd).add(1.0)))
        ETr = num1.add(num2).divide(den).max(0).rename('ETr')

        return img.addBands([es, Delta, Gamma, Ra.rename('Ra'),
                              Rso_img.rename('Rso'), Rnl.rename('Rnl'),
                              Rn, G, ETr])


# ==============================================================
# KUNLIK ERA5 AGREGATSIYA — ETref uchun (tez, bitta so'rov)
# ==============================================================

def get_daily_era5_aggregate(date, roi, utc_offset=0):
    """
    Butun kalendar kun uchun ERA5-Land'dan T_max/T_min/T_mean,
    kunlik o'rtacha u2/P/ea, kunlik yig'indi Rs.

    utc_offset — MAHALLIY STANDART vaqt zonasi (soat; DST QO'LLANMAYDI).
      SEBAL Manual Appendix 5 (A): kunlik oyna mahalliy standart kalendar kun
      bo'lishi kerak (UTC kun EMAS). Mahalliy 00:00 = UTC (00:00 − utc_offset).
      Masalan Nebraska (Central, −6): oyna 06:00 UTC dan boshlanadi.
      utc_offset=0 → eski UTC-kun xatti-harakati.

    Bitta ImageCollection filtrlash + bir nechta reducer — tez ishlaydi
    (overpass-vaqtidagi ±1soatlik oynadan farqli, bu yerda 24 soatlik
    to'liq kun kerak, lekin barcha operatsiyalar server-side, bitta
    so'rov ichida).
    """
    # Mahalliy standart kalendar kun → UTC oynasi
    day_start = ee.Date(date).advance(-utc_offset, 'hour')
    day_end = day_start.advance(1, 'day')

    hourly = (ee.ImageCollection(cfg.ERA5['collection'])
              .filterDate(day_start, day_end)
              .filterBounds(roi))

    # --- Harorat: kunlik mean/max/min ---
    t_k = hourly.select(cfg.ERA5['bands']['air_temp'])
    t_mean_c = t_k.mean().subtract(273.15).rename('T_air')
    t_max_c = t_k.max().subtract(273.15).rename('T_max')
    t_min_c = t_k.min().subtract(273.15).rename('T_min')

    # --- Shamol: har soat u,v dan tezlik, keyin kunlik o'rtacha, 2m'ga ---
    def add_wind_speed(img):
        u = img.select(cfg.ERA5['bands']['u_wind'])
        v = img.select(cfg.ERA5['bands']['v_wind'])
        return img.addBands(u.pow(2).add(v.pow(2)).sqrt().rename('WS10'))

    u10_mean = hourly.map(add_wind_speed).select('WS10').mean()
    wind_2m_factor = 4.87 / math.log(67.8 * 10 - 5.42)   # FAO-56, ≈0.748
    u2_mean = u10_mean.multiply(wind_2m_factor).rename('u2')

    # --- Bosim: kunlik o'rtacha, Pa → kPa ---
    p_mean = (hourly.select(cfg.ERA5['bands']['pressure']).mean()
              .divide(1000.0).rename('P_kPa'))

    # --- Haqiqiy bug' bosimi: har soat dewpoint'dan, keyin o'rtacha ---
    def add_ea(img):
        td_c = img.select(cfg.ERA5['bands']['dewpoint']).subtract(273.15)
        ea_hr = (td_c.multiply(17.27).divide(td_c.add(237.3))
                 .exp().multiply(0.6108).rename('EA_HR'))
        return img.addBands(ea_hr)

    ea_mean = hourly.map(add_ea).select('EA_HR').mean().rename('ea')

    # --- Rs: kunlik yig'indi, J/m² → MJ/m²/day ---
    ssrd_sum_j = hourly.select(cfg.ERA5['bands']['ssrd']).sum()
    rs_daily_mj = ssrd_sum_j.divide(1e6).rename('Rs')

    daily_img = (t_mean_c.addBands(t_max_c).addBands(t_min_c)
                 .addBands(u2_mean).addBands(p_mean)
                 .addBands(ea_mean).addBands(rs_daily_mj))

    # DOY hisoblash uchun kun-o'rtasi vaqti yetarli
    return daily_img.set('system:time_start', day_start.advance(12, 'hour').millis())


# ==============================================================
# ETREF_24 — Landsat sahnaga qo'shish
# ==============================================================

def compute_etref_daily(image, roi, utc_offset=0):
    """
    Landsat sahna sanasiga mos kunlik ETREF_24 (grass, mm/day) hisoblab,
    image'ga qo'shadi.

    ERA5 DAILY agregatsiyadan (Tmax/Tmin, kunlik o'rtacha met.
    parametrlar) — overpass-vaqtidagi hourly oyna EMAS, tezlik va
    aniqlik uchun.
    """
    day_str = ee.Date(image.get('system:time_start')).format('YYYY-MM-dd')
    day_start = ee.Date(day_str)

    daily_met = get_daily_era5_aggregate(day_start, roi, utc_offset=utc_offset)
    dem = image.select('DEM')

    calc = RefETCalculator(ref_type='grass')
    result = calc.calculate(daily_met, dem, mode='daily')

    etref = result.select('ETr').rename('ETREF_24')
    return image.addBands(etref)


# ==============================================================
# INSTANT (OVERPASS) ALFALFA ETr — SEBAL_ID anchor kalibratsiyasi uchun
# ==============================================================

def compute_instant_etr(image, ref_type='alfalfa', band_name='ETR_INST'):
    """
    Overpass momentidagi ASCE-EWRI SOATLIK referens ET [mm/soat] — FAO-56
    Penman-Monteith (Tasumi 2003, Appendix B). SEBAL_ID cold piksel
    (ET_cp = 1.05·ETr) va hot piksel suv balansi uchun.

    Kirish (image, overpass-soatga mos ERA5 bandlari + DEM):
      AIR_TEMP (K), PRESSURE (Pa), WIND_SPEED_10M (m/s), DEWPOINT (K),
      SSRD (surface_solar_radiation_downwards_hourly, J/m²), DEM (m).
    Rs = SSRD/1e6 (MJ/m²/soat). Chiqish: 'ETR_INST' band (mm/soat).

    MUHIM: Rs uchun K_DOWN (SEBAL instant qisqa to'lqin) EMAS, aynan
    haqiqiy quyosh radiatsiyasi (SSRD) ishlatiladi — ETr standart PM
    tenglamasidan (o'z Rn=Rns−Rnl bilan) kelishi shart.
    """
    img = ee.Image(image)
    calc = RefETCalculator(ref_type=ref_type)
    dem = img.select('DEM')

    ll = ee.Image.pixelLonLat()
    lat_rad = ll.select('latitude').multiply(math.pi / 180.0)
    lon_deg = ll.select('longitude')

    date = ee.Date(img.get('system:time_start'))
    doy = ee.Number(date.getRelative('day', 'year')).add(1)
    hour = ee.Number(date.get('hour'))     # UTC soat (omega lon/15 bilan localga o'tadi)
    dr, dec = calc._dr_decl(doy)

    # --- Meteo kirishlar (bizning ERA5 bandlaridan) ---
    T = img.select('AIR_TEMP').subtract(273.15)              # °C
    P = img.select('PRESSURE').divide(1000.0)                # kPa
    wind_2m = 4.87 / math.log(67.8 * 10 - 5.42)             # 10m→2m, ≈0.748
    u2 = img.select('WIND_SPEED_10M').multiply(wind_2m)      # m/s
    Td = img.select('DEWPOINT').subtract(273.15)
    ea = calc._esat(Td)                                      # kPa
    es = calc._esat(T)                                       # kPa
    Rs = img.select('SSRD').divide(1e6)                      # MJ/m²/soat

    Delta = calc._delta_svp(T, es)
    Gamma = calc._gamma(P)

    # --- Radiatsiya (soatlik) ---
    Ra = calc.Ra_hourly(lat_rad, lon_deg, doy, hour, dr, dec)
    Rso = calc.Rso(Ra, dem)
    Rns = Rs.multiply(1.0 - calc.albedo)
    Rnl = calc.Rnl_hourly(T.add(273.16), ea, Rs, Rso)
    Rn = Rns.subtract(Rnl)
    G = calc.soil_heat_flux(Rn, 'hourly')

    # --- ASCE PM (alfalfa, kunduz koeffitsientlari — overpass doim kunduzi) ---
    Cn, Cd = calc.Cn_hr_day, calc.Cd_hr_day
    num1 = Delta.multiply(Rn.subtract(G)).multiply(0.408)
    num2 = (Gamma.multiply(u2).multiply(es.subtract(ea).max(0))
            .multiply(ee.Image.constant(Cn).divide(T.add(273.15))))
    den = Delta.add(Gamma.multiply(u2.multiply(Cd).add(1.0)))
    etr = num1.add(num2).divide(den).max(0).rename(band_name)   # mm/soat

    return img.addBands(etr, overwrite=True)


# ==============================================================
# ETREF_24 (grass) + ETPOT_24 (alfalfa) — BITTA ERA5 so'rovdan
# ==============================================================

def compute_reference_ets_daily(image, roi):
    """
    Kunlik referens ET'larni hisoblab, image'ga qo'shadi:
      ETREF_24 — grass (FAO-56 ETo) — meteorologik referens
      ETPOT_24 — alfalfa (ASCE-EWRI ETr) — "potensial" yuqori chegara,
                 baland/g'adir-budur ekinlarga (paxta, bug'doy to'liq
                 qoplamda) yaqinroq proksi (METRIC/Allen an'anasi)

    Ikkalasi HAM bitta kunlik ERA5 agregatsiyadan (get_daily_era5_
    aggregate) hisoblanadi — ikki marta ERA5 so'rov yuborilmaydi,
    faqat Cn/Cd konstantalari (referens turi) farq qiladi.
    """
    day_str = ee.Date(image.get('system:time_start')).format('YYYY-MM-dd')
    day_start = ee.Date(day_str)

    daily_met = get_daily_era5_aggregate(day_start, roi)
    dem = image.select('DEM')

    # Grass — meteorologik referens
    grass_calc = RefETCalculator(ref_type='grass')
    grass_result = grass_calc.calculate(daily_met, dem, mode='daily')
    etref = grass_result.select('ETr').rename('ETREF_24')

    # Alfalfa — potensial (yuqori chegara)
    alfalfa_calc = RefETCalculator(ref_type='alfalfa')
    alfalfa_result = alfalfa_calc.calculate(daily_met, dem, mode='daily')
    etpot = alfalfa_result.select('ETr').rename('ETPOT_24')

    return image.addBands(etref).addBands(etpot)

# ==============================================================
# ETREF_24 + ETPOT_24 — istalgan kalendar kun uchun, Landsat'siz
# ==============================================================

def compute_reference_ets_for_date(date, roi):
    """
    Kunlik ETREF_24 (grass) + ETPOT_24 (alfalfa) — Landsat sahnaga
    BOG'LIQ EMAS (sof meteorologik + astronomik hisob).

    Monthly analytics uchun: har kalendar kunda to'g'ridan-to'g'ri
    chaqiriladi — interpolyatsiya yoki radiatsiya-nisbat bilan
    "cho'zish" shart emas, chunki bu meteorologik miqdor har doim
    ERA5'dan mustaqil, aniq hisoblanadi.
    """
    day_start = ee.Date(date)
    daily_met = get_daily_era5_aggregate(day_start, roi)

    dem = (ee.Image(cfg.DEM['collection'])
           .select(cfg.DEM['band']).rename('DEM'))

    grass_calc = RefETCalculator(ref_type='grass')
    grass_result = grass_calc.calculate(daily_met, dem, mode='daily')
    etref = grass_result.select('ETr').rename('ETREF_24')

    alfalfa_calc = RefETCalculator(ref_type='alfalfa')
    alfalfa_result = alfalfa_calc.calculate(daily_met, dem, mode='daily')
    etpot = alfalfa_result.select('ETr').rename('ETPOT_24')

    return etref.addBands(etpot).set('system:time_start', day_start.millis())


# ==============================================================
# Landsat sahnaga qo'shish uchun — endi yuqoridagini chaqiradi
# ==============================================================

def compute_reference_ets_daily2(image, roi):
    """
    Landsat sahna sanasiga mos ETREF_24/ETPOT_24'ni image'ga qo'shadi.
    (et_decomposition.py uchun — sahna-darajasidagi diagnostika.)
    """
    day_str = ee.Date(image.get('system:time_start')).format('YYYY-MM-dd')
    refs = compute_reference_ets_for_date(day_str, roi)
    return image.addBands(refs)