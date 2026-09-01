"""T-REORDER: مصدر الحقيقة الوحيد لحالة مخزون المنتج.

لماذا وحدةٌ لقاعدةٍ من سطرين: كانت القاعدة مكتوبة **ستّ مرّات** — في
`inventory/serializers.py` (بطاقة المنتج)، وفي `inventory/views.py` (فلتر الجدول)،
وفي `core/dashboard_api.py` (عدّادات الصفحة الأولى)، وفي `core/reports/inventory.py`
(تقرير تحت حدّ الطلب)، وفي شاشتَي `StockLevelsPage` و`ItemsManagement`. وتباعدت
فعلاً لا احتمالاً: الداشبورد كان يشترط وجود حدٍّ أدنى **قبل** أن يعدّ منتجاً نافداً
فيخفي أغلب النافد، والشاشة كانت تصبغ كلّ رصيدٍ صفر بلون «منخفض» بينما الخادم
يسمّيه «نفذ». رقمان مختلفان لسؤالٍ واحد على شاشتين.

ثلاثة قرارات تسكن هنا ولا تُكرَّر:

1. **الحالة تُقاس على «المتاح» لا على «الرصيد».** المتاح = الرصيد − المحجوز،
   والمحجوز من `sales.services.reserved_quantity_map` — نفس مصدر حارس البيع.
   منتجٌ رصيده عشرة وكلّه محجوزٌ لزبون ليس متوفّراً لزبونٍ آخر.
2. **«نفذ» لا يشترط حدّاً أدنى.** المتاح ≤ 0 نفادٌ سواء ضُبط له حدّ أم لا — وهذا
   هو العيب الذي كان يُخفي أغلب الكتالوج عن عدّاد الداشبورد.
3. **الحدّ الفعّال يقبل بديلاً محسوباً.** إن لم يضبط المستخدم `min_stock_level`
   يحلّ محلّه الحدّ المقترَح من `inventory/replenishment.py` — فالكتالوج الذي لم
   يُضبط له حدّ يدويّاً (وهو معظمه) يعمل من اليوم الأول بلا إدخال.

الخدمة (`is_service`) بلا مخزون أصلاً — فحالتها «متوفّر» دائماً، وإلّا صُبغ كلّ
بند خدمةٍ في الفاتورة بلون «نفذ» وهو إنذارٌ كاذب.
"""
from __future__ import annotations

from decimal import Decimal

from django.db.models import Case, DecimalField, F, Q, Value, When

ZERO = Decimal("0")

STATUS_OUT_OF_STOCK = "out_of_stock"
STATUS_LOW = "low_stock"
STATUS_OVERSTOCK = "overstock"
STATUS_IN_STOCK = "in_stock"

#: مرتّبة بالإلحاح — أوّلها أشدّها.
STATUS_CHOICES = (STATUS_OUT_OF_STOCK, STATUS_LOW, STATUS_OVERSTOCK, STATUS_IN_STOCK)

STATUS_LABELS = {
    STATUS_OUT_OF_STOCK: "نفذ",
    STATUS_LOW: "منخفض",
    STATUS_OVERSTOCK: "فائض",
    STATUS_IN_STOCK: "متوفّر",
}

_QTY_FIELD = DecimalField(max_digits=18, decimal_places=4)


def _dec(value) -> Decimal:
    if value is None or value == "":
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def reserved_of(product, reserved_map=None) -> Decimal:
    """المحجوز لهذا المنتج من خريطة الحجز (فارغةٌ = لا حجز)."""
    if not reserved_map:
        return ZERO
    return _dec(reserved_map.get(getattr(product, "id", None) or getattr(product, "pk", None)))


def available_of(product, reserved_map=None) -> Decimal:
    """المتاح = الرصيد − المحجوز. الخدمة بلا مخزون فمتاحها صفر (ولا يُقاس)."""
    return _dec(getattr(product, "quantity_on_hand", 0)) - reserved_of(product, reserved_map)


def effective_min(product, suggested_min=None) -> Decimal:
    """الحدّ الأدنى الحاكم: اليدوي إن وُجد، وإلّا المقترَح، وإلّا صفر.

    اليدوي يسبق المقترَح دائماً — رقم المالك لا يُدهَس برقمٍ محسوب.
    """
    manual = getattr(product, "min_stock_level", None)
    if manual is not None and _dec(manual) > ZERO:
        return _dec(manual)
    return max(_dec(suggested_min), ZERO)


