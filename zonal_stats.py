# """
# SEBAL Zonal Statistics
# =======================
# Mosaic rasterlar + shapefile → zonal statistika.

# Ishlatish:
#   python zonal_stats.py

# Sozlamalar: pastdagi CONFIG bo'limida.
# """

# import os
# import sys
# import glob
# import numpy as np
# import geopandas as gpd
# from osgeo import gdal, ogr, osr
# from tqdm import tqdm
# from collections import OrderedDict

# gdal.UseExceptions()


# # ==============================================================
# # CONFIG — SHU YERDA O'ZGARTIRING
# # ==============================================================

# # Mosaic papka
# RASTER_DIR = r"D:\ET_2026\Samarqand\Sebal\SEBAL_Samarqand_2026-20260601T094526Z-3-002\SEBAL_Samarqand_2026\mosaic"

# # Shapefile
# SHP_PATH = r"e:\Rocket\ET_2026\Sam_ET.shp"

# # Output
# OUTPUT_PATH = r"D:\ET_2026\Samarqand\Sebal\output\Fields\Sam_stats.shp"
# # OUTPUT_PATH = r"D:\ET_2026\Samarqand\zonal_stats.gpkg"  # GPKG uchun

# # Raster patternlar — qaysilarni hisoblash kerak
# # Nomi: (pattern, birlik, turi)
# # turi: 'mm' → mm, m³ ham hisoblanadi
# #        'kg_ha' → kg/ha, ton ham hisoblanadi
# #        'other' → faqat mean/min/max
# PRODUCT_TYPES = OrderedDict([
#     ('ET',      ('mm',    'mm')),
#     ('Biomass', ('kg/ha', 'kg_ha')),
#     ('ETref',   ('mm',    'mm')),
#     ('Tact',    ('mm',    'mm')),
#     ('Eact',    ('mm',    'mm')),
# ])

# # ============================================================
# # KERAK BO'LSA QO'SHING:
# # ('WP',     ('SEBAL_monthly_WP_2026-03.tif',     'kg/m3', 'other')),
# # ('NDVI',   ('SEBAL_monthly_NDVI_2026-03.tif',   '',      'other')),
# # ('KC',     ('SEBAL_monthly_KC_2026-03.tif',      '',      'other')),
# # ============================================================

# NODATA = -9999


# # ==============================================================
# # ZONAL STATS HISOBLASH
# # ==============================================================

# def raster_info(raster_path):
#     """Raster ma'lumotlari."""
#     ds = gdal.Open(raster_path)
#     gt = ds.GetGeoTransform()
#     proj = ds.GetProjection()
#     srs = osr.SpatialReference()
#     srs.ImportFromWkt(proj)
#     px_m = gt[1]  # pixel o'lchami metrda (UTM uchun)
#     ds = None
#     return {
#         'pixel_size': px_m,
#         'crs_wkt': proj,
#         'is_projected': srs.IsProjected(),
#         'unit': srs.GetLinearUnitsName() if srs.IsProjected() else 'degree',
#     }


# # def compute_polygon_stats(raster_path, geometry, gt, arr, nodata=NODATA):
# #     """
# #     Bitta polygon uchun zonal statistika.
# #     Rasterize → mask → hisoblash.
# #     """
# #     # Polygon bounds
# #     minx, miny, maxx, maxy = geometry.bounds

# #     # Pixel koordinatalar
# #     col0 = int((minx - gt[0]) / gt[1])
# #     row0 = int((maxy - gt[3]) / gt[5])
# #     col1 = int((maxx - gt[0]) / gt[1]) + 1
# #     row1 = int((miny - gt[3]) / gt[5]) + 1

# #     # Chegaralarni tekshirish
# #     col0 = max(0, col0)
# #     row0 = max(0, row0)
# #     col1 = min(arr.shape[1], col1)
# #     row1 = min(arr.shape[0], row1)

# #     if col0 >= col1 or row0 >= row1:
# #         return None

