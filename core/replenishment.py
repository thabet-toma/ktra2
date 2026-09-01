"""T-REORDER: محرّك التجديد — «ماذا أطلب، وكم، ومتى» محسوباً من المبيعات.

المشكلة التي يحلّها: `min_stock_level` رقمٌ يدويّ على ألف وخمسمئة منتج، فبقي
فارغاً في معظمها — وتقرير «تحت حدّ الطلب» يشترطه، فكان يصمت عن الكتالوج كلّه
تقريباً. والرقم اليدوي، حين يُكتب، يُكتب مرّةً ولا يُراجَع: منتجٌ كان يبيع خمسةً
في الشهر وصار يبيع خمسين يبقى حدّه خمسةً حتى ينفد.

فالحدّ يُشتقّ هنا من ثلاثة أرقام: **كم يُصرَف يومياً** (من حركة المخزون)،
**كم يستغرق التوريد** (من فارق تاريخ الطلبية إلى تاريخ استلامها)، و**كم يتقلّب
كلاهما** (مخزون الأمان). والاقتراح **يُعرَض ولا يُكتب**: `min_stock_level`
اليدوي يبقى هو الحاكم متى وُجد (`inventory/stock_status.py` — `effective_min`)،
والكتابة فعلٌ صريح من المستخدم (`apply-replenishment`).

## المعادلات

    معدّل الصرف اليومي (ADU) = صافي الصادر (OUT − RETURN_IN) ÷ أيام السجل
    ذروة الصرف اليومي        = أعلى صافٍ **أسبوعي** ÷ 7
    مخزون الأمان             = (الذروة × أطول مهلة) − (ADU × المهلة)
                               وبحدٍّ أدنى ADU × المهلة × 0.5  (قاعدة الـ50%)
    الحدّ الأدنى المقترَح     = ⌈ADU × المهلة + مخزون الأمان⌉
    الحدّ الأقصى المقترَح     = ⌈الأدنى + ADU × مدة المراجعة⌉
    الكمية المقترح طلبها     = الأقصى − (المتاح + قيد الطلب)   [لا أقلّ من صفر]

**الذروة أسبوعية لا يومية** عمداً: يومٌ واحد بِيعت فيه شحنةٌ كاملة يجعل كلّ منتجٍ
يبدو متقلّباً، فيتضخّم مخزون الأمان على الكتالوج كلّه. الأسبوع يمسك الموسمية بلا
أن يجعل شذوذاً قاعدة.

**السجل القصير لا يُقترَح له.** منتجٌ عمرُه في المخزن خمسة أيام باع عشرة ليس
معدّله يومان — هو منتجٌ لا نعرفه بعد. دون `MIN_HISTORY_DAYS` يعود الصفّ بلا
اقتراح وبسببٍ مكتوب، لا بصفرٍ صامت يقرأه المستخدم «لا تطلب».

## البُعد الذي يميّز هذا المحرّك: النوع

المنتجات هنا موديلاتٌ متبادلة: «205/65/16» موديل قديم و«205/65/16» موديل جديد
شيءٌ واحد أمام الزبون. فحسابُ كل SKU على حدة يقول «اطلب القديم — نفد» بينما
الجديد على الرفّ بأربعين. لذلك يحمل كل صفٍّ، إلى جانب أرقامه، أرقامَ **نوعه**
(`inventory/services.py` — `product_group_key`)، ويُحسم الإلحاح بهما معاً:

    عاجل   — المنتج تحت حدّه **والنوع كلّه** تحت حدّ النوع ⇒ اطلب
    مؤجَّل  — المنتج تحت حدّه والنوع مغطّى بموديل آخر ⇒ بِعِ البديل ولا تطلب
    راكد   — رصيدٌ موجب وبلا مبيعات في النافذة ⇒ لا يُطلَب أبداً

وأرقام النوع مجاميعُ أرقام أفراده لا حسابٌ ثانٍ عليها — كي يُفتَح صفّ النوع على
أفراده فيساوي مجموعُهم رقمَه (`docs/modules/core.md` — 6.1.1). رقمٌ متحفّظٌ
يُراجَع خيرٌ من رقمٍ أدقّ لا يُراجَع.

**لماذا يسكن هنا لا في `inventory/`:** الحساب يحتاج ثلاثة apps معاً — حركةَ
المخزون (`inventory`)، والمحجوزَ من طلبيات البيع (`sales.services`)، ومهلةَ
التوريد من طلبيات الشراء (`logistics.models`) — و`.importlinter` يمنع `inventory`
من استيراد `sales` أو `logistics` (عقد «الاتجاه المعكوس»). و`core` هي الطبقة
المشتركة التي يصحّ لها أن تقرأ من الجميع، وفيها تسكن أصلاً كل قراءةٍ عابرة
للـapps (`core/reports/`، `core/dashboard_api.py`، `core/pricing.py`). قاعدةُ
**حالة** المخزون وحدها بقيت في `inventory/stock_status.py` لأنها لا تحتاج غيره.

الحساب كلّه **قراءةٌ محضة**. النقطة الوحيدة التي تكتب هي
`apply_suggested_levels` أسفل الملف، وهي لا تُستدعى إلا بفعلٍ صريح من
المستخدم — ولا تمسّ حركةَ مخزون ولا قيداً بحال.

## السلسلة الأسبوعية وهولت (#32)

رقما الصنف الحيّان — البيع الأسبوعي الحالي (`level`) والاتجاه (`trend`) —
يُشتقّان بهولت (`holt_forecast`) من نفس حركة المخزون، ويُخزَّنان في
`inventory.ProductDemandForecast` عبر
`python manage.py recompute_demand_forecast` — لا صفحةٌ تحسبهما عند الفتح:
هولت متسلسل، وإعادة تشغيل السلسلة كاملةً لكل صنفٍ في كل فتحة تُعلّق الصفحة.

**كل تشغيلٍ يعيد حساب السلسلة كاملةً من حركة المخزون الخام — لا يخطو حالةً
محفوظة خطوةً واحدة للأمام.** المالك وصف التحديث تدريجياً («الجديد = ربع
الأسبوع المنتهي + ثلاثة أرباع القديم») وهذا بعينه ما تفعله المعادلة
الاستقرائية؛ إعادة تشغيلها من الصفر تعطي **نفس** الناتج تماماً (هولت دالّةٌ لا
حالة) وتكسب مجاناً: التعافي الذاتي (حركةٌ بتاريخٍ رجعي أو تصحيحٌ أو أسبوعٌ
فائتٌ يُصحَّح نفسه في التشغيل التالي بلا تدخّل)، ومعاودة الاستدعاء بلا أثر
(تشغيلان في نفس الأسبوع ⇒ نفس الأرقام بالضبط). والثمن — إعادة قراءة النافذة
كاملةً بدل حالة صغيرة — لا يُحَسّ: استعلامان مجمَّعان للشركة كلّها (نمط
`_demand_profiles` أعلاه بحرفيّته)، لا استعلامٌ لكل صنف.
"""
from __future__ import annotations

