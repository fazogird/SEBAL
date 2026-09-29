# -*- coding: utf-8 -*-
"""
Sensorlararo LST sinovi (T42SUJ): haqiqiy ECOSTRESS / VIIRS LST vs o'sha kungi Landsat LST. Faqat GEE'dan o'qiydi.

Asos (haqiqat): Landsat 8/9 C2 L2 ST_B10, MGRS 30 m gridi.
Sensor LST o'z gridida olinadi va 30 m ga tushiriladi:
  asl        — bilinear (keskinlashtirishsiz)
  tsharp     — TsHARP (NDVI→fc, Kustas 2003 / Agam 2007)
  dms        — DMS (lokal + global RF), EC box = sensor pikseli
  dms_rf     — faqat global Random Forest, EC
  dms_lokal  — faqat lokal regressiya, EC
  dms_ecX    — DMS, kattalashtirilgan EC box (joylashuv siljishiga qarshi; Xue 2020)
Baholash uch masshtabda: sensorning o'z gridi (Landsat nurlanishda yig'iladi), 100 m, 30 m.
Metrikalar: n, MBE, RMSE, RMSEu (bias olib tashlangandagi xato), R².
MBE'ga o'tish vaqti farqi ham kiradi (Landsat ~10:40; VIIRS ~12:40–13:30; ECOSTRESS har xil).

Ishlatish: python crosssensor_lst.py eco 2024-04-08 [...]   |   python crosssensor_lst.py viirs 2023-07-11 [...]
"""
import ee, os, sys, datetime
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dms
from selftest_lst import CRS, TILE, tf, F30, truth_lst, hls_sr, next_day

OUT_TPL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'crosssensor_lst_{}.csv')
PF = ee.Projection(CRS, F30)
P100 = ee.Projection(CRS, tf(100))
OFF_H = 67.32 / 15.0                                   # mahalliy quyosh vaqti = UTC + lon/15


def eco_lst(d):
    """ECOSTRESS L2T (42SUJ), kunduzgi (9–17) tasvirlar; bir o'tishdagi sahnalar mozaikasi."""
    col = (ee.ImageCollection('NASA/ECOSTRESS/L2T_LSTE/V2').filterBounds(TILE)
           .filterDate(d, next_day(d)).filter(ee.Filter.stringEndsWith('system:index', '42SUJ')))
    info = col.aggregate_array('system:time_start').getInfo()
    keep = [t for t in info if 9 <= (datetime.datetime.utcfromtimestamp(t / 1000).hour
                                     + datetime.datetime.utcfromtimestamp(t / 1000).minute / 60 + OFF_H) % 24 <= 17]
    if not keep:
        return None, None, None
    t0 = min(keep)
    col = col.filter(ee.Filter.rangeContains('system:time_start', t0 - 300000, t0 + 300000))   # ±5 daqiqa
    proj = ee.Image(col.first()).select('LST').projection()

    def prep(i):
        ok = i.select('cloud').eq(0).And(i.select('QC').bitwiseAnd(3).lte(1))
        return i.select('LST').updateMask(ok).rename('lst')
    img = col.map(prep).mosaic().reproject(proj)
    vz = ee.Image(col.first()).select('view_zenith')
    hour = (datetime.datetime.utcfromtimestamp(t0 / 1000).hour
            + datetime.datetime.utcfromtimestamp(t0 / 1000).minute / 60 + OFF_H) % 24
    return img, proj, dict(sensor_soat=round(hour, 2), vz=vz, t0=t0)


