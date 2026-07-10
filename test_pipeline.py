"""
SEBAL-GEE v4 — Test Pipeline
==============================
Ishlatish:
  python test_pipeline.py              → mode="maqola" (default)
  python test_pipeline.py pysebal      → mode="pysebal" (qo'shimcha analitikalar)
  python test_pipeline.py all          → ikkalasi ham
  python test_pipeline.py maqola --export  → export bilan
"""

import ee
import sys

# ==============================================================
# CONFIG
# ==============================================================



TEST_DATE_START = '2026-03-01'
TEST_DATE_END = '2026-03-31'
TEST_SATELLITE = 'BOTH'

MODE = sys.argv[1] if len(sys.argv) > 1 else 'maqola'
EXPORT = '--export' in sys.argv
VALIDATE = '--validate' in sys.argv

# ==============================================================
# INIT
# ==============================================================
GEE_PROJECT = "ee-chexovant11" 

try:
    ee.Initialize(project=GEE_PROJECT)
    print("✅ GEE initialized")
except Exception as e:
    print(f"❌ GEE init xato: {e}")
    print("   ee.Authenticate() qiling avval")
    raise

sys.path.insert(0, '.')
from sebal_gee_v4 import config as cfg
from sebal_gee_v4 import preprocessing
from sebal_gee_v4 import surface_props
from sebal_gee_v4 import radiation
from sebal_gee_v4 import energy_balance
from sebal_gee_v4 import daily_et


# TEST_ROI = ee.Geometry.Rectangle([-114.24, 43.03, -114.14, 43.13])

TEST_ROI = cfg.build_roi('gaul', name='Kashkadarya', level=1)

print(f"✅ Mode: {MODE} | Export: {EXPORT}")
print(f"   ROI: Twin Falls, Idaho")
print(f"   Sana: {TEST_DATE_START} → {TEST_DATE_END}")


# ==============================================================
# SEBAL CORE — maqola mode (har doim ishlaydi)
# ==============================================================

