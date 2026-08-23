# -*- coding: utf-8 -*-
"""
PER-CROP Kc jadvali — O'zbekiston ekin turlari uchun (FAO-56 asosida).
Kadastr "turi" ustuni: Paxta/Bug'doy/Bog'/Beda/Makka/Kartoshka/Noxot/Sabzi/
Poliz/Ozuqa/Boshqa (+ Baliqxovuz/Issiqxona — ekin EMAS, mask).

STRUKTURA:
  • FAO_KC_BASIS — ASOS (hujjatlashtirilgan): FAO-56 Table 12 (grass ETo) qiymatlari
    manba sifatida (Kc_mid, Kc_end, late-season kunlari).
  • CROP_KC — QIYMAT (alohida): modelda ishlatiladigan koeffitsientlar.

MODEL FORMULASI (SIMS/Allen reflektans-Kcb, FAO'ga izchil):
  Kcb = kcb_max · clamp((NDVI − NDVI_BARE)/(NDVI_FULL − NDVI_BARE), 0, 1)
  Senescence: cho'qqi NDVI kunidan keyin Kcb → kcb_max·kcb_end_frac (sen_len kunda).
  Ke (tuproq bug'lanishi) — barcha ekinda bir xil (tuproqqa bog'liq, ekinga emas).

QAROR (2026-08-19): O'zbekiston uchun BARCHA ekin (paxta ham) FAO-56 dan.
Bushland lizimetr paxta koeffitsienti ALOHIDA (COTTON_USA_LYSIMETER) — USA uchun,
UZB'da ishlatilmaydi (US-nuqta kalibratsiyasi UZB'ga ko'chmaydi; FAO xalqaro o'rtacha).
"""

# ---- ASOS: FAO-56 Table 12 (grass ETo) — TASDIQLANGAN ----
# Manba: Allen R.G., Pereira L.S., Raes D., Smith M. (1998) "Crop Evapotranspiration —
#   Guidelines for computing crop water requirements", FAO Irrigation & Drainage Paper 56,
#   Table 12 (Kc_mid, Kc_end) + Table 11 (stage lengths). Onlayn: fao.org/4/x0490e/x0490e0b.htm
#   Qiymatlar 2026-08-19 da FAO-56 dan tekshirilgan (WebFetch). Diapazon berilganда o'rtasi.
FAO_KC_BASIS = {
    'Paxta':     dict(fao='Cotton',                 kc_mid=1.175, kc_end=0.60, late_days=55),  # 1.15-1.20/0.70-0.50
    'Bug\'doy':  dict(fao='Winter wheat',           kc_mid=1.15,  kc_end=0.30, late_days=30),  # 0.25-0.40
    'Bog\'':     dict(fao='Apple+cover, frost',     kc_mid=1.20,  kc_end=0.95, late_days=45),
    'Beda':      dict(fao='Alfalfa (peak cutting)', kc_mid=1.175, kc_end=1.10, late_days=0),   # o'rtacha-o'rim 0.95
    'Makka':     dict(fao='Maize (grain)',          kc_mid=1.20,  kc_end=0.50, late_days=40),  # 0.60-0.35
    'Kartoshka': dict(fao='Potato',                 kc_mid=1.15,  kc_end=0.75, late_days=30),
    'Noxot':     dict(fao='Chickpea',               kc_mid=1.00,  kc_end=0.35, late_days=30),
    'Sabzi':     dict(fao='Carrot',                 kc_mid=1.05,  kc_end=0.95, late_days=25),
    'Poliz':     dict(fao='Sweet melon',            kc_mid=1.05,  kc_end=0.75, late_days=30),
    'Ozuqa':     dict(fao='Pasture/forage (rot.)',  kc_mid=1.00,  kc_end=0.85, late_days=0),   # 0.85-1.05
    'Boshqa':    dict(fao='O\'rtacha ekin',         kc_mid=1.10,  kc_end=0.60, late_days=40),  # o'rtacha
}

