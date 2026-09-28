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
from django.db.models import Sum

from .models import Product, ProductSerial, StockMovement

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
    """المنتج يتتبّع أرقاماً تسلسلية؟ (مُفعَّل عليه، وليس خدمة — الخدمة بلا وحدات)."""
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


def strip_serials_when_off(rows, tenant_id, side: str) -> None:
    """نمط «بدون» لا يخزّن أرقاماً أصلاً — تُفرَّغ من حمولة البنود عند الحفظ.

    الإلزام في الخدمات يمنع إنشاء الوحدات على أي حال؛ التفريغ هنا يمنع بقاء أرقامٍ
    نائمة على المستندات تصبح فاعلة فجأةً لو شُغّل الإعداد لاحقاً.

    #233: النمط الفعّال **لكل بند** عبر `effective_serial_mode` — بندٌ لمنتجٍ
    مفروضٍ بسياسة كفالة يبقى بأرقامه حتى إن كان نمط الشركة `off`؛ لهذا تغيّر
    التوقيع من نمطٍ واحد ثابت إلى `(tenant_id, side)` بنداءٍ واحد للدفعة.
    """
    candidates = [
        row for row in (rows or [])
        if isinstance(row, dict) and row.get('serials') and row.get('product') is not None
    ]
    if not candidates:
        return
    from core.hooks import serial_requirements
    requirement_map = serial_requirements(
        tenant_id, [row['product'].pk for row in candidates],
    )
    for row in candidates:
        mode = effective_serial_mode(
            tenant_id, row['product'], side, requirement_map=requirement_map,
        )
        if mode == SERIAL_MODE_OFF:
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
    """الوحدة المُرقَّمة لا تُجزَّأ — كمية كسرية على منتج تسلسلي خطأ إدخال."""
    qty = Decimal(str(quantity or 0))
    if qty != qty.to_integral_value():
        raise ValidationError(
            f"المنتج «{label}» يتتبّع أرقاماً تسلسلية — الكمية ({qty}) يجب أن تكون عدداً صحيحاً."
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


def effective_serial_mode(tenant_id, product, side: str, *, requirement_map=None) -> str:
    """مصدر واحد لكل قرار نمطٍ في هذا الملف (#233) — البيع والشراء يمرّان من هنا.

    منتجٌ يسمّيه `core.hooks.serial_requirements` (سياسة كفالة «برقم تسلسلي» في
    `after_sales` — بلا استيراده هنا، الربط عبر الـhook وحده) مفروضٌ:
    - `side='sale'`: `required` مهما كان إعداد الشركة — لا FIFO ولا بطاقة على
      رقم مخمَّن.
    - `side='purchase'`: `optional` على الأقل، و`required` إن كان إعداد
      الشركة كذلك — الحاوية قد لا تُفتح قبل الترحيل.

    منتجٌ غير مسمّى: نمط الشركة كما هو.

    `requirement_map`: يُمرَّر جاهزاً من مستدعٍ يعالج عدّة بنودٍ لمستندٍ واحد —
    نداءٌ واحد للمستند لا لكل بند. غيابه يحسبها لهذا المنتج وحده.
    """
    if requirement_map is None:
        from core.hooks import serial_requirements

        requirement_map = serial_requirements(tenant_id, [product.pk])
    forced = product.pk in requirement_map

    if side == 'sale':
        return SERIAL_MODE_REQUIRED if forced else sales_serial_mode(tenant_id)
    if side == 'purchase':
        company_mode = purchase_serial_mode(tenant_id)
        if not forced:
            return company_mode
        return company_mode if company_mode == SERIAL_MODE_REQUIRED else SERIAL_MODE_OPTIONAL
    raise ValueError(f"جانبٌ غير معروف لنمط الأرقام التسلسلية: {side}")


# ══════════════════════════════════════════════════════════════════════════
# الشراء: الاستلام يُنشئ الوحدات · التراجع يحرّرها
# ══════════════════════════════════════════════════════════════════════════

def assert_purchase_serials_declared(invoice) -> None:
    """«إجباري» يحرس **ترحيل** فاتورة الشراء لا استلامها وحده.

    الاستلام مع الترحيل مشروط (محلية + GR/IR + قيمة موجبة)، فالفاتورة الدولية أو
    فاتورة الكمية بلا قيمة كانت تُرحَّل بلا رقم واحد ثم يُقفل تعديلها فلا سبيل
    لإضافة الأرقام إلا بإلغاء الترحيل. الحارس هنا يقع **قبل** أي كتابة، والاستلام
    يبقى خط الدفاع الثاني كما هو (`apply_purchase_serials`).

    #233: النمط الفعّال **لكل بند** عبر `effective_serial_mode` — منتجٌ
    مفروضٌ بسياسة كفالة يصير `optional` هنا لا `required` تلقائياً (يُحرسه
    مصدره أدناه)، فلا يدخل هذا الحارس إلا حين يكون إعداد الشركة نفسه `required`.
    """
    items = [
        item for item in invoice.items.select_related('product').all()
        if product_tracks_serials(item.product)
    ]
    if not items:
        return
    from core.hooks import serial_requirements
    requirement_map = serial_requirements(
        invoice.tenant_id, [item.product_id for item in items],
    )

    incomplete: list[str] = []
    for item in items:
        product = item.product
        mode = effective_serial_mode(
            invoice.tenant_id, product, 'purchase', requirement_map=requirement_map,
        )
        if mode != SERIAL_MODE_REQUIRED:
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

    #233: لكل منتجٍ نمطه الفعّال الخاص — منتجٌ مفروضٌ بسياسة كفالة يصير على
    الأقلّ `optional` (لا يُمنع الاستلام بلا رقم)، ويُمنع فقط حين يبلغ
    `required` فعلاً (إعداد الشركة نفسه `required`، أو الشركة أيضاً فرضته).
    """
    candidates = [p for p in products if product_tracks_serials(p)]
    if not candidates:
        return
    from core.hooks import serial_requirements
    requirement_map = serial_requirements(tenant_id, [p.pk for p in candidates])
    tracked = [
        _product_label(p) for p in candidates
        if effective_serial_mode(tenant_id, p, 'purchase', requirement_map=requirement_map)
        == SERIAL_MODE_REQUIRED
    ]
    if not tracked:
        return
    raise ValidationError(
        'نمط الأرقام التسلسلية في إعدادات الشراء «إجباري»، وسند الاستلام المستقل '
        'لا يحمل أرقاماً — استلم هذه المنتجات من فاتورة الشراء نفسها، أو سجّل أرقام '
        'مخزونها من كرت المنتج: ' + '، '.join(tracked) + '.'
    )


def register_existing_serials(*, tenant_id, product, serials) -> int:
    """ترقيم مخزون قائم: وحدات «في المخزن» بلا بند شراء.

    الوحدة لا تُنشأ إلا من فاتورة شراء، فتشغيل «إجباري» في البيع كان يُجمّد بيع كل
    مخزونٍ سابق للميزة بلا طريق للأمام. هنا يُسجَّل ما هو موجود فعلاً: نفس قواعد
    التحقق (تنظيف، تكرار، تصادم)، وسقفه رصيد المنتج — الترقيم **يصف** مخزوناً
    قائماً ولا يخلق مخزوناً، فلا حركة مخزون له ولا قيد.
    """
    if not product_tracks_serials(product):
        raise ValidationError(
            f"المنتج «{_product_label(product)}» لا يتتبّع أرقاماً تسلسلية — "
            "فعّل «تتبّع بالرقم التسلسلي» في كرت المنتج أولاً."
        )
    label = _product_label(product)
    clean = normalize_serials(serials, label=label)
    if not clean:
        raise ValidationError('أدخل رقماً تسلسلياً واحداً على الأقل.')
    _assert_serials_free(tenant_id, product, clean)

    on_hand = Decimal(str(product.quantity_on_hand or 0))
    tracked = _tracked_in_stock_count(tenant_id, product)
    if tracked + len(clean) > on_hand:
        on_hand_label = (
            str(int(on_hand)) if on_hand == on_hand.to_integral_value() else str(on_hand)
        )
        raise ValidationError(
            f"المنتج «{label}»: رصيد المخزن {on_hand_label} وحدة ومنها {tracked} "
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
    - `required` ⇒ كل بند لمنتج تسلسلي يجب أن يحمل أرقاماً بعدد كميته المفوترة.
    - `optional` ⇒ ما وُجد يُتحقَّق ويُخزَّن، وما نقص يُترك بلا تتبّع.

    الاستلام الجزئي يأخذ الأرقام بالترتيب المُدخَل: ما استُلم سابقاً موجود أصلاً
    كصفوف، فتبدأ الحصّة الجديدة من حيث انتهت. كل التحقق يسبق أي كتابة.

    #233: النمط الفعّال **لكل بند** عبر `effective_serial_mode` — بند لمنتجٍ
    مفروضٍ بسياسة كفالة لا يتخطّاه `off` الشركة، ونداءٌ واحد لكل الدفعة لا لكل بند.
    """
    tenant_id = getattr(tenant, 'TenantID', tenant)
    rows = list(rows)
    tracked_products = {
        item.product_id: item.product for item, _ in rows
        if product_tracks_serials(item.product)
    }
    if not tracked_products:
        return 0
    from core.hooks import serial_requirements
    requirement_map = serial_requirements(tenant_id, list(tracked_products))

    planned: list[tuple] = []
    for item, quantity in rows:
        product = item.product
        if not product_tracks_serials(product):
            continue
        mode = effective_serial_mode(
            tenant_id, product, 'purchase', requirement_map=requirement_map,
        )
        if mode == SERIAL_MODE_OFF:
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
            'product serials received: tenant=%s units=%d lines=%d',
            tenant_id, created, len(planned),
        )
    return created


