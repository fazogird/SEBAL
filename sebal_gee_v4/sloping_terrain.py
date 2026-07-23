"""
SEBAL-GEE v4 — QIYA YUZALAR / TOG'LAR (sloping_terrain=True)
============================================================
Tasumi (2003), Ch.V "Application of SEBAL to Sloping Terrains" + App. E, K.
BARCHA rejimlarda ishlaydi (SEBAL_B, SEBAL_ID, pysebal) — `sloping_terrain`
bayrog'i bilan yoqiladi. False (default) → hech narsa o'zgarmaydi.

4 ta mustaqil tuzatish:

1. **Ts_dem** (Eq 5.11) — dT hisobi uchun yuza haroratini umumiy tayanch
   balandlikka keltirish:
       Ts_dem = Ts + 0.0065·Δz          (6.5 °C/km, nam havo lapse rate)
   Aks holda baland joylar orografik sovish tufayli "salqin" ko'rinib, past dT
   → past H → **noto'g'ri yuqori ET** beradi (App. K, Fig K.1).
   ⚠️ FAQAT dT–Ts munosabatida. Radiatsiyada (L↑, G₀) ASL Ts qoladi —
   yuza haqiqiy haroratida nur chiqaradi.
   ⚠️ `datum` AHAMIYATSIZ: u c5 (kesma) ichida qisqaradi, chunki
   c4 = (dT_hot−dT_cold)/(Ts_hot−Ts_cold) — AYIRMA. Shuning uchun datum=0.

2. **cosθ qiya yuzada** (Eq 5.12-5.13, Duffie & Beckman 1980):
   quyosh tushish burchagi qiyalik (s) va ekspozitsiya (γ) bilan o'zgaradi;
   keyin gorizontal ekvivalentga keltiriladi (÷cos s). K↓ ga kiradi.

3. **ETrF / Rs24 radiatsiya tuzatishi** (Eq 5.17-5.19):
       C_rad = [Rso_inst_Flat/Rso_inst_Pixel] × [Rso_24_Pixel/Rso_24_Flat]
   Instant holat sutkani ifodalamaydi (ertalab JSh qiyalik ko'p oladi, kechqurun
   kam) → "ETrF kunduzi barqaror" farazi qiyalikda buziladi.
   🔑 (K_B+K_D) atmosfera hadi flat va pixel uchun BIR XIL (quyosh o'rni
   qiyalikdan o'zgarmaydi) → NISBATLARDA QISQARADI → C_rad SOF GEOMETRIYA.
   Shuning uchun App.E dagi K_t/W/P/e_a kerak emas.

4. **z₀m va u200 tuzatishi** (Eq 5.20-5.23):
       C_z0m  = 1 + (s−5)/20        [faqat s ≥ 5°]  → z₀m_adj = C_z0m·z₀m
       C_wind = 1 + 0.1·(z−z_ws)/1000              → u200_adj = C_wind·u200
   ⚠️ App. K: ET bu ikkalasiga JUDA KAM sezgir (z₀m 2x o'zgarsa ham ET
   deyarli o'zgarmaydi — cold piksel 1.05·ETr ga qotirilgani uchun dT
   kompensatsiya qiladi). Lekin to'liqlik uchun qo'llanadi.

⚠️ MA'LUM CHEKLOV (App. K, Fig K.5-K.6): tog'da shamol fazoviy keskin
o'zgarsa, BITTA dT funksiyasi butun sahnaga to'g'ri kelmaydi (shamol Ts ni
sovutadi → chiziq buni "namroq" deb o'qiydi → ET oshadi). Kitob yechimi —
tasvirni ob-havo sharoitiga qarab SUB-HUDUDLARGA bo'lib, har biriga alohida
anchor va alohida dT. Bu modul buni HAL QILMAYDI (alohida ish).
"""

import ee
import math

LAPSE_RATE = 0.0065        # K/m — Eq 5.11 (6.5 °C/km, nam havo)
COS_THETA_MIN = 0.05       # o'z-soyasidagi qiyalik uchun quyi chegara
C_RAD_MIN, C_RAD_MAX = 0.5, 2.0   # C_radiation xavfsiz oralig'i
N_DAY_STEPS = 24           # sutkalik integrallash qadamlari (soatlik)


# ==============================================================
# 1. DEM-ga moslashtirilgan yuza harorati (Eq 5.11)
# ==============================================================

