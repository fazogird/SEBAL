"""
Sahna yig'uvchi (mode_process='LHLSVIIRSECO'): kalendar qabul qilgan kuzatuvdan SEBAL kirish tasviri.

Chiqish — mavjud pipeline kutgan standart bandlar: SR_B1..SR_B7 (reflektans), LST (K),
SZA/SAA, DEM/SLOPE, ERA5 (AIR_TEMP, PRESSURE, DEWPOINT, shamol, SSRD, STRD), RHO_AIR, WATER_MASK;
system:time_start — TERMAL kuzatuv vaqti (sahna sanasi va energiya balansi lahzasi).
  L — Landsat C2 L2: mavjud preprocessing zanjiri (QA, scale, L1 burchak, relyef, ERA5), bir
      kunlik qatorlar mozaikasi. LST keyin radiatsiyada SMW bilan (hozirgi yo'l bilan bir xil).
  V — VIIRS: kalendar tanlagan HLS (L30/S30, ±2 kun) optikasi + RF bilan 30 m LST (T-A pilot
      sozlamasi: VIIRS → UTM 1 km bilinear, RF global + EC, seed 7). Vaqt — VIIRS View_Time
      medianasi; quyosh burchaklari astronomik va ERA5 — SHU vaqtga (pilotda ERA5 Landsat vaqtida
      qolgan edi — sharpening/sebal_eco_vs_landsat.patch).
  E — ECOSTRESS: HLS optika + 70 m LST → 30 m bilinear. Vaqt — o'tish vaqti.
Optik parametrlar (NDVI, LAI, albedo, ...) HLS kunidan; HLS'ning o'z quyosh burchagi SZA_OPT
bandida saqlanadi (albedo sinovi uchun), SZA — termal vaqtdagi burchak.
"""
import datetime as dt

import ee

from .. import config as cfg
from .. import preprocessing as pp
from .downscale import sharpen_rf, BANDS as DMS_BANDS

SR_NAMES = ['SR_B1', 'SR_B2', 'SR_B3', 'SR_B4', 'SR_B5', 'SR_B6', 'SR_B7']
HLS_SR = {'L30': ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7'],
          'S30': ['B1', 'B2', 'B3', 'B4', 'B8A', 'B11', 'B12']}   # S30: B8A/B11/B12 → SR_B5/6/7
_HLS_BAD = (cfg.HLS_QA_BITMASK['cirrus'] | cfg.HLS_QA_BITMASK['cloud'] | cfg.HLS_QA_BITMASK['adjacent']
            | cfg.HLS_QA_BITMASK['cloud_shadow'] | cfg.HLS_QA_BITMASK['snow'])


def hls_optics(h):
    """HLS L30/S30 → SR_B1..SR_B7 (0.001–1.0, preprocessing.apply_scale_factors_hls kabi),
    WATER_MASK, SZA_OPT; bulut/soya/qo'shni/qor/sirrus maskalangan (apply_qa_mask_hls kabi)."""
    img = ee.Image(h['_refs'][0])
    fm = img.select('Fmask')
    sr = img.select(HLS_SR[h['sensor'][-3:]], SR_NAMES).clamp(0.001, 1.0)
    water = fm.bitwiseAnd(cfg.HLS_QA_BITMASK['water']).gt(0).rename('WATER_MASK')
    return (sr.addBands(water).addBands(img.select('SZA').rename('SZA_OPT'))
            .updateMask(fm.bitwiseAnd(_HLS_BAD).eq(0)))


def _finish(img, t0_ms, roi, props):
    """Termal vaqt → astronomik SZA/SAA, relyef, ERA5 (shu vaqtga), havo zichligi."""
    img = img.set('system:time_start', t0_ms).set({k: v for k, v in props.items() if v is not None})
    img = img.addBands(pp._astro_sun_angles(img))
    img = pp.add_terrain(img, roi)
    img = pp.get_era5_for_image(img, roi)
    return pp.add_air_density(img).set('SOLAR_GEOM_SOURCE', 'ASTRONOMIK')


def _optics_props(h, t_date):
    off = (dt.date.fromisoformat(h['sana']) - dt.date.fromisoformat(t_date)).days
    return {'OPTICAL_SENSOR': h['sensor'], 'OPTICAL_ID': h['id'],
            'OPTICAL_DATE': h['sana'], 'OPTICAL_OFFSET_DAYS': off}


