"""
Anchor zonalari — Esri LULC, H3 (user qarori 2026-09-28; cfg.ANCHOR_H3).

  cold — Esri 5 (Crops) ulushi (ANCHOR_SCALE pikselida, 10 m dan reduceResolution);
  hot  — bosqichlar:
    H2 — Esri 5 ichida (metodlar hot'ni NDVI eng past → eng issiq qilib tanlaydi = yalang'och /
         bo'sh dala; CIMEC — Allen 2013, geeSEBAL — Laipelt 2021);
    H1 — Esri 8 (Bare ground) istisnolar bilan: balandlik tile ekin maydonlari oralig'ida
         (p5–p95 ± elev_margin_m), eng yaqin ekindan ≤ dist_max_km, albedo ≤ albedo_max
         (sahnaga bog'liq — energy_balance'da); qiyalik < 5° — umumiy anchor maskasida;
    aralash — ulush > 0 (AYNI sinflar) — bulutli kunlar zaxirasi (ROI emas).
  Hot uchun hech qachon: 7, 1, 2, 4, 9, 10, 11 — zonalar faqat 5 va 8 dan quriladi.
variant: 'H3' (H2 → H1), 'H2' (faqat ekin), 'H1' (faqat Esri 8) — solishtirish sinovi uchun.
geom — kalibratsiya hududi: tile ∩ viloyat (user, 2026-09-29: Qashqadaryo hisoblansa anchor ham
Qashqadaryo ekinidan — tile Samarqand/Buxoroni qoplasa ham anchor u yerga ketmasin). Ekin balandligi
oralig'i va nomzod sanog'i shu hududda; qidiruvning o'zi ham shu hudud (energy_balance'ga roi sifatida
beriladi). None → butun tile.
Qaytaradi (cold_zone, hot_zone) — energy_balance.select_anchor_pixels bosqichli dict'ni taniydi.
"""
import ee

from .. import config as cfg
from ..energy_balance import ANCHOR_SCALE


def _frac(img, proj):
    return img.toFloat().reduceResolution(ee.Reducer.mean(), maxPixels=1024).reproject(proj)


def h3_zones(tile, year, variant='H3', log=print, geom=None):
    p = cfg.ANCHOR_H3
    g = geom if geom is not None else tile.geometry
    proj = tile.proj(ANCHOR_SCALE)
    lulc = tile.lulc(year)
    crop = _frac(lulc.eq(p['crop_class']), proj).rename('COLD_FRAC')
    bare = _frac(lulc.eq(p['bare_class']), proj)

    dem = (ee.Image(cfg.DEM['collection']).select(cfg.DEM['band'])
           .reduceResolution(ee.Reducer.mean(), maxPixels=64).reproject(proj))
    lo_p, hi_p = p['crop_elev_pct']
    kw = dict(crs=tile.crs, crsTransform=tile.transform(ANCHOR_SCALE), maxPixels=1e10, tileScale=4)
    crop_px = crop.gte(0.5)
    dist_m = (crop_px.fastDistanceTransform(256, 'pixels', 'squared_euclidean').sqrt()
              .multiply(ANCHOR_SCALE).reproject(proj))
    q = ee.Dictionary({
        'elev': dem.updateMask(crop_px).reduceRegion(ee.Reducer.percentile([lo_p, hi_p]), g, **kw),
    }).getInfo()['elev']
    e_lo = q[f'elevation_p{lo_p}'] - p['elev_margin_m']
    e_hi = q[f'elevation_p{hi_p}'] + p['elev_margin_m']
    static_ok = dem.gte(e_lo).And(dem.lte(e_hi)).And(dist_m.lte(p['dist_max_km'] * 1000))
    h1 = bare.multiply(static_ok).rename('HOT_FRAC')

    stages = {'H3': [('H2', crop), ('H1', h1)], 'H2': [('H2', crop)], 'H1': [('H1', h1)]}[variant]
    hot_any = None
    for _, f in stages:
        hot_any = f.gt(0) if hot_any is None else hot_any.Or(f.gt(0))

    cnt = ee.Image.cat([crop.gte(t / 100).rename(f'c{t}') for t in (80, 60)]
                       + [h1.gte(t / 100).rename(f'h{t}') for t in (80, 60)]).reduceRegion(
        ee.Reducer.sum(), g, **kw).getInfo()
    ey = tile.esri_year(year)
    log(f"  Anchor zonalari — Esri {ey}, {variant}, {'tile ∩ hudud' if geom is not None else 'butun tile'} | ekin ulush px @{ANCHOR_SCALE}m ≥0.8: "
        f"{cnt['c80']:.0f} ≥0.6: {cnt['c60']:.0f} | Esri 8 (istisnolardan keyin) ≥0.8: "
        f"{cnt['h80']:.0f} ≥0.6: {cnt['h60']:.0f} | ekin balandligi p{lo_p}–p{hi_p}: "
        f"{e_lo + p['elev_margin_m']:.0f}–{e_hi - p['elev_margin_m']:.0f} m "
        f"(hot oralig'i {e_lo:.0f}–{e_hi:.0f} m, ekindan ≤ {p['dist_max_km']} km)")
    zones = {'scheme': 'staged', 'label': f'Esri {ey} {variant}', 'cold': crop,
             'stages': stages, 'albedo_max': {'H1': p['albedo_max']},
             'any': (crop.gt(0), hot_any), 'elev_range': (e_lo, e_hi)}
    return crop, zones