def _tracked_in_stock_count(tenant_id, product) -> int:
    """عدد وحدات المنتج المُرقَّمة `in_stock` — نواة رصيد «غير المرقّم» المشتركة
    بين تسجيل مخزونٍ قائم (`register_existing_serials`) والترقيم عند البيع
    (`consume_sales_serials`، #233)."""
    return ProductSerial.objects.filter(
        tenant_id=tenant_id, product=product, status=ProductSerial.STATUS_IN_STOCK,
    ).count()


def _pre_sale_on_hand(invoice, product) -> Decimal:
    """رصيد المنتج قبل حركة صرف **هذه الفاتورة تحديداً** — مُحسَبٌ صراحةً لا
    مفترَضاً من بقاء كائنٍ في الذاكرة بلا تحديث (#233-r1، مراجعة).

    الرصيد الحالي **مُنعَشٌ من القاعدة** زائد ما صرفته حركات هذه الفاتورة
    (`reference_type='SALE'`, `movement_type='OUT'`) لهذا المنتج بالضبط —
    يعمل سواءً سبقت حركةُ المخزون هذا النداء (`stock_on_post=True`، فتُضاف
    كميتها لتُلغي أثرها) أو لم تحدث أصلاً (`stock_on_post=False`، فلا شيء
    يُضاف والرصيد الحالي هو رصيد ما قبل البيع فعلاً). لا يفترض شيئاً عن
    الكائن الذي مرّره المستدعي ولا عن ترتيب الاستدعاءات."""
    current = Product.objects.filter(pk=product.pk).values_list(
        'quantity_on_hand', flat=True,
    ).first()
    current = Decimal(str(current or 0))
    already_out = StockMovement.objects.filter(
        tenant_id=invoice.tenant_id, product_id=product.pk,
        reference_type='SALE', reference_id=invoice.pk, movement_type='OUT',
    ).aggregate(total=Sum('quantity'))['total'] or Decimal('0')
    return current + Decimal(str(already_out))


