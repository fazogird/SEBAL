# -*- coding: utf-8 -*-
"""
T42SUJ (MGRS) — 2025-yil tasvirlari inventari Excel'ga: Landsat 8, Landsat 9, HLS L30, HLS S30, VIIRS, ECOSTRESS.
Faqat o'qish (GEE getInfo). Har tasvir: ID, o'tish vaqti (UTC / mahalliy quyosh / Toshkent),
metadata bulut % (butun sahna), tile qoplash %, tile bulut % (qoplangan qism ichida), tile ochiq %, ekin ochiq %.
Ishlatish: EE_PROJECT=ee-chexovant11 python inventory_2025_excel.py
"""
import ee, os, sys, datetime
import pandas as pd
import openpyxl.styles

sys.stdout.reconfigure(encoding='utf-8')
ee.Initialize(project=os.environ.get('EE_PROJECT', 'ee-chexovant11'))
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, 'T42SUJ_2025_tasvirlar.xlsx')
CRS = 'EPSG:32642'
TILE = ee.Geometry.Rectangle([300000, 4290240, 409800, 4400040], CRS, False)
A, B = '2025-01-01', '2026-01-01'
LON_C = 67.32                                   # tile markazi → mahalliy quyosh vaqti = UTC + lon/15
CROP = ee.ImageCollection('ESA/WorldCover/v200').first().select('Map').eq(40)
CROP_MEAN = CROP.reduceRegion(ee.Reducer.mean(), TILE, 300, crs=CRS).get('Map').getInfo()


def stats(img, cov, cld, clr, scale):
    # unmask(0, False): tasvir chegarasidan tashqarini ham 0 qiladi (sukut True — faqat footprint ichida, xato natija)
    st = ee.Image.cat([cov.unmask(0, False).rename('cov'), cld.And(cov).unmask(0, False).rename('cld'),
                       clr.unmask(0, False).rename('clr'), clr.unmask(0, False).multiply(CROP).rename('cc')])
    r = st.reduceRegion(ee.Reducer.mean(), TILE, scale, crs=CRS, maxPixels=1e9, tileScale=4)
    return ee.Feature(None, r).set('t', img.get('system:time_start'), 'id', img.get('system:index'))


def fetch(col, fn, props):
    fc = ee.FeatureCollection(col.map(fn))
    cols = ['id', 't', 'cov', 'cld', 'clr', 'cc'] + props
    return pd.DataFrame(fc.reduceColumns(ee.Reducer.toList(len(cols)), cols).get('list').getInfo(), columns=cols)


def landsat(sat):
    col = ee.ImageCollection(f'LANDSAT/{sat}/C02/T1_L2').filterBounds(TILE).filterDate(A, B)
    props = ['LANDSAT_PRODUCT_ID', 'WRS_PATH', 'WRS_ROW', 'CLOUD_COVER', 'CLOUD_COVER_LAND']

    def fn(i):
        qa = i.select('QA_PIXEL')
        cov = qa.bitwiseAnd(1).eq(0)                                  # fill emas
        cld = qa.bitwiseAnd(0b11110).neq(0)                           # dilated, cirrus, cloud, shadow
        clr = qa.bitwiseAnd(1 << 6).neq(0)
        return stats(i, cov, cld, clr, 300).copyProperties(i, props)
    return fetch(col, fn, props)


def hls(which):
    col = (ee.ImageCollection(f'NASA/HLS/HLS{which}/v002').filterBounds(TILE).filterDate(A, B)
           .filter(ee.Filter.stringStartsWith('system:index', 'T42SUJ')))
    props = ['CLOUD_COVERAGE', 'SPATIAL_COVERAGE', 'MEAN_VIEW_ZENITH_ANGLE', 'MEAN_SUN_ZENITH_ANGLE'] + \
            (['LANDSAT_PRODUCT_ID'] if which == 'L30' else [])

    def fn(i):
        fm = i.select('Fmask')
        cov = i.select('B4').mask().gt(0)
        cld = fm.bitwiseAnd(0b1110).neq(0)                            # cloud, adjacent, shadow
        clr = cov.And(fm.bitwiseAnd(0b11110).eq(0))                   # + qor/muz ham chiqariladi
        return stats(i, cov, cld, clr, 300).copyProperties(i, props)
    return fetch(col, fn, props)


