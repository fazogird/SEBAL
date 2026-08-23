# -*- coding: utf-8 -*-
"""
Validatsiya metrikalari — model vs kuzatuv (ground truth) uchun to'liq to'plam.
val_stats(pred, obs) → dict: n, R2, r2_pearson, RMSE, MBE, MAE, MAPE, PBIAS,
                              NSE, willmott_d, slope, intercept.
Barcha ET/energiya-balans solishtirmalarida bir xil ishlatiladi.
"""
import numpy as np


def val_stats(pred, obs, drop_nonpos_obs=True):
    """
    pred, obs — array-like (mos juftliklar). NaN/None avtomatik tashlanadi.
    drop_nonpos_obs — MAPE uchun obs<=0 ni chiqarish (0 ga bo'linishdan himoya).
    """
    p = np.asarray(pred, dtype='float64')
    o = np.asarray(obs, dtype='float64')
    m = np.isfinite(p) & np.isfinite(o)
    p, o = p[m], o[m]
    if len(o) < 3:
        return dict(n=int(len(o)), R2=np.nan, r2_pearson=np.nan, RMSE=np.nan,
                    MBE=np.nan, MAE=np.nan, MAPE=np.nan, PBIAS=np.nan,
                    NSE=np.nan, willmott_d=np.nan, slope=np.nan, intercept=np.nan)
    e = p - o
    obar = o.mean()
    # Pearson r²
    r = np.corrcoef(p, o)[0, 1]
    r2_pearson = r * r
    # 1:1 ga nisbatan R² (= NSE bilan bir xil formula, lekin nomi R²)
    ss_res = np.sum(e ** 2)
    ss_tot = np.sum((o - obar) ** 2)
    nse = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
    # Willmott moslik indeksi d
    denom = np.sum((np.abs(p - obar) + np.abs(o - obar)) ** 2)
    d = 1.0 - ss_res / denom if denom > 0 else np.nan
    # regressiya (pred = slope·obs + intercept)
    slope, intercept = np.polyfit(o, p, 1)
    # MAPE / PBIAS
    if drop_nonpos_obs:
        mm = o > 0
        mape = np.mean(np.abs(e[mm] / o[mm])) * 100 if mm.sum() else np.nan
    else:
        mape = np.mean(np.abs(e / o)) * 100
    pbias = 100.0 * e.sum() / o.sum() if o.sum() != 0 else np.nan
    return dict(
        n=int(len(o)),
        R2=round(float(nse), 3),               # 1:1 (Nash-Sutcliffe formulasi)
        r2_pearson=round(float(r2_pearson), 3),
        RMSE=round(float(np.sqrt(ss_res / len(o))), 3),
        MBE=round(float(e.mean()), 3),
        MAE=round(float(np.abs(e).mean()), 3),
        MAPE=round(float(mape), 1),
        PBIAS=round(float(pbias), 1),
        NSE=round(float(nse), 3),
        willmott_d=round(float(d), 3),
        slope=round(float(slope), 3),
        intercept=round(float(intercept), 3),
    )


def le_to_et_daily(le_wm2):
    """LE (W/m², kunlik o'rtacha) → ET (mm/kun). λ=2.45 MJ/kg → 86400/2.45e6."""
    return np.asarray(le_wm2, dtype='float64') * 0.035265


def le_to_et_inst(le_wm2):
    """LE (W/m², lahzalik) → ET (mm/soat). 3600/2.45e6."""
    return np.asarray(le_wm2, dtype='float64') * 1.4694e-3


METRIC_ORDER = ['n', 'R2', 'r2_pearson', 'RMSE', 'MBE', 'MAE', 'MAPE',
                'PBIAS', 'NSE', 'willmott_d', 'slope', 'intercept']
