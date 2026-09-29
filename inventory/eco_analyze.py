import pandas as pd, numpy as np, sys, os
sys.stdout.reconfigure(encoding='utf-8')
SP = os.path.dirname(os.path.abspath(__file__))
d = pd.read_csv(os.path.join(SP, 'eco_t42suj_detail.csv'))
LON = 67.32; OFF = LON / 15
d['utc'] = pd.to_datetime(d.t, unit='ms')
d['id_utc'] = pd.to_datetime(d.id.str.slice(0, 17), format='%Y_%m_%d_%H%M%S')
d['dt_err_s'] = (d.utc - d.id_utc).dt.total_seconds()
d['orbit'] = d.id.str.split('_').str[4].astype(int)
d['loc'] = d.utc + pd.to_timedelta(OFF, unit='h')
d['hour'] = d['loc'].dt.hour + d['loc'].dt.minute / 60
d['year'] = d['loc'].dt.year
d['cls'] = pd.cut(d.hour, [-0.1, 6, 9, 17, 20, 24.1], labels=['tun(0-6)', 'tong(6-9)', 'KUN(9-17)', 'kech(17-20)', 'tun(20-24)'])
d['crop_clr'] = 100 * d.cc / d.crop
d['usable'] = (d.cls == 'KUN(9-17)') & (d.view_zenith <= 25) & (d.crop_clr >= 30)
print('1) VAQT TEKSHIRUVI: id-vaqt va time_start farqi (s): min', d.dt_err_s.min(), 'max', d.dt_err_s.max())
print('\n2) KUN/TUN LST bilan (bulutsiz qism, median K), iyun-avgust:')
s = d[d['loc'].dt.month.isin([6, 7, 8]) & d.LST.notna()]
print(s.groupby('cls', observed=True).LST.agg(['count', 'median', 'min', 'max']).round(1).to_string())
print('\n3) YILLAR BO\'YICHA (butun yil): tasvirlar soni soat sinfi bo\'yicha | yaroqli = kunduz + vz<=25 + ekinning >=30% bulutsiz')
t = pd.crosstab(d.year, d.cls)
t['JAMI'] = t.sum(axis=1); t['YAROQLI'] = d.groupby('year').usable.sum()
print(t.to_string())
print('\n4) QOPLASH: tile qoplash % taqsimoti (hamma tasvir):', d['cov'].mul(100).describe()[['25%', '50%', '75%']].round(0).to_dict(),
      '| qoplash <30%:', int((d['cov'] < 0.3).sum()), 'ta')
print('   BULUT: bulutli ulush median %:', round(100 * d.cld.median(), 0), '| kunduzgi tasvirlarda:', round(100 * d.loc[d.cls == 'KUN(9-17)', 'cld'].median(), 0))
print('\n5) SILJISH: ketma-ket kunlardagi o\'tishlar — mahalliy vaqt kuniga qancha siljiydi')
e = d.sort_values('utc').reset_index(drop=True)
dd = []
for i in range(1, len(e)):
    gap = (e.utc[i] - e.utc[i - 1]).total_seconds() / 86400
    if 0.8 < gap < 1.2:
        dh = ((e.hour[i] - e.hour[i - 1] + 12) % 24) - 12
        dd.append(dh * 60)
dd = np.array(dd)
print(f'   ketma-ket kun juftlari: {len(dd)}, siljish median {np.median(dd):.0f} min/kun (25-75%: {np.percentile(dd,25):.0f}..{np.percentile(dd,75):.0f})')
print('\n6) YAROQLI TASVIRLAR RO\'YXATI (sana, mahalliy vaqt, vz, ekin bulutsiz %, qoplash %):')
u = d[d.usable].sort_values('utc')
for _, r in u.iterrows():
    print(f"   {r['loc']:%Y-%m-%d %H:%M}  vz{r.view_zenith:4.0f}°  ekin {r.crop_clr:5.1f}%  qoplash {100*r['cov']:5.1f}%")
print('\n7) OYLAR BO\'YICHA kunduzgi (9-17) tasvirlar, barcha yillar:')
print(d[d.cls == 'KUN(9-17)'].groupby(d['loc'].dt.month).size().to_dict())
d.to_csv(os.path.join(SP, 'eco_t42suj_analyzed.csv'), index=False)
