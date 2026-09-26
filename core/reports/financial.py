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

AGING_BUCKETS = ((0, 30), (31, 60), (61, 90), (91, None))


def _open_note_rows(tenant_id: int, *, creditor: bool) -> list[tuple]:
    """الإشعارات المدينة/الدائنة المرحّلة التي لا تُطفئ مستنداً — صفٌّ موقَّعٌ بتاريخها.

    المربوط بفاتورة شراء أو مستحقٍّ لوجستي داخلٌ في متبقّيه أصلاً فلا يُكرَّر؛ وربطُ
    فاتورة البيع مرجعٌ فقط فإشعار العميل يظهر دائماً. الموجب يزيد ما على العميل أو
    ما للدائن (مدينٌ للعميل، دائنٌ للدائن)، والسالب يُصفّيه — بالعملة الأساسية.
    """
    from partners.models import CREDITOR_PARTNER_TYPES
    from sales.models import CreditDebitNote

    qs = CreditDebitNote.objects.filter(
        tenant_id=tenant_id, status=CreditDebitNote.STATUS_POSTED,
    ).select_related("partner")
    if creditor:
        qs = qs.filter(
            partner__partner_type__in=CREDITOR_PARTNER_TYPES,
            related_purchase_invoice__isnull=True, related_clearance__isnull=True,
            related_local_shipment__isnull=True, related_shipment__isnull=True,
        )
    else:
        qs = qs.exclude(partner__partner_type__in=CREDITOR_PARTNER_TYPES)
    rows = []
    for note in qs:
        base = Decimal(str(note.amount)) * Decimal(str(note.exchange_rate or 1))
        increases = (note.note_type == CreditDebitNote.TYPE_DEBIT) != creditor
        rows.append((note.partner_id, note.partner.name, note.note_date, base if increases else -base))
    return rows


def _aging(tenant_id: int, params: dict, *, side: str) -> list[dict]:
    """أعمار الذمم بأربع خانات — المدين للعملاء والدائن للموردين.

    الأساس هو المتبقّي على المستندات المرحّلة نفسها (لا رصيد الحساب) كي يبقى
    التقرير قابلاً للتفسير سطراً سطراً.
    """
    today = _parse_date(params.get("as_of")) or timezone.localdate()
    buckets: dict = {}

    if side == "customer":
        from sales.models import SalesInvoice
        from sales.services import (
            linked_return_credit_summary,
            unapplied_sales_return_credits,
        )

        # المتبقي الخام الموجب شرطٌ لازم للصافي الموجب، فالمسدَّد لا يُحمَّل.
        docs = list(SalesInvoice.objects.filter(
            tenant_id=tenant_id,
            status=SalesInvoice.STATUS_POSTED,
            invoice_kind=SalesInvoice.INVOICE_KIND_SALE,
        ).annotate(
            _gross_remaining=F("grand_total") - F("amount_paid"),
        ).filter(_gross_remaining__gt=0).select_related("customer"))
        summaries = linked_return_credit_summary(docs)
        rows_src = [
            (d.customer_id, d.customer.name if d.customer_id else "",
             d.due_date or d.invoice_date,
             summaries[d.pk]["collectible"])
            for d in docs
        ]
        # الرصيد الدائن غير المطبَّق (مرتجعٌ لا يُطرح من أصل) يُعرض سالباً في
        # خانة عمره فيُصفّي ما على الزبون — كما في QuickBooks وOdoo — بدل أن
        # يختفي فيرتفع إجمالي الأعمار عن دفتر الزبون.
        rows_src += [
            (ret.customer_id, ret.customer.name if ret.customer_id else "",
             ret.invoice_date, -open_credit)
            for ret, open_credit in unapplied_sales_return_credits(tenant_id)
        ]
        rows_src += _open_note_rows(tenant_id, creditor=False)
    else:
        from logistics.models import PurchaseInvoice
        from logistics.services import annotate_purchase_invoice_payment_summary

        # المرحلة 5 / P0-9 (SCALABILITY_AUDIT §2 بند 1): كان هذا يستدعي
        # purchase_invoice_payment_summary لكل فاتورة، وهي ≥6 استعلامات
        # (fees + supplier_payments×allocations + payment_allocations×payment
        # + payments) على **كل** الفواتير المرحّلة منذ النشأة ⇒ ~20 ألف استعلام
        # في الطلب الواحد. النسخة المُعلَّمة تحسب الملخص نفسه بـsubqueries داخل
        # استعلام واحد، وهي المستخدَمة أصلاً في قائمة فواتير الشراء
        # (logistics/views/invoices.py:152) فالحساب واحد لا اثنان.
        docs = annotate_purchase_invoice_payment_summary(
            PurchaseInvoice.objects.filter(
                tenant_id=tenant_id, is_posted=True, is_return=False,
            ).select_related("partner")
        )
        rows_src = [
            # T-DUE: تُعمَّر بالاستحقاق كنظيرتها المدينة — كان الجانب الدائن
            # وحده يُعمَّر بتاريخ الفاتورة لأن `PurchaseInvoice` كانت بلا
            # `due_date` أصلاً، فتظهر فاتورةٌ مهلتها 60 يوماً «متأخرة» بعد 31.
            (d.partner_id, d.partner.name if d.partner_id else "",
             d.due_date or d.invoice_date,
             Decimal(str(d.list_remaining_balance or 0)))
            for d in docs
        ]
        # مستحقّات التخليص والشحن والنقل ذممٌ دائنةٌ للمخلّص والوكيل والناقل — كان
        # التقرير من فواتير الشراء وحدها فيغيب دَينهم كلّه ويقصر مجموعُه عن الدفتر.
        from logistics.domain.party_accruals import tenant_open_accruals
        rows_src += tenant_open_accruals(tenant_id)
        rows_src += _open_note_rows(tenant_id, creditor=True)

    for partner_id, partner_name, base_date, remaining in rows_src:
        # السالب رصيدٌ مقصود: دائنٌ للزبون (مرتجعٌ أو إشعارٌ دائن)، ومدينٌ على الدائن
        # (إشعارٌ مدينٌ غير مربوط). متبقّي المستندات نفسها لا يكون سالباً.
        if abs(remaining) <= DEC:
            continue
        age = (today - base_date).days if base_date else 0
        bucket = buckets.setdefault(partner_id, {
            "partner_id": partner_id, "partner_name": partner_name,
            "b0": ZERO, "b1": ZERO, "b2": ZERO, "b3": ZERO, "total": ZERO,
        })
        if age <= 30:
            bucket["b0"] += remaining
        elif age <= 60:
            bucket["b1"] += remaining
        elif age <= 90:
            bucket["b2"] += remaining
        else:
            bucket["b3"] += remaining
        bucket["total"] += remaining

    rows = [{
        "partner_id": b["partner_id"],
        "partner_name": b["partner_name"],
        "b0": _money(b["b0"]), "b1": _money(b["b1"]),
        "b2": _money(b["b2"]), "b3": _money(b["b3"]),
        "total": _money(b["total"]),
    } for b in buckets.values()]
    rows.sort(key=lambda r: Decimal(r["total"]), reverse=True)
    return rows


