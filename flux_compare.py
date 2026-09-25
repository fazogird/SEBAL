# -*- coding: utf-8 -*-
"""
FLUX_COMPARE — SEBAL modellari (FLUXVAL export) vs ground-truth (AmeriFlux EC + Bushland lizimetr).
Har (model × sayt × yil) uchun DAILY_ET (overpass-kun) ni kuzatuv ET bilan solishtiradi.

Ground truth:
  • AmeriFlux 8 sayt: ET_ground_truth_DD xlsx → LE_F_MDS (gap-filled) & LE_CORR (closure-corrected)
    LE (W/m², kunlik o'rt.) → ET (mm/kun) = LE × 0.035265
  • Bushland lizimetr (2021): 4 lizimetr (NE/SE/NW/SW) "ET from Catch Precip" o'rtachasi (mm/kun)
  • US-UR8: DD yo'q (faqat HH) → hozircha o'tkazib yuboriladi (NOT_AVAILABLE)

Chiqish:
  validation_result/flux_metrics_ALL.csv   — to'liq (har model×sayt×LE-ref×stat)
  validation_result/flux_pairs.csv         — barcha juftliklar (model, obs)
  konsolga — model bo'yicha umumiy jadval
"""
import os, glob, re
import numpy as np
import pandas as pd
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from val_metrics import val_stats, METRIC_ORDER

FLUXVAL = r'D:/Cloud_comp/GDisk_down/FLUXVAL'
GT      = r'D:/Cloud_comp/new_way_cloud_comp/input/ground_truth'
OUT     = r'D:/Cloud_comp/Sebal/scripts/validation_result'
MODES   = ['SEBAL_Milliy_Kc', 'SEBAL_Milliy', 'SEBAL_ID', 'SEBAL_B']  # uzun birinchi (suffix-match)
LE2ET   = 0.035265   # W/m² (kunlik o'rt.) → mm/kun
QC_MIN  = 0.75       # LE_F_MDS_QC filtri (asosiy); -1 → filtrsiz
BUSHLAND_NAME = 'Bushland_lys'


# ============================================================
# 1) MODEL TOMONI — FLUXVAL DAILY_ET CSV lar
# ============================================================
def parse_folder(fname):
    """FLUXVAL_{group}_{year}_{mode} → (group, year, mode). Mode/group underscore-larni to'g'ri ajratadi."""
    rest = fname[len('FLUXVAL_'):]
    for mode in MODES:                       # uzun birinchi
        if rest.endswith('_' + mode):
            head = rest[:-(len(mode) + 1)]   # 'California_2022'
            year = head[-4:]
            group = head[:-5]
            return group, int(year), mode
    return None, None, None


def load_model():
    rows = []
    for d in sorted(glob.glob(os.path.join(FLUXVAL, 'FLUXVAL_*'))):
        if not os.path.isdir(d):
            continue
        group, year, mode = parse_folder(os.path.basename(d))
        if mode is None:
            print('  ? papka nomi tushunilmadi:', os.path.basename(d)); continue
        for csv in glob.glob(os.path.join(d, '*DAILY_ET*.csv')):
            try:
                df = pd.read_csv(csv, usecols=['date', 'mean', 'median', 'name'])
            except Exception as e:
                print('  ! o\'qilmadi', os.path.basename(csv), e); continue
            df['date'] = pd.to_datetime(df['date']).dt.normalize()
            df = df.rename(columns={'mean': 'et_mean', 'median': 'et_median', 'name': 'site'})
            df['mode'] = mode; df['group'] = group; df['year'] = year
            rows.append(df[['mode', 'group', 'year', 'site', 'date', 'et_mean', 'et_median']])
    if not rows:
        raise SystemExit('MODEL CSV topilmadi!')
    m = pd.concat(rows, ignore_index=True)
    # bir nuqta 2 tile'da bo'lishi mumkin (P35/P36) — faqat bittasida haqiqiy qiymat.
    # (mode,site,date) bo'yicha NaN-larni tashlab, o'rtacha (amalda 1 ta qoladi)
    m = (m.groupby(['mode', 'group', 'year', 'site', 'date'], as_index=False)
           .agg(et_mean=('et_mean', 'mean'), et_median=('et_median', 'mean')))
    return m


# ============================================================
# 2) KUZATUV TOMONI — ground truth
# ============================================================
def amf_folder(site):
    hits = glob.glob(os.path.join(GT, f'AMF_{site}_*'))
    return hits[0] if hits else None


def load_obs_amf(site):
    """AmeriFlux DD ET ground truth → DataFrame[date, et_fmds, et_corr]."""
    fold = amf_folder(site)
    if not fold:
        return None
    dd = glob.glob(os.path.join(fold, f'{site}_ET_ground_truth_DD_*.xlsx'))
    dd = [f for f in dd if 'NOT_AVAILABLE' not in f]
    if not dd:
        return None
    df = pd.read_excel(dd[0])
    df['date'] = pd.to_datetime(df['TIMESTAMP'].astype(int).astype(str), format='%Y%m%d')
    for c in ['LE_F_MDS', 'LE_CORR', 'LE_F_MDS_QC']:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors='coerce')
            df.loc[df[c] <= -9990, c] = np.nan
    # QC filtri LE_F_MDS ga
    fmds = df['LE_F_MDS'].copy()
    if QC_MIN >= 0 and 'LE_F_MDS_QC' in df:
        fmds = fmds.where(df['LE_F_MDS_QC'] >= QC_MIN)
    out = pd.DataFrame({
        'date': df['date'],
        'et_fmds': fmds * LE2ET,
        'et_corr': df['LE_CORR'] * LE2ET if 'LE_CORR' in df else np.nan,
    })
    return out


