"""مدى زمني محلّي آمن — بديل `__date` على أعمدة `DateTimeField` (Shared/Core).

**لماذا هذا الملف موجود.** جانغو يترجم `created_at__date = X` إلى
`DATE(CONVERT_TZ(created_at,'UTC','Asia/Hebron'))`. و`CONVERT_TZ` بمنطقةٍ
مُسمّاة تحتاج جداول `mysql.time_zone` مُحمَّلة على الخادم؛ وهي **فارغة** على
خادم الإنتاج عندنا، فتُعيد الدالة `NULL` ⇒ الشرط لا يطابق أي صف ⇒ الشاشة تظهر
فارغة بلا خطأ ولا أثر في اللوج. هكذا اختفى سجل النشاط بالكامل (١٣٤٤ صفاً في
الجدول، وصفرٌ على الشاشة).

**العلاج.** نحسب حدود اليوم المحلي في بايثون ونقارن الوقت بها مباشرةً:
`ts >= بداية اليوم` و`ts < بداية الغد`. لا `CONVERT_TZ` ولا اعتماد على إعداد
الخادم — **والفهرس على العمود يبقى مستعملاً**، بينما `DATE(CONVERT_TZ(...))`
يُلغيه ويفرض مسحاً كاملاً.

الحدّ الأعلى **مفتوح** (`__lt` لا `__lte`) عمداً: `<= 23:59:59` يُسقط الكسور
الثانوية التي تخزّنها MySQL في `datetime(6)`.
"""
from __future__ import annotations

import datetime as _dt

from django.utils import timezone

# أسماء المدى الجاهزة كما تصل من الواجهة. `all` = بلا حدّ.
RANGE_PRESETS = (
    "today", "yesterday", "week", "month", "quarter", "year", "all",
)


def local_day_start(day: _dt.date) -> _dt.datetime:
    """منتصف ليل `day` بتوقيت الشركة، كوقتٍ واعٍ بالمنطقة.

    ملاحظة على الانتقال الصيفي: في السنوات التي يبدأ فيها التوقيت الصيفي عند
    منتصف الليل تماماً، تكون الساعة 00:00 غير موجودة محلياً. `zoneinfo` لا يرمي
    في هذه الحالة بل يستعمل إزاحة ما قبل الانتقال (PEP 495)، فينزاح الحدّ ساعةً
    واحدة على أسوأ تقدير — وهو أهون بما لا يقاس من `NULL` تبتلع الصفوف كلّها.
    """
    return timezone.make_aware(
        _dt.datetime.combine(day, _dt.time.min),
        timezone.get_current_timezone(),
    )


def day_bounds(
    date_from: _dt.date | None, date_to: _dt.date | None,
) -> tuple[_dt.datetime | None, _dt.datetime | None]:
    """حوّل يومين شاملين إلى مدى نصف مفتوح `[start, end)`."""
    start = local_day_start(date_from) if date_from else None
    end = local_day_start(date_to + _dt.timedelta(days=1)) if date_to else None
    return start, end


def filter_local_date_range(qs, field: str, date_from=None, date_to=None):
    """طبّق مدى يومين محلّيين على حقل `DateTimeField` بلا `CONVERT_TZ`.

    `field` اسم الحقل الخام (`timestamp`, `created_at`, `journal__created_at`) —
    **بلا** لاحقة `__date`.
    """
    start, end = day_bounds(date_from, date_to)
    if start is not None:
        qs = qs.filter(**{f"{field}__gte": start})
    if end is not None:
        qs = qs.filter(**{f"{field}__lt": end})
    return qs


def resolve_preset(name: str, today: _dt.date | None = None):
    """اسم مدى جاهز ← (من، إلى) يومين شاملين. غير المعروف يسقط إلى «اليوم».

    الأسبوع يبدأ **السبت** (عرف الأسبوع المحاسبي المحلي، لا الاثنين الأوروبي):
    `weekday()` في بايثون يجعل الاثنين ٠ والسبت ٥، فالإزاحة `(weekday + 2) % 7`.
    """
    today = today or timezone.localdate()
    name = (name or "").strip().lower()
    if name == "all":
        return None, None
    if name == "yesterday":
        y = today - _dt.timedelta(days=1)
        return y, y
    if name == "week":
        return today - _dt.timedelta(days=(today.weekday() + 2) % 7), today
    if name == "month":
        return today.replace(day=1), today
    if name == "quarter":
        first_month = 3 * ((today.month - 1) // 3) + 1
        return today.replace(month=first_month, day=1), today
    if name == "year":
        return today.replace(month=1, day=1), today
    return today, today