def lst_dem(image):
    """Ts_dem = Ts + 0.0065·z  (datum=0 — u c5 ichida qisqaradi)."""
    return (image.select('LST')
            .add(image.select('DEM').multiply(LAPSE_RATE))
            .rename('LST'))


# ==============================================================
# 2. Quyosh geometriyasi — qiyalik/ekspozitsiya (Eq 5.12-5.16)
# ==============================================================

def slope_aspect(image):
    """
    s (rad) va γ (rad) — DEM dan.
    γ konvensiyasi (Eq 5.12): 0=janub, −π/2=sharq, +π/2=g'arb, ±π=shimol.
    GEE aspect esa shimoldan soat yo'nalishida 0–360° → γ = aspect − 180°.
    """
    dem = image.select('DEM')
    s = ee.Terrain.slope(dem).multiply(math.pi / 180.0)
    gamma = (ee.Terrain.aspect(dem).subtract(180.0)
             .multiply(math.pi / 180.0))
    return s, gamma


def _decl(doy):
    """Quyosh og'ishi δ (Eq 5.14/E.6)."""
    return ee.Number(doy).multiply(2 * math.pi / 365.0).subtract(1.39).sin() \
             .multiply(0.409)


def _sc(doy):
    """Mavsumiy vaqt tuzatmasi Sc (Eq 5.16/E.8), soat."""
    b = ee.Number(doy).subtract(81).multiply(2 * math.pi / 364.0)
    return (b.multiply(2).sin().multiply(0.1645)
            .subtract(b.cos().multiply(0.1255))
            .subtract(b.sin().multiply(0.025)))


def _omega(t_utc_h, lon_deg, sc):
    """
    Soat burchagi ω (Eq 5.15/E.7), rad.
    Kitob: ω = π/12[(t_local + (Lz−Lm)/15 + Sc) − 12].
    t_local = t_utc + utc_offset,  Lz = −utc_offset·15,  Lm = −lon
    → utc_offset QISQARADI:  ω = π/12[(t_utc + lon/15 + Sc) − 12]
    """
    return (ee.Image(lon_deg).divide(15.0)
            .add(ee.Number(t_utc_h)).add(ee.Number(sc))
            .subtract(12.0).multiply(math.pi / 12.0))


def _cos_theta_slope(phi, delta, s, gamma, omega):
    """
    cosθ qiya yuzada — Duffie & Beckman (1980), Eq 5.12, keyin ÷cos s (5.13).

    cosθ_u = sinδ·sinφ·cos s − sinδ·cosφ·sin s·cosγ + cosδ·cosφ·cos s·cosω
           + cosδ·sinφ·sin s·cosγ·cosω + cosδ·sin s·sinγ·sinω
    """
    sd, cd = delta.sin(), delta.cos()
    sp, cp = phi.sin(), phi.cos()
    ss, cs = s.sin(), s.cos()
    sg, cg = gamma.sin(), gamma.cos()
    sw, cw = omega.sin(), omega.cos()

    cos_u = (sp.multiply(cs).multiply(sd)
             .subtract(cp.multiply(ss).multiply(cg).multiply(sd))
             .add(cp.multiply(cs).multiply(cw).multiply(cd))
             .add(sp.multiply(ss).multiply(cg).multiply(cw).multiply(cd))
             .add(ss.multiply(sg).multiply(sw).multiply(cd)))
    return cos_u.divide(cs)          # (5.13) gorizontal ekvivalent


def _sin_phi_sun(phi, delta, omega):
    """Quyoshning ufqdan balandligi sinusi — yassi yuza (E.5)."""
    return (phi.sin().multiply(delta.sin())
            .add(phi.cos().multiply(delta.cos()).multiply(omega.cos())))


def _geom(image):
    """Umumiy geometriya: φ, lon, DOY, δ, Sc, s, γ, t_utc (kasrli soat)."""
    ll = ee.Image.pixelLonLat()
    phi = ll.select('latitude').multiply(math.pi / 180.0)
    lon = ll.select('longitude')
    date = ee.Date(image.get('system:time_start'))
    doy = ee.Number(date.getRelative('day', 'year')).add(1)
    t_utc = date.difference(ee.Date(date.format('YYYY-MM-dd')), 'hour')
    s, gamma = slope_aspect(image)
    return phi, lon, doy, _decl(doy), _sc(doy), s, gamma, t_utc


