"""
Inventory services: stock movement recording with WAC (Weighted Average Cost).

All stock changes go through record_stock_movement() which:
1. Creates a StockMovement row with before/after snapshots
2. Updates Product.quantity_on_hand and Product.avg_cost atomically
"""
import logging
import re
from decimal import Decimal
from django.db import transaction
from django.core.exceptions import ValidationError

from .models import Product, StockMovement

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────
# تجميع البراندات: «المقاس/الأساس» مصدر حقيقة واحد (DRY) للشجرة + الجرد + الكرت
# المجمّع. المنتجات بنفس group_key (مثل عجل 185/65/14 بمختلف البراندات) تُجمَّع
# تحت عقدة أب واحدة، والبراند يميّز الورقة.
# ──────────────────────────────────────────────────────────────────────────

# مقاس إطار (عرض/نسبة/قطر مثل 185/65/14 أو 31/10.5/15). الحدّان (?<!\d)/(?!\d)
# يمنعان التقاط جزء من رقم أطول أو تاريخ. مرآة لـ tireSizeKey في الواجهة.
_TIRE_SIZE_RE = re.compile(
    r'(?<!\d)(\d{2,3})\s*/\s*(\d{1,2}(?:\.\d)?)\s*/\s*(\d{2}(?:\.\d)?)(?!\d)'
)


def tire_size_key(name: str) -> str | None:
    """يستخرج مقاس الإطار المعياري «W/A/D» من الاسم، أو None لغير العجال."""
    if not name:
        return None
    m = _TIRE_SIZE_RE.search(name)
    if not m:
        return None
    return f"{m.group(1)}/{m.group(2)}/{m.group(3)}"


def product_group_key(product) -> str:
    """مفتاح تجميع المنتج (اسم الصنف الفرعي/عقدة الأب). الأولوية:
    1) `variant_group` الصريح الذي يدخله المستخدم (مثل 185/65/14) — يُنشئ مجلّداً
       يتجمّع تحته حتى لو منتج واحد.
    2) مقاس الإطار المُستخرَج من الاسم (توافق مع البيانات القائمة للعجال).
    3) البراند — فالمنتجات بنفس البراند تتجمّع تلقائياً (≥2) دون إدخال إضافي.
    4) الاسم الأساسي. مصدر حقيقة واحد للتجميع."""
    explicit = (getattr(product, 'variant_group', '') or '').strip()
    if explicit:
        return explicit
    name = (product.name_ar or product.name_en or '').strip()
    size = tire_size_key(name)
    if size:
        return size
    brand = (getattr(product, 'brand', '') or '').strip()
    if brand:
        return brand
    return name or (product.sku or '')


def product_has_explicit_group(product) -> bool:
    """هل عُيِّن للمنتج صنف فرعي صريح — فيظهر مجلّده حتى لو منتجاً واحداً."""
    return bool((getattr(product, 'variant_group', '') or '').strip())


def product_display_name(product) -> str:
    """اسم العرض للورقة: الاسم + البراند بين قوسين (إن لم يكن مذكوراً أصلاً)."""
    name = (product.name_ar or product.name_en or product.sku or '').strip()
    brand = (getattr(product, 'brand', '') or '').strip()
    if brand and brand not in name:
        return f"{name} ({brand})".strip()
    return name

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


# أنواع حركات تُورِّد المخزون (يُبنى عليها لاحقاً) مقابل التي تستهلكه.
_SUPPLY_MOVEMENTS = ("IN", "ADJUST_IN", "RETURN_IN")
_CONSUME_MOVEMENTS = ("OUT", "ADJUST_OUT", "RETURN_OUT")

# تسميات عربية لأنواع مراجع الحركات (لرسالة الاعتمادية عند منع التراجع).
_REFERENCE_LABELS = {
    "SALE": "فاتورة بيع",
    "STOCK_ISSUE": "إذن صرف",
    "PURCHASE_INVOICE": "فاتورة شراء",
    "SHIPMENT": "شحنة",
    "DEAL": "صفقة",
    "CLEARANCE": "تخليص جمركي",
    "WAREHOUSE_TRANSFER": "تحويل مستودعي",
    "STOCKTAKE": "جرد",
    "MANUAL": "حركة يدوية",
}


