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

def _customer_payments(tenant_id: int, params: dict) -> list[dict]:
    from sales.models import CustomerPayment

    qs = CustomerPayment.objects.filter(tenant_id=tenant_id).select_related(
        "partner", "cash_or_bank_account", "currency",
    )
    qs = _apply_dates(qs, "payment_date", params)
    partner = _int_param(params, "partner")
    if partner:
        qs = qs.filter(partner_id=partner)
    return [{
        "id": p.id,
        "number": f"#{p.id}",
        "date": p.payment_date,
        "partner_name": p.partner.name if p.partner_id else "",
        "account": (f"{p.cash_or_bank_account.code} — {p.cash_or_bank_account.name}"
                    if p.cash_or_bank_account_id else ""),
        "currency": p.currency.Code if p.currency_id else "",
        "amount": _money(p.amount),
        "status": "مرحّل" if p.is_posted else "مسودة",
    } for p in qs.order_by("payment_date", "id")]


def _supplier_payments(tenant_id: int, params: dict) -> list[dict]:
    from sales.models import SupplierPayment

    qs = SupplierPayment.objects.filter(tenant_id=tenant_id).select_related(
        "partner", "cash_or_bank_account", "currency",
    )
    qs = _apply_dates(qs, "payment_date", params)
    partner = _int_param(params, "partner")
    if partner:
        qs = qs.filter(partner_id=partner)
    return [{
        "id": p.id,
        "number": f"#{p.id}",
        "date": p.payment_date,
        "partner_name": p.partner.name if p.partner_id else "",
        "account": (f"{p.cash_or_bank_account.code} — {p.cash_or_bank_account.name}"
                    if p.cash_or_bank_account_id else ""),
        "currency": p.currency.Code if p.currency_id else "",
        "amount": _money(p.amount),
        "status": "مرحّل" if p.is_posted else "مسودة",
    } for p in qs.order_by("payment_date", "id")]


_VOUCHER_COLUMNS = (
    ReportColumn("number", "رقم السند", width="100px"),
    ReportColumn("date", "التاريخ", KIND_DATE, width="110px"),
    ReportColumn("partner_name", "الطرف"),
    ReportColumn("account", "الصندوق / البنك"),
    ReportColumn("currency", "العملة", width="80px"),
    ReportColumn("amount", "المبلغ", KIND_MONEY, total=True),
    ReportColumn("status", "الحالة", width="90px"),
)

register(ReportSpec(
    key="customer-payments",
    title="سندات القبض",
    category="finance",
    description="ما قُبض من العملاء وإلى أي صندوق أو بنك دخل.",
    filters=DATE_FILTERS + (ReportFilter("partner", "العميل", "customer"),),
    columns=_VOUCHER_COLUMNS,
    permission="sales.payment.create",
    build=_customer_payments,
))

register(ReportSpec(
    key="supplier-payments",
    title="سندات الصرف",
    category="finance",
    description="ما صُرف للموردين ومن أي صندوق أو بنك خرج.",
    filters=DATE_FILTERS + (ReportFilter("partner", "المورد", "supplier"),),
    columns=_VOUCHER_COLUMNS,
    permission="purchase.payment.create",
    build=_supplier_payments,
))


def _cash_movements(tenant_id: int, params: dict) -> list[dict]:
    """حركة الصناديق والبنوك من أسطر القيود المرحّلة على حسابات النقدية."""
    from accounting.models import Account, JournalLine
    from accounting.services import _without_partner_accounts

    # فرعان لا فرعٌ واحد: السلالة المعيارية **تعريفٌ** لا تخمين، والاسم تخمينٌ
    # وحده — فحسابات الأطراف تُستبعد من الفرع الثاني وحده. `accounting/api.py`
    # (`sync_partner_accounting`) يسمّي حساب الطرف باسم صاحبه، فزبونٌ اسمه
    # «صندوق التوفير» كانت ذمّته تُعرَض حركةً في الخزينة: تقريرٌ يُظهر ديناً على
    # زبون نقداً في الصندوق. لا قيد يُكتب هنا — لكن القرار يُقرأ من هنا.
    #
    # ولا `is_active=True` عمداً، بخلاف `accounting/services.py`
    # (`resolve_cash_account`): ذاك يختار **أين يذهب مالٌ جديد** فالمعطَّل ممنوع،
    # وهذا يعرض **ما جرى فعلاً** فصندوقٌ عُطّل الشهر الماضي حركتُه حقيقيةٌ
    # مرحّلة، وإخفاؤها يجعل التقرير لا يطابق الأستاذ بلا أن يقول لماذا.
    base = Account.objects.filter(tenant_id=tenant_id, account_type="Asset")
    by_lineage = base.filter(
        Q(code__startswith="1101") | Q(code__startswith="1102")
        | Q(code__startswith="1110"),
    )
    by_name = _without_partner_accounts(
        base.filter(Q(name__icontains="صندوق") | Q(name__icontains="بنك")),
        tenant_id,
    )
    account_ids = (
        set(by_lineage.values_list("id", flat=True))
        | set(by_name.values_list("id", flat=True))
    )
    account = _int_param(params, "account")
    if account:
        account_ids &= {account}

    qs = JournalLine.objects.filter(
        tenant_id=tenant_id, journal__is_posted=True,
        account_id__in=account_ids,
    ).select_related("journal", "account", "partner")
    qs = _apply_dates(qs, "journal__transaction_date", params)

    rows = []
    for line in qs.order_by("journal__transaction_date", "id"):
        debit = Decimal(str(line.base_debit or 0))
        credit = Decimal(str(line.base_credit or 0))
        rows.append({
            "date": line.journal.transaction_date,
            "account": f"{line.account.code} — {line.account.name}",
            "journal": f"#{line.journal_id}",
            "reference": line.journal.reference_type or "",
            "partner_name": line.partner.name if line.partner_id else "",
            "description": (line.description or line.journal.description or "")[:120],
            "inflow": _money(debit),
            "outflow": _money(credit),
            "net": _money(debit - credit),
        })
    return rows