def unnumbered_serial_balance(tenant_id, product) -> int:
    """رصيد المنتج غير المرقَّم الآن — للعرض (معاينة سياسة الكفالة قبل الحفظ،
    #233) لا حارساً وقت الحفظ الفعلي؛ الرقم قد يتغيّر حتى لحظة التنفيذ."""
    on_hand = Decimal(str(product.quantity_on_hand or 0))
    balance = on_hand - _tracked_in_stock_count(tenant_id, product)
    return int(balance) if balance > 0 else 0


def _assert_serials_free(tenant_id, product, serials) -> None:
    """الرقم التسلسلي فريد لكل (شركة، منتج) — التصادم يُسمّى لا يُبتَلع."""
    taken = sorted(
        ProductSerial.objects.filter(
            tenant_id=tenant_id, product=product, serial__in=list(serials),
        ).values_list('serial', flat=True)
    )
    if taken:
        raise ValidationError(
            f"المنتج «{_product_label(product)}»: الأرقام التسلسلية التالية مستخدمة "
            f"مسبقاً — {'، '.join(taken)}."
        )


def release_purchase_serials(
    *, tenant_id, quantities_by_item, document_label='', action_label='التراجع عن',
) -> int:
    """يحذف وحدات مستند شراء عند التراجع عنه — ويمنع التراجع إن غادرت أيٌّ منها المخزن.

    quantities_by_item: {item_id: عدد الوحدات المراد تحريرها} — و`None` تعني
    «كل وحدات هذا البند». التحرير الجزئي (إلغاء إرسالية واحدة من عدّة إرساليات)
    يأخذ الأحدث أولاً: الاستلام يُنشئ بالترتيب والبيع يستهلك بـFIFO من الأقدم،
    فأحدث الوحدات هي بالضبط ما جاءت به الإرسالية الملغاة.

    وحدةٌ بحالةٍ غير `in_stock` (مُباعة بفاتورة بيع، أو مصروفةٌ خارج البيع
    `issued`، #223) تعني أثراً بُني على هذا المستند: تُسمّى الوحدات وحالتها
    ويُرفض التراجع — نفس منطق حارس اعتمادية المخزون، فلا يبقى أثرٌ لوحدة لا أصل لها.
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

    # المنع لكل حالةٍ غير `in_stock` لا لـ`sold` وحدها: وحدةٌ `issued` (صُرفت
    # خارج البيع، #223) تُحذَف بصمت إن اقتصر الفحص على البيع — نفس الثغرة التي
    # كانت تفتح لو تُرك الفحص على مُباع دون غيره.
    not_in_stock = list(
        ProductSerial.objects.filter(pk__in=doomed)
        .exclude(status=ProductSerial.STATUS_IN_STOCK)
        .select_related('sales_line__invoice')
    )
    if not_in_stock:
        listing = '؛ '.join(
            f"{s.serial} ({s.get_status_display()})"
            + (
                f" — فاتورة {s.sales_line.invoice.invoice_number}"
                if s.status == ProductSerial.STATUS_SOLD and s.sales_line_id
                and s.sales_line.invoice_id else ''
            )
            for s in not_in_stock
        )
        logger.warning(
            'release_purchase_serials blocked: %s has %d non-in-stock unit(s)',
            document_label or 'purchase document', len(not_in_stock),
        )
        raise ValidationError(
            f"تعذّر {action_label} {document_label or 'هذا المستند'}: وحدات بأرقام "
            f"تسلسلية من هذه البضاعة ليست في المخزن — {listing}"
        )

    deleted = ProductSerial.objects.filter(pk__in=doomed).delete()[0]
    logger.info(
        'product serials released: %s units=%d', document_label or 'purchase document', deleted,
    )
    return deleted


def release_returned_purchase_serials(return_invoice) -> int:
    """مرجع الشراء يُخرج بضاعته من المخزن — ووحداتها المُرقَّمة تخرج معها.

    الوحدات المقصودة هي وحدات **الفاتورة الأصلية** لنفس المنتج، تُؤخذ الأحدث أولاً
    (نفس قاعدة إلغاء الإرسالية)، ووحدةٌ ليست `in_stock` منها (مُباعة، أو مصروفة
    خارج البيع) تمنع ترحيل المرجع بدل أن تبقى «في المخزن» وبضاعتها عند المورد.
    مرجعٌ بلا فاتورة أصلية لا يُمسّ: لا شيء يقول أي وحدة بعينها رجعت.
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
        # بلا فلترة حالة: أي وحدةٍ غادرت `in_stock` يجب أن تدخل الاختيار كي يوقفها الحارس.
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
        document_label=f"مرتجع الشراء {return_invoice.invoice_number}",
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

