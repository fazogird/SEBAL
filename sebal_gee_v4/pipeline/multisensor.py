"""
Ko'p sensorli yo'l — mode_process='LHLSVIIRSECO' (main.process_tile shu yerga yo'naltiradi).
Bitta MGRS tile uchun (roi — butun tile, anchor hududi):

  1. Kalendar (calendar.TileCalendar) — kelishilgan qoidalar bo'yicha qaysi kun qaysi sensor
     qabul qilinadi; VIIRS / ECOSTRESS kuni HLS optika bilan juftlangan (piksel ikkalasida toza).
     Excel nusxasi: inventory/<tile>_kalendar_<boshi>_<oxiri>.xlsx.
  2. Sahna yig'uvchi (scenes.build) → surface_props → radiatsiya (Landsat bo'lmasa SMW
     o'tkaziladi: LST tayyor) → main.process_scene (hozirgi yo'l bilan AYNI anchor/EB/kunlik ET).
  3. Sensorlararo daraja: har sahnada ET_24_RAW (+ SOLAR_FRAC_RAW / ETRF_INST_RAW / EVAP_FRAC_RAW);
     VIIRS'da ET_24 = k·xom (rules.viirs_k = 1, user qarori 2026-10-02), ECOSTRESS'da rules.eco_k.
  4. Kunlik birlashma: bir kunda bir nechta sahna → piksel bo'yicha Landsat > ECOSTRESS > VIIRS;
     SOURCE bandi (1 Landsat, 2 ECOSTRESS, 3 VIIRS). Oylik hisob keyin mavjud yo'l bilan
     (eng yaqin sahna, SOLAR_FRAC × Rs24); termal kuzatuvsiz kunlar uchun suv balansi — keyin.
"""
import collections
import datetime as dt
import os

import ee

from .. import config as cfg
from .. import energy_balance, radiation, surface_props
from . import anchor_zones, scenes
from .calendar import TileCalendar, SCRIPTS
from .rules import InputRules

KIND_CODE = {'L': 1, 'E': 2, 'V': 3}
PRIORITY = 'LEV'          # piksel bo'yicha ustuvorlik: Landsat > ECOSTRESS > VIIRS


def _level_bands(mode):
    if mode == 'SEBAL_Milliy':
        return ['ET_24', 'SOLAR_FRAC']
    return ['ET_24', 'ETRF_INST'] if cfg.is_id_mode(mode) else ['ET_24', 'EVAP_FRAC']


def harmonize(img, mode, k):
    """Xom bandlar saqlanadi (<band>_RAW), asosiy bandlar k ga ko'paytiriladi; KC qayta hisoblanadi."""
    bands = _level_bands(mode)
    img = img.addBands(img.select(bands, [b + '_RAW' for b in bands])).set('K_FACTOR', k)
    if k == 1.0:
        return img
    img = img.addBands(img.select(bands).multiply(k), overwrite=True)
    if mode != 'pysebal':
        kc = (img.select('ET_24').divide(img.select('ETREF_24').max(0.5))
              .clamp(0, 2.5).rename('KC'))
        img = img.addBands(kc, overwrite=True)
    return img


def compose_daily(processed):
    """[(sana, tur, img)] → kunlik tasvirlar (sana bo'yicha), piksel bo'yicha ustuvorlik."""
    by = collections.defaultdict(list)
    for d, kind, img in processed:
        by[d].append((kind, img))
    out, dates, kinds = [], [], []
    for d in sorted(by):
        lst = sorted(by[d], key=lambda x: PRIORITY.index(x[0]))       # yuqori ustuvorlik birinchi

        def tag(kind, img, bands=None):
            # Bandlar turi Float'ga keltiriladi (qiymat o'zgarmaydi): sahnalarda bir band (masalan DTA) turli
            # qiymat oralig'i bilan e'lon qilinadi, mosaic/oylik ImageCollection esa bir xil tur talab qiladi
            # ("Expected a homogeneous image collection ... band 'DTA'" — Sirdaryo 2025-07 oylik eksporti).
            src = (ee.Image.constant(KIND_CODE[kind]).toByte().rename('SOURCE')
                   .updateMask(img.select('ET_24').mask()))
            sel = img.select(bands) if bands else img
            return (ee.Image(sel.toFloat().addBands(src).copyProperties(img))     # copyProperties → Element
                    .set('system:time_start', img.get('system:time_start')))

        label = '+'.join(k for k, _ in lst)
        if len(lst) == 1:
            kind, img = lst[0]
            out.append(tag(kind, img).set('SOURCE_KINDS', label))
        else:
            names = [set(img.bandNames().getInfo()) for _, img in lst]
            common = sorted(set.intersection(*names))
            # mosaic: oxirgi tasvir ustida → eng yuqori ustuvorlik oxirida; har piksel — bitta sahnadan
            ims = [tag(kind, img, common).updateMask(img.select('ET_24').mask())
                   for kind, img in reversed(lst)]
            top = lst[0][1]
            out.append(ee.Image(ee.ImageCollection(ims).mosaic()
                                .setDefaultProjection(top.select('NDVI').projection())
                                .copyProperties(top))
                       .set({'system:time_start': top.get('system:time_start'),
                             'SOURCE_KINDS': label}))
        dates.append(d)
        kinds.append(label)
    return out, dates, kinds


