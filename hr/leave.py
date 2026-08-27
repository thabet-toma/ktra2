"""أرصدة الإجازات — محسوبةٌ من دفترها لا مخزَّنةٌ في عمود.

**لماذا لا عمود رصيد؟** الرصيد المخزَّن يفترق عن دفتره عند أول تعديلٍ رجعيّ
(طلبٌ أُلغي بعد اعتماده، أو تاريخ تعيينٍ صُحِّح، أو قاعدةُ استحقاقٍ تغيّرت)،
ولا يُكتشف فرقُه إلا حين يشتكي صاحبه. وهو نفس السبب الذي جعل رصيد الموظف في
الرواتب مشتقّاً من قيوده لا محفوظاً بجانبها.

المعادلة:

    الرصيد = منحةُ السنة + (استحقاقٌ شهري × شهور الخدمة في السنة)
             + تسوياتٌ يدوية − أيامٌ اعتُمدت هذه السنة

والسنة **تقويمية**: تبدأ في كانون الثاني وتنتهي في كانون الأول. سنةٌ متحرّكة
تبدأ من تاريخ تعيين كل موظف كانت تجعل جدول الأرصدة غير قابلٍ للقراءة صفّاً
بجانب صف، وهو الجدول الذي يُراجَع.

هذه الوحدة **يستوردها محرّك الحضور كسولاً** (`hr/attendance.py::_day_context`)
كي يبقى مستقلاً عنها: قبل بنائها كان يعمل بلا إجازات، وبعدها يجدها بلا تعديل
فيه.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.db.models import Q, Sum
from django.utils import timezone

from .models import EmployeeRequest, LeaveBalanceAdjustment, LeaveType

logger = logging.getLogger(__name__)

ZERO = Decimal('0')


def year_bounds(year: int):
    """حدود السنة التقويمية — شاملةٌ الطرفين."""
    import datetime

    return datetime.date(year, 1, 1), datetime.date(year, 12, 31)


def approved_leave_on(employee, day):
    """طلب الإجازة المعتمَد الذي يغطّي هذا اليوم — أو `None`.

    يستدعيها محرّك الحضور فيقلب اليوم إلى «إجازة» بدل «غياب». والاعتماد وحده
    يُحتسب: طلبٌ قيد المراجعة لا يُعفي صاحبه من الحضور بعد.
    """
    return (
        EmployeeRequest.objects
        .filter(
            employee=employee,
            kind=EmployeeRequest.KIND_LEAVE,
            status=EmployeeRequest.STATUS_APPROVED,
            date_from__lte=day,
            date_to__gte=day,
        )
        .select_related('leave_type')
        .first()
    )


def accrued_days(employee, leave_type, *, year=None, today=None) -> Decimal:
    """المستحقّ حتى اليوم: المنحة السنوية + الاستحقاق الشهري عن شهور الخدمة.

    الشهور تُعدّ من **الأكبر** بين بداية السنة وتاريخ التعيين — موظفٌ عُيّن في
    تموز لا يستحقّ عن شهور لم يعمل فيها، وموظفٌ قديم لا يُحرم من أول السنة.
    """
    today = today or timezone.localdate()
    year = year or today.year
    start, end = year_bounds(year)
    horizon = min(today, end)
    if horizon < start:
        return ZERO

    grant = leave_type.annual_grant or ZERO
    monthly = leave_type.monthly_accrual or ZERO
    if monthly <= 0:
        return grant

    begin = start
    if employee.hire_date and employee.hire_date > begin:
        begin = employee.hire_date
    if begin > horizon:
        return ZERO
    months = (horizon.year - begin.year) * 12 + (horizon.month - begin.month) + 1
    return grant + monthly * Decimal(max(0, months))


def taken_days(employee, leave_type, *, year=None) -> Decimal:
    """الأيام المعتمَدة من هذا النوع داخل السنة.

    الطلب المعتمَد وحده يُخصم — والملغى بعد اعتماده يعود رصيده تلقائياً لأن
    الحساب يقرأ الحالة الراهنة لا لقطةً وقت الاعتماد.
    """
    year = year or timezone.localdate().year
    start, end = year_bounds(year)
    rows = (
        EmployeeRequest.objects
        .filter(
            employee=employee,
            leave_type=leave_type,
            status=EmployeeRequest.STATUS_APPROVED,
            date_from__lte=end,
            date_to__gte=start,
        )
        .values_list('date_from', 'date_to')
    )
    total = ZERO
    for date_from, date_to in rows:
        # الطلب العابر لحدّ السنة يُقصّ عليها — لا تُحمَّل سنةٌ أيامَ غيرها.
        first = max(date_from, start)
        last = min(date_to, end)
        if last >= first:
            total += Decimal((last - first).days + 1)
    return total


def adjusted_days(employee, leave_type, *, year=None) -> Decimal:
    """مجموع التسويات اليدوية داخل السنة — موجبُها يمنح وسالبُها يخصم."""
    year = year or timezone.localdate().year
    start, end = year_bounds(year)
    total = (
        LeaveBalanceAdjustment.objects
        .filter(
            employee=employee, leave_type=leave_type,
            date__gte=start, date__lte=end,
        )
        .aggregate(total=Sum('days'))['total']
    )
    return total or ZERO


def leave_balance(employee, leave_type, *, year=None, today=None) -> dict:
    """رصيد نوعٍ واحد لموظف واحد — مفكَّكاً كي يُقرأ سببُ الرقم لا الرقم وحده."""
    today = today or timezone.localdate()
    year = year or today.year
    accrued = accrued_days(employee, leave_type, year=year, today=today)
    taken = taken_days(employee, leave_type, year=year)
    adjusted = adjusted_days(employee, leave_type, year=year)
    return {
        'leave_type': leave_type.pk,
        'leave_type_name': leave_type.name,
        'is_paid': leave_type.is_paid,
        'year': year,
        'accrued': accrued,
        'adjusted': adjusted,
        'taken': taken,
        'remaining': accrued + adjusted - taken,
    }


def employee_balances(employee, *, year=None, today=None) -> list:
    """أرصدة كل أنواع الإجازات النشطة لموظف."""
    types = LeaveType.objects.filter(tenant_id=employee.tenant_id, is_active=True)
    return [leave_balance(employee, t, year=year, today=today) for t in types]


def pending_days(employee, leave_type, *, exclude_request=None) -> Decimal:
    """أيامٌ في طلباتٍ قيد المراجعة — تُحجَز فلا يُنفَق الرصيد مرّتين.

    بلا هذا يقدّم الموظف ثلاثة طلبات بكامل رصيده فتمرّ كلّها لأن كلاً منها
    وحده يكفيه الرصيد.
    """
    qs = EmployeeRequest.objects.filter(
        employee=employee,
        leave_type=leave_type,
        status=EmployeeRequest.STATUS_PENDING,
    )
    if exclude_request is not None:
        qs = qs.exclude(pk=exclude_request)
    total = ZERO
    for date_from, date_to in qs.values_list('date_from', 'date_to'):
        if date_from and date_to and date_to >= date_from:
            total += Decimal((date_to - date_from).days + 1)
    return total


def available_days(employee, leave_type, *, exclude_request=None, today=None) -> Decimal:
    """المتاح فعلاً للطلب الآن = الرصيد ناقصَ ما هو محجوزٌ قيد المراجعة."""
    balance = leave_balance(employee, leave_type, today=today)
    return balance['remaining'] - pending_days(
        employee, leave_type, exclude_request=exclude_request)
