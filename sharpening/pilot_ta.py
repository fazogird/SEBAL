# -*- coding: utf-8 -*-
"""
T-A pilot (T42SUJ): bir kunlik Landsat–VIIRS juftlaridan VIIRS ET darajasini kalibrlash uchun to'plam.
Pipeline fayllari O'ZGARMAYDI (sebal_eco_vs_landsat.run_variant — faqat shu jarayon ichida almashtirish).

Har kun uchun:
  L — Landsat-SEBAL_Milliy (SMW LST), odatdagidek;
  V — VIIRS-SEBAL_Milliy: LST = RF bilan keskinlashtirilgan VIIRS (asset, export_viirs_rf.py),
      vaqt/ERA5/quyosh burchaklari — VIIRS vaqtida, optika — o'sha kungi Landsat.
Ikkala variant VIIRS yaroqli piksellarida. Hamma kunlar BIR XIL nuqtalar to'plamida namunalanadi
(ekin maydoni, 5000 nuqta, qat'iy seed) — kunlararo solishtirish (P3) uchun.

Chiqish: pilot_ta_samples{OUT_SUFFIX}.csv — har nuqta × kun:
  sana, doy, yil, vz, vtime, pid, lon, lat, L_*/V_* (ET_24, SOLAR_FRAC, RS24, ETRF_RAW, ETR24, NDVI, LST)
Ishlatish: EE_PROJECT=ee-chexovant11 EE_ASSET_FOLDER=projects/ee-chexovant11/assets/sebal_sharpening_test \
           python pilot_ta.py 2019-08-17 [...]
"""
import ee, os, sys, datetime
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from selftest_lst import TILE, CRS
from crosssensor_lst import viirs_lst
from sebal_eco_vs_landsat import run_variant
from export_viirs_rf import asset_id
from t1_holdout import viirs_t0

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   f"pilot_ta_samples{os.environ.get('OUT_SUFFIX', '')}.csv")
BANDS = ['ET_24', 'SOLAR_FRAC', 'RS24', 'ETRF_RAW', 'ETR24', 'NDVI', 'LST']
CROP = ee.ImageCollection('ESA/WorldCover/v200').first().select('Map').eq(40)


def points():
    """Ekin maydonidan 5000 ta qat'iy nuqta (har jarayonda bir xil — seed=42)."""
    pts = CROP.selfMask().rename('crop').stratifiedSample(
        numPoints=5000, classBand='crop', region=TILE, scale=30, projection=CRS,
        seed=42, geometries=True, tileScale=4)

    def add(f):
        c = f.geometry().transform('EPSG:4326', 1).coordinates()
        return f.set({'pid': f.id(), 'lon': c.get(0), 'lat': c.get(1)})
    return pts.map(add)


def run_date(d, pts):
    v1k, _, extra = viirs_lst(d)
    t0, vt = viirs_t0(d, extra)
    vz = (extra['vz'].reduceRegion(ee.Reducer.median(), TILE, 1000, crs=CRS, bestEffort=True)
          .get('View_Angle').getInfo())
    print(f'\n######## {d} — VIIRS soati {vt:.2f}, ko\'rish burchagi {vz}', flush=True)
    print(f'######## {d} — LANDSAT', flush=True)
    L = run_variant(d, v1k, t0, swap=False)
    print(f'######## {d} — VIIRS RF', flush=True)
    vr = ee.Image(asset_id(d)).select('lst').updateMask(v1k.mask().gt(0))
    V = run_variant(d, vr, t0, swap=True)
    if L is None or V is None:
        print(f'{d}: variantlardan biri sahna bermadi — o\'tkazildi', flush=True)
        return
    st = (L.select(BANDS, [f'L_{b}' for b in BANDS])
           .addBands(V.select(BANDS, [f'V_{b}' for b in BANDS])))
    fc = st.reduceRegions(collection=pts, reducer=ee.Reducer.first(), scale=30, crs=CRS, tileScale=8)
    cols = ['pid', 'lon', 'lat'] + [f'L_{b}' for b in BANDS] + [f'V_{b}' for b in BANDS]
    rows = fc.reduceColumns(ee.Reducer.toList(len(cols)), cols).get('list').getInfo()
    df = pd.DataFrame(rows, columns=cols)
    dt = datetime.date.fromisoformat(d)
    df.insert(0, 'vtime', round(vt, 2)); df.insert(0, 'vz', vz)
    df.insert(0, 'doy', dt.timetuple().tm_yday); df.insert(0, 'yil', dt.year); df.insert(0, 'sana', d)
    ok = df[['L_ET_24', 'V_ET_24']].notna().all(axis=1)
    print(f'{d}: {int(ok.sum())} nuqta (ikkala ET bor) | median ET_L {df.loc[ok, "L_ET_24"].median():.2f}, '
          f'ET_V {df.loc[ok, "V_ET_24"].median():.2f}, median(ET_L/ET_V) '
          f'{(df.loc[ok, "L_ET_24"] / df.loc[ok, "V_ET_24"]).median():.3f}', flush=True)
    df.to_csv(OUT, mode='a', header=not os.path.exists(OUT), index=False, encoding='utf-8')


if __name__ == '__main__':
    pts = points()
    for d in sys.argv[1:]:
        try:
            run_date(d, pts)
        except Exception as e:
            print(f'{d}: XATO — {type(e).__name__}: {str(e)[:400]}', flush=True)
    print('\nnatija ->', OUT)
