# Uchinchi tomon kodi / Third-party code

## OpenET `openet-landsat-lst` — Apache License 2.0

- Manba / Source: https://github.com/Open-ET/openet-landsat-lst, `openet/lst/model.py`
- Mualliflar / Authors: Yanghui Kang, Yun Yang (OpenET). Litsenziya loyihaning `pyproject.toml` faylida
  e'lon qilingan (`Apache-2.0`); asl repoda NOTICE fayli yo'q.
- Litsenziya matni / License text: [LICENSES/Apache-2.0.txt](LICENSES/Apache-2.0.txt)

Shu kod asosida yozilgan (o'zgartirilgan) fayllar — o'zgarishlar har fayl sarlavhasida qayd etilgan
(Apache-2.0, 4(b)) / Derived (modified) files, with changes noted in each file header:

- `sharpening/dms.py` — DMS (Random Forest + lokal regressiya + energiya saqlanishi);
- `sebal_gee_v4/pipeline/downscale.py` — `sharpening/dms.py` ning global RF + energiya saqlanishi qismi.

Bu fayllar Apache License 2.0 shartlari asosida tarqatiladi. Repozitoriyning qolgan qismiga bu
litsenziya taalluqli emas. / These files are distributed under the Apache License 2.0; the license
does not apply to the rest of this repository.
