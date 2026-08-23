# -*- coding: utf-8 -*-
"""
mosaic_zonstat.py — SEBAL ETCU rasterlarni MOSAIC + ZONAL STAT
================================================================
Drive'dan yuklab olingan  SEBAL_monthly_ETCU_YYYY-MM_Pxxx_Rxx.tif
(3 band: ET_MONTHLY, CUIRR, AW — mm/oy) rasterlari uchun:

  1) MOSAIC     — OYMA-OY (har oy alohida; oylar chalkashmaydi), o'sha oydagi
                  barcha tile'ni birlashtiradi (nearest / bilinear).
  2) ZONAL STAT — ekin dala shapefile'i berilsa, har oy uchun ET/CUirr/AW
                  qiymatlarini dalaga yozadi: mm, m3ga (m3/ha), m3 (jami)
                  + mavsumiy JAMI.

Ustun nomlari (DBF ≤10 belgi):  et_03_mm  et_03_ga  et_03_m3  (aw_/cu_ ham)
Jami:                           et_t_mm  et_t_ga  et_t_m3   (aw_/cu_ ham)

Env: gis_pro  (rasterio, geopandas, rasterstats).
Ishga tushirish:  python mosaic_zonstat.py
"""
import os
import re
import glob
import time
import numpy as np
import rasterio
from rasterio.warp import reproject
from rasterio.enums import Resampling
from rasterio.transform import from_origin
import geopandas as gpd
from rasterstats import zonal_stats

NODATA = -9999.0   # chiqish nodata (ET/CUirr/AW ≥0 → xavfsiz)

# ============================================================
#  KONFIGURATSIYA  ← shu yerni to'ldiring
# ============================================================
raster_dir = r"D:\ET_2026\Samarqand\SEBAL_Mil"          # ETCU tif'lar papkasi (Drive'dan yuklangan)
shp_dir    = r"e:\Rocket\GEOBOX\new\UZ_2026_Samarqand_06_new_cadastres\UZ_2026_Samarqand_06_new_cadastres.shp"          # ekin dala shapefile papkasi (zonal uchun; bo'sh bo'lsa faqat mosaic)
out_dir    = r"D:\ET_2026\Samarqand\SEBAL_Mil\Sam"          # chiqish papkasi

mosaic      = True        # True/False — MOSAIC bosqichi (yangi raster saqlash)
zonal_stat  = True        # True/False — ZONAL STAT bosqichi (dalaga qiymat)
mosaic_mode = 'nearest'   # 'nearest' / 'bilinear'  — qayta-namunalash
# ============================================================

# GEE export BAND tartibi — CHALKASHTIRMANG (band description'dan avtomatik topiladi)
PARAM_OF   = {'ET_MONTHLY': 'et', 'CUIRR': 'cu', 'AW': 'aw'}
PARAM_ORDER = ['et', 'cu', 'aw']
PARAM_NAME = {'et': 'ET (bug\'lanish)', 'cu': 'CUirr (sug\'orish iste\'moli)',
              'aw': 'AW (qo\'llangan suv)'}
RESAMPLING = {'nearest': Resampling.nearest, 'bilinear': Resampling.bilinear}

# ---- chiroyli log (ANSI) ----
if os.name == 'nt':
    os.system('')   # Windows 10+ da ANSI ranglarni yoqadi
_C = dict(r='\033[0m', b='\033[1m', dim='\033[2m', cyan='\033[96m', grn='\033[92m',
          yel='\033[93m', red='\033[91m', blu='\033[94m', mag='\033[95m')
def col(s, c): return f"{_C[c]}{s}{_C['r']}"
def hr(ch='─', n=68, c='dim'): print(col(ch * n, c))
def head(txt):
    print()
    print(col('╔' + '═' * 68 + '╗', 'cyan'))
    print(col('║ ', 'cyan') + col(f"{txt:<66}", 'b') + col('║', 'cyan'))
    print(col('╚' + '═' * 68 + '╝', 'cyan'))
def step(icon, txt): print(f"  {icon} {txt}")
def ok(txt): print(f"  {col('✅', 'grn')} {txt}")
def warn(txt): print(f"  {col('⚠️ ', 'yel')} {txt}")
def err(txt): print(f"  {col('❌', 'red')} {txt}")


