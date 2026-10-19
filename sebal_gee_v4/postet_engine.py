# -*- coding: utf-8 -*-
"""
Post-ET suv hisobi — VEKTORLANGAN dvigatel (piksellar massivi, kunlik qadam), uchta rejim (user, 2026-10-05).
GEE bitta grafda uzluksiz suv yilini ko'tarmaydi (sinov 2026-10-05: haqiqiy kunlik kirishlar bilan 180 kunda
"User memory limit exceeded") → gibrid: GEE kirishlarni chiqaradi (postet_inputs), hisob shu yerda (postet_run).

Rejimlar:
  HS   — Hydrosat yo'li (ochiq hujjatlar; yopiq qismlar eng yaqin ochiq ekvivalent bilan):
         S (ildiz zonasi, o'zgarmas Zr_max) — termal kunda Scott/SEBAL θ = θs·exp((EF − 1)/0.421) ga tenglashtiriladi,
         oraliqda IDC kunlik balansi (sug'orishsiz); bulutli kun ET — suv balansi modeli (Ks·Kcb + Ke)·ETo;
         AW_oy = ΣET + ΣR + Σq + ΔS − ΣP;  ETPR = α·ET, α = S_pr/S (Hydrosat 2025; α ≤ 1 bilan, oshgan kunlar soni QA);
         S_pr — parallel faqat-yog'in IDC chelagi;  ETPR_VPP = P − R − DP (VPP 2022);  ETAW = ET − ETPR.
  BZ   — bizning yo'l: termal kunda ET = SEBAL, qolgan kun (Ks·Kcb + Ke)·ETo; FAO-56 Zr(t) + ildiz osti qatlami;
         IDC qoidasi (mavsumda, Dr > RAW → FC gacha); manba kuzatuvi S_P/S_A/S_0.
         Parametrlar: delta_s — zaxira (ΔS) usuli (DELTA_S_USULLARI), stress — 'feddes' | 'fao'.
         rule_stop_on_stress=False bilan: delta_s='balans' + stress='fao' → wb_engine_np V0 bilan AYNAN;
         'scott'/'ks_fao' → V1/V3 bilan zaxira aynan. Sukut (True): termal stress kuni qoida barcha variantlarda o'chadi.
  ETAW — faqat ETAW (AW yo'q): ET mahsuloti − ETPR (yog'in chelagi P − R − DP) − ETG.
Vaqt: suv yili 1-okt → 30-sen; holat UZLUKSIZ (yil chegarasida qayta boshlanmaydi); S0 faqat birinchi kunda (spin-up).
Ekin mavsumi — har piksel, har suv yili NDVI fenologiyasidan (CROP_START, PEAK, CROP_END); mavsumdan tashqarida
ildiz Zr_min, IDC qoidasi o'chiq.
Tuproq — HiHydroSoil v2 6 qatlami (xom ×10⁻⁴); qatlam ichida o'zgarmas → zona o'rtachasi qatlam qalinligi ulushlari bilan
(wb_engine_np'ning 5 sm bo'laklari bilan aynan bir xil natija); oxirgi qatlam z_bottom gacha davom etadi.
ETG — sizot suvi: etg_capillary_rise() ulanish joyi; sizot chuqurligi (WTD) va tasdiqlangan parametrlar bo'lmaguncha NaN.
"""
import numpy as np

from .wb_engine_np import (COTTON, CN_ROW_CROPS, H_FC_CM, HHS_SCALE, KC_MAX, KE_SCALE, KCB_MIN_OBS, NDVI_BARE,
                           NDVI_FULL, ZE, vg_theta)

LAYER_NAMES = ['0-5cm', '5-15cm', '15-30cm', '30-60cm', '60-100cm', '100-200cm']
LAYER_TOP = np.array([0.00, 0.05, 0.15, 0.30, 0.60, 1.00])
LAYER_BOT = np.array([0.05, 0.15, 0.30, 0.60, 1.00, 2.00])
HHS_VARS = ['wcsat', 'wcres', 'alpha', 'N', 'ksat', 'wcpf4-2']
SCOTT_C = 0.421                     # Scott, Bastiaanssen, Ahmad 2003 (pySEBAL)
FEDDES_H3, FEDDES_H4 = -1000.0, -15000.0   # sm; user qarori 2026-10-05 (Bushland: stress pF ≈ 3,0 da boshlanadi)
# BZ rejimida ΔS (zaxira) qanday topiladi — parametr delta_s (user, 2026-10-05):
#   'balans'    — suv balansi; termal kunda ET = SEBAL ET, zaxiraga tegilmaydi (V0)       ← Bushland zond sinovida eng yaxshi
#   'termalsiz' — suv balansi; termal umuman ishlatilmaydi (ET har kuni modeldan)
#   'scott'     — termal kunda θ = θs·exp((EF − 1)/0,421) ga K bilan yaqinlashtiriladi (V1, pySEBAL/Scott 2003)
#   'ks_fao'    — Ks_obs = (ET/ETo − Ke)/Kcb; Ks_obs < 1 → FAO-56 Ks teskari (RAW_FAO = p·TAW), K bilan; Ks_obs ≥ 1
#                 va model RAW_FAO dan quruq → S_FC − RAW_FAO gacha (V3)
#   'feddes'    — xuddi shunday, lekin Feddes teskari: h = h4 + Ks_obs·(h3 − h4) → θ(h) (van Genuchten); chegara θ(h3) (VF)
#   Operator chegarasi o'ziniki; sug'orish qoidasi chegarasi — `stress` dan (user qarori 2026-10-05).
DELTA_S_USULLARI = ('balans', 'termalsiz', 'scott', 'ks_fao', 'feddes')
STRESS_USULLARI = ('fao', 'feddes')