def _dependent_label(reference_type, reference_id, tenant_id) -> str:
    """تسمية مقروءة للمستند المعتمِد — رقم الفاتورة للبيع/الصرف وإلا «النوع #المعرّف»."""
    noun = _REFERENCE_LABELS.get(reference_type, reference_type)
    number = None
    try:
        if reference_type in ("SALE", "STOCK_ISSUE"):
            from sales.models import SalesInvoice
            inv = (
                SalesInvoice.objects.filter(tenant_id=tenant_id, id=reference_id)
                .only("invoice_number")
                .first()
            )
            if inv:
                number = inv.invoice_number
    except Exception:  # noqa: BLE001 — التسمية تجميلية، لا تُفشل الحارس
        number = None
    return f"{noun} {number}" if number else f"{noun} #{reference_id}"


def find_stock_dependents(*, tenant_id, reference_id, reference_types) -> list[dict]:
    """ابحث عن المستندات اللاحقة المعتمِدة على المخزون/التكلفة الذي وفّره مستند.

    عند التراجع عن ترحيل مستند **مُورِّد للمخزون** (شراء/استلام/تسوية إضافة)، فإن
    أي حركة **صرف/بيع لاحقة** على نفس الأصناف تكون قد استهلكت رصيده وبُنيت تكلفتها
    (COGS) على متوسط التكلفة المتضمِّن هذا المستند. حذف المستند يُيتّم تلك الحركات
    وقيودها (تكلفة المبيعات…). تُرجع قائمة المستندات المعتمِدة (نوع/رقم/أصناف)
    لمنع الحذف. قائمة فارغة ⇒ لا اعتمادية (يجوز التراجع).

    مستند **مستهلِك** (بيع/صرف) لا تابعين له — التراجع عنه يحرّر مخزوناً فقط.
    """
    if not reference_types:
        return []
    own = list(
        StockMovement.objects.filter(
            tenant_id=tenant_id,
            reference_id=reference_id,
            reference_type__in=list(reference_types),
        ).only("id", "product_id", "movement_type")
    )
    if not own:
        return []
    supply_products = {m.product_id for m in own if m.movement_type in _SUPPLY_MOVEMENTS}
    if not supply_products:
        return []
    anchor_id = min(m.id for m in own)
    dependents = (
        StockMovement.objects.filter(
            tenant_id=tenant_id,
            product_id__in=supply_products,
            movement_type__in=_CONSUME_MOVEMENTS,
            id__gt=anchor_id,
        )
        .exclude(reference_type__in=list(reference_types), reference_id=reference_id)
        .select_related("product")
        .order_by("id")
    )
    grouped: dict[tuple, dict] = {}
    for m in dependents:
        key = (m.reference_type, m.reference_id)
        entry = grouped.setdefault(key, {
            "reference_type": m.reference_type,
            "reference_id": m.reference_id,
            "label": _dependent_label(m.reference_type, m.reference_id, tenant_id),
            "products": set(),
        })
        p = m.product
        entry["products"].add(p.name_ar or p.name_en or p.sku or f"#{m.product_id}")
    result = []
    for entry in grouped.values():
        entry["products"] = sorted(entry["products"])
        result.append(entry)
    if result:
        logger.info(
            "find_stock_dependents: ref=%s types=%s -> %d dependent document(s)",
            reference_id, list(reference_types), len(result),
        )
    return result


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

    # توحيد تكلفة الاستيراد مع نموذج «تكلفة المنتجات» (تذكير task23):
    # بعد استلام الشحنة يُعاد ضبط avg_cost بالمتوسط المرجّح للمشتريات المرحّلة
    # (يشمل landed cost لأن product_cost_breakdown يقدّم حقول landed) — القرار
    # بين الدوري/المتحرك مركزي في apply_purchase_cost_model.
    seen_products = set()
    for mv in created:
        if mv.product_id and mv.product_id not in seen_products:
            seen_products.add(mv.product_id)
            apply_purchase_cost_model(mv.product)

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

    # W8: معدّلات البيع من StockMovement (المصدر الوحيد، مطابق لجدول الأصناف):
    # أسبوعي = صافي (OUT − RETURN_IN) خلال 28 يوماً ÷ 4؛ شهري = 90 يوماً ÷ 3.
    import datetime as _dt
    from .models import StockMovement
    today = _dt.date.today()

    def _net_rate(days: int, divisor: str) -> Decimal:
        cutoff = today - _dt.timedelta(days=days)
        mv = StockMovement.objects.filter(
            tenant_id=tenant_id, product_id=product_id, movement_date__gte=cutoff)
        out_q = mv.filter(movement_type='OUT').aggregate(q=Sum('quantity'))['q'] or 0
        ret_q = mv.filter(movement_type='RETURN_IN').aggregate(q=Sum('quantity'))['q'] or 0
        net = Decimal(str(out_q)) - Decimal(str(ret_q))
        return (net / Decimal(divisor)).quantize(Decimal('0.01'))

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
        'avg_weekly_sales': str(_net_rate(28, '4')),
        'avg_monthly_sales': str(_net_rate(90, '3')),
    }


