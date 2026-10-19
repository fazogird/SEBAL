# -*- coding: utf-8 -*-
"""
Suv balansi dvigateli (yo'l xaritasi 7-B, "Yo'l B") — NUMPY NUSXA: bitta nuqta (piksel), kunlik.

GEE versiyasi shu formulalar bilan yoziladi. Bu nusxa Bushland lizimetri tekshiruvi (1-bosqich) va keyin GEE
natijasini solishtirish uchun. Har had manbasi bilan:

  Zr(d)  — FAO-56 bosqichlari (Table 11 uzunliklari, Table 22 Zr_max, p): ekishgacha Zr_min, rivojlanish oxirigacha
           chiziqli o'sadi, keyin Zr_max. Ildiz o'sganda ildiz ostidagi qatlam suvi ildiz zonasiga o'tadi.
  ETpot  = (Kcb(NDVI) + Ke)·ETo        — Milliy_Kc formulalari (ndvi_kc), paxta koeffitsientlari (crop_kc_table)
  ET     — termal kun: ET_obs;  aks holda (Ks·Kcb + Ke)·ETo
  Ks     — FAO-56 Eq 84 (ekin p) yoki IDC Eq 17 (p = 0.5)
  R      — SCS-CN, namlikka bog'liq (IDC Eq 5–7), faqat yog'indan
  q      — van Genuchten–Mualem (IDC Eq 13), bir kunda FC dan pastga quritmaydi → ildiz ostidagi qatlamga;
           u qatlam FC dan oshsa — chuqur drenaj
  AW     — hodisa (S1/SWIR yoki berilgan sanalar) yoki IDC qoidasi (Dr > RAW): FC gacha;
           termal tekshiruv (variant) tuzatadi
  manba  — IDC manba kuzatuvi: S = S_P + S_A + S_0 (S_0 — boshlang'ich suv, kelib chiqishi noma'lum)

Termal yangilash variantlari (faqat shu qadam farq qiladi):
  V0 — termal zaxiraga tegmaydi (faqat termal kunda ET = ET_obs)
  V1 — Scott/pySEBAL: θ_obs = θs·exp((EF − 1)/0.421), har termal kunda, K bilan
  V3 — bizniki: Ks_obs = (ET_obs/ETo − Ke)/Kcb; Ks_obs < 1 → S_obs (Ks teskari), K bilan;
       Ks_obs ≥ 1 va model Dr > RAW → S kamida S_FC − RAW gacha (ko'rilmagan sug'orish)

AW tuzatishlari (hisobot): termal "suv ko'p" desa — oraliqdagi (oxirgi termal kundan beri) AW oxiridan boshlab
kamaytiriladi; yetmasa — qolgani "qo'shimcha yo'qotish" (belgi). Termal "ko'rilmagan sug'orish" topsa — oraliqda
hodisa (radar) kuni bo'lsa o'sha kunga, bo'lmasa termal kuniga "sana kuzatilmagan" belgisi bilan yoziladi.
"""
import numpy as np
import pandas as pd

# ---- Tuproq: HiHydroSoil v2 qatlamlari (xom qiymat ×10⁻⁴; water_balance._vg_theta bilan bir xil VG) ----
LAYERS = [('0-5cm', 0.00, 0.05), ('5-15cm', 0.05, 0.15), ('15-30cm', 0.15, 0.30),
          ('30-60cm', 0.30, 0.60), ('60-100cm', 0.60, 1.00), ('100-200cm', 1.00, 2.00)]
HHS_SCALE = 1e-4
H_FC_CM = 33.0 * 10.197          # 33 kPa → sm suv ustuni (water_balance._vg_theta: kPa·10.197)
# SCS-CN: qator ekin, to'g'ri qator, yaxshi holat (USDA TR-55, Table 2-2b) — HSG A, B, C, D
CN_ROW_CROPS = {1: 67.0, 2: 78.0, 3: 85.0, 4: 89.0}

# ---- Ekin: paxta (crop_kc_table 'Paxta' + FAO-56) ----
COTTON = dict(kcb_max=1.10, kcb_end_frac=0.52, sen_len=55.0,    # crop_kc_table (FAO-56 asosida)
              p=0.65, zr_min=0.20, zr_max=1.4,                    # FAO-56 Table 22; ZR_MIN — crop_kc_table
              stages=(30, 50, 55, 45))                            # FAO-56 Table 11, Texas: L_ini, L_dev, L_mid, L_late