# Fenologiya (NDVI) — sozlanadigan chegaralar (taxminiy emas, aniq qoida; hisobotda ko'rsatiladi)
PHENO = dict(frac=0.10,            # mavsum boshi/oxiri: minimum + frac·(cho'qqi − minimum) chegarasi kesishgan kun
             min_amp=0.20,         # cho'qqi − minimum < shu → ekin mavsumi yo'q (ekin emas / yalang'och)
             min_peak=0.35)        # cho'qqi NDVI < shu → ekin mavsumi yo'q


# ----------------------------------------------------------------------------------------------------------------
# Tuproq
# ----------------------------------------------------------------------------------------------------------------
class SoilV:
    """Piksellar massivi uchun tuproq. hhs — {var: (6, n) xom HiHydroSoil}; hsg, top_fc, top_wp, top_rew — (n,)."""

    def __init__(self, hhs, hsg, top_fc, top_wp, top_rew, z_bottom, ksat_mm_per_unit=1e-3):
        s = HHS_SCALE
        self.ts, self.tr = hhs['wcsat'] * s, hhs['wcres'] * s
        self.alpha, self.n = hhs['alpha'] * s, hhs['N'] * s
        self.fc = vg_theta(H_FC_CM, self.ts, self.tr, self.alpha, self.n)
        self.wp = hhs['wcpf4-2'] * s
        self.ks = hhs['ksat'] * ksat_mm_per_unit                                   # mm/kun
        n = self.ts.shape[1]
        hsg = np.asarray(hsg, dtype=float).round().astype(int)
        hsg = np.where(hsg > 4, hsg % 10, hsg)                                      # ikki guruhli (11–14) → birinchi harf
        self.cn = np.vectorize(lambda g: CN_ROW_CROPS.get(int(g), np.nan))(hsg).astype(float)
        self.zb = np.broadcast_to(np.asarray(z_bottom, dtype=float), (n,)).copy()
        self.bot = np.repeat(LAYER_BOT[:, None], n, axis=1)
        self.bot[-1] = np.maximum(LAYER_BOT[-1], self.zb)                           # oxirgi qatlam z_bottom gacha
        self.top = np.repeat(LAYER_TOP[:, None], n, axis=1)
        self.tew = np.maximum(1000.0 * (np.asarray(top_fc) - 0.5 * np.asarray(top_wp)) * ZE, 1.0)
        self.rew = np.minimum(np.asarray(top_rew, dtype=float), self.tew)

    def zone(self, z0, z1):
        """[z0, z1) — S_fc, S_wp, S_sat, S_r (mm), o'rtacha θ (ts, tr, fc, wp), n, garmonik Ks; z0, z1 — (n,) yoki son."""
        w = np.clip(np.minimum(self.bot, z1) - np.maximum(self.top, z0), 0.0, None)   # (6, n) qalinlik, m
        h = w.sum(0)
        hs = np.where(h > 0, h, np.nan)
        out = dict(h=h, S_fc=1000 * (w * self.fc).sum(0), S_wp=1000 * (w * self.wp).sum(0),
                   S_sat=1000 * (w * self.ts).sum(0), S_r=1000 * (w * self.tr).sum(0))
        for k, v in (('ts', self.ts), ('tr', self.tr), ('fc', self.fc), ('wp', self.wp), ('n', self.n),
                     ('alpha', self.alpha)):
            out[k] = (w * v).sum(0) / hs
        with np.errstate(divide='ignore', invalid='ignore'):
            out['ks'] = h / np.where(w > 0, w / self.ks, 0.0).sum(0)
        return out


