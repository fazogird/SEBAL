# -*- coding: utf-8 -*-
"""
Yo'l A — Hydrosat usuli (ochiq hujjatlardan tiklangan), NUMPY: bitta nuqta (piksel), kunlik hisob → oylik natija.

Hujjatlarda bori (Madera GSA paketi ilovasi 69–70-b.; VPP 2022 yakuniy hisoboti, Davids; Hydrosat javoblari):
  AW_oy   = ΣET + ΣR + Σq + ΔS − ΣP                       — oylik qoldiq
  ETPR    = P − R − DP  (yog'in chelagi, kunlik → oylik)  — VPP 2022 yakuniy shakli (ilovada α = S_pr/S shakli ham bor)
  ETAW    = ET − ETPR
  Ildiz chuqurligi — o'zgarmas (yo'l xaritasi 7-B jadvali: "Hydrosat'da ildiz o'zgarmas").
Yopiq ikki qism — eng yaqin OCHIQ ekvivalent bilan almashtirilgan (user tasdig'i, 2026-10-04):
  termal → namlik:  pySEBAL/Scott (2003): θ = θs·exp((EF − 1)/0.421), [θr, θs] oralig'ida (dvigatel V1 bilan bir xil);
                    termal kunlar orasida chiziqli, chetlarda yaqin qiymat; S = 1000·θ·Zr
  bulutli kun ET:   'nearest_rs' (A_1) — eng yaqin termal kunning ET/Rs ulushi × kunlik Rs (SEBAL standarti, daily_et.py);
                    'milliy_kc'  (A_2) — Milliy_Kc moduli (ndvi_kc, ekinga xos FAO-56 tarmog'i):
                                         ET = (Kcb(NDVI) + Ke)·ETo, Kcb = kcb_max·fc(NDVI)·sen, Ke — yog'in bilan
                                         yuritiladigan yuza qatlam (De), Ks YO'Q.
q — van Genuchten–Mualem (IDC Eq 13) θ_d bo'yicha, FC dan ortig'i bilan cheklangan (dvigatel bilan bir xil);
R — SCS-CN θ_d bo'yicha (IDC Eq 5–7); yopiq ustunda (lizimetr) 0.
Dvigatel (wb_engine_np) funksiyalari o'zgarishsiz import qilinadi.
"""
import numpy as np
import pandas as pd

from .wb_engine_np import KC_MAX, KE_SCALE, kcb_of


def _daily_et(inp, soil, crop, cloudy, planting, season_end):
    """Kunlik ET: termal kun — ET_obs; termalsiz — 'nearest_rs' yoki 'milliy_kc'."""
    obs = inp['ET_obs']
    th = obs.notna().values
    et = obs.copy()
    if cloudy == 'nearest_rs':
        ratio = (obs / inp['Rs']).where(th)
        tdays = inp.index[th]
        r_obs = ratio[th].values
        for i, day in enumerate(inp.index):
            if th[i]:
                continue
            j = int(np.argmin(np.abs((tdays - day).days)))               # teng masofada — oldingisi
            et.iloc[i] = r_obs[j] * float(inp['Rs'].iloc[i])
        return et, None
    # Milliy_Kc (ekinga xos tarmoq): De — kun boshidagi depletion; yog'in De yangilanishida (FAO-56 Eq 74, 77)
    peak = inp.loc[(inp.index >= planting) & (inp.index <= season_end), 'NDVI'].idxmax()
    De, rows = soil.tew, []
    for i, day in enumerate(inp.index):
        r = inp.iloc[i]
        kcb, fcov = kcb_of(float(r['NDVI']), max((day - peak).days, 0.0), crop)
        Kr = 1.0 if De <= soil.rew else float(np.clip((soil.tew - De) / (soil.tew - soil.rew), 0.0, 1.0))
        ke = max(min(Kr * (KC_MAX - kcb), (1.0 - fcov) * KC_MAX), 0.0) * KE_SCALE
        E = ke * float(r['ETo'])
        if not th[i]:
            et.iloc[i] = (kcb + ke) * float(r['ETo'])
        De = min(max(De - float(r['P']), 0.0) + E, soil.tew)
        rows.append((kcb, ke))
    return et, pd.DataFrame(rows, index=inp.index, columns=['Kcb', 'Ke'])


