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


def _recompute_product_stock(product: Product) -> None:
    """أعد احتساب الرصيد ومتوسط التكلفة لصنف بإعادة تشغيل كل حركاته المتبقية.

    تُستدعى بعد حذف حركات مستند ما (إلغاء الترحيل/الحذف) لتعيد ضبط
    quantity_on_hand و avg_cost بدقة بغضّ النظر عن ترتيب الحركات — بدلاً من
    تعديل تقريبي قد يفسد متوسط التكلفة (WAC). تُطبّق نفس معادلة
    record_stock_movement بالترتيب الزمني (التاريخ ثم المعرّف).
    """
    with transaction.atomic():
        prod = Product.objects.select_for_update().get(pk=product.pk)
        movements = (
            StockMovement.objects.filter(product=prod)
            .order_by('movement_date', 'id')
        )
        qty = Decimal('0')
        avg = Decimal('0')
        for m in movements:
            mqty = Decimal(str(m.quantity))
            munit = Decimal(str(m.unit_cost or 0))
            if m.movement_type in INBOUND_TYPES:
                new_qty = qty + mqty
                if new_qty > 0:
                    avg = ((qty * avg) + (mqty * munit)) / new_qty
                else:
                    avg = munit
                qty = new_qty
            else:
                qty = qty - mqty
                # avg_cost لا يتغيّر بحركات الصرف (متطابق مع record_stock_movement)
        prod.quantity_on_hand = qty.quantize(Decimal('0.0001'))
        prod.avg_cost = avg.quantize(Decimal('0.0001'))
        prod.save(update_fields=['quantity_on_hand', 'avg_cost'])


def reverse_stock_movements(*, tenant_id, reference_id, reference_types) -> int:
    """احذف حركات المخزون التي ولّدها مستند معيّن وأعد احتساب أرصدة أصنافه.

    تُستخدم في «إلغاء الترحيل»/الحذف لإرجاع المخزون لما كان عليه قبل المستند.
    النطاق محصور تماماً بـ (tenant, reference_id, reference_type ∈ reference_types)
    فلا تُمَسّ حركات أي مستند آخر. تُرجع عدد الحركات المحذوفة.
    """
    if not reference_types:
        return 0
    movements = list(
        StockMovement.objects.filter(
            tenant_id=tenant_id,
            reference_id=reference_id,
            reference_type__in=list(reference_types),
        ).select_related('product')
    )
    if not movements:
        return 0
    affected_products = {m.product_id: m.product for m in movements}
    count = len(movements)
    StockMovement.objects.filter(id__in=[m.id for m in movements]).delete()
    for prod in affected_products.values():
        _recompute_product_stock(prod)
    logger.info(
        "reverse_stock_movements: deleted %d movements ref=%s types=%s products=%d",
        count, reference_id, list(reference_types), len(affected_products),
    )
    return count


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


# ──────────────────────────────────────────────────────────────────────────
# FEAT-3 — Product profile (KPIs + linked invoices + stock ledger)
# ──────────────────────────────────────────────────────────────────────────
def product_profile(*, tenant_id: int, product_id: int) -> dict:
    """Header KPIs for the product profile. Totals come from posted documents;
    on-hand / valuation come from the canonical Product fields (A4)."""
    from django.db.models import Sum

    from logistics.models import PurchaseInvoiceItem
    from sales.models import SalesInvoice, SalesInvoiceLine

    p = Product.objects.select_related('category').get(id=product_id, tenant_id=tenant_id)

    purchased = PurchaseInvoiceItem.objects.filter(
        invoice__tenant_id=tenant_id, invoice__is_posted=True, product_id=product_id,
    ).aggregate(q=Sum('quantity'), v=Sum('total_price'))
    sold = SalesInvoiceLine.objects.filter(
        tenant_id=tenant_id, product_id=product_id,
        invoice__status=SalesInvoice.STATUS_POSTED,
        invoice__invoice_kind=SalesInvoice.INVOICE_KIND_SALE,
    ).aggregate(q=Sum('quantity'), v=Sum('line_total_excl_tax'))

    on_hand = Decimal(str(p.quantity_on_hand or 0))
    avg_cost = Decimal(str(p.avg_cost or 0))
    return {
        'id': p.id,
        'sku': p.sku,
        'name': p.name_ar or p.name_en or p.sku,
        'category': p.category.name if p.category_id else None,
        'quantity_on_hand': str(on_hand),
        'avg_cost': str(avg_cost),
        'inventory_valuation': str((on_hand * avg_cost).quantize(Decimal('0.01'))),
        'purchased_qty': str(purchased['q'] or 0),
        'purchased_value': str(purchased['v'] or 0),
        'sold_qty': str(sold['q'] or 0),
        'sold_value': str(sold['v'] or 0),
    }