def banner():
    print(col(r"""
   ╭──────────────────────────────────────────────────────────────╮
   │   💧  SEBAL  MOSAIC  +  ZONAL STAT   —   ET · CUirr · AW  💧    │
   │        oyma-oy mosaic  →  ekin dalaga suv hisobi (m³)          │
   ╰──────────────────────────────────────────────────────────────╯""", 'cyan'))
    print(f"   {col('Mode:', 'dim')} mosaic={col(mosaic,'grn' if mosaic else 'red')}  "
          f"zonal_stat={col(zonal_stat,'grn' if zonal_stat else 'red')}  "
          f"resampling={col(mosaic_mode,'mag')}")


def month_key(path):
    """Fayl nomidan YYYY-MM ni ajratib olish."""
    m = re.search(r'(\d{4})[-_](\d{2})', os.path.basename(path))
    return f"{m.group(1)}-{m.group(2)}" if m else None


def band_index_map(sample_path):
    """Band description'dan {param: band_index}. Topilmasa fiks tartib (1=ET,2=CU,3=AW)."""
    with rasterio.open(sample_path) as src:
        desc = src.descriptions or ()
    bmap = {}
    for i, d in enumerate(desc, 1):
        if d in PARAM_OF:
            bmap[PARAM_OF[d]] = i
    if set(bmap) != set(PARAM_ORDER):
        bmap = {'et': 1, 'cu': 2, 'aw': 3}   # GEE export tartibi (zaxira)
        return bmap, 'FIKS tartib (band description yo\'q)'
    return bmap, 'band description\'dan'


def load_shapefile():
    """shp_dir — .shp FAYL yo'li YOKI ichida .shp bo'lgan PAPKA (ikkalasi ham OK)."""
    if not shp_dir:
        return None, None
    if os.path.isfile(shp_dir) and shp_dir.lower().endswith('.shp'):
        return gpd.read_file(shp_dir), shp_dir           # to'g'ridan fayl
    shps = glob.glob(os.path.join(shp_dir, '*.shp'))      # papka → *.shp qidirish
    if not shps:
        return None, None
    return gpd.read_file(shps[0]), shps[0]


def mean_mosaic(srcs, resampling):
    """
    OVERLAP'da MEAN (o'rtacha) mosaic. Barcha tile umumiy to'rga (union extent,
    bir xil piksel) reproyeksiya qilinadi, keyin har pikselда nodata'siz o'rtacha:
    mean = Σ qiymat / Σ mavjud-tile. Non-overlap = qiymatning o'zi. rasterio.merge
    kabi USTMA-UST yozmaydi (chok/dominatsiya bo'lmaydi).
    Chiqish: nan-nodata float32 array (bands,H,W), transform, (H,W).
    """
    crs = srcs[0].crs
    nb = srcs[0].count
    res = abs(srcs[0].transform.a)                 # piksel o'lchami (m)
    src_nd = srcs[0].nodata
    left = min(s.bounds.left for s in srcs);  right = max(s.bounds.right for s in srcs)
    bottom = min(s.bounds.bottom for s in srcs); top = max(s.bounds.top for s in srcs)
    W = int(round((right - left) / res));  H = int(round((top - bottom) / res))
    transform = from_origin(left, top, res, res)

    ssum = np.zeros((nb, H, W), dtype='float64')
    cnt = np.zeros((nb, H, W), dtype='float64')
    for s in srcs:
        for b in range(nb):
            dst = np.full((H, W), np.nan, dtype='float64')
            reproject(source=rasterio.band(s, b + 1), destination=dst,
                      src_transform=s.transform, src_crs=s.crs,
                      dst_transform=transform, dst_crs=crs, resampling=resampling,
                      src_nodata=src_nd, dst_nodata=np.nan)
            m = np.isfinite(dst)
            ssum[b][m] += dst[m]
            cnt[b][m] += 1.0
    out = np.where(cnt > 0, ssum / np.where(cnt == 0, 1.0, cnt), np.nan)
    return out.astype('float32'), transform, (H, W)


