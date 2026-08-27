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

_PO_STATUS = {
    "draft": "مسودّة", "confirmed": "مؤكّد",
    "converted": "محوَّل إلى فاتورة", "cancelled": "ملغى",
}


def _purchase_orders(tenant_id: int, params: dict) -> list[dict]:
    from logistics.models import PurchaseOrder

    qs = PurchaseOrder.objects.filter(tenant_id=tenant_id).select_related("supplier")
    qs = _apply_dates(qs, "order_date", params)
    supplier = _int_param(params, "partner")
    if supplier:
        qs = qs.filter(supplier_id=supplier)
    status = params.get("status") or ""
    if status:
        qs = qs.filter(status=status)
    return [{
        "id": o.id,
        "number": o.order_number or f"#{o.id}",
        "date": o.order_date,
        "partner_name": o.supplier.name if o.supplier_id else "",
        "expected": o.expected_delivery_date,
        "status": _PO_STATUS.get(o.status, o.status or ""),
        "invoice": "نعم" if o.invoice_id else "لا",
        "grand_total": _money(o.grand_total),
    } for o in qs.order_by("order_date", "id")]


register(ReportSpec(
    key="purchase-orders",
    title="أوامر الشراء",
    category="purchases",
    description="أوامر الشراء وحالتها وما تحوّل منها إلى فاتورة — متابعة ما هو قيد التوريد.",
    filters=DATE_FILTERS + (
        ReportFilter("partner", "المورد", "supplier"),
        ReportFilter(
            "status", "الحالة", "select",
            options=(("", "الكل"), ("draft", "مسودّة"), ("confirmed", "مؤكّد"),
                     ("converted", "محوَّل إلى فاتورة"), ("cancelled", "ملغى")),
        ),
    ),
    columns=(
        ReportColumn("number", "رقم الأمر", width="130px"),
        ReportColumn("date", "التاريخ", KIND_DATE, width="110px"),
        ReportColumn("partner_name", "المورد"),
        ReportColumn("expected", "التسليم المتوقّع", KIND_DATE, width="120px"),
        ReportColumn("status", "الحالة", width="140px"),
        ReportColumn("invoice", "له فاتورة", width="90px"),
        ReportColumn("grand_total", "الإجمالي", KIND_MONEY, total=True),
    ),
    permission="purchase.invoice.view",
    build=_purchase_orders,
))


_SQ_STATUS = {
    "draft": "مسودّة", "sent": "مُرسَل", "pending_info": "بانتظار معلومات",
    "under_discussion": "قيد المناقشة", "accepted": "مقبول", "rejected": "مرفوض",
    "expired": "منتهٍ", "cancelled": "ملغى", "converted": "محوَّل",
}


def _supplier_quotations(tenant_id: int, params: dict) -> list[dict]:
    from logistics.models import SupplierQuotation

    qs = SupplierQuotation.objects.filter(tenant_id=tenant_id).select_related("supplier")
    qs = _apply_dates(qs, "quotation_date", params)
    supplier = _int_param(params, "partner")
    if supplier:
        qs = qs.filter(supplier_id=supplier)
    status = params.get("status") or ""
    if status:
        qs = qs.filter(status=status)
    return [{
        "id": q.id,
        "number": q.quotation_number or f"#{q.id}",
        "date": q.quotation_date,
        "partner_name": q.supplier.name if q.supplier_id else (q.supplier_draft_name or ""),
        "scope": "استيراد" if q.scope == "import" else "محلي",
        "valid_until": q.valid_until,
        "status": _SQ_STATUS.get(q.status, q.status or ""),
        "grand_total": _money(q.grand_total),
    } for q in qs.order_by("quotation_date", "id")]


