from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db.models.functions import Coalesce

from .models import (
    COGS_METHOD_AVCO, COGS_METHOD_FIFO, COGS_METHOD_LAST_PURCHASE, COGS_METHOD_STANDARD, StockLayer,
    StockMovement,
)

# DEAL وCLEARANCE من `StockMovement.IMPORT_REFERENCE_TYPES` مستبعدان: §3.3 تعرّف
# «آخر شراء» بطبقة فاتورة شراء أو استلام بضاعة أو شحنة فقط.
PURCHASE_RECEIPT_REFERENCE_TYPES = StockMovement.LOCAL_REFERENCE_TYPES + ('SHIPMENT',)
SALE_ISSUE_REFERENCE_TYPES = ('SALE', 'STOCK_ISSUE')
FIXED_SNAPSHOT_METHODS = (COGS_METHOD_STANDARD, COGS_METHOD_LAST_PURCHASE)
MISSING_COST_VARIANCE_ACCOUNT_ERROR = "عيّن حساب فروقات تكلفة المبيعات في إعدادات المبيعات."


def cost_variance_account_id(tenant_id):
    """حساب فروقات تكلفة المبيعات للشركة — يُستدعى فقط عند وجود فرق للقطة ثابتة."""
    from sales.models import SalesSettings

    account_id = (
        SalesSettings.objects.filter(tenant_id=tenant_id)
        .values_list('cost_variance_account_id', flat=True)
        .first()
    )
    if account_id is None:
        raise ValidationError(MISSING_COST_VARIANCE_ACCOUNT_ERROR)
    return account_id


def tenant_cogs_method(tenant_id) -> str:
    """طريقة احتساب تكلفة المبيعات للشركة — السقوط إلى FIFO عند غياب صفّ الإعدادات."""
    if not tenant_id:
        return COGS_METHOD_FIFO
    from sales.models import SalesSettings

    method = (
        SalesSettings.objects.filter(tenant_id=tenant_id)
        .values_list('cogs_cost_method', flat=True)
        .first()
    )
    return method or COGS_METHOD_FIFO


def is_sale_issue(movement_type, reference_type):
    return movement_type == 'OUT' and reference_type in SALE_ISSUE_REFERENCE_TYPES


def effective_cogs_expression():
    """أساس تكلفة البيع — تكلفة الطريقة الملتقَطة مع السقوط إلى كلفة المخزون الفعلية للحركات القديمة."""
    return Coalesce("cogs_cost", "total_cost")


def sync_fifo_snapshot(movement):
    if movement.cogs_method == COGS_METHOD_FIFO and movement.cogs_cost != movement.total_cost:
        movement.cogs_cost = movement.total_cost
        return True
    return False


def last_purchase_unit_costs(*, tenant_id, product_ids, as_of) -> dict[int, Decimal]:
    """تكلفة الوحدة من آخر طبقة استلام شراء غير مؤقتة حتى `as_of` لكل منتج — استعلامٌ واحد.

    `product_ids=None` يقرأ كل منتجات الشركة؛ قائمةٌ فارغة ⇒ `{}` بلا استعلام.
    """
    if not tenant_id:
        return {}
    qs = StockLayer.objects.filter(
        tenant_id=tenant_id,
        is_provisional=False,
        source_movement__reference_type__in=PURCHASE_RECEIPT_REFERENCE_TYPES,
        layer_date__lte=as_of,
    )
    if product_ids is not None:
        ids = [pid for pid in product_ids if pid is not None]
        if not ids:
            return {}
        qs = qs.filter(product_id__in=ids)
    rows = (
        qs.order_by('product_id', '-layer_date', '-id')
        .values_list('product_id', 'unit_cost')
    )
    result: dict[int, Decimal] = {}
    for pid, unit_cost in rows:
        result.setdefault(pid, unit_cost)
    return result


def method_unit_cost(*, product, method, as_of):
    if method == COGS_METHOD_STANDARD:
        return product.standard_cost
    if method == COGS_METHOD_LAST_PURCHASE:
        return last_purchase_unit_costs(
            tenant_id=product.tenant_id,
            product_ids=[product.pk],
            as_of=as_of,
        ).get(product.pk)
    return None


def apply_sale_cogs_snapshot(movement, *, method):
    price = method_unit_cost(product=movement.product, method=method, as_of=movement.movement_date)
    if price is None:
        # يستخدم AVCO قيمة الطبقات المستهلكة؛ وعند غياب السعر الثابت أو جهل الطريقة يُستخدم FIFO.
        # يرفع المستدعي التحذير عند غياب التكلفة المعيارية أو شراء سابق.
        movement.cogs_cost = movement.total_cost
        movement.cogs_method = COGS_METHOD_AVCO if method == COGS_METHOD_AVCO else COGS_METHOD_FIFO
    else:
        movement.cogs_cost = (movement.quantity * price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        movement.cogs_method = method


def build_cogs_adjustment_lines(
    *,
    cogs_diff: Decimal,
    variance_diff: Decimal,
    inv_diff: Decimal,
    cogs_account_id: int | None,
    variance_account_id: int | None,
    inv_account_id: int | None,
    cogs_description: str,
    variance_description: str,
    inv_description: str,
) -> list[dict]:
    """يبني أسطر قيد تسوية COGS/فروقات/مخزون بالمدين أولاً ثم الدائن، بلا سطر صفري."""
    # الإشارة على المخزون معكوسة عن المصروف: زيادة التكلفة تُنقص المخزون (دائن).
    entries = [
        (cogs_account_id, cogs_diff, cogs_description),
        (variance_account_id, variance_diff, variance_description),
        (inv_account_id, -inv_diff, inv_description),
    ]
    debits = [
        {'account': acc_id, 'debit': amt, 'credit': Decimal('0'), 'description': desc}
        for acc_id, amt, desc in entries if amt > 0
    ]
    credits = [
        {'account': acc_id, 'debit': Decimal('0'), 'credit': -amt, 'description': desc}
        for acc_id, amt, desc in entries if amt < 0
    ]
    return debits + credits
