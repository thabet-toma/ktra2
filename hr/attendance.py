"""محرّك الحضور — قبولُ البصمة، ونسبتُها ليومها، واشتقاقُ اليوم منها.

ثلاث مسؤوليات لا رابع لها، وكلّها خادميّة:

1. **هل تُقبل البصمة؟** (`evaluate_punch`) — مسافةٌ من موقع العمل، وشبكةٌ
   مسموحة، وصورةٌ إن لزمت. القرار هنا وحده: المتصفّح يرسل ادّعاءً، والادّعاء
   لا يُصدَّق في مكان صدوره.
2. **أيّ يومٍ هذه البصمة؟** (`resolve_attendance_date`) — وليس بالضرورة يوم
   ساعتها: من دخل العاشرة مساءً وخرج السادسة صباحاً عمل يوماً واحداً هو يوم
   بداية ورديته.
3. **ماذا كان ذلك اليوم؟** (`recompute_attendance_day`) — دالّة **حتميّة**
   تُعيد بناء `AttendanceDay` من بصماته كلّ مرّة. تُستدعى بعد كل بصمة وكل
   تصحيح وكل موافقة إجازة، ونتيجتها لا تتوقّف على عدد مرّات استدعائها.

**التوقيت كلّه واعٍ بالمنطقة** (`Asia/Hebron` مع التوقيت الصيفي):
`timezone.localdate()` وحدها مصدرَ «اليوم» — ونظيرتها الساذجة في المكتبة
القياسية ممنوعةٌ بحارسٍ في `core/tests/test_docs_freshness.py`، لأنها تُزيح
يوم الحضور ساعتين مرّتين في السنة بلا أن يشتكي شيء.

الوحدة **محايدة مالياً**: لا قيد ولا حساب ولا مبلغ. المال يبدأ من الرواتب
حين تقرأ `AttendanceDay` (المعلم السابع)، وهنا لا شيء إلا دقائق.
"""
from __future__ import annotations

import ipaddress
import logging
from datetime import datetime, time, timedelta
from decimal import Decimal
from math import asin, cos, radians, sin, sqrt

from django.db import transaction
from django.utils import timezone

from .models import AttendanceDay, CheckEvent, Shift, ShiftAssignment, WorkLocation

logger = logging.getLogger(__name__)

EARTH_RADIUS_M = 6_371_000.0

#: مهلةٌ بعد نهاية الوردية الليلية تبقى فيها البصمة منسوبةً ليوم بدايتها.
#: من خرج متأخّراً ساعةً أو ساعتين ما زال في مناوبة أمس؛ وما بعدها يومٌ جديد.
OVERNIGHT_GRACE = timedelta(hours=4)


def haversine_meters(lat1, lng1, lat2, lng2) -> float:
    """المسافة بين نقطتين على سطح الأرض بالأمتار.

    صيغة haversine بايثون خالصة — لا امتداد جغرافي في قاعدة البيانات ولا
    حاجة إليه: النقطة الواحدة مقابل نقطةٍ واحدة، والدقة على مقياس مئات
    الأمتار تفوق دقّة GPS الهاتف نفسه.
    """
    lat1, lng1, lat2, lng2 = (float(v) for v in (lat1, lng1, lat2, lng2))
    d_lat = radians(lat2 - lat1)
    d_lng = radians(lng2 - lng1)
    a = (
        sin(d_lat / 2) ** 2
        + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lng / 2) ** 2
    )
    return 2 * EARTH_RADIUS_M * asin(min(1.0, sqrt(a)))


def parse_ip_allowlist(raw: str) -> list:
    """يقرأ عناوين ومَدَيات CIDR من نصٍّ حرّ، ويتجاهل ما لا يُفهم بصمت.

    الحقل يكتبه إنسان في مربّع نصّ: سطرٌ فارغ أو فاصلةٌ زائدة أو نصّ ملصوق
    لا يجوز أن يُسقط الطلب — ما يُفهم يُطبَّق وما لا يُفهم يُسجَّل ويُهمل.
    """
    networks = []
    for chunk in str(raw or '').replace(',', '\n').split('\n'):
        token = chunk.strip()
        if not token:
            continue
        try:
            networks.append(ipaddress.ip_network(token, strict=False))
        except ValueError:
            logger.warning('hr.attendance: تعذّرت قراءة عنوان في قائمة الشبكات: %s', token)
    return networks


