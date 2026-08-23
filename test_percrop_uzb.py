# -*- coding: utf-8 -*-
"""Per-crop Kc SINOV — Samarqand: har ekin turi har xil ET berishini tekshirish."""
import sys
sys.path.insert(0, r'D:/Cloud_comp/Sebal/scripts')
import ee
from sebal_gee_v4 import ndvi_kc, crop_kc_table as ckt
ee.Initialize(project='ee-chexovant11')

CROP = 'projects/ee-chexovant11/assets/Samarqand_crop_30m'
region = ee.Geometry.Rectangle([66.85, 39.55, 67.00, 39.68])   # kichik Samarqand box
dem = ee.Image('USGS/SRTMGL1_003').rename('DEM')


def scenes():
    def ndvi(img):
        nir = img.select('SR_B5').multiply(0.0000275).add(-0.2)
        red = img.select('SR_B4').multiply(0.0000275).add(-0.2)
        return (nir.subtract(red).divide(nir.add(red)).rename('NDVI')
                .addBands(dem).copyProperties(img, ['system:time_start']))
    col = (ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
           .merge(ee.ImageCollection('LANDSAT/LC09/C02/T1_L2'))
           .filterBounds(region).filterDate('2024-04-01', '2024-11-01')
           .filter(ee.Filter.lt('CLOUD_COVER', 40)).map(ndvi))
    n = col.size().getInfo()
    lst = col.sort('system:time_start').toList(n)
    return [ee.Image(lst.get(i)) for i in range(n)], n


il, n = scenes()
print(f"  {n} ta Landsat sahna (Samarqand 2024)")
et = ndvi_kc.compute_monthly_et_kc(il, region, 2024, 7, utc_offset=5,
                                   etr24_source='era5', crop_assets=[CROP])
crop = ee.Image(CROP).rename('crop')
g = (et.rename('ET').addBands(crop).reduceRegion(
        ee.Reducer.mean().group(1, 'crop'), region, 30,
        maxPixels=1e9, bestEffort=True).getInfo())
name = {v['code']: k for k, v in ckt.CROP_KC.items()}
print("  === IYUL ET (mm/oy) har ekin bo'yicha (kcb_max bilan) ===")
for grp in sorted(g['groups'], key=lambda x: x['crop']):
    c = int(grp['crop']); et_v = grp['mean']
    if c == 0 or et_v is None:
        continue
    km = ckt.CROP_KC[name[c]]['kcb_max']
    print(f"    {c:2d} {name.get(c,'?'):10s}: ET={et_v:6.1f} mm  (kcb_max={km})")
