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

logger = logging.getLogger(__name__)

DEC = Decimal("0.01")
ZERO = Decimal("0")

# ── فئات التقارير (ترتيب العرض في الفهرس) ─────────────────────────────
CATEGORIES: list[tuple[str, str]] = [
    ("sales", "المبيعات"),
    ("purchases", "المشتريات"),
    ("partners", "العملاء والموردون"),
    ("inventory", "المخزون"),
    ("finance", "المالية والنقدية"),
    ("accounting", "المحاسبة"),
    ("import", "الاستيراد"),
    ("hr", "الموارد البشرية"),
]

# أنواع الأعمدة التي تفهمها الواجهة: text | money | number | int | date | badge
KIND_MONEY = "money"
KIND_NUMBER = "number"
KIND_INT = "int"
KIND_DATE = "date"
KIND_TEXT = "text"


@dataclass(frozen=True)
class ReportColumn:
    key: str
    header: str
    kind: str = KIND_TEXT
    #: يُجمع في سطر الإجمالي أسفل الجدول
    total: bool = False
    width: str | None = None


@dataclass(frozen=True)
class ReportFilter:
    key: str
    label: str
    #: date | partner | customer | supplier | product | warehouse | select | text
    kind: str
    options: tuple[tuple[str, str], ...] = ()
    default: str | None = None


@dataclass(frozen=True)
class ReportSpec:
    key: str
    title: str
    category: str
    description: str
    columns: tuple[ReportColumn, ...]
    build: Callable[[int, dict], list[dict]]
    filters: tuple[ReportFilter, ...] = ()
    permission: str | None = None
    #: تقرير له شاشة مخصّصة قائمة — الفهرس يقود إليها بدل الجدول العام
    screen_path: str | None = None
    #: مسار المستند خلف السطر، بقوالب من مفاتيح الصف — «/sales/invoices/{id}».
    #: وجوده يجعل السطر قابلاً للفتح في الشاشة العامّة (لا شاشة تعرف مستنداتها).
    row_link: str | None = None


REPORTS: dict[str, ReportSpec] = {}


def register(spec: ReportSpec) -> ReportSpec:
    if spec.key in REPORTS:
        raise ValueError(f"تقرير مكرر: {spec.key}")
    REPORTS[spec.key] = spec
    return spec


# ── أدوات مشتركة ──────────────────────────────────────────────────────

DATE_FILTERS = (
    ReportFilter("from", "من تاريخ", "date"),
    ReportFilter("to", "إلى تاريخ", "date"),
)


def _parse_date(value) -> datetime.date | None:
    from django.utils.dateparse import parse_date

    if not value:
        return None
    if isinstance(value, datetime.date):
        return value
    return parse_date(str(value))


def _date_range(params: dict) -> tuple[datetime.date | None, datetime.date | None]:
    return _parse_date(params.get("from")), _parse_date(params.get("to"))


def _apply_dates(qs, field_name: str, params: dict):
    start, end = _date_range(params)
    if start:
        qs = qs.filter(**{f"{field_name}__gte": start})
    if end:
        qs = qs.filter(**{f"{field_name}__lte": end})
    return qs


def _int_param(params: dict, key: str) -> int | None:
    raw = params.get(key)
    return int(raw) if raw not in (None, "") and str(raw).isdigit() else None


def _money(value) -> str:
    """مبلغ نصّي بقرشين — مصدر واحد لتنسيق المال في كل التقارير."""
    return str(Decimal(str(value or 0)).quantize(DEC))


def _qty(value) -> str:
    """كمية بلا أصفار زائدة — الكميات كسرية أحياناً والقطع صحيحة غالباً."""
    dec = Decimal(str(value or 0)).normalize()
    return format(dec, "f")


def _sum(rows: list[dict], key: str) -> str:
    return _money(sum((Decimal(str(r.get(key) or 0)) for r in rows), ZERO))


def _money_sum(field_name: str):
    return Coalesce(
        Sum(field_name), Value(ZERO), output_field=DecimalField(max_digits=20, decimal_places=4),
    )


def compute_totals(spec: ReportSpec, rows: list[dict]) -> dict[str, str]:
    """سطر الإجمالي من الأعمدة الموسومة `total=True` — لا حساب يدوي لكل تقرير."""
    totals: dict[str, str] = {}
    for col in spec.columns:
        if not col.total:
            continue
        acc = sum((Decimal(str(r.get(col.key) or 0)) for r in rows), ZERO)
        totals[col.key] = _money(acc) if col.kind == KIND_MONEY else _qty(acc)
    return totals