# #     # Sub-array
# #     sub = arr[row0:row1, col0:col1]

# #     # Polygon ni rasterize
# #     h = row1 - row0
# #     w = col1 - col0

# #     sub_gt = (gt[0] + col0 * gt[1], gt[1], 0,
# #               gt[3] + row0 * gt[5], 0, gt[5])

# #     mem_drv = gdal.GetDriverByName('MEM')
# #     mem_ds = mem_drv.Create('', w, h, 1, gdal.GDT_Byte)
# #     mem_ds.SetGeoTransform(sub_gt)
    
# #     # 🛡 XATONI TUZATISH: Proyeksiyani o'rnatamiz
# #     if projection:
# #         mem_ds.SetProjection(projection)

# #     mem_band = mem_ds.GetRasterBand(1)
# #     mem_band.Fill(0)

# #     # OGR geometry yaratish
# #     ogr_geom = ogr.CreateGeometryFromWkb(geometry.wkb)

# #     mem_lyr_drv = ogr.GetDriverByName('Memory')
# #     mem_vec = mem_lyr_drv.CreateDataSource('')
# #     srs = osr.SpatialReference()
# #     srs.ImportFromWkt(mem_ds.GetProjection() if mem_ds.GetProjection() else '')
    
# #     if projection:
# #         srs.ImportFromWkt(projection)
        
# #     mem_lyr = mem_vec.CreateLayer('', srs, ogr.wkbPolygon)
# #     feat = ogr.Feature(mem_lyr.GetLayerDefn())
# #     feat.SetGeometry(ogr_geom)
# #     mem_lyr.CreateFeature(feat)

# #     gdal.RasterizeLayer(mem_ds, [1], mem_lyr, burn_values=[1])
# #     mask = mem_band.ReadAsArray().astype(bool)

# #     mem_ds = None
# #     mem_vec = None

# #     # Valid piksellar
# #     valid = mask & (sub > -9000) & ~np.isnan(sub) & (sub != nodata)
# #     values = sub[valid]

# #     if len(values) == 0:
# #         return None

# #     return {
# #         'mean': float(np.mean(values)),
# #         'min': float(np.min(values)),
# #         'max': float(np.max(values)),
# #         'std': float(np.std(values)),
# #         'count': int(len(values)),
# #     }

# def compute_polygon_stats(raster_path, geometry, gt, arr, projection, nodata=NODATA):
#     """
#     Bitta polygon uchun zonal statistika.
#     Rasterize → mask → hisoblash.
#     """
#     # Polygon bounds
#     minx, miny, maxx, maxy = geometry.bounds

#     # Pixel koordinatalar
#     col0 = int((minx - gt[0]) / gt[1])
#     row0 = int((maxy - gt[3]) / gt[5])
#     col1 = int((maxx - gt[0]) / gt[1]) + 1
#     row1 = int((miny - gt[3]) / gt[5]) + 1

#     # Chegaralarni tekshirish
#     col0 = max(0, col0)
#     row0 = max(0, row0)
#     col1 = min(arr.shape[1], col1)
#     row1 = min(arr.shape[0], row1)

#     if col0 >= col1 or row0 >= row1:
#         return None

#     # Sub-array
#     sub = arr[row0:row1, col0:col1]

#     # Polygon ni rasterize
#     h = row1 - row0
#     w = col1 - col0

#     sub_gt = (gt[0] + col0 * gt[1], gt[1], 0,
#               gt[3] + row0 * gt[5], 0, gt[5])

#     mem_drv = gdal.GetDriverByName('MEM')
#     mem_ds = mem_drv.Create('', w, h, 1, gdal.GDT_Byte)
#     mem_ds.SetGeoTransform(sub_gt)
    
#     # 🛡 XATONI TUZATISH: Proyeksiyani o'rnatamiz
#     if projection:
#         mem_ds.SetProjection(projection)

