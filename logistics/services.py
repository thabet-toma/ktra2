"""P-H-1/3: Business-logic services for logistics app.

Mirrors sales/services.py patterns for attached payment vouchers (M2-T3)
and AP account resolution.
"""

import logging
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction

from accounting.models import Account, Cheque
from core.payments import document_payment_summary
from django.utils import timezone

logger = logging.getLogger(__name__)

# T-PCTX: أنواع حركات المخزون التي يسبّبها **مستند فاتورة الشراء نفسه**.
# سند الاستلام المستقلّ (GR/IR) يحمل `GOODS_RECEIPT` بمعرّف السند لا الفاتورة،
# فلا يدخل هنا — تبويب الفاتورة يقول ما فعلته هي.
PURCHASE_STOCK_REFERENCE_TYPES = ("PURCHASE_INVOICE", "PURCHASE_RETURN")

GR_IR_ACCOUNT_CODE = "2110"
GR_IR_ACCOUNT_NAME = "بضاعة مُستلَمة لم تُفوتَر (GR/IR Clearing)"

DEC = Decimal("0.01")
# دقّة الكميات = دقّة العمود نفسه (`decimal_places=4`). التقريب صريحٌ هنا كي لا
# يخرج «الباقي» مرّةً «1550.0000» ومرّةً «0» فيختلف شكل الرقم بين حالتين.
QTY = Decimal("0.0001")


def materialize_quotation_draft_parties(quotation, *, user=None):
    """T-DRAFTPARTY: يحوّل المورد/المنتجات **المبدئية** في عرض السعر إلى سجلات حقيقية.

    عرض السعر يُكتب أثناء الاستكشاف: المورد قد يكون اسماً سمعه المشتري، والمنتج
    نصاً في رسالة. لا شيء من ذلك يدخل دفتر الشركاء أو فهرس المنتجات حتى **لحظة
    التحويل** إلى صفقة/طلبية/فاتورة — عندها فقط صار القرار حقيقياً.

    المطابقة بالاسم أولاً: الاسم الموجود مسبقاً يُعاد استعماله، فلا يتضاعف مورد
    أو منتج لأن العرض كُتب يدوياً. مصدر واحد يستدعيه طُرق التحويل الثلاثة.

    #21: مطابقة المنتج **مطبَّعة** لا حرفية (`inventory.services
    .find_by_normalized_name`) — نفس قاعدة اقتراح «هذا موجود» في شاشة تسجيل
    المنتج، موضعٌ ثانٍ لدالّةٍ واحدة لا نسخةٍ ثانية منها.
    """
    from django.db import IntegrityError

    from inventory.models import Product
    from inventory.services import (
        build_normalized_name_index, create_product_with_family,
        normalize_product_name, generate_next_sku,
    )
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
    # فالقراءة من الذاكرة تعطي منتجات قديمة بعد الإنشاء.
    # #21: فهرس الأسماء المطبَّعة يُبنى **مرّةً** لا مرّةً لكل بند — المطابقة
    # العربية بايثونية حتماً (لا SQL يطبّع الألف/الهمزة)، فمسحٌ داخل الحلقة كان
    # يحمّل أصناف الشركة كلَّها لكل سطر: عرضٌ بخمسين بنداً على شركةٍ بـ1490
    # صنفاً = 74,500 صفّاً. ويُحدَّث بما يُنشأ هنا كي لا يتكرّر اسمٌ في العرض نفسه.
    name_index = build_normalized_name_index(
        Product.objects.filter(tenant_id=quotation.tenant_id)
    )
    for line in quotation.lines.select_related('product').all():
        if line.product_id:
            continue
        name = (line.name_snapshot or '').strip()
        if not name:
            raise ValidationError(
                f'بند بلا اسم في العرض {quotation.quotation_number} — أكمل البنود قبل التحويل.'
            )
        product = name_index.get(normalize_product_name(name))
        if product is None:
            # تفرّد SKU يضمنه قيد unique(tenant, sku) — نعيد المحاولة عند السباق
            # كما في مسار إنشاء المنتج العادي. #20: المسار الثاني لإنشاء منتجٍ في
            # الخادم — يمرّ بنقطة الإنشاء الموحّدة كي لا يُسرّب براندًا بلا أبٍ فوقه.
            for _ in range(5):
                try:
                    _family, product = create_product_with_family(
                        tenant=quotation.tenant,
                        sku=generate_next_sku(quotation.tenant),
                        name_ar=name,
                    )
                    break
                except IntegrityError:
                    product = None
            if product is None:
                raise ValidationError('تعذّر توليد رقم منتج — أعد المحاولة.')
            created_products.append(product)
        name_index.setdefault(normalize_product_name(name), product)
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
    # ISSUE #112: quotation.local_order صار FK عكسياً (manager) لا وصولاً
    # مباشراً بعد رفع OneToOne — .first() يحلّ محلّ except DoesNotExist.
    existing_order = quotation.local_order.first()
    if existing_order is not None:
        return existing_order, False

    if quotation.scope != SupplierQuotation.SCOPE_LOCAL:
        raise ValidationError('يمكن تحويل عروض الشراء المحلية فقط إلى طلبية شراء.')
    if quotation.status != SupplierQuotation.STATUS_ACCEPTED:
        raise ValidationError('يجب اعتماد عرض الشراء قبل تحويله إلى طلبية.')

    # ISSUE #117: المفتاح يحكم الإنشاء لا الرؤية — لا طلبية جديدة مطفأً، لكن
    # طلبيةً قائمة (سُطر 158) تعود كما هي بلا حجب.
    settings_obj = get_or_create_purchase_settings(quotation.tenant)
    if not settings_obj.use_purchase_orders:
        raise ValidationError(
            'خطوة أمر الشراء معطّلة من إعدادات الشراء — التسلسل الافتراضي طلبية ← عروض ← فاتورة.'
        )

    # T-DRAFTPARTY: المورد/المنتجات المبدئية تصير سجلات حقيقية هنا لا قبل ذلك.
    materialize_quotation_draft_parties(quotation, user=user)

    # طازج بعد تجسيد المبدئيّ: ذاكرة prefetch السابقة تحمل منتجات فارغة.
    lines = list(quotation.lines.select_related('product').all())
    if not lines:
        raise ValidationError('لا يمكن تحويل عرض سعر بلا منتجات.')
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
    from inventory.services import product_display_name

    name_max_length = PurchaseInvoiceItem._meta.get_field('name').max_length

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
            # #42: هذا القيد يفيض عمود ٢٥٥ (يبلغ ٣٠٣ في أسوأ حال) — القصّ بحدّ
            # العمود نفسه، مقروءاً من النموذج لا رقماً مطبوعاً.
            name=(line.name_snapshot or product_display_name(line.product))[:name_max_length],
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
def confirm_purchase_order(order):
    """تأكيد طلبية الشراء — القاعدة الوحيدة، أينما جاء التأكيد.

    كانت هذه الشروط تعيش **داخل `PurchaseOrderViewSet.confirm`** وحدها. ولمّا
    صار المورّد يقدر أن يقبل الطلبية من رابط المشاركة العام، كان أمام `docshare`
    طريقان: أن ينسخها (فتصير قاعدتان تنحرفان عند أول تعديل)، أو أن يستورد
    `logistics.views` — و`.importlinter` يمنعه بعقد `no-cross-app-internals`.
    فاستُخرجت إلى خدمة يستدعيها الطرفان.

    وحالةُ «مؤكدة» واحدةٌ مهما كان المُقِرّ: أن نضغط نحن «تأكيد» بعد مكالمةٍ مع
    المصنع، أو أن يضغط المصنع «موافق» على الرابط — كلاهما يقول إن الطلبية
    مُتَّفقٌ عليها. **ومَن أقرّ ومتى** يُسجَّل في `DocumentShare` (الاسم والتوقيت
    وIP) وفي `ActivityLog`، لا في عمود الحالة.
    """
    from logistics.models import PurchaseOrder

    locked = PurchaseOrder.objects.select_for_update().get(pk=order.pk)
    if locked.status == PurchaseOrder.STATUS_CONFIRMED:
        return locked
    if locked.status != PurchaseOrder.STATUS_DRAFT:
        raise ValidationError('يمكن تأكيد الطلبية المسودة فقط.')
    if not locked.lines.exists():
        raise ValidationError('لا يمكن تأكيد طلبية بلا منتجات.')
    locked.status = PurchaseOrder.STATUS_CONFIRMED
    locked.save(update_fields=['status', 'updated_at'])
    logger.info(
        'purchase_order.confirm order=%s tenant=%s', locked.id, locked.tenant_id,
    )
    return locked


