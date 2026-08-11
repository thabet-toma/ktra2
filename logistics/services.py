"""P-H-1/3: Business-logic services for logistics app.

Mirrors sales/services.py patterns for attached payment vouchers (M2-T3)
and AP account resolution.
"""

import logging
from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction

from accounting.models import Account, Cheque
from core.payments import document_payment_summary

logger = logging.getLogger(__name__)

GR_IR_ACCOUNT_CODE = "2110"
GR_IR_ACCOUNT_NAME = "بضاعة مُستلَمة لم تُفوتَر (GR/IR Clearing)"

DEC = Decimal("0.01")


def materialize_quotation_draft_parties(quotation, *, user=None):
    """T-DRAFTPARTY: يحوّل المورد/الأصناف **المبدئية** في عرض السعر إلى سجلات حقيقية.

    عرض السعر يُكتب أثناء الاستكشاف: المورد قد يكون اسماً سمعه المشتري، والصنف
    نصاً في رسالة. لا شيء من ذلك يدخل دفتر الشركاء أو فهرس الأصناف حتى **لحظة
    التحويل** إلى صفقة/طلبية/فاتورة — عندها فقط صار القرار حقيقياً.

    المطابقة بالاسم أولاً: الاسم الموجود مسبقاً يُعاد استعماله، فلا يتضاعف مورد
    أو صنف لأن العرض كُتب يدوياً. مصدر واحد يستدعيه طُرق التحويل الثلاثة.
    """
    from django.db import IntegrityError

    from inventory.models import Product
    from inventory.services import generate_next_sku
    from logistics.models import SupplierQuotation
    from partners.models import Partner

    created_supplier = None
    created_products = []

    if quotation.supplier_id is None:
        name = (quotation.supplier_draft_name or '').strip()
        if not name:
            raise ValidationError('عرض السعر بلا مورد — اختر مورداً أو اكتب اسمه قبل التحويل.')
        supplier = Partner.objects.filter(
            tenant_id=quotation.tenant_id, partner_type='Supplier', name=name,
        ).first()
        if supplier is None:
            supplier = Partner.objects.create(
                tenant_id=quotation.tenant_id,
                name=name,
                partner_type='Supplier',
                supplier_scope=(
                    Partner.SUPPLIER_SCOPE_INTERNATIONAL
                    if quotation.scope == SupplierQuotation.SCOPE_IMPORT
                    else Partner.SUPPLIER_SCOPE_LOCAL
                ),
            )
            created_supplier = supplier
        quotation.supplier = supplier
        quotation.supplier_draft_name = ''
        quotation.save(update_fields=['supplier', 'supplier_draft_name', 'updated_at'])
        logger.info(
            'quotation.materialize supplier quotation=%s partner=%s created=%s',
            quotation.pk, supplier.pk, created_supplier is not None,
        )

    # استعلام طازج لا ذاكرة prefetch: المستدعون يجلبون `lines__product` قبل النداء،
    # فالقراءة من الذاكرة تعطي أصنافاً قديمة بعد الإنشاء.
    for line in quotation.lines.select_related('product').all():
        if line.product_id:
            continue
        name = (line.name_snapshot or '').strip()
        if not name:
            raise ValidationError(
                f'بند بلا اسم في العرض {quotation.quotation_number} — أكمل البنود قبل التحويل.'
            )
        product = Product.objects.filter(
            tenant_id=quotation.tenant_id, name_ar=name,
        ).first()
        if product is None:
            # تفرّد SKU يضمنه قيد unique(tenant, sku) — نعيد المحاولة عند السباق
            # كما في مسار إنشاء الصنف العادي.
            for _ in range(5):
                try:
                    with transaction.atomic():
                        product = Product.objects.create(
                            tenant_id=quotation.tenant_id,
                            sku=generate_next_sku(quotation.tenant),
                            name_ar=name,
                        )
                    break
                except IntegrityError:
                    product = None
            if product is None:
                raise ValidationError('تعذّر توليد رقم صنف — أعد المحاولة.')
            created_products.append(product)
        line.product = product
        line.save(update_fields=['product'])
        logger.info(
            'quotation.materialize product quotation=%s line=%s product=%s created=%s',
            quotation.pk, line.pk, product.pk, product in created_products,
        )

    if created_supplier is not None or created_products:
        logger.info(
            'quotation.materialize done quotation=%s new_supplier=%s new_products=%s',
            quotation.pk,
            getattr(created_supplier, 'pk', None),
            [p.pk for p in created_products],
        )
    return created_supplier, created_products


@transaction.atomic
def convert_local_quotation_to_order(quotation, *, user=None):
    """حوّل عرض شراء محلي مقبول إلى طلبية شراء واحدة قابلة لإعادة المحاولة."""
    from accounting.services import next_document_number
    from logistics.models import (
        PurchaseOrder,
        PurchaseOrderLine,
        SupplierQuotation,
    )

    quotation = (
        SupplierQuotation.objects.select_for_update()
        .select_related('tenant', 'supplier', 'currency')
        .prefetch_related('lines__product')
        .get(pk=quotation.pk)
    )
    try:
        return quotation.local_order, False
    except PurchaseOrder.DoesNotExist:
        pass

    if quotation.scope != SupplierQuotation.SCOPE_LOCAL:
        raise ValidationError('يمكن تحويل عروض الشراء المحلية فقط إلى طلبية شراء.')
    if quotation.status != SupplierQuotation.STATUS_ACCEPTED:
        raise ValidationError('يجب اعتماد عرض الشراء قبل تحويله إلى طلبية.')

    # T-DRAFTPARTY: المورد/الأصناف المبدئية تصير سجلات حقيقية هنا لا قبل ذلك.
    materialize_quotation_draft_parties(quotation, user=user)

    # طازج بعد تجسيد المبدئيّ: ذاكرة prefetch السابقة تحمل أصنافاً فارغة.
    lines = list(quotation.lines.select_related('product').all())
    if not lines:
        raise ValidationError('لا يمكن تحويل عرض سعر بلا أصناف.')
    number = next_document_number(quotation.tenant_id, 'purchase_order')
    order = PurchaseOrder.objects.create(
        tenant=quotation.tenant,
        order_number=f'PO-{number:04d}',
        supplier=quotation.supplier,
        quotation=quotation,
        order_date=quotation.quotation_date,
        expected_delivery_date=quotation.valid_until,
        currency=quotation.currency,
        exchange_rate=quotation.exchange_rate,
        subtotal=quotation.subtotal,
        discount_amount=quotation.discount_amount,
        tax_rate=quotation.tax_rate,
        tax_amount=quotation.tax_amount,
        grand_total=quotation.grand_total,
        shipping_cost=quotation.shipping_cost_estimate,
        is_shipping_included=quotation.is_shipping_included,
        shipping_method=quotation.shipping_method,
        payment_method=quotation.payment_method,
        delivery_days=quotation.delivery_days,
        notes=quotation.notes,
        created_by=user if user and getattr(user, 'is_authenticated', False) else None,
    )
    PurchaseOrderLine.objects.bulk_create([
        PurchaseOrderLine(
            tenant=quotation.tenant,
            order=order,
            product=line.product,
            seq=line.seq,
            name_snapshot=line.name_snapshot,
            description_line=line.description_line,
            quantity=line.quantity,
            unit_price=line.unit_price,
            line_total=line.line_total,
        )
        for line in lines
    ])
    quotation.status = SupplierQuotation.STATUS_CONVERTED
    quotation.save(update_fields=['status', 'updated_at'])
    return order, True


def _next_purchase_invoice_number(tenant) -> str:
    """أعلى رقم INV-#### مستعمل لهذه الشركة + 1 — الترقيم لا يعتمد على العدّ."""
    import re

    from logistics.models import PurchaseInvoice

    numbers = PurchaseInvoice.objects.filter(
        tenant=tenant,
        invoice_number__startswith='INV-',
    ).values_list('invoice_number', flat=True)
    last_number = max(
        (
            int(match.group(1))
            for value in numbers
            if (match := re.match(r'^INV-(\d+)$', str(value or '')))
        ),
        default=0,
    )
    return f'INV-{last_number + 1:04d}'


def _draft_purchase_invoice_from_document(
    source, *, lines, invoice_name, invoice_date, supplier, shipping_cost,
    user=None, **extra_fields,
):
    """فاتورة شراء محلية **مسودة** من مستند سابق (طلبية أو عرض سعر).

    مصدر واحد للطريقين: لا قيد ولا حركة مخزون قبل الترحيل/الاستلام، ونفس عقد
    البنود والضريبة في الحالتين — فلا تختلف فاتورةٌ عن أخرى بحسب طريق وصولها.
    """
    from logistics.models import PurchaseInvoice, PurchaseInvoiceItem

    invoice = PurchaseInvoice.objects.create(
        tenant=source.tenant,
        invoice_number=_next_purchase_invoice_number(source.tenant),
        invoice_name=invoice_name,
        invoice_date=invoice_date,
        invoice_type=PurchaseInvoice.INVOICE_TYPE_LOCAL,
        partner=supplier,
        currency=source.currency,
        exchange_rate=source.exchange_rate,
        subtotal=source.subtotal,
        discount_amount=source.discount_amount,
        tax_rate=source.tax_rate,
        tax_amount=source.tax_amount,
        shipping_cost=shipping_cost,
        shipping_included=source.is_shipping_included,
        grand_total=source.grand_total,
        status='draft',
        receipt_status=PurchaseInvoice.RECEIPT_NOT,
        notes=source.notes,
        payment_type=PurchaseInvoice.PAYMENT_TYPE_CREDIT,
        created_by=user if user and getattr(user, 'is_authenticated', False) else None,
        **extra_fields,
    )
    PurchaseInvoiceItem.objects.bulk_create([
        PurchaseInvoiceItem(
            invoice=invoice,
            product=line.product,
            name=line.name_snapshot or str(line.product),
            quantity=line.quantity,
            unit_price=line.unit_price,
            total_price=line.line_total,
            seq=line.seq,
            name_snapshot=line.name_snapshot,
            description_line=line.description_line[:500],
            line_currency=source.currency,
            line_exchange_rate=source.exchange_rate,
            is_taxable=bool(source.tax_rate),
            vat_percent=source.tax_rate,
        )
        for line in lines
    ])
    return invoice


