# -*- coding: utf-8 -*-
"""
Bushland 2021 — INSTANT ET validatsiya (1-qadam). TEZ in-memory (CSV/Drive YO'Q).
SEBAL_Milliy (ENERGIYA BALANSI, Kc EMAS). Anchor uchun butun tile, LEKIN qiymat
HAR LIZIMETR NUQTASINING BITTA PIKSELIDAN (fizikadan: Bushland H=2.8m, ⌀17m → 1×1).
4 lizimetr → 4 alohida bitta-piksel. Har overpass uchun:
  ET_INST(mm/soat), ETR_INST, ETRF_INST, SOLAR_FRAC, ET_24(kunlik), ETR24, RN24,
  NDVI, SAVI, LAI  — script hozir qanday hisoblasa shunday (o'zgartirilmagan).
"""
import sys
sys.path.insert(0, r'D:/Cloud_comp/Sebal/scripts')
import ee, pandas as pd, numpy as np
from sebal_gee_v4 import main as sm, config as cfg
ee.Initialize(project='ee-chexovant11')
cfg.CROP_CLOUD_MAX = 100   # sahna-keng bulut precheck O'CHIQ → barcha P30/R36 overpass qoladi
#   (lizimetr pikseli toza bo'lsa yetarli; bulutli piksel NaN bo'ladi, sahna tashlanmaydi)

CENTERS = {'NE': [-102.0955385, 35.18816985], 'SE': [-102.0955390, 35.18612583],
           'NW': [-102.0978919, 35.18817119], 'SW': [-102.0979121, 35.18613288]}
RES = r'D:/ET_2026/lyzimetr/25114670/result'

# 4 nuqta FC (BITTA PIKSEL — parcel EMAS)
pts = ee.FeatureCollection([ee.Feature(ee.Geometry.Point(v), {'nuqta': k})
                            for k, v in CENTERS.items()])

# Anchor konteksti: Bushland atrofida ~40km box (issiq/sovuq kontrast bor,
# to'liq 170km WRS tile emas → anchor getInfo ancha yengil/tez).
anchor_roi = ee.Geometry.Point([-102.097, 35.187]).buffer(20000).bounds()
print("  SEBAL_Milliy sahnalar ishlanmoqda (~40km anchor box)...", flush=True)
scenes, info = sm.process_tile(anchor_roi, '2021-03-01', '2021-11-01',
                               'SEBAL_Milliy', 'BOTH', 95, 'P30_R36',
                               anchor_method='cascade', utc_offset=-6)
print(f"  ✅ {len(scenes)} sahna | overpass sanalar: {info.get('dates')}")

WANT = ['ET_INST_MM_HR', 'ETR_INST', 'ETRF_INST', 'SOLAR_FRAC', 'ET_24', 'ETR24',
        'RN24', 'NDVI', 'SAVI', 'LAI']
avail = ee.Image(scenes[0]).bandNames().getInfo()
bands = [b for b in WANT if b in avail]
print(f"  Mavjud bandlar: {bands}")
print(f"  YO'Q: {[b for b in WANT if b not in avail]}")

rows = []
import time
for i, sc in enumerate(scenes):
    t0 = time.time()
    sc = ee.Image(sc)
    date = ee.Date(sc.get('system:time_start')).format('YYYY-MM-dd').getInfo()
    # BITTA PIKSEL: reduceRegions, first(), 30m native → nuqtadagi piksel qiymati
    fc = sc.select(bands).reduceRegions(pts, ee.Reducer.first(), 30).getInfo()
    print(f"    sahna {i+1}/{len(scenes)}  {date}  ({time.time()-t0:.0f}s)", flush=True)
    for f in fc['features']:
        p = f['properties']
        rows.append(dict(sana=date, nuqta=p.get('nuqta'),
                         **{b: (round(p[b], 4) if p.get(b) is not None else None)
                            for b in bands}))

df = pd.DataFrame(rows)

# Lizimetr instant (mm/soat) — cmp_instant_pairs.csv (o'lchangan)
lys = pd.read_csv(RES + '/cmp_instant_pairs.csv').rename(
    columns={'lizimetr': 'nuqta', 'lizimetr_qiymat': 'lys_inst'})[['sana', 'nuqta', 'lys_inst']]
df = df.merge(lys, on=['sana', 'nuqta'], how='left')
if 'ET_INST_MM_HR' in df:
    df['bias_%'] = np.where(df['lys_inst'] > 0,
                            ((df['ET_INST_MM_HR'] / df['lys_inst'] - 1) * 100).round(0), np.nan)

pd.set_option('display.width', 200, 'display.max_columns', 30)
print("\n  === HAR NUQTA-SAHNA (bitta piksel) ===")
print(df.to_string(index=False))

# Sahna kesimida o'rtacha (4 nuqta) — instant bias
print("\n  === SAHNA KESIMIDA (4 nuqta o'rt., instant ET) ===")
g = df.groupby('sana').agg(
    lys=('lys_inst', 'mean'), SEBAL=('ET_INST_MM_HR', 'mean'),
    NDVI=('NDVI', 'mean'), LAI=('LAI', 'mean')).round(3)
g['bias_%'] = ((g.SEBAL / g.lys - 1) * 100).round(0)
print(g.to_string())
df.to_csv(r'C:/Users/DA21F~1.NOZ/AppData/Local/Temp/instant_bushland.csv', index=False)