#     mem_band = mem_ds.GetRasterBand(1)
#     mem_band.Fill(0)

#     # OGR geometry yaratish
#     ogr_geom = ogr.CreateGeometryFromWkb(geometry.wkb)

#     mem_lyr_drv = ogr.GetDriverByName('Memory')
#     mem_vec = mem_lyr_drv.CreateDataSource('')
#     srs = osr.SpatialReference()
    
#     # 🛡 XATONI TUZATISH: To'g'ridan-to'g'ri o'zimiz bergan proyeksiyadan o'qiymiz
#     if projection:
#         srs.ImportFromWkt(projection)
        
#     mem_lyr = mem_vec.CreateLayer('', srs, ogr.wkbPolygon)
#     feat = ogr.Feature(mem_lyr.GetLayerDefn())
#     feat.SetGeometry(ogr_geom)
#     mem_lyr.CreateFeature(feat)

#     gdal.RasterizeLayer(mem_ds, [1], mem_lyr, burn_values=[1])
#     mask = mem_band.ReadAsArray().astype(bool)

#     mem_ds = None
#     mem_vec = None

#     # Valid piksellar
#     valid = mask & (sub > -9000) & ~np.isnan(sub) & (sub != nodata)
#     values = sub[valid]

#     if len(values) == 0:
#         return None

#     return {
#         'mean': float(np.mean(values)),
#         'min': float(np.min(values)),
#         'max': float(np.max(values)),
#         'std': float(np.std(values)),
#         'count': int(len(values)),
#     }


# def zonal_stats_for_raster(raster_path, gdf, pixel_area_m2):
#     """
#     Barcha polygonlar uchun bitta raster bo'yicha zonal stats.
#     """
#     ds = gdal.Open(raster_path)
#     gt = ds.GetGeoTransform()
#     arr = ds.GetRasterBand(1).ReadAsArray().astype(np.float64)
#     projection = ds.GetProjection()
#     ds = None

#     results = []
#     for idx in range(len(gdf)):
#         geom = gdf.geometry.iloc[idx]
#         if geom is None or geom.is_empty:
#             results.append(None)
#             continue
#         # PROJECTION qator oxiriga qo'shildi!
#         stats = compute_polygon_stats(raster_path, geom, gt, arr, projection)
#         results.append(stats)

#     return results


# # ==============================================================
# # USTUN NOMLARI (shapefile 10 belgi limit)
# # ==============================================================

# def make_columns(name, unit_type, pixel_area_m2):
#     """
#     Produkt uchun ustun nomlari va konversiya.
#     Shapefile: max 10 belgi!
#     """
#     cols = OrderedDict()

#     # Asosiy: mean, min, max
#     cols[f'{name}_mean'] = 'mean'
#     cols[f'{name}_min'] = 'min'
#     cols[f'{name}_max'] = 'max'

#     if unit_type == 'mm':
#         # mm → m³ = mean_mm × area_ha × 10
#         # 1 mm = 10 m³/ha
#         cols[f'{name}_m3'] = 'volume_m3'

#     elif unit_type == 'kg_ha':
#         # kg/ha → ton = mean × area_ha / 1000
#         cols[f'{name}_ton'] = 'mass_ton'

#     return cols


# # ==============================================================
# # MAIN
# # ==============================================================

# def main():
#     print(f"\n{'='*60}")
#     print(f"  SEBAL Zonal Statistics")
#     print(f"{'='*60}")

#     # ---- 1. Shapefile yuklash ----
#     print(f"\n  📂 Shapefile: {os.path.basename(SHP_PATH)}")
#     gdf = gpd.read_file(SHP_PATH)
#     print(f"     Polygonlar: {len(gdf)}")
#     print(f"     CRS: {gdf.crs}")

#     # ---- 2. CRS tekshirish ----
#     # Raster CRS olish
#     first_raster = None
#     # for name, (pattern, unit, utype) in PRODUCT_TYPES.items():
#     #     path = os.path.join(RASTER_DIR, pattern)
#     #     if os.path.exists(path):
#     #         first_raster = path
#     #         break
    
