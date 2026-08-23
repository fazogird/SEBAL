# -*- coding: utf-8 -*-
"""
Bushland 2021 — INSTANT ET TO'LIQ DIAGNOSTIKA (buzuq sahnalar sababini topish).
Har sahna × 4 lizimetr nuqtasi (BITTA PIKSEL) uchun BARCHA SEBAL parametrlari:
  A guruh — energiya→LE→ET: Rn, G, H, LE(LAMBDA_E), EVAP_FRAC, ET_inst, ETr, ETrF,
            ET_24, ETR24 + H-motori (dT, rah, u*, u200, L, z0m, rho, shamol, Tair)
  B guruh — kirish/yuza: SR bandlar, albedo(+5 usul), LST, emissivitet, NDVI/SAVI/LAI,
            K_DOWN/L_DOWN/L_UP/TAU_SW
Excelga saqlanadi (sahna sana+id bilan). Buzuq (ET=0) vs sog' sahnalar taqqoslanadi.
"""
import sys, time
sys.path.insert(0, r'D:/Cloud_comp/Sebal/scripts')
import ee, pandas as pd, numpy as np
from sebal_gee_v4 import main as sm, config as cfg
ee.Initialize(project='ee-chexovant11')
cfg.CROP_CLOUD_MAX = 100   # barcha P30/R36 overpass qolsin

CENTERS = {'NE': [-102.0955385, 35.18816985], 'SE': [-102.0955390, 35.18612583],
           'NW': [-102.0978919, 35.18817119], 'SW': [-102.0979121, 35.18613288]}
RES = r'D:/ET_2026/lyzimetr/25114670/result'
OUT = RES + '/instant_diag_bushland_2021.xlsx'
pts = ee.FeatureCollection([ee.Feature(ee.Geometry.Point(v), {'nuqta': k})
                            for k, v in CENTERS.items()])

anchor_roi = ee.Geometry.Point([-102.097, 35.187]).buffer(20000).bounds()
print("  process_tile (SEBAL_Milliy, ~40km box, barcha overpass)...", flush=True)
scenes, info = sm.process_tile(anchor_roi, '2021-03-01', '2021-11-01',
                               'SEBAL_Milliy', 'BOTH', 95, 'P30_R36',
                               anchor_method='cascade', utc_offset=-6)
print(f"  ✅ {len(scenes)} sahna", flush=True)

avail = ee.Image(scenes[0]).bandNames().getInfo()
print(f"  Sahnadagi BARCHA band ({len(avail)}): {avail}", flush=True)

# Guruhlar (mavjud bo'lganini olamiz)
A_BANDS = ['ET_INST_MM_HR', 'ETRF_INST', 'ET_24', 'ETR_INST', 'ETR24', 'SOLAR_FRAC',
           'LAMBDA_E', 'EVAP_FRAC', 'RN', 'G0', 'H', 'RN_G0', 'G_RATIO', 'RN24',
           'DTA', 'RAH', 'USTAR', 'U_200', 'L_MO', 'Z0M', 'Z0M_WIND', 'RHO_AIR',
           'SLOPE', 'WIND_SPEED_10M', 'AIR_TEMP']
B_BANDS = ['LST', 'ALBEDO', 'EMISSIVITY', 'NDVI', 'SAVI', 'LAI',
           'K_DOWN', 'L_DOWN', 'L_UP', 'TAU_SW',
           'ALB_OLMEDO', 'ALB_LIANG', 'ALB_KE', 'ALB_TASUMI', 'ALB_AVG3']
# SR (surface reflectance) bandlari — nomi qanday bo'lsa
SR = [b for b in avail if b.startswith('SR_') or b in
      ('BLUE', 'GREEN', 'RED', 'NIR', 'SWIR1', 'SWIR2', 'B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7')]
B_BANDS = SR + B_BANDS

allb = [b for b in (A_BANDS + B_BANDS) if b in avail]
missing = [b for b in (A_BANDS + B_BANDS) if b not in avail]
print(f"  Olinadi: {len(allb)} band | YO'Q: {missing}", flush=True)

rows = []
for i, sc in enumerate(scenes):
    sc = ee.Image(sc)
    t0 = time.time()
    date = ee.Date(sc.get('system:time_start')).format('YYYY-MM-dd').getInfo()
    sid = sc.get('system:index').getInfo()
    fc = sc.select(allb).reduceRegions(pts, ee.Reducer.first(), 30).getInfo()
    for f in fc['features']:
        p = f['properties']
        rows.append(dict(sana=date, sahna_id=sid, nuqta=p.get('nuqta'),
                         **{b: p.get(b) for b in allb}))
    print(f"    {i+1}/{len(scenes)} {date} ({time.time()-t0:.0f}s)", flush=True)

df = pd.DataFrame(rows)
# lizimetr instant
lys = pd.read_csv(RES + '/cmp_instant_pairs.csv').rename(
    columns={'lizimetr': 'nuqta', 'lizimetr_qiymat': 'lys_inst'})[['sana', 'nuqta', 'lys_inst']]
df = df.merge(lys, on=['sana', 'nuqta'], how='left')

META = ['sana', 'sahna_id', 'nuqta', 'lys_inst']
A_cols = META + [b for b in A_BANDS if b in df] + ['bias_%']
df['bias_%'] = np.where((df['lys_inst'] > 0), (df['ET_INST_MM_HR'] / df['lys_inst'] - 1) * 100, np.nan)
B_cols = META + [b for b in B_BANDS if b in df]

# Buzuq (ET=0) vs sog' — o'rtacha taqqoslash
df['buzuq'] = df['ET_INST_MM_HR'].fillna(-1) <= 0
diag = df.groupby('sana').agg(
    ET_inst=('ET_INST_MM_HR', 'mean'), lys=('lys_inst', 'mean'),
    RN=('RN', 'mean'), G0=('G0', 'mean'), H=('H', 'mean'),
    LST=('LST', 'mean'), ALBEDO=('ALBEDO', 'mean'), NDVI=('NDVI', 'mean'),
    K_DOWN=('K_DOWN', 'mean'), DTA=('DTA', 'mean'), RAH=('RAH', 'mean'),
    buzuq=('buzuq', 'first')).round(3)

with pd.ExcelWriter(OUT, engine='openpyxl') as xw:
    df[A_cols].round(4).to_excel(xw, 'A_energiya_LE_ET', index=False)
    df[B_cols].round(4).to_excel(xw, 'B_kirish_yuza', index=False)
    diag.to_excel(xw, 'buzuq_tahlil')
    df.round(4).to_excel(xw, 'HAMMASI', index=False)
print(f"\n  💾 Excel: {OUT}", flush=True)
print("\n  === BUZUQ (ET=0) vs SOG' — sahna kesimida ===")
print(diag.to_string())
