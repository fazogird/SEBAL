"""
Tile kalendari — kirish bosqichining birinchi mahsuloti (SEBAL'dan oldin, arzon hisob).

Har kuzatuv uchun (100 m; VIIRS — 1 km), ekin — Esri 5 ning piksel ichidagi ulushi bilan og'irlangan:
  ekin_ko'rildi_% — tile ekinining (region berilsa — tile ∩ region ekinining) tasvir ko'rgan ulushi;
  ekin_bulut_%    — ko'rilgan ekin ustidagi bulut ulushi;
  tile_bulut_%    — ko'rilgan tile ustidagi bulut (VIIRS / ECOSTRESS uchun dastlabki filtr).
Qoidalar — rules.InputRules. VIIRS va ECOSTRESS kuni HLS (±2 kun) bilan juftlanadi: piksel
ikkalasida ham toza bo'lishi shart, qoidalar birlashgan maska ustida qayta tekshiriladi. HLS
nomzodlar tartibi (user tasdiqlagan): ko'proq toza ekin → yaqinroq sana → L30.
Kun turi (piksel bo'yicha ustuvorlik Landsat > ECOSTRESS > VIIRS): L, E, V birikmalari yoki SB (suv balansi).
SEBAL_ekin_% — shu kuni kamida bitta qabul qilingan manbada toza ko'ringan ekin ulushi.

Ishga tushirish (scripts papkasidan, gee_env):
  python -m sebal_gee_v4.pipeline.calendar T42SUJ 2025-04-01 2025-11-01
  python -m sebal_gee_v4.pipeline.calendar T42SUJ 2025-04-01 2025-11-01 --region Qashqadaryo

Ierarxiya (user, 2026-09-29): hudud (viloyat) → uni qoplovchi MGRS tile'lar → tile ichidagi ekin.
region berilsa qoidalar (ekinning ko'rilgan ulushi, ekin ustidagi bulut) TILE ∩ HUDUD ekinida
tekshiriladi: masalan T42SUJ'da Qashqadaryo ekinini faqat WRS 155033 ko'radi — path 154 va 155032
(Samarqand ekini) Qashqadaryo uchun rad etiladi. Anchor esa butun tile ustida qoladi (multisensor).
"""
import argparse
import datetime as dt
import os
import time

import ee
import pandas as pd

from .. import ee_utils
from .rules import InputRules
from .sources import LandsatC2, Hls, Viirs, Ecostress
from .tile import MgrsTile

SCRIPTS = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SEEN, CLOUD = "ekin_ko'rildi_%", 'ekin_bulut_%'
V_SEEN, V_CLOUD = "birlashgan_ekin_ko'rildi_%", 'birlashgan_ekin_bulut_%'


def _clear(o, seen=SEEN, cloud=CLOUD):
    """Toza ko'ringan ekin ulushi (tile ekinidan, %)."""
    return o[seen] * (1 - o[cloud] / 100)


def _vclear(o):
    return _clear(o, V_SEEN, V_CLOUD)