def landsat_scene(o, roi):
    """Landsat C2 L2 — mavjud build_collection Landsat zanjiri, faqat kalendar tanlagan qatorlar."""
    nxt = (dt.date.fromisoformat(o['sana']) + dt.timedelta(days=1)).isoformat()
    l1 = pp.build_l1_angle_collection(roi, o['sana'], nxt, [o['sun_yoldosh']])

    def prep(ref):
        im = pp.apply_qa_mask(ee.Image(ref))
        im = pp.apply_scale_factors(im)
        im = pp.add_sun_angles(im, l1)
        im = pp.add_terrain(im, roi)
        im = pp.get_era5_for_image(im, roi)
        return pp.add_air_density(im)

    img = ee.Image(pp._mosaic_same_date(ee.ImageCollection([prep(r) for r in o['_refs']])).first())
    return img.set({'LST_SOURCE': 'LANDSAT', 'SCENE_KIND': 'L'})


def viirs_time_ms(v, tile):
    """VIIRS View_Time (mahalliy quyosh soati, tile medianasi) → UTC millisekund."""
    day0 = dt.datetime.fromisoformat(v['sana']).replace(tzinfo=dt.timezone.utc)
    return int((day0 + dt.timedelta(hours=v['View_Time'] - tile.lon / 15)).timestamp() * 1000)


def viirs_coarse_lst(tile, v, rules):
    """VIIRS LST 1 km — downscaling'dan OLDIN: toza piksellar (QC 0–1 va 4–5-bitlar 0, |VZA| ≤
    chegara), sinusoidal 927 m → tile'ning UTM 1 km gridiga bilinear (T-A pilot kabi)."""
    img = ee.Image(v['_refs'][0])
    qc = img.select('QC')
    good = (qc.bitwiseAnd(3).eq(0).And(qc.rightShift(4).bitwiseAnd(3).eq(0))
            .And(img.select('View_Angle').abs().lte(rules.viirs_vza_max)))
    return (img.select('LST_1KM').updateMask(good).rename('lst')
            .resample('bilinear').reproject(tile.proj(1000)))


def viirs_scene(tile, v, h, roi, rules):
    opt = hls_optics(h)
    lst_c = viirs_coarse_lst(tile, v, rules)
    lst = (sharpen_rf(opt.select(SR_NAMES[1:], DMS_BANDS), lst_c, tile.geometry,
                      tile.proj(30), tile.proj(1000), tile.proj(1000),
                      cv_threshold=rules.rf_cv_threshold, n_samples=rules.rf_samples,
                      seed=rules.rf_seed)
           .updateMask(lst_c.mask().gt(0)))
    props = {'LST_SOURCE': 'VIIRS', 'SCENE_KIND': 'V', 'VIIRS_ID': v['id'],
             'VIIRS_VZA_MEDIAN': v.get('VZA_median'), 'VIIRS_VIEW_TIME': v.get('View_Time'),
             **_optics_props(h, v['sana'])}
    return _finish(opt.addBands(lst), viirs_time_ms(v, tile), roi, props)


def ecostress_scene(tile, e, h, roi, rules):
    opt = hls_optics(h)
    ims = []
    for ref in e['_refs']:
        im = ee.Image(ref)
        ok = (im.select('cloud').eq(0).And(im.select('QC').bitwiseAnd(3).lte(1))
              .And(im.select('view_zenith').lte(rules.eco_vza_max)))
        ims.append(im.select('LST').updateMask(ok))
    p70 = ee.Image(e['_refs'][0]).select('LST').projection()
    lst = (ee.ImageCollection(ims).mosaic().setDefaultProjection(p70)
           .resample('bilinear').reproject(tile.proj(30)).rename('LST'))
    props = {'LST_SOURCE': 'ECOSTRESS', 'SCENE_KIND': 'E', 'ECOSTRESS_ID': e['id'],
             **_optics_props(h, e['sana'])}
    return _finish(opt.addBands(lst), e['_t0'], roi, props)


def build(kind, tile, o, h, roi, rules):
    if kind == 'L':
        return landsat_scene(o, roi)
    if kind == 'V':
        return viirs_scene(tile, o, h, roi, rules)
    if kind == 'E':
        return ecostress_scene(tile, o, h, roi, rules)
    raise ValueError(f"sahna turi: {kind!r}")
