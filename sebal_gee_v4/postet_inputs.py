# -*- coding: utf-8 -*-
"""
Post-ET kirishlari — GEE'dan Drive'ga (gibrid arxitektura, 2026-10-05). Hisobning o'zi lokal: postet_engine/postet_run.
Sabab: uzluksiz suv yili bitta GEE grafida sig'maydi (180 kun → "User memory limit exceeded").

Har tile, har oy (kalendar oyi) ikkita fayl (samarali: bir xil gridli bandlar bitta faylda):
  POSTETIN_{tile}_{YYYY-MM}      — 30 m (tile gridi), Int16, nodata −32768:
        ET_YYYYMMDD  — termal kun ET_24 ×100 (mm·100), istalgan ET rejimi (SEBAL_B/ID/Milliy/pysebal, ko'p sensorli kun)
        EF_YYYYMMDD  — EVAP_FRAC ×10000 (HS yo'li uchun; bandi yo'q rejimda yozilmaydi — HS ishlamaydi)
        NDVI_YYYYMMDD — HLS L30+S30 NDVI ×10000 (Fmask 0–4 bitlar = 0; bir sanadagi granulalar o'rtachasi)
  POSTETIN_{tile}_MET_{YYYY-MM}  — dag'al (990 m = 33×30, tile gridiga tekis), Float32:
        ETO_YYYYMMDD — kunlik grass ETo (ERA5 soatlik yig'indi, daily_et.get_daily_etr24, mahalliy kun)
        P_YYYYMMDD   — CHIRPS kunlik yog'in (UTC kun)
Bir marta: POSTETIN_{tile}_SOIL — 240 m (8×30): HiHydroSoil v2 6 qatlam × (wcsat, wcres, alpha, N, ksat, wcpf4-2) xom,
        HSG, top_fc, top_wp, top_rew (water_balance.soil_fc_wp_rew — loyiha yagona manbai).
Spin-up yillari uchun scenes=None — faqat NDVI va MET (SEBAL ishlamaydi; lokal dvigatel model ET bilan yuradi).
Oraliq natija asset'ga YOZILMAYDI (user qarori).
"""
import datetime as dt

import ee

from . import config as cfg
from . import daily_et
from . import water_balance as wbm

INT_NODATA = -32768
HHS_VARS = ['wcsat', 'wcres', 'alpha', 'N', 'ksat', 'wcpf4-2']
HHS_LAYERS = ['0-5cm', '5-15cm', '15-30cm', '30-60cm', '60-100cm', '100-200cm']
HLS_IDS = {'L30': ('NASA/HLS/HLSL30/v002', 'B5', 'B4'), 'S30': ('NASA/HLS/HLSS30/v002', 'B8A', 'B4')}


