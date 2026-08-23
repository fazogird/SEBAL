# -*- coding: utf-8 -*-
"""
SEBAL_Milliy_Kc rejimini GEE'da UCHIDAN-UCHIGA sinash — to'liq SEBAL pipeline'siz.
Landsat NDVI sahnalaridan yangi ndvi_kc.compute_monthly_et_kc ni chaqirib,
Bushland 4 parcelda oylik ET → lizimetr bilan solishtiramiz (haqiqiy deploy holati:
CHIRPS yog'in-asosli Ke, sug'orish miqdori YO'Q).
"""
import sys
import numpy as np
import pandas as pd
import ee

sys.path.insert(0, r'D:/Cloud_comp/Sebal/scripts')
from sebal_gee_v4 import main as sebal_main
from sebal_gee_v4 import ndvi_kc

RES = r'D:/ET_2026/lyzimetr/25114670/result'
CENTERS = {'NE': [-102.0955385, 35.18816985], 'SE': [-102.0955390, 35.18612583],
           'NW': [-102.0978919, 35.18817119], 'SW': [-102.0979121, 35.18613288]}
MN = {'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6, 'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10}


def make_scenes(region):
    dem = ee.Image('USGS/SRTMGL1_003').rename('DEM')

    def to_ndvi(img):
        nir = img.select('SR_B5').multiply(0.0000275).add(-0.2)
        red = img.select('SR_B4').multiply(0.0000275).add(-0.2)
        ndvi = nir.subtract(red).divide(nir.add(red)).rename('NDVI')
        return (ndvi.addBands(dem)
                .copyProperties(img, ['system:time_start']))

    col = (ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
           .merge(ee.ImageCollection('LANDSAT/LC09/C02/T1_L2'))
           .filterBounds(region).filterDate('2021-01-01', '2022-01-01')
           .filter(ee.Filter.lt('CLOUD_COVER', 40)).map(to_ndvi))
    n = col.size().getInfo()
    lst = col.sort('system:time_start').toList(n)
    return [ee.Image(lst.get(i)) for i in range(n)], n


def main():
    ee.Initialize(project='ee-chexovant11')
    fc = sebal_main.parcels_from_points(CENTERS, size_m=210, inner_buffer_m=-30)
    region = fc.geometry()
    image_list, n = make_scenes(region)
    print(f"  ✅ {n} ta Landsat NDVI sahna (2021, cloud<40%)")

    rows = []
    for mon_name, m in MN.items():
        et = ndvi_kc.compute_monthly_et_kc(image_list, region, 2021, m,
                                           utc_offset=-6, etr24_source='gridmet')
        res = et.reduceRegions(fc, ee.Reducer.mean(), 30).getInfo()
        for ft in res['features']:
            v = ft['properties'].get('mean')
            rows.append({'month': mon_name, 'lys': ft['properties']['name'],
                         'pred': (float(v) if v is not None else np.nan)})
        print(f"  ✅ {mon_name}: "
              + "  ".join(f"{ft['properties']['name']}={ft['properties'].get('mean',0):.0f}"
                          for ft in res['features']))

    pred = pd.DataFrame(rows)
    # lizimetr oylik
    lys = pd.read_csv(RES + '/cmp_monthly_pairs.csv').rename(
        columns={'oy': 'month', 'lizimetr': 'lys', 'lizimetr_mm': 'obs'})
    df = pred.merge(lys[['month', 'lys', 'obs']], on=['month', 'lys'])
    d = df.dropna(); d = d[d['obs'] > 0]
    e = d['pred'].values - d['obs'].values
    r = np.corrcoef(d['pred'], d['obs'])[0, 1]
    print("\n  === SEBAL_Milliy_Kc (GEE, deploy: CHIRPS-only Ke) vs lizimetr ===")
    print(f"    n={len(d)}  R2={r*r:.3f}  MBE={e.mean():+.1f}  "
          f"MAE={np.abs(e).mean():.1f}  RMSE={np.sqrt((e**2).mean()):.1f}")
    print("    (taqqoslash — eski SEBAL_Milliy: R2=0.548 RMSE=45.6; "
          "offline proto: R2=0.85 RMSE=25.2)")
    g = df.groupby('month').agg(obs=('obs', 'mean'), pred=('pred', 'mean'))
    g['xato'] = (g['pred'] - g['obs']).round(1)
    g['mon_n'] = g.index.map(MN)
    print("\n  === OYMA-OY ===")
    print(g.sort_values('mon_n')[['obs', 'pred', 'xato']].round(1).to_string())
    df.to_csv(RES + '/openet/sebal_milliy_kc_GEE_oylik.csv', index=False,
              encoding='utf-8-sig')
    print(f"\n  💾 {RES}/openet/sebal_milliy_kc_GEE_oylik.csv")


if __name__ == '__main__':
    main()
