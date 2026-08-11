"""تتبّع الأرقام التسلسلية للوحدة + توليد الباركود.

الوحدة المُرقَّمة تعيش في `ProductSerial`؛ ما يُدخله المستخدم على بند المستند
(`PurchaseInvoiceItem.serials` / `SalesInvoiceLine.serials`) نيّةٌ تُترجَم إلى صفوف
هنا: الشراء يُنشئها عند **استلام** البضاعة، والبيع يوسمها «مُباع» عند **ترحيل**
الفاتورة. لا شيء من هذا يعمل قبل أن تُشغّله الشركة من إعداداتها
(`serial_entry_mode`) — الافتراضي `off` فلا أثر لأي سطر هنا على شركة لم تطلبه.

الإلزام كله خادمي: الواجهة تحرس الإدخال، والخادم يحرس الدفاتر.
"""
import logging
import random
import re
from decimal import Decimal

from django.core.exceptions import ValidationError

from .models import Product, ProductSerial

logger = logging.getLogger(__name__)

# ── أنماط إدخال الرقم التسلسلي (مشتركة بين إعدادات الشراء والبيع) ──────────
SERIAL_MODE_OFF = 'off'
SERIAL_MODE_OPTIONAL = 'optional'
SERIAL_MODE_REQUIRED = 'required'
SERIAL_MODE_CHOICES = [
    (SERIAL_MODE_OFF, 'بدون أرقام تسلسلية'),
    (SERIAL_MODE_OPTIONAL, 'اختياري'),
    (SERIAL_MODE_REQUIRED, 'إجباري'),
]

SERIAL_MAX_LENGTH = 100

_TRAILING_DIGITS_RE = re.compile(r'(\d+)$')


# ══════════════════════════════════════════════════════════════════════════
# أدوات عامّة
# ══════════════════════════════════════════════════════════════════════════

def product_tracks_serials(product) -> bool:
    """الصنف يتتبّع أرقاماً تسلسلية؟ (مُفعَّل عليه، وليس خدمة — الخدمة بلا وحدات)."""
    return bool(
        product is not None
        and getattr(product, 'is_serialized', False)
        and not getattr(product, 'is_service', False)
    )


def normalize_serials(raw, *, label: str = '') -> list[str]:
    """قائمة نظيفة مرتّبة كما أُدخلت: بلا فراغات ولا فراغاتٍ زائدة ولا تكرار.

    التكرار داخل نفس الحمولة **خطأ** لا تجاهُلٌ صامت: رقمان متطابقان يعنيان
    وحدتين لا تُفرَّقان، وقبولهما بحذف أحدهما يُنقص العدد بلا إخبار.
    """
    where = f" ({label})" if label else ''
    if raw in (None, ''):
        return []
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        raise ValidationError(f"الأرقام التسلسلية{where} يجب أن تكون قائمة نصوص.")
    out: list[str] = []
    seen: set[str] = set()
    for value in raw:
        serial = str(value or '').strip()
        if not serial:
            continue
        if len(serial) > SERIAL_MAX_LENGTH:
            raise ValidationError(
                f"الرقم التسلسلي «{serial[:20]}…»{where} أطول من {SERIAL_MAX_LENGTH} حرفاً."
            )
        if serial in seen:
            raise ValidationError(f"الرقم التسلسلي «{serial}»{where} مكرَّر في نفس البند.")
        seen.add(serial)
        out.append(serial)
    return out


def strip_serials_when_off(rows, mode: str) -> None:
    """نمط «بدون» لا يخزّن أرقاماً أصلاً — تُفرَّغ من حمولة البنود عند الحفظ.

    الإلزام في الخدمات يمنع إنشاء الوحدات على أي حال؛ التفريغ هنا يمنع بقاء أرقامٍ
    نائمة على المستندات تصبح فاعلة فجأةً لو شُغّل الإعداد لاحقاً.
    """
    if mode != SERIAL_MODE_OFF:
        return
    for row in rows or []:
        if isinstance(row, dict) and row.get('serials'):
            row['serials'] = []


