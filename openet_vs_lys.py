# -*- coding: utf-8 -*-
"""
OpenET (har model alohida) vs Bushland lizimetr — OYLIK ET taqqoslash.

- Nuqta/footprint: SEBAL ishlatgan AYNAN 4 lizimetr poligoni (NE/SE/NW/SW),
  Bushland TX (35.186714, -102.094189). Koordinata soxta emas — SEBAL CSV .geo dan.
- OpenET CONUS GRIDMET MONTHLY v2.0 (AQSh — Bushland ichida).
- Lizimetr oylik ET_catch: result/cmp_monthly_pairs.csv (biz tozalagan, xom).
- Chiqish: har model uchun R2/MBE/MAE/RMSE (xuddi SEBAL_Milliy analitikasi) +
  oylik juftliklar. SEBAL_Milliy raqamlari yonma-yon (YAKUNIY_validatsiya.csv dan).

Hech qanday qiymat to'qib chiqarilmaydi; OpenET/lizimetr xom holicha olinadi.
"""
import os
import sys
import ee
import numpy as np
import pandas as pd

sys.path.insert(0, r'D:/Cloud_comp/Sebal/scripts')
from sebal_gee_v4 import main as sebal_main   # parcels_from_points (SEBAL bilan bir xil)

PROJECT = 'carbon-science-461016-q2'          # run_sebal bilan bir xil
RESULT_DIR = r'D:/ET_2026/lyzimetr/25114670/result'
MONTHLY_PAIRS = os.path.join(RESULT_DIR, 'cmp_monthly_pairs.csv')
OUT_DIR = os.path.join(RESULT_DIR, 'openet')
os.makedirs(OUT_DIR, exist_ok=True)

