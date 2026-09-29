import pandas as pd, numpy as np, sys, os
sys.stdout.reconfigure(encoding='utf-8')
SP = os.path.dirname(os.path.abspath(__file__))
d = pd.read_csv(os.path.join(SP, 'eco_t42suj_analyzed.csv'), parse_dates=['utc', 'loc'])
d = d.sort_values('utc').reset_index(drop=True)
# 1) Uzoq muddatli siljish: bir xil "ketma-ketlik" ichida (<=10 kun oralig'i) soat qanday siljiydi
seqs, cur = [], [0]
for i in range(1, len(d)):
    if (d.utc[i] - d.utc[cur[-1]]).days <= 10:
        cur.append(i)
    else:
        seqs.append(cur); cur = [i]
seqs.append(cur)
rates = []
for s in seqs:
    if len(s) >= 3:
        g = d.loc[s]
        days = (g.utc - g.utc.iloc[0]).dt.total_seconds() / 86400
        h = np.unwrap(g.hour.values * 2 * np.pi / 24) * 24 / (2 * np.pi)
        if days.iloc[-1] > 3:
            x = days.values; xm = x.mean(); ym = h.mean()
            rates.append(float(((x - xm) * (h - ym)).sum() / ((x - xm) ** 2).sum()) * 60)
print(f"Uzoq siljish (ketma-ketliklar ichida chiziqli moslash): median {np.median(rates):.0f} min/kun, n={len(rates)}"
      f" -> 24 soatlik aylanish ~{24*60/abs(np.median(rates)):.0f} kun")
# 2) Kunduzgi (9-17) tasvirlar "deraza"lari: <=12 kun oraliq bilan guruhlash
k = d[d.cls == 'KUN(9-17)'].reset_index(drop=True)
wins, cur = [], [0]
for i in range(1, len(k)):
    if (k['loc'][i] - k['loc'][cur[-1]]).days <= 12:
        cur.append(i)
    else:
        wins.append(cur); cur = [i]
wins.append(cur)
print("\nKUNDUZGI DERAZALAR (9-17): boshi — oxiri | tasvir soni | soat oralig'i | shundan yaroqli")
prev = None
gaps = []
for w in wins:
    g = k.loc[w]
    a, b = g['loc'].min(), g['loc'].max()
    if prev is not None:
        gaps.append((a - prev).days)
    prev = b
    print(f"  {a:%Y-%m-%d} — {b:%Y-%m-%d} | {len(g):2d} | {g.hour.max():5.2f} -> {g.hour.min():5.2f} | {int(g.usable.sum())}")
print(f"\nDerazalar orasidagi bo'shliq (kun): median {np.median(gaps):.0f}, 25-75%: {np.percentile(gaps,25):.0f}-{np.percentile(gaps,75):.0f}")
