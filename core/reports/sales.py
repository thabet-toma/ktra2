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

def _posted_sales(tenant_id: int, params: dict, *, kind: str | None = "sale"):
    from sales.models import SalesInvoice

    qs = SalesInvoice.objects.filter(
        tenant_id=tenant_id, status=SalesInvoice.STATUS_POSTED,
    )
    if kind == "sale":
        qs = qs.filter(
            Q(invoice_kind=SalesInvoice.INVOICE_KIND_SALE) | Q(invoice_kind__isnull=True)
            | Q(invoice_kind=""),
        )
    elif kind == "return":
        qs = qs.filter(invoice_kind=SalesInvoice.INVOICE_KIND_SALE_RETURN)
    customer = _int_param(params, "partner")
    if customer:
        qs = qs.filter(customer_id=customer)
    return _apply_dates(qs, "invoice_date", params)


def _sales_invoice_rows(tenant_id: int, params: dict, *, kind: str | None = "sale"):
    rows = []
    qs = _posted_sales(tenant_id, params, kind=kind).select_related("customer", "currency")
    for inv in qs.order_by("invoice_date", "id"):
        remaining = Decimal(str(inv.grand_total or 0)) - Decimal(str(inv.amount_paid or 0))
        rows.append({
            "id": inv.id,
            "invoice_number": inv.invoice_number,
            "invoice_date": inv.invoice_date,
            "partner_name": inv.customer.name if inv.customer_id else "",
            "invoice_type": "نقدي" if inv.invoice_type == "cash" else "آجل",
            "subtotal": _money(inv.subtotal_excl_tax),
            "discount": _money(inv.invoice_discount),
            "tax_amount": _money(inv.tax_amount),
            "grand_total": _money(inv.grand_total),
            "amount_paid": _money(inv.amount_paid),
            "remaining": _money(remaining),
        })
    return rows


_INVOICE_COLUMNS = (
    ReportColumn("invoice_number", "رقم المستند", width="130px"),
    ReportColumn("invoice_date", "التاريخ", KIND_DATE, width="110px"),
    ReportColumn("partner_name", "الطرف"),
    ReportColumn("invoice_type", "نوع الدفع", width="90px"),
    ReportColumn("subtotal", "قبل الضريبة", KIND_MONEY, total=True),
    ReportColumn("discount", "الخصم", KIND_MONEY, total=True),
    ReportColumn("tax_amount", "الضريبة", KIND_MONEY, total=True),
    ReportColumn("grand_total", "الإجمالي", KIND_MONEY, total=True),
    ReportColumn("amount_paid", "المدفوع", KIND_MONEY, total=True),
    ReportColumn("remaining", "المتبقي", KIND_MONEY, total=True),
)

register(ReportSpec(
    key="sales-invoices",
    title="سجل فواتير البيع",
    category="sales",
    description="كل فاتورة بيع مرحّلة في الفترة بتفاصيل الضريبة والتحصيل والمتبقي.",
    filters=DATE_FILTERS + (ReportFilter("partner", "العميل", "customer"),),
    columns=_INVOICE_COLUMNS,
    permission="sales.invoice.view",
    build=lambda t, p: _sales_invoice_rows(t, p),
))

register(ReportSpec(
    key="sales-returns",
    title="مرتجعات البيع",
    category="sales",
    description="مراجع البيع المرحّلة — ما ردّه العملاء وقيمته.",
    filters=DATE_FILTERS + (ReportFilter("partner", "العميل", "customer"),),
    columns=_INVOICE_COLUMNS,
    permission="sales.invoice.view",
    build=lambda t, p: _sales_invoice_rows(t, p, kind="return"),
))