YEAR = 2021
MONTHS = {'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
          'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10}

# --- 4 lizimetr DALASI markazlari (SEBAL bilan AYNAN bir xil) ---
#   NE=LZ6, SE=LZ1 (drip);  NW=LZ4, SW=LZ3 (sprinkler).
#   parcels_from_points: 210×210m dala → −30m ichki bufer → ~150×150m yadro.
CENTERS = {
    'NE': [-102.0955385, 35.18816985],
    'SE': [-102.0955390, 35.18612583],
    'NW': [-102.0978919, 35.18817119],
    'SW': [-102.0979121, 35.18613288],
}

# --- OpenET modellar (EE MONTHLY v2.1 — eng yangi) ---
MODELS = {
    'SSEBop':   'projects/openet/assets/ssebop/conus/gridmet/monthly/v2_1',
    'geeSEBAL': 'projects/openet/assets/geesebal/conus/gridmet/monthly/v2_1',
    'PT-JPL':   'projects/openet/assets/ptjpl/conus/gridmet/monthly/v2_1',
    'eeMETRIC': 'projects/openet/assets/eemetric/conus/gridmet/monthly/v2_1',
    'DisALEXI': 'projects/openet/assets/disalexi/conus/gridmet/monthly/v2_1',
    'SIMS':     'projects/openet/assets/sims/conus/gridmet/monthly/v2_1',
    'Ensemble': 'projects/openet/assets/ensemble/conus/gridmet/monthly/v2_1',
}


def et_band(ic):
    """ET band nomini aniqlash (model='et', ensemble='et_ensemble_mad')."""
    names = ic.first().bandNames().getInfo()
    for cand in ('et', 'et_ensemble_mad', 'et_ensemble_sam'):
        if cand in names:
            return cand
    for n in names:
        if 'et' in n.lower():
            return n
    return names[0]


def main():
    ee.Initialize(project=PROJECT)
    print(f"  ✅ EE init (project={PROJECT})")

    # SEBAL bilan AYNAN bir xil parcel'lar (210m dala −30m → ~150m yadro)
    fc = sebal_main.parcels_from_points(CENTERS, size_m=210, inner_buffer_m=-30)
    region = fc.geometry()          # tayl tanlash uchun (filterBounds)

    # --- Lizimetr oylik (xom, biz tozalagan) ---
    lys = pd.read_csv(MONTHLY_PAIRS)          # oy,lizimetr,lizimetr_mm,SEBAL_mm,xato_%,kun
    lys = lys.rename(columns={'oy': 'month', 'lizimetr': 'lys',
                              'lizimetr_mm': 'lys_mm', 'SEBAL_mm': 'SEBAL_Milliy_mm'})
    lys['mon_n'] = lys['month'].map(MONTHS)
    print(f"  ✅ Lizimetr oylik juft: {len(lys)} qator ({lys['month'].nunique()} oy × "
          f"{lys['lys'].nunique()} lizimetr)")

    # --- OpenET: har model, har oy → 4 poligon mean ---
    rows = []
    for mname, cid in MODELS.items():
        try:
            ic = ee.ImageCollection(cid)
            band = et_band(ic)
        except Exception as e:
            print(f"  ⚠️ {mname} ({cid}) OCHILMADI: {e} — o'tkazib yuborildi")
            continue
        got = 0
        for mon_name, m in MONTHS.items():
            start = ee.Date.fromYMD(YEAR, m, 1)
            end = start.advance(1, 'month')
            # Bushland'ni qamragan BITTA taylni olamiz (mosaic emas —
            # 4 parcel ~250m ichida, hammasi bitta 30m taylga tushadi).
            img = ic.filterDate(start, end).filterBounds(region).select(band).first()
            try:
                res = ee.Image(img).reduceRegions(
                    collection=fc, reducer=ee.Reducer.mean(), scale=30).getInfo()
            except Exception as e:
                print(f"     ⚠️ {mname} {mon_name}: {e}")
                continue
            for ft in res['features']:
                v = ft['properties'].get('mean')
                rows.append({'model': mname, 'month': mon_name, 'mon_n': m,
                             'lys': ft['properties']['name'],
                             'openet_mm': (float(v) if v is not None else np.nan)})
                if v is not None:
                    got += 1
        print(f"  ✅ {mname:9s} band='{band}'  → {got} qiymat")

    oe = pd.DataFrame(rows)
    if oe.empty:
        print("  ❌ OpenET'dan hech narsa olinmadi (auth/asset?)")
        return

    # --- Birlashtirish: (month,lys) bo'yicha lizimetr + har model ---
    merged = oe.merge(lys[['month', 'lys', 'lys_mm', 'SEBAL_Milliy_mm', 'mon_n']],
                      on=['month', 'lys', 'mon_n'], how='left')
    merged = merged.sort_values(['model', 'mon_n', 'lys']).reset_index(drop=True)

    # --- Statistika (SEBAL_Milliy analitikasi bilan bir xil: R2,MBE,MAE,RMSE) ---
    def stats(pred, obs):
        d = pd.DataFrame({'p': pred, 'o': obs}).dropna()
        if len(d) < 3:
            return dict(n=len(d), R2=np.nan, MBE=np.nan, MAE=np.nan, RMSE=np.nan)
        p, o = d['p'].values, d['o'].values
        err = p - o
        ss_res = np.sum((o - p) ** 2)
        ss_tot = np.sum((o - o.mean()) ** 2)
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
        # Pearson r^2 ham (SEBAL jadvali korrelyatsion R2 ni ko'rsatadi)
        r = np.corrcoef(p, o)[0, 1] if len(d) > 1 else np.nan
        return dict(n=len(d), R2=round(r * r, 3), R2_1to1=round(r2, 3),
                    MBE=round(err.mean(), 2), MAE=round(np.abs(err).mean(), 2),
                    RMSE=round(np.sqrt((err ** 2).mean()), 2))

    stat_rows = []
    for mname in MODELS:
        sub = merged[merged['model'] == mname]
        if sub.empty:
            continue
        st = stats(sub['openet_mm'], sub['lys_mm'])
        st = {'model': f'OpenET {mname}', 'masshtab': 'OYLIK (mm/oy)', **st}
        stat_rows.append(st)
    # SEBAL_Milliy (bizniki) — bir xil (month,lys) juftlikda, yonma-yon
    lys_valid = lys.dropna(subset=['SEBAL_Milliy_mm'])
    st_sebal = stats(lys_valid['SEBAL_Milliy_mm'], lys_valid['lys_mm'])
    stat_rows.append({'model': 'SEBAL_Milliy (bizniki)', 'masshtab': 'OYLIK (mm/oy)', **st_sebal})

    stat_df = pd.DataFrame(stat_rows).sort_values('RMSE').reset_index(drop=True)

    # --- Saqlash ---
    pairs_path = os.path.join(OUT_DIR, 'openet_vs_lys_oylik_juftliklar.csv')
    stats_path = os.path.join(OUT_DIR, 'openet_vs_lys_STATS.csv')
    xlsx_path = os.path.join(OUT_DIR, 'OpenET_vs_lizimetr_2021.xlsx')
    merged.to_csv(pairs_path, index=False, encoding='utf-8-sig')
    stat_df.to_csv(stats_path, index=False, encoding='utf-8-sig')
    try:
        with pd.ExcelWriter(xlsx_path, engine='openpyxl') as xw:
            stat_df.to_excel(xw, sheet_name='STATS', index=False)
            # wide pivot: har model ustun
            piv = merged.pivot_table(index=['mon_n', 'month', 'lys', 'lys_mm'],
                                     columns='model', values='openet_mm').reset_index()
            piv.to_excel(xw, sheet_name='oylik_wide', index=False)
            merged.to_excel(xw, sheet_name='oylik_long', index=False)
    except ModuleNotFoundError:
        print("  ⚠️ openpyxl yo'q — Excel o'tkazildi, CSV lar saqlandi")
        xlsx_path = '(o\'tkazildi — openpyxl yo\'q)'

    print("\n" + "=" * 60)
    print("  NATIJA — OpenET modellar vs Bushland lizimetr (OYLIK, 2021)")
    print("=" * 60)
    print(stat_df.to_string(index=False))
    print(f"\n  💾 {stats_path}")
    print(f"  💾 {pairs_path}")
    print(f"  💾 {xlsx_path}")


if __name__ == '__main__':
    main()