# ----------------------------------------------------------------------------------------------------------------
# Yordamchi formulalar (wb_engine_np bilan aynan)
# ----------------------------------------------------------------------------------------------------------------
def root_depth(t_days, crop):
    """FAO-56: ekishgacha (t ≤ 0) Zr_min; L_ini + L_dev davomida chiziqli; keyin Zr_max. t_days — (n,)."""
    li, ld = crop['stages'][0], crop['stages'][1]
    zr = crop['zr_min'] + (crop['zr_max'] - crop['zr_min']) * np.minimum(np.maximum(t_days, 0) / (li + ld), 1.0)
    return np.where(t_days <= 0, crop['zr_min'], zr)


def kcb_of(ndvi, days_after_peak, crop):
    """Milliy_Kc UZ yo'li: Kcb = kcb_max·fc(NDVI)·sen; fc = clamp((NDVI − bare)/(full − bare), 0, 1)."""
    fc = np.clip((ndvi - NDVI_BARE) / (NDVI_FULL - NDVI_BARE), 0.0, 1.0)
    sen = 1.0 - (1.0 - crop['kcb_end_frac']) * np.minimum(np.maximum(days_after_peak, 0.0) / crop['sen_len'], 1.0)
    return crop['kcb_max'] * fc * sen, fc


def ke_of(kcb, fcov, De, soil):
    Kr = np.where(De <= soil.rew, 1.0, np.clip((soil.tew - De) / (soil.tew - soil.rew), 0.0, 1.0))
    return np.maximum(np.minimum(Kr * (KC_MAX - kcb), (1.0 - fcov) * KC_MAX), 0.0) * KE_SCALE


def ks_fao(S, z, p):
    """FAO-56 Eq 84 (Dr = S_fc − S; RAW = p·TAW)."""
    TAW = z['S_fc'] - z['S_wp']
    RAW = p * TAW
    Dr = z['S_fc'] - S
    return np.where(Dr <= RAW, 1.0, np.clip((TAW - Dr) / np.where(TAW - RAW > 0, TAW - RAW, np.nan), 0.0, 1.0)), TAW, RAW


def vg_h(theta, z):
    """van Genuchten teskari: θ → h (sm, manfiy), zona parametrlari bilan."""
    m = 1.0 - 1.0 / z['n']
    se = np.clip((theta - z['tr']) / (z['ts'] - z['tr']), 1e-6, 1.0)
    return -((se ** (-1.0 / m) - 1.0) ** (1.0 / z['n'])) / z['alpha']


def ks_feddes(S, z, zr):
    """Feddes quruq tarmog'i (yig'ma ildiz zonasi): Ks = (h − h4)/(h3 − h4), h — θ_rz dan (van Genuchten).
    RAW — stress boshlanishigacha bo'lgan kamomad: S_fc − 1000·θ(h3)·Zr. Qaytaradi: Ks, TAW, RAW."""
    TAW = z['S_fc'] - z['S_wp']
    th_on = vg_theta(-FEDDES_H3, z['ts'], z['tr'], z['alpha'], z['n'])
    RAW = np.maximum(z['S_fc'] - 1000.0 * th_on * zr, 0.0)
    h = vg_h(S / (1000.0 * zr), z)
    return np.clip((h - FEDDES_H4) / (FEDDES_H3 - FEDDES_H4), 0.0, 1.0), TAW, RAW


def runoff_scs(P, S, z, zr, soil):
    """IDC Eq 5–7: namlikka bog'liq SCS-CN (faqat yog'in)."""
    th = S / (1000.0 * zr)
    Smax = 25400.0 / soil.cn - 254.0
    Scn = np.where(th <= z['fc'] / 2, Smax,
                   np.maximum(Smax * (1 - (th - z['fc'] / 2) / (z['ts'] - z['fc'] / 2)), 0.0))
    return np.where(P > 0.2 * Scn, (P - 0.2 * Scn) ** 2 / np.where(P + 0.8 * Scn > 0, P + 0.8 * Scn, np.nan), 0.0)


def percolation_vg(S_star, z, zr):
    """IDC Eq 13: van Genuchten–Mualem, bir kunda FC dan pastga quritmaydi."""
    Se = np.clip((S_star / (1000.0 * zr) - z['tr']) / (z['ts'] - z['tr']), 0.0, 1.0)
    m = 1.0 - 1.0 / z['n']
    q_vg = z['ks'] * Se ** 0.5 * (1.0 - (1.0 - Se ** (1.0 / m)) ** m) ** 2
    return np.minimum(q_vg, np.maximum(S_star - z['S_fc'], 0.0))


def etg_capillary_rise(wtd_m, S, z, et_demand):
    """ETG — sizot suvidan kapillyar ko'tarilish (user qarori 2026-10-05: 1-yo'l — quduq + model).
    Tuzilma: Liu, Pereira, Fernando 2006 (AWM 84:27–40; ISAREG/SIMDualKc) — GW = f(sizot chuqurligi, ildiz zonasi
    zaxirasi, ET talabi). Parametrlar maqoladan tasdiqlanmaguncha va WTD (quduq) rasteri bo'lmaguncha — NaN (o'ylab
    topilgan qiymat yo'q). Qaytaradi: (etg_mm, mavjud_belgisi)."""
    n = S.shape[0]
    return np.full(n, np.nan), np.zeros(n, dtype=bool)


