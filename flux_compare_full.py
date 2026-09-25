# -*- coding: utf-8 -*-
"""
FLUX_COMPARE_FULL — SEBAL 4 model vs ground-truth, 3 daraja, ko'p parametr.
Har (daraja × model × sayt × parametr) uchun R2/bias/RMSE/n → 3 alohida Excel.

DARAJALAR & PARAMETRLAR (faqat HAQIQATAN mos keladiganlar solishtiriladi):
  INST (overpass lahzasi):
     AmeriFlux (HR, overpass soati): RN↔NETRAD, LE↔LE_F_MDS&LE_CORR, AIR_TEMP↔TA_F_MDS,
        ALBEDO↔SW_OUT/SW_IN, USTAR↔USTAR, LST↔LW_OUT (Stefan-Boltzmann)
     Bushland (15-min, overpass ±30min): RN, AIR_TEMP, ALBEDO, LST(Nadir Surf.Temp), G0(soil heat flux)
     (H — obs yo'q (FLUXMET'da H/G yo'q); Bushland LE_inst yo'q → solishtirilmaydi, halol qayd)
  DAILY:  ET ↔ LE_F_MDS/LE_CORR (DD)              [SEBAL daily faqat ET]
  MONTHLY: ET ↔ LE_F_MDS/LE_CORR (MM, ×days)      [SEBAL monthly faqat ET]

Overpass vaqti: overpass_hours.json (GEE'dan aniq olingan, mahalliy standart soat).
Chiqish: validation_result/{inst,daily,monthly}_validation.xlsx  (metrics + pairs + notes sheet)
"""
import os, glob, re, json, sys
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass
import numpy as np
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from val_metrics import val_stats, METRIC_ORDER

FLUXVAL = r'D:/Cloud_comp/GDisk_down/FLUXVAL'
GT      = r'D:/Cloud_comp/new_way_cloud_comp/input/ground_truth'
OUT     = r'D:/Cloud_comp/Sebal/scripts/validation_result'
MODES   = ['SEBAL_Milliy_Kc', 'SEBAL_Milliy', 'SEBAL_ID', 'SEBAL_B']
LE2ET   = 0.035265        # W/m² (kunlik/oylik o'rt.) → mm/kun
USTAR_MIN = 0.1           # u* turbulentlik chegarasi (m/s) — LE reference validligi (deck sl.60)
QC_DD_MIN = 0.75          # kunlik/oylik LE ulush-QC (asosan o'lchangan kunlar)
SIGMA   = 5.67e-8
EPS_S   = 0.98            # sirt emissivligi (LW_OUT→LST)
OVERPASS = json.load(open(os.path.join(OUT, 'overpass_hours.json')))
KELVIN = 273.15


# ============================================================
# MODEL yuklash (INST_KOMPONENT + INST + DAILY + MONTHLY)
# ============================================================
def parse_folder(fname):
    rest = fname[len('FLUXVAL_'):]
    for mode in MODES:
        if rest.endswith('_' + mode):
            head = rest[:-(len(mode) + 1)]
            return head[:-5], int(head[-4:]), mode
    return None, None, None


def _read_csv_cols(path, cols):
    df = pd.read_csv(path)
    keep = [c for c in cols if c in df.columns]
    return df[keep]


def load_model_inst():
    """INST_KOMPONENT + INST birlashtirilgan (overpass lahza), (mode,site,date)."""
    komp_cols = ['date', 'name', 'RN_mean', 'G0_mean', 'H_mean', 'LST_mean',
                 'ALBEDO_mean', 'AIR_TEMP_mean', 'USTAR_mean', 'NDVI_mean', 'LAI_mean']
    inst_cols = ['date', 'name', 'LAMBDA_E_mean', 'ET_INST_MM_HR_mean', 'EVAP_FRAC_mean']
    rows = []
    for d in sorted(glob.glob(os.path.join(FLUXVAL, 'FLUXVAL_*'))):
        if not os.path.isdir(d):
            continue
        grp, yr, mode = parse_folder(os.path.basename(d))
        if mode is None:
            continue
        for kf in glob.glob(os.path.join(d, '*INST_KOMPONENT*.csv')):
            inf = kf.replace('INST_KOMPONENT', 'INST')
            try:
                k = _read_csv_cols(kf, komp_cols)
                if os.path.exists(inf):
                    i = _read_csv_cols(inf, inst_cols)
                    k = k.merge(i, on=['date', 'name'], how='left')
            except Exception as e:
                print('  ! inst o\'qilmadi', os.path.basename(kf), e); continue
            k['mode'] = mode; k['date'] = pd.to_datetime(k['date']).dt.normalize()
            rows.append(k)
    m = pd.concat(rows, ignore_index=True).rename(columns={'name': 'site'})
    num = [c for c in m.columns if c not in ('date', 'site', 'mode')]
    m = m.groupby(['mode', 'site', 'date'], as_index=False)[num].mean()   # tile-dedupe
    return m