def _group_products(tenant_id: int, product_ids: list[int]) -> list:
    """يحلّ ويصفّي قائمة معرّفات إلى منتجات الشركة فقط (عزل المستأجر)."""
    return list(
        Product.objects.select_related('category')
        .filter(tenant_id=tenant_id, id__in=product_ids)
        .order_by('brand', 'sku')
    )


def product_group_profile(*, tenant_id: int, product_ids: list[int]) -> dict:
    """الكرت المجمّع: يجمع مؤشّرات كل البراندات (المنتجات) التي تشترك بنفس المقاس/
    الأساس في بطاقة واحدة — المخزون والمشتريات والمبيعات الإجمالية + تفصيل كل براند.

    يعيد استخدام منطق `product_profile` لكل عضو (DRY) ثم يجمع، فيبقى مصدر حقيقة
    واحد لطريقة احتساب المؤشّرات."""
    members = _group_products(tenant_id, product_ids)
    if not members:
        return {
            'name': '', 'category': None, 'member_count': 0, 'members': [],
            'quantity_on_hand': '0', 'inventory_valuation': '0.00',
            'purchased_qty': '0', 'purchased_value': '0',
            'sold_qty': '0', 'sold_value': '0',
        }

    qty = val = pq = pv = sq = sv = Decimal('0')
    member_rows = []
    for p in members:
        prof = product_profile(tenant_id=tenant_id, product_id=p.id)
        qty += Decimal(prof['quantity_on_hand'])
        val += Decimal(prof['inventory_valuation'])
        pq += Decimal(prof['purchased_qty'])
        pv += Decimal(prof['purchased_value'])
        sq += Decimal(prof['sold_qty'])
        sv += Decimal(prof['sold_value'])
        member_rows.append({
            'id': p.id,
            'sku': p.sku,
            'brand': (p.brand or '').strip(),
            'name': product_display_name(p),
            'quantity_on_hand': prof['quantity_on_hand'],
            'avg_cost': prof['avg_cost'],
            'inventory_valuation': prof['inventory_valuation'],
            'sold_qty': prof['sold_qty'],
        })

    first = members[0]
    return {
        'name': product_group_key(first),
        'category': first.category.name if first.category_id else None,
        'member_count': len(members),
        'members': member_rows,
        'quantity_on_hand': str(qty),
        'inventory_valuation': str(val.quantize(Decimal('0.01'))),
        'purchased_qty': str(pq),
        'purchased_value': str(pv),
        'sold_qty': str(sq),
        'sold_value': str(sv),
    }


_STOCK_IN_TYPES = {'IN', 'ADJUST_IN', 'RETURN_IN'}


