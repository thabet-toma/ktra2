"""T-HR — تقارير وحدة الموارد البشرية المرخّصة (`hr_suite`).

منفصلةٌ عن `core/reports/hr.py` عمداً: تلك تقارير الرواتب القديمة **المفتوحة
لكل شركة**، وهذه تقارير الوحدة — كلّها تحمل `module="hr_suite"` فتردّ الفهرسُ
والتشغيلُ **404** لشركةٍ غير مرخّصة (`core/reports_api.py::_authorize`).

**ولا حساب جديد هنا.** كل رقمٍ في هذه التقارير مقروءٌ من `AttendanceDay`
كما اشتقّه `hr/attendance.py` — تقريرٌ يُعيد حساب ما حُسب يصير مصدرَ حقيقةٍ
ثانياً ينزاح عن الأول بلا أن يشتكي أحد.
"""
from __future__ import annotations

import datetime
import logging

from django.db.models import Count, Q, Sum
from django.utils import timezone

logger = logging.getLogger("core.reports")

from ._framework import (
    DATE_FILTERS,
    KIND_DATE,
    KIND_INT,
    KIND_NUMBER,
    KIND_TEXT,
    ReportColumn,
    ReportFilter,
    ReportSpec,
    _date_range,
    register,
)

MODULE = "hr_suite"
PERM = "hr.attendance.view"

#: سقف الفترة في شبكة الأيام — عمودٌ لكل يوم، نفس حارس كشف الساعات القائم.
GRID_MAX_DAYS = 31

#: من الإثنين إلى الأحد كترتيب `date.weekday()` — نفس ترتيب `Shift.weekly_off_days`.
_WEEKDAYS = ("إث", "ثل", "أر", "خم", "جم", "سب", "أح")

#: رمزُ كل حالة في خانة الشبكة. الخانة تقول **ماذا حدث** لا رقماً فقط، لأن
#: الكشف يُراجَع بالعين قبل أن يصير خصماً في الراتب.
_STATUS_MARK = {
    "present": "✓",
    "late": "ت",
    "absent": "غ",
    "leave": "إ",
    "holiday": "ع",
    "off": "—",
    "unscheduled": "·",
}


def _period(params: dict, *, cap: int | None = None):
    """فترة التقرير — الشهر الحالي حين لا يُحدَّد شيء، ومحروسةً بسقفها."""
    from rest_framework.exceptions import ValidationError

    start, end = _date_range(params)
    if not start or not end:
        # `localdate` لا نظيرتها الساذجة: الخادم بتوقيت UTC يقلب «هذا الشهر»
        # يوماً كاملاً حول رأس الشهر — مصدر «اليوم» واحد في المشروع كله.
        today = timezone.localdate()
        start = today.replace(day=1)
        end = (start + datetime.timedelta(days=32)).replace(day=1) \
            - datetime.timedelta(days=1)
    if end < start:
        raise ValidationError("نهاية الفترة قبل بدايتها.")
    if cap and (end - start).days + 1 > cap:
        raise ValidationError(
            f"اختر فترة لا تتجاوز {cap} يوماً — الكشف عمودٌ لكل يوم.")
    return start, end


def _grid_days(params: dict) -> list[datetime.date]:
    start, end = _period(params, cap=GRID_MAX_DAYS)
    return [start + datetime.timedelta(days=i) for i in range((end - start).days + 1)]


def _scope(qs, params):
    """فلاتر مشتركة — الموظف والقسم والفرع."""
    for key, field in (
        ("employee", "employee_id"),
        ("department", "employee__department_id"),
        ("branch", "employee__branch_id"),
    ):
        raw = params.get(key)
        if str(raw or "").isdigit():
            qs = qs.filter(**{field: raw})
    return qs


# ══════════════════════════════════════════════════════════════════════
#  شبكة الحضور اليومية — الموظفون أسطراً والأيام أعمدة
# ══════════════════════════════════════════════════════════════════════