@transaction.atomic
def convert_purchase_order_to_invoice(order, *, user=None):
    """أنشئ فاتورة شراء محلية مسودة؛ لا قيد ولا حركة مخزون قبل الترحيل/الاستلام."""
    from logistics.models import PurchaseOrder

    order = (
        PurchaseOrder.objects.select_for_update()
        .select_related('tenant', 'supplier', 'currency', 'invoice')
        .prefetch_related('lines__product')
        .get(pk=order.pk)
    )
    if order.invoice_id:
        return order.invoice, False
    if order.status != PurchaseOrder.STATUS_CONFIRMED:
        raise ValidationError('يجب تأكيد طلبية الشراء قبل تحويلها إلى فاتورة.')

    invoice = _draft_purchase_invoice_from_document(
        order,
        lines=order.lines.all(),
        invoice_name=f'فاتورة من طلبية {order.order_number}',
        invoice_date=order.order_date,
        supplier=order.supplier,
        shipping_cost=order.shipping_cost,
        user=user,
    )
    order.invoice = invoice
    order.status = PurchaseOrder.STATUS_CONVERTED
    order.save(update_fields=['invoice', 'status', 'updated_at'])
    logger.info(
        'purchase_order.to_invoice order=%s invoice=%s tenant=%s',
        order.pk, invoice.pk, order.tenant_id,
    )
    return invoice, True


@transaction.atomic
def convert_local_quotation_to_invoice(quotation, *, user=None):
    """عرض شراء محلي مقبول → فاتورة شراء مسودة **مباشرةً** (بلا طلبية وسيطة).

    الطريق الثاني إلى جانب `convert_local_quotation_to_order`: المشتري الذي
    وصلته البضاعة مع العرض لا يلزمه اختلاق طلبية ليصل إلى فاتورة. قفل صف العرض
    + OneToOne على المصدر يجعلان العملية ذرّية ومتكررة بأمان.
    """
    from logistics.models import PurchaseInvoice, PurchaseOrder, SupplierQuotation

    quotation = (
        SupplierQuotation.objects.select_for_update()
        .select_related('tenant', 'supplier', 'currency')
        .prefetch_related('lines__product')
        .get(pk=quotation.pk)
    )
    try:
        return quotation.local_invoice, False
    except PurchaseInvoice.DoesNotExist:
        pass

    if quotation.scope != SupplierQuotation.SCOPE_LOCAL:
        raise ValidationError('يمكن تحويل عروض الشراء المحلية فقط إلى فاتورة شراء.')
    if quotation.status != SupplierQuotation.STATUS_ACCEPTED:
        raise ValidationError('يجب اعتماد عرض الشراء قبل تحويله إلى فاتورة.')
    try:
        existing_order = quotation.local_order
    except PurchaseOrder.DoesNotExist:
        existing_order = None
    if existing_order is not None:
        raise ValidationError(
            f'عرض السعر {quotation.quotation_number} محوَّل إلى طلبية '
            f'{existing_order.order_number} — حوّل الطلبية إلى فاتورة.'
        )

    # T-DRAFTPARTY: المورد/الأصناف المبدئية تصير سجلات حقيقية هنا لا قبل ذلك.
    materialize_quotation_draft_parties(quotation, user=user)

    # طازج بعد تجسيد المبدئيّ: ذاكرة prefetch السابقة تحمل أصنافاً فارغة.
    lines = list(quotation.lines.select_related('product').all())
    if not lines:
        raise ValidationError('لا يمكن تحويل عرض سعر بلا أصناف.')

    invoice = _draft_purchase_invoice_from_document(
        quotation,
        lines=lines,
        invoice_name=f'فاتورة من عرض سعر {quotation.quotation_number}',
        invoice_date=quotation.quotation_date,
        supplier=quotation.supplier,
        shipping_cost=quotation.shipping_cost_estimate,
        user=user,
        source_quotation=quotation,
    )
    quotation.status = SupplierQuotation.STATUS_CONVERTED
    quotation.save(update_fields=['status', 'updated_at'])
    logger.info(
        'supplier_quotation.to_invoice quotation=%s invoice=%s tenant=%s',
        quotation.pk, invoice.pk, quotation.tenant_id,
    )
    return invoice, True


@transaction.atomic
def convert_import_quotation_to_deal(quotation, *, user=None):
    """حوّل عرض استيراد مقبول إلى طلبية الاستيراد القانونية (LogisticsDeal).

    قفل صف العرض + OneToOne على المصدر يجعلان العملية ذرّية ومتكررة بأمان:
    إعادة نفس الطلب ترجع الصفقة القائمة ولا تنشئ صفقة ثانية.
    """
    from accounting.services import next_deal_number
    from logistics.models import (
        LogisticsDeal,
        LogisticsDealItem,
        SupplierQuotation,
    )

    quotation = (
        SupplierQuotation.objects.select_for_update()
        .select_related('tenant', 'supplier', 'currency')
        .prefetch_related('lines__product')
        .get(pk=quotation.pk)
    )
    try:
        return quotation.import_deal, False
    except LogisticsDeal.DoesNotExist:
        pass

    if quotation.scope != SupplierQuotation.SCOPE_IMPORT:
        raise ValidationError('يمكن تحويل عروض الاستيراد فقط إلى طلبية استيراد.')
    if quotation.status != SupplierQuotation.STATUS_ACCEPTED:
        raise ValidationError('يجب اعتماد عرض الاستيراد قبل تحويله إلى طلبية.')
    if quotation.tax_rate or quotation.tax_amount:
        raise ValidationError('عرض الاستيراد لا يجوز أن يتضمن ضريبة قبل التخليص.')

    # T-DRAFTPARTY: المورد/الأصناف المبدئية تصير سجلات حقيقية هنا لا قبل ذلك.
    materialize_quotation_draft_parties(quotation, user=user)

    if quotation.supplier.tenant_id != quotation.tenant_id:
        raise ValidationError('مورد عرض السعر لا يتبع الشركة الحالية.')

    # طازج بعد تجسيد المبدئيّ: ذاكرة prefetch السابقة تحمل أصنافاً فارغة.
    lines = list(quotation.lines.select_related('product').all())
    if not lines:
        raise ValidationError('لا يمكن تحويل عرض سعر بلا أصناف.')
    for line in lines:
        if line.tenant_id != quotation.tenant_id:
            raise ValidationError('أحد بنود العرض لا يتبع الشركة الحالية.')
        if line.product.tenant_id != quotation.tenant_id:
            raise ValidationError('أحد أصناف العرض لا يتبع الشركة الحالية.')

    ref_number = f'D-{next_deal_number(quotation.tenant_id):04d}'
    supplier_name = quotation.supplier.legal_name or quotation.supplier.name
    deal = LogisticsDeal.objects.create(
        tenant=quotation.tenant,
        source_quotation=quotation,
        ref_number=ref_number,
        partner=quotation.supplier,
        order_date=quotation.quotation_date,
        currency=quotation.currency,
        currency_rate=quotation.exchange_rate,
        status='Open',
        stage=LogisticsDeal.STAGE_DRAFT,
        notes=quotation.notes,
        description=f'طلبية من عرض سعر {quotation.quotation_number}',
        incoterms=quotation.incoterms,
        shipping_method=quotation.shipping_method,
        payment_method=quotation.payment_method,
        production_days=quotation.production_days,
        delivery_days=quotation.delivery_days,
        total_cbm=quotation.total_cbm,
        total_weight=quotation.total_weight_kg,
        total_weight_kg=quotation.total_weight_kg,
        shipping_cost_estimate=quotation.shipping_cost_estimate,
        is_shipping_included=quotation.is_shipping_included,
        discount_amount=quotation.discount_amount,
        subtotal=quotation.subtotal,
        tax_rate=Decimal('0'),
        tax_amount=Decimal('0'),
        total_amount=quotation.grand_total,
        remaining_amount=quotation.grand_total,
        price_offer_id=str(quotation.pk),
        original_offer_number=quotation.quotation_number,
        factory_name=supplier_name,
        # T-IMPOFFER: مصدر التسعير يُنقل مع الصفقة — كان ينقطع عند حدود العرض.
        alibaba_link=quotation.alibaba_link or None,
        created_by=user if user and getattr(user, 'is_authenticated', False) else None,
    )
    LogisticsDealItem.objects.bulk_create([
        LogisticsDealItem(
            deal=deal,
            product=line.product,
            quantity=line.quantity,
            unit_price=line.unit_price,
            seq=line.seq,
            name_snapshot=line.name_snapshot,
            description_line=line.description_line[:500],
            notes=line.description_line[:255] or None,
            line_currency=quotation.currency,
            line_exchange_rate=quotation.exchange_rate,
            is_taxable=False,
            vat_percent=Decimal('0'),
        )
        for line in lines
    ])
    quotation.status = SupplierQuotation.STATUS_CONVERTED
    quotation.save(update_fields=['status', 'updated_at'])
    return deal, True