_AGING_COLUMNS = (
    ReportColumn("partner_name", "الطرف"),
    ReportColumn("b0", "حتى 30 يوماً", KIND_MONEY, total=True),
    ReportColumn("b1", "31 – 60", KIND_MONEY, total=True),
    ReportColumn("b2", "61 – 90", KIND_MONEY, total=True),
    ReportColumn("b3", "أكثر من 90", KIND_MONEY, total=True),
    ReportColumn("total", "الإجمالي", KIND_MONEY, total=True),
)

register(ReportSpec(
    key="receivables-aging",
    title="أعمار الذمم المدينة",
    category="partners",
    description="ما على العملاء موزَّعاً على أعمار الدين — لمتابعة التحصيل.",
    filters=(ReportFilter("as_of", "حتى تاريخ", "date"),),
    columns=_AGING_COLUMNS,
    permission="sales.customer.view",
    build=lambda t, p: _aging(t, p, side="customer"),
))

register(ReportSpec(
    key="payables-aging",
    title="أعمار الذمم الدائنة",
    category="partners",
    description="ما لنا عند الموردين موزَّعاً على أعمار الالتزام.",
    filters=(ReportFilter("as_of", "حتى تاريخ", "date"),),
    columns=_AGING_COLUMNS,
    permission="purchase.invoice.view",
    build=lambda t, p: _aging(t, p, side="supplier"),
))