#     all_rasters = sorted(glob.glob(os.path.join(RASTER_DIR, 'SEBAL_monthly_*.tif')))
#     first_raster = all_rasters[0] if all_rasters else None

#     if first_raster is None:
#         print("  ❌ Raster topilmadi! RASTER_DIR va PRODUCT_TYPES ni tekshiring.")
#         return

#     r_info = raster_info(first_raster)
#     print(f"     Raster CRS: {r_info['unit']}, pixel: {r_info['pixel_size']:.1f}m")


#     try:
#         from fiona.crs import from_wkt
#         import pyproj
#         raster_srs = osr.SpatialReference()
#         raster_srs.ImportFromWkt(r_info['crs_wkt'])
#         raster_epsg = raster_srs.GetAuthorityCode(None)
#         if raster_epsg:
#             target_crs = f'EPSG:{raster_epsg}'
#         else:
#             target_crs = r_info['crs_wkt']
#     except:
#         target_crs = r_info['crs_wkt']

#     if str(gdf.crs) != str(target_crs):
#         print(f"     ⚠️ CRS farq! Reproject: {gdf.crs} → {target_crs}")
#         gdf = gdf.to_crs(target_crs)

#     # ---- 3. Polygon maydonlarini hisoblash ----
#     pixel_area_m2 = r_info['pixel_size'] ** 2
#     gdf['area_m2'] = gdf.geometry.area
#     gdf['area_ha'] = gdf['area_m2'] / 10000.0
#     print(f"     Umumiy maydon: {gdf['area_ha'].sum():.0f} ha")

#     # ---- 4. Barcha oy va produktlarni avtomatik topish ----
#     print(f"\n  📊 Rasterlar qidirilmoqda...\n")

#     all_rasters = sorted(glob.glob(os.path.join(RASTER_DIR, 'SEBAL_monthly_*.tif')))
#     print(f"     Topilgan rasterlar: {len(all_rasters)}")

#     for raster_path in tqdm(all_rasters, desc="  Zonal stats", ncols=60):
#         fname = os.path.basename(raster_path).replace('.tif', '')
#         # SEBAL_monthly_ET_2026-03 → parts
#         parts = fname.split('_')
#         # parts: ['SEBAL', 'monthly', 'ET', '2026-03']
#         #    yoki ['SEBAL', 'monthly', 'Biomass', '2026-03']
#         prod_name = parts[2]      # ET, Biomass, ETref, Tact, Eact
#         month_str = parts[3]      # 2026-03, 2026-04

#         # Produkt turini olish
#         if prod_name not in PRODUCT_TYPES:
#             print(f"\n     ⚠️ {prod_name} turi noma'lum, o'tkazildi")
#             continue

#         unit, utype = PRODUCT_TYPES[prod_name]

#         # Ustun prefiksi: ET_03, Biom_04 kabi (10 belgi limit)
#         month_short = month_str[-2:]  # 03, 04
#         prefix = f'{prod_name[:4]}_{month_short}'  # ET_03, Biom_03, ETre_04

#         # Zonal stats
#         results = zonal_stats_for_raster(raster_path, gdf, pixel_area_m2)

#         means, mins, maxs = [], [], []
#         for r in results:
#             if r is not None:
#                 means.append(r['mean'])
#                 mins.append(r['min'])
#                 maxs.append(r['max'])
#             else:
#                 means.append(np.nan)
#                 mins.append(np.nan)
#                 maxs.append(np.nan)

#         gdf[f'{prefix}_mn'] = means
#         gdf[f'{prefix}_mi'] = mins
#         gdf[f'{prefix}_mx'] = maxs

