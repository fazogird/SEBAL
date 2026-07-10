import ee
ee.Initialize(project='carbon-science-461016-q2')
from sebal_gee_v4 import ee_utils; ee_utils.install_getinfo_retry()
from sebal_gee_v4 import main as M
from sebal_gee_v4 import hls_s30_etrf as s30

roi = (ee.FeatureCollection('FAO/GAUL/2015/level1')
       .filter(ee.Filter.eq('ADM1_NAME', 'Kashkadarya')).geometry())
TILE = 'T41SPD'
START, END = '2026-05-01', '2026-05-31'

tg = M.get_hls_tile_geometry(TILE, START, END)
tile_roi = roi.intersection(tg, ee.ErrorMargin(30))
scenes, info = M.process_tile(tile_roi, START, END, 'pysebal', 'HLS', 70, TILE)
print('L30 anchorlar:', info['dates'])

# multi6 + per-pixel interp + cropland mask + diagnostika
monthly, diag = s30.build_tile_monthly_etrf_s30(
    scenes, info, tile_roi, START, END, 'multi6', 'lenient', 'linear',
    70, TILE, cropland_only=True)

print('--- DIAGNOSTIKA ---')
for d in diag:
    print(f"  {d['anchor_date']} → S30 {d['closest_s30']} (Δ{d['days_diff']}k) "
          f"R2={d['R2']} N={d['N']} used={d['used']}")

print('S30 oylik ET (ekin, mm/oy):', monthly.reduceRegion(
    ee.Reducer.minMax().combine(ee.Reducer.mean(), sharedInputs=True),
    tile_roi, 300, maxPixels=1e9, bestEffort=True, tileScale=8).getInfo())

# per-pixel interp tekshiruvi: between-day
print('=== TUGADI ===')