def generate_serial_range(start: str, count) -> list[str]:
    """«SN-0098» + 3 ⇒ SN-0098 · SN-0099 · SN-0100.

    الجزء الرقمي في نهاية النص وحده يتزايد، مع الحفاظ على البادئة وعلى عدد
    الخانات (الصفر البادئ). البداية بلا جزء رقمي مرفوضة — لا شيء فيها يتزايد.
    """
    raw = str(start or '').strip()
    match = _TRAILING_DIGITS_RE.search(raw)
    if not match:
        raise ValidationError(
            'الرقم التسلسلي الأول يجب أن ينتهي برقم كي يتزايد — مثال: SN-0098.'
        )
    try:
        count = int(count)
    except (TypeError, ValueError):
        raise ValidationError('عدد الوحدات غير صالح.')
    if count < 1:
        raise ValidationError('عدد الوحدات يجب أن يكون 1 أو أكثر.')

    digits = match.group(1)
    prefix = raw[: match.start(1)]
    width = len(digits)
    first = int(digits)
    serials = [f"{prefix}{str(first + i).zfill(width)}" for i in range(count)]
    too_long = next((s for s in serials if len(s) > SERIAL_MAX_LENGTH), None)
    if too_long is not None:
        raise ValidationError(
            f"الرقم التسلسلي «{too_long[:20]}…» أطول من {SERIAL_MAX_LENGTH} حرفاً."
        )
    return serials


def _whole_units(quantity, *, label: str) -> int:
    """الوحدة المُرقَّمة لا تُجزَّأ — كمية كسرية على صنف تسلسلي خطأ إدخال."""
    qty = Decimal(str(quantity or 0))
    if qty != qty.to_integral_value():
        raise ValidationError(
            f"الصنف «{label}» يتتبّع أرقاماً تسلسلية — الكمية ({qty}) يجب أن تكون عدداً صحيحاً."
        )
    return int(qty)


def _product_label(product) -> str:
    return (
        getattr(product, 'name_ar', None)
        or getattr(product, 'name_en', None)
        or getattr(product, 'sku', None)
        or f"#{getattr(product, 'pk', '')}"
    )


# ══════════════════════════════════════════════════════════════════════════
# الأنماط المُعلَنة في إعدادات الشركة
# ══════════════════════════════════════════════════════════════════════════

def purchase_serial_mode(tenant_id) -> str:
    """نمط إدخال الرقم التسلسلي في الشراء — بلا صفّ إعدادات: `off`."""
    from logistics.models import PurchaseSettings

    mode = (
        PurchaseSettings.objects.filter(tenant_id=tenant_id)
        .values_list('serial_entry_mode', flat=True)
        .first()
    )
    return mode or SERIAL_MODE_OFF


def sales_serial_mode(tenant_id) -> str:
    """نمط إدخال الرقم التسلسلي في البيع — بلا صفّ إعدادات: `off`."""
    from sales.models import SalesSettings

    mode = (
        SalesSettings.objects.filter(tenant_id=tenant_id)
        .values_list('serial_entry_mode', flat=True)
        .first()
    )
    return mode or SERIAL_MODE_OFF


# ══════════════════════════════════════════════════════════════════════════
# الشراء: الاستلام يُنشئ الوحدات · التراجع يحرّرها
# ══════════════════════════════════════════════════════════════════════════

def assert_purchase_serials_declared(invoice) -> None:
    """«إجباري» يحرس **ترحيل** فاتورة الشراء لا استلامها وحده.

    الاستلام مع الترحيل مشروط (محلية + GR/IR + قيمة موجبة)، فالفاتورة الدولية أو
    فاتورة الكمية بلا قيمة كانت تُرحَّل بلا رقم واحد ثم يُقفل تعديلها فلا سبيل
    لإضافة الأرقام إلا بإلغاء الترحيل. الحارس هنا يقع **قبل** أي كتابة، والاستلام
    يبقى خط الدفاع الثاني كما هو (`apply_purchase_serials`).
    """
    mode = purchase_serial_mode(invoice.tenant_id)
    if mode != SERIAL_MODE_REQUIRED:
        return

    incomplete: list[str] = []
    for item in invoice.items.select_related('product').all():
        product = item.product
        if not product_tracks_serials(product):
            continue
        label = _product_label(product)
        ordered = _whole_units(item.quantity, label=label)
        if ordered <= 0:
            continue
        declared = normalize_serials(item.serials, label=label)
        if len(declared) != ordered:
            incomplete.append(
                f"«{label}» (المطلوب {ordered} والمُدخَل {len(declared)})"
            )

    if incomplete:
        raise ValidationError(
            'إدخال الأرقام التسلسلية إجباري قبل الترحيل — أكمل أرقام البنود التالية: '
            + '؛ '.join(incomplete) + '.'
        )


