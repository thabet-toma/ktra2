"""Inland transport as the single landed-cost source (import redesign, Q2).

Today inland (local haulage) can reach landed cost two ways — a clearance line
labelled «شحن محلي» (allocated by deal *value*), or a capitalized LocalShipment
(a separate GL posting) — with a supersede guard stopping the double-count. The
target is one source: the **Transport (LocalShipment) row**, allocated on the same
**chargeable unit** as freight (inland is a haulage cost, so CBM/KG is the right
basis, not value).

This module computes both the OLD and the NEW deal-level inland allocation so the
owner can review the delta on sample and real data before we flip the live path.
Nothing here changes the live invoice math yet — it is comparison-only until approved.
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List

from logistics.models import LocalShipment
from logistics import landed_cost as lc

Q2 = Decimal('0.01')


def transport_pool_ils(shipment, clearance=None) -> Decimal:
    """Total inland cost (ILS) from Transport rows linked to this shipment/clearance.

    Sums LocalShipment.amount × exchange_rate for capitalized, non-cancelled rows.
    Prefers clearance link; falls back to the shipment link.
    """
    qs = LocalShipment.objects.filter(capitalize_to_inventory=True).exclude(status='cancelled')
    if clearance is not None:
        qs = qs.filter(clearance=clearance)
    elif shipment is not None:
        qs = qs.filter(shipment=shipment)
    else:
        return Decimal('0')
    total = Decimal('0')
    for ls in qs:
        amt = lc._d(ls.amount)
        rate = lc._d(ls.exchange_rate, '1') or Decimal('1')
        total += (amt * rate)
    return total.quantize(Q2, rounding=ROUND_HALF_UP)


def deal_inland_new_ils(deal, shipment, clearance) -> Decimal:
    """NEW: deal's inland = Transport pool × the deal's chargeable-unit share (freight basis)."""
    pool = transport_pool_ils(shipment, clearance)
    share = lc.deal_volume_share_on_shipment(deal, shipment)  # CBM/KG share
    return (pool * share).quantize(Q2, rounding=ROUND_HALF_UP)


def deal_inland_old_ils(deal, shipment, clearance) -> Decimal:
    """OLD: deal's inland = clearance «شحن محلي»/carrier lines × the deal's value share
    (honoring the supersede guard that zeroes it when a capitalized Transport exists)."""
    pool = lc.sum_clearance_logistics_for_landed_share_ils(clearance)
    share = lc.deal_share_on_shipment(deal, shipment)  # value share
    return (pool * share).quantize(Q2, rounding=ROUND_HALF_UP)


def reconcile_shipment(shipment, clearance, *, deal_remaining_rate=Decimal('3.6'),
                       shipment_remaining_rate=Decimal('3.6'), use_cost_lines=False) -> List[Dict]:
    """Per-deal OLD vs NEW landed comparison for one shipment+clearance.

    Returns a row per linked deal with merch/freight/customs held constant and only
    the inland component (source + basis) changing, so the delta isolates the effect
    of making Transport the single inland source.
    """
    from logistics.models import LogisticsShipmentDeal
    rows: List[Dict] = []
    links = LogisticsShipmentDeal.objects.filter(shipment=shipment).select_related('deal')
    clr_pool, _src = lc.clearance_pool_ils(clearance, use_cost_lines, shipment_remaining_rate) if clearance else (Decimal('0'), 'none')
    for link in links:
        deal = link.deal
        deal_val_ils, *_ = lc.deal_total_ils(deal, deal_remaining_rate)
        share_value = lc.deal_share_on_shipment(deal, shipment)
        share_unit = lc.deal_volume_share_on_shipment(deal, shipment)
        freight = lc._d(link.allocated_shipping_cost)  # USD allocation (freight basis)
        customs = (clr_pool * share_value).quantize(Q2, rounding=ROUND_HALF_UP) if clearance else Decimal('0')
        inland_old = deal_inland_old_ils(deal, shipment, clearance) if clearance else Decimal('0')
        inland_new = deal_inland_new_ils(deal, shipment, clearance) if clearance else Decimal('0')
        rows.append({
            'deal_id': deal.id,
            'ref_number': deal.ref_number,
            'merch_ils': deal_val_ils,
            'customs_ils': customs,
            'inland_old_ils': inland_old,
            'inland_new_ils': inland_new,
            'inland_delta_ils': (inland_new - inland_old).quantize(Q2, rounding=ROUND_HALF_UP),
            'share_value': share_value,
            'share_unit': share_unit,
        })
    return rows
