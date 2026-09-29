"""
Kirish bosqichi — sensorlar. Har kuzatuv ikki bandli tasvirga keltiriladi:
  SEEN — piksel shu kuzatuvda ko'rilgan (tasvir chegarasi ichida, geometriya sharti bajarilgan);
  BAD  — ko'rilgan, lekin bulut / soya / qor / sifatsiz.
Ikkalasi ham tasvirdan tashqarida 0: unmask(0, False) — sukut sameFootprint=True tile ulushini buzadi.

Kuzatuv birligi: Landsat — bir kunlik qatorlar mozaikasi (bitta path o'tishi); HLS — granula;
VIIRS — kun; ECOSTRESS — bitta o'tish (±5 daqiqadagi granulalar mozaikasi).
"""
import datetime as dt

import ee

from .. import config as cfg
from .rules import LANDSAT_C2, HLS, VIIRS_LST, ECOSTRESS_LST


def _utc(ms):
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc)


def _solar(t, lon):
    """UTC vaqtidan mahalliy quyosh soati (0..24)."""
    return round((t.hour + t.minute / 60 + lon / 15) % 24, 2)


def _seen_bad(seen, bad):
    return ee.Image.cat([seen.rename('SEEN'), bad.And(seen).rename('BAD')]).toByte()


def _mosaic(images):
    # Har tasvir faqat ko'rgan piksellari bilan qatnashadi — qator chekkasidagi fill qo'shni
    # qatorning haqiqiy pikselini yopib qo'ymasin.
    return (ee.ImageCollection([im.updateMask(im.select('SEEN')) for im in images])
            .mosaic().unmask(0, False))


def _rows(col, sel):
    return [dict(zip(sel, r)) for r in
            col.reduceColumns(ee.Reducer.toList(len(sel)), sel).get('list').getInfo()]


class LandsatC2:
    """Landsat 8/9 Collection 2 Level-2. Bir kunlik qatorlar (bitta o'tish) — bitta kuzatuv."""
    name = 'Landsat'
    scale = 100
    _BAD = (cfg.QA_BITMASK['dilated_cloud'] | cfg.QA_BITMASK['cirrus'] | cfg.QA_BITMASK['cloud']
            | cfg.QA_BITMASK['cloud_shadow'] | cfg.QA_BITMASK['snow'])

    def observations(self, tile, start, end, rules):
        sel = ['system:index', 'system:time_start', 'DATE_ACQUIRED', 'WRS_PATH', 'WRS_ROW', 'CLOUD_COVER']
        groups = {}
        for sc, cid in LANDSAT_C2.items():
            col = ee.ImageCollection(cid).filterBounds(tile.geometry).filterDate(start, end)
            for d in _rows(col, sel):
                d['asset'] = f"{cid}/{d['system:index']}"
                groups.setdefault((d['DATE_ACQUIRED'], sc), []).append(d)
        obs = []
        for (date, sc), g in sorted(groups.items()):
            g.sort(key=lambda d: d['WRS_ROW'])
            keep = [d for d in g if d['CLOUD_COVER'] < rules.scene_cloud_max]
            t = _utc(g[0]['system:time_start'])
            obs.append({
                'sensor': self.name, 'sana': date, 'sun_yoldosh': sc.replace('LANDSAT_', 'L'),
                'path': g[0]['WRS_PATH'], 'qatorlar': ', '.join(str(d['WRS_ROW']) for d in g),
                'id': ', '.join(d['system:index'] for d in g),
                'UTC': t.strftime('%H:%M'), 'mahalliy_quyosh': _solar(t, tile.lon),
                'metadata_bulut_%': ', '.join(f"{d['CLOUD_COVER']:.0f}" for d in g),
                'pre_ok': bool(keep),
                'sabab': '' if keep else f"sahna buluti ≥ {rules.scene_cloud_max:.0f}% (metadata)",
                '_refs': [d['asset'] for d in keep],
            })
        return obs

    def scenes(self, tile, start, end):
        """Davrda tile'ga tekkan WRS sahnalari (path/row) — har biri uchun davrdagi birinchi tasvir
        (footprint har sanada deyarli bir xil). Qoplash jadvali va xarita uchun; bulutga qaralmaydi."""
        sel = ['system:index', 'WRS_PATH', 'WRS_ROW', 'DATE_ACQUIRED']
        out = {}
        for cid in LANDSAT_C2.values():
            col = ee.ImageCollection(cid).filterBounds(tile.geometry).filterDate(start, end)
            for d in _rows(col, sel):
                key = (d['WRS_PATH'], d['WRS_ROW'])
                if key not in out or d['DATE_ACQUIRED'] < out[key]['sana']:
                    out[key] = {'WRS': f'{key[0]}{key[1]:03d}', 'path': key[0], 'row': key[1],
                                'sana': d['DATE_ACQUIRED'], 'asset': f"{cid}/{d['system:index']}"}
        return [out[k] for k in sorted(out)]

    def image(self, o, rules):
        ims = []
        for a in o['_refs']:
            qa = ee.Image(a).select('QA_PIXEL')
            seen = qa.bitwiseAnd(cfg.QA_BITMASK['fill']).eq(0)
            ims.append(_seen_bad(seen, qa.bitwiseAnd(self._BAD).neq(0)))
        return _mosaic(ims)


