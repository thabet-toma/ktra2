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

def _import_deals(tenant_id: int, params: dict) -> list[dict]:
    from logistics.models import LogisticsDeal

    qs = LogisticsDeal.objects.filter(tenant_id=tenant_id).select_related("partner")
    qs = _apply_dates(qs, "order_date", params)
    partner = _int_param(params, "partner")
    if partner:
        qs = qs.filter(partner_id=partner)
    return [{
        "id": d.id,
        "number": d.ref_number or d.pi_number or f"#{d.id}",
        "date": d.order_date,
        "partner_name": d.partner.name if d.partner_id else "",
        "stage": d.stage or "",
        "status": d.status or "",
        "payment_status": d.payment_status or "",
        "total": _money(d.total_amount),
        "remaining": _money(d.remaining_amount),
    } for d in qs.order_by("-id")]


register(ReportSpec(
    key="import-deals",
    title="صفقات الاستيراد",
    category="import",
    description="الصفقات ومراحلها وقيمها — نظرة واحدة على خط الاستيراد.",
    filters=DATE_FILTERS + (ReportFilter("partner", "المورد", "supplier"),),
    columns=(
        ReportColumn("number", "رقم الصفقة", width="130px"),
        ReportColumn("date", "التاريخ", KIND_DATE, width="110px"),
        ReportColumn("partner_name", "المورد"),
        ReportColumn("stage", "المرحلة", width="130px"),
        ReportColumn("status", "الحالة", width="110px"),
        ReportColumn("payment_status", "حالة الدفع", width="110px"),
        ReportColumn("total", "القيمة", KIND_MONEY, total=True),
        ReportColumn("remaining", "المتبقي", KIND_MONEY, total=True),
    ),
    permission="import.deal.manage",
    build=_import_deals,
))


def _import_shipments(tenant_id: int, params: dict) -> list[dict]:
    from logistics.models import LogisticsShipment

    qs = LogisticsShipment.objects.filter(tenant_id=tenant_id).select_related(
        "shipping_agent",
    )
    qs = _apply_dates(qs, "departure_date", params)
    return [{
        "id": sh.id,
        "number": sh.shipment_number or f"#{sh.id}",
        "departure_date": sh.departure_date,
        "arrival_date": sh.arrival_date,
        "agent": sh.shipping_agent.name if sh.shipping_agent_id else "",
        "bill_of_lading": sh.bill_of_lading or "",
        "container_number": sh.container_number or "",
        "status": sh.status or "",
        "shipping_cost": _money(sh.total_shipping_cost_usd),
        "grand_total": _money(sh.grand_total),
    } for sh in qs.order_by("-id")]


register(ReportSpec(
    key="import-shipments",
    title="الشحنات",
    category="import",
    description="الشحنات ووكلاؤها وبوالصها وحاوياتها وكلفة شحنها.",
    filters=DATE_FILTERS,
    columns=(
        ReportColumn("number", "رقم الشحنة", width="130px"),
        ReportColumn("departure_date", "المغادرة", KIND_DATE, width="110px"),
        ReportColumn("arrival_date", "الوصول", KIND_DATE, width="110px"),
        ReportColumn("agent", "وكيل الشحن"),
        ReportColumn("bill_of_lading", "بوليصة الشحن", width="140px"),
        ReportColumn("container_number", "الحاوية", width="120px"),
        ReportColumn("status", "الحالة", width="110px"),
        ReportColumn("shipping_cost", "كلفة الشحن ($)", KIND_MONEY, total=True),
        ReportColumn("grand_total", "الإجمالي", KIND_MONEY, total=True),
    ),
    permission="import.deal.manage",
    build=_import_shipments,
))


# ══════════════════════════════════════════════════════════════════════
#  T-REPORTS2 — الدفاتر + بقية مستندات المنصة
#
#  القسم كان يغطي الفواتير والمخزون وأسطر القيود، ويترك المنصّة بلا دفترٍ
#  يُدخَل عليه: كشف حساب طرف، ودفتر أستاذ حساب، واليومية العامة — وهي أكثر
#  ما يُطلب في دفترة وأودو وزوهو ويطابق سلوك «الأصيل». كلها للقراءة، ومن
#  الأسطر المرحّلة وحدها، فلا مصدر حقيقة موازٍ.
# ══════════════════════════════════════════════════════════════════════