import datetime
import logging
import statistics
from decimal import Decimal, ROUND_CEILING

from django.db.models import Min, Q, Sum
from django.db.models.functions import TruncWeek

from inventory.stock_status import (
    STATUS_LOW,
    STATUS_OUT_OF_STOCK,
    available_of,
    effective_min,
    family_available_map,
    reserved_of,
    stock_status_of,
)

logger = logging.getLogger("core.replenishment")

ZERO = Decimal("0")

#: أقل عمرٍ في المخزن يُبنى عليه اقتراح. أقصر منه = منتجٌ لا نعرفه بعد.
MIN_HISTORY_DAYS = 14
#: أقل عدد عيّنات مهلة توريد يُعتدّ بوسيطها على مستوى المنتج/المورّد.
MIN_LEAD_SAMPLES = 2
#: نسبة أطول مهلة إلى المهلة المعتادة حين لا يُرصَد تباينٌ فعلي.
LEAD_MAX_FACTOR = Decimal("1.5")
#: قاعدة الـ50%: أرضية مخزون الأمان حين تكون البيانات فقيرة.
SAFETY_FLOOR_RATIO = Decimal("0.5")

URGENCY_URGENT = "urgent"
URGENCY_DEFERRED = "deferred"
URGENCY_DEAD = "dead"
URGENCY_OK = "ok"

URGENCY_LABELS = {
    URGENCY_URGENT: "عاجل",
    URGENCY_DEFERRED: "مؤجَّل",
    URGENCY_DEAD: "راكد",
    URGENCY_OK: "—",
}

#: ترتيب العرض: الأشدّ أوّلاً.
URGENCY_ORDER = {URGENCY_URGENT: 0, URGENCY_DEFERRED: 1, URGENCY_DEAD: 2, URGENCY_OK: 3}

#: تسمية وضع الصنف — نسخةٌ محلّية من `Product.REORDER_MODE_CHOICES` كي لا
#: يستورد هذا الملف نماذج `inventory` عند التحميل (نمط الاستيراد المحلّي أعلاه).
MODE_LABELS = {"manual": "يدوي", "auto": "تلقائي"}

REASON_SHORT_HISTORY = "سجل غير كافٍ — المنتج حديث في المخزن"
REASON_NO_SALES = "بلا مبيعات في النافذة"
#: #33: صنفٌ على `auto` بلا صفٍّ في `ProductDemandForecast` — الأمر لم يُشغَّل
#: بعد على هذا المنتج (أو ليس له حركة مخزون على الإطلاق فلا يدخل سلسلته أصلاً).
#: نفس فلسفة `REASON_SHORT_HISTORY`: سببٌ مكتوب لا صفرٌ صامت.
REASON_NO_FORECAST = "لا تنبّؤ محفوظ — لم يُشغَّل أمر الحساب بعد على هذا المنتج"

TREND_UP = "طالع"
TREND_DOWN = "نازل"
TREND_FLAT = "ثابت"

_OUT = "OUT"
_RETURN_IN = "RETURN_IN"
_PURCHASE_REF = "PURCHASE_INVOICE"


def _dec(value) -> Decimal:
    if value is None or value == "":
        return ZERO
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _ceil(value: Decimal) -> int:
    if value <= ZERO:
        return 0
    return int(value.quantize(Decimal("1"), rounding=ROUND_CEILING))


class ReplenishmentParams:
    """بارامترات الشركة — من `logistics.PurchaseSettings`، وإلا الافتراضات."""

    __slots__ = ("window_days", "default_lead_time_days", "review_period_days")

    def __init__(self, window_days=90, default_lead_time_days=14, review_period_days=30):
        self.window_days = max(int(window_days or 90), 7)
        self.default_lead_time_days = max(int(default_lead_time_days or 14), 1)
        self.review_period_days = max(int(review_period_days or 30), 1)


def replenishment_params(tenant_id: int) -> ReplenishmentParams:
    from logistics.models import PurchaseSettings

    row = PurchaseSettings.objects.filter(tenant_id=tenant_id).values(
        "replenishment_window_days", "default_lead_time_days", "review_period_days",
    ).first()
    if not row:
        return ReplenishmentParams()
    return ReplenishmentParams(
        row["replenishment_window_days"],
        row["default_lead_time_days"],
        row["review_period_days"],
    )


def suggest_levels(*, adu: Decimal, adu_peak: Decimal, lead_days: Decimal,
                   lead_max_days: Decimal, review_days: int) -> dict:
    """المعادلات وحدها — بلا استعلام، فتُختبر بالورقة والقلم.

    تُطبَّق كما هي على المنتج الواحد وعلى النوع المجمَّع؛ نفس الدالّة لا نسختان.
    """
    cycle = adu * lead_days
    peak_cycle = adu_peak * lead_max_days
    safety = peak_cycle - cycle
    floor = cycle * SAFETY_FLOOR_RATIO
    if safety < floor:
        safety = floor
    if safety < ZERO:
        safety = ZERO
    minimum = cycle + safety
    maximum = minimum + adu * Decimal(review_days)
    return {
        "safety_stock": safety,
        "suggested_min": _ceil(minimum),
        "suggested_max": _ceil(maximum),
    }


# ── جمع البيانات: أربعة استعلامات مجمَّعة، لا استعلامَ لكل منتج ──────────