def purchase_invoice_payment_summary(invoice):
    """ملخص دفع فاتورة الشراء من السندات المرتبطة والمرحّلة فقط."""
    cached = getattr(invoice, "_payment_summary_cache", None)
    if cached is not None:
        return cached
    fees_total = sum(
        (Decimal(str(f.amount or 0)) for f in invoice.fees.all()),
        Decimal("0"),
    ).quantize(DEC)
    payable = (Decimal(str(invoice.grand_total or 0)) + fees_total).quantize(DEC)
    # T-ONACC: السند الموزَّع يُحسب بمبالغ توزيعه على هذه الفاتورة فقط؛ والسند
    # المرتبط بالحقل المفرد (السلوك القديم) يُحسب بكامل مبلغه — ولا يُجمع الاثنان
    # لنفس السند فلا يتكرّر الاحتساب.
    linked_paid = sum(
        (
            Decimal(str(payment.amount or 0))
            for payment in invoice.supplier_payments.all()
            if payment.is_posted and not payment.allocations.all()
        ),
        Decimal("0"),
    )
    allocated_paid = sum(
        (
            Decimal(str(alloc.amount_in_invoice_currency or alloc.amount or 0))
            for alloc in invoice.payment_allocations.all()
            if alloc.payment.is_posted
        ),
        Decimal("0"),
    )
    linked_paid += allocated_paid
    legacy_paid = sum(
        (
            Decimal(str(payment.amount or 0))
            for payment in invoice.payments.all()
            if payment.is_posted
        ),
        Decimal("0"),
    )
    recorded_paid = linked_paid + legacy_paid
    paid = recorded_paid if recorded_paid > 0 else Decimal(str(invoice.attached_cash_amount or 0))
    if invoice.payment_type == "cash" and invoice.is_posted:
        paid = max(paid, payable)
    summary = {
        "fees_total": fees_total,
        "payable_total": payable,
        **document_payment_summary(payable, paid),
    }
    invoice._payment_summary_cache = summary
    return summary


def annotate_purchase_invoice_payment_summary(queryset):
    """نسخة SQL لملخص الدفع تُستخدم في القوائم والفلترة قبل pagination."""
    from django.db.models import (
        Case, CharField, DecimalField, ExpressionWrapper, F, OuterRef,
        Subquery, Sum, Value, When,
    )
    from django.db.models.functions import Coalesce, Greatest
    from logistics.models import PurchaseInvoiceFee, PurchaseInvoicePayment
    from sales.models import SupplierPayment, SupplierPaymentAllocation

    money = DecimalField(max_digits=18, decimal_places=2)

    def total_subquery(model, amount_field="amount", **filters):
        return (
            model.objects
            .filter(invoice_id=OuterRef("pk"), **filters)
            .values("invoice_id")
            .annotate(total=Sum(amount_field))
            .values("total")[:1]
        )

    fee_total = total_subquery(PurchaseInvoiceFee)
    # T-ONACC: نفس قاعدة purchase_invoice_payment_summary — السند الموزَّع يُستثنى
    # من الربط المفرد ويُحسب بمبالغ توزيعه وحدها (فلا يتكرّر الاحتساب).
    linked_paid = (
        SupplierPayment.objects
        .filter(purchase_invoice_id=OuterRef("pk"), is_posted=True, allocations__isnull=True)
        .values("purchase_invoice_id")
        .annotate(total=Sum("amount"))
        .values("total")[:1]
    )
    allocated_paid = (
        SupplierPaymentAllocation.objects
        .filter(invoice_id=OuterRef("pk"), payment__is_posted=True)
        .values("invoice_id")
        .annotate(total=Sum(Coalesce("amount_in_invoice_currency", "amount")))
        .values("total")[:1]
    )
    legacy_paid = total_subquery(PurchaseInvoicePayment, is_posted=True)
    zero = Value(Decimal("0.00"), output_field=money)

    queryset = queryset.annotate(
        list_fees_total=Coalesce(Subquery(fee_total, output_field=money), zero),
        list_linked_paid=Coalesce(Subquery(linked_paid, output_field=money), zero),
        list_allocated_paid=Coalesce(Subquery(allocated_paid, output_field=money), zero),
        list_legacy_paid=Coalesce(Subquery(legacy_paid, output_field=money), zero),
    ).annotate(
        list_payable_total=ExpressionWrapper(
            F("grand_total") + F("list_fees_total"), output_field=money,
        ),
        list_recorded_paid=ExpressionWrapper(
            F("list_linked_paid") + F("list_allocated_paid") + F("list_legacy_paid"),
            output_field=money,
        ),
    ).annotate(
        list_effective_paid=Case(
            When(
                payment_type="cash", is_posted=True,
                then=F("list_payable_total"),
            ),
            When(list_recorded_paid__gt=0, then=F("list_recorded_paid")),
            default=F("attached_cash_amount"),
            output_field=money,
        ),
    ).annotate(
        list_amount_paid=Case(
            When(
                list_effective_paid__gt=F("list_payable_total"),
                then=F("list_payable_total"),
            ),
            default=F("list_effective_paid"),
            output_field=money,
        ),
    ).annotate(
        list_remaining_balance=Greatest(
            ExpressionWrapper(
                F("list_payable_total") - F("list_amount_paid"),
                output_field=money,
            ),
            zero,
        ),
    ).annotate(
        list_payment_status=Case(
            When(list_payable_total__lte=0, then=Value("unpaid")),
            When(
                list_amount_paid__gte=F("list_payable_total"),
                then=Value("paid"),
            ),
            When(list_amount_paid__gt=0, then=Value("partially_paid")),
            default=Value("unpaid"),
            output_field=CharField(),
        ),
    )
    return queryset


def get_or_create_purchase_settings(tenant):
    """FEAT-1: يُعيد (أو يُنشئ) إعدادات الشراء للشركة بقيم افتراضية."""
    from logistics.models import PurchaseSettings

    tenant_id = getattr(tenant, "TenantID", tenant)
    obj = PurchaseSettings.objects.filter(tenant_id=tenant_id).first()
    if obj is None:
        obj = PurchaseSettings.objects.create(tenant_id=tenant_id)
    # T-DEFACC: الصندوق الافتراضي يُملأ من مصدر الشركة الواحد (إعدادات المبيعات ثم
    # الشجرة) بدل أن يبقى فارغاً فيرفض حفظ أي دفعة نقدية على فاتورة شراء.
    if obj.default_cash_account_id is None:
        from accounting.services import resolve_default_cash_account

        acc = resolve_default_cash_account(tenant_id)
        if acc:
            obj.default_cash_account = acc
            obj.save(update_fields=["default_cash_account"])
            logger.info(
                "purchase.settings.default_cash_filled tenant=%s account=%s",
                tenant_id, acc.pk,
            )
    return obj


def _resolve_ap_account(partner) -> Account:
    """P-H-3: يحلّ حساب الذمم الدائنة للمورد بسلسلة أولويات.

    1. حساب مرتبط بالمورد مباشرة (partner.linked_account)
    2. حساب ذمم مجموعة المورد (partner.group.account_payable)
    3. حساب برمز 2101 (حساب ذمم موردين معياري)
    4. أول حساب خصوم (Liability) نشط في الشركة
    """
    # T-DEFACC: المورد بلا حساب مربوط يُنشأ له حسابه تحت «الدائنون» أولاً — بلا
    # هذا كان القيد يقع على الأب العام فيختلط كل الموردين في حساب واحد.
    from partners.signals import ensure_partner_linked_account

    partner = ensure_partner_linked_account(partner) or partner
    if partner.linked_account_id:
        return partner.linked_account
    if partner.group_id:
        from partners.models import PartnerGroup
        g = PartnerGroup.objects.filter(pk=partner.group_id).first()
        if g and g.account_payable_id:
            return g.account_payable
    ap = Account.objects.filter(tenant_id=partner.tenant_id, code="2101").first()
    if ap:
        return ap
    ap = Account.objects.filter(
        tenant_id=partner.tenant_id, account_type="Liability", is_active=True,
    ).first()
    if ap:
        return ap
    raise ValidationError(
        f"لم يُعثر على حساب ذمم دائنة للمورد «{partner.name}». "
        "اربط المورد بحساب، أو حدد حساب ذمم للمجموعة، أو أنشئ حساب 2101."
    )


