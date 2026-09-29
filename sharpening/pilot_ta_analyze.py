# -*- coding: utf-8 -*-
"""
T-A pilot tahlili (pilot_ta_samples_*.csv):
  1) Kalibrlash: har kun k_d = median(ET_L/ET_V); umumiy k (median); bir kunni chiqarib qoldirish (LOO).
  2) Qoldiq (k qo'llangandan keyin) — NDVI, yil kuni, ko'rish burchagi, yil bo'yicha.
  3) Fizik tekshiruv: kunlikka o'tkazish ETrF·ETr24 bilan (SOLAR_FRAC·Rs24 o'rniga).
  4) P3 (faqat optika) va T-A (VIIRS) — 2023-05-24 → 2023-06-09 juftligida, t2 dagi Landsat bilan.
"""
import glob, os, sys
import numpy as np
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
d = pd.concat([pd.read_csv(f) for f in sorted(glob.glob(os.path.join(HERE, 'pilot_ta_samples_*.csv')))])
ok = d.L_ET_24.notna() & d.V_ET_24.notna() & (d.L_ET_24 > 0.1) & (d.V_ET_24 > 0.1)
d = d[ok].copy()
d['r'] = d.L_ET_24 / d.V_ET_24


def met(t, p):
    e = p - t
    tm, pm = t.mean(), p.mean()
    r = ((t - tm) * (p - pm)).sum() / np.sqrt(((t - tm) ** 2).sum() * ((p - pm) ** 2).sum())
    return f"MBE {100 * e.mean() / tm:+6.1f}%  RMSE {np.sqrt((e ** 2).mean()):.2f}  R² {r * r:.2f}"


# 0) Tekshiruv: ET_24 = SOLAR_FRAC × RS24 × 86400 (SEBAL_Milliy)
chk = (d.L_SOLAR_FRAC * d.L_RS24 * 86400 / d.L_ET_24).median()
print(f'Tekshiruv ET_24 / (SOLAR_FRAC·RS24·86400) median = {chk:.3f} (1 bo\'lishi kerak)\n')

# 1) Kalibrlash
print('===== 1) HAR KUN: VIIRS vs Landsat ET (ekin nuqtalari) =====')
rows = []
for s, g in d.groupby('sana'):
    k_d = g.r.median()
    rows.append((s, len(g), g.vz.iloc[0], g.L_ET_24.median(), g.V_ET_24.median(), k_d))
    print(f"{s}  n={len(g):4d}  vz={g.vz.iloc[0]:>4}  ET_L {g.L_ET_24.median():.2f}  ET_V {g.V_ET_24.median():.2f}  "
          f"k_d={k_d:.3f}  | xom: {met(g.L_ET_24, g.V_ET_24)}")
k_all = d.r.median()
k_days = pd.Series([r[5] for r in rows])
print(f'\nUmumiy k (barcha nuqtalar medianasi) = {k_all:.3f} | kunlik k: median {k_days.median():.3f}, '
      f'min {k_days.min():.3f}, max {k_days.max():.3f}, CV {100 * k_days.std() / k_days.mean():.1f}%')

print('\n===== LOO: har kun uchun k boshqa kunlardan =====')
for s, g in d.groupby('sana'):
    k_loo = d[d.sana != s].r.median()
    print(f"{s}  k_LOO={k_loo:.3f}  tuzatilgan: {met(g.L_ET_24, k_loo * g.V_ET_24)}")
d['V_corr'] = d.sana.map({s: d[d.sana != s].r.median() for s in d.sana.unique()}) * d.V_ET_24
print(f"\nJAMI (LOO bilan tuzatilgan): {met(d.L_ET_24, d.V_corr)}   | xom: {met(d.L_ET_24, d.V_ET_24)}")

# 2) Qoldiq tahlili
d['eps_pct'] = 100 * (d.V_corr - d.L_ET_24) / d.L_ET_24.clip(lower=0.5)
print('\n===== 2) QOLDIQ (LOO tuzatishdan keyin), median % =====')
d['ndvi_s'] = pd.cut(d.L_NDVI, [-1, 0.3, 0.6, 1], labels=['NDVI<0.3', '0.3–0.6', '>0.6'])
print('NDVI bo\'yicha:', d.groupby('ndvi_s', observed=True).eps_pct.median().round(1).to_dict())
d['oy'] = pd.to_datetime(d.sana).dt.month
print('Oy bo\'yicha:  ', d.groupby('oy').eps_pct.median().round(1).to_dict())
print('Yil bo\'yicha: ', d.groupby('yil').eps_pct.median().round(1).to_dict())
print('Ko\'rish burchagi:', d.groupby('vz').eps_pct.median().round(1).to_dict())

# 3) Fizik tekshiruv: ETrF bilan kunlikka o'tkazish
d['V_alt'] = d.V_ETRF_RAW * d.V_ETR24
d['L_alt'] = d.L_ETRF_RAW * d.L_ETR24
print('\n===== 3) KUNLIKKA O\'TKAZISH USULI (ekin, barcha kunlar) =====')
print(f"VIIRS SOLAR (hozirgi) vs Landsat SOLAR : {met(d.L_ET_24, d.V_ET_24)}")
print(f"VIIRS ETrF·ETr24      vs Landsat SOLAR : {met(d.L_ET_24, d.V_alt)}")
print(f"VIIRS ETrF·ETr24      vs Landsat ETrF  : {met(d.L_alt, d.V_alt)}")
print(f"Landsat ETrF          vs Landsat SOLAR : {met(d.L_ET_24, d.L_alt)}")

# 4) P3 va T-A — 2023-05-24 → 2023-06-09
t1, t2 = '2023-05-24', '2023-06-09'
a = d[d.sana == t1].set_index('pid'); b = d[d.sana == t2].set_index('pid')
j = a.join(b, lsuffix='_1', rsuffix='_2', how='inner')
if len(j) > 30:
    print(f'\n===== 4) {t1} → {t2}: t2 dagi Landsat ET bashorati (n={len(j)}) =====')
    p0 = j.L_SOLAR_FRAC_1 * j.L_RS24_2 * 86400
    x, y = j.L_NDVI_1, j.L_SOLAR_FRAC_1                       # P3: F = a + b·NDVI (t1 da), t2 NDVI bilan
    bx = ((x - x.mean()) * (y - y.mean())).sum() / ((x - x.mean()) ** 2).sum()
    ax = y.mean() - bx * x.mean()
    p3 = (ax + bx * j.L_NDVI_2).clip(lower=0) * j.L_RS24_2 * 86400
    k_loo = d[d.sana != t2].r.median()
    ta = k_loo * j.V_ET_24_2
    print(f"P0 hozirgi usul (F o'zgarmas):   {met(j.L_ET_24_2, p0)}")
    print(f"P3 faqat optika (NDVI yangilanadi): {met(j.L_ET_24_2, p3)}")
    print(f"T-A VIIRS (k_LOO={k_loo:.3f}):        {met(j.L_ET_24_2, ta)}")
