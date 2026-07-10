# """
# SEBAL-GEE v4 — Test Script
# ============================
# Har bir modulni ketma-ket sinab ko'rish.

# Ishlatish:
#   1. Google Colab da yoki lokal Python da
#   2. ee.Authenticate() va ee.Initialize() qilish
#   3. Bu skriptni ishga tushirish

# Har qadam natijasini tekshiramiz — xatolik bo'lsa to'xtaymiz.
# """

# import ee

# # ---- GEE INIT ----
# # Colab da: ee.Authenticate() kerak bo'lishi mumkin

# GEE_PROJECT = "ee-chexovant11" # O'zgartiring o'z GEE project nomingizga

# try:
#     ee.Initialize(project=GEE_PROJECT)
#     print("✅ GEE initialized")
# except Exception as e:
#     print(f"❌ GEE init xato: {e}")
#     print("   ee.Authenticate() qiling avval")
#     raise

# # ---- IMPORT ----
# import sys
# sys.path.insert(0, '.')  # agar sebal_gee_v4/ joriy papkada bo'lsa

# from sebal_gee_v4 import config as cfg
# from sebal_gee_v4 import preprocessing
# from sebal_gee_v4 import surface_props
# from sebal_gee_v4 import radiation
# from sebal_gee_v4 import energy_balance
# from sebal_gee_v4 import daily_et

# print("✅ Barcha modullar import qilindi")

# # ==============================================================
# # TEST PARAMETRLARI — kichik hudud, bitta oy
# # ==============================================================

# # Idaho — kichik test hudud (Twin Falls atrofi)
# TEST_ROI = ee.Geometry.Rectangle([-114.5, 42.5, -114.2, 42.7])
# TEST_DATE_START = '2024-07-01'
# TEST_DATE_END = '2024-07-31'
# TEST_SATELLITE = 'BOTH'

# print("\nTest hudud: Twin Falls, Idaho")
# print(f"Sana: {TEST_DATE_START} → {TEST_DATE_END}")
# print(f"Satellite: {TEST_SATELLITE}")


# # ==============================================================
# # TEST 1: Config
# # ==============================================================
# print("\n" + "="*60)
# print("TEST 1: Config")
# print("="*60)



# # ROI builder test
# try:
#     roi_rect = cfg.build_roi('rectangle', bounds=[-114.5, 42.5, -114.2, 42.7])
#     roi_gaul = cfg.build_roi('gaul', name='Idaho', level=1)
#     print("✅ ROI builder ishlaydi (rectangle, gaul)")
# except Exception as e:
#     print(f"❌ ROI builder xato: {e}")

# # Olmedo koeffitsientlar yig'indisi ≈ 1.0 bo'lishi kerak
# olmedo_sum = sum(cfg.OLMEDO_COEFFICIENTS.values())
# print(f"   Olmedo koeffitsientlar yig'indisi: {olmedo_sum:.3f} (≈1.0 bo'lishi kerak)")


# # ==============================================================
# # TEST 2: Preprocessing
# # ==============================================================
# print("\n" + "="*60)
# print("TEST 2: Preprocessing")
# print("="*60)

# try:
#     collection = preprocessing.build_collection(
#         roi=TEST_ROI,
#         date_start=TEST_DATE_START,
#         date_end=TEST_DATE_END,
#         satellite=TEST_SATELLITE,
#         cloud_max=20
#     )
#     info = preprocessing.collection_info(collection)
#     print(f"✅ Collection qurildi: {info['image_count']} tasvir")
#     print(f"   Sanalar: {info['dates']}")

#     if info['image_count'] == 0:
#         print("⚠️  Tasvir topilmadi — sanani yoki ROI ni o'zgartiring")
#         print("   Test to'xtatildi.")
#         sys.exit(1)

#     # Birinchi tasvirni olish
#     first = ee.Image(collection.first())
#     bands = first.bandNames().getInfo()
#     print(f"   Bandlar soni: {len(bands)}")

#     # Kerakli bandlarni tekshirish
#     required = ['SR_B2', 'SR_B4', 'SR_B5', 'LST', 'DEM', 'SLOPE',
#                 'WIND_SPEED_10M', 'AIR_TEMP', 'RHO_AIR']
#     missing = [b for b in required if b not in bands]
#     if missing:
#         print(f"❌ Yo'q bandlar: {missing}")
#     else:
#         print(f"✅ Barcha kerakli bandlar mavjud")

#     # LST qiymatini tekshirish (280-340K oraliq bo'lishi kerak)
#     lst_sample = (first.select('LST')
#                   .reduceRegion(ee.Reducer.mean(), TEST_ROI, 300)
#                   .get('LST'))
#     lst_val = ee.Number(lst_sample).getInfo()
#     print(f"   LST o'rtacha: {lst_val:.1f} K ({lst_val-273.15:.1f} °C)")

#     if 270 < lst_val < 350:
#         print("✅ LST oqilona diapazonda")
#     else:
#         print(f"❌ LST tashqarida: {lst_val} K — scale factor xato?")

# except Exception as e:
#     print(f"❌ Preprocessing xato: {e}")
#     import traceback
#     traceback.print_exc()
#     sys.exit(1)


