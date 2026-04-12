"""
Inventory services: stock movement recording with WAC (Weighted Average Cost).

All stock changes go through record_stock_movement() which:
1. Creates a StockMovement row with before/after snapshots
2. Updates Product.quantity_on_hand and Product.avg_cost atomically
"""
import logging
from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError

from .models import Product, StockMovement

logger = logging.getLogger(__name__)

INBOUND_TYPES = {'IN', 'ADJUST_IN', 'RETURN_IN'}
OUTBOUND_TYPES = {'OUT', 'ADJUST_OUT', 'RETURN_OUT'}


def record_stock_movement(
    *,
    product: Product,
    movement_type: str,
    quantity: Decimal,
    unit_cost: Decimal = Decimal('0'),
    reference_type: str = 'MANUAL',
    reference_id: int | None = None,
    partner=None,
    movement_date,
    notes: str = '',
    tenant=None,
) -> StockMovement:
    """
    Record a stock movement and update Product stock/cost atomically.

    WAC formula (inbound):
        new_avg = (old_qty * old_avg + incoming_qty * incoming_cost) / new_qty

    Outbound movements use existing avg_cost (no change to avg_cost).
    """
    quantity = Decimal(str(quantity))
    unit_cost = Decimal(str(unit_cost))

    if quantity <= 0:
        raise ValidationError("الكمية يجب أن تكون أكبر من صفر")

    valid_types = {c[0] for c in StockMovement.MOVEMENT_TYPES}
    if movement_type not in valid_types:
        raise ValidationError(f"نوع الحركة غير صالح: {movement_type}")

    with transaction.atomic():
        prod = Product.objects.select_for_update().get(pk=product.pk)

        qty_before = Decimal(str(prod.quantity_on_hand))
        avg_before = Decimal(str(prod.avg_cost))

        if movement_type in INBOUND_TYPES:
            new_qty = qty_before + quantity
            total_cost = quantity * unit_cost
            if new_qty > 0:
                new_avg = (
                    (qty_before * avg_before) + (quantity * unit_cost)
                ) / new_qty
            else:
                new_avg = unit_cost
        else:
            new_qty = qty_before - quantity
            total_cost = quantity * avg_before
            unit_cost = avg_before
            new_avg = avg_before

        new_qty = new_qty.quantize(Decimal('0.0001'))
        new_avg = new_avg.quantize(Decimal('0.0001'))
        total_cost = total_cost.quantize(Decimal('0.01'))

        movement = StockMovement.objects.create(
            tenant=tenant or prod.tenant,
            product=prod,
            movement_type=movement_type,
            quantity=quantity,
            unit_cost=unit_cost,
            total_cost=total_cost,
            reference_type=reference_type,
            reference_id=reference_id,
            partner=partner,
            movement_date=movement_date,
            notes=notes or '',
            quantity_before=qty_before,
            quantity_after=new_qty,
            avg_cost_before=avg_before,
            avg_cost_after=new_avg,
        )

        prod.quantity_on_hand = new_qty
        prod.avg_cost = new_avg
        prod.save(update_fields=['quantity_on_hand', 'avg_cost'])

        logger.info(
            "Stock movement #%d: %s %s of product %s (%s → %s)",
            movement.id, movement_type, quantity,
            prod.sku, qty_before, new_qty,
        )

    return movement


def receive_shipment_stock(shipment, movement_date=None):
    """
    Create IN movements for all deal items in a cleared shipment.
    Called when shipment status changes to Cleared.
    Returns list of created StockMovement objects.
    """
    import datetime
    from logistics.models import LogisticsShipmentDeal

    if movement_date is None:
        movement_date = shipment.arrival_date or datetime.date.today()

    links = LogisticsShipmentDeal.objects.filter(
        shipment=shipment,
    ).select_related('deal', 'deal__partner')

    created = []
    for link in links:
        deal = link.deal
        items = deal.items.select_related('product').filter(is_deleted=False)
        for item in items:
            existing = StockMovement.objects.filter(
                reference_type='SHIPMENT',
                reference_id=shipment.pk,
                product=item.product,
            ).exists()
            if existing:
                continue

            mv = record_stock_movement(
                product=item.product,
                movement_type='IN',
                quantity=item.quantity,
                unit_cost=item.unit_price,
                reference_type='SHIPMENT',
                reference_id=shipment.pk,
                partner=deal.partner,
                movement_date=movement_date,
                notes=f"شحنة {shipment.shipment_number} | صفقة {deal.ref_number}",
                tenant=deal.tenant,
            )
            created.append(mv)

    return created