def assert_sales_serials_declared(invoice, lines) -> None:
    """«إجباري» يحرس ترحيل فاتورة البيع **قبل** أي كتابة.

    مرآة `assert_purchase_serials_declared` على جانب البيع: الترحيل يكتب قيداً
    وحركة مخزون وإرسالية قبل أن يصل الاستهلاك، فرفضٌ متأخّر داخل معاملة ذرّية
    يُلغي كل ذلك بصمت ويعيد المستخدم لشاشة لا تقول له ما ينقص. هنا يُسمّى الناقص
    بندَاً بندَاً ومعه المخرج: المخزون القديم بلا أرقام يُرقَّم من كرت المنتج.

    بندٌ استُهلكت وحداته فعلاً (إعادة ترحيل بعد إلغاء) لا يُطالَب ثانيةً — نفس
    قاعدة الذرّية في `consume_sales_serials`.

    #233: النمط الفعّال **لكل بند** عبر `effective_serial_mode` — بند لمنتجٍ
    مفروضٍ بسياسة كفالة يُطالَب دائماً بغضّ النظر عن إعداد الشركة.
    """
    lines = [ln for ln in lines if product_tracks_serials(ln.product)]
    if not lines:
        return
    from core.hooks import serial_requirements
    requirement_map = serial_requirements(
        invoice.tenant_id, [ln.product_id for ln in lines],
    )

    incomplete: list[str] = []
    for line in lines:
        product = line.product
        mode = effective_serial_mode(
            invoice.tenant_id, product, 'sale', requirement_map=requirement_map,
        )
        if mode != SERIAL_MODE_REQUIRED:
            continue
        label = _product_label(product)
        needed = _whole_units(line.quantity, label=label)
        if needed <= 0:
            continue
        if ProductSerial.objects.filter(
            sales_line=line, status=ProductSerial.STATUS_SOLD,
        ).exists():
            continue
        declared = normalize_serials(line.serials, label=label)
        if len(declared) != needed:
            incomplete.append(
                f"«{label}» (المطلوب {needed} والمختار {len(declared)})"
            )

    if incomplete:
        raise ValidationError(
            'اختيار الأرقام التسلسلية إجباري قبل ترحيل فاتورة البيع — أكمل وحدات '
            'البنود التالية من عمود «الوحدات»: ' + '؛ '.join(incomplete)
            + '. ومخزونٌ قديم بلا أرقام يُرقَّم من تبويب «الأرقام التسلسلية» في كرت المنتج.'
        )


def assert_sales_return_serials_declared(return_invoice, lines) -> None:
    """«إجباري» يحرس ترحيل **مرجع** البيع كما يحرس البيع — قبل أي كتابة.

    مرآة `assert_sales_serials_declared`: «أي وحدةٍ رجعت؟» سؤالٌ لا يجيبه
    ترتيبُ المعرّفات. تحت `required` تُسمّى الوحدة المرتجعة على البند، وإلا
    استعاد المخزنُ وحدةً وأنهى `after_sales` بطاقةَ وحدةٍ أخرى — كلتاهما خطأ في
    ورقة زبون. وتحت `optional` يبقى الترتيب احتياطاً كما كان.

    مرجعٌ بلا فاتورة أصلية لا يستعيد شيئاً فلا يُطالَب بشيء، وبندٌ استُعيدت
    وحداته فعلاً (إعادة ترحيل) لا يُطالَب ثانيةً.
    """
    mode = sales_serial_mode(return_invoice.tenant_id)
    if mode != SERIAL_MODE_REQUIRED:
        return
    if getattr(return_invoice, 'original_invoice', None) is None:
        return

    incomplete: list[str] = []
    for line in lines:
        product = line.product
        if not product_tracks_serials(product):
            continue
        label = _product_label(product)
        needed = _whole_units(line.quantity, label=label)
        if needed <= 0:
            continue
        if ProductSerial.objects.filter(return_line=line).exists():
            continue
        declared = normalize_serials(line.serials, label=label)
        if len(declared) != needed:
            incomplete.append(
                f"«{label}» (المطلوب {needed} والمختار {len(declared)})"
            )

    if incomplete:
        raise ValidationError(
            'اختيار الأرقام التسلسلية إجباري قبل ترحيل مرجع البيع — سمِّ الوحدات '
            'المرتجعة في البنود التالية: ' + '؛ '.join(incomplete)
            + '. الوحدة المرتجعة تُسمّى ولا تُخمَّن: عليها تُبنى استعادة المخزن '
            'وإنهاء بطاقة الكفالة.'
        )


