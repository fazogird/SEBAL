# -*- coding: utf-8 -*-
"""
"Landsat o'zini-o'zi tekshirish" — LST keskinlashtirish sinovi (T42SUJ, MGRS 30 m). Faqat GEE'dan o'qiydi.

Haqiqat: Landsat C2 L2 ST_B10 (K), MGRS 30 m gridiga bilinear.
Simulyatsiya: haqiqat nurlanish fazosida 70 m (ECOSTRESS gridi) va 1 km (VIIRS o'rniga) ga yig'iladi.
Keskinlashtirish: dms.sharpen, prediktor — o'sha kungi HLS L30.
Taqqoslash: keskinlashtirishsiz (dag'al → 30 m bilinear) va DMS variantlari.

Ishlatish: python selftest_lst.py 2023-07-11 [2023-08-12 ...]
"""
import ee, os, sys, datetime
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dms

ee.Initialize(project=os.environ.get('EE_PROJECT', 'carbon-science-461016-q2'))
sys.stdout.reconfigure(encoding='utf-8')

CRS = 'EPSG:32642'
X0, Y0 = 300000, 4400040                                   # T42SUJ (HLS/ECOSTRESS gridi bilan bir xil)
TILE = ee.Geometry.Rectangle([300000, 4290240, 409800, 4400040], CRS, False)
tf = lambda r: [r, 0, X0, 0, -r, Y0]
F30 = tf(30)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'selftest_lst_results.csv')

SENSORS = {                        # dag'al piksel, EC box variantlari, lokal oyna radiusi, CV chegarasi
    'ECO70':  dict(res=70,   ecs=[70, 270],    k=10, cv=0.15),
    'VII1km': dict(res=1000, ecs=[1000, 2000], k=5,  cv=0.25),
}


def next_day(d):
    return (datetime.date.fromisoformat(d) + datetime.timedelta(days=1)).isoformat()


def truth_lst(d):
    col = (ee.ImageCollection('LANDSAT/LC08/C02/T1_L2').merge(ee.ImageCollection('LANDSAT/LC09/C02/T1_L2'))
           .filterBounds(TILE).filterDate(d, next_day(d)))

    def prep(i):
        st = i.select('ST_B10').multiply(0.00341802).add(149.0)
        ok = i.select('QA_PIXEL').bitwiseAnd(1 << 6).neq(0).And(i.select('ST_B10').gt(0))
        return st.updateMask(ok).rename('lst').resample('bilinear')
    return col.map(prep).mosaic().reproject(crs=CRS, crsTransform=F30), col.size()


def hls_sr(d):
    col = (ee.ImageCollection('NASA/HLS/HLSL30/v002').filterBounds(TILE).filterDate(d, next_day(d))
           .filter(ee.Filter.stringStartsWith('system:index', 'T42SUJ')))
    i = ee.Image(col.first())
    ok = i.select('Fmask').bitwiseAnd(0b1110).eq(0)
    sr = i.select(['B2', 'B3', 'B4', 'B5', 'B6', 'B7'], dms.BANDS).updateMask(ok)
    return sr.reproject(crs=CRS, crsTransform=F30), col.size()


def metrics(df, col, mask):
    e = (df.loc[mask, col] - df.loc[mask, 'truth']).dropna()
    t = df.loc[e.index, 'truth']; p = df.loc[e.index, col]
    if len(e) < 30:
        return dict(n=len(e))
    tm, pm = t.mean(), p.mean()
    cc = float(((t - tm) * (p - pm)).sum() / (((t - tm) ** 2).sum() * ((p - pm) ** 2).sum()) ** 0.5)
    return dict(n=len(e), bias=round(float(e.mean()), 2), rmse=round(float((e ** 2).mean() ** 0.5), 2),
                sd_err=round(float(e.std()), 2), cc=round(cc, 3))