register(ReportSpec(
    key="supplier-quotations",
    title="عروض أسعار الموردين",
    category="purchases",
    description="العروض الواردة وحالتها وصلاحيتها — أين وقف كل عرض ومتى ينتهي.",
    filters=DATE_FILTERS + (
        ReportFilter("partner", "المورد", "supplier"),
        ReportFilter(
            "status", "الحالة", "select",
            options=(("", "الكل"), ("draft", "مسودّة"), ("sent", "مُرسَل"),
                     ("pending_info", "بانتظار معلومات"), ("under_discussion", "قيد المناقشة"),
                     ("accepted", "مقبول"), ("rejected", "مرفوض"),
                     ("expired", "منتهٍ"), ("converted", "محوَّل")),
        ),
    ),
    columns=(
        ReportColumn("number", "رقم العرض", width="130px"),
        ReportColumn("date", "التاريخ", KIND_DATE, width="110px"),
        ReportColumn("partner_name", "المورد"),
        ReportColumn("scope", "الوجهة", width="90px"),
        ReportColumn("valid_until", "صالح حتى", KIND_DATE, width="110px"),
        ReportColumn("status", "الحالة", width="140px"),
        ReportColumn("grand_total", "القيمة", KIND_MONEY, total=True),
    ),
    permission="purchase.invoice.view",
    build=_supplier_quotations,
))


def _goods_receipts(tenant_id: int, params: dict) -> list[dict]:
    from logistics.models import GoodsReceipt

    qs = GoodsReceipt.objects.filter(tenant_id=tenant_id).select_related(
        "partner", "invoice",
    )
    qs = _apply_dates(qs, "receipt_date", params)
    supplier = _int_param(params, "partner")
    if supplier:
        qs = qs.filter(partner_id=supplier)
    return [{
        "id": r.id,
        "number": r.receipt_number or f"#{r.id}",
        "date": r.receipt_date,
        "partner_name": r.partner.name if r.partner_id else "",
        "invoice_number": r.invoice.invoice_number if r.invoice_id else "",
        "supplier_ref": r.supplier_ref or "",
        "source": "تلقائي" if r.auto_created else "يدوي",
        "journal": f"#{r.journal_id}" if r.journal_id else "",
    } for r in qs.order_by("receipt_date", "id")]


register(ReportSpec(
    key="goods-receipts",
    title="إشعارات استلام البضاعة",
    category="purchases",
    description="ما استُلم فعلاً من الموردين وفاتورته وقيده — الفجوة بين الأمر والاستلام.",
    filters=DATE_FILTERS + (ReportFilter("partner", "المورد", "supplier"),),
    columns=(
        ReportColumn("number", "رقم الإشعار", width="130px"),
        ReportColumn("date", "التاريخ", KIND_DATE, width="110px"),
        ReportColumn("partner_name", "المورد"),
        ReportColumn("invoice_number", "الفاتورة", width="130px"),
        ReportColumn("supplier_ref", "مرجع المورد", width="130px"),
        ReportColumn("source", "المصدر", width="90px"),
        ReportColumn("journal", "القيد", width="80px"),
    ),
    permission="purchase.invoice.view",
    row_link="/purchase-receipts/{id}",
    build=_goods_receipts,
))


# ── مستندات المخزون التي لم تكن مُغطّاة ─────────────────────────────────

def _warehouse_transfers(tenant_id: int, params: dict) -> list[dict]:
    from django.db.models import Count

    from inventory.models import WarehouseTransfer

    qs = WarehouseTransfer.objects.filter(tenant_id=tenant_id).select_related(
        "source_warehouse", "dest_warehouse",
    ).annotate(line_count=Count("lines"))
    qs = _apply_dates(qs, "transfer_date", params)
    warehouse = _int_param(params, "warehouse")
    if warehouse:
        qs = qs.filter(Q(source_warehouse_id=warehouse) | Q(dest_warehouse_id=warehouse))
    return [{
        "id": t.id,
        "number": t.transfer_number or f"#{t.id}",
        "date": t.transfer_date,
        "source": t.source_warehouse.name if t.source_warehouse_id else "",
        "destination": t.dest_warehouse.name if t.dest_warehouse_id else "",
        "line_count": t.line_count,
        "state": "مرحّل" if t.is_posted else "مسودّة",
        "notes": (t.notes or "")[:120],
    } for t in qs.order_by("transfer_date", "id")]


register(ReportSpec(
    key="warehouse-transfers",
    title="تحويلات المستودعات",
    category="inventory",
    description="حركة البضاعة بين المستودعات: من أين إلى أين وكم منتجاً وهل رُحّلت.",
    filters=DATE_FILTERS + (ReportFilter("warehouse", "المستودع", "warehouse"),),
    columns=(
        ReportColumn("number", "رقم التحويل", width="130px"),
        ReportColumn("date", "التاريخ", KIND_DATE, width="110px"),
        ReportColumn("source", "من مستودع"),
        ReportColumn("destination", "إلى مستودع"),
        ReportColumn("line_count", "عدد المنتجات", KIND_INT, total=True, width="100px"),
        ReportColumn("state", "الحالة", width="90px"),
        ReportColumn("notes", "ملاحظات"),
    ),
    permission="inventory.item.view",
    build=_warehouse_transfers,
))


