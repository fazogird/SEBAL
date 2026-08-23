# -*- coding: utf-8 -*-
"""
Ildiz-zona kunlik suv balansi — SKALYAR (numpy) REFERENS + testlar.
Maqsad: AWnet ni water-balansdan (ΣInet) hisoblash mantig'ini ISBOTLASH, keyin
GEE rasterга AYNAN shu mantiqni port qilish.

Kunlik (FAO-56, sug'orish-rejali):
  x = Dr_prev + ETa − (P − RO) − CR
  x < 0:  DP = −x ;        Dr_before = 0          (FC dan oshdi → chuqur perkolatsiya)
  x ≥ 0:  DP = 0  ;        Dr_before = x
  RAW = p·TAW
  Dr_before ≥ RAW:  Inet = Dr_before ; Dr_end = 0 ; event = 1   (RAW ga yetdi → FC gacha)
  else:             Inet = 0         ; Dr_end = Dr_before ; event = 0

Yakuniy:
  AWnet   = Σ Inet
  AWgross = AWnet / efficiency
  ΔS_storage = Dr_start − Dr_end
  residual = ΣP + ΣInet + ΣCR − ΣETa − ΣRO − ΣDP − ΔS_storage   → ~0 bo'lishi shart.

AWnet CUirr+ΔS dan EMAS — sug'orishlar yig'indisidan. Tenglama = TEKSHIRUV.
"""
import numpy as np


def simulate_daily(eta, P, taw, p_frac, efficiency=0.55, ro=None, cr=0.0,
                   dr_init=0.0):
    """
    eta, P — kunlik massiv (mm). ro — kunlik yuzaki oqim (None→0). taw, p_frac,
    efficiency, cr, dr_init — skalyar. Qaytaradi: dict (jami + kunlik jadval).
    dr_init — boshlang'ich depletion (TAXMIN; default 0 = tuproq FC da).
    """
    eta = np.asarray(eta, float); P = np.asarray(P, float)
    n = len(eta)
    ro = np.zeros(n) if ro is None else np.asarray(ro, float)
    assert taw > 0, "TAW > 0 bo'lishi kerak"
    assert 0.0 <= p_frac <= 1.0, "0 ≤ p ≤ 1"
    assert 0.0 < efficiency <= 1.0, "0 < efficiency ≤ 1"
    RAW = p_frac * taw
    assert RAW <= taw, "RAW ≤ TAW"

    Dr = float(dr_init)
    rows = []
    sum_inet = sum_dp = 0.0
    for i in range(n):
        x = Dr + eta[i] - (P[i] - ro[i]) - cr
        if x < 0.0:
            dp = -x; dr_before = 0.0
        else:
            dp = 0.0; dr_before = x
        if dr_before >= RAW:
            inet = dr_before; dr_end = 0.0; event = 1
        else:
            inet = 0.0; dr_end = dr_before; event = 0
        dr_end = min(max(dr_end, 0.0), taw)          # 0 ≤ Dr ≤ TAW kafolat
        sum_inet += inet; sum_dp += dp
        rows.append(dict(day=i, Dr=dr_end, avail=taw - dr_end, Inet=inet,
                         DP=dp, event=event, cum_Inet=sum_inet))
        Dr = dr_end

    awnet = sum_inet
    awgross = awnet / efficiency
    dS_storage = dr_init - Dr                          # S_end − S_start = Dr_start − Dr_end
    residual = (P.sum() + sum_inet + cr * n
                - eta.sum() - ro.sum() - sum_dp - dS_storage)
    return dict(AWnet=awnet, AWgross=awgross, DP=sum_dp, dS=dS_storage,
                residual=residual, Dr_end=Dr, avail_end=taw - Dr,
                RAW=RAW, TAW=taw, n_irrig=int(sum(r['event'] for r in rows)),
                rows=rows)


# ─────────────────────────── UNIT TESTLAR ───────────────────────────
def _almost(a, b, tol=1e-6):
    return abs(a - b) < tol