# # ==============================================================
# # TEST 3: Surface Properties
# # ==============================================================
# print("\n" + "="*60)
# print("TEST 3: Surface Properties")
# print("="*60)

# try:
#     first_sp = surface_props.compute_all(first)
#     sp_bands = first_sp.bandNames().getInfo()

#     new_bands = ['NDVI', 'SAVI', 'ALBEDO', 'EMISSIVITY', 'Z0M', 'Z0H',
#                  'TAU_SW', 'LAI']
#     missing = [b for b in new_bands if b not in sp_bands]
#     if missing:
#         print(f"❌ Yo'q bandlar: {missing}")
#     else:
#         print(f"✅ Barcha surface property bandlar yaratildi")

#     # Qiymatlarni tekshirish
#     stats = (first_sp.select(new_bands)
#              .reduceRegion(ee.Reducer.mean(), TEST_ROI, 300)
#              .getInfo())

#     for band, val in stats.items():
#         if val is not None:
#             print(f"   {band}: {val:.4f}")
#         else:
#             print(f"   {band}: None ❌")

#     # NDVI oralig'i: -1 — 1
#     ndvi_val = stats.get('NDVI', 0)
#     if -1 <= ndvi_val <= 1:
#         print("✅ NDVI oqilona")
#     else:
#         print(f"❌ NDVI tashqarida: {ndvi_val}")

#     # Albedo oralig'i: 0 — 0.5 (odatiy yer yuzasi)
#     alb_val = stats.get('ALBEDO', 0)
#     if 0.05 <= alb_val <= 0.50:
#         print("✅ Albedo oqilona")
#     else:
#         print(f"❌ Albedo tashqarida: {alb_val}")

# except Exception as e:
#     print(f"❌ Surface props xato: {e}")
#     import traceback
#     traceback.print_exc()


# # ==============================================================
# # TEST 4: Radiation (Q*, G₀)
# # ==============================================================
# print("\n" + "="*60)
# print("TEST 4: Radiation")
# print("="*60)

# try:
#     first_rad = radiation.compute_all(first_sp)
#     rad_bands = ['K_DOWN', 'L_DOWN', 'L_UP', 'RN', 'G0', 'RN_G0']

#     stats = (first_rad.select(rad_bands)
#              .reduceRegion(ee.Reducer.mean(), TEST_ROI, 300)
#              .getInfo())

#     for band, val in stats.items():
#         if val is not None:
#             print(f"   {band}: {val:.1f} W/m²")
#         else:
#             print(f"   {band}: None ❌")

#     # Q* odatda 400-800 W/m² (kunduzi, yozda)
#     rn_val = stats.get('RN', 0)
#     if 200 < rn_val < 900:
#         print("✅ Q* oqilona diapazonda")
#     else:
#         print(f"⚠️  Q* kutilganidan farq: {rn_val} W/m²")

#     # G₀ odatda 30-150 W/m²
#     g0_val = stats.get('G0', 0)
#     if 10 < g0_val < 200:
#         print("✅ G₀ oqilona diapazonda")
#     else:
#         print(f"⚠️  G₀ kutilganidan farq: {g0_val} W/m²")

#     # G₀/Q* nisbati: 0.05 — 0.40
#     if rn_val > 0:
#         g_ratio = g0_val / rn_val
#         print(f"   G₀/Q* nisbati: {g_ratio:.3f} (0.05-0.40 oqilona)")

# except Exception as e:
#     print(f"❌ Radiation xato: {e}")
#     import traceback
#     traceback.print_exc()


# # ==============================================================
# # TEST 5: Energy Balance (anchor + H + λE)
# # ==============================================================
# print("\n" + "="*60)
# print("TEST 5: Energy Balance")
# print("="*60)

# try:
#     first_eb = energy_balance.compute_all(first_rad, TEST_ROI)
#     eb_bands = ['H', 'LAMBDA_E', 'ETrF', 'EVAP_FRAC', 'DTA', 'USTAR']

#     stats = (first_eb.select(eb_bands)
#              .reduceRegion(ee.Reducer.mean(), TEST_ROI, 300)
#              .getInfo())

#     for band, val in stats.items():
#         if val is not None:
#             print(f"   {band}: {val:.2f}")
#         else:
#             print(f"   {band}: None ❌")

#     # H odatda 50-300 W/m² (kunduzi)
#     h_val = stats.get('H', 0)
#     le_val = stats.get('LAMBDA_E', 0)
#     print(f"\n   Energiya balansi tekshiruvi:")
#     print(f"   Q*={rn_val:.0f}, G₀={g0_val:.0f}, H={h_val:.0f}, λE={le_val:.0f}")
#     residual = rn_val - g0_val - h_val - le_val
#     print(f"   Residual (0 bo'lishi kerak): {residual:.1f} W/m²")

#     # Λ oralig'i: 0 — 1
#     ef_val = stats.get('EVAP_FRAC', 0)
#     if 0 <= ef_val <= 1:
#         print(f"✅ Λ = {ef_val:.3f} (oqilona)")
#     else:
#         print(f"❌ Λ tashqarida: {ef_val}")

# except Exception as e:
#     print(f"❌ Energy balance xato: {e}")
#     import traceback
#     traceback.print_exc()