def _stocktakes(tenant_id: int, params: dict) -> list[dict]:
    from django.db.models import Count

    from inventory.models import Stocktake

    qs = Stocktake.objects.filter(tenant_id=tenant_id).select_related("warehouse")
    qs = _apply_dates(qs, "stocktake_date", params)
    warehouse = _int_param(params, "warehouse")
    if warehouse:
        qs = qs.filter(warehouse_id=warehouse)
    qs = qs.annotate(
        line_count=Count("lines", distinct=True),
        variance_total=_money_sum("lines__variance"),
    )
    return [{
        "id": s.id,
        "number": s.stocktake_number or f"#{s.id}",
        "date": s.stocktake_date,
        "warehouse": s.warehouse.name if s.warehouse_id else "",
        "line_count": s.line_count,
        "variance_total": _qty(s.variance_total),
        "state": "مرحّل" if s.is_posted else "مسودّة",
        "journal": f"#{s.journal_id}" if s.journal_id else "",
    } for s in qs.order_by("stocktake_date", "id")]


register(ReportSpec(
    key="stocktakes",
    title="عمليات الجرد",
    category="inventory",
    description="كل جرد وفروقه الكمية وقيده — أثر التسويات على المخزون.",
    filters=DATE_FILTERS + (ReportFilter("warehouse", "المستودع", "warehouse"),),
    columns=(
        ReportColumn("number", "رقم الجرد", width="130px"),
        ReportColumn("date", "التاريخ", KIND_DATE, width="110px"),
        ReportColumn("warehouse", "المستودع"),
        ReportColumn("line_count", "عدد المنتجات", KIND_INT, total=True, width="100px"),
        ReportColumn("variance_total", "صافي الفرق", KIND_NUMBER, total=True, width="110px"),
        ReportColumn("state", "الحالة", width="90px"),
        ReportColumn("journal", "القيد", width="80px"),
    ),
    permission="inventory.item.view",
    build=_stocktakes,
))


def _product_serials(tenant_id: int, params: dict) -> list[dict]:
    from inventory.models import ProductSerial

    qs = ProductSerial.objects.filter(tenant_id=tenant_id).select_related("product")
    product = _int_param(params, "product")
    if product:
        qs = qs.filter(product_id=product)
    status = params.get("status") or ""
    if status:
        qs = qs.filter(status=status)
    qs = _apply_dates(qs, "created_at__date", params)
    return [{
        "id": s.product_id,
        "serial": s.serial,
        "sku": s.product.sku if s.product_id else "",
        "product_name": (s.product.name_ar or s.product.name_en or "") if s.product_id else "",
        "status": "في المخزون" if s.status == "in_stock" else "مُباع",
        "created_at": s.created_at.date() if s.created_at else None,
    } for s in qs.order_by("product_id", "serial")]


register(ReportSpec(
    key="product-serials",
    title="الأرقام التسلسلية",
    category="inventory",
    description="كل رقم تسلسلي وحالته — ما زال في المخزون أم خرج بفاتورة بيع.",
    filters=DATE_FILTERS + (
        ReportFilter("product", "المنتج", "product"),
        ReportFilter(
            "status", "الحالة", "select",
            options=(("", "الكل"), ("in_stock", "في المخزون"), ("sold", "مُباع")),
        ),
    ),
    columns=(
        ReportColumn("serial", "الرقم التسلسلي", width="180px"),
        ReportColumn("sku", "الرمز", width="120px"),
        ReportColumn("product_name", "المنتج"),
        ReportColumn("status", "الحالة", width="100px"),
        ReportColumn("created_at", "أُدخل في", KIND_DATE, width="110px"),
    ),
    permission="inventory.item.view",
    row_link="/products/{id}",
    build=_product_serials,
))


# ── الاستيراد: التخليص والشحن المحلي ───────────────────────────────────

_CLEARANCE_STATUS = {"Processing": "قيد المعالجة", "Cleared": "مُفرَج", "Hold": "موقوف"}


