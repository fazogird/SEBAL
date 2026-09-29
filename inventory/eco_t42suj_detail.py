# ECOSTRESS L2T LSTE V2 — T42SUJ, 2018-07..2026-09: har tasvir (id, vaqt, qoplash, bulut, LST median, vz)
import ee, csv, os
ee.Initialize(project="carbon-science-461016-q2")
CRS = 'EPSG:32642'
TILE = ee.Geometry.Rectangle([300000, 4290240, 409800, 4400040], CRS, False)
CROP = ee.ImageCollection('ESA/WorldCover/v200').first().select('Map').eq(40)
col = (ee.ImageCollection('NASA/ECOSTRESS/L2T_LSTE/V2').filterBounds(TILE)
       .filterDate('2018-07-01', '2026-10-01')
       .filter(ee.Filter.stringEndsWith('system:index', '42SUJ')))

def f(img):
    cov = img.select('view_zenith').mask().gt(0).unmask(0)
    lstv = img.select('LST').mask().gt(0).unmask(0)
    cld = img.select('cloud').eq(1).unmask(0)
    clr = lstv.And(img.select('cloud').eq(0).unmask(0))
    st = ee.Image.cat([cov.rename('cov'), lstv.rename('lstv'), cld.rename('cld'),
                       clr.rename('clr'), clr.multiply(CROP).rename('cc'), CROP.rename('crop')])
    r = st.reduceRegion(ee.Reducer.mean(), TILE, 500, crs=CRS, maxPixels=1e9, tileScale=4)
    m = (img.select(['LST', 'view_zenith']).updateMask(clr)
         .reduceRegion(ee.Reducer.median(), TILE, 500, crs=CRS, maxPixels=1e9, tileScale=4))
    return ee.Feature(None, r).set(m).set({'id': img.get('system:index'), 't': img.get('system:time_start')})

fc = ee.FeatureCollection(col.map(f))
feats = fc.getInfo()['features']
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'eco_t42suj_detail.csv')
keys = ['id', 't', 'cov', 'lstv', 'cld', 'clr', 'cc', 'crop', 'LST', 'view_zenith']
with open(out, 'w', newline='', encoding='utf-8') as fh:
    w = csv.writer(fh); w.writerow(keys)
    for x in feats:
        p = x['properties']; w.writerow([p.get(k) for k in keys])
print(len(feats), 'tasvir ->', out)