def _demand_profiles(tenant_id: int, product_ids, window_start, today) -> dict:
    """لكل منتج: صافي الصرف في النافذة، وذروته الأسبوعية، وأوّل حركةٍ له.

    استعلامان اثنان مهما بلغ عدد المنتجات — النمط المتّبع في هذا المستودع
    (`inventory/views.py` — تجميعات `purchased_qty`/`sold_qty_90d`).
    """
    from inventory.models import StockMovement

    base = StockMovement.objects.filter(tenant_id=tenant_id)
    if product_ids is not None:
        base = base.filter(product_id__in=product_ids)

    weekly = (
        base.filter(
            movement_date__gte=window_start,
            movement_date__lte=today,
            movement_type__in=(_OUT, _RETURN_IN),
        )
        .annotate(week=TruncWeek("movement_date"))
        .values("product_id", "week")
        .annotate(
            out_qty=Sum("quantity", filter=Q(movement_type=_OUT)),
            ret_qty=Sum("quantity", filter=Q(movement_type=_RETURN_IN)),
        )
    )
    profiles: dict[int, dict] = {}
    for row in weekly:
        net = _dec(row["out_qty"]) - _dec(row["ret_qty"])
        entry = profiles.setdefault(
            row["product_id"], {"net": ZERO, "peak_week": ZERO, "first_movement": None},
        )
        entry["net"] += net
        if net > entry["peak_week"]:
            entry["peak_week"] = net

    firsts = base.values("product_id").annotate(first=Min("movement_date"))
    for row in firsts:
        entry = profiles.setdefault(
            row["product_id"], {"net": ZERO, "peak_week": ZERO, "first_movement": None},
        )
        entry["first_movement"] = row["first"]
    return profiles


# ── السلسلة الأسبوعية وتنبّؤ هولت: T-REORDER #32 ─────────────────────────

#: معاملا هولت — ثابتان في هذه التذكرة؛ تحويلهما لمقبضين في الإعدادات مؤجَّل
#: لتذكرة لاحقة (#34) فلا يُستبقان هنا.
HOLT_ALPHA = Decimal("0.25")
HOLT_BETA = Decimal("0.15")
#: نافذة السلسلة الأسبوعية — ستة أشهر. منفصلة عمداً عن `window_days` أعلاه
#: (تلك تقيس معدّلاً فيكفيها تسعون يوماً، وهذه تحتاج سلسلةً طويلة كي يستقرّ
#: الاتجاه — ط11 على الخريطة).
FORECAST_HISTORY_WEEKS = 26
#: أقلّ من ستة أسابيع مكتملة: بلا اتجاه (ط1) — المستوى متوسط آخر أسبوعين فقط.
MIN_TREND_HISTORY_WEEKS = 6
#: أقلّ عدد أخطاء توقّع لاعتماد `MAD` رقماً — عيّنة من خطأٍ واحد أو اثنين ضجيج.
MIN_MAD_SAMPLES = 4

# ── #33: المسار التلقائي — من المستوى/الاتجاه المخزَّنين إلى حدٍّ وكمية ────
#: عاملُ تحويل الخطأ المطلق (MAD) إلى انحرافٍ معياري تقديري (ط7 على الخريطة).
MAD_TO_SIGMA = Decimal("1.25")
#: عامل ثقةٍ (z) يضرب σ لإنتاج مخزون الأمان — ثابتٌ في هذه التذكرة؛ تحويله
#: لمقبضٍ في الإعدادات مهمّة #34، فلا يُستبَق هنا.
SAFETY_Z_FACTOR = Decimal("1.28")
#: سقف الاتجاه الصاعد: الزيادة الأسبوعية لا تتجاوز المستوى ÷ 3 (ط8) — النازل
#: بلا سقف عمداً، فخطأ المبالغة صعوداً يكلّف بضاعةً راكدة والنازل يصحّحه السوق.
TREND_CAP_DIVISOR = Decimal("3")


def holt_forecast(weekly_demand: list) -> dict:
    """هولت (تنعيم أسّي مزدوج) على سلسلة صافي طلبٍ أسبوعية — دالّة صافية بلا
    استعلام، فتُختبر بالورقة والقلم كما `suggest_levels` أعلاه.

    `weekly_demand`: قائمة Decimal الأقدم أوّلاً، **مكتملة الأسابيع** (أسبوع
    الصفر عنصرٌ لا فجوة) وخاليةً من الأسبوع الجاري غير المكتمل — هذا شرط
    المستدعي (`_weekly_series` أسفله) لا هذه الدالّة.

        L_t = α·y_t + (1−α)·(L_{t−1} + T_{t−1})      α = 0.25
        T_t = β·(L_t − L_{t−1}) + (1−β)·T_{t−1}       β = 0.15

    **التهيئة**: `L` يبدأ متوسط أوّل أسبوعين (الأسبوع الوحيد إن كان هذا كل
    السجلّ)، و`T` يبدأ صفراً. **أقلّ من ست أسابيع مكتملة**: لا اتجاه — المستوى
    المُعاد متوسط **آخر** أسبوعين بدل ناتج الاستقراء (ط1: «صنفٌ أقلّ من ست
    أسابيع → آخر أسبوعين مؤشّراً وبلا اتجاه»).

    **`MAD`**: متوسط القيمة المطلقة لخطأ توقّع أسبوعٍ واحدٍ قدماً —
    `|الفعلي_t − (المستوى_{t−1} + الاتجاه_{t−1})|` — على الأسابيع التي سبقها
    توقّعٌ فعلاً؛ خطأ **التوقّع** لا انحرافٌ عن متوسط، لأنه مدخل مخزون الأمان
    (ط7/#33). غائبٌ دون أربعة أسابيع من هذه الأخطاء.
    """
    n = len(weekly_demand)
    if n == 0:
        return {"level": ZERO, "trend": ZERO, "weeks_observed": 0, "mad": None}
    if n == 1:
        return {"level": weekly_demand[0], "trend": ZERO, "weeks_observed": 1, "mad": None}

    level = (weekly_demand[0] + weekly_demand[1]) / Decimal("2")
    trend = ZERO
    errors: list = []
    for actual in weekly_demand[2:]:
        forecast = level + trend
        errors.append(abs(actual - forecast))
        new_level = HOLT_ALPHA * actual + (Decimal("1") - HOLT_ALPHA) * (level + trend)
        trend = HOLT_BETA * (new_level - level) + (Decimal("1") - HOLT_BETA) * trend
        level = new_level

    if n < MIN_TREND_HISTORY_WEEKS:
        # الاستقراء يُحسب دائماً (يغذّي أخطاء MAD أعلاه) لكن لا يُعتمَد ناتجه
        # هنا — قاعدة السجل القصير في ط1 صريحة: آخر أسبوعين وبلا اتجاه.
        level = (weekly_demand[-1] + weekly_demand[-2]) / Decimal("2")
        trend = ZERO

    mad = (sum(errors) / Decimal(len(errors))) if len(errors) >= MIN_MAD_SAMPLES else None
    return {"level": level, "trend": trend, "weeks_observed": n, "mad": mad}


