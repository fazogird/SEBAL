# -*- coding: utf-8 -*-
"""
LST VARIANTLAR + KO'P-SENSOR — Bushland 2021, 4 lizimetr bitta piksel.
A: Landsat L1/TOA RAW B10 → LST (Tb brightness, Artis-Carnahan emissivitet).
B: Boshqa sensorlar (MODIS MOD11, VIIRS VNP21) shu joyda — lizimetrga bias.
Maqsad: (1) raw B10 dan LST formulalari qanday farq beradi; (2) boshqa sensorlar ham
+5°C warm o'qiydimi (→ nuqta-vs-footprint tasdiqi) yoki Landsat-ga xosmi.
"""
import sys
sys.path.insert(0, r'D:/Cloud_comp/Sebal/scripts')
import ee, pandas as pd, numpy as np
ee.Initialize(project='ee-chexovant11')
OUTDIR = r'D:/ET_2026/lyzimetr/25114670/result/LST_diag'
LYZ = r'D:/ET_2026/lyzimetr/25114670/data/lyz_2021_15min.xlsx'
K1, K2 = 774.8853, 1321.0789
LAM, RHO = 10.895, 14388.0    # µm, µm·K (Artis-Carnahan)
CENTERS = {'NE': [-102.0955385, 35.18816985], 'SE': [-102.0955390, 35.18612583],
           'NW': [-102.0978919, 35.18817119], 'SW': [-102.0979121, 35.18613288]}
pts = ee.FeatureCollection([ee.Feature(ee.Geometry.Point(v), {'nuqta': k}) for k, v in CENTERS.items()])

# lizimetr LST (overpass CST) yordamchi
lz = pd.read_excel(LYZ, sheet_name='Comparison_15min')
lz['sana'] = pd.to_datetime(lz.Year.astype(int).astype(str)+'-'+lz.DOY.astype(int).astype(str),
                            format='%Y-%j').dt.strftime('%Y-%m-%d')