@transaction.atomic
def submit_rfq_supplier_quote(
    recipient, *, name: str, prices: dict, ip: str = '', currency_id=None,
    general_note: str = '', notes: dict | None = None,
):
    """يُنشئ أو يحدّث عرض السعر المتولّد من ردّ المورّد على رابطه الخاص (ISSUE #115).

    القاعدة الوحيدة التي تكتب `SupplierQuotation` من رابطٍ عام — تُستدعى من
    `docshare/documents/purchase_docs.py` (`_apply_purchase_rfq_quote`) وحدها،
    نفس نمط `confirm_purchase_order` أعلاه. `docshare` لا يستورد شيئاً من هنا
    غير هذه الدالّة، فيبقى جاهلاً بشكل `PurchaseRFQRecipient`/`SupplierQuotation`.

    **ISSUE #133 غ٢**: `currency_id` اختياريّ — موردٌ أجنبيّ (والاستيراد
    مورّدوه أجانب بالتعريف) يكتب بعملته لا عملتنا. غيابه أو موافقته لعملة
    الأساس يُبقي السلوك القديم حرفياً (عملة الأساس، سعر صرف = 1). عملةٌ أخرى
    تُحوَّل بسعر صرفٍ يُحسَم **الآن** (`accounting.services.get_exchange_rate`)
    ويُحفظ على العرض — فيصير «سعر صرف المستند نفسه» الذي تُحاكم إليه مصفوفة
    المقارنة لاحقاً (`comparison/`)، لا سعر اليوم المتغيّر عند كل قراءة.

    **الفرق عن عرضٍ يُدخله موظف**: هذا يتولّد **باسم المورّد** لا موظفنا،
    ومرّةً واحدة لكل مستقبِل (`PurchaseRFQRecipient.quotation` OneToOne) —
    الرد الثاني من نفس الرابط يُحدِّث بنود العرض نفسه، لا ينشئ عرضاً ثانياً.

    **ISSUE #133 غ٣**: `general_note` (ملاحظة المورّد العامة على الطلبية كلّها)
    و`notes` (‏`{line_id: raw_note}` — ملاحظته على كلّ بند) اختياريّان
    ويُكتبان هنا وحدها — نفس نقطة الكتابة الوحيدة لـ`entry_source`/`rfq_line`
    في #122. القاعدةُ الوحيدة التي تكتب `SupplierQuotationLine.supplier_note`
    و`SupplierQuotation.general_note` — محرِّرُ العروض الداخليّ يقرؤهما فقط
    (`SupplierQuotationLineSerializer`/`SupplierQuotationSerializer`، للقراءة
    فقط بنيوياً)، فنصّ المورّد يبقى كما كتبه عند خلاف.
    """
    from logistics.models import PurchaseRFQ, SupplierQuotation, SupplierQuotationLine

    notes = notes or {}

    rfq = PurchaseRFQ.objects.select_for_update().get(pk=recipient.rfq_id)
    if rfq.status != PurchaseRFQ.STATUS_SENT:
        raise ValidationError('لم تعد الطلبية تقبل الأسعار — أُغلقت أو أُلغيت.')

    rfq_lines = list(rfq.lines.all())
    if not rfq_lines:
        raise ValidationError('لا بنود في هذه الطلبية.')

    parsed_prices = {}
    for line in rfq_lines:
        raw = prices.get(line.id)
        if raw in (None, ''):
            raise ValidationError('الرجاء إدخال سعر لكل بند.')
        try:
            price = Decimal(str(raw))
        except (InvalidOperation, ValueError, TypeError):
            raise ValidationError('سعر غير صالح.')
        if price < 0:
            raise ValidationError('السعر لا يمكن أن يكون سالباً.')
        parsed_prices[line.id] = price

    from tenants.models import Currency

    # لا حقل عملة على `PurchaseRFQ` نفسها (طلبيةٌ بلا أسعار) — العرض المتولّد
    # يحتاج واحدة، فيُختار الأساس افتراضياً. نفس نمط `create_purchase_return`.
    base_currency = (
        Currency.objects.filter(IsBaseCurrency=True).first()
        or Currency.objects.order_by('CurrencyID').first()
    )
    if base_currency is None:
        raise ValidationError('لا توجد عملة معرّفة للشركة.')

    def _resolve_quote_currency():
        """عملةُ هذا الإرسال وسعرُ صرفها — ISSUE #133 غ٢.

        غيابُ `currency_id` أو موافقتُه لعملة الأساس = عملة الأساس بسعر 1
        (السلوك القديم حرفياً). عملةٌ أخرى تُحوَّل بسعر صرفٍ **يُحسم الآن**
        لا يُترك للقراءة اللاحقة.

        **لا سقوطَ صامتاً إلى 1**: `currency_options` (أدناه) تستبعد أصلاً أيّ
        عملةٍ بلا سعرٍ قابلٍ للحسم اليوم، فوصولُ `currency_id` كهذا من طلبٍ
        عاديّ لا يحدث. وصولُه فعلياً (نموذجٌ مُتلاعَبٌ به، أو سعرٌ زال بين
        فتح الصفحة وإرسالها) اعتلالٌ حقيقيّ يستحقّ رفضاً صريحاً — تخزينُ 1
        كان يعني بالضبط ما كُتبت هذه التذكرة لمنعه: عرضاً أجنبياً يدخل
        المقارنة بقيمةٍ ملفَّقة فيبدو أرخص أو أغلى ممّا هو حقيقةً.
        """
        if not currency_id:
            return base_currency, Decimal('1')
        candidate = Currency.objects.filter(pk=currency_id).first()
        if candidate is None or candidate.pk == base_currency.pk:
            return base_currency, Decimal('1')
        from accounting.services import get_exchange_rate

        try:
            rate = get_exchange_rate(rfq.tenant_id, candidate.pk, base_currency.pk)
        except ValidationError:
            logger.warning(
                'purchase_rfq.supplier_quote no_exchange_rate rfq=%s currency=%s',
                rfq.pk, candidate.pk,
            )
            raise
        return candidate, rate

    quotation = recipient.quotation
    if quotation is None:
        from accounting.services import next_document_number

        currency, exchange_rate = _resolve_quote_currency()

        prefix = 'IQ' if rfq.scope == PurchaseRFQ.SCOPE_IMPORT else 'PQ'
        sequence = next_document_number(rfq.tenant_id, f'supplier_quotation_{rfq.scope}')
        quotation = SupplierQuotation.objects.create(
            tenant=rfq.tenant,
            rfq=rfq,
            scope=rfq.scope,
            supplier=recipient.supplier,
            quotation_number=f'{prefix}-{sequence:04d}',
            quotation_date=timezone.localdate(),
            currency=currency,
            exchange_rate=exchange_rate,
            status=SupplierQuotation.STATUS_SENT,
            order_name=rfq.rfq_number or '',
            supplier_contact=name,
            # ISSUE #122: ختمٌ صريح — هذا المسارُ وحده هو «سعّره المورّد بنفسه».
            entry_source=SupplierQuotation.ENTRY_SUPPLIER_LINK,
            # ISSUE #133 غ٣: ملاحظة المورّد العامة — تُكتب هنا وحدها.
            general_note=general_note,
        )
    else:
        update_fields = ['supplier_contact', 'updated_at']
        quotation.supplier_contact = name
        # التصحيح اللاحق قد يغيّر العملة أيضاً (سعّر بالخطأ بعملةٍ ثم صحّح) —
        # لا يُلمس شيء إن لم يصل `currency_id` أصلاً (تعديل سعرٍ عادي).
        if currency_id:
            currency, exchange_rate = _resolve_quote_currency()
            if currency.pk != quotation.currency_id:
                quotation.currency = currency
                quotation.exchange_rate = exchange_rate
                update_fields += ['currency', 'exchange_rate']
        # ISSUE #133 غ٣: المورّدُ يعدّل ملاحظته العامة بحرّية مراراً — نفس قاعدة
        # السعر، ما دامت الطلبية مفتوحة.
        if general_note != quotation.general_note:
            quotation.general_note = general_note
            update_fields.append('general_note')
        quotation.save(update_fields=update_fields)

    subtotal = Decimal('0')
    for line in rfq_lines:
        price = parsed_prices[line.id]
        line_total = (Decimal(line.quantity) * price).quantize(DEC)
        subtotal += line_total
        SupplierQuotationLine.objects.update_or_create(
            quotation=quotation, seq=line.seq,
            defaults=dict(
                tenant=rfq.tenant, product=line.product,
                # ISSUE #122: البندُ الأبّ نفسُه لا ترتيبُه. المطابقةُ بـ`seq`
                # في المصفوفة تكذب متى حُذف بندٌ من عرضٍ يُحرَّر بحرّية فتُرقَّم
                # البقيةُ من جديد — وهذا المسارُ يمرّ على بنود الطلبية أصلاً،
                # فالإسنادُ سطرٌ واحد.
                rfq_line=line,
                name_snapshot=line.name_snapshot,
                unit_of_measure=line.unit_of_measure,
                quantity=line.quantity,
                unit_price=price,
                line_total=line_total,
                # ISSUE #133 غ٣: نصّ المورّد على هذا البند تحديداً — نفس
                # منطق السعر: يُعاد كتابته على كل إرسال، فتصحيحُه لاحقاً
                # («في الحقيقة ٥ لا ٤ قطع») يمرّ من نفس الرابط.
                supplier_note=str(notes.get(line.id) or '').strip(),
            ),
        )
    quotation.subtotal = subtotal.quantize(DEC)
    quotation.tax_amount = Decimal('0')
    quotation.grand_total = subtotal.quantize(DEC)
    quotation.save(update_fields=['subtotal', 'tax_amount', 'grand_total', 'updated_at'])

    update_fields = []
    if recipient.quotation_id != quotation.pk:
        recipient.quotation = quotation
        update_fields.append('quotation')
    if recipient.replied_at is None:
        recipient.replied_at = timezone.now()
        update_fields.append('replied_at')
    if update_fields:
        recipient.save(update_fields=update_fields)

    logger.info(
        'purchase_rfq.supplier_quote rfq=%s recipient=%s quotation=%s ip=%s',
        rfq.pk, recipient.pk, quotation.pk, ip,
    )
    return quotation


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
    # ISSUE #112: نفس تكييف .first() في convert_local_quotation_to_order أعلاه.
    existing_invoice = quotation.local_invoice.first()
    if existing_invoice is not None:
        return existing_invoice, False

    if quotation.scope != SupplierQuotation.SCOPE_LOCAL:
        raise ValidationError('يمكن تحويل عروض الشراء المحلية فقط إلى فاتورة شراء.')
    if quotation.status != SupplierQuotation.STATUS_ACCEPTED:
        raise ValidationError('يجب اعتماد عرض الشراء قبل تحويله إلى فاتورة.')
    existing_order = quotation.local_order.first()
    if existing_order is not None:
        raise ValidationError(
            f'عرض السعر {quotation.quotation_number} محوَّل إلى طلبية '
            f'{existing_order.order_number} — حوّل الطلبية إلى فاتورة.'
        )

    # T-DRAFTPARTY: المورد/المنتجات المبدئية تصير سجلات حقيقية هنا لا قبل ذلك.
    materialize_quotation_draft_parties(quotation, user=user)

    # طازج بعد تجسيد المبدئيّ: ذاكرة prefetch السابقة تحمل منتجات فارغة.
    lines = list(quotation.lines.select_related('product').all())
    if not lines:
        raise ValidationError('لا يمكن تحويل عرض سعر بلا منتجات.')

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


