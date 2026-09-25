"""
SEBAL-GEE v4 — Main Pipeline (Production)
===========================================
Ishlatish: run_sebal.py dan chaqiriladi.

Xususiyatlar:
  - Oylik: har produkt alohida TIF (True/False)
  - Kunlik: multi-band (1 fayl per sahna)
  - Tile-based: WRS path/row bo'yicha alohida ishlash
  - ROI: gaul, rectangle, shapefile, point
"""

import ee

from . import config as cfg
from . import preprocessing
from . import surface_props
from . import radiation
from . import energy_balance
from . import daily_et
from . import ref_et
from . import et_decomposition, soil_moisture, biomass, irrigation


# ==============================================================
# DAILY BAND SETS
# ==============================================================

DAILY_BANDS_SEBAL_B = [
    'ET_24', 'LAMBDA_E', 'H', 'RN', 'G0', 'EVAP_FRAC', 'NDVI', 'LST','LAI',
]

DAILY_BANDS_PYSEBAL = [
    'ET_24', 'ETREF_24', 'ETPOT_24', 'ET_DEFICIT',
    'KC', 'KC_MAX', 'ADV_FACTOR',
    'TACT_24', 'EACT_24', 'TPOT_24', 'T_DEFICIT',
    'BENEFICIAL_FRACTION', 'MOISTURE_STRESS',
    'TOP_SOIL_MOISTURE', 'ROOT_ZONE_MOISTURE', 'SM_WETNESS',
    'FPAR', 'APAR', 'LUE',
    'BIOMASS_PROD', 'WATER_PRODUCTIVITY', 'BIOMASS_DEFICIT',
    'IRRIGATION_CLASS', 'IRRIGATION_DEPTH',
    'NDVI', 'LST',
]


# ==============================================================
# WRS TILES — path/row aniqlash
# ==============================================================

def detect_wrs_tiles(roi, date_start, date_end, satellite='BOTH', cloud_max=20):
    """
    ROI ichidagi WRS path/row larni aniqlash.
    Qaysi tilelar mavjud ekanini ko'rsatadi.
    """
    collections = []
    if satellite in ('BOTH', 'L8'):
        collections.append('LANDSAT/LC08/C02/T1_L2')
    if satellite in ('BOTH', 'L9'):
        collections.append('LANDSAT/LC09/C02/T1_L2')

    tiles = set()
    for col_id in collections:
        col = (ee.ImageCollection(col_id)
               .filterBounds(roi)
               .filterDate(date_start, date_end)
               .filter(ee.Filter.lte('CLOUD_COVER', cloud_max))) # Agar ≤20% bulsa

        props = col.aggregate_array('WRS_PATH').zip(
            col.aggregate_array('WRS_ROW')).distinct().getInfo()

        for p, r in props:
            tiles.add((p, r))

    return sorted(tiles)


def get_tile_geometry(path, row):
    """WRS path/row geometriyasini Landsat C2 dan olish."""
    tile = (ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
            .filter(ee.Filter.eq('WRS_PATH', path))
            .filter(ee.Filter.eq('WRS_ROW', row))
            .first()
            .geometry())
    return tile


def get_hls_tile_geometry(mgrs_tile, date_start='2024-01-01',
                          date_end='2027-01-01'):
    """
    HLS (MGRS) tile footprint geometriyasi — granula chegarasidan.
    Sana filtri SHART: butun arxivni stringContains bilan skanlamaslik
    uchun (aks holda "Computation timed out").
    """
    tid = mgrs_tile if mgrs_tile.startswith('T') else f'T{mgrs_tile}'
    img = (ee.ImageCollection(cfg.HLS_COLLECTION)
           .filterDate(date_start, date_end)
           .filter(ee.Filter.stringContains('system:index', tid))
           .first())
    return ee.Image(img).geometry()

# ==============================================================
# BITTA TILE NI ISHLASH
# ==============================================================

def process_tile(roi, date_start, date_end, mode, satellite, cloud_max,
                 tile_label='', anchor_method='cimec',
                 anchor_mode='median_anchor',
                 cloud_roi=None, cloud_use_cropland=True,
                 ref_type='alfalfa', utc_offset=None, etr24_source='era5',
                 sloping_terrain=False):
    """
    Bitta ROI/tile uchun SEBAL pipeline.
    Returns:
    tuple: (list of processed ee.Image objects, info dict)
    """
    prefix = f"  [{tile_label}]" if tile_label else "  "

    # SEBAL_Milliy_Kc: sahna bosqichi AYNAN SEBAL_Milliy kabi (NDVI + barcha band
    # kerak). Oylik ET esa Kc-quruvchi (cfg.is_kc_mode) bilan alohida quriladi —
    # u main.run'dagi ASL mode bilan compute_monthly_et'ga boradi. Shu sabab bu
    # yerda (faqat sahna ishlab chiqarish uchun) mode'ni Milliy'ga normallashtiramiz.
    if cfg.is_kc_mode(mode):
        print(f"{prefix} ℹ️ SEBAL_Milliy_Kc → sahnalar SEBAL_Milliy kabi, "
              f"oylik ET = NDVI-langan FAO-56 Kc")
        mode = 'SEBAL_Milliy'

    # SEBAL_ID: anchor BITTA NUQTA bo'lishi shart (cold/hot dT hamda hot suv
    # balansi AYNI bir pikselga tayanadi — izchillik). Metod (cimec/plan/…)
    # kandidatlarni topadi, point_anchor ulardan bittasini oladi.
    if cfg.is_id_mode(mode) and anchor_mode != 'point_anchor':
        print(f"{prefix} ℹ️ {mode} → anchor_mode='point_anchor' (bitta nuqta) majburiy")
        anchor_mode = 'point_anchor'

    # Mahalliy standart vaqt zonasi (SEBAL Manual App.5-A; DST YO'Q).
    # Kunlik oyna (Rs24 / ETr24) shu offsetga ko'ra mahalliy kunga bog'lanadi.
    if utc_offset is None:
        utc_offset = daily_et.utc_offset_from_roi(roi)
        print(f"{prefix} 🕒 utc_offset avtomatik = {utc_offset:+d} soat "
              f"(zona markazi ≈ boylam/15; aniq bo'lmasa qo'lda bering)")
    # ERA5-Land soatlik to'liqligi (W2): sahna kunlari, oylik hisob oylari va hot suv
    # balansi orqaga qarashi (max_lookback) — HAR soat bo'lishi shart (BITTA getInfo).
    from datetime import datetime as _dt, timedelta as _td
    _ds = _dt.strptime(date_start, '%Y-%m-%d')
    _de = _dt.strptime(date_end, '%Y-%m-%d')
    _e5_start = (_ds.replace(day=1) - _td(days=cfg.HOT_WB['max_lookback'] + 2)).strftime('%Y-%m-%d')
    _e5_end = ((_de.replace(day=1) + _td(days=32)).replace(day=1) + _td(days=2)).strftime('%Y-%m-%d')
    ref_et.check_era5_hours(_e5_start, _e5_end)

    # QIYA YUZA rejimi (Tasumi Ch.V): z_ws — "ob-havo stansiyasi" balandligi
    # (ERA5 uchun ROI o'rtacha balandligi; App.K: shamol ta'siri past)
    z_ws = 0.0
    if sloping_terrain:
        from . import sloping_terrain as slt
        dem_ref = ee.Image(cfg.DEM['collection']).select(cfg.DEM['band'])
        z_ws = slt.mean_elevation(dem_ref, roi)
        print(f"{prefix} ⛰️ sloping_terrain=True | z_ws (ROI o'rtacha) = {z_ws:.0f} m")
    # Tile label bo'lsa: P156_R032 kabi qiymatdan path/row ajratamiz
    if tile_label:
        is_hls = satellite == 'HLS'
        if is_hls:
            # HLS: tile_label = 'T42TVK'
            mgrs_tile = tile_label
            path_num = None
            row_num = None
        else:
            # Landsat: tile_label = 'P155_R33'
            mgrs_tile = None
            path_num = int(tile_label.split('_')[0].replace('P', ''))
            row_num = int(tile_label.split('_')[1].replace('R', ''))
    else:
        mgrs_tile = None
        path_num = None
        row_num = None
 
    collection = preprocessing.build_collection(
        roi=roi, date_start=date_start, date_end=date_end,
        satellite=satellite, cloud_max=cloud_max,
        mosaic_same_date=True,   # 1 tasvirli sanaga tegmaydi (tile rejimida ham xavfsiz)
        wrs_path=path_num, wrs_row=row_num,
        mgrs_tile=mgrs_tile,
        cloud_roi=cloud_roi, cloud_use_cropland=cloud_use_cropland)
    info = preprocessing.collection_info(collection)

    if tile_label:
        print(
            f"{prefix} Filtrlangan: "
            f"Path={path_num} Row={row_num} → {info['image_count']} tasvir"
        )

    print(f"{prefix} Tasvirlar: {info['image_count']} | {info['dates']}")
    # Per-piksel quyosh burchaklari (SZA/SAA) manbai — preprocessing.add_sun_angles
    _src = info['solar_src']
    if len(_src) != info['image_count']:
        raise RuntimeError(f"{prefix} SOLAR_GEOM_SOURCE soni ({len(_src)}) != tasvirlar "
                           f"({info['image_count']})")
    _n_ok = sum(1 for s_ in _src if s_ in ('L1_ANGLE', 'HLS_ANGLE'))
    print(f"{prefix} ☀️ Quyosh burchaklari SZA/SAA (per-piksel, K↓ / albedo BRDF / qiyalik): "
          f"{_n_ok}/{len(_src)} sahna o'z burchak bandidan"
          f" ({', '.join(sorted(set(_src)))})")
    for _d, _s in zip(info['dates'], _src):
        if _s not in ('L1_ANGLE', 'HLS_ANGLE'):
            print(f"{prefix}   ⚠️ {_d}: mos L1 sahna topilmadi → {_s} "
                  f"(astronomik per-piksel SZA/SAA; L1 bilan farq ≤ ~0.25°)")

    if info['image_count'] == 0:
        print(f"{prefix} ⚠️ Tasvir yo'q, o'tkazildi")
        return [], info

    # Surface props (mode → SEBAL_ID emissivity Eq.4.28 uchun)
    collection = collection.map(lambda im: surface_props.compute_all(im, mode, roi))

    # ---- Anchor zonalari — TILE uchun BIR MARTA (cold=cropland, hot=bare+shrub) ----
    # Sinf ULUSHI rasmlari; sahnada ulush ≥0.80 → 0.70 → 0.60 → ROI.
    cold_zone, hot_zone = energy_balance.compute_tile_anchor_zones(roi)

    # Radiation — L↓ usuli mode'dan (config.LDOWN_*). Noma'lum mode → xato.
    #   ERA5 (SEBAL_Milliy, yangiliklar): to'liq radiatsiya shu yerda (map).
    #   Empirik (SEBAL_ID, SEBAL_B, pysebal): Tref = cold anchor LST → map'da
    #   faqat L↓ ga bog'liq bo'lmagan qism; L↓/Rn/G₀ anchor tanlangandan KEYIN.
    ldown_empirical = cfg.ldown_is_empirical(mode)
    if ldown_empirical:
        collection = collection.map(
            lambda im: radiation.compute_pre_longwave(
                im, mode, sloping_terrain=sloping_terrain))
    else:
        collection = collection.map(
            lambda im: radiation.compute_all(
                im, mode, sloping_terrain=sloping_terrain))

    # Energy balance — har sahna alohida
    image_list = collection.toList(collection.size())
    n = info['image_count']

    scene_images = []
    scene_dates = []   # FAQAT saqlangan sahnalar sanasi (scene_images bilan indeksma-indeks)
    qc_rows = []       # sahna sifat hisoboti (OK / OGOHLANTIRISH / RAD ETILDI + sabab)

    def _reject(date, why, qc_, extra=None):
        qc_.update(extra or {})
        qc_.update({'status': 'RAD ETILDI', 'sabab': why})
        print(f"{prefix} ❌ Sahna {date}: {why} — O'TKAZIB YUBORILADI")

    for i in range(n):
        print(f"{prefix} Sahna {i + 1}/{n}...")

        img = ee.Image(image_list.get(i))
        qc = {'sana': info['dates'][i], 'quyosh_geom': info['solar_src'][i]}
        qc_rows.append(qc)

        # ---- Anchor tekshiruvi — YIQILISHDAN OLDIN ----
        # QIYA YUZA: anchor AYNI Ts maydonidan tanlanishi SHART — dT–Ts
        # munosabati LST_DEM bilan qurilgani uchun (energy_balance.compute_all
        # ichida). Aks holda cold/hot skalyarlari asl LST da, raster dT esa
        # LST_DEM da bo'lib, c5 (kesma) 0.0065·z ga siljib ketadi.
        def _anchor_view(im):
            if sloping_terrain:
                from . import sloping_terrain as _slt
                return im.addBands(_slt.lst_dem(im), overwrite=True)
            return im

        # Anchor → energiya balansi. Anchor topilib, FIZIK QC'dan o'tmasa (SceneQCError)
        # — o'sha (metod, zona) chetlanadi va kaskad KEYINGI metoddan davom etadi
        # (user qarori 2026-09-19). Har urinish L↓/energiya balansidan OLDINGI toza
        # tasvirdan boshlanadi; muvaffaqiyatsiz urinishlar QC'ga yoziladi.
        img_pre = img
        tried = []                      # [(metod, zona, fizik QC sababi)]
        img_ok = None
        while True:
            att = {}                    # shu urinishning QC maydonlari
            img = img_pre
            img_anchor = _anchor_view(img)
            # Empirik L↓: Rn−G₀ hali yo'q → anchor zona/LST tanlanadi (need_rn=False).
            anchors = energy_balance.select_anchor_pixels(
                img_anchor, roi, cold_zone=cold_zone, hot_zone=hot_zone,
                method=anchor_method, anchor_mode=anchor_mode,
                need_rn=not ldown_empirical,
                hot_soil=cfg.is_id_mode(mode),   # SEBAL_ID oilasi: hot — faqat tuproq piksel
                cold_full_cover=cfg.is_id_mode(mode),   # 1.05·ETr — to'liq qoplama (LAI ≥ 4)
                exclude={(m_, z_) for m_, z_, _ in tried})

            # Anchor LST/Rn−G₀/nuqta BIR MARTA hisoblanadi (klient konstantasi) —
            # keyingi barcha bosqichlar AYNI qiymat va AYNI pikselni ishlatadi.
            extra = {}
            if ldown_empirical:
                extra['tref'] = energy_balance.cold_anchor_surface_temp(
                    img, img_anchor, anchors, roi, anchor_mode)
            anchors, chk = energy_balance.materialize_anchors(anchors, extra)
            chk['cold_lst_1'] = chk.get('cold_lst')
            c_, h_ = chk.get('cold_lst'), chk.get('hot_lst')
            if c_ is not None and h_ is not None and c_ > 200 and h_ > 200:
                att.update({'cold_LST': c_, 'hot_LST': h_, 'dT_LST': h_ - c_})
            qc_tried = ("; fizik QC'dan o'tmagan anchor: " + "; ".join(
                f"{m_}/{z_} ({r_})" for m_, z_, r_ in tried)) if tried else ''

            if not chk['valid']:
                rn_bad = [sd for sd in ('cold', 'hot')
                          if f'{sd}_rn_g0' in chk and (chk[f'{sd}_rn_g0'] is None
                                                       or chk[f'{sd}_rn_g0'] <= -900)]
                if 'dT_LST' in att and att['dT_LST'] < cfg.ANCHOR['min_dt']:
                    why = (f"anchor ΔT = {h_ - c_:.1f} K < {cfg.ANCHOR['min_dt']} K "
                           f"(cold {c_:.1f} K, hot {h_:.1f} K)")
                elif 'dT_LST' in att and rn_bad:
                    why = f"anchor Rn−G₀ topilmadi ({'/'.join(rn_bad)})"
                else:
                    why = anchors.get('fail_reason') or "anchor: cold/hot nomzod topilmadi"
                qc.update(att)
                _reject(info['dates'][i], why + qc_tried, qc)
                break   # bu sahna scene_images ga QO'SHILMAYDI

            def _pur(v):
                return f"ulush ≥{v:.2f}" if v else "ROI (zona yetmadi)"
            print(f"{prefix}   anchor: {anchors.get('method')}/{anchors.get('zone')} | zona: cold "
                  f"{_pur(anchors['cold_zone_purity'])} | hot {_pur(anchors['hot_zone_purity'])}")
            att['anchor'] = f"{anchors.get('method')}/{anchors.get('zone')}"
            if anchors.get('note'):              # default zaxirasi ishlatilgan — QC'ga
                att.setdefault('warnings', []).append(anchors['note'])

            if ldown_empirical:
                # L↓ Tref = cold anchor pikselning asl LST — topilmasa TO'XTAYDI.
                if chk.get('tref') is None:
                    raise RuntimeError(
                        f"{prefix} Sahna {i + 1}/{n}: cold anchor LST (L↓ Tref) "
                        f"topilmadi — default harorat ishlatilmaydi.")
                tref = chk['tref']
                print(f"{prefix}   L↓ Tref = cold anchor LST ({anchor_mode}) = {tref:.2f} K")
                img = radiation.compute_longwave_balance(img, mode, tref=tref)
                # AYNI cold/hot maskalardan yakuniy qiymatlar (LST, Rn−G₀)
                img_anchor = _anchor_view(img)
                anchors = energy_balance.finalize_anchor_values(
                    img_anchor, roi, anchors, anchor_mode)
                anchors, chk2 = energy_balance.materialize_anchors(anchors)
                if not chk2['valid']:
                    qc.update(att)
                    _reject(info['dates'][i],
                            "anchor Rn−G₀ topilmadi (yakuniy bosqich)" + qc_tried, qc)
                    break
                if abs(chk2['cold_lst'] - chk['cold_lst_1']) > 0.01:
                    print(f"{prefix}   ⚠️ cold anchor LST 1-bosqich {chk['cold_lst_1']:.2f} K ≠ "
                          f"yakuniy {chk2['cold_lst']:.2f} K (Rn−G₀ maskasi farqi)")

            try:
                img = energy_balance.compute_all(
                    img, roi, cold_zone=cold_zone, hot_zone=hot_zone, anchors=anchors,
                    mode=mode, sloping_terrain=sloping_terrain, z_ws=z_ws, qc=att,
                    etr24_source=etr24_source)
            except energy_balance.SceneQCError as e:
                tried.append((anchors.get('method'), anchors.get('zone'), str(e)))
                print(f"{prefix}   ↪ {anchors.get('method')}/{anchors.get('zone')}: {e} "
                      f"— keyingi metod sinaladi")
                continue
            img_ok = img
            qc.update(att)
            if tried:
                qc.setdefault('warnings', []).append(qc_tried.lstrip('; '))
            break

        if img_ok is None:
            continue   # sahna rad etildi (sababi _reject'da)
        img = img_ok
        _grid_tpw_qc(img, roi, mode, qc, prefix)   # qiymatlarga TEGMAYDI
        img = daily_et.compute_daily_et(img, roi, mode=mode, ref_type=ref_type,
                                        utc_offset=utc_offset,
                                        etr24_source=etr24_source,
                                        sloping_terrain=sloping_terrain)
        _daily_qc(img, roi, mode, qc, prefix, sloping_terrain)   # qiymatlarga TEGMAYDI

        if mode == 'pysebal':
            img = et_decomposition.compute_all(img, roi, utc_offset=utc_offset)
            img = soil_moisture.compute_all(img)
            img = biomass.compute_all(img)
            img = irrigation.compute_all(img)
        else:
            # 'SEBAL_B' rejimida ham S30 ETrF va VIIRS(kc) ishlashi uchun
            # ETREF_24 (grass, ASCE-EWRI) va KC har sahnaga qo'shiladi.
            # pysebal'da bularni et_decomposition allaqachon beradi.

            img = ref_et.compute_etref_daily(img, roi, utc_offset=utc_offset)
            kc = (img.select('ET_24')
                  .divide(img.select('ETREF_24').max(0.5))
                  .clamp(0, 2.5).rename('KC'))
            img = img.addBands(kc)

        scene_images.append(img)
        scene_dates.append(info['dates'][i])
        qc['status'] = 'OGOHLANTIRISH' if qc.get('warnings') else 'OK'
        qc['sabab'] = '; '.join(qc.get('warnings', []))

    # ---- SAHNA SIFAT HISOBOTI — eksportdan OLDIN ----
    _scene_qc_report(qc_rows, prefix, tile_label, mode, date_start, date_end)

    # Biror oyda BIRONTA yaroqli sahna qolmasa — eksportdan OLDIN TO'XTAYDI
    # (o'sha oy qo'shni oylardan yolg'on to'ldirilmasin).
    months_all = sorted({d[:7] for d in info['dates']})
    months_ok = {d[:7] for d in scene_dates}
    empty = [m for m in months_all if m not in months_ok]
    if empty:
        lines = [f"   {r['sana']}: {r['sabab']}" for r in qc_rows
                 if r.get('status') == 'RAD ETILDI' and r['sana'][:7] in empty]
        raise RuntimeError(
            f"{prefix} Yaroqli sahna qolmagan oy(lar): {', '.join(empty)} — "
            f"eksport boshlanmadi. Rad etilgan sahnalar:\n" + "\n".join(lines))

    # info['dates']       — kolleksiyadagi BARCHA sanalar (oylar ro'yxati uchun)
    # info['scene_dates'] — faqat saqlangan sahnalar; scenes[i] ↔ scene_dates[i].
    # Anchor topilmay o'tkazilgan sahna bo'lsa ikkalasi farq qiladi.
    info['scene_dates'] = scene_dates
    info['utc_offset'] = utc_offset   # oylik hisob shu offsetni ishlatishi uchun
    info['sloping_terrain'] = sloping_terrain
    return scene_images, info