def ip_is_allowed(ip: str, allowlist: str) -> bool:
    """قائمةٌ فارغة تعني «بلا قيد شبكة» — لا «امنع الجميع»."""
    networks = parse_ip_allowlist(allowlist)
    if not networks:
        return True
    try:
        address = ipaddress.ip_address(str(ip or '').strip())
    except ValueError:
        return False
    return any(address in network for network in networks)


def candidate_locations(employee):
    """مواقع العمل التي تُقاس البصمة عليها.

    موظفٌ مربوط بموقع يُقاس عليه وحده؛ ومن تُرك بلا ربط يُقبل عند أي موقع نشط
    — بائعٌ يتنقّل بين فرعين لا يُطالَب بأن يختار أحدهما إلى الأبد.
    """
    if employee.work_location_id:
        return list(
            WorkLocation.objects.filter(pk=employee.work_location_id, is_active=True))
    return list(
        WorkLocation.objects.filter(tenant_id=employee.tenant_id, is_active=True))


class PunchDecision:
    """حصيلة فحص البصمة — تُخزَّن كما هي سواء قُبلت أو رُفضت."""

    __slots__ = ('accepted', 'reason', 'location', 'distance_m')

    def __init__(self, accepted, reason='', location=None, distance_m=None):
        self.accepted = accepted
        self.reason = reason
        self.location = location
        self.distance_m = distance_m

    def __repr__(self):  # pragma: no cover — تشخيص فقط
        return f'<PunchDecision accepted={self.accepted} reason={self.reason!r}>'


def evaluate_punch(employee, *, latitude=None, longitude=None, ip='', photo_url='') -> PunchDecision:
    """أتُقبل هذه البصمة؟ والقرار يعود بموقعه ومسافته ليُخزَّنا معه.

    الترتيب مقصود: نجرّب كل موقعٍ مرشَّح ونأخذ **أقربه**، فمن يقف بين فرعين
    يُنسب للأقرب لا لأول ما وُجد في الجدول. والرفض يحمل سبب **أقرب** موقع لا
    سبب آخر ما جُرّب، وإلا قرأ الموظف رسالةً عن فرعٍ لا يعرفه.
    """
    locations = candidate_locations(employee)
    if not locations:
        # بلا موقعٍ معرَّف لا سياسةَ تُطبَّق — والقبول هنا مقصود: شركةٌ لم تضبط
        # مواقعها بعد يجب أن تستطيع تشغيل الحضور، ثم تشدّده حين تجهز.
        return PunchDecision(True, location=None)

    has_geo = latitude is not None and longitude is not None
    best = None  # (distance, location)
    for location in locations:
        if not (has_geo and location.has_coordinates):
            continue
        distance = haversine_meters(
            latitude, longitude, location.latitude, location.longitude)
        if best is None or distance < best[0]:
            best = (distance, location)

    if best is not None:
        distance, location = best
        distance_m = int(round(distance))
        if distance <= location.radius_m:
            if location.require_photo and not str(photo_url or '').strip():
                return PunchDecision(
                    False, CheckEvent.REJECT_PHOTO_REQUIRED, location, distance_m)
            if not ip_is_allowed(ip, location.ip_allowlist):
                return PunchDecision(
                    False, CheckEvent.REJECT_IP_BLOCKED, location, distance_m)
            return PunchDecision(True, '', location, distance_m)

        # خارج النطاق — والشبكة المسموحة تُنقذ الموقف حين تسمح سياسة الموقع.
        if location.allow_ip_fallback and location.ip_allowlist.strip() \
                and ip_is_allowed(ip, location.ip_allowlist):
            if location.require_photo and not str(photo_url or '').strip():
                return PunchDecision(
                    False, CheckEvent.REJECT_PHOTO_REQUIRED, location, distance_m)
            return PunchDecision(True, '', location, distance_m)
        return PunchDecision(False, CheckEvent.REJECT_OUT_OF_RANGE, location, distance_m)

    # لا إحداثيات وصلت (أو لا إحداثيات للموقع) — يبقى مسار الشبكة وحده.
    strict = [loc for loc in locations if loc.require_geo]
    for location in locations:
        if location.allow_ip_fallback and location.ip_allowlist.strip() \
                and ip_is_allowed(ip, location.ip_allowlist):
            if location.require_photo and not str(photo_url or '').strip():
                return PunchDecision(False, CheckEvent.REJECT_PHOTO_REQUIRED, location)
            return PunchDecision(True, '', location)
    if strict:
        return PunchDecision(False, CheckEvent.REJECT_NO_GEO, strict[0])
    lenient = locations[0]
    if lenient.require_photo and not str(photo_url or '').strip():
        return PunchDecision(False, CheckEvent.REJECT_PHOTO_REQUIRED, lenient)
    return PunchDecision(True, '', lenient)