def product_stock_ledger(
    *, tenant_id: int, product_id: int | None = None,
    product_ids: list[int] | None = None, limit: int = 50, offset: int = 0,
) -> dict:
    """Chronological stock ledger for a product, with a running balance per row.

    The running balance reuses the movement's stored `quantity_after` — the
    canonical per-product on-hand after that movement — so it reconciles exactly
    to current stock (A4) without a parallel computation. Paginated.

    تمرير `product_ids` يجمع دفتر الحركة لعدة براندات (الكرت المجمّع) ويضيف اسم
    المنتج لكل سطر؛ الرصيد الجاري يبقى رصيد كل صنف على حدة (لقطته بعد حركته).
    """
    if product_ids:
        base = StockMovement.objects.filter(tenant_id=tenant_id, product_id__in=product_ids)
    else:
        base = StockMovement.objects.filter(tenant_id=tenant_id, product_id=product_id)
    base = base.select_related('warehouse', 'partner', 'product').order_by('movement_date', 'id')
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
            # الطرف (المورد في المشتريات / الزبون في المبيعات) — مثل تبويب الفواتير المرتبطة.
            'party': m.partner.name if m.partner_id else None,
            'warehouse': m.warehouse.name if m.warehouse_id else None,
            # اسم البراند للكرت المجمّع (يميّز أي براند يخصّ السطر).
            'product_name': product_display_name(m.product),
            'qty_in': str(qty) if is_in else '0',
            'qty_out': str(qty) if not is_in else '0',
            'running_balance': str(m.quantity_after),
        })
    return {'results': rows, 'count': total, 'limit': limit, 'offset': offset}


