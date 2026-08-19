"""T-REPORTS: محرّك تقارير المنصة — سجل واحد لكل تقرير.

لماذا سجلّ لا صفحة لكل تقرير: التقارير كانت متناثرة (ميزان مراجعة وقائمة دخل
وأعمار ديون…) كلٌّ بشاشته ونقطته، فكل تقرير جديد يعني صفحة كاملة. هنا يُعلن
التقرير مرّةً واحدة — عنوانه وفلاتره وأعمدته ودالّة بنائه — وتُنفَّذه نقطتان
اثنتان (`/api/reports/` للفهرس و`/api/reports/<key>/` للتشغيل)، وتعرضه شاشة
واحدة عامّة. إضافة تقرير لاحقاً = دالّة واحدة في هذا الملف.

كل بانٍ يستقبل `(tenant_id, params)` ويُعيد `list[dict]` بمفاتيح أعمدة التقرير.
المبالغ نصوص (`str(Decimal)`) كبقية المشروع — لا عوائم في المال.
"""
from __future__ import annotations

import dataclasses
import datetime
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Callable

from django.db.models import Case, DecimalField, F, Q, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone

logger = logging.getLogger("core.reports")

from ._framework import (
    DEC,
    ZERO,
    CATEGORIES,
    KIND_MONEY,
    KIND_NUMBER,
    KIND_INT,
    KIND_DATE,
    KIND_TEXT,
    ReportColumn,
    ReportFilter,
    ReportSpec,
    REPORTS,
    register,
    DATE_FILTERS,
    _parse_date,
    _date_range,
    _apply_dates,
    _int_param,
    _money,
    _qty,
    _sum,
    _money_sum,
    compute_totals,
    report_catalog,
    MAX_ROWS,
    run_report,
)

def _payslips(tenant_id: int, params: dict) -> list[dict]:
    from hr.models import Payslip

    qs = Payslip.objects.filter(tenant_id=tenant_id).select_related("employee")
    # الكشف فترةٌ لا يوم: يدخل التقرير إن تقاطعت فترته مع النطاق المطلوب.
    start, end = _date_range(params)
    if start:
        qs = qs.filter(period_end__gte=start)
    if end:
        qs = qs.filter(period_start__lte=end)
    status = params.get("status") or ""
    if status:
        qs = qs.filter(status=status)
    rows = []
    for p in qs.order_by("period_start", "id"):
        deductions = (
            Decimal(str(p.absence_deduction or 0))
            + Decimal(str(p.late_deduction or 0))
            + Decimal(str(p.other_deductions or 0))
        )
        rows.append({
            "id": p.id,
            "employee_name": p.employee.name if p.employee_id else "",
            "period_start": p.period_start,
            "period_end": p.period_end,
            "pay_type": "شهري" if p.pay_type == "monthly" else "بالساعة",
            "worked_hours": _qty(p.worked_hours),
            "absence_days": _qty(p.absence_days),
            "gross": _money(p.gross),
            "allowances": _money(p.allowances),
            "absence_deduction": _money(p.absence_deduction),
            "late_deduction": _money(p.late_deduction),
            "other_deductions": _money(p.other_deductions),
            "deductions": _money(deductions),
            "net": _money(p.net),
            "state": "مرحّل" if p.status == "posted" else "مسودّة",
        })
    return rows