def effective_max(product, suggested_max=None) -> Decimal:
    """الحدّ الأقصى الحاكم (صفر = بلا حدّ أقصى، فلا «فائض»)."""
    manual = getattr(product, "max_stock_level", None)
    if manual is not None and _dec(manual) > ZERO:
        return _dec(manual)
    return max(_dec(suggested_max), ZERO)


def family_available_map(tenant_id: int, *, reserved_map=None) -> dict:
    """أرصدة كل عائلةٍ (منتج/أب) في الشركة مجمَّعةً «متاح» — استعلامٌ واحدٌ
    للشركة كلّها، لا واحدٌ لكل صفّ (#25).

    المصدر الذي تقرأه `stock_status_of` حين يكون للمنتج أبٌ: مجموع أرصدة **كل**
    برانداته لا رصيد هذا البراند وحده — وإلا ظهر كل براندٍ «منخفضاً» كذباً في
    منتجٍ وفير (البند 3، #25). يُبنى مرّةً لكل طلب ويُمرَّر إلى `stock_status_of`
    صفّاً بصفّ، بنفس نمط `reserved_map` القائم — لا استعلامٌ مترابطٌ لكل صفّ،
    فذاك النمط كلّف هذا المستودع 17 ثانية من قبل.
    """
    from .models import Product

    totals: dict[int, Decimal] = {}
    rows = (
        Product.objects.filter(tenant_id=tenant_id, family_id__isnull=False)
        .values('id', 'family_id', 'quantity_on_hand')
    )
    for row in rows:
        available = _dec(row['quantity_on_hand']) - _dec((reserved_map or {}).get(row['id']))
        totals[row['family_id']] = totals.get(row['family_id'], ZERO) + available
    return totals


def _status_for(available: Decimal, minimum: Decimal, maximum: Decimal) -> str:
    """السلّم من أربعة أسطر — القرار الوحيد، يستدعيه `stock_status_of` (صفٌّ
    واحد) و`family_status_map` (أبٌ واحد) كلاهما. لا نسخة ثانية منه (#28)."""
    if available <= ZERO:
        return STATUS_OUT_OF_STOCK
    if minimum > ZERO and available <= minimum:
        return STATUS_LOW
    if maximum > ZERO and available > maximum:
        return STATUS_OVERSTOCK
    return STATUS_IN_STOCK


def stock_status_of(product, *, reserved_map=None, suggested_min=None, suggested_max=None,
                     family_totals=None) -> str:
    """حالة المنتج الواحد — نفس ترتيب القرار الذي يطبّقه `filter_by_stock_status`.

    #25: لمنتجٍ له أبٌ (`family_id`)، إن حملت `family_totals` (من
    `family_available_map`) مجموع إخوته، الحالة تُقاس على ذلك المجموع مقابل
    حدّ **الأب** — لا رصيد هذا البراند وحده مقابل حدّه هو. `family_totals`
    اختياريةٌ وتُهمَل بصمتٍ حين لا تُمرَّر أو حين لا يحمل المنتج أباً بعد —
    فلا يتغيّر سلوك مستدعٍ قائم لم يُحدَّث ليمرّرها.
    """
    if getattr(product, "is_service", False):
        return STATUS_IN_STOCK
    family_id = getattr(product, 'family_id', None)
    if family_id and family_totals is not None and family_id in family_totals:
        available = family_totals[family_id]
        threshold_source = product.family
    else:
        available = available_of(product, reserved_map)
        threshold_source = product
    minimum = effective_min(threshold_source, suggested_min)
    maximum = effective_max(threshold_source, suggested_max)
    return _status_for(available, minimum, maximum)