def load_model_simple(kind):
    """DAILY_ET yoki MONTHLY_ET. kind='DAILY'|'MONTHLY'."""
    rows = []
    for d in sorted(glob.glob(os.path.join(FLUXVAL, 'FLUXVAL_*'))):
        if not os.path.isdir(d):
            continue
        grp, yr, mode = parse_folder(os.path.basename(d))
        if mode is None:
            continue
        pat = '*DAILY_ET*.csv' if kind == 'DAILY' else '*MONTHLY_ET*.csv'
        for f in glob.glob(os.path.join(d, pat)):
            df = pd.read_csv(f)
            df = df.rename(columns={'mean': 'et_mean', 'median': 'et_median', 'name': 'site'})
            df['mode'] = mode
            if kind == 'DAILY':
                df['date'] = pd.to_datetime(df['date']).dt.normalize()
                rows.append(df[['mode', 'site', 'date', 'et_mean', 'et_median']])
            else:
                rows.append(df[['mode', 'site', 'year', 'month', 'et_mean', 'et_median']])
    m = pd.concat(rows, ignore_index=True)
    key = ['mode', 'site', 'date'] if kind == 'DAILY' else ['mode', 'site', 'year', 'month']
    return m.groupby(key, as_index=False)[['et_mean', 'et_median']].mean()


# ============================================================
# OBS — AmeriFlux
# ============================================================
def amf_folder(site):
    h = glob.glob(os.path.join(GT, f'AMF_{site}_*'))
    return h[0] if h else None


def _amf_file(site, tag):
    fold = amf_folder(site)
    if not fold:
        return None
    h = glob.glob(os.path.join(fold, f'*FLUXMET_{tag}_*.csv'))
    return h[0] if h else None


def obs_amf_inst(site):
    """AmeriFlux HR/HH overpass-soatida: RN,LE,AIR_TEMP,ALBEDO,USTAR,LST → DataFrame[date, <param>...]."""
    f = _amf_file(site, 'HR') or _amf_file(site, 'HH')   # soatlik yoki yarim-soatlik
    if not f or site not in OVERPASS or OVERPASS[site] is None:
        return None
    hour = int(OVERPASS[site]['local_hour'])       # overpass mahalliy soat
    use = ['TIMESTAMP_START', 'NETRAD', 'LE_F_MDS', 'LE_F_MDS_QC', 'LE_CORR',
           'TA_F_MDS', 'SW_IN_F', 'SW_OUT', 'USTAR', 'LW_IN_F', 'LW_OUT']
    df = pd.read_csv(f, usecols=lambda c: c in use)
    for c in df.columns:
        if c != 'TIMESTAMP_START':
            df[c] = pd.to_numeric(df[c], errors='coerce')
            df.loc[df[c] <= -9990, c] = np.nan
    ts = df['TIMESTAMP_START'].astype(np.int64).astype(str)
    df['date'] = pd.to_datetime(ts.str[:8], format='%Y%m%d')
    df['hh'] = ts.str[8:10].astype(int)
    d = df[df['hh'] == hour].copy()
    # LST LW_OUT dan: emitted = LW_OUT-(1-eps)LW_IN
    lw_emit = d['LW_OUT'] - (1 - EPS_S) * d['LW_IN_F']
    lst_c = (lw_emit / (EPS_S * SIGMA)) ** 0.25 - KELVIN
    # DECK sl.60: "Never validate against gap-filled reference." LE_F_MDS_QC = BAYROQ
    # (0=O'LCHANGAN, 1=yaxshi gap-fill, 2/3=yomon). => faqat QC==0 (o'lchangan) + u* turbulentlik
    # filtri (footprint validligi). Bu filtr FAQAT LE ga (flux); RN/LST/TA/albedo radiometrik → tegmaydi.
    le = d['LE_F_MDS'].where((d['LE_F_MDS_QC'] == 0) & (d['USTAR'] >= USTAR_MIN))
    alb = (d['SW_OUT'] / d['SW_IN_F']).where(d['SW_IN_F'] > 50)
    out = pd.DataFrame({
        'date': d['date'],
        'RN': d['NETRAD'],
        'LE_fmds': le, 'LE_corr': d['LE_CORR'],
        'AIR_TEMP': d['TA_F_MDS'],                 # °C
        'ALBEDO': alb,
        'USTAR': d['USTAR'],
        'LST': lst_c,                              # °C
    })
    return out.groupby('date', as_index=False).mean()