def do_month(mkey, paths, band_map, gdf, raster_crs):
    """Bitta oy: MEAN mosaic (+save) va (agar gdf) zonal stat → gdf'ga ustun."""
    MM = mkey[5:7]
    srcs = [rasterio.open(p) for p in paths]

    # CRS QAT'IY tekshiruv — barcha tile bir xil CRS bo'lishi shart
    crss = {s.crs.to_string() for s in srcs}
    if len(crss) > 1:
        err(f"{mkey}: tile'lar CRS'i har xil {crss} — mosaic BEKOR")
        for s in srcs: s.close()
        return
    desc = srcs[0].descriptions
    profile = srcs[0].profile.copy()

    arr, transform, (H, W) = mean_mosaic(srcs, RESAMPLING[mosaic_mode])
    for s in srcs: s.close()

    step('🧩', f"{col(mkey,'b')}  tile={len(paths)}  →  mosaic {W}×{H} px  "
               f"({mosaic_mode}, overlap={col('MEAN','grn')})")

    # --- mosaic saqlash ---
    if mosaic:
        arr_save = np.where(np.isfinite(arr), arr, NODATA).astype('float32')
        profile.update(height=H, width=W, transform=transform, count=arr.shape[0],
                       dtype='float32', nodata=NODATA, compress='deflate')
        out_tif = os.path.join(out_dir, f"mosaic_ETCU_{mkey}.tif")
        with rasterio.open(out_tif, 'w', **profile) as dst:
            dst.write(arr_save)
            if desc and all(desc):
                dst.descriptions = desc
        ok(f"mosaic saqlandi → {col(os.path.basename(out_tif),'blu')}")

    # --- zonal stat ---
    if zonal_stat and gdf is not None:
        area_ha = gdf.geometry.area / 10000.0    # raster_crs = UTM → m² → ha
        for p in PARAM_ORDER:
            b = arr[band_map[p] - 1]
            band = np.where(np.isfinite(b), b, NODATA).astype('float64')
            zs = zonal_stats(gdf, band, affine=transform, nodata=NODATA,
                             stats=['mean'], all_touched=False)
            mm = np.array([z['mean'] if z['mean'] is not None else 0.0 for z in zs])
            gdf[f'{p}_{MM}_mm'] = np.round(mm, 2)              # mm/oy (o'rtacha chuqurlik)
            gdf[f'{p}_{MM}_ga'] = np.round(mm * 10.0, 1)       # m³/ha  (1mm/ha = 10 m³)
            gdf[f'{p}_{MM}_m3'] = np.round(mm * 10.0 * area_ha, 1)  # m³ (dala bo'yicha jami)
        ok(f"zonal: {col(len(gdf),'b')} dalaga  et/cu/aw_{MM}_(mm|ga|m3) yozildi")


def add_totals(gdf):
    """Barcha oylar bo'yicha JAMI: et_t_mm / et_t_ga / et_t_m3 (aw_/cu_ ham)."""
    for p in PARAM_ORDER:
        mm_cols = sorted(c for c in gdf.columns if re.fullmatch(fr'{p}_\d\d_mm', c))
        m3_cols = sorted(c for c in gdf.columns if re.fullmatch(fr'{p}_\d\d_m3', c))
        if not mm_cols:
            continue
        gdf[f'{p}_t_mm'] = np.round(gdf[mm_cols].sum(axis=1), 2)
        gdf[f'{p}_t_ga'] = np.round(gdf[f'{p}_t_mm'] * 10.0, 1)
        gdf[f'{p}_t_m3'] = np.round(gdf[m3_cols].sum(axis=1), 1)
    return gdf


def summary_table(gdf):
    """Chiroyli yakuniy jadval — mavsumiy JAMI (barcha dala yig'indisi)."""
    hr('━')
    print(col('  📊  MAVSUMIY JAMI (barcha dala)', 'b'))
    hr()
    print(f"  {'Parametr':<28}{'mm (ort)':>12}{'m3/ha (ort)':>15}{'m3 (jami)':>16}")
    hr()
    for p in PARAM_ORDER:
        if f'{p}_t_mm' not in gdf.columns:
            continue
        mm = gdf[f'{p}_t_mm'].mean()
        ga = gdf[f'{p}_t_ga'].mean()
        m3 = gdf[f'{p}_t_m3'].sum()
        cc = {'et': 'grn', 'cu': 'cyan', 'aw': 'mag'}[p]
        print(f"  {col(PARAM_NAME[p],cc):<37}{mm:>12.1f}{ga:>15.0f}{m3:>16,.0f}")
    hr('━')