def family_status_and_thresholds(tenant_id: int, *, reserved_map=None, family_totals=None):
    """حالة كل عائلةٍ (أبٍ) وحدَّاها الحاكمان معاً — من نفس الاستعلام (#35).

    استعلامان اثنان **للشركة كلّها** لا للصفّ: `family_available_map` (إن لم
    يُمرَّر `family_totals` جاهزاً من مستدعٍ يملكه أصلاً) ثم استعلامٌ واحد على
    `ProductFamily` لحدَّي كل أبٍ ظهر في المجموع. الحالة والحدّان يُشتقّان
    كلاهما من نفس الصفوف المجلوبة — سيريالايزر يعرض الحدّ الحاكم (`family_id،
    min، max`) بجانب شارة `stock_status` بلا استعلامٍ ثالث (#35: الرقم
    المعروض على صفّ المنتج كان يُؤخذ من البراند المرجعي بينما الشارة تُحاكَم
    على حدّ الأب — فيتناقض الاثنان بعد أي ضمٍّ لا يُسوّي الحدّين).

    `family_status_map` أدناه غلافٌ رقيقٌ يُبقي عقدها القديم (خريطة حالةٍ
    وحدها) لمستدعييها الحاليّين (`filter_by_stock_status`، عدّادا الداشبورد).
    """
    if family_totals is None:
        family_totals = family_available_map(tenant_id, reserved_map=reserved_map)
    if not family_totals:
        return {}, {}
    from .models import ProductFamily

    families = ProductFamily.objects.filter(
        tenant_id=tenant_id, id__in=family_totals.keys(),
    ).only('id', 'min_stock_level', 'max_stock_level')
    statuses: dict = {}
    thresholds: dict = {}
    for family in families:
        statuses[family.id] = _status_for(
            family_totals.get(family.id, ZERO),
            effective_min(family), effective_max(family),
        )
        # خامٌ لا مُشتقّ عبر `effective_min`: العرض يُبقي «—» حين لا حدّ يدويّاً
        # مضبوطاً، تماماً كحقل المنتج الخام اليوم — لا صفراً يبدّل «—» برقم.
        thresholds[family.id] = (family.min_stock_level, family.max_stock_level)
    return statuses, thresholds


def family_status_map(tenant_id: int, *, reserved_map=None, family_totals=None) -> dict:
    """حالة كل عائلةٍ (أبٍ) في الشركة — نفس سلّم `stock_status_of` مطبَّقاً
    على مجموع الإخوة مقابل حدّ الأب، لا رصيد براندٍ وحده مقابل حدّه هو (#28).

    غلافٌ رقيقٌ فوق `family_status_and_thresholds` (#35) — نفس عدد
    الاستعلامات (اثنان) ونفس العقد، يُهمِل خريطة الحدود لمن لا يحتاجها.

    يقرأها `filter_by_stock_status` (فلتر الجدول) وعدّادا الداشبورد — كلاهما
    عبر هذه الدالة وحدها، فلا يتفرّع السلّم في مكانٍ ثانٍ.
    """
    statuses, _ = family_status_and_thresholds(
        tenant_id, reserved_map=reserved_map, family_totals=family_totals,
    )
    return statuses


def available_expression(reserved_map=None):
    """تعبير ORM للمتاح — يطابق `available_of` صفّاً بصفّ.

    الحجز مشتقٌّ من الطلبيات لا عمودٌ على المنتج، فلا سبيل لطرحه في SQL إلا
    بحقنه. حُقن كـ`CASE` على معرّفات المنتجات المحجوزة وحدها (وهي قلّة: بنود
    طلبيات مؤكَّدة لم ينتهِ حجزها) بدل استعلامٍ مترابط لكل صفّ — ذاك النمط قاس
    في هذا المستودع من قبل: رصيد الطرف في القوائم كلّف 17 ثانية.
    """
    if not reserved_map:
        return F("quantity_on_hand")
    whens = [
        When(pk=pid, then=Value(_dec(qty), output_field=_QTY_FIELD))
        for pid, qty in reserved_map.items()
        if _dec(qty) > ZERO
    ]
    if not whens:
        return F("quantity_on_hand")
    return F("quantity_on_hand") - Case(
        *whens, default=Value(ZERO, output_field=_QTY_FIELD), output_field=_QTY_FIELD
    )


def annotate_available(qs, reserved_map=None):
    """يضيف عمود `available_qty` — والفلترة والترتيب يقرآن منه."""
    return qs.annotate(available_qty=available_expression(reserved_map))


def _low_q():
    return Q(available_qty__gt=0, min_stock_level__gt=0,
             available_qty__lte=F("min_stock_level"))


def _over_q():
    return (Q(available_qty__gt=0) & Q(max_stock_level__gt=0)
            & Q(available_qty__gt=F("max_stock_level")))


def _not_low_q():
    # نفيٌ مكتوبٌ صراحةً لا بـ`~Q`: العمود يقبل NULL، و`NOT (NULL > 0)` تعود
    # NULL في MySQL — أي «كاذب» — فيسقط من «متوفّر» كلُّ منتجٍ بلا حدّ أدنى،
    # وهو معظم الكتالوج. الصمتُ هنا أسوأ من الخطأ.
    return Q(min_stock_level__isnull=True) | Q(min_stock_level__lte=0) | Q(
        available_qty__gt=F("min_stock_level"))