def run(inp, soil, crop, cfg):
    """
    inp — DataFrame (index: kunlar): P, ETo, NDVI, Rs (MJ/m², 'nearest_rs' uchun), ET_obs (termal kun, aks holda NaN),
          EF_obs (termal kun).
    cfg — cloudy ('nearest_rs' | 'milliy_kc'), zr (o'zgarmas ildiz zonasi, m), runoff (bool), S0 (yog'in chelagi
          boshlang'ich holati: 'wp' | 'fc' | ulush 0…1), planting, season_end.
    Qaytaradi: (kunlik DataFrame, oylik DataFrame).
    """
    zr = float(cfg['zr'])
    rz = soil.zone(0.0, zr)
    planting, season_end = cfg['planting'], cfg['season_end']
    et, kc = _daily_et(inp, soil, crop, cfg['cloudy'], planting, season_end)

    # termal → θ (Scott)
    th_obs = pd.Series(np.nan, index=inp.index)
    ok = inp['ET_obs'].notna() & inp['EF_obs'].notna()
    th_obs[ok] = np.clip(rz['ts'] * np.exp((inp.loc[ok, 'EF_obs'] - 1.0) / 0.421), rz['tr'], rz['ts'])
    m = 1.0 - 1.0 / rz['n']
    P = inp['P']
    s_mode = cfg.get('s_mode', 'interp')
    if s_mode == 'interp':
        # (user tasdiqlagan, 2026-10-04) θ termal kunlar orasida chiziqli; q — θ_d bo'yicha.
        # KAMCHILIK (sinovda topildi): θ berilgani uchun zaxira kamaymaydi → FC ustidagi bir xil suv har kuni qayta q bo'ladi.
        theta = th_obs.interpolate('time').ffill().bfill()
        S = 1000.0 * theta * zr
        Se = ((theta - rz['tr']) / (rz['ts'] - rz['tr'])).clip(0.0, 1.0)
        q_vg = rz['ks'] * Se ** 0.5 * (1.0 - (1.0 - Se ** (1.0 / m)) ** m) ** 2
        q = np.minimum(q_vg, (S - rz['S_fc']).clip(lower=0.0))
    else:
        # 'idc_reset' (TAKLIF, user qarori kutilmoqda): "S — SEBAL4.0 + IDC suv balansi" — zaxira har kuni balans bilan
        # yuradi (sug'orishsiz): S ← S + P − ET − q, q — shu holatdan (FC ustidagi suv bir marta oqadi);
        # termal kunda S = S_obs (to'liq tenglashtirish). Fizik chegara: S ≥ S_r.
        S_l, q_l, R_l = [], [], []
        S_cur = float(1000.0 * th_obs.dropna().iloc[0] * zr)
        Smax = 25400.0 / soil.cn - 254.0
        for i, day in enumerate(inp.index):
            if not np.isnan(th_obs.iloc[i]):
                S_cur = float(1000.0 * th_obs.iloc[i] * zr)
            Pd, Rd = float(P.iloc[i]), 0.0
            if cfg.get('runoff', True):                                   # SCS-CN, namlikka bog'liq (holatdan)
                thc = S_cur / (1000.0 * zr)
                Scn = Smax if thc <= rz['fc'] / 2 else max(Smax * (1 - (thc - rz['fc'] / 2) / (rz['ts'] - rz['fc'] / 2)), 0.0)
                Rd = (Pd - 0.2 * Scn) ** 2 / (Pd + 0.8 * Scn) if Pd > 0.2 * Scn else 0.0
            R_l.append(Rd)
            S_star = S_cur + Pd - Rd - float(et.iloc[i])
            Se_ = float(np.clip((S_star / (1000.0 * zr) - rz['tr']) / (rz['ts'] - rz['tr']), 0.0, 1.0))
            qv = rz['ks'] * Se_ ** 0.5 * (1.0 - (1.0 - Se_ ** (1.0 / m)) ** m) ** 2
            qd = min(qv, max(S_star - rz['S_fc'], 0.0))
            S_cur = min(max(S_star - qd, rz['S_r']), rz['S_sat'])
            S_l.append(S_cur)
            q_l.append(qd)
        S = pd.Series(S_l, index=inp.index)
        q = pd.Series(q_l, index=inp.index)
        theta = S / (1000.0 * zr)
    if s_mode != 'interp':
        R = pd.Series(R_l, index=inp.index)
    elif cfg.get('runoff', True):
        Smax = 25400.0 / soil.cn - 254.0
        Scn = np.where(theta <= rz['fc'] / 2, Smax,
                       np.maximum(Smax * (1 - (theta - rz['fc'] / 2) / (rz['ts'] - rz['fc'] / 2)), 0.0))
        R = pd.Series(np.where(P > 0.2 * Scn, (P - 0.2 * Scn) ** 2 / (P + 0.8 * Scn), 0.0), index=inp.index)
    else:
        R = pd.Series(0.0, index=inp.index)

    # yog'in chelagi (VPP: ETPR = P − R − DP), haqiqiy ET bilan quritiladi, Dr ≤ TAW
    TAW = rz['S_fc'] - rz['S_wp']
    s0 = cfg.get('S0', 'fc')
    f0 = 0.0 if s0 == 'wp' else 1.0 if s0 == 'fc' else float(s0)
    Dr, dp, drs = (1.0 - f0) * TAW, [], []
    for i in range(len(inp)):
        Dr = Dr - (float(P.iloc[i]) - float(R.iloc[i])) + float(et.iloc[i])
        d = -Dr if Dr < 0 else 0.0
        Dr = min(max(Dr, 0.0), TAW)
        dp.append(d)
        drs.append(Dr)
    DP = pd.Series(dp, index=inp.index)

    day = pd.DataFrame({'ET': et, 'termal': inp['ET_obs'].notna(), 'theta': theta, 'theta_obs': th_obs, 'S': S,
                        'q': q, 'R': R, 'P': P, 'DP_yogin': DP, 'Dr_yogin': drs, 'ETPR': P - R - DP})
    if kc is not None:
        day = day.join(kc)
    mo = day[['ET', 'q', 'R', 'P', 'ETPR']].resample('MS').sum()
    S_end = day['S'].resample('MS').last()
    S_beg = S_end.shift(1)
    S_beg.iloc[0] = day['S'].iloc[0]
    mo['dS'] = S_end - S_beg
    mo['AW'] = mo['ET'] + mo['R'] + mo['q'] + mo['dS'] - mo['P']
    mo['ETAW'] = mo['ET'] - mo['ETPR']
    return day, mo