def obs_amf_period(site, tag):
    """DD yoki MM: LE_F_MDS & LE_CORR → ET. tag='DD'|'MM'."""
    f = _amf_file(site, tag)
    if not f:
        return None
    df = pd.read_csv(f, usecols=lambda c: c in
                     ['TIMESTAMP', 'LE_F_MDS', 'LE_F_MDS_QC', 'LE_CORR'])
    for c in ['LE_F_MDS', 'LE_CORR', 'LE_F_MDS_QC']:
        df[c] = pd.to_numeric(df[c], errors='coerce')
        df.loc[df[c] <= -9990, c] = np.nan
    # DD/MM da LE_F_MDS_QC = ULUSH (0-1, o'lchangan yarim-soatlar ulushi). Asosan-o'lchangan kunlar.
    fmds = df['LE_F_MDS'].where(df['LE_F_MDS_QC'] >= QC_DD_MIN)
    if tag == 'DD':
        df['date'] = pd.to_datetime(df['TIMESTAMP'].astype(int).astype(str), format='%Y%m%d')
        return pd.DataFrame({'date': df['date'],
                             'et_fmds': fmds * LE2ET, 'et_corr': df['LE_CORR'] * LE2ET})
    else:
        ts = df['TIMESTAMP'].astype(int).astype(str)
        yr = ts.str[:4].astype(int); mo = ts.str[4:6].astype(int)
        nd = pd.to_datetime(dict(year=yr, month=mo, day=1)).dt.days_in_month
        return pd.DataFrame({'year': yr, 'month': mo,
                             'et_fmds': fmds * LE2ET * nd, 'et_corr': df['LE_CORR'] * LE2ET * nd})


# ============================================================
# OBS — Bushland lizimetr
# ============================================================
def _bush_files():
    return {'E': os.path.join(GT, 'lyzimetr', '2021_Cotton_E_Lys_ClimDat.xlsx'),
            'W': os.path.join(GT, 'lyzimetr', '2021_Cotton_W_Lys_ClimDat.xlsx')}


def _find(col, pattern):
    """col = {stripped_name: orig}; pattern regex (case-insens., ichki bo'shliq moslashuvchan)."""
    for nm, orig in col.items():
        if re.search(pattern, re.sub(r'\s+', ' ', nm), re.I):
            return orig
    raise KeyError(pattern)


