# -*- coding: utf-8 -*-
"""
LST DIAGNOSTIKA — C2L2 warm-bias'ni NDVI-emissivitet qayta-inversiyasi bilan tuzatish.
Standalone (raw Landsat C2L2, SEBAL pipeline'siz — tez). Bushland 2021, 4 lizimetr bitta piksel.

3 TEKSHIRUV:
  1) LST bias NDVI/emissivitet bilan korrelyatsiyami? (→ emissivitet ildizmi)
  2) C2L2 ST_EMIS vs NDVI-emissivitet farqi qancha?
  3) Qayta-inversiya (ε_NDVI) LST ni lizimetrga qancha yaqinlashtiradi?

Qayta-inversiya (USGS C2 single-channel RTE):
  B(Ts) = ((TRAD − URAD)/ATRAN − (1−ε)·DRAD) / ε
  LST   = K2 / ln(K1/B(Ts) + 1),  K1=774.8853, K2=1321.0789 (L8/9 B10)
Tekshiruv: ε=ST_EMIS qo'ysak → LST_C2L2 ni qayta tiklashi kerak (formula sanity).
"""
import sys
sys.path.insert(0, r'D:/Cloud_comp/Sebal/scripts')
import ee, pandas as pd, numpy as np
ee.Initialize(project='ee-chexovant11')

OUTDIR = r'D:/ET_2026/lyzimetr/25114670/result/LST_diag'
LYZ = r'D:/ET_2026/lyzimetr/25114670/data/lyz_2021_15min.xlsx'
K1, K2 = 774.8853, 1321.0789
CENTERS = {'NE': [-102.0955385, 35.18816985], 'SE': [-102.0955390, 35.18612583],
           'NW': [-102.0978919, 35.18817119], 'SW': [-102.0979121, 35.18613288]}
pts = ee.FeatureCollection([ee.Feature(ee.Geometry.Point(v), {'nuqta': k})
                            for k, v in CENTERS.items()])

col = (ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
       .filterDate('2021-03-01', '2021-11-01')
       .filter(ee.Filter.eq('WRS_PATH', 30)).filter(ee.Filter.eq('WRS_ROW', 36))
       .filter(ee.Filter.lt('CLOUD_COVER', 95)))
ids = col.aggregate_array('system:index').getInfo()
times = col.aggregate_array('system:time_start').getInfo()
print(f"  {len(ids)} sahna (P30/R36)")

BANDS = ['ST_B10', 'ST_TRAD', 'ST_URAD', 'ST_DRAD', 'ST_ATRAN', 'ST_EMIS', 'SR_B4', 'SR_B5']
rows = []
for sid, t in zip(ids, times):
    img = col.filter(ee.Filter.eq('system:index', sid)).first().select(BANDS)
    sana = pd.Timestamp(t, unit='ms').strftime('%Y-%m-%d')
    ov_cst = pd.Timestamp(t, unit='ms', tz='UTC')
    ov_min = (ov_cst.hour * 60 + ov_cst.minute) - 6 * 60   # CST (DST'siz)
    fc = img.reduceRegions(pts, ee.Reducer.first(), 30).getInfo()
    for f in fc['features']:
        p = f['properties']
        rows.append(dict(sana=sana, ov_min=ov_min, nuqta=p['nuqta'],
                         **{b: p.get(b) for b in BANDS}))
df = pd.DataFrame(rows).dropna(subset=['ST_B10'])

# --- Scale factorlar ---
df['LST_C2L2'] = df.ST_B10 * 0.00341802 + 149.0 - 273.15          # °C
df['TRAD'] = df.ST_TRAD * 0.001
df['URAD'] = df.ST_URAD * 0.001
df['DRAD'] = df.ST_DRAD * 0.001
df['ATRAN'] = df.ST_ATRAN * 0.0001
df['EMIS_C2L2'] = df.ST_EMIS * 0.0001
df['red'] = df.SR_B4 * 0.0000275 - 0.2
df['nir'] = df.SR_B5 * 0.0000275 - 0.2
df['NDVI'] = (df.nir - df.red) / (df.nir + df.red)

# --- NDVI-emissivitet (Sobrino 2008 FVC; ε_v=0.985, ε_s=0.960, cavity) ---
Pv = (((df.NDVI - 0.2) / (0.5 - 0.2)).clip(0, 1)) ** 2
df['Pv'] = Pv
df['EMIS_NDVI'] = 0.985 * Pv + 0.960 * (1 - Pv) + 0.06 * Pv * (1 - Pv)

