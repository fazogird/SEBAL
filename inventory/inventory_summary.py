import pandas as pd, numpy as np, sys, os
sys.stdout.reconfigure(encoding='utf-8')
d = pd.read_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'inventory_T42SUJ.csv'))
d['date'] = pd.to_datetime(d['date_local'])
d = d[(d.date.dt.month >= 4) & (d.date.dt.month <= 9)].copy()          # aprel–sentabr
d['cc'] = d['crop_clear_pct'].fillna(0) / 100
h = d['time_local'].str.slice(0, 2).astype(int) + d['time_local'].str.slice(3, 5).astype(int) / 60
d['hour'] = np.where(d.sensor == 'VIIRS', d['viirs_time'], h)
eco_day = (d.sensor == 'ECOSTRESS') & d.hour.between(9, 17) & (d.vz_med <= 25)
vii_ok = (d.sensor == 'VIIRS') & (d.vz_med <= 40)
d['grp'] = None
d.loc[d.sensor == 'LANDSAT', 'grp'] = 'L'
d.loc[eco_day, 'grp'] = 'E'
d.loc[vii_ok, 'grp'] = 'V'
rows = []
for y, g in d.groupby('year'):
    r = {'yil': y}
    r['Landsat'] = g.loc[g.grp == 'L', 'cc'].sum()
    r['ECO_kunduz'] = g.loc[g.grp == 'E', 'cc'].sum()
    r['ECO_jami'] = g.loc[g.sensor == 'ECOSTRESS', 'cc'].sum()
    r['VIIRS_vz40'] = g.loc[g.grp == 'V', 'cc'].sum()
    r['VIIRS_jami'] = g.loc[g.sensor == 'VIIRS', 'cc'].sum()
    r['S30_optik'] = g.loc[g.sensor == 'HLS_S30', 'cc'].sum()
    # kunlik birlashma — pastki chegara: har kun eng katta ulush
    for name, gs in [('L+E', ['L', 'E']), ('L+E+V', ['L', 'E', 'V'])]:
        r[name] = g[g.grp.isin(gs)].groupby('date')['cc'].max().sum()
    r['ECO_kunduz_obs>=30%'] = int(((g.grp == 'E') & (g.crop_clear_pct >= 30)).sum())
    r['ECO_tun_tong_obs'] = int(((g.sensor == 'ECOSTRESS') & ~g.hour.between(9, 17)).sum())
    rows.append(r)
t = pd.DataFrame(rows).set_index('yil').round(1)
pd.set_option('display.width', 200)
print("O'rtacha BITTA EKIN PIKSELI uchun bulutsiz termal kuzatuvlar soni, aprel–sentabr (183 kun), T42SUJ")
print(t.to_string())
print()
v = d[d.sensor == 'VIIRS']
print("VIIRS vaqti (mahalliy):", round(v.hour.min(), 2), "-", round(v.hour.max(), 2),
      "| VZA median taqsimoti:", v.vz_med.describe()[['25%', '50%', '75%']].round(0).to_dict())
e = d[d.sensor == 'ECOSTRESS']
print("ECOSTRESS soat taqsimoti (barcha yillar, apr–sen):",
      pd.cut(e.hour, [0, 6, 9, 12, 15, 17, 20, 24]).value_counts().sort_index().to_dict())