def assert_receipt_without_serials_allowed(tenant_id, products) -> None:
    """سند الاستلام المستقل لا يحمل أرقاماً — فلا يُدخل بضاعة مُرقَّمة تحت «إجباري».

    بابٌ يُدخل المخزون بلا ترقيم يُنتج بالضبط المخزون الذي يرفض البيعُ بيعه؛
    والمخرج مُسمّى في الرسالة لا متروك للمستخدم يبحث عنه.
    """
    if purchase_serial_mode(tenant_id) != SERIAL_MODE_REQUIRED:
        return
    tracked = [_product_label(p) for p in products if product_tracks_serials(p)]
    if not tracked:
        return
    raise ValidationError(
        'نمط الأرقام التسلسلية في إعدادات الشراء «إجباري»، وسند الاستلام المستقل '
        'لا يحمل أرقاماً — استلم هذه الأصناف من فاتورة الشراء نفسها، أو سجّل أرقام '
        'مخزونها من كرت الصنف: ' + '، '.join(tracked) + '.'
    )


def register_existing_serials(*, tenant_id, product, serials) -> int:
    """ترقيم مخزون قائم: وحدات «في المخزن» بلا بند شراء.

    الوحدة لا تُنشأ إلا من فاتورة شراء، فتشغيل «إجباري» في البيع كان يُجمّد بيع كل
    مخزونٍ سابق للميزة بلا طريق للأمام. هنا يُسجَّل ما هو موجود فعلاً: نفس قواعد
    التحقق (تنظيف، تكرار، تصادم)، وسقفه رصيد الصنف — الترقيم **يصف** مخزوناً
    قائماً ولا يخلق مخزوناً، فلا حركة مخزون له ولا قيد.
    """
    if not product_tracks_serials(product):
        raise ValidationError(
            f"الصنف «{_product_label(product)}» لا يتتبّع أرقاماً تسلسلية — "
            "فعّل «تتبّع بالرقم التسلسلي» في كرت الصنف أولاً."
        )
    label = _product_label(product)
    clean = normalize_serials(serials, label=label)
    if not clean:
        raise ValidationError('أدخل رقماً تسلسلياً واحداً على الأقل.')
    _assert_serials_free(tenant_id, product, clean)

    on_hand = Decimal(str(product.quantity_on_hand or 0))
    tracked = ProductSerial.objects.filter(
        tenant_id=tenant_id, product=product, status=ProductSerial.STATUS_IN_STOCK,
    ).count()
    if tracked + len(clean) > on_hand:
        on_hand_label = (
            str(int(on_hand)) if on_hand == on_hand.to_integral_value() else str(on_hand)
        )
        raise ValidationError(
            f"الصنف «{label}»: رصيد المخزن {on_hand_label} وحدة ومنها {tracked} "
            f"مُرقَّمة — لا مكان لتسجيل {len(clean)} رقماً إضافياً. الترقيم يصف "
            "مخزوناً قائماً؛ الوحدات الجديدة تدخل بفاتورة شراء."
        )

    for serial in clean:
        ProductSerial.objects.create(
            tenant_id=tenant_id,
            product=product,
            serial=serial,
            status=ProductSerial.STATUS_IN_STOCK,
        )
    logger.info(
        'existing stock serials registered: tenant=%s product=%s units=%d',
        tenant_id, product.pk, len(clean),
    )
    return len(clean)