def viirs_lst(d):
    """VNP21A1D LST_1KM, QC eng yaxshi sifat (bitlar 0–1 = 0).
    Sinusoidal gridi (927 m) MGRS'ga tekislangan UTM 1 km gridga bilinear bilan o'tkaziladi:
    30 m UTM → sinusoidal yig'ish GEE'da xotira/vaqt chegarasidan oshdi (2026-09-27).
    Bu kichik silliqlanish beradi (927 m → 1000 m) — natijada qayd etiladi."""
    col = ee.ImageCollection('NASA/VIIRS/002/VNP21A1D').filterDate(d, next_day(d))
    i = ee.Image(col.first())
    proj = ee.Projection(CRS, tf(1000))
    ok = i.select('QC').bitwiseAnd(3).eq(0)
    img = i.select('LST_1KM').updateMask(ok).rename('lst').resample('bilinear').reproject(proj)
    return img, proj, dict(vt=i.select('View_Time'), vz=i.select('View_Angle').abs())


def metrics(df, col, mask):
    e = (df.loc[mask, col] - df.loc[mask, 'truth']).dropna()
    if len(e) < 30:
        return dict(n=len(e))
    t = df.loc[e.index, 'truth']; p = df.loc[e.index, col]
    tm, pm = t.mean(), p.mean()
    r = float(((t - tm) * (p - pm)).sum() / (((t - tm) ** 2).sum() * ((p - pm) ** 2).sum()) ** 0.5)
    return dict(n=len(e), MBE=round(float(e.mean()), 2), RMSE=round(float((e ** 2).mean() ** 0.5), 2),
                RMSEu=round(float(e.std()), 2), R2=round(r * r, 3))


def sample_df(img, proj, cols):
    pts = img.sample(region=TILE, projection=proj, numPixels=20000, seed=11, tileScale=8, geometries=False)
    return pd.DataFrame(pts.reduceColumns(ee.Reducer.toList(len(cols)), cols).get('list').getInfo(), columns=cols)


def strata(df, frac):
    """frac=True: dag'al/100 m masshtab (lc, water — ulush); aks holda 30 m sinf."""
    land = (df.water < 0.5) if frac else (df.lc != 80)
    crop = land & ((df.lc >= 0.8) if frac else (df.lc == 40))
    return {'hammasi (quruqlik)': land, 'ekin maydoni': crop,
            'sovuq nomzod (ekin, NDVI>0.7)': crop & (df.ndvi > 0.7),
            'issiq nomzod (ekin, NDVI<0.2)': crop & (df.ndvi < 0.2)}


