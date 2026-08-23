# -*- coding: utf-8 -*-
"""
OFFLINE PROTOTIP — NDVI-langan FAO-56 QO'SH koeffitsient (Kcb+Ke) upscaling.
Maqsad: rejim kodini yozishdan OLDIN R² ko'tarilishini isbotlash + Kc egri kalibrlash.

ET_kun = (Kcb(NDVI) + Ke(suv balansi)) × ETo_kun     [FAO-56]
  Kcb = clamp(a·NDVI + b, 0, kcb_max)                (kanopiy transpiratsiya)
  Ke  = kunlik topsoil suv balansi (yog'in+sug'orish ho'llash → tuproq bug'lanishi)

Kirish (hammasi XOM/o'lchangan — to'qima yo'q):
  - NDVI: SEBAL sahna CSV (per parcel, 15 sana) → kunlik lineer interp
  - ETo, precip: GRIDMET kunlik (Bushland nuqta)
  - sug'orish/yog'in hodisasi: lizimetr kunlik token (0/1)
  - haqiqat: lizimetr ET_catch_mm (per parcel, kunlik → oylik yig'indi)
"""
import numpy as np
import pandas as pd
import ee

RESULT = r'D:/ET_2026/lyzimetr/25114670/result'
DAILY_XLSX = r'D:/ET_2026/lyzimetr/25114670/data/lyz_2021_daily.xlsx'
SCENE_CSV = (r'D:/ET_2026/lyzimetr/result_sebal/'
             r'SEBAL_Milliy_Bushland_CSV_2021-20260728T090331Z-1-001/'
             r'SEBAL_Milliy_Bushland_CSV_2021/SEBAL_csv_scene_P30_R36.csv')
PARCELS = ['NE', 'SE', 'NW', 'SW']
MONTHS = list(range(3, 11))                     # Mar..Oct
TEW, REW = 20.0, 9.0                            # Saxton (hot-pixel loglaridan ~)
KE_SCALE = 1.0                                   # Ke miqyosi (grid search'da o'rnatiladi)
SEN_ON = True                                    # senescence tuzatishi
SEN_LEN = 45.0                                   # cho'qqidan keyin Kcb tushish davri (kun)
KCB_END_FRAC = 0.40                              # Kcb cho'qqidan qaysi ulushgacha tushadi


def gridmet_daily():
    ee.Initialize(project='carbon-science-461016-q2')
    pt = ee.Geometry.Point([-102.0955, 35.1882])
    ic = (ee.ImageCollection('IDAHO_EPSCOR/GRIDMET')
          .filterDate('2021-01-01', '2022-01-01').select(['eto', 'etr', 'pr']))
    rows = ic.getRegion(pt, 4000).getInfo()
    hdr = rows[0]
    df = pd.DataFrame(rows[1:], columns=hdr)
    df['date'] = pd.to_datetime(df['time'], unit='ms')
    df = df[['date', 'eto', 'etr', 'pr']].astype(
        {'eto': float, 'etr': float, 'pr': float}).sort_values('date')
    df['doy'] = df['date'].dt.dayofyear
    return df.set_index('doy')


def ndvi_daily_by_parcel():
    sc = pd.read_csv(SCENE_CSV)
    sc['date'] = pd.to_datetime(sc['date'])
    sc['doy'] = sc['date'].dt.dayofyear
    out = {}
    for p in PARCELS:
        s = sc[sc['name'] == p][['doy', 'NDVI_mean']].sort_values('doy')
        full = pd.Series(index=range(1, 366), dtype=float)
        full.loc[s['doy'].values] = s['NDVI_mean'].values
        full = full.interpolate('linear', limit_direction='both')
        out[p] = full
    return out


def lys_daily():
    d = pd.read_excel(DAILY_XLSX, 'Comparison_Daily')
    d = d[['DOY', 'Lysimeter', 'ET_catch_mm', 'precip_token', 'irrigation_token']]
    return d


def ke_series(doy_index, ndvi, eto, wet_flag, kcb, kcb_max, kc_max=1.20, few_max=1.0):
    """FAO-56 topsoil suv balansi → kunlik Ke.
    few = 1 − fc (fc = kanopiy qoplami, NDVIdan): kanopiy yopilganda Ke→0."""
    De = TEW
    Ke = pd.Series(index=doy_index, dtype=float)
    for doy in doy_index:
        if wet_flag.get(doy, 0) >= 1:            # ho'llash hodisasi → topsoil to'la
            De = 0.0
        # fc — kanopiy qoplami NDVIdan (FAO-56): NDVI 0.15→0.85 = fc 0→1
        fc = min(max((ndvi.get(doy, 0.15) - 0.15) / (0.85 - 0.15), 0.0), 1.0)
        few = min(1.0 - fc, few_max)             # ochiq+ho'l tuproq ulushi
        Kr = 1.0 if De <= REW else max(0.0, (TEW - De) / (TEW - REW))
        ke = min(Kr * (kc_max - kcb.get(doy, 0.0)), few * kc_max)
        ke = max(ke, 0.0)
        Ke[doy] = ke
        E = ke * eto.get(doy, 0.0)               # tuproq bug'lanishi (mm)
        De = min(TEW, De + E)                     # keyingi kunga depletion
    return Ke * KE_SCALE