def _partner_is_customer(tenant_id: int, partner_id: int) -> bool:
    from partners.models import Partner

    kind = (
        Partner.objects.filter(tenant_id=tenant_id, id=partner_id)
        .values_list("partner_type", flat=True).first()
    )
    return str(kind or "").lower() == "customer"


def _partner_statement(tenant_id: int, params: dict) -> list[dict]:
    """كشف حساب طرف: رصيد افتتاحي قبل الفترة + حركات الفترة برصيد جارٍ.

    نفس قاعدة `accounting.services.partner_account_statement`: للعميل
    مدين−دائن، ولغيره دائن−مدين — كي لا يقرأ الطرفان الرقم نفسه بإشارتين.
    """
    from accounting.models import JournalLine

    partner_id = _int_param(params, "partner")
    if not partner_id:
        return []
    is_customer = _partner_is_customer(tenant_id, partner_id)
    start, _end = _date_range(params)

    base = JournalLine.objects.filter(
        tenant_id=tenant_id, partner_id=partner_id, journal__is_posted=True,
    )
    opening = ZERO
    if start:
        agg = base.filter(journal__transaction_date__lt=start).aggregate(
            d=_money_sum("base_debit"), c=_money_sum("base_credit"),
        )
        d, c = Decimal(str(agg["d"] or 0)), Decimal(str(agg["c"] or 0))
        opening = (d - c) if is_customer else (c - d)

    rows = [{
        "id": None,
        "date": start,
        "journal": "",
        "reference": "",
        "description": "رصيد افتتاحي",
        "debit": _money(ZERO),
        "credit": _money(ZERO),
        "balance": _money(opening),
    }]
    running = opening
    qs = _apply_dates(base, "journal__transaction_date", params).select_related("journal")
    for line in qs.order_by("journal__transaction_date", "journal_id", "id"):
        debit = Decimal(str(line.base_debit or 0))
        credit = Decimal(str(line.base_credit or 0))
        running += (debit - credit) if is_customer else (credit - debit)
        rows.append({
            "id": line.journal_id,
            "date": line.journal.transaction_date,
            "journal": f"#{line.journal_id}",
            "reference": line.journal.reference_type or "",
            "description": (line.description or line.journal.description or "")[:140],
            "debit": _money(debit),
            "credit": _money(credit),
            "balance": _money(running),
        })
    return rows


register(ReportSpec(
    key="partner-statement",
    title="كشف حساب طرف",
    category="partners",
    description="حركة العميل أو المورد: رصيد افتتاحي، ثم كل حركة برصيد جارٍ حتى الختامي.",
    filters=(ReportFilter("partner", "الطرف", "partner"),) + DATE_FILTERS,
    columns=(
        ReportColumn("date", "التاريخ", KIND_DATE, width="110px"),
        ReportColumn("journal", "القيد", width="80px"),
        ReportColumn("reference", "المصدر", width="150px"),
        ReportColumn("description", "البيان"),
        ReportColumn("debit", "مدين", KIND_MONEY, total=True),
        ReportColumn("credit", "دائن", KIND_MONEY, total=True),
        ReportColumn("balance", "الرصيد", KIND_MONEY),
    ),
    permission="accounting.journal.view",
    row_link="/accounting/journals/{id}",
    build=_partner_statement,
))