def _sales_summary(tenant_id: int, params: dict) -> list[dict]:
    """ملخّص يومي: عدد الفواتير وقيمها لكل يوم في الفترة."""
    qs = _posted_sales(tenant_id, params).values("invoice_date").annotate(
        invoices=Sum(Value(1), output_field=DecimalField(max_digits=12, decimal_places=0)),
        subtotal=_money_sum("subtotal_excl_tax"),
        tax_amount=_money_sum("tax_amount"),
        grand_total=_money_sum("grand_total"),
        amount_paid=_money_sum("amount_paid"),
    ).order_by("invoice_date")
    rows = []
    for r in qs:
        rows.append({
            "invoice_date": r["invoice_date"],
            "invoices": int(r["invoices"] or 0),
            "subtotal": _money(r["subtotal"]),
            "tax_amount": _money(r["tax_amount"]),
            "grand_total": _money(r["grand_total"]),
            "amount_paid": _money(r["amount_paid"]),
            "remaining": _money(
                Decimal(str(r["grand_total"] or 0)) - Decimal(str(r["amount_paid"] or 0))),
        })
    return rows


register(ReportSpec(
    key="sales-summary",
    title="ملخّص المبيعات اليومي",
    category="sales",
    description="حركة المبيعات يوماً بيوم: عدد الفواتير والقيمة والضريبة والمحصَّل.",
    filters=DATE_FILTERS,
    columns=(
        ReportColumn("invoice_date", "اليوم", KIND_DATE, width="120px"),
        ReportColumn("invoices", "عدد الفواتير", KIND_INT, total=True, width="110px"),
        ReportColumn("subtotal", "قبل الضريبة", KIND_MONEY, total=True),
        ReportColumn("tax_amount", "الضريبة", KIND_MONEY, total=True),
        ReportColumn("grand_total", "الإجمالي", KIND_MONEY, total=True),
        ReportColumn("amount_paid", "المحصَّل", KIND_MONEY, total=True),
        ReportColumn("remaining", "المتبقي", KIND_MONEY, total=True),
    ),
    permission="sales.invoice.view",
    build=_sales_summary,
))


def _sales_by_customer(tenant_id: int, params: dict) -> list[dict]:
    qs = _posted_sales(tenant_id, params).values(
        "customer_id", "customer__name",
    ).annotate(
        invoices=Sum(Value(1), output_field=DecimalField(max_digits=12, decimal_places=0)),
        subtotal=_money_sum("subtotal_excl_tax"),
        tax_amount=_money_sum("tax_amount"),
        grand_total=_money_sum("grand_total"),
        amount_paid=_money_sum("amount_paid"),
    ).order_by("-grand_total")
    return [{
        "partner_id": r["customer_id"],
        "partner_name": r["customer__name"] or "",
        "invoices": int(r["invoices"] or 0),
        "subtotal": _money(r["subtotal"]),
        "tax_amount": _money(r["tax_amount"]),
        "grand_total": _money(r["grand_total"]),
        "amount_paid": _money(r["amount_paid"]),
        "remaining": _money(
            Decimal(str(r["grand_total"] or 0)) - Decimal(str(r["amount_paid"] or 0))),
    } for r in qs]


register(ReportSpec(
    key="sales-by-customer",
    title="المبيعات حسب العميل",
    category="sales",
    description="من يشتري أكثر — إجمالي مبيعات كل عميل وما بقي عليه.",
    filters=DATE_FILTERS,
    columns=(
        ReportColumn("partner_name", "العميل"),
        ReportColumn("invoices", "عدد الفواتير", KIND_INT, total=True, width="110px"),
        ReportColumn("subtotal", "قبل الضريبة", KIND_MONEY, total=True),
        ReportColumn("tax_amount", "الضريبة", KIND_MONEY, total=True),
        ReportColumn("grand_total", "الإجمالي", KIND_MONEY, total=True),
        ReportColumn("amount_paid", "المدفوع", KIND_MONEY, total=True),
        ReportColumn("remaining", "المتبقي", KIND_MONEY, total=True),
    ),
    permission="sales.invoice.view",
    build=_sales_by_customer,
))