# # ==============================================================
# # TEST 6: Daily ET
# # ==============================================================
# print("\n" + "="*60)
# print("TEST 6: Daily ET")
# print("="*60)

# try:
#     first_et = daily_et.compute_daily_et(first_eb, TEST_ROI)

#     et_stats = (first_et.select(['ET_24', 'RN24'])
#                 .reduceRegion(ee.Reducer.mean(), TEST_ROI, 300)
#                 .getInfo())

#     et_val = et_stats.get('ET_24', 0)
#     rn24_val = et_stats.get('RN24', 0)

#     print(f"   Rn24: {rn24_val:.1f} W/m²")
#     print(f"   ET₂₄: {et_val:.2f} mm/day")

#     # Idaho yozda irrigatsiya bilan ET: 4-8 mm/day
#     # Quruq yer: 0.5-2 mm/day
#     # O'rtacha: 2-5 mm/day
#     if 0 < et_val < 15:
#         print(f"✅ ET₂₄ oqilona diapazonda")
#     else:
#         print(f"⚠️  ET₂₄ kutilganidan farq: {et_val} mm/day")

# except Exception as e:
#     print(f"❌ Daily ET xato: {e}")
#     import traceback
#     traceback.print_exc()


# # ==============================================================
# # YAKUNIY XULOSA
# # ==============================================================
# print("\n" + "="*60)
# print("YAKUNIY XULOSA")
# print("="*60)
# print(f"""
# Pipeline natijasi (birinchi sahna):
#   LST:     {lst_val:.1f} K ({lst_val-273.15:.1f} °C)
#   NDVI:    {stats.get('NDVI', ndvi_val):.3f}
#   Albedo:  {alb_val:.3f}
#   Q*:      {rn_val:.0f} W/m²
#   G₀:      {g0_val:.0f} W/m²
#   H:       {h_val:.0f} W/m²
#   λE:      {le_val:.0f} W/m²
#   Λ:       {ef_val:.3f}
#   ET₂₄:   {et_val:.2f} mm/day

# Energiya balansi: Q*-G₀-H-λE = {residual:.1f} W/m²
# """)

# print("Agar barcha qiymatlar oqilona bo'lsa — pipeline ishlaydi! 🎉")
# print("Keyingi qadam: main.run() bilan to'liq export.")



"""
SEBAL-GEE v4 — Test Script
============================
Har bir modulni ketma-ket sinab ko'rish.

Ishlatish:
  1. Google Colab da yoki lokal Python da
  2. ee.Authenticate() va ee.Initialize() qilish
  3. Bu skriptni ishga tushirish

Har qadam natijasini tekshiramiz — xatolik bo'lsa to'xtaymiz.
"""

import ee

# ---- GEE INIT ----
# Colab da: ee.Authenticate() kerak bo'lishi mumkin

GEE_PROJECT = "ee-chexovant11" 

try:
    ee.Initialize(project=GEE_PROJECT)
    print("✅ GEE initialized")
except Exception as e:
    print(f"❌ GEE init xato: {e}")
    print("   ee.Authenticate() qiling avval")
    raise

# ---- IMPORT ----
import sys
sys.path.insert(0, '.')  # agar sebal_gee_v4/ joriy papkada bo'lsa

from sebal_gee_v4 import config as cfg
from sebal_gee_v4 import preprocessing
from sebal_gee_v4 import surface_props
from sebal_gee_v4 import radiation
from sebal_gee_v4 import energy_balance
from sebal_gee_v4 import daily_et

print("✅ Barcha modullar import qilindi")

# ==============================================================
# TEST PARAMETRLARI — kichik hudud, bitta oy
# ==============================================================

# Idaho — kichik test hudud (Twin Falls atrofi)
# TEST_ROI = ee.Geometry.Rectangle([-114.5, 42.5, -114.2, 42.7])
TEST_ROI = ee.Geometry.Rectangle([-114.24, 43.03, -114.14, 43.13])


TEST_DATE_START = '2024-07-01'
TEST_DATE_END = '2024-07-31'
TEST_SATELLITE = 'BOTH'

print("\nTest hudud: Twin Falls, Idaho")
print(f"Sana: {TEST_DATE_START} → {TEST_DATE_END}")
print(f"Satellite: {TEST_SATELLITE}")


# ==============================================================
# TEST 1: Config
# ==============================================================
print("\n" + "="*60)
print("TEST 1: Config")
print("="*60)

# ROI builder test
try:
    roi_rect = cfg.build_roi('rectangle', bounds=[-114.5, 42.5, -114.2, 42.7])
    roi_gaul = cfg.build_roi('gaul', name='Idaho', level=1)
    print("✅ ROI builder ishlaydi (rectangle, gaul)")
except Exception as e:
    print(f"❌ ROI builder xato: {e}")

# Olmedo koeffitsientlar yig'indisi ≈ 1.0 bo'lishi kerak
olmedo_sum = sum(cfg.OLMEDO_COEFFICIENTS.values())
print(f"   Olmedo koeffitsientlar yig'indisi: {olmedo_sum:.3f} (≈1.0 bo'lishi kerak)")


# ==============================================================
# TEST 2: Preprocessing
# ==============================================================
print("\n" + "="*60)
print("TEST 2: Preprocessing")
print("="*60)