# ---- QIYMAT: model koeffitsientlari (kcb_max ≈ Kcb_mid = Kc_mid−0.05) ----
#  code — rasterizatsiya uchun raqamli kod (0 = ekin emas / mask).
#  senescence=False — o'rimli ekin (beda/ozuqa): NDVI arra-tishли o'zi tushiradi.
# zr_max — ILDIZ chuqurligi (m); p — depletion fraction (stress'siz olinadigan suv ulushi).
# Manba: FAO-56 Table 22 (tasdiqlangan 2026-08-19, WebFetch). zr_max = FAO diapazon o'rtasi.
# 2-QADAM (suv balansi / mavjud suv / sug'orish): RAW = p·TAW (Dr≥RAW → sug'or).
# ET (NDVI) da ishlatilmaydi. Bosqichli: Zr = ZR_MIN + (zr_max−ZR_MIN)·fc(NDVI).
CROP_KC = {
    'Paxta':     dict(code=1,  kcb_max=1.10, kcb_end_frac=0.52, sen_len=55, senescence=True,  zr_max=1.4, p=0.65),
    'Bug\'doy':  dict(code=2,  kcb_max=1.10, kcb_end_frac=0.26, sen_len=30, senescence=True,  zr_max=1.5, p=0.55),
    'Bog\'':     dict(code=3,  kcb_max=1.15, kcb_end_frac=0.79, sen_len=45, senescence=True,  zr_max=1.5, p=0.50),
    'Beda':      dict(code=4,  kcb_max=1.15, kcb_end_frac=1.00, sen_len=60, senescence=False, zr_max=1.5, p=0.55),
    'Makka':     dict(code=5,  kcb_max=1.15, kcb_end_frac=0.42, sen_len=40, senescence=True,  zr_max=1.2, p=0.55),
    'Kartoshka': dict(code=6,  kcb_max=1.10, kcb_end_frac=0.65, sen_len=30, senescence=True,  zr_max=0.5, p=0.35),
    'Noxot':     dict(code=7,  kcb_max=0.95, kcb_end_frac=0.35, sen_len=30, senescence=True,  zr_max=0.8, p=0.50),
    'Sabzi':     dict(code=8,  kcb_max=1.00, kcb_end_frac=0.90, sen_len=25, senescence=True,  zr_max=0.6, p=0.35),
    'Poliz':     dict(code=9,  kcb_max=1.00, kcb_end_frac=0.71, sen_len=30, senescence=True,  zr_max=1.0, p=0.40),
    'Ozuqa':     dict(code=10, kcb_max=0.95, kcb_end_frac=1.00, sen_len=60, senescence=False, zr_max=0.8, p=0.60),
    'Boshqa':    dict(code=11, kcb_max=1.05, kcb_end_frac=0.55, sen_len=40, senescence=True,  zr_max=1.0, p=0.50),
}
ZR_MIN = 0.20           # boshlang'ich ildiz chuqurligi (m) — universal (unib chiqish)

# ---- Ekin EMAS — hisoblanmaydi (mask; Kc yo'q) ----
EXCLUDE = ['Baliqxovuz', 'Issiqxona']       # suv havzasi / teplitsa

# ---- Universal (barcha ekin uchun bir xil) ----
NDVI_BARE = 0.15
NDVI_FULL = 0.85
KC_MAX = 1.20            # Ke ustki chegara (FAO-56)
KE_SCALE = 0.30
TEW = 20.0
REW = 9.0

# ---- USA (Bushland lizimetr paxta) — ALOHIDA, UZB'da ISHLATILMAYDI ----
# Ground-truth kalibrlangan (R²=0.92); faqat USA/validatsiya uchun saqlanadi.
COTTON_USA_LYSIMETER = dict(kcb_a=1.25, kcb_b=-0.10, kcb_max=1.00,
                            sen_len=60, kcb_end_frac=0.45, ke_scale=0.30)


def code_map():
    """{'Paxta':1, ...} — SHP 'turi' → raqamli kod (rasterizatsiya uchun)."""
    return {name: v['code'] for name, v in CROP_KC.items()}


def coeff_arrays():
    """Rasterizatsiya/remap uchun: (codes, kcb_max[], kcb_end_frac[], sen_len[], sen_on[])."""
    names = list(CROP_KC)
    codes = [CROP_KC[n]['code'] for n in names]
    return (codes,
            [CROP_KC[n]['kcb_max'] for n in names],
            [CROP_KC[n]['kcb_end_frac'] for n in names],
            [float(CROP_KC[n]['sen_len']) for n in names],
            [1.0 if CROP_KC[n]['senescence'] else 0.0 for n in names])


def zr_arrays():
    """(codes, zr_max[], p[]) — 2-QADAM (ildiz-zona balans, RAW=p·TAW) uchun remap."""
    names = list(CROP_KC)
    return ([CROP_KC[n]['code'] for n in names],
            [CROP_KC[n]['zr_max'] for n in names],
            [CROP_KC[n]['p'] for n in names])