def attach_pi_payment_voucher(
    invoice,
    *,
    cash_amount: Decimal | str | float = 0,
    cash_account_id: int | None = None,
    cheques: list[dict] | None = None,
    user=None,
):
    """يربط سند مالي (نقدي + شيكات) بفاتورة الشراء قبل الترحيل.

    Mirror of sales/services.py:attach_payment_voucher for PurchaseInvoice.

    - Replace-semantics: each call replaces previously-attached Draft cheques.
    - The journal is NOT posted here — post handler reads the attached data.
    - Idempotent when called multiple times pre-post.

    cheques: list of dicts with keys:
        cheque_number (str), amount (Decimal/str), bank_name (str, optional),
        due_date (date/str, optional), issue_date (date/str, optional),
        payee_name (str, optional), notes (str, optional).
    """
    if invoice.is_posted:
        raise ValidationError("لا يمكن تعديل السند بعد ترحيل فاتورة الشراء.")

    cash_amount = Decimal(str(cash_amount or 0)).quantize(DEC)
    if cash_amount < 0:
        raise ValidationError("مبلغ النقدي لا يمكن أن يكون سالباً.")

    cheques = cheques or []
    for i, c in enumerate(cheques):
        if not str(c.get("cheque_number", "")).strip():
            raise ValidationError(f"الشيك #{i+1}: رقم الشيك مطلوب.")
        try:
            amt = Decimal(str(c.get("amount", 0)))
        except Exception:
            raise ValidationError(f"الشيك #{i+1}: مبلغ غير صالح.")
        if amt <= 0:
            raise ValidationError(f"الشيك #{i+1}: المبلغ يجب أن يكون أكبر من صفر.")

    cheques_total = sum(
        (Decimal(str(c.get("amount", 0))) for c in cheques), Decimal("0")
    ).quantize(DEC)

    grand = Decimal(str(invoice.grand_total or 0)).quantize(DEC)
    if (cash_amount + cheques_total) > grand:
        raise ValidationError(
            f"مجموع السند ({cash_amount} نقدي + {cheques_total} شيكات) "
            f"يتجاوز مبلغ الفاتورة {grand}."
        )

    if cash_amount > 0 and not cash_account_id:
        # T-DEFACC: الصندوق الافتراضي للشركة بدل رفض السند — نفس مصدر سندي
        # القبض والصرف، فلا تختلف فاتورة الشراء عن بقية المعاملات.
        from accounting.services import resolve_default_cash_account

        default_cash = resolve_default_cash_account(invoice.tenant_id)
        if default_cash is None:
            raise ValidationError(
                "لا بدّ من تحديد حساب الصندوق عند وجود مبلغ نقدي — أو عيّن صندوقاً "
                "افتراضياً في إعدادات المبيعات."
            )
        cash_account_id = default_cash.pk
        logger.info(
            "purchase.invoice.cash_account_defaulted invoice=%s account=%s",
            invoice.pk, cash_account_id,
        )

    with transaction.atomic():
        invoice.attached_cash_amount = cash_amount
        invoice.save(update_fields=["attached_cash_amount"])

        # Replace previously-linked Draft cheques
        Cheque.objects.filter(
            purchase_invoice=invoice, status="Draft"
        ).delete()
        for c in cheques:
            Cheque.objects.create(
                tenant_id=invoice.tenant_id,
                purchase_invoice=invoice,
                partner=invoice.partner,
                direction="Outgoing",
                status="Draft",
                cheque_number=str(c.get("cheque_number")).strip(),
                bank_name=(c.get("bank_name") or "")[:100],
                amount=Decimal(str(c.get("amount"))).quantize(DEC),
                currency_id=invoice.currency_id,
                due_date=c.get("due_date") or None,
                issue_date=c.get("issue_date") or None,
                payee_name=(c.get("payee_name") or "")[:150],
                notes=c.get("notes") or "",
                created_by=user if user and not getattr(user, "is_anonymous", False) else None,
            )


def _resolve_inventory_account(tenant) -> Account:
    """حساب المخزون لقيد استلام البضاعة — 1104 ثم مخزون بالاسم ثم أصل."""
    acc = (
        Account.objects.filter(tenant=tenant, code="1104").first()
        or Account.objects.filter(
            tenant=tenant, account_type="Asset", name__icontains="مخزون",
        ).first()
        or Account.objects.filter(
            tenant=tenant, account_type="Asset", is_active=True,
        ).first()
    )
    if not acc:
        raise ValidationError(
            "لم يُعثر على حساب مخزون (1104). أكمل شجرة الحسابات أولاً."
        )
    return acc


def _resolve_vat_input_account(tenant) -> Account:
    """حساب ضريبة المدخلات (1105) — مطلوب عند وجود ضريبة على الاستلام."""
    acc = (
        Account.objects.filter(tenant=tenant, code="1105").first()
        or Account.objects.filter(
            tenant=tenant, account_type="Asset", name__icontains="ضريبة",
        ).first()
    )
    if not acc or acc.account_type != "Asset":
        raise ValidationError(
            "ضريبة المدخلات > 0 تتطلب حساب «1105 ضريبة مدخلات» من نوع Asset."
        )
    return acc


def _resolve_gr_ir_account(tenant) -> Account:
    """الحساب الوسيط «بضاعة مُستلَمة لم تُفوتَر» (GR/IR Clearing، كود 2110).

    يفصل حدث استلام البضاعة عن الالتزام للمورّد: قيد الاستلام يدائنه، وقيد
    الفاتورة يدينه — فيُصفَّر عندما يُنشآن معاً. يُنشأ تلقائياً للمستأجرين الذين
    لم تُبذَر شجرتهم بعد (لا يتطلب إعادة seed).
    """
    acc = Account.objects.filter(tenant=tenant, code=GR_IR_ACCOUNT_CODE).first()
    if acc:
        if acc.name != GR_IR_ACCOUNT_NAME or acc.account_type != "Liability":
            logger.error(
                "GR/IR account code collision: tenant=%s code=%s account=%s name=%r type=%s",
                tenant.TenantID, GR_IR_ACCOUNT_CODE, acc.id, acc.name, acc.account_type,
            )
            raise ValidationError(
                f"رمز حساب وسيط الاستلام {GR_IR_ACCOUNT_CODE} مستخدم لحساب آخر."
            )
        return acc
    parent = Account.objects.filter(tenant=tenant, code="21").first()
    acc, created = Account.objects.get_or_create(
        tenant=tenant,
        code=GR_IR_ACCOUNT_CODE,
        defaults={
            "name": GR_IR_ACCOUNT_NAME,
            "account_type": "Liability",
            "parent": parent,
            "is_active": True,
        },
    )
    if created:
        logger.info(
            "Created GR/IR clearing account: tenant=%s account=%s code=%s",
            tenant.TenantID, acc.id, GR_IR_ACCOUNT_CODE,
        )
    return acc


def goods_clearing_unit_costs(invoice, total_clearing):
    """يوزّع قيمة البضاعة المارّة بالوسيط (GR/IR) على بنود الفاتورة بنسبة قيمة
    السطر، ويُرجع {item_id: (تكلفة الوحدة, حصة السطر)}.

    مصدر توزيع واحد لقيد الاستلام عند الترحيل ولاستلام البنود لاحقاً — فتتطابق
    قيمة المخزون الفعلية (WAC) مع رصيد حساب المخزون في الدفتر مهما كان المسار.
    آخر سطر يأخذ الباقي لتفادي فروق التقريب.
    """
    goods_lines = [
        it for it in invoice.items.all()
        if it.product_id and not it.expense_account_id
        and Decimal(str(it.quantity or 0)) > 0
    ]
    base = sum(
        (Decimal(str(it.total_price or it.quantity * it.unit_price or 0)) for it in goods_lines),
        Decimal('0'),
    )
    total_clearing = Decimal(str(total_clearing or 0))
    out: dict[int, tuple[Decimal, Decimal]] = {}
    allocated = Decimal('0')
    for idx, it in enumerate(goods_lines):
        qty = Decimal(str(it.quantity or 0))
        line_val = Decimal(str(it.total_price or it.quantity * it.unit_price or 0))
        if idx == len(goods_lines) - 1:
            cost_share = total_clearing - allocated
        elif base > 0:
            cost_share = (total_clearing * line_val / base).quantize(DEC)
        else:
            cost_share = Decimal('0')
        allocated += cost_share
        out[it.id] = ((cost_share / qty) if qty > 0 else Decimal('0'), cost_share)
    return out


def open_goods_clearing(invoice):
    """وسيط الاستلام (GR/IR) لفاتورة مرحّلة: (الحساب، إجمالي المدين، الرصيد المفتوح).

    المفتوح = مدين الوسيط في قيد الفاتورة ناقص ما صُفِّي منه بقيود الاستلام
    (PURCHASE_GRN). صفر = لا شيء ينتظر الاستلام محاسبياً (فاتورة بلا وسيط، أو
    استُلمت بالكامل).
    """
    from django.db.models import Sum
    from accounting.models import JournalLine

    acc = Account.objects.filter(
        tenant=invoice.tenant, code=GR_IR_ACCOUNT_CODE,
    ).first()
    if acc is None:
        return None, Decimal('0'), Decimal('0')
    rows = JournalLine.objects.filter(
        tenant_id=invoice.tenant_id,
        account=acc,
        journal__reference_id=invoice.pk,
        journal__reference_type__in=('PURCHASE_INVOICE', 'PURCHASE_GRN'),
    ).aggregate(d=Sum('debit'), c=Sum('credit'))
    total = Decimal(str(rows['d'] or 0)).quantize(DEC)
    open_amt = (total - Decimal(str(rows['c'] or 0))).quantize(DEC)
    return acc, total, (open_amt if open_amt > 0 else Decimal('0'))


def next_goods_receipt_number(tenant_id, branch=None) -> str:
    """رقم إرسالية الشراء التالي — عبر دفاتر الترقيم المركزية (GRN-0001)."""
    from accounting.services import next_document_number

    seq = next_document_number(
        tenant_id, 'goods_receipt', branch_id=branch.id if branch else None,
    )
    return f"GRN-{seq:04d}"