try:
    collection = preprocessing.build_collection(
        roi=TEST_ROI,
        date_start=TEST_DATE_START,
        date_end=TEST_DATE_END,
        satellite=TEST_SATELLITE,
        cloud_max=20
    )
    info = preprocessing.collection_info(collection)
    print(f"✅ Collection qurildi: {info['image_count']} tasvir")
    print(f"   Sanalar: {info['dates']}")

    if info['image_count'] == 0:
        print("⚠️  Tasvir topilmadi — sanani yoki ROI ni o'zgartiring")
        print("   Test to'xtatildi.")
        sys.exit(1)

    # Birinchi tasvirni olish
    first = ee.Image(collection.first())
    bands = first.bandNames().getInfo()
    print(f"   Bandlar soni: {len(bands)}")

    # ERA5 vaqt tekshiruvi — oldingi bug shu yerda edi
    img_time = ee.Date(first.get('system:time_start')).format('YYYY-MM-dd HH:mm').getInfo()
    print(f"   Landsat overpass UTC: {img_time}")

    # SSRD qiymatini tekshirish (ERA5 K↓ xom qiymati)
    ssrd_val = (first.select('SSRD')
                .reduceRegion(ee.Reducer.mean(), TEST_ROI, 1000)
                .get('SSRD'))
    ssrd_val = ee.Number(ssrd_val).getInfo()
    ssrd_wm2 = ssrd_val / 3600.0 if ssrd_val else 0
    print(f"   ERA5 SSRD: {ssrd_val:.0f} J/m² = {ssrd_wm2:.0f} W/m²")
    if ssrd_wm2 < 100:
        print(f"   ⚠️  SSRD juda past! ERA5 vaqt noto'g'ri bo'lishi mumkin")
    else:
        print(f"   ✅ SSRD oqilona (kunduzi)")

    # Kerakli bandlarni tekshirish
    required = ['SR_B2', 'SR_B4', 'SR_B5', 'LST', 'DEM', 'SLOPE',
                'WIND_SPEED_10M', 'AIR_TEMP', 'RHO_AIR']
    missing = [b for b in required if b not in bands]
    if missing:
        print(f"❌ Yo'q bandlar: {missing}")
    else:
        print(f"✅ Barcha kerakli bandlar mavjud")

    # LST qiymatini tekshirish (280-340K oraliq bo'lishi kerak)
    lst_sample = (first.select('LST')
                  .reduceRegion(ee.Reducer.mean(), TEST_ROI, 300)
                  .get('LST'))
    lst_val = ee.Number(lst_sample).getInfo()
    print(f"   LST o'rtacha: {lst_val:.1f} K ({lst_val-273.15:.1f} °C)")

    if 270 < lst_val < 350:
        print("✅ LST oqilona diapazonda")
    else:
        print(f"❌ LST tashqarida: {lst_val} K — scale factor xato?")
        
    # WRS path/row tekshiruvi
    print("\n   Har tasvir tafsilotlari:")
    img_list_check = collection.toList(10)
    for i in range(min(info['image_count'], 10)):
        im = ee.Image(img_list_check.get(i))
        props = im.toDictionary([
            'system:time_start', 'SPACECRAFT_ID',
            'WRS_PATH', 'WRS_ROW', 'CLOUD_COVER'
        ]).getInfo()
        d = ee.Date(props['system:time_start']).format('YYYY-MM-dd').getInfo()
        sat = props.get('SPACECRAFT_ID', '?')
        path = props.get('WRS_PATH', '?')
        row = props.get('WRS_ROW', '?')
        cloud = props.get('CLOUD_COVER', '?')
        print(f"   {i+1}. {d} | {sat} | Path:{path} Row:{row} | Cloud:{cloud}%")