register(ReportSpec(
    key="payslips",
    title="كشوف الرواتب",
    category="hr",
    description="كشف كل موظف في الفترة: الأساسي والبدلات والخصومات وصافي المستحق.",
    filters=DATE_FILTERS + (
        ReportFilter(
            "status", "الحالة", "select",
            options=(("", "الكل"), ("posted", "المرحّلة"), ("draft", "المسودّات")),
        ),
    ),
    # الخصم مفكَّك لا مدموجاً: المراجع لا يسأل «كم خُصم» بل «خُصم مقابل ماذا»،
    # وعمودٌ واحد يجمع الغياب والتأخير وما اتُّفق عليه يُجبره على فتح كل كشف
    # ليعرف. المجموع المدموج يبقى عموداً بجانبها لمن يريد الرقم الواحد.
    columns=(
        ReportColumn("employee_name", "الموظف"),
        ReportColumn("period_start", "من", KIND_DATE, width="110px"),
        ReportColumn("period_end", "إلى", KIND_DATE, width="110px"),
        ReportColumn("pay_type", "نوع الأجر", width="90px"),
        ReportColumn("worked_hours", "ساعات", KIND_NUMBER, total=True, width="80px"),
        ReportColumn("absence_days", "أيام غياب", KIND_NUMBER, total=True, width="80px"),
        ReportColumn("gross", "الأساسي", KIND_MONEY, total=True),
        ReportColumn("allowances", "بدلات", KIND_MONEY, total=True),
        ReportColumn("absence_deduction", "خصم غياب", KIND_MONEY, total=True),
        ReportColumn("late_deduction", "خصم تأخير", KIND_MONEY, total=True),
        ReportColumn("other_deductions", "خصومات أخرى", KIND_MONEY, total=True),
        ReportColumn("deductions", "مجموع الخصم", KIND_MONEY, total=True),
        ReportColumn("net", "الصافي", KIND_MONEY, total=True),
        ReportColumn("state", "الحالة", width="90px"),
    ),
    permission="hr.payroll.view",
    build=_payslips,
))


def _payroll_payments(tenant_id: int, params: dict) -> list[dict]:
    from hr.models import PayrollPayment

    qs = PayrollPayment.objects.filter(tenant_id=tenant_id).select_related(
        "employee", "cash_account",
    )
    qs = _apply_dates(qs, "date", params)
    return [{
        "id": p.id,
        "date": p.date,
        "employee_name": p.employee.name if p.employee_id else "",
        "payslip": f"#{p.payslip_id}" if p.payslip_id else "",
        "cash_account": p.cash_account.name if p.cash_account_id else "",
        "notes": (p.notes or "")[:120],
        "amount": _money(p.amount),
    } for p in qs.order_by("date", "id")]


register(ReportSpec(
    key="payroll-payments",
    title="مدفوعات الرواتب",
    category="hr",
    description="ما صُرف فعلاً للموظفين ومن أي صندوق — مقابل ما استُحقّ في الكشوف.",
    filters=DATE_FILTERS,
    columns=(
        ReportColumn("date", "التاريخ", KIND_DATE, width="110px"),
        ReportColumn("employee_name", "الموظف"),
        ReportColumn("payslip", "الكشف", width="80px"),
        ReportColumn("cash_account", "الصندوق/البنك"),
        ReportColumn("notes", "ملاحظات"),
        ReportColumn("amount", "المبلغ", KIND_MONEY, total=True),
    ),
    permission="hr.payroll.view",
    build=_payroll_payments,
))


# ══════════════════════════════════════════════════════════════════════
#  كشف الساعات اليومي
# ══════════════════════════════════════════════════════════════════════
#
# **الموظفون أسطراً والأيام أعمدة** — لا العكس. عدد الأيام محدود بطبعه (شهر =
# 31 عموداً على الأكثر) وعدد الموظفين ليس كذلك: الأسطر تتدرّج عمودياً بلا كلفة،
# بينما خمسون موظفاً أعمدةً جدولٌ لا يُقرأ ولا يُطبع. وهو عرف سجلّ الحضور الذي
# يعرفه المحاسب من Excel أصلاً.
#
# والكشف يُراجَع بالعين قبل الاعتماد، فالخانة تقول **ماذا حدث** لا رقماً فقط:
# ساعات اليوم للجزئي، و«غ» للغياب و«ت» للتأخير للدائم — وهي مادة خصمه.

#: من الإثنين إلى الأحد كترتيب `date.weekday()`.
_WEEKDAYS = ("إث", "ثل", "أر", "خم", "جم", "سب", "أح")

#: سقف الفترة: عمودٌ لكل يوم، وما فوق الشهر جدولٌ لا يُقرأ ولا يُطبع.
TIMESHEET_MAX_DAYS = 31


