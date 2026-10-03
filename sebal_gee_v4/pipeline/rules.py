"""
Kirish bosqichi qoidalari — user bilan kelishilgan (2026-09-28, post_et_yol_xaritasi.md 8-bo'lim).

Hamma sensor uchun bir xil:
  1) dastlabki filtr — sahna (metadata) yoki tile buluti < scene_cloud_max (80%);
  2) tasvir ko'rgan ekin ustida bulut ≤ crop_cloud_max (20%);
  3) tasvir tile ekinining kamida crop_seen_min (10%) ini ko'rsin (S30 "tasmalari" chiqadi).
VIIRS: QC 0–1-bitlar = 0 va 4–5-bitlar (bulut bayrog'i) = 0; |ko'rish burchagi| ≤ 40°.
VIIRS + HLS: piksel ikkalasida ham toza bo'lsa olinadi; HLS ±hls_window_days kun ichida.
"""
from dataclasses import dataclass

LANDSAT_C2 = {'LANDSAT_8': 'LANDSAT/LC08/C02/T1_L2', 'LANDSAT_9': 'LANDSAT/LC09/C02/T1_L2'}
HLS = {'L30': 'NASA/HLS/HLSL30/v002', 'S30': 'NASA/HLS/HLSS30/v002'}
VIIRS_LST = 'NASA/VIIRS/002/VNP21A1D'
ECOSTRESS_LST = 'NASA/ECOSTRESS/L2T_LSTE/V2'
ESRI_LULC = 'projects/sat-io/open-datasets/landcover/ESRI_Global-LULC_10m_TS'
ESRI_CROPS = 5
# O'zbekiston viloyat chegaralari (user asseti; GAUL 2015 o'rniga, 2026-09-29)
ADMIN1 = 'projects/ee-chexovant11/assets/uzb_admin1_2026'
ADMIN1_FIELD = 'region_nam'          # 'Qashqadaryo', 'Samarqand', ...


@dataclass(frozen=True)
class InputRules:
    scene_cloud_max: float = 80.0     # dastlabki filtr, %
    crop_cloud_max: float = 20.0      # ko'rilgan ekin ustida bulut, %
    crop_seen_min: float = 10.0       # tile ekinining ko'rilgan ulushi, %
    viirs_vza_max: float = 40.0       # VIIRS |View_Angle|, gradus
    hls_window_days: int = 2          # VIIRS kuni uchun HLS optika oynasi, ±kun
    # ECOSTRESS — VAQTINCHA (yo'l xaritasi, ochiq savol 3: vaqt oynasi user qarorida)
    eco_local_hours: tuple = (9.0, 17.0)
    eco_vza_max: float = 25.0
    stats_scale: float = 100.0        # bulut/qoplam hisobi masshtabi, m (VIIRS — 1000)
    # VIIRS LST → 30 m (DMS global RF + EC) — T-A pilot sozlamasi (sharpening/export_viirs_rf.py)
    rf_cv_threshold: float = 0.25
    rf_samples: int = 5000
    rf_seed: int = 7
    # Sensorlararo daraja (ET_V_tuzatilgan = k · ET_V_xom; xom ham saqlanadi).
    # User qarori (2026-10-02): k = 1. Yangi yo'lda qayta baholandi — T42SUJ ∩ Qashqadaryo 2025, 11 ta bir kunlik
    # L+V juft: xom VIIRS ET bias −1.5 % (r 0.90), juftlar k 0.73…1.28 tarqoq, oylik trend yo'q.
    # Avvalgi 0.92 T-A pilotidan (Landsat C2 optika, Landsat vaqtidagi ERA5) edi.
    viirs_k: float = 1.0
    eco_k: float = 1.0                # o'lchanmagan (8 yilda 4 juft)
    # Anchor zonalari: 'H3' (Esri: hot — ekin ichidagi yalang'och dala → Esri 8 istisnolar bilan;
    # user qarori 2026-09-28, cfg.ANCHOR_H3); 'H2' / 'H1' — faqat bitta bosqich (solishtirish);
    # 'WC' — Landsat yo'lidagi WorldCover zonalari (40 / 60+20).
    anchor_scheme: str = 'H3'
    # tile rejasi (plan_tiles): tile'ning to'liq footprint'ida hudud ekini shundan kam bo'lsa — tushiriladi
    # (kichik maydondan anchor ishonchsiz). User tasdiqladi (2026-09-29): 100 km²; egaligi kichik (kesik)
    # tile'lar ham hisoblanadi — anchor baribir butun tile ∩ hudud ekinidan.
    min_calib_crop_km2: float = 100.0

    def judge(self, seen_pct, cloud_pct):
        """(qabul, sabab) — 2) va 3) qoidalar."""
        if seen_pct < self.crop_seen_min:
            return False, f"ekinning {seen_pct:.0f}% i ko'rindi (< {self.crop_seen_min:.0f}%)"
        if cloud_pct > self.crop_cloud_max:
            return False, f"ko'rilgan ekin ustida bulut {cloud_pct:.0f}% (> {self.crop_cloud_max:.0f}%)"
        return True, ''