def apply_purchase_serials(*, tenant, rows) -> int:
    """يُنشئ وحدات `in_stock` لحصّة البضاعة المستلَمة من بنود فاتورة شراء.

    rows: [(PurchaseInvoiceItem, quantity)] — الحصّة المستلَمة في هذا النداء.

    الإلزام:
    - `off`      ⇒ لا شيء (حتى لو حملت البنود أرقاماً — لا تُخزَّن وحدات).
    - `required` ⇒ كل بند لصنف تسلسلي يجب أن يحمل أرقاماً بعدد كميته المفوترة.
    - `optional` ⇒ ما وُجد يُتحقَّق ويُخزَّن، وما نقص يُترك بلا تتبّع.

    الاستلام الجزئي يأخذ الأرقام بالترتيب المُدخَل: ما استُلم سابقاً موجود أصلاً
    كصفوف، فتبدأ الحصّة الجديدة من حيث انتهت. كل التحقق يسبق أي كتابة.
    """
    tenant_id = getattr(tenant, 'TenantID', tenant)
    mode = purchase_serial_mode(tenant_id)
    if mode == SERIAL_MODE_OFF:
        return 0

    planned: list[tuple] = []
    for item, quantity in rows:
        product = item.product
        if not product_tracks_serials(product):
            continue
        label = _product_label(product)
        received_now = _whole_units(quantity, label=label)
        if received_now <= 0:
            continue
        declared = normalize_serials(item.serials, label=label)
        ordered = _whole_units(item.quantity, label=label)

        if mode == SERIAL_MODE_REQUIRED and len(declared) != ordered:
            raise ValidationError(
                f"البند «{label}»: إدخال الأرقام التسلسلية إجباري — "
                f"المطلوب {ordered} رقماً والمُدخَل {len(declared)}."
            )

        already = ProductSerial.objects.filter(purchase_item=item).count()
        take = declared[already:already + received_now]
        if not take:
            continue
        if mode == SERIAL_MODE_REQUIRED and len(take) < received_now:
            raise ValidationError(
                f"البند «{label}»: الأرقام التسلسلية المُدخَلة لا تكفي الكمية المستلَمة "
                f"({len(take)} من {received_now})."
            )
        _assert_serials_free(tenant_id, product, take)
        planned.append((item, product, take))

    created = 0
    for item, product, take in planned:
        for serial in take:
            ProductSerial.objects.create(
                tenant_id=tenant_id,
                product=product,
                serial=serial,
                status=ProductSerial.STATUS_IN_STOCK,
                purchase_item=item,
            )
            created += 1

    if created:
        logger.info(
            'product serials received: tenant=%s mode=%s units=%d lines=%d',
            tenant_id, mode, created, len(planned),
        )
    return created


def _assert_serials_free(tenant_id, product, serials) -> None:
    """الرقم التسلسلي فريد لكل (شركة، صنف) — التصادم يُسمّى لا يُبتَلع."""
    taken = sorted(
        ProductSerial.objects.filter(
            tenant_id=tenant_id, product=product, serial__in=list(serials),
        ).values_list('serial', flat=True)
    )
    if taken:
        raise ValidationError(
            f"الصنف «{_product_label(product)}»: الأرقام التسلسلية التالية مستخدمة "
            f"مسبقاً — {'، '.join(taken)}."
        )