def create_goods_receipt_document(
    tenant, *, lines, invoice=None, partner=None, branch=None, user=None,
    receipt_date=None, notes='', supplier_ref='', auto_created=False, journal=None,
    receipt=None, allow_empty=False,
):
    """يوثّق حدث الاستلام كمستند «إرسالية شراء» ببنوده.

    lines: [{'item': PurchaseInvoiceItem|None, 'product_id': int, 'quantity': Decimal,
             'warehouse': Warehouse|None, 'unit_price': Decimal, 'movement': StockMovement|None}]

    مصدر واحد يستدعيه: الاستلام اليدوي، والاستلام التلقائي مع الترحيل، وسند
    الاستلام المستقل — فلا يوجد استلام بلا مستند يوثّقه. `receipt` مُمرَّراً =
    إعادة بناء بنود إرسالية قائمة (تعديل) بنفس رقمها.
    """
    import datetime
    from .models import GoodsReceipt, GoodsReceiptLine

    if not lines and not allow_empty:
        return None
    tenant_id = getattr(tenant, 'TenantID', tenant)
    default_date = (invoice.invoice_date if invoice else None) or datetime.date.today()
    if receipt is None:
        receipt = GoodsReceipt.objects.create(
            tenant=tenant,
            branch=branch,
            receipt_number=next_goods_receipt_number(tenant_id, branch),
            invoice=invoice,
            partner=partner or (invoice.partner if invoice else None),
            supplier_ref=(supplier_ref or '')[:100],
            receipt_date=receipt_date or default_date,
            notes=(notes or '')[:500],
            auto_created=auto_created,
            journal=journal,
            created_by=user if (user and not getattr(user, 'is_anonymous', False)) else None,
        )
    else:
        receipt.lines.all().delete()
        receipt.receipt_date = receipt_date or receipt.receipt_date
        receipt.notes = (notes or '')[:500]
        receipt.supplier_ref = (supplier_ref or '')[:100]
        receipt.partner = partner or (invoice.partner if invoice else receipt.partner)
        receipt.journal = journal
        receipt.save(update_fields=[
            'receipt_date', 'notes', 'supplier_ref', 'partner', 'journal',
        ])
    for row in lines:
        if not row.get('product_id'):
            continue
        GoodsReceiptLine.objects.create(
            tenant=receipt.tenant,
            receipt=receipt,
            item=row.get('item'),
            product_id=row['product_id'],
            warehouse=row.get('warehouse'),
            quantity=row['quantity'],
            unit_price=row.get('unit_price') or Decimal('0'),
            movement=row.get('movement'),
        )
    return receipt


def receive_purchase_invoice(invoice, *, lines, branch=None, user=None, movement_date=None,
                             receipt_date=None, notes='', supplier_ref='',
                             existing_receipt=None):
    """استلام بضاعة فاتورة شراء محلية إلى المخزن (انعكاس على المستودع + قيد).

    حصري للفواتير المحلية (غير مستوردة: بلا صفقة/شحنة/تخليص) — مسار الاستيراد
    يستلم البضاعة عبر تخليص الشحنة، لا من هنا.

    lines: قائمة [{'item_id': int, 'quantity': Decimal, 'warehouse_id': int}].
    لكل بند ذي صنف مخزون: تُنشأ حركة IN (متوسط مرجح) موسومة بالفرع والمستودع،
    ويُحدَّث received_quantity. ثم يُرحَّل قيد استلام للقيمة المستلمة في هذا النداء:

    - فاتورة **مرحّلة** (الاستلام مؤجَّل عن الترحيل): مدين المخزون / دائن وسيط
      الاستلام (GR/IR) — ذمم المورد دُوئنت في قيد الفاتورة، فتكرارها هنا يُضاعف
      دينه. التكلفة من توزيع مدين الوسيط نفسه فيُصفَّر تماماً عند اكتمال الاستلام.
    - فاتورة **غير مرحّلة** (المسار القديم): مدين مخزون + ضريبة مدخلات / دائن
      ذمم المورد، ويُعدّ الاستلام ترحيلاً للفاتورة.

    العملية ذرّية. إعادة الإرسال مرفوضة ضمنياً: لا يمكن استلام أكثر من المطلوب،
    فإن استُلمت الكميات كلها يرفض النداء التالي «لا يوجد ما يُستلَم».
    """
    import datetime
    import logging
    from inventory.models import Warehouse
    from inventory.serials import apply_purchase_serials
    from inventory.services import record_stock_movement
    from accounting.services import post_journal
    from .models import PurchaseInvoice

    logger = logging.getLogger(__name__)

    if invoice.deal_id or invoice.shipment_id or invoice.clearance_id:
        raise ValidationError(
            "هذه فاتورة مستوردة — يتم استلام بضاعتها من تخليص الشحنة، لا من الفاتورة."
        )

    if not lines:
        raise ValidationError("حدّد البنود والكميات المراد استلامها.")

    if movement_date is None:
        movement_date = invoice.invoice_date or datetime.date.today()

    base_factor = Decimal(str(invoice.exchange_rate or 1))
    items_by_id = {it.id: it for it in invoice.items.select_related('product').all()}

    # الفاتورة المرحّلة: التكلفة من توزيع مدين وسيط الاستلام (كي يتطابق المخزون
    # الفعلي مع الدفتر ويُصفَّر الوسيط)، وقيدها يدائن الوسيط لا ذمم المورد.
    gr_ir_account, gr_ir_total, gr_ir_open = (
        open_goods_clearing(invoice) if invoice.is_posted else (None, Decimal('0'), Decimal('0'))
    )
    use_clearing = bool(invoice.is_posted and gr_ir_account and gr_ir_open > 0)
    clearing_costs = (
        goods_clearing_unit_costs(invoice, gr_ir_total) if use_clearing else {}
    )

    inv_net = Decimal('0')   # صافي قيمة المخزون المستلمة (بالعملة الأساس)
    inv_vat = Decimal('0')   # ضريبة المدخلات على المستلَم (المسار غير المرحّل فقط)
    movements = []

    with transaction.atomic():
        # مرحلة أولى: تحقّق واحسب — كي تُعرف الكميات كلها قبل الترحيل، فيُصفَّى
        # الوسيط بالضبط عند الاستلام الأخير بلا كسور تقريب متروكة.
        planned = []
        for raw in lines:
            item_id = raw.get('item_id')
            item = items_by_id.get(int(item_id)) if item_id is not None else None
            if not item:
                raise ValidationError(f"البند {item_id} لا ينتمي لهذه الفاتورة.")
            if not item.product_id:
                raise ValidationError(
                    f"البند «{item.name}» بلا صنف مخزون مربوط — لا يمكن استلامه."
                )

            try:
                qty = Decimal(str(raw.get('quantity', 0)))
            except Exception:
                raise ValidationError(f"كمية غير صالحة للبند «{item.name}».")
            if qty <= 0:
                continue

            ordered = Decimal(str(item.quantity or 0))
            already = Decimal(str(item.received_quantity or 0))
            remaining = ordered - already
            if qty > remaining:
                raise ValidationError(
                    f"البند «{item.name}»: الكمية المطلوب استلامها ({qty}) "
                    f"تتجاوز المتبقي ({remaining})."
                )

            wh = Warehouse.objects.filter(
                pk=raw.get('warehouse_id'), tenant=invoice.tenant
            ).first()
            if not wh:
                raise ValidationError(f"المستودع المحدد للبند «{item.name}» غير موجود.")

            if use_clearing:
                unit_cost = clearing_costs.get(item.id, (Decimal('0'), Decimal('0')))[0]
                line_vat = Decimal('0')
            else:
                unit_price = Decimal(str(item.unit_price or 0))
                if unit_price <= 0:
                    # احتياطي: اشتقاق تكلفة الوحدة من إجمالي السطر إن كان سعر الوحدة صفراً
                    total_price = Decimal(str(item.total_price or 0))
                    if total_price > 0 and ordered > 0:
                        unit_price = total_price / ordered
                unit_cost = (unit_price * base_factor)
                vat_pct = (
                    Decimal(str(item.vat_percent or 0)) if item.is_taxable else Decimal('0')
                )
                line_vat = (
                    (qty * unit_cost).quantize(DEC) * vat_pct / Decimal('100')
                ).quantize(DEC)
            planned.append({
                'item': item, 'qty': qty, 'warehouse': wh,
                'unit_cost': unit_cost,
                'line_net': (qty * unit_cost).quantize(DEC),
                'line_vat': line_vat,
            })

        if not planned:
            raise ValidationError("لا يوجد ما يُستلَم — تحقق من الكميات.")

        # هل تكتمل الفاتورة بهذا الاستلام؟ عندها يُصفَّى الوسيط بالكامل — يُحمَّل
        # الفارق (كسور التوزيع) على آخر بند فيتطابق الدفتر مع قيمة المخزون.
        planned_qty = {}
        for p in planned:
            planned_qty[p['item'].id] = planned_qty.get(p['item'].id, Decimal('0')) + p['qty']
        completes_invoice = all(
            Decimal(str(it.received_quantity or 0)) + planned_qty.get(it.id, Decimal('0'))
            >= Decimal(str(it.quantity or 0))
            for it in items_by_id.values() if it.product_id
        )
        if use_clearing and completes_invoice:
            residual = gr_ir_open - sum((p['line_net'] for p in planned), Decimal('0'))
            # يُحمَّل على آخر بند له قيمة موجبة، وبشرط ألّا يقلبها سالبة: بقاء
            # كسر في الوسيط أهون من مدين مخزون سالب.
            target = next(
                (p for p in reversed(planned)
                 if p['qty'] > 0 and p['item'].id in clearing_costs), None,
            )
            if residual and target is not None and target['line_net'] + residual >= 0:
                target['line_net'] = (target['line_net'] + residual).quantize(DEC)
                target['unit_cost'] = target['line_net'] / target['qty']

        for p in planned:
            item, qty, wh = p['item'], p['qty'], p['warehouse']
            p['movement'] = mv = record_stock_movement(
                product=item.product,
                movement_type='IN',
                quantity=qty,
                unit_cost=p['unit_cost'],
                reference_type='PURCHASE_INVOICE',
                reference_id=invoice.id,
                partner=invoice.partner,
                movement_date=movement_date,
                notes=f"استلام فاتورة {invoice.invoice_number} | مستودع {wh.name}",
                tenant=invoice.tenant,
                branch=branch,
                warehouse=wh,
            )
            movements.append(mv)

            item.received_quantity = Decimal(str(item.received_quantity or 0)) + qty
            item.warehouse = wh.name
            item.save(update_fields=['received_quantity', 'warehouse'])

            inv_net += p['line_net']
            inv_vat += p['line_vat']

        # الوحدات المُرقَّمة تدخل المخزن مع بضاعتها — لا قبل ذلك: بندٌ يحمل أرقاماً
        # ولم يُستلَم بعد ليس مخزوناً. مُطفأ ما لم تطلبه الشركة من إعدادات الشراء.
        apply_purchase_serials(
            tenant=invoice.tenant, rows=[(p['item'], p['qty']) for p in planned],
        )

        # ── ترحيل قيد الاستلام للقيمة المستلمة في هذا النداء ──
        # استلام بقيمة صفرية (فاتورة كمية فقط بلا أسعار) مشروع: ينعكس على المخزن
        # دون قيد محاسبي (لا قيد فارغ يُرفض من post_journal).
        gross = (inv_net + inv_vat).quantize(DEC)
        journal = None
        if gross > 0:
            inventory_account = _resolve_inventory_account(invoice.tenant)
            if use_clearing:
                # قيد استلام مستقل: مدين المخزون / دائن الوسيط. لا شريك على أيّ
                # منهما — ليسا حسابين رقابيين، ووسمهما بالمورد يلوّث كشف حسابه.
                lines_payload = [
                    {'account': inventory_account.id, 'debit': inv_net,
                     'credit': Decimal('0'), 'partner': None,
                     'description': f"مخزون مستلَم — {invoice.invoice_number}"[:500]},
                    {'account': gr_ir_account.id, 'debit': Decimal('0'),
                     'credit': inv_net, 'partner': None,
                     'description': f"تصفية وسيط الاستلام — {invoice.invoice_number}"[:500]},
                ]
                reference_type = 'PURCHASE_GRN'
            else:
                # Feature 2: قيد الاستلام يدين المخزون/الضريبة ويدائن ذمم المورد بالكامل
                # فقط — لا يُسوّي النقدية. الدفع للمورد يُسجَّل كوصل دفع مستقل
                # (SupplierPayment، Dr ذمم المورد / Cr صندوق) بعد الاستلام.
                ap_account = _resolve_ap_account(invoice.partner)
                lines_payload = [
                    {'account': inventory_account.id, 'debit': inv_net, 'credit': Decimal('0'),
                     'partner': invoice.partner_id},
                ]
                if inv_vat > 0:
                    vat_acc = _resolve_vat_input_account(invoice.tenant)
                    lines_payload.append({
                        'account': vat_acc.id, 'debit': inv_vat, 'credit': Decimal('0'),
                        'partner': invoice.partner_id,
                    })

                # دائن ذمم المورد بكامل القيمة المستلمة
                lines_payload.append({
                    'account': ap_account.id, 'debit': Decimal('0'), 'credit': gross,
                    'partner': invoice.partner_id,
                })
                reference_type = 'PURCHASE_INVOICE'

            journal = post_journal(
                tenant_id=invoice.tenant_id,
                transaction_date=movement_date,
                reference_type=reference_type,
                reference_id=invoice.id,
                description=f"استلام بضاعة فاتورة {invoice.invoice_number} | {invoice.partner.name}"[:500],
                lines_data=lines_payload,
                branch_id=branch.id if branch else None,
                user=user if user and not getattr(user, 'is_anonymous', False) else None,
                idempotent=False,
            )

        # ── تحديث حالة الاستلام للفاتورة ──
        product_items = [it for it in items_by_id.values() if it.product_id]
        fully = all(
            Decimal(str(it.received_quantity or 0)) >= Decimal(str(it.quantity or 0))
            for it in product_items
        )
        any_received = any(
            Decimal(str(it.received_quantity or 0)) > 0 for it in product_items
        )
        invoice.receipt_status = (
            PurchaseInvoice.RECEIPT_FULL if fully
            else PurchaseInvoice.RECEIPT_PARTIAL if any_received
            else PurchaseInvoice.RECEIPT_NOT
        )
        update_fields = ['receipt_status']
        if journal is not None and not invoice.is_posted:
            invoice.is_posted = True
            invoice.journal = journal
            update_fields += ['is_posted', 'journal']
        invoice.save(update_fields=update_fields)

        # مستند الإرسالية يوثّق ما استُلم في هذا النداء (بنوده وكمياته ومستودعاته).
        receipt = create_goods_receipt_document(
            invoice.tenant,
            invoice=invoice,
            lines=[{
                'item': p['item'],
                'product_id': p['item'].product_id,
                'quantity': p['qty'],
                'warehouse': p['warehouse'],
                'unit_price': p['unit_cost'],
                'movement': p.get('movement'),
            } for p in planned],
            branch=branch, user=user, receipt_date=receipt_date or movement_date,
            notes=notes, supplier_ref=supplier_ref, journal=journal,
            receipt=existing_receipt,
        )

        # نموذج «تكلفة المنتجات»: اجعل avg_cost المتوسط المرجّح للمشتريات المرحّلة
        # (مصدر الحقيقة الجديد) كي يقرأ ترحيل COGS عند البيع القيمة الصحيحة.
        if invoice.is_posted:
            # النموذج الدوري يَضبط avg_cost من كل المشتريات؛ أما شركات المتوسط
            # المرجّح المتحرك فيُترك WAC الذي بناه record_stock_movement (تكلفة
            # لحظة البيع) كما هو. القرار مركزي في apply_purchase_cost_model.
            from inventory.services import apply_purchase_cost_model
            seen = set()
            for it in product_items:
                if it.product_id and it.product_id not in seen:
                    seen.add(it.product_id)
                    apply_purchase_cost_model(it.product)

    logger.info(
        "Purchase invoice #%s received: %d movement(s), receipt_status=%s, journal=%s, receipt=%s",
        invoice.id, len(movements), invoice.receipt_status,
        journal.id if journal else None, receipt.receipt_number if receipt else None,
    )
    return {
        'movements': movements, 'journal': journal,
        'receipt_status': invoice.receipt_status, 'receipt': receipt,
    }


