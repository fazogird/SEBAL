# -*- coding: utf-8 -*-
"""
Validatsiya nuqtalari — 9 AmeriFlux minorasi + Bushland lizimetr = 10 nuqta.
TILE bo'yicha GURUHLANGAN: bir tile'ga tushgan nuqtalar BITTA run bilan
hisoblanadi (tile bir marta, csv_region = guruhdagi barcha nuqtalar).

Har guruh: nuqtalar, UTM CRS, mahalliy vaqt (standart, DST YO'Q), YILLAR.
"""

# --- Nuqta koordinatalari (BIF LOCATION_LAT/LONG dan) ---
POINTS = {
    'US-Ne1': dict(lat=41.1651, lon=-96.4766, crop='makka sug\'or.'),
    'US-Ne2': dict(lat=41.1649, lon=-96.4701, crop='makka-soya sug\'or.'),
    'US-Ne3': dict(lat=41.1797, lon=-96.4397, crop='makka-soya lalmi'),
    'US-MN1': dict(lat=45.6168, lon=-96.1269, crop='makka-soya cover'),
    'US-MN3': dict(lat=45.6091, lon=-96.1265, crop='makka-soya conv.'),
    'US-Bi1': dict(lat=38.0992, lon=-121.4993, crop='beda (alfalfa)'),
    'US-DFC': dict(lat=43.3448, lon=-89.7117, crop='yem-xashak'),
    'US-HRC': dict(lat=34.5888, lon=-91.7517, crop='sholi (rice)'),
    'US-UR8': dict(lat=37.5405, lon=-108.7390, crop='beda (alfalfa)'),
    'Bushland_lys': dict(lat=35.186714, lon=-102.094189, crop='paxta (lizimetr)'),
}

# --- TILE/hudud guruhlari (bir tile → bitta run, ko'p nuqta) ---
GROUPS = {
    'Nebraska':  dict(points=['US-Ne1', 'US-Ne2', 'US-Ne3'],
                      crs='EPSG:32614', utc=-6, years=[2022, 2023, 2024]),
    'Minnesota': dict(points=['US-MN1', 'US-MN3'],
                      crs='EPSG:32614', utc=-6, years=[2022, 2023, 2024]),
    'California': dict(points=['US-Bi1'],
                      crs='EPSG:32610', utc=-8, years=[2022, 2023, 2024]),
    'Wisconsin': dict(points=['US-DFC'],
                      crs='EPSG:32616', utc=-6, years=[2022, 2023, 2024]),
    'Arkansas':  dict(points=['US-HRC'],
                      crs='EPSG:32615', utc=-6, years=[2022, 2023, 2024]),
    'Colorado':  dict(points=['US-UR8'],
                      crs='EPSG:32612', utc=-7, years=[2024, 2025]),   # UR8: 2024-25
    'Texas_lys': dict(points=['Bushland_lys'],
                      crs='EPSG:32613', utc=-6, years=[2021]),          # lizimetr 2021
}

# O'suv mavsumi oynasi (har yil): Aprel–Oktabr
SEASON = ('04-01', '11-01')
FOOTPRINT_M = 200
MODES = ['SEBAL_B', 'SEBAL_ID', 'SEBAL_Milliy', 'SEBAL_Milliy_Kc']
