import pandas as pd, os, sys
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
SP = os.path.dirname(os.path.abspath(__file__))
OUT = r'D:\Cloud_comp\Sebal\scripts\inventory\ECOSTRESS_T42SUJ_vaqt.png'
d = pd.read_csv(os.path.join(SP, 'eco_t42suj_analyzed.csv'), parse_dates=['loc'])
day = d.cls == 'KUN(9-17)'
years = list(range(2019, 2027))
fig, axes = plt.subplots(len(years), 1, figsize=(11, 15), sharey=True)
for ax, y in zip(axes, years):
    g = d[d['loc'].dt.year == y]
    x = g['loc'].apply(lambda t: t.replace(year=2000))
    ax.axhspan(9, 17, color='#fff3cd', zorder=0)
    ax.axvspan(pd.Timestamp('2000-04-01'), pd.Timestamp('2000-09-30'), color='#e8f4ea', zorder=0, alpha=0.6)
    m_u = g.usable; m_d = (g.cls == 'KUN(9-17)') & ~g.usable; m_n = g.cls != 'KUN(9-17)'
    ax.scatter(x[m_n], g.hour[m_n], s=14, c='#9aa0a6', label='tun / tong / kech (SEBAL uchun yaroqsiz)', zorder=2)
    ax.scatter(x[m_d], g.hour[m_d], s=22, c='#f0a202', label="kunduz, lekin yaroqsiz (qisman qoplash, bulut yoki burchak >25°)", zorder=3)
    ax.scatter(x[m_u], g.hour[m_u], s=40, c='#1b7f3b', marker='D', label="YAROQLI: kunduz, burchak ≤25°, ekinning ≥30% bulutsiz", zorder=4)
    ax.set_xlim(pd.Timestamp('2000-01-01'), pd.Timestamp('2000-12-31'))
    ax.set_ylim(0, 24); ax.set_yticks([0, 6, 9, 12, 17, 24])
    ax.set_ylabel(str(y), rotation=0, labelpad=22, fontsize=12, fontweight='bold', va='center')
    ax.text(1.005, 0.5, f"{len(g)} tasvir\n{int(day[g.index].sum())} kunduzgi\n{int(g.usable.sum())} yaroqli",
            transform=ax.transAxes, fontsize=8.5, va='center')
    ax.xaxis.set_major_locator(mdates.MonthLocator()); ax.xaxis.set_major_formatter(mdates.DateFormatter('%b'))
    ax.grid(axis='x', color='#dddddd', lw=0.6)
axes[0].legend(loc='upper center', bbox_to_anchor=(0.5, 1.9), ncol=1, fontsize=9, frameon=False)
fig.suptitle("ECOSTRESS — T42SUJ (Samarqand) tile ustidan o'tish vaqti, 2019–2026\n"
             "y: mahalliy quyosh vaqti (soat); sariq tasma — 9–17 kunduz; yashil fon — aprel–sentabr",
             fontsize=12, y=0.995)
fig.text(0.5, 0.005, "O'tish vaqti har kuni ~25 daqiqaga erta siljiydi (~58 kunlik to'liq aylanish) → kunduzgi 'derazalar' taxminan har 7 haftada. "
         "Manba: NASA/ECOSTRESS/L2T_LSTE/V2 (GEE).", ha='center', fontsize=8.5)
plt.tight_layout(rect=(0, 0.015, 0.95, 0.955))
fig.savefig(OUT, dpi=110)
print('saqlandi:', OUT)