_STOCK_IN_TYPES = {'IN', 'ADJUST_IN', 'RETURN_IN'}


def product_stock_ledger(*, tenant_id: int, product_id: int, limit: int = 50, offset: int = 0) -> dict:
    """Chronological stock ledger for a product, with a running balance per row.

    The running balance reuses the movement's stored `quantity_after` — the
    canonical per-product on-hand after that movement — so it reconciles exactly
    to current stock (A4) without a parallel computation. Paginated.
    """
    base = (
        StockMovement.objects.filter(tenant_id=tenant_id, product_id=product_id)
        .select_related('warehouse')
        .order_by('movement_date', 'id')
    )
    total = base.count()
    rows = []
    for m in base[offset:offset + limit]:
        qty = Decimal(str(m.quantity or 0))
        is_in = m.movement_type in _STOCK_IN_TYPES
        rows.append({
            'id': m.id,
            'date': m.movement_date.isoformat() if m.movement_date else None,
            'movement_type': m.movement_type,
            'movement_type_label': m.get_movement_type_display(),
            'reference_type': m.reference_type,
            'reference_id': m.reference_id,
            'warehouse': m.warehouse.name if m.warehouse_id else None,
            'qty_in': str(qty) if is_in else '0',
            'qty_out': str(qty) if not is_in else '0',
            'running_balance': str(m.quantity_after),
        })
    return {'results': rows, 'count': total, 'limit': limit, 'offset': offset}


def product_linked_invoices(*, tenant_id: int, product_id: int) -> list[dict]:
    """All purchase + sales invoices that contain this product (clickable)."""
    from logistics.models import PurchaseInvoiceItem
    from sales.models import SalesInvoiceLine

    out: list[dict] = []
    pis = (
        PurchaseInvoiceItem.objects.filter(
            invoice__tenant_id=tenant_id, product_id=product_id,
        )
        .select_related('invoice', 'invoice__partner')
        .order_by('-invoice__invoice_date', '-invoice_id')
    )
    seen_p = set()
    for it in pis:
        if it.invoice_id in seen_p:
            continue
        seen_p.add(it.invoice_id)
        inv = it.invoice
        out.append({
            'document_type': 'PURCHASE_INVOICE',
            'document_id': inv.id,
            'document_number': inv.invoice_number,
            'date': inv.invoice_date.isoformat() if inv.invoice_date else None,
            'party': inv.partner.name if inv.partner_id else None,
            'is_posted': bool(inv.is_posted),
        })
    sls = (
        SalesInvoiceLine.objects.filter(tenant_id=tenant_id, product_id=product_id)
        .select_related('invoice', 'invoice__customer')
        .order_by('-invoice__invoice_date', '-invoice_id')
    )
    seen_s = set()
    for ln in sls:
        if ln.invoice_id in seen_s:
            continue
        seen_s.add(ln.invoice_id)
        inv = ln.invoice
        out.append({
            'document_type': 'SALES_INVOICE',
            'document_id': inv.id,
            'document_number': inv.invoice_number,
            'date': inv.invoice_date.isoformat() if inv.invoice_date else None,
            'party': inv.customer.name if inv.customer_id else None,
            'is_posted': inv.status == 'posted',
        })
    return out


# ════════════════════════════════════════════════════════════════════
# Phase 7 (T-I1/T-I2): ترحيل مستندات المخزون — تحويل + جرد
# ════════════════════════════════════════════════════════════════════

