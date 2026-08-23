# -*- coding: utf-8 -*-
"""
VALIDATSIYA DRIVER — 10 nuqta (9 flux + Bushland lizimetr), TILE bo'yicha guruhlangan.
BITTA ishga tushirish → barcha (guruh × yil × model) uchun CSV-zonal export (GEE→Drive).

  • Bir tile'ga tushgan nuqtalar (mas. Nebraska Ne1/Ne2/Ne3) BITTA run bilan:
    tile bir marta hisoblanadi, csv_region = guruhning HAMMA nuqtasi → hammasi namuna.
  • Har guruh o'z YILLARIда (flux 2022-24; UR8 2024-25; lizimetr 2021).
  • Har (guruh×yil) uchun 4 model alohida.

Har run → scene CSV (INST + DAILY-overpass + barcha komponent) + monthly CSV.
Ishga: python run_flux_validation.py   (avval GROUPS_TO_RUN bilan kichik sinang)
"""
import sys
# Windows konsol/redirect (cp1251) emoji/belgi crash qilmasin → UTF-8 majburlash
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import ee
import time
from datetime import datetime
from sebal_gee_v4 import main
from sebal_gee_v4 import ee_utils
from flux_sites import POINTS, GROUPS, SEASON, FOOTPRINT_M, MODES

ee_utils.install_getinfo_retry()
ee.Initialize(project="carbon-science-461016-q2")

# --- TO'LIQ RUN: 7 guruh × o'z yillari × 4 model = 72 run ---
GROUPS_TO_RUN = list(GROUPS)           # HAMMA guruh (Nebraska..Texas_lys)
YEARS_LIMIT = None                     # None → har guruh O'Z yillari (flux 2022-24; UR8 24-25; lys 2021)
MODES_TO_RUN = MODES                   # 4 model


def _bbox(pts, pad=0.2):
    lons = [POINTS[p]['lon'] for p in pts]; lats = [POINTS[p]['lat'] for p in pts]
    return [min(lons) - pad, min(lats) - pad, max(lons) + pad, max(lats) + pad]


def run_combo(gname, g, year, mode):
    pts = g['points']
    fc = main.parcels_from_points({p: [POINTS[p]['lon'], POINTS[p]['lat']] for p in pts},
                                  size_m=FOOTPRINT_M, inner_buffer_m=0)
    ds, de = f'{year}-{SEASON[0]}', f'{year}-{SEASON[1]}'
    print(f"\n{'='*62}\n  {gname} {year} | {mode} | nuqtalar: {pts}\n{'='*62}")
    return main.run(
        roi_type='rectangle', bounds=_bbox(pts),
        date_start=ds, date_end=de,
        mode=mode, satellite='BOTH', cloud_max=70,
        utc_offset=g['utc'], process_by_tile=True, tiles=None,
        export_daily=False, export_monthly=False, export_csv=True,
        csv_region=fc,
        save_et=True, save_biomass=False, save_etref=False,
        save_tact=False, save_eact=False, save_cuirr=False, validate=False,
        folder=f'FLUXVAL_{gname}_{year}_{mode}',
        scale=30, crs=g['crs'], anchor_method='cascade',
    )


def main_run():
    combos = []
    for gname in GROUPS_TO_RUN:
        g = GROUPS[gname]
        years = YEARS_LIMIT or g['years']
        for year in years:
            for mode in MODES_TO_RUN:
                combos.append((gname, g, year, mode))
    t0 = time.time()
    print(f"  Guruhlar: {GROUPS_TO_RUN}")
    print(f"  Jami run: {len(combos)}  |  boshlandi: {datetime.now():%Y-%m-%d %H:%M}")
    ok, fail = 0, 0
    for i, (gname, g, year, mode) in enumerate(combos, 1):
        el = (time.time() - t0) / 60
        print(f"\n  ▶ [{i}/{len(combos)}]  {datetime.now():%H:%M}  (+{el:.0f} daq)")
        try:
            run_combo(gname, g, year, mode); ok += 1
        except Exception as e:
            fail += 1; print(f"  ⚠️ {gname} {year} {mode} XATO: {e}")
    dt = (time.time() - t0) / 60
    print(f"\n  ✅ {ok} muvaffaqiyatli, {fail} xato  |  jami {dt:.0f} daqiqa  "
          f"|  tugadi: {datetime.now():%H:%M}")
    print(f"  GEE Tasks → tugagach Drive'dan FLUXVAL_* → flux_compare.py")


if __name__ == '__main__':
    main_run()