def run(sensor, d):
    truth, _ = truth_lst(d)
    sr, _ = hls_sr(d)
    lst_c, cproj, extra = (eco_lst(d) if sensor == 'eco' else viirs_lst(d))
    if lst_c is None:
        print(f'{d}: {sensor} kunduzgi tasvir yo\'q — o\'tkazildi', flush=True)
        return
    ec_big = cproj.scale(270 / 70.0, 270 / 70.0) if sensor == 'eco' else cproj.scale(2, 2)
    kr, cvt = (10, 0.15) if sensor == 'eco' else (5, 0.25)
    ndvi = sr.normalizedDifference(['nir', 'red']).rename('ndvi')
    wc = ee.ImageCollection('ESA/WorldCover/v200').first().select('Map').reproject(PF)

    meth = {'asl': lst_c.resample('bilinear').reproject(PF)}
    meth['tsharp'] = dms.tsharp(ndvi, lst_c, TILE, PF, cproj)
    sh = dms.sharpen(sr, lst_c, TILE, PF, cproj, cproj, kernel_radius=kr, cv_threshold=cvt)
    meth['dms'] = sh.select('lst')
    meth['dms_rf'] = sh.select('lst_global')
    meth['dms_lokal'] = sh.select('lst_local')
    meth['dms_ecX'] = dms.sharpen(sr, lst_c, TILE, PF, cproj, ec_big, kernel_radius=kr, cv_threshold=cvt).select('lst')
    names = list(meth)

    # Yordamchi ma'lumot: sensor soati / ko'rish burchagi (tile medianasi)
    if sensor == 'eco':
        s_hour = extra['sensor_soat']
        vz = extra['vz'].reduceRegion(ee.Reducer.median(), TILE, 500, crs=CRS, bestEffort=True).get('view_zenith').getInfo()
    else:
        med = (extra['vt'].addBands(extra['vz'])
               .reduceRegion(ee.Reducer.median(), TILE, 1000, crs=CRS, bestEffort=True).getInfo())
        s_hour, vz = med.get('View_Time'), med.get('View_Angle')
    print(f'\n=== {sensor.upper()} {d}: sensor soati {s_hour}, ko\'rish burchagi {vz}', flush=True)

    rows = []
    # 1) Sensorning o'z masshtabi: Landsat nurlanishda yig'iladi, sensor LST o'zi (downscalingsiz)
    red_c, nir_c = dms.aggregate(sr.select('red'), cproj), dms.aggregate(sr.select('nir'), cproj)
    st_c = (dms.aggregate_lst(truth, cproj).rename('truth').addBands(lst_c.rename('sensor'))
            .addBands(nir_c.subtract(red_c).divide(nir_c.add(red_c)).rename('ndvi'))
            .addBands(dms.aggregate(wc.eq(40).rename('lc'), cproj))
            .addBands(dms.aggregate(wc.eq(80).rename('water'), cproj)))
    df = sample_df(st_c, cproj, ['truth', 'sensor', 'ndvi', 'lc', 'water'])
    for q, m in strata(df, True).items():
        r = dict(sensor=sensor, sana=d, sensor_soat=s_hour, vz=vz, masshtab='sensor', qatlam=q, usul='sensor (downscalingsiz)')
        r.update(metrics(df, 'sensor', m)); rows.append(r)

    # 2) 100 m va 3) 30 m
    red100, nir100 = dms.aggregate(sr.select('red'), P100), dms.aggregate(sr.select('nir'), P100)
    st100 = (dms.aggregate_lst(truth, P100).rename('truth')
             .addBands(nir100.subtract(red100).divide(nir100.add(red100)).rename('ndvi'))
             .addBands(dms.aggregate(wc.eq(40).rename('lc'), P100))
             .addBands(dms.aggregate(wc.eq(80).rename('water'), P100)))
    st30 = truth.rename('truth').addBands(ndvi).addBands(wc.rename('lc'))
    for n in names:
        st100 = st100.addBands(dms.aggregate_lst(meth[n], P100).rename(n))
        st30 = st30.addBands(meth[n].rename(n))
    for scale, img, proj, frac in [('100 m', st100, P100, True), ('30 m', st30, PF, False)]:
        cols = ['truth', 'ndvi', 'lc'] + (['water'] if frac else []) + names
        df = sample_df(img, proj, cols)
        if not frac:
            df['water'] = 0.0
        for q, m in strata(df, frac).items():
            for n in names:
                r = dict(sensor=sensor, sana=d, sensor_soat=s_hour, vz=vz, masshtab=scale, qatlam=q, usul=n)
                r.update(metrics(df, n, m)); rows.append(r)
    res = pd.DataFrame(rows)
    show = res[res.qatlam.isin(['ekin maydoni', 'sovuq nomzod (ekin, NDVI>0.7)', 'issiq nomzod (ekin, NDVI<0.2)'])]
    print(show[['masshtab', 'qatlam', 'usul', 'n', 'MBE', 'RMSE', 'RMSEu', 'R2']].to_string(index=False), flush=True)
    out = OUT_TPL.format(sensor)
    res.to_csv(out, mode='a', header=not os.path.exists(out), index=False, encoding='utf-8')


if __name__ == '__main__':
    sensor = sys.argv[1]
    for d in sys.argv[2:]:
        try:
            run(sensor, d)
        except Exception as e:                                  # bitta kun butun yurishni buzmasin
            print(f'{sensor} {d}: XATO — {type(e).__name__}: {str(e)[:300]}', flush=True)
    print('\nnatija ->', OUT_TPL.format(sensor))
