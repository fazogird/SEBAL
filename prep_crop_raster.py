# -*- coding: utf-8 -*-
"""
SHP → CROP-CODE RASTER (lokal, yengil). 3 viloyat kadastr → 30m crop-code GeoTIFF
(uint8, deflate — kichik fayl) → GEE'ga Image asset qilib yuklash TEZ.

Har piksel = ekin kodi (Paxta=1..Boshqa=11; Baliqxovuz/Issiqxona=0=nodata).
CRS EPSG:4326 (GEE reproyeksiyani o'zi qiladi; area GEE'da geodezik). ~30m ≈ 0.00027°.
3 viloyat BITTA merged rasterга (bo'shliqlar=0, siqiladi).
"""
import numpy as np
import geopandas as gpd
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.merge import merge

OUT = r'D:/Cloud_comp/Sebal/Input/polygons/for_gee'
PROVS = ['Samarqand', 'Fargona', 'Qashqadaryo']
RES = 0.00027                       # ~30 m (daraja)


def rasterize_prov(prov):
    g = gpd.read_file(f'{OUT}/{prov}_crop.shp')     # 4326, crop_code
    b = g.total_bounds
    w = int(np.ceil((b[2] - b[0]) / RES))
    h = int(np.ceil((b[3] - b[1]) / RES))
    tr = from_origin(b[0], b[3], RES, RES)
    arr = rasterize(
        ((geom, int(c)) for geom, c in zip(g.geometry, g.crop_code) if c > 0),
        out_shape=(h, w), transform=tr, fill=0, dtype='uint8', all_touched=False)
    tif = f'{OUT}/{prov}_crop_30m.tif'
    with rasterio.open(tif, 'w', driver='GTiff', height=h, width=w, count=1,
                       dtype='uint8', crs='EPSG:4326', transform=tr,
                       compress='deflate', nodata=0) as dst:
        dst.write(arr, 1)
    import os
    mb = os.path.getsize(tif) / 1e6
    print(f"  ✅ {prov}: {h}×{w} px → {tif}  ({mb:.1f} MB)")
    return tif


def main():
    import os
    tifs = [rasterize_prov(p) for p in PROVS]
    # 3 → bitta merged
    srcs = [rasterio.open(t) for t in tifs]
    marr, mtr = merge(srcs)
    for s in srcs:
        s.close()
    out = f'{OUT}/UZB_3viloyat_crop_30m.tif'
    with rasterio.open(out, 'w', driver='GTiff', height=marr.shape[1],
                       width=marr.shape[2], count=1, dtype='uint8', crs='EPSG:4326',
                       transform=mtr, compress='deflate', nodata=0) as dst:
        dst.write(marr[0], 1)
    print(f"\n  🎯 MERGED: {marr.shape[2]}×{marr.shape[1]} px → {out}"
          f"  ({os.path.getsize(out)/1e6:.1f} MB)")
    print("  → GEE Assets → New → GeoTIFF → shu faylni yukla.")


if __name__ == '__main__':
    main()
