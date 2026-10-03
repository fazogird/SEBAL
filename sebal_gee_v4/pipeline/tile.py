"""
Tile pasporti — MGRS tile: HLS/MGRS 30 m grid, UTM zona, Esri ekin ulushi (har yil o'z yili).

Grid manbai — shu tile'ning HLS granulasi (yuqori-chap burchak x0, y0). MGRS 100 km kvadrat
harflaridan faqat taxminiy markaz olinadi (granulani qidirish uchun); aniq burchak har doim
granuladan (S2 tile burchagi 100 km panjaradan ±20–40 m farq qiladi, masalan T41SQC x0=699960).
"""
import ee

from .rules import HLS, ESRI_LULC, ESRI_CROPS

_COLS = {1: 'ABCDEFGH', 2: 'JKLMNPQR', 0: 'STUVWXYZ'}   # zona % 3 → 100 km ustun harflari
_ROWS = 'ABCDEFGHJKLMNPQRSTUV'                         # 100 km qator harflari (2000 km sikl)
_BANDS = 'CDEFGHJKLMNPQRSTUVWX'                        # kenglik bandlari, −80° dan har 8°
_M_PER_DEG = 110946.0                                  # faqat 2000 km siklini tanlash uchun


def square_center(tile_id):
    """MGRS 100 km kvadrati markazi: (zona, easting, northing), shimoliy yarimshar."""
    zone, band, col, row = int(tile_id[1:3]), tile_id[3], tile_id[4], tile_id[5]
    east = (_COLS[zone % 3].index(col) + 1) * 100000 + 50000
    north100 = ((_ROWS.index(row) - (5 if zone % 2 == 0 else 0)) % 20) * 100000
    lat_mid = -80 + 8 * _BANDS.index(band) + 4
    k = round((lat_mid * _M_PER_DEG - north100) / 2e6)
    return zone, east, north100 + k * 2e6 + 50000


class MgrsTile:
    SIDE = 109800.0

    def __init__(self, tile_id):
        tid = tile_id.upper()
        self.id = tid if tid.startswith('T') else 'T' + tid
        self.zone, e, n = square_center(self.id)
        self.crs = f'EPSG:{32600 + self.zone}'
        self.x0, self.y0 = self._origin(ee.Geometry.Point([e, n], self.crs))
        self.geometry = ee.Geometry.Rectangle(
            [self.x0, self.y0 - self.SIDE, self.x0 + self.SIDE, self.y0], self.crs, False)
        self.lon, self.lat = self.geometry.centroid(1).coordinates().getInfo()
        self._esri_years = None

    def _origin(self, hint):
        for key in ('S30', 'L30'):
            col = (ee.ImageCollection(HLS[key]).filterBounds(hint)
                   .filter(ee.Filter.stringStartsWith('system:index', self.id)).limit(1))
            if col.size().getInfo():
                p = ee.Image(col.first()).select('B4').projection().getInfo()
                if p['crs'] != self.crs:
                    raise RuntimeError(f"{self.id}: HLS CRS {p['crs']} ≠ kutilgan {self.crs}")
                return p['transform'][2], p['transform'][5]
        raise RuntimeError(f"{self.id}: HLS granulasi topilmadi — tile nomini tekshiring")

    def transform(self, scale):
        return [scale, 0, self.x0, 0, -scale, self.y0]

    def proj(self, scale):
        return ee.Projection(self.crs, self.transform(scale))

    # ---- Esri LULC (har yil o'z yili; yo'q bo'lsa eng yaqin oldingi yil) ----
    def esri_year(self, year):
        if self._esri_years is None:
            ys = (ee.ImageCollection(ESRI_LULC).filterBounds(self.geometry)
                  .aggregate_array('system:time_start')
                  .map(lambda t: ee.Date(t).get('year')).distinct().sort().getInfo())
            self._esri_years = [int(y) for y in ys]
        past = [y for y in self._esri_years if y <= year]
        return past[-1] if past else self._esri_years[0]

    def lulc(self, year):
        """Esri 10 m sinflari, tile'ning 10 m gridida (zona chegarasidagi tile — ikki zona mozaikasi)."""
        y = self.esri_year(year)
        col = (ee.ImageCollection(ESRI_LULC).filterBounds(self.geometry)
               .filterDate(f'{y}-01-01', f'{y + 1}-01-01'))
        return col.mosaic().select(0).rename('LULC').setDefaultProjection(self.proj(10))

    def class_fraction(self, year, cls, scale=100):
        """Esri sinfi (cls) ULUSHI 0..1, scale ≤ 100 m, tile gridida.
        Tile'ning o'z UTM zonasidagi Esri tasviri — 10 m dan to'g'ridan-to'g'ri tile gridiga (aniq, avvalgidek).
        BOSHQA zonadagi tasvir (zona chegarasidagi tile) — avval O'Z zonasida `scale` ga kamaytiriladi, keyin
        shu masshtabda tile gridiga o'tadi: aks holda u butun tile bo'ylab 10 m da qayta proyeksiyalanadi va 1 km /
        masofa hisoblarida "Reprojection output too large (11000x11000)" chiqadi (Bushland T13SGU, 2026-09-30)."""
        y = self.esri_year(year)
        proj = self.proj(scale)
        crs = ee.String(self.crs)
        col = (ee.ImageCollection(ESRI_LULC).filterBounds(self.geometry)
               .filterDate(f'{y}-01-01', f'{y + 1}-01-01'))

        def frac(im):
            b = im.select(0)
            f = b.eq(cls).toFloat().reduceResolution(ee.Reducer.mean(), maxPixels=1024)
            own = b.projection()
            return ee.Image(ee.Algorithms.If(own.crs().equals(crs), f.reproject(proj),
                                             f.reproject(own.atScale(scale))))
        return col.map(frac).mosaic().setDefaultProjection(proj)

    def crop_fraction(self, year, scale):
        """Piksel ichidagi ekin (Esri 5) ULUSHI 0..1 — 10 m dan reduceResolution(mean) (class_fraction).
        scale ≤ 100 m bir bosqichda; kattasi (VIIRS 1 km) 100 m orqali ikki bosqichda."""
        f100 = self.class_fraction(year, ESRI_CROPS, min(scale, 100))
        if scale <= 100:
            return f100.rename('CROP')
        return (f100.reduceResolution(ee.Reducer.mean(), maxPixels=1024)
                .reproject(self.proj(scale)).rename('CROP'))

    def crop_mask(self, year, scale=30):
        """Chiqish uchun CROP_MASK (0/1): piksel yuzasining ≥ 50% i ekin."""
        return self.crop_fraction(year, scale).gte(0.5).toByte().rename('CROP_MASK')