def _grid_columns(tenant_id: int, params: dict) -> tuple[ReportColumn, ...]:
    days = _grid_days(params)
    one_month = days[0].month == days[-1].month and days[0].year == days[-1].year
    return (
        ReportColumn("employee", "الموظف", width="150px"),
        *(
            ReportColumn(
                f"d{i}",
                # داخل شهرٍ واحد يكفي اليوم واسمه — واسم اليوم هو ما يجعل خانةً
                # فارغة يوم الجمعة عاديّةً وفارغةً يوم الثلاثاء سؤالاً.
                f"{day.day} {_WEEKDAYS[day.weekday()]}" if one_month
                else f"{day.day}/{day.month}",
                KIND_TEXT, width="52px",
            )
            for i, day in enumerate(days, start=1)
        ),
        ReportColumn("worked_hours", "ساعات العمل", KIND_NUMBER, total=True, width="100px"),
        ReportColumn("overtime_hours", "ساعات إضافية", KIND_NUMBER, total=True, width="100px"),
        ReportColumn("late_minutes", "دقائق التأخير", KIND_INT, total=True, width="100px"),
        ReportColumn("absence_days", "أيام الغياب", KIND_NUMBER, total=True, width="90px"),
    )


def _attendance_grid(tenant_id: int, params: dict) -> list[dict]:
    from hr.models import AttendanceDay, Employee

    days = _grid_days(params)
    day_index = {day: i for i, day in enumerate(days, start=1)}

    employees = Employee.objects.filter(tenant_id=tenant_id, is_active=True)
    if str(params.get("employee") or "").isdigit():
        employees = employees.filter(pk=params["employee"])
    if str(params.get("department") or "").isdigit():
        employees = employees.filter(department_id=params["department"])
    if str(params.get("branch") or "").isdigit():
        employees = employees.filter(branch_id=params["branch"])
    employees = list(employees.order_by("name").values("id", "name"))
    if not employees:
        return []

    rows = {
        row["id"]: {"employee": row["name"], "row_employee": row["id"],
                    "worked": 0, "overtime": 0, "late": 0, "absence": 0}
        for row in employees
    }

    # استعلامٌ واحد لكل الموظفين والأيام معاً — لا استعلام لكل صف.
    stored = (
        AttendanceDay.objects
        .filter(
            tenant_id=tenant_id, employee_id__in=list(rows),
            date__gte=days[0], date__lte=days[-1],
        )
        .values("employee_id", "date", "status", "worked_minutes",
                "overtime_minutes", "late_minutes", "absence_days")
    )
    for record in stored:
        bucket = rows.get(record["employee_id"])
        if bucket is None:
            continue
        index = day_index.get(record["date"])
        if index is not None:
            mark = _STATUS_MARK.get(record["status"], "·")
            if record["status"] == "late" and record["late_minutes"]:
                mark = f"ت {record['late_minutes']}"
            bucket[f"d{index}"] = mark
        bucket["worked"] += record["worked_minutes"] or 0
        bucket["overtime"] += record["overtime_minutes"] or 0
        bucket["late"] += record["late_minutes"] or 0
        bucket["absence"] += float(record["absence_days"] or 0)

    out = []
    for bucket in rows.values():
        worked = bucket.pop("worked")
        overtime = bucket.pop("overtime")
        late = bucket.pop("late")
        absence = bucket.pop("absence")
        bucket["worked_hours"] = round(worked / 60, 2)
        bucket["overtime_hours"] = round(overtime / 60, 2)
        bucket["late_minutes"] = late
        bucket["absence_days"] = round(absence, 2)
        out.append(bucket)
    return out


register(ReportSpec(
    key="hr-attendance-grid",
    title="شبكة الحضور اليومية",
    category="hr",
    module=MODULE,
    permission=PERM,
    description="صفٌّ لكل موظف وعمودٌ لكل يوم: حاضر · متأخّر · غائب · إجازة — ومجاميع الفترة.",
    filters=DATE_FILTERS,
    columns=(ReportColumn("employee", "الموظف"),),
    columns_for=_grid_columns,
    build=_attendance_grid,
))


