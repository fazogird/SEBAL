"""
SEBAL Tile Mosaic — Overlap da O'RTACHA
=========================================
python mosaic_tiles.py "D:\path\to\SEBAL_Samarqand_2026"
python mosaic_tiles.py "D:\path" --daily
"""

import os
import sys
import glob
import numpy as np
from collections import defaultdict
from osgeo import gdal, osr

gdal.UseExceptions()


def find_groups(input_dir, include_daily=False):
    """TIF larni produkt+oy bo'yicha guruhlash."""
    groups = defaultdict(list)
    for f in sorted(glob.glob(os.path.join(input_dir, '*.tif'))):
        name = os.path.basename(f)
        if not include_daily and '_day_' in name:
            continue
        parts = name.rsplit('_P', 1)
        if len(parts) == 2:
            groups[parts[0]].append(f)
    return dict(groups)


def mosaic_mean(files, output_path):
    """
    Bir nechta tile ni mosaic qilish.
    Overlap da: O'RTACHA (mean).
    NoData joylar: boshqa tile dan olish.
    """
    # Barcha tile larni ochish
    datasets = [gdal.Open(f) for f in files]

    # Umumiy bounds hisoblash
    min_x, max_y = float('inf'), float('-inf')
    max_x, min_y = float('-inf'), float('inf')

    for ds in datasets:
        gt = ds.GetGeoTransform()
        w = ds.RasterXSize
        h = ds.RasterYSize
        x0 = gt[0]
        y0 = gt[3]
        x1 = x0 + w * gt[1]
        y1 = y0 + h * gt[5]  # gt[5] manfiy
        min_x = min(min_x, x0, x1)
        max_x = max(max_x, x0, x1)
        min_y = min(min_y, y0, y1)
        max_y = max(max_y, y0, y1)

    # Pixel o'lchami (birinchi tile dan)
    gt0 = datasets[0].GetGeoTransform()
    px = gt0[1]
    py = gt0[5]  # manfiy

    # Output o'lchamlari
    cols = int(np.ceil((max_x - min_x) / px))
    rows = int(np.ceil((max_y - min_y) / abs(py)))

    # Band soni
    n_bands = datasets[0].RasterCount

    # Sum va count massivlar (overlap mean uchun)
    sum_arr = np.zeros((n_bands, rows, cols), dtype=np.float64)
    count_arr = np.zeros((n_bands, rows, cols), dtype=np.int16)

    # NoData qiymati
    nodata = datasets[0].GetRasterBand(1).GetNoDataValue()
    if nodata is None:
        nodata = -9999

    print(f"     Mosaic: {cols}x{rows} px, {n_bands} band")

    for i, ds in enumerate(datasets):
        gt = ds.GetGeoTransform()

        # Bu tile mosaic da qayerga tushadi
        col_off = int(round((gt[0] - min_x) / px))
        row_off = int(round((gt[3] - max_y) / py))

        for b in range(n_bands):
            band = ds.GetRasterBand(b + 1)
            arr = band.ReadAsArray().astype(np.float64)

            # NoData mask
            valid = ~np.isclose(arr, nodata) & ~np.isnan(arr) & (arr > -9000)

            # NaN tekshiruv
            valid = valid & ~np.isnan(arr)

            h, w = arr.shape
            r0 = max(0, row_off)
            c0 = max(0, col_off)
            r1 = min(rows, row_off + h)
            c1 = min(cols, col_off + w)

            # Tile ichidagi mos qism
            tr0 = r0 - row_off
            tc0 = c0 - col_off
            tr1 = tr0 + (r1 - r0)
            tc1 = tc0 + (c1 - c0)

            tile_data = arr[tr0:tr1, tc0:tc1]
            tile_valid = valid[tr0:tr1, tc0:tc1]

            sum_arr[b, r0:r1, c0:c1] += np.where(tile_valid, tile_data, 0)
            count_arr[b, r0:r1, c0:c1] += tile_valid.astype(np.int16)

        print(f"     Tile {i+1}/{len(datasets)}: {os.path.basename(files[i])}")

    # O'rtacha hisoblash (count=0 bo'lsa NoData)
    with np.errstate(divide='ignore', invalid='ignore'):
        result = np.where(count_arr > 0, sum_arr / count_arr, np.nan)

    # GeoTIFF yozish
    driver = gdal.GetDriverByName('GTiff')
    out_ds = driver.Create(
        output_path, cols, rows, n_bands, gdal.GDT_Float32,
        options=['COMPRESS=LZW', 'TILED=YES', 'BIGTIFF=YES'])

    out_gt = (min_x, px, 0, max_y, 0, py)
    out_ds.SetGeoTransform(out_gt)
    out_ds.SetProjection(datasets[0].GetProjection())

    for b in range(n_bands):
        band = out_ds.GetRasterBand(b + 1)
        band_data = result[b]
        band_data = np.where(np.isnan(band_data), -9999, band_data)
        band.WriteArray(band_data.astype(np.float32))
        band.SetNoDataValue(-9999)

    out_ds.FlushCache()
    out_ds = None

    # Dataset larni yopish
    for ds in datasets:
        ds = None


def run(input_dir, include_daily=False):
    """Asosiy pipeline."""
    print(f"\n{'='*50}")
    print(f"  SEBAL Tile Mosaic")
    print(f"  Input:  {input_dir}")
    print(f"  Daily:  {'Ha' if include_daily else 'Faqat monthly'}")
    print(f"{'='*50}\n")

    groups = find_groups(input_dir, include_daily)

    if not groups:
        print("  ❌ TIF topilmadi!")
        return

    out_dir = os.path.join(input_dir, 'mosaic')
    os.makedirs(out_dir, exist_ok=True)

    for base, files in sorted(groups.items()):
        out_path = os.path.join(out_dir, f'{base}.tif')

        if len(files) == 1:
            gdal.Translate(out_path, files[0],
                           creationOptions=['COMPRESS=LZW', 'TILED=YES'])
            size_mb = os.path.getsize(out_path) / 1e6
            print(f"  📋 {base} (1 tile → {size_mb:.0f} MB)")
        else:
            print(f"  🔄 {base} ({len(files)} tile)...")
            mosaic_mean(files, out_path)
            size_mb = os.path.getsize(out_path) / 1e6
            print(f"  ✅ {base} → {size_mb:.0f} MB\n")

    print(f"{'='*50}")
    print(f"  ✅ Tayyor! {out_dir}")
    print(f"{'='*50}")


if __name__ == '__main__':
    input_dir = sys.argv[1] if len(sys.argv) > 1 else '.'
    include_daily = '--daily' in sys.argv
    run(input_dir, include_daily)