def mgrs_tiles_for(region, year, log=print):
    """Hududni (viloyatni) qoplovchi MGRS tile'lar — HLS L30/S30 granula nomlaridan (shu yil iyuni).
    user 2026-09-29: har viloyatni birma-bir ko'rib o'tirmaslik uchun avtomatik; ortiqchasi (hudud ekini
    oz yoki boshqa tile bilan to'liq qoplangan) plan_tiles'da tushadi. S30 filterBounds ba'zan uzoq
    granula qaytaradi — hudud UTM zonalaridan tashqaridagilar tashlanadi."""
    lons = [c[0] for c in region.bounds(100).coordinates().get(0).getInfo()]
    zones = set(range(int((min(lons) + 180) // 6) + 1, int((max(lons) + 180) // 6) + 2))
    ids = []
    for cid in HLS.values():
        ids += (ee.ImageCollection(cid).filterBounds(region).filterDate(f'{year}-06-01', f'{year}-07-01')
                .aggregate_array('system:index').getInfo())
    tiles = sorted({i.split('_')[0] for i in ids if i[:1] == 'T' and i[1:3].isdigit() and int(i[1:3]) in zones})
    log(f"  Hudud tile'lari (HLS {year}-06, UTM {sorted(zones)}): {tiles}")
    return tiles


def plan_tiles(tile_ids, region, year, min_crop_km2=100.0, log=print):
    """Ishga tushirish rejasi (hudud → tile'lar → ekin) — har viloyat uchun bir xil, avtomatik qoida
    (user 2026-09-29):
      1) har tile'ning to'liq footprint'idagi hudud ekini C — kalibratsiya (kalendar, anchor) shu yerda;
      2) C < min_crop_km2 → tile tushiriladi (kichik maydondan anchor ishonchsiz);
      3) egalik (eksport, ustma-ustliksiz): qolgan tile'lar C kamayishi tartibida — birinchisi butun
         footprint'ini oladi, keyingisi faqat oldingilar olmagan qismini ("bittasi butun, qolgani kesik");
         egaligida hudud ekini < 1 km² bo'lgan tile (boshqalar bilan to'liq qoplangan) ishlanmaydi;
      4) bo'shliq — qolgan tile'lar qoplamagan hudud ekini (tushirilgan tile'lardan qolgani).
    Ekin — Esri 5 (tile'da 100 m ulush; hudud jami — 100 m tanlama, shu sabab ±0.1% farq bo'ladi).
    Qaytaradi: (qatorlar, jami lug'at, {ishlanadigan tile: egalik geometriyasi})."""
    tiles = {t: MgrsTile(t) for t in tile_ids}
    km2 = lambda img: img.multiply(ee.Image.pixelArea()).divide(1e6).rename('km2')

    def crop_in(t, geom):
        return km2(t.crop_fraction(year, 100)).reduceRegion(
            ee.Reducer.sum(), geom.intersection(region, ee.ErrorMargin(30)), crs=t.crs,
            crsTransform=t.transform(100), maxPixels=1e10, tileScale=4).get('km2')

    def fetch(items):
        out = []
        for i in range(0, len(items), 4):                 # "Too many concurrent aggregations" dan qochish
            out += ee.List(items[i:i + 4]).getInfo()
        return [v or 0.0 for v in out]

    C = dict(zip(tile_ids, fetch([crop_in(tiles[t], tiles[t].geometry) for t in tile_ids])))
    order = sorted([t for t in tile_ids if C[t] >= min_crop_km2], key=lambda t: -C[t])
    geom, claimed = {}, None
    for t in order:
        g = tiles[t].geometry
        geom[t] = g if claimed is None else g.difference(claimed, ee.ErrorMargin(1))
        claimed = g if claimed is None else claimed.union(g, ee.ErrorMargin(1))
    O = dict(zip(order, fetch([crop_in(tiles[t], geom[t]) for t in order])))
    ey = tiles[tile_ids[0]].esri_year(year)
    total = ee.Number(km2(ee.ImageCollection(ESRI_LULC).filterBounds(region)
                          .filterDate(f'{ey}-01-01', f'{ey + 1}-01-01').mosaic().select(0).eq(ESRI_CROPS))
                      .reduceRegion(ee.Reducer.sum(), region, crs='EPSG:4326', scale=100, maxPixels=1e11,
                                    tileScale=8).get('km2')).getInfo() or 0.0
    rows = []
    for t in sorted(tile_ids, key=lambda t: (order.index(t) if t in order else 99, t)):
        o = O.get(t, 0.0)
        if t not in O:
            holat = f"tushirildi: tile'da hudud ekini {C[t]:.0f} km² < {min_crop_km2:.0f} km² (anchor ishonchsiz)"
        elif o < 1.0:
            holat = "tushirildi: boshqa tile'lar bilan to'liq qoplangan"
        else:
            holat = 'butun' if o >= 0.995 * C[t] else f"kesik: egaligida {o:.0f} km² (tile'da {C[t]:.0f})"
        rows.append({'tile': t, 'tartib': order.index(t) + 1 if t in order else None,
                     'ekin_tile_km2': round(C[t], 1), 'ekin_egalik_km2': round(o, 1),
                     'hudud_ekinidan_%': round(100 * o / total, 1) if total else None,
                     'ishlanadi': t in O and o >= 1.0, 'holat': holat})
    s_own = sum(r['ekin_egalik_km2'] for r in rows)
    summary = {'hudud_ekini_km2': round(total, 1), 'egalik_yigindisi_km2': round(s_own, 1),
               'boshliq_km2': round(max(total - s_own, 0.0), 1),
               'qoplangan_%': round(100 * min(s_own / total, 1.0), 1) if total else None,
               'min_crop_km2': min_crop_km2}
    log(f"  Tile rejasi — hudud ekini (Esri {ey}): {summary['hudud_ekini_km2']} km², ishlanadigan tile'lar "
        f"egaligida {summary['egalik_yigindisi_km2']} km² ({summary['qoplangan_%']}%), bo'shliq "
        f"≈{summary['boshliq_km2']} km² (100 m tanlama farqi ±0.1% ichida)")
    for r in rows:
        log(f"    {r['tile']}: tile'da {r['ekin_tile_km2']:7.1f} km² → egaligida {r['ekin_egalik_km2']:7.1f} km² "
            f"| {r['holat']}")
    return rows, summary, {t: geom[t] for t in order if O[t] >= 1.0}