class Hls:
    """HLS v2 L30 / S30 — MGRS granula (kesish shart emas)."""
    scale = 100
    _BAD = (cfg.HLS_QA_BITMASK['cirrus'] | cfg.HLS_QA_BITMASK['cloud'] | cfg.HLS_QA_BITMASK['adjacent']
            | cfg.HLS_QA_BITMASK['cloud_shadow'] | cfg.HLS_QA_BITMASK['snow'])

    def __init__(self, which):
        self.which, self.name, self.cid = which, f'HLS_{which}', HLS[which]

    def observations(self, tile, start, end, rules):
        sel = ['system:index', 'system:time_start', 'CLOUD_COVERAGE', 'SPATIAL_COVERAGE']
        col = (ee.ImageCollection(self.cid).filterBounds(tile.geometry).filterDate(start, end)
               .filter(ee.Filter.stringStartsWith('system:index', tile.id)))
        obs = []
        for d in _rows(col, sel):
            t = _utc(d['system:time_start'])
            ok = d['CLOUD_COVERAGE'] < rules.scene_cloud_max
            obs.append({
                'sensor': self.name, 'sana': t.strftime('%Y-%m-%d'), 'id': d['system:index'],
                'UTC': t.strftime('%H:%M'), 'mahalliy_quyosh': _solar(t, tile.lon),
                'metadata_bulut_%': d['CLOUD_COVERAGE'], 'metadata_qoplash_%': d['SPATIAL_COVERAGE'],
                'pre_ok': ok,
                'sabab': '' if ok else f"granula buluti ≥ {rules.scene_cloud_max:.0f}% (metadata)",
                '_refs': [f"{self.cid}/{d['system:index']}"],
            })
        return sorted(obs, key=lambda o: (o['sana'], o['UTC']))

    def image(self, o, rules):
        img = ee.Image(o['_refs'][0])
        seen = img.select('B4').mask().gt(0)
        return _seen_bad(seen, img.select('Fmask').bitwiseAnd(self._BAD).neq(0)).unmask(0, False)


