"""
VIIRS vegetation-predictor ET downscaling — CLI runner
======================================================
Mavjud SEBAL pipeline (sebal_gee_v4) Landsat/HLS anchorlarini VIIRS
VNP09GA (I1/I2/I3) predictorlari bilan oy ichida kunlik 30 m ET
time-series ga aylantiradi. SEBAL mantig'i O'ZGARMAYDI.

Misollar:
  python viirs_main.py --project carbon-science-461016-q2 --month 2026-03 \
      --downscale-mode lambda --viirs-model ndvi --dry-run
  python viirs_main.py --project carbon-science-461016-q2 --month 2026-03 \
      --downscale-mode lambda --viirs-model compare --export
  python viirs_main.py --project carbon-science-461016-q2 --month 2026-03 \
      --downscale-mode kc --viirs-model multi --export
"""

import argparse
import calendar
import csv
import sys

import ee


# ==============================================================
# CLI
# ==============================================================

def parse_args():
    p = argparse.ArgumentParser(description='VIIRS ET downscaling')
    p.add_argument('--project', required=True)
    p.add_argument('--roi-name', default='Sirdarya', help='GAUL ADM1_NAME')
    p.add_argument('--month', help='YYYY-MM')
    p.add_argument('--start', help='YYYY-MM-DD')
    p.add_argument('--end', help='YYYY-MM-DD')
    p.add_argument('--anchor-source', choices=['landsat', 'hls', 'both'],
                   default='landsat')
    p.add_argument('--downscale-mode', choices=['lambda', 'kc'],
                   default='lambda')
    p.add_argument('--viirs-model',
                   choices=['ndvi', 'ndvi2', 'multi', 'compare'],
                   default='ndvi')
    p.add_argument('--viirs-qa-mode', choices=['strict', 'lenient'],
                   default='lenient')
    p.add_argument('--temporal-fill', choices=['linear', 'nearest'],
                   default='linear')
    p.add_argument('--cloud-max', type=int, default=70)
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--export', action='store_true')
    p.add_argument('--tile-scale', type=int, default=4)
    p.add_argument('--stats-scale', type=int, default=30)
    return p.parse_args()


def resolve_dates(args):
    if args.month:
        y, m = map(int, args.month.split('-'))
        days = calendar.monthrange(y, m)[1]
        return f'{y}-{m:02d}-01', f'{y}-{m:02d}-{days:02d}', f'{y}_{m:02d}'
    if args.start and args.end:
        tag = args.start.replace('-', '_')
        return args.start, args.end, tag
    sys.exit('XATO: --month yoki --start/--end bering')


# ==============================================================
# Anchor yuklash (SEBAL — o'zgarmaydi)
# ==============================================================

def load_anchors(roi, start, end, anchor_source, cloud_max):
    """SEBAL process_tile orqali Landsat/HLS anchor sahnalarini olish."""
    from sebal_gee_v4 import main as M

    sat = 'HLS' if anchor_source == 'hls' else 'BOTH'
    scenes, info = M.process_tile(roi, start, end, 'pysebal', sat,
                                  cloud_max, '')
    anchors = []
    for i, img in enumerate(scenes):
        anchors.append({'image': ee.Image(img), 'date': info['dates'][i]})
    return anchors, info


# ==============================================================
# DRY-RUN — yengil tekshiruvlar
# ==============================================================