def _week_start(day: datetime.date) -> datetime.date:
    """اثنين الأسبوع المحتوي على `day` — يطابق تجميع `TruncWeek` الافتراضي في جانغو."""
    return day - datetime.timedelta(days=day.weekday())


def last_completed_week_start(today: datetime.date) -> datetime.date:
    """اثنين آخر أسبوعٍ اكتمل فعلاً. أسبوع اليوم الجاري (ولو بدأ للتوّ) مُستبعَدٌ
    دائماً — دلوه لا يمثّل أسبوعاً كاملاً فيسحب المستوى للأسفل في كل تشغيل."""
    return _week_start(today) - datetime.timedelta(days=7)


def _weekly_series(tenant_id, product_ids, window_start, last_week_start) -> dict:
    """صافي الطلب الأسبوعي لكل منتج، الأقدم أوّلاً، بلا فجوات — استعلامان لا
    أكثر مهما بلغ عدد المنتجات (نمط `_demand_profiles` أعلاه بحرفيّته).

    أسابيع الصفر جزءٌ من السلسلة عمداً (ط1/ط2 على الخريطة): الاستعلام المجمَّع
    يعيد الأسابيع التي فيها حركةٌ فقط، وهنا تُملأ الفجوات صفراً على شبكة أسابيع
    كاملة من بداية سجلّ المنتج (أو بداية النافذة، أيّهما أحدث — تماماً كما
    تحسب `_history_days` أعلاه بداية سجلّ المنتج) إلى آخر أسبوعٍ مكتمل.
    """
    from inventory.models import StockMovement

    last_week_end = last_week_start + datetime.timedelta(days=6)

    base = StockMovement.objects.filter(tenant_id=tenant_id)
    if product_ids is not None:
        base = base.filter(product_id__in=product_ids)

    # أوّل حركةٍ للمنتج على الإطلاق — بلا حدٍّ زمني، كي لا يُقصَّر عمر منتجٍ
    # سابقٍ للنافذة على أنه وُلد معها.
    firsts = {
        row["product_id"]: row["first"]
        for row in base.values("product_id").annotate(first=Min("movement_date"))
        if row["first"] is not None
    }
    if not firsts:
        return {}

    weekly = (
        base.filter(
            movement_date__gte=window_start,
            movement_date__lte=last_week_end,
            movement_type__in=(_OUT, _RETURN_IN),
        )
        .annotate(week=TruncWeek("movement_date"))
        .values("product_id", "week")
        .annotate(
            out_qty=Sum("quantity", filter=Q(movement_type=_OUT)),
            ret_qty=Sum("quantity", filter=Q(movement_type=_RETURN_IN)),
        )
    )
    nets: dict = {}
    for row in weekly:
        week = row["week"]
        week = week.date() if hasattr(week, "date") else week
        net = _dec(row["out_qty"]) - _dec(row["ret_qty"])
        nets.setdefault(row["product_id"], {})[week] = net

    series: dict = {}
    for product_id, first_movement in firsts.items():
        start = max(_week_start(first_movement), window_start)
        if start > last_week_start:
            # كل حركات المنتج داخل الأسبوع الجاري غير المكتمل — لا أسبوعٌ
            # واحدٌ مكتمل بعد.
            continue
        product_weeks = nets.get(product_id, {})
        weeks = []
        cursor = start
        while cursor <= last_week_start:
            weeks.append(product_weeks.get(cursor, ZERO))
            cursor += datetime.timedelta(days=7)
        series[product_id] = weeks
    return series


def weekly_demand_series(tenant_id: int, product_ids=None, *, today=None):
    """(سلسلةٌ أسبوعية لكل منتج، اثنين آخر أسبوعٍ مكتمل) — نقطة الدخول العامة
    لهذا القسم.

    النافذة `FORECAST_HISTORY_WEEKS` أسبوعاً تنتهي عند آخر أسبوعٍ مكتمل، لا
    اليوم: الأسبوع الجاري ثلاثة أيامٍ منه فقط تكفي لسحب المستوى للأسفل في كل
    تشغيل لو دخلت السلسلة (الحرف ب في التذكرة).
    """
    from django.utils import timezone

    today = today or timezone.localdate()
    last_week = last_completed_week_start(today)
    window_start = last_week - datetime.timedelta(days=7 * (FORECAST_HISTORY_WEEKS - 1))
    return _weekly_series(tenant_id, product_ids, window_start, last_week), last_week