def _account_ledger(tenant_id: int, params: dict) -> list[dict]:
    """دفتر أستاذ حساب واحد: افتتاحي + حركات الفترة برصيد جارٍ (مدين−دائن)."""
    from accounting.models import JournalLine

    account_id = _int_param(params, "account")
    if not account_id:
        return []
    start, _end = _date_range(params)
    base = JournalLine.objects.filter(
        tenant_id=tenant_id, account_id=account_id, journal__is_posted=True,
    )
    opening = ZERO
    if start:
        agg = base.filter(journal__transaction_date__lt=start).aggregate(
            d=_money_sum("base_debit"), c=_money_sum("base_credit"),
        )
        opening = Decimal(str(agg["d"] or 0)) - Decimal(str(agg["c"] or 0))

    rows = [{
        "id": None,
        "date": start,
        "journal": "",
        "reference": "",
        "partner_name": "",
        "description": "رصيد افتتاحي",
        "debit": _money(ZERO),
        "credit": _money(ZERO),
        "balance": _money(opening),
    }]
    running = opening
    qs = _apply_dates(base, "journal__transaction_date", params).select_related(
        "journal", "partner",
    )
    for line in qs.order_by("journal__transaction_date", "journal_id", "id"):
        debit = Decimal(str(line.base_debit or 0))
        credit = Decimal(str(line.base_credit or 0))
        running += debit - credit
        rows.append({
            "id": line.journal_id,
            "date": line.journal.transaction_date,
            "journal": f"#{line.journal_id}",
            "reference": line.journal.reference_type or "",
            "partner_name": line.partner.name if line.partner_id else "",
            "description": (line.description or line.journal.description or "")[:140],
            "debit": _money(debit),
            "credit": _money(credit),
            "balance": _money(running),
        })
    return rows


register(ReportSpec(
    key="account-ledger",
    title="دفتر أستاذ حساب",
    category="accounting",
    description="حركة حساب واحد من الشجرة: رصيد افتتاحي ثم كل قيد مسّه برصيد جارٍ.",
    filters=(ReportFilter("account", "الحساب", "account"),) + DATE_FILTERS,
    columns=(
        ReportColumn("date", "التاريخ", KIND_DATE, width="110px"),
        ReportColumn("journal", "القيد", width="80px"),
        ReportColumn("reference", "المصدر", width="150px"),
        ReportColumn("partner_name", "الطرف"),
        ReportColumn("description", "البيان"),
        ReportColumn("debit", "مدين", KIND_MONEY, total=True),
        ReportColumn("credit", "دائن", KIND_MONEY, total=True),
        ReportColumn("balance", "الرصيد", KIND_MONEY),
    ),
    permission="accounting.journal.view",
    row_link="/accounting/journals/{id}",
    build=_account_ledger,
))


def _general_journal(tenant_id: int, params: dict) -> list[dict]:
    """اليومية العامة: قيد في كل سطر بمجموعه — لا سطوره."""
    from accounting.models import JournalHeader

    qs = JournalHeader.objects.filter(tenant_id=tenant_id)
    posted = params.get("posted") or "posted"
    if posted == "posted":
        qs = qs.filter(is_posted=True)
    elif posted == "draft":
        qs = qs.filter(is_posted=False)
    qs = _apply_dates(qs, "transaction_date", params)
    qs = qs.annotate(
        total_debit=_money_sum("lines__base_debit"),
        total_credit=_money_sum("lines__base_credit"),
    )
    return [{
        "id": j.id,
        "journal": f"#{j.id}",
        "date": j.transaction_date,
        "reference": j.reference_type or "",
        "description": (j.description or "")[:140],
        "state": "مرحّل" if j.is_posted else "مسودّة",
        "debit": _money(j.total_debit),
        "credit": _money(j.total_credit),
    } for j in qs.order_by("transaction_date", "id")]


register(ReportSpec(
    key="general-journal",
    title="اليومية العامة",
    category="accounting",
    description="كل قيد في الفترة بمجموعه المدين والدائن — الدفتر الذي تُراجَع منه الحركة.",
    filters=DATE_FILTERS + (
        ReportFilter(
            "posted", "الحالة", "select",
            options=(("posted", "المرحّلة"), ("draft", "المسودّات"), ("all", "الكل")),
            default="posted",
        ),
    ),
    columns=(
        ReportColumn("journal", "القيد", width="80px"),
        ReportColumn("date", "التاريخ", KIND_DATE, width="110px"),
        ReportColumn("reference", "المصدر", width="160px"),
        ReportColumn("description", "البيان"),
        ReportColumn("state", "الحالة", width="90px"),
        ReportColumn("debit", "مدين", KIND_MONEY, total=True),
        ReportColumn("credit", "دائن", KIND_MONEY, total=True),
    ),
    permission="accounting.journal.view",
    row_link="/accounting/journals/{id}",
    build=_general_journal,
))


# ── مستندات الشراء التي لم تكن مُغطّاة ──────────────────────────────────