class Viirs:
    """VNP21A1D (Suomi NPP, 1 km, kunlik). Toza = LST bor, QC 0–1 va 4–5-bitlar 0, |VZA| ≤ chegara.
    Kuzatilgan = LST bor YOKI QC 0–1 = 2/3 ("bulut / boshqa sabab bilan ishlab chiqilmagan").
    LST yo'q va QC 0 — ma'lumot yo'q: GEE'da QC bu yerda 0 bilan to'ldirilgan (2025-07-05/06 T42SUJ'da
    tekshirildi), "toza" emas. VZA ma'lum va chegaradan katta piksel — ko'rilmagan (geometriya)."""
    name = 'VIIRS'
    scale = 1000

    def observations(self, tile, start, end, rules):
        ids = ee.ImageCollection(VIIRS_LST).filterDate(start, end).aggregate_array('system:index').getInfo()
        return [{'sensor': self.name, 'sana': i.replace('_', '-'), 'id': i, 'pre_ok': True, 'sabab': '',
                 '_refs': [f'{VIIRS_LST}/{i}']} for i in sorted(ids)]

    def _parts(self, o, rules):
        img = ee.Image(o['_refs'][0])
        qc = img.select('QC')
        q01 = qc.bitwiseAnd(3)
        lst = img.select('LST_1KM').mask().gt(0)
        vza = img.select('View_Angle').abs()
        observed = lst.Or(q01.gte(2))
        good = (lst.And(q01.eq(0)).And(qc.rightShift(4).bitwiseAnd(3).eq(0))
                .And(vza.lte(rules.viirs_vza_max)))
        return img, observed, vza, good

    def image(self, o, rules):
        _, observed, vza, good = self._parts(o, rules)
        seen = observed.And(vza.gt(rules.viirs_vza_max).unmask(0, False).Not())
        return _seen_bad(seen, good.unmask(0, False).Not()).unmask(0, False)

    def geometry_bands(self, o, rules):
        """|VZA| (hamma LST piksel) va toza piksellardagi |VZA|, View_Time — tile medianasi uchun."""
        img, _, vza, good = self._parts(o, rules)
        return ee.Image.cat([vza.rename('VZA_ALL'), vza.updateMask(good).rename('VZA'),
                             img.select('View_Time').updateMask(good).rename('VT')])


class Ecostress:
    """ECOSTRESS L2T LSTE (MGRS granula, 70 m). Toza = cloud 0 va QC 0–1-bitlar ≤ 1 (oldingi sinovdagidek).
    Vaqt oynasi va VZA chegarasi — VAQTINCHA (rules.eco_*)."""
    name = 'ECOSTRESS'
    scale = 100

    def observations(self, tile, start, end, rules):
        col = (ee.ImageCollection(ECOSTRESS_LST).filterBounds(tile.geometry).filterDate(start, end)
               .filter(ee.Filter.stringEndsWith('system:index', tile.id[1:])))
        rows = sorted(_rows(col, ['system:index', 'system:time_start']),
                      key=lambda d: d['system:time_start'])
        passes = []
        for d in rows:                      # bir o'tish: oldingi granuladan ≤ 5 daqiqa
            if passes and d['system:time_start'] - passes[-1][-1]['system:time_start'] <= 300000:
                passes[-1].append(d)
            else:
                passes.append([d])
        h0, h1 = rules.eco_local_hours
        obs = []
        for p in passes:
            t = _utc(p[0]['system:time_start'])
            loc = _solar(t, tile.lon)
            ok = h0 <= loc <= h1
            obs.append({
                'sensor': self.name, 'sana': (t + dt.timedelta(hours=tile.lon / 15)).strftime('%Y-%m-%d'),
                'id': ', '.join(d['system:index'] for d in p), 'UTC': t.strftime('%H:%M'),
                'mahalliy_quyosh': loc, 'pre_ok': ok,
                'sabab': '' if ok else f"mahalliy vaqt {loc:.1f} — {h0:.0f}–{h1:.0f} oynasidan tashqarida",
                '_refs': [f"{ECOSTRESS_LST}/{d['system:index']}" for d in p],
                '_t0': p[0]['system:time_start'],
            })
        return obs

    def image(self, o, rules):
        ims = []
        for a in o['_refs']:
            im = ee.Image(a)
            cloud = im.select('cloud')
            observed = im.select('LST').mask().gt(0).Or(cloud.eq(1).unmask(0, False))
            seen = observed.And(im.select('view_zenith').gt(rules.eco_vza_max).unmask(0, False).Not())
            good = cloud.eq(0).And(im.select('QC').bitwiseAnd(3).lte(1)).unmask(0, False)
            ims.append(_seen_bad(seen, good.Not()))
        return _mosaic(ims)