def release_purchase_serials(
    *, tenant_id, quantities_by_item, document_label='', action_label='التراجع عن',
) -> int:
    """يحذف وحدات مستند شراء عند التراجع عنه — ويمنع التراجع إن بِيعت أيٌّ منها.

    quantities_by_item: {item_id: عدد الوحدات المراد تحريرها} — و`None` تعني
    «كل وحدات هذا البند». التحرير الجزئي (إلغاء إرسالية واحدة من عدّة إرساليات)
    يأخذ الأحدث أولاً: الاستلام يُنشئ بالترتيب والبيع يستهلك بـFIFO من الأقدم،
    فأحدث الوحدات هي بالضبط ما جاءت به الإرسالية الملغاة.

    وحدة مُباعة تعني فاتورة بيع بُنيت على هذا المستند: تُسمّى الوحدات وفواتيرها
    ويُرفض التراجع — نفس منطق حارس اعتمادية المخزون، فلا يبقى بيعٌ لوحدة لا أصل لها.
    """
    if not quantities_by_item:
        return 0

    doomed: list[int] = []
    for item_id, limit in quantities_by_item.items():
        qs = ProductSerial.objects.filter(
            tenant_id=tenant_id, purchase_item_id=item_id,
        ).order_by('-id').only('id')
        if limit is None:
            doomed.extend(u.pk for u in qs)
            continue
        units = int(Decimal(str(limit or 0)))
        if units <= 0:
            continue
        doomed.extend(u.pk for u in qs[:units])

    if not doomed:
        return 0

    sold = list(
        ProductSerial.objects.filter(
            pk__in=doomed, status=ProductSerial.STATUS_SOLD,
        ).select_related('sales_line__invoice')
    )
    if sold:
        listing = '؛ '.join(
            f"{s.serial}"
            + (
                f" (فاتورة {s.sales_line.invoice.invoice_number})"
                if s.sales_line_id and s.sales_line.invoice_id else ''
            )
            for s in sold
        )
        logger.warning(
            'release_purchase_serials blocked: %s has %d sold unit(s)',
            document_label or 'purchase document', len(sold),
        )
        raise ValidationError(
            f"تعذّر {action_label} {document_label or 'هذا المستند'}: وحدات بأرقام "
            f"تسلسلية من هذه البضاعة مُباعة بالفعل. ألغِ ترحيل فواتير بيعها أولاً — "
            f"المُباعة: {listing}"
        )

    deleted = ProductSerial.objects.filter(pk__in=doomed).delete()[0]
    logger.info(
        'product serials released: %s units=%d', document_label or 'purchase document', deleted,
    )
    return deleted


def release_returned_purchase_serials(return_invoice) -> int:
    """مرجع الشراء يُخرج بضاعته من المخزن — ووحداتها المُرقَّمة تخرج معها.

    الوحدات المقصودة هي وحدات **الفاتورة الأصلية** لنفس الصنف، تُؤخذ الأحدث أولاً
    (نفس قاعدة إلغاء الإرسالية)، ووحدةٌ مُباعة منها تمنع ترحيل المرجع بدل أن تبقى
    «في المخزن» وبضاعتها عند المورد. مرجعٌ بلا فاتورة أصلية لا يُمسّ: لا شيء يقول
    أي وحدة بعينها رجعت.
    """
    original = getattr(return_invoice, 'original_invoice', None)
    if original is None:
        return 0

    tenant_id = return_invoice.tenant_id
    wanted: dict[int, int] = {}
    for line in return_invoice.items.select_related('product').all():
        product = line.product
        if not product_tracks_serials(product):
            continue
        label = _product_label(product)
        qty = _whole_units(line.quantity, label=label)
        if qty <= 0:
            continue
        # بلا فلترة حالة: الوحدة المُباعة يجب أن تدخل الاختيار كي يوقفها الحارس.
        item_ids = list(
            ProductSerial.objects.filter(
                tenant_id=tenant_id, product=product, purchase_item__invoice=original,
            ).order_by('-id').values_list('purchase_item_id', flat=True)[:qty]
        )
        for item_id in item_ids:
            wanted[item_id] = wanted.get(item_id, 0) + 1

    return release_purchase_serials(
        tenant_id=tenant_id,
        quantities_by_item=wanted,
        document_label=f"مرجع الشراء {return_invoice.invoice_number}",
        action_label='ترحيل',
    )