def purchase_journal_settlement_debit(invoice) -> Decimal:
    """ما سُوّي **داخل قيد فاتورة الشراء نفسه** — مجموع مدين ذمم المورد فيه.

    قبل Feature 2 كانت الفاتورة النقدية تُرحَّل بقسمين: إثباتٌ يدائن الذمم ثم
    «Section B» يدينها ويدائن الصندوق — تسويةٌ داخل القيد بلا سند صرف. تلك
    القيود متوازنة وصحيحة، فحسابُها «مدفوعاً» حقٌّ لا افتراض؛ وحذفُ القاعدة كان
    سيقلب فواتير تاريخية مسدَّدة إلى «غير مدفوعة».

    اليوم لا يُنتج الترحيل هذا السطر إطلاقاً (يثبته `test_pi_subledger_routing`)،
    فالقيمة صفرٌ لكل فاتورة جديدة وتبقى القاعدة واحدة للزمنين.

    المرجع مستثنى: هو يدين الذمم **بحكم تعريفه** لا تسويةً. مرآة
    `sales/services/flow.py` (`invoice_journal_settlement_credit`).
    """
    from django.db.models import Sum

    from accounting.models import JournalLine

    if getattr(invoice, "is_return", False):
        return Decimal("0")
    if not invoice.journal_id:
        return Decimal("0")
    ap_account_id = getattr(invoice.partner, "linked_account_id", None)
    if not ap_account_id:
        return Decimal("0")
    total = JournalLine.objects.filter(
        journal_id=invoice.journal_id, account_id=ap_account_id, debit__gt=0,
    ).aggregate(total=Sum("debit"))["total"]
    return Decimal(str(total or 0)).quantize(DEC)


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
    # T-APPAID: «المدفوع» يُحسب ولا يُفترض. القاعدة السابقة كانت تعطي كل فاتورة
    # نقدية مرحّلة `paid = payable` بغضّ النظر عن وجود سند، وتسقط على
    # `attached_cash_amount` وهو عمودٌ لا يُرحّل شيئاً — فتقول الشاشة «مدفوعة
    # بالكامل» وذمم المورد دائنة. ما يُحتسب اليوم شيئان فقط، وكلاهما قيدٌ في
    # الدفاتر: سنداتٌ مرحّلة، وتسويةٌ داخل قيد الفاتورة نفسه (فواتير ما قبل
    # Feature 2). النسخة الـSQL أدناه تطبّق القاعدة نفسها حرفاً بحرف.
    paid = linked_paid + legacy_paid + purchase_journal_settlement_debit(invoice)
    summary = {
        "fees_total": fees_total,
        "payable_total": payable,
        # T-INTENT: النيّة تُعرَض ولا تُحتسب — خارج `paid` وخارج حالة الدفع.
        "pending_payment_total": purchase_invoice_pending_payment_total(invoice),
        **document_payment_summary(payable, paid),
    }
    invoice._payment_summary_cache = summary
    return summary