# ──────────────────────────────────────────────────────────────────────────
# الورديات ونسبة البصمة ليومها
# ──────────────────────────────────────────────────────────────────────────

def shift_for(employee, day, *, assignments=None):
    """وردية الموظف في يومٍ بعينه — آخر إسنادٍ يغطّيه.

    `assignments` تُمرَّر جاهزةً حين نحسب شهراً كاملاً، فلا يُستعلَم لكل يوم.
    """
    rows = assignments
    if rows is None:
        rows = list(
            ShiftAssignment.objects
            .filter(employee=employee)
            .select_related('shift')
            .order_by('-start_date', '-id')
        )
    for assignment in rows:
        if assignment.covers(day):
            return assignment.shift
    return None


def _period_bounds(day, start: time, end: time):
    """يحوّل فترةً من الوردية إلى لحظتين واعيتين، مع عبور منتصف الليل."""
    tz = timezone.get_current_timezone()
    begin = timezone.make_aware(datetime.combine(day, start), tz)
    finish = timezone.make_aware(datetime.combine(day, end), tz)
    if end <= start:
        finish += timedelta(days=1)
    return begin, finish


def shift_window(shift, day):
    """أوسع نافذةٍ تغطّيها وردية يومٍ ما — من أول بدايةٍ إلى آخر نهاية."""
    bounds = [_period_bounds(day, start, end) for start, end in shift.periods]
    return min(b for b, _ in bounds), max(f for _, f in bounds)


