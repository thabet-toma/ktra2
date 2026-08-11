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

def _posted_purchases(tenant_id: int, params: dict, *, returns: bool = False):
    from logistics.models import PurchaseInvoice

    qs = PurchaseInvoice.objects.filter(tenant_id=tenant_id, is_posted=True)
    qs = qs.filter(is_return=returns)
    partner = _int_param(params, "partner")
    if partner:
        qs = qs.filter(partner_id=partner)
    return _apply_dates(qs, "invoice_date", params)


def _purchase_invoice_rows(tenant_id: int, params: dict, *, returns: bool = False):
    rows = []
    qs = _posted_purchases(tenant_id, params, returns=returns).select_related("partner")
    for inv in qs.order_by("invoice_date", "id"):
        rows.append({
            "id": inv.id,
            "invoice_number": inv.invoice_number,
            "invoice_date": inv.invoice_date,
            "partner_name": inv.partner.name if inv.partner_id else "",
            "supplier_invoice_number": inv.supplier_invoice_number or "",
            "invoice_type": "نقدي" if inv.payment_type == "cash" else "آجل",
            "subtotal": _money(inv.subtotal),
            "discount": _money(inv.discount_amount),
            "tax_amount": _money(inv.tax_amount),
            "shipping_cost": _money(inv.shipping_cost),
            "grand_total": _money(inv.grand_total),
        })
    return rows


_PURCHASE_COLUMNS = (
    ReportColumn("invoice_number", "رقم الفاتورة", width="130px"),
    ReportColumn("invoice_date", "التاريخ", KIND_DATE, width="110px"),
    ReportColumn("partner_name", "المورد"),
    ReportColumn("supplier_invoice_number", "رقم فاتورة المورد", width="140px"),
    ReportColumn("invoice_type", "نوع الدفع", width="90px"),
    ReportColumn("subtotal", "قبل الضريبة", KIND_MONEY, total=True),
    ReportColumn("discount", "الخصم", KIND_MONEY, total=True),
    ReportColumn("tax_amount", "الضريبة", KIND_MONEY, total=True),
    ReportColumn("shipping_cost", "الشحن", KIND_MONEY, total=True),
    ReportColumn("grand_total", "الإجمالي", KIND_MONEY, total=True),
)

register(ReportSpec(
    key="purchase-invoices",
    title="سجل فواتير الشراء",
    category="purchases",
    description="كل فاتورة شراء مرحّلة في الفترة بتفاصيل الضريبة والشحن.",
    filters=DATE_FILTERS + (ReportFilter("partner", "المورد", "supplier"),),
    columns=_PURCHASE_COLUMNS,
    permission="purchase.invoice.view",
    build=lambda t, p: _purchase_invoice_rows(t, p),
))

register(ReportSpec(
    key="purchase-returns",
    title="مرتجعات الشراء",
    category="purchases",
    description="ما رُدّ للموردين وقيمته.",
    filters=DATE_FILTERS + (ReportFilter("partner", "المورد", "supplier"),),
    columns=_PURCHASE_COLUMNS,
    permission="purchase.invoice.view",
    build=lambda t, p: _purchase_invoice_rows(t, p, returns=True),
))


def _purchases_by_supplier(tenant_id: int, params: dict) -> list[dict]:
    qs = _posted_purchases(tenant_id, params).values(
        "partner_id", "partner__name",
    ).annotate(
        invoices=Sum(Value(1), output_field=DecimalField(max_digits=12, decimal_places=0)),
        subtotal=_money_sum("subtotal"),
        tax_amount=_money_sum("tax_amount"),
        grand_total=_money_sum("grand_total"),
    ).order_by("-grand_total")
    return [{
        "partner_id": r["partner_id"],
        "partner_name": r["partner__name"] or "",
        "invoices": int(r["invoices"] or 0),
        "subtotal": _money(r["subtotal"]),
        "tax_amount": _money(r["tax_amount"]),
        "grand_total": _money(r["grand_total"]),
    } for r in qs]


register(ReportSpec(
    key="purchases-by-supplier",
    title="المشتريات حسب المورد",
    category="purchases",
    description="حجم التعامل مع كل مورد في الفترة.",
    filters=DATE_FILTERS,
    columns=(
        ReportColumn("partner_name", "المورد"),
        ReportColumn("invoices", "عدد الفواتير", KIND_INT, total=True, width="110px"),
        ReportColumn("subtotal", "قبل الضريبة", KIND_MONEY, total=True),
        ReportColumn("tax_amount", "الضريبة", KIND_MONEY, total=True),
        ReportColumn("grand_total", "الإجمالي", KIND_MONEY, total=True),
    ),
    permission="purchase.invoice.view",
    build=_purchases_by_supplier,
))


def _purchases_by_product(tenant_id: int, params: dict) -> list[dict]:
    from logistics.models import PurchaseInvoiceItem

    invoices = list(_posted_purchases(tenant_id, params).values_list("id", flat=True))
    qs = PurchaseInvoiceItem.objects.filter(invoice_id__in=invoices).select_related("product")
    product = _int_param(params, "product")
    if product:
        qs = qs.filter(product_id=product)

    buckets: dict = {}
    for item in qs:
        prod = item.product
        key = item.product_id or f"free:{item.name or item.name_snapshot or ''}"
        bucket = buckets.setdefault(key, {
            "sku": getattr(prod, "sku", "") or "",
            "name": (getattr(prod, "name_ar", None) or item.name
                     or item.name_snapshot or ""),
            "quantity": ZERO, "total_price": ZERO,
        })
        bucket["quantity"] += Decimal(str(item.quantity or 0))
        bucket["total_price"] += Decimal(str(item.total_price or 0))

    rows = []
    for bucket in buckets.values():
        qty = bucket["quantity"]
        rows.append({
            "sku": bucket["sku"],
            "name": bucket["name"],
            "quantity": _qty(qty),
            "total_price": _money(bucket["total_price"]),
            "avg_price": _money(bucket["total_price"] / qty if qty else ZERO),
        })
    rows.sort(key=lambda r: Decimal(r["total_price"]), reverse=True)
    return rows


register(ReportSpec(
    key="purchases-by-product",
    title="المشتريات حسب الصنف",
    category="purchases",
    description="كم اشترينا من كل صنف وبأيّ متوسط سعر.",
    filters=DATE_FILTERS + (ReportFilter("product", "الصنف", "product"),),
    columns=(
        ReportColumn("sku", "الرمز", width="120px"),
        ReportColumn("name", "الصنف"),
        ReportColumn("quantity", "الكمية", KIND_NUMBER, total=True, width="100px"),
        ReportColumn("total_price", "القيمة", KIND_MONEY, total=True),
        ReportColumn("avg_price", "متوسط السعر", KIND_MONEY, width="120px"),
    ),
    permission="purchase.invoice.view",
    build=_purchases_by_product,
))


# ══════════════════════════════════════════════════════════════════════
#  العملاء والموردون
# ══════════════════════════════════════════════════════════════════════