def _auto_purchase_settlement_note(invoice) -> str:
    """نصّ ملاحظات سند التسوية التلقائي — مصدر واحد يكتبه الترحيل ويقرأه التمييز."""
    return f"صرف نقدي تلقائي — فاتورة شراء {invoice.invoice_number}"


def is_auto_cash_purchase_settlement(payment, invoice) -> bool:
    """هل هذا السند هو تسوية الفاتورة النقدية التلقائية (لا سند مستخدم)؟

    العلامة الصريحة (`auto_settled_invoice`) هي المرجع. البيانات السابقة لها
    تُطابَق بتوقيع صارم: نصّ الملاحظات الذي يولّده الكود + ارتباطٌ بهذه الفاتورة
    وحدها بلا توزيع — فلا يُلتقط سند مستخدم بالخطأ. مرآة
    `sales/services/flow.py` (`is_auto_cash_settlement`).
    """
    if payment.auto_settled_invoice_id == invoice.pk:
        return True
    if (payment.notes or "").strip() != _auto_purchase_settlement_note(invoice):
        return False
    if payment.purchase_invoice_id != invoice.pk:
        return False
    return not payment.allocations.all().exists()


def guard_purchase_invoice_payments_before_unpost(
    invoice, *, action_label: str = "إلغاء ترحيل"
) -> None:
    """T-APINT: يمنع إلغاء ترحيل فاتورة شراء عليها سندات صرف مرحّلة.

    الجذر المُصلَح: إلغاء الترحيل كان يحذف قيود الفاتورة وحدها، فيبقى سند الصرف
    مرحّلاً وقيده **يدين ذمم المورد بلا مقابل** — رصيدٌ وهميّ لصالح الشركة عند
    مورّد لم يُدفع له شيء زائد. مرآةُ `guard_invoice_payments_before_unpost`
    على جانب البيع، وحارسِ الاعتمادية في `unpost_document` لحركات المخزون.

    السند التلقائي للشراء النقدي مستثنى — يُحرَّر بالحذف عبر
    `release_auto_cash_purchase_settlement` قبل الحذف لا بمنعه.
    """
    from sales.models import SupplierPayment, SupplierPaymentAllocation

    from accounting.services import guard_document_cheques_before_unpost

    document_label = f"فاتورة الشراء {invoice.invoice_number}"
    guard_document_cheques_before_unpost(
        list(Cheque.objects.filter(
            tenant_id=invoice.tenant_id, purchase_invoice=invoice)),
        document_label=document_label,
        action_label=action_label,
    )

    blockers: list[str] = []
    for alloc in (
        SupplierPaymentAllocation.objects
        .filter(invoice=invoice, payment__is_posted=True)
        .select_related("payment")
    ):
        blockers.append(
            f"سند #{alloc.payment_id} ({Decimal(str(alloc.amount or 0)).quantize(DEC)})"
        )
    for payment in (
        SupplierPayment.objects
        .filter(purchase_invoice=invoice, is_posted=True)
        .prefetch_related("allocations")
    ):
        if payment.allocations.all():
            continue  # حُسِب أعلاه بمبالغ توزيعه — لا يُعدّ مرّتين
        if is_auto_cash_purchase_settlement(payment, invoice):
            continue  # يُحرَّر لا يَمنع
        blockers.append(
            f"سند #{payment.id} ({Decimal(str(payment.amount or 0)).quantize(DEC)})"
        )
    # الدفعات القديمة (PurchaseInvoicePayment) تحمل قيوداً مرحّلة أيضاً.
    from logistics.models import PurchaseInvoicePayment
    for legacy in PurchaseInvoicePayment.objects.filter(invoice=invoice, is_posted=True):
        blockers.append(
            f"دفعة #{legacy.id} ({Decimal(str(legacy.amount or 0)).quantize(DEC)})"
        )

    if not blockers:
        return
    logger.warning(
        "unpost blocked for purchase invoice %s: %d posted payment(s)",
        invoice.invoice_number, len(blockers),
    )
    raise ValidationError(
        f"تعذّر {action_label} {document_label}: توجد سندات صرف مرحّلة عليها "
        f"({'، '.join(blockers)}). ألغِ ترحيل هذه السندات (أو احذفها) أولاً ثم "
        f"أعد المحاولة."
    )


def release_auto_cash_purchase_settlement(invoice, *, user=None) -> list[int]:
    """يحرّر سند التسوية النقدية التلقائي قبل إلغاء ترحيل فاتورة شرائه.

    هذا السند من إنتاج الترحيل نفسه (`_auto_settle_cash_purchase`) لا من إنشاء
    المستخدم، فيُحذف مع قيوده ضمن نفس معاملة إلغاء الترحيل ويُعاد إنشاؤه عند
    إعادة الترحيل — وإلا بقي معلّقاً (مدين ذمم بلا مقابل) وتضاعف عند كل إعادة
    ترحيل. سندات المستخدم لا تُمَسّ: يحرسها
    `guard_purchase_invoice_payments_before_unpost`.

    T-INTENT: شيكات السند تعود **مسودةً** قبل حذفه — وإلا بقيت «برسم الدفع» بلا
    سندٍ يحملها (الرابط `SET_NULL`) فلا يكنسها الترحيل التالي ولا تظهر نيّةً على
    المسودة. مرآة `release_auto_cash_settlement`.
    """
    from django.db.models import Q

    from accounting.services import record_document_cheque_unposting, unpost_document
    from sales.models import SupplierPayment

    candidates = (
        SupplierPayment.objects.filter(tenant_id=invoice.tenant_id)
        .filter(
            Q(auto_settled_invoice_id=invoice.pk)
            | Q(purchase_invoice_id=invoice.pk)
        )
        .distinct()
        .prefetch_related("allocations")
    )
    released: list[int] = []
    for payment in candidates:
        if not is_auto_cash_purchase_settlement(payment, invoice):
            continue
        if payment.is_posted:
            unpost_document(
                tenant_id=payment.tenant_id,
                reference_id=payment.id,
                journal_reference_types=["SUPPLIER_PAYMENT"],
                user=user,
                document_label=f"سند صرف تلقائي #{payment.id}",
            )
        record_document_cheque_unposting(list(payment.cheques.all()), user=user)
        payment_id = payment.id
        payment.delete()  # صفوف التوزيع تُحذف تلقائياً (CASCADE)
        released.append(payment_id)
        logger.info(
            "Released auto cash purchase settlement %s of invoice %s (unpost).",
            payment_id, invoice.invoice_number,
        )
    return released