NDVI_BARE, NDVI_FULL, KC_MAX, KE_SCALE = 0.15, 0.85, 1.20, 0.30   # crop_kc_table (Milliy_Kc UZ yo'li)
ZE = 0.10                                                         # yuza qatlam, m (FAO-56; ndvi_kc)
KCB_MIN_OBS = 0.05                                                # Kcb bundan kichik (yalang'och) — Ks_obs ma'nosiz


def vg_theta(h_cm, ts, tr, alpha, n):
    """van Genuchten θ(h): θr + (θs − θr)/[1 + (α·h)^n]^(1 − 1/n)."""
    return tr + (ts - tr) / (1.0 + (alpha * h_cm) ** n) ** (1.0 - 1.0 / n)


class Soil:
    """Profil 5 sm qatlamchalarga bo'linadi (har biri o'z HiHydroSoil qatlami parametrlari bilan)."""

    def __init__(self, row, z_bottom, ksat_mm_per_unit, dz=0.05):
        self.dz = dz
        self.zt = np.arange(0.0, z_bottom - 1e-9, dz)                    # qatlamcha usti, m
        lay = [next((nm for nm, t, b in LAYERS if t <= z < b), LAYERS[-1][0]) for z in self.zt]
        g = lambda v: np.array([float(row[f'{v}|{nm}']) for nm in lay])
        self.ts, self.tr = g('wcsat') * HHS_SCALE, g('wcres') * HHS_SCALE
        self.alpha, self.n = g('alpha') * HHS_SCALE, g('N') * HHS_SCALE
        self.fc = vg_theta(H_FC_CM, self.ts, self.tr, self.alpha, self.n)
        self.wp = g('wcpf4-2') * HHS_SCALE
        self.ks = g('ksat') * ksat_mm_per_unit                          # mm/kun
        hsg = int(round(float(row['HSG'])))
        self.cn = CN_ROW_CROPS[hsg % 10 if hsg > 4 else hsg]            # ikki guruhli (11–14) → birinchi harf
        self.z_bottom = z_bottom
        # yuza qatlam (Ke) — Milliy_Kc bilan bir xil manba: soil_fc_wp_rew (0–15 sm), FAO-56 Eq 7.1
        self.tew = max(1000.0 * (float(row['top_fc']) - 0.5 * float(row['top_wp'])) * ZE, 1.0)
        self.rew = min(float(row['top_rew']), self.tew)

    def zone(self, z0, z1):
        """[z0, z1) oralig'i: S_FC, S_WP, S_sat, S_r (mm), o'rtacha θ, n, garmonik Ks."""
        w = np.clip(np.minimum(self.zt + self.dz, z1) - np.maximum(self.zt, z0), 0.0, None)
        h = w.sum()
        k = w > 0
        return dict(h=h, S_fc=1000 * (w * self.fc).sum(), S_wp=1000 * (w * self.wp).sum(),
                    S_sat=1000 * (w * self.ts).sum(), S_r=1000 * (w * self.tr).sum(),
                    ts=(w * self.ts).sum() / h, tr=(w * self.tr).sum() / h, fc=(w * self.fc).sum() / h,
                    wp=(w * self.wp).sum() / h, n=(w * self.n).sum() / h,
                    ks=h / (w[k] / self.ks[k]).sum())


def root_depth(day, crop, planting):
    """FAO-56: ekishgacha Zr_min; L_ini + L_dev davomida chiziqli o'sadi; keyin Zr_max (mavsum oxirigacha)."""
    li, ld, _, _ = crop['stages']
    t = (day - planting).days
    if t <= 0:
        return crop['zr_min']
    return crop['zr_min'] + (crop['zr_max'] - crop['zr_min']) * min(t / (li + ld), 1.0)


