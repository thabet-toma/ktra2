"""محرّك FIFO لطبقات كلفة المخزون — نظير `accounting/fx_fifo.py` لكن للمخزون
(مواصفة #137، المرحلة 1: النماذج والمحرّك وحدهما، بلا التحام مع
`inventory.services.record_stock_movement` — تلك مرحلةٌ لاحقة).

كلفة كل صرفٍ مشتقّةٌ من ترتيب ورود البضاعة نفسه — لا من رقمٍ يُدخله أحد ولا
من متوسطٍ يُذيب كل الوارِدات في رقمٍ واحد. صرفٌ يستهلك طبقتين مختلفتي السعر
يحمل كلفتين مختلفتين حقيقيّتين، بدل متوسطٍ يُخفي الفرق.

`StockLayerConsumption` هو ما يجعل «الرَّدّ الدقيق» ممكناً: حين يُلغى ترحيل
حركة صرف، `restore()` تقرأ بالضبط أيّ طبقةٍ أُخذ منها وكم، فتُعيد الكمية إلى
*نفس* الطبقة — لا طبقة جديدة في آخر الرتل. موقع الطبقة في رتل FIFO (بترتيب
`layer_date, id`) محفوظٌ تماماً لأن الطبقة نفسها لم تُحذف قط، فالاستهلاك
اللاحق (بعد الرَّدّ ثم إعادة الترحيل) يأخذ من نفس الطبقات بنفس الترتيب — وهذا
بالضبط ما يجعل إلغاء الترحيل يُرجع المخزون لحالته قبلُ حرفياً لا تقريبياً.

الكمية غير المغطّاة عند نفاد الطبقات (مخزون سالب) مسؤولية مرحلةٍ لاحقة —
`consume()` هنا لا ترمي استثناءً ولا تخترع كلفة، بل تُرجع ما استُهلك فعلاً
والباقي غير المغطّى صراحةً.
"""
import datetime
from decimal import Decimal
from typing import NamedTuple

from django.db import transaction
from django.db.models import DecimalField, F, Sum
from django.db.models.functions import Coalesce

from .models import Product, StockLayer, StockLayerConsumption, StockMovement

Q4 = Decimal("0.0001")

#: تاريخُ الطبقة الافتتاحيّة — سابقٌ لأيّ تاريخٍ حقيقيّ في المستودع، فتقع أوّلَ
#: الرتل دائماً بلا مقارنةٍ بتواريخ الطبقات الأخرى ولا استعلامٍ عنها.
OPENING_LAYER_DATE = datetime.date(1900, 1, 1)


def _d(v) -> Decimal:
    return Decimal(str(v if v is not None else 0))


class ConsumeResult(NamedTuple):
    """ناتج `consume()`: الكلفة المُستهلَكة فعلاً + ما تعذّر تغطيته من الطلب.

    `uncovered_qty > 0` يعني أن الطبقات المفتوحة نفدت قبل تغطية الكمية
    المطلوبة كاملةً (حالة المخزون السالب) — مسؤولية المرحلة اللاحقة، لا
    استثناءً يُرمى هنا.
    """

    cost: Decimal
    uncovered_qty: Decimal


def create_layer(*, movement: StockMovement, quantity, unit_cost, provisional: bool = False) -> StockLayer:
    """ينشئ طبقة كلفة من حركة مخزون واردة (IN/ADJUST_IN/RETURN_IN...).

    `layer_date` و`warehouse` يُشتقّان من الحركة نفسها — الطبقة تسجّل نفس
    لحظة الورود ونفس المستودع الذي وثّقته الحركة، بلا تكرار إدخال.
    """
    quantity = _d(quantity).quantize(Q4)
    unit_cost = _d(unit_cost).quantize(Q4)
    with transaction.atomic():
        return StockLayer.objects.create(
            tenant_id=movement.tenant_id,
            product_id=movement.product_id,
            warehouse_id=movement.warehouse_id,
            layer_date=movement.movement_date,
            original_qty=quantity,
            remaining_qty=quantity,
            unit_cost=unit_cost,
            source_movement=movement,
            is_provisional=provisional,
        )



