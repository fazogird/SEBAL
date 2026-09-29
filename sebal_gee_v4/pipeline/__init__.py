"""
Ko'p sensorli SEBAL pipeline ("Satellite data revolution") — MGRS tile bo'yicha.

Arxitektura (user bilan kelishilgan, 2026-09-28; tuzatilma/post_et_yol_xaritasi.md 8-bo'lim):
  0. Tile pasporti  — tile.MgrsTile: HLS/MGRS 30 m grid, UTM zona, Esri ekin (har yil o'z yili).
  1–3. Kirish       — sources.*: Landsat C2 L2, HLS L30/S30, VIIRS VNP21A1D, ECOSTRESS L2T.
                      Har kuzatuv SEEN / BAD bandlariga keltiriladi; qoidalar — rules.InputRules.
  9. Kalendar       — calendar.TileCalendar: har kun qaysi sensor bilan SEBAL, qaysi kun suv balansi.

Keyingi bosqichlar (sahna yig'uvchi, SEBAL, kunlik birlashma, oylik) hali yozilmagan.
Mavjud modullar (preprocessing, energy_balance, ...) bu paket tomonidan o'zgartirilmaydi.
"""