def test_only_et_no_irrigation():
    """Faqat ET, yomg'ir/sug'orish yo'q (RAW juda katta) → AWnet=0, tuproq quriydi."""
    r = simulate_daily([5, 5, 5], [0, 0, 0], taw=100, p_frac=0.99, dr_init=0.0)
    assert _almost(r['AWnet'], 0.0), r['AWnet']
    assert _almost(r['Dr_end'], 15.0), r['Dr_end']       # 3×5 to'plandi
    assert _almost(r['residual'], 0.0), r['residual']     # balans yopiladi
    print("  ✅ test 1 (faqat ET, sug'orishsiz): AWnet=0, Dr=15, residual~0")


def test_heavy_rain_dp():
    """Kuchli yomg'in > ET → DP>0, Dr past qoladi, AWnet=0."""
    r = simulate_daily([3, 3], [50, 0], taw=20, p_frac=0.5, dr_init=10.0)
    # kun1: x=10+3-50=-37 → DP=37, Dr=0 ; kun2: x=0+3-0=3 <RAW(10) → Dr=3
    assert r['DP'] > 30, r['DP']
    assert _almost(r['AWnet'], 0.0), r['AWnet']
    assert _almost(r['residual'], 0.0), r['residual']
    print(f"  ✅ test 2 (kuchli yomg'in): DP={r['DP']:.0f}, AWnet=0, residual~0")


def test_raw_trigger():
    """Dr RAW ga yetganda sug'orish yonadi."""
    r = simulate_daily([6, 6, 6], [0, 0, 0], taw=100, p_frac=0.10, dr_init=0.0)
    # RAW=10. kun2: Dr_before=12≥10 → Inet=12, Dr→0. Har ~2 kunda sug'oradi.
    assert r['n_irrig'] >= 1, r['n_irrig']
    assert r['AWnet'] > 0, r['AWnet']
    assert _almost(r['residual'], 0.0), r['residual']
    print(f"  ✅ test 3 (RAW trigger): {r['n_irrig']} sug'orish, AWnet={r['AWnet']:.0f}, residual~0")


def test_consecutive_irrigation():
    """Ketma-ket sug'orish: mavsum bo'yicha ko'p hodisa, AWnet ≈ ΣETa (yomg'irsiz)."""
    eta = [5] * 30
    r = simulate_daily(eta, [0] * 30, taw=100, p_frac=0.10, dr_init=0.0)
    assert r['n_irrig'] >= 10, r['n_irrig']
    # yomg'irsiz, CR=0: AWnet ≈ ΣETa − (oxirgi qolgan Dr)
    assert _almost(r['AWnet'], sum(eta) - r['Dr_end']), (r['AWnet'], r['Dr_end'])
    assert _almost(r['residual'], 0.0), r['residual']
    print(f"  ✅ test 4 (ketma-ket): {r['n_irrig']} sug'orish, AWnet={r['AWnet']:.0f}≈ΣET-Dr")


def test_balance_closure():
    """Aralash: yomg'in + ET + sug'orish → residual ~0 (balans yopilishi)."""
    np.random.seed(3)
    eta = np.random.uniform(3, 8, 40)
    P = np.where(np.random.rand(40) < 0.2, np.random.uniform(5, 25, 40), 0.0)
    ro = P * 0.1
    r = simulate_daily(eta, P, taw=120, p_frac=0.5, ro=ro, dr_init=20.0)
    assert _almost(r['residual'], 0.0, tol=1e-4), r['residual']
    print(f"  ✅ test 5 (balans yopilishi): residual={r['residual']:.2e} ~0")


if __name__ == '__main__':
    print("  === root_zone_balance skalyar testlar ===")
    test_only_et_no_irrigation()
    test_heavy_rain_dp()
    test_raw_trigger()
    test_consecutive_irrigation()
    test_balance_closure()
    print("  🎯 5/5 test o'tdi — mantiq to'g'ri, GEE portga tayyor.")