def backfill_opening_layer(*, tenant_id: int, product_id: int, quantity_on_hand, avg_cost):
    """يرأب فجوةَ «رصيدٌ موجبٌ بلا طبقاتٍ تغطّيه» بطبقةٍ افتتاحيّة، ويُرجعها
    (أو `None` إن لم تكن ثمّة فجوة).

    كلُّ صنفٍ في قاعدةٍ قائمة يحمل رصيداً وكلفةً و**صفرَ طبقات** — الطبقاتُ
    اختراعُ #137 نفسِها. فبلا هذا الرأب تعمل `consume` على رتلٍ فارغ فتُرجع
    الكميّةَ كلَّها «غيرَ مغطّاة»، فتُنشأ طبقةٌ **مؤقّتة** تُستهلَك فوراً،
    فتبقى `remaining_qty` صفراً و`derived_avg_cost` تقسم صفراً على صفر:
    **أوّلُ بيعةٍ لكلّ صنفٍ تُصفّر كلفته**، وكلُّ شراءٍ لاحقٍ يرى «معلَّقاً»
    فيُطلِع قيدَ فرقٍ لا مبرّرَ له.

    الكلفةُ هي `avg_cost` الجارية، فالرأبُ **محايدٌ على الميزانية بالبناء**:
    كميّة × متوسّط = القيمةُ الدفتريّة المسجَّلة نفسُها، بلا قيدِ تسويةٍ ولا
    حركةٍ في الميزان (خيارُ المالك في #135). والتاريخُ `OPENING_LAYER_DATE`
    فتُستهلَك أوّلاً: بضاعةُ ما قبل البيانات بالتعريف، وأولى بأن تخرج كلفتُها
    المشكوكة من الدفاتر سريعاً.

    و`source_movement=None` عمداً — لا حركةَ ورودٍ أنتجتها؛ وهو أيضاً ما يميّزها
    فلا تُنشأ مرّتين (الفجوةُ تُغلَق فلا يبقى ما يُرأب). و`is_provisional=False`:
    ليست تخميناً عن بضاعةٍ لم تصل، بل بضاعةٌ موجودةٌ يقول الدفترُ إنّنا نملكها.

    يُنادى داخل قفلِ صفّ المنتج في `record_stock_movement` — لا يقفل بنفسه.
    """
    quantity_on_hand = _d(quantity_on_hand)
    if quantity_on_hand <= 0:
        return None
    covered = sum(
        (
            layer.remaining_qty
            for layer in StockLayer.objects.filter(
                tenant_id=tenant_id, product_id=product_id, remaining_qty__gt=0,
            ).only("remaining_qty")
        ),
        Decimal("0"),
    )
    shortfall = (quantity_on_hand - covered).quantize(Q4)
    if shortfall <= 0:
        return None
    return StockLayer.objects.create(
        tenant_id=tenant_id,
        product_id=product_id,
        warehouse_id=None,
        layer_date=OPENING_LAYER_DATE,
        original_qty=shortfall,
        remaining_qty=shortfall,
        unit_cost=_d(avg_cost).quantize(Q4),
        source_movement=None,
        is_provisional=False,
    )