register(ReportSpec(
    key="cash-bank-movements",
    title="حركة الصناديق والبنوك",
    category="finance",
    description="كل دخول وخروج نقدي من واقع القيود المرحّلة على حسابات النقدية.",
    filters=DATE_FILTERS + (ReportFilter("account", "الصندوق / البنك", "cash_account"),),
    columns=(
        ReportColumn("date", "التاريخ", KIND_DATE, width="110px"),
        ReportColumn("account", "الحساب"),
        ReportColumn("journal", "القيد", width="80px"),
        ReportColumn("reference", "المصدر", width="150px"),
        ReportColumn("partner_name", "الطرف"),
        ReportColumn("description", "البيان"),
        ReportColumn("inflow", "وارد", KIND_MONEY, total=True),
        ReportColumn("outflow", "صادر", KIND_MONEY, total=True),
        ReportColumn("net", "الصافي", KIND_MONEY, total=True),
    ),
    permission="accounting.report.view",
    build=_cash_movements,
))


def _cheques(tenant_id: int, params: dict) -> list[dict]:
    from accounting.models import Cheque

    qs = Cheque.objects.filter(tenant_id=tenant_id).select_related("partner", "currency")
    qs = _apply_dates(qs, "due_date", params)
    direction = (params.get("direction") or "").strip()
    if direction in ("Incoming", "Outgoing"):
        qs = qs.filter(direction=direction)
    status = (params.get("status") or "").strip()
    if status:
        qs = qs.filter(status=status)
    return [{
        "id": c.id,
        "cheque_number": c.cheque_number,
        "direction": "وارد" if c.direction == "Incoming" else "صادر",
        "partner_name": c.partner.name if c.partner_id else (c.payee_name or ""),
        "bank_name": c.bank_name or "",
        "issue_date": c.issue_date,
        "due_date": c.due_date,
        "status": c.status,
        "amount": _money(c.amount),
    } for c in qs.order_by("due_date", "id")]


register(ReportSpec(
    key="cheques",
    title="الشيكات",
    category="finance",
    description="الشيكات الواردة والصادرة بحالاتها واستحقاقها — متابعة الأوراق المالية.",
    filters=DATE_FILTERS + (
        ReportFilter("direction", "الاتجاه", "select", options=(
            ("", "الكل"), ("Incoming", "وارد"), ("Outgoing", "صادر"),
        )),
        ReportFilter("status", "الحالة", "select", options=(
            ("", "الكل"), ("Draft", "مسودة"), ("Under_Collection", "برسم التحصيل"),
            ("Collected", "محصَّل"), ("Bounced", "مرتدّ"),
            ("Returned", "مُعاد"), ("Settled", "مسوّى"),
        )),
    ),
    columns=(
        ReportColumn("cheque_number", "رقم الشيك", width="120px"),
        ReportColumn("direction", "الاتجاه", width="80px"),
        ReportColumn("partner_name", "الطرف"),
        ReportColumn("bank_name", "البنك", width="140px"),
        ReportColumn("issue_date", "الإصدار", KIND_DATE, width="110px"),
        ReportColumn("due_date", "الاستحقاق", KIND_DATE, width="110px"),
        ReportColumn("status", "الحالة", width="120px"),
        ReportColumn("amount", "المبلغ", KIND_MONEY, total=True),
    ),
    permission="accounting.report.view",
    build=_cheques,
))