def viirs():
    col = ee.ImageCollection('NASA/VIIRS/002/VNP21A1D').filterBounds(TILE).filterDate(A, B)

    def fn(i):
        q = i.select('QC').bitwiseAnd(3)
        cov = q.gte(0)
        good = q.eq(0)
        f = stats(i, cov, q.eq(2), good, 1000)
        m = (i.select(['View_Time', 'View_Angle']).updateMask(good)
             .reduceRegion(ee.Reducer.median(), TILE, 1000, crs=CRS, maxPixels=1e9))
        return f.set('vt', m.get('View_Time'), 'vza', m.get('View_Angle'))
    return fetch(col, fn, ['vt', 'vza'])


def times(df, vt=None):
    utc = pd.to_datetime(df.t, unit='ms')
    if vt is not None:                                                # VIIRS: kunlik mahsulot, vaqt View_Time'dan
        utc = utc.dt.normalize() + pd.to_timedelta(vt - LON_C / 15, unit='h')
    df.insert(1, 'sana', utc.dt.strftime('%Y-%m-%d'))
    df.insert(2, 'UTC', utc.dt.strftime('%H:%M'))
    df.insert(3, 'mahalliy_quyosh', (utc + pd.to_timedelta(LON_C / 15, unit='h')).dt.strftime('%H:%M'))
    df.insert(4, 'Toshkent_UTC5', (utc + pd.to_timedelta(5, unit='h')).dt.strftime('%H:%M'))
    return df.drop(columns='t')


def finish(df):
    df['tile_qoplash_%'] = (100 * df.pop('cov')).round(1)
    df['tile_bulut_%'] = (100 * df.pop('cld') / df['tile_qoplash_%'].div(100).where(lambda s: s > 0)).round(1)
    df['tile_ochiq_%'] = (100 * df.pop('clr')).round(1)
    df['ekin_ochiq_%'] = (100 * df.pop('cc') / CROP_MEAN).round(1).clip(upper=100)
    return df


sheets = {}
for sat, name in (('LC08', 'Landsat8'), ('LC09', 'Landsat9')):
    df = finish(times(landsat(sat)))
    df = df.rename(columns={'CLOUD_COVER': 'metadata_bulut_%_sahna', 'CLOUD_COVER_LAND': 'metadata_bulut_%_quruqlik'})
    sheets[name] = df.sort_values(['sana', 'WRS_ROW'])
    print(name, len(df), flush=True)
for which in ('L30', 'S30'):
    df = finish(times(hls(which))).rename(columns={'CLOUD_COVERAGE': 'metadata_bulut_%_tile',
                                                   'SPATIAL_COVERAGE': 'metadata_qoplash_%'})
    if which == 'L30':
        df.insert(5, 'sun_yoldosh', df.LANDSAT_PRODUCT_ID.str[:4].map({'LC08': 'Landsat 8', 'LC09': 'Landsat 9'}))
    sheets[f'HLS_{which}'] = df.sort_values('sana')
    print('HLS', which, len(df), flush=True)
v = viirs()
v = finish(times(v, vt=v.vt)).rename(columns={'vt': 'View_Time_mahalliy', 'vza': 'korish_burchagi_median',
                                              'tile_bulut_%': 'tile_bulut_%(QC)', 'tile_ochiq_%': 'tile_sifatli_%(QC=0)'})
v['VZA<=40'] = v.korish_burchagi_median.abs() <= 40
sheets['VIIRS'] = v.sort_values('sana')
print('VIIRS', len(v), flush=True)