def _partner_balances(tenant_id: int, params: dict, *, partner_types: tuple) -> list[dict]:
    """أرصدة الأطراف من دفتر الأستاذ — مدين ودائن ورصيد لكل حساب طرف مربوط."""
    from accounting.models import JournalLine
    from partners.models import PARTNER_TYPE_LABELS, Partner

    chosen = params.get("partner_type")
    if chosen:
        partner_types = tuple(t for t in partner_types if t == chosen)
    partners = Partner.objects.filter(
        tenant_id=tenant_id, partner_type__in=partner_types,
    ).values("id", "name", "partner_type")
    lines = JournalLine.objects.filter(
        tenant_id=tenant_id, journal__is_posted=True, partner_id__isnull=False,
    )
    lines = _apply_dates(lines, "journal__transaction_date", params)
    agg = {
        r["partner_id"]: r
        for r in lines.values("partner_id").annotate(
            debit=_money_sum("base_debit"), credit=_money_sum("base_credit"),
        )
    }
    rows = []
    for p in partners:
        r = agg.get(p["id"]) or {}
        debit = Decimal(str(r.get("debit") or 0))
        credit = Decimal(str(r.get("credit") or 0))
        balance = debit - credit
        if debit == ZERO and credit == ZERO:
            continue
        rows.append({
            "partner_id": p["id"],
            "partner_name": p["name"],
            "partner_type": PARTNER_TYPE_LABELS.get(p["partner_type"], p["partner_type"]),
            "debit": _money(debit),
            "credit": _money(credit),
            "balance": _money(abs(balance)),
            "side": "مدين" if balance > 0 else ("دائن" if balance < 0 else "متوازن"),
        })
    rows.sort(key=lambda r: Decimal(r["balance"]), reverse=True)
    return rows


_BALANCE_COLUMNS = (
    ReportColumn("partner_name", "الطرف"),
    ReportColumn("debit", "مدين", KIND_MONEY, total=True),
    ReportColumn("credit", "دائن", KIND_MONEY, total=True),
    ReportColumn("balance", "الرصيد", KIND_MONEY, total=True),
    ReportColumn("side", "الجهة", width="90px"),
)

register(ReportSpec(
    key="customer-balances",
    title="أرصدة العملاء",
    category="partners",
    description="مدين ودائن ورصيد كل عميل من واقع القيود المرحّلة.",
    filters=DATE_FILTERS,
    columns=_BALANCE_COLUMNS,
    permission="sales.customer.view",
    build=lambda t, p: _partner_balances(t, p, partner_types=("Customer",)),
))

#: الأطراف الدائنة بترتيب فلتر النوع — المورد ثم المخلّص والوكيل والناقل.
_CREDITOR_TYPES = ("Supplier", "CustomsBroker", "FreightForwarder", "LocalTransporter", "Carrier")

register(ReportSpec(
    key="supplier-balances",
    title="أرصدة الموردين والأطراف الدائنة",
    category="partners",
    description="مدين ودائن ورصيد كل مورد ومخلّص ووكيل شحن وناقل من واقع القيود المرحّلة.",
    filters=(
        *DATE_FILTERS,
        ReportFilter("partner_type", "النوع", "select", options=(
            ("Supplier", "مورد"), ("CustomsBroker", "مخلّص جمركي"), ("FreightForwarder", "وكيل شحن"),
            ("LocalTransporter", "ناقل محلي"), ("Carrier", "ناقل"),
        )),
    ),
    columns=(
        _BALANCE_COLUMNS[0],
        ReportColumn("partner_type", "النوع", width="110px"),
        *_BALANCE_COLUMNS[1:],
    ),
    permission="purchase.invoice.view",
    build=lambda t, p: _partner_balances(t, p, partner_types=_CREDITOR_TYPES),
))


def _dormant_customers(tenant_id: int, params: dict) -> list[dict]:
    from sales.services import dormant_customers

    days = _int_param(params, "days")
    rows = dormant_customers(tenant_id=tenant_id, days=days)
    return [{
        "partner_id": r.get("customer_id") or r.get("id"),
        "partner_name": r.get("customer_name") or r.get("name") or "",
        "last_invoice_date": r.get("last_invoice_date"),
        "days_since": r.get("days_since"),
        "last_invoice_total": _money(r.get("last_invoice_total")),
    } for r in rows]


register(ReportSpec(
    key="dormant-customers",
    title="العملاء المتوقّفون",
    category="partners",
    description="من لم يشترِ منذ مدّة تتجاوز عتبة الإعدادات — قائمة متابعة.",
    filters=(ReportFilter("days", "العتبة بالأيام", "text"),),
    columns=(
        ReportColumn("partner_name", "العميل"),
        ReportColumn("last_invoice_date", "آخر شراء", KIND_DATE, width="120px"),
        ReportColumn("days_since", "منذ (يوم)", KIND_INT, width="100px"),
        ReportColumn("last_invoice_total", "قيمة آخر فاتورة", KIND_MONEY, total=True),
    ),
    permission="sales.customer.view",
    build=_dormant_customers,
))


# ══════════════════════════════════════════════════════════════════════
#  المخزون
# ══════════════════════════════════════════════════════════════════════