def _lead_time_samples(tenant_id: int, limit: int = 300) -> tuple[dict, dict, list]:
    """عيّنات مهلة التوريد بالأيام: لكل منتج، ولكل مورّد، وللشركة.

    المهلة = من تاريخ الطلبية إلى **أول حركة وارد** لفاتورتها — لا إلى تاريخ
    الفاتورة: الفاتورة ورقة، والبضاعة تصل يوم تصل.
    """
    from logistics.models import PurchaseOrder, PurchaseOrderLine
    from inventory.models import StockMovement

    orders = list(
        PurchaseOrder.objects.filter(tenant_id=tenant_id, invoice__isnull=False)
        .exclude(status=PurchaseOrder.STATUS_CANCELLED)
        .order_by("-order_date", "-id")
        .values("id", "order_date", "invoice_id", "supplier_id")[:limit]
    )
    if not orders:
        return {}, {}, []

    invoice_ids = [o["invoice_id"] for o in orders if o["invoice_id"]]
    received = {
        row["reference_id"]: row["first"]
        for row in StockMovement.objects.filter(
            tenant_id=tenant_id,
            movement_type="IN",
            reference_type=_PURCHASE_REF,
            reference_id__in=invoice_ids,
        ).values("reference_id").annotate(first=Min("movement_date"))
    }
    order_ids = [o["id"] for o in orders]
    lines = PurchaseOrderLine.objects.filter(
        tenant_id=tenant_id, order_id__in=order_ids,
    ).values("order_id", "product_id")
    products_by_order: dict[int, set] = {}
    for line in lines:
        products_by_order.setdefault(line["order_id"], set()).add(line["product_id"])

    by_product: dict[int, list] = {}
    by_supplier: dict[int, list] = {}
    tenant_samples: list[int] = []
    for order in orders:
        arrival = received.get(order["invoice_id"])
        if not arrival or not order["order_date"]:
            continue
        days = (arrival - order["order_date"]).days
        if days < 0 or days > 365:
            # وصولٌ قبل الطلب (تصحيح تاريخٍ يدوي) أو بعد سنة: عيّنةٌ لا تصف مهلة.
            continue
        tenant_samples.append(days)
        by_supplier.setdefault(order["supplier_id"], []).append(days)
        for pid in products_by_order.get(order["id"], ()):
            by_product.setdefault(pid, []).append(days)
    return by_product, by_supplier, tenant_samples


def _lead_for(samples: list, fallback_days: int) -> tuple[Decimal, Decimal, str]:
    """(المهلة المعتادة، أطول مهلة، مصدرها) — الوسيط لا المتوسط.

    الوسيط يقاوم الطلبية الشاذّة التي تأخّرت في الجمارك ثلاثة أشهر؛ المتوسط لا.
    """
    if len(samples) >= MIN_LEAD_SAMPLES:
        typical = _dec(statistics.median(samples))
        longest = _dec(max(samples))
        if longest < typical:
            longest = typical
        return typical, longest, "observed"
    typical = _dec(fallback_days)
    return typical, typical * LEAD_MAX_FACTOR, "default"


def _forecast_map(tenant_id: int, product_ids=None) -> dict:
    """(المستوى، الاتجاه، MAD) المخزَّنة لكل منتج — استعلامٌ واحد للشركة كلّها.

    نفس نمط `_on_order_map`/`reserved_map`: لا استعلام لكل صفّ. منتجٌ بلا صفّ
    (الأمر لم يُشغَّل بعد، أو بلا حركة مخزون على الإطلاق) غائبٌ عن القاموس عمداً
    — هذا هو الإشارة التي يقرأها `_product_row` لـ`REASON_NO_FORECAST`.
    """
    from inventory.models import ProductDemandForecast

    qs = ProductDemandForecast.objects.filter(tenant_id=tenant_id)
    if product_ids is not None:
        qs = qs.filter(product_id__in=product_ids)
    return {
        row["product_id"]: row
        for row in qs.values("product_id", "level", "trend", "mad", "weeks_observed")
    }


def _on_order_map(tenant_id: int, product_ids=None) -> dict:
    """قيد الطلب: كميات طلبيات الشراء المؤكَّدة التي لم تُحوَّل إلى فاتورة بعد."""
    from logistics.models import PurchaseOrder, PurchaseOrderLine

    qs = PurchaseOrderLine.objects.filter(
        tenant_id=tenant_id, order__status=PurchaseOrder.STATUS_CONFIRMED,
    )
    if product_ids is not None:
        qs = qs.filter(product_id__in=product_ids)
    return {
        row["product_id"]: _dec(row["qty"])
        for row in qs.values("product_id").annotate(qty=Sum("quantity"))
    }


# ── الحساب ────────────────────────────────────────────────────────────

def _history_days(first_movement, window_start, today) -> int:
    """أيام السجل = من أوّل حركةٍ للمنتج (أو بداية النافذة، أيّهما أحدث) إلى اليوم.

    القسمة على طول النافذة كاملةً تظلم المنتج الحديث: خمسون قطعةً بيعت في
    أسبوعٍ ÷ تسعين يوماً = نصف قطعة يومياً، فيُقترَح له حدٌّ يكفي يومين.
    """
    if first_movement is None:
        return 0
    start = max(first_movement, window_start)
    return max((today - start).days + 1, 1)