def kcb_of(ndvi, days_after_peak, crop):
    """Milliy_Kc UZ yo'li: Kcb = K_full·fc(NDVI)·sen;  fc = clamp((NDVI − bare)/(full − bare), 0, 1).
    K_full — to'liq qoplamdagi potensial koeffitsient:
      crop['kc_pot_sat'] berilsa — sun'iy yo'ldoshdan: stresssiz to'liq qoplam (NDVI ≥ 0.85) piksellardagi ET_SEBAL/ETo
                                   yuqori chegarasi (ichida transpiratsiya, tuproq bug'lanishi, adveksiya bor);
      aks holda crop['kcb_max']  — FAO-56 jadvali (crop_kc_table)."""
    fc = float(np.clip((ndvi - NDVI_BARE) / (NDVI_FULL - NDVI_BARE), 0.0, 1.0))
    sen = 1.0 - (1.0 - crop['kcb_end_frac']) * min(max(days_after_peak, 0.0) / crop['sen_len'], 1.0)
    k_full = crop['kc_pot_sat'] if crop.get('kc_pot_sat') is not None else crop['kcb_max']
    return k_full * fc * sen, fc


def _remove(amt, need, first=None):
    """amt (P, A, 0 miqdorlari)dan `need` mm olib tashlash; first berilsa — avval o'sha manbadan."""
    take = np.zeros(3)
    if first is not None:
        t = min(amt[first], need)
        take[first] += t
        need -= t
    rest = amt - take
    if need > 0 and rest.sum() > 0:
        take += rest * min(need / rest.sum(), 1.0)
    return amt - take, take