def consume(*, movement: StockMovement, quantity) -> ConsumeResult:
    """يستهلك `quantity` بترتيب FIFO (الأقدم أوّلاً) من طبقات (الشركة، المنتج)
    المفتوحة، وينشئ صفّ `StockLayerConsumption` لكل طبقةٍ أُخذ منها.

    محصورٌ بالشركة والمنتج معاً (لا بالمستودع — انظر docstring `StockLayer`).
    يقفل صفوف الطبقات (`select_for_update`) كي لا يتجاوز استهلاكان متزامنان
    على نفس المنتج الرصيد الفعلي.

    عند نفاد الطبقات قبل تغطية الكمية كاملةً: تُرجع الكلفة لما استُهلك فعلاً
    والكمية غير المغطّاة > صفر — بلا استثناء، فتلك حالة المخزون السالب
    ومسؤولية طبقةٍ مؤقّتة (`is_provisional`) في مرحلةٍ لاحقة.
    """
    quantity = _d(quantity).quantize(Q4)
    if quantity <= 0:
        return ConsumeResult(cost=Decimal("0"), uncovered_qty=Decimal("0"))

    with transaction.atomic():
        layers = list(
            StockLayer.objects.select_for_update()
            .filter(tenant_id=movement.tenant_id, product_id=movement.product_id, remaining_qty__gt=0)
            .order_by("layer_date", "id")
        )
        remaining = quantity
        total_cost = Decimal("0")
        for layer in layers:
            if remaining <= 0:
                break
            take = min(layer.remaining_qty, remaining)
            if take <= 0:
                continue
            layer.remaining_qty = (layer.remaining_qty - take).quantize(Q4)
            layer.save(update_fields=["remaining_qty"])
            StockLayerConsumption.objects.create(
                tenant_id=movement.tenant_id,
                movement=movement,
                layer=layer,
                quantity=take,
                unit_cost=layer.unit_cost,
            )
            total_cost += take * layer.unit_cost
            remaining -= take

        uncovered = remaining.quantize(Q4) if remaining > 0 else Decimal("0")
        return ConsumeResult(cost=total_cost.quantize(Q4), uncovered_qty=uncovered)


class ReconcileDetail(NamedTuple):
    """تسويةٌ واحدة على طبقةٍ مؤقّتة واحدة — جزءٌ من ناتج `reconcile_provisional()`.

    `provisional_unit_cost` هي الكلفة المخمَّنة التي حُمِّلت وقت البيع على
    المخزون السالب؛ الفرق بينها وبين الكلفة الحقيقية (التي يعرفها المستدعي)
    هو أساس قيد الفرق — هذه الدالة لا تحسبه، فقط تُرجع التفصيل الخام.
    """

    layer_id: int
    filled_qty: Decimal
    provisional_unit_cost: Decimal


class ReconcileResult(NamedTuple):
    """ناتج `reconcile_provisional()`: الطبقة الجديدة (بكميتها المتبقية بعد
    سدّ المعلَّق) + إجمالي ما سُدّ + تفصيل كل طبقةٍ مؤقّتة شارَكَت في السدّ."""

    new_layer: StockLayer
    filled_qty: Decimal
    details: list