def obs_bush_inst():
    """Bushland 15-min overpass ±30min: RN, AIR_TEMP, ALBEDO, LST, G0 (4 lys o'rtacha)."""
    op = OVERPASS['Bushland_lys']['local_hour']
    recs = []
    for side, f in _bush_files().items():
        if not os.path.exists(f):
            continue
        sh = [s for s in pd.ExcelFile(f).sheet_names if s.strip().endswith('15-Min') and 'Dic' not in s]
        if not sh:
            continue
        raw = pd.read_excel(f, sheet_name=sh[0], header=0)
        col = {str(c).strip(): c for c in raw.columns}
        yr = pd.to_numeric(raw[_find(col, r'^Year$')], errors='coerce')
        doy = pd.to_numeric(raw[_find(col, r'^Doy$')], errors='coerce')
        tt = pd.to_numeric(raw[_find(col, r'^Time')], errors='coerce')
        hh = (tt // 100) + (tt % 100) / 60.0
        date = pd.to_datetime(yr.astype('Int64').astype(str), format='%Y', errors='coerce') \
               + pd.to_timedelta(doy - 1, unit='D')
        mask = (hh >= op - 0.5) & (hh <= op + 0.5)
        sub = raw[mask].copy(); dts = date[mask]
        def g(pat):
            cs = [orig for nm, orig in col.items() if re.search(pat, nm)]
            if not cs:
                return pd.Series(np.nan, index=sub.index)
            return sub[cs].apply(pd.to_numeric, errors='coerce').mean(axis=1)
        rn = g(r'^[NS][EW] Rn in W')
        if rn.isna().all():
            rn = g(r'^[NS][EW] Calculated Rn')
        rs_in = g(r'^[NS][EW] Rs in W'); rs_out = g(r'^[NS][EW] Rs Reflected')
        alb = rs_out / rs_in.where(rs_in > 50)
        at = g(r'^[NS][EW] Air Temp')
        lst = g(r'^[NS][EW] Nadir Surface Temp')
        g0 = g(r'^[NS][EW] .*Soil Heat Flux')
        recs.append(pd.DataFrame({'date': dts.values, 'RN': rn.values, 'AIR_TEMP': at.values,
                                  'ALBEDO': alb.values, 'LST': lst.values, 'G0': g0.values}))
    if not recs:
        return None
    a = pd.concat(recs, ignore_index=True).dropna(subset=['date'])
    a['date'] = pd.to_datetime(a['date']).dt.normalize()
    return a.groupby('date', as_index=False).mean()


def obs_bush_daily():
    lyz = os.path.join(GT, 'lyzimetr')
    series = []
    for f in _bush_files().values():
        if not os.path.exists(f):
            continue
        sh = [s for s in pd.ExcelFile(f).sheet_names if s.strip().endswith('Daily') and 'Dic' not in s]
        raw = pd.read_excel(f, sheet_name=sh[0], header=0)
        col = {str(c).strip(): c for c in raw.columns}
        etc = [o for n, o in col.items() if re.match(r'^[NS][EW] ET from Catch Precip', n)]
        yr = pd.to_numeric(raw[_find(col, r'^Year$')], errors='coerce')
        doy = pd.to_numeric(raw[_find(col, r'^DOY$')], errors='coerce')
        date = pd.to_datetime(yr.astype('Int64').astype(str), format='%Y', errors='coerce') \
               + pd.to_timedelta(doy - 1, unit='D')
        for ec in etc:
            series.append(pd.DataFrame({'date': date, 'et': pd.to_numeric(raw[ec], errors='coerce')}))
    a = pd.concat(series, ignore_index=True).dropna(subset=['date'])
    daily = a.groupby('date', as_index=False)['et'].mean()
    daily['date'] = pd.to_datetime(daily['date']).dt.normalize()
    return pd.DataFrame({'date': daily['date'], 'et_fmds': daily['et'], 'et_corr': daily['et']})


def obs_bush_monthly():
    dd = obs_bush_daily()
    dd['year'] = dd['date'].dt.year; dd['month'] = dd['date'].dt.month
    mm = dd.groupby(['year', 'month'], as_index=False)['et_fmds'].sum()
    return pd.DataFrame({'year': mm['year'], 'month': mm['month'],
                         'et_fmds': mm['et_fmds'], 'et_corr': mm['et_fmds']})


# ============================================================
# Metrikalar yig'ish
# ============================================================
def metric_row(level, mode, site, param, ref, model_vals, obs_vals):
    s = val_stats(model_vals, obs_vals)
    p = np.asarray(model_vals, float); o = np.asarray(obs_vals, float)
    msk = np.isfinite(p) & np.isfinite(o)
    r = dict(level=level, mode=mode, site=site, param=param, ref=ref,
             obs_mean=round(float(np.nanmean(o[msk])), 3) if msk.any() else np.nan,
             model_mean=round(float(np.nanmean(p[msk])), 3) if msk.any() else np.nan)
    r.update(s)
    return r


# INST parametr xaritasi: model_col -> (param_nomi, obs_col, model_transform)
INST_MAP_AMF = [
    ('RN_mean',       'RN',       'RN',       lambda x: x),
    ('LAMBDA_E_mean', 'LE',       'LE_fmds',  lambda x: x),
    ('LAMBDA_E_mean', 'LE',       'LE_corr',  lambda x: x),
    ('AIR_TEMP_mean', 'AIR_TEMP', 'AIR_TEMP', lambda x: x - KELVIN),   # K→°C
    ('ALBEDO_mean',   'ALBEDO',   'ALBEDO',   lambda x: x),
    ('USTAR_mean',    'USTAR',    'USTAR',    lambda x: x),
    ('LST_mean',      'LST',      'LST',      lambda x: x - KELVIN),   # K→°C
]
INST_MAP_BUSH = [
    ('RN_mean',       'RN',       'RN',       lambda x: x),
    ('AIR_TEMP_mean', 'AIR_TEMP', 'AIR_TEMP', lambda x: x - KELVIN),
    ('ALBEDO_mean',   'ALBEDO',   'ALBEDO',   lambda x: x),
    ('LST_mean',      'LST',      'LST',      lambda x: x - KELVIN),
    ('G0_mean',       'G0',       'G0',       lambda x: x),
]


def build_inst():
    M = load_model_inst()
    recs, pairs = [], []
    for site in sorted(M['site'].unique()):
        if site == 'Bushland_lys':
            o = obs_bush_inst(); mp = INST_MAP_BUSH
        else:
            o = obs_amf_inst(site); mp = INST_MAP_AMF
        if o is None:
            print(f'  INST {site}: obs yo\'q'); continue
        msite = M[M['site'] == site]
        for mode in msite['mode'].unique():
            sub = msite[msite['mode'] == mode].merge(o, on='date', how='inner', suffixes=('', '_obs'))
            if sub.empty:
                continue
            for mcol, pname, ocol, tf in mp:
                if mcol not in sub or ocol not in sub:
                    continue
                mv = tf(sub[mcol]); ov = sub[ocol]
                good = np.isfinite(mv) & np.isfinite(ov)
                if good.sum() >= 3:
                    ref = 'LE_CORR' if ocol.endswith('corr') else ('LE_F_MDS' if ocol.endswith('fmds') else '-')
                    recs.append(metric_row('INST', mode, site, pname, ref, mv[good], ov[good]))
                    pr = sub.loc[good, ['date']].copy()
                    pr['mode'] = mode; pr['site'] = site; pr['param'] = pname; pr['ref'] = ref
                    pr['model'] = mv[good].values; pr['obs'] = ov[good].values
                    pairs.append(pr)
        print(f'  INST {site}: OK')
    Pall = pd.concat(pairs, ignore_index=True) if pairs else pd.DataFrame()
    if not Pall.empty:                                  # POOLED (barcha sayt) — site='ALL'
        for (mode, param, ref), g in Pall.groupby(['mode', 'param', 'ref']):
            g2 = g.dropna(subset=['model', 'obs'])
            if len(g2) >= 3:
                recs.append(metric_row('INST', mode, 'ALL', param, ref, g2['model'], g2['obs']))
    return pd.DataFrame(recs), Pall


def build_period(kind):
    """kind='DAILY'|'MONTHLY' — ET only, ref F_MDS & CORR, model mean & median."""
    M = load_model_simple(kind)
    recs, pairs = [], []
    for site in sorted(M['site'].unique()):
        if site == 'Bushland_lys':
            o = obs_bush_daily() if kind == 'DAILY' else obs_bush_monthly()
        else:
            o = obs_amf_period(site, 'DD' if kind == 'DAILY' else 'MM')
        if o is None:
            print(f'  {kind} {site}: obs yo\'q'); continue
        key = ['date'] if kind == 'DAILY' else ['year', 'month']
        sub = M[M['site'] == site].merge(o, on=key, how='inner')
        for mode in sub['mode'].unique():
            s = sub[sub['mode'] == mode]
            for mcol in ['et_mean', 'et_median']:
                for rcol in ['et_fmds', 'et_corr']:
                    good = np.isfinite(s[mcol]) & np.isfinite(s[rcol])
                    if good.sum() >= 3:
                        ref = ('LE_CORR' if rcol == 'et_corr' else 'LE_F_MDS')
                        recs.append(metric_row(kind, mode, site, 'ET_' + mcol.split('_')[1],
                                               ref, s.loc[good, mcol], s.loc[good, rcol]))
        # pairs (model=mean & median)
        pp = sub[['mode'] + key + ['et_mean', 'et_median', 'et_fmds', 'et_corr']].copy()
        pp['site'] = site; pairs.append(pp)
        print(f'  {kind} {site}: {len(sub)} qator')
    Pall = pd.concat(pairs, ignore_index=True) if pairs else pd.DataFrame()
    if not Pall.empty:                                  # POOLED (barcha sayt) — site='ALL'
        for mode in Pall['mode'].unique():
            s = Pall[Pall['mode'] == mode]
            for mcol in ['et_mean', 'et_median']:
                for rcol in ['et_fmds', 'et_corr']:
                    good = np.isfinite(s[mcol]) & np.isfinite(s[rcol])
                    if good.sum() >= 3:
                        ref = 'LE_CORR' if rcol == 'et_corr' else 'LE_F_MDS'
                        recs.append(metric_row(kind, mode, 'ALL', 'ET_' + mcol.split('_')[1],
                                               ref, s.loc[good, mcol], s.loc[good, rcol]))
    return pd.DataFrame(recs), Pall


def order_metrics(R):
    if R.empty:
        return R
    R = R.copy()
    R['mode'] = pd.Categorical(R['mode'], [m for m in MODES], ordered=True)
    cols = ['level', 'mode', 'site', 'param', 'ref', 'obs_mean', 'model_mean'] + METRIC_ORDER
    return R.sort_values(['param', 'site', 'mode'])[cols]


NOTES = [
    ['DARAJA', 'PARAMETR', 'MODEL manba', 'OBS manba', 'IZOH'],
    ['INST', 'RN', 'RN_mean (W/m²)', 'AMF NETRAD / Bushland Rn', 'overpass soati'],
    ['INST', 'LE', 'LAMBDA_E_mean (W/m²)', 'AMF LE_F_MDS & LE_CORR', 'gap-fill CHIQARILDI: QC==0 (o\'lchangan) + u*>=0.1; Bushland LE_inst yo\'q'],
    ['INST', 'AIR_TEMP', 'AIR_TEMP_mean (K→°C)', 'AMF TA_F_MDS / Bushland Air Temp', ''],
    ['INST', 'ALBEDO', 'ALBEDO_mean', 'SW_OUT/SW_IN / Bushland Rs_refl/Rs', 'SW_IN>50'],
    ['INST', 'USTAR', 'USTAR_mean', 'AMF USTAR', 'Bushland: yo\'q'],
    ['INST', 'LST', 'LST_mean (K→°C)', 'AMF LW_OUT (Stefan-Boltzmann, ε=0.98) / Bushland Nadir Surf.Temp', ''],
    ['INST', 'G0', 'G0_mean (W/m²)', 'Bushland 80mm Soil Heat Flux (4 o\'rt.)', 'AMF: G yo\'q'],
    ['INST', 'H', '—', '—', 'OBS yo\'q (FLUXMET H yo\'q; Bushland LE_inst yo\'q) → solishtirilmadi'],
    ['DAILY', 'ET', 'DAILY_ET mean & median (mm/kun)', 'AMF LE_F_MDS (QC ulush>=0.75) & LE_CORR ×0.035265', 'ochiq-osmon kun = MODELni sinaydi; Bushland 4-lys ET Catch Precip'],
    ['MONTHLY', 'ET', 'MONTHLY_ET mean & median (mm/oy)', 'AMF LE ×0.035265×kun', 'Bushland: kunlik ET yig\'indisi'],
    ['—', 'site=ALL', '', '', 'POOLED (barcha sayt birga); boshqa qatorlar = stratum (har sayt)'],
    ['—', 'Overpass', '', '', 'GEE Landsat system:time_start median; mahalliy standart soat (DST yo\'q)'],
    ['—', 'metrika', '', '', 'R2=Nash-Sutcliffe(1:1); RMSE_pct/MBE_pct = kuzatuv o\'rt.dan %; verdict: RMSE<=15% & |MBE|<=10% (ET uchun)'],
    ['—', 'bias/scatter', '', '', 'ubRMSE=bias\'siz RMSE (scatter); bias_share=MBE²/MSE (>0.5=bias hukmron, yig\'ilishда saqlanadi)'],
    ['—', 'r2_pearson', '', '', 'DIQQAT (deck sl.72): mavsumiy R² shishirilgan/kam-ma\'noli; NSE/RMSE/MBE\'ni yetakchi qil. Oy-ichi R² bu yerda hisoblanmadi (atigi ~6 minora)'],
    ['—', 'footprint', '', '', 'u*+QC filtri qo\'llandi; geometrik shamol-sektor maydon-poligonisiz qilinmadi (katta bir jinsli maydonlarda kichik ta\'sir); to\'liq Kljun H yo\'qligi sabab qilinmadi'],
    ['—', 'reference', '', '', 'flux minora 10-30% o\'zi noaniq (deck sl.59); LE_CORR(yopiq) vs LE_F_MDS(ochiq) 10-30% farq'],
    ['—', 'CHEK', '', '', 'Yetishmagan eksport (Minnesota/Arkansas/ba\'zi Milliy_Kc) kiritilmagan; hech qanday reference-korreksiya QILINMADI (xom SEBAL)'],
]


def bydate_param(pairs, level, param):
    """Bitta parametr uchun HAR SANA jadvali: obs + har model yonma-yon.
       INST: value=model(param); DAILY/MONTHLY: param='ET_mean'|'ET_median'."""
    mcols = [m for m in MODES]
    if level == 'INST':
        p = pairs[pairs['param'] == param]
        idx = ['site', 'ref', 'date']
        piv = p.pivot_table(index=idx, columns='mode', values='model', aggfunc='first')
        obs = p.groupby(idx)['obs'].first()
        by = obs.to_frame('obs_kuzatuv').join(piv).reset_index()
        cols = idx + ['obs_kuzatuv'] + [m for m in mcols if m in by.columns]
        by = by[cols].sort_values(['site', 'ref', 'date'])
        # LE dan boshqa parametrlarda ref = '-' → ustunni tashlaymiz
        if (by['ref'] == '-').all():
            by = by.drop(columns=['ref'])
    else:
        which = 'et_mean' if param == 'ET_mean' else 'et_median'
        key = ['site', 'date'] if level == 'DAILY' else ['site', 'year', 'month']
        piv = pairs.pivot_table(index=key, columns='mode', values=which, aggfunc='first')
        obs = pairs.groupby(key)[['et_fmds', 'et_corr']].first()
        by = obs.join(piv).reset_index().rename(
            columns={'et_fmds': 'obs_LE_F_MDS', 'et_corr': 'obs_LE_CORR'})
        cols = key + ['obs_LE_F_MDS', 'obs_LE_CORR'] + [m for m in mcols if m in by.columns]
        by = by[cols].sort_values(key)
    numc = by.select_dtypes('number').columns
    by[numc] = by[numc].round(3)
    return by


def write_excel(path, metrics, pairs, level):
    if level == 'INST':
        params = sorted(pairs['param'].unique()) if not pairs.empty else []
    else:
        params = ['ET_mean', 'ET_median']
    with pd.ExcelWriter(path, engine='openpyxl') as w:
        # metrics = YIG'MA xulosa (har model×sayt×param: R2, bias, RMSE...)
        order_metrics(metrics).to_excel(w, sheet_name='metrics', index=False)
        # HAR PARAMETR sahifasi = o'sha parametrning HAR SANA aniq qiymatlari (obs vs modellar)
        for pname in params:
            if pairs is None or pairs.empty:
                continue
            bydate_param(pairs, level, pname).to_excel(
                w, sheet_name=f'm_{pname}'[:31], index=False)
        pd.DataFrame(NOTES[1:], columns=NOTES[0]).to_excel(w, sheet_name='notes', index=False)
    print(f'  → {path}  ({len(metrics)} metrik-qator, {len(params)} parametr sahifa)')


def main():
    os.makedirs(OUT, exist_ok=True)
    print('INST...');    Ri, Pi = build_inst()
    print('DAILY...');   Rd, Pd = build_period('DAILY')
    print('MONTHLY...'); Rm, Pm = build_period('MONTHLY')
    write_excel(os.path.join(OUT, 'inst_validation.xlsx'),    Ri, Pi, 'INST')
    write_excel(os.path.join(OUT, 'daily_validation.xlsx'),   Rd, Pd, 'DAILY')
    write_excel(os.path.join(OUT, 'monthly_validation.xlsx'), Rm, Pm, 'MONTHLY')

    # qisqa konsol xulosa — INST, model=asosiy param bo'yicha n
    for name, R in [('INST', Ri), ('DAILY', Rd), ('MONTHLY', Rm)]:
        if R.empty:
            print(f'\n{name}: bo\'sh'); continue
        print(f'\n===== {name}: parametrlar × juftliklar =====')
        piv = R.groupby('param')['n'].agg(['count', 'sum'])
        print(piv.to_string())
    return Ri, Rd, Rm


if __name__ == '__main__':
    main()