def _not_over_q():
    return Q(max_stock_level__isnull=True) | Q(max_stock_level__lte=0) | Q(
        available_qty__lte=F("max_stock_level"))


def _row_status_q(value):
    """محمول القرار على مستوى الصفّ وحده — بلا أبٍ. نفس شروط `_status_for`
    مكتوبةً كـ`Q` بدل بايثون، لأن الفلتر يعمل في SQL."""
    if value == STATUS_IN_STOCK:
        # الخدمة «متوفّرة» دائماً — بلا مخزونٍ يُقاس.
        return Q(is_service=True) | (Q(available_qty__gt=0) & _not_low_q() & _not_over_q())
    base = ~Q(is_service=True)
    if value == STATUS_OUT_OF_STOCK:
        return base & Q(available_qty__lte=0)
    if value == STATUS_LOW:
        return base & _low_q()
    return base & _over_q()


def filter_by_stock_status(qs, value, *, reserved_map=None, family_statuses=None):
    """يقصر الـqueryset على حالةٍ واحدة. قيمةٌ مجهولة ⇒ لا فلترة.

    يقرأ الحدّ **اليدوي** وحده: المقترَح محسوبٌ في بايثون ولا يعيش في عمود، ولو
    فُلتِر به لاختلف عدّ الصفحة عن عدد الصفوف. من أراد الحدّ المقترَح فمكانه
    تقرير التجديد لا فلتر الجدول — وهو مكتوبٌ في وصف الفلتر لا مسكوتٌ عنه.

    #28: `family_statuses` (من `family_status_map`) خريطةٌ اختياريةٌ
    `{family_id: status}`. غائبةً أو فارغةً ⇒ السلوك **نفسه** حرفياً كما قبل
    هذا التاريخ (فلا يتغيّر `?view=lookup` ولا أيّ مستدعٍ قديمٍ لم يُحدَّث).
    حاضرةً: منتجٌ له أبٌ ظاهرٌ فيها يُفلتَر بحالة **أبيه** لا حالة صفّه — نفس
    قاعدة `stock_status_of` — ومنتجٌ بلا أبٍ (أو أبوه غائبٌ عن الخريطة، بيانات
    ما قبل #20) يبقى على المحمول السابق صفّاً بصفّ. «متوفّر» يُبنى من متمّم
    الحالات الشاذّة (منخفض/نافد/فائض) لا من تعداد كل عائلةٍ متوفّرة — فقائمة
    المعرّفات محدودةٌ بعدد العائلات الشاذّة لا بحجم الكتالوج.
    """
    if value not in STATUS_CHOICES:
        return qs
    qs = annotate_available(qs, reserved_map)
    if not family_statuses:
        return qs.filter(_row_status_q(value))

    family_ids = list(family_statuses.keys())
    no_family_q = ~Q(family_id__in=family_ids)
    if value == STATUS_IN_STOCK:
        abnormal_ids = [fid for fid, st in family_statuses.items() if st != STATUS_IN_STOCK]
        family_q = Q(family_id__in=family_ids) & ~Q(family_id__in=abnormal_ids)
        # الخدمة تفوز أوّلاً — كما في `stock_status_of` حرفاً بحرف. وهي منذ #20
        # تحمل أباً كسائر المنتجات، وأبوها بلا رصيدٍ أبداً (خدمةٌ لا تُخزَّن)
        # فحكمُ أبيه «نفذ». بلا هذا الطرف تسقط كل خدمةٍ من الفلترين معاً:
        # «متوفّر» يرفضها لأن أباها شاذّ، و«نفذ» يستثنيها لأنها خدمة — فلا تظهر
        # تحت أيّ حالة بينما شارتها تقول «متوفّر».
        return qs.filter(
            Q(is_service=True) | family_q | (no_family_q & _row_status_q(value))
        )
    # الخدمة تفوز أولاً كما في `stock_status_of` — لا تدخل عائلةً شاذّةً أبداً.
    qs = qs.exclude(is_service=True)
    matching_ids = [fid for fid, st in family_statuses.items() if st == value]
    family_q = Q(family_id__in=matching_ids)
    return qs.filter(family_q | (no_family_q & _row_status_q(value)))