def run_dry_run(roi, start, end, args):
    from sebal_gee_v4 import viirs_downscaling as vds

    print('\n=== DRY-RUN ===')
    print(f'ROI: {args.roi_name} | {start} → {end}')

    anchors, info = load_anchors(roi, start, end, args.anchor_source,
                                 args.cloud_max)
    print(f'SEBAL anchorlar: {len(anchors)} | sanalar: {info["dates"]}')
    if not anchors:
        print('❌ Anchor topilmadi — to\'xtatildi'); return

    bands = anchors[0]['image'].bandNames().getInfo()
    need = (['EVAP_FRAC', 'RN24'] if args.downscale_mode == 'lambda'
            else ['KC', 'ETREF_24'])
    need += ['ALBEDO', 'TAU_SW', 'ET_24']
    missing = [b for b in need if b not in bands]
    print(f'Kerakli bandlar: {need}')
    if missing:
        print(f'❌ YETISHMAYDI: {missing}')
        if args.downscale_mode == 'lambda' and 'RN24' in missing:
            print('   → Lambda mode uchun RN24/Rn24-G24 kerak.')
        if args.downscale_mode == 'kc' and 'ETREF_24' in missing:
            print('   → KC mode uchun ETREF_24 kerak.')
    else:
        print('✅ Barcha kerakli bandlar mavjud')

    # VNP09GA I1/I2/I3
    vimg = vds.get_viirs_vnp09ga(start, roi)
    try:
        vbands = vimg.bandNames().getInfo()
        ok_i = all(b in vbands for b in ['I1', 'I2', 'I3'])
        print(f'VNP09GA I1/I2/I3 mavjud: {ok_i}')
    except Exception as e:
        print(f'⚠️ VNP09GA tekshirilmadi: {e}')

    avail = vds.viirs_available_dates(start, end, roi)
    print(f'VIIRS mavjud kunlar: {len(avail)}')
    print(f'Oydagi kunlar: {len(vds._days_in_range(start, end))}')
    print(f'Taxminiy regressiya namunasi: ≤ {len(anchors)} × '
          f'{vds.DCFG["max_samples"]}')
    print('=== DRY-RUN tugadi ===\n')


# ==============================================================
# TO'LIQ ISH OQIMI
# ==============================================================