def _product_row(product, *, profile, reserved_map, lead, lead_max, lead_source,
                 on_order, params, window_start, today, family_totals=None,
                 forecast=None) -> dict:
    from inventory.services import (
        family_display_name, product_display_name, product_group_key,
    )

    net = profile.get("net", ZERO)
    peak_week = profile.get("peak_week", ZERO)
    history = _history_days(profile.get("first_movement"), window_start, today)

    available = available_of(product, reserved_map)
    # حساب الصرف اليومي وذروته يبقى كما هو **دائماً**، مهما كان وضع المنتج:
    # المسار اليدوي يعتمده مباشرةً، والتلقائي يستعيره فقط حين لا يكفي سجل
    # الأخطاء لحساب MAD (أسفل)، وكلاهما يستعمل `hist_reason` لتمييز «راكد»
    # (بلا مبيعات في النافذة) عن «حديث» (سجلٌّ أقصر من الحدّ).
    hist_reason = ""
    if history < MIN_HISTORY_DAYS:
        adu = ZERO
        adu_peak = ZERO
        hist_reason = REASON_SHORT_HISTORY
    else:
        adu = net / Decimal(history) if net > ZERO else ZERO
        adu_peak = peak_week / Decimal("7")
        if adu_peak < adu:
            adu_peak = adu
        if adu <= ZERO:
            hist_reason = REASON_NO_SALES

    lead_weeks = lead / Decimal("7")
    review_weeks = Decimal(params.review_period_days) / Decimal("7")
    coverage_weeks = lead_weeks + review_weeks

    mode = product.reorder_mode
    weekly_sale = forecast["level"] if forecast else None
    trend = forecast["trend"] if forecast else None

    if mode == product.REORDER_MODE_AUTO:
        if forecast is None:
            # لم يُشغَّل الأمر بعد على هذا المنتج، أو بلا حركة مخزونٍ إطلاقاً
            # فلم يدخل سلسلته أصلاً (`weekly_demand_series`) — الحالتان معاً
            # تعنيان «لا أعرف بعد»، لا صفراً صامتاً (ط1/#33).
            reason = REASON_NO_FORECAST
            levels = {"safety_stock": ZERO, "suggested_min": 0, "suggested_max": 0}
        else:
            level = forecast["level"]
            trend = forecast["trend"]
            mad = forecast["mad"]
            # سقف الاتجاه صعوداً فقط (ط8) — النازل بلا سقف.
            trend_capped = (
                trend if trend <= ZERO else min(trend, level / TREND_CAP_DIVISOR)
            )
            need = (
                level * coverage_weeks
                + trend_capped * coverage_weeks * (coverage_weeks + Decimal("1")) / Decimal("2")
            )
            if mad is not None:
                safety = SAFETY_Z_FACTOR * (MAD_TO_SIGMA * mad) * coverage_weeks.sqrt()
            else:
                # سجلّ أخطاءٍ لا يكفي لـMAD (أقلّ من أربعة أسابيع مرصودة، ط7):
                # قاعدة الذروة القائمة أفضل من لا رقم — نفس دالّة المسار اليدوي.
                safety = suggest_levels(
                    adu=adu, adu_peak=adu_peak, lead_days=lead, lead_max_days=lead_max,
                    review_days=params.review_period_days,
                )["safety_stock"]
            levels = {
                "safety_stock": safety,
                "suggested_min": _ceil(level * lead_weeks + safety),
                "suggested_max": _ceil(need + safety),
            }
            # صنفٌ بلا مبيعاتٍ فعلياً (المستوى نفسه هابطٌ لصفر تقريباً) يبقى
            # يُقرأ «راكد» — نفس الإشارة التي يقرأها المسار اليدوي، كي يبقى
            # فلتر «راكد» (ط10) يراه رغم أن له صفّ تنبّؤٍ محفوظاً.
            reason = REASON_NO_SALES if hist_reason == REASON_NO_SALES else ""
    else:
        reason = hist_reason
        if reason:
            levels = {"safety_stock": ZERO, "suggested_min": 0, "suggested_max": 0}
        else:
            levels = suggest_levels(
                adu=adu, adu_peak=adu_peak, lead_days=lead, lead_max_days=lead_max,
                review_days=params.review_period_days,
            )

    manual_min = product.min_stock_level
    manual_max = product.max_stock_level
    governing_min = effective_min(product, levels["suggested_min"])
    status = stock_status_of(
        product, reserved_map=reserved_map, suggested_min=levels["suggested_min"],
        suggested_max=levels["suggested_max"], family_totals=family_totals,
    )
    # بلا مستوىً مستهدَف لا كمية تُطلَب. وبغير هذا الشرط كان منتجٌ رصيده سالب
    # (‑401 من فوضى بياناتٍ قديمة) وبلا مبيعةٍ واحدة يُقترَح طلب 401 منه —
    # الصفر ناقص السالب. المسار التلقائي **لا** يستشير `manual_max` — صيغته
    # مكتملة بذاتها (ط1/#33: «الاحتياج + الأمان − المتاح − قيد الطلب»).
    if mode == product.REORDER_MODE_AUTO:
        target = _dec(levels["suggested_max"])
    else:
        target = _dec(manual_max) if manual_max else _dec(levels["suggested_max"])
    order_qty = (target - (available + on_order)) if target > ZERO else ZERO
    if trend is None:
        trend_label = "—"
    elif trend > ZERO:
        trend_label = TREND_UP
    elif trend < ZERO:
        trend_label = TREND_DOWN
    else:
        trend_label = TREND_FLAT
    return {
        "product_id": product.id,
        "sku": product.sku or "",
        "name": product_display_name(product),
        "brand": product.brand or "",
        "category": product.category.name if product.category_id else "",
        "group_key": product_group_key(product),
        # #26: مفتاح التقارير المجمَّعة على المنتج — منفصلٌ عن `group_key`
        # (سلّم «الأنواع المتبادلة» الأوسع). عائلةٌ صريحة (`ProductFamily`)
        # فقط، لا مقاس إطارٍ ولا براندٌ متكرّر.
        "family_id": product.family_id,
        "family_name": (
            family_display_name(product.family, product.family_id)
            if product.family_id else ""
        ),
        # #26-دلتا: نفس المتاح الذي **قِيس عليه حكم `status` فعلاً** حين للمنتج
        # أبٌ (`stock_status_of` تقرأ `family_totals[family_id]` لا رصيد هذا
        # البراند وحده) — لا رصيدٌ يُعاد جمعه من الإخوة المفلترين/الظاهرين، فقد
        # يُسقط فلترٌ (منتج/مورّد) بعضهم فينحرف المجموع عن الحكم الفعلي. `None`
        # لمنتجٍ بلا أبٍ. مُشتقٌّ من `family_totals` المحسوبة مرّةً للشركة كلّها
        # في `replenishment_rows` — بلا استعلامٍ إضافي لكل صفّ.
        "family_available": (
            family_totals.get(product.family_id)
            if product.family_id and family_totals is not None else None
        ),
        "created_at": product.created_at,
        "on_hand": _dec(product.quantity_on_hand),
        "reserved": reserved_of(product, reserved_map),
        "available": available,
        "on_order": on_order,
        "history_days": history,
        "adu": adu,
        "adu_peak": adu_peak,
        "lead_days": lead,
        "lead_source": lead_source,
        "safety_stock": levels["safety_stock"],
        "manual_min": manual_min,
        "manual_max": manual_max,
        "suggested_min": levels["suggested_min"],
        "suggested_max": levels["suggested_max"],
        "effective_min": governing_min,
        "order_qty": max(order_qty, ZERO),
        "status": status,
        "reason": reason,
        # #33: أعمدة تفسّر الرقم — «ما بدي رقم بينزل من السما» (ط1). المستوى
        # والاتجاه من `ProductDemandForecast` إن وُجد صفّه (بصرف النظر عن
        # الوضع: منتجٌ يدويّ قد يملك تنبّؤاً محفوظاً هو الآخر)، وإلا `None`.
        "reorder_mode": mode,
        "weekly_sale": weekly_sale,
        "trend": trend,
        "trend_label": trend_label,
        "coverage_weeks": coverage_weeks,
    }