def main():
    t0 = time.time()
    banner()

    # --- tekshiruvlar ---
    if not raster_dir or not os.path.isdir(raster_dir):
        err(f"raster_dir yo'q yoki bo'sh: {raster_dir!r}"); return
    if not out_dir:
        err("out_dir ko'rsatilmagan"); return
    os.makedirs(out_dir, exist_ok=True)
    if not (mosaic or zonal_stat):
        warn("mosaic=False va zonal_stat=False — qiladigan ish yo'q"); return

    head("1) RASTERLARNI TOPISH VA OYGA GURUHLASH")
    tifs = sorted(glob.glob(os.path.join(raster_dir, '*.tif')))
    tifs = [t for t in tifs if not os.path.basename(t).startswith('mosaic_')]
    if not tifs:
        err(f"{raster_dir} da *.tif topilmadi"); return
    groups = {}
    for t in tifs:
        mk = month_key(t)
        if mk:
            groups.setdefault(mk, []).append(t)
        else:
            warn(f"oy aniqlanmadi, o'tkazildi: {os.path.basename(t)}")
    ok(f"{len(tifs)} raster  →  {len(groups)} oy: {col(', '.join(sorted(groups)),'yel')}")

    band_map, src_ = band_index_map(tifs[0])
    step('🎛️ ', f"band tartibi ({src_}): "
               f"ET=b{band_map['et']}  CU=b{band_map['cu']}  AW=b{band_map['aw']}")

    # --- shapefile ---
    gdf, shp_path = (None, None)
    if zonal_stat:
        head("2) EKIN DALA SHAPEFILE + CRS MOSLASH")
        gdf, shp_path = load_shapefile()
        if gdf is None:
            warn("shp_dir bo'sh/shp yo'q — ZONAL STAT o'tkazib yuboriladi (faqat mosaic)")
        else:
            with rasterio.open(tifs[0]) as s:
                rc = s.crs
            step('🗺️ ', f"shp: {col(os.path.basename(shp_path),'blu')}  "
                       f"({len(gdf)} dala)  CRS={gdf.crs}")
            if gdf.crs is None:
                err("shapefile CRS aniqlanmagan (.prj yo'q) — to'xtatildi"); return
            if gdf.crs.to_string() != rc.to_string():
                warn(f"CRS FARQLI  shp={gdf.crs.to_string()} → raster={rc.to_string()}"
                     f"  |  shp qayta proyeksiya qilinadi")
                gdf = gdf.to_crs(rc)
            ok(f"CRS mos: {col(rc.to_string(),'grn')}  (maydon m² → ha)")

    # --- oyма-oy ishlov ---
    head("3) OYMA-OY MOSAIC" + ("  +  ZONAL STAT" if (zonal_stat and gdf is not None) else ""))
    with rasterio.open(tifs[0]) as s:
        rcrs = s.crs
    for mk in sorted(groups):
        do_month(mk, groups[mk], band_map, gdf, rcrs)

    # --- jami + saqlash ---
    if zonal_stat and gdf is not None:
        head("4) MAVSUMIY JAMI VA SAQLASH")
        gdf = add_totals(gdf)
        out_shp = os.path.join(out_dir, "Sam_fields_ETCU_zonal.shp")
        gdf.to_file(out_shp, encoding='utf-8')
        ok(f"shapefile saqlandi → {col(os.path.basename(out_shp),'blu')}  "
           f"({len(gdf.columns)} ustun)")
        summary_table(gdf)

    print()
    ok(col(f"TAYYOR!  {time.time()-t0:.1f}s  |  chiqish: {out_dir}", 'b'))
    print()


if __name__ == '__main__':
    main()