def consume_sales_serials(invoice, lines) -> int:
    """يوسم وحدات فاتورة بيع «مُباع» ويربطها ببنودها عند الترحيل.

    ما اختاره المستخدم صريحاً على البند يُستهلَك كما هو (بعد التحقق أنه موجود
    وفي المخزن ولنفس المنتج)، والباقي يُخصَّص تلقائياً **FIFO** من أقدم الوحدات
    المتاحة — كي لا يُلزَم من لا يهمّه اختيار الوحدة بعينها.

    و«اختياري» وحده هو ما يقبل هذا التخصيص التلقائي: تحت `required` يُرفض البند
    الناقص اختياره بدل أن يُملأ FIFO. سببه أن التخصيص التلقائي **تخمين**: يقول
    «خرجت أقدم وحدة» لا «خرجت هذه الوحدة»، فمطالبة كفالةٍ لاحقة تُطابَق برقمٍ لم
    يره أحد على العلبة. من يشغّل «إجباري» يطلب واقعةً مسجَّلة لا استنتاجاً.

    نقص المتاح (مخزون قديم سابق للتتبّع): `optional` يخصّص ما وُجد ويترك الباقي
    بلا تتبّع، و`required` يكون قد رُفض قبل ذلك. `off` لا يفعل شيئاً.

    #233: رقمٌ مُدخَل لا وجود له بعد في السجل **يُسجَّل ويُستهلك في نفس
    الخطوة** — ما دام للمنتج رصيدٌ غير مرقَّم (رصيد المخزن قبل حركة هذه
    البيعة، ناقص وحداته المرقَّمة `in_stock` حالياً)؛ تجاوزه 400 تسمّي البند
    والعدد. الرصيد «قبل حركة هذه البيعة» يُحسب صراحةً بـ`_pre_sale_on_hand`
    (رصيدٌ مُنعَشٌ من القاعدة زائد ما صرفته حركات هذه الفاتورة نفسها) — لا
    اعتماداً على بقاء `product.quantity_on_hand` في الذاكرة بلا تحديث،
    فالحساب صحيحٌ بصرف النظر عن ترتيب استدعاءات المستدعي. قواعد التسجيل
    نفسها التي يفرضها `register_existing_serials` (تنظيف، تكرار، تصادم) —
    لا فرعٌ ثانٍ منها.
    """
    lines = [ln for ln in lines if product_tracks_serials(ln.product)]
    if not lines:
        return 0
    from core.hooks import serial_requirements
    requirement_map = serial_requirements(
        invoice.tenant_id, [ln.product_id for ln in lines],
    )

    planned: list[tuple] = []
    for line in lines:
        product = line.product
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

        mode = effective_serial_mode(
            invoice.tenant_id, product, 'sale', requirement_map=requirement_map,
        )
        if mode == SERIAL_MODE_OFF:
            continue

        declared = normalize_serials(line.serials, label=label)
        if len(declared) > needed:
            raise ValidationError(
                f"البند «{label}»: عدد الأرقام التسلسلية المختارة ({len(declared)}) "
                f"يتجاوز الكمية ({needed})."
            )
        # خط الدفاع الثاني تحت «إجباري»: الحارس الأول
        # (`assert_sales_serials_declared`) يقع قبل أي كتابة، وهذا يحمي كل مسار
        # يستدعي الاستهلاك مباشرةً بلا مروره.
        if mode == SERIAL_MODE_REQUIRED and len(declared) != needed:
            raise ValidationError(
                f"البند «{label}»: اختيار الأرقام التسلسلية إجباري — "
                f"المطلوب {needed} والمختار {len(declared)}."
            )

        existing_by_serial = {
            u.serial: u for u in ProductSerial.objects.filter(
                tenant_id=invoice.tenant_id, product=product, serial__in=declared,
            )
        }
        unusable = [
            s for s in declared
            if s in existing_by_serial
            and existing_by_serial[s].status != ProductSerial.STATUS_IN_STOCK
        ]
        if unusable:
            raise ValidationError(
                f"البند «{label}»: الأرقام التسلسلية التالية غير متوفرة في المخزن "
                f"لهذا المنتج — {'، '.join(unusable)}."
            )
        chosen = [
            existing_by_serial[s] for s in declared if s in existing_by_serial
        ]
        new_serials = [s for s in declared if s not in existing_by_serial]

        if new_serials:
            on_hand = _pre_sale_on_hand(invoice, product)
            tracked = _tracked_in_stock_count(invoice.tenant_id, product)
            balance = on_hand - tracked
            if len(new_serials) > balance:
                balance = balance if balance > 0 else Decimal('0')
                balance_label = (
                    str(int(balance)) if balance == balance.to_integral_value()
                    else str(balance)
                )
                raise ValidationError(
                    f"البند «{label}»: {len(new_serials)} رقماً جديداً يتجاوز رصيد "
                    f"المنتج غير المرقَّم ({balance_label} وحدة) — قلّل عدد الأرقام "
                    "الجديدة، أو سجّل أرقام المخزون القديم من كرت المنتج أولاً."
                )
            new_units = [
                ProductSerial.objects.create(
                    tenant_id=invoice.tenant_id, product=product, serial=serial,
                    status=ProductSerial.STATUS_IN_STOCK,
                )
                for serial in new_serials
            ]
            chosen.extend(new_units)
            logger.info(
                'product serials numbered at sale: invoice=%s product=%s units=%d',
                invoice.pk, product.pk, len(new_units),
            )

        # التخصيص التلقائي لـ«اختياري» وحده — تحت «إجباري» يكون الاختيار مكتملاً
        # ومتحقَّقاً أعلاه، فلا نقص يُملأ ولا تخمين يُسجَّل.
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
            'product serials sold: invoice=%s units=%d', invoice.pk, consumed,
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

    تُستعاد وحدات **الفاتورة الأصلية** لنفس المنتج بقدر الكمية المرتجعة، فلا
    تبقى وحدةٌ «مُباعة» لزبون أعادها. بندٌ بلا وحدات متتبَّعة — أو مرجعٌ بلا
    فاتورة أصلية — لا يفعل شيئاً: المخزون غير المتتبَّع يبقى كما كان.

    **ما سمّاه البند يُستعاد كما هو** (#222): `line.serials` هو الجواب على «أيُّ
    وحدةٍ رجعت»، ويُتحقَّق أنها مُباعةٌ على الفاتورة الأصلية ولنفس المنتج. كان
    الاختيار بترتيب `id` وحده فيُعيد المخزنُ الوحدة الأولى مهما كان المكتوب على
    ورقة المرجع — ويُنهي `after_sales` بطاقةَ جهازٍ لم يُرجَع. الترتيب يبقى
    احتياطاً لـ`optional` وحده (تحت `required` يرفض
    `assert_sales_return_serials_declared` البندَ الناقص قبل أي كتابة).

    **الأثر لا يُمحى:** `sales_line` يبقى على بند البيع الأصلي، ويُسجَّل بندُ
    المرجع في `return_line` — فيعرف `revert_returned_sales_serials` عند إلغاء
    ترحيل المرجع أيَّ وحدةٍ أعاد وإلى أيِّ بيعٍ تعود، ويعرف
    `after_sales/services.py` (`on_sales_return_posted`) أيَّ بطاقةٍ يُنهي.
    الحالةُ `in_stock` هي ما يقول إن الوحدة ليست لزبون، و`_serial_row` لا
    يُسمّي زبوناً لوحدةٍ في المخزن.
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
        sold_on_original = ProductSerial.objects.filter(
            tenant_id=return_invoice.tenant_id, product=product,
            status=ProductSerial.STATUS_SOLD, sales_line__invoice=original,
        )
        declared = normalize_serials(line.serials, label=label)
        if len(declared) > qty:
            raise ValidationError(
                f"بند المرجع «{label}»: عدد الأرقام التسلسلية المختارة "
                f"({len(declared)}) يتجاوز الكمية المرتجعة ({qty})."
            )
        units = list(sold_on_original.filter(serial__in=declared)) if declared else []
        if len(units) != len(declared):
            found = {u.serial for u in units}
            missing = [s for s in declared if s not in found]
            raise ValidationError(
                f"بند المرجع «{label}»: الأرقام التسلسلية التالية ليست مُباعة على "
                f"الفاتورة الأصلية «{original.invoice_number}» — "
                f"{'، '.join(missing)}."
            )
        shortfall = qty - len(units)
        if shortfall > 0:
            units.extend(
                sold_on_original
                .exclude(pk__in=[u.pk for u in units])
                .order_by('id')[:shortfall]
            )
        for unit in units:
            unit.status = ProductSerial.STATUS_IN_STOCK
            unit.return_line = line
            unit.save(update_fields=['status', 'return_line'])
        restored += len(units)

    if restored:
        logger.info(
            'product serials restored by sale return: return=%s original=%s units=%d',
            return_invoice.pk, original.pk, restored,
        )
    return restored


def revert_returned_sales_serials(return_invoice) -> int:
    """إلغاء ترحيل مرجع البيع يُعيد وحداته «مُباعة» على بيعها الأصلي.

    مرآة `release_purchase_serials` على جانب البيع: الوحدات هي ما سجّل
    `restore_returned_sales_serials` بندَ هذا المرجع عليها (`return_line`).
    وحدةٌ تحرّكت بعد المرجع — بِيعت ثانيةً، أو انفصلت عن بند بيعها الأصلي
    (إلغاءُ ترحيل ذلك البيع أو بيعٍ لاحقٍ فرّغ الرابط) — تُسمّى ويُرفض الإلغاء:
    إعادتُها «مُباعة» كانت ستسرق وحدةً من زبونٍ آخر أو تُسندها لبيعٍ لا وجود له.

    مرجعٌ رُحِّل قبل وجود `return_line` لا أثر له فلا يُعيد شيئاً — تخمينُ
    الوحدات هنا أسوأ من تركها في المخزن.
    """
    units = list(
        ProductSerial.objects.filter(
            tenant_id=return_invoice.tenant_id,
            return_line__invoice=return_invoice,
        ).select_related('sales_line__invoice').order_by('id')
    )
    if not units:
        return 0

    original_id = getattr(return_invoice, 'original_invoice_id', None)
    moved = [
        u for u in units
        if u.status != ProductSerial.STATUS_IN_STOCK
        or not u.sales_line_id
        or u.sales_line.invoice_id != original_id
    ]
    if moved:
        listing = '؛ '.join(
            u.serial + (
                f" (فاتورة {u.sales_line.invoice.invoice_number})"
                if u.status == ProductSerial.STATUS_SOLD and u.sales_line_id
                and u.sales_line.invoice_id else ''
            )
            for u in moved
        )
        logger.warning(
            'revert_returned_sales_serials blocked: return=%s moved=%d',
            return_invoice.pk, len(moved),
        )
        raise ValidationError(
            f"تعذّر إلغاء ترحيل مرجع البيع {return_invoice.invoice_number}: وحداتٌ "
            f"بأرقام تسلسلية أعادها هذا المرجع تحرّكت بعده (بِيعت ثانيةً أو انفصلت "
            f"عن فاتورة بيعها الأصلية). ألغِ ترحيل ما بُني عليها أولاً — "
            f"الوحدات: {listing}"
        )

    reverted = ProductSerial.objects.filter(pk__in=[u.pk for u in units]).update(
        status=ProductSerial.STATUS_SOLD, return_line=None,
    )
    logger.info(
        'product serials sold again by return unpost: return=%s original=%s units=%d',
        return_invoice.pk, original_id, reverted,
    )
    return reverted


# ══════════════════════════════════════════════════════════════════════════
# الصرف خارج البيع: بندُ مستندٍ في app آخر يستهلك وحدةً بلا فاتورة (#223)
# ══════════════════════════════════════════════════════════════════════════

def assert_issue_serials_declared(tenant_id, parts) -> None:
    """«إجباري» يحرس صرفاً خارج البيع قبل أي كتابة — مرآة `assert_sales_serials_declared`.

    `parts`: كائناتٌ تحمل `product`/`quantity`/`serials` (بند مستندٍ في app آخر
    مثل `ServiceOrderPart`) — لا استيراد لنوعها هنا، والفرض يتبع `effective_serial_mode`
    بـ`side='sale'` (#233: الصرف خارج البيع صرفٌ للزبون كالبيع تماماً)، لكل بندٍ
    على حدة، بنداءٍ واحد للدفعة.
    """
    parts = [p for p in parts if product_tracks_serials(p.product)]
    if not parts:
        return
    from core.hooks import serial_requirements
    requirement_map = serial_requirements(tenant_id, [p.product_id for p in parts])

    incomplete: list[str] = []
    for part in parts:
        product = part.product
        mode = effective_serial_mode(
            tenant_id, product, 'sale', requirement_map=requirement_map,
        )
        if mode != SERIAL_MODE_REQUIRED:
            continue
        label = _product_label(product)
        needed = _whole_units(part.quantity, label=label)
        if needed <= 0:
            continue
        declared = normalize_serials(part.serials, label=label)
        if len(declared) != needed:
            incomplete.append(
                f"«{label}» (المطلوب {needed} والمختار {len(declared)})"
            )

    if incomplete:
        raise ValidationError(
            'اختيار الأرقام التسلسلية إجباري قبل هذا الصرف — أكمل وحدات '
            'البنود التالية: ' + '؛ '.join(incomplete) + '.'
        )


def issue_serials(tenant_id, parts) -> int:
    """يستهلك وحداتٍ مُرقَّمة لبنودٍ صُرفت خارج البيع — مرآة `consume_sales_serials`.

    الاختيار الصريح على البند يُستهلَك أولاً (بعد التحقّق أنه في المخزن ولنفس
    المنتج)، والباقي يُخصَّص FIFO تحت `optional` وحده — نفس قاعدة البيع بالضبط.
    الوحدة تصير `STATUS_ISSUED` لا `STATUS_SOLD`: بيعٌ لاحقٌ بـFIFO
    (`consume_sales_serials`) يستعلم `in_stock` وحدها فلن يخصّصها أبداً.

    #233: النمط الفعّال **لكل بند** بـ`side='sale'` (صرفٌ للزبون خارج فاتورة
    البيع، مرآة `assert_issue_serials_declared`) — بنداءٍ واحد للدفعة.
    """
    parts = [p for p in parts if product_tracks_serials(p.product)]
    if not parts:
        return 0
    from core.hooks import serial_requirements
    requirement_map = serial_requirements(tenant_id, [p.product_id for p in parts])

    planned: list[tuple] = []
    for part in parts:
        product = part.product
        mode = effective_serial_mode(
            tenant_id, product, 'sale', requirement_map=requirement_map,
        )
        if mode == SERIAL_MODE_OFF:
            continue
        label = _product_label(product)
        needed = _whole_units(part.quantity, label=label)
        if needed <= 0:
            continue

        declared = normalize_serials(part.serials, label=label)
        if len(declared) > needed:
            raise ValidationError(
                f"البند «{label}»: عدد الأرقام التسلسلية المختارة ({len(declared)}) "
                f"يتجاوز الكمية ({needed})."
            )
        if mode == SERIAL_MODE_REQUIRED and len(declared) != needed:
            raise ValidationError(
                f"البند «{label}»: اختيار الأرقام التسلسلية إجباري — "
                f"المطلوب {needed} والمختار {len(declared)}."
            )
        chosen = list(
            ProductSerial.objects.filter(
                tenant_id=tenant_id, product=product, serial__in=declared,
                status=ProductSerial.STATUS_IN_STOCK,
            ).order_by('id')
        )
        if len(chosen) != len(declared):
            found = {s.serial for s in chosen}
            missing = [s for s in declared if s not in found]
            raise ValidationError(
                f"البند «{label}»: الأرقام التسلسلية التالية غير متوفرة في المخزن "
                f"لهذا المنتج — {'، '.join(missing)}."
            )

        shortfall = needed - len(chosen)
        if shortfall > 0:
            auto = list(
                ProductSerial.objects.filter(
                    tenant_id=tenant_id, product=product,
                    status=ProductSerial.STATUS_IN_STOCK,
                )
                .exclude(pk__in=[s.pk for s in chosen])
                .order_by('id')[:shortfall]
            )
            chosen.extend(auto)
        planned.append((part, chosen))

    consumed = 0
    for part, chosen in planned:
        for unit in chosen:
            unit.status = ProductSerial.STATUS_ISSUED
            unit.issued_to = part
            unit.save(update_fields=['status', 'issued_to'])
            consumed += 1

    if consumed:
        logger.info(
            'product serials issued outside sale: tenant=%s units=%d',
            tenant_id, consumed,
        )
    return consumed


def unissue_serials(tenant_id, parts) -> int:
    """يعيد وحدات بنودٍ صُرفت خارج البيع إلى المخزن — مرآة `release_sales_serials`."""
    part_ids = [p.pk for p in parts]
    if not part_ids:
        return 0
    released = ProductSerial.objects.filter(
        tenant_id=tenant_id, issued_to_id__in=part_ids,
    ).update(status=ProductSerial.STATUS_IN_STOCK, issued_to=None)
    if released:
        logger.info(
            'product serials unissued back to stock: tenant=%s units=%d',
            tenant_id, released,
        )
    return released


# ══════════════════════════════════════════════════════════════════════════
# القراءة: «أي وحدة ذهبت لأي زبون»
# ══════════════════════════════════════════════════════════════════════════

def _serial_row(unit) -> dict:
    purchase_item = unit.purchase_item if unit.purchase_item_id else None
    purchase_invoice = (
        purchase_item.invoice if purchase_item and purchase_item.invoice_id else None
    )
    # وحدةٌ في المخزن ليست لزبون: مرجعُ البيع يُبقي `sales_line` أثراً لبيعها
    # الأصلي (`restore_returned_sales_serials`)، فالحالةُ هي ما يقرّر لا الرابط.
    sales_line = (
        unit.sales_line
        if unit.sales_line_id and unit.status == ProductSerial.STATUS_SOLD else None
    )
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
        # مطالبة الكفالة تبدأ بمسح الرقم وتنتهي بـ«من اشتراه ومتى»: الاسم وحده
        # يسمّي ولا يُثبت — المعرّف يفتح كرت الطرف، والهاتف يتحقّق على الطاولة،
        # وتاريخ الفاتورة هو ما تُحسب منه مدّة الكفالة.
        'customer': sales_invoice.customer_id if sales_invoice else None,
        'customer_phone': (
            (sales_invoice.customer.phone or '')
            if sales_invoice and sales_invoice.customer_id else None
        ),
        'sold_at': (
            sales_invoice.invoice_date.isoformat()
            if sales_invoice and sales_invoice.invoice_date else None
        ),
        'created_at': unit.created_at.isoformat() if unit.created_at else None,
    }