def report_catalog() -> list[dict]:
    """الفهرس مرتَّباً بالفئات — يستهلكه `ReportsHubPage`."""
    by_category: dict[str, list[dict]] = {}
    for spec in REPORTS.values():
        by_category.setdefault(spec.category, []).append({
            "key": spec.key,
            "title": spec.title,
            "description": spec.description,
            "permission": spec.permission,
            "screen_path": spec.screen_path,
            "row_link": spec.row_link,
            "filters": [
                {
                    "key": f.key, "label": f.label, "kind": f.kind,
                    "options": [{"value": v, "label": l} for v, l in f.options],
                    "default": f.default,
                }
                for f in spec.filters
            ],
            "columns": [
                {"key": c.key, "header": c.header, "kind": c.kind,
                 "total": c.total, "width": c.width}
                for c in spec.columns
            ],
        })
    out = []
    for key, label in CATEGORIES:
        reports = sorted(by_category.get(key, []), key=lambda r: r["title"])
        if reports:
            out.append({"key": key, "label": label, "reports": reports})
    return out


#: سقف الصفوف المُرسَلة للمتصفح. دفتر يوميةٍ لشركةٍ عاملة يتجاوز 30 ألف سطر،
#: ورسمها كلها يُجمّد التبويب. الإجماليات تُحسب على الصفوف كاملةً قبل القصّ —
#: فالمعروض ينقص، والمجموع لا يكذب.
MAX_ROWS = 5000


def run_report(key: str, tenant_id: int, params: dict) -> dict:
    """ينفّذ تقريراً ويُعيد الحمولة الكاملة (أعمدة + صفوف + إجماليات)."""
    spec = REPORTS[key]
    rows = spec.build(tenant_id, params or {})
    total_rows = len(rows)
    totals = compute_totals(spec, rows)
    truncated = total_rows > MAX_ROWS
    if truncated:
        rows = rows[:MAX_ROWS]
    logger.info(
        "reports.run key=%s tenant=%s rows=%s truncated=%s params=%s",
        key, tenant_id, total_rows, truncated,
        {k: v for k, v in (params or {}).items() if v},
    )
    return {
        "key": spec.key,
        "title": spec.title,
        "category": spec.category,
        "description": spec.description,
        "row_link": spec.row_link,
        "columns": [
            {"key": c.key, "header": c.header, "kind": c.kind,
             "total": c.total, "width": c.width}
            for c in spec.columns
        ],
        "rows": rows,
        "totals": totals,
        "total_rows": total_rows,
        "truncated": truncated,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }


# ══════════════════════════════════════════════════════════════════════
#  المبيعات
# ══════════════════════════════════════════════════════════════════════

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
    """تجميع أسطر فواتير البيع حسب الصنف أو الماركة — قاعدة واحدة لتقريرين.

    الربح = صافي البيع − (الكمية × متوسط تكلفة الصنف). متوسط التكلفة لحظي (لا
    تاريخي)، وهذا مذكور في وصف التقرير كي لا يُقرأ على أنه تكلفة وقت البيع.
    """
    from sales.models import SalesInvoiceLine

    invoices = _posted_sales(tenant_id, params).values_list("id", flat=True)
    qs = SalesInvoiceLine.objects.filter(
        tenant_id=tenant_id, invoice_id__in=list(invoices),
    ).select_related("product")
    product = _int_param(params, "product")
    if product:
        qs = qs.filter(product_id=product)

    buckets: dict = {}
    for line in qs:
        prod = line.product
        if group == "product":
            key = line.product_id
            label = {
                "sku": getattr(prod, "sku", "") or "",
                "name": getattr(prod, "name_ar", "") or getattr(prod, "name_en", "") or "",
            }
        else:
            key = (getattr(prod, "brand", "") or "— بلا ماركة —")
            label = {"sku": "", "name": key}
        bucket = buckets.setdefault(key, {
            **label, "quantity": ZERO, "net_sales": ZERO, "tax_amount": ZERO, "cost": ZERO,
        })
        qty = Decimal(str(line.quantity or 0))
        bucket["quantity"] += qty
        bucket["net_sales"] += Decimal(str(line.line_total_excl_tax or 0))
        bucket["tax_amount"] += Decimal(str(line.line_tax_amount or 0))
        bucket["cost"] += qty * Decimal(str(getattr(prod, "avg_cost", 0) or 0))

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
        })
    rows.sort(key=lambda r: Decimal(r["net_sales"]), reverse=True)
    return rows


_PRODUCT_SALES_COLUMNS = (
    ReportColumn("sku", "الرمز", width="120px"),
    ReportColumn("name", "الصنف"),
    ReportColumn("quantity", "الكمية", KIND_NUMBER, total=True, width="100px"),
    ReportColumn("net_sales", "صافي المبيعات", KIND_MONEY, total=True),
    ReportColumn("tax_amount", "الضريبة", KIND_MONEY, total=True),
    ReportColumn("cost", "التكلفة", KIND_MONEY, total=True),
    ReportColumn("profit", "الربح", KIND_MONEY, total=True),
    ReportColumn("margin", "الهامش %", KIND_NUMBER, width="90px"),
)

