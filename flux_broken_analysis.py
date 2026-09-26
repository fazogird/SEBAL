# -*- coding: utf-8 -*-
"""
BUZUQ SAHNA tahlili — ET≈0 sahnalar metrikaga qancha zarar beradi?
Buzuqlik belgisi (obs'dan MUSTAQIL, fizik): EVAP_FRAC_mean < EF_MIN → issiq/yalang'och
tuproq, EF hot-anchor tomonidan 0 ga qisilgan (root cause: LST >= hot anchor).
DAILY ET uchun: metrika HAMMASI / BUZUQSIZ / FAQAT-BUZUQ bo'lib model bo'yicha.
Chiqish: validation_result/broken_analysis.xlsx + konsol.
"""
import os, sys
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from val_metrics import val_stats
from flux_compare_full import (load_model_simple, load_model_inst, obs_amf_period,
                               obs_bush_daily, MODES, OUT)

EF_MIN = 0.05        # EVAP_FRAC shu qiymatdan past → buzuq (ET yo'q)


def main():
    daily = load_model_simple('DAILY')                 # mode,site,date,et_mean,et_median
    inst = load_model_inst()                            # ... EVAP_FRAC_mean, LST_mean
    ef = inst[['mode', 'site', 'date', 'EVAP_FRAC_mean']].copy()

    # obs qo'shish
    obs_all = []
    for site in sorted(daily['site'].unique()):
        o = obs_bush_daily() if site == 'Bushland_lys' else obs_amf_period(site, 'DD')
        if o is None:
            continue
        s = daily[daily['site'] == site].merge(o[['date', 'et_fmds']], on='date', how='inner')
        obs_all.append(s)
    P = pd.concat(obs_all, ignore_index=True)
    P = P.merge(ef, on=['mode', 'site', 'date'], how='left')
    P['broken'] = P['EVAP_FRAC_mean'] < EF_MIN
    P = P.dropna(subset=['et_mean', 'et_fmds'])

    rows = []
    for mode in MODES:
        sub = P[P['mode'] == mode]
        if sub.empty:
            continue
        nb = int(sub['broken'].sum()); nt = len(sub)
        for label, s in [('HAMMASI', sub),
                         ('BUZUQSIZ', sub[~sub['broken']]),
                         ('FAQAT_BUZUQ', sub[sub['broken']])]:
            if len(s) >= 3:
                st = val_stats(s['et_mean'].values, s['et_fmds'].values)
                rows.append(dict(mode=mode, nabor=label, n=st['n'],
                                 broken_n=nb, broken_pct=round(100 * nb / nt, 1),
                                 R2=st['R2'], r2_pearson=st['r2_pearson'],
                                 RMSE=st['RMSE'], MBE=st['MBE'],
                                 obs_mean=round(float(s['et_fmds'].mean()), 2),
                                 model_mean=round(float(s['et_mean'].mean()), 2)))
    R = pd.DataFrame(rows)

    # buzuq sahnalar ro'yxati (qaysi sana/sayt/model, obs bor edi lekin model~0)
    br = P[P['broken']][['mode', 'site', 'date', 'et_mean', 'et_fmds', 'EVAP_FRAC_mean']].copy()
    br = br.rename(columns={'et_mean': 'model_ET', 'et_fmds': 'obs_ET'}).sort_values(
        ['mode', 'site', 'date'])
    br[['model_ET', 'obs_ET', 'EVAP_FRAC_mean']] = br[['model_ET', 'obs_ET', 'EVAP_FRAC_mean']].round(3)

    path = os.path.join(OUT, 'broken_analysis.xlsx')
    with pd.ExcelWriter(path, engine='openpyxl') as w:
        R.to_excel(w, sheet_name='metrika', index=False)
        br.to_excel(w, sheet_name='buzuq_sahnalar', index=False)
    print(f'→ {path}\n')

    # konsol
    print('=== DAILY ET: buzuq sahna zarari (model=mean, ref=LE_F_MDS) ===')
    print(f'(buzuq = EVAP_FRAC < {EF_MIN})\n')
    for mode in MODES:
        t = R[R['mode'] == mode]
        if t.empty:
            continue
        h = t[t['nabor'] == 'HAMMASI']
        h = h.iloc[0] if len(h) else t.iloc[0]
        ntot = int(h.n)
        print(f'{mode}  (buzuq: {int(h.broken_n)}/{ntot} = {h.broken_pct}%)')
        for _, r in t.iterrows():
            print(f'   {r.nabor:<12} n={r.n:<4} R2={r.R2:>6}  r2p={r.r2_pearson:>5}  '
                  f'RMSE={r.RMSE:>5}  MBE={r.MBE:>6}  obs={r.obs_mean} model={r.model_mean}')
        print()
    return R, br


if __name__ == '__main__':
    main()
