"""The single cost-allocation engine (import redesign M0/M2).

Pure Decimal arithmetic, no ORM writes. Guarantees allocated amounts sum back to
the total with zero leakage via the **largest-remainder** method: floor every
share to the penny, then hand the leftover pennies to the shares with the biggest
fractional remainder. This is fairer than dumping all drift on the last line and
still holds the invariant  Σ allocated ≡ total  exactly.

Freight uses the manually-chosen chargeable unit (CBM or KG). Customs uses value.
Each basis is explicit here and labeled in the UI — no hidden inference (RC-5).
"""
from __future__ import annotations

from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from typing import List

Q2 = Decimal('0.01')
Q4 = Decimal('0.0001')
PENNY = Decimal('0.01')


def _d(x, default: str = '0') -> Decimal:
    if x is None:
        return Decimal(default)
    if isinstance(x, Decimal):
        return x
    try:
        return Decimal(str(x))
    except Exception:
        return Decimal(default)


def quantize_money(x: Decimal) -> Decimal:
    return _d(x).quantize(Q2, rounding=ROUND_HALF_UP)


def reconcile(total, weights: List[Decimal]) -> List[Decimal]:
    """Distribute `total` across `weights` so the parts sum to `total` exactly.

    Largest-remainder apportionment at penny granularity. Zero/negative weight
    sum falls back to an equal split (pennies still reconciled).
    """
    total = _d(total).quantize(Q2, rounding=ROUND_HALF_UP)
    n = len(weights)
    if n == 0:
        return []
    ws = [_d(w) for w in weights]
    wsum = sum(ws, Decimal('0'))
    if wsum <= 0:
        ws = [Decimal('1')] * n
        wsum = Decimal(n)

    raw = [total * w / wsum for w in ws]
    floors = [r.quantize(Q2, rounding=ROUND_DOWN) for r in raw]
    allocated = sum(floors, Decimal('0'))
    # Number of leftover pennies to hand out (can be 0).
    leftover = int(((total - allocated) / PENNY).to_integral_value(rounding=ROUND_HALF_UP))
    if leftover > 0:
        # Rank by fractional remainder desc; ties broken by original order (stable).
        order = sorted(range(n), key=lambda i: (raw[i] - floors[i]), reverse=True)
        for k in range(leftover):
            floors[order[k % n]] += PENNY
    return [f.quantize(Q2, rounding=ROUND_HALF_UP) for f in floors]


def freight_total(rate, total_units) -> Decimal:
    """Freight total = rate × Σ(chosen chargeable unit)."""
    return quantize_money(_d(rate) * _d(total_units))


def allocate_freight(unit_measures: List[Decimal], total) -> List[Decimal]:
    """Allocate `total` freight pro-rata by each deal's share of the chosen unit."""
    return reconcile(total, [_d(u) for u in unit_measures])


# ── Chargeable-unit resolution (single source; used by freight everywhere) ──
CHARGEABLE_CBM = 'cbm'
CHARGEABLE_KG = 'kg'


def resolve_chargeable_unit(shipment) -> str:
    """The freight chargeable unit for a shipment, explicit field first.

    Falls back to the legacy pricing_method×unit_type triad during the additive
    window (unit+weight → KG; everything else, incl. the orphan 'container' → CBM),
    so freight math is identical before and after backfill.
    """
    cu = (getattr(shipment, 'chargeable_unit', None) or '').lower()
    if cu in (CHARGEABLE_CBM, CHARGEABLE_KG):
        return cu
    method = (getattr(shipment, 'pricing_method', None) or 'total').lower()
    utype = (getattr(shipment, 'unit_type', None) or 'cbm').lower()
    if method == 'unit' and utype == 'weight':
        return CHARGEABLE_KG
    return CHARGEABLE_CBM


def deal_unit_measure(deal, chargeable_unit: str) -> Decimal:
    """A deal's quantity in the chosen chargeable unit (KG falls back to gross weight)."""
    if chargeable_unit == CHARGEABLE_KG:
        wkg = getattr(deal, 'total_weight_kg', None)
        if wkg is None:
            wkg = getattr(deal, 'total_weight', None)
        return _d(wkg)
    return _d(getattr(deal, 'total_cbm', None))


def proportional_shares(weights: List[Decimal]) -> List[Decimal]:
    """Fractional shares (each weight ÷ Σ weights), 4dp; equal split if Σ ≤ 0."""
    ws = [_d(w) for w in weights]
    wsum = sum(ws, Decimal('0'))
    n = len(ws)
    if n == 0:
        return []
    if wsum <= 0:
        return [(Decimal('1') / Decimal(n)).quantize(Q4, rounding=ROUND_HALF_UP)] * n
    return [(w / wsum).quantize(Q4, rounding=ROUND_HALF_UP) for w in ws]
