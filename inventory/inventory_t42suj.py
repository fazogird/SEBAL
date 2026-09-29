# -*- coding: utf-8 -*-
"""T42SUJ (MGRS) ma'lumot inventarizatsiyasi — FAQAT O'QISH (GEE getInfo).
Har kuzatuv: sensor, sana/vaqt (mahalliy quyosh), tile qoplashi %, bulutsiz %,
ekin maydonidagi bulutsiz % (ESA WorldCover 40), ko'rish burchagi.
Ishlatish: python inventory_t42suj.py 2023 [2024 ...]  -> inventory_T42SUJ.csv ga qo'shadi."""
import ee, sys, os, csv, datetime
ee.Initialize(project="carbon-science-461016-q2")

CRS = 'EPSG:32642'
TILE = ee.Geometry.Rectangle([300000, 4290240, 409800, 4400040], CRS, False)  # HLS T42SUJ transformidan
SC, SCV = 500, 1000                     # fraksiya hisobi masshtabi (Landsat/HLS/ECO; VIIRS)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'inventory_T42SUJ.csv')
LON_C = TILE.centroid(1).coordinates().get(0).getInfo()
OFF = LON_C / 15.0                       # mahalliy quyosh vaqti ~ UTC + lon/15
CROP = ee.ImageCollection('ESA/WorldCover/v200').first().select('Map').eq(40)

def crop_mean(scale):
    return CROP.reduceRegion(ee.Reducer.mean(), TILE, scale, crs=CRS, maxPixels=1e9).get('Map').getInfo()
CM, CMV = crop_mean(SC), crop_mean(SCV)

def feat(img, cov01, clr01, scale, extra=None):
    st = ee.Image.cat([cov01.unmask(0).rename('cov'), clr01.unmask(0).rename('clr'),
                       clr01.unmask(0).multiply(CROP).rename('cc')])
    r = st.reduceRegion(ee.Reducer.mean(), TILE, scale, crs=CRS, maxPixels=1e9, tileScale=4)
    f = ee.Feature(None, r).set('t', img.get('system:time_start'))
    if extra is not None:
        e = extra.reduceRegion(ee.Reducer.median(), TILE, scale, crs=CRS, maxPixels=1e9, tileScale=4)
        f = f.set(e)
    return f

def by_day(col, fn):
    days = col.aggregate_array('system:time_start').map(
        lambda t: ee.Date(t).format('YYYY-MM-dd')).distinct()
    def one(d):
        d0 = ee.Date.parse('YYYY-MM-dd', d)
        m = col.filterDate(d0, d0.advance(1, 'day'))
        img = m.mosaic().set('system:time_start', m.first().get('system:time_start'), 'n', m.size())
        return fn(img).set('n', m.size())
    return ee.FeatureCollection(days.map(one))

def landsat(img):
    st = img.select('ST_B10')
    cov = st.gt(0)
    clr = cov.And(img.select('QA_PIXEL').bitwiseAnd(1 << 6).neq(0))
    return feat(img, cov, clr, SC)

def hls(img):
    b = img.select('B4').mask().gt(0)
    clr = b.And(img.select('Fmask').bitwiseAnd(0b1110).eq(0))
    return feat(img, b, clr, SC)

def eco(img):
    cov = img.select('view_zenith').mask().gt(0)
    clr = img.select('LST').mask().gt(0).And(img.select('cloud').eq(0))
    vz = img.select('view_zenith').updateMask(clr).rename('vz')
    return feat(img, cov, clr, SC, vz)

def viirs(img):
    clr = img.select('LST_1KM').mask().gt(0)
    ex = ee.Image.cat([img.select('View_Angle').abs().rename('vz'),
                       img.select('View_Time').rename('vt')]).updateMask(clr)
    return feat(img, clr, clr, SCV, ex)

def collections(y):
    a, b = f'{y}-01-01', f'{y + 1}-01-01'
    L = (ee.ImageCollection('LANDSAT/LC08/C02/T1_L2').merge(ee.ImageCollection('LANDSAT/LC09/C02/T1_L2'))
         .filterBounds(TILE).filterDate(a, b))
    HL = (ee.ImageCollection('NASA/HLS/HLSL30/v002').filterBounds(TILE).filterDate(a, b)
          .filter(ee.Filter.stringStartsWith('system:index', 'T42SUJ')))
    HS = (ee.ImageCollection('NASA/HLS/HLSS30/v002').filterBounds(TILE).filterDate(a, b)
          .filter(ee.Filter.stringStartsWith('system:index', 'T42SUJ')))
    E = (ee.ImageCollection('NASA/ECOSTRESS/L2T_LSTE/V2').filterBounds(TILE).filterDate(a, b)
         .filter(ee.Filter.stringEndsWith('system:index', '42SUJ')))
    V = ee.ImageCollection('NASA/VIIRS/002/VNP21A1D').filterBounds(TILE).filterDate(a, b)
    return [('LANDSAT', by_day(L, landsat), CM), ('HLS_L30', by_day(HL, hls), CM),
            ('HLS_S30', by_day(HS, hls), CM), ('ECOSTRESS', E.map(eco), CM),
            ('VIIRS', V.map(viirs), CMV)]

cols = ['sensor', 'year', 'date_local', 'time_local', 'n_img', 'cov_pct', 'clear_pct', 'crop_clear_pct', 'vz_med', 'viirs_time']
new = not os.path.exists(OUT)
with open(OUT, 'a', newline='', encoding='utf-8') as fh:
    w = csv.writer(fh)
    if new:
        w.writerow(cols)
    for y in [int(a) for a in sys.argv[1:]]:
        for name, fc, cm in collections(y):
            feats = fc.getInfo()['features']
            k = 0
            for f in feats:
                p = f['properties']
                if p.get('t') is None:
                    continue
                loc = datetime.datetime.utcfromtimestamp(p['t'] / 1000) + datetime.timedelta(hours=OFF)
                cc = 100 * p.get('cc', 0) / cm if cm else None
                w.writerow([name, y, loc.strftime('%Y-%m-%d'), loc.strftime('%H:%M'), p.get('n', 1),
                            round(100 * p.get('cov', 0), 1), round(100 * p.get('clr', 0), 1),
                            None if cc is None else round(cc, 1),
                            None if p.get('vz') is None else round(p['vz'], 1),
                            None if p.get('vt') is None else round(p['vt'], 2)])
                k += 1
            fh.flush()
            print(f'{y} {name}: {k} kuzatuv', flush=True)
print('crop ulushi tile ichida:', round(100 * CM, 1), '% ; tayyor ->', OUT)
