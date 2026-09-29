# -*- coding: utf-8 -*-
"""
SEBAL_Milliy bir kunda ikki marta: (1) Landsat LST bilan, (2) ECOSTRESS LST bilan — natijalar solishtiriladi (T42SUJ).

Pipeline fayllari O'ZGARMAYDI. Faqat shu skript ichida (ishlash paytida) ikki funksiya almashtiriladi:
  preprocessing.build_collection — ECOSTRESS variantida Landsat tasviriga ECOSTRESS LST'si,
                                   ECOSTRESS o'tish vaqti va o'sha vaqtdagi quyosh burchaklari (astronomik) qo'yiladi;
                                   ikkala variantda tasvir ECOSTRESS yaroqli joyi bilan masklanadi (bir xil piksellar).
  radiation.compute_lst_smw     — ECOSTRESS variantida LST'ni qayta yozmaydi (Landsat variantida — SMW, odatdagidek).
Optik kiritmalar (albedo, NDVI, LAI, emissivlik) — o'sha kungi Landsat'dan; meteorologiya (ERA5) — o'z o'tish vaqtida.

Ishlatish: python sebal_eco_vs_landsat.py 2024-04-08 [2020-08-03 ...]
"""
import ee, os, sys
import pandas as pd

sys.path.insert(0, r'D:\Cloud_comp\Sebal\scripts')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sebal_gee_v4 import main, preprocessing, radiation, config as cfg
from selftest_lst import TILE, next_day
from crosssensor_lst import eco_lst

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sebal_eco_vs_landsat.csv')
_orig_build = preprocessing.build_collection
_orig_smw = radiation.compute_lst_smw
BANDS = ['ET_24', 'SOLAR_FRAC', 'EVAP_FRAC', 'LST', 'NDVI']


def patch(eco_img, t0, swap):
    """swap=False: Landsat varianti (faqat maska). swap=True: ECOSTRESS varianti."""
    valid = eco_img.mask().gt(0)

    def build(*a, **k):
        col = _orig_build(*a, **k)

        def f(im):
            im = ee.Image(im)
            proj = im.select(cfg.BAND_NAMES['red']).projection()
            m = valid.reproject(proj)
            if swap:
                im = im.set('system:time_start', t0)
                ang = preprocessing._astro_sun_angles(im)
                lst = eco_img.resample('bilinear').reproject(proj).rename('LST')
                im = (im.addBands(ang, overwrite=True).addBands(lst, overwrite=True)
                        .set('SOLAR_GEOM_SOURCE', 'ASTRONOMIK'))
            return im.updateMask(m)
        return col.map(f)

    preprocessing.build_collection = build
    radiation.compute_lst_smw = (lambda image: image) if swap else _orig_smw


def run_variant(d, eco_img, t0, swap):
    patch(eco_img, t0, swap)
    try:
        scenes, info = main.process_tile(TILE, d, next_day(d), 'SEBAL_Milliy', 'BOTH', 70,
                                         tile_label='', anchor_method='cimec',
                                         anchor_mode='median_anchor', utc_offset=None)
    finally:
        preprocessing.build_collection = _orig_build
        radiation.compute_lst_smw = _orig_smw
    if not scenes:
        return None
    return ee.Image(scenes[0])


def metrics(a, b):
    e = (b - a).dropna()
    if len(e) < 30:
        return dict(n=len(e))
    a, b = a[e.index], b[e.index]
    am, bm = a.mean(), b.mean()
    r = float(((a - am) * (b - bm)).sum() / (((a - am) ** 2).sum() * ((b - bm) ** 2).sum()) ** 0.5)
    return dict(n=len(e), landsat_orta=round(float(am), 3), eco_orta=round(float(bm), 3),
                MBE=round(float(e.mean()), 3), MBE_pct=round(100 * float(e.mean()) / float(am), 1) if am else None,
                RMSE=round(float((e ** 2).mean() ** 0.5), 3), R2=round(r * r, 3))


def run(d):
    eco_img, _, extra = eco_lst(d)
    if eco_img is None:
        print(f'{d}: ECOSTRESS kunduzgi tasvir yo\'q', flush=True)
        return
    t0 = extra['t0']
    print(f'\n######## {d} — LANDSAT varianti (SMW LST)', flush=True)
    im_l = run_variant(d, eco_img, t0, swap=False)
    print(f'\n######## {d} — ECOSTRESS varianti (ECOSTRESS LST, soat {extra["sensor_soat"]})', flush=True)
    im_e = run_variant(d, eco_img, t0, swap=True)
    if im_l is None or im_e is None:
        print(f'{d}: variantlardan biri sahna bermadi (anchor rad etilgan) — solishtirilmaydi', flush=True)
        return
    wc = ee.ImageCollection('ESA/WorldCover/v200').first().select('Map').rename('lc')
    proj = im_l.select('ET_24').projection()
    st = (im_l.select(BANDS, [f'L_{b}' for b in BANDS])
          .addBands(im_e.select(BANDS, [f'E_{b}' for b in BANDS])).addBands(wc))
    cols = [f'L_{b}' for b in BANDS] + [f'E_{b}' for b in BANDS] + ['lc']
    pts = st.sample(region=TILE, projection=proj, numPixels=20000, seed=11, tileScale=8, geometries=False)
    df = pd.DataFrame(pts.reduceColumns(ee.Reducer.toList(len(cols)), cols).get('list').getInfo(), columns=cols)
    crop = df.lc == 40
    strata = {'ekin maydoni': crop,
              'ekin, NDVI>0.6': crop & (df.L_NDVI > 0.6),
              'ekin, NDVI 0.3–0.6': crop & df.L_NDVI.between(0.3, 0.6),
              'ekin, NDVI<0.3': crop & (df.L_NDVI < 0.3)}
    rows = []
    for q, m in strata.items():
        for b in ['ET_24', 'SOLAR_FRAC', 'EVAP_FRAC', 'LST']:
            r = dict(sana=d, eco_soat=extra['sensor_soat'], qatlam=q, kattalik=b)
            r.update(metrics(df.loc[m, f'L_{b}'], df.loc[m, f'E_{b}'])); rows.append(r)
    res = pd.DataFrame(rows)
    print(res.to_string(index=False), flush=True)
    res.to_csv(OUT, mode='a', header=not os.path.exists(OUT), index=False, encoding='utf-8')


if __name__ == '__main__':
    for d in sys.argv[1:]:
        try:
            run(d)
        except Exception as e:
            print(f'{d}: XATO — {type(e).__name__}: {str(e)[:400]}', flush=True)
    print('\nnatija ->', OUT)