def run_core():
    results = {}

    # ---- PREPROCESSING ----
    print("\n" + "="*60)
    print("M1-M2: Preprocessing")
    print("="*60)

    collection = preprocessing.build_collection(
        roi=TEST_ROI, date_start=TEST_DATE_START,
        date_end=TEST_DATE_END, satellite=TEST_SATELLITE, cloud_max=20)

    info = preprocessing.collection_info(collection)
    print(f"   Tasvirlar: {info['image_count']} | Sanalar: {info['dates']}")

    if info['image_count'] == 0:
        print("❌ Tasvir topilmadi!")
        sys.exit(1)

    first = ee.Image(collection.first())

    # WRS tekshiruvi
    img_list_check = collection.toList(10)
    for i in range(min(info['image_count'], 10)):
        im = ee.Image(img_list_check.get(i))
        props = im.toDictionary([
            'system:time_start', 'SPACECRAFT_ID', 'WRS_PATH', 'WRS_ROW'
        ]).getInfo()
        d = ee.Date(props['system:time_start']).format('YYYY-MM-dd HH:mm').getInfo()
        sat = props.get('SPACECRAFT_ID', '?')
        print(f"   {i+1}. {d} | {sat} | P:{props.get('WRS_PATH')} R:{props.get('WRS_ROW')}")

    ssrd_val = ee.Number(first.select('SSRD')
        .reduceRegion(ee.Reducer.mean(), TEST_ROI, 1000).get('SSRD')).getInfo()
    print(f"   SSRD: {ssrd_val/3600:.0f} W/m² {'✅' if ssrd_val/3600 > 100 else '⚠️'}")

    results['lst'] = ee.Number(first.select('LST')
        .reduceRegion(ee.Reducer.mean(), TEST_ROI, 300).get('LST')).getInfo()
    print(f"   LST: {results['lst']:.1f} K ({results['lst']-273.15:.1f}°C)")

    # ---- SURFACE PROPERTIES ----
    print("\n" + "="*60)
    print("M3: Surface Properties")
    print("="*60)

    first = surface_props.compute_all(first)
    sp_stats = (first.select(['NDVI', 'SAVI', 'ALBEDO', 'EMISSIVITY', 'Z0M', 'LAI', 'TAU_SW'])
                .reduceRegion(ee.Reducer.mean(), TEST_ROI, 300).getInfo())
    for k, v in sp_stats.items():
        print(f"   {k}: {v:.4f}" if v else f"   {k}: None ❌")
    results.update(sp_stats)

    # ---- RADIATION ----
    print("\n" + "="*60)
    print("M4: Radiation (Q*, G₀)")
    print("="*60)

    first = radiation.compute_all(first)
    rad_stats = (first.select(['K_DOWN', 'L_DOWN', 'L_UP', 'RN', 'G0', 'RN_G0'])
                 .reduceRegion(ee.Reducer.mean(), TEST_ROI, 300).getInfo())
    for k, v in rad_stats.items():
        print(f"   {k}: {v:.1f} W/m²" if v else f"   {k}: None ❌")
    results.update(rad_stats)
    print(f"   G₀/Q*: {rad_stats['G0']/rad_stats['RN']:.3f}")

    # ---- ENERGY BALANCE ----
    print("\n" + "="*60)
    print("M5-M8: Energy Balance")
    print("="*60)

    # Anchor debug
    from sebal_gee_v4 import energy_balance as eb
    temp = eb.compute_friction_velocity(first)
    temp = eb.compute_rah_neutral(temp)
    anchors = eb.select_anchor_pixels(temp, TEST_ROI)
    cold = anchors['cold_lst'].getInfo()
    hot = anchors['hot_lst'].getInfo()
    print(f"   Cold: {cold:.1f}K ({cold-273.15:.1f}°C) | Hot: {hot:.1f}K ({hot-273.15:.1f}°C) | dT: {hot-cold:.1f}K")

    first = energy_balance.compute_all(first, TEST_ROI)
    eb_stats = (first.select(['H', 'LAMBDA_E', 'EVAP_FRAC', 'DTA', 'USTAR'])
                .reduceRegion(ee.Reducer.mean(), TEST_ROI, 300).getInfo())
    results.update(eb_stats)

    res = rad_stats['RN'] - rad_stats['G0'] - eb_stats['H'] - eb_stats['LAMBDA_E']
    print(f"   H={eb_stats['H']:.1f}  λE={eb_stats['LAMBDA_E']:.1f}  Λ={eb_stats['EVAP_FRAC']:.3f}")
    print(f"   Residual: {res:.1f} W/m² {'✅' if abs(res) < 5 else '⚠️'}")

    # ---- DAILY ET ----
    print("\n" + "="*60)
    print("M9: Daily ET")
    print("="*60)

    first = daily_et.compute_daily_et(first, TEST_ROI)
    et_stats = (first.select(['ET_24', 'RN24', 'ET_INST_MM_HR'])
                .reduceRegion(ee.Reducer.mean(), TEST_ROI, 300).getInfo())
    results.update(et_stats)
    print(f"   Rn24: {et_stats['RN24']:.1f} W/m²")
    print(f"   ET lahzali: {et_stats['ET_INST_MM_HR']:.3f} mm/soat")
    print(f"   ET₂₄: {et_stats['ET_24']:.2f} mm/day")

    # ---- VALIDATION ----
    # ---- VALIDATION ----
    if VALIDATE:
        print("\n" + "="*60)
        print("Validation: SEBAL vs OpenET")
        print("="*60)
        try:
            from sebal_gee_v4 import validation
            validation.validate(sebal_image=first, roi=TEST_ROI,
                            year=2024, month=7, n_points=2000)
        except Exception as e:
            print(f"   ⚠️ {e}")

    # ---- Oylik (to'g'ri interpolyatsiya) ----
    # ---- Oylik (to'g'ri interpolyatsiya) ----
    if EXPORT:
        from sebal_gee_v4 import monthly_analytics
        from sebal_gee_v4 import et_decomposition
        from sebal_gee_v4 import soil_moisture as sm_mod
        from sebal_gee_v4 import biomass as bio_mod
        from sebal_gee_v4 import irrigation as irr_mod

        # Barcha sahnalarni ishlab chiqish
        print("\n  Barcha sahnalarni tayyorlash...")
        all_col = collection.map(surface_props.compute_all).map(radiation.compute_all)
        img_list = all_col.toList(all_col.size())
        n = info['image_count']

        scene_images = []
        for i in range(n):
            print(f"    Sahna {i+1}/{n}...")
            img = ee.Image(img_list.get(i))
            img = energy_balance.compute_all(img, TEST_ROI)
            img = daily_et.compute_daily_et(img, TEST_ROI)
            if MODE in ('pysebal', 'all'):
                img = et_decomposition.compute_all(img)
                img = sm_mod.compute_all(img)
                img = bio_mod.compute_all(img)
                img = irr_mod.compute_all(img)
            scene_images.append(img)

        print("\n  Oylik hisoblash (interpolyatsiya)...")

    return first, results, collection, info


