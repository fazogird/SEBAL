# -*- coding: utf-8 -*-
"""
Navbatdagi ORTIQCHA FLUXVAL task'larni bekor qiladi → kerakli task'lar tezroq.
Bekor qilinadi (faqat READY/RUNNING — ishlayotganlar):
  1. Kc scene dublikatlari: '..._Milliy_Kc_INST/DAILY_ET/INST_KOMPONENT/lstdiag...'
     (SEBAL_Milliy bilan AYNAN bir xil; Kc'dan faqat MONTHLY_ET kerak).
  2. Barcha '..._lstdiag_...' (footprint diagnostika — ET/komponent validatsiyaga shart emas).
Tugagan (COMPLETED) task'lar TEGILMAYDI.

Ishga: python cancel_redundant_tasks.py         (sanaydi, bekor qiladi)
        python cancel_redundant_tasks.py --dry   (faqat sanaydi, bekor QILMAYDI)
"""
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass
import ee

ee.Initialize(project="carbon-science-461016-q2")
DRY = '--dry' in sys.argv
CANCEL_LSTDIAG = False           # lstdiag SAQLANADI (footprint LST flux uchun foydali).
#                                  True → uni ham bekor qiladi (agar kerak bo'lmasa).


def is_redundant(desc):
    if not desc.startswith('FLUXVAL_'):
        return False
    # 1) Kc scene dublikatlari (MONTHLY_ET dan boshqa Kc fayllari)
    if 'Milliy_Kc' in desc and 'MONTHLY_ET' not in desc:
        return True
    # 2) lstdiag (ixtiyoriy)
    if CANCEL_LSTDIAG and '_lstdiag_' in desc:
        return True
    return False


def main():
    print("  Task'lar ro'yxati olinmoqda...")
    tasks = ee.batch.Task.list()
    pend, cancelled, kept = 0, 0, 0
    for t in tasks:
        st = t.status()
        state = st.get('state')
        desc = st.get('description', '')
        if state not in ('READY', 'RUNNING'):     # faqat kutayotgan/ishlayotgan
            continue
        pend += 1
        if is_redundant(desc):
            if DRY:
                print(f"    [BEKOR bo'lardi] {desc}")
            else:
                try:
                    t.cancel(); print(f"    ✖ bekor: {desc}")
                except Exception as e:
                    print(f"    ⚠️ {desc}: {e}")
            cancelled += 1
        else:
            kept += 1
    verb = "bekor bo'lardi" if DRY else "bekor qilindi"
    print(f"\n  Kutayotgan: {pend} | {verb}: {cancelled} | qoladi (kerakli): {kept}")
    if DRY:
        print("  (--dry — hech narsa bekor qilinmadi. Rozilik bo'lsa --dry'siz ishga tushiring.)")


if __name__ == '__main__':
    main()