def reinvert(eps):
    B = ((df.TRAD - df.URAD) / df.ATRAN - (1 - eps) * df.DRAD) / eps
    return K2 / np.log(K1 / B + 1) - 273.15

df['LST_recover'] = reinvert(df.EMIS_C2L2)      # sanity: ≈ LST_C2L2 bo'lishi kerak
df['LST_corr'] = reinvert(df.EMIS_NDVI)         # NDVI-ε bilan tuzatilgan
df['EMIS_diff'] = (df.EMIS_C2L2 - df.EMIS_NDVI).round(4)

# --- Lizimetr LST (overpass CST) ---
lz = pd.read_excel(LYZ, sheet_name='Comparison_15min')
lz['sana'] = pd.to_datetime(lz.Year.astype(int).astype(str) + '-' + lz.DOY.astype(int).astype(str),
                            format='%Y-%j').dt.strftime('%Y-%m-%d')
lz['min'] = (lz.Time_hhmm // 100) * 60 + (lz.Time_hhmm % 100)
lys = []
for (sana, nq), grp in df.groupby(['sana', 'nuqta']):
    s2 = lz[(lz.sana == sana) & (lz.Lysimeter == nq)]
    if s2.empty: continue
    omin = grp.ov_min.iloc[0]
    lys.append(dict(sana=sana, nuqta=nq, lys_LST=s2.iloc[(s2['min'] - omin).abs().argmin()]['LST_nadir_C']))
df = df.merge(pd.DataFrame(lys), on=['sana', 'nuqta'], how='left')
df['bias_C2L2'] = (df.LST_C2L2 - df.lys_LST).round(2)
df['bias_corr'] = (df.LST_corr - df.lys_LST).round(2)

# ============ NATIJALAR ============
v = df.dropna(subset=['lys_LST'])
def stats(b):
    return dict(MBE=round(b.mean(), 2), RMSE=round(np.sqrt((b**2).mean()), 2),
                min=round(b.min(), 2), max=round(b.max(), 2))
print("\n  === TEKSHIRUV 3: LST tuzatish (lizimetrga nisbatan) ===")
print("   C2L2   :", stats(v.bias_C2L2))
print("   Tuzatilgan (ε_NDVI):", stats(v.bias_corr))
print(f"\n  === TEKSHIRUV 1: bias korrelyatsiyasi ===")
print(f"   corr(bias_C2L2, NDVI) = {v.bias_C2L2.corr(v.NDVI):.3f}")
print(f"   corr(bias_C2L2, EMIS_C2L2) = {v.bias_C2L2.corr(v.EMIS_C2L2):.3f}")
print(f"\n  === TEKSHIRUV 2: ST_EMIS vs ε_NDVI ===")
print(f"   o'rt EMIS_C2L2={v.EMIS_C2L2.mean():.4f}  EMIS_NDVI={v.EMIS_NDVI.mean():.4f}  farq={v.EMIS_diff.mean():.4f}")
print(f"   formula sanity: LST_recover − LST_C2L2 o'rt = {(v.LST_recover-v.LST_C2L2).mean():.3f}°C (≈0 kerak)")

g = v.groupby('sana').agg(NDVI=('NDVI','mean'), EMIS_C2L2=('EMIS_C2L2','mean'),
    EMIS_NDVI=('EMIS_NDVI','mean'), LST_C2L2=('LST_C2L2','mean'), LST_corr=('LST_corr','mean'),
    lys=('lys_LST','mean'), bias_C2L2=('bias_C2L2','mean'), bias_corr=('bias_corr','mean')).round(2)
pd.set_option('display.width', 220)
print("\n  === Sahna kesimida ===")
print(g.to_string())

OUT = OUTDIR + '/lst_reinvert_bushland_2021.xlsx'
with pd.ExcelWriter(OUT, engine='openpyxl') as xw:
    g.to_excel(xw, 'sahna')
    df.round(4).to_excel(xw, 'nuqta_hammasi', index=False)
    pd.DataFrame([{'metod':'C2L2', **stats(v.bias_C2L2)},
                  {'metod':'ε_NDVI tuzatilgan', **stats(v.bias_corr)}]).to_excel(xw, 'xulosa', index=False)
print(f"\n  💾 {OUT}")