def _sales_line_aggregate(tenant_id: int, params: dict, *, group: str) -> list[dict]:
    """تجميع أسطر فواتير البيع حسب المنتج أو الماركة — قاعدة واحدة لتقريرين.

    THA-60: التكلفة تُقرأ من حركات المخزون المسجَّلة لحظة الترحيل/التسليم عبر
    `sales_cogs_map` — القاعدة الموحّدة نفسها التي يستهلكها «أرباح الفواتير»،
    لا `avg_cost` اللحظي. الفرق جوهري: المتوسط يتحرّك مع كل شراء لاحق، فكان
    ربح فواتير مضت ورُحّلت يتغيّر بلا أن يُمسّ أي مستند.

    الإيراد = صافي السطر ناقص نصيبه التناسبي من خصم الفاتورة — كي يطابق مجموعُ
    المنتجات ربحَ «أرباح الفواتير» على الفواتير نفسها (يطرح الخصم مرّة واحدة على
    مستوى الفاتورة). التراكم بلا تقريب وسيط، والتقريب في النهاية وحدها.

    ما لا حركة له (مستورَد بلا حركات، أو بند لم يُسلَّم بعد) يُعلَن في عمود
    «كمية بلا تكلفة» بدل أن يمرّ كتكلفة صفر صامتة. الخدمات مستثناة — بلا تكلفة
    مخزون بحقّ. ثلاثة استعلامات إجمالاً: الفواتير، الأسطر، خريطة التكلفة.
    """
    from sales.models import SalesInvoiceLine
    from sales.services import allocate_invoice_discount, sales_cogs_map

    inv_rows = list(
        _posted_sales(tenant_id, params).values(
            "id", "subtotal_excl_tax", "invoice_discount",
        )
    )
    invoice_ids = [r["id"] for r in inv_rows]
    # نصيب السطر من خصم الفاتورة يُحسب بنسبة السطر إلى مجموع أسطرها.
    discounts = {
        r["id"]: (
            Decimal(str(r["invoice_discount"] or 0)),
            Decimal(str(r["subtotal_excl_tax"] or 0)),
        )
        for r in inv_rows
    }

    qs = SalesInvoiceLine.objects.filter(
        tenant_id=tenant_id, invoice_id__in=invoice_ids,
    ).select_related("product")
    product = _int_param(params, "product")
    if product:
        qs = qs.filter(product_id=product)

    def _bucket_of(prod, product_id):
        """دلو المنتج أو الماركة — مفتاحه ولافتته من المنتج نفسه."""
        if group == "product":
            key = product_id
            label = {
                "sku": getattr(prod, "sku", "") or "",
                "name": getattr(prod, "name_ar", "") or getattr(prod, "name_en", "") or "",
            }
        else:
            key = (getattr(prod, "brand", "") or "— بلا ماركة —")
            label = {"sku": "", "name": key}
        return buckets.setdefault(key, {
            **label, "quantity": ZERO, "net_sales": ZERO, "tax_amount": ZERO,
            "cost": ZERO, "uncosted_qty": ZERO,
        })

    buckets: dict = {}
    # كمية البضائع لكل (فاتورة، منتج) — أساس مقارنة المُكلَّف بالمُباع.
    goods_qty: dict[tuple[int, int], Decimal] = {}
    bucket_of_product: dict[int, dict] = {}
    for line in qs:
        prod = line.product
        bucket = _bucket_of(prod, line.product_id)
        bucket_of_product[line.product_id] = bucket
        qty = Decimal(str(line.quantity or 0))
        # قاعدة توزيع خصم الفاتورة مشتركة مع `sales_revenue_map` (ومنها تقرير
        # «حركة المخزون حسب بُعد») — نسختان منها كانتا ستفترقان عند أول تعديل.
        discount, subtotal = discounts.get(line.invoice_id, (ZERO, ZERO))
        net = allocate_invoice_discount(line.line_total_excl_tax, discount, subtotal)
        bucket["quantity"] += qty
        bucket["net_sales"] += net
        bucket["tax_amount"] += Decimal(str(line.line_tax_amount or 0))
        if not getattr(prod, "is_service", False):
            key = (line.invoice_id, line.product_id)
            goods_qty[key] = goods_qty.get(key, ZERO) + qty

    # تمريرة ثانية على خريطة التكلفة — لا استعلام داخل حلقة الأسطر.
    cogs = sales_cogs_map(tenant_id=tenant_id, invoice_ids=invoice_ids)
    if product:
        cogs = {k: v for k, v in cogs.items() if k[1] == product}
    # حركة لمنتج لا سطر له في الفاتورة: تكلفتها حقيقية ولا يجوز إسقاطها، فيُجلب
    # منتجها في استعلام واحد احتياطي بدل تجاهل المبلغ.
    missing = {pid for (_, pid) in cogs if pid not in bucket_of_product}
    if missing:
        from inventory.models import Product

        for prod in Product.objects.filter(tenant_id=tenant_id, id__in=missing):
            bucket_of_product[prod.id] = _bucket_of(prod, prod.id)

    for key in set(goods_qty) | set(cogs):
        bucket = bucket_of_product.get(key[1])
        if bucket is None:
            continue
        moved = cogs.get(key) or {}
        bucket["cost"] += Decimal(str(moved.get("cost") or 0))
        uncosted = goods_qty.get(key, ZERO) - Decimal(str(moved.get("qty") or 0))
        if uncosted > 0:
            bucket["uncosted_qty"] += uncosted

    rows = []
    for bucket in buckets.values():
        profit = bucket["net_sales"] - bucket["cost"]
        margin = (profit / bucket["net_sales"] * 100) if bucket["net_sales"] else ZERO
        rows.append({
            "sku": bucket["sku"],
            "name": bucket["name"],
            "quantity": _qty(bucket["quantity"]),
            "net_sales": _money(bucket["net_sales"]),
            "tax_amount": _money(bucket["tax_amount"]),
            "cost": _money(bucket["cost"]),
            "profit": _money(profit),
            "margin": _money(margin),
            "uncosted_qty": _qty(bucket["uncosted_qty"]),
        })
    rows.sort(key=lambda r: Decimal(r["net_sales"]), reverse=True)
    return rows


