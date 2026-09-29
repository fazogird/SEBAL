"""
Qashqadaryo MGRS tile'lari — maydon va qoplash tahlili ("Satellite data revolution", kirish bosqichi).

1) 8 ta MGRS tile kvadrati (HLS S30 granulasi proyeksiyasidan): UTM zona, yuqori-chap burchak.
2) Tile'lar orasidagi ustma-ust tushish (ayniqsa UTM 41/42 zona chegarasida).
3) Har tile: Qashqadaryo (GAUL 2015) ichidagi ulushi, ekin maydoni (ESA WorldCover 2021, sinf 40).
4) 2025 HLS L30 (Landsat 8/9 → MGRS) va S30 metadata: WRS path / orbita bo'yicha tile qoplami.
5) Har (tile, path): path tile ekin maydonining necha foizini qoplaydi
   (shu path'ning eng katta qoplamli L30 granulasi footprint'i bo'yicha).
6) Esri 10 m LULC GEE community katalogida bormi.

Faqat metadata + 100 m reduceRegion — kvota sarfi juda kichik.
Ishga tushirish: gee_env python, EE_PROJECT (sukut ee-chexovant11).
"""
import os
import re
import time

import ee
import pandas as pd

ee.Initialize(project=os.environ.get('EE_PROJECT', 'ee-chexovant11'))

TILES = ['T41SPC', 'T41SPD', 'T41SQC', 'T41SQD', 'T42STH', 'T42STJ', 'T42SUH', 'T42SUJ']
SIDE = 109800.0
A, B = '2025-01-01', '2026-01-01'
OUT = os.path.dirname(os.path.abspath(__file__))
KM2 = 1e6

REGION = (ee.FeatureCollection('FAO/GAUL/2015/level1')
          .filter(ee.Filter.eq('ADM1_NAME', 'Kashkadarya')).geometry())
CROP = ee.ImageCollection('ESA/WorldCover/v200').first().select('Map').eq(40).rename('crop')
CROP_AREA = CROP.multiply(ee.Image.pixelArea())
L30 = ee.ImageCollection('NASA/HLS/HLSL30/v002')
S30 = ee.ImageCollection('NASA/HLS/HLSS30/v002')


def hls_tile(col, t):
    # filterBounds + nom filtri (S30 filterBounds antimeridian xatosi — nom bo'yicha qo'shimcha filtr)
    return col.filterBounds(REGION).filter(ee.Filter.stringStartsWith('system:index', t))


def crop_km2(geom, crs):
    return CROP_AREA.reduceRegion(ee.Reducer.sum(), geom, 100, crs=crs,
                                  maxPixels=1e10, tileScale=4).get('crop')


# ---- 1) tile kvadratlari ----
projs = ee.List([ee.Image(hls_tile(S30, t).filterDate(A, B).first()).select('B4').projection()
                 for t in TILES]).getInfo()
SQ = {}
for t, p in zip(TILES, projs):
    x0, y0 = p['transform'][2], p['transform'][5]
    SQ[t] = {'crs': p['crs'], 'x0': x0, 'y0': y0,
             'geom': ee.Geometry.Rectangle([x0, y0 - SIDE, x0 + SIDE, y0], p['crs'], False)}
print('Tile kvadratlari (yuqori-chap burchak):')
for t in TILES:
    print(f"  {t}: {SQ[t]['crs']}  x0={SQ[t]['x0']:.0f}  y0={SQ[t]['y0']:.0f}")

# ---- 2) va 3) ustma-ust tushish, hudud ulushi, ekin ----
em = ee.ErrorMargin(50)
per = []
for t in TILES:
    g = SQ[t]['geom']
    gr = g.intersection(REGION, ee.ErrorMargin(100))
    per.append(ee.Dictionary({
        't': t, 'area': g.area(50), 'in_region': gr.area(100),
        'crop_tile': crop_km2(g, SQ[t]['crs']), 'crop_region': crop_km2(gr, SQ[t]['crs'])}))
pairs = []
for i in range(len(TILES)):
    for j in range(i + 1, len(TILES)):
        a, b = TILES[i], TILES[j]
        pairs.append(ee.Dictionary({'a': a, 'b': b, 'ov': SQ[a]['geom'].intersection(
            SQ[b]['geom'], em).area(50)}))
res = ee.Dictionary({'per': ee.List(per), 'pairs': ee.List(pairs)}).getInfo()

tile_rows = []
for d in res['per']:
    tile_rows.append({'tile': d['t'], 'maydon_km2': d['area'] / KM2,
                      'hudud_ichida_%': 100 * d['in_region'] / d['area'],
                      'ekin_tile_km2': (d['crop_tile'] or 0) / KM2,
                      'ekin_tile_%': 100 * (d['crop_tile'] or 0) / d['area'],
                      'ekin_hudud_ichida_km2': (d['crop_region'] or 0) / KM2})
tdf = pd.DataFrame(tile_rows)
print('\nTile — maydon, Qashqadaryo ichidagi ulush, ekin (WorldCover 2021):')
print(tdf.round(1).to_string(index=False))

print("\nUstma-ust tushish (tile maydonining %; faqat > 1%):")
for d in res['pairs']:
    pct = 100 * d['ov'] / (SIDE * SIDE)
    if pct > 1:
        print(f"  {d['a']} ∩ {d['b']}: {d['ov'] / KM2:.0f} km² ({pct:.0f}%)")

