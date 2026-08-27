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


def stock_status_of(product, *, reserved_map=None, suggested_min=None, suggested_max=None) -> str:
    """حالة المنتج الواحد — نفس ترتيب القرار الذي يطبّقه `filter_by_stock_status`."""
    if getattr(product, "is_service", False):
        return STATUS_IN_STOCK
    available = available_of(product, reserved_map)
    if available <= ZERO:
        return STATUS_OUT_OF_STOCK
    minimum = effective_min(product, suggested_min)
    if minimum > ZERO and available <= minimum:
        return STATUS_LOW
    maximum = effective_max(product, suggested_max)
    if maximum > ZERO and available > maximum:
        return STATUS_OVERSTOCK
    return STATUS_IN_STOCK


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


def filter_by_stock_status(qs, value, *, reserved_map=None):
    """يقصر الـqueryset على حالةٍ واحدة. قيمةٌ مجهولة ⇒ لا فلترة.

    يقرأ الحدّ **اليدوي** وحده: المقترَح محسوبٌ في بايثون ولا يعيش في عمود، ولو
    فُلتِر به لاختلف عدّ الصفحة عن عدد الصفوف. من أراد الحدّ المقترَح فمكانه
    تقرير التجديد لا فلتر الجدول — وهو مكتوبٌ في وصف الفلتر لا مسكوتٌ عنه.
    """
    if value not in STATUS_CHOICES:
        return qs
    qs = annotate_available(qs, reserved_map)
    if value == STATUS_IN_STOCK:
        # الخدمة «متوفّرة» دائماً — بلا مخزونٍ يُقاس.
        return qs.filter(
            Q(is_service=True)
            | (Q(available_qty__gt=0) & _not_low_q() & _not_over_q())
        )
    qs = qs.exclude(is_service=True)
    if value == STATUS_OUT_OF_STOCK:
        return qs.filter(available_qty__lte=0)
    if value == STATUS_LOW:
        return qs.filter(_low_q())
    return qs.filter(_over_q())