def cos_theta_instant(image):
    """
    Overpass momentidagi cosθ (qiyalik/ekspozitsiya bilan, gorizontal ekvivalent).
    K↓ = Gsc·cosθ·dr·τsw uchun. Quyi chegara COS_THETA_MIN.
    """
    phi, lon, doy, delta, sc, s, gamma, t_utc = _geom(image)
    om = _omega(t_utc, lon, sc)
    return (_cos_theta_slope(phi, delta, s, gamma, om)
            .max(COS_THETA_MIN).rename('COS_THETA_SLOPE'))


# ==============================================================
# 3. Radiatsiya tuzatish koeffitsienti C_rad (Eq 5.17)
# ==============================================================

def _daily_ratio(image, n_steps=N_DAY_STEPS):
    """
    Ra24_pixel / Ra24_flat — cosθ va sinφ_quyosh ni sutka bo'yi raqamli
    integrallash (App. E yassi 24h formulasi qiyalik uchun berilmagan).
    Faqat musbat (kunduzgi) qismlar yig'iladi.
    """
    phi, lon, doy, delta, sc, s, gamma, _ = _geom(image)
    dt = 24.0 / n_steps
    sum_px = None
    sum_fl = None
    for i in range(n_steps):
        t = (i + 0.5) * dt                     # qadam markazi (UTC soat)
        om = _omega(t, lon, sc)
        cp_ = _cos_theta_slope(phi, delta, s, gamma, om).max(0)
        cf_ = _sin_phi_sun(phi, delta, om).max(0)
        sum_px = cp_ if sum_px is None else sum_px.add(cp_)
        sum_fl = cf_ if sum_fl is None else sum_fl.add(cf_)
    return sum_px.divide(sum_fl.max(1e-6))


def c_radiation(image, n_steps=N_DAY_STEPS):
    """
    C_rad (Eq 5.17) = [Rso_inst_Flat/Rso_inst_Pixel]·[Rso_24_Pixel/Rso_24_Flat]

    (K_B+K_D) flat va pixel uchun bir xil → qisqaradi → sof geometriya:
        C_rad = [sinφ_sun / cosθ_pixel] × [Ra24_pixel / Ra24_flat]
    """
    phi, lon, doy, delta, sc, s, gamma, t_utc = _geom(image)
    om = _omega(t_utc, lon, sc)
    cos_px = _cos_theta_slope(phi, delta, s, gamma, om).max(COS_THETA_MIN)
    sin_fl = _sin_phi_sun(phi, delta, om).max(COS_THETA_MIN)
    inst_ratio = sin_fl.divide(cos_px)
    day_ratio = _daily_ratio(image, n_steps)
    return (inst_ratio.multiply(day_ratio)
            .clamp(C_RAD_MIN, C_RAD_MAX).rename('C_RAD'))


def ra24_ratio(image, n_steps=N_DAY_STEPS):
    """Ra24_pixel/Ra24_flat — SEBAL_B da Rs24 ni tuzatish uchun."""
    return (_daily_ratio(image, n_steps)
            .clamp(C_RAD_MIN, C_RAD_MAX).rename('RA24_RATIO'))


# ==============================================================
# 4. z₀m va u200 tuzatishi (Eq 5.20-5.23)
# ==============================================================

def adjust_z0m(image, z0m):
    """
    z₀m_adj = C_z0m·z₀m,  C_z0m = 1 + (s−5)/20   [faqat s ≥ 5°]  (Eq 5.20-5.21)
    Har 10° qiyalikka z₀m 50% oshadi.
    """
    slope_deg = ee.Terrain.slope(image.select('DEM'))
    c = slope_deg.subtract(5.0).divide(20.0).add(1.0).max(1.0)
    c = c.where(slope_deg.lt(5.0), 1.0)
    return z0m.multiply(c)


def adjust_u200(image, u200, z_ws):
    """
    u200_adj = C_wind·u200,  C_wind = 1 + 0.1·(z−z_ws)/1000   (Eq 5.22-5.23)
    z_ws — "ob-havo stansiyasi" balandligi; bizda ERA5 → ROI o'rtacha balandligi.
    """
    dz = image.select('DEM').subtract(ee.Number(z_ws))
    c = dz.divide(1000.0).multiply(0.1).add(1.0).max(0.5)
    return u200.multiply(c)


def mean_elevation(dem, roi):
    """ROI o'rtacha balandligi — z_ws sifatida (client skalyar)."""
    v = dem.reduceRegion(ee.Reducer.mean(), roi, 1000,
                         maxPixels=1e9, bestEffort=True).values().get(0)
    return ee.Number(v).getInfo()