register(ReportSpec(
    key="sales-by-product",
    title="المبيعات حسب الصنف",
    category="sales",
    description="كمّ بيع كل صنف وربحه. التكلفة بمتوسط التكلفة الحالي للصنف.",
    filters=DATE_FILTERS + (ReportFilter("product", "الصنف", "product"),),
    columns=_PRODUCT_SALES_COLUMNS,
    permission="sales.invoice.view",
    build=lambda t, p: _sales_line_aggregate(t, p, group="product"),
))

register(ReportSpec(
    key="sales-by-brand",
    title="المبيعات حسب الماركة",
    category="sales",
    description="أي ماركة تبيع أكثر وأيّها أربح — تجميع أسطر البيع على ماركة الصنف.",
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

AGING_BUCKETS = ((0, 30), (31, 60), (61, 90), (91, None))


def _aging(tenant_id: int, params: dict, *, side: str) -> list[dict]:
    """أعمار الذمم بأربع خانات — المدين للعملاء والدائن للموردين.

    الأساس هو المتبقّي على المستندات المرحّلة نفسها (لا رصيد الحساب) كي يبقى
    التقرير قابلاً للتفسير سطراً سطراً.
    """
    today = _parse_date(params.get("as_of")) or datetime.date.today()
    buckets: dict = {}

    if side == "customer":
        from sales.models import SalesInvoice

        docs = SalesInvoice.objects.filter(
            tenant_id=tenant_id, status=SalesInvoice.STATUS_POSTED,
        ).select_related("customer")
        rows_src = (
            (d.customer_id, d.customer.name if d.customer_id else "",
             d.due_date or d.invoice_date,
             Decimal(str(d.grand_total or 0)) - Decimal(str(d.amount_paid or 0)))
            for d in docs
        )
    else:
        from logistics.models import PurchaseInvoice
        from logistics.services import purchase_invoice_payment_summary

        docs = PurchaseInvoice.objects.filter(
            tenant_id=tenant_id, is_posted=True, is_return=False,
        ).select_related("partner")
        rows_src = (
            (d.partner_id, d.partner.name if d.partner_id else "", d.invoice_date,
             Decimal(str(purchase_invoice_payment_summary(d).get("remaining", 0) or 0)))
            for d in docs
        )

    for partner_id, partner_name, base_date, remaining in rows_src:
        if remaining <= DEC:
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


def _partner_balances(tenant_id: int, params: dict, *, partner_type: str) -> list[dict]:
    """أرصدة الأطراف من دفتر الأستاذ — مدين ودائن ورصيد لكل حساب طرف مربوط."""
    from accounting.models import JournalLine
    from partners.models import Partner

    partners = Partner.objects.filter(
        tenant_id=tenant_id, partner_type=partner_type,
    ).values("id", "name")
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
    build=lambda t, p: _partner_balances(t, p, partner_type="Customer"),
))

register(ReportSpec(
    key="supplier-balances",
    title="أرصدة الموردين",
    category="partners",
    description="مدين ودائن ورصيد كل مورد من واقع القيود المرحّلة.",
    filters=DATE_FILTERS,
    columns=_BALANCE_COLUMNS,
    permission="purchase.invoice.view",
    build=lambda t, p: _partner_balances(t, p, partner_type="Supplier"),
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

    cash_accounts = Account.objects.filter(
        tenant_id=tenant_id, account_type="Asset",
    ).filter(
        Q(code__startswith="1101") | Q(code__startswith="1102")
        | Q(code__startswith="1110") | Q(name__icontains="صندوق")
        | Q(name__icontains="بنك"),
    )
    account = _int_param(params, "account")
    if account:
        cash_accounts = cash_accounts.filter(pk=account)

    qs = JournalLine.objects.filter(
        tenant_id=tenant_id, journal__is_posted=True,
        account_id__in=list(cash_accounts.values_list("id", flat=True)),
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
    description="حركة البضاعة بين المستودعات: من أين إلى أين وكم صنفاً وهل رُحّلت.",
    filters=DATE_FILTERS + (ReportFilter("warehouse", "المستودع", "warehouse"),),
    columns=(
        ReportColumn("number", "رقم التحويل", width="130px"),
        ReportColumn("date", "التاريخ", KIND_DATE, width="110px"),
        ReportColumn("source", "من مستودع"),
        ReportColumn("destination", "إلى مستودع"),
        ReportColumn("line_count", "عدد الأصناف", KIND_INT, total=True, width="100px"),
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
        ReportColumn("line_count", "عدد الأصناف", KIND_INT, total=True, width="100px"),
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
        ReportFilter("product", "الصنف", "product"),
        ReportFilter(
            "status", "الحالة", "select",
            options=(("", "الكل"), ("in_stock", "في المخزون"), ("sold", "مُباع")),
        ),
    ),
    columns=(
        ReportColumn("serial", "الرقم التسلسلي", width="180px"),
        ReportColumn("sku", "الرمز", width="120px"),
        ReportColumn("product_name", "الصنف"),
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