class TileCalendar:
    """region (ee.Geometry, masalan viloyat) berilsa — hamma qoidalar TILE ∩ REGION ekini bo'yicha:
    tasvir foydali bo'lishi uchun viloyatning SHU tile ichidagi ekinini ko'rishi kerak (user, 2026-09-29:
    T42SUJ'da Qashqadaryo ekinini faqat 155033 ko'radi, 155032 — Samarqand ekinini). Yo'q — butun tile."""

    def __init__(self, tile_id, start, end, rules=None, chunk_fine=6, chunk_coarse=40, log=print,
                 region=None):
        self.tile = MgrsTile(tile_id)
        self.region = region
        self.geom = (self.tile.geometry.intersection(region, ee.ErrorMargin(30)) if region is not None
                     else self.tile.geometry)
        self.start, self.end = start, end                    # end — eksklyuziv
        self.rules = rules or InputRules()
        self.chunk_fine, self.chunk_coarse, self.log = chunk_fine, chunk_coarse, log
        self.src = {'Landsat': LandsatC2(), 'HLS_L30': Hls('L30'), 'HLS_S30': Hls('S30'),
                    'VIIRS': Viirs(), 'ECOSTRESS': Ecostress()}
        self._crop = {}
        self.crop_km2 = None

    # ---- ekin ulushi va statistika ----
    def crop(self, date, scale):
        key = (int(date[:4]), scale)
        if key not in self._crop:
            self._crop[key] = self.tile.crop_fraction(key[0], scale)
        return self._crop[key]

    def _reduce(self, img, scale, geom=None):
        return img.reduceRegion(ee.Reducer.sum(), geom or self.geom, crs=self.tile.crs,
                                crsTransform=self.tile.transform(scale), maxPixels=1e10, tileScale=4)

    def _stats(self, obs_img, date, scale):
        crop = self.crop(date, scale)
        seen, bad = obs_img.select('SEEN'), obs_img.select('BAD')
        cs = crop.multiply(seen)
        return self._reduce(ee.Image.cat([
            crop.rename('C'), cs.rename('CS'), cs.multiply(bad).rename('CSB'),
            seen.rename('S'), seen.multiply(bad).rename('SB'), ee.Image.constant(1).rename('N')]), scale)

    @staticmethod
    def _pct(st):
        g = lambda k: st.get(k) or 0.0
        seen = 100 * g('CS') / g('C') if g('C') else 0.0
        cloud = 100 * g('CSB') / g('CS') if g('CS') else 100.0
        tseen = 100 * g('S') / g('N') if g('N') else 0.0
        tcloud = 100 * g('SB') / g('S') if g('S') else 100.0
        return seen, cloud, tseen, tcloud

    def _batched(self, items, build, chunk, label):
        """Bo'laklab getInfo — bitta so'rovda ko'p agregatsiya "Too many concurrent" beradi."""
        out = []
        for i in range(0, len(items), chunk):
            out += ee.List([build(it) for it in items[i:i + chunk]]).getInfo()
            self.log(f"    {label}: {min(i + chunk, len(items))}/{len(items)}")
        return out

    # ---- 1–3: har sensor ----
    def _sensor(self, key):
        src = self.src[key]
        start, end = self.start, self.end
        if key.startswith('HLS'):     # oyna chetidagi VIIRS/ECOSTRESS kunlari ham ±W kunlik HLS bilan juftlansin
            W = self.rules.hls_window_days
            start = (dt.date.fromisoformat(self.start) - dt.timedelta(days=W)).isoformat()
            end = (dt.date.fromisoformat(self.end) + dt.timedelta(days=W)).isoformat()
        obs = src.observations(self.tile, start, end, self.rules)
        todo = [o for o in obs if o['pre_ok']]
        self.log(f"  {key}: {len(obs)} kuzatuv, dastlabki filtrdan o'tdi {len(todo)}")
        coarse = src.scale > 100

        def build(o):
            d = {'st': self._stats(src.image(o, self.rules), o['sana'], src.scale)}
            if isinstance(src, Viirs):
                d['geo'] = src.geometry_bands(o, self.rules).reduceRegion(
                    ee.Reducer.median(), self.geom, crs=self.tile.crs,
                    crsTransform=self.tile.transform(1000), maxPixels=1e9)
            return ee.Dictionary(d)

        res = self._batched(todo, build, self.chunk_coarse if coarse else self.chunk_fine, key)
        for o, r in zip(todo, res):
            seen, cloud, tseen, tcloud = self._pct(r['st'])
            o.update({SEEN: round(seen, 1), CLOUD: round(cloud, 1),
                      "tile_ko'rildi_%": round(tseen, 1), 'tile_bulut_%': round(tcloud, 1)})
            vza_all = None
            if 'geo' in r:
                vza_all = r['geo'].get('VZA_ALL')
                o['VZA_median'] = r['geo'].get('VZA')
                o['View_Time'] = r['geo'].get('VT')
            if key in ('VIIRS', 'ECOSTRESS') and (tseen == 0 or tcloud >= self.rules.scene_cloud_max):
                o['pre_ok'] = False                      # metadata yo'q — tile buluti bo'yicha
                if tseen > 0:
                    o['sabab'] = f"tile buluti {tcloud:.0f}% (≥ {self.rules.scene_cloud_max:.0f}%)"
                elif vza_all is not None and vza_all > self.rules.viirs_vza_max:
                    o['sabab'] = f"|VZA| {vza_all:.0f}° > {self.rules.viirs_vza_max:.0f}°"
                else:
                    o['sabab'] = "ma'lumot yo'q (tile kuzatilmagan)"
                continue
            o['qabul'], o['sabab'] = self.rules.judge(seen, cloud)
        for o in obs:
            o.setdefault('qabul', False)
        if res and not coarse and self.crop_km2 is None:
            self.crop_km2 = round((res[0]['st'].get('C') or 0.0) * src.scale ** 2 / 1e6, 1)
        return obs

    # ---- termal (VIIRS / ECOSTRESS) + HLS optika juftligi ----
    def _combined(self, t, h):
        ti = self.src[t['sensor']].image(t, self.rules)
        hi = self.src[h['sensor']].image(h, self.rules)
        seen = ti.select('SEEN').And(hi.select('SEEN'))
        bad = ti.select('BAD').Or(hi.select('BAD'))
        return ee.Image.cat([seen.rename('SEEN'), bad.And(seen).rename('BAD')])

    def _pair(self, thermal, hls):
        """Termal kuzatuvga HLS optika: ±W kun, nomzodlar — ko'proq toza ekin → yaqin sana → L30
        (user tasdiqlagan). Qoidalar birlashgan maskada (piksel ikkalasida ham toza)."""
        W = self.rules.hls_window_days
        acc = [h for h in hls if h['qabul']]
        for v in thermal:
            if not v['qabul']:
                continue
            dv = dt.date.fromisoformat(v['sana'])
            c = []
            for h in acc:
                off = (dt.date.fromisoformat(h['sana']) - dv).days
                if abs(off) <= W:
                    c.append((-_clear(h), abs(off), h['sensor'] != 'HLS_L30', off, h))
            c.sort(key=lambda x: x[:3])
            v['_cands'] = [(x[3], x[4]) for x in c[:3]]
            if not c:
                v['juft'], v['juft_sabab'] = False, f"±{W} kun ichida qabul qilingan HLS yo'q"
        pairs = []
        for k in range(3):
            todo = [v for v in thermal if v['qabul'] and 'juft' not in v and len(v['_cands']) > k]
            if not todo:
                break
            res = self._batched(
                todo, lambda v: self._stats(self._combined(v, v['_cands'][k][1]), v['sana'], 100),
                self.chunk_fine, f'termal+HLS ({k + 1}-nomzod)')
            for v, st in zip(todo, res):
                off, h = v['_cands'][k]
                seen, cloud, _, _ = self._pct(st)
                ok, why = self.rules.judge(seen, cloud)
                pairs.append({'termal': v['sensor'], 'termal_sana': v['sana'], 'HLS': h['sensor'],
                              'HLS_id': h['id'], 'HLS_sana': h['sana'], 'siljish_kun': off,
                              'nomzod': k + 1, SEEN: round(seen, 1), CLOUD: round(cloud, 1),
                              'qabul': ok, 'sabab': why})
                if ok:
                    v.update({'juft': True, 'juft_sabab': '', '_hls': h, 'HLS': h['sensor'],
                              'HLS_sana': h['sana'], 'HLS_siljish': off,
                              V_SEEN: round(seen, 1), V_CLOUD: round(cloud, 1)})
        for v in thermal:
            if v['qabul'] and 'juft' not in v:
                v['juft'], v['juft_sabab'] = False, "birlashgan maskada qoidadan o'tmadi (3 nomzod)"
        return pairs

    # ---- kunlar ----
    def _clear_img(self, kind, o):
        img = self.src['Landsat'].image(o, self.rules) if kind == 'L' else self._combined(o, o['_hls'])
        return img.select('SEEN').And(img.select('BAD').Not())

    def _days(self, L, E, V):
        def best(lst, cond, score):
            out = {}
            for o in lst:
                if cond(o) and (o['sana'] not in out or score(o) > score(out[o['sana']])):
                    out[o['sana']] = o
            return out
        Lk = best(L, lambda o: o['qabul'], _clear)
        Ek = best(E, lambda o: o.get('juft'), _vclear)       # ECOSTRESS ham HLS optika bilan
        Vk = best(V, lambda o: o.get('juft'), _vclear)
        Lall = {o['sana']: o for o in L}
        Vall = {o['sana']: o for o in V}
        end = dt.date.fromisoformat(self.end)
        rows, multi = [], []
        d = dt.date.fromisoformat(self.start)
        while d < end:
            s = d.isoformat()
            src = [(k, m[s]) for k, m in (('L', Lk), ('E', Ek), ('V', Vk)) if s in m]
            lo, vo = Lall.get(s), Vall.get(s)
            r = {'sana': s, 'oy': s[:7], 'kun_turi': '+'.join(k for k, _ in src) or 'SB',
                 'Landsat': f"path {lo['path']} ({lo['sun_yoldosh']})" if lo else '',
                 'L_toza_ekin_%': round(_clear(lo), 1) if lo and lo['qabul'] else None,
                 'L_sabab': lo['sabab'] if lo and not lo['qabul'] else '',
                 'E_toza_ekin_%': round(_vclear(Ek[s]), 1) if s in Ek else None,
                 'VIIRS_VZA': vo.get('VZA_median') if vo else None,
                 'VIIRS_vaqt': vo.get('View_Time') if vo else None,
                 'V_toza_ekin_%': round(_vclear(Vk[s]), 1) if s in Vk else None,
                 'HLS_optika': (f"{Vk[s]['HLS']} {Vk[s]['HLS_sana']} ({Vk[s]['HLS_siljish']:+d})"
                                if s in Vk else ''),
                 'V_sabab': '' if s in Vk or not vo else (vo.get('juft_sabab') or vo['sabab'])}
            if len(src) == 1:
                k, o = src[0]
                r['SEBAL_ekin_%'] = round(_clear(o) if k == 'L' else _vclear(o), 1)
            elif src:
                multi.append((r, src))
            else:
                r['SEBAL_ekin_%'] = 0.0
            rows.append(r)
            d += dt.timedelta(days=1)

        def build(item):            # bir nechta manba — toza ekin birlashmasi (aniq, piksel bo'yicha)
            r, src = item
            u = ee.ImageCollection([self._clear_img(k, o).rename('U').toByte() for k, o in src]).max()
            crop = self.crop(r['sana'], 100)
            return self._reduce(ee.Image.cat([crop.rename('C'),
                                              crop.multiply(u.unmask(0, False)).rename('CU')]), 100)
        for (r, _), st in zip(multi, self._batched(multi, build, self.chunk_fine, 'birlashma')):
            r['SEBAL_ekin_%'] = round(100 * (st.get('CU') or 0) / st['C'], 1) if st.get('C') else 0.0
        return pd.DataFrame(rows)

    @staticmethod
    def _monthly(days):
        out = []
        for m, g in days.groupby('oy'):
            t = g['kun_turi']
            run = best = 0
            for k in t:
                run = run + 1 if k == 'SB' else 0
                best = max(best, run)
            sebal = g[t != 'SB']
            out.append({'oy': m, 'kunlar': len(g),
                        'Landsat_kunlari': int(t.str.contains('L').sum()),
                        "ECOSTRESS_kunlari (L yo'q)": int((t.str.contains('E') & ~t.str.contains('L')).sum()),
                        'faqat_VIIRS_kunlari': int((t == 'V').sum()),
                        'SEBAL_kunlari': len(sebal), 'suv_balansi_kunlari': int((t == 'SB').sum()),
                        'SEBAL_kunida_ekin_qoplami_%':
                            round(sebal['SEBAL_ekin_%'].mean(), 1) if len(sebal) else 0.0,
                        'samarali_SEBAL_kunlari': round(g['SEBAL_ekin_%'].sum() / 100, 1),
                        'eng_uzun_SB_ketma_ket': best})
        df = pd.DataFrame(out)
        tot = df.sum(numeric_only=True).to_dict()
        sb = days.loc[days['kun_turi'] != 'SB', 'SEBAL_ekin_%']
        tot['SEBAL_kunida_ekin_qoplami_%'] = round(sb.mean(), 1) if len(sb) else 0.0
        tot['eng_uzun_SB_ketma_ket'] = int(df['eng_uzun_SB_ketma_ket'].max())
        return pd.concat([df, pd.DataFrame([{'oy': 'jami', **tot}])], ignore_index=True)

    # ---- WRS sahnalari: kim qaysi ekinni ko'radi ----
    def wrs_coverage(self, regions=None):
        """Har WRS sahnasi (path/row) footprint'i tile ekinining, tile ∩ hudud ekinining va (regions —
        {nom: ee.Geometry}, masalan tile ichidagi viloyatlar) har viloyat ekinining necha foizini ko'radi.
        Bulutga qaralmaydi — faqat geometriya: qaysi sahna qaysi ekin uchun umuman foydali bo'la oladi.
        Ekini < 1 km² bo'lgan maydon uchun ulush chiqarilmaydi (None) — 0 ga yaqin maxrajdan "100%" chiqmasin.
        Natija self.wrs (jadval), self.crop_areas (ekin maydonlari), self.footprints ({WRS: ee.Geometry})."""
        src = self.src['Landsat']
        sc = src.scenes(self.tile, self.start, self.end)
        crop = self.crop(self.start, 100)
        stack = ee.Image.cat([crop.rename('C')] + [
            crop.multiply(src.image({'_refs': [s['asset']]}, self.rules).select('SEEN')).rename('S' + s['WRS'])
            for s in sc])
        geoms = {'tile': self.tile.geometry}
        if self.region is not None:
            geoms['hudud'] = self.geom
        for n, g in (regions or {}).items():
            geoms[n] = self.tile.geometry.intersection(g, ee.ErrorMargin(30))
        res = ee.Dictionary({k: self._reduce(stack, 100, g) for k, g in geoms.items()}).getInfo()
        tot = {k: res[k].get('C') or 0.0 for k in geoms}
        name = lambda k: {'tile': 'tile', 'hudud': 'tile ∩ hudud'}.get(k, k)
        self.crop_areas = pd.DataFrame([{'maydon': name(k), 'ekin_km2': round(tot[k] * 1e4 / 1e6, 1),
                                         'tile_ekinidan_%': round(100 * tot[k] / tot['tile'], 1) if tot['tile'] else 0.0}
                                        for k in geoms])
        rows = []
        for s in sc:
            r = {'WRS': s['WRS'], 'path': s['path'], 'row': s['row'], 'sana (namuna)': s['sana']}
            for k in geoms:
                v = res[k].get('S' + s['WRS']) or 0.0
                r[f"{name(k)} ekinidan_%"] = round(100 * v / tot[k], 1) if tot[k] * 1e4 / 1e6 >= 1 else None
            rows.append(r)
        self.wrs = pd.DataFrame(rows)
        self.footprints = {s['WRS']: ee.Image(s['asset']).geometry() for s in sc}
        return self.wrs

    # ---- hammasi ----
    def run(self):
        t0 = time.time()
        ys = sorted({self.tile.esri_year(int(self.start[:4])), self.tile.esri_year(int(self.end[:4]))})
        self.log(f"Tile {self.tile.id} ({self.tile.crs}, x0={self.tile.x0:.0f}, y0={self.tile.y0:.0f}) | "
                 f"{self.start} … {self.end} | Esri yili: {ys} | qoidalar: "
                 f"{'tile ∩ hudud ekini' if self.region is not None else 'butun tile ekini'}")
        self.obs = {k: self._sensor(k) for k in ('Landsat', 'HLS_L30', 'HLS_S30', 'ECOSTRESS', 'VIIRS')}
        self.pairs = pd.DataFrame(self._pair(self.obs['VIIRS'] + self.obs['ECOSTRESS'],
                                             self.obs['HLS_L30'] + self.obs['HLS_S30']))
        self.days = self._days(self.obs['Landsat'], self.obs['ECOSTRESS'], self.obs['VIIRS'])
        self.summary = self._monthly(self.days)
        self.elapsed = time.time() - t0
        return self

    def tables(self):
        drop = lambda df: df[[c for c in df.columns if not c.startswith('_')]]
        out = {k: drop(pd.DataFrame(v)) for k, v in self.obs.items()}
        r = self.rules
        out['Qoidalar'] = pd.DataFrame([
            ('tile', self.tile.id), ('CRS', self.tile.crs),
            ('x0, y0', f'{self.tile.x0:.0f}, {self.tile.y0:.0f}'),
            ('davr', f'{self.start} … {self.end} (oxirgi kun kirmaydi)'),
            ('ekin xaritasi', f'Esri 10 m LULC, sinf 5, yil {self.tile.esri_year(int(self.start[:4]))}'),
            ('qoidalar hududi', 'tile ∩ hudud (ROI) ekini' if self.region is not None else 'butun tile ekini'),
            ('hudud ekin maydoni, km²', self.crop_km2),
            ('dastlabki bulut filtri', f'< {r.scene_cloud_max:.0f}% (Landsat/HLS metadata; VIIRS/ECOSTRESS tile)'),
            ("ko'rilgan ekin ustida bulut", f'≤ {r.crop_cloud_max:.0f}%'),
            ("ekinning ko'rilgan ulushi", f'≥ {r.crop_seen_min:.0f}%'),
            ('VIIRS', f'QC 0–1 va 4–5-bitlar = 0, |VZA| ≤ {r.viirs_vza_max:.0f}°'),
            ('VIIRS + HLS', f'±{r.hls_window_days} kun; piksel ikkalasida ham toza; qoidalar birlashgan maskada'),
            ('ECOSTRESS (vaqtincha)',
             f'mahalliy {r.eco_local_hours[0]:.0f}–{r.eco_local_hours[1]:.0f}, VZA ≤ {r.eco_vza_max:.0f}°'),
            ('masshtab', f'{r.stats_scale:.0f} m (VIIRS 1000 m)'),
            ('hisob vaqti, s', round(getattr(self, 'elapsed', 0))),
        ], columns=['parametr', 'qiymat'])
        return out

    def to_excel(self, path):
        t = self.tables()
        with pd.ExcelWriter(path) as w:
            self.summary.to_excel(w, sheet_name='Xulosa', index=False)
            self.days.to_excel(w, sheet_name='Kalendar', index=False)
            for k in ('Landsat', 'HLS_L30', 'HLS_S30', 'VIIRS', 'ECOSTRESS'):
                t[k].to_excel(w, sheet_name=k, index=False)
            self.pairs.to_excel(w, sheet_name='Termal_HLS', index=False)
            if getattr(self, 'wrs', None) is not None:
                self.wrs.to_excel(w, sheet_name='WRS_qoplash', index=False)
                self.crop_areas.to_excel(w, sheet_name='Ekin_maydoni', index=False)
            t['Qoidalar'].to_excel(w, sheet_name='Qoidalar', index=False)
        return path


