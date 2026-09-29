# -*- coding: utf-8 -*-
"""crosssensor_lst_{eco,viirs}.csv → sensor × masshtab × qatlam × usul bo'yicha kunlar o'rtachasi (min..max)."""
import os, sys
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
QATLAM = ['ekin maydoni', 'sovuq nomzod (ekin, NDVI>0.7)', 'issiq nomzod (ekin, NDVI<0.2)']
for sensor in ('eco', 'viirs'):
    f = os.path.join(HERE, f'crosssensor_lst_{sensor}.csv')
    if not os.path.exists(f):
        continue
    d = pd.read_csv(f)
    d = d[d.qatlam.isin(QATLAM) & d.RMSE.notna()]
    days = d[['sana', 'sensor_soat', 'vz']].drop_duplicates().sort_values('sana')
    print(f'\n################ {sensor.upper()} — {len(days)} kun')
    print(days.round(2).to_string(index=False))
    g = d.groupby(['masshtab', 'qatlam', 'usul'], sort=False).agg(
        kun=('sana', 'nunique'), MBE=('MBE', 'mean'), RMSE=('RMSE', 'mean'),
        RMSEu=('RMSEu', 'mean'), RMSEu_min=('RMSEu', 'min'), RMSEu_max=('RMSEu', 'max'),
        R2=('R2', 'mean'), R2_min=('R2', 'min'), R2_max=('R2', 'max')).round(2)
    for (m, q), gq in g.groupby(level=[0, 1], sort=False):
        print(f'\n[{m} | {q}]')
        for (_, _, u), r in gq.iterrows():
            print(f'  {u:24s} kun {int(r.kun):2d}  MBE {r.MBE:+5.2f}  RMSE {r.RMSE:4.2f}  '
                  f'RMSEu {r.RMSEu:4.2f} ({r.RMSEu_min:4.2f}..{r.RMSEu_max:4.2f})  R² {r.R2:.2f} ({r.R2_min:.2f}..{r.R2_max:.2f})')