#         if utype == 'mm':
#             gdf[f'{prefix}_m3'] = (
#                 gdf[f'{prefix}_mn'] / 1000.0 * gdf['area_m2']
#             )
#         elif utype == 'kg_ha':
#             gdf[f'{prefix}_tn'] = (
#                 gdf[f'{prefix}_mn'] * gdf['area_ha'] / 1000.0
#             )

#     # ---- 5. Saqlash ----
#     print(f"\n  💾 Saqlash: {OUTPUT_PATH}")

#     # Ortiqcha geometry ustunlarini tozalash
#     cols_to_drop = [c for c in gdf.columns
#                     if c.startswith('_') or c in ['area_m2']]
#     gdf = gdf.drop(columns=cols_to_drop, errors='ignore')

#     # Format bo'yicha saqlash
#     ext = os.path.splitext(OUTPUT_PATH)[1].lower()
#     if ext == '.gpkg':
#         gdf.to_file(OUTPUT_PATH, driver='GPKG')
#     elif ext == '.geojson':
#         gdf.to_file(OUTPUT_PATH, driver='GeoJSON')
#     else:
#         gdf.to_file(OUTPUT_PATH, driver='ESRI Shapefile')

#     # ---- 6. Xulosa ----
#     print(f"\n{'='*60}")
#     print(f"  ✅ Tayyor!")
#     print(f"  📁 {OUTPUT_PATH}")
#     print(f"  📊 Polygonlar: {len(gdf)}")
#     print(f"  📋 Ustunlar:")

#     stat_cols = [c for c in gdf.columns
#                  if c not in ['geometry'] and not c.startswith('_')]
#     for c in stat_cols:
#         if c == 'geometry':
#             continue
#         if gdf[c].dtype in [np.float64, np.float32, float]:
#             print(f"     {c:<12} {gdf[c].mean():.2f} (o'rtacha)")
#         else:
#             print(f"     {c:<12}")

#     print(f"{'='*60}")

#     # Jadval ko'rsatish
#     print(f"\n  📋 Birinchi 5 ta polygon:")
#     display_cols = [c for c in gdf.columns if c != 'geometry']
#     print(gdf[display_cols].head().to_string(index=False))


# if __name__ == '__main__':
#     main()



"""
SEBAL Zonal Statistics
=======================
Mosaic rasterlar + shapefile → zonal statistika.
(Faqat mm, m3 va m3ga hisoblaydi. Ortiqcha min/max olib tashlangan!)

Ishlatish:
  python zonal_stats.py
"""

import os
import sys
import glob
import numpy as np
import geopandas as gpd
from osgeo import gdal, ogr, osr
from tqdm import tqdm
from collections import OrderedDict

gdal.UseExceptions()

# ==============================================================
# CONFIG — SHU YERDA O'ZGARTIRING
# ==============================================================

# Mosaic papka
RASTER_DIR = r"D:\ET_2026\Qashqadaryo\Sebal\drive-download-20260604T153930Z-3-001\mosaic"

# Shapefile
SHP_PATH = r"e:\Rocket\ET_2026\Qashqadaryo\Qashqadaryo_ET.shp"

# Output
OUTPUT_PATH = r"e:\Rocket\ET_2026\Qashqadaryo\Qashqadaryo_ET_stats.shp"

# Raster patternlar
PRODUCT_TYPES = OrderedDict([
    ('ET',      ('mm',    'mm')),
    ('Biomass', ('kg/ha', 'kg_ha')),
    ('ETref',   ('mm',    'mm')),
    ('Tact',    ('mm',    'mm')),
    ('Eact',    ('mm',    'mm')),
])

NODATA = -9999

# ==============================================================
# ZONAL STATS HISOBLASH
# ==============================================================

def raster_info(raster_path):
    """Raster ma'lumotlari."""
    ds = gdal.Open(raster_path)
    gt = ds.GetGeoTransform()
    proj = ds.GetProjection()
    srs = osr.SpatialReference()
    srs.ImportFromWkt(proj)
    px_m = gt[1]  
    ds = None
    return {
        'pixel_size': px_m,
        'crs_wkt': proj,
        'is_projected': srs.IsProjected(),
        'unit': srs.GetLinearUnitsName() if srs.IsProjected() else 'degree',
    }