_GRID_QC_BANDS = ('LST', 'LAI', 'EMISSIVITY', 'L_UP', 'DTA', 'RN')


# Kunlik bosqich QC chegaralari — faqat LOG/QC-CSV ogohlantirishi (qiymatga tegmaydi)
ETRF_RAW_WARN = 1.10         # ETrF_raw > 1.10: cold anchordan (1.05) sezilarli "namroq"
ETRF_RAW_WARN_PCT = 1.0      # ekinzor piksellarining shu %idan ko'pi → ogohlantirish
CRAD_CLAMP_WARN_PCT = 1.0    # C_RAD / RA24_RATIO [0.5, 2.0] chegarasidagi ROI piksellari %


def _daily_qc(img, roi, mode, qc, prefix, sloping_terrain=False):
    """
    Kunlik bosqich QC (qiymatlarga TEGMAYDI), BITTA getInfo (kerak bo'lsa):
      1) SEBAL_ID oilasi: ETRF_RAW (= ET_inst/ETr_inst, cheklanmagan) > ETRF_RAW_WARN
         bo'lgan EKINZOR piksellari ulushi va p99. SEBAL_ID ET_24 ETrF ni 1.05 da
         cheklaydi; SEBAL_Milliy — cheklamaydi (xom nisbat, user qarori (b)).
         Ulush > ETRF_RAW_WARN_PCT → OGOHLANTIRISH (sahna nam / cold anchor issiq?).
      2) sloping_terrain: C_RAD (SEBAL_ID oilasi) yoki RA24_RATIO (SEBAL_B, pysebal)
         [C_RAD_MIN, C_RAD_MAX] clamp chegarasiga urilgan ROI piksellari ulushi.
         > CRAD_CLAMP_WARN_PCT → OGOHLANTIRISH (tik/soya qiyalik — tuzatish kesilgan).
    """
    from . import sloping_terrain as slt
    req = {}
    kw = dict(geometry=roi, crs=energy_balance.analysis_proj(img), scale=90,
              maxPixels=1e9, bestEffort=True, tileScale=4)
    if cfg.is_id_mode(mode):
        raw = img.select('ETRF_RAW').updateMask(preprocessing.get_cropland_mask())
        req['etrf'] = (raw.gt(ETRF_RAW_WARN).rename('GT').addBands(raw.rename('R'))
                       .reduceRegion(ee.Reducer.mean().combine(
                           ee.Reducer.percentile([99]), sharedInputs=True), **kw))
    cband = None
    if sloping_terrain:
        cband = 'C_RAD' if cfg.is_id_mode(mode) else 'RA24_RATIO'
        c = img.select(cband)
        req['crad'] = (c.lte(slt.C_RAD_MIN + 1e-6).rename('LO')
                       .addBands(c.gte(slt.C_RAD_MAX - 1e-6).rename('HI'))
                       .reduceRegion(ee.Reducer.mean(), **kw))
    if not req:
        return
    d = ee.Dictionary(req).getInfo()
    e = d.get('etrf') or {}
    if e.get('GT_mean') is not None:
        pct, p99 = 100.0 * e['GT_mean'], e.get('R_p99')
        qc.update({'pct_etrf_gt110': pct, 'etrf_raw_p99': p99})
        if pct > ETRF_RAW_WARN_PCT:
            msg = (f"ETrF_raw > {ETRF_RAW_WARN} ekinzorning {pct:.1f} %ida "
                   f"(> {ETRF_RAW_WARN_PCT} %; p99 = {p99:.3f}) — "
                   + ("SEBAL_ID'da 1.05 ga kesilgan" if mode == 'SEBAL_ID'
                      else "SEBAL_Milliy ET_24 xom nisbat bilan (kesilmagan)")
                   + "; sahna nam yoki cold anchor issiq bo'lishi mumkin")
            print(f"{prefix}   ⚠️ OGOHLANTIRISH: {msg}")
            qc.setdefault('warnings', []).append(msg)
    c = d.get('crad') or {}              # yagona mean reduktor → kalitlar band nomi (LO, HI)
    if c.get('LO') is not None:
        lo, hi = 100.0 * c['LO'], 100.0 * c['HI']
        qc.update({'pct_crad_lo': lo, 'pct_crad_hi': hi})
        if lo + hi > CRAD_CLAMP_WARN_PCT:
            msg = (f"{cband} clamp chegarasida ROI'ning {lo + hi:.1f} %i "
                   f"(≤{slt.C_RAD_MIN}: {lo:.1f} %, ≥{slt.C_RAD_MAX}: {hi:.1f} %; "
                   f"> {CRAD_CLAMP_WARN_PCT} %) — tik/soya qiyalikda kunlik tuzatish kesilgan")
            print(f"{prefix}   ⚠️ OGOHLANTIRISH: {msg}")
            qc.setdefault('warnings', []).append(msg)


