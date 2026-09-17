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
    pbar = p.mean()
    # Pearson r² — sof numpy (BLAS/corrcoef ishlatilmaydi: ba'zi MKL build'lar crash beradi)
    pm, om = p - pbar, o - obar
    spo = np.sum(pm * om)
    spp = np.sum(pm * pm)
    soo = np.sum(om * om)
    r = spo / np.sqrt(spp * soo) if (spp > 0 and soo > 0) else np.nan
    r2_pearson = r * r
    # 1:1 ga nisbatan R² (= NSE bilan bir xil formula, lekin nomi R²)
    ss_res = np.sum(e ** 2)
    ss_tot = soo
    nse = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
    # Willmott moslik indeksi d
    denom = np.sum((np.abs(p - obar) + np.abs(o - obar)) ** 2)
    d = 1.0 - ss_res / denom if denom > 0 else np.nan
    # regressiya (pred = slope·obs + intercept) — OLS, sof numpy (polyfit/lstsq emas)
    slope = spo / soo if soo > 0 else np.nan
    intercept = pbar - slope * obar
    # MAPE / PBIAS
    if drop_nonpos_obs:
        mm = o > 0
        mape = np.mean(np.abs(e[mm] / o[mm])) * 100 if mm.sum() else np.nan
    else:
        mape = np.mean(np.abs(e / o)) * 100
    pbias = 100.0 * e.sum() / o.sum() if o.sum() != 0 else np.nan
    # --- Özdoğan traning deck (Module 2) talablari ---
    mse = ss_res / len(o)
    rmse = np.sqrt(mse)
    mbe = e.mean()
    # bias/scatter ajratmasi: MSE = bias² + variance(residual)
    ub_rmse = np.sqrt(max(mse - mbe ** 2, 0.0))     # unbiased RMSE (= residual std)
    bias_share = (mbe ** 2) / mse if mse > 0 else np.nan   # >0.5 = ogohlantirish
    # kuzatuv o'rtachasidan % (chegara shu asosda: RMSE<=15%, |MBE|<=10%)
    denom = abs(obar) if obar != 0 else np.nan
    rmse_pct = 100.0 * rmse / denom if denom else np.nan
    mbe_pct = 100.0 * mbe / denom if denom else np.nan
    mae_pct = 100.0 * np.abs(e).mean() / denom if denom else np.nan
    verdict = ('PASS' if (np.isfinite(rmse_pct) and np.isfinite(mbe_pct)
                          and rmse_pct <= 15 and abs(mbe_pct) <= 10) else 'FAIL')
    return dict(
        n=int(len(o)),
        R2=round(float(nse), 3),               # 1:1 (Nash-Sutcliffe formulasi)
        r2_pearson=round(float(r2_pearson), 3),
        RMSE=round(float(rmse), 3),
        RMSE_pct=round(float(rmse_pct), 1),
        MBE=round(float(mbe), 3),
        MBE_pct=round(float(mbe_pct), 1),
        MAE=round(float(np.abs(e).mean()), 3),
        MAE_pct=round(float(mae_pct), 1),
        ubRMSE=round(float(ub_rmse), 3),       # scatter (bias'siz)
        bias_share=round(float(bias_share), 3),  # MBE²/MSE, >0.5 ogohlantirish
        verdict=verdict,                        # RMSE<=15% & |MBE|<=10% (ET uchun)
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


METRIC_ORDER = ['n', 'R2', 'r2_pearson', 'RMSE', 'RMSE_pct', 'MBE', 'MBE_pct',
                'MAE', 'MAE_pct', 'ubRMSE', 'bias_share', 'verdict',
                'MAPE', 'PBIAS', 'NSE', 'willmott_d', 'slope', 'intercept']