def restock_returned_purchase_serials(return_invoice) -> int:
    """التراجع عن مرجع شراء يعيد كميته للمخزن — ووحداتها المُرقَّمة تعود معها.

    مرآة `release_returned_purchase_serials`: الوحدات المحرَّرة كانت آخر ما أُنشئ
    من أرقام بنود الفاتورة الأصلية، فإعادةُ إنشائها هي تماماً ما يفعله الاستلام
    لبقيّة الأرقام المُعلَنة — بالمصدر نفسه (`apply_purchase_serials`) لا بقاعدة
    ثانية. بلا ذلك تعود الكمية للمخزن بلا وحداتها.
    """
    original = getattr(return_invoice, 'original_invoice', None)
    if original is None:
        return 0

    tenant_id = return_invoice.tenant_id
    returned: dict[int, int] = {}
    for line in return_invoice.items.select_related('product').all():
        product = line.product
        if not product_tracks_serials(product):
            continue
        qty = _whole_units(line.quantity, label=_product_label(product))
        if qty > 0:
            returned[product.pk] = returned.get(product.pk, 0) + qty
    if not returned:
        return 0

    rows: list[tuple] = []
    # الأحدث أولاً: التحرير أخذ الأحدث، فالاستعادة تملأ من الطرف نفسه.
    for item in original.items.select_related('product').order_by('-id'):
        remaining = returned.get(item.product_id or 0, 0)
        if remaining <= 0:
            continue
        declared = normalize_serials(item.serials, label=_product_label(item.product))
        existing = ProductSerial.objects.filter(purchase_item=item).count()
        missing = len(declared) - existing
        take = min(missing, remaining)
        if take <= 0:
            continue
        rows.append((item, Decimal(take)))
        returned[item.product_id] = remaining - take

    if not rows:
        return 0
    return apply_purchase_serials(tenant=return_invoice.tenant, rows=rows)


# ══════════════════════════════════════════════════════════════════════════
# البيع: الترحيل يستهلك الوحدات · إلغاء الترحيل يعيدها للمخزن
# ══════════════════════════════════════════════════════════════════════════

def consume_sales_serials(invoice, lines) -> int:
    """يوسم وحدات فاتورة بيع «مُباع» ويربطها ببنودها عند الترحيل.

    ما اختاره المستخدم صريحاً على البند يُستهلَك كما هو (بعد التحقق أنه موجود
    وفي المخزن ولنفس الصنف)، والباقي يُخصَّص تلقائياً **FIFO** من أقدم الوحدات
    المتاحة — كي لا يُلزَم من لا يهمّه اختيار الوحدة بعينها.

    نقص المتاح (مخزون قديم سابق للتتبّع): `required` يرفض الترحيل، و`optional`
    يخصّص ما وُجد ويترك الباقي بلا تتبّع. `off` لا يفعل شيئاً.
    """
    mode = sales_serial_mode(invoice.tenant_id)
    if mode == SERIAL_MODE_OFF:
        return 0

    planned: list[tuple] = []
    for line in lines:
        product = line.product
        if not product_tracks_serials(product):
            continue
        label = _product_label(product)
        needed = _whole_units(line.quantity, label=label)
        if needed <= 0:
            continue
        # ذرّية إعادة الترحيل: بند استُهلكت وحداته فعلاً لا يُستهلَك ثانيةً
        # (مرآة حارس الترحيل المكرّر في `_post_stock_out_for_invoice`).
        if ProductSerial.objects.filter(
            sales_line=line, status=ProductSerial.STATUS_SOLD,
        ).exists():
            continue

        declared = normalize_serials(line.serials, label=label)
        if len(declared) > needed:
            raise ValidationError(
                f"البند «{label}»: عدد الأرقام التسلسلية المختارة ({len(declared)}) "
                f"يتجاوز الكمية ({needed})."
            )
        chosen = list(
            ProductSerial.objects.filter(
                tenant_id=invoice.tenant_id, product=product, serial__in=declared,
                status=ProductSerial.STATUS_IN_STOCK,
            ).order_by('id')
        )
        if len(chosen) != len(declared):
            found = {s.serial for s in chosen}
            missing = [s for s in declared if s not in found]
            raise ValidationError(
                f"البند «{label}»: الأرقام التسلسلية التالية غير متوفرة في المخزن "
                f"لهذا الصنف — {'، '.join(missing)}."
            )

        shortfall = needed - len(chosen)
        if shortfall > 0:
            auto = list(
                ProductSerial.objects.filter(
                    tenant_id=invoice.tenant_id, product=product,
                    status=ProductSerial.STATUS_IN_STOCK,
                )
                .exclude(pk__in=[s.pk for s in chosen])
                .order_by('id')[:shortfall]
            )
            chosen.extend(auto)

        if len(chosen) < needed:
            if mode == SERIAL_MODE_REQUIRED:
                raise ValidationError(
                    f"البند «{label}»: إدخال الأرقام التسلسلية إجباري — "
                    f"المتوفر في المخزن {len(chosen)} وحدة والمطلوب {needed}."
                )
            logger.info(
                'sales serials partial: invoice=%s product=%s matched=%d needed=%d',
                invoice.pk, product.pk, len(chosen), needed,
            )
        planned.append((line, chosen))

    consumed = 0
    for line, chosen in planned:
        for unit in chosen:
            unit.status = ProductSerial.STATUS_SOLD
            unit.sales_line = line
            unit.save(update_fields=['status', 'sales_line'])
            consumed += 1

    if consumed:
        logger.info(
            'product serials sold: invoice=%s mode=%s units=%d', invoice.pk, mode, consumed,
        )
    return consumed


