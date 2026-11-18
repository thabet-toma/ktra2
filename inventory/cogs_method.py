from decimal import Decimal, ROUND_HALF_UP

from .models import (
    COGS_METHOD_FIFO, COGS_METHOD_LAST_PURCHASE, COGS_METHOD_STANDARD, StockLayer,
    StockMovement,
)

# DEAL وCLEARANCE من `StockMovement.IMPORT_REFERENCE_TYPES` مستبعدان: §3.3 تعرّف
# «آخر شراء» بطبقة فاتورة شراء أو استلام بضاعة أو شحنة فقط.
PURCHASE_RECEIPT_REFERENCE_TYPES = StockMovement.LOCAL_REFERENCE_TYPES + ('SHIPMENT',)
SALE_ISSUE_REFERENCE_TYPES = ('SALE', 'STOCK_ISSUE')


def is_sale_issue(movement_type, reference_type):
    return movement_type == 'OUT' and reference_type in SALE_ISSUE_REFERENCE_TYPES


def sync_fifo_snapshot(movement):
    if movement.cogs_method == COGS_METHOD_FIFO and movement.cogs_cost != movement.total_cost:
        movement.cogs_cost = movement.total_cost
        return True
    return False


def method_unit_cost(*, product, method, as_of):
    if method == COGS_METHOD_STANDARD:
        return product.standard_cost
    if method == COGS_METHOD_LAST_PURCHASE:
        return (StockLayer.objects.filter(
            tenant_id=product.tenant_id, product=product, is_provisional=False,
            source_movement__reference_type__in=PURCHASE_RECEIPT_REFERENCE_TYPES,
            layer_date__lte=as_of,
        ).order_by('-layer_date', '-id').values_list('unit_cost', flat=True).first())
    return None


def apply_sale_cogs_snapshot(movement, *, method):
    price = method_unit_cost(product=movement.product, method=method, as_of=movement.movement_date)
    if price is None:
        # avco وأيُّ طريقةٍ غير معروفة تُعامَل fifo حتى M5، وهو أيضاً السقوط لـ standard
        # بلا standard_cost ولـ last_purchase بلا شراء سابق (التحذير يرفعه المستدعي).
        movement.cogs_cost = movement.total_cost
        movement.cogs_method = COGS_METHOD_FIFO
    else:
        movement.cogs_cost = (movement.quantity * price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        movement.cogs_method = method
