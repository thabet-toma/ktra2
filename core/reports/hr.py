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
            "gross": _money(p.gross),
            "allowances": _money(p.allowances),
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
    columns=(
        ReportColumn("employee_name", "الموظف"),
        ReportColumn("period_start", "من", KIND_DATE, width="110px"),
        ReportColumn("period_end", "إلى", KIND_DATE, width="110px"),
        ReportColumn("pay_type", "نوع الأجر", width="90px"),
        ReportColumn("gross", "الأساسي", KIND_MONEY, total=True),
        ReportColumn("allowances", "بدلات", KIND_MONEY, total=True),
        ReportColumn("deductions", "خصومات", KIND_MONEY, total=True),
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