def _timesheet_period(params: dict) -> tuple[datetime.date, datetime.date]:
    """فترة الكشف — الشهر الحالي حين لا يُحدَّد شيء، ومحروسةً بسقف الأعمدة."""
    from rest_framework.exceptions import ValidationError

    start, end = _date_range(params)
    if not start or not end:
        # `localdate` لا `date.today`: الخادم بتوقيت UTC يقلب «هذا الشهر» يوماً
        # كاملاً حول رأس الشهر — مصدر «اليوم» واحد في المشروع كله.
        today = timezone.localdate()
        start = today.replace(day=1)
        end = (start + datetime.timedelta(days=32)).replace(day=1) \
            - datetime.timedelta(days=1)
    if end < start:
        raise ValidationError("نهاية الفترة قبل بدايتها.")
    if (end - start).days + 1 > TIMESHEET_MAX_DAYS:
        raise ValidationError(
            f"اختر فترة لا تتجاوز {TIMESHEET_MAX_DAYS} يوماً — الكشف عمودٌ لكل يوم.")
    return start, end


def _timesheet_days(params: dict) -> list[datetime.date]:
    start, end = _timesheet_period(params)
    return [start + datetime.timedelta(days=i) for i in range((end - start).days + 1)]


def _timesheet_columns(tenant_id: int, params: dict) -> tuple[ReportColumn, ...]:
    days = _timesheet_days(params)
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
                KIND_TEXT, width="58px",
            )
            for i, day in enumerate(days, start=1)
        ),
        ReportColumn("total_hours", "مجموع الساعات", KIND_NUMBER, total=True, width="100px"),
        ReportColumn("overtime_hours", "فوق الدوام", KIND_NUMBER, total=True, width="90px"),
        ReportColumn("absence_days", "أيام الغياب", KIND_NUMBER, total=True, width="90px"),
        ReportColumn("late_minutes", "دقائق التأخير", KIND_NUMBER, total=True, width="100px"),
    )


def _timesheet_daily(tenant_id: int, params: dict) -> list[dict]:
    from hr.models import AttendanceAdjustment, Employee, WorkLog

    days = _timesheet_days(params)
    start, end = days[0], days[-1]
    day_index = {day: i for i, day in enumerate(days, start=1)}

    # ثلاثة استعلامات مهما بلغ عدد الموظفين أو الأيام — الشبكة تُبنى في الذاكرة.
    logs = list(WorkLog.objects.filter(
        tenant_id=tenant_id, date__gte=start, date__lte=end,
    ).values("employee_id", "date", "hours"))
    adjustments = list(AttendanceAdjustment.objects.filter(
        tenant_id=tenant_id, date__gte=start, date__lte=end,
    ).values("employee_id", "date", "kind", "days", "minutes"))

    # النشطون كلهم — الصفر الظاهر معلومة («لم يُسجَّل له شيء») والغياب من
    # الكشف ليس معلومة. ومعهم كل من له سجلّ في الفترة وإن عُطِّل بعدها.
    with_records = ({row["employee_id"] for row in logs}
                    | {row["employee_id"] for row in adjustments})
    employees = list(Employee.objects.filter(tenant_id=tenant_id).filter(
        Q(is_active=True) | Q(id__in=with_records),
    ).order_by("name", "id"))

    cells: dict[int, dict[int, list[str]]] = {}
    hours: dict[int, Decimal] = {}
    overtime: dict[int, Decimal] = {}
    absence: dict[int, Decimal] = {}
    late: dict[int, int] = {}
    standard = {e.id: (e.standard_hours_per_day or ZERO) for e in employees}

    for row in logs:
        index = day_index.get(row["date"])
        if index is None:
            continue
        employee_id = row["employee_id"]
        worked = Decimal(str(row["hours"] or 0))
        hours[employee_id] = hours.get(employee_id, ZERO) + worked
        agreed = standard.get(employee_id) or ZERO
        if agreed and worked > agreed:
            overtime[employee_id] = overtime.get(employee_id, ZERO) + (worked - agreed)
        cells.setdefault(employee_id, {}).setdefault(index, []).append(_qty(worked))

    for row in adjustments:
        index = day_index.get(row["date"])
        if index is None:
            continue
        employee_id = row["employee_id"]
        if row["kind"] == AttendanceAdjustment.KIND_ABSENCE:
            value = Decimal(str(row["days"] or 0))
            absence[employee_id] = absence.get(employee_id, ZERO) + value
            mark = "غ" if value == 1 else f"غ {_qty(value)}"
        else:
            minutes = int(row["minutes"] or 0)
            late[employee_id] = late.get(employee_id, 0) + minutes
            mark = f"ت {minutes}"
        cells.setdefault(employee_id, {}).setdefault(index, []).append(mark)

    rows = []
    for employee in employees:
        grid = cells.get(employee.id, {})
        row = {
            "id": employee.id,
            "employee": employee.name,
            "total_hours": _qty(hours.get(employee.id, ZERO)),
            "overtime_hours": _qty(overtime.get(employee.id, ZERO)),
            "absence_days": _qty(absence.get(employee.id, ZERO)),
            "late_minutes": _qty(late.get(employee.id, 0)),
        }
        for index in day_index.values():
            row[f"d{index}"] = " · ".join(grid.get(index, ()))
        rows.append(row)
    return rows