# ══════════════════════════════════════════════════════════════════════
#  ملخّص الحضور والانضباط — نسبة الحضور لكل موظف
# ══════════════════════════════════════════════════════════════════════

def _attendance_summary(tenant_id: int, params: dict) -> list[dict]:
    from hr.models import AttendanceDay

    start, end = _period(params)
    qs = _scope(
        AttendanceDay.objects.filter(
            tenant_id=tenant_id, date__gte=start, date__lte=end),
        params,
    )
    aggregated = (
        qs.values("employee_id", "employee__name", "employee__department__name")
        .annotate(
            worked=Sum("worked_minutes"),
            overtime=Sum("overtime_minutes"),
            late=Sum("late_minutes"),
            absence=Sum("absence_days"),
            present_days=Count("id", filter=Q(status__in=("present", "late"))),
            late_days=Count("id", filter=Q(status="late")),
            absent_days=Count("id", filter=Q(status="absent")),
            leave_days=Count("id", filter=Q(status="leave")),
        )
        .order_by("employee__name")
    )

    out = []
    for row in aggregated:
        present = row["present_days"] or 0
        # المقام أيام الدوام المتوقَّعة وحدها: العطلة الأسبوعية والرسمية ليستا
        # حضوراً ولا غياباً، وإقحامُها يخفض نسبة كلِّ منتظم.
        expected = present + (row["absent_days"] or 0)
        out.append({
            "row_employee": row["employee_id"],
            "employee": row["employee__name"],
            "department": row["employee__department__name"] or "",
            "present_days": present,
            "late_days": row["late_days"] or 0,
            "absent_days": row["absent_days"] or 0,
            "leave_days": row["leave_days"] or 0,
            "worked_hours": round((row["worked"] or 0) / 60, 2),
            "overtime_hours": round((row["overtime"] or 0) / 60, 2),
            "late_minutes": row["late"] or 0,
            # نسبةٌ من صفر كذبة — تبقى فارغة لا صفراً ولا مئة.
            "attendance_rate": round(100 * present / expected, 1) if expected else "",
        })
    return out


register(ReportSpec(
    key="hr-attendance-summary",
    title="ملخّص الحضور والانضباط",
    category="hr",
    module=MODULE,
    permission=PERM,
    description="لكل موظف في الفترة: أيام حضوره وغيابه وتأخيره وساعاته ونسبة حضوره.",
    filters=DATE_FILTERS,
    columns=(
        ReportColumn("employee", "الموظف", width="160px"),
        ReportColumn("department", "القسم", width="120px"),
        ReportColumn("present_days", "أيام حضور", KIND_INT, total=True, width="90px"),
        ReportColumn("late_days", "أيام تأخير", KIND_INT, total=True, width="90px"),
        ReportColumn("absent_days", "أيام غياب", KIND_INT, total=True, width="90px"),
        ReportColumn("leave_days", "أيام إجازة", KIND_INT, total=True, width="90px"),
        ReportColumn("worked_hours", "ساعات العمل", KIND_NUMBER, total=True, width="100px"),
        ReportColumn("overtime_hours", "ساعات إضافية", KIND_NUMBER, total=True, width="100px"),
        ReportColumn("late_minutes", "دقائق التأخير", KIND_INT, total=True, width="100px"),
        ReportColumn("attendance_rate", "نسبة الحضور ٪", KIND_NUMBER, width="100px"),
    ),
    build=_attendance_summary,
))


# ══════════════════════════════════════════════════════════════════════
#  سجل البصمات — بمصدرها وموقعها، ومعها المرفوضة
# ══════════════════════════════════════════════════════════════════════

