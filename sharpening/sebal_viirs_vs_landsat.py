# -*- coding: utf-8 -*-
"""
SEBAL_Milliy bir kunda uch marta (T42SUJ): (L) Landsat LST, (VB) VIIRS 1 km → 30 m bilinear,
(VR) VIIRS RF bilan keskinlashtirilgan 30 m (asset, export_viirs_rf.py). Natijalar Landsat bilan solishtiriladi.

Pipeline fayllari O'ZGARMAYDI — sebal_eco_vs_landsat.py dagi kabi faqat shu jarayon ichida
build_collection / compute_lst_smw almashtiriladi. VIIRS varianti vaqti — tile bo'yicha View_Time medianasi;
quyosh burchaklari shu vaqtga astronomik. Uchala variant VIIRS yaroqli piksellarida hisoblanadi.
Ishlatish: python sebal_viirs_vs_landsat.py 2019-08-17 [...]
"""
import ee, os, sys, datetime
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from selftest_lst import TILE, CRS
from crosssensor_lst import viirs_lst, OFF_H
from sebal_eco_vs_landsat import run_variant, metrics, BANDS
from export_viirs_rf import asset_id, exists

# Parallel yurishlar uchun: OUT_SUFFIX=_a kabi (har jarayon o'z fayliga yozadi)
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   f"sebal_viirs_vs_landsat{os.environ.get('OUT_SUFFIX', '')}.csv")


def run(d):
    v1k, _, extra = viirs_lst(d)
    vt = extra['vt'].reduceRegion(ee.Reducer.median(), TILE, 1000, crs=CRS, bestEffort=True).get('View_Time').getInfo()
    day0 = datetime.datetime.strptime(d, '%Y-%m-%d').replace(tzinfo=datetime.timezone.utc)
    t0 = int((day0 + datetime.timedelta(hours=vt - OFF_H)).timestamp() * 1000)
    has_rf = exists(asset_id(d))          # RF asset tayyor bo'lsagina (GEE eksport navbati)
    print(f'\n######## {d} — VIIRS soati {vt:.2f} (mahalliy quyosh), UTC '
          f'{datetime.datetime.utcfromtimestamp(t0/1000):%H:%M} | RF asset: {"bor" if has_rf else "YO‘Q"}', flush=True)
    print(f'######## {d} — LANDSAT varianti (SMW LST)', flush=True)
    im_l = run_variant(d, v1k, t0, swap=False)
    ims = {'L': im_l}
    if not os.environ.get('SKIP_VB'):     # SKIP_VB=1: bilinear avval hisoblangan — kvotani tejash
        print(f'######## {d} — VIIRS BILINEAR varianti', flush=True)
        ims['VB'] = run_variant(d, v1k, t0, swap=True)
    if has_rf:
        print(f'######## {d} — VIIRS RF varianti', flush=True)
        vr = ee.Image(asset_id(d)).select('lst')
        ims['VR'] = run_variant(d, vr.updateMask(v1k.mask().gt(0)), t0, swap=True)
    if any(v is None for v in ims.values()):
        print(f'{d}: variantlardan biri sahna bermadi — solishtirilmaydi: '
              f'{[k for k, v in ims.items() if v is None]}', flush=True)
        return
    wc = ee.ImageCollection('ESA/WorldCover/v200').first().select('Map').rename('lc')
    proj = im_l.select('ET_24').projection()
    st = wc
    for k, im in ims.items():
        st = st.addBands(im.select(BANDS, [f'{k}_{b}' for b in BANDS]))
    cols = ['lc'] + [f'{k}_{b}' for k in ims for b in BANDS]
    pts = st.sample(region=TILE, projection=proj, numPixels=20000, seed=11, tileScale=8, geometries=False)
    df = pd.DataFrame(pts.reduceColumns(ee.Reducer.toList(len(cols)), cols).get('list').getInfo(), columns=cols)
    crop = df.lc == 40
    strata = {'ekin maydoni': crop,
              'ekin, NDVI>0.6': crop & (df.L_NDVI > 0.6),
              'ekin, NDVI 0.3–0.6': crop & df.L_NDVI.between(0.3, 0.6),
              'ekin, NDVI<0.3': crop & (df.L_NDVI < 0.3)}
    rows = []
    for v in [k for k in ims if k != 'L']:
        for q, m in strata.items():
            for b in ['ET_24', 'EVAP_FRAC', 'LST']:
                r = dict(sana=d, viirs_soat=round(vt, 2), variant=v, qatlam=q, kattalik=b)
                r.update(metrics(df.loc[m, f'L_{b}'], df.loc[m, f'{v}_{b}'])); rows.append(r)
    res = pd.DataFrame(rows).rename(columns={'eco_orta': 'viirs_orta'})
    print(res[res.kattalik != 'LST'].to_string(index=False), flush=True)
    res.to_csv(OUT, mode='a', header=not os.path.exists(OUT), index=False, encoding='utf-8')


if __name__ == '__main__':
    for d in sys.argv[1:]:
        try:
            run(d)
        except Exception as e:
            print(f'{d}: XATO — {type(e).__name__}: {str(e)[:400]}', flush=True)
    print('\nnatija ->', OUT)