def run(inp, soil, crop, cfg):
    """
    inp  — DataFrame (index: kunlar), ustunlar:
           P, ETo, NDVI (kunlik interpolyatsiya), ET_obs (termal kun, aks holda NaN), EF_obs (NaN mumkin),
           event (bool — sug'orish hodisasi kuni)
    cfg  — variant ('V0'|'V1'|'V3'), stress ('fao'|'idc'), K, S0 ('wp'|'fc'), planting, season_end (pd.Timestamp),
           w_top (sug'orish yuzani ho'llaydimi: 1 — yomg'irlatib/egat, 0 — yer osti tomchilatib),
           runoff (sukut True; False — yopiq ustun, masalan tarozili lizimetr: yuza oqimi chiqmaydi),
           rule (sukut True — IDC sug'orish qoidasi), aw_obs (massiv, mm/kun — berilsa sug'orish shu, hodisa o'rniga)
    Qaytaradi: kunlik DataFrame (zaxira, oqimlar, AW manbasi bilan, ETPR/ETAW/ET_boshl).
    """
    var, K = cfg['variant'], float(cfg.get('K', 0.5))
    p_st = crop['p'] if cfg['stress'] == 'fao' else 0.5               # IDC Eq 17 = FAO shakli, p = 0.5
    planting, season_end, w_top = cfg['planting'], cfg['season_end'], float(cfg.get('w_top', 1.0))
    runoff = bool(cfg.get('runoff', True))                              # False — yopiq ustun (lizimetr): yuza oqimi yo'q
    rule = bool(cfg.get('rule', True))                                  # False — IDC qoidasi o'chiq (sinov: sug'orish berilgan)
    aw_obs = cfg.get('aw_obs')                                          # kuzatilgan sug'orish (mm/kun) — berilsa, hodisa o'rniga
    zb = soil.z_bottom
    peak = inp.loc[(inp.index >= planting) & (inp.index <= season_end), 'NDVI'].idxmax()

    zr = root_depth(inp.index[0], crop, planting)
    rz, sb = soil.zone(0.0, zr), soil.zone(zr, zb)
    s0 = cfg['S0']                                                      # 'wp' | 'fc' | ulush 0…1 (WP→FC oralig'ida)
    f0 = 0.0 if s0 == 'wp' else 1.0 if s0 == 'fc' else float(s0)
    a_rz = np.array([0.0, 0.0, rz['S_wp'] + f0 * (rz['S_fc'] - rz['S_wp'])])   # ildiz zonasi suvi manbalar bo'yicha [P, A, 0]
    a_sb = np.array([0.0, 0.0, sb['S_wp'] + f0 * (sb['S_fc'] - sb['S_wp'])])   # ildiz ostidagi qatlam
    De = soil.tew                                                       # ndvi_kc: boshlang'ich De = TEW
    open_aw = []                                                        # oxirgi termal kundan beri: [kun_idx, mm, manba]
    adj = np.zeros(len(inp))                                            # hisobot: kunlik AW tuzatishlari (±)
    flag_date = np.zeros(len(inp), dtype=bool)
    rows = []

    for i, day in enumerate(inp.index):
        r = inp.iloc[i]
        P, ETo = float(r['P']), float(r['ETo'])
        # 1. Ildiz o'sishi: yangi qatlam suvi (o'z manbalari bilan) ildiz zonasiga o'tadi
        zr_new = root_depth(day, crop, planting)
        if zr_new > zr + 1e-9:
            move = a_sb * (zr_new - zr) / (zb - zr)
            a_rz, a_sb = a_rz + move, a_sb - move
        zr = zr_new
        rz, sb = soil.zone(0.0, zr), soil.zone(zr, zb)
        S = a_rz.sum()
        TAW = rz['S_fc'] - rz['S_wp']
        RAW = p_st * TAW
        # 2. Ekin modeli (Milliy_Kc): Kcb, Ke, ETpot
        in_season = planting <= day <= season_end
        kcb, fcov = kcb_of(float(r['NDVI']), (day - peak).days if in_season else 0.0, crop)
        Kr = 1.0 if De <= soil.rew else float(np.clip((soil.tew - De) / (soil.tew - soil.rew), 0.0, 1.0))
        ke = max(min(Kr * (KC_MAX - kcb), (1.0 - fcov) * KC_MAX), 0.0) * KE_SCALE
        ETpot = (kcb + ke) * ETo
        # 3. Stress (kechagi holatdan)
        Dr = rz['S_fc'] - S
        Ks = 1.0 if Dr <= RAW else float(np.clip((TAW - Dr) / (TAW - RAW), 0.0, 1.0))
        # 4. ET
        thermal = not np.isnan(r['ET_obs'])
        ET = float(r['ET_obs']) if thermal else (Ks * kcb + ke) * ETo
        # 5. Yuza oqimi (faqat yog'in), namlikka bog'liq CN
        th = S / (1000.0 * zr)
        Smax = 25400.0 / soil.cn - 254.0
        Scn = Smax if th <= rz['fc'] / 2 else max(Smax * (1 - (th - rz['fc'] / 2) / (rz['ts'] - rz['fc'] / 2)), 0.0)
        R = (P - 0.2 * Scn) ** 2 / (P + 0.8 * Scn) if P > 0.2 * Scn else 0.0
        if not runoff:                                                   # yopiq ustun (lizimetr) — oqim chiqmaydi
            R = 0.0
        # 6. Hodisa bo'yicha sug'orish (FC gacha)
        if aw_obs is not None:                                            # A/B sinovlari: haqiqiy sug'orish miqdori va kuni
            I_h = float(aw_obs[i])
        else:
            I_h = max(rz['S_fc'] - (S + P - R - ET), 0.0) if (in_season and bool(r['event'])) else 0.0
        # 7. Perkolatsiya (vG–Mualem, bir kunda FC dan pastga quritmaydi)
        S_star = S + P - R + I_h - ET
        Se = float(np.clip((S_star / (1000.0 * zr) - rz['tr']) / (rz['ts'] - rz['tr']), 0.0, 1.0))
        m = 1.0 - 1.0 / rz['n']
        q_vg = rz['ks'] * Se ** 0.5 * (1.0 - (1.0 - Se ** (1.0 / m)) ** m) ** 2
        q = min(q_vg, max(S_star - rz['S_fc'], 0.0))
        S_m = S_star - q
        if S_m > rz['S_sat']:                                              # to'yinishdan ortig'i — oqim (yopiq ustunda — pastga)
            if runoff:
                R += S_m - rz['S_sat']
            else:
                q += S_m - rz['S_sat']
            S_m = rz['S_sat']
        deficit = 0.0
        if S_m < rz['S_r']:                                               # kuzatilgan ET suvdan ko'p — fizik chegara
            deficit = rz['S_r'] - S_m
            S_m = rz['S_r']
        # 8. IDC qoidasi (hodisa yo'q, tuproq chegaradan quruq, mavsumda, ekin bor; V3: termal stress ko'rsatmasa)
        Ks_obs = np.nan
        if thermal and var == 'V3' and kcb > KCB_MIN_OBS and ETo > 0:
            Ks_obs = (float(r['ET_obs']) / ETo - ke) / kcb
        stressed_obs = (not np.isnan(Ks_obs)) and Ks_obs < 1.0
        I_q = 0.0
        if rule and in_season and I_h == 0 and kcb > KCB_MIN_OBS and (rz['S_fc'] - S_m) > RAW and not stressed_obs:
            I_q = rz['S_fc'] - S_m
            S_m = rz['S_fc']
        # 9. Termal yangilash (variant)
        S_obs, d = np.nan, 0.0
        if thermal and var == 'V1' and not np.isnan(r['EF_obs']):
            th_obs = float(np.clip(rz['ts'] * np.exp((float(r['EF_obs']) - 1.0) / 0.421), rz['tr'], rz['ts']))
            S_obs = 1000.0 * th_obs * zr
            d = K * (S_obs - S_m)
        elif thermal and var == 'V3' and not np.isnan(Ks_obs):
            if Ks_obs < 1.0:
                S_obs = rz['S_fc'] - (TAW - max(Ks_obs, 0.0) * (TAW - RAW))
                d = K * (S_obs - S_m)
            elif rz['S_fc'] - S_m > RAW:                                  # "quruq emas" chegarasi — to'liq
                S_obs = rz['S_fc'] - RAW
                d = S_obs - S_m
        I_t, cut, q_t = max(d, 0.0), 0.0, 0.0
        if d < 0:                                                         # oraliqdagi ortiqcha AW kamaytiriladi
            need = -d
            for rec in reversed(open_aw):
                take = min(rec[1], need)
                rec[1] -= take
                adj[rec[0]] -= take
                cut += take
                need -= take
                if need <= 1e-9:
                    break
            q_t = need                                                    # qolgani — qo'shimcha yo'qotish (belgi)
        if I_t > 0:                                                       # ko'rilmagan sug'orish sanasi
            ev = [rec for rec in open_aw if rec[2] == 'hodisa']
            j = ev[-1][0] if ev else i
            adj[j] += I_t
            flag_date[j] = flag_date[j] or not ev
        S_new = S_m + d
        # 10. Manbalar: kirim P−R → P, AW → A, fizik chegara → 0; chiqim ET, q, q_t — tarkib bo'yicha; cut — A dan
        AW_today = I_h + I_q + I_t
        a = a_rz + np.array([P - R, AW_today, deficit])
        frac = a / a.sum() if a.sum() > 0 else np.array([0.0, 0.0, 1.0])
        a = a - frac * (ET + q + q_t)
        a, _ = _remove(np.clip(a, 0.0, None), cut, first=1)
        a_rz = a * (S_new / a.sum()) if a.sum() > 0 else np.array([0.0, 0.0, S_new])   # yaxlitlash xatosiz
        ETPR, ETAW, ET0 = frac * ET
        # 11. Ildiz ostidagi qatlam: q kiradi; FC dan oshgani — chuqur drenaj
        a_sb = a_sb + frac * q
        q_deep = max(a_sb.sum() - sb['S_fc'], 0.0)
        if q_deep > 0:
            a_sb = a_sb * (1.0 - q_deep / a_sb.sum())
        # 12. Yuza qatlam (Milliy_Kc De; sug'orish yuzani ho'llasa — u ham)
        De = min(max(De - P - w_top * AW_today, 0.0) + ke * ETo, soil.tew)
        if I_h > 0:
            open_aw.append([i, I_h, 'hodisa'])
        if I_q > 0:
            open_aw.append([i, I_q, 'qoida'])
        if thermal:
            open_aw = []
        rows.append(dict(sana=day, Zr=zr, S_rz=S_new, S_sub=a_sb.sum(), S_tot=S_new + a_sb.sum(),
                         theta=S_new / (1000 * zr), TAW=TAW, RAW=RAW, Dr=rz['S_fc'] - S_new,
                         ETo=ETo, NDVI=float(r['NDVI']), Kcb=kcb, Ke=ke, ETpot=ETpot, Ks=Ks, Ks_obs=Ks_obs,
                         ET=ET, termal=thermal, P=P, R=R, q=q, q_deep=q_deep,
                         I_hodisa=I_h, I_qoida=I_q, I_termal=I_t, AW_kamaytirildi=cut, q_tuzatish=q_t,
                         taqchil=deficit, ETPR=ETPR, ETAW=ETAW, ET_boshl=ET0))
    out = pd.DataFrame(rows).set_index('sana')
    # Hisobot AW: shu kuni berilgan (hodisa + qoida) + termal topgani (sanasi bilan) − keyin kamaytirilgani
    out['AW'] = out['I_hodisa'] + out['I_qoida'] + adj
    out['sana_kuzatilmagan'] = flag_date
    return out