def reconcile_provisional(*, movement: StockMovement, quantity, unit_cost) -> ReconcileResult:
    """يسوّي وارِداً جديداً (`quantity` بكلفة `unit_cost`) مقابل الطبقات المؤقّتة
    (`is_provisional=True`) المعلَّقة لنفس (الشركة، المنتج) — الأقدم فأقدم،
    نفس ترتيب رتل FIFO (`layer_date, id`).

    المعلَّق لكل طبقة = `original_qty - reconciled_qty` (يسمح بتسويةٍ جزئية
    عبر أكثر من وارِدٍ). يُسدّ منها ما تسمح به `quantity` الواردة، وتُزاد
    `reconciled_qty` لكل طبقةٍ شاركت بمقدار ما أُخذ منها.

    **الطبقة الجديدة تُنشأ بـ`original_qty = quantity`** (ما وصل فعلاً —
    تاريخٌ صادق) **و`remaining_qty = quantity - filled`**: الجزء الذي سدّ
    حفرةً بيعت أصلاً على مخزونٍ سالب لا يبقى متاحاً لصرفٍ جديد — هذا بالضبط
    ما يُصلح ثابت Σ`remaining_qty` == `Product.quantity_on_hand` حين يصل
    واردٌ بعد بيعٍ على مخزون سالب (العطب الذي وثّقته مواصفة #137).

    لا تبني قيداً محاسبياً هنا — محرّكٌ حسابيٌّ بحت؛ المستدعي
    (`inventory.services.record_stock_movement`) يبني قيد الفرق من
    `details` المُرجَعة وكلفة `unit_cost` الحقيقية.
    """
    quantity = _d(quantity).quantize(Q4)
    unit_cost = _d(unit_cost).quantize(Q4)

    with transaction.atomic():
        provisional_layers = list(
            StockLayer.objects.select_for_update()
            .filter(
                tenant_id=movement.tenant_id,
                product_id=movement.product_id,
                is_provisional=True,
            )
            .filter(reconciled_qty__lt=F("original_qty"))
            .order_by("layer_date", "id")
        )
        remaining = quantity
        details: list[ReconcileDetail] = []
        for layer in provisional_layers:
            if remaining <= 0:
                break
            pending = (layer.original_qty - layer.reconciled_qty).quantize(Q4)
            if pending <= 0:
                continue
            filled = min(pending, remaining)
            layer.reconciled_qty = (layer.reconciled_qty + filled).quantize(Q4)
            layer.save(update_fields=["reconciled_qty"])
            details.append(
                ReconcileDetail(
                    layer_id=layer.pk,
                    filled_qty=filled,
                    provisional_unit_cost=layer.unit_cost,
                )
            )
            remaining -= filled

        filled_total = (quantity - remaining).quantize(Q4)
        new_layer = StockLayer.objects.create(
            tenant_id=movement.tenant_id,
            product_id=movement.product_id,
            warehouse_id=movement.warehouse_id,
            layer_date=movement.movement_date,
            original_qty=quantity,
            remaining_qty=(quantity - filled_total).quantize(Q4),
            unit_cost=unit_cost,
            source_movement=movement,
            is_provisional=False,
        )
        return ReconcileResult(new_layer=new_layer, filled_qty=filled_total, details=details)


def pending_provisional_layers(*, tenant_id: int) -> list:
    """تقرير «طبقاتٌ مؤقّتة لم تُسوَّ» لشركةٍ ما — استعلامٌ واحد محصورٌ بالشركة.

    تُرجع الطبقات حيث `is_provisional=True` و`reconciled_qty < original_qty`
    (معلَّقٌ جزئياً أو كلياً)، مرتّبةً بترتيب رتل FIFO (الأقدم أوّلاً — الأكثر
    إلحاحاً غالباً). **بلا حذفٍ تلقائيّ ولا عمرٍ أقصى** — قرارٌ محسوم عمداً:
    الإخفاء يُسكِت عطباً في البيانات، وطبقةٌ معلَّقةٌ منذ شهورٍ هي علامة بيعٍ
    على صنفٍ لم يُستلَم قط، لا ضجيجاً يُنظَّف.
    """
    rows = (
        StockLayer.objects.filter(
            tenant_id=tenant_id, is_provisional=True,
        )
        .filter(reconciled_qty__lt=F("original_qty"))
        .select_related("product")
        .order_by("layer_date", "id")
    )
    return [
        {
            "layer_id": layer.pk,
            "product_id": layer.product_id,
            "product_sku": layer.product.sku,
            "pending_qty": (layer.original_qty - layer.reconciled_qty).quantize(Q4),
            "provisional_unit_cost": layer.unit_cost,
            "layer_date": layer.layer_date,
        }
        for layer in rows
    ]