def create_standalone_goods_receipt(
    tenant, *, partner, lines, branch=None, user=None, receipt_date=None,
    notes='', supplier_ref='', receipt=None,
):
    """سند استلام مستقل — بضاعة وصلت قبل فاتورتها (GR/IR الكلاسيكي).

    lines: [{'product_id': int, 'quantity': Decimal, 'unit_price': Decimal,
             'warehouse_id': int}]

    القيد: مدين المخزون / دائن «بضاعة مُستلَمة لم تُفوتَر» (2110) — فحين تصل
    الفاتورة لاحقاً يُدين قيدُها الوسيطَ نفسه فيُصفَّر. بلا أسعار (استلام كمية
    فقط) ينعكس على المخزن دون قيد، كاستلام الفاتورة صفرية القيمة.
    """
    import datetime
    from inventory.models import Warehouse
    from inventory.services import record_stock_movement, apply_purchase_cost_model
    from accounting.services import post_journal
    from inventory.models import Product

    if not lines:
        raise ValidationError('حدّد الأصناف والكميات المستلمة.')
    if partner is None:
        raise ValidationError('حدّد المورد لسند الاستلام المستقل.')

    movement_date = receipt_date or datetime.date.today()
    tenant_id = getattr(tenant, 'TenantID', tenant)
    products = {
        p.id: p for p in Product.objects.filter(
            tenant_id=tenant_id,
            pk__in=[row.get('product_id') for row in lines if row.get('product_id')],
        )
    }

    planned = []
    total_value = Decimal('0')
    for raw in lines:
        product = products.get(int(raw.get('product_id') or 0))
        if product is None:
            raise ValidationError(f"الصنف {raw.get('product_id')} غير موجود في هذه الشركة.")
        try:
            qty = Decimal(str(raw.get('quantity', 0)))
        except Exception:
            raise ValidationError(f"كمية غير صالحة للصنف «{product}».")
        if qty <= 0:
            continue
        try:
            unit_cost = Decimal(str(raw.get('unit_price', 0) or 0))
        except Exception:
            unit_cost = Decimal('0')
        wh = Warehouse.objects.filter(
            pk=raw.get('warehouse_id'), tenant_id=tenant_id,
        ).first()
        if not wh:
            raise ValidationError(f"المستودع المحدد للصنف «{product}» غير موجود.")
        planned.append({
            'product': product, 'qty': qty, 'warehouse': wh, 'unit_cost': unit_cost,
        })
        total_value += (qty * unit_cost).quantize(DEC)

    if not planned:
        raise ValidationError('لا يوجد ما يُستلَم — تحقق من الكميات.')

    # السند المستقل لا يحمل أرقاماً تسلسلية: تحت «إجباري» يُرفض بدل أن يُدخل
    # مخزوناً غير متتبَّع يرفض البيعُ بيعه لاحقاً.
    from inventory.serials import assert_receipt_without_serials_allowed
    assert_receipt_without_serials_allowed(tenant_id, [p['product'] for p in planned])

    with transaction.atomic():
        journal = None
        doc = receipt
        if doc is None:
            # الرأس أولاً كي تحمل حركات المخزون مرجعه، ثم تُملأ بنوده بعد الحركات.
            doc = create_goods_receipt_document(
                tenant, invoice=None, partner=partner, lines=[], branch=branch,
                user=user, receipt_date=movement_date, notes=notes,
                supplier_ref=supplier_ref, allow_empty=True,
            )
        for p in planned:
            p['movement'] = record_stock_movement(
                product=p['product'],
                movement_type='IN',
                quantity=p['qty'],
                unit_cost=p['unit_cost'],
                reference_type='GOODS_RECEIPT',
                reference_id=(doc.id if doc else 0),
                partner=partner,
                movement_date=movement_date,
                notes=f"سند استلام | مستودع {p['warehouse'].name}",
                tenant=tenant,
                branch=branch,
                warehouse=p['warehouse'],
            )

        if total_value > 0:
            inventory_account = _resolve_inventory_account(tenant)
            gr_ir_account = _resolve_gr_ir_account(tenant)
            journal = post_journal(
                tenant_id=tenant_id,
                transaction_date=movement_date,
                reference_type='GOODS_RECEIPT',
                reference_id=doc.id,
                description=f"سند استلام {doc.receipt_number} | {partner.name}"[:500],
                lines_data=[
                    {'account': inventory_account.id, 'debit': total_value,
                     'credit': Decimal('0'), 'partner': None,
                     'description': f"مخزون مستلَم — {doc.receipt_number}"[:500]},
                    {'account': gr_ir_account.id, 'debit': Decimal('0'),
                     'credit': total_value, 'partner': None,
                     'description': f"بضاعة مستلَمة لم تُفوتَر — {doc.receipt_number}"[:500]},
                ],
                branch_id=branch.id if branch else None,
                user=user if user and not getattr(user, 'is_anonymous', False) else None,
                idempotent=False,
            )

        create_goods_receipt_document(
            tenant, invoice=None, partner=partner,
            lines=[{
                'item': None,
                'product_id': p['product'].id,
                'quantity': p['qty'],
                'warehouse': p['warehouse'],
                'unit_price': p['unit_cost'],
                'movement': p['movement'],
            } for p in planned],
            branch=branch, user=user, receipt_date=movement_date, notes=notes,
            supplier_ref=supplier_ref, journal=journal, receipt=doc,
        )

        for p in planned:
            apply_purchase_cost_model(p['product'])

    logger.info(
        'Standalone goods receipt %s: %d line(s), value=%s, journal=%s',
        doc.receipt_number, len(planned), total_value, journal.id if journal else None,
    )
    return {'receipt': doc, 'journal': journal, 'movements': [p['movement'] for p in planned]}


