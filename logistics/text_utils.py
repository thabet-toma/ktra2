"""Shared deal/shipment title heuristics.

Single source of truth for the "is this string English payment/legal
boilerplate?" check. Previously duplicated verbatim in
`landed_cost.py` (invoice title) and `serializers.py` (deal list
preview); the two copies were drift-prone and re-introduced exactly the
fragility T2-01 set out to remove. Mirrors the frontend
`dealTitleDisplay.isEnglishPaymentOrLegalBoilerplate`.
"""
import re

# Broad Arabic detection: base block + Supplement + Extended-A +
# Presentation Forms A/B. (The old serializers copy used only
# [؀-ۿ] and would misclassify presentation-form text.)
_AR_RE = re.compile(
    r'[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]'
)


def has_arabic(s: str) -> bool:
    return bool(s and _AR_RE.search(s))


def is_english_payment_or_legal_boilerplate(s: str) -> bool:
    """True when an all-Latin string looks like supplier payment/legal
    boilerplate (terms of payment, bank charges, deposit/balance, L/C,
    place of origin) rather than a usable deal name."""
    t = (s or '').strip()
    if not t or has_arabic(t):
        return False
    # نص إنجليزي أطول من 80 حرفاً ليس اسم صفقة أبداً — فقرات شروط/شهادات موردين
    if len(t) > 80:
        return True
    low = t.lower()
    if re.search(r'\bterms\s+of\s+payment\b', low):
        return True
    # «Trade terms: FOB…» / «Payment terms:30%…» — شروط تجارية وليست اسم صفقة
    if re.search(r'\b(?:trade|payment|price|delivery)\s+terms\b', low):
        return True
    # «30% of the payment is made in advance…» — نسب دفعات
    if (
        '%' in t
        and re.search(r'\b(?:advance|deposit|balance|payment)\b', low)
        and len(t) > 25
    ):
        return True
    # «Delivery will be within two weeks / 3 workdays…» — مدد تسليم
    if (
        re.search(r'\bdeliver', low)
        and re.search(r'\b(?:days?|weeks?|workdays?)\b', low)
        and len(t) > 25
    ):
        return True
    if re.search(r'\bplace\s+of\s+origin\b', low) and len(t) > 40:
        return True
    if re.search(r'\bbank\s+charges?\b', low) and len(t) > 20:
        return True
    if (
        re.search(r'\b(?:\d{1,2}\s*%|percent)\s*(?:deposit|advance|down)\b', low)
        and re.search(r'\b(?:before\s+)?(?:delivery|shipment)\b', low)
    ):
        return True
    if (
        re.search(r'\bdeposit\b', low)
        and re.search(r'\b(?:rest|balance|remaining)\b', low)
        and re.search(r'\bpayment\b', low)
        and len(t) > 30
    ):
        return True
    if re.search(r'\bletter\s+of\s+credit\b', low) and len(t) > 25:
        return True
    return False
