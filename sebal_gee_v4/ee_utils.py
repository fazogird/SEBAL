"""
GEE utility: getInfo() uchun avtomatik retry (429 rate-limit himoyasi).

GEE serveri band bo'lganda ("Too many concurrent aggregations",
"Too many requests", "User memory limit" emas — faqat vaqtinchalik
xatolar) eksponensial kutish bilan qayta urinadi.

Ishlatish (ee.Initialize dan keyin bir marta):
    from sebal_gee_v4 import ee_utils
    ee_utils.install_getinfo_retry()
"""

import time

import ee
from ee.ee_exception import EEException

# Vaqtinchalik (retry qilsa bo'ladigan) xato belgilari
_TRANSIENT_MARKERS = (
    'Too many concurrent',
    'Too Many Requests',
    'too many requests',
    'Quota exceeded',
    'rate limit',
    'Rate Limit',
    'Earth Engine capacity exceeded',
    'Service Unavailable',
    'Internal error',
    'Deadline',
    'timed out',
    '429',
    '500',
    '503',
)

_installed = False


def _is_transient(exc):
    msg = str(exc)
    return any(marker in msg for marker in _TRANSIENT_MARKERS)


def install_getinfo_retry(retries=6, base_delay=10, max_delay=300):
    """
    ee.ComputedObject.getInfo ni retry bilan o'raydi.
    Barcha getInfo() chaqiruvlari (Image, ImageCollection, Number, ...)
    avtomatik himoyalanadi.

    Kutish vaqtlari (default): 10, 20, 40, 80, 160, 300 sekund.
    """
    global _installed
    if _installed:
        return

    original_getinfo = ee.ComputedObject.getInfo

    def getinfo_with_retry(self):
        last_exc = None
        for attempt in range(retries + 1):
            try:
                return original_getinfo(self)
            except EEException as e:
                if not _is_transient(e):
                    raise
                last_exc = e
                if attempt == retries:
                    break
                wait = min(base_delay * (2 ** attempt), max_delay)
                print(f"  ⏳ GEE band ({e}). {wait}s kutilmoqda... "
                      f"[urinish {attempt + 1}/{retries}]")
                time.sleep(wait)
        raise last_exc

    ee.ComputedObject.getInfo = getinfo_with_retry
    _installed = True
