"""create_shipment_from_deals — the deal→shipment action (import redesign M1).

Fixes RC-1: the platform-standard direction is *select ready-to-ship deals →
create one shipment*, not *create an empty shipment → attach deals one by one*.
This service is that action, done atomically:

  1. validate the selected deals (tenant, unlinked, eligible stage),
  2. create the shipment with the manually-chosen chargeable unit + rate,
  3. link every deal, aggregate CBM & KG, compute total freight,
  4. allocate freight pro-rata by the chosen unit (reconciled to the penny),
  5. advance each deal READY_TO_SHIP → IN_SHIPMENT through the guarded machine.
"""
from __future__ import annotations

from decimal import Decimal
from typing import List, Optional

from django.core.exceptions import ValidationError
from django.db import transaction

from logistics.models import LogisticsDeal, LogisticsShipment, LogisticsShipmentDeal
from logistics.domain import allocation, stages

# Deal stages from which a deal may be placed onto a new shipment.
ELIGIBLE_STAGES = frozenset({
    LogisticsDeal.STAGE_DRAFT,
    LogisticsDeal.STAGE_READY_TO_SHIP,
})

# Header fields the caller may set on the shipment at creation time.
_ALLOWED_HEADER_FIELDS = frozenset({
    'shipment_name', 'shipping_agent_id', 'shipping_agent', 'shipping_type',
    'agent_shipment_number', 'bill_of_lading', 'container_number',
    'departure_date', 'arrival_date', 'international_shipping_company',
    'ship_name', 'from_term', 'to_term', 'notes', 'israeli_side_name',
})


def _unit_label(chargeable_unit: str) -> str:
    return 'الوزن (KG)' if chargeable_unit == LogisticsShipment.CHARGEABLE_KG else 'الحجم (CBM)'


def assert_deals_have_measure(deals, chargeable_unit: str) -> None:
    """Raise a clear error naming any deal missing its measure in the chosen unit.

    Without CBM/KG the pro-rata freight split is wrong (that deal silently gets a
    0 share, or the whole shipment falls back to an equal split). So when a freight
    rate is being applied we refuse and tell the user exactly which deals to fill.
    """
    missing = [
        d.ref_number for d in deals
        if allocation.deal_unit_measure(d, chargeable_unit) <= 0
    ]
    if missing:
        label = _unit_label(chargeable_unit)
        raise ValidationError(
            f"صفقات بلا {label}: {'، '.join(missing)}. "
            f"عبّئ {label} لكل صفقة أولاً حتى يُوزَّع الشحن بشكل صحيح."
        )


def create_shipment_from_deals(
    *,
    tenant,
    deal_ids: List[int],
    chargeable_unit: str,
    freight_rate=0,
    header: Optional[dict] = None,
    user=None,
) -> LogisticsShipment:
    if not deal_ids:
        raise ValidationError('اختر صفقة واحدة على الأقل لإنشاء الشحنة.')
    if chargeable_unit not in (LogisticsShipment.CHARGEABLE_CBM, LogisticsShipment.CHARGEABLE_KG):
        raise ValidationError("وحدة تسعير الشحن يجب أن تكون 'cbm' أو 'kg'.")

    ids = []
    for x in deal_ids:
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            raise ValidationError(f'معرّف صفقة غير صالح: {x!r}.')
    # Preserve caller order, drop duplicates.
    seen = set()
    ids = [i for i in ids if not (i in seen or seen.add(i))]

    rate = allocation._d(freight_rate)
    if rate < 0:
        raise ValidationError('سعر الشحن لا يمكن أن يكون سالباً.')

    header = {k: v for k, v in (header or {}).items() if k in _ALLOWED_HEADER_FIELDS}

    with transaction.atomic():
        deals = list(
            LogisticsDeal.objects.select_for_update()
            .filter(pk__in=ids, tenant=tenant)
        )
        found = {d.pk for d in deals}
        missing = [i for i in ids if i not in found]
        if missing:
            raise ValidationError(f'صفقات غير موجودة أو لا تتبع الشركة: {missing}.')

        # Refuse deals already on any shipment (a deal lives on ≤1 shipment).
        already = list(
            LogisticsShipmentDeal.objects.filter(deal_id__in=ids)
            .values_list('deal_id', 'shipment_id')
        )
        if already:
            pairs = '، '.join(f'صفقة #{d}→شحنة #{s}' for d, s in already)
            raise ValidationError(f'صفقات مربوطة بشحنة بالفعل: {pairs}.')

        # Refuse ineligible stages (e.g. already invoiced/cancelled).
        bad = [d.ref_number for d in deals if stages.derive_stage(d) not in ELIGIBLE_STAGES]
        if bad:
            raise ValidationError(
                'صفقات ليست في مرحلة تسمح بالشحن (يجب أن تكون مسودة أو جاهزة للشحن): '
                + '، '.join(bad) + '.'
            )

        # Order deals to match the caller's selection order for stable allocation.
        by_id = {d.pk: d for d in deals}
        ordered = [by_id[i] for i in ids]

        # When a freight rate is applied, every deal must carry its measure in the
        # chosen unit — otherwise the allocation is silently wrong. Guide the user.
        if rate > 0:
            assert_deals_have_measure(ordered, chargeable_unit)

        measures = [allocation.deal_unit_measure(d, chargeable_unit) for d in ordered]
        total_units = sum(measures, Decimal('0'))
        total_freight = allocation.freight_total(rate, total_units)

        total_cbm = sum((allocation._d(d.total_cbm) for d in ordered), Decimal('0'))
        total_kg = sum(
            (allocation._d(d.total_weight_kg if d.total_weight_kg is not None else d.total_weight)
             for d in ordered),
            Decimal('0'),
        )

        shipment = LogisticsShipment(
            tenant=tenant,
            chargeable_unit=chargeable_unit,
            freight_rate=rate,
            total_shipping_cost_usd=total_freight,
            total_volume=total_cbm.quantize(Decimal('0.001')),
            total_weight_kg=total_kg.quantize(Decimal('0.001')),
            # Mirror the legacy freight fields so existing landed-cost math keeps
            # working during the additive window (M2 re-sources it from chargeable_unit).
            pricing_method='unit',
            unit_type=('weight' if chargeable_unit == LogisticsShipment.CHARGEABLE_KG else 'cbm'),
            price_per_unit=rate,
            **header,
        )
        shipment.save()  # save() assigns SH-#### atomically

        alloc = allocation.allocate_freight(measures, total_freight)
        for idx, deal in enumerate(ordered):
            LogisticsShipmentDeal.objects.create(
                shipment=shipment,
                deal=deal,
                allocated_shipping_cost=alloc[idx] if idx < len(alloc) else Decimal('0'),
                extra_costs=Decimal('0'),
            )
            # Advance through the guarded machine (force: some deals may be DRAFT).
            stages.advance_deal_stage(deal, LogisticsDeal.STAGE_IN_SHIPMENT, force=True)

    return shipment