_PRODUCT_SALES_COLUMNS = (
    ReportColumn("sku", "الرمز", width="120px"),
    ReportColumn("name", "المنتج"),
    ReportColumn("quantity", "الكمية", KIND_NUMBER, total=True, width="100px"),
    ReportColumn("net_sales", "صافي المبيعات", KIND_MONEY, total=True),
    ReportColumn("tax_amount", "الضريبة", KIND_MONEY, total=True),
    ReportColumn("cost", "التكلفة", KIND_MONEY, total=True),
    ReportColumn("profit", "الربح", KIND_MONEY, total=True),
    ReportColumn("margin", "الهامش %", KIND_NUMBER, width="90px"),
    # كمية بيعت بلا حركة مخزون تحمل تكلفتها — تُعلَن ولا تمرّ كتكلفة صفر صامتة.
    ReportColumn("uncosted_qty", "كمية بلا تكلفة", KIND_NUMBER, total=True, width="120px"),
)

register(ReportSpec(
    key="sales-by-product",
    title="المبيعات حسب المنتج",
    category="sales",
    description=(
        "كمّ بيع كل منتج وربحه. التكلفة من حركات المخزون لحظة الترحيل/التسليم — "
        "تاريخية لا يحرّكها شراء لاحق. «كمية بلا تكلفة» ما لم تُسجَّل له حركة بعد."
    ),
    filters=DATE_FILTERS + (ReportFilter("product", "المنتج", "product"),),
    columns=_PRODUCT_SALES_COLUMNS,
    permission="sales.invoice.view",
    build=lambda t, p: _sales_line_aggregate(t, p, group="product"),
))