def _next_doc_number(tenant_id, model, field, prefix):
    """رقم تسلسلي بسيط لكل شركة: PREFIX-0001 (مرآة منطق توليد SKU)."""
    last = (
        model.objects.filter(tenant_id=tenant_id)
        .exclude(**{f'{field}': ''})
        .order_by('-id')
        .values_list(field, flat=True)
        .first()
    )
    n = 0
    if last:
        try:
            n = int(str(last).split('-')[-1])
        except (ValueError, IndexError):
            n = model.objects.filter(tenant_id=tenant_id).count()
    return f"{prefix}-{n + 1:04d}"


def post_warehouse_transfer(transfer, user=None):
    """T-I1: يرحّل تحويلاً بين مستودعين — صرف من المصدر + استلام في الوجهة بالتكلفة
    المتوسطة. صافي الأثر على إجمالي المخزون/المتوسط = صفر (نقل موقعي). لا قيد محاسبي."""
    from .models import WarehouseTransfer
    if transfer.is_posted:
        raise ValidationError("التحويل مُرحَّل مسبقاً.")
    if transfer.source_warehouse_id == transfer.dest_warehouse_id:
        raise ValidationError("مستودع المصدر والوجهة متطابقان.")
    lines = list(transfer.lines.select_related('product').all())
    if not lines:
        raise ValidationError("أضف بنداً واحداً على الأقل.")

    with transaction.atomic():
        if not transfer.transfer_number:
            transfer.transfer_number = _next_doc_number(
                transfer.tenant_id, WarehouseTransfer, 'transfer_number', 'TRF')
        for ln in lines:
            prod = ln.product
            # نلتقط التكلفة المتوسطة الحالية لاستخدامها في الاستلام (نقل بالتكلفة).
            avg = Decimal(str(prod.avg_cost))
            record_stock_movement(
                product=prod, movement_type='OUT', quantity=ln.quantity,
                reference_type='WAREHOUSE_TRANSFER', reference_id=transfer.id,
                movement_date=transfer.transfer_date, tenant=transfer.tenant,
                warehouse=transfer.source_warehouse,
                notes=f"تحويل إلى {transfer.dest_warehouse.name}",
            )
            record_stock_movement(
                product=prod, movement_type='IN', quantity=ln.quantity, unit_cost=avg,
                reference_type='WAREHOUSE_TRANSFER', reference_id=transfer.id,
                movement_date=transfer.transfer_date, tenant=transfer.tenant,
                warehouse=transfer.dest_warehouse,
                notes=f"تحويل من {transfer.source_warehouse.name}",
            )
        transfer.is_posted = True
        transfer.save(update_fields=['is_posted', 'transfer_number'])
    logger.info("Warehouse transfer #%s posted (%d lines)", transfer.id, len(lines))
    return transfer


def unpost_warehouse_transfer(transfer, user=None):
    """يعكس التحويل: استلام في المصدر + صرف من الوجهة بالتكلفة المتوسطة الحالية."""
    if not transfer.is_posted:
        raise ValidationError("التحويل ليس مُرحَّلاً.")
    lines = list(transfer.lines.select_related('product').all())
    with transaction.atomic():
        for ln in lines:
            prod = ln.product
            avg = Decimal(str(prod.avg_cost))
            record_stock_movement(
                product=prod, movement_type='OUT', quantity=ln.quantity,
                reference_type='WAREHOUSE_TRANSFER', reference_id=transfer.id,
                movement_date=transfer.transfer_date, tenant=transfer.tenant,
                warehouse=transfer.dest_warehouse, notes="عكس تحويل",
            )
            record_stock_movement(
                product=prod, movement_type='IN', quantity=ln.quantity, unit_cost=avg,
                reference_type='WAREHOUSE_TRANSFER', reference_id=transfer.id,
                movement_date=transfer.transfer_date, tenant=transfer.tenant,
                warehouse=transfer.source_warehouse, notes="عكس تحويل",
            )
        transfer.is_posted = False
        transfer.save(update_fields=['is_posted'])
    return transfer


