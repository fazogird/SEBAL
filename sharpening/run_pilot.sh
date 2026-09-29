#!/bin/bash
# T-A pilot: 1) RF VIIRS asset'lari (ee-chexovant11) 2) 10 kun, 4 parallel jarayon.
cd /d/Cloud_comp/Sebal/scripts/sharpening || exit 1
export EE_PROJECT=ee-chexovant11
export EE_ASSET_FOLDER=projects/ee-chexovant11/assets/sebal_sharpening_test
export PYTHONUNBUFFERED=1 PYTHONIOENCODING=utf-8
PY=/c/Users/d.nozimov/AppData/Local/miniconda3/envs/gee_env/python.exe

echo "eksport boshlandi: $(date +%H:%M)"
$PY export_viirs_rf.py 2019-08-17 2020-08-03 2021-06-19 2022-10-12 2023-05-24 2023-06-09 \
    2023-07-11 2023-09-29 2024-08-14 2025-04-11 > pilot_export.log 2>&1 || { echo "EKSPORT XATO"; exit 1; }
grep -E "FAILED|CANCELLED" pilot_export.log && { echo "EKSPORT MUVAFFAQIYATSIZ"; exit 1; }
echo "eksport tugadi: $(date +%H:%M)"

rm -f pilot_ta_samples_*.csv
OUT_SUFFIX=_a $PY pilot_ta.py 2019-08-17 2020-08-03 2021-06-19 > pilot_a.log 2>&1 &
OUT_SUFFIX=_b $PY pilot_ta.py 2022-10-12 2023-05-24 2023-06-09 > pilot_b.log 2>&1 &
OUT_SUFFIX=_c $PY pilot_ta.py 2023-07-11 2023-09-29 > pilot_c.log 2>&1 &
OUT_SUFFIX=_d $PY pilot_ta.py 2024-08-14 2025-04-11 > pilot_d.log 2>&1 &
wait
echo "PILOT TUGADI: $(date +%H:%M)"
grep -hE "XATO|o'tkazildi" pilot_[abcd].log
grep -hE "nuqta \(ikkala ET bor\)" pilot_[abcd].log