def compute_polygon_stats(raster_path, geometry, gt, arr, projection, nodata=NODATA):
    """
    Bitta polygon uchun faqat O'RTACHA (mean) zonal statistika.
    """
    minx, miny, maxx, maxy = geometry.bounds

    col0 = int((minx - gt[0]) / gt[1])
    row0 = int((maxy - gt[3]) / gt[5])
    col1 = int((maxx - gt[0]) / gt[1]) + 1
    row1 = int((miny - gt[3]) / gt[5]) + 1

    col0 = max(0, col0)
    row0 = max(0, row0)
    col1 = min(arr.shape[1], col1)
    row1 = min(arr.shape[0], row1)

    if col0 >= col1 or row0 >= row1:
        return None

    sub = arr[row0:row1, col0:col1]

    h = row1 - row0
    w = col1 - col0

    sub_gt = (gt[0] + col0 * gt[1], gt[1], 0,
              gt[3] + row0 * gt[5], 0, gt[5])

    mem_drv = gdal.GetDriverByName('MEM')
    mem_ds = mem_drv.Create('', w, h, 1, gdal.GDT_Byte)
    mem_ds.SetGeoTransform(sub_gt)
    
    if projection:
        mem_ds.SetProjection(projection)

    mem_band = mem_ds.GetRasterBand(1)
    mem_band.Fill(0)

    ogr_geom = ogr.CreateGeometryFromWkb(geometry.wkb)

    mem_lyr_drv = ogr.GetDriverByName('Memory')
    mem_vec = mem_lyr_drv.CreateDataSource('')
    srs = osr.SpatialReference()
    
    if projection:
        srs.ImportFromWkt(projection)
        
    mem_lyr = mem_vec.CreateLayer('', srs, ogr.wkbPolygon)
    feat = ogr.Feature(mem_lyr.GetLayerDefn())
    feat.SetGeometry(ogr_geom)
    mem_lyr.CreateFeature(feat)

    gdal.RasterizeLayer(mem_ds, [1], mem_lyr, burn_values=[1])
    mask = mem_band.ReadAsArray().astype(bool)

    mem_ds = None
    mem_vec = None

    valid = mask & (sub > -9000) & ~np.isnan(sub) & (sub != nodata)
    values = sub[valid]

    if len(values) == 0:
        return None

    # ORTIQCHA YUKLARDAN QUTULDIK! Faqat mean hisoblaydi
    return {
        'mean': float(np.mean(values)),
    }

def zonal_stats_for_raster(raster_path, gdf, pixel_area_m2):
    ds = gdal.Open(raster_path)
    gt = ds.GetGeoTransform()
    arr = ds.GetRasterBand(1).ReadAsArray().astype(np.float64)
    projection = ds.GetProjection()
    ds = None

    results = []
    for idx in range(len(gdf)):
        geom = gdf.geometry.iloc[idx]
        if geom is None or geom.is_empty:
            results.append(None)
            continue
        stats = compute_polygon_stats(raster_path, geom, gt, arr, projection)
        results.append(stats)

    return results

# ==============================================================
# MAIN
# ==============================================================