def process_tile(roi, date_start, date_end, mode, tile_label, *, anchor_method, anchor_mode,
                 ref_type, utc_offset, etr24_source, sloping_terrain, z_ws, prefix,
                 rules=None, calendar_xlsx=True, calendar=None, details=None, region=None,
                 region_label=''):
    """calendar — tayyor TileCalendar (qayta hisoblanmaydi); details — ro'yxat berilsa, har sahna
    uchun {'sana','tur','obs','hls','kirish','natija','qc'} qo'shiladi (notebook ko'rinishi uchun).
    region — foydalanuvchi hududi (viloyat): tasvir qoidalari VA kalibratsiya (anchor zonalari va qidiruvi,
    z0m persentillari, sahna QC) tile ∩ region ekinida (user, 2026-09-29: anchor boshqa viloyatga ketmasin).
    calendar berilsa hudud uning o'zidan (cal.region) olinadi. RF downscaling o'qitish — butun tile (roi)."""
    from .. import main as M                 # process_scene, _scene_qc_report (aylanma importsiz)
    rules = rules or InputRules()
    if not tile_label:
        raise ValueError("LHLSVIIRSECO: tile_label — MGRS tile nomi kerak (masalan 'T42SUJ')")

    if calendar is not None:
        cal = calendar
    else:
        print(f"{prefix} 🛰️ LHLSVIIRSECO | {tile_label} | kalendar (kirish bosqichi)...")
        cal = TileCalendar(tile_label, date_start, date_end, rules,
                           log=lambda s: print(f"{prefix}{s}"), region=region).run()
        if calendar_xlsx:
            tag = f'{cal.tile.id}_{region_label}' if region is not None and region_label else cal.tile.id
            path = os.path.join(SCRIPTS, 'inventory', f'{tag}_kalendar_{date_start}_{date_end}.xlsx')
            cal.to_excel(path)
            print(f"{prefix} 📅 kalendar: {path}")

    # Kalibratsiya hududi: tile ∩ viloyat (region yo'q — butun tile). Sahna yig'uvchi (ERA5 / L1 burchak
    # filterBounds) va RF o'qitish esa butun tile bilan qoladi.
    calib = cal.geom
    if cal.region is not None:
        print(f"{prefix} 🎯 Kalibratsiya hududi (anchor, z0m, QC): tile ∩ {region_label or 'hudud'}")
    items = [(o['sana'], 'L', o, None) for o in cal.obs['Landsat'] if o['qabul']]
    items += [(o['sana'], 'E', o, o['_hls']) for o in cal.obs['ECOSTRESS'] if o.get('juft')]
    items += [(o['sana'], 'V', o, o['_hls']) for o in cal.obs['VIIRS'] if o.get('juft')]
    items.sort(key=lambda x: (x[0], PRIORITY.index(x[1])))
    n = len(items)
    print(f"{prefix} Sahnalar: {n} (L {sum(i[1] == 'L' for i in items)}, "
          f"E {sum(i[1] == 'E' for i in items)}, V {sum(i[1] == 'V' for i in items)})")
    info = {'dates': [], 'scene_dates': [], 'image_count': 0, 'solar_src': [],
            'utc_offset': utc_offset, 'sloping_terrain': sloping_terrain,
            'mode_process': 'LHLSVIIRSECO', 'tile': cal.tile, 'calendar': cal}
    if not n:
        return [], info

    zones_by_year = {}

    def zones_for(d):                        # anchor zonalari — tile uchun har yil BIR MARTA
        y = int(d[:4])
        if y not in zones_by_year:
            if rules.anchor_scheme == 'WC':
                zones_by_year[y] = energy_balance.compute_tile_anchor_zones(calib)
            else:
                zones_by_year[y] = anchor_zones.h3_zones(cal.tile, y, rules.anchor_scheme,
                                                         log=lambda s: print(f"{prefix}{s}"), geom=calib)
        return zones_by_year[y]

    ldown_empirical = cfg.ldown_is_empirical(mode)
    ctx = dict(prefix=prefix, anchor_method=anchor_method, anchor_mode=anchor_mode,
               ldown_empirical=ldown_empirical, sloping_terrain=sloping_terrain, z_ws=z_ws,
               ref_type=ref_type, utc_offset=utc_offset, etr24_source=etr24_source)
    k_of = {'L': 1.0, 'E': rules.eco_k, 'V': rules.viirs_k}
    processed, qc_rows = [], []
    for j, (d, kind, o, h) in enumerate(items):
        label = f"Sahna {j + 1}/{n} [{kind}]"
        opt = f", optika {h['sensor']} {h['sana']}" if h else ''
        print(f"{prefix} {label} {d}{opt}...")
        img = scenes.build(kind, cal.tile, o, h, roi, rules)
        img = surface_props.compute_all(img, mode, calib)
        img = (radiation.compute_pre_longwave(img, mode, sloping_terrain=sloping_terrain,
                                              lst_ready=kind != 'L') if ldown_empirical else
               radiation.compute_all(img, mode, sloping_terrain=sloping_terrain, lst_ready=kind != 'L'))
        qc = {'sana': d, 'manba': kind, 'optika': f"{h['sensor']} {h['sana']}" if h else 'Landsat',
              'quyosh_geom': 'L1/ASTRONOMIK' if kind == 'L' else 'ASTRONOMIK'}
        qc_rows.append(qc)
        cz, hz = zones_for(d)
        try:
            out = M.process_scene(img, qc, calib, mode, date=d, label=label,
                                  cold_zone=cz, hot_zone=hz, **ctx)
        except (RuntimeError, ee.EEException) as e:
            # Bitta sahna xatosi butun tile'ni to'xtatmasin (Sirdaryo T42TVK, 2025-07-10 V: "hot anchor
            # koordinatasi topilmadi" — 20 sahnalik tile tushib qolgan). Xato yutilmaydi: sahna RAD ETILDI,
            # sababi QC hisobotida. Landsat yo'li (main.process_tile) o'zgarmagan.
            out = None
            M._reject(d, f'XATO: {type(e).__name__}: {e}', qc, prefix)
        if out is not None:
            out = harmonize(out, mode, k_of[kind])
            processed.append((d, kind, out))
        if details is not None:
            details.append({'sana': d, 'tur': kind, 'obs': o, 'hls': h, 'kirish': img,
                            'natija': out, 'qc': qc})

    M._scene_qc_report(qc_rows, prefix, tile_label, mode, date_start, date_end)
    daily, dates, kinds = compose_daily(processed)
    info.update({'dates': dates, 'scene_dates': dates, 'image_count': len(daily),
                 'solar_src': kinds})
    print(f"{prefix} ✅ kunlik tasvirlar: {len(daily)} ({', '.join(f'{d} {k}' for d, k in zip(dates, kinds))})")
    return daily, info


def export_crop_mask(tile, region, date_start, date_end, folder):
    """CROP_MASK (Esri 5, piksel ≥ 50% ekin) — har yil uchun bitta raster, tile gridida."""
    last = (dt.date.fromisoformat(date_end) - dt.timedelta(days=1)).year
    tasks = []
    for y in range(int(date_start[:4]), last + 1):
        name = f'SEBAL_CROPMASK_{tile.id}_{y}'
        t = ee.batch.Export.image.toDrive(
            image=tile.crop_mask(y, 30).clip(region), description=name, folder=folder,
            fileNamePrefix=name, region=region, crs=tile.crs, crsTransform=tile.transform(30),
            maxPixels=1e13, fileFormat='GeoTIFF')
        t.start()
        tasks.append(t)
        print(f"  ✅ {name} (Esri {tile.esri_year(y)})")
    return tasks