# ----------------------------------------------------------------------------------------------------------------
# NDVI — kunlik chiziqli interpolyatsiya (har piksel o'z yaroqli kuzatuvlari orasida; chetda ushlab turadi)
# ----------------------------------------------------------------------------------------------------------------
class NdviDaily:
    def __init__(self, obs_t, obs_v):
        """obs_t — (k,) kun raqami (int, o'sib boruvchi); obs_v — (k, n), NaN = bulut/yo'q."""
        self.t = np.asarray(obs_t, dtype=np.int64)
        self.v = np.asarray(obs_v, dtype=float)
        k, n = self.v.shape
        valid = np.isfinite(self.v)
        ar = np.arange(k)[:, None]
        last = np.where(valid, ar, -1)
        self.prev_i = np.maximum.accumulate(last, axis=0)                              # ≤ k dagi oxirgi yaroqli
        nxt = np.where(valid, ar, k)
        self.next_i = np.minimum.accumulate(nxt[::-1], axis=0)[::-1]                   # ≥ k dagi birinchi yaroqli
        self.any = valid.any(0)

    def at(self, day):
        k, n = self.v.shape
        cols = np.arange(n)
        a = np.searchsorted(self.t, day, side='right') - 1                            # oxirgi kuzatuv ≤ day
        b = np.searchsorted(self.t, day, side='left')                                 # birinchi kuzatuv ≥ day
        pi = self.prev_i[a] if a >= 0 else np.full(n, -1)
        ni = self.next_i[b] if b < k else np.full(n, k)
        has_p, has_n = pi >= 0, ni < k
        pv = np.where(has_p, self.v[np.clip(pi, 0, k - 1), cols], np.nan)
        nv = np.where(has_n, self.v[np.clip(ni, 0, k - 1), cols], np.nan)
        pt = np.where(has_p, self.t[np.clip(pi, 0, k - 1)], 0)
        nt = np.where(has_n, self.t[np.clip(ni, 0, k - 1)], 0)
        w = np.where(has_p & has_n & (nt > pt), (day - pt) / np.where(nt > pt, nt - pt, 1), 0.0)
        out = np.where(has_p & has_n, pv + w * (nv - pv), np.where(has_p, pv, nv))
        # interpolate('time').ffill().bfill() bilan bir xil: chetda yaqin qiymat ushlanadi
        return out


# ----------------------------------------------------------------------------------------------------------------
# Fenologiya — har piksel, har suv yili
# ----------------------------------------------------------------------------------------------------------------
def phenology(ndvi_year, pheno=PHENO):
    """ndvi_year — (365|366, n) bitta suv yilining kunlik NDVI'si. Qaytaradi kun indekslari (suv yili boshidan):
    start, peak, end (mavsum yo'q → -1) va has_season (bool)."""
    nd, n = ndvi_year.shape
    peak = np.nanargmax(np.where(np.isfinite(ndvi_year), ndvi_year, -np.inf), axis=0)
    npk = ndvi_year[peak, np.arange(n)]
    idx = np.arange(nd)[:, None]
    before = idx <= peak[None, :]
    after = idx >= peak[None, :]
    nmin_b = np.nanmin(np.where(before, ndvi_year, np.inf), axis=0)
    nmin_a = np.nanmin(np.where(after, ndvi_year, np.inf), axis=0)
    thr_b = nmin_b + pheno['frac'] * (npk - nmin_b)
    thr_a = nmin_a + pheno['frac'] * (npk - nmin_a)
    below_b = before & (ndvi_year < thr_b[None, :])
    start = np.where(below_b.any(0), nd - 1 - np.argmax(below_b[::-1], axis=0), 0)       # chegaradan pastdagi oxirgi kun
    below_a = after & (ndvi_year < thr_a[None, :])
    end = np.where(below_a.any(0), np.argmax(below_a, axis=0), nd - 1)                   # cho'qqidan keyin birinchi kun
    has = (npk - nmin_b >= pheno['min_amp']) & (npk >= pheno['min_peak'])
    return (np.where(has, start, -1), np.where(has, peak, -1), np.where(has, end, -1), has)