except Exception as e:
    print(f"❌ Preprocessing xato: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
    



# ==============================================================
# TEST 3: Surface Properties
# ==============================================================
print("\n" + "="*60)
print("TEST 3: Surface Properties")
print("="*60)

try:
    first_sp = surface_props.compute_all(first)
    sp_bands = first_sp.bandNames().getInfo()

    new_bands = ['NDVI', 'SAVI', 'ALBEDO', 'EMISSIVITY', 'Z0M', 'Z0H',
                 'TAU_SW', 'LAI']
    missing = [b for b in new_bands if b not in sp_bands]
    if missing:
        print(f"❌ Yo'q bandlar: {missing}")
    else:
        print(f"✅ Barcha surface property bandlar yaratildi")

    # Qiymatlarni tekshirish
    stats = (first_sp.select(new_bands)
             .reduceRegion(ee.Reducer.mean(), TEST_ROI, 300)
             .getInfo())

    for band, val in stats.items():
        if val is not None:
            print(f"   {band}: {val:.4f}")
        else:
            print(f"   {band}: None ❌")

    # NDVI oralig'i: -1 — 1
    ndvi_val = stats.get('NDVI', 0)
    if -1 <= ndvi_val <= 1:
        print("✅ NDVI oqilona")
    else:
        print(f"❌ NDVI tashqarida: {ndvi_val}")

    # Albedo oralig'i: 0 — 0.5 (odatiy yer yuzasi)
    alb_val = stats.get('ALBEDO', 0)
    if 0.05 <= alb_val <= 0.50:
        print("✅ Albedo oqilona")
    else:
        print(f"❌ Albedo tashqarida: {alb_val}")

except Exception as e:
    print(f"❌ Surface props xato: {e}")
    import traceback
    traceback.print_exc()


# ==============================================================
# TEST 4: Radiation (Q*, G₀)
# ==============================================================
print("\n" + "="*60)
print("TEST 4: Radiation")
print("="*60)

try:
    first_rad = radiation.compute_all(first_sp)
    rad_bands = ['K_DOWN', 'L_DOWN', 'L_UP', 'RN', 'G0', 'RN_G0']

    stats = (first_rad.select(rad_bands)
             .reduceRegion(ee.Reducer.mean(), TEST_ROI, 300)
             .getInfo())

    for band, val in stats.items():
        if val is not None:
            print(f"   {band}: {val:.1f} W/m²")
        else:
            print(f"   {band}: None ❌")

    # Q* odatda 400-800 W/m² (kunduzi, yozda)
    rn_val = stats.get('RN', 0)
    if 200 < rn_val < 900:
        print("✅ Q* oqilona diapazonda")
    else:
        print(f"⚠️  Q* kutilganidan farq: {rn_val} W/m²")

    # G₀ odatda 30-150 W/m²
    g0_val = stats.get('G0', 0)
    if 10 < g0_val < 200:
        print("✅ G₀ oqilona diapazonda")
    else:
        print(f"⚠️  G₀ kutilganidan farq: {g0_val} W/m²")

    # G₀/Q* nisbati: 0.05 — 0.40
    if rn_val > 0:
        g_ratio = g0_val / rn_val
        print(f"   G₀/Q* nisbati: {g_ratio:.3f} (0.05-0.40 oqilona)")

except Exception as e:
    print(f"❌ Radiation xato: {e}")
    import traceback
    traceback.print_exc()


# ==============================================================
# TEST 5: Energy Balance (anchor + H + λE)
# ==============================================================
print("\n" + "="*60)
print("TEST 5: Energy Balance")
print("="*60)

try:
    first_eb = energy_balance.compute_all(first_rad, TEST_ROI)
    eb_bands = ['H', 'LAMBDA_E', 'ETrF', 'EVAP_FRAC', 'DTA', 'USTAR']

    stats = (first_eb.select(eb_bands)
             .reduceRegion(ee.Reducer.mean(), TEST_ROI, 300)
             .getInfo())

    for band, val in stats.items():
        if val is not None:
            print(f"   {band}: {val:.2f}")
        else:
            print(f"   {band}: None ❌")

    # H odatda 50-300 W/m² (kunduzi)
    h_val = stats.get('H', 0)
    le_val = stats.get('LAMBDA_E', 0)
    print(f"\n   Energiya balansi tekshiruvi:")
    print(f"   Q*={rn_val:.0f}, G₀={g0_val:.0f}, H={h_val:.0f}, λE={le_val:.0f}")
    residual = rn_val - g0_val - h_val - le_val
    print(f"   Residual (0 bo'lishi kerak): {residual:.1f} W/m²")

    # Λ oralig'i: 0 — 1
    ef_val = stats.get('EVAP_FRAC', 0)
    if 0 <= ef_val <= 1:
        print(f"✅ Λ = {ef_val:.3f} (oqilona)")
    else:
        print(f"❌ Λ tashqarida: {ef_val}")

except Exception as e:
    print(f"❌ Energy balance xato: {e}")
    import traceback
    traceback.print_exc()


# ==============================================================
# TEST 6: Daily ET
# ==============================================================
print("\n" + "="*60)
print("TEST 6: Daily ET")
print("="*60)

try:
    
        # Anchor pixel debug
    from sebal_gee_v4 import energy_balance as eb
    first_rad_wind = eb.compute_friction_velocity(first_rad)
    first_rad_wind = eb.compute_rah_neutral(first_rad_wind)
    anchors = eb.select_anchor_pixels(first_rad_wind, TEST_ROI)

    cold_lst_val = anchors['cold_lst'].getInfo()
    hot_lst_val = anchors['hot_lst'].getInfo()
    hot_rng0_val = anchors['hot_rn_g0'].getInfo()
    print(f"   ANCHOR Cold LST: {cold_lst_val:.1f} K ({cold_lst_val-273.15:.1f} °C)")
    print(f"   ANCHOR Hot LST:  {hot_lst_val:.1f} K ({hot_lst_val-273.15:.1f} °C)")
    print(f"   ANCHOR Hot (Q*-G₀): {hot_rng0_val:.1f} W/m²")
    print(f"   ANCHOR dT range: {hot_lst_val-cold_lst_val:.1f} K")
    if hot_lst_val - cold_lst_val < 5:
        print("   ⚠️  Cold-Hot farq juda kichik! Anchor sifati past")
    elif hot_lst_val - cold_lst_val > 40:
        print("   ⚠️  Cold-Hot farq juda katta! Tekshiring")
    else:
        print("   ✅ Anchor farqi oqilona")
    
    first_et = daily_et.compute_daily_et(first_eb, TEST_ROI)

    et_stats = (first_et.select(['ET_24', 'RN24', 'ET_INST_MM_HR'])
                .reduceRegion(ee.Reducer.mean(), TEST_ROI, 300)
                .getInfo())

    et_val = et_stats.get('ET_24', 0)
    rn24_val = et_stats.get('RN24', 0)
    et_inst = et_stats.get('ET_INST_MM_HR', 0)

    print(f"   Rn24: {rn24_val:.1f} W/m²")
    print(f"   ET lahzali: {et_inst:.3f} mm/soat")
    print(f"   ET₂₄: {et_val:.2f} mm/day")

    # Idaho yozda irrigatsiya bilan ET: 4-8 mm/day
    # Quruq yer: 0.5-2 mm/day
    # O'rtacha: 2-5 mm/day
    if 0 < et_val < 15:
        print(f"✅ ET₂₄ oqilona diapazonda")
    else:
        print(f"⚠️  ET₂₄ kutilganidan farq: {et_val} mm/day")

except Exception as e:
    print(f"❌ Daily ET xato: {e}")
    import traceback
    traceback.print_exc()
    
# # ==============================================================
# # TEST 7: Drive ga export (bitta sahna)
# # ==============================================================
# print("\n" + "="*60)
# print("TEST 7: Drive ga export")
# print("="*60)

# try:
#     export_bands = first_et.select([
#         'ET_24', 'ETrF', 'LAMBDA_E', 'H', 'RN', 'G0', 'NDVI', 'LST'
#     ])

#     task = ee.batch.Export.image.toDrive(
#         image=export_bands.toFloat(),
#         description='SEBAL_monthly_Idaho_2024-07',
#         folder='SEBAL_Output',
#         fileNamePrefix='SEBAL_monthly_Idaho_2024-07',
#         region=TEST_ROI,
#         scale=30,
#         crs='EPSG:32611',
#         maxPixels=1e13,
#         fileFormat='GeoTIFF'
#     )
#     task.start()
#     print(f"✅ Export ishga tushdi!")
#     print(f"   Task ID: {task.id}")
#     print(f"   Folder: Google Drive → SEBAL_Output")
#     print(f"   File: SEBAL_monthly_Idaho_2024-07.tif")
#     print(f"   Bandlar: ET_24, ETrF, LAMBDA_E, H, RN, G0, NDVI, LST")
#     print(f"   GEE Tasks: https://code.earthengine.google.com/tasks")
# except Exception as e:
#     print(f"❌ Export xato: {e}")
#     import traceback
#     traceback.print_exc()
    

    
# # ==============================================================
# # TEST 8: OpenET Validatsiya
# # ==============================================================
print("\n" + "="*60)
print("TEST 8: OpenET Validatsiya")
print("="*60)

try:
    from sebal_gee_v4 import validation

    # SEBAL natijamiz (bitta sana — iyul 2024)
    # OpenET oylik beradi, shuning uchun oylik o'rtacha bilan solishtiramiz
    val_results = validation.validate(
        sebal_image=first_et,
        roi=TEST_ROI,
        year=2024,
        month=7,
        n_points=2000
    )

    # Scatter CSV export
    if val_results:
        openet = validation.get_openet_daily_mean(TEST_ROI, 2024, 7)
        sampled = validation.sample_points(first_et, openet, TEST_ROI, 2000)
        validation.export_scatter_csv(sampled, TEST_ROI)

except Exception as e:
    print(f"❌ Validatsiya xato: {e}")
    import traceback
    traceback.print_exc()

# ==============================================================
# TEST 8: Oylik ET hisoblash + OpenET Validatsiya
# ==============================================================
print("\n" + "="*60)
print("TEST 8: Oylik ET + OpenET Validatsiya")
print("="*60)

try:
    from sebal_gee_v4 import validation

    # ---- 1. BARCHA tasvirlarni ishlab chiqish ----
    print("[Monthly] Barcha sahnalarni SEBAL orqali ishlamoqda...")

    all_collection = collection.map(surface_props.compute_all)
    all_collection = all_collection.map(radiation.compute_all)

    image_list_ee = all_collection.toList(all_collection.size())
    n_total = info['image_count']

    processed_all = []
    for i in range(n_total):
        print(f"  → Sahna {i+1}/{n_total}...")
        img = ee.Image(image_list_ee.get(i))
        img = energy_balance.compute_all(img, TEST_ROI)
        img = daily_et.compute_daily_et(img, TEST_ROI)
        processed_all.append(img)

    print(f"✅ {n_total} ta sahna ishlandi")

    # ---- 2. Oylik ET hisoblash (Λ interpolyatsiya) ----
    print("[Monthly] Iyul 2024 oylik ET hisoblanmoqda...")
    et_monthly = daily_et.compute_monthly_et(
        image_list=processed_all,
        roi=TEST_ROI,
        year=2024,
        month=7
    )

    # O'rtacha qiymatni tekshirish
    monthly_mean = (et_monthly
                    .reduceRegion(ee.Reducer.mean(), TEST_ROI, 300)
                    .get('ET_MONTHLY'))
    monthly_mean_val = ee.Number(monthly_mean).getInfo()
    daily_equiv = monthly_mean_val / 31.0
    print(f"   ET oylik o'rtacha: {monthly_mean_val:.1f} mm/month")
    print(f"   Kunlik ekvivalent: {daily_equiv:.2f} mm/day")

    # ---- 3. OpenET oylik olish (mm/month — xom qiymat) ----
    print("[Monthly] OpenET yuklanmoqda...")
    openet_monthly = validation.get_openet_monthly(TEST_ROI, 2024, 7)
    openet_bands = openet_monthly.bandNames().getInfo()
    print(f"   OpenET modellar: {openet_bands}")

    # ---- 4. Sampling va statistika ----
    print("[Monthly] Random sampling (2000 nuqta)...")

    # Ikkalasi ham mm/month — to'g'ri solishtirish!
    combined = (et_monthly.rename('ET_SEBAL')
                .addBands(openet_monthly))

    points = ee.FeatureCollection.randomPoints(
        region=TEST_ROI, points=2000, seed=42)

    sampled = combined.sampleRegions(
        collection=points, scale=30, geometries=True)

    sampled = sampled.filter(ee.Filter.notNull(['ET_SEBAL']))
    actual_n = sampled.size().getInfo()
    print(f"   Valid nuqtalar: {actual_n}")

    # ---- 5. Har model uchun statistika ----
    print("\n" + "="*70)
    print(f"  OYLIK VALIDATSIYA: SEBAL vs OpenET (mm/month, Iyul 2024)")
    print("="*70)
    print(f"{'Model':<12} {'R²':>6} {'RMSE':>8} {'NSE':>8} "
          f"{'MBE':>8} {'MAE':>8} {'SEBAL':>8} {'OpenET':>8}")
    print("-"*70)

    for band_name in openet_bands:
        model_name = band_name.replace('ET_', '')
        try:
            stats = validation.compute_statistics(
                sampled, 'ET_SEBAL', band_name)
            si = {k: v.getInfo() if hasattr(v, 'getInfo') else v
                  for k, v in stats.items()}

            print(f"{model_name:<12} "
                  f"{si['r2']:>6.3f} "
                  f"{si['rmse']:>8.2f} "
                  f"{si['nse']:>8.3f} "
                  f"{si['mbe']:>8.2f} "
                  f"{si['mae']:>8.2f} "
                  f"{si['mean_sebal']:>8.1f} "
                  f"{si['mean_openet']:>8.1f}")
        except Exception as e:
            print(f"{model_name:<12} ❌ {e}")

    print("="*70)

    # ---- 6. Oylik natijani Drive ga export ----
    task = ee.batch.Export.image.toDrive(
        image=et_monthly.toFloat(),
        description='SEBAL_monthly_Idaho_2024-07',
        folder='SEBAL_Output',
        fileNamePrefix='ET_monthly_2024-07',
        region=TEST_ROI, scale=30,
        crs='EPSG:32611', maxPixels=1e13)
    task.start()
    print(f"\n✅ Oylik ET export: ET_monthly_2024-07.tif")

except Exception as e:
    print(f"❌ Oylik validatsiya xato: {e}")
    import traceback
    traceback.print_exc()
    
# ==============================================================
# TEST 9: PySEBAL mode — qo'shimcha analitikalar
# ==============================================================
print("\n" + "="*60)
print("TEST 9: PySEBAL qo'shimcha analitikalar")
print("="*60)

try:
    from sebal_gee_v4 import et_decomposition
    from sebal_gee_v4 import soil_moisture
    from sebal_gee_v4 import biomass
    from sebal_gee_v4 import irrigation

    # Oldingi SEBAL natijasi (first_et) ustiga qo'shamiz
    print("[PySEBAL] ET decomposition...")
    result = et_decomposition.compute_all(first_et)

    print("[PySEBAL] Soil moisture...")
    result = soil_moisture.compute_all(result)

    print("[PySEBAL] Biomass & water productivity...")
    result = biomass.compute_all(result)

    print("[PySEBAL] Irrigation classification...")
    result = irrigation.compute_all(result)

    # Natijalarni tekshirish
    pysebal_bands = [
        'ETREF_24', 'ETPOT_24', 'KC', 'KC_MAX', 'ET_DEFICIT',
        'TACT_24', 'EACT_24', 'BENEFICIAL_FRACTION',
        'TOP_SOIL_MOISTURE', 'ROOT_ZONE_MOISTURE',
        'FPAR', 'APAR', 'LUE', 'BIOMASS_PROD', 'WATER_PRODUCTIVITY',
        'IRRIGATION_CLASS', 'IRRIGATION_DEPTH'
    ]

    stats = (result.select(pysebal_bands)
             .reduceRegion(ee.Reducer.mean(), TEST_ROI, 300)
             .getInfo())

    print(f"\n{'='*50}")
    print(f"  PySEBAL NATIJALAR")
    print(f"{'='*50}")
    print(f"  --- ET Decomposition ---")
    print(f"  ETref:       {stats.get('ETREF_24', 0):.2f} mm/day")
    print(f"  ETpot:       {stats.get('ETPOT_24', 0):.2f} mm/day")
    print(f"  ETact:       {et_val:.2f} mm/day")
    print(f"  ET deficit:  {stats.get('ET_DEFICIT', 0):.2f} mm/day")
    print(f"  kc:          {stats.get('KC', 0):.3f}")
    print(f"  kc_max:      {stats.get('KC_MAX', 0):.3f}")
    print(f"  --- E/T Separation ---")
    print(f"  Tact:        {stats.get('TACT_24', 0):.2f} mm/day")
    print(f"  Eact:        {stats.get('EACT_24', 0):.2f} mm/day")
    print(f"  Beneficial:  {stats.get('BENEFICIAL_FRACTION', 0):.2f}")
    print(f"  --- Soil Moisture ---")
    print(f"  Top SM:      {stats.get('TOP_SOIL_MOISTURE', 0):.3f} m³/m³")
    print(f"  Root SM:     {stats.get('ROOT_ZONE_MOISTURE', 0):.3f} m³/m³")
    print(f"  --- Biomass ---")
    print(f"  FPAR:        {stats.get('FPAR', 0):.3f}")
    print(f"  LUE:         {stats.get('LUE', 0):.3f} gC/MJ")
    print(f"  Biomass:     {stats.get('BIOMASS_PROD', 0):.1f} kg/ha/day")
    print(f"  Water prod:  {stats.get('WATER_PRODUCTIVITY', 0):.2f} kg/m³")
    print(f"  --- Irrigation ---")
    print(f"  Class o'rt:  {stats.get('IRRIGATION_CLASS', 0):.2f} (0-3)")
    print(f"  Depth:       {stats.get('IRRIGATION_DEPTH', 0):.1f} mm")
    print(f"{'='*50}")

    # Bandlar soni
    all_bands = result.bandNames().getInfo()
    print(f"\n  Jami bandlar: {len(all_bands)}")

    # Drive ga export
    export_bands = result.select(pysebal_bands + ['ET_24', 'NDVI', 'LST'])
    task = ee.batch.Export.image.toDrive(
        image=export_bands.toFloat(),
        description='SEBAL_pysebal_Idaho_2024-07-07',
        folder='SEBAL_Output',
        fileNamePrefix='SEBAL_pysebal_test',
        region=TEST_ROI, scale=30,
        crs='EPSG:32611', maxPixels=1e13)
    task.start()
    print(f"\n✅ PySEBAL export: SEBAL_pysebal_test.tif ({len(pysebal_bands)+3} band)")

except Exception as e:
    print(f"❌ PySEBAL xato: {e}")
    import traceback
    traceback.print_exc()

# ==============================================================
# DIAG: Λ interpolyatsiya diagnostikasi
# ==============================================================
print("\n" + "="*60)
print("DIAG: Extrapolation diagnostikasi")
print("="*60)

# 1. Har sahnaning Λ qiymati
print("\nHar sahna uchun Λ:")
for i, img in enumerate(processed_all):
    d = ee.Date(img.get('system:time_start')).format('YYYY-MM-dd').getInfo()
    lam = (img.select('EVAP_FRAC')
           .reduceRegion(ee.Reducer.mean(), TEST_ROI, 300)
           .get('EVAP_FRAC'))
    lam_val = ee.Number(lam).getInfo()
    print(f"  Sahna {i+1}: {d} → Λ = {lam_val:.3f}")

# 2. Sodda usul: o'rtacha Λ × o'rtacha Rn24 × 31 kun
mean_lambda = ee.ImageCollection(processed_all).select('EVAP_FRAC').mean()
mean_et24 = ee.ImageCollection(processed_all).select('ET_24').mean()

simple_monthly = mean_et24.multiply(31)
simple_mean = (simple_monthly
               .reduceRegion(ee.Reducer.mean(), TEST_ROI, 300)
               .get('ET_24'))
simple_val = ee.Number(simple_mean).getInfo()

mean_lam_val = (mean_lambda
                .reduceRegion(ee.Reducer.mean(), TEST_ROI, 300)
                .get('EVAP_FRAC'))
mean_lam = ee.Number(mean_lam_val).getInfo()

print(f"\nO'rtacha Λ (barcha sahnalar): {mean_lam:.3f}")
print(f"Sodda usul: o'rtacha ET₂₄ × 31 = {simple_val:.1f} mm/month")
print(f"Interpolyatsiya usuli:          = 95.5 mm/month")
print(f"OpenET ENSEMBLE:                = 122.3 mm/month")

# ==============================================================
# YAKUNIY XULOSA
# ==============================================================
print("\n" + "="*60)
print("YAKUNIY XULOSA")
print("="*60)
print(f"""
Pipeline natijasi (birinchi sahna):
  LST:     {lst_val:.1f} K ({lst_val-273.15:.1f} °C)
  NDVI:    {stats.get('NDVI', ndvi_val):.3f}
  Albedo:  {alb_val:.3f}
  Q*:      {rn_val:.0f} W/m²
  G₀:      {g0_val:.0f} W/m²
  H:       {h_val:.0f} W/m²
  λE:      {le_val:.0f} W/m²
  Λ:       {ef_val:.3f}
  ET₂₄:   {et_val:.2f} mm/day

Energiya balansi: Q*-G₀-H-λE = {residual:.1f} W/m²
""")

print("Agar barcha qiymatlar oqilona bo'lsa — pipeline ishlaydi! 🎉")
print("Keyingi qadam: main.run() bilan to'liq export.")