# ---- 4) HLS metadata 2025 ----
def meta(col, t, props):
    cols = ['system:index', 'system:time_start'] + props
    return hls_tile(col, t).filterDate(A, B).reduceColumns(
        ee.Reducer.toList(len(cols)), cols).get('list')


ml = ee.Dictionary({
    'L30': ee.Dictionary({t: meta(L30, t, ['SPATIAL_COVERAGE', 'CLOUD_COVERAGE', 'LANDSAT_PRODUCT_ID'])
                          for t in TILES}),
    'S30': ee.Dictionary({t: meta(S30, t, ['SPATIAL_COVERAGE', 'CLOUD_COVERAGE']) for t in TILES}),
}).getInfo()

rows = []
for sensor in ('L30', 'S30'):
    for t in TILES:
        for r in ml[sensor][t]:
            gid, ts, cov, cld = r[0], r[1], r[2], r[3]
            utc = pd.to_datetime(ts, unit='ms')
            if sensor == 'L30':
                m = re.search(r'_(\d{3})(\d{3})_', r[4] or '')
                grp = f"path {m.group(1)}" if m else 'path ?'
                sat = (r[4] or '')[:4]
            else:
                grp = f"orbita {utc.strftime('%H:%M')[:4]}0"   # o'tish vaqti (10 daqiqa aniqlikda)
                sat = 'S2'
            rows.append({'sensor': sensor, 'tile': t, 'id': gid, 'sana': utc.strftime('%Y-%m-%d'),
                         'UTC': utc.strftime('%H:%M'), 'guruh': grp, 'sun_yoldosh': sat,
                         'qoplash_%': cov, 'bulut_%': cld})
hdf = pd.DataFrame(rows)
hdf.to_csv(os.path.join(OUT, 'qashqadaryo_hls_2025.csv'), index=False, encoding='utf-8-sig')

# ---- 5) har (tile, path): ekin maydonining qoplami ----
l30 = hdf[hdf.sensor == 'L30']
rep = l30.loc[l30.groupby(['tile', 'guruh'])['qoplash_%'].idxmax()]
cc = []
for _, r in rep.iterrows():   # har biri alohida getInfo — bittada "Too many concurrent aggregations"
    t = r['tile']
    img = ee.Image(hls_tile(L30, t).filterDate(A, B).filter(
        ee.Filter.eq('system:index', r['id'])).first())
    fp = img.select('B4').mask().gt(0).unmask(0, False)
    v = CROP_AREA.updateMask(fp).reduceRegion(ee.Reducer.sum(), SQ[t]['geom'], 100,
                                              crs=SQ[t]['crs'], maxPixels=1e10,
                                              tileScale=4).get('crop')
    for k in range(4):
        try:
            cc.append(ee.Number(v).getInfo())
            break
        except ee.EEException as e:
            if 'concurrent' not in str(e) or k == 3:
                raise
            time.sleep(15)
crop_tile = dict(zip(tdf.tile, tdf.ekin_tile_km2))
rep = rep.assign(ekin_qoplash_pct=[100 * (v or 0) / KM2 / crop_tile[t] if crop_tile[t] else None
                                   for v, t in zip(cc, rep.tile)])

summ = []
for (sensor, t, g), d in hdf.groupby(['sensor', 'tile', 'guruh']):
    s = {'sensor': sensor, 'tile': t, 'guruh': g, 'n_2025': len(d),
         'qoplash_median_%': d['qoplash_%'].median(),
         'qoplash_min_%': d['qoplash_%'].min(), 'qoplash_max_%': d['qoplash_%'].max()}
    if sensor == 'L30':
        m = rep[(rep.tile == t) & (rep.guruh == g)]
        s['ekin_qoplash_%'] = float(m.ekin_qoplash_pct.iloc[0]) if len(m) else None
    summ.append(s)
sdf = pd.DataFrame(summ)
sdf.to_csv(os.path.join(OUT, 'qashqadaryo_tiles_qoplash.csv'), index=False, encoding='utf-8-sig')
tdf.to_csv(os.path.join(OUT, 'qashqadaryo_tiles.csv'), index=False, encoding='utf-8-sig')

print('\nHLS 2025 — har tile uchun path / orbita qoplami (metadata SPATIAL_COVERAGE):')
print(sdf.round(1).to_string(index=False))

print('\nL30 sana bo\'yicha qoplash taqsimoti (2025):')
for t in TILES:
    d = l30[l30.tile == t]['qoplash_%']
    print(f"  {t}: jami {len(d)} | ≥90%: {(d >= 90).sum()} | 50–89%: {((d >= 50) & (d < 90)).sum()} "
          f"| <50%: {(d < 50).sum()}")

# ---- 6) Esri LULC ----
try:
    esri = ee.ImageCollection('projects/sat-io/open-datasets/landcover/ESRI_Global-LULC_10m_TS')
    ei = ee.Dictionary({
        'n': esri.size(),
        'years': esri.filterBounds(REGION).aggregate_array('system:time_start')
        .map(lambda x: ee.Date(x).format('YYYY')).distinct().sort(),
    }).getInfo()
    print(f"\nEsri 10 m LULC (sat-io): {ei['n']} tasvir; Qashqadaryo yillari: {ei['years']}")
except Exception as e:  # katalog yo'q yoki ruxsat yo'q
    print(f"\nEsri LULC tekshiruvi: {type(e).__name__}: {e}")