lz['min'] = (lz.Time_hhmm//100)*60 + (lz.Time_hhmm % 100)
def lys_at(sana, nq, omin):
    s2 = lz[(lz.sana==sana)&(lz.Lysimeter==nq)]
    if s2.empty: return None
    return float(s2.iloc[(s2['min']-omin).abs().argmin()]['LST_nadir_C'])

# ---------- A: Landsat L1/TOA RAW ----------
toa = (ee.ImageCollection('LANDSAT/LC08/C02/T1_TOA').filterDate('2021-03-01','2021-11-01')
       .filter(ee.Filter.eq('WRS_PATH',30)).filter(ee.Filter.eq('WRS_ROW',36))
       .filter(ee.Filter.lt('CLOUD_COVER',95)))
ids = toa.aggregate_array('system:index').getInfo()
times = toa.aggregate_array('system:time_start').getInfo()
print(f"  A: {len(ids)} TOA sahna")
rowsA = []
for sid,t in zip(ids,times):
    img = toa.filter(ee.Filter.eq('system:index',sid)).first()
    sana = pd.Timestamp(t,unit='ms').strftime('%Y-%m-%d')
    omin = (pd.Timestamp(t,unit='ms',tz='UTC').hour*60+pd.Timestamp(t,unit='ms',tz='UTC').minute)-360
    ndvi = img.normalizedDifference(['B5','B4']).rename('NDVI')
    Tb = img.select('B10').rename('Tb')                     # TOA brightness temp (K)
    Pv = ndvi.subtract(0.2).divide(0.3).clamp(0,1).pow(2)
    eps = Pv.multiply(0.985).add(ee.Image(1).subtract(Pv).multiply(0.96)).add(Pv.multiply(ee.Image(1).subtract(Pv)).multiply(0.06)).rename('eps')
    # Artis-Carnahan: LST = Tb / (1 + (LAM*Tb/RHO)*ln(eps))
    lst_ac = Tb.divide(Tb.multiply(LAM/RHO).multiply(eps.log()).add(1)).rename('LST_AC')
    samp = img.addBands([ndvi,Tb,eps,lst_ac]).select(['Tb','NDVI','eps','LST_AC']) \
              .reduceRegions(pts, ee.Reducer.first(), 30).getInfo()
    for f in samp['features']:
        p=f['properties']
        rowsA.append(dict(sana=sana, nuqta=p['nuqta'],
            Tb_C=round(p['Tb']-273.15,2) if p.get('Tb') else None,
            LST_AC_C=round(p['LST_AC']-273.15,2) if p.get('LST_AC') else None,
            NDVI=round(p['NDVI'],3) if p.get('NDVI') is not None else None,
            lys=lys_at(sana,p['nuqta'],omin)))
A = pd.DataFrame(rowsA).dropna(subset=['Tb_C','lys'])
A['Tb_bias']=(A.Tb_C-A.lys).round(2); A['AC_bias']=(A.LST_AC_C-A.lys).round(2)

# ---------- B: MODIS + VIIRS ----------
def sensor(coll, band, scale, off, vt_band, vt_scale, vt_off, name, res):
    c = (ee.ImageCollection(coll).filterDate('2021-03-01','2021-11-01').filterBounds(pts.geometry()))
    sids = c.aggregate_array('system:index').getInfo()
    sts = c.aggregate_array('system:time_start').getInfo()
    out=[]
    for sid,t in zip(sids,sts):
        im = c.filter(ee.Filter.eq('system:index',sid)).first()
        sana = pd.Timestamp(t,unit='ms').strftime('%Y-%m-%d')
        bands=[band]+([vt_band] if vt_band else [])
        r = im.select(bands).reduceRegion(ee.Reducer.first(), pts.geometry().centroid(), res, maxPixels=1e9).getInfo()
        v=r.get(band)
        if v is None: continue
        lstK = v*scale+off
        if vt_band and r.get(vt_band) is not None:
            solar_h = r[vt_band]*vt_scale+vt_off
            omin = int(solar_h*60 + 48)     # local solar → CST (Bushland ~+48min)
        else:
            omin = 13*60+30
        # lizimetr (4 nuqta o'rtacha, sensor overpass CST)
        ly=[lys_at(sana,nq,omin) for nq in CENTERS]; ly=[x for x in ly if x is not None]
        out.append(dict(sensor=name, sana=sana, LST_C=round(lstK-273.15,2),
                        ov_CST=f'{omin//60:02d}:{omin%60:02d}',
                        lys=round(np.mean(ly),2) if ly else None))
    return pd.DataFrame(out)

print("  B: MODIS MOD11A1...")
mod = sensor('MODIS/061/MOD11A1','LST_Day_1km',0.02,0,'Day_view_time',0.1,0,'MODIS_Terra',1000)
print("  B: VIIRS VNP21A1D...")
try:
    vii = sensor('NASA/VIIRS/002/VNP21A1D','LST_1KM',1.0,0,None,0,0,'VIIRS',1000)
    if not vii.empty and vii.LST_C.mean()>1000: vii['LST_C']=(vii.LST_C+273.15)*0.02-273.15  # scale fallback
except Exception as e:
    print("   VIIRS xato:",e); vii=pd.DataFrame()
B = pd.concat([mod,vii], ignore_index=True)
B=B.dropna(subset=['lys']); B['bias']=(B.LST_C-B.lys).round(2)

# ---------- Natijalar ----------
pd.set_option('display.width',200)
print("\n  === A: Landsat RAW B10 formulalari (o'rt bias, °C) ===")
print(f"   Tb (brightness, atmosferasiz): MBE={A.Tb_bias.mean():.2f}  RMSE={np.sqrt((A.Tb_bias**2).mean()):.2f}")
print(f"   Artis-Carnahan (emissivitet):  MBE={A.AC_bias.mean():.2f}  RMSE={np.sqrt((A.AC_bias**2).mean()):.2f}")
print("   (eslatma: C2L2 SMW pipeline'da MBE≈+5.1; C2L2 raw≈+6.6)")
print("\n  === B: Boshqa sensorlar bias (LST − lizimetr, °C) ===")
if not B.empty:
    print(B.groupby('sensor')['bias'].agg(['mean','min','max','count']).round(2).to_string())
    print("\n  (sensor kesimi):"); print(B.to_string(index=False))
with pd.ExcelWriter(OUTDIR+'/lst_variants_multisensor_2021.xlsx', engine='openpyxl') as xw:
    A.round(3).to_excel(xw,'A_landsat_raw',index=False)
    if not B.empty: B.round(3).to_excel(xw,'B_multisensor',index=False)
print("\n  💾 lst_variants_multisensor_2021.xlsx")