def _group_rows(rows: list[dict], params: ReplenishmentParams) -> dict:
    """يجمع منتجات كل نوعٍ في صفٍّ واحد.

    **أرقام النوع مجاميعُ أرقام أفراده، لا حسابٌ ثانٍ عليها.** جُرِّب البديل
    (إعادة تطبيق المعادلة على الطلب المجمَّع، وهو نظرياً أدقّ لأن تجميع الطلب
    يقلّل التقلّب) ورُفض: الشاشة تفتح صفّ النوع على أفراده، ومجموعُ التفصيل يجب
    أن يساوي رقم الصفّ وإلّا فقد الرقمُ قابليةَ التحقّق — وهي قاعدةٌ معلنة في
    `docs/modules/core.md` (6.1.1). رقمٌ متحفّظٌ يُراجَع خيرٌ من رقمٍ أدقّ لا
    يُراجَع.
    """
    groups: dict[str, dict] = {}
    for row in rows:
        g = groups.setdefault(row["group_key"], {
            "group_key": row["group_key"],
            "products": [],
            "on_hand": ZERO, "available": ZERO, "on_order": ZERO,
            "adu": ZERO, "adu_peak": ZERO, "lead_days": ZERO,
            "safety_stock": ZERO, "suggested_min": 0, "suggested_max": 0,
            "effective_min": ZERO, "order_qty": ZERO,
        })
        g["products"].append(row)
        g["on_hand"] += row["on_hand"]
        g["available"] += row["available"]
        g["on_order"] += row["on_order"]
        g["adu"] += row["adu"]
        g["adu_peak"] += row["adu_peak"]
        g["safety_stock"] += row["safety_stock"]
        g["suggested_min"] += row["suggested_min"]
        g["suggested_max"] += row["suggested_max"]
        g["effective_min"] += row["effective_min"]
        g["order_qty"] += row["order_qty"]
        if row["lead_days"] > g["lead_days"]:
            # مهلة النوع = أطول مهلةٍ فيه: النوع لا يكون مغطّى حتى يصل أبطؤه.
            g["lead_days"] = row["lead_days"]

    for g in groups.values():
        g["products_count"] = len(g["products"])
    return groups


def _urgency_of(row: dict, group: dict) -> str:
    """قرار الطلب — من المنتج ونوعه معاً لا من المنتج وحده.

    **بلا إشارة طلبٍ لا «عاجل».** قِيس على بيانات حقيقية (1490 منتجاً) قبل هذا
    الشرط: 722 منتجاً خرجت «عاجلة» لأن رصيدها ≤ 0، وفيها منتجاتٌ لم تُبَع مرّةً
    في تسعين يوماً ورصيدها سالبٌ من فوضى بياناتٍ قديمة. قائمةُ طلبٍ نصفُها ضجيج
    لا تُقرأ أصلاً، فيسقط التقرير كلّه — لا لأنه أخطأ في رقم بل لأنه لم يُرتّب.

    فالإلحاح لا يُعطى إلا لمنتجٍ له معدّل صرفٍ محسوب (`reason` فارغ واقتراحٌ
    موجب). وما عداه يقول سببه في عموده ولا يُصنَّف: «راكد» لرصيدٍ موجب بلا
    مبيعات، و«—» لمنتجٍ لا نعرفه بعد.
    """
    has_signal = not row["reason"] and row["suggested_min"] > 0
    if not has_signal:
        if row["available"] > ZERO and row["reason"] == REASON_NO_SALES:
            return URGENCY_DEAD
        return URGENCY_OK
    if row["status"] not in (STATUS_OUT_OF_STOCK, STATUS_LOW):
        return URGENCY_OK
    if group["effective_min"] > ZERO and group["available"] > group["effective_min"]:
        return URGENCY_DEFERRED
    if (group["products_count"] > 1 and group["effective_min"] <= ZERO
            and group["available"] > row["available"]):
        # نوعٌ بلا حدٍّ محسوب لكن فيه موديلٌ عليه رصيد ⇒ بِعْه قبل أن تطلب.
        return URGENCY_DEFERRED
    return URGENCY_URGENT