register(ReportSpec(
    key="sales-by-brand",
    title="المبيعات حسب الماركة",
    category="sales",
    description=(
        "أي ماركة تبيع أكثر وأيّها أربح — تجميع أسطر البيع على ماركة المنتج. "
        "التكلفة تاريخية من حركات المخزون، لا بمتوسط التكلفة اليوم."
    ),
    filters=DATE_FILTERS,
    columns=tuple(c for c in _PRODUCT_SALES_COLUMNS if c.key != "sku"),
    permission="sales.invoice.view",
    build=lambda t, p: _sales_line_aggregate(t, p, group="brand"),
))


def _quotations(tenant_id: int, params: dict) -> list[dict]:
    from sales.models import SalesQuotation

    qs = SalesQuotation.objects.filter(tenant_id=tenant_id).select_related("customer")
    qs = _apply_dates(qs, "quotation_date", params)
    partner = _int_param(params, "partner")
    if partner:
        qs = qs.filter(customer_id=partner)
    return [{
        "id": q.id,
        "number": q.quotation_number,
        "date": q.quotation_date,
        "valid_until": q.valid_until,
        "partner_name": q.customer.name if q.customer_id else "",
        "status": q.get_status_display() if hasattr(q, "get_status_display") else q.status,
        "grand_total": _money(q.grand_total),
        "converted": "نعم" if q.invoice_id else "لا",
    } for q in qs.order_by("quotation_date", "id")]


register(ReportSpec(
    key="sales-quotations",
    title="عروض الأسعار",
    category="sales",
    description="كل عرض سعر وحالته وهل تحوّل لفاتورة — لقياس نسبة التحويل.",
    filters=DATE_FILTERS + (ReportFilter("partner", "العميل", "customer"),),
    columns=(
        ReportColumn("number", "رقم العرض", width="130px"),
        ReportColumn("date", "التاريخ", KIND_DATE, width="110px"),
        ReportColumn("valid_until", "صالح حتى", KIND_DATE, width="110px"),
        ReportColumn("partner_name", "العميل"),
        ReportColumn("status", "الحالة", width="120px"),
        ReportColumn("grand_total", "الإجمالي", KIND_MONEY, total=True),
        ReportColumn("converted", "حُوِّل لفاتورة", width="110px"),
    ),
    permission="sales.quotation.manage",
    build=_quotations,
))


def _sales_orders(tenant_id: int, params: dict) -> list[dict]:
    from sales.models import SalesOrder

    qs = SalesOrder.objects.filter(tenant_id=tenant_id).select_related("customer")
    qs = _apply_dates(qs, "order_date", params)
    partner = _int_param(params, "partner")
    if partner:
        qs = qs.filter(customer_id=partner)
    return [{
        "id": o.id,
        "number": o.order_number,
        "date": o.order_date,
        "delivery_date": o.delivery_date,
        "reserved_until": o.reserved_until,
        "partner_name": o.customer.name if o.customer_id else "",
        "status": o.status,
        "grand_total": _money(o.grand_total),
        "deposit_amount": _money(o.deposit_amount),
        "converted": "نعم" if o.invoice_id else "لا",
    } for o in qs.order_by("order_date", "id")]


register(ReportSpec(
    key="sales-orders",
    title="طلبيات الزبائن",
    category="sales",
    description="الطلبيات وحالتها ومواعيد التسليم والعربون والحجز الساري.",
    filters=DATE_FILTERS + (ReportFilter("partner", "العميل", "customer"),),
    columns=(
        ReportColumn("number", "رقم الطلبية", width="130px"),
        ReportColumn("date", "التاريخ", KIND_DATE, width="110px"),
        ReportColumn("partner_name", "العميل"),
        ReportColumn("status", "الحالة", width="110px"),
        ReportColumn("delivery_date", "موعد التسليم", KIND_DATE, width="110px"),
        ReportColumn("reserved_until", "الحجز حتى", KIND_DATE, width="110px"),
        ReportColumn("grand_total", "الإجمالي", KIND_MONEY, total=True),
        ReportColumn("deposit_amount", "العربون", KIND_MONEY, total=True),
        ReportColumn("converted", "حُوِّل لفاتورة", width="110px"),
    ),
    permission="sales.quotation.manage",
    build=_sales_orders,
))


