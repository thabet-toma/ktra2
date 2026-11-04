"""محرّك المواعيد — **دالةٌ نقيّة**: لا استعلامَ قاعدة، ولا تاريخَ قانونيّاً في الكود.

تأخذ سطرَ اللائحة (`DeadlineRule`) وفترةً وإعداداتٍ جاهزة، وتُعيد
`DeadlineResult`: التاريخَ بالقاعدة، والرسميَّ بعد سياسة يوم الراحة، والفعليَّ
بعد التمديد الإلكترونيّ، والداخليَّ بعد أيام الإعداد ورجوعِ عطلة المكتب.

**ولا رقمَ هنا إلا أعدادُ التقويم** (صفرٌ للافتراضي، واحدٌ في حساب الشهر، واثنا
عشر شهراً): كلُّ يومٍ وكلُّ شهرٍ يُقرأ من صفٍّ في `DeadlineSchedule` /
`DeadlineRule`. يحرس ذلك مسحُ `ast` في
`accounting_office/tests/test_deadlines.py` — لا في تعليقٍ يُنسى.

**الترتيب أربعة، ولا يُقدَّم أحدُها على غيره:**
1. `legal_date` — من `rule_kind` وحدها.
2. `official_date` — تعديلُ النشرة المنشور، أو سياسةُ يوم الراحة، أو تنبيهٌ بلا
   زحزحة (فلسطين) بحسب `DeadlineSchedule.rest_day_policy`.
3. `actual_deadline` — الرسميُّ زائدَ التمديد الإلكترونيّ حين تكون طريقةُ
   التقديم إلكترونية.
4. `internal_deadline` — الفعليُّ ناقصَ أيام الإعداد، ثم رجوعٌ ليوم عملٍ في عطلة
   المكتب.
"""
import calendar
import dataclasses
import datetime
from typing import Any, Iterable

from accounting_office import settings_registry
from accounting_office.models import (
    CADENCE_SPAN_MONTHS,
    REST_DAY_POLICY_POSTPONE_CLIENT,
    RULE_KIND_END_OF_PERIOD,
    RULE_KIND_MONTH_DAY_NEXT_YEAR,
)

#: طريقةُ التقديم الإلكترونيّ — القيمةُ التي تُفعِّل التمديد في الخطوة الثالثة.
FILING_METHOD_ELECTRONIC = "electronic"

#: تنبيهُ إعداداتٍ تقول «كلُّ أيام الأسبوع عطلة»: المحرّكُ يتوقّف عن الزحزحة بعد
#: أسبوعٍ كامل ويُعلنها، فلا يُعلّق الطلبَ ولا يصمت عن بياناتٍ خاطئة.
ALL_DAYS_CLOSED_WARNING = "كل أيام الأسبوع مغلقة في الإعدادات — راجع"

#: أسماءُ الشهور — تسميةُ الفترة تُبنى منها، ولا تُخترَع في الواجهة.
MONTH_LABELS: tuple[str, ...] = (
    "كانون الثاني", "شباط", "آذار", "نيسان", "أيار", "حزيران",
    "تموز", "آب", "أيلول", "تشرين الأول", "تشرين الثاني", "كانون الأول",
)

#: مفاتيحُ الأسبوع بترتيب `date.weekday()` (الاثنين أولاً). تُبنى من
#: `settings_registry.WEEKDAY_KEYS` (الأحد أولاً) بإزاحةٍ واحدة — فلا نسخةً
#: ثانية من المفاتيح تفترق عن السجلّ.
WEEKDAY_KEYS_BY_PYTHON_INDEX: tuple[str, ...] = (
    settings_registry.WEEKDAY_KEYS[1:] + settings_registry.WEEKDAY_KEYS[:1]
)


@dataclasses.dataclass(frozen=True)
class DeadlineResult:
    """نتيجةُ حساب موعدٍ واحد — أربعةُ تواريخَ وثلاثُ علاماتٍ وتنبيهاتُها."""

    legal_date: datetime.date
    official_date: datetime.date
    actual_deadline: datetime.date
    internal_deadline: datetime.date
    estimated: bool
    postponed: bool
    warnings: list[str]
    rule_code: str
    period_start: datetime.date
    period_end: datetime.date