def annotate_purchase_invoice_payment_summary(queryset):
    """نسخة SQL لملخص الدفع تُستخدم في القوائم والفلترة قبل pagination."""
    from django.db.models import (
        Case, CharField, DecimalField, ExpressionWrapper, F, OuterRef,
        Subquery, Sum, Value, When,
    )
    from django.db.models.functions import Coalesce, Greatest
    from accounting.models import JournalLine
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
    pending_cheques = (
        Cheque.objects
        .filter(
            purchase_invoice_id=OuterRef("pk"), status="Draft",
            supplier_payment__isnull=True,
        )
        .values("purchase_invoice_id")
        .annotate(total=Sum("amount"))
        .values("total")[:1]
    )
    # T-APPAID: التسوية داخل قيد الفاتورة نفسه (فواتير ما قبل Feature 2) —
    # نفس قاعدة `purchase_journal_settlement_debit` حرفاً بحرف: مدينُ حساب ذمم
    # المورد المرتبط، داخل قيد الفاتورة وحده، والمرجع مستثنى. القاعدتان في
    # موضعين ولا يجوز أن تفترقا — القائمة والتفصيل يقولان الرقم نفسه.
    journal_settled = (
        JournalLine.objects
        .filter(
            journal_id=OuterRef("journal_id"),
            account_id=OuterRef("partner__linked_account_id"),
            debit__gt=0,
        )
        .values("journal_id")
        .annotate(total=Sum("debit"))
        .values("total")[:1]
    )
    zero = Value(Decimal("0.00"), output_field=money)

    queryset = queryset.annotate(
        list_fees_total=Coalesce(Subquery(fee_total, output_field=money), zero),
        list_linked_paid=Coalesce(Subquery(linked_paid, output_field=money), zero),
        list_allocated_paid=Coalesce(Subquery(allocated_paid, output_field=money), zero),
        list_legacy_paid=Coalesce(Subquery(legacy_paid, output_field=money), zero),
        list_journal_settled=Case(
            When(is_return=True, then=zero),
            default=Coalesce(Subquery(journal_settled, output_field=money), zero),
            output_field=money,
        ),
    ).annotate(
        list_payable_total=ExpressionWrapper(
            F("grand_total") + F("list_fees_total"), output_field=money,
        ),
        list_recorded_paid=ExpressionWrapper(
            F("list_linked_paid") + F("list_allocated_paid") + F("list_legacy_paid")
            + F("list_journal_settled"),
            output_field=money,
        ),
    ).annotate(
        list_amount_paid=Case(
            When(
                list_recorded_paid__gt=F("list_payable_total"),
                then=F("list_payable_total"),
            ),
            default=F("list_recorded_paid"),
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
        # T-INTENT: الدفعة المرفقة بمسودة — نقدٌ منويّ + شيكات مسودة. نفس قاعدة
        # `purchase_invoice_pending_payment_total` حرفاً بحرف: لا تدخل «المدفوع»
        # ولا حالة الدفع، فما لم يُرحَّل ليس مدفوعاً في الدفاتر.
        list_pending_payment_total=Case(
            When(is_posted=True, then=zero),
            default=ExpressionWrapper(
                F("attached_cash_amount")
                + Coalesce(Subquery(pending_cheques, output_field=money), zero),
                output_field=money,
            ),
            output_field=money,
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
    from accounting.api import ensure_partner_account

    partner = ensure_partner_account(partner) or partner
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


def create_supplier_payment_cheques(payment, cheques) -> None:
    """ينشئ شيكات سند الصرف بقاعدة واحدة — يستدعيها السيريالايزر والمنسّق معاً.

    كانت الكتابة في السيريالايزر وحده، فأيّ مسارٍ ثانٍ يعني نسخةً ثانية من عقد
    الشيك (الاتجاه والحالة الابتدائية وقصّ الحقول) تفترق عنها غداً.
    """
    from accounting.models import Cheque as _Cheque

    for c in cheques or []:
        _Cheque.objects.create(
            tenant=payment.tenant,
            supplier_payment=payment,
            partner=payment.partner,
            direction='Outgoing',
            status='Draft',  # يصير «برسم الدفع» عند ترحيل السند
            cheque_number=str(c['cheque_number']).strip(),
            amount=Decimal(str(c['amount'])).quantize(DEC),
            currency=payment.currency,
            bank_name=(c.get('bank_name') or '')[:100],
            account_number=(c.get('account_number') or '')[:50],
            bank_branch=(c.get('bank_branch') or '')[:100],
            due_date=c.get('due_date') or None,
            issue_date=c.get('issue_date') or None,
            payee_name=(c.get('payee_name') or '')[:150],
            notes=c.get('notes') or '',
        )


def _validate_supplier_cheque_payloads(cheques, *, require_due_date=True) -> Decimal:
    """يتحقّق من صفوف الشيكات ويعيد مجموعها — نفس شروط جانب البيع."""
    total = Decimal('0')
    for i, c in enumerate(cheques or []):
        if not str(c.get('cheque_number', '')).strip():
            raise ValidationError("الشيك #%d: رقم الشيك مطلوب." % (i + 1))
        try:
            amount = Decimal(str(c.get('amount', 0)))
        except Exception:
            raise ValidationError("الشيك #%d: مبلغ غير صالح." % (i + 1))
        if amount <= 0:
            raise ValidationError("الشيك #%d: المبلغ يجب أن يكون أكبر من صفر." % (i + 1))
        if require_due_date and not c.get('due_date'):
            raise ValidationError("الشيك #%d: تاريخ الاستحقاق مطلوب." % (i + 1))
        total += amount
    return total.quantize(DEC)


def attach_purchase_payment_voucher(
    invoice,
    *,
    cash_amount=0,
    cash_account_id=None,
    cheques=None,
    user=None,
):
    """T-INTENT: يربط نيّة دفع بمسودة فاتورة الشراء — مرآة `attach_payment_voucher`.

    تحضيرٌ لا دفع: لا قيد ولا سند صرف ولا أثر على رصيد المورد. عند ترحيل
    الفاتورة يكنس `_settle_attached_purchase_intent` النقدَ والشيكات معاً في
    **سند صرف واحد**. Replace-semantics: كل نداء يستبدل ما سبق، و`{0, []}` يمسح.
    """
    if invoice.is_posted:
        raise ValidationError("لا يمكن تعديل السند بعد ترحيل الفاتورة.")

    cash_amount = Decimal(str(cash_amount or 0)).quantize(DEC)
    if cash_amount < 0:
        raise ValidationError("مبلغ النقدي لا يمكن أن يكون سالباً.")

    cheques = cheques or []
    cheques_total = _validate_supplier_cheque_payloads(cheques, require_due_date=False)

    payable = purchase_invoice_payment_summary(invoice)["payable_total"]
    intent_total = (cash_amount + cheques_total).quantize(DEC)
    if intent_total > payable:
        raise ValidationError(
            f"مجموع الدفعة المرفقة ({intent_total}) يتجاوز مبلغ الفاتورة {payable}."
        )
    cash_account_id = cash_account_id or None
    if cash_amount > 0 and cash_account_id:
        if not Account.objects.filter(
            pk=cash_account_id, tenant_id=invoice.tenant_id
        ).exists():
            raise ValidationError("حساب الصندوق/البنك غير موجود في هذه الشركة.")

    with transaction.atomic():
        invoice.attached_cash_amount = cash_amount
        invoice.attached_cash_account_id = cash_account_id if cash_amount > 0 else None
        invoice.save(update_fields=[
            "attached_cash_amount", "attached_cash_account",
        ])

        # استبدال الشيكات المسودة وحدها — ما تجاوز «برسم الدفع» لا يُمسّ.
        Cheque.objects.filter(
            purchase_invoice=invoice, status="Draft", supplier_payment__isnull=True,
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
            )

    # الملخّص المخزَّن على النسخة صار بائتاً بعد تغيير النيّة.
    invoice._payment_summary_cache = None
    return invoice


def _attached_purchase_settlement_note(invoice) -> str:
    """توقيع سند دفع ما وصل مرفقاً مع فاتورة الشراء (شيكات ± نقد)."""
    return f"دفع مرفق مع فاتورة الشراء {invoice.invoice_number}"


def settle_attached_purchase_intent(invoice, *, user=None) -> Decimal:
    """T-INTENT: يجسّد نيّة الدفع المرفقة بفاتورة الشراء في **سند صرف واحد**.

    مرآة `sales/services/flow.py` (`_settle_attached_cheques`). يُستدعى داخل
    معاملة الترحيل بعد القيد وقبل التسوية النقدية التلقائية، فيجد الأخيرُ
    الفاتورةَ مسوّاةً جزئياً ويكمل الباقي وحده بدل أن يخرج سندان.

    النيّة تُقصّ على ما بقي فعلاً: نيّةٌ بائتة نجت من إلغاء ترحيلٍ ثم دُفعت
    الفاتورة يدوياً لا يجوز أن تُدفع ثانيةً عند إعادة الترحيل.

    `attached_cash_amount` **لا يُمسح** — هو سجلّ النيّة الدائم، والتجسّد هو
    السند (`auto_settled_invoice`) الذي يُحرَّر مع إلغاء الترحيل.

    يُعيد المبلغ الذي سُوّي (صفر إن لا نيّة).
    """
    from sales.models import SupplierPayment, SupplierPaymentAllocation
    from sales.services import post_supplier_payment

    if invoice.is_return:
        # الشيك الصادر لا معنى له على مرتجع شراء — يُترك مسودةً بلا تسوية.
        return Decimal("0.00")
    cheques = list(
        Cheque.objects.filter(
            tenant_id=invoice.tenant_id, purchase_invoice=invoice,
            status="Draft", supplier_payment__isnull=True,
        )
    )
    cheques_total = sum(
        (Decimal(str(c.amount or 0)) for c in cheques), Decimal("0")
    ).quantize(DEC)
    cash_intent = Decimal(str(invoice.attached_cash_amount or 0)).quantize(DEC)
    if cheques_total + cash_intent <= 0:
        return Decimal("0.00")

    invoice._payment_summary_cache = None
    remaining = purchase_invoice_payment_summary(invoice)["remaining_balance"]
    if remaining <= 0:
        return Decimal("0.00")
    cash_part = min(cash_intent, max((remaining - cheques_total).quantize(DEC), Decimal("0")))
    amount = min((cheques_total + cash_part).quantize(DEC), remaining)
    if amount <= 0:
        return Decimal("0.00")

    # T-CASHBOX M1: المرفق **أولاً** — اختيار المستخدم في لوحة الدفع لا يكتبه
    # إلا `attach-payment/`، بينما رأس الفاتورة تملؤه الواجهة تلقائياً. بالعكس
    # كان الرأس يبتلع الاختيار فيُدائَن صندوقٌ آخر بصمت.
    cash_account_id = (
        invoice.attached_cash_account_id or invoice.cash_or_bank_account_id
    )
    if not cash_account_id:
        from accounting.services import resolve_default_cash_account

        default_cash = resolve_default_cash_account(invoice.tenant_id)
        cash_account_id = default_cash.pk if default_cash else None
    if not cash_account_id:
        # التخطّي هنا يعني إسقاط دفعة مدفوعة بصمت، فالترحيل كلّه يرتدّ ويبقى
        # المستند مسودة مع رسالة تُسمّي الإعداد الناقص.
        raise ValidationError(
            f"الفاتورة {invoice.invoice_number} عليها دفعة مرفقة لكن لا يوجد "
            "حساب صندوق/بنك لتحرير سند الصرف. عيّن الصندوق الافتراضي للشركة "
            "أو حدّد حساب الصندوق على الفاتورة."
        )

    payment = SupplierPayment.objects.create(
        tenant_id=invoice.tenant_id,
        partner_id=invoice.partner_id,
        payment_date=invoice.invoice_date or timezone.localdate(),
        amount=amount,
        currency_id=invoice.currency_id,
        exchange_rate=invoice.exchange_rate or Decimal("1"),
        cash_or_bank_account_id=cash_account_id,
        auto_settled_invoice=invoice,
        notes=_attached_purchase_settlement_note(invoice),
    )
    if cheques:
        Cheque.objects.filter(pk__in=[c.pk for c in cheques]).update(
            supplier_payment=payment
        )
    SupplierPaymentAllocation.objects.create(
        tenant_id=invoice.tenant_id,
        payment=payment,
        invoice=invoice,
        amount=amount,
    )
    post_supplier_payment(payment, user=user)
    invoice._payment_summary_cache = None

    from core.activity import log_activity

    log_activity(
        action="payment", entity_type="supplier_payment", entity_id=payment.id,
        entity_label=f"#{payment.id}", description="سند صرف دفعة مرفقة",
        partner_ids=[payment.partner_id], tenant=invoice.tenant, user=user,
    )
    log_activity(
        action="post", entity_type="supplier_payment", entity_id=payment.id,
        entity_label=f"#{payment.id}", description="ترحيل سند صرف دفعة مرفقة",
        partner_ids=[payment.partner_id], tenant=invoice.tenant, user=user,
    )
    logger.info(
        "Settled attached payment of purchase invoice %s via supplier payment %s "
        "(cheques %s + cash %s of %s).",
        invoice.invoice_number, payment.id, cheques_total, cash_part, amount,
    )
    return amount


def purchase_invoice_pending_payment_total(invoice) -> Decimal:
    """T-INTENT: الدفعة المرفقة بمسودة شراء — نقدٌ منويّ + شيكات مسودة.

    مرآة `sales.services.invoice_pending_payment_total`. لا تدخل «المدفوع» ولا
    تغيّر حالة الدفع — فما لم يُرحَّل ليس مدفوعاً في الدفاتر. تقرأ التعليق
    `pending_cheques_total` إن حُقن، فلا استعلامٌ لكل صفّ في القائمة.
    """
    if invoice.is_posted:
        return Decimal("0.00")
    cheques_total = getattr(invoice, "pending_cheques_total", None)
    if cheques_total is None:
        from django.db.models import Sum

        cheques_total = Cheque.objects.filter(
            purchase_invoice_id=invoice.pk, status="Draft",
            supplier_payment__isnull=True,
        ).aggregate(total=Sum("amount"))["total"]
    return (
        Decimal(str(invoice.attached_cash_amount or 0))
        + Decimal(str(cheques_total or 0))
    ).quantize(DEC)


def suggest_supplier_fifo_allocations(*, tenant_id: int, partner_id: int, amount):
    """T-PSIMPL: اقتراح توزيع سند صرف على فواتير المورّد من الأقدم (FIFO).

    مرآة `sales/services/numbering.py` (`suggest_fifo_allocations`) على جانب
    المورّد. كانت موجودة للعميل وحده، فتوزيعُ سندٍ كبير على فواتير مورّدٍ يبقى
    عملاً يدوياً وبحساباتٍ على ورقة.

    الترتيب بالاستحقاق ثم بتاريخ الفاتورة: أقدمُ ما استحقّ يُسدَّد أولاً — وهو
    المعنى الذي يريده المستخدم من «FIFO» هنا، لا أقدمُ ما صدر.

    «المتبقّي» يأتي من `annotate_purchase_invoice_payment_summary` — القاعدة
    نفسها التي تحكم القائمة والتقارير، فلا حسبةَ رابعة.
    """
    from logistics.models import PurchaseInvoice

    remaining = Decimal(str(amount or 0)).quantize(DEC)
    if remaining <= 0:
        return []
    rows = annotate_purchase_invoice_payment_summary(
        PurchaseInvoice.objects.filter(
            tenant_id=tenant_id, partner_id=partner_id,
            is_posted=True, is_return=False,
        )
    ).order_by('due_date', 'invoice_date', 'id')

    out: list[dict] = []
    for inv in rows:
        if remaining <= 0:
            break
        due = Decimal(str(inv.list_remaining_balance or 0)).quantize(DEC)
        if due <= 0:
            continue
        take = min(due, remaining)
        out.append({
            'invoice': inv.id,
            'invoice_number': inv.invoice_number,
            'due_date': inv.due_date.isoformat() if inv.due_date else None,
            'amount': str(take),
        })
        remaining -= take
    return out


def pay_purchase_invoice(
    invoice,
    *,
    cash=None,
    cash_account_id=None,
    cheques=None,
    from_on_account=None,
    payment_date=None,
    user=None,
):
    """T-APPAY: دفع فاتورة الشراء من نقطة واحدة — نقد + شيكات + سلف المورّد، ذرّياً.

    مرآة `sales/services/flow.py` (`collect_invoice_payment`). كان الدفع على جانب
    الشراء خطوتين منفصلتين في الواجهة: «رحّل» ثم «افتح سند الصرف» — نداءان
    مستقلّان، فانقطاعُ الثاني يترك فاتورةً مرحّلة بلا سند ومورّداً دائناً بلا سبب
    ظاهر للمستخدم الذي ظنّ أنه دفع.

    **صفر منطق ترحيل جديد** — تركيبُ خدمات قائمة:

    1. النقد + الشيكات ⇒ **سند صرف واحد** (`post_supplier_payment`) بتوزيعٍ
       مقصوص على المتبقّي؛ ما زاد يبقى «على الحساب» سلفةً للمورّد (T-ONACC).
    2. كل صفّ `from_on_account` ⇒ `allocate_supplier_payment`: ربطٌ بلا قيد
       جديد — ترحيلُ ذلك السند دَيَّن الذمم أصلاً.
    3. الفاتورة النقدية مدفوعةٌ بالتعريف: نقدٌ **غير مذكور** يُكمَّل تلقائياً،
       ونقصٌ بعد نقدٍ مذكور يَرفض العملية كلَّها.

    الفاتورة يجب أن تكون **مرحّلة** قبل الاستدعاء — الترحيل يملكه
    `PurchaseInvoiceViewSet.post_to_accounting`، والنقطة `pay/` تجمع الاثنين في
    `transaction.atomic()` واحد فلا تُترك فاتورةٌ مرحّلة بسندٍ نصفِ مولود.

    from_on_account: `[{"payment_id": <id>, "amount": <Decimal|str>}, ...]`
    """
    from sales.models import SupplierPayment, SupplierPaymentAllocation
    from sales.services import allocate_supplier_payment, post_supplier_payment

    cheque_rows = list(cheques or [])
    on_account_rows = list(from_on_account or [])
    # «غير مذكور» ليس «صفراً»: الأول يُكمَّل على الفاتورة النقدية، والثاني إعلانُ
    # نيّةٍ بعدم دفع نقد فيُحاسَب عليه.
    cash_given = cash is not None and str(cash).strip() != ""
    try:
        cash_amount = Decimal(str(cash or 0)).quantize(DEC)
    except Exception:
        raise ValidationError("مبلغ النقدي غير صالح.")
    if cash_amount < 0:
        raise ValidationError("مبلغ النقدي لا يمكن أن يكون سالباً.")
    cheques_total = _validate_supplier_cheque_payloads(cheque_rows)

    on_account_total = Decimal('0')
    for i, row in enumerate(on_account_rows):
        if not row.get('payment_id'):
            raise ValidationError("الرصيد #%d: رقم سند الصرف مطلوب." % (i + 1))
        try:
            amount = Decimal(str(row.get('amount', 0)))
        except Exception:
            raise ValidationError("الرصيد #%d: مبلغ غير صالح." % (i + 1))
        if amount <= 0:
            raise ValidationError("الرصيد #%d: المبلغ يجب أن يكون أكبر من صفر." % (i + 1))
        on_account_total += amount

    if getattr(invoice, 'is_return', False):
        raise ValidationError(
            "مرتجع الشراء لا يُدفع — هو يخفّض ذمم المورد بحكم تعريفه."
        )

    payment = None
    with transaction.atomic():
        if not invoice.is_posted:
            raise ValidationError(
                "الفاتورة %s غير مرحّلة — رحّلها أولاً أو اطلب الترحيل مع الدفع."
                % invoice.invoice_number
            )
        invoice.refresh_from_db()
        summary = purchase_invoice_payment_summary(invoice)
        remaining = Decimal(str(summary['remaining_balance'])).quantize(DEC)
        amount = (cash_amount + cheques_total).quantize(DEC)
        target = max((remaining - on_account_total).quantize(DEC), Decimal('0'))

        is_cash_invoice = invoice.payment_type == 'cash'
        if is_cash_invoice and not cash_given and amount < target:
            cash_amount = (cash_amount + target - amount).quantize(DEC)
            amount = (cash_amount + cheques_total).quantize(DEC)

        if amount <= 0 and not on_account_rows:
            raise ValidationError("لا مبلغ للدفع.")

        if amount > 0:
            resolved_cash_id = cash_account_id or invoice.cash_or_bank_account_id
            if not resolved_cash_id:
                from accounting.services import resolve_default_cash_account
                default_cash = resolve_default_cash_account(invoice.tenant_id)
                resolved_cash_id = default_cash.pk if default_cash else None
            if not resolved_cash_id:
                raise ValidationError(
                    "دفع الفاتورة %s يحتاج حساب صندوق/بنك لتحرير سند الصرف. عيّن "
                    "صندوقاً افتراضياً في الإعدادات أو حدّد حساب الصندوق على "
                    "الفاتورة." % invoice.invoice_number
                )
            payment = SupplierPayment.objects.create(
                tenant_id=invoice.tenant_id,
                partner_id=invoice.partner_id,
                purchase_invoice=invoice,
                payment_date=payment_date or invoice.invoice_date or timezone.localdate(),
                amount=amount,
                currency_id=invoice.currency_id,
                exchange_rate=invoice.exchange_rate or Decimal('1'),
                cash_or_bank_account_id=resolved_cash_id,
                notes="سند صرف من داخل الفاتورة",
            )
            create_supplier_payment_cheques(payment, cheque_rows)
            allocated = min(amount, target)
            if allocated > 0:
                SupplierPaymentAllocation.objects.create(
                    tenant_id=invoice.tenant_id,
                    payment=payment,
                    invoice=invoice,
                    amount=allocated,
                    amount_in_invoice_currency=allocated,
                )
            post_supplier_payment(payment, user=user)
            from core.activity import log_activity
            log_activity(
                action='payment', entity_type='supplier_payment',
                entity_id=payment.id, entity_label='#%s' % payment.id,
                description='سند صرف من داخل الفاتورة',
                partner_ids=[payment.partner_id], tenant=invoice.tenant, user=user,
            )
            log_activity(
                action='post', entity_type='supplier_payment',
                entity_id=payment.id, entity_label='#%s' % payment.id,
                description='ترحيل سند صرف من داخل الفاتورة',
                partner_ids=[payment.partner_id], tenant=invoice.tenant, user=user,
            )

        for row in on_account_rows:
            source = SupplierPayment.objects.filter(
                pk=row['payment_id'], tenant_id=invoice.tenant_id,
            ).first()
            if source is None:
                raise ValidationError(
                    "سند الصرف #%s غير موجود في هذه الشركة." % row['payment_id']
                )
            if source.partner_id != invoice.partner_id:
                raise ValidationError(
                    "سند الصرف #%s لا يخصّ مورّد الفاتورة." % source.pk
                )
            if not source.is_posted:
                raise ValidationError(
                    "سند الصرف #%s غير مرحّل — لا رصيد منه على الحساب." % source.pk
                )
            allocate_supplier_payment(
                source, [{'invoice': invoice.pk, 'amount': row['amount']}], user=user,
            )

        invoice = type(invoice).objects.get(pk=invoice.pk)
        left = Decimal(
            str(purchase_invoice_payment_summary(invoice)['remaining_balance'])
        ).quantize(DEC)
        if is_cash_invoice and left > DEC:
            raise ValidationError(
                "الفاتورة نقدية — المدفوع لا يغطي الإجمالي؛ اجعلها فاتورة ذمم "
                "(آجلة) أو أكمل المبلغ."
            )
    logger.info(
        "Paid purchase invoice %s: payment=%s amount=%s on_account=%s left=%s",
        invoice.invoice_number, getattr(payment, 'id', None), amount,
        on_account_total, left,
    )
    return payment


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


def purchase_item_receipt_quantities(item):
    """(المطلوب، المستلَم، الباقي) لبند فاتورة شراء — القاعدة الوحيدة في النظام.

    الباقي = المطلوب − المستلَم، **مقصوصاً عند الصفر**: استلامٌ زائد (تصحيح يدوي
    أو إرسالية أُعيد تطبيقها) لا يصنع باقياً سالباً يُطرَح من بندٍ آخر.

    كانت هذه السطور الثلاثة منسوخةً في ستّة مواضع (تقرير البواقي، بنود الاستلام،
    بند الإرسالية، مجموع الإرسالية، حارس `receive_purchase_invoice`، وأخيراً
    الواجهة) — ونسخةٌ سادسة كانت ستجعل «الباقي» رقمين مختلفين على شاشتين.
    """
    ordered = Decimal(str(item.quantity or 0)).quantize(QTY)
    received = Decimal(str(item.received_quantity or 0)).quantize(QTY)
    remaining = ordered - received
    return ordered, received, remaining if remaining > 0 else Decimal('0').quantize(QTY)


def purchase_invoice_receipt_summary(invoice, items=None):
    """ملخّص استلام الفاتورة: «استُلم X من Y — باقي Z» بمصدرٍ واحد.

    مرآةُ `purchase_invoice_payment_summary` على بُعد المخزن بدل بُعد المال.
    تُحتسب **بنود المنتجات المخزنية وحدها** — بند خدمة بلا منتج لا يدخل مستودعاً
    فلا يصحّ أن يُبقي الفاتورة «ناقصة الاستلام» إلى الأبد (نفس استثناء
    `GoodsReceiptViewSet.outstanding`).

    `items` اختيارية لتفادي استعلام ثانٍ حين تكون البنود محمّلة سلفاً.
    """
    rows = invoice.items.all() if items is None else items
    ordered_total = received_total = remaining_total = Decimal('0')
    lines_total = lines_remaining = 0
    for it in rows:
        if not it.product_id:
            continue
        ordered, received, remaining = purchase_item_receipt_quantities(it)
        ordered_total += ordered
        received_total += received
        remaining_total += remaining
        lines_total += 1
        if remaining > 0:
            lines_remaining += 1
    return {
        'ordered': ordered_total,
        'received': received_total,
        'remaining': remaining_total,
        'lines_total': lines_total,
        'lines_remaining': lines_remaining,
    }


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
    default_date = (invoice.invoice_date if invoice else None) or timezone.localdate()
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
    لكل بند ذي منتج مخزون: تُنشأ حركة IN (متوسط مرجح) موسومة بالفرع والمستودع،
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
        movement_date = invoice.invoice_date or timezone.localdate()

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
                    f"البند «{item.name}» بلا منتج مخزون مربوط — لا يمكن استلامه."
                )

            try:
                qty = Decimal(str(raw.get('quantity', 0)))
            except Exception:
                raise ValidationError(f"كمية غير صالحة للبند «{item.name}».")
            if qty <= 0:
                continue

            ordered, _already, remaining = purchase_item_receipt_quantities(item)
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
        raise ValidationError('حدّد المنتجات والكميات المستلمة.')
    if partner is None:
        raise ValidationError('حدّد المورد لسند الاستلام المستقل.')

    movement_date = receipt_date or timezone.localdate()
    tenant_id = getattr(tenant, 'TenantID', tenant)
    products = {
        p.id: p for p in Product.objects.filter(
            tenant_id=tenant_id,
            pk__in=[row.get('product_id') for row in lines if row.get('product_id')],
        )
    }

    from inventory.services import product_display_name

    planned = []
    total_value = Decimal('0')
    for raw in lines:
        product = products.get(int(raw.get('product_id') or 0))
        if product is None:
            raise ValidationError(f"المنتج {raw.get('product_id')} غير موجود في هذه الشركة.")
        name = product_display_name(product)
        try:
            qty = Decimal(str(raw.get('quantity', 0)))
        except Exception:
            raise ValidationError(f"كمية غير صالحة للمنتج «{name}».")
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
            raise ValidationError(f"المستودع المحدد للمنتج «{name}» غير موجود.")
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
    لكل منتج — يغذّي منتقي بنود المرجع في الواجهة. مصدر حقيقة واحد مع حارس الإنشاء.
    يُجمّع بالمنتج (لو تكرّر المنتج في أسطر الفاتورة)."""
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
    from inventory.services import product_display_name
    from .models import PurchaseInvoice, PurchaseInvoiceItem

    if return_date is None:
        return_date = timezone.localdate()
    if partner is None:
        raise ValidationError("المورد مطلوب لمرجع الشراء.")
    if partner.tenant_id != tenant.TenantID:
        raise ValidationError("المورد لا يتبع نفس الشركة.")

    # نسبة الضريبة لكل منتج من الفاتورة الأصلية (لعكسها بدقة عند الترحيل).
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
        # W6: منع تجاوز الكمية المرتجعة الكمية الأصلية المفوترة (لكل منتج). المتبقّي
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
                        f"الكمية المرتجعة للمنتج «{pname}» ({l['quantity']}) تتجاوز المتبقّي "
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
                raise ValidationError(f"المنتج {l['product']} غير موجود أو لا يتبع الشركة.")
            qty = l['quantity']
            line_net = (qty * l['unit_price'] * base_factor).quantize(DEC)
            vat_pct = vat_by_product.get(prod.id, _D('0'))
            inv_net += line_net
            inv_vat += (line_net * vat_pct / _D('100')).quantize(DEC)

            # #42: `name_ar` وحده هو المقاس بعد #20 (لا لافتة مميِّزة) —
            # `product_display_name` هي الصيغة الصحيحة، لا احتياطها ولا `str(prod)`.
            PurchaseInvoiceItem.objects.create(
                invoice=ret, product=prod,
                name=product_display_name(prod)[
                    :PurchaseInvoiceItem._meta.get_field('name').max_length
                ],
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
    return_date = invoice.invoice_date or timezone.localdate()
    base_factor = _D(str(invoice.exchange_rate or 1))

    with transaction.atomic():
        validate_fiscal_period(tenant.TenantID, return_date)

        items = list(invoice.items.select_related('product').all())
        if not items:
            raise ValidationError("المرجع بلا بنود.")

        # البضاعة تعود للمورد ⇒ وحداتها المُرقَّمة تخرج من المخزن معها، وإلا بقي
        # كرت المنتج يقول «في المخزن» عن وحدة غادرت. يسبق أي كتابة: وحدة مُباعة
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
                    notes=f"مرتجع شراء {invoice.invoice_number}",
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
                description=f"مرتجع شراء {invoice.invoice_number} | {partner.name}"[:500],
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
