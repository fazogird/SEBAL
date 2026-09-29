import pandas as pd, sys, os
sys.stdout.reconfigure(encoding='utf-8')
INV = r'D:\Cloud_comp\Sebal\scripts\inventory'
d = pd.read_csv(os.path.join(INV, 'eco_t42suj_analyzed.csv'), parse_dates=['utc', 'loc'])
d = d.sort_values('utc')
d['tash'] = d.utc + pd.Timedelta(hours=5)                     # Toshkent vaqti (UTC+5)
bins = [0, 3, 6, 9, 12, 15, 18, 21, 24]
lab = ['00-03', '03-06', '06-09', '09-12', '12-15', '15-18', '18-21', '21-24']
d['oraliq'] = pd.cut(d.hour, bins, labels=lab, right=False, include_lowest=True)
t = pd.crosstab(d.year, d.oraliq)
t['JAMI'] = t.sum(axis=1)
print("TASVIRLAR SONI — mahalliy quyosh vaqti oraliqlari bo'yicha (Toshkent vaqti = +31 daqiqa)")
print(t.to_string())
print('\n2019 — HAR BIR TASVIR (sana: quyosh vaqti; [K]=kunduz 9-17, [Y]=yaroqli, q=tile qoplash %)')
g = d[d['loc'].dt.year == 2019]
for m, gm in g.groupby(g['loc'].dt.month):
    items = []
    for _, r in gm.iterrows():
        tag = '[Y]' if r.usable else ('[K]' if r.cls == 'KUN(9-17)' else '')
        items.append(f"{r['loc']:%d} {r['loc']:%H:%M}{tag} q{100*r['cov']:.0f}")
    print(f"  {m:02d}-oy ({len(gm)}): " + '; '.join(items))
out = d[['id']].copy()
out['sana'] = d['loc'].dt.strftime('%Y-%m-%d')
out['quyosh_vaqti'] = d['loc'].dt.strftime('%H:%M')
out['toshkent_vaqti'] = d['tash'].dt.strftime('%Y-%m-%d %H:%M')
out['sinf'] = d.cls.astype(str)
out['tile_qoplash_pct'] = (100 * d['cov']).round(1)
out['ekin_bulutsiz_pct'] = d.crop_clr.round(1)
out['korish_burchagi'] = d.view_zenith.round(1)
out['LST_median_K'] = d.LST.round(1)
out['yaroqli'] = d.usable
out.to_csv(os.path.join(INV, 'ECOSTRESS_T42SUJ_tasvirlar.csv'), index=False, encoding='utf-8-sig')
print('\nsaqlandi: inventory/ECOSTRESS_T42SUJ_tasvirlar.csv', len(out), 'qator')
