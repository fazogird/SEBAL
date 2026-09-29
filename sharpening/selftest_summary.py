# -*- coding: utf-8 -*-
"""selftest_lst_results.csv → kunlar bo'yicha o'rtacha (va oraliq) jadval, 100 m va 30 m."""
import os, sys
import pandas as pd

sys.stdout.reconfigure(encoding='utf-8')
d = pd.read_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'selftest_lst_results.csv'))
print('kunlar:', sorted(d.sana.unique()))
for scale in (100, 30):
    s = d[d.masshtab_m == scale]
    g = s.groupby(['qatlam', 'variant']).agg(
        n_kun=('sana', 'nunique'),
        bias=('bias', 'mean'), bias_min=('bias', 'min'), bias_max=('bias', 'max'),
        rmse=('rmse', 'mean'), rmse_min=('rmse', 'min'), rmse_max=('rmse', 'max'), cc=('cc', 'mean')).round(2)
    print(f'\n===== {scale} m: kunlar bo\'yicha o\'rtacha (min..max) =====')
    for q, gq in g.groupby(level=0, sort=False):
        print(f'\n[{q}]')
        for (_, v), r in gq.iterrows():
            print(f'  {v:18s} bias {r.bias:+5.2f} ({r.bias_min:+5.2f}..{r.bias_max:+5.2f})  '
                  f'RMSE {r.rmse:4.2f} ({r.rmse_min:4.2f}..{r.rmse_max:4.2f})  CC {r.cc:.3f}')
