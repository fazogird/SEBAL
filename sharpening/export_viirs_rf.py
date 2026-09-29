# -*- coding: utf-8 -*-
"""
VIIRS LST'ni RF (DMS global) bilan 30 m ga keskinlashtirib, GEE asset'iga eksport (T42SUJ).
SEBAL sinovi keskinlashtirishni har so'rovda qayta hisoblamasligi uchun (vaqt/xotira chegarasi).
Asset papkasi: projects/carbon-science-461016-q2/assets/sebal_sharpening_test (faqat sinov uchun).
Ishlatish: python export_viirs_rf.py 2019-08-17 2020-08-03 ...
"""
import ee, os, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dms
from selftest_lst import CRS, TILE, F30, hls_sr
from crosssensor_lst import viirs_lst, PF

FOLDER = os.environ.get('EE_ASSET_FOLDER', 'projects/carbon-science-461016-q2/assets/sebal_sharpening_test')


def asset_id(d):
    return f"{FOLDER}/viirs_rf30_T42SUJ_{d.replace('-', '')}"


def exists(aid):
    try:
        ee.data.getAsset(aid)
        return True
    except ee.EEException:
        return False


if __name__ == '__main__':
    if not exists(FOLDER):
        ee.data.createAsset({'type': 'FOLDER'}, FOLDER)
        print('papka yaratildi:', FOLDER, flush=True)
    tasks = []
    for d in sys.argv[1:]:
        aid = asset_id(d)
        if exists(aid):
            print('allaqachon bor:', aid, flush=True)
            continue
        sr, _ = hls_sr(d)
        lst_c, cproj, _ = viirs_lst(d)
        sh = dms.sharpen(sr, lst_c, TILE, PF, cproj, cproj, kernel_radius=5, cv_threshold=0.25)
        img = (sh.select('lst_global').rename('lst').toFloat()
                 .set({'sana': d, 'usul': 'DMS global RF, EC 1 km',
                       'manba': 'VNP21A1D QC=0 -> UTM 1 km bilinear; prediktor HLS L30 (o\'sha kun)'}))
        t = ee.batch.Export.image.toAsset(image=img, description=f'viirs_rf30_{d}', assetId=aid,
                                          region=TILE, crs=CRS, crsTransform=F30, maxPixels=1e10)
        t.start()
        tasks.append(t)
        print('eksport boshlandi:', aid, flush=True)
    while tasks and any(t.status()['state'] in ('READY', 'RUNNING') for t in tasks):
        time.sleep(30)
    for t in tasks:
        s = t.status()
        print(s['description'], s['state'], s.get('error_message', ''), flush=True)