def product_linked_invoices(
    *, tenant_id: int, product_id: int | None = None,
    product_ids: list[int] | None = None,
) -> list[dict]:
    """All purchase + sales invoices that contain this product (clickable).

    تمرير `product_ids` يجمع فواتير عدة براندات في قائمة واحدة (الكرت المجمّع)."""
    from logistics.models import PurchaseInvoiceItem
    from sales.models import SalesInvoiceLine

    pid_filter = {'product_id__in': product_ids} if product_ids else {'product_id': product_id}

    out: list[dict] = []
    pis = (
        PurchaseInvoiceItem.objects.filter(
            invoice__tenant_id=tenant_id, **pid_filter,
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
        SalesInvoiceLine.objects.filter(tenant_id=tenant_id, **pid_filter)
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


def product_cost_breakdown(*, tenant_id: int, product_id: int) -> dict:
    """واجهة «تكلفة المنتجات»: تكلفة كل فاتورة شراء لهذا الصنف على حدة، ومتوسط سعر
    الوحدة لكل فاتورة (إجمالي الفاتورة ÷ كميتها)، ثم تكلفة المنتج = **متوسط أسعار
    وحدات الفواتير مرجّحاً بكمية كل فاتورة** — أي Σ(سعر وحدة الفاتورة × كميتها) ÷
    Σ(كميات الشراء). المقام هو إجمالي الكمية المشتراة (لا الكمية الحالية المتبقية)،
    فلا يتأثر بما بِيع.

    تكلفة بند الفاتورة تُؤخذ بأفضلية landed cost (السعر النازل الحقيقي للمستورد):
      landed_line_total_ils ← landed_unit_price_ils × qty ← total_price.
    البنود متعددة لنفس الصنف داخل فاتورة واحدة تُجمَّع في صفّ فاتورة واحد.
    """
    from logistics.models import PurchaseInvoiceItem

    items = (
        PurchaseInvoiceItem.objects.filter(
            invoice__tenant_id=tenant_id, product_id=product_id,
            invoice__is_posted=True,
        )
        .select_related('invoice', 'invoice__partner')
        .order_by('invoice__invoice_date', 'invoice_id')
    )

    by_invoice: dict[int, dict] = {}
    order: list[int] = []
    for it in items:
        inv = it.invoice
        if inv.id not in by_invoice:
            order.append(inv.id)
            by_invoice[inv.id] = {
                'invoice_id': inv.id,
                'invoice_number': inv.invoice_number,
                'date': inv.invoice_date.isoformat() if inv.invoice_date else None,
                'party': inv.partner.name if inv.partner_id else None,
                'is_posted': bool(inv.is_posted),
                '_qty': Decimal('0'),
                '_cost': Decimal('0'),
            }
        qty = Decimal(str(it.quantity or 0))
        if it.landed_line_total_ils is not None and Decimal(str(it.landed_line_total_ils)) > 0:
            cost = Decimal(str(it.landed_line_total_ils))
        elif it.landed_unit_price_ils is not None and Decimal(str(it.landed_unit_price_ils)) > 0:
            cost = Decimal(str(it.landed_unit_price_ils)) * qty
        else:
            cost = Decimal(str(it.total_price or 0))
        by_invoice[inv.id]['_qty'] += qty
        by_invoice[inv.id]['_cost'] += cost

    rows: list[dict] = []
    weighted_sum = Decimal('0')   # Σ(سعر وحدة الفاتورة × كميتها)
    total_qty = Decimal('0')      # Σ(كميات الشراء)
    for inv_id in order:
        v = by_invoice[inv_id]
        qty = v.pop('_qty')
        cost = v.pop('_cost')
        unit = (cost / qty) if qty > 0 else Decimal('0')
        weighted_sum += unit * qty
        total_qty += qty
        v['quantity'] = str(qty.quantize(Decimal('0.0001')))
        v['invoice_cost'] = str(cost.quantize(Decimal('0.01')))
        v['unit_cost'] = str(unit.quantize(Decimal('0.0001')))
        rows.append(v)

    # تكلفة المنتج = متوسط أسعار وحدات الفواتير مرجّحاً بكمية كل فاتورة.
    if total_qty > 0:
        average_cost = (weighted_sum / total_qty).quantize(Decimal('0.0001'))
    else:
        average_cost = Decimal('0')

    p = Product.objects.get(id=product_id, tenant_id=tenant_id)
    logger.info(
        "product_cost_breakdown product=%s invoices=%d qty=%s weighted_avg=%s",
        product_id, len(rows), total_qty, average_cost,
    )
    return {
        'product_id': p.id,
        'sku': p.sku,
        'name': p.name_ar or p.name_en or p.sku,
        'invoices': rows,
        'invoice_count': len(rows),
        'total_purchased_qty': str(total_qty.quantize(Decimal('0.0001'))),
        'average_cost': str(average_cost),
    }


def set_avg_cost_from_purchases(product) -> Decimal:
    """يضبط `avg_cost` للصنف من فواتير الشراء المرحّلة بنموذج «تكلفة المنتجات»
    (متوسط مرجّح بالكمية). يُستدعى بعد استلام/ترحيل فاتورة شراء محلية كي يصبح
    avg_cost مصدر الحقيقة للنموذج الجديد بدل WAC المتحرك المنحرف — فيقرأ ترحيل
    COGS عند البيع القيمة الصحيحة تلقائياً. لا فواتير ⇒ يُترك avg_cost كما هو."""
    bd = product_cost_breakdown(tenant_id=product.tenant_id, product_id=product.id)
    if bd['invoice_count'] == 0:
        return Decimal(str(product.avg_cost or 0))
    avg = Decimal(bd['average_cost'])
    with transaction.atomic():
        prod = Product.objects.select_for_update().get(pk=product.pk)
        prod.avg_cost = avg
        prod.save(update_fields=['avg_cost'])
    logger.info("set_avg_cost_from_purchases product=%s avg=%s", product.pk, avg)
    return avg


def apply_purchase_cost_model(product) -> None:
    """يطبّق نموذج التكلفة حسب إعداد الشركة بعد استلام/تراجع فاتورة شراء.

    - الشركة على **المتوسط المرجّح المتحرك** (`SalesSettings.use_moving_average_cost`)
      ⇒ لا نفعل شيئاً: `avg_cost` الذي ضبطه `record_stock_movement` (WAC المتحرك،
      أي تكلفة لحظة البيع) هو مصدر الحقيقة، فلا يُدهَس.
    - غير ذلك ⇒ النموذج الدوري: `set_avg_cost_from_purchases` (متوسط كل المشتريات).

    مصدر حقيقة واحد لقرار طريقة التكلفة، يستدعيه كل مسارات الشراء (استلام/تراجع).
    """
    from sales.models import SalesSettings
    ss = (
        SalesSettings.objects.filter(tenant_id=product.tenant_id)
        .only('use_moving_average_cost').first()
    )
    if ss and ss.use_moving_average_cost:
        return
    set_avg_cost_from_purchases(product)


def reconcile_product_cogs(*, tenant_id: int, product_id: int, apply: bool = False, user=None) -> dict:
    """يصحّح تكلفة البضاعة المباعة وقائمة الدخل لصنف وفق نموذج «تكلفة المنتجات»
    (متوسط مرجّح بالكمية، periodic — يتحقق: COGS + مخزون آخر المدة = إجمالي المشتريات).

    يعيد تقييم حركات البيع (movement_type=OUT, reference_type=SALE) بالمتوسط الجديد
    (فيصبح تقرير أرباح الفواتير صحيحاً لأنه يقرأ total_cost للحركة)، ويُرحّل **قيد
    تسوية واحداً** بفرق التكلفة (مدين ت.ب.م / دائن المخزون عند الزيادة، والعكس عند
    النقص) فتصبح قائمة الدخل صحيحة. يعالج حالة البيع قبل وصول الشراء (COGS=0).

    apply=False ⇒ معاينة فقط (لا تعديل). idempotent: تشغيل ثانٍ لا فرق فيه ⇒ لا قيد.
    """
    from accounting.services import post_journal
    import datetime

    bd = product_cost_breakdown(tenant_id=tenant_id, product_id=product_id)
    avg = Decimal(bd['average_cost'])
    out_moves = list(StockMovement.objects.filter(
        tenant_id=tenant_id, product_id=product_id,
        movement_type='OUT', reference_type='SALE',
    ))
    old_cogs = sum((Decimal(str(m.total_cost or 0)) for m in out_moves), Decimal('0')).quantize(Decimal('0.01'))
    new_cogs = sum((Decimal(str(m.quantity or 0)) * avg for m in out_moves), Decimal('0')).quantize(Decimal('0.01'))
    diff = (new_cogs - old_cogs).quantize(Decimal('0.01'))

    result = {
        'product_id': product_id, 'average_cost': str(avg),
        'sold_moves': len(out_moves), 'old_cogs': str(old_cogs),
        'new_cogs': str(new_cogs), 'diff': str(diff),
        'applied': False, 'journal_id': None,
    }
    if not apply or bd['invoice_count'] == 0:
        return result

    p = Product.objects.get(id=product_id, tenant_id=tenant_id)
    with transaction.atomic():
        for m in out_moves:
            q = Decimal(str(m.quantity or 0))
            m.unit_cost = avg
            m.total_cost = (q * avg).quantize(Decimal('0.01'))
            m.avg_cost_after = avg
            m.save(update_fields=['unit_cost', 'total_cost', 'avg_cost_after'])
        p.avg_cost = avg
        p.save(update_fields=['avg_cost'])
        journal = None
        if diff != 0:
            cogs_acct = _resolve_line_account(p, 'cogs', tenant_id=tenant_id)
            inv_acct = _resolve_line_account(p, 'inventory', tenant_id=tenant_id)
            if diff > 0:
                lines_data = [
                    {'account': cogs_acct.id, 'debit': diff, 'credit': Decimal('0'), 'description': 'تسوية ت.ب.م'},
                    {'account': inv_acct.id, 'debit': Decimal('0'), 'credit': diff, 'description': 'تسوية مخزون'},
                ]
            else:
                amt = -diff
                lines_data = [
                    {'account': inv_acct.id, 'debit': amt, 'credit': Decimal('0'), 'description': 'تسوية مخزون'},
                    {'account': cogs_acct.id, 'debit': Decimal('0'), 'credit': amt, 'description': 'تسوية ت.ب.م'},
                ]
            # تاريخ التسوية = آخر تاريخ بيع (ضمن فترة البيانات/الفترة المحاسبية المفتوحة).
            sale_dates = [m.movement_date for m in out_moves if m.movement_date]
            txn_date = max(sale_dates) if sale_dates else datetime.date.today()
            journal = post_journal(
                tenant_id=tenant_id,
                transaction_date=txn_date,
                reference_type='COGS_RECONCILE',
                reference_id=product_id,
                description=f"تسوية تكلفة المبيعات — {p.sku}",
                lines_data=lines_data,
                user=user if user and not getattr(user, 'is_anonymous', False) else None,
            )
        result['applied'] = True
        result['journal_id'] = journal.id if journal else None
    logger.info(
        "reconcile_product_cogs product=%s avg=%s diff=%s journal=%s",
        product_id, avg, diff, result['journal_id'],
    )
    return result


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