def load_obs_bushland():
    """Bushland 4 lizimetr (NE/SE/NW/SW) 'ET from Catch Precip' o'rtachasi → DataFrame[date, et_fmds, et_corr]."""
    lyz = os.path.join(GT, 'lyzimetr')
    files = {'E': os.path.join(lyz, '2021_Cotton_E_Lys_ClimDat.xlsx'),
             'W': os.path.join(lyz, '2021_Cotton_W_Lys_ClimDat.xlsx')}
    series = []
    for side, f in files.items():
        if not os.path.exists(f):
            continue
        sheet = [s for s in pd.ExcelFile(f).sheet_names if s.strip().endswith('Daily') and 'Dic' not in s]
        if not sheet:
            continue
        raw = pd.read_excel(f, sheet_name=sheet[0], header=0)
        cols = {str(c).strip(): c for c in raw.columns}
        # ET ustunlari: '<LYS> ET from Catch Precip in mm'
        et_cols = [orig for name, orig in cols.items()
                   if re.match(r'^[NS][EW] ET from Catch Precip', name)]
        yr = pd.to_numeric(raw[cols['Year']], errors='coerce')
        doy = pd.to_numeric(raw[cols['DOY']], errors='coerce')
        date = pd.to_datetime(yr.astype('Int64').astype(str), format='%Y', errors='coerce') \
               + pd.to_timedelta(doy - 1, unit='D')
        for ec in et_cols:
            series.append(pd.DataFrame({'date': date,
                                        'lys': str(ec).strip()[:2],
                                        'et': pd.to_numeric(raw[ec], errors='coerce')}))
    if not series:
        return None
    alls = pd.concat(series, ignore_index=True).dropna(subset=['date'])
    daily = alls.groupby('date', as_index=False)['et'].mean()   # 4 lizimetr o'rtacha
    return pd.DataFrame({'date': daily['date'], 'et_fmds': daily['et'], 'et_corr': daily['et']})


def load_obs(site):
    if site == BUSHLAND_NAME:
        return load_obs_bushland()
    return load_obs_amf(site)


# ============================================================
# 3) SOLISHTIRISH
# ============================================================
def build():
    os.makedirs(OUT, exist_ok=True)
    model = load_model()
    print(f'Model juftlik-manba: {len(model)} qator, '
          f'saytlar: {sorted(model.site.unique())}')

    obs_cache = {}
    pairs = []
    for site in sorted(model.site.unique()):
        o = obs_cache.get(site)
        if o is None:
            o = load_obs(site); obs_cache[site] = o
        if o is None:
            print(f'  ! {site}: ground truth topilmadi (o\'tkazildi)'); continue
        msite = model[model.site == site]
        merged = msite.merge(o, on='date', how='inner')
        pairs.append(merged)
        print(f'  {site}: {len(merged)} mos kun (model×obs)')
    if not pairs:
        raise SystemExit('Hech qanday juftlik topilmadi!')
    P = pd.concat(pairs, ignore_index=True)
    P.to_csv(os.path.join(OUT, 'flux_pairs.csv'), index=False)

    # --- metrikalar: model (mean/median) × LE-ref (fmds/corr), guruhlash bo'yicha ---
    recs = []
    def add(scope, mode, site, model_col, ref_col, sub):
        s = val_stats(sub[model_col].values, sub[ref_col].values)
        rec = dict(scope=scope, mode=mode, site=site,
                   model=model_col.replace('et_', ''), ref=ref_col.replace('et_', ''))
        rec.update(s); recs.append(rec)

    for mcol in ['et_mean', 'et_median']:
        for rcol in ['et_fmds', 'et_corr']:
            # umumiy (barcha sayt pooled) — har model
            for mode in P['mode'].unique():
                sub = P[P['mode'] == mode].dropna(subset=[mcol, rcol])
                if len(sub) >= 3:
                    add('OVERALL', mode, 'ALL', mcol, rcol, sub)
            # har model × sayt
            for (mode, site), sub in P.groupby(['mode', 'site']):
                sub = sub.dropna(subset=[mcol, rcol])
                if len(sub) >= 3:
                    add('PER_SITE', mode, site, mcol, rcol, sub)
    R = pd.DataFrame(recs)
    R = R[['scope', 'mode', 'site', 'model', 'ref'] + METRIC_ORDER]
    R.to_csv(os.path.join(OUT, 'flux_metrics_ALL.csv'), index=False)

    # --- konsol jadvali: OVERALL, model=mean ---
    print('\n' + '=' * 78)
    print('UMUMIY (barcha sayt pooled) — model=MEAN, DAILY overpass ET')
    print('=' * 78)
    for rcol, label in [('fmds', 'LE_F_MDS (gap-filled)'), ('corr', 'LE_CORR (closure-corrected)')]:
        t = R[(R.scope == 'OVERALL') & (R.model == 'mean') & (R.ref == rcol)]
        if t.empty:
            continue
        order = [m for m in MODES if m in set(t['mode'])]
        t = t.set_index('mode').reindex(order)
        print(f'\n  --- ref: {label} ---')
        print(f'  {"model":<18}{"n":>5}{"R2":>8}{"r2_p":>8}{"RMSE":>8}{"MBE":>8}{"MAPE":>8}{"slope":>8}')
        for mode, r in t.iterrows():
            print(f'  {mode:<18}{int(r.n):>5}{r.R2:>8.3f}{r.r2_pearson:>8.3f}'
                  f'{r.RMSE:>8.3f}{r.MBE:>8.3f}{r.MAPE:>8.1f}{r.slope:>8.3f}')
    print(f'\nTo\'liq: {os.path.join(OUT, "flux_metrics_ALL.csv")}')
    print(f'Juftliklar: {os.path.join(OUT, "flux_pairs.csv")}')
    return R, P


if __name__ == '__main__':
    build()