def void_goods_receipt(receipt, *, user=None):
    """يعكس أثر إرسالية واحدة: حركاتها وقيدها وكمياتها المستلمة — دون غيرها.

    التتبّع عبر `GoodsReceiptLine.movement`، فلا تُمسّ إرساليات أخرى لنفس
    الفاتورة (بخلاف الحذف بالمرجع الذي يطالها كلها).
    """
    from accounting.models import JournalHeader
    from inventory.models import StockMovement
    from inventory.serials import release_purchase_serials
    from inventory.services import _recompute_product_stock, apply_purchase_cost_model
    from .models import PurchaseInvoice

    with transaction.atomic():
        lines = list(receipt.lines.select_related('item', 'product', 'movement'))
        movement_ids = [l.movement_id for l in lines if l.movement_id]
        products = {l.product_id: l.product for l in lines if l.product_id}

        # الوحدات المُرقَّمة تخرج مع بضاعتها. الحصّة التي جاءت بهذه الإرسالية هي
        # الأحدث (الاستلام يُنشئ بالترتيب والبيع يستهلك من الأقدم)، وأيُّ وحدة
        # مُباعة منها تمنع الإلغاء — لا بيع لوحدة يُمحى أصلها.
        quantities_by_item: dict[int, Decimal] = {}
        for line in lines:
            if not line.item_id:
                continue
            quantities_by_item[line.item_id] = (
                quantities_by_item.get(line.item_id, Decimal('0'))
                + Decimal(str(line.quantity or 0))
            )
        if quantities_by_item:
            release_purchase_serials(
                tenant_id=receipt.tenant_id,
                quantities_by_item=quantities_by_item,
                document_label=f"إلغاء الإرسالية {receipt.receipt_number}",
            )

        if movement_ids:
            StockMovement.objects.filter(pk__in=movement_ids).delete()

        # قيد هذه الإرسالية وحدها (قد تشترك عدة إرساليات في مرجع الفاتورة).
        if receipt.journal_id:
            JournalHeader.objects.filter(pk=receipt.journal_id).delete()

        invoice = receipt.invoice
        if invoice is not None:
            for line in lines:
                if line.item_id is None:
                    continue
                item = line.item
                item.received_quantity = max(
                    Decimal('0'),
                    Decimal(str(item.received_quantity or 0)) - Decimal(str(line.quantity or 0)),
                )
                item.save(update_fields=['received_quantity'])

        receipt_id = receipt.id
        receipt_number = receipt.receipt_number
        receipt.delete()

        for product in products.values():
            _recompute_product_stock(product)
            apply_purchase_cost_model(product)

        if invoice is not None:
            product_items = [it for it in invoice.items.all() if it.product_id]
            fully = product_items and all(
                Decimal(str(it.received_quantity or 0)) >= Decimal(str(it.quantity or 0))
                for it in product_items
            )
            any_received = any(
                Decimal(str(it.received_quantity or 0)) > 0 for it in product_items
            )
            invoice.receipt_status = (
                PurchaseInvoice.RECEIPT_FULL if fully
                else PurchaseInvoice.RECEIPT_PARTIAL if any_received
                else PurchaseInvoice.RECEIPT_NOT
            )
            invoice.save(update_fields=['receipt_status'])

    logger.info(
        'Goods receipt %s (#%s) voided: %d movement(s) reversed',
        receipt_number, receipt_id, len(movement_ids),
    )
    return {'movements_reversed': len(movement_ids)}


def returnable_lines_for_invoice(original_invoice):
    """W6: بنود الفاتورة الأصلية مع (المفوتر · المرتجع سابقاً · المتبقّي القابل للإرجاع)
    لكل صنف — يغذّي منتقي بنود المرجع في الواجهة. مصدر حقيقة واحد مع حارس الإنشاء.
    يُجمّع بالصنف (لو تكرّر الصنف في أسطر الفاتورة)."""
    from decimal import Decimal as _D
    from .models import PurchaseInvoiceItem

    if original_invoice is None:
        return []

    orig: dict[int, dict] = {}
    for it in original_invoice.items.all():
        if not it.product_id:
            continue
        row = orig.setdefault(it.product_id, {
            'product': it.product_id,
            'name': it.name or (getattr(it.product, 'name_ar', None) or str(it.product_id)),
            'unit_price': _D(str(it.unit_price or 0)),
            'invoiced_qty': _D('0'),
        })
        row['invoiced_qty'] += _D(str(it.quantity or 0))

    returned: dict[int, _D] = {}
    prior = PurchaseInvoiceItem.objects.filter(
        invoice__original_invoice=original_invoice,
        invoice__is_return=True,
    ).values_list('product_id', 'quantity')
    for pid, q in prior:
        if pid:
            returned[pid] = returned.get(pid, _D('0')) + _D(str(q or 0))

    out = []
    for pid, row in orig.items():
        ret_q = returned.get(pid, _D('0'))
        remaining = row['invoiced_qty'] - ret_q
        out.append({
            'product': pid,
            'name': row['name'],
            'unit_price': str(row['unit_price']),
            'invoiced_qty': str(row['invoiced_qty']),
            'returned_qty': str(ret_q),
            'remaining_qty': str(remaining if remaining > 0 else _D('0')),
        })
    return out


