# -*- coding: utf-8 -*-
"""
LST'ni HLS reflektansi yordamida 30 m ga keskinlashtirish (GEE): DMS va TsHARP.

DMS asosi: OpenET `openet-landsat-lst`, fayl `openet/lst/model.py`
      (Apache-2.0, pyproject.toml bo'yicha; mualliflar Yanghui Kang, Yun Yang;
      https://github.com/Open-ET/openet-landsat-lst).
Usul: Gao va boshq. 2012 (Remote Sens. 4:3287); Xue va boshq. 2020 (RSE 251:112055);
      Liu va boshq. 2026 (RSE 336:115299).
TsHARP: Kustas va boshq. 2003 (RSE 85:429); Agam va boshq. 2007 (RSE 107:545).

DMS asl koddan farqlar (Apache-2.0, 4(b) bo'yicha o'zgartirishlar qayd etiladi):
  1. Sensor parametrlari qotirilmagan. Dag'al grid, EC box, lokal oyna, CV chegarasi
     va RF namunalar soni argument sifatida beriladi (ECOSTRESS 70 m, VIIRS ~1 km).
     Asl kodda ular SPACECRAFT_ID orqali faqat Landsat uchun qotirilgan.
  2. Yig'ish va regressiya NURLANISH fazosida (Planck, 10.9 µm). Asl kodda harorat
     avval o'rtachalanib, keyin T^4 ga ko'tarilgan.
  3. RF namunalari ulush bilan emas, soni bilan olinadi. Asl kodda ulush 0.5% bo'lib,
     1 km gridda juda kam namuna beradi.
  4. Dag'al LST alohida rasm sifatida, o'z proyeksiyasida beriladi (sensorning haqiqiy
     gridi, masalan VIIRS sinusoidal) yoki sinov uchun simulyatsiya.
  5. Kombinatsiya og'irliklarida nolga bo'linishning oldi kichik eps bilan olinadi
     (asl kodda nol qoldiq alohida tarmoqlar bilan qayta ishlangan).
  6. Lokal regressiya natijasi dag'al gridga qotiriladi. Asl kodda regressiya natijasi
     to'g'ridan-to'g'ri nozik gridga reproject qilinadi va GEE regressiyani nozik gridda
     bajaradi: oyna radiusi "10 dag'al piksel" o'rniga 10 × 30 m bo'lib qoladi
     (2026-09-27 da aniqlandi: 1 km da natija deyarli butunlay bo'sh chiqqan).
  7. Faqat global (RF) va faqat lokal model natijalari ham (har biri EC bilan) qaytariladi.

Proyeksiyalar ee.Projection sifatida beriladi (crs + transform).
"""
import ee

C1 = 1.191042e8      # W µm^4 m^-2 sr^-1 (2hc^2)
C2 = 1.4387752e4     # µm K (hc/k)
LAM = 10.9           # µm — nurlanish fazosi uchun

BANDS = ['blue', 'green', 'red', 'nir', 'swir1', 'swir2']


def t2r(t):
    """Harorat (K) → Planck nurlanishi (W m^-2 sr^-1 µm^-1)."""
    den = ee.Image.constant(C2 / LAM).divide(t).exp().subtract(1)
    return ee.Image.constant(C1 / LAM ** 5).divide(den).rename('rad')


def r2t(r):
    """Planck nurlanishi → harorat (K)."""
    ln = ee.Image.constant(C1 / LAM ** 5).divide(r).add(1).log()
    return ee.Image.constant(C2 / LAM).divide(ln).rename('lst')


def aggregate(img, proj, reducer=None, max_pixels=4096):
    """Nozik rasmni `proj` gridiga yig'ish (maydon og'irlikli)."""
    reducer = reducer or ee.Reducer.mean()
    return img.reduceResolution(reducer=reducer, maxPixels=max_pixels).reproject(proj)


def aggregate_lst(lst, proj):
    """LST'ni nurlanish fazosida yig'ish (harorat emas, nurlanish o'rtachalanadi)."""
    return r2t(aggregate(t2r(lst), proj))


def _ec(r_fine, r_c, fine_proj, coarse_proj, ec_proj):
    """Energiya saqlanishi: EC box'dagi farqni bilinear tarqatib ayirish.
    Yig'ish ikki bosqichda (nozik → dag'al → EC): GEE'da bir amalda 4096 piksel chegarasi bor."""
    res_ec = aggregate(aggregate(r_fine, coarse_proj), ec_proj).subtract(aggregate(r_c, ec_proj))
    return r_fine.subtract(res_ec.resample('bilinear').reproject(fine_proj))


