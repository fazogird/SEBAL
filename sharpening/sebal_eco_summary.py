# -*- coding: utf-8 -*-
"""sebal_eco_vs_landsat.csv + log → kunlar bo'yicha ET_24 / EVAP_FRAC taqqoslash va anchorlar."""
import os, re, sys
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
HERE = os.path.dirname(os.path.abspath(__file__))
d = pd.read_csv(os.path.join(HERE, 'sebal_eco_vs_landsat.csv'))

# Anchorlar logdan: har kun uchun Landsat va ECOSTRESS varianti
anc, cur = [], None
for line in open(os.path.join(HERE, 'sebal_eco_vs_landsat.log'), encoding='utf-8', errors='replace'):
    m = re.search(r'######## (\S+) — (LANDSAT|ECOSTRESS)', line)
    if m:
        cur = (m.group(1), m.group(2))
    m = re.search(r'cold=([\d.]+)K\s+hot=([\d.]+)K\s+ΔT=([\d.]+)K', line)
    if m and cur:
        anc.append(dict(sana=cur[0], variant=cur[1], cold=float(m.group(1)), hot=float(m.group(2)), dT=float(m.group(3))))
a = pd.DataFrame(anc).pivot_table(index='sana', columns='variant', values=['cold', 'hot', 'dT'])
print('ANCHORLAR (K):'); print(a.round(1).to_string())

for k in ['ET_24', 'EVAP_FRAC', 'LST']:
    s = d[d.kattalik == k]
    print(f'\n===== {k}: ECOSTRESS − Landsat (har kun) =====')
    print(s[['sana', 'eco_soat', 'qatlam', 'n', 'landsat_orta', 'eco_orta', 'MBE', 'MBE_pct', 'RMSE', 'R2']]
          .sort_values(['qatlam', 'sana']).to_string(index=False))