def restore(movement: StockMovement) -> int:
    """يعكس استهلاك حركةٍ بعينها: يقرأ صفوف `StockLayerConsumption` الخاصة بها،
    يُعيد `quantity` إلى `remaining_qty` لكل طبقة، ثم يحذف صفوف الاستهلاك.

    هذا هو ما يجعل إلغاء الترحيل يُرجع المخزون لحالته قبلُ بالضبط: الطبقة
    نفسها (بمعرّفها وتاريخها) لم تُحذف قط، فموقعها في رتل FIFO محفوظ — إعادة
    الترحيل لاحقاً تستهلك من نفس الطبقات بنفس الترتيب تماماً.

    يُرجع عدد صفوف الاستهلاك التي أُعيدت (وحُذفت).
    """
    with transaction.atomic():
        consumptions = list(
            StockLayerConsumption.objects.select_for_update()
            .filter(movement=movement)
            .select_related("layer")
        )
        if not consumptions:
            return 0
        layer_ids = [c.layer_id for c in consumptions]
        # قفل الطبقات نفسها قبل تعديلها — تناظر القفل في consume().
        locked_layers = {
            layer.pk: layer
            for layer in StockLayer.objects.select_for_update().filter(pk__in=layer_ids)
        }
        for c in consumptions:
            layer = locked_layers[c.layer_id]
            layer.remaining_qty = (layer.remaining_qty + c.quantity).quantize(Q4)
            layer.save(update_fields=["remaining_qty"])
        count = len(consumptions)
        StockLayerConsumption.objects.filter(
            pk__in=[c.pk for c in consumptions]
        ).delete()
        return count


def open_layers_value(*, tenant_id: int, product_ids) -> dict:
    """قيمة الطبقات المفتوحة لكل منتج (Σ remaining_qty × unit_cost) — استعلامٌ
    تجميعيٌّ واحد لكل المنتجات المُمرَّرة معاً (نمط `sales_cogs_map`).

    قائمة فارغة ⇒ `{}` بلا استعلام.
    """
    ids = list(product_ids or [])
    if not ids:
        return {}
    value_expr = Coalesce(
        Sum(F("remaining_qty") * F("unit_cost")),
        Decimal("0"),
        output_field=DecimalField(max_digits=18, decimal_places=4),
    )
    rows = (
        StockLayer.objects.filter(
            tenant_id=tenant_id, product_id__in=ids, remaining_qty__gt=0,
        )
        .values("product_id")
        .annotate(value=value_expr)
    )
    return {row["product_id"]: _d(row["value"]).quantize(Q4) for row in rows}


def open_layers_quantity(*, tenant_id: int, product_ids) -> dict:
    """كمية الطبقات المفتوحة لكل منتج (Σ remaining_qty) — استعلامٌ تجميعيٌّ
    واحد لكل المنتجات المُمرَّرة معاً. قائمة فارغة ⇒ `{}` بلا استعلام."""
    ids = list(product_ids or [])
    if not ids:
        return {}
    qty_expr = Coalesce(
        Sum("remaining_qty"),
        Decimal("0"),
        output_field=DecimalField(max_digits=18, decimal_places=4),
    )
    rows = (
        StockLayer.objects.filter(
            tenant_id=tenant_id, product_id__in=ids, remaining_qty__gt=0,
        )
        .values("product_id")
        .annotate(qty=qty_expr)
    )
    return {row["product_id"]: _d(row["qty"]).quantize(Q4) for row in rows}


def derived_avg_cost(*, tenant_id: int, product_id: int) -> Decimal:
    """متوسط الكلفة المشتقّ من الطبقات المفتوحة (قيمتها ÷ كميّتها). صفرٌ عند
    صفر كمية — بلا قسمة على صفر.

    **استعلامٌ واحد** يجمع القيمة والكمية معاً لا نداءان لـ`open_layers_value`
    و`open_layers_quantity`: تُنادى هذه الدالّة مرّةً في كلّ حركة مخزون
    (`record_stock_movement`)، ففاتورةٌ بخمسين بنداً كانت تدفع خمسين استعلاماً
    زائداً بلا مقابل.
    """
    row = (
        StockLayer.objects.filter(
            tenant_id=tenant_id, product_id=product_id, remaining_qty__gt=0,
        )
        .aggregate(
            qty=Sum("remaining_qty"),
            value=Sum(
                F("remaining_qty") * F("unit_cost"),
                output_field=DecimalField(max_digits=18, decimal_places=4),
            ),
        )
    )
    qty = _d(row["qty"])
    if qty == 0:
        return Decimal("0")
    return (_d(row["value"]) / qty).quantize(Q4)