def _serial_queryset(tenant_id):
    return ProductSerial.objects.filter(tenant_id=tenant_id).select_related(
        'product',
        'purchase_item__invoice__partner',
        'sales_line__invoice__customer',
    )


def product_serials(
    *, tenant_id, product_id, status=None, sales_invoice=None, limit=500,
) -> list[dict]:
    """وحدات منتج واحد — بفلترة الحالة، أو بوحدات **فاتورة بيعٍ بعينها** اختيارياً.

    `sales_invoice` لمرجع البيع (#222 مراجعة): الوحدات المرتجَعة **مُباعة على
    الفاتورة الأصلية** لا «في المخزن» — فمُنتقي الأرقام هناك يحتاج مُباع هذه
    الفاتورة تحديداً، لا فلتر الحالة العام الذي لا يعرف أيّ فاتورة.
    """
    qs = _serial_queryset(tenant_id).filter(product_id=product_id)
    if sales_invoice:
        qs = qs.filter(
            sales_line__invoice_id=sales_invoice, status=ProductSerial.STATUS_SOLD,
        )
    elif status:
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
    مُصنِّع حقيقي. التفرّد يُفحص مقابل باركودات منتجات الشركة نفسها لا النظام كله:
    الباركود سمة المنتج عند صاحبه، وشركتان مستقلّتان قد تحملان الرقم ذاته.
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