def _grid_tpw_qc(img, roi, mode, qc, prefix):
    """
    Sahna QC (qiymatlarga TEGMAYDI), BITTA getInfo:
      1) Grid — LST, LAI, EMISSIVITY, L_UP, DTA, RN proyeksiyasi Landsat tahlil
         gridiga (NDVI) teng bo'lishi shart; farq → OGOHLANTIRISH.
      2) SEBAL_Milliy (SMW LST): ROI ichidagi ERA5 TCWV min/max va TPW klass
         (0.6 sm) oralig'i → QC ustunlari; >1 klass → MA'LUMOT (A/B/C Ermida-original
         bilinear silliqlangan — pog'ona yo'q). Algoritm o'zgarmaydi.
    """
    bands = list(_GRID_QC_BANDS)            # compute_all'dan keyin doim mavjud
    req = {b: img.select(b).projection() for b in ('NDVI',) + _GRID_QC_BANDS}
    if mode == 'SEBAL_Milliy':
        tpw = radiation._era5_tcwv_cm(img).rename('TPW')
        req['tpw'] = tpw.reduceRegion(ee.Reducer.minMax(), roi, 1000, maxPixels=1e9,
                                      bestEffort=True, tileScale=4)
    d = ee.Dictionary(req).getInfo()
    ref = d['NDVI']
    ref_scale = abs(ref['transform'][0]) if ref.get('transform') else None
    qc['grid'] = f"{ref.get('crs')} {ref_scale:g}m" if ref_scale else ref.get('crs')
    bad = []
    for b in bands:
        p = d.get(b)
        if p is not None and (p.get('crs') != ref.get('crs')
                              or p.get('transform') != ref.get('transform')):
            sc = abs(p['transform'][0]) if p.get('transform') else '?'
            bad.append(f"{b} ({p.get('crs')}, {sc})")
    qc['grid_ok'] = not bad
    if bad:
        msg = f"proyeksiya Landsat gridi ({qc['grid']}) dan farq qiladi: {', '.join(bad)}"
        print(f"{prefix}   ⚠️ OGOHLANTIRISH: {msg}")
        qc.setdefault('warnings', []).append(msg)
    t = d.get('tpw') or {}
    if t.get('TPW_min') is not None:
        step, nb = radiation.SMW_TPW_STEP, radiation.SMW_TPW_NBIN
        b0 = min(max(int(t['TPW_min'] // step), 0), nb - 1)
        b1 = min(max(int(t['TPW_max'] // step), 0), nb - 1)
        qc.update({'TPW_min': t['TPW_min'], 'TPW_max': t['TPW_max'],
                   'TPW_bin_min': b0, 'TPW_bin_max': b1, 'n_TPW_bins': b1 - b0 + 1})
        if b1 > b0:
            # MA'LUMOT (ogohlantirish EMAS): A/B/C Ermida-original bilinear (radiation.
            # compute_lst_smw) → klass chegarasida LST pog'onasi yo'q; QC ustunlari qoladi.
            print(f"{prefix}   ℹ️ SMW: ROI ichida {b1 - b0 + 1} ta TPW klassi ({b0}–{b1}; TCWV "
                  f"{t['TPW_min']:.2f}–{t['TPW_max']:.2f} sm) — A/B/C bilinear silliqlangan (Ermida)")


def _scene_qc_report(rows, prefix, tile_label, mode, date_start, date_end):
    """Sahna sifat jadvali (print) + CSV (joriy papkada) — eksportdan OLDIN."""
    import csv
    cols = ['sana', 'status', 'sabab', 'quyosh_geom', 'anchor', 'cold_LAI', 'cold_LST', 'hot_LST', 'dT_LST', 'etrf_hot',
            'P_sum', 'window', 'converged', 'etrf_wet_start', 'etrf_dry_start', 'wet_reset',
            'De', 'Kr', 'TEW', 'REW', 'FC', 'WP',
            'dT_hot', 'dT_cold', 'H_hot', 'H_cold', 'dT_cold_neutral', 'rah_cold_ratio',
            'Ta_hot', 'Ta_era5_hot', 'Ta_cold', 'Ta_era5_cold', 'pct_Ta_out15',
            'grid', 'grid_ok', 'TPW_min', 'TPW_max', 'TPW_bin_min', 'TPW_bin_max', 'n_TPW_bins',
            'pct_etrf_gt110', 'etrf_raw_p99', 'pct_crad_lo', 'pct_crad_hi',
            'lon', 'lat']
    n_bad = sum(1 for r in rows if r.get('status') == 'RAD ETILDI')
    n_warn = sum(1 for r in rows if r.get('status') == 'OGOHLANTIRISH')
    print(f"\n{prefix} ===== SAHNA SIFAT HISOBOTI: {len(rows)} sahna | "
          f"rad etildi {n_bad} | ogohlantirish {n_warn} =====")

    def _f(v, n=2):
        return '' if v is None else (f'{v:.{n}f}' if isinstance(v, float) else str(v))
    for r in rows:
        if r.get('status') != 'OK':
            print(f"{prefix}   {r['sana']} | {r.get('status')} | {r.get('sabab')}")
    label = tile_label or 'ROI'
    fname = f"scene_qc_{mode}_{label}_{date_start}_{date_end}.csv"
    with open(fname, 'w', newline='', encoding='utf-8') as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction='ignore')
        w.writeheader()
        for r in rows:
            w.writerow({k: _f(r.get(k), 4) if isinstance(r.get(k), float) else r.get(k)
                        for k in cols})
    print(f"{prefix}   💾 {fname}")


# ==============================================================
# EXPORT — yumaloqlash (verguldan keyingi xonalar)
# ==============================================================

def _round_export(img):
    """
    Export oldidan verguldan keyin cfg.EXPORT_DECIMALS xona → float32.
    FAQAT eksport nusxasi yumaloqlanadi — oraliq hisob to'liq aniqlikda qoladi.
    cfg.EXPORT_DECIMALS_BY_BAND — alohida bandlar uchun boshqa xona soni.
    EXPORT_DECIMALS=None va override yo'q → faqat float32 (yumaloqlashsiz).
    """
    img = ee.Image(img)
    dec = cfg.EXPORT_DECIMALS
    over = cfg.EXPORT_DECIMALS_BY_BAND or {}
    if not over:
        if dec is None:
            return img.toFloat()
        f = 10 ** int(dec)
        return img.multiply(f).round().divide(f).toFloat()

    over_d = ee.Dictionary(over)
    names = img.bandNames()

    def _one(n):
        n = ee.String(n)
        band = img.select([n])
        d = ee.Number(over_d.get(n, -1 if dec is None else int(dec)))
        f = ee.Number(10).pow(d)
        rounded = band.multiply(f).round().divide(f)
        return ee.Image(ee.Algorithms.If(d.lt(0), band, rounded)).toFloat()

    return ee.ImageCollection.fromImages(names.map(_one)).toBands().rename(names)


# ==============================================================
# EXPORT — kunlik
# ==============================================================

def _export_daily(scene_images, roi, mode, folder, scale, crs,
                 tile_label=''):
    """Kunlik rasterlar — multi-band, har sahna alohida fayl."""
    bands = DAILY_BANDS_PYSEBAL if mode == 'pysebal' else DAILY_BANDS_SEBAL_B
    tasks = []

    for i, img in enumerate(scene_images):

        # GEE cache — tezlashtirish
        try:
            st = (img.select(['ET_24', 'NDVI'])
                  .reduceRegion(ee.Reducer.minMax(), roi, 1000,
                               maxPixels=1e8, bestEffort=True).getInfo())
            et_min = st.get('ET_24_min', 0)
            et_max = st.get('ET_24_max', 0)
            ndvi_max = st.get('NDVI_max', 0)
            print(f"  📊 ET: {et_min:.1f}-{et_max:.1f} mm/day | NDVI max: {ndvi_max:.2f}")
        except Exception:
            pass                                   # faqat diagnostika chiqishi
        d = (ee.Date(img.get('system:time_start'))
             .format('YYYY-MM-dd').getInfo())

        name = f'SEBAL_day_{d}'
        if tile_label:
            name = f'SEBAL_day_{d}_{tile_label}'
        available_bands = img.bandNames().getInfo()
        existing_bands = [b for b in bands if b in available_bands]
        missing_bands = [b for b in bands if b not in available_bands]

        if missing_bands:
            print(f"⚠️ Quyidagi bandlar topilmadi va export qilinmaydi: {missing_bands}")

        if not existing_bands:
            # Oldin `return None` → chaqiruvchida all_tasks.extend(None) xatosi va qolgan
            # sahnalar eksport qilinmasdi. Endi shu sahna o'tkaziladi, qolganlari davom etadi.
            print(f"❌ {name}: so'ralgan bandlardan hech biri yo'q — sahna eksport qilinmadi.")
            continue

        task = ee.batch.Export.image.toDrive(
            image=_round_export(img.select(existing_bands)),
            description=name, folder=folder, fileNamePrefix=name,
            region=roi, scale=scale, crs=crs,
            maxPixels=1e13, fileFormat='GeoTIFF')
        
        task.start()
        tasks.append(task)
        print(f"  ✅ {name} ({len(existing_bands)} band)")

    return tasks


# ==============================================================
# EXPORT — oylik (har produkt ALOHIDA raster)
# ==============================================================
 
def _viirs_export_month(scenes, info, tile_roi, year, month, month_key,
                        folder, scale, crs, tile_label,
                        viirs_mode, viirs_model, viirs_qa, viirs_fill, tasks):
    """
    Bitta oy uchun VIIRS-kuchaytirilgan oylik ET (tile ichida) → export.
    SEBAL o'zgarmaydi; faqat oylik ET ni VIIRS daily seriyasidan quradi.
    """
    import calendar
    from . import viirs_downscaling as vds

    days = calendar.monthrange(year, month)[1]
    m_start = f'{year}-{month:02d}-01'
    m_end = f'{year}-{month:02d}-{days:02d}'

    # Shu oydagi anchor sahnalar (scene_dates — scenes bilan indeksma-indeks)
    idx = [i for i, d in enumerate(info['scene_dates']) if d[:7] == month_key]
    m_scenes = [scenes[i] for i in idx]
    m_info = {'dates': [info['scene_dates'][i] for i in idx],
              'utc_offset': info.get('utc_offset', 0)}   # Rs24 — mahalliy kun
    if not m_scenes:
        print(f"  ⚠️ VIIRS {month_key}: anchor yo'q")
        return

    try:
        monthly = vds.build_tile_monthly_et_viirs(
            m_scenes, m_info, tile_roi, m_start, m_end,
            viirs_mode, viirs_model, viirs_qa, viirs_fill)
        suffix = f'_{tile_label}' if tile_label else ''
        name = f'SEBAL_VIIRS_ET_{month_key}{suffix}'
        task = ee.batch.Export.image.toDrive(
            image=_round_export(monthly), description=name, folder=folder,
            fileNamePrefix=name, region=tile_roi, scale=scale, crs=crs,
            maxPixels=1e13, fileFormat='GeoTIFF')
        task.start()
        tasks.append(task)
        print(f"  ✅ VIIRS ET {month_key} export boshlandi")
    except Exception as e:
        print(f"  ⚠️ VIIRS ET {month_key}: {e}")


def _s30_export_month(scenes, info, tile_roi, year, month, month_key,
                      folder, scale, crs, tile_label,
                      s30_model, s30_qa, s30_fill, cloud_max, tasks,
                      s30_cropland_only=False, s30_validate=False):
    """
    Bitta oy uchun HLS S30 ETrF regressiya oylik ET (tile ichida) → export.
    ET_daily = ETrF × ETREF_24_daily. SEBAL o'zgarmaydi.
    Diagnostika CSV (har anchor R²/N/eng yaqin S30) ham yoziladi.
    """
    import calendar
    import csv
    from . import hls_s30_etrf as s30

    days = calendar.monthrange(year, month)[1]
    m_start = f'{year}-{month:02d}-01'
    m_end = f'{year}-{month:02d}-{days:02d}'

    idx = [i for i, d in enumerate(info['scene_dates']) if d[:7] == month_key]
    m_scenes = [scenes[i] for i in idx]
    m_info = {'dates': [info['scene_dates'][i] for i in idx],
              'utc_offset': info.get('utc_offset', 0)}   # Rs24 — mahalliy kun
    if not m_scenes:
        print(f"  ⚠️ S30 {month_key}: anchor yo'q")
        return

    mgrs = tile_label if (tile_label and tile_label.startswith('T')) else None
    suffix = f'_{tile_label}' if tile_label else ''

    try:
        monthly, diag = s30.build_tile_monthly_etrf_s30(
            m_scenes, m_info, tile_roi, m_start, m_end,
            s30_model, s30_qa, s30_fill, cloud_max, mgrs,
            cropland_only=s30_cropland_only)

        name = f'SEBAL_S30_ET_{month_key}{suffix}'
        task = ee.batch.Export.image.toDrive(
            image=_round_export(monthly), description=name, folder=folder,
            fileNamePrefix=name, region=tile_roi, scale=scale, crs=crs,
            maxPixels=1e13, fileFormat='GeoTIFF')
        task.start()
        tasks.append(task)
        print(f"  ✅ S30 ET {month_key} export boshlandi")

        # Diagnostika CSV (har anchor)
        if diag:
            cname = f'S30_diag_{month_key}{suffix}.csv'
            with open(cname, 'w', newline='', encoding='utf-8') as f:
                w = csv.DictWriter(f, fieldnames=list(diag[0].keys()))
                w.writeheader()
                w.writerows(diag)
            print(f"  💾 {cname}")

        # Hold-out validatsiya (ixtiyoriy, 2+ anchor)
        if s30_validate and len(m_scenes) >= 2:
            vrows = []
            for hi in range(len(m_scenes)):
                res = s30.validate_holdout_s30(
                    m_scenes, m_info, tile_roi, m_start, m_end, hi,
                    s30_model, s30_qa, cloud_max, mgrs)
                if 'RMSE' in res:
                    vrows.append(res)
                    print(f"    holdout {res['holdout_date']}: "
                          f"RMSE={res['RMSE']:.3f} R2={res['R2']:.3f}")
            if vrows:
                vname = f'S30_holdout_{month_key}{suffix}.csv'
                with open(vname, 'w', newline='', encoding='utf-8') as f:
                    w = csv.DictWriter(f, fieldnames=list(vrows[0].keys()))
                    w.writeheader()
                    w.writerows(vrows)
                print(f"  💾 {vname}")
    except (ee.EEException, OSError, csv.Error) as e:
        print(f"  ⚠️ S30 ET {month_key}: {e}")


def _export_monthly(scene_images, roi, year, month, mode,
                   folder, scale, crs, tile_label='',
                   save_et=True, save_biomass=True,
                   save_etref=True, save_tact=True, save_eact=True,
                   etrf_water_balance=False, ref_type='alfalfa', utc_offset=0,
                   sloping_terrain=False, save_cuirr=False,
                   save_prz=False, save_niwr=False, save_aw=False,
                   dr_init_img=None):
    """
    Oylik rasterlar — har produkt ALOHIDA TIF.
    True/False bilan tanlash mumkin. save_aw → ildiz-zona water-balans AW bandlari.
    dr_init_img — oldingi oy oxiridagi Dr rasteri (mavsumiy-uzluksiz AW uchun).
    Qaytaradi: (tasks, dr_end_img) — dr_end_img keyingi oyga uzatiladi (save_aw'siz None).
    Barcha rasterlar ROI ga (tile ∩ viloyat) CLIP qilinadi — bo'sh qism saqlanmaydi.
    """
    from . import monthly_analytics
    tasks = []
    dr_end_img = None
    errors = []        # eksport xatolari — YUTILMAYDI, oxirida RuntimeError

    prefix = f'_{tile_label}' if tile_label else ''
    month_str = f'{year}-{month:02d}'

    print(f"  Oylik hisoblash {month_str}...")

    if mode == 'pysebal':
        monthly = monthly_analytics.compute_all_monthly(
            scene_images, roi, year, month, utc_offset=utc_offset,
            sloping_terrain=sloping_terrain)
    else:
        monthly = daily_et.compute_monthly_et(
            scene_images, roi, year, month, mode=mode,
            etrf_water_balance=etrf_water_balance,
            ref_type=ref_type, utc_offset=utc_offset,
            sloping_terrain=sloping_terrain)

    if monthly is None:
        print(f"  ❌ {month_str}: monthly image hosil bo‘lmadi.")
        return tasks, dr_end_img

    products = []
    if save_et:
        products.append(('ET', 'ET_MONTHLY', 'mm/month'))
    if save_biomass and mode == 'pysebal':
        products.append(('Biomass', 'BIOMASS_MONTHLY', 'kg/ha/month'))
    if save_etref and mode == 'pysebal':
        products.append(('ETref', 'ETREF_MONTHLY', 'mm/month'))
    if save_tact and mode == 'pysebal':
        products.append(('Tact', 'TACT_MONTHLY', 'mm/month'))
    if save_eact and mode == 'pysebal':
        products.append(('Eact', 'EACT_MONTHLY', 'mm/month'))

    # CUirr / Peffec(Prz) / NIWR / AW — save_cuirr=True bo'lsa ISTALGAN rejimda.
    # ⚠️ BITTA ko'p-bandli TIF sifatida eksport qilinadi (alohida EMAS): shunda
    # umumiy og'ir suv balansi (Prz) va ETr BIR MARTA hisoblanadi — 4 alohida task
    # har biri Prz'ni qaytadan hisoblab, NIWR (+31 kun ETr) 2 soat ketardi.
    if save_cuirr or save_aw:
        try:
            combined = monthly.select('ET_MONTHLY')
            out_bands = ['ET_MONTHLY'] if save_et else []
            if save_cuirr:
                from . import consumptive_use
                cu = consumptive_use.compute_all(
                    monthly.select('ET_MONTHLY'), scene_images, roi, year, month,
                    mode=mode, utc_offset=utc_offset, ref_type=ref_type,
                    sloping_terrain=sloping_terrain, with_niwr=save_niwr)
                bn = cu.bandNames()                      # AW → AW_CUirr (CUirr/eff)
                cu = cu.select(bn, bn.map(lambda b: ee.Algorithms.If(
                    ee.String(b).equals('AW'), 'AW_CUirr', b)))
                combined = combined.addBands(cu)
                out_bands += ['CUIRR', 'AW_CUirr']
                if save_prz:
                    out_bands.append('PRZ')
                if save_niwr:
                    out_bands.append('NIWR')
            if save_aw:
                from . import root_zone_water
                awimg = root_zone_water.compute_awnet(
                    scene_images, roi, year, month, utc_offset=utc_offset,
                    dr_init_img=dr_init_img)   # None → har oy RAW dan (sug'orish talabi)
                # dr_end_img = awimg.select('DR_END')  # ZANJIR O'CHIQ (grafik "too complex")
                # Mavsumiy-uzluksiz kerak bo'lsa: yuqoridagi qatorni yoqib, dr_carry uzatiladi.
                combined = combined.addBands(awimg.select(
                    ['AW', 'AW_Eff', 'AVAILABLE_WATER', 'DP_MONTHLY', 'N_IRRIG', 'TAW']))
                out_bands += ['AW', 'AW_Eff', 'AVAILABLE_WATER', 'DP_MONTHLY',
                              'N_IRRIG', 'TAW']
            cu_name = f'SEBAL_monthly_ETCU_{month_str}{prefix}'
            cu_task = ee.batch.Export.image.toDrive(
                image=_round_export(combined.select(out_bands)).clip(roi),
                description=cu_name, folder=folder, fileNamePrefix=cu_name,
                region=roi, scale=scale, crs=crs, maxPixels=1e13,
                fileFormat='GeoTIFF')
            cu_task.start(); tasks.append(cu_task)
            print(f"  ⚡ ET+CU/AW birlashgan → {cu_name} @ {scale}m | bandlar: {out_bands}")
            products = [p for p in products if p[1] != 'ET_MONTHLY']
        except Exception as e:
            errors.append(f"CU/AW bloki: {type(e).__name__}: {e}")
            print(f"  ❌ CU/AW bloki: {e}")

    print(f"  📐 Export region: {roi.bounds().coordinates().getInfo()}")
    
    # DIQQAT: monthly image 19+ sahnaning to'liq hisob zanjirini o'z ichiga
    # oladi (har sahnada anchor reduceRegion lar bor). Unga interaktiv
    # getInfo()/bandNames()/reduceRegion qilish "Too many concurrent
    # aggregations" beradi. Shuning uchun diagnostika YO'Q — to'g'ridan
    # batch export qilinadi (batch tizimida limit yuqori).

    for prod_name, band_name, unit in products:
        try:
            prod_image = monthly.select(band_name)

            name = f'SEBAL_monthly_{prod_name}_{month_str}{prefix}'

            task = ee.batch.Export.image.toDrive(
                image=_round_export(prod_image).clip(roi),
                description=name,
                folder=folder,
                fileNamePrefix=name,
                region=roi,
                scale=scale,
                crs=crs,
                maxPixels=1e13,
                fileFormat='GeoTIFF'
            )

            task.start()
            tasks.append(task)

            print(f"  ✅ {prod_name} export boshlandi")

        except Exception as e:
            errors.append(f"{prod_name}: {type(e).__name__}: {e}")
            print(f"  ❌ {prod_name}: {e}")

    # Xato YUTILMAYDI: qolgan produktlar baribir eksport qilindi, lekin oy
    # "OK" deb hisoblanmaydi — chaqiruvchi (_export_monthly_safe) qayd etadi.
    if errors:
        raise RuntimeError(f"{month_str}{prefix} oylik eksport: " + "; ".join(errors))

    return tasks, dr_end_img


def _export_monthly_safe(failed, scene_images, roi, year, month, mode, *a, **kw):
    """
    `_export_monthly` + xato YUTILMAYDI: oy `failed` ro'yxatiga yoziladi (run
    status = 'QISMAN', xulosada va natija lug'atida chiqadi), run esa keyingi
    oy/tayl bilan davom etadi. Kutilmagan xato turlari — to'liq traceback bilan.
    """
    tile_label = a[3] if len(a) > 3 else kw.get('tile_label', '')
    try:
        return _export_monthly(scene_images, roi, year, month, mode, *a, **kw)
    except Exception as e:
        import traceback
        err = f"{type(e).__name__}: {e}"
        failed.append({'tile': tile_label or 'ROI', 'oy': f'{year}-{month:02d}', 'error': err})
        print(f"  ❌ OYLIK EKSPORT {tile_label or 'ROI'} {year}-{month:02d}: {err}")
        if not isinstance(e, RuntimeError):
            print(traceback.format_exc())
        return [], None


# ==============================================================
# CSV ZONAL-STAT EXPORT (batch table — raster EMAS, qiymat)
# ==============================================================
# Lizimetr/parcel ustida mean+median → CSV. BATCH bo'lgani uchun interaktiv
# limitlar (5-daqiqa, "too many concurrent aggregations") YO'Q. Anchor sahnaga
# allaqachon "pishirilgan" (process_tile getInfo), shuning uchun bu yengil.

# Lizimetr bilan solishtiriladigan + SEBAL diagnostika bandlari.
# (Lizimetr o'lchaydi: Rn, G, LE→ET, LST(yuza harorat), albedo(Rs'dan), H.
#  SEBAL diagnostika: NDVI, LAI, u*, rah, dT, EF.)
CSV_LYS_BANDS = [
    # --- yakuniy / oqim ---
    'ET_24', 'ET_INST_MM_HR', 'ETRF_INST', 'ETRF_RAW', 'LAMBDA_E', 'EVAP_FRAC',
    'RN', 'G0', 'H', 'RN_G0', 'G_RATIO',
    # --- yuza / radiometriya ---
    'LST', 'ALBEDO', 'NDVI', 'SAVI', 'LAI', 'EMISSIVITY',
    # --- albedo usullari (diagnostika — qaysi oyда qaysi usul lizimetrga mos) ---
    'ALB_OLMEDO_BRDF', 'ALB_OLMEDO', 'ALB_LIANG', 'ALB_KE', 'ALB_TASUMI', 'ALB_AVG3',
    # --- radiatsiya komponentlari (Rn xatosini ajratish: vs lizimetr Rs/LWdn/LWup) ---
    'K_DOWN', 'L_DOWN', 'L_UP', 'TAU_SW',
    # --- aerodinamika / H motori ---
    'DTA', 'RAH', 'USTAR', 'U_200', 'L_MO', 'Z0M', 'Z0M_WIND', 'RHO_AIR', 'SLOPE',
    # --- meteo (ERA5) — mustaqil tekshirish (#7) ---
    'WIND_SPEED_10M', 'AIR_TEMP',
    # --- kunlik / referens (Rn24 = (1−α)Rs24 − 110·τ24, τ24 = Rs24/Ra24) ---
    'RN24', 'RS24', 'TAU24', 'SOLAR_FRAC', 'ETR_INST', 'ETR24',
]

# Anchor tashxis (sahna PROPERTY'lari — energy_balance yozib qo'ygan). Per-piksel
# EMAS: butun tile uchun bitta (tanlangan cold/hot piksel xususiyatlari + motor).
CSV_ANCHOR_PROPS = [
    'ANCHOR_COLD_LST', 'ANCHOR_HOT_LST', 'ANCHOR_DT_HOT', 'ANCHOR_RAH_HOT',
    'ANCHOR_H_HOT', 'ANCHOR_COLD_ALBEDO', 'ANCHOR_HOT_ALBEDO',
    'ANCHOR_COLD_NDVI', 'ANCHOR_HOT_NDVI', 'ANCHOR_COLD_WIND', 'ANCHOR_HOT_WIND',
]


def parcels_from_points(points, size_m=210, inner_buffer_m=-30):
    """
    {nom: [lon, lat]} → ee.FeatureCollection: har nuqta markazida size_m kvadrat,
    ichki bufer bilan (chekka/yo'l chiqarilgan). 'name' xususiyati saqlanadi.
    Masalan lizimetr: 210×210m dala → −30m → 150×150m yadro.
    Kvadrat nuqtaning UTM zonasida (metr) quriladi: tomoni AYNAN size_m (+2·inner).
    Oldin buffer(r).bounds() EPSG:4326 da — doira ko'pburchagi chegara qutisi
    ~215×216 m (yadro 153×154 m) chiqardi.
    """
    feats = []
    for nom, lonlat in points.items():
        lon, lat = float(lonlat[0]), float(lonlat[1])
        epsg = (32600 if lat >= 0 else 32700) + int((lon + 180.0) // 6.0) + 1   # UTM zona
        proj = ee.Projection(f'EPSG:{epsg}')
        em = ee.ErrorMargin(0.01, 'projected')                             # 1 sm, proj birligida
        g = (ee.Geometry.Point([lon, lat])
             .buffer(size_m / 2.0, em, proj).bounds(em, proj))             # size_m kvadrat
        if inner_buffer_m:
            g = g.buffer(inner_buffer_m, em, proj)                          # ichki bufer (m)
        feats.append(ee.Feature(g, {'name': nom}))
    return ee.FeatureCollection(feats)


def _export_zonal_csv(scenes, info, roi, region_fc, bands, folder,
                      tile_label, mode, utc_offset, scale=30, save_cuirr=False,
                      save_aw=False, csv_monthly=True, sloping_terrain=False):
    """
    region_fc (parcel) ustida MEAN+MEDIAN zonal-stat → BATCH table CSV.
      • per-scene CSV: har sahna, instant+daily bandlar (date bilan)
      • per-month CSV: har oy, ET_MONTHLY (+ save_cuirr → Peffec/CUirr/NIWR) —
        faqat csv_monthly=True (run(csv_monthly=…)); export_monthly — RASTER uchun.
    bands — eksport qilinadigan sahna bandlari (run(csv_bands=…) yoki CSV_LYS_BANDS);
      fayllarga turkumlanadi: INST (lahzalik ET/fraksiyalar), DAILY_ET (ET_24),
      INST_KOMPONENT (qolgan barcha so'ralgan bandlar + anchor QC props).
    Raster export EMAS — faqat qiymatlar (kichik CSV → Drive).
    """
    reducer = ee.Reducer.mean().combine(ee.Reducer.median(), sharedInputs=True)
    prefix = f'_{tile_label}' if tile_label else ''
    tasks = []
    # Tahlil gridi (Landsat UTM) — crs ANIQ: aks holda birinchi tanlangan bandning
    # default proyeksiyasi olinadi (oylik kompozit / LST / LAI — WGS84 grid).
    grid = energy_balance.analysis_proj(ee.Image(scenes[0]))

    def _reduce(img, band_list, tags, plain_single=False):
        # faqat MAVJUD bandlarni tanlaymiz (yo'q band select'ni buzmasin)
        sel = img.bandNames().filter(ee.Filter.inList('item', ee.List(band_list)))
        # GEE: BIR bandli tanlovda ustunlar band nomisiz 'mean'/'median' chiqadi
        # (ko'p bandlida '<band>_mean'). csv_bands erkin bo'lgani uchun bitta bandli
        # INST/INST_KOMPONENT'da band nomi yo'qolmasin → '<band>_mean/_median'.
        # plain_single=True — DAILY_ET/MONTHLY_ET eski formati ('mean'/'median';
        # flux_compare shunday o'qiydi).
        red_r = reducer
        if len(band_list) == 1 and not plain_single:
            red_r = reducer.setOutputs([f'{band_list[0]}_mean', f'{band_list[0]}_median'])
        red = img.select(sel).reduceRegions(
            collection=region_fc, reducer=red_r, scale=scale, crs=grid)
        for k, v in tags.items():
            red = red.map(lambda f, kk=k, vv=v: f.set(kk, vv))
        return red

    # --- PER-SCENE (instant + daily bir CSV'da; ular ayni sahnaning bandlari) ---
    # Har qatorga sahna ANCHOR property'lari ham qo'shiladi (tanlangan cold/hot
    # piksel xususiyatlari — anchor tanlashni QC + fizik oyna sozlash uchun).
    # ALOHIDA fayllar (aniq nomlar): INST (ET-lahzalik) | DAILY_ET | INST_KOMPONENT.
    # Fayl nomiga PAPKA (model+hudud+yil) + tur + tayl → GEE Tasks/Drive'da UNIKAL.
    # Fayl TURKUMLARI (nomlari o'zgarmaydi — flux_compare shu nomlarni o'qiydi);
    # BANDLAR esa `bands` dan (oldin qattiq yozilgan 20 band — `bands` e'tiborsiz edi,
    # CSV_LYS_BANDS'ning 21 bandi hech qachon chiqmasdi).
    INST_SET = ('ET_INST_MM_HR', 'LAMBDA_E', 'ETRF_INST', 'ETRF_RAW', 'EVAP_FRAC',
                'SOLAR_FRAC', 'ETR_INST')
    DAILY_SET = ('ET_24',)
    req = list(dict.fromkeys(bands))                     # tartib saqlanadi, takror yo'q
    avail = set(ee.Image(scenes[0]).bandNames().getInfo())
    missing = [b for b in req if b not in avail]
    if missing:
        print(f"  ⚠️ CSV: so'ralgan bandlar sahnada yo'q — chiqmaydi: {missing}")
    use = [b for b in req if b in avail]
    SCENE_GROUPS = {
        'INST':           [b for b in use if b in INST_SET],
        'DAILY_ET':       [b for b in use if b in DAILY_SET],
        'INST_KOMPONENT': [b for b in use if b not in INST_SET and b not in DAILY_SET],
    }
    SCENE_GROUPS = {k: v for k, v in SCENE_GROUPS.items() if v}
    print(f"  📄 CSV sahna bandlari: {len(use)} ta — "
          + "; ".join(f"{k} {len(v)}" for k, v in SCENE_GROUPS.items()))
    # SEBAL_Milliy_Kc: sahna bandlari SEBAL_Milliy bilan AYNAN bir xil (nusxa) →
    # scene/lstdiag fayllarni CHIQARMAYMIZ; Kc'dan faqat MONTHLY_ET noyob.
    if cfg.is_kc_mode(mode):
        SCENE_GROUPS = {}
    for gname, gbands in SCENE_GROUPS.items():
        sfcs = []
        for s in scenes:
            img = ee.Image(s)
            date = ee.Date(img.get('system:time_start')).format('YYYY-MM-dd')
            tags = {'date': date}
            if gname == 'INST_KOMPONENT':          # anchor QC props faqat komponent CSV'ga
                for p in CSV_ANCHOR_PROPS:
                    tags[p] = img.get(p)
            sfcs.append(_reduce(img, gbands, tags, plain_single=(gname == 'DAILY_ET')))
        gfc = ee.FeatureCollection(sfcs).flatten()
        tg = ee.batch.Export.table.toDrive(
            collection=gfc, description=f'{folder}_{gname}{prefix}',
            folder=folder, fileNamePrefix=f'{folder}_{gname}{prefix}', fileFormat='CSV')
        tg.start(); tasks.append(tg)
        print(f"  📄 CSV {gname} → {folder}_{gname}{prefix}")

    # --- LST FOOTPRINT DIAGNOSTIKA (parcel MARKAZIDA, nuqta namuna) ---
    # compute_lst_smw O'ZGARMAYDI; hech qanday tuzatish yo'q. PSF/neighborhood/
    # WV/QA bandlari L0–L3 footprint validatsiya testi uchun (ayrim CSV).
    # Kc'da SKIP (sahna = Milliy nusxasi).
    if not cfg.is_kc_mode(mode):
        _export_lst_diag_csv(scenes, region_fc, folder, tile_label, scale)

    # --- PER-MONTH (ET_MONTHLY + save_cuirr → Peffec/CUirr; save_aw → water-balans AW) ---
    if not csv_monthly:
        print("  ⏭️  CSV MONTHLY o'tkazildi (csv_monthly=False)")
        return tasks
    mon_bands = ['ET_MONTHLY']
    if save_cuirr:
        mon_bands += ['PRZ', 'CUIRR', 'NIWR', 'AW_CU', 'ETPOT_MONTHLY',
                      'RUNOFF_MONTHLY', 'DEEPPERC_MONTHLY']       # AW_CU = CUirr/eff (eski)
    if save_aw:
        mon_bands += ['AW', 'AW_Eff', 'AVAILABLE_WATER', 'DP_MONTHLY',
                      'N_IRRIG', 'TAW']                            # water-balans (yangi)
    scene_months = sorted({d[:7] for d in info.get('dates', [])})
    month_fcs = []
    for mk in scene_months:
        yr, mo = int(mk[:4]), int(mk[5:7])
        monthly = daily_et.compute_monthly_et(scenes, roi, yr, mo, mode=mode,
                                              utc_offset=utc_offset,
                                              sloping_terrain=sloping_terrain)
        if monthly is None:
            continue
        if save_cuirr:
            # CUirr / Peffec(Prz) / NIWR (kunlik FAO-56 + CN). AW → AW_CU (water-balans
            # AW bilan to'qnashmasin).
            from . import consumptive_use
            cu = consumptive_use.compute_all(
                monthly.select('ET_MONTHLY'), scenes, roi, yr, mo,
                mode=mode, utc_offset=utc_offset, sloping_terrain=sloping_terrain)
            bn = cu.bandNames()
            cu = cu.select(bn, bn.map(lambda b: ee.Algorithms.If(
                ee.String(b).equals('AW'), 'AW_CU', b)))
            monthly = monthly.addBands(cu)
        if save_aw:
            # Ildiz-zona water-balans AW (root_zone_water) — per-crop (cfg.CROP_ASSETS)
            from . import root_zone_water
            awimg = root_zone_water.compute_awnet(
                scenes, roi, yr, mo, utc_offset=utc_offset)
            monthly = monthly.addBands(awimg.select(
                ['AW', 'AW_Eff', 'AVAILABLE_WATER', 'DP_MONTHLY', 'N_IRRIG', 'TAW']))
        month_fcs.append(_reduce(monthly, mon_bands, {
            'year': yr, 'month': mo,
            'n_landsat_scenes': monthly.get('n_landsat_scenes'),   # shu oydagi sahnalar
            'max_gap_days': monthly.get('max_gap_days')},           # QC
            plain_single=True))
    if month_fcs:
        month_fc = ee.FeatureCollection(month_fcs).flatten()
        t2 = ee.batch.Export.table.toDrive(
            collection=month_fc, description=f'{folder}_MONTHLY_ET{prefix}',
            folder=folder, fileNamePrefix=f'{folder}_MONTHLY_ET{prefix}', fileFormat='CSV')
        t2.start(); tasks.append(t2)
        print(f"  📄 CSV MONTHLY_ET → {folder}_MONTHLY_ET{prefix} (mean+median)")
    return tasks


# LST footprint tashxis bandlari uchun CSV band ro'yxati (radiation.
# add_lst_footprint_diagnostics chiqaradi + mavjud EMISSIVITY/TAU_SW/RN/H/G0/ET_24).
CSV_LSTDIAG_BANDS = [
    'LST', 'LST_raw_center', 'LST_mean_3x3', 'LST_median_3x3', 'LST_mean_5x5',
    'LST_p10_5x5', 'LST_std_5x5', 'LST_psf_weighted',
    'NDVI', 'NDVI_mean_5x5', 'NDVI_std_5x5', 'ALBEDO', 'ALBEDO_std_5x5',
    'DIST_EDGE', 'ST_QA', 'EMISSIVITY', 'TAU_SW', 'WATER_VAPOR',
    'RN', 'H', 'G0', 'ET_24',
]


def _export_lst_diag_csv(scenes, region_fc, folder, tile_label, scale=30):
    """
    LST footprint TASHXIS CSV — parcel MARKAZIDA (nuqta) namuna.

    compute_lst_smw O'ZGARMAYDI; hech qanday tuzatish/ofset qo'llanmaydi. Har
    sahna uchun neighborhood (3×3/5×5), PSF-vaznli radiance-footprint, WV, ST_QA
    va boshqa tashxis bandlari parcel MARKAZIY nuqtasida (ee.Reducer.first)
    namuna olinadi — bu 30 m piksel/PSF footprintni lizimetr nuqtasiga
    moslashtiradi (parcel o'rtachasi emas). L0–L3 variant testi uchun.
    """
    from . import radiation

    # parcel → markaziy NUQTA (footprint piksel/PSF markazi)
    pts = region_fc.map(lambda f: f.setGeometry(f.geometry().centroid(1)))
    prefix = f'_{tile_label}' if tile_label else ''

    fcs = []
    for s in scenes:
        img = radiation.add_lst_footprint_diagnostics(ee.Image(s), scale)
        date = ee.Date(img.get('system:time_start')).format('YYYY-MM-dd')
        sel = img.bandNames().filter(
            ee.Filter.inList('item', ee.List(CSV_LSTDIAG_BANDS)))
        # crs ANIQ (Landsat grid): 3×3/5×5/PSF yadrolari so'rov gridida ishlaydi →
        # 90×90 / 150×150 m (oldin LST birinchi band bo'lsa 4326@30 m: 90×69 m).
        red = img.select(sel).reduceRegions(
            collection=pts, reducer=ee.Reducer.first(), scale=scale,
            crs=energy_balance.analysis_proj(ee.Image(s)))
        red = red.map(lambda f, dd=date: f.set('date', dd))
        fcs.append(red)

    fc = ee.FeatureCollection(fcs).flatten()
    t = ee.batch.Export.table.toDrive(
        collection=fc, description=f'{folder}_lstdiag{prefix}',
        folder=folder, fileNamePrefix=f'{folder}_lstdiag{prefix}',
        fileFormat='CSV')
    t.start()
    print(f"  📄 CSV LST-diag (footprint/PSF/neighborhood, nuqta) → "
          f"{folder}_lstdiag{prefix}")
    return [t]


# ==============================================================
# MAIN RUN
# ==============================================================

def run(roi_type='gaul', date_start=None, date_end=None,
        mode='SEBAL_B', satellite='BOTH', cloud_max=70, validate=False,
        utc_offset=None,   # mahalliy standart soat (None=avto boylam/15). Siyosiy
        #   vaqt zonasi boylamdan farq qilsa QO'LDA bering: mas. Texas panhandle
        #   Central Time = -6 (avto -7 beradi — El Paso'dan tashqari xato).

        # Export sozlamalari
        export_daily=True,
        export_monthly=True,

        # CSV ZONAL-STAT (raster emas — parcel/lizimetr ustida mean+median → CSV)
        export_csv=False,     # True → csv_region ustida qiymatlarni CSV qiladi (batch)
        csv_region=None,      # ee.FeatureCollection ('name' xususiyatli parcellar).
        #                       main.parcels_from_points({'NE':[lon,lat],...}) yordamchisi bor.
        csv_bands=None,       # None → CSV_LYS_BANDS (lizimetr bilan solishtiriladiganlar);
        #                       ro'yxat berilsa AYNAN shu bandlar chiqadi (yo'qlari logda)
        csv_scale=30,
        csv_monthly=True,     # CSV oylik (MONTHLY_ET) hisob+eksport. export_monthly — faqat
        #                       RASTER oylik; CSV oylik shu flag bilan boshqariladi.
        cloud_roi=None,       # bulut precheck hududi. None + export_csv → avtomatik
        #   csv_region (parcel) ustida (TEZ, faqat lizimetr uchun). Oddiy raster
        #   rejimda None qoladi → butun ROI (butun tile kerak). Qo'lda ham berish mumkin.

        # Oylik produktlar (True/False)
        save_et=True,
        save_biomass=True,
        save_etref=True,
        save_tact=True,
        save_eact=True,
        # CUirr / Peffec(Prz) / NIWR (sug'orish suvi iste'moli) — True bo'lsa
        # ISTALGAN rejimda ishlaydi (ETa shu rejim ET_MONTHLY'sidan). Kunlik
        # FAO-56 + Curve Number; NIWR ETr = ERA5 daily kunlik-timestep (yengil).
        save_cuirr=False,
        # save_aw — ILDIZ-ZONA water-balans AW (root_zone_water): AW/AW_Eff/
        # AVAILABLE_WATER/DP_MONTHLY/N_IRRIG/TAW bandlarini qo'shadi (CUirr'dan
        # ALOHIDA, fizik water-balans). SEBAL_Milliy_Kc + crop_assets bilan per-crop.
        save_aw=False,
        # CU eksporti DEFAULT: faqat CUirr + AW (30m = `scale`). Peffec(PRZ) va
        # NIWR ni ALOHIDA yoqish (default O'CHIQ). ⚠️ save_niwr=True bo'lsa OG'IR
        # ETr (31 kun) hisoblanadi — sekinlashtiradi; kerak bo'lmasa False qoldiring.
        save_prz=False,
        save_niwr=False,

        # Tile sozlamalari
        tiles=None,          # [(156,32), (156,33)] yoki None=auto
        process_by_tile=False, # True=har tile alohida

        # Anchor tanlash strategiyasi (beton kaskad):
        #   'cimec' (DEFAULT) | 'plan_a' | 'plan_b' | 'default' | 'pysebal'
        #   | 'cascade'. Tartib: cimec → plan_a → plan_b → default → pysebal;
        #   nomlangan metod birinchi, keyin qolganlari shu tartibda; avval ekin
        #   zonasida, so'ng ROI'da. Hech biri topmasa — sahna rad etiladi.
        #   'cascade' = 'cimec'. default zaxirasi loglanadi (QC). Har qadam log'da.
        anchor_method='cimec',
        # anchor_mode: kandidatlardan qiymat olish qadami (anchor_method'dan
        #   ALOHIDA emas — o'sha metod topgan kandidatlar ustida ishlaydi):
        #   'median_anchor' (default) = kandidatlar medianasi (hozirgi holat);
        #   'point_anchor' = kandidatlar ichidan BITTA ekstremal (hot=eng issiq,
        #   cold=eng sovuq; Rn−G₀ hot pikseldan). Natijaga sezilarli ta'sir qiladi.
        anchor_mode='median_anchor',

        # Cold anchor referens-ET fraksiyasi (λET_cold = cold_etrf·ETr_inst).
        # Default 1.05 (Tasumi/SEBAL_ID). SEBAL_Milliy ground-truth test uchun
        # 0.85 (METRIC) kabi qiymatlar sinaladi. SEBAL_ID default'da o'zgarmaydi.
        cold_etrf=1.05,

        # QIYA YUZA (Tasumi 2003 Ch.V): Ts–DEM (dT), cosθ → K↓, kunlik C_rad (SEBAL_ID,
        # SEBAL_Milliy) / Ra24_ratio·Rs24 (SEBAL_B, pysebal), z0m/u200 tuzatishlari.
        # Default False (tekis). Sahna + standart oylik + CSV + CUirr yo'llariga uzatiladi.
        # VIIRS / S30 / Kc_ETo oylik yo'llarida kunlik qiyalik tuzatishi YO'Q (logda aytiladi).
        sloping_terrain=False,

        # Ekin-spetsifik z0m (h=f(LAI) → z0m=0.123·h; Tasumi/Wright R²0.98-0.99).
        # FAQAT export_csv rejimida (tadqiqot nuqtasi ekin turi ma'lum) qo'llanadi.
        # None → default z0m=0.018·LAI. Qiymatlar: cfg.CROP_H_LAI kalitlari
        # ('alfalfa','corn','potato','beans_beet_peas','spring_wheat','winter_wheat','default').
        crop_type=None,

        # Broadband albedo usuli — production 'ALBEDO' bandini tanlaydi:
        #   'olmedo_brdf' (DEFAULT) → cfg.OLMEDO_COEFFICIENTS − (0.001464·θ_elev − 0.079103)
        #   'config' → cfg.OLMEDO_COEFFICIENTS (ofsetsiz, BRDF tuzatishsiz)
        #   'olmedo'|'liang'|'ke'|'tasumi'|'avg3' → foydalanuvchi koeffitsientlari.
        # ⚠️ 'olmedo'(foydalanuvchi,ofsetli) ≠ 'config'(cfg). Har run'da ALB_*
        # diagnostika bandlari CSV'ga chiqadi.
        albedo_method='olmedo_brdf',

        # Export sozlamalari
        folder='SEBAL_Output',
        scale=30,
        crs='EPSG:4326',

        # VIIRS downscaling (ixtiyoriy qatlam — SEBAL o'zgarmaydi)
        use_viirs=False,            # True → oylik ET VIIRS bilan kuchaytiriladi
        viirs_mode='lambda',        # 'lambda' (EVAP_FRAC) yoki 'kc' (KC)
        viirs_model='ndvi',         # 'ndvi' | 'ndvi2' | 'multi'
        viirs_qa='lenient',         # 'lenient' | 'strict'
        viirs_fill='linear',        # 'linear' | 'nearest'
        viirs_crs=None,             # 30m fine grid CRS (aggregate/holdout uchun).
                                    # None → asosiy `crs` ishlatiladi (xavfsiz).
                                    # Har hudud uchun to'g'ri UTM zona bering,
                                    # masalan Idaho='EPSG:32611', UZB='EPSG:32642'.

        # HLS S30 ETrF regressiya (ixtiyoriy qatlam — SEBAL o'zgarmaydi)
        use_s30_etrf=False,         # True → oylik ET HLS S30 (30m) ETrF bilan
        s30_model='ndvi',           # 'ndvi'|'ndvi2'|'multi'|'multi6'
        s30_qa='lenient',           # 'lenient' | 'strict'
        s30_fill='linear',          # 'linear' | 'nearest'
        s30_cropland_only=False,    # True → yakuniy ET faqat ekin maydoniga
        s30_validate=False,         # True → hold-out validatsiya CSV

        # PER-CROP Kc (SEBAL_Milliy_Kc): crop-code raster asset(lar) ro'yxati →
        # har piksel o'z ekinining FAO-56 koeffitsienti. None → bitta Kc (Bushland).
        crop_assets=None,

        **roi_kwargs):
    """
    SEBAL-GEE v4 production pipeline.

    Tile parametrlari:
      tiles=None, process_by_tile=False → ROI bo'yicha ishlash (kichik hududlar)
      tiles=None, process_by_tile=True  → avtomatik tile aniqlash
      tiles=[(156,32),(156,33)], process_by_tile=True → faqat shu tilelar
      tiles=[...],               process_by_tile=False → XATO (ValueError)
    """
    # tiles faqat tile rejimida ishlatiladi. ROI rejimida build_collection
    # filterBounds(roi) bilan ROI ga tekkan BARCHA path/row ni oladi — tiles
    # jimgina e'tiborsiz qolardi. Chalkashlik bo'lmasin: aniq to'xtatamiz.
    if tiles is not None and not process_by_tile:
        raise ValueError(
            f"tiles faqat process_by_tile=True bilan ishlaydi "
            f"(berildi: tiles={tiles}, process_by_tile=False). "
            f"Aniq tile'lar kerak → process_by_tile=True; "
            f"ROI ga tekkan barcha tile'lar kerak → tiles=None.")

    roi = cfg.build_roi(roi_type, **roi_kwargs)
    cfg.CROP_ASSETS = crop_assets      # PER-CROP Kc: ndvi_kc cfg.CROP_ASSETS'ni o'qiydi

    # BULUT PRECHECK HUDUDI: CSV/lizimetr rejimida FAQAT parcel ustida (tez +
    # to'g'ri — bizga Bushland ustida bulutsizlik kerak, butun shtat emas).
    # Oddiy raster rejimda cloud_roi=None → butun ROI (butun tile kerak).
    _cloud_use_cropland = True
    _csv_mode = export_csv and csv_region is not None
    if cloud_roi is None and _csv_mode:
        cloud_roi = csv_region.geometry()   # parcellar birlashgan geometriyasi (reduceRegion uchun)
        _cloud_use_cropland = False
        print("  ☁️  export_csv → bulut precheck LOKAL (csv_region parcellari; tez)")

    # ANCHOR masshtabi — energy_balance.ANCHOR_SCALE (100 m, BARCHA rejimlarda bir xil;
    # oldin ROI 30 m / CSV-tile 100 m edi → bir xil sahna rejimga qarab turli anchor).
    print(f"  ⚡ anchor {energy_balance.ANCHOR_SCALE} m da (Landsat termal native; ET 30 m)")

    # Cold anchor ETrF (λET_cold = cold_etrf·ETr) — SEBAL_ID default 1.05
    energy_balance.COLD_ETRF = cold_etrf
    if cold_etrf != 1.05:
        print(f"  🧊 cold anchor ETrF = {cold_etrf} (default 1.05 dan farqli)")
    if sloping_terrain:
        no_slope = [n for n, on in (('VIIRS oylik', use_viirs), ('S30 oylik', use_s30_etrf),
                                    ('Kc_ETo oylik', cfg.is_kc_mode(mode))) if on]
        print("  ⛰️ sloping_terrain=True — qiya yuza tuzatishlari (sahna, oylik, CSV, CUirr)")
        if no_slope:
            print(f"  ⚠️ OGOHLANTIRISH: {', '.join(no_slope)} yo'lida kunlik qiyalik "
                  f"tuzatishi (C_rad / Ra24_ratio) YO'Q — faqat sahna (lahzalik) qismi")

    # Broadband albedo usuli — production 'ALBEDO' (default 'olmedo_brdf').
    # ALB_* diagnostika bandlari har doim CSV'ga chiqadi (usuldan qat'i nazar).
    surface_props.ALBEDO_METHOD = albedo_method
    print(f"  🎨 albedo usuli = '{albedo_method}' (production ALBEDO)")

    # Ekin-spetsifik z0m — FAQAT export_csv rejimida (nuqta ekin turi ma'lum).
    # Boshqa rejimda None (default z0m=0.018·LAI), chunki butun tile ekin turi noma'lum.
    surface_props.CROP_TYPE = crop_type if (_csv_mode and crop_type) else None
    if surface_props.CROP_TYPE:
        print(f"  🌱 ekin-spetsifik z0m: crop_type='{surface_props.CROP_TYPE}' "
              f"(h=f(LAI) → z0m=0.123·h; faqat CSV rejimi)")

    # VIIRS/S30 downscaling 30m fine-grid CRS. Berilmasa → asosiy export
    # `crs`. Bu ilgari viirs_downscaling.DCFG da hardcode ('EPSG:32642',
    # faqat O'zbekiston UTM) edi — boshqa hududda (masalan Idaho) noto'g'ri
    # natija berardi. Endi hudud CRS'i bilan sinxron.
    viirs_crs = viirs_crs or crs
    from . import viirs_downscaling as _vds
    _vds.DCFG['fine_crs'] = viirs_crs

    print(f"\n{'='*60}")
    print(f"  SEBAL-GEE v4 | Mode: {mode}")
    print(f"  ROI: {roi_type} | {date_start} → {date_end}")
    print(f"  Tile mode: {process_by_tile}")
    print(f"  VIIRS fine CRS: {viirs_crs}")
    print(f"  Anchor metod: {anchor_method}  | rejim: {anchor_mode}")
    print(f"{'='*60}")

    all_tasks = []
    failed_tiles = []     # [{'tile', 'error'}] — xato bilan TASHLAB KETILGAN taylar
    failed_months = []    # [{'tile', 'oy', 'error'}] — oylik eksport xatolari (yutilmaydi)
    empty_tiles = []      # yaroqli sahnasi bo'lmagan taylar (xato emas)
    tile_warnings = []    # masalan tayl geometriyasi topilmadi → ROI

    # ---- TILE-BASED PROCESSING ----
    if process_by_tile:
        if tiles is None:
            print("\n  WRS tiles aniqlanmoqda...")
            tiles = detect_wrs_tiles(roi, date_start, date_end,
                                     satellite, cloud_max)

        print(f"  Topilgan tiles: {tiles}")

        for tile_item in tiles:
            # Tile format: Landsat = (155, 33), HLS = 'T42TVK' yoki ('T42TVK',)
            if isinstance(tile_item, str):
                # HLS: string formatda
                tile_label = tile_item
            elif isinstance(tile_item, tuple) and len(tile_item) == 2 and isinstance(tile_item[0], int):
                # Landsat: (path, row) formatda
                path, row = tile_item
                tile_label = f'P{path}_R{row}'
            elif isinstance(tile_item, tuple) and len(tile_item) == 1:
                # HLS: ('T42TVK',) formatda
                tile_label = tile_item[0]
            else:
                print(f"  ⚠️ Noma'lum tile format: {tile_item}")
                continue
 
            print(f"\\n{'='*60}")
            print(f"  TILE: {tile_label}")
            print(f"{'='*60}")

            # Tile geometriyasi — TILE CHEGARASIDA ishlash uchun.
            # HLS: MGRS granula footprint; Landsat: WRS path/row.
            # tile_roi = roi ∩ tile_geom → har tile o'z chegarasida.
            try:
                if satellite == 'HLS':
                    tile_geom = get_hls_tile_geometry(
                        tile_label, date_start, date_end)
                else:
                    tile_geom = get_tile_geometry(path, row)
                tile_roi = roi.intersection(tile_geom, ee.ErrorMargin(30))
            except Exception as e:
                print(f"  ⚠️ Tile geometriya topilmadi ({e}) → ROI ishlatiladi")
                tile_warnings.append({'tile': tile_label,
                                      'warning': f"tayl geometriyasi topilmadi → ROI ({e})"})
                tile_roi = roi

            # Chekka/bo'sh tayl BUTUN run'ni buzmasin — o'tkaziladi, LEKIN xato
            # yutilmaydi: turi va sababi qayd etiladi, run oxirida ro'yxat chiqadi va
            # natija lug'atida qaytariladi (run_flux_validation uni "qisman" sanaydi).
            # Kutilmagan xato turlari (RuntimeError emas) — to'liq traceback bilan.
            try:
                scenes, info = process_tile(
                    tile_roi, date_start, date_end, mode,
                    satellite, cloud_max, tile_label,
                    anchor_method=anchor_method, anchor_mode=anchor_mode,
                    utc_offset=utc_offset, sloping_terrain=sloping_terrain,
                    cloud_roi=cloud_roi, cloud_use_cropland=_cloud_use_cropland)
            except Exception as e:
                import traceback
                err = f"{type(e).__name__}: {e}"
                failed_tiles.append({'tile': tile_label, 'error': err})
                print(f"  ❌ TAYL {tile_label} O'TKAZIB YUBORILDI — {err}")
                if not isinstance(e, RuntimeError):      # kutilmagan xato — kod/GEE
                    print(traceback.format_exc())
                continue

            if not scenes:
                empty_tiles.append(tile_label)
                print(f"  ⏭️  {tile_label}: yaroqli sahna yo'q")
                continue

            # CSV zonal-stat (parcel/lizimetr ustida mean+median → batch CSV)
            if export_csv and csv_region is not None:
                ctasks = _export_zonal_csv(
                    scenes, info, tile_roi, csv_region,
                    csv_bands or CSV_LYS_BANDS, folder, tile_label, mode,
                    info.get('utc_offset', 0), csv_scale, save_cuirr=save_cuirr,
                    save_aw=save_aw, csv_monthly=csv_monthly,
                    sloping_terrain=sloping_terrain)
                all_tasks.extend(ctasks)

            if export_daily:
                tasks = _export_daily(scenes, tile_roi, mode,
                                        folder, scale, crs, tile_label)
                all_tasks.extend(tasks)

            if export_monthly:
                from datetime import datetime
                # start_dt = datetime.strptime(date_start, '%Y-%m-%d')
                # tasks = _export_monthly(
                #     scenes, tile_roi, start_dt.year, start_dt.month,
                #     mode, folder, scale, crs, tile_label,
                #     save_et, save_biomass, save_etref, save_tact, save_eact)
                start_dt = datetime.strptime(date_start, '%Y-%m-%d')
                end_dt = datetime.strptime(date_end, '%Y-%m-%d')

                tasks = []
                dr_carry = None   # oylararo Dr uzatish (mavsumiy-uzluksiz AW)

                # Faqat SAHNASI bor oylarni hisoblaymiz.
                # info['dates'] = ['2026-05-15', ...] (client-side).
                # Sahnasiz oy interpolyatsiyada bo'sh band beradi →
                # "Image.divide: Got 0 and 1" xatosi.
                scene_months = {d[:7] for d in info.get('dates', [])}

                current_year = start_dt.year
                current_month = start_dt.month

                while (current_year < end_dt.year) or (
                    current_year == end_dt.year and current_month <= end_dt.month
                ):
                    month_key = f'{current_year}-{current_month:02d}'
                    if month_key not in scene_months:
                        print(f"  ⏭️  {month_key}: sahna yo'q, oylik o'tkazildi")
                        if current_month == 12:
                            current_month = 1
                            current_year += 1
                        else:
                            current_month += 1
                        continue

                    # Oylik ET manbai: S30 ETrF > VIIRS > standart (lineer).
                    # Downscaling yoqilsa → standart ET o'rniga (save_et=False),
                    # boshqa produktlar (biomass/tact/eact/etref) standart yo'l.
                    if use_s30_etrf:
                        _s30_export_month(
                            scenes, info, tile_roi, current_year,
                            current_month, month_key, folder, scale, crs,
                            tile_label, s30_model, s30_qa, s30_fill,
                            cloud_max, tasks, s30_cropland_only, s30_validate)
                        month_tasks, dr_carry = _export_monthly_safe(
                            failed_months,
                            scenes, tile_roi, current_year, current_month,
                            mode, folder, scale, crs, tile_label,
                            False, save_biomass, save_etref, save_tact, save_eact,
                            utc_offset=info.get('utc_offset', 0),
                            sloping_terrain=sloping_terrain,
                            save_cuirr=save_cuirr, save_prz=save_prz,
                            save_niwr=save_niwr, save_aw=save_aw,
                            dr_init_img=dr_carry)
                    elif use_viirs:
                        _viirs_export_month(
                            scenes, info, tile_roi, current_year,
                            current_month, month_key, folder, scale, crs,
                            tile_label, viirs_mode, viirs_model, viirs_qa,
                            viirs_fill, tasks)
                        month_tasks, dr_carry = _export_monthly_safe(
                            failed_months,
                            scenes, tile_roi, current_year, current_month,
                            mode, folder, scale, crs, tile_label,
                            False,  # save_et=False → VIIRS ET ishlatiladi
                            save_biomass, save_etref, save_tact, save_eact,
                            utc_offset=info.get('utc_offset', 0),
                            sloping_terrain=sloping_terrain,
                            save_cuirr=save_cuirr, save_prz=save_prz,
                            save_niwr=save_niwr, save_aw=save_aw,
                            dr_init_img=dr_carry)
                    else:
                        month_tasks, dr_carry = _export_monthly_safe(
                            failed_months,
                            scenes, tile_roi, current_year, current_month,
                            mode, folder, scale, crs, tile_label,
                            save_et, save_biomass, save_etref,
                            save_tact, save_eact,
                            utc_offset=info.get('utc_offset', 0),
                            sloping_terrain=sloping_terrain,
                            save_cuirr=save_cuirr, save_prz=save_prz,
                            save_niwr=save_niwr, save_aw=save_aw,
                            dr_init_img=dr_carry)

                    tasks.extend(month_tasks)

                    if current_month == 12:
                        current_month = 1
                        current_year += 1
                    else:
                        current_month += 1
                all_tasks.extend(tasks)

    # ---- ROI-BASED PROCESSING (kichik hududlar) ----
    else:
        scenes, info = process_tile(
            roi, date_start, date_end, mode,
            satellite, cloud_max, anchor_method=anchor_method,
            anchor_mode=anchor_mode, utc_offset=utc_offset,
            sloping_terrain=sloping_terrain,
            cloud_roi=cloud_roi, cloud_use_cropland=_cloud_use_cropland)

        if scenes:
            if export_daily:
                tasks = _export_daily(scenes, roi, mode,
                                        folder, scale, crs)
                all_tasks.extend(tasks)

            if export_monthly:
                from datetime import datetime
                start_dt = datetime.strptime(date_start, '%Y-%m-%d')
                end_dt = datetime.strptime(date_end, '%Y-%m-%d')

                tasks = []
                dr_carry = None   # oylararo Dr uzatish (mavsumiy-uzluksiz AW)

                # Faqat SAHNASI bor oylar (yuqoridagi tile branch bilan bir xil).
                scene_months = {d[:7] for d in info.get('dates', [])}

                current_year = start_dt.year
                current_month = start_dt.month

                while (current_year < end_dt.year) or (
                    current_year == end_dt.year and current_month <= end_dt.month
                ):
                    month_key = f'{current_year}-{current_month:02d}'
                    if month_key not in scene_months:
                        print(f"  ⏭️  {month_key}: sahna yo'q, oylik o'tkazildi")
                        if current_month == 12:
                            current_month = 1
                            current_year += 1
                        else:
                            current_month += 1
                        continue

                    month_tasks, dr_carry = _export_monthly_safe(
                        failed_months,
                        scenes,
                        roi,
                        current_year,
                        current_month,
                        mode,
                        folder,
                        scale,
                        crs,
                        '',
                        save_et,
                        save_biomass,
                        save_etref,
                        save_tact,
                        save_eact,
                        utc_offset=info.get('utc_offset', 0),
                        sloping_terrain=sloping_terrain,
                        save_cuirr=save_cuirr, save_prz=save_prz,
                        save_niwr=save_niwr, save_aw=save_aw,
                        dr_init_img=dr_carry
                    )

                    tasks.extend(month_tasks)

                    if current_month == 12:
                        current_month = 1
                        current_year += 1
                    else:
                        current_month += 1
                all_tasks.extend(tasks)
                
    if validate and scenes:
            print("\n  Validation: SEBAL vs OpenET (oylik)...")
            try:
                from . import validation
                from . import monthly_analytics
                from datetime import datetime
                start_dt = datetime.strptime(date_start, '%Y-%m-%d')
                
                # Oylik ET — HAR REJIM O'Z usulida (oldin barcha rejimlar uchun
                # pysebal uslubidagi monthly_analytics ishlatilardi)
                uo = utc_offset if utc_offset is not None else daily_et.utc_offset_from_roi(roi)
                monthly = daily_et.compute_monthly_et(
                    scenes, roi, start_dt.year, start_dt.month, mode=mode, utc_offset=uo,
                    sloping_terrain=sloping_terrain)
                
                # OpenET oylik olish (mm/month)
                openet = validation.get_openet_monthly(
                    roi, start_dt.year, start_dt.month)
                
                # Sampling
                combined = (monthly.select('ET_MONTHLY').rename('ET_SEBAL')
                        .addBands(openet))
                points = ee.FeatureCollection.randomPoints(roi, 2000, seed=42)
                sampled = combined.sampleRegions(
                    collection=points, scale=30, geometries=True)
                sampled = sampled.filter(ee.Filter.notNull(['ET_SEBAL']))
                
                n = sampled.size().getInfo()
                print(f"  Valid nuqtalar: {n}")
                
                print(f"\n  {'Model':<12} {'R²':>6} {'RMSE':>8} {'MBE':>8} {'SEBAL':>8} {'OpenET':>8}")
                print(f"  {'-'*56}")
                
                for band in openet.bandNames().getInfo():
                    name = band.replace('ET_', '')
                    try:
                        st = validation.compute_statistics(sampled, 'ET_SEBAL', band)
                        si = {k: v.getInfo() if hasattr(v, 'getInfo') else v
                            for k, v in st.items()}
                        print(f"  {name:<12} {si['r2']:>6.3f} {si['rmse']:>8.1f} "
                            f"{si['mbe']:>8.1f} {si['mean_sebal']:>8.1f} "
                            f"{si['mean_openet']:>8.1f}")
                    except Exception as e:
                        print(f"  {name:<12} ❌ {e}")
            except Exception as e:
                print(f"  ⚠️ Validation: {e}")
    

    # ---- XULOSA ----
    print(f"\n{'='*60}")
    if failed_tiles:
        print(f"  ❌ {len(failed_tiles)} ta tayl XATO bilan tashlab ketildi (natija YO'Q):")
        for ft in failed_tiles:
            print(f"     • {ft['tile']}: {ft['error']}")
    if failed_months:
        print(f"  ❌ {len(failed_months)} ta OYLIK EKSPORT xato (mahsulot YO'Q):")
        for fm in failed_months:
            print(f"     • {fm['tile']} {fm['oy']}: {fm['error']}")
    if empty_tiles:
        print(f"  ⏭️  Yaroqli sahnasiz taylar: {empty_tiles}")
    for tw in tile_warnings:
        print(f"  ⚠️ {tw['tile']}: {tw['warning']}")
    status = 'QISMAN' if (failed_tiles or failed_months) else 'OK'
    print(f"  {'✅' if status == 'OK' else '⚠️'} {'Tayyor' if status == 'OK' else 'QISMAN tayyor'}! "
          f"{len(all_tasks)} ta export task")
    print(f"  📁 Drive → {folder}/")
    print("  🔗 https://code.earthengine.google.com/tasks")
    print(f"{'='*60}")
    return {'tasks': all_tasks, 'status': status, 'failed_tiles': failed_tiles,
            'failed_months': failed_months,
            'empty_tiles': empty_tiles, 'tile_warnings': tile_warnings}


# ==============================================================
# POLYGON-ASOSLI ET (zonal) — dala-darajasida validatsiya
# ==============================================================
# MUHIM: bu FAQAT orkestratsiya qatlami — SEBAL hisob-kitob zanjiri
# (process_tile → energy_balance/radiation/daily_et) UMUMAN o'zgarmaydi.
# Kalibratsiya kengroq hududda (polygon atrofida bufer, cold+hot anchor uchun);
# zonal extraktsiya esa polygon(lar) bo'yicha.


def _zonal_add(fc_in, image, prop_name, scale=30, reducer=None, crs=None):
    """
    `image` (BITTA band) ni `fc_in` polygonlari bo'yicha reduce qilib (default
    mean), natijani to'g'ridan-to'g'ri `prop_name` atributi sifatida qo'shadi
    (Reducer.setOutputs — 'mean' oraliq nomisiz). Akkumulyatsiya: qaytgan FC
    oldingi barcha atributlarni saqlaydi, shuning uchun ketma-ket chaqiriladi.
    """
    reducer = (reducer or ee.Reducer.mean()).setOutputs([prop_name])
    return image.reduceRegions(
        collection=fc_in, reducer=reducer, scale=scale, crs=crs, tileScale=4)


def run_polygons(polygon_asset,
                 date_start='2024-04-01', date_end='2024-09-01',
                 mode='SEBAL_B', satellite='BOTH', cloud_max=70,
                 calib_buffer_m=15000, inner_buffer_m=-30,
                 anchor_method='cascade', anchor_mode='median_anchor',
                 out_asset=None, out_folder='SEBAL_Polygon',
                 crs='EPSG:32610', months=(4, 5, 6, 7, 8),
                 year=2024, export_rasters=False,
                 etrf_water_balance=False, ref_type='alfalfa', utc_offset=None,
                 etr24_source='era5', sloping_terrain=False,
                 albedo_method='olmedo_brdf', cold_etrf=1.05,
                 crop_type=None, crop_assets=None):
    """
    Polygon(lar) bo'yicha SEBAL ET — zonal (mean).

    1 ta polygon bo'lsa bittasi, 100+ bo'lsa har biri uchun hisoblanadi.
    Har polygonga atribut: ET_{year}_{MM} (oylik mm) + ET_{YYYYMMDD} (har bulutsiz
    Landsat sahna kuni ET_24, mm/kun) + n_pixels, n_scenes. Natija GEE asset
    (out_asset berilsa) va Drive CSV sifatida export qilinadi.

    Parameters
    ----------
    polygon_asset : str | ee.FeatureCollection | ee.Geometry
        Polygon asset ID yoki FC/Geometry.
    albedo_method, cold_etrf, crop_type, crop_assets : run() dagi bilan AYNI.
        OLDIN run_polygons ularni O'RNATMASDI — bitta sessiyada oldingi `run()`
        dan qolgan global qiymat jimgina ishlatilardi (albedo usuli, cold ETrF,
        z0m ekin turi, per-crop Kc). Endi har chaqiruv o'z qiymatini o'rnatadi
        va logda chop etadi.
    calib_buffer_m : int
        Kalibratsiya ROI = polygon bounds + shu bufer (~cold+hot anchor uchun).
    inner_buffer_m : int
        Zonaldan oldin polygonga ichki bufer (chet aralash pikselni chiqarish).
        0 = to'liq polygon (fraksion vaznlash). Manfiy = eroziya.
    months : tuple
        Oylik ET hisoblanadigan oylar (default 2024 Apr–Aug).
    """
    # 1. Polygon FC
    if isinstance(polygon_asset, ee.Geometry):
        fc = ee.FeatureCollection([ee.Feature(polygon_asset)])
    else:
        fc = ee.FeatureCollection(polygon_asset)

    n_poly = fc.size().getInfo()
    print(f"\n{'='*60}")
    print(f"  POLYGON ET | polygonlar: {n_poly} | {date_start}..{date_end}")
    print(f"  Mode: {mode} | anchor: {anchor_method}/{anchor_mode}")
    print(f"{'='*60}")

    poly_geom = fc.geometry()

    # 1b. GLOBAL SOZLAMALAR — `run()` bilan AYNI. OLDIN run_polygons ularni
    #     o'rnatmasdi: bitta sessiyada avvalgi `run()` dan qolgan qiymat (albedo
    #     usuli, cold ETrF, z0m ekin turi, per-crop Kc) jimgina ishlatilardi.
    cfg.CROP_ASSETS = crop_assets
    energy_balance.COLD_ETRF = cold_etrf
    surface_props.ALBEDO_METHOD = albedo_method
    surface_props.CROP_TYPE = crop_type
    print(f"  🎨 albedo usuli = '{albedo_method}' | 🧊 cold anchor ETrF = {cold_etrf}"
          + (f" | 🌱 z0m crop_type = '{crop_type}'" if crop_type else '')
          + (f" | 🌾 per-crop Kc: {len(crop_assets)} ta asset" if crop_assets else ''))

    # 2. Kalibratsiya ROI — polygon atrofida bufer (cold+hot anchor uchun kengroq)
    roi_calib = poly_geom.bounds().buffer(calib_buffer_m).bounds()

    # 3. Tile aniqlash — polygonni qamrab, eng ko'p bulutsiz sahnali path/row
    tiles = detect_wrs_tiles(poly_geom, date_start, date_end, satellite, cloud_max)
    if not tiles:
        print("  ❌ Polygon uchun Landsat tile topilmadi.")
        return {'tasks': []}
    best, best_n = None, -1
    for (p, r) in tiles:
        nn = (ee.ImageCollection('LANDSAT/LC08/C02/T1_L2')
              .filterBounds(poly_geom).filterDate(date_start, date_end)
              .filter(ee.Filter.eq('WRS_PATH', p))
              .filter(ee.Filter.eq('WRS_ROW', r))
              .filter(ee.Filter.lt('CLOUD_COVER', cloud_max)).size().getInfo())
        if nn > best_n:
            best_n, best = nn, (p, r)
    path, row = best
    tile_label = f'P{path}_R{row}'
    print(f"  Tile: {tile_label} ({best_n} bulutsiz L8 sahna)")

    # 4. SEBAL — MAVJUD pipeline (o'zgarmagan). MUHIM: cloud precheck DALA
    #    (polygon) ustida — keng kalibratsiya ROI'da bulut bo'lsa ham, dala
    #    toza sahnalar saqlanadi (aks holda SJV yozida ko'p clear sahna xato
    #    rad etiladi → paxta piki yo'qoladi → ET past baholanadi).
    scenes, info = process_tile(
        roi_calib, date_start, date_end, mode, satellite, cloud_max,
        tile_label=tile_label, anchor_method=anchor_method,
        anchor_mode=anchor_mode, ref_type=ref_type, utc_offset=utc_offset,
        etr24_source=etr24_source, sloping_terrain=sloping_terrain,
        cloud_roi=poly_geom, cloud_use_cropland=False)
    if not scenes:
        print("  ❌ Sahna yo'q — to'xtatildi.")
        return {'tasks': []}
    grid = energy_balance.analysis_proj(ee.Image(scenes[0]))   # zonal — Landsat tahlil gridi

    # sahna sanalari (bitta getInfo)
    scene_dates = ee.List(
        [ee.Image(s).date().format('YYYYMMdd') for s in scenes]).getInfo()

    # 5. Zonal geometriya — ichki bufer (chet piksel himoyasi) + poly_id
    work = fc.map(lambda f: f.set('poly_id', f.get('system:index')))
    if inner_buffer_m:
        work = work.map(
            lambda f: f.setGeometry(f.geometry().buffer(inner_buffer_m)))

    # 6. Oylik zonal (ET_{year}_{MM}) — akkumulyativ
    first_et = None
    for m in months:
        monthly = daily_et.compute_monthly_et(scenes, roi_calib, year, m, mode=mode,
                                              etrf_water_balance=etrf_water_balance,
                                              ref_type=ref_type,
                                              utc_offset=info['utc_offset'],
                                              etr24_source=etr24_source,
                                              sloping_terrain=sloping_terrain)
        et = monthly.select('ET_MONTHLY')
        if first_et is None:
            first_et = et
        work = _zonal_add(work, et, f'ET_{year}_{m:02d}', crs=grid)
        print(f"  ↪ oylik zonal: ET_{year}_{m:02d}")

    # 7. Per-sahna zonal (ET_{YYYYMMDD} — instant ET_24)
    for s, d in zip(scenes, scene_dates):
        work = _zonal_add(work, ee.Image(s).select('ET_24'), f'ET_{d}', crs=grid)
    print(f"  ↪ {len(scenes)} sahna zonal qo'shildi")

    # 8. QC — valid piksel soni (first oy ET_MONTHLY count) + sahna soni
    work = _zonal_add(work, first_et, 'n_pixels', reducer=ee.Reducer.count(), crs=grid)
    work = work.map(lambda f: f.set('n_scenes', len(scenes)))

    # 9. Export — asset + CSV
    tasks = []
    stamp = f'{year}_{months[0]:02d}_{months[-1]:02d}'
    if out_asset:
        t = ee.batch.Export.table.toAsset(
            collection=work, description=f'polyET_{stamp}_asset',
            assetId=out_asset)
        t.start(); tasks.append(t)
        print(f"  ✅ Asset export → {out_asset}")
    t2 = ee.batch.Export.table.toDrive(
        collection=work, description=f'polyET_{stamp}_csv',
        folder=out_folder, fileFormat='CSV')
    t2.start(); tasks.append(t2)
    print(f"  ✅ CSV export → Drive/{out_folder}/")

    # 10. Ixtiyoriy — oylik ET raster (polygonga clip)
    if export_rasters:
        for m in months:
            monthly = daily_et.compute_monthly_et(scenes, roi_calib, year, m, mode=mode,
                                              etrf_water_balance=etrf_water_balance,
                                              ref_type=ref_type,
                                              utc_offset=info['utc_offset'],
                                              etr24_source=etr24_source,
                                              sloping_terrain=sloping_terrain)
            img = monthly.select('ET_MONTHLY').clip(poly_geom)
            name = f'polyET_raster_{year}-{m:02d}'
            tr = ee.batch.Export.image.toDrive(
                image=_round_export(img), description=name, folder=out_folder,
                fileNamePrefix=name, region=poly_geom.bounds(), scale=30,
                crs=crs, maxPixels=1e13, fileFormat='GeoTIFF')
            tr.start(); tasks.append(tr)
        print(f"  ✅ {len(months)} oylik raster export (clip)")

    print(f"\n  ✅ Tayyor! {len(tasks)} export task")
    print("  🔗 https://code.earthengine.google.com/tasks")
    return {'tasks': tasks, 'scene_dates': scene_dates, 'tile': tile_label}