e = pd.read_csv(os.path.join(HERE, 'eco_t42suj_analyzed.csv'), parse_dates=['utc'])
e = e[e.utc.dt.year == 2025].copy()
e = pd.DataFrame({'id': e.id, 'sana': e.utc.dt.strftime('%Y-%m-%d'), 'UTC': e.utc.dt.strftime('%H:%M'),
                  'mahalliy_quyosh': (e.utc + pd.to_timedelta(LON_C / 15, unit='h')).dt.strftime('%H:%M'),
                  'Toshkent_UTC5': (e.utc + pd.to_timedelta(5, unit='h')).dt.strftime('%H:%M'),
                  'sinf': e.cls, 'tile_qoplash_%': (100 * e['cov']).round(1), 'tile_bulut_%': (100 * e.cld).round(1),
                  'ekin_ochiq_%': e.crop_clr.round(1), 'korish_burchagi': e.view_zenith.round(1),
                  'LST_median_K': e.LST.round(1), 'SEBAL_uchun_yaroqli': e.usable})
sheets['ECOSTRESS'] = e.sort_values(['sana', 'UTC'])

# Xulosa: jami va foydali (ekin maydonining >=50% ochiq; VIIRS — yana ko'rish burchagi <=40°)
rows = []
for name, df in sheets.items():
    ok = df['ekin_ochiq_%'] >= 50
    if name == 'VIIRS':
        ok &= df['VZA<=40']
    if name == 'ECOSTRESS':
        ok = df['SEBAL_uchun_yaroqli'].astype(bool)
    m = pd.to_datetime(df.sana).dt.month
    r = {'sensor': name, 'jami_tasvir': len(df), 'tile_qoplash>=50%': int((df['tile_qoplash_%'] >= 50).sum()),
         'foydali': int(ok.sum())}
    r.update({f'{k:02d}-oy': int((ok & (m == k)).sum()) for k in range(1, 13)})
    rows.append(r)
summary = pd.DataFrame(rows)
notes = pd.DataFrame({'izoh': [
    'Tile: T42SUJ (MGRS, UTM 42N), 109.8 × 109.8 km. Yil: 2025.',
    "Vaqt: UTC; mahalliy quyosh = UTC + 4.49 soat (tile markazi 67.32°E); Toshkent = UTC + 5.",
    "metadata_bulut_% — provayder bergan qiymat: Landsat — butun WRS sahna; HLS — butun MGRS tile.",
    "tile_bulut_% — T42SUJ ichida, tasvir qoplagan qismdagi bulut/soya ulushi (Landsat QA_PIXEL, HLS Fmask).",
    "tile_ochiq_% — butun tile maydoniga nisbatan ochiq piksellar; ekin_ochiq_% — ekin maydonining (ESA WorldCover) ochiq ulushi.",
    "Landsat: har WRS sahna alohida qator (bir kunda bir nechta sahna tile'ni birga qoplashi mumkin).",
    "VIIRS: VNP21A1D (1 km, Suomi NPP) — kunlik o'rtacha; vaqt View_Time medianasidan; bulut = QC bitlari 0–1 = 2.",
    "ECOSTRESS: L2T LSTE V2; yaroqli = kunduz 9–17, ko'rish burchagi ≤25°, ekin maydonining ≥30% ochiq.",
    "Foydali (xulosada): ekin maydonining ≥50% ochiq; VIIRS uchun yana ko'rish burchagi ≤40°.",
    "Diqqat: HLS S30 2026-yil maydan GEE'da tile'ning ~4% ini qoplaydi (2025-yilga tegishli emas).",
]})
with pd.ExcelWriter(OUT, engine='openpyxl') as w:
    summary.to_excel(w, sheet_name='Xulosa', index=False)
    notes.to_excel(w, sheet_name='Xulosa', index=False, startrow=len(summary) + 3)
    for name, df in sheets.items():
        df.to_excel(w, sheet_name=name, index=False)
    for ws in w.book.worksheets:
        ws.freeze_panes = 'A2'
        for col in ws.columns:
            width = max(len(str(c.value)) if c.value is not None else 0 for c in col[:60])
            ws.column_dimensions[col[0].column_letter].width = min(max(10, width + 2), 48)
        for c in ws[1]:
            c.font = openpyxl.styles.Font(bold=True)
print('saqlandi:', OUT)
print(summary.to_string(index=False))