def scheduled_minutes(shift, day) -> int:
    """دقائق الدوام المقرّرة في اليوم — مجموع فتراته."""
    total = 0
    for start, end in shift.periods:
        begin, finish = _period_bounds(day, start, end)
        total += int((finish - begin).total_seconds() // 60)
    return total


def resolve_attendance_date(employee, moment, *, assignments=None):
    """اليوم الذي تُنسب إليه بصمةٌ وقعت في `moment`.

    الافتراضي يوم الساعة محلياً. والاستثناء الوحيد وردية أمس الليلية: إن كانت
    البصمة ما تزال داخل نافذتها (زائد مهلة `OVERNIGHT_GRACE`) فهي من أمس.
    """
    local_day = timezone.localdate(moment)
    previous = local_day - timedelta(days=1)
    shift = shift_for(employee, previous, assignments=assignments)
    if shift is None:
        return local_day
    _, finish = shift_window(shift, previous)
    if finish > timezone.make_aware(
            datetime.combine(local_day, time.min), timezone.get_current_timezone()) \
            and moment <= finish + OVERNIGHT_GRACE:
        return previous
    return local_day


# ──────────────────────────────────────────────────────────────────────────
# اشتقاق اليوم
# ──────────────────────────────────────────────────────────────────────────

def pair_events(events) -> list:
    """يزاوج الدخول بالخروج بالترتيب الزمني، ويُهمل ما لا زوج له.

    دخولان متتاليان: الثاني يُطرح (ضغطةٌ مكرّرة، أو نسيانُ خروج) والأول هو
    المعتمَد — لأن أول دخولٍ هو لحظةُ الوصول التي يُقاس عليها التأخير.
    خروجٌ بلا دخولٍ سابق يُهمل: لا مدّةَ تُحسب من عدم.
    """
    pairs = []
    open_in = None
    for event in events:
        if event.kind == CheckEvent.KIND_IN:
            if open_in is None:
                open_in = event
            # دخولٌ فوق دخولٍ مفتوح: نُبقي الأول ولا نفتح ثانياً.
        else:
            if open_in is not None:
                pairs.append((open_in, event))
                open_in = None
    return pairs


def worked_minutes_from(events) -> int:
    total = 0
    for start, end in pair_events(events):
        delta = int((end.ts - start.ts).total_seconds() // 60)
        if delta > 0:
            total += delta
    return total


def day_events(employee, day):
    """بصمات اليوم المعتمَدة — المرفوضة والمُبطَلة خارج الحساب دائماً."""
    return list(
        CheckEvent.objects
        .filter(employee=employee, attendance_date=day, accepted=True, is_voided=False)
        .order_by('ts', 'id')
    )


def absence_requires_shift(tenant_id) -> bool:
    """هل يُشترط وجود وردية مُسنَدة قبل إعلان الغياب؟ (افتراضي: نعم).

    شركةٌ بلا صفّ إعدادات بعد تُعامَل بالافتراضي المتحفّظ — لا غياب بلا جدول.
    """
    from tenants.models import TenantSettings  # noqa: PLC0415 — كسولٌ لتفادي دورة الاستيراد

    value = (
        TenantSettings.objects
        .filter(tenant_id=tenant_id)
        .values_list('hr_absence_requires_shift', flat=True)
        .first()
    )
    return True if value is None else bool(value)


def _day_context(employee, day):
    """حقائق اليوم التي لا تأتي من البصمات — عطلةٌ رسمية أو إجازة معتمَدة.

    تُحلّ كسولاً كي يبقى محرّك الحضور مستقلاً عن وحدة الإجازات: قبل بنائها
    يعمل هذا بلا شيء، وبعدها يجدها بلا تعديل هنا.
    """
    holiday = None
    leave = None
    try:
        from .models import Holiday  # noqa: PLC0415 — اختياريّ بحسب المعلم
    except ImportError:  # pragma: no cover
        Holiday = None
    if Holiday is not None:
        holiday = Holiday.objects.filter(tenant_id=employee.tenant_id, date=day).first()
    try:
        from .leave import approved_leave_on  # noqa: PLC0415
    except ImportError:
        approved_leave_on = None
    if approved_leave_on is not None:
        leave = approved_leave_on(employee, day)
    return holiday, leave


@transaction.atomic
def recompute_attendance_day(employee, day, *, assignments=None, strict_absence=None) -> AttendanceDay:
    """يُعيد بناء يوم الحضور من بصماته — حتميّاً ومهما تكرّر.

    القفل على الصفّ مقصود: بصمتان متزامنتان (ضغطتان متتاليتان من الهاتف)
    كانتا تتسابقان على `update_or_create` فتُسقط إحداهما الأخرى بقيد الفرادة.

    والتصحيح اليدوي (`is_manual_override`) لا يُكتسح: من صحّح يوماً بيده أعلن
    أن البصمات لا تحكيه، وإعادةُ الحساب لا تنقض قراره.
    """
    existing = (
        AttendanceDay.objects
        .select_for_update()
        .filter(employee=employee, date=day)
        .first()
    )
    if existing is not None and existing.is_manual_override:
        return existing

    shift = shift_for(employee, day, assignments=assignments)
    events = day_events(employee, day)
    holiday, leave = _day_context(employee, day)

    worked = worked_minutes_from(events)
    first_in = next((e.ts for e in events if e.kind == CheckEvent.KIND_IN), None)
    last_out = next((e.ts for e in reversed(events) if e.kind == CheckEvent.KIND_OUT), None)

    late = 0
    early = 0
    overtime = 0
    planned = 0

    if shift is not None:
        planned = scheduled_minutes(shift, day)
        if first_in is not None:
            begin, _ = _period_bounds(day, *shift.periods[0])
            allowed = begin + timedelta(minutes=shift.grace_minutes)
            if first_in > allowed:
                late = int((first_in - allowed).total_seconds() // 60)
        if last_out is not None:
            _, finish = shift_window(shift, day)
            if last_out < finish:
                early = int((finish - last_out).total_seconds() // 60)
        if worked > planned:
            extra = worked - planned
            if extra > shift.overtime_after_minutes:
                overtime = extra - shift.overtime_after_minutes

    if strict_absence is None:
        strict_absence = absence_requires_shift(employee.tenant_id)
    status, absence = _resolve_status(
        shift=shift, day=day, events=events, late=late, holiday=holiday, leave=leave,
        strict_absence=strict_absence,
    )

    values = {
        'tenant_id': employee.tenant_id,
        'shift': shift,
        'status': status,
        'worked_minutes': max(0, worked),
        'late_minutes': max(0, late),
        'early_leave_minutes': max(0, early),
        'overtime_minutes': max(0, overtime),
        'scheduled_minutes': max(0, planned),
        'absence_days': absence,
        'first_in': first_in,
        'last_out': last_out,
    }
    day_row, _created = AttendanceDay.objects.update_or_create(
        employee=employee, date=day, defaults=values)
    return day_row


def _resolve_status(*, shift, day, events, late, holiday, leave, strict_absence=True):
    """حالة اليوم وأيام غيابه — بترتيبٍ يغلب فيه العذرُ الغياب.

    العطلة الرسمية أولاً ثم الإجازة المعتمدة ثم العطلة الأسبوعية: يومٌ لا
    دوام فيه أصلاً لا يُسأل صاحبه عن بصمة. وبعدها فقط يُنظر في البصمات.
    """
    if holiday is not None:
        return AttendanceDay.STATUS_HOLIDAY, Decimal('0')
    if leave is not None:
        # الإجازة غير المدفوعة تُسجَّل إجازةً في السجل الإداري ويوماً مخصوماً
        # في المال — الحقيقتان مختلفتان ولا تُدمجان.
        unpaid = not getattr(getattr(leave, 'leave_type', None), 'is_paid', True)
        return AttendanceDay.STATUS_LEAVE, (Decimal('1') if unpaid else Decimal('0'))
    if shift is None:
        # بلا وردية لا يُعرف المتوقَّع. الافتراضي ألّا يُعلَن غياب: الشركة التي
        # لم تبنِ جداولها بعد لا يجوز أن تستيقظ على موظفيها كلّهم «غائبين»
        # بأثرٍ مالي في المسير. ومن أرادها صارمة يُطفئ العَلَم في الإعدادات.
        if strict_absence or events:
            return AttendanceDay.STATUS_UNSCHEDULED, Decimal('0')
        return AttendanceDay.STATUS_ABSENT, Decimal('1')
    if shift.is_weekly_off(day.weekday()):
        return AttendanceDay.STATUS_OFF, Decimal('0')
    if not events:
        return AttendanceDay.STATUS_ABSENT, Decimal('1')
    if late > 0:
        return AttendanceDay.STATUS_LATE, Decimal('0')
    return AttendanceDay.STATUS_PRESENT, Decimal('0')


def record_punch(employee, *, kind, moment=None, source=CheckEvent.SOURCE_ESS,
                 latitude=None, longitude=None, accuracy_m=None, ip='', photo_url='',
                 user=None, notes='') -> CheckEvent:
    """يسجّل بصمةً — مقبولةً أو مرفوضة — ثم يعيد حساب يومها إن قُبلت.

    المرفوضة تُحفظ ولا تُعيد الحساب: هي واقعةٌ إدارية لا ساعةُ عمل.
    """
    moment = moment or timezone.now()
    decision = evaluate_punch(
        employee, latitude=latitude, longitude=longitude, ip=ip, photo_url=photo_url)
    attendance_date = resolve_attendance_date(employee, moment)

    event = CheckEvent.objects.create(
        tenant_id=employee.tenant_id,
        employee=employee,
        kind=kind,
        ts=moment,
        attendance_date=attendance_date,
        source=source,
        latitude=latitude,
        longitude=longitude,
        accuracy_m=accuracy_m,
        distance_m=decision.distance_m,
        ip=str(ip or '')[:45],
        photo_url=str(photo_url or ''),
        work_location=decision.location,
        accepted=decision.accepted,
        reject_reason=decision.reason,
        created_by=user,
        notes=notes,
    )
    if decision.accepted:
        recompute_attendance_day(employee, attendance_date)
    return event


def open_check_in(employee):
    """آخر دخولٍ لم يُقابله خروج — مصدرُ العدّاد الحيّ في الخدمة الذاتية.

    الحساب خادميّ لأن العدّاد يقيس مالاً في النهاية؛ الواجهة تتلقّى لحظة
    البدء وتَعُدّ منها، ولا تخترعها.
    """
    today = timezone.localdate()
    events = list(
        CheckEvent.objects
        .filter(
            employee=employee,
            accepted=True,
            is_voided=False,
            attendance_date__gte=today - timedelta(days=1),
        )
        .order_by('ts', 'id')
    )
    open_event = None
    for event in events:
        if event.kind == CheckEvent.KIND_IN:
            if open_event is None:
                open_event = event
        else:
            open_event = None
    return open_event