def _deliveries(tenant_id: int, params: dict) -> list[dict]:
    from sales.models import DeliveryOrder

    qs = DeliveryOrder.objects.filter(tenant_id=tenant_id).select_related(
        "partner", "invoice",
    )
    qs = _apply_dates(qs, "delivery_date", params)
    partner = _int_param(params, "partner")
    if partner:
        qs = qs.filter(partner_id=partner)
    return [{
        "id": d.id,
        "number": d.delivery_number or f"#{d.id}",
        "date": d.delivery_date,
        "partner_name": d.partner.name if d.partner_id else "",
        "invoice_number": d.invoice.invoice_number if d.invoice_id else "— بلا فاتورة —",
        "status": d.status,
        "customer_ref": d.customer_ref or "",
    } for d in qs.order_by("delivery_date", "id")]


register(ReportSpec(
    key="sales-deliveries",
    title="سندات التسليم",
    category="sales",
    description="ما خرج للعملاء: إرساليات الفواتير وسندات التسليم المستقلة.",
    filters=DATE_FILTERS + (ReportFilter("partner", "العميل", "customer"),),
    columns=(
        ReportColumn("number", "رقم السند", width="130px"),
        ReportColumn("date", "التاريخ", KIND_DATE, width="110px"),
        ReportColumn("partner_name", "العميل"),
        ReportColumn("invoice_number", "الفاتورة", width="140px"),
        ReportColumn("status", "الحالة", width="110px"),
        ReportColumn("customer_ref", "مرجع العميل"),
    ),
    permission="sales.invoice.view",
    build=_deliveries,
))


def _credit_notes(tenant_id: int, params: dict) -> list[dict]:
    from sales.models import CreditDebitNote

    qs = CreditDebitNote.objects.filter(tenant_id=tenant_id).select_related(
        "customer", "related_invoice",
    )
    qs = _apply_dates(qs, "note_date", params)
    return [{
        "id": n.id,
        "number": n.note_number,
        "date": n.note_date,
        "note_type": "إشعار دائن" if n.note_type == CreditDebitNote.TYPE_CREDIT else "إشعار مدين",
        "partner_name": n.customer.name if n.customer_id else "",
        "invoice_number": n.related_invoice.invoice_number if n.related_invoice_id else "",
        "status": n.status,
        "amount": _money(n.amount),
    } for n in qs.order_by("note_date", "id")]


register(ReportSpec(
    key="sales-credit-notes",
    title="الإشعارات الدائنة والمدينة",
    category="sales",
    description="تسويات ما بعد الفاتورة — إشعارات الخصم والإضافة على حساب العميل.",
    filters=DATE_FILTERS,
    columns=(
        ReportColumn("number", "رقم الإشعار", width="130px"),
        ReportColumn("date", "التاريخ", KIND_DATE, width="110px"),
        ReportColumn("note_type", "النوع", width="110px"),
        ReportColumn("partner_name", "العميل"),
        ReportColumn("invoice_number", "الفاتورة المرتبطة", width="140px"),
        ReportColumn("status", "الحالة", width="100px"),
        ReportColumn("amount", "المبلغ", KIND_MONEY, total=True),
    ),
    permission="sales.invoice.view",
    build=_credit_notes,
))


# ══════════════════════════════════════════════════════════════════════
#  المشتريات
# ══════════════════════════════════════════════════════════════════════