def _clearances(tenant_id: int, params: dict) -> list[dict]:
    from logistics.models import LogisticsClearance

    qs = LogisticsClearance.objects.filter(tenant_id=tenant_id).select_related(
        "shipment", "customs_broker",
    )
    qs = _apply_dates(qs, "clearance_date", params)
    broker = _int_param(params, "partner")
    if broker:
        qs = qs.filter(customs_broker_id=broker)
    return [{
        "id": c.shipment_id,
        "book_number": c.book_number or f"#{c.id}",
        "date": c.clearance_date,
        "shipment": c.shipment.shipment_number if c.shipment_id else "",
        "broker": c.customs_broker.name if c.customs_broker_id else "",
        "declaration_number": c.declaration_number or "",
        "status": _CLEARANCE_STATUS.get(c.status, c.status or ""),
        "subtotal_no_vat": _money(c.subtotal_no_vat),
        "vat_total": _money(c.vat_total),
        "grand_total": _money(c.grand_total),
    } for c in qs.order_by("clearance_date", "id")]


register(ReportSpec(
    key="clearances",
    title="معاملات التخليص",
    category="import",
    description="بيانات التخليص الجمركي: البيان والمخلّص والضريبة وإجمالي المعاملة.",
    filters=DATE_FILTERS + (ReportFilter("partner", "المخلّص", "partner"),),
    columns=(
        ReportColumn("book_number", "رقم الدفتر", width="120px"),
        ReportColumn("date", "التاريخ", KIND_DATE, width="110px"),
        ReportColumn("shipment", "الشحنة", width="130px"),
        ReportColumn("broker", "المخلّص"),
        ReportColumn("declaration_number", "رقم البيان", width="130px"),
        ReportColumn("status", "الحالة", width="110px"),
        ReportColumn("subtotal_no_vat", "قبل الضريبة", KIND_MONEY, total=True),
        ReportColumn("vat_total", "الضريبة", KIND_MONEY, total=True),
        ReportColumn("grand_total", "الإجمالي", KIND_MONEY, total=True),
    ),
    permission="import.shipment.manage",
    row_link="/shipments/{id}",
    build=_clearances,
))


_LOCAL_SHIPMENT_STATUS = {
    "pending": "بانتظار الشحن", "in_transit": "في الطريق",
    "delivered": "تم التسليم", "cancelled": "ملغى",
}


def _local_shipments(tenant_id: int, params: dict) -> list[dict]:
    from logistics.models import LocalShipment

    qs = LocalShipment.objects.filter(tenant_id=tenant_id).select_related("carrier")
    qs = _apply_dates(qs, "pickup_date", params)
    carrier = _int_param(params, "partner")
    if carrier:
        qs = qs.filter(carrier_id=carrier)
    return [{
        "id": s.id,
        "number": s.shipment_number or f"#{s.id}",
        "pickup_date": s.pickup_date,
        "delivery_date": s.delivery_date,
        "carrier": s.carrier.name if s.carrier_id else "",
        "route": " ← ".join([p for p in (s.destination or "", s.origin or "") if p]),
        "status": _LOCAL_SHIPMENT_STATUS.get(s.status, s.status or ""),
        "state": "مرحّل" if s.is_posted else "غير مرحّل",
        "amount": _money(s.amount),
    } for s in qs.order_by("pickup_date", "id")]


register(ReportSpec(
    key="local-shipments",
    title="الشحن المحلي",
    category="import",
    description="نقل البضاعة داخلياً: الناقل والمسار والكلفة وهل رُحّلت للدفاتر.",
    filters=DATE_FILTERS + (ReportFilter("partner", "الناقل", "partner"),),
    columns=(
        ReportColumn("number", "رقم الشحنة", width="130px"),
        ReportColumn("pickup_date", "التحميل", KIND_DATE, width="110px"),
        ReportColumn("delivery_date", "التسليم", KIND_DATE, width="110px"),
        ReportColumn("carrier", "الناقل"),
        ReportColumn("route", "المسار"),
        ReportColumn("status", "الحالة", width="110px"),
        ReportColumn("state", "القيد", width="100px"),
        ReportColumn("amount", "الكلفة", KIND_MONEY, total=True),
    ),
    permission="import.shipment.manage",
    build=_local_shipments,
))


# ── الرواتب ───────────────────────────────────────────────────────────

