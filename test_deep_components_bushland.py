# -*- coding: utf-8 -*-
"""
Bushland 2021 — CHUQUR KOMPONENT VALIDATSIYA (SEBAL vs lizimetr, overpass onida).
Har bir energiya-balans komponentini ground-truth bilan solishtiradi:
  LST, ALBEDO, Rn, K_DOWN(Rs_in), L_DOWN(LWdown), L_UP(LWup), G0(G_mean), Tair.
SEBAL param = saqlangan Excel (qayta run YO'Q). Lizimetr = 15-min fayl, overpass slotida.
Maqsad: buzuq sahnalarda QAYSI komponent (ayniqsa LST) noto'g'ri — warm-bias tekshiruvi.
"""
import sys
sys.path.insert(0, r'D:/Cloud_comp/Sebal/scripts')
import ee, pandas as pd, numpy as np
ee.Initialize(project='ee-chexovant11')

RES = r'D:/ET_2026/lyzimetr/25114670/result'
LYZ = r'D:/ET_2026/lyzimetr/25114670/data/lyz_2021_15min.xlsx'
XLS = RES + '/instant_diag_bushland_2021.xlsx'
OUT = RES + '/deep_components_bushland_2021.xlsx'

# 1) Overpass UTC vaqtlari (yengil — metadata, SEBAL emas)
box = ee.Geometry.Point([-102.097, 35.187])
col = (ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
       .filterBounds(box).filterDate('2021-03-01', '2021-11-01')
       .filter(ee.Filter.eq('WRS_PATH', 30)).filter(ee.Filter.eq('WRS_ROW', 36)))
times = col.aggregate_array('system:time_start').getInfo()
ov = {}
for t in times:
    dt = pd.Timestamp(t, unit='ms', tz='UTC').tz_convert('US/Central')
    ov[dt.strftime('%Y-%m-%d')] = dt.hour * 60 + dt.minute   # mahalliy daqiqa
print("  Overpass mahalliy vaqt (CST):",
      {k: f'{v//60:02d}:{v%60:02d}' for k, v in ov.items()})

# 2) SEBAL param (Excel HAMMASI)
seb = pd.read_excel(XLS, sheet_name='HAMMASI')
seb['sana'] = seb['sana'].astype(str).str[:10]

# 3) Lizimetr 15-min → overpass slotidagi qiymat (har sana, har nuqta)
lz = pd.read_excel(LYZ, sheet_name='Comparison_15min')
lz['sana'] = pd.to_datetime(lz['Year'].astype(int).astype(str) + '-' +
                            lz['DOY'].astype(int).astype(str), format='%Y-%j').dt.strftime('%Y-%m-%d')
lz['min'] = (lz['Time_hhmm'] // 100) * 60 + (lz['Time_hhmm'] % 100)
LCOL = {'LST_nadir_C': 'lys_LST', 'Albedo': 'lys_ALB', 'Rn_Wm2': 'lys_RN',
        'Rs_in_Wm2': 'lys_KDOWN', 'LWdown_Wm2': 'lys_LDOWN', 'LWup_Wm2': 'lys_LUP',
        'G_mean_Wm2': 'lys_G0', 'Ta_C': 'lys_Ta'}
recs = []
for sana, omin in ov.items():
    sub = lz[lz['sana'] == sana]
    if sub.empty:
        continue
    for nq in ['NE', 'SE', 'NW', 'SW']:
        s2 = sub[sub['Lysimeter'] == nq]
        if s2.empty:
            continue
        r = s2.iloc[(s2['min'] - omin).abs().argmin()]     # overpassga eng yaqin slot
        recs.append(dict(sana=sana, nuqta=nq, ov_slot=int(r['Time_hhmm']),
                         **{v: r[k] for k, v in LCOL.items()}))
lys = pd.DataFrame(recs)

# 4) Birlashtirish + komponent bias
m = seb.merge(lys, on=['sana', 'nuqta'], how='left')
m['SEBAL_LST_C'] = m['LST'] - 273.15
m['LST_bias'] = (m['SEBAL_LST_C'] - m['lys_LST']).round(2)
m['ALB_bias'] = (m['ALBEDO'] - m['lys_ALB']).round(3)
m['RN_bias'] = (m['RN'] - m['lys_RN']).round(1)
m['KDOWN_bias'] = (m['K_DOWN'] - m['lys_KDOWN']).round(1)
m['LDOWN_bias'] = (m['L_DOWN'] - m['lys_LDOWN']).round(1)
m['LUP_bias'] = (m['L_UP'] - m['lys_LUP']).round(1)
m['G0_bias'] = (m['G0'] - m['lys_G0']).round(1)

BROKEN = ['2021-03-03', '2021-05-06', '2021-06-23']
m['holat'] = np.where(m['sana'].isin(BROKEN), 'BUZUQ', 'sog')

# 5) Sahna kesimida komponent taqqoslash
cols = ['SEBAL_LST_C', 'lys_LST', 'LST_bias', 'ALBEDO', 'lys_ALB', 'ALB_bias',
        'RN', 'lys_RN', 'RN_bias', 'K_DOWN', 'lys_KDOWN', 'KDOWN_bias',
        'L_DOWN', 'lys_LDOWN', 'LDOWN_bias', 'L_UP', 'lys_LUP', 'LUP_bias',
        'G0', 'lys_G0', 'G0_bias']
g = m.groupby(['sana', 'holat'])[cols].mean().round(2).reset_index()
pd.set_option('display.width', 260, 'display.max_columns', 40)
print("\n  === LST validatsiya (SEBAL vs lizimetr nadir, overpass) ===")
print(g[['sana', 'holat', 'SEBAL_LST_C', 'lys_LST', 'LST_bias',
         'ALBEDO', 'lys_ALB', 'RN', 'lys_RN', 'RN_bias']].to_string(index=False))
print("\n  === LST bias: BUZUQ vs sog' o'rtacha ===")
print(m.groupby('holat')['LST_bias'].agg(['mean', 'min', 'max', 'count']).round(2).to_string())

with pd.ExcelWriter(OUT, engine='openpyxl') as xw:
    g.to_excel(xw, 'sahna_komponent', index=False)
    m[['sana', 'nuqta', 'holat', 'ov_slot'] + cols].round(3).to_excel(xw, 'nuqta_komponent', index=False)
print(f"\n  💾 {OUT}")
