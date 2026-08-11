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

def _products(tenant_id: int, params: dict):
    from inventory.models import Product

    qs = Product.objects.filter(tenant_id=tenant_id).select_related("category")
    product = _int_param(params, "product")
    if product:
        qs = qs.filter(pk=product)
    return qs


def _stock_valuation(tenant_id: int, params: dict) -> list[dict]:
    rows = []
    for p in _products(tenant_id, params).order_by("sku"):
        qty = Decimal(str(p.quantity_on_hand or 0))
        cost = Decimal(str(p.avg_cost or 0))
        rows.append({
            "sku": p.sku or "",
            "name": p.name_ar or p.name_en or "",
            "brand": p.brand or "",
            "category": p.category.name if p.category_id else "",
            "quantity": _qty(qty),
            "avg_cost": _money(cost),
            "value": _money(qty * cost),
        })
    return rows


register(ReportSpec(
    key="stock-valuation",
    title="تقييم المخزون",
    category="inventory",
    description="رصيد كل صنف وقيمته بمتوسط التكلفة — قيمة البضاعة على الرفّ.",
    filters=(ReportFilter("product", "الصنف", "product"),),
    columns=(
        ReportColumn("sku", "الرمز", width="120px"),
        ReportColumn("name", "الصنف"),
        ReportColumn("brand", "الماركة", width="120px"),
        ReportColumn("category", "الفئة", width="130px"),
        ReportColumn("quantity", "الرصيد", KIND_NUMBER, total=True, width="100px"),
        ReportColumn("avg_cost", "متوسط التكلفة", KIND_MONEY, width="120px"),
        ReportColumn("value", "القيمة", KIND_MONEY, total=True),
    ),
    permission="inventory.item.view",
    build=_stock_valuation,
))


def _low_stock(tenant_id: int, params: dict) -> list[dict]:
    rows = []
    for p in _products(tenant_id, params).filter(min_stock_level__gt=0).order_by("sku"):
        qty = Decimal(str(p.quantity_on_hand or 0))
        minimum = Decimal(str(p.min_stock_level or 0))
        if qty > minimum:
            continue
        rows.append({
            "sku": p.sku or "",
            "name": p.name_ar or p.name_en or "",
            "quantity": _qty(qty),
            "min_stock_level": _qty(minimum),
            "shortage": _qty(max(minimum - qty, ZERO)),
        })
    return rows


register(ReportSpec(
    key="low-stock",
    title="الأصناف تحت حدّ الطلب",
    category="inventory",
    description="ما بلغ أو نزل عن الحدّ الأدنى المعرَّف على الصنف — قائمة إعادة الطلب.",
    filters=(ReportFilter("product", "الصنف", "product"),),
    columns=(
        ReportColumn("sku", "الرمز", width="120px"),
        ReportColumn("name", "الصنف"),
        ReportColumn("quantity", "الرصيد", KIND_NUMBER, total=True, width="100px"),
        ReportColumn("min_stock_level", "الحد الأدنى", KIND_NUMBER, width="110px"),
        ReportColumn("shortage", "النقص", KIND_NUMBER, total=True, width="100px"),
    ),
    permission="inventory.item.view",
    build=_low_stock,
))


def _stock_movements(tenant_id: int, params: dict) -> list[dict]:
    from inventory.models import StockMovement

    qs = StockMovement.objects.filter(tenant_id=tenant_id).select_related(
        "product", "warehouse", "partner",
    )
    qs = _apply_dates(qs, "movement_date", params)
    product = _int_param(params, "product")
    if product:
        qs = qs.filter(product_id=product)
    warehouse = _int_param(params, "warehouse")
    if warehouse:
        qs = qs.filter(warehouse_id=warehouse)
    return [{
        "id": m.id,
        "movement_date": m.movement_date,
        "sku": m.product.sku if m.product_id else "",
        "name": (m.product.name_ar or m.product.name_en) if m.product_id else "",
        "warehouse": m.warehouse.name if m.warehouse_id else "",
        "movement_type": "وارد" if m.movement_type == "IN" else "صادر",
        "quantity": _qty(m.quantity),
        "quantity_after": _qty(m.quantity_after),
        "unit_cost": _money(m.unit_cost),
        "total_cost": _money(m.total_cost),
        "reference": f"{m.reference_type} #{m.reference_id}" if m.reference_type else "",
        "partner_name": m.partner.name if m.partner_id else "",
    } for m in qs.order_by("movement_date", "id")]


register(ReportSpec(
    key="stock-movements",
    title="حركة المخزون",
    category="inventory",
    description="كل حركة وارد وصادر بمصدرها ورصيدها بعد الحركة.",
    filters=DATE_FILTERS + (
        ReportFilter("product", "الصنف", "product"),
        ReportFilter("warehouse", "المستودع", "warehouse"),
    ),
    columns=(
        ReportColumn("movement_date", "التاريخ", KIND_DATE, width="110px"),
        ReportColumn("sku", "الرمز", width="110px"),
        ReportColumn("name", "الصنف"),
        ReportColumn("warehouse", "المستودع", width="120px"),
        ReportColumn("movement_type", "النوع", width="80px"),
        ReportColumn("quantity", "الكمية", KIND_NUMBER, total=True, width="90px"),
        ReportColumn("quantity_after", "الرصيد بعدها", KIND_NUMBER, width="110px"),
        ReportColumn("unit_cost", "تكلفة الوحدة", KIND_MONEY, width="110px"),
        ReportColumn("total_cost", "إجمالي التكلفة", KIND_MONEY, total=True),
        ReportColumn("reference", "المستند", width="150px"),
        ReportColumn("partner_name", "الطرف"),
    ),
    permission="inventory.item.view",
    build=_stock_movements,
))


def _reserved_stock(tenant_id: int, params: dict) -> list[dict]:
    from sales.services import reserved_stock_rows

    start, end = _date_range(params)
    rows = reserved_stock_rows(
        tenant_id,
        product_id=_int_param(params, "product"),
        customer_id=_int_param(params, "partner"),
        date_from=start, date_to=end,
    )
    return [{
        "order_number": r.get("order_number") or "",
        "partner_name": r.get("customer_name") or "",
        "sku": r.get("sku") or "",
        "name": r.get("product_name") or "",
        "quantity": _qty(r.get("quantity")),
        "reserved_until": r.get("reserved_until"),
    } for r in rows]


register(ReportSpec(
    key="reserved-stock",
    title="الكميات المحجوزة",
    category="inventory",
    description="ما حجزته الطلبيات المؤكَّدة ولم يُسلَّم — نفس مصدر حارس البيع.",
    filters=DATE_FILTERS + (
        ReportFilter("product", "الصنف", "product"),
        ReportFilter("partner", "العميل", "customer"),
    ),
    columns=(
        ReportColumn("order_number", "الطلبية", width="130px"),
        ReportColumn("partner_name", "العميل"),
        ReportColumn("sku", "الرمز", width="110px"),
        ReportColumn("name", "الصنف"),
        ReportColumn("quantity", "المحجوز", KIND_NUMBER, total=True, width="100px"),
        ReportColumn("reserved_until", "الحجز حتى", KIND_DATE, width="110px"),
    ),
    permission="inventory.item.view",
    build=_reserved_stock,
))


# ══════════════════════════════════════════════════════════════════════
#  المالية والنقدية
# ══════════════════════════════════════════════════════════════════════