def _cheques_maturity(tenant_id: int, params: dict) -> list[dict]:
    """CHQ-3 — استحقاق الشيكات أسبوعاً بأسبوع بصافيها التراكمي.

    الأرقام كلها من `accounting.services` (`cheque_maturity_timeline`) — نفس
    تعريف «المفتوح» الذي تقرأه محفظة الشيكات. هنا عرضٌ فقط: لا حساب ثانٍ.
    """
    from accounting.services import cheque_maturity_timeline

    data = cheque_maturity_timeline(
        tenant_id, today=_parse_date(params.get("as_of")))
    rows = [{
        "period_key": r["key"],
        "period": r["label"],
        "due_from": r["from"],
        "due_to": r["to"],
        "incoming_count": r["incoming_count"],
        "incoming": r["incoming"],
        "outgoing_count": r["outgoing_count"],
        "outgoing": r["outgoing"],
        "net": r["net"],
        "cumulative_net": r["cumulative_net"],
    } for r in data["rows"]]

    # الشيكات بلا تاريخ استحقاق: مبلغها يُعرض كي لا يختفي، وخانة التراكمي
    # تبقى فارغة (تظهر «—») — ورقةٌ بلا تاريخ لا موضع لها على خطّ زمني.
    undated = data["undated"]
    if undated["incoming_count"] or undated["outgoing_count"]:
        rows.append({
            "period_key": undated["key"],
            "period": undated["label"],
            "due_from": None,
            "due_to": None,
            "incoming_count": undated["incoming_count"],
            "incoming": undated["incoming"],
            "outgoing_count": undated["outgoing_count"],
            "outgoing": undated["outgoing"],
            "net": undated["net"],
            "cumulative_net": "",
        })
    return rows


register(ReportSpec(
    key="cheques-maturity",
    title="استحقاق الشيكات وأثر السيولة",
    category="finance",
    description=(
        "الشيكات المفتوحة أسبوعاً بأسبوع على أفق 90 يوماً — الوارد المستحق "
        "والصادر المستحق وصافيهما، والصافي التراكمي الذي يُظهر ما يبقى في اليد "
        "لو حُصِّل كل وارد وصُرف كل صادر في موعده. المتأخر يظهر أولاً وما بعد "
        "الأفق آخراً؛ والشيكات بلا تاريخ استحقاق تُعرض في سطرها الأخير خارج "
        "الخطّ الزمني."
    ),
    filters=(ReportFilter("as_of", "اعتباراً من", "date"),),
    columns=(
        ReportColumn("period", "الفترة", width="150px"),
        ReportColumn("due_from", "من", KIND_DATE, width="110px"),
        ReportColumn("due_to", "إلى", KIND_DATE, width="110px"),
        ReportColumn("incoming_count", "عدد الوارد", KIND_INT, total=True, width="90px"),
        ReportColumn("incoming", "وارد مستحق", KIND_MONEY, total=True),
        ReportColumn("outgoing_count", "عدد الصادر", KIND_INT, total=True, width="90px"),
        ReportColumn("outgoing", "صادر مستحق", KIND_MONEY, total=True),
        ReportColumn("net", "الصافي", KIND_MONEY, total=True),
        # الصافي التراكمي رصيدٌ جارٍ لا مبلغ — جمعه أسفل الجدول بلا معنى.
        ReportColumn("cumulative_net", "الصافي التراكمي", KIND_MONEY),
    ),
    permission="accounting.report.view",
    build=_cheques_maturity,
))


def _journal_lines(tenant_id: int, params: dict) -> list[dict]:
    from accounting.models import JournalLine

    qs = JournalLine.objects.filter(
        tenant_id=tenant_id, journal__is_posted=True,
    ).select_related("journal", "account", "partner")
    qs = _apply_dates(qs, "journal__transaction_date", params)
    account = _int_param(params, "account")
    if account:
        qs = qs.filter(account_id=account)
    return [{
        "date": l.journal.transaction_date,
        "journal": f"#{l.journal_id}",
        "reference": l.journal.reference_type or "",
        "account": f"{l.account.code} — {l.account.name}" if l.account_id else "",
        "partner_name": l.partner.name if l.partner_id else "",
        "description": (l.description or l.journal.description or "")[:120],
        "debit": _money(l.base_debit),
        "credit": _money(l.base_credit),
    } for l in qs.order_by("journal__transaction_date", "journal_id", "id")]


register(ReportSpec(
    key="journal-lines",
    title="دفتر اليومية التفصيلي",
    category="accounting",
    description="كل سطر قيد مرحّل في الفترة — الأساس الذي تُشتقّ منه بقية التقارير.",
    filters=DATE_FILTERS + (ReportFilter("account", "الحساب", "account"),),
    columns=(
        ReportColumn("date", "التاريخ", KIND_DATE, width="110px"),
        ReportColumn("journal", "القيد", width="80px"),
        ReportColumn("reference", "المصدر", width="150px"),
        ReportColumn("account", "الحساب"),
        ReportColumn("partner_name", "الطرف"),
        ReportColumn("description", "البيان"),
        ReportColumn("debit", "مدين", KIND_MONEY, total=True),
        ReportColumn("credit", "دائن", KIND_MONEY, total=True),
    ),
    permission="accounting.journal.view",
    build=_journal_lines,
))


# ══════════════════════════════════════════════════════════════════════
#  الاستيراد
# ══════════════════════════════════════════════════════════════════════