register(ReportSpec(
    key="timesheet-daily",
    title="كشف الساعات اليومي",
    category="hr",
    description="صفٌّ لكل موظف وعمودٌ لكل يوم: ساعاته وغياباته وتأخيراته، "
                "ومجاميعها التي تُراجَع قبل اعتماد الرواتب.",
    filters=(
        # «هذا الشهر» افتراضاً: فترةٌ أوسع تصطدم بحارس الأعمدة فوراً، فيُستقبَل
        # التقرير برسالة خطأ بدل أن يُفتح على الشهر الذي يريده المستخدم أصلاً.
        ReportFilter("from", "من تاريخ", "date", default="month"),
        ReportFilter("to", "إلى تاريخ", "date", default="month"),
    ),
    # المعلَن في الفهرس أعمدة الملخّص وحدها — أعمدة الأيام لا تُعرف إلا بفترة.
    columns=(
        ReportColumn("employee", "الموظف", width="150px"),
        ReportColumn("total_hours", "مجموع الساعات", KIND_NUMBER, total=True, width="100px"),
        ReportColumn("overtime_hours", "فوق الدوام", KIND_NUMBER, total=True, width="90px"),
        ReportColumn("absence_days", "أيام الغياب", KIND_NUMBER, total=True, width="90px"),
        ReportColumn("late_minutes", "دقائق التأخير", KIND_NUMBER, total=True, width="100px"),
    ),
    columns_for=_timesheet_columns,
    permission="hr.payroll.view",
    build=_timesheet_daily,
))


# ── مسار المستند خلف السطر ────────────────────────────────────────────
# مُعلَن في مكان واحد بدل تكراره في كل تسجيل: التقرير سؤال، وسطره بابٌ إلى
# مستنده. المفاتيح الغائبة تُتجاهَل كي لا يُسقِط تقريرٌ محذوف الوحدةَ كلها.
ROW_LINKS: dict[str, str] = {
    "sales-invoices": "/sales/invoices/{id}",
    "sales-returns": "/sales/invoices/{id}",
    "sales-credit-notes": "/sales/invoices/{id}",
    "sales-deliveries": "/sales/delivery-notes/{id}",
    "purchase-invoices": "/purchase-invoices/{id}",
    "purchase-returns": "/purchase-invoices/{id}",
    "customer-balances": "/partners/{id}",
    "supplier-balances": "/partners/{id}",
    "receivables-aging": "/partners/{id}",
    "payables-aging": "/partners/{id}",
    "dormant-customers": "/partners/{id}",
    "stock-valuation": "/products/{id}",
    "low-stock": "/products/{id}",
    "import-deals": "/deals/{id}",
    "import-shipments": "/shipments/{id}",
    "journal-lines": "/accounting/journals/{id}",
}

for _key, _path in ROW_LINKS.items():
    _spec = REPORTS.get(_key)
    if _spec is not None and _spec.row_link is None:
        REPORTS[_key] = dataclasses.replace(_spec, row_link=_path)

