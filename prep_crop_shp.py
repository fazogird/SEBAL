# -*- coding: utf-8 -*-
"""
1-QADAM (SHP→raster tayyorgarlik): 3 viloyat kadastr SHP'ga 'crop_code' qo'shadi,
EPSG:4326 ga o'giradi va YENGIL SHP (faqat crop_code + geometry) saqlaydi → GEE'ga
FeatureCollection asset qilib yuklash oson.

  turi → crop_code:  Paxta=1..Boshqa=11 (crop_kc_table bilan bir xil);
                     Baliqxovuz/Issiqxona = 0 (ekin emas → keyin maskalanadi).
GEE'da area GEODEZIK (to'g'ri) hisoblanadi — CRS 3857 muammosi GEE'da yo'q;
lekin standart uchun 4326 ga o'giramiz.
"""
import geopandas as gpd

IN = r'D:/Cloud_comp/Sebal/Input/polygons'
OUT = r'D:/Cloud_comp/Sebal/Input/polygons/for_gee'
PROVS = ['Samarqand', 'Fargona', 'Qashqadaryo']

# crop_kc_table.CROP_KC bilan AYNAN bir xil kod (bog'liqlik uchun shu yerda ham)
CODE = {'Paxta': 1, "Bug'doy": 2, "Bog'": 3, 'Beda': 4, 'Makka': 5,
        'Kartoshka': 6, 'Noxot': 7, 'Sabzi': 8, 'Poliz': 9, 'Ozuqa': 10, 'Boshqa': 11}
EXCLUDE = ['Baliqxovuz', 'Issiqxona']       # ekin emas → 0


def main():
    import os
    os.makedirs(OUT, exist_ok=True)
    for prov in PROVS:
        f = f'{IN}/UZ_2026_{prov}_06_new_cadastres.shp'
        g = gpd.read_file(f)
        col = 'turi' if 'turi' in g.columns else \
            next((c for c in g.columns if 'tur' in c.lower()), None)
        g['crop_code'] = g[col].map(lambda t: 0 if t in EXCLUDE else CODE.get(t, 0))
        n_excl = int((g['crop_code'] == 0).sum())
        g = g.to_crs('EPSG:4326')
        out = f'{OUT}/{prov}_crop.shp'
        g[['crop_code', 'geometry']].to_file(out, encoding='utf-8')
        vc = g['crop_code'].value_counts().sort_index()
        print(f"  ✅ {prov}: {len(g)} poligon → {out}")
        print(f"     kod taqsimoti: {dict(vc)}  (0=ekin emas: {n_excl})")


if __name__ == '__main__':
    main()
