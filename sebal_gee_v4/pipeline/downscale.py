"""
Dag'al LST'ni (VIIRS 1 km) HLS reflektansi bilan 30 m ga tushirish — DMS global model
(Random Forest) + energiya saqlanishi. GEE grafi ichida, asset'siz; seed qat'iy — anchor
tanlash va eksport so'rovlari aynan bir xil LST oladi.

Asos: OpenET `openet-landsat-lst`, fayl `openet/lst/model.py` (Apache-2.0; mualliflar
Yanghui Kang, Yun Yang; https://github.com/Open-ET/openet-landsat-lst) — sharpening/dms.py
orqali. Asl koddan farqlar o'sha faylda qayd etilgan (nurlanish fazosida yig'ish, RF namunalari
soni bilan, proyeksiyalar argument sifatida, ...). Bu yerda faqat global RF + EC qismi:
sharpening/dms.sharpen(...)['lst_global'] bilan AYNAN bir xil hisob (T-A pilotda eng yaxshi usul,
sharpening/README.md). Usul: Gao va boshq. 2012; Xue va boshq. 2020; Liu va boshq. 2026.
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


def sharpen_rf(sr, lst_coarse, region, fine_proj, coarse_proj, ec_proj, bands=BANDS,
               cv_threshold=0.25, n_samples=5000, rf_trees=100, rf_vars=4, rf_leaf=50, seed=7):
    """
    sr — 30 m reflektans (`bands` nomlari), fine_proj gridida; lst_coarse — dag'al LST (K),
    coarse_proj gridida; ec_proj — energiya saqlanishi qutisi. Qaytaradi: 'LST' (K), fine_proj.
    """
    bands = list(bands)
    fine = sr.select(bands)
    r_c = t2r(lst_coarse)

    sr_mean = aggregate(fine, coarse_proj, ee.Reducer.mean())
    sr_std = aggregate(fine, coarse_proj, ee.Reducer.stdDev())
    cv = sr_std.divide(sr_mean).reduce(ee.Reducer.mean()).rename('cv')
    one = sr_mean.select([0]).multiply(0).add(1).rename('bias')
    agg = sr_mean.addBands(one).addBands(r_c)          # dms.sharpen bilan aynan bir xil namuna

    # Global model: bir jinsli dag'al piksellarda Random Forest (regressiya), nurlanish fazosida
    samples = (agg.updateMask(cv.lt(cv_threshold))
                  .sample(region=region, projection=coarse_proj,
                          numPixels=n_samples, seed=seed, tileScale=4))
    rf = (ee.Classifier.smileRandomForest(numberOfTrees=rf_trees, variablesPerSplit=rf_vars,
                                          minLeafPopulation=rf_leaf, seed=seed)
            .setOutputMode('REGRESSION').train(samples, 'rad', bands))
    r_global = fine.classify(rf, 'rad')

    # Energiya saqlanishi: EC qutisidagi farq bilinear tarqatilib ayiriladi (yig'ish ikki bosqichda)
    res_ec = aggregate(aggregate(r_global, coarse_proj), ec_proj).subtract(aggregate(r_c, ec_proj))
    r = r_global.subtract(res_ec.resample('bilinear').reproject(fine_proj))
    return r2t(r).rename('LST').reproject(fine_proj)
