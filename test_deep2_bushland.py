# -*- coding: utf-8 -*-
"""Vaqt konvensiyasini aniqlash (CST vs CDT) + to'liq komponent bias (KDOWN/LDOWN/LUP)."""
import sys
sys.path.insert(0, r'D:/Cloud_comp/Sebal/scripts')
import ee, pandas as pd, numpy as np
ee.Initialize(project='ee-chexovant11')
RES = r'D:/ET_2026/lyzimetr/25114670/result'
LYZ = r'D:/ET_2026/lyzimetr/25114670/data/lyz_2021_15min.xlsx'
XLS = RES + '/instant_diag_bushland_2021.xlsx'

lz = pd.read_excel(LYZ, sheet_name='Comparison_15min')
lz['sana'] = pd.to_datetime(lz['Year'].astype(int).astype(str) + '-' +
                            lz['DOY'].astype(int).astype(str), format='%Y-%j').dt.strftime('%Y-%m-%d')
lz['min'] = (lz['Time_hhmm'] // 100) * 60 + (lz['Time_hhmm'] % 100)

# --- Quyosh peak: Jul25 (yozgi kun) uchun Rs_in max qaysi vaqtda? ---
for sana in ['2021-07-25', '2021-08-26']:
    s = lz[(lz['sana'] == sana) & (lz['Lysimeter'] == 'NE')]
    pk = s.loc[s['Rs_in_Wm2'].idxmax(), 'Time_hhmm']
    print(f"  {sana}: Rs_in peak @ Time_hhmm={int(pk)} (CST bo'lsa peak~1247, CDT bo'lsa~1347)")

# Overpass UTC (GEE)
box = ee.Geometry.Point([-102.097, 35.187])
col = (ee.ImageCollection('LANDSAT/LC08/C02/T1_L2').filterBounds(box)
       .filterDate('2021-03-01', '2021-11-01')
       .filter(ee.Filter.eq('WRS_PATH', 30)).filter(ee.Filter.eq('WRS_ROW', 36)))
times = col.aggregate_array('system:time_start').getInfo()
# CST (standart, UTC-6, DST YO'Q) — barcha sana uchun
ovU = {pd.Timestamp(t, unit='ms', tz='UTC').strftime('%Y-%m-%d'):
       pd.Timestamp(t, unit='ms', tz='UTC') for t in times}
ov_cst = {d: (u.hour * 60 + u.minute) - 6 * 60 for d, u in ovU.items()}   # UTC-6 fixed
print("  Overpass CST (DST'siz):", {k: f'{v//60:02d}:{v%60:02d}' for k, v in list(ov_cst.items())[:4]}, '...')

seb = pd.read_excel(XLS, sheet_name='HAMMASI'); seb['sana'] = seb['sana'].astype(str).str[:10]
LCOL = {'LST_nadir_C': 'lys_LST', 'Albedo': 'lys_ALB', 'Rn_Wm2': 'lys_RN',
        'Rs_in_Wm2': 'lys_KDOWN', 'LWdown_Wm2': 'lys_LDOWN', 'LWup_Wm2': 'lys_LUP',
        'G_mean_Wm2': 'lys_G0'}
recs = []
for sana, omin in ov_cst.items():
    sub = lz[lz['sana'] == sana]
    for nq in ['NE', 'SE', 'NW', 'SW']:
        s2 = sub[sub['Lysimeter'] == nq]
        if s2.empty: continue
        r = s2.iloc[(s2['min'] - omin).abs().argmin()]
        recs.append(dict(sana=sana, nuqta=nq, **{v: r[k] for k, v in LCOL.items()}))
lys = pd.DataFrame(recs)
m = seb.merge(lys, on=['sana', 'nuqta'], how='left')
m['LST_b'] = (m['LST'] - 273.15 - m['lys_LST'])
m['RN_b'] = (m['RN'] - m['lys_RN'])
m['KDOWN_b'] = (m['K_DOWN'] - m['lys_KDOWN'])
m['LDOWN_b'] = (m['L_DOWN'] - m['lys_LDOWN'])
m['LUP_b'] = (m['L_UP'] - m['lys_LUP'])
m['G0_b'] = (m['G0'] - m['lys_G0'])
BROKEN = ['2021-03-03', '2021-05-06', '2021-06-23']
m['holat'] = np.where(m['sana'].isin(BROKEN), 'BUZUQ', 'sog')
g = m.groupby(['sana', 'holat']).agg(
    LST_b=('LST_b', 'mean'), RN_b=('RN_b', 'mean'), KDOWN_b=('KDOWN_b', 'mean'),
    LDOWN_b=('LDOWN_b', 'mean'), LUP_b=('LUP_b', 'mean'), G0_b=('G0_b', 'mean')).round(1).reset_index()
pd.set_option('display.width', 200)
print("\n  === KOMPONENT BIAS (SEBAL − lizimetr, CST vaqt) ===")
print(g.to_string(index=False))
print("\n  === O'RTACHA bias (barcha, W/m2 va °C) ===")
print(m[['LST_b','KDOWN_b','LDOWN_b','LUP_b','RN_b','G0_b']].mean().round(1).to_string())