def main():
    p = argparse.ArgumentParser(description='MGRS tile kalendari: qaysi kun SEBAL, qaysi kun suv balansi')
    p.add_argument('tile')
    p.add_argument('start')
    p.add_argument('end', help='eksklyuziv, masalan 2025-11-01')
    p.add_argument('--region', help="viloyat (rules.ADMIN1 asseti, region_nam, masalan Qashqadaryo): "
                                    "qoidalar tile ∩ viloyat ekinida")
    p.add_argument('--out')
    p.add_argument('--project', default=os.environ.get('EE_PROJECT', 'ee-chexovant11'))
    a = p.parse_args()
    ee.Initialize(project=a.project)
    ee_utils.install_getinfo_retry()
    from .. import config as cfg
    from .rules import ADMIN1, ADMIN1_FIELD
    region = (cfg.build_roi('asset', asset_id=ADMIN1, name=a.region, name_field=ADMIN1_FIELD)
              if a.region else None)
    cal = TileCalendar(a.tile, a.start, a.end, region=region).run()
    cal.wrs_coverage()
    tag = f'{cal.tile.id}_{a.region}' if a.region else cal.tile.id
    out = a.out or os.path.join(SCRIPTS, 'inventory', f'{tag}_kalendar_{a.start}_{a.end}.xlsx')
    cal.to_excel(out)
    print(cal.summary.to_string(index=False))
    print(f"\n✅ {out}  ({cal.elapsed / 60:.1f} daqiqa)")


if __name__ == '__main__':
    main()