# ----------------------------------------------------------------------------------------------------------------
# Asosiy yurish
# ----------------------------------------------------------------------------------------------------------------
def run(days, P, ETo, ndvi, thermal_et, thermal_ef, soil, crop=None, *, season, S0_frac=0.5, w_top=1.0,
        runoff=True, modes=('HS', 'BZ', 'ETAW'), et_product=None, wtd=None, hs_cloudy='wb', out_start=None,
        delta_s='balans', stress='feddes', K_termal=0.5, rule_stop_on_stress=True):
    """
    delta_s    — BZ rejimida zaxira (ΔS) usuli: DELTA_S_USULLARI ('balans' | 'termalsiz' | 'scott' | 'ks_fao' | 'feddes');
    stress     — BZ stress va IDC qoidasi chegarasi: 'feddes' (h3 = −1000 sm, user qarori) | 'fao' (FAO-56, ekin p);
    K_termal   — 'scott' / 'ks_fao' / 'feddes' operatorlari kuchaytirishi (0…1);
    rule_stop_on_stress — termal Ks_obs < 1 kuni IDC qoidasi o'chadi: True — barcha termal variantlarda (sukut);
                 False — faqat 'ks_fao'/'feddes' (eski wb_engine_np V0/V1/V3 bilan aynanlik uchun);
    days       — pandas.DatetimeIndex (uzluksiz kunlar; spin-up + maqsad yillari);
    P, ETo     — kunlik massivlar: funksiya f(i) → (n,) yoki (n_days, n) massiv;
    ndvi       — NdviDaily (yoki f(i) → (n,));
    thermal_et — {kun indeksi: (n,) ET_24 (NaN = shu pikselda kuzatuv yo'q)}; thermal_ef — {kun indeksi: (n,) EF};
    soil       — SoilV; crop — COTTON kabi lug'at; season — {'start','peak','end'}: (n_days,) emas, balki
                 har kun uchun mavsum holatini beruvchi lug'at (season_arrays() natijasi);
    S0_frac    — boshlang'ich zaxira, WP→FC ulushi (son yoki (n,)); w_top — sug'orish yuzani ho'llaydimi (1/0);
    et_product — ETAW rejimi uchun kunlik ET mahsuloti f(i) → (n,) (bo'lmasa HS ET'si ishlatiladi);
    wtd        — sizot suvi chuqurligi f(i) → (n,) metr (ETG uchun; bo'lmasa ETG = NaN);
    out_start  — natija yig'ila boshlaydigan sana (spin-up chiqarilmaydi).
    Qaytaradi: oylik natijalar lug'ati {(YYYY, MM): {band: (n,)}} va kunlik diagnostika (ixtiyoriy emas — yengil).
    """
    crop = crop or COTTON
    if delta_s not in DELTA_S_USULLARI:
        raise ValueError(f"delta_s = '{delta_s}' noma'lum; tanlov: {DELTA_S_USULLARI}")
    if stress not in STRESS_USULLARI:
        raise ValueError(f"stress = '{stress}' noma'lum; tanlov: {STRESS_USULLARI}")
    n = soil.ts.shape[1]
    get = lambda f, i: f(i) if callable(f) else (f[i] if np.ndim(f) == 2 else np.broadcast_to(f[i], (n,)))
    zb = soil.zb
    zmax = np.full(n, crop['zr_max'])
    p_st = crop['p']
    out_start = days[0] if out_start is None else out_start
    w_top = np.broadcast_to(np.asarray(w_top, dtype=float), (n,))
    f0 = np.broadcast_to(np.asarray(S0_frac, dtype=float), (n,))

    # ---------- boshlang'ich holat ----------
    zr = np.full(n, crop['zr_min'])
    rz, sb = soil.zone(0.0, zr), soil.zone(zr, zb)
    # BZ: manbalar [P, A, 0]
    a_rz = np.stack([np.zeros(n), np.zeros(n), rz['S_wp'] + f0 * (rz['S_fc'] - rz['S_wp'])])
    a_sb = np.stack([np.zeros(n), np.zeros(n), sb['S_wp'] + f0 * (sb['S_fc'] - sb['S_wp'])])
    De = soil.tew.copy()
    # HS: o'zgarmas ildiz zonasi [0, Zr_max]
    hz = soil.zone(0.0, zmax)
    S_hs = hz['S_wp'] + f0 * (hz['S_fc'] - hz['S_wp'])
    S_pr = S_hs.copy()
    De_hs = soil.tew.copy()
    Dr_vpp = (1.0 - f0) * (hz['S_fc'] - hz['S_wp'])
    # ETAW rejimi: yog'in chelagi (o'zgarmas Zr_max)
    Dr_e = Dr_vpp.copy()

    monthly = {}
    for i, day in enumerate(days):
        P_d = np.asarray(get(P, i), dtype=float)
        ETo_d = np.asarray(get(ETo, i), dtype=float)
        nd = ndvi.at(i) if hasattr(ndvi, 'at') else np.asarray(get(ndvi, i), dtype=float)
        th = thermal_et.get(i) if thermal_et is not None else None
        ef = thermal_ef.get(i) if thermal_ef is not None else None
        in_season = season['in_season'](i)
        dap = season['days_after_peak'](i)
        t_plant = season['days_since_start'](i)

        # ================= BZ (delta_s='balans', stress='fao' → wb_engine_np V0 bilan aynan) =================
        if 'BZ' in modes:
            zr_new = np.where(season['active_roots'](i), root_depth(t_plant, crop), crop['zr_min'])
            grow = zr_new > zr + 1e-9
            if grow.any():
                frac = np.where(grow, (zr_new - zr) / np.where(zb - zr > 0, zb - zr, np.nan), 0.0)
                move = a_sb * np.nan_to_num(frac)
                a_rz, a_sb = a_rz + move, a_sb - move
            shrink = zr_new < zr - 1e-9                                                 # hosildan keyin ildiz o'ladi
            if shrink.any():
                frac = np.where(shrink, (zr - zr_new) / zr, 0.0)
                move = a_rz * frac
                a_rz, a_sb = a_rz - move, a_sb + move
            zr = zr_new
            rz, sb = soil.zone(0.0, zr), soil.zone(zr, zb)
            S = a_rz.sum(0)
            kcb, fcov = kcb_of(nd, np.where(in_season, dap, 0.0), crop)
            ke = ke_of(kcb, fcov, De, soil)
            if stress == 'feddes':
                Ks, TAW, RAW = ks_feddes(S, rz, zr)
            else:
                Ks, TAW, RAW = ks_fao(S, rz, p_st)
            use_th = th is not None and delta_s != 'termalsiz'
            is_th = np.isfinite(th) if use_th else np.zeros(n, dtype=bool)
            ET = np.where(is_th, th if use_th else 0.0, (Ks * kcb + ke) * ETo_d)
            R = runoff_scs(P_d, S, rz, zr, soil) if runoff else np.zeros(n)
            S_star = S + P_d - R - ET
            q = percolation_vg(S_star, rz, zr)
            S_m = S_star - q
            over = S_m > rz['S_sat']
            if over.any():
                ex = np.where(over, S_m - rz['S_sat'], 0.0)
                if runoff:
                    R = R + ex
                else:
                    q = q + ex
                S_m = np.where(over, rz['S_sat'], S_m)
            deficit = np.where(S_m < rz['S_r'], rz['S_r'] - S_m, 0.0)
            S_m = np.maximum(S_m, rz['S_r'])
            # termal Ks_obs: stress ko'rsatsa (Ks_obs < 1) — IDC qoidasi shu kuni ishlamaydi. rule_stop_on_stress=True
            # (user qarori 2026-10-05) — barcha termal variantlarda; False — faqat 'ks_fao'/'feddes' (wb_engine_np V3)
            Ks_obs = np.full(n, np.nan)
            if use_th and (rule_stop_on_stress or delta_s in ('ks_fao', 'feddes')):
                ok_k = is_th & (kcb > KCB_MIN_OBS) & (ETo_d > 0)
                with np.errstate(divide='ignore', invalid='ignore'):
                    Ks_obs = np.where(ok_k, (np.where(is_th, th, 0.0) / ETo_d - ke) / kcb, np.nan)
            stressed_obs = np.isfinite(Ks_obs) & (Ks_obs < 1.0)
            I_q = np.where(in_season & (kcb > KCB_MIN_OBS) & ((rz['S_fc'] - S_m) > RAW) & ~stressed_obs,
                           rz['S_fc'] - S_m, 0.0)
            S_m = S_m + I_q
            # termal operator (delta_s): zaxiraga tuzatish d (mm); 'balans' / 'termalsiz' — tuzatish yo'q
            d = np.zeros(n)
            if use_th and delta_s == 'scott' and ef is not None:
                okf = is_th & np.isfinite(ef)
                th_obs = np.clip(rz['ts'] * np.exp((np.where(okf, ef, 1.0) - 1.0) / SCOTT_C), rz['tr'], rz['ts'])
                d = np.where(okf, K_termal * (1000.0 * th_obs * zr - S_m), 0.0)
            elif use_th and delta_s in ('ks_fao', 'feddes'):
                kso = np.where(np.isfinite(Ks_obs), np.clip(Ks_obs, 0.0, 1.0), 0.0)   # faqat Ks_obs < 1 da ishlatiladi
                # operator o'z chegarasi bilan (user qarori 2026-10-05): ks_fao — RAW_FAO = p·TAW; feddes — θ(h3) gacha;
                # sug'orish qoidasi chegarasi (RAW) — `stress` parametridan, alohida
                if delta_s == 'ks_fao':
                    RAW_op = p_st * TAW
                    S_obs = rz['S_fc'] - (TAW - kso * (TAW - RAW_op))
                else:
                    RAW_op = ks_feddes(S, rz, zr)[2]
                    h_obs = FEDDES_H4 + kso * (FEDDES_H3 - FEDDES_H4)
                    S_obs = 1000.0 * vg_theta(-h_obs, rz['ts'], rz['tr'], rz['alpha'], rz['n']) * zr
                low = np.isfinite(Ks_obs) & (Ks_obs < 1.0)
                bound = np.isfinite(Ks_obs) & (Ks_obs >= 1.0) & ((rz['S_fc'] - S_m) > RAW_op)
                d = np.where(low, K_termal * (S_obs - S_m), np.where(bound, (rz['S_fc'] - RAW_op) - S_m, 0.0))
            S_new = S_m + d
            a = a_rz + np.stack([P_d - R, I_q + np.maximum(d, 0.0), deficit])
            tot = a.sum(0)
            fr = np.where(tot > 0, a / np.where(tot > 0, tot, 1.0), np.array([[0.0], [0.0], [1.0]]))
            a = np.clip(a - fr * (ET + q), 0.0, None)
            at = a.sum(0)
            a_rz = np.where(at > 0, a * (S_new / np.where(at > 0, at, 1.0)), np.stack([np.zeros(n), np.zeros(n), S_new]))
            ETPR_b, ETAW_b, ET0_b = fr * ET
            a_sb = a_sb + fr * q
            sbt = a_sb.sum(0)
            q_deep = np.maximum(sbt - sb['S_fc'], 0.0)
            a_sb = np.where(q_deep > 0, a_sb * (1.0 - q_deep / np.where(sbt > 0, sbt, 1.0)), a_sb)
            De = np.minimum(np.maximum(De - P_d - w_top * (I_q + np.maximum(d, 0.0)), 0.0) + ke * ETo_d, soil.tew)
            # BZ_AW — faqat IDC qoidasi; termal tuzatish alohida BZ_TERMAL (+ qo'shilgan / − olingan), AW ga qo'shilmaydi
            bz = dict(BZ_ET=ET, BZ_AW=I_q, BZ_ETPR=ETPR_b, BZ_ETAW=ETAW_b, BZ_ET0=ET0_b, BZ_R=R, BZ_DP=q_deep,
                      BZ_NIRR=(I_q > 0.5).astype(float), BZ_TAQCHIL=deficit, BZ_TERMAL=d)
            bz_state = dict(BZ_S_RZ=S_new, BZ_S_SUB=a_sb.sum(0), BZ_THETA=S_new / (1000.0 * zr),
                            BZ_DR=rz['S_fc'] - S_new, BZ_ZR=zr)
        else:
            bz, bz_state = {}, {}

        # ================= HS (Hydrosat yo'li) =================
        if 'HS' in modes or 'ETAW' in modes:
            kcb_h, fcov_h = kcb_of(nd, np.where(in_season, dap, 0.0), crop)
            ke_h = ke_of(kcb_h, fcov_h, De_hs, soil)
            is_th = np.isfinite(th) if th is not None else np.zeros(n, dtype=bool)
            S_prev_end = S_hs.copy()                                                    # kechagi kun oxiri
            okf = np.zeros(n, dtype=bool)
            if ef is not None:                                                         # termal kun: S ← S_obs (Scott)
                okf = is_th & np.isfinite(ef)
                th_obs = np.clip(hz['ts'] * np.exp((ef - 1.0) / SCOTT_C), hz['tr'], hz['ts'])
                S_hs = np.where(okf, 1000.0 * th_obs * zmax, S_hs)
            Ks_h, TAW_h, RAW_h = ks_fao(S_hs, hz, p_st)
            if hs_cloudy == 'wb':
                et_cloud = (Ks_h * kcb_h + ke_h) * ETo_d
            else:                                                                      # 'kc' — Milliy_Kc (Ks yo'q)
                et_cloud = (kcb_h + ke_h) * ETo_d
            ET_h = np.where(is_th, th if th is not None else 0.0, et_cloud)
            R_h = runoff_scs(P_d, S_hs, hz, zmax, soil) if runoff else np.zeros(n)
            Sst = S_hs + P_d - R_h - ET_h
            q_h = percolation_vg(Sst, hz, zmax)
            S_hs = np.clip(Sst - q_h, hz['S_r'], hz['S_sat'])
            dS_h = S_hs - S_prev_end                       # tenglashtirish sakrashi ham kiradi (AW qoldig'i shundan)
            # parallel faqat-yog'in chelagi (IDC) — α = S_pr/S
            Ks_p, _, _ = ks_fao(S_pr, hz, p_st)
            ET_p = (Ks_p * kcb_h + ke_h) * ETo_d
            R_p = runoff_scs(P_d, S_pr, hz, zmax, soil) if runoff else np.zeros(n)
            Spst = S_pr + P_d - R_p - ET_p
            q_p = percolation_vg(Spst, hz, zmax)
            S_pr = np.clip(Spst - q_p, hz['S_r'], hz['S_sat'])
            alpha = S_pr / np.where(S_hs > 0, S_hs, np.nan)
            ETPR_a = np.minimum(alpha, 1.0) * ET_h
            # VPP yog'in chelagi (haqiqiy ET bilan quritiladi)
            Dr_vpp = Dr_vpp - (P_d - R_h) + ET_h
            DP_v = np.where(Dr_vpp < 0, -Dr_vpp, 0.0)
            Dr_vpp = np.clip(Dr_vpp, 0.0, TAW_h)
            ETPR_v = P_d - R_h - DP_v
            De_hs = np.minimum(np.maximum(De_hs - P_d, 0.0) + ke_h * ETo_d, soil.tew)
            hs = dict(HS_ET=ET_h, HS_P=P_d, HS_R=R_h, HS_Q=q_h, HS_DS=dS_h, HS_ETPR=ETPR_a, HS_ETPR_VPP=ETPR_v,
                      HS_ALFA_GT1=(alpha > 1).astype(float), HS_RESET=okf.astype(float))
            hs_state = dict(HS_S=S_hs, HS_THETA=S_hs / (1000.0 * zmax), HS_S_PR=S_pr)
        else:
            hs, hs_state = {}, {}

        # ================= ETAW (faqat ETAW) =================
        if 'ETAW' in modes:
            ET_e = np.asarray(get(et_product, i), dtype=float) if et_product is not None else ET_h
            R_e = runoff_scs(P_d, hz['S_fc'] - Dr_e, hz, zmax, soil) if runoff else np.zeros(n)
            Dr_e = Dr_e - (P_d - R_e) + ET_e
            DP_e = np.where(Dr_e < 0, -Dr_e, 0.0)
            Dr_e = np.clip(Dr_e, 0.0, hz['S_fc'] - hz['S_wp'])
            ETPR_e = P_d - R_e - DP_e
            etg, etg_ok = etg_capillary_rise(get(wtd, i) if wtd is not None else None, hz['S_fc'] - Dr_e, hz, ET_e)
            ea = dict(ETAW_ET=ET_e, ETAW_ETPR=ETPR_e, ETAW_ETBLUE=ET_e - ETPR_e, ETAW_ETG=etg,
                      ETAW_ETAW=np.where(etg_ok, ET_e - ETPR_e - etg, np.nan))
        else:
            ea = {}

        # ---------- oylik yig'ish ----------
        if day >= out_start:
            key = (day.year, day.month)
            m = monthly.setdefault(key, {})
            for k, v in {**bz, **hs, **ea}.items():
                m[k] = m.get(k, 0.0) + v
            m['N_DAYS'] = m.get('N_DAYS', 0) + 1
            for k, v in {**bz_state, **hs_state}.items():                              # oy oxiri holati
                m[k] = v
            m['P'] = m.get('P', 0.0) + P_d
            m['ETO'] = m.get('ETO', 0.0) + ETo_d

    # HS AW (oylik qoldiq) va ETAW
    for key, m in monthly.items():
        if 'HS_ET' in m:
            m['HS_AW'] = m['HS_ET'] + m['HS_R'] + m['HS_Q'] + m['HS_DS'] - m['HS_P']
            m['HS_ETAW'] = m['HS_ET'] - m['HS_ETPR']
            m['HS_ETAW_VPP'] = m['HS_ET'] - m['HS_ETPR_VPP']
    return monthly


def season_arrays(days, wy_start_idx, pheno_by_year, n):
    """Har kun uchun mavsum holatini beruvchi funksiyalar. pheno_by_year — {suv_yili_boshi_indeksi: (start, peak, end,
    has)} (indekslar suv yili ichida). Ekish = CROP_START; mavsum = [start, end]; ildiz o'sishi start dan end gacha."""
    wy_of_day = np.searchsorted(np.asarray(wy_start_idx), np.arange(len(days)), side='right') - 1
    starts = np.asarray(wy_start_idx)

    def unpack(i):
        w = wy_of_day[i]
        s0 = starts[w]
        st, pk, en, has = pheno_by_year[s0]
        k = i - s0
        return k, st, pk, en, has

    def in_season(i):
        k, st, pk, en, has = unpack(i)
        return has & (k >= st) & (k <= en)

    def days_after_peak(i):
        k, st, pk, en, has = unpack(i)
        return np.where(has, k - pk, 0.0)

    def days_since_start(i):
        k, st, pk, en, has = unpack(i)
        return np.where(has, k - st, -1.0)

    def active_roots(i):
        return in_season(i)

    return dict(in_season=in_season, days_after_peak=days_after_peak, days_since_start=days_since_start,
                active_roots=active_roots)