def replenishment_rows(tenant_id: int, *, product_ids=None, category_id=None,
                       supplier_id=None, urgency=None, level="item",
                       today=None) -> list[dict]:
    """صفوف التجديد — على مستوى المنتج أو النوع.

    `level="group"` يطوي كل نوعٍ في صفٍّ واحد بحدٍّ محسوبٍ من طلبه المجمَّع.
    الفلاتر كلّها اختيارية، ودالّة الفلترة **واحدة** للصفوف وللتنقيب معاً كي لا
    ينحرف مجموع التفصيل عن رقم الصفّ.
    """
    from django.utils import timezone

    from sales.services import reserved_quantity_map

    from inventory.models import Product
    from inventory.services import category_descendant_product_ids

    today = today or timezone.localdate()
    params = replenishment_params(tenant_id)
    window_start = today - datetime.timedelta(days=params.window_days - 1)

    qs = Product.objects.filter(
        tenant_id=tenant_id, is_service=False, is_store_only=False,
    ).select_related("category", "family")
    if product_ids is not None:
        qs = qs.filter(pk__in=product_ids)
    if category_id:
        qs = qs.filter(pk__in=category_descendant_product_ids(
            tenant_id=tenant_id, category_id=category_id,
        ))
    if supplier_id:
        from inventory.models import SupplierProduct

        qs = qs.filter(pk__in=SupplierProduct.objects.filter(
            tenant_id=tenant_id, supplier_id=supplier_id,
        ).values("product_id"))

    products = list(qs)
    if not products:
        return []
    ids = [p.id for p in products]

    reserved_map = reserved_quantity_map(tenant_id, ids)
    # #25: مجموع أرصدة إخوة كل أبٍ — استعلامٌ واحدٌ للشركة كلّها لا واحدٌ لكل صفّ.
    family_totals = family_available_map(tenant_id, reserved_map=reserved_map)
    profiles = _demand_profiles(tenant_id, ids, window_start, today)
    lead_by_product, lead_by_supplier, tenant_samples = _lead_time_samples(tenant_id)
    on_order = _on_order_map(tenant_id, ids)
    forecasts = _forecast_map(tenant_id, ids)
    tenant_lead = _lead_for(tenant_samples, params.default_lead_time_days) \
        if len(tenant_samples) >= 3 else None

    rows = []
    for product in products:
        samples = lead_by_product.get(product.id) or []
        if len(samples) >= MIN_LEAD_SAMPLES:
            lead, lead_max, lead_source = _lead_for(samples, params.default_lead_time_days)
        elif tenant_lead is not None:
            lead, lead_max, lead_source = tenant_lead[0], tenant_lead[1], "tenant"
        else:
            lead, lead_max, lead_source = _lead_for([], params.default_lead_time_days)
        rows.append(_product_row(
            product,
            profile=profiles.get(product.id, {}),
            reserved_map=reserved_map,
            lead=lead, lead_max=lead_max, lead_source=lead_source,
            on_order=on_order.get(product.id, ZERO),
            params=params, window_start=window_start, today=today,
            family_totals=family_totals,
            forecast=forecasts.get(product.id),
        ))

    groups = _group_rows(rows, params)
    newest_by_group: dict[str, dict] = {}
    for row in rows:
        if row["available"] <= ZERO:
            continue
        current = newest_by_group.get(row["group_key"])
        if current is None or (row["created_at"] and current["created_at"]
                               and row["created_at"] > current["created_at"]):
            newest_by_group[row["group_key"]] = row

    for row in rows:
        group = groups[row["group_key"]]
        row["urgency"] = _urgency_of(row, group)
        row["urgency_label"] = URGENCY_LABELS[row["urgency"]]
        row["group_available"] = group["available"]
        row["group_effective_min"] = group["effective_min"]
        siblings = [
            r for r in group["products"]
            if r["product_id"] != row["product_id"] and r["available"] > ZERO
        ]
        row["alternatives"] = len(siblings)
        newest = newest_by_group.get(row["group_key"])
        row["newest_alternative"] = (
            newest["name"] if newest and newest["product_id"] != row["product_id"] else ""
        )

    if level == "group":
        out = []
        for g in groups.values():
            members = g["products"]
            worst = min(members, key=lambda r: URGENCY_ORDER[r["urgency"]])
            out.append({
                "group_key": g["group_key"],
                "products_count": g["products_count"],
                "on_hand": g["on_hand"],
                "available": g["available"],
                "on_order": g["on_order"],
                "adu": g["adu"],
                "lead_days": g["lead_days"],
                "safety_stock": g["safety_stock"],
                "suggested_min": g["suggested_min"],
                "suggested_max": g["suggested_max"],
                "effective_min": g["effective_min"],
                "order_qty": g["order_qty"],
                "urgency": worst["urgency"],
                "urgency_label": URGENCY_LABELS[worst["urgency"]],
                "out_of_stock_count": sum(
                    1 for r in members if r["status"] == STATUS_OUT_OF_STOCK
                ),
                "newest_alternative": (
                    newest_by_group.get(g["group_key"], {}).get("name", "")
                ),
            })
        rows = out

    if urgency:
        rows = [r for r in rows if r["urgency"] == urgency]
    rows.sort(key=lambda r: (URGENCY_ORDER[r["urgency"]], -float(r["order_qty"])))
    return rows


# ── التطبيق: النقطة الوحيدة التي تكتب ─────────────────────────────────

def apply_suggested_levels(tenant_id: int, product_ids, *, user=None) -> dict:
    """يثبّت الحدّين المقترَحين على المنتجات المحدَّدة.

    ما لا يُكتب ولماذا: منتجٌ بلا اقتراح (سجلّ قصير أو بلا مبيعات) يُترَك كما هو
    ويعود في `skipped` بسببه. كتابةُ صفرٍ عليه تعني «لا تطلب هذا أبداً» وهي
    ليست ما تقوله البيانات — البيانات تقول «لا أعرف بعد».
    """
    from core.activity import log_activity

    from inventory.models import Product

    ids = [int(pid) for pid in (product_ids or [])]
    if not ids:
        return {"applied": 0, "skipped": [], "products": []}

    rows = replenishment_rows(tenant_id, product_ids=ids, level="item")
    by_id = {r["product_id"]: r for r in rows}
    products = {p.id: p for p in Product.objects.filter(tenant_id=tenant_id, pk__in=ids)}

    applied, skipped, touched = [], [], []
    for pid in ids:
        row = by_id.get(pid)
        product = products.get(pid)
        if row is None or product is None:
            skipped.append({"product_id": pid, "reason": "المنتج غير موجود أو خدمة"})
            continue
        if row["reason"] or row["suggested_min"] <= 0:
            skipped.append({"product_id": pid, "sku": row["sku"],
                            "reason": row["reason"] or REASON_NO_SALES})
            continue
        product.min_stock_level = row["suggested_min"]
        product.max_stock_level = row["suggested_max"]
        touched.append(product)
        applied.append({
            "product_id": pid, "sku": row["sku"], "name": row["name"],
            "min_stock_level": row["suggested_min"],
            "max_stock_level": row["suggested_max"],
        })

    if touched:
        Product.objects.bulk_update(touched, ["min_stock_level", "max_stock_level"])
        # #20: حدّا التجديد حقلان «أبويّان» والقراءة تفضّل الأب — فكاتبٌ لا
        # يزامن يترك الكرت يعرض الحدَّ القديم بعد تطبيق الجديد، بلا خطأٍ ظاهر.
        from inventory.services import sync_families_from_products

        sync_families_from_products(touched)
        log_activity(
            action="update",
            entity_type="product",
            entity_label=f"{len(touched)} منتجاً",
            description=(
                f"طبّق الحدّ الأدنى/الأقصى المقترَح على {len(touched)} منتجاً "
                f"من تقرير تجديد المخزون"
            ),
            metadata={"applied": applied[:50], "skipped_count": len(skipped)},
            user=user,
        )
        logger.info(
            "replenishment.apply tenant=%s applied=%s skipped=%s",
            tenant_id, len(touched), len(skipped),
        )
        # التقارير مكشوفة بكاشٍ 60ث — وبلا إبطاله يعود التقرير بأرقامه القديمة
        # بعد الضغط مباشرةً، فيبدو الزرّ معطّلاً.
        from core.reports_api import invalidate_tenant_reports

        invalidate_tenant_reports(tenant_id)
    return {"applied": len(touched), "skipped": skipped, "products": applied}