def run(d):
    truth, n_l = truth_lst(d)
    sr, n_h = hls_sr(d)
    print(f'\n=== {d}: Landsat sahna {n_l.getInfo()}, HLS L30 {n_h.getInfo()}', flush=True)
    wc = ee.ImageCollection('ESA/WorldCover/v200').first().select('Map')
    ndvi = sr.normalizedDifference(['nir', 'red']).rename('ndvi')
    stack = truth.rename('truth').addBands(ndvi).addBands(wc.rename('lc').reproject(crs=CRS, crsTransform=F30))
    names = []
    for s, p in SENSORS.items():
        coarse = dms.aggregate_lst(truth, ee.Projection(CRS, tf(p["res"])))
        base = coarse.resample('bilinear').reproject(crs=CRS, crsTransform=F30)
        stack = stack.addBands(base.rename(f'{s}_asl'))
        names.append(f'{s}_asl')
        for ec in p['ecs']:
            sh = dms.sharpen(sr, coarse, TILE, ee.Projection(CRS, F30), ee.Projection(CRS, tf(p["res"])), ee.Projection(CRS, tf(ec)),
                             kernel_radius=p['k'], cv_threshold=p['cv'])
            stack = stack.addBands(sh.select('lst').rename(f'{s}_dms_ec{ec}'))
            names.append(f'{s}_dms_ec{ec}')
    cols = ['truth', 'ndvi', 'lc'] + names
    # 100 m baholash: Landsat termalining asl aniqligi va SEBAL anchor masshtabi (ANCHOR_SCALE=100).
    # Hamma LST nurlanish fazosida 100 m ga yig'iladi; NDVI — yig'ilgan reflektansdan; lc — ekin ulushi.
    T100 = tf(100)
    red100 = dms.aggregate(sr.select("red"), ee.Projection(CRS, T100))
    nir100 = dms.aggregate(sr.select("nir"), ee.Projection(CRS, T100))
    st100 = (dms.aggregate_lst(truth, ee.Projection(CRS, T100)).rename('truth')
             .addBands(nir100.subtract(red100).divide(nir100.add(red100)).rename('ndvi'))
             .addBands(dms.aggregate(wc.eq(40).rename('lc').reproject(crs=CRS, crsTransform=F30), ee.Projection(CRS, T100)))
             .addBands(dms.aggregate(wc.eq(80).rename('water').reproject(crs=CRS, crsTransform=F30), ee.Projection(CRS, T100))))
    for c in names:
        st100 = st100.addBands(dms.aggregate_lst(stack.select(c), ee.Projection(CRS, T100)).rename(c))
    res_all = []
    for scale, img, proj in [(30, stack, F30), (100, st100, T100)]:
        cc = cols if scale == 30 else cols + ['water']
        pts = img.sample(region=TILE, projection=ee.Projection(CRS, proj), numPixels=20000,
                         seed=11, tileScale=8, geometries=False)
        lists = pts.reduceColumns(ee.Reducer.toList(len(cc)), cc).get('list').getInfo()  # 5000 cheklovisiz
        df = pd.DataFrame(lists, columns=cc)
        if scale == 30:
            land = df.lc != 80
            crop = land & (df.lc == 40)
        else:                                           # 100 m: lc = ekin ulushi, water = suv ulushi
            land = df.water < 0.5
            crop = land & (df.lc >= 0.8)                # toza ekin pikseli
        strata = {
            'hammasi (quruqlik)': land,
            'ekin maydoni': crop,
            'sovuq nomzod (ekin, NDVI>0.7)': crop & (df.ndvi > 0.7),
            'issiq nomzod (NDVI<0.2)': land & (df.ndvi < 0.2),
        }
        for st, m in strata.items():
            for c in names:
                r = dict(sana=d, masshtab_m=scale, qatlam=st, variant=c); r.update(metrics(df, c, m))
                res_all.append(r)
    res = pd.DataFrame(res_all)
    print(res.to_string(index=False), flush=True)
    res.to_csv(OUT, mode='a', header=not os.path.exists(OUT), index=False, encoding='utf-8')


if __name__ == '__main__':
    for d in sys.argv[1:]:
        run(d)
    print('\nnatija ->', OUT)