def _months(date_start, date_end):
    d = dt.date.fromisoformat(date_start).replace(day=1)
    end = dt.date.fromisoformat(date_end)
    while d < end:
        nxt = (d.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
        yield d, nxt
        d = nxt


def _grid(tile, scale, crs):
    """Eksport gridi: MGRS tile bo'lsa tile gridiga tekis (crsTransform), aks holda crs + scale."""
    if tile is not None:
        return dict(crs=tile.crs, crsTransform=tile.transform(scale))
    return dict(crs=crs, scale=scale)


def _hls_ndvi(region, d0, d1):
    """HLS L30+S30 NDVI, har sana uchun bitta tasvir (granulalar o'rtachasi), Fmask 0–4 bitlar toza."""
    out = []
    for key, (cid, nir, red) in HLS_IDS.items():
        col = ee.ImageCollection(cid).filterBounds(region).filterDate(d0, d1)

        def f(im, nir=nir, red=red):
            clear = im.select('Fmask').bitwiseAnd(0b11111).eq(0)
            return (im.normalizedDifference([nir, red]).rename('NDVI').updateMask(clear)
                    .set('sana', im.date().format('YYYYMMdd')))
        out.append(col.map(f))
    col = out[0].merge(out[1])
    dates = sorted(set(col.aggregate_array('sana').getInfo()))
    return [(d, col.filter(ee.Filter.eq('sana', d)).mean().rename(f'NDVI_{d}')) for d in dates]


def _scaled(img, factor):
    return img.multiply(factor).round().clamp(INT_NODATA + 1, 32767).unmask(INT_NODATA, False).toInt16()


def export_soil(region, tile_label, *, folder, tile=None, crs=None, scale=240):
    bands = [wbm._hhs_layer(v, l).rename(f'{v}|{l}') for v in HHS_VARS for l in HHS_LAYERS]
    hsg = ee.Image('projects/sat-io/open-datasets/HiHydroSoilv2_0/Hydrologic_Soil_Group_250m').select(0).rename('HSG')
    fc, wp, rew = wbm.soil_fc_wp_rew()
    img = ee.Image.cat(bands + [hsg, fc.rename('top_fc'), wp.rename('top_wp'), rew.rename('top_rew')]).toFloat()
    name = f'POSTETIN_{tile_label}_SOIL'
    t = ee.batch.Export.image.toDrive(image=img.clip(region), description=name, folder=folder, fileNamePrefix=name,
                                      region=region, maxPixels=1e13, fileFormat='GeoTIFF', **_grid(tile, scale, crs))
    t.start()
    print(f'  ✅ {name}')
    return [t]


def export_tile_inputs(region, tile_label, date_start, date_end, *, folder, scenes=None, dates=None, tile=None,
                       crs=None, scale=30, coarse_scale=990, utc_offset=0, with_soil=True, log=print):
    """scenes/dates — process_tile natijasi (termal kunlar; dates[i] = 'YYYY-MM-DD' scenes[i] bilan mos).
    scenes=None — spin-up: faqat NDVI va MET. Qaytaradi: ee.batch.Task ro'yxati."""
    tasks = []
    dem = ee.Image(cfg.DEM['collection']).select(cfg.DEM['band'])
    by_month = {}
    for d, img in zip(dates or [], scenes or []):
        by_month.setdefault(d[:7], []).append((d.replace('-', ''), img))
    ef_ok = None
    for m0, m1 in _months(date_start, date_end):
        key = f'{m0:%Y-%m}'
        bands = []
        for dkey, img in by_month.get(key, []):
            bands.append(_scaled(ee.Image(img).select('ET_24'), 100).rename(f'ET_{dkey}'))
            if ef_ok is None:
                ef_ok = 'EVAP_FRAC' in ee.Image(img).bandNames().getInfo()
                if not ef_ok:
                    log(f"  ⚠️ {tile_label}: EVAP_FRAC bandi yo'q — HS (Hydrosat) yo'li bu rejimda ishlamaydi")
            if ef_ok:
                bands.append(_scaled(ee.Image(img).select('EVAP_FRAC'), 10000).rename(f'EF_{dkey}'))
        for dkey, nd in _hls_ndvi(region, str(m0), str(m1)):
            bands.append(_scaled(nd, 10000).rename(f'NDVI_{dkey}'))
        if bands:
            name = f'POSTETIN_{tile_label}_{key}'
            t = ee.batch.Export.image.toDrive(
                image=ee.Image.cat(bands).clip(region), description=name, folder=folder, fileNamePrefix=name,
                region=region, maxPixels=1e13, fileFormat='GeoTIFF', formatOptions={'noData': INT_NODATA},
                **_grid(tile, scale, crs))
            t.start()
            tasks.append(t)
            log(f'  ✅ {name}: {len(bands)} band')
        # MET (dag'al): kunlik ETo va yog'in
        met = []
        d = m0
        while d < m1:
            day = ee.Date(str(d))
            eto = daily_et.get_daily_etr24(day, region, dem, ref_type='grass', utc_offset=utc_offset, source='era5')
            p = ee.Image(ee.ImageCollection(wbm.CHIRPS).filterDate(day, day.advance(1, 'day')).first()) \
                .select('precipitation')
            met += [eto.rename(f'ETO_{d:%Y%m%d}').toFloat(), p.rename(f'P_{d:%Y%m%d}').toFloat()]
            d += dt.timedelta(days=1)
        name = f'POSTETIN_{tile_label}_MET_{key}'
        t = ee.batch.Export.image.toDrive(
            image=ee.Image.cat(met).clip(region.buffer(coarse_scale * 2)), description=name, folder=folder,
            fileNamePrefix=name, region=region.buffer(coarse_scale * 2), maxPixels=1e13, fileFormat='GeoTIFF',
            **_grid(tile, coarse_scale, crs))
        t.start()
        tasks.append(t)
        log(f'  ✅ {name}: {len(met)} band')
    if with_soil:
        tasks += export_soil(region.buffer(500), tile_label, folder=folder, tile=tile, crs=crs)
    return tasks
