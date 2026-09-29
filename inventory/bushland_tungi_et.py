# Bushland 2021 (East: NE, SE) — tungi ET ulushi, 15 daqiqalik lizimetr omboridan (faqat o'qish)
import pandas as pd, numpy as np, sys
sys.stdout.reconfigure(encoding='utf-8')
d = pd.read_csv(r'D:\ET_2026\lyzimetr\25114670\export\lys2021E_15min.csv')
d = d.sort_values(['DOY', 'hhmm']).reset_index(drop=True)
rn = d[['NE_Rn', 'SE_Rn']].mean(axis=1)
d['night'] = rn < 0
rows = []
for lys in ['NE', 'SE']:
    s = d[f'{lys}_stor']
    et15 = -s.diff()                                   # ombor kamayishi = ET (mm/15min)
    wet = (d[f'{lys}_P'] > 0) | (et15 < -0.3)           # yog'in/sug'orish yoki keskin o'sish
    g = pd.DataFrame({'DOY': d.DOY, 'et': et15, 'night': d.night, 'wet': wet})
    day = g.groupby('DOY').agg(et_all=('et', 'sum'), et_night=('et', lambda x: x[g.loc[x.index, 'night']].sum()),
                               wet=('wet', 'any'), n=('et', 'size'))
    day = day[(~day.wet) & (day.n >= 90) & (day.et_all > 0.5)]
    day['frac'] = 100 * day.et_night / day.et_all
    day['lys'] = lys
    rows.append(day)
r = pd.concat(rows)
r['month'] = pd.to_datetime('2021-01-01') + pd.to_timedelta(r.index - 1, unit='D')
r['month'] = r['month'].dt.month
r = r[r.month.between(6, 9)]
t = r.groupby(['lys', 'month']).agg(kunlar=('frac', 'size'), ET_kun_mm=('et_all', 'median'),
                                    ET_tun_mm=('et_night', 'median'), tun_ulush_pct=('frac', 'median'),
                                    ulush_p25=('frac', lambda x: np.percentile(x, 25)),
                                    ulush_p75=('frac', lambda x: np.percentile(x, 75))).round(2)
print("Bushland 2021, quruq (yog'in/sug'orishsiz) kunlar: kunlik ET va uning tunda (Rn<0) bo'lgan qismi")
print(t.to_string())
