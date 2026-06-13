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

# task14 M2 (DEF-A2/A4): توليد رقم صنف خادمي قصير — أرقام صرفة تسلسلية لكل شركة
SKU_PAD = 6


def generate_next_sku(tenant) -> str:
    """
    أعلى SKU رقمي-صرف للشركة + 1، بصيغة مبطّنة بالأصفار (مثل 000124).
    أرقام الهجرة القديمة (FB-…) لا تدخل في التسلسل. التفرّد النهائي يضمنه
    قيد unique(tenant, sku) — المستدعي يعيد المحاولة عند IntegrityError.
    """
    numeric_skus = (
        Product.objects.filter(tenant=tenant, sku__regex=r'^\d+$')
        .values_list('sku', flat=True)
    )
    highest = max((int(s) for s in numeric_skus), default=0)
    return str(highest + 1).zfill(SKU_PAD)


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
    branch=None,
    warehouse=None,
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
            # Sales return (RETURN_IN): preserve WAC by using current avg_cost
            if movement_type == 'RETURN_IN' and unit_cost == 0:
                unit_cost = avg_before
            new_qty = qty_before + quantity
            total_cost = quantity * unit_cost
            if new_qty > 0:
                new_avg = (
                    (qty_before * avg_before) + (quantity * unit_cost)
                ) / new_qty
            else:
                new_avg = unit_cost
        else:
            # ── Negative stock prevention (يتجاوزها allow_negative_stock على المنتج أو الإعداد العام) ──
            if qty_before < quantity:
                from sales.models import SalesSettings
                ss = SalesSettings.objects.filter(tenant_id=tenant.TenantID if tenant else prod.tenant_id).first()
                global_allow = ss.allow_negative_stock_default if ss else True

                # Allow if either global default is true, or product explicitly allows it
                allow_negative = global_allow or bool(getattr(prod, "allow_negative_stock", False))
                if not allow_negative:
                    raise ValidationError(
                        f"لا يمكن صرف {quantity} من الصنف «{prod.sku}» — "
                        f"الرصيد المتاح: {qty_before}. "
                        f"تأكد من استلام البضاعة أولاً أو قم بتسوية المخزون."
                    )
                else:
                    logger.warning(
                        "NEGATIVE STOCK ALLOWED: product=%s sku=%s qty_before=%s outbound=%s",
                        prod.pk, prod.sku, qty_before, quantity,
                    )

            new_qty = qty_before - quantity
            total_cost = quantity * avg_before
            unit_cost = avg_before
            new_avg = avg_before

        new_qty = new_qty.quantize(Decimal('0.0001'))
        new_avg = new_avg.quantize(Decimal('0.0001'))
        total_cost = total_cost.quantize(Decimal('0.01'))

        movement = StockMovement.objects.create(
            tenant=tenant or prod.tenant,
            branch=branch,
            warehouse=warehouse,
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

    تكلفة الاستلام (unit_cost) تُحدَّد بترتيب الأولوية:
      1) landed_unit_price_ils من PurchaseInvoiceItem للصفقة/الشحنة (إن وُجد فاتورة شراء
         مُستَوردة من التخليص الجمركي) — هذه هي التكلفة الحقيقية النازلة.
      2) unit_price من LogisticsDealItem (سعر الصفقة الأصلي) — احتياطي إن لم تتم الفوترة بعد.

    ملاحظة محاسبية: هذه الدالة تُحدّث WAC (متوسط التكلفة) في المخزون الفرعي (Subledger) فقط.
    القيد المحاسبي في GL (Dr Inventory / Cr AP) يُنشأ من PurchaseInvoice.post_to_accounting.
    لذا ينبغي استيراد فاتورة الشراء قبل إكمال "Cleared" للحصول على landed cost.
    """
    import datetime
    from decimal import Decimal
    from logistics.models import LogisticsShipmentDeal, PurchaseInvoice, PurchaseInvoiceItem

    if movement_date is None:
        movement_date = shipment.arrival_date or datetime.date.today()

    links = LogisticsShipmentDeal.objects.filter(
        shipment=shipment,
    ).select_related('deal', 'deal__partner')

    created = []
    for link in links:
        deal = link.deal

        # محاولة إيجاد فاتورة شراء لهذه الصفقة/الشحنة — تحتوي على landed_unit_price_ils
        pi_items_by_product: dict[int, PurchaseInvoiceItem] = {}
        pi = (
            PurchaseInvoice.objects
            .filter(tenant=deal.tenant, shipment=shipment, deal=deal)
            .prefetch_related('items')
            .first()
        )
        if pi:
            for pi_item in pi.items.all():
                if pi_item.product_id:
                    pi_items_by_product[pi_item.product_id] = pi_item

        items = deal.items.select_related('product').filter(is_deleted=False)
        for item in items:
            # Idempotency key includes deal to handle same product across multiple deals
            existing = StockMovement.objects.filter(
                reference_type='SHIPMENT',
                reference_id=shipment.pk,
                product=item.product,
                notes__contains=f"صفقة {deal.ref_number}",
            ).exists()
            if existing:
                continue

            # تحديد تكلفة الوحدة — أفضلية لـ landed cost
            pi_item = pi_items_by_product.get(item.product_id) if item.product_id else None
            landed = None
            if pi_item and pi_item.landed_unit_price_ils is not None:
                try:
                    landed = Decimal(str(pi_item.landed_unit_price_ils))
                    if landed <= 0:
                        landed = None
                except Exception:
                    landed = None

            unit_cost = landed if landed else Decimal(str(item.unit_price or 0))
            cost_source = "landed" if landed else "deal_unit_price"

            mv = record_stock_movement(
                product=item.product,
                movement_type='IN',
                quantity=item.quantity,
                unit_cost=unit_cost,
                reference_type='SHIPMENT',
                reference_id=shipment.pk,
                partner=deal.partner,
                movement_date=movement_date,
                notes=(
                    f"شحنة {shipment.shipment_number} | صفقة {deal.ref_number} "
                    f"| تكلفة: {cost_source}"
                ),
                tenant=deal.tenant,
            )
            created.append(mv)

    return created


def warn_landed_cost_mismatch(purchase_invoice):
    """تحذير فقط (لا تسويات تلقائية خطيرة): إن كانت فاتورة الشراء وُرِّدت بعد أن سُلِّمت
    الشحنة (stock IN سُجِّل بسعر الصفقة بدل landed)، نُسجّل تحذيراً في السجلات ليقوم
    المستخدم بمراجعة متوسط التكلفة يدوياً.

    يمكن استدعاؤها من PurchaseInvoice.post_to_accounting لتنبيه المحاسب.
    """
    from decimal import Decimal

    if not purchase_invoice or not purchase_invoice.shipment_id:
        return []

    warnings = []
    for pi_item in purchase_invoice.items.select_related('product').all():
        if not pi_item.product_id or pi_item.landed_unit_price_ils is None:
            continue
        try:
            landed = Decimal(str(pi_item.landed_unit_price_ils))
        except Exception:
            continue
        if landed <= 0:
            continue
        mv = StockMovement.objects.filter(
            reference_type='SHIPMENT',
            reference_id=purchase_invoice.shipment_id,
            product_id=pi_item.product_id,
            movement_type='IN',
        ).order_by('-id').first()
        if not mv:
            continue
        current_cost = Decimal(str(mv.unit_cost or 0))
        diff = (landed - current_cost).quantize(Decimal('0.0001'))
        if abs(diff) < Decimal('0.01'):
            continue
        logger.warning(
            "Landed cost mismatch for product %s (shipment=%s): "
            "landed=%s vs recorded=%s. المخزون سُجِّل قبل استيراد فاتورة الشراء؛ "
            "راجع حركة المخزون لتصحيح متوسط التكلفة.",
            pi_item.product_id, purchase_invoice.shipment_id, landed, current_cost,
        )
        warnings.append({
            'product_id': pi_item.product_id,
            'shipment_id': purchase_invoice.shipment_id,
            'landed': str(landed),
            'recorded': str(current_cost),
        })
    return warnings


def _resolve_line_account(product, account_type='revenue', *, tenant_id=None):
    """P-H-7: يحلّ الحساب المحاسبي لصنف/بند المخزون بسلسلة أولويات.

    1. Product-level override (حسب account_type)
    2. Category-level account
    3. Settings default (SalesSettings)
    4. Hardcoded fallback (أول حساب نشيط حسب النوع/الكود)

    account_type: 'revenue' | 'cogs' | 'inventory' | 'purchase'
    Returns: Account instance
    Raises: ValidationError if not found
    """
    from accounting.models import Account
    from sales.models import SalesSettings

    tid = tenant_id or (product.tenant_id if hasattr(product, 'tenant_id') else None)

    # ── Level 1: Product-level override ──────────────────────────
    override_map = {
        'revenue': 'sale_account_override',
        'cogs': None,  # not overridable per product
        'inventory': 'ending_inventory_account_override',
        'purchase': 'purchase_account_override',
    }
    override_field = override_map.get(account_type)
    if override_field:
        val = getattr(product, override_field, None)
        if val is not None:
            return val

    # ── Level 2: Category-level account ──────────────────────────
    cat = getattr(product, 'category', None)
    if cat:
        cat_field_map = {
            'revenue': 'revenue_account',
            'cogs': 'cogs_account',
            'inventory': 'inventory_account',
            'purchase': 'inventory_account',  # purchases use inventory account
        }
        cat_field = cat_field_map.get(account_type)
        if cat_field:
            val = getattr(cat, cat_field, None)
            if val is not None:
                return val

    # ── Level 3: Settings default ────────────────────────────────
    if tid:
        ss = SalesSettings.objects.filter(tenant_id=tid).first()
        if ss:
            ss_field_map = {
                'revenue': 'default_revenue_account_product',
                'cogs': 'default_cogs_account',
                'inventory': 'default_inventory_account',
                'purchase': 'default_inventory_account',
            }
            ss_field = ss_field_map.get(account_type)
            if ss_field:
                val = getattr(ss, ss_field, None)
                if val is not None:
                    return val

    # ── Level 4: Hardcoded fallback ──────────────────────────────
    code_fallbacks = {
        'revenue': '4101',
        'cogs': '5101',
        'inventory': '1104',
        'purchase': '1104',
    }
    fb_code = code_fallbacks.get(account_type)
    if fb_code and tid:
        acc = Account.objects.filter(tenant_id=tid, code=fb_code).first()
        if acc:
            return acc

    # Last resort: any matching account type
    type_fallbacks = {
        'revenue': 'Revenue',
        'cogs': 'Expense',
        'inventory': 'Asset',
        'purchase': 'Asset',
    }
    fb_type = type_fallbacks.get(account_type)
    if fb_type and tid:
        acc = Account.objects.filter(tenant_id=tid, account_type=fb_type, is_active=True).first()
        if acc:
            return acc

    raise ValidationError(
        f"لم يُعثر على حساب {account_type} للصنف «{product.sku or product.name}». "
        "حدد حساباً للصنف أو للتصنيف أو في إعدادات المبيعات."
    )