def post_stocktake(stocktake, user=None):
    """T-I2: يرحّل جرداً — يسوّي رصيد كل صنف ليطابق الكمية المعدودة عبر حركات
    ADJUST_IN/ADJUST_OUT، ويُنشئ قيد فرق الجرد (المخزون مقابل تكلفة البضاعة المباعة).
      فائض (عُدّ > النظام): مدين المخزون / دائن ت.ب.م.
      عجز  (عُدّ < النظام): مدين ت.ب.م / دائن المخزون.
    """
    from .models import Stocktake
    from accounting.services import post_journal
    if stocktake.is_posted:
        raise ValidationError("الجرد مُرحَّل مسبقاً.")
    lines = list(stocktake.lines.select_related('product').all())
    if not lines:
        raise ValidationError("أضف بنداً واحداً على الأقل.")

    # تجميع أطراف القيد حسب الحساب (مخزون/ت.ب.م) عبر كل البنود.
    debit_by_acct = {}   # account_id -> Decimal
    credit_by_acct = {}
    acct_obj = {}

    def _add(d, acct, amt):
        d[acct.id] = d.get(acct.id, Decimal('0')) + amt
        acct_obj[acct.id] = acct

    with transaction.atomic():
        if not stocktake.stocktake_number:
            stocktake.stocktake_number = _next_doc_number(
                stocktake.tenant_id, Stocktake, 'stocktake_number', 'JRD')
        for ln in lines:
            prod = ln.product
            system_qty = Decimal(str(prod.quantity_on_hand))
            counted = Decimal(str(ln.counted_quantity))
            variance = (counted - system_qty).quantize(Decimal('0.0001'))
            ln.system_quantity = system_qty
            ln.variance = variance
            ln.save(update_fields=['system_quantity', 'variance'])
            if variance == 0:
                continue
            avg = Decimal(str(prod.avg_cost))
            value = (abs(variance) * avg).quantize(Decimal('0.01'))
            inv_acct = _resolve_line_account(prod, 'inventory', tenant_id=stocktake.tenant_id)
            cogs_acct = _resolve_line_account(prod, 'cogs', tenant_id=stocktake.tenant_id)
            if variance > 0:
                # فائض: زيادة مخزون
                record_stock_movement(
                    product=prod, movement_type='ADJUST_IN', quantity=variance, unit_cost=avg,
                    reference_type='STOCKTAKE', reference_id=stocktake.id,
                    movement_date=stocktake.stocktake_date, tenant=stocktake.tenant,
                    warehouse=stocktake.warehouse, notes="فائض جرد",
                )
                if value > 0:
                    _add(debit_by_acct, inv_acct, value)
                    _add(credit_by_acct, cogs_acct, value)
            else:
                # عجز: نقص مخزون
                record_stock_movement(
                    product=prod, movement_type='ADJUST_OUT', quantity=abs(variance),
                    reference_type='STOCKTAKE', reference_id=stocktake.id,
                    movement_date=stocktake.stocktake_date, tenant=stocktake.tenant,
                    warehouse=stocktake.warehouse, notes="عجز جرد",
                )
                if value > 0:
                    _add(debit_by_acct, cogs_acct, value)
                    _add(credit_by_acct, inv_acct, value)

        # بناء أطراف القيد (صافي مدين/دائن لكل حساب) وترحيله إن وُجد فرق قيمي.
        lines_data = []
        net = {}
        for aid, amt in debit_by_acct.items():
            net[aid] = net.get(aid, Decimal('0')) + amt
        for aid, amt in credit_by_acct.items():
            net[aid] = net.get(aid, Decimal('0')) - amt
        for aid, amt in net.items():
            if amt == 0:
                continue
            if amt > 0:
                lines_data.append({'account': aid, 'debit': amt, 'credit': Decimal('0'), 'description': 'فرق جرد'})
            else:
                lines_data.append({'account': aid, 'debit': Decimal('0'), 'credit': -amt, 'description': 'فرق جرد'})

        journal = None
        if lines_data:
            journal = post_journal(
                tenant_id=stocktake.tenant_id,
                transaction_date=stocktake.stocktake_date,
                reference_type='STOCKTAKE',
                reference_id=stocktake.id,
                description=f"فرق جرد {stocktake.stocktake_number}",
                lines_data=lines_data,
                user=user,
            )
        stocktake.is_posted = True
        stocktake.journal = journal
        stocktake.save(update_fields=['is_posted', 'journal', 'stocktake_number'])
    logger.info("Stocktake #%s posted (journal=%s)", stocktake.id, journal.id if journal else None)
    return stocktake