def sharpen(sr, lst_coarse, region, fine_proj, coarse_proj, ec_proj,
            bands=BANDS, kernel_radius=10, cv_threshold=0.15, n_samples=5000,
            rf_trees=100, rf_vars=4, rf_leaf=50, seed=7, eps=1e-12):
    """
    DMS. sr — nozik (30 m) reflektans (`bands` nomlari), fine_proj gridida.
    lst_coarse — dag'al LST (K), coarse_proj gridida. ec_proj — EC box (>= dag'al piksel).
    Qaytaradi: bandlar 'lst' (lokal+global, EC), 'lst_global' (faqat RF, EC),
    'lst_local' (faqat lokal, EC), 'w_local', 'cv'.
    """
    bands = list(bands)
    fine = sr.select(bands)
    r_c = t2r(lst_coarse)

    sr_mean = aggregate(fine, coarse_proj, ee.Reducer.mean())
    sr_std = aggregate(fine, coarse_proj, ee.Reducer.stdDev())
    cv = sr_std.divide(sr_mean).reduce(ee.Reducer.mean()).rename('cv')
    one = sr_mean.select([0]).multiply(0).add(1).rename('bias')
    agg = sr_mean.addBands(one).addBands(r_c)

    # 1) Lokal model: dag'al gridda harakatlanuvchi oynada chiziqli regressiya.
    #    Natija avval DAG'AL gridga qotiriladi (6-farq).
    fit = agg.reduceNeighborhood(
        ee.Reducer.linearRegression(len(bands) + 1, 1),
        ee.Kernel.square(kernel_radius), None, False).reproject(coarse_proj)
    coef = (fit.select('coefficients').arrayProject([0])
               .arrayFlatten([bands + ['bias']]).reproject(fine_proj))
    x_f = fine.addBands(fine.select([0]).multiply(0).add(1).rename('bias'))
    r_local = x_f.multiply(coef).reduce(ee.Reducer.sum()).rename('rad')

    # 2) Global model: bir jinsli dag'al piksellarda Random Forest (regressiya)
    samples = (agg.updateMask(cv.lt(cv_threshold))
                  .sample(region=region, projection=coarse_proj,
                          numPixels=n_samples, seed=seed, tileScale=4))
    rf = (ee.Classifier.smileRandomForest(numberOfTrees=rf_trees, variablesPerSplit=rf_vars,
                                          minLeafPopulation=rf_leaf, seed=seed)
            .setOutputMode('REGRESSION').train(samples, 'rad', bands))
    r_global = fine.classify(rf, 'rad')

    # 3) Kombinatsiya: dag'al qoldiq kvadratiga teskari og'irlik
    res_l = aggregate(r_local, coarse_proj).subtract(r_c).abs()
    res_g = aggregate(r_global, coarse_proj).subtract(r_c).abs()
    wl = res_l.pow(2).add(eps).pow(-1)
    wg = res_g.pow(2).add(eps).pow(-1)
    w_local = wl.divide(wl.add(wg)).rename('w_local')
    r_comb = r_local.multiply(w_local).add(r_global.multiply(w_local.multiply(-1).add(1)))

    # 4) Energiya saqlanishi (har bir variant uchun)
    out = r2t(_ec(r_comb, r_c, fine_proj, coarse_proj, ec_proj)).rename('lst')
    out_g = r2t(_ec(r_global, r_c, fine_proj, coarse_proj, ec_proj)).rename('lst_global')
    out_l = r2t(_ec(r_local, r_c, fine_proj, coarse_proj, ec_proj)).rename('lst_local')
    return (out.addBands(out_g).addBands(out_l).reproject(fine_proj)
               .addBands(w_local).addBands(cv))


def tsharp(ndvi, lst_coarse, region, fine_proj, coarse_proj,
           cv_threshold=0.25, pct=(2, 98)):
    """
    TsHARP (Kustas 2003; Agam 2007): dag'al gridda LST = a + b·fc (bir jinsli piksellar),
    nozik gridda qo'llanadi, dag'al qoldiq qo'shiladi (har dag'al piksel ichida bir xil — asl usul).
    fc = 1 − ((NDVImax − NDVI)/(NDVImax − NDVImin))^0.625; NDVImin/max — sahna persentillari.
    Harorat fazosida (asl usul). Qaytaradi: 'lst' (K), nozik gridda.
    """
    p = ndvi.reduceRegion(ee.Reducer.percentile(list(pct)), region, crs=fine_proj.crs(),
                          scale=90, maxPixels=1e9, bestEffort=True)
    nmin = ee.Number(p.get(f'ndvi_p{pct[0]}'))
    nmax = ee.Number(p.get(f'ndvi_p{pct[1]}'))

    def fc(n):
        x = ee.Image.constant(nmax).subtract(n).divide(nmax.subtract(nmin)).clamp(0, 1)
        return x.pow(0.625).multiply(-1).add(1).rename('fc')

    ndvi_c = aggregate(ndvi, coarse_proj)
    ndvi_sd = aggregate(ndvi, coarse_proj, ee.Reducer.stdDev())
    cv = ndvi_sd.divide(ndvi_c.abs().max(1e-3))
    fc_c = fc(ndvi_c)
    lst_c = lst_coarse.rename('lst')
    fit = (fc_c.addBands(lst_c).updateMask(cv.lt(cv_threshold))
              .reduceRegion(ee.Reducer.linearFit(), region, crs=coarse_proj.crs(),
                            crsTransform=coarse_proj.getInfo()['transform'],
                            maxPixels=1e9, bestEffort=True, tileScale=4))
    a = ee.Number(fit.get('offset'))
    b = ee.Number(fit.get('scale'))
    resid_c = lst_c.subtract(fc_c.multiply(b).add(a))
    pred_f = fc(ndvi).multiply(b).add(a)
    return pred_f.add(resid_c.reproject(coarse_proj)).rename('lst').reproject(fine_proj)