def weekday_key(day: datetime.date) -> str:
    """مفتاحُ يوم الأسبوع (`fri`…) كما في سجلّ الإعدادات — من تاريخه وحده."""
    return WEEKDAY_KEYS_BY_PYTHON_INDEX[day.weekday()]


def weekday_label(day: datetime.date) -> str:
    return settings_registry.WEEKDAY_LABELS[weekday_key(day)]


def _first_of_month(day: datetime.date) -> datetime.date:
    return day.replace(day=1)


def add_months(day: datetime.date, months: int) -> datetime.date:
    """اليومُ نفسه بعد `months` شهراً — **مقيَّداً بآخر يومٍ في شهره**.

    نسخةُ حساب الأشهر الوحيدة في الموديول: يقرؤها `services` لأفق التقويم، ولا
    كائنَ `relativedelta` في المستودع.
    """
    total = day.year * 12 + (day.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    _weekday_of_first, last_day = calendar.monthrange(year, month)
    return day.replace(year=year, month=month, day=min(day.day, last_day))


def month_start_after(day: datetime.date, months: int) -> datetime.date:
    """أولُ يومٍ في الشهر بعد `months` شهراً (سالبٌ للخلف) — بعبور السنة."""
    total = day.year * 12 + (day.month - 1) + months
    year, month = divmod(total, 12)
    return _first_of_month(day).replace(year=year, month=month + 1)


def _next_month(day: datetime.date) -> tuple[int, int]:
    """`(سنة, شهر)` للشهر التالي — بعبور حدّ السنة."""
    if day.month == 12:
        return day.year + 1, 1
    return day.year, day.month + 1


def _clamped_date(year: int, month: int, day: int) -> datetime.date:
    """تاريخٌ لا يتجاوز آخر يومٍ في شهره — قاعدةُ «31» في شهرٍ من ثلاثين."""
    _weekday_of_first, last_day = calendar.monthrange(year, month)
    return datetime.date(year, month, min(day, last_day))


def _legal_date(rule, period_end: datetime.date) -> datetime.date:
    """الخطوة الأولى: التاريخُ كما في النصّ، بلا زحزحةٍ وبلا عطلة."""
    if rule.rule_kind == RULE_KIND_END_OF_PERIOD:
        return period_end
    if rule.rule_kind == RULE_KIND_MONTH_DAY_NEXT_YEAR:
        return _clamped_date(
            period_end.year + 1, rule.rule_month or 1, rule.rule_day or 1,
        )
    year, month = _next_month(period_end)
    return _clamped_date(year, month, rule.rule_day or 1)


def _period_key(day: datetime.date) -> str:
    """مفتاحُ شهر نهاية الفترة كما في `period_overrides` — `YYYY-MM`."""
    return f"{day.year:04d}-{day.month:02d}"


def _published_override(rule, period_end: datetime.date) -> dict[str, Any] | None:
    """تعديلُ النشرة المنشور لهذه الفترة، أو `None` إذا لم يُنشر لها شيء."""
    raw = (rule.period_overrides or {}).get(_period_key(period_end))
    if not raw:
        return None
    try:
        day = datetime.date.fromisoformat(str(raw.get("date")))
    except (TypeError, ValueError):
        return None
    return {"date": day, "rest_day_only": bool(raw.get("rest_day_only"))}


def _advance_past_rest_days(day: datetime.date, closed: Iterable[str]):
    """يقدّم يوماً بيوم حتى يوم عمل — `(اليوم, أعجزَ أسبوعٌ كامل؟)`.

    والحدُّ أسبوعٌ كامل: بياناتٌ تقول «كلُّ الأيام عطلة» لا تُدخل المحرّكَ في حلقةٍ
    لا تنتهي — يتوقّف عند آخر يومٍ فحصه ويُعلنها في التنبيهات.
    """
    closed = set(closed)
    for _attempt in range(len(WEEKDAY_KEYS_BY_PYTHON_INDEX)):
        if weekday_key(day) not in closed:
            return day, False
        day += datetime.timedelta(days=1)
    return day, True


def _step_back_past_rest_days(day: datetime.date, closed: Iterable[str]):
    """نظيرُ `_advance_past_rest_days` للخلف — `(اليوم, أعجزَ أسبوعٌ كامل؟)`."""
    closed = set(closed)
    for _attempt in range(len(WEEKDAY_KEYS_BY_PYTHON_INDEX)):
        if weekday_key(day) not in closed:
            return day, False
        day -= datetime.timedelta(days=1)
    return day, True


def compute_deadline(
    rule,
    *,
    period_start: datetime.date,
    period_end: datetime.date,
    estimated: bool,
    client_rest_days: Iterable[str],
    office_rest_days: Iterable[str],
    filing_method: str,
    internal_lead_days: int,
    schedule_policy: str,
    authority_closed_days: Iterable[str],
) -> DeadlineResult:
    """يحسب موعدَ سطرٍ واحدٍ لفترةٍ واحدة — بلا قاعدةٍ وبلا ساعة.

    **الخطوةُ الثانية (الرسمي)** بالترتيب: تعديلٌ منشورٌ في `period_overrides`
    ليس سببه يومَ الراحة وحده ⇒ يُؤخذ كما هو؛ وإلا فسياسةُ النسخة: في إسرائيل
    يُقدَّم يوماً بيوم فوق أيام راحة الزبون وأيام إغلاق السلطة، وفي فلسطين يبقى
    التاريخُ كما هو ويُضاف تنبيهٌ إن وقع في يوم إغلاق. والنسخةُ «التقديرية»
    (سنةٌ بلا لائحة) تتجاهل التعديلات كلَّها لأنها لسنةٍ أخرى.

    **الخطوةُ الثالثة (الفعلي)** = الرسميّ زائدَ `electronic_extension_days` إن
    كانت `filing_method` إلكترونية، وإلا الرسميُّ نفسه. **ولا زحزحةَ بعدها**:
    الأبكرُ أحوط، فالتأجيلُ الزائد يخالف «الموعد الأخير» ولا يُنقصه.

    **الخطوةُ الرابعة (الداخلي)** = الفعليُّ ناقصَ `internal_lead_days`، ثم رجوعٌ
    يوماً بيوم ما دام اليومُ في `office_rest_days` — الموعدُ الداخليُّ يومَ عمل
    للمكتب دائماً.
    """
    legal_date = _legal_date(rule, period_end)
    warnings: list[str] = []
    published = None if estimated else _published_override(rule, period_end)
    stalled = False

    if published is not None and not published["rest_day_only"]:
        official_date = published["date"]
    elif schedule_policy == REST_DAY_POLICY_POSTPONE_CLIENT:
        official_date, stalled = _advance_past_rest_days(
            legal_date, [*client_rest_days, *authority_closed_days],
        )
    else:
        official_date = legal_date
        if weekday_key(official_date) in set(authority_closed_days):
            warnings.append(f"الموعد يوم {weekday_label(official_date)} — قدّم قبل")

    actual_deadline = official_date
    if filing_method == FILING_METHOD_ELECTRONIC:
        actual_deadline = official_date + datetime.timedelta(
            days=rule.electronic_extension_days or 0,
        )

    internal_deadline, stepped_back_stalled = _step_back_past_rest_days(
        actual_deadline - datetime.timedelta(days=internal_lead_days or 0),
        office_rest_days,
    )
    if stalled or stepped_back_stalled:
        warnings.append(ALL_DAYS_CLOSED_WARNING)

    return DeadlineResult(
        legal_date=legal_date,
        official_date=official_date,
        actual_deadline=actual_deadline,
        internal_deadline=internal_deadline,
        estimated=estimated,
        postponed=official_date != legal_date,
        warnings=warnings,
        rule_code=rule.code,
        period_start=period_start,
        period_end=period_end,
    )


def periods_for(
    cadence_or_frequency: str | None,
    start: datetime.date,
    end: datetime.date,
) -> list[tuple[datetime.date, datetime.date]]:
    """الفتراتُ المتقاطعة مع المدى، **محاذاةً للتقويم**.

    شهرية: كلُّ شهر. وكلُّ شهرين: كانون الثاني–شباط ثم آذار–نيسان… ورُبعية: أرباع
    السنة. وسنوية: السنةُ الميلادية. و`on_demand` (و`service` معها) لا شيء:
    لا دوريةَ ثابتةً تُحسب منها فترة.
    """
    span = CADENCE_SPAN_MONTHS.get(cadence_or_frequency or "", 0)
    if span <= 0:
        return []

    cursor = _first_of_month(start)
    # أولُ حزمةٍ في السنة تبدأ بشهر واحد، فالسنةُ تُقسَم حزماً متساويةً مهما
    # كان أولُ المدى — وإلا بدأت الفتراتُ من منتصف شهرٍ فاختلفت باختلاف الطلب.
    cursor = cursor.replace(month=((cursor.month - 1) // span) * span + 1)
    periods: list[tuple[datetime.date, datetime.date]] = []
    while cursor <= end:
        period_end = month_start_after(cursor, span) - datetime.timedelta(days=1)
        if period_end >= start:
            periods.append((cursor, period_end))
        cursor = month_start_after(cursor, span)
    return periods


def service_periods(
    frequency_of_month,
    start: datetime.date,
    end: datetime.date,
) -> list[tuple[datetime.date, datetime.date, str]]:
    """فتراتُ خدمةٍ دوريتُها تتغيّر — `(البداية, النهاية, الدورية)`، **حزمٌ محاذاةٌ
    للتقويم، بلا فجوة ولا تداخل**.

    `frequency_of_month` دالّةٌ يأخذها المُنادي وتُعيد الدوريةَ السارية في شهرٍ ما
    (أو `None`). والخادمُ يمرّر قراءةَ **آخر يومٍ في الشهر**، فما يسري في نهايته
    يحكمه.

    ولكلِّ شهرٍ تُقرأ دوريتُه، ثم تُوسَم **الحزمةُ المحاذيةُ للتقويم** التي تحويه
    (كـ`periods_for`). وأولُ فترةٍ تبدأ ببداية حزمتها، وما بعدها يبدأ بالمؤشّر إن
    كان داخل الحزمة — فتغييرُ الدورية إلى «كل شهرين» من نيسان يعطي نيسانَ وحدَه
    بقيّةَ حزمة آذار–نيسان، ثم أيار–حزيران.

    **وتنتهي الفترةُ بنهاية حزمتها إلا إذا تغيّرت الدوريةُ في شهرٍ لاحقٍ داخلها**:
    تُقطع عندئذٍ في آخر الشهر الذي قبل أول شهرٍ مختلف. فكل شهرين حتى آذار ثم
    شهرية من نيسان تعطي آذارَ وحدَه ثم نيسان — لا حزمةً تبتلع نيسان. والمقارنةُ
    بالدورية نفسها (النصّ) لا بطول الحزمة. **ولا فجوةَ ولا تداخل**، والنتيجةُ لا
    تتغيّر ببداية المدى المطلوب لأن الحزم محاذاة.
    """
    periods: list[tuple[datetime.date, datetime.date, str]] = []
    cursor = _first_of_month(start)
    first = True
    while cursor <= end:
        frequency = frequency_of_month(cursor)
        span = CADENCE_SPAN_MONTHS.get(frequency or "", 0)
        if span <= 0:
            cursor = month_start_after(cursor, 1)
            continue
        bucket_start = cursor.replace(month=((cursor.month - 1) // span) * span + 1)
        bucket_end = month_start_after(bucket_start, span) - datetime.timedelta(days=1)
        period_end = bucket_end
        following = month_start_after(cursor, 1)
        while following <= bucket_end:
            if frequency_of_month(following) != frequency:
                period_end = following - datetime.timedelta(days=1)
                break
            following = month_start_after(following, 1)
        periods.append((
            bucket_start if first else max(bucket_start, cursor),
            period_end,
            frequency,
        ))
        first = False
        cursor = period_end + datetime.timedelta(days=1)
    return periods


def period_label(start: datetime.date, end: datetime.date) -> str:
    """تسميةُ الفترة كما تُعرض: «كانون الثاني 2026» أو «كانون الثاني–آذار 2026»."""
    if (start.year, start.month) == (end.year, end.month):
        return f"{MONTH_LABELS[start.month - 1]} {start.year}"
    if start.year == end.year and (start.month, end.month) == (1, 12):
        return str(start.year)
    if start.year == end.year:
        return f"{MONTH_LABELS[start.month - 1]}–{MONTH_LABELS[end.month - 1]} {start.year}"
    return (
        f"{MONTH_LABELS[start.month - 1]} {start.year}"
        f"–{MONTH_LABELS[end.month - 1]} {end.year}"
    )

