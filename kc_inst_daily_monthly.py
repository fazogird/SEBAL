# -*- coding: utf-8 -*-
"""
Lizimetr vs model — INST / DAILY / MONTHLY grafik + jadval.
FAQAT eksport qilingan BOR ma'lumot (qayta hisob YO'Q, fake YO'Q):
  - INST  (mm/soat): yangi scene CSV ET_INST_MM_HR = SEBAL_Milliy (energiya balans)
  - DAILY (mm/kun):  yangi scene CSV ET_24        = SEBAL_Milliy (energiya balans)
  - MONTHLY (mm/oy): yangi monthly CSV            = SEBAL_Milliy_Kc (NDVI-FAO56)
  Lizimetr qiymatlari: mavjud cmp_*_pairs.csv (haqiqiy o'lchov).
DIQQAT: INST/DAILY papkada Kc EMAS (Kc faqat oylik). Ular sahna energiya-balansi.
"""
import os
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

RES = r'D:/ET_2026/lyzimetr/25114670/result'
FLD = (r'D:/ET_2026/lyzimetr/result_sebal/'
       r'SEBAL_Milliy_Kc_Bushland_2021-20260812T113800Z-1-001/'
       r'SEBAL_Milliy_Kc_Bushland_2021')
OUT = os.path.join(RES, 'openet')
MN = {3: 'Mar', 4: 'Apr', 5: 'May', 6: 'Jun', 7: 'Jul', 8: 'Aug', 9: 'Sep', 10: 'Oct'}

sc = pd.read_csv(FLD + '/SEBAL_csv_scene_P30_R36.csv')
sc = sc.rename(columns={'name': 'parcel'})
mo = pd.read_csv(FLD + '/SEBAL_csv_monthly_P30_R36.csv').rename(columns={'name': 'parcel'})


def per_date_table(pairs_csv, sc_col, unit, label):
    """cmp_*_pairs (lizimetr) + scene CSV (model) → har sana o'rtacha jadval."""
    lp = pd.read_csv(pairs_csv).rename(columns={'sana': 'date', 'lizimetr': 'parcel',
                                                'lizimetr_qiymat': 'lys'})
    m = sc[['date', 'parcel', sc_col]].rename(columns={sc_col: 'model'})
    j = lp.merge(m, on=['date', 'parcel'], how='inner')
    g = (j.groupby('date').agg(lizimetr=('lys', 'mean'), natija=('model', 'mean'))
         .reset_index())
    g['bias'] = (g['natija'] - g['lizimetr']).round(4)
    g['lizimetr'] = g['lizimetr'].round(4); g['natija'] = g['natija'].round(4)
    g = g.rename(columns={'date': 'sana'})
    g.attrs['unit'] = unit; g.attrs['label'] = label
    return g[['sana', 'lizimetr', 'natija', 'bias']]


# --- INST (mm/soat) ---
inst = per_date_table(RES + '/cmp_instant_pairs.csv', 'ET_INST_MM_HR_mean',
                      'mm/soat', 'SEBAL_Milliy (sahna, inst)')
# --- DAILY (mm/kun) ---
daily = per_date_table(RES + '/cmp_daily_pairs.csv', 'ET_24_mean',
                       'mm/kun', 'SEBAL_Milliy (sahna, kunlik)')
# --- MONTHLY (mm/oy) — Kc ---
lm = pd.read_csv(RES + '/cmp_monthly_pairs.csv').rename(
    columns={'oy': 'month', 'lizimetr': 'parcel', 'lizimetr_mm': 'lys'})
lm['mn'] = lm['month'].map({v: k for k, v in MN.items()})
mo['oy'] = mo['month'].map(MN)
mj = lm.merge(mo[['month', 'parcel', 'mean']].rename(columns={'mean': 'model'}),
              left_on=['mn', 'parcel'], right_on=['month', 'parcel'])
mg = (mj.groupby(['mn', 'month_x']).agg(lizimetr=('lys', 'mean'),
      natija=('model', 'mean')).reset_index().sort_values('mn'))
mg['bias'] = (mg['natija'] - mg['lizimetr']).round(2)
mg['lizimetr'] = mg['lizimetr'].round(2); mg['natija'] = mg['natija'].round(2)
monthly = mg.rename(columns={'month_x': 'sana'})[['sana', 'lizimetr', 'natija', 'bias']]

# ---- Excel (3 sheet) ----
xlsx = os.path.join(OUT, 'lizimetr_vs_model_INST_DAILY_MONTHLY.xlsx')
with pd.ExcelWriter(xlsx, engine='openpyxl') as xw:
    inst.to_excel(xw, 'INST_mm_soat', index=False)
    daily.to_excel(xw, 'DAILY_mm_kun', index=False)
    monthly.to_excel(xw, 'MONTHLY_mm_oy_Kc', index=False)

# ---- Grafiklar (x=sana, y=qiymat) ----
def plot(df, unit, title, fname, xrot=45):
    fig, ax = plt.subplots(figsize=(11, 5.2))
    x = range(len(df))
    ax.plot(x, df['lizimetr'], 'o-', color='#1a9850', lw=2, ms=6, label='Lizimetr')
    ax.plot(x, df['natija'], 's--', color='#d73027', lw=2, ms=6, label='Model natija')
    ax.set_xticks(list(x)); ax.set_xticklabels(df['sana'], rotation=xrot, ha='right', fontsize=9)
    ax.set_ylabel(f'ET, {unit}', fontsize=11); ax.set_xlabel('Sana', fontsize=11)
    ax.set_title(title, fontsize=12, fontweight='bold')
    ax.legend(fontsize=11); ax.grid(alpha=0.25)
    fig.tight_layout()
    p = os.path.join(OUT, fname); fig.savefig(p, dpi=140); plt.close(fig)
    return p

p1 = plot(inst, 'mm/soat', 'INST — Lizimetr vs SEBAL_Milliy (overpass, mavjud tasvir sanalari)',
          'cmp_INST.png')
p2 = plot(daily, 'mm/kun', 'DAILY — Lizimetr vs SEBAL_Milliy (overpass kun, mavjud tasvirlar)',
          'cmp_DAILY.png')
p3 = plot(monthly, 'mm/oy', 'MONTHLY — Lizimetr vs SEBAL_Milliy_Kc (oylik)',
          'cmp_MONTHLY.png', xrot=0)

print("=== INST (mm/soat) ===\n", inst.to_string(index=False))
print("\n=== DAILY (mm/kun) ===\n", daily.to_string(index=False))
print("\n=== MONTHLY (mm/oy, Kc) ===\n", monthly.to_string(index=False))
print(f"\nExcel: {xlsx}\nPNG: {p1}\n     {p2}\n     {p3}")