def run_full(roi, start, end, tag, args):
    from sebal_gee_v4 import viirs_downscaling as vds

    anchors, info = load_anchors(roi, start, end, args.anchor_source,
                                 args.cloud_max)
    if len(anchors) < 1:
        sys.exit('❌ Anchor topilmadi')
    print(f'Anchorlar: {len(anchors)} | {info["dates"]}')

    mode = args.downscale_mode
    vproj = vds.get_viirs_projection(vds.get_viirs_vnp09ga(start, roi))

    models = list(vds.MODELS) if args.viirs_model == 'compare' \
        else [args.viirs_model]

    # --- Regressiya (har model) ---
    fc = vds.build_training_samples(anchors, roi, vproj, mode,
                                    args.viirs_qa_mode)
    snp = vds.samples_to_numpy(fc)

    reg_rows = []
    reg_by_model = {}
    for mdl in models:
        reg = vds.fit_viirs_regression(snp, mdl)
        reg_by_model[mdl] = reg
        print(f'  [{mdl}] R2={reg.get("R2")}, RMSE={reg.get("RMSE")}, '
              f'N={reg.get("N")}')
        reg_rows.append({
            'model_name': mdl, 'downscale_mode': mode,
            'coefficients': reg.get('coeffs'),
            'R2': reg.get('R2'), 'RMSE': reg.get('RMSE'),
            'MAE': reg.get('MAE'), 'Bias': reg.get('Bias'), 'N': reg.get('N'),
        })
    _write_csv(f'viirs_regression_metrics_{tag}.csv', reg_rows)

    # --- Weight diagnostikasi ---
    tband = 'EVAP_FRAC' if mode == 'lambda' else 'KC'
    w_rows = []
    for a in anchors:
        w = vds.build_spatial_weight(a['image'].select(tband), vproj, mode)
        wcoarse = vds.aggregate_to_viirs_grid(w, vproj)
        st = wcoarse.reduceRegion(
            ee.Reducer.mean().combine(ee.Reducer.minMax(), sharedInputs=True),
            roi, args.stats_scale * 30, maxPixels=1e9, bestEffort=True).getInfo()
        wmean = st.get('W_mean')
        w_rows.append({
            'anchor_date': a['date'], 'target_mode': mode,
            'weight_min': st.get('W_min'), 'weight_max': st.get('W_max'),
            'weight_mean': wmean,
            'weight_mean_error': (abs(wmean - 1.0) if wmean is not None else None),
        })
    _write_csv(f'viirs_weight_diagnostics_{tag}.csv', w_rows)

    # --- Hold-out validatsiya (2+ anchor bo'lsa) ---
    val_rows = []
    if len(anchors) >= 2:
        for mdl in models:
            for idx in range(len(anchors)):
                res = vds.validate_holdout(anchors, idx, roi, vproj, mdl,
                                           mode, args.viirs_qa_mode)
                if 'RMSE' in res:
                    val_rows.append(res)
                    print(f'  holdout {res["holdout_date"]} [{mdl}]: '
                          f'RMSE={res["RMSE"]:.3f} R2={res["R2"]:.3f}')
    else:
        print('  ⚠️ Hold-out uchun 2+ anchor kerak')
    if val_rows:
        _write_csv(f'viirs_holdout_validation_{tag}.csv', val_rows)

    # --- Oylik ET (eng yaxshi/tanlangan model) ---
    best = (min(reg_by_model.values(),
                key=lambda r: r.get('RMSE', 9e9)) if args.viirs_model == 'compare'
            else reg_by_model[args.viirs_model])
    print(f'  Oylik ET uchun model: {best["model_name"]}')

    daily_et = vds.build_daily_viirs_downscaled_collection(
        start, end, roi, anchors, best, best['model_name'], mode, vproj,
        args.viirs_qa_mode, args.temporal_fill)

    monthly = vds.build_monthly_et_sum(daily_et)
    mstat = monthly.reduceRegion(
        ee.Reducer.minMax().combine(ee.Reducer.mean(), sharedInputs=True),
        roi, args.stats_scale * 30, maxPixels=1e9, bestEffort=True).getInfo()
    n_days = len(vds._days_in_range(start, end))
    _write_csv(f'monthly_et_summary_{tag}.csv', [{
        'month': tag, 'downscale_mode': mode,
        'viirs_model': best['model_name'], 'daily_count': n_days,
        'ET_month_min': mstat.get('ET_MONTHLY_min'),
        'ET_month_max': mstat.get('ET_MONTHLY_max'),
        'ET_month_mean': mstat.get('ET_MONTHLY_mean'),
    }])
    print(f'  Oylik ET (mean): {mstat.get("ET_MONTHLY_mean")} mm/oy')

    # --- Stage 2: raster export (ixtiyoriy) ---
    if args.export:
        task = ee.batch.Export.image.toDrive(
            image=monthly.toFloat(),
            description=f'VIIRS_ET_MONTHLY_{tag}',
            folder='VIIRS_ET_downscaling',
            fileNamePrefix=f'VIIRS_ET_MONTHLY_{tag}',
            region=roi, scale=30, crs='EPSG:32642',
            maxPixels=1e13)
        task.start()
        print(f'  📤 Oylik ET raster export boshlandi (task {task.id})')


def _write_csv(name, rows):
    if not rows:
        return
    keys = list(rows[0].keys())
    with open(name, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f'  💾 {name} ({len(rows)} qator)')


# ==============================================================
# MAIN
# ==============================================================

def main():
    args = parse_args()
    ee.Initialize(project=args.project)

    from sebal_gee_v4 import ee_utils
    ee_utils.install_getinfo_retry()

    roi = (ee.FeatureCollection('FAO/GAUL/2015/level1')
           .filter(ee.Filter.eq('ADM1_NAME', args.roi_name)).geometry())

    start, end, tag = resolve_dates(args)

    print('=' * 60)
    print('  VIIRS ET DOWNSCALING')
    print(f'  Mode: {args.downscale_mode} | Model: {args.viirs_model} | '
          f'QA: {args.viirs_qa_mode} | Fill: {args.temporal_fill}')
    print('=' * 60)

    if args.dry_run:
        run_dry_run(roi, start, end, args)
    else:
        run_full(roi, start, end, tag, args)


if __name__ == '__main__':
    main()