def main():
    print(f"\n{'='*60}")
    print(f"  SEBAL Zonal Statistics (Optimized)")
    print(f"{'='*60}")

    print(f"\n  📂 Shapefile: {os.path.basename(SHP_PATH)}")
    gdf = gpd.read_file(SHP_PATH)
    print(f"     Polygonlar: {len(gdf)}")
    print(f"     CRS: {gdf.crs}")

    all_rasters = sorted(glob.glob(os.path.join(RASTER_DIR, 'SEBAL_monthly_*.tif')))
    first_raster = all_rasters[0] if all_rasters else None

    if first_raster is None:
        print("  ❌ Raster topilmadi! RASTER_DIR ni tekshiring.")
        return

    r_info = raster_info(first_raster)
    print(f"     Raster CRS: {r_info['unit']}, pixel: {r_info['pixel_size']:.1f}m")

    try:
        raster_srs = osr.SpatialReference()
        raster_srs.ImportFromWkt(r_info['crs_wkt'])
        raster_epsg = raster_srs.GetAuthorityCode(None)
        target_crs = f'EPSG:{raster_epsg}' if raster_epsg else r_info['crs_wkt']
    except:
        target_crs = r_info['crs_wkt']

    if str(gdf.crs) != str(target_crs):
        print(f"     ⚠️ CRS farq! Reproject: {gdf.crs} → {target_crs}")
        gdf = gdf.to_crs(target_crs)

    gdf['area_m2'] = gdf.geometry.area
    gdf['area_ha'] = gdf['area_m2'] / 10000.0
    print(f"     Umumiy maydon: {gdf['area_ha'].sum():.0f} ha")

    print(f"\n  📊 Rasterlar qidirilmoqda...\n")
    print(f"     Topilgan rasterlar: {len(all_rasters)}")

    for raster_path in tqdm(all_rasters, desc="  Zonal stats", ncols=60):
        fname = os.path.basename(raster_path).replace('.tif', '')
        parts = fname.split('_')
        prod_name = parts[2]      
        month_str = parts[3]      

        if prod_name not in PRODUCT_TYPES:
            continue

        unit, utype = PRODUCT_TYPES[prod_name]
        month_short = month_str[-2:]  
        prefix = f'{prod_name[:4]}_{month_short}' 

        results = zonal_stats_for_raster(raster_path, gdf, r_info['pixel_size']**2)

        means = []
        for r in results:
            if r is not None:
                means.append(r['mean'])
            else:
                means.append(np.nan)

        # ==========================================
        # FAKAT SIZ SORG'AN USTUNLAR (mm, m3, m3ga)
        # ==========================================
        if utype == 'mm':
            gdf[f'{prefix}_mm']   = np.round(means, 2)
            gdf[f'{prefix}_m3']   = np.round((gdf[f'{prefix}_mm'] / 1000.0) * gdf['area_m2'], 1)
            gdf[f'{prefix}_m3ga'] = np.round(gdf[f'{prefix}_mm'] * 10.0, 1)
            
        elif utype == 'kg_ha':
            gdf[f'{prefix}_kg'] = np.round(means, 2)
            gdf[f'{prefix}_tn'] = np.round((gdf[f'{prefix}_kg'] * gdf['area_ha']) / 1000.0, 2)

    print(f"\n  💾 Saqlash: {OUTPUT_PATH}")

    cols_to_drop = [c for c in gdf.columns if c.startswith('_') or c in ['area_m2']]
    gdf = gdf.drop(columns=cols_to_drop, errors='ignore')

    ext = os.path.splitext(OUTPUT_PATH)[1].lower()
    if ext == '.gpkg':
        gdf.to_file(OUTPUT_PATH, driver='GPKG')
    elif ext == '.geojson':
        gdf.to_file(OUTPUT_PATH, driver='GeoJSON')
    else:
        gdf.to_file(OUTPUT_PATH, driver='ESRI Shapefile')

    print(f"\n{'='*60}")
    print(f"  ✅ Tayyor!")
    print(f"  📁 {OUTPUT_PATH}")
    print(f"  📊 Polygonlar: {len(gdf)}")
    print(f"  📋 Yangi yaratilgan aniq ustunlar (min/max larsiz):")

    stat_cols = [c for c in gdf.columns if c not in ['geometry', 'area_ha']]
    for c in stat_cols:
        if gdf[c].dtype in [np.float64, np.float32, float]:
            print(f"     {c:<12} {gdf[c].mean():.2f} (o'rtacha)")

    print(f"{'='*60}")

if __name__ == '__main__':
    main()