# ==============================================================
# PYSEBAL MODE — qo'shimcha analitikalar
# ==============================================================

def run_pysebal(first_et):
    print("\n" + "="*60)
    print("PySEBAL: Qo'shimcha Analitikalar")
    print("="*60)

    from sebal_gee_v4 import et_decomposition
    from sebal_gee_v4 import soil_moisture
    from sebal_gee_v4 import biomass
    from sebal_gee_v4 import irrigation

    print("   ET decomposition...")
    result = et_decomposition.compute_all(first_et)
    print("   Soil moisture...")
    result = soil_moisture.compute_all(result)
    print("   Biomass...")
    result = biomass.compute_all(result)
    print("   Irrigation...")
    result = irrigation.compute_all(result)

    pysebal_bands = [
        'ETREF_24', 'ETPOT_24', 'KC', 'KC_MAX', 'ET_DEFICIT',
        'TACT_24', 'EACT_24', 'BENEFICIAL_FRACTION',
        'TOP_SOIL_MOISTURE', 'ROOT_ZONE_MOISTURE',
        'FPAR', 'APAR', 'LUE', 'BIOMASS_PROD', 'WATER_PRODUCTIVITY',
        'IRRIGATION_CLASS', 'IRRIGATION_DEPTH'
    ]

    stats = (result.select(pysebal_bands)
             .reduceRegion(ee.Reducer.mean(), TEST_ROI, 300).getInfo())

    print(f"\n{'='*50}")
    print(f"  PySEBAL NATIJALAR")
    print(f"{'='*50}")
    print(f"  ETref:      {stats.get('ETREF_24',0):.2f} mm/day")
    print(f"  ETpot:      {stats.get('ETPOT_24',0):.2f} mm/day")
    print(f"  ET deficit: {stats.get('ET_DEFICIT',0):.2f} mm/day")
    print(f"  kc:         {stats.get('KC',0):.3f}")
    print(f"  kc_max:     {stats.get('KC_MAX',0):.3f}")
    print(f"  Tact:       {stats.get('TACT_24',0):.2f} mm/day")
    print(f"  Eact:       {stats.get('EACT_24',0):.2f} mm/day")
    print(f"  Beneficial: {stats.get('BENEFICIAL_FRACTION',0):.2f}")
    print(f"  Top SM:     {stats.get('TOP_SOIL_MOISTURE',0):.3f} m³/m³")
    print(f"  Root SM:    {stats.get('ROOT_ZONE_MOISTURE',0):.3f} m³/m³")
    print(f"  FPAR:       {stats.get('FPAR',0):.3f}")
    print(f"  LUE:        {stats.get('LUE',0):.3f} gC/MJ")
    print(f"  Biomass:    {stats.get('BIOMASS_PROD',0):.1f} kg/ha/day")
    print(f"  Water prod: {stats.get('WATER_PRODUCTIVITY',0):.2f} kg/m³")
    print(f"  Irrig class:{stats.get('IRRIGATION_CLASS',0):.1f} (0-3)")
    print(f"  Irrig depth:{stats.get('IRRIGATION_DEPTH',0):.1f} mm")
    print(f"{'='*50}")
    print(f"  Jami bandlar: {len(result.bandNames().getInfo())}")

    if EXPORT:
        bands = result.select(pysebal_bands + ['ET_24', 'NDVI', 'LST'])
        task = ee.batch.Export.image.toDrive(
            image=bands.toFloat(), description='SEBAL_pysebal_test',
            folder='SEBAL_Output', fileNamePrefix='SEBAL_pysebal_test',
            region=TEST_ROI, scale=30, crs='EPSG:32642', maxPixels=1e13)   #   EPSG:32611
        task.start()
        print(f"\n✅ Export: {task.id}")
        
    # ---- MODIS GPP Validation ----
    print("\n  --- MODIS GPP bilan solishtirish ---")
    try:
        date = ee.Date('2026-03-15')
        modis_gpp = (ee.ImageCollection('MODIS/061/MOD17A2H')
                     .filterDate(date.advance(-8, 'day'), date.advance(8, 'day'))
                     .filterBounds(TEST_ROI)
                     .first()
                     .select('Gpp'))

        # MODIS: Gpp × 0.0001 = kgC/m²/8kun → gC/m²/kun
        # × 0.0001 / 8 × 1000 = × 0.0125
        modis_daily = modis_gpp.multiply(0.0125).rename('MODIS_GPP')

        # Bizning: Biomass kgDM/ha/kun → gC/m²/kun
        # / 10000(ha→m²) × 1000(kg→g) / 2(DM→C) = × 0.05
        # SEBAL ni 500m ga aggregate qilish — MODIS bilan bir xil scale
        sebal_gpp = (result.select('BIOMASS_PROD').multiply(0.05)
                            .setDefaultProjection(crs='EPSG:4326', scale=30)
                            .reduceResolution(reducer=ee.Reducer.mean(), maxPixels=1024)
                            .reproject(crs=modis_gpp.projection())
                            .rename('SEBAL_GPP'))

        gpp_stats = (modis_daily.addBands(sebal_gpp)
                     .reduceRegion(ee.Reducer.mean(), TEST_ROI, 500)
                     .getInfo())

        modis_val = gpp_stats.get('MODIS_GPP', 0)
        sebal_val = gpp_stats.get('SEBAL_GPP', 0)
        diff_pct = ((sebal_val - modis_val) / modis_val * 100) if modis_val > 0 else 0

        print(f"  MODIS GPP:  {modis_val:.2f} gC/m²/day")
        print(f"  SEBAL GPP:  {sebal_val:.2f} gC/m²/day")
        print(f"  Farq:       {diff_pct:.1f}%")

        # Pixel-by-pixel R²
        combined = modis_daily.addBands(sebal_gpp)
        pts = ee.FeatureCollection.randomPoints(TEST_ROI, 500, seed=42)
        sampled = combined.sampleRegions(collection=pts, scale=1000)  #500m scale, chunki MODIS 500m resolutionda
        sampled = sampled.filter(ee.Filter.notNull(['MODIS_GPP', 'SEBAL_GPP']))

        corr = sampled.reduceColumns(
            ee.Reducer.pearsonsCorrelation(), ['SEBAL_GPP', 'MODIS_GPP'])
        r = ee.Number(corr.get('correlation')).getInfo()
        print(f"  R²:         {r**2:.3f}")

    except Exception as e:
        print(f"  ⚠️ MODIS GPP xato: {e}")

    return result


# ==============================================================
# MAIN
# ==============================================================

if __name__ == '__main__':
    print(f"\n{'='*60}")
    print(f"  SEBAL-GEE v4 | Mode: {MODE}")
    print(f"{'='*60}")

    first_et, results, collection, info = run_core()

    if MODE in ('pysebal', 'all'):
        try:
            run_pysebal(first_et)
        except Exception as e:
            print(f"❌ PySEBAL xato: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'='*60}")
    print(f"  Q*={results.get('RN',0):.0f}  G₀={results.get('G0',0):.0f}  "
          f"H={results.get('H',0):.0f}  λE={results.get('LAMBDA_E',0):.0f}")
    print(f"  Λ={results.get('EVAP_FRAC',0):.3f}  ET₂₄={results.get('ET_24',0):.2f} mm/day")
    print(f"  ✅ Tayyor!")