def create_purchase_return(
    tenant, *, original_invoice, partner, return_date, lines, notes='',
    invoice_number=None, currency=None, exchange_rate=None, user=None,
):
    """مرجع شراء: إنشاء فاتورة إرجاع للمورد **كمسودة** (بلا ترحيل).

    يُخزَّن المستند فقط (status='draft'، is_posted=False) — لا حركة مخزون ولا قيد.
    الترحيل خطوة منفصلة عبر `post_purchase_return` (زر «ترحيل» من فواتير الشراء).
    نسبة الضريبة تُشتق من بنود الفاتورة الأصلية وتُخزَّن على بند المرجع كي يقرأها
    الترحيل لاحقاً.

    lines: [{'product': int, 'quantity': Decimal, 'unit_price': Decimal}].
    """
    import datetime
    from decimal import Decimal as _D
    from inventory.models import Product
    from .models import PurchaseInvoice, PurchaseInvoiceItem

    if return_date is None:
        return_date = datetime.date.today()
    if partner is None:
        raise ValidationError("المورد مطلوب لمرجع الشراء.")
    if partner.tenant_id != tenant.TenantID:
        raise ValidationError("المورد لا يتبع نفس الشركة.")

    # نسبة الضريبة لكل صنف من الفاتورة الأصلية (لعكسها بدقة عند الترحيل).
    vat_by_product: dict[int, _D] = {}
    if original_invoice is not None:
        for it in original_invoice.items.all():
            if it.product_id and getattr(it, 'is_taxable', False):
                vat_by_product[it.product_id] = _D(str(it.vat_percent or 0))

    clean_lines = []
    for raw in lines or []:
        pid = raw.get('product')
        if not pid:
            continue
        try:
            qty = _D(str(raw.get('quantity', 0)))
            price = _D(str(raw.get('unit_price', 0)))
        except Exception:
            raise ValidationError("كمية أو سعر غير صالح في أحد البنود.")
        if qty <= 0:
            continue
        clean_lines.append({'product': int(pid), 'quantity': qty, 'unit_price': price})
    if not clean_lines:
        raise ValidationError("أضِف بنداً واحداً على الأقل بكمية موجبة.")

    products = {
        p.id: p for p in Product.objects.filter(
            tenant=tenant, id__in=[l['product'] for l in clean_lines],
        )
    }
    base_factor = _D(str(exchange_rate if exchange_rate is not None else 1))

    with transaction.atomic():
        # W6: منع تجاوز الكمية المرتجعة الكمية الأصلية المفوترة (لكل صنف). المتبقّي
        # القابل للإرجاع = المفوتر − (مجموع كل المراجيع السابقة لنفس الفاتورة الأصلية).
        if original_invoice is not None:
            orig_qty: dict[int, _D] = {}
            for it in original_invoice.items.all():
                if it.product_id:
                    orig_qty[it.product_id] = orig_qty.get(it.product_id, _D('0')) + _D(str(it.quantity or 0))
            returned_qty: dict[int, _D] = {}
            prior = PurchaseInvoiceItem.objects.filter(
                invoice__original_invoice=original_invoice,
                invoice__is_return=True,
            ).values_list('product_id', 'quantity')
            for pid, q in prior:
                if pid:
                    returned_qty[pid] = returned_qty.get(pid, _D('0')) + _D(str(q or 0))
            for l in clean_lines:
                pid = l['product']
                allowed = orig_qty.get(pid, _D('0')) - returned_qty.get(pid, _D('0'))
                if l['quantity'] > allowed:
                    prod = products.get(pid)
                    pname = (getattr(prod, 'name_ar', None) or getattr(prod, 'sku', None)
                             or f"#{pid}") if prod else f"#{pid}"
                    remaining = allowed if allowed > 0 else _D('0')
                    raise ValidationError(
                        f"الكمية المرتجعة للصنف «{pname}» ({l['quantity']}) تتجاوز المتبقّي "
                        f"القابل للإرجاع ({remaining}) من أصل {orig_qty.get(pid, _D('0'))} مفوترة."
                    )

        if not invoice_number:
            last = (
                PurchaseInvoice.objects.filter(tenant=tenant, is_return=True)
                .order_by('-id').values_list('invoice_number', flat=True).first()
            )
            if last and last.startswith('PRET-'):
                try:
                    seq = int(last.split('-')[1]) + 1
                except (ValueError, IndexError):
                    seq = PurchaseInvoice.objects.filter(tenant=tenant, is_return=True).count() + 1
            else:
                seq = PurchaseInvoice.objects.filter(tenant=tenant, is_return=True).count() + 1
            invoice_number = f"PRET-{seq:04d}"

        if currency is None:
            currency = getattr(original_invoice, 'currency', None)
        if currency is None:
            from tenants.models import Currency
            currency = Currency.objects.filter(IsBaseCurrency=True).first() \
                or Currency.objects.order_by('CurrencyID').first()
        if currency is None:
            raise ValidationError("لا توجد عملة معرّفة للمرجع.")

        ret = PurchaseInvoice.objects.create(
            tenant=tenant,
            invoice_number=invoice_number,
            invoice_date=return_date,
            invoice_type=PurchaseInvoice.INVOICE_TYPE_LOCAL,
            partner=partner,
            currency=currency,
            exchange_rate=base_factor,
            is_return=True,
            original_invoice=original_invoice,
            payment_type=PurchaseInvoice.PAYMENT_TYPE_CREDIT,
            status='draft',
            is_posted=False,
            notes=notes or '',
            created_by=user if user and not getattr(user, 'is_anonymous', False) else None,
        )

        inv_net = _D('0')
        inv_vat = _D('0')
        for l in clean_lines:
            prod = products.get(l['product'])
            if prod is None:
                raise ValidationError(f"الصنف {l['product']} غير موجود أو لا يتبع الشركة.")
            qty = l['quantity']
            line_net = (qty * l['unit_price'] * base_factor).quantize(DEC)
            vat_pct = vat_by_product.get(prod.id, _D('0'))
            inv_net += line_net
            inv_vat += (line_net * vat_pct / _D('100')).quantize(DEC)

            PurchaseInvoiceItem.objects.create(
                invoice=ret, product=prod,
                name=getattr(prod, 'name_ar', None) or getattr(prod, 'name', '') or str(prod),
                quantity=qty, unit_price=l['unit_price'],
                total_price=(qty * l['unit_price']).quantize(DEC),
                is_taxable=vat_pct > 0,
                vat_percent=vat_pct,
            )

        ret.subtotal = inv_net
        ret.tax_amount = inv_vat
        ret.grand_total = (inv_net + inv_vat).quantize(DEC)
        ret.save(update_fields=['subtotal', 'tax_amount', 'grand_total'])

    return ret


def post_purchase_return(invoice, *, user=None):
    """ترحيل مرجع شراء (مسودة): يُخرج الكمية من المخزن (RETURN_OUT) ويُرحّل قيداً
    عكسياً للشراء (Dr ذمم المورد الإجمالي / Cr مخزون الصافي + Cr ض.مدخلات).

    الأموال: المرجع يُخفّض ذمم المورد؛ إن كانت الفاتورة مدفوعة يصبح المورد مديناً
    لنا (رصيد سالب) يُحصَّل بسند صرف/قبض مستقل — مطابقةً لتدفّق النظام القائم.
    """
    import datetime
    import logging
    from decimal import Decimal as _D
    from inventory.serials import release_returned_purchase_serials
    from inventory.services import record_stock_movement
    from accounting.services import post_journal, validate_fiscal_period

    logger = logging.getLogger(__name__)

    if not getattr(invoice, 'is_return', False):
        raise ValidationError("هذه ليست فاتورة مرجع شراء.")
    if invoice.is_posted:
        raise ValidationError("المرجع مرحّل مسبقاً.")

    tenant = invoice.tenant
    partner = invoice.partner
    return_date = invoice.invoice_date or datetime.date.today()
    base_factor = _D(str(invoice.exchange_rate or 1))

    with transaction.atomic():
        validate_fiscal_period(tenant.TenantID, return_date)

        items = list(invoice.items.select_related('product').all())
        if not items:
            raise ValidationError("المرجع بلا بنود.")

        # البضاعة تعود للمورد ⇒ وحداتها المُرقَّمة تخرج من المخزن معها، وإلا بقي
        # كرت الصنف يقول «في المخزن» عن وحدة غادرت. يسبق أي كتابة: وحدة مُباعة
        # منها تمنع الترحيل.
        release_returned_purchase_serials(invoice)

        inv_net = _D('0')
        inv_vat = _D('0')
        movements = []
        for it in items:
            qty = _D(str(it.quantity or 0))
            if qty <= 0:
                continue
            line_net = (qty * _D(str(it.unit_price or 0)) * base_factor).quantize(DEC)
            vat_pct = _D(str(it.vat_percent or 0)) if it.is_taxable else _D('0')
            inv_net += line_net
            inv_vat += (line_net * vat_pct / _D('100')).quantize(DEC)

            prod = it.product
            if prod and not getattr(prod, 'is_service', False):
                mv = record_stock_movement(
                    product=prod,
                    movement_type='RETURN_OUT',
                    quantity=qty,
                    unit_cost=_D(str(prod.avg_cost or 0)),
                    reference_type='PURCHASE_RETURN',
                    reference_id=invoice.id,
                    partner=partner,
                    movement_date=return_date,
                    notes=f"مرجع شراء {invoice.invoice_number}",
                    tenant=tenant,
                )
                movements.append(mv)

        gross = (inv_net + inv_vat).quantize(DEC)
        journal = None
        if gross > 0:
            ap_account = _resolve_ap_account(partner)
            inventory_account = _resolve_inventory_account(tenant)
            lines_payload = [
                {'account': ap_account.id, 'debit': gross, 'credit': _D('0'),
                 'partner': partner.id},
                {'account': inventory_account.id, 'debit': _D('0'), 'credit': inv_net,
                 'partner': partner.id},
            ]
            if inv_vat > 0:
                vat_acc = _resolve_vat_input_account(tenant)
                lines_payload.append({
                    'account': vat_acc.id, 'debit': _D('0'), 'credit': inv_vat,
                    'partner': partner.id,
                })
            journal = post_journal(
                tenant_id=tenant.TenantID,
                transaction_date=return_date,
                reference_type='PURCHASE_RETURN',
                reference_id=invoice.id,
                description=f"مرجع شراء {invoice.invoice_number} | {partner.name}"[:500],
                lines_data=lines_payload,
                currency=invoice.currency,
                exchange_rate=base_factor,
                user=user if user and not getattr(user, 'is_anonymous', False) else None,
                idempotent=False,
            )

        invoice.subtotal = inv_net
        invoice.tax_amount = inv_vat
        invoice.grand_total = gross
        invoice.is_posted = True
        invoice.journal = journal
        invoice.status = 'completed'
        invoice.save(update_fields=[
            'subtotal', 'tax_amount', 'grand_total', 'is_posted', 'journal', 'status',
        ])

    logger.info(
        "Purchase return #%s posted: %d movement(s), journal=%s, gross=%s",
        invoice.id, len(movements), journal.id if journal else None, gross,
    )
    return invoice
