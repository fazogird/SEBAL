# -*- coding: utf-8 -*-
"""
M-SEBAL PROTOTIP — IZOLYATSIYA (ishlab turgan energy_balance.py ga TEGMAYDI).
Allaqachon chiqarilgan SEBAL parametrlaridan (instant_diag Excel) M-SEBAL trapezoid
EF/ET ni OFFLINE hisoblaydi, lizimetr + SEBAL bilan solishtiradi. Production'ga NOL ta'sir.

Trapezoid (Long&Singh 2012 / Moran 1994):
  Issiq chekka (ET=0):  Ts_max = Ta + (Rn − G)·rah / (ρ·cp)      [LE=0 → H=Rn−G]
  Sovuq chekka (ET=max): Ts_min = Ta
  EF = (Ts_max − Ts) / (Ts_max − Ts_min)   [0..1]
  LE = EF·(Rn − G);  ET(mm/soat) = LE·3600 / λ
Bare piksel Ts < Ts_max bo'lsa EF>0 (SEBAL da soxta 0 bo'lardi).
"""
import pandas as pd, numpy as np
RES = r'D:/ET_2026/lyzimetr/25114670/result'
XLS = RES + '/instant_diag_bushland_2021.xlsx'
OUT = RES + '/M_SEBAL/msebal_proto_bushland_2021.xlsx'
CP = 1004.0        # havo issiqlik sig'imi J/kg/K
LAMBDA = 2.45e6    # bug'lanish yashirin issiqligi J/kg

df = pd.read_excel(XLS, sheet_name='HAMMASI')
df['sana'] = df['sana'].astype(str).str[:10]
need = ['RN', 'G0', 'RAH', 'AIR_TEMP', 'LST', 'RHO_AIR', 'NDVI', 'ET_INST_MM_HR', 'lys_inst']
print("  Ustunlar bor:", [c for c in need if c in df.columns])
print("  YO'Q:", [c for c in need if c not in df.columns])

Ta = df['AIR_TEMP']            # K (SEBAL ERA5)
Rn, G, rah = df['RN'], df['G0'], df['RAH']
rho = df['RHO_AIR']
Ts = df['LST']                 # K (SMW)

# --- M-SEBAL trapezoid (per-piksel; prototip) ---
dT_max = (Rn - G) * rah / (rho * CP)      # issiq chekka dT (LE=0)
Ts_max = Ta + dT_max
Ts_min = Ta
df['Ts_max_C'] = (Ts_max - 273.15).round(2)
df['EF_mseb'] = ((Ts_max - Ts) / (Ts_max - Ts_min)).clip(0, 1).round(3)
LE = df['EF_mseb'] * (Rn - G)
df['ET_mseb'] = (LE * 3600 / LAMBDA).clip(lower=0).round(4)    # mm/soat
df['ET_sebal'] = df['ET_INST_MM_HR'].round(4)
df['lys'] = df['lys_inst'].round(4)
df['bias_sebal'] = (df.ET_sebal - df.lys).round(3)
df['bias_mseb'] = (df.ET_mseb - df.lys).round(3)

BROKEN = ['2021-03-03', '2021-05-06', '2021-06-23']
df['holat'] = np.where(df['sana'].isin(BROKEN), 'BUZUQ', 'sog')

# --- Sahna kesimida ---
g = df.groupby(['sana', 'holat']).agg(
    NDVI=('NDVI', 'mean'), Ts_C=('LST', lambda x: (x.mean()-273.15).round(1)),
    Ts_max_C=('Ts_max_C', 'mean'), EF_mseb=('EF_mseb', 'mean'),
    ET_sebal=('ET_sebal', 'mean'), ET_mseb=('ET_mseb', 'mean'),
    lys=('lys', 'mean')).round(3).reset_index()
g['bias_sebal'] = (g.ET_sebal - g.lys).round(2)
g['bias_mseb'] = (g.ET_mseb - g.lys).round(2)

pd.set_option('display.width', 200)
print("\n  === SAHNA KESIMIDA (instant ET, mm/soat) ===")
print(g.to_string(index=False))

v = df.dropna(subset=['lys'])
def st(b):
    return f"MBE={b.mean():+.3f} RMSE={np.sqrt((b**2).mean()):.3f} n={b.notna().sum()}"
print("\n  === UMUMIY (lizimetrga nisbatan) ===")
print("   SEBAL  :", st(v.bias_sebal))
print("   M-SEBAL:", st(v.bias_mseb))
print("\n  === BUZUQ 3 sahna (SEBAL=0 edi) — M-SEBAL nima beradi ===")
bb = df[df.holat == 'BUZUQ'].groupby('sana').agg(
    Ts_C=('LST', lambda x:(x.mean()-273.15).round(1)), Ts_max_C=('Ts_max_C','mean'),
    ET_sebal=('ET_sebal','mean'), ET_mseb=('ET_mseb','mean'), lys=('lys','mean')).round(3)
print(bb.to_string())

import os
os.makedirs(RES + '/M_SEBAL', exist_ok=True)
with pd.ExcelWriter(OUT, engine='openpyxl') as xw:
    g.to_excel(xw, 'sahna', index=False)
    df[['sana','nuqta','holat','NDVI','LST','Ts_max_C','EF_mseb','ET_sebal','ET_mseb','lys',
        'bias_sebal','bias_mseb']].round(4).to_excel(xw, 'nuqta', index=False)
print(f"\n  💾 {OUT}")