def run(a, b, kcb_max, kc_max, few, gm, ndvi_p, lysd):
    """Berilgan Kc parametrlar bilan oylik ET → (juftliklar df)."""
    rows = []
    for p in PARCELS:
        ndvi = ndvi_p[p]
        kcb = (a * ndvi + b).clip(0, kcb_max)
        # ho'llash: shu parcel field'i (E: NE/SE, W: NW/SW)
        field_lys = p
        wl = lysd[lysd['Lysimeter'] == field_lys].set_index('DOY')
        wet = (wl['precip_token'].fillna(0) + wl['irrigation_token'].fillna(0)).clip(0, 1)
        doy_idx = list(range(60, 320))           # Mar..Okt oralig'i
        Ke = ke_series(doy_idx, ndvi, gm['eto'], wet.to_dict(),
                       {d: kcb.get(d, 0) for d in doy_idx}, kcb_max, kc_max, few)
        # senescence: cho'qqi NDVI kunidan keyin Kcb pasayadi (FAO-56 late-season)
        peak_doy = ndvi.loc[[d for d in doy_idx]].idxmax()
        et_day = pd.Series(index=doy_idx, dtype=float)
        for doy in doy_idx:
            k = kcb.get(doy, 0.0)
            if SEN_ON and doy > peak_doy:
                k *= 1.0 - (1.0 - KCB_END_FRAC) * min((doy - peak_doy) / SEN_LEN, 1.0)
            et_day[doy] = (k + Ke[doy]) * gm['eto'].get(doy, 0.0)
        # oylik yig'indi (pred) va lizimetr (obs)
        dd = pd.to_datetime('2021-01-01') + pd.to_timedelta(np.array(doy_idx) - 1, 'D')
        mon = pd.Series(dd.month, index=doy_idx)
        for m in MONTHS:
            pred = et_day[mon == m].sum()
            obs = wl.loc[wl.index.isin([i for i in doy_idx if mon.get(i) == m]),
                         'ET_catch_mm'].sum()
            rows.append({'parcel': p, 'month': m, 'pred': pred, 'obs': obs})
    return pd.DataFrame(rows)


def stats(df):
    d = df.dropna()
    d = d[(d['obs'] > 0)]
    p, o = d['pred'].values, d['obs'].values
    e = p - o
    r = np.corrcoef(p, o)[0, 1]
    return dict(n=len(d), R2=round(r * r, 3), MBE=round(e.mean(), 1),
               MAE=round(np.abs(e).mean(), 1), RMSE=round(np.sqrt((e**2).mean()), 1))


def main():
    gm = gridmet_daily()
    ndvi_p = ndvi_daily_by_parcel()
    lysd = lys_daily()
    print("  ✅ GRIDMET + NDVI + lizimetr yuklandi")
    print(f"     GRIDMET 2021 ETo yig'indi (Mar-Okt): "
          f"{gm.loc[60:319,'eto'].sum():.0f} mm")

    # --- Kalibratsiya: grid search + SENESCENCE, MAQSAD = min RMSE ---
    global KE_SCALE, SEN_LEN, KCB_END_FRAC
    a, b, kc_max = 1.10, -0.10, 1.15               # oldingi eng yaxshidan qat'iy
    best = None
    for kcb_max in [0.90, 1.00, 1.10]:
        for ke_scale in [0.3, 0.5]:
            for sen_len in [30.0, 45.0, 60.0]:
                for kcb_end in [0.25, 0.35, 0.45]:
                    KE_SCALE = ke_scale; SEN_LEN = sen_len; KCB_END_FRAC = kcb_end
                    df = run(a, b, kcb_max, kc_max, 1.0, gm, ndvi_p, lysd)
                    st = stats(df)
                    score = (-st['RMSE'], st['R2'])
                    if best is None or score > best[0]:
                        best = (score, dict(a=a, b=b, kcb_max=kcb_max, kc_max=kc_max,
                                ke_scale=ke_scale, sen_len=sen_len, kcb_end=kcb_end), st, df)
    _, par, st, df = best
    KE_SCALE = par['ke_scale']; SEN_LEN = par['sen_len']; KCB_END_FRAC = par['kcb_end']
    print("\n  === ENG YAXSHI KALIBRATSIYA (senescence bilan) ===")
    print(f"    Kcb = clamp({par['a']}·NDVI + ({par['b']}), 0, {par['kcb_max']})")
    print(f"    Kc_max={par['kc_max']}  Ke_scale={par['ke_scale']}  "
          f"SEN_len={par['sen_len']}  Kcb_end_frac={par['kcb_end']}")
    print(f"    → n={st['n']}  R2={st['R2']}  MBE={st['MBE']}  "
          f"MAE={st['MAE']}  RMSE={st['RMSE']}")
    print("\n  === OYMA-OY (o'rtacha, 4 parcel) ===")
    g = df.groupby('month').agg(obs=('obs', 'mean'), pred=('pred', 'mean'))
    g['xato'] = (g['pred'] - g['obs']).round(1)
    print(g.round(1).to_string())
    print("\n  === ESKI SEBAL_Milliy (taqqoslash) ===")
    print("    R2=0.548  MBE=4.4  MAE=40.2  RMSE=45.6")
    df.to_csv(RESULT + '/openet/proto_ndvi_kc_oylik.csv', index=False,
              encoding='utf-8-sig')
    print(f"\n  💾 {RESULT}/openet/proto_ndvi_kc_oylik.csv")


if __name__ == '__main__':
    main()