def _check_events(tenant_id: int, params: dict) -> list[dict]:
    from hr.models import CheckEvent

    start, end = _period(params)
    qs = _scope(
        CheckEvent.objects
        .filter(tenant_id=tenant_id, attendance_date__gte=start, attendance_date__lte=end)
        .select_related("employee", "work_location"),
        params,
    )
    status = str(params.get("state") or "").strip()
    if status == "rejected":
        qs = qs.filter(accepted=False)
    elif status == "accepted":
        qs = qs.filter(accepted=True, is_voided=False)
    elif status == "voided":
        qs = qs.filter(is_voided=True)

    rows = []
    for event in qs.order_by("attendance_date", "ts")[:5000]:
        rows.append({
            "row_employee": event.employee_id,
            "employee": event.employee.name,
            "date": event.attendance_date,
            "time": timezone.localtime(event.ts).strftime("%H:%M"),
            "kind": event.get_kind_display(),
            "source": event.get_source_display(),
            "state": (
                "مُبطَلة" if event.is_voided
                else "مسجَّل" if event.accepted
                else (event.get_reject_reason_display() or "مرفوضة")
            ),
            "location": event.work_location.name if event.work_location_id else "",
            "distance_m": event.distance_m if event.distance_m is not None else "",
        })
    return rows


register(ReportSpec(
    key="hr-check-events",
    title="سجل البصمات",
    category="hr",
    module=MODULE,
    permission=PERM,
    description="كل تسجيل دخول وخروج بمصدره وموقعه — ومعه المرفوض وسببه.",
    filters=DATE_FILTERS + (
        ReportFilter(
            "state", "الحالة", "select",
            options=(("", "الكل"), ("accepted", "المسجَّلة"),
                     ("rejected", "المرفوضة"), ("voided", "المُبطَلة")),
        ),
    ),
    columns=(
        ReportColumn("employee", "الموظف", width="150px"),
        ReportColumn("date", "التاريخ", KIND_DATE, width="110px"),
        ReportColumn("time", "الوقت", width="70px"),
        ReportColumn("kind", "دخول/خروج", width="90px"),
        ReportColumn("source", "المصدر", width="110px"),
        ReportColumn("state", "الحالة", width="140px"),
        ReportColumn("location", "موقع العمل", width="130px"),
        ReportColumn("distance_m", "المسافة (م)", KIND_INT, width="90px"),
    ),
    build=_check_events,
))


# ══════════════════════════════════════════════════════════════════════
#  أرصدة الإجازات — محسوبةٌ من دفترها في كل تشغيل
# ══════════════════════════════════════════════════════════════════════

def _leave_balances(tenant_id: int, params: dict) -> list:
    from hr.leave import employee_balances
    from hr.models import Employee

    employees = Employee.objects.filter(tenant_id=tenant_id, is_active=True)
    if str(params.get("employee") or "").isdigit():
        employees = employees.filter(pk=params["employee"])
    if str(params.get("department") or "").isdigit():
        employees = employees.filter(department_id=params["department"])

    year = params.get("year")
    year = int(year) if str(year or "").isdigit() else None

    rows = []
    for employee in employees.select_related("department").order_by("name"):
        for balance in employee_balances(employee, year=year):
            rows.append({
                "row_employee": employee.pk,
                "employee": employee.name,
                "department": employee.department.name if employee.department_id else "",
                "leave_type": balance["leave_type_name"],
                "accrued": str(balance["accrued"]),
                "adjusted": str(balance["adjusted"]),
                "taken": str(balance["taken"]),
                "remaining": str(balance["remaining"]),
            })
    return rows


register(ReportSpec(
    key="hr-leave-balances",
    title="أرصدة الإجازات",
    category="hr",
    module=MODULE,
    permission=PERM,
    description="لكل موظف ونوع إجازة: المستحقّ والتسويات والمستهلَك والمتبقّي.",
    filters=(),
    columns=(
        ReportColumn("employee", "الموظف", width="160px"),
        ReportColumn("department", "القسم", width="120px"),
        ReportColumn("leave_type", "نوع الإجازة", width="130px"),
        ReportColumn("accrued", "المستحقّ", KIND_NUMBER, total=True, width="90px"),
        ReportColumn("adjusted", "تسويات", KIND_NUMBER, total=True, width="90px"),
        ReportColumn("taken", "المستهلَك", KIND_NUMBER, total=True, width="90px"),
        ReportColumn("remaining", "المتبقّي", KIND_NUMBER, total=True, width="90px"),
    ),
    build=_leave_balances,
))
