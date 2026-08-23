# -*- coding: utf-8 -*-
"""
Bushland AW/mavjud-suv — TEZ in-memory test (CSV/Drive'SIZ). 4 lizimetr parcelida
root_zone_water.compute_awnet ni to'g'ridan-to'g'ri getInfo bilan hisoblab, lizimetr
ET (+ keyin sug'orish/SWC) bilan solishtiradi. Paxta (crop_assets yo'q).
"""
import sys
sys.path.insert(0, r'D:/Cloud_comp/Sebal/scripts')
import numpy as np, pandas as pd, ee
from sebal_gee_v4 import main as sm, config as cfg, root_zone_water as rzw
ee.Initialize(project='ee-chexovant11')

# Paxta uchun: Zr≈1.4 m, p≈0.65 (FAO Table 22) — konfigga vaqtincha
cfg.CROP_ASSETS = None
cfg.CONSUMPTIVE_USE['root_depth'] = 1.4
cfg.CONSUMPTIVE_USE['depletion_frac'] = 0.65

CENTERS = {'NE': [-102.0955385, 35.18816985], 'SE': [-102.0955390, 35.18612583],
           'NW': [-102.0978919, 35.18817119], 'SW': [-102.0979121, 35.18613288]}
MN = {'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10}
RES = r'D:/ET_2026/lyzimetr/25114670/result'

fc = sm.parcels_from_points(CENTERS, size_m=210, inner_buffer_m=-30)
region = fc.geometry()
dem = ee.Image('USGS/SRTMGL1_003').rename('DEM')


def scenes():
    def nd(img):
        nir = img.select('SR_B5').multiply(0.0000275).add(-0.2)
        red = img.select('SR_B4').multiply(0.0000275).add(-0.2)
        return (nir.subtract(red).divide(nir.add(red)).rename('NDVI')
                .addBands(dem).copyProperties(img, ['system:time_start']))
    col = (ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
           .merge(ee.ImageCollection('LANDSAT/LC09/C02/T1_L2'))
           .filterBounds(region).filterDate('2021-01-01', '2022-01-01')
           .filter(ee.Filter.lt('CLOUD_COVER', 40)).map(nd))
    n = col.size().getInfo()
    return [ee.Image(col.sort('system:time_start').toList(n).get(i)) for i in range(n)]


il = scenes()
print(f"  {len(il)} sahna (Bushland 2021)")
rows = []
for mn, m in MN.items():
    # DEFAULT (production): start_at_raw → har oy MUSTAQIL, AW = oylik sug'orish talabi
    out = rzw.compute_awnet(il, region, 2021, m, utc_offset=-6,
                            etr24_source='gridmet')
    r = out.select(['ET_MONTHLY', 'AW', 'AVAILABLE_WATER', 'N_IRRIG', 'TAW']
                   ).reduceRegion(ee.Reducer.mean(), region, 30,
                                  maxPixels=1e9, bestEffort=True).getInfo()
    rows.append(dict(oy=mn, **{k: (round(v, 1) if v is not None else None)
                               for k, v in r.items()}))
df = pd.DataFrame(rows)

# lizimetr ET (oylik, o'rtacha 4 parcel)
lz = pd.read_csv(RES + '/cmp_monthly_pairs.csv').rename(columns={'oy': 'oy', 'lizimetr_mm': 'lys'})
lz_et = lz.groupby('oy')['lys'].mean().round(1)
df['lizimetr_ET'] = df['oy'].map(lz_et)
df['ET_bias'] = (df['ET_MONTHLY'] - df['lizimetr_ET']).round(1)

print("\n  === Bushland 2021 — bizning water-balans vs lizimetr ET ===")
print(df[['oy', 'ET_MONTHLY', 'lizimetr_ET', 'ET_bias', 'AW', 'AVAILABLE_WATER',
          'N_IRRIG', 'TAW']].to_string(index=False))
print(f"\n  Mavsumiy: ET={df['ET_MONTHLY'].sum():.0f}  AW={df['AW'].sum():.0f}  "
      f"lizimetr_ET={df['lizimetr_ET'].sum():.0f} mm")
print("  [i] Har oy RAW dan (mustaqil): AW = oylik sof sug'orish talabi (ET - eff.yomg'in).")