def release_sales_serials(invoice) -> int:
    """يعيد وحدات فاتورة بيع إلى المخزن عند إلغاء ترحيلها.

    الرابط بالبند يُفرَّغ والحالة تعود `in_stock`؛ ما اختاره المستخدم يبقى محفوظاً
    على البند نفسه، فإعادة الترحيل تستهلك الوحدات ذاتها لا غيرها.
    """
    released = ProductSerial.objects.filter(
        tenant_id=invoice.tenant_id, sales_line__invoice=invoice,
    ).update(status=ProductSerial.STATUS_IN_STOCK, sales_line=None)
    if released:
        logger.info(
            'product serials released back to stock: invoice=%s units=%d',
            invoice.pk, released,
        )
    return released


def restore_returned_sales_serials(return_invoice, lines) -> int:
    """مرجع البيع يُعيد البضاعة للمخزن (RETURN_IN) — ووحداتها المُباعة تعود معها.

    تُستعاد وحدات **الفاتورة الأصلية** لنفس الصنف بترتيب استهلاكها (الأقدم أولاً)
    بقدر الكمية المرتجعة، فلا تبقى وحدةٌ «مُباعة» لزبون أعادها. بندٌ بلا وحدات
    متتبَّعة — أو مرجعٌ بلا فاتورة أصلية — لا يفعل شيئاً: المخزون غير المتتبَّع
    يبقى كما كان.

    أيُّ وحدة بعينها رجعت ليس سؤالاً يجيبه المستند (لا اختيار في مرجع البيع)،
    فالترتيب هو الجواب الحتمي الوحيد المتاح.
    """
    original = getattr(return_invoice, 'original_invoice', None)
    if original is None:
        return 0

    restored = 0
    for line in lines:
        product = line.product
        if not product_tracks_serials(product):
            continue
        label = _product_label(product)
        qty = _whole_units(line.quantity, label=label)
        if qty <= 0:
            continue
        units = list(
            ProductSerial.objects.filter(
                tenant_id=return_invoice.tenant_id, product=product,
                status=ProductSerial.STATUS_SOLD, sales_line__invoice=original,
            ).order_by('id')[:qty]
        )
        for unit in units:
            unit.status = ProductSerial.STATUS_IN_STOCK
            unit.sales_line = None
            unit.save(update_fields=['status', 'sales_line'])
        restored += len(units)

    if restored:
        logger.info(
            'product serials restored by sale return: return=%s original=%s units=%d',
            return_invoice.pk, original.pk, restored,
        )
    return restored


# ══════════════════════════════════════════════════════════════════════════
# القراءة: «أي وحدة ذهبت لأي زبون»
# ══════════════════════════════════════════════════════════════════════════

