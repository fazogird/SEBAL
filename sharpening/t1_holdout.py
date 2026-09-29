# -*- coding: utf-8 -*-
"""
T1 sinovi (hold-out, T42SUJ): "daraja Landsat'dan, o'zgarish VIIRS'dan".
t1 dagi Landsat-SEBAL + VIIRS o'zgarishi bilan t2 bashorat qilinadi va t2 dagi haqiqiy Landsat-SEBAL bilan solishtiriladi.

  P0 (hozirgi usul, eng yaqin sahna): SOLAR_FRAC(t1) o'zgarmas → ET_P0 = ET_L(t1) × RS24(t2) / RS24(t1)
  P1 (T1, optika t1 — ish sharoitiga yaqin): ET_P0 × R1,  R1 = F_V(t2 | optika t1) / F_V(t1)
  P2 (T1, optika t2 — eng qulay holat):      ET_P0 × R2,  R2 = F_V(t2 | optika t2) / F_V(t1)
F = SOLAR_FRAC (SEBAL_Milliy), F_V — VIIRS LST bilan SEBAL (1 km → 30 m bilinear; asset/eksport yo'q).
R — faqat ekin maydoni piksellaridan, 1 km da hisoblanadi va [0.25, 4] oralig'ida cheklanadi.
Hamma variantlar t1 va t2 dagi VIIRS yaroqli piksellari kesishmasida.
Ishlatish: EE_PROJECT=ee-chexovant11 python t1_holdout.py 2023-08-12 2023-08-28
"""
import ee, os, sys, datetime
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from selftest_lst import TILE, CRS, tf
from crosssensor_lst import viirs_lst, OFF_H
from sebal_eco_vs_landsat import run_variant, metrics

P1K = ee.Projection(CRS, tf(1000))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   f"t1_holdout{os.environ.get('OUT_SUFFIX', '')}.csv")
CROP = ee.ImageCollection('ESA/WorldCover/v200').first().select('Map').eq(40)


def viirs_t0(d, extra):
    vt = (extra['vt'].reduceRegion(ee.Reducer.median(), TILE, 1000, crs=CRS, bestEffort=True)
          .get('View_Time').getInfo())
    day0 = datetime.datetime.strptime(d, '%Y-%m-%d').replace(tzinfo=datetime.timezone.utc)
    return int((day0 + datetime.timedelta(hours=vt - OFF_H)).timestamp() * 1000), vt


def agg1k_crop(f):
    """SOLAR_FRAC ni faqat ekin piksellaridan 1 km ga o'rtachalash."""
    return f.updateMask(CROP).reduceResolution(ee.Reducer.mean(), maxPixels=4096).reproject(P1K)


def run_pair(t1, t2):
    v1, _, e1 = viirs_lst(t1)
    v2, _, e2 = viirs_lst(t2)
    both = v1.mask().And(v2.mask())
    v1m, v2m = v1.updateMask(both), v2.updateMask(both)
    t0_1, vt1 = viirs_t0(t1, e1)
    t0_2, vt2 = viirs_t0(t2, e2)
    print(f'\n######## JUFT {t1} → {t2} | VIIRS soati {vt1:.2f} / {vt2:.2f}', flush=True)
    print(f'######## {t1} LANDSAT', flush=True)
    L1 = run_variant(t1, v1m, t0_1, swap=False)
    print(f'######## {t2} LANDSAT (haqiqat)', flush=True)
    L2 = run_variant(t2, v2m, t0_2, swap=False)
    print(f'######## {t1} VIIRS (optika t1)', flush=True)
    V1 = run_variant(t1, v1m, t0_1, swap=True)
    print(f'######## {t2} VIIRS, optika t1', flush=True)
    V2p = run_variant(t1, v2m, t0_2, swap=True)
    print(f'######## {t2} VIIRS, optika t2', flush=True)
    V2o = run_variant(t2, v2m, t0_2, swap=True)
    if any(x is None for x in (L1, L2, V1, V2p, V2o)):
        print(f'{t1}→{t2}: variantlardan biri sahna bermadi — o\'tkazildi', flush=True)
        return

    f = lambda im: im.select('SOLAR_FRAC')
    den = agg1k_crop(f(V1)).max(1e-12)
    r1 = agg1k_crop(f(V2p)).divide(den).clamp(0.25, 4)
    r2 = agg1k_crop(f(V2o)).divide(den).clamp(0.25, 4)
    p0 = L1.select('ET_24').multiply(L2.select('RS24').divide(L1.select('RS24')))
    st = (L2.select('ET_24').rename('truth').addBands(p0.rename('P0'))
            .addBands(p0.multiply(r1).rename('P1')).addBands(p0.multiply(r2).rename('P2'))
            .addBands(L2.select('NDVI').rename('ndvi')).addBands(CROP.rename('crop'))
            .addBands(r1.rename('R1')).addBands(r2.rename('R2')))
    cols = ['truth', 'P0', 'P1', 'P2', 'ndvi', 'crop', 'R1', 'R2']
    proj = L2.select('ET_24').projection()
    pts = st.sample(region=TILE, projection=proj, numPixels=20000, seed=11, tileScale=8, geometries=False)
    df = pd.DataFrame(pts.reduceColumns(ee.Reducer.toList(len(cols)), cols).get('list').getInfo(), columns=cols)
    crop = df.crop == 1
    strata = {'ekin maydoni': crop, 'ekin, NDVI>0.6': crop & (df.ndvi > 0.6),
              'ekin, NDVI 0.3–0.6': crop & df.ndvi.between(0.3, 0.6), 'ekin, NDVI<0.3': crop & (df.ndvi < 0.3)}
    rows = []
    for q, m in strata.items():
        for p in ('P0', 'P1', 'P2'):
            r = dict(t1=t1, t2=t2, qatlam=q, bashorat=p)
            r.update(metrics(df.loc[m, 'truth'], df.loc[m, p])); rows.append(r)
    res = pd.DataFrame(rows).rename(columns={'landsat_orta': 'haqiqat_orta', 'eco_orta': 'bashorat_orta'})
    print(res.to_string(index=False), flush=True)
    print(f"R1 (ekin) median {df.loc[crop, 'R1'].median():.3f} | R2 median {df.loc[crop, 'R2'].median():.3f} | "
          f"haqiqiy F nisbati ET_L2/ET_P0 median {(df.loc[crop, 'truth'] / df.loc[crop, 'P0']).median():.3f}", flush=True)
    res.to_csv(OUT, mode='a', header=not os.path.exists(OUT), index=False, encoding='utf-8')


if __name__ == '__main__':
    a = sys.argv[1:]
    for t1, t2 in zip(a[0::2], a[1::2]):
        try:
            run_pair(t1, t2)
        except Exception as e:
            print(f'{t1}→{t2}: XATO — {type(e).__name__}: {str(e)[:400]}', flush=True)
    print('\nnatija ->', OUT)