def _serial_row(unit) -> dict:
    purchase_item = unit.purchase_item if unit.purchase_item_id else None
    purchase_invoice = (
        purchase_item.invoice if purchase_item and purchase_item.invoice_id else None
    )
    sales_line = unit.sales_line if unit.sales_line_id else None
    sales_invoice = sales_line.invoice if sales_line and sales_line.invoice_id else None
    return {
        'id': unit.id,
        'serial': unit.serial,
        'status': unit.status,
        'status_display': unit.get_status_display(),
        'product': unit.product_id,
        'product_name': _product_label(unit.product),
        'product_sku': getattr(unit.product, 'sku', '') or '',
        'purchase_invoice': purchase_invoice.id if purchase_invoice else None,
        'purchase_invoice_number': (
            purchase_invoice.invoice_number if purchase_invoice else None
        ),
        'supplier_name': (
            purchase_invoice.partner.name
            if purchase_invoice and purchase_invoice.partner_id else None
        ),
        'sales_invoice': sales_invoice.id if sales_invoice else None,
        'sales_invoice_number': (
            sales_invoice.invoice_number if sales_invoice else None
        ),
        'customer_name': (
            sales_invoice.customer.name
            if sales_invoice and sales_invoice.customer_id else None
        ),
        'created_at': unit.created_at.isoformat() if unit.created_at else None,
    }


def _serial_queryset(tenant_id):
    return ProductSerial.objects.filter(tenant_id=tenant_id).select_related(
        'product',
        'purchase_item__invoice__partner',
        'sales_line__invoice__customer',
    )


def product_serials(*, tenant_id, product_id, status=None, limit=500) -> list[dict]:
    """وحدات صنف واحد — بفلترة الحالة اختيارياً."""
    qs = _serial_queryset(tenant_id).filter(product_id=product_id)
    if status:
        qs = qs.filter(status=status)
    return [_serial_row(u) for u in qs.order_by('id')[:limit]]


def search_serials(*, tenant_id, q='', status=None, product_id=None, limit=100) -> list[dict]:
    """بحث على مستوى الشركة: من أين جاءت هذه الوحدة وإلى أي زبون ذهبت."""
    qs = _serial_queryset(tenant_id)
    term = str(q or '').strip()
    if term:
        qs = qs.filter(serial__icontains=term)
    if status:
        qs = qs.filter(status=status)
    if product_id:
        qs = qs.filter(product_id=product_id)
    limit = max(1, min(int(limit or 100), 500))
    return [_serial_row(u) for u in qs.order_by('-id')[:limit]]


# ══════════════════════════════════════════════════════════════════════════
# الباركود: EAN-13 داخلي (بادئة 2 من نطاق GS1 للاستخدام الداخلي)
# ══════════════════════════════════════════════════════════════════════════

def ean13_check_digit(twelve: str) -> str:
    """خانة التحقق لـEAN-13: مجموع موزون (1، 3 بالتناوب) ثم مكمّل العشرة."""
    digits = str(twelve or '')
    if len(digits) != 12 or not digits.isdigit():
        raise ValidationError('حساب خانة التحقق يتطلب 12 رقماً.')
    total = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(digits))
    return str((10 - total % 10) % 10)


def is_valid_ean13(barcode: str) -> bool:
    """باركود سليم البنية وخانة التحقق — مرجع واحد للتوليد والاختبار."""
    code = str(barcode or '')
    if len(code) != 13 or not code.isdigit():
        return False
    return ean13_check_digit(code[:12]) == code[12]


def generate_product_barcode(tenant_id, *, attempts: int = 40) -> str:
    """باركود EAN-13 غير مستخدم لهذه الشركة، يبدأ بـ«2».

    البادئة 2 محفوظة في GS1 للترقيم **الداخلي** للمتاجر، فلا تتعارض مع باركود
    مُصنِّع حقيقي. التفرّد يُفحص مقابل باركودات أصناف الشركة نفسها لا النظام كله:
    الباركود سمة الصنف عند صاحبه، وشركتان مستقلّتان قد تحملان الرقم ذاته.
    """
    used = set(
        Product.objects.filter(tenant_id=tenant_id)
        .exclude(barcode__isnull=True).exclude(barcode='')
        .values_list('barcode', flat=True)
    )
    for _ in range(max(1, attempts)):
        body = '2' + ''.join(random.choices('0123456789', k=11))
        candidate = body + ean13_check_digit(body)
        if candidate not in used:
            logger.info('barcode generated: tenant=%s barcode=%s', tenant_id, candidate)
            return candidate
    raise ValidationError('تعذّر توليد باركود غير مستخدم — أعد المحاولة.')
