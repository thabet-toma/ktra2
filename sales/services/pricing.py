"""
ترحيل فواتير المبيعات، حركة المخزون، وتحصيل العملاء.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum

from accounting.models import Account, JournalLine
from accounting.services import (
    convert_amount,
    create_audit_log,
    post_journal,
    resolve_forex_account,
    unpost_document,
    validate_fiscal_period,
    validate_journal_entry,
)
from inventory.models import Product, StockMovement
from inventory.serials import (
    consume_sales_serials,
    release_sales_serials,
    restore_returned_sales_serials,
)
from inventory.services import record_stock_movement
from partners.models import Partner, PartnerGroup
from accounting.api import ensure_partner_account
from tenants.models import Tenant

from sales.models import (
    CreditDebitNote,
    CustomerPayment,
    DeliveryOrder,
    DeliveryOrderLine,
    PaymentAllocation,
    SalesInvoice,
    SalesInvoiceLine,
    SalesSettings,
)

logger = logging.getLogger("sales.services")

DEC = Decimal("0.01")



def sales_cogs_map(
    *,
    tenant_id: int,
    invoice_ids,
) -> dict[tuple[int, int], dict]:
    """THA-60 M1: قاعدة تكلفة المبيع التاريخية الموحَّدة — مستهلك واحد للحقيقة.

    تُرجع `{(invoice_id, product_id): {"cost": Decimal, "qty": Decimal}}` بتجميع
    حركات مخزون البيع (`SALE`/`STOCK_ISSUE`) المرتبطة بالفواتير المُمرَّرة، في
    **استعلام تجميعي واحد** (لا استعلام داخل حلقة).

    التكلفة هنا تاريخية بحقّ: `record_stock_movement` يخزّن الصادر بكمية موجبة
    و`total_cost = qty × avg_cost_before` لحظة الترحيل/التسليم، فمجموعها هو
    تكلفة البضاعة المباعة كما كانت يومها — لا يحرّكها شراء لاحق يرفع المتوسط.
    حركة التسليم نفسها `reference_type="SALE"` (قيد `SALES_DELIVERY_COGS` قيدٌ لا
    حركة)، فتكلفة التسليم داخلة في القاعدة تلقائياً.

    محصورة بالشركة؛ `invoice_ids` فارغة ⇒ `{}` بلا استعلام.
    """
    ids = list(invoice_ids or [])
    if not ids:
        return {}
    rows = (
        StockMovement.objects.filter(
            tenant_id=tenant_id,
            reference_type__in=("SALE", "STOCK_ISSUE"),
            reference_id__in=ids,
        )
        .values("reference_id", "product_id")
        .annotate(cost=Sum("total_cost"), qty=Sum("quantity"))
    )
    return {
        (r["reference_id"], r["product_id"]): {
            "cost": Decimal(str(r["cost"] or "0")),
            "qty": Decimal(str(r["qty"] or "0")),
        }
        for r in rows
    }


def invoice_profits(
    *,
    tenant_id: int,
    branch=None,
    date_from: str | None = None,
    date_to: str | None = None,
    customer_id: int | None = None,
) -> dict:
    """task18 DEF-C4: تقرير أرباح الفواتير المرحَّلة.

    الإيراد = صافي البنود قبل الضريبة (subtotal_excl_tax − خصم الفاتورة) — يطابق
    الدائن في قيد الإيراد. التكلفة من `sales_cogs_map` (THA-60 M1) — القاعدة
    التاريخية الموحَّدة نفسها التي تقرأها تقارير «حسب الصنف/الماركة»، فلا يوجد
    رقما ربح متنافسان في المنصة. الربح = الإيراد − التكلفة.

    محصور بالشركة (والفرع غير الرئيسي إن مُرّر) وبفواتير البيع (لا مراجيع)، مع
    التسامح مع الصفوف القديمة بلا نوع (null/"") التي لا تنشأ إلا من مسارات SQL
    خام سابقة لهجرة 0012 — تُعامَل مبيعاتٍ كما يعاملها قسم التقارير.
    """
    qs = SalesInvoice.objects.filter(
        tenant_id=tenant_id,
        status=SalesInvoice.STATUS_POSTED,
    ).filter(
        Q(invoice_kind=SalesInvoice.INVOICE_KIND_SALE) | Q(invoice_kind__isnull=True)
        | Q(invoice_kind=""),
    )
    if branch is not None and not getattr(branch, "is_main", False):
        qs = qs.filter(branch=branch)
    if date_from:
        qs = qs.filter(invoice_date__gte=date_from)
    if date_to:
        qs = qs.filter(invoice_date__lte=date_to)
    if customer_id:
        qs = qs.filter(customer_id=customer_id)
    qs = qs.select_related("customer").order_by("-invoice_date", "-id")

    invoice_ids = list(qs.values_list("id", flat=True))
    cogs_map: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    for (inv_id, _product_id), cell in sales_cogs_map(
        tenant_id=tenant_id, invoice_ids=invoice_ids,
    ).items():
        cogs_map[inv_id] += cell["cost"]

    rows: list[dict] = []
    tot_rev = Decimal("0")
    tot_cost = Decimal("0")
    for inv in qs:
        revenue = (inv.subtotal_excl_tax - inv.invoice_discount).quantize(DEC)
        cost = cogs_map.get(inv.id, Decimal("0")).quantize(DEC)
        profit = (revenue - cost).quantize(DEC)
        margin = (profit / revenue * 100).quantize(DEC) if revenue > 0 else Decimal("0")
        rows.append(
            {
                "invoice": inv.id,
                "invoice_number": inv.invoice_number,
                "invoice_date": inv.invoice_date.isoformat() if inv.invoice_date else None,
                "customer": inv.customer_id,
                "customer_name": getattr(inv.customer, "name", "") or "",
                "revenue": str(revenue),
                "cost": str(cost),
                "profit": str(profit),
                "margin_pct": str(margin),
            }
        )
        tot_rev += revenue
        tot_cost += cost

    tot_profit = (tot_rev - tot_cost).quantize(DEC)
    tot_margin = (tot_profit / tot_rev * 100).quantize(DEC) if tot_rev > 0 else Decimal("0")
    return {
        "rows": rows,
        "totals": {
            "count": len(rows),
            "revenue": str(tot_rev.quantize(DEC)),
            "cost": str(tot_cost.quantize(DEC)),
            "profit": str(tot_profit),
            "margin_pct": str(tot_margin),
        },
    }


def last_sale_price(
    *,
    tenant_id: int,
    product_id: int,
    customer_id: int | None = None,
) -> dict:
    """task18 DEF-C2: آخر سعر بيع للوحدة لهذا الصنف (واختيارياً لهذا العميل).

    يُرجع أحدث `unit_price` من سطور فواتير بيع مرحَّلة. إن مُرّر customer_id
    فُضِّل آخر سعر لذلك العميل، وإلا فآخر سعر عام. يُمكّن الواجهة من اقتراح السعر.
    """
    qs = SalesInvoiceLine.objects.filter(
        tenant_id=tenant_id,
        product_id=product_id,
        invoice__status=SalesInvoice.STATUS_POSTED,
        invoice__invoice_kind=SalesInvoice.INVOICE_KIND_SALE,
    )
    line = None
    if customer_id:
        line = (
            qs.filter(invoice__customer_id=customer_id)
            .order_by("-invoice__invoice_date", "-invoice_id")
            .first()
        )
    if line is None:
        line = qs.order_by("-invoice__invoice_date", "-invoice_id").first()
    if line is None:
        return {"unit_price": None, "invoice_number": None, "invoice_date": None}
    return {
        "unit_price": str(line.unit_price),
        "invoice_number": line.invoice.invoice_number,
        "invoice_date": line.invoice.invoice_date.isoformat() if line.invoice.invoice_date else None,
    }


def customer_price_list(*, tenant_id: int, customer_id: int) -> list[dict]:
    """DEF-004: عرض السعر لكل العميل عبر كامل الكتالوج.

    لكل منتج فعّال:
      - إن اشتراه العميل سابقاً (فاتورة بيع مرحَّلة) → سعر آخر فاتورة (للقراءة فقط).
      - وإلا → عرض السعر اليدوي المحفوظ (قابل للتحرير)، أو فارغ إن لم يُحفظ.
    لا أثر محاسبي — مصدر تسعير احتياطي فقط.
    """
    from sales.models import CustomerProductQuote

    last_by_product: dict[int, SalesInvoiceLine] = {}
    lowest_by_product: dict[int, SalesInvoiceLine] = {}
    lines = (
        SalesInvoiceLine.objects.filter(
            tenant_id=tenant_id,
            invoice__customer_id=customer_id,
            invoice__status=SalesInvoice.STATUS_POSTED,
            invoice__invoice_kind=SalesInvoice.INVOICE_KIND_SALE,
        )
        .select_related("invoice")
        .order_by("product_id", "-invoice__invoice_date", "-invoice_id", "-id")
    )
    for ln in lines:
        if ln.product_id not in last_by_product:
            last_by_product[ln.product_id] = ln
        if ln.product_id not in lowest_by_product or ln.unit_price < lowest_by_product[ln.product_id].unit_price:
            lowest_by_product[ln.product_id] = ln

    quotes = {
        q.product_id: q
        for q in CustomerProductQuote.objects.filter(tenant_id=tenant_id, customer_id=customer_id)
    }

    # عرض سعر «واجهة العروض» (SalesQuotation) — أحدث سطر لكل منتج لهذا العميل. يظهر
    # في القائمة (وخيارات الفاتورة) حتى للعروض القديمة التي لم تُعبّئ كرت الزبون.
    from sales.models import SalesQuotationLine

    sq_by_product: dict[int, SalesQuotationLine] = {}
    for sl in (
        SalesQuotationLine.objects.filter(
            tenant_id=tenant_id, quotation__customer_id=customer_id,
        )
        .select_related("quotation")
        .order_by("product_id", "-quotation__quotation_date", "-quotation_id", "-id")
    ):
        if sl.product_id not in sq_by_product:
            sq_by_product[sl.product_id] = sl

    rows: list[dict] = []
    products = Product.objects.filter(tenant_id=tenant_id).order_by("name_ar", "sku")
    for p in products:
        ln_last = last_by_product.get(p.id)
        ln_lowest = lowest_by_product.get(p.id)
        q = quotes.get(p.id)
        sq = sq_by_product.get(p.id)
        name = p.name_ar or p.name_en or p.sku or f"#{p.id}"
        
        prices = []
        if ln_last:
            prices.append({
                "label": "آخر فاتورة",
                "unit_price": str(ln_last.unit_price),
                "source_type": "SALES_INVOICE",
                "document_id": ln_last.invoice_id,
                "invoice_number": ln_last.invoice.invoice_number,
            })
        if ln_lowest and (not ln_last or ln_lowest.invoice_id != ln_last.invoice_id):
            prices.append({
                "label": "أقل سعر",
                "unit_price": str(ln_lowest.unit_price),
                "source_type": "SALES_INVOICE",
                "document_id": ln_lowest.invoice_id,
                "invoice_number": ln_lowest.invoice.invoice_number,
            })
            
        if not prices and sq is not None and Decimal(str(sq.unit_price)) > 0:
            prices.append({
                "label": "عرض السعر",
                "unit_price": str(sq.unit_price),
                "source_type": "QUOTE",
                "document_id": None,  # عرض (لا فاتورة) — نتفادى رابط فاتورة خاطئ
                "invoice_number": sq.quotation.quotation_number,
            })
        if not prices and q is not None:
            prices.append({
                "label": "عرض السعر",
                "unit_price": str(q.unit_price),
                "source_type": "QUOTE",
                "document_id": q.id,
                "invoice_number": None,
            })
        # آخر مصدر: «سعر البيع» العام في كرت الصنف — يظهر فقط حين لا شراء سابق
        # لهذا الزبون ولا عرض له. تبقى الخانة قابلة للتحرير لحفظ عرض خاص به.
        if not prices and p.sale_price is not None and Decimal(str(p.sale_price)) > 0:
            prices.append({
                "label": "سعر عام (كرت الصنف)",
                "unit_price": str(p.sale_price),
                "source_type": "PRODUCT",
                "document_id": None,
                "invoice_number": None,
            })

        if prices:
            rows.append({
                "product_id": p.id,
                "sku": p.sku,
                "name": name,
                "price": prices[0]["unit_price"],
                "source": (
                    "last_invoice" if prices[0]["source_type"] == "SALES_INVOICE"
                    else "default" if prices[0]["source_type"] == "PRODUCT"
                    else "quote"
                ),
                "source_label": prices[0]["label"],
                # السعر العام ليس عرضاً للزبون — يبقى قابلاً للتحرير ليُحفظ عرضه الخاص.
                "editable": prices[0]["source_type"] in ("QUOTE", "PRODUCT"),
                "invoice_number": prices[0]["invoice_number"],
                "prices": prices,
            })
        else:
            rows.append({
                "product_id": p.id,
                "sku": p.sku,
                "name": name,
                "price": None,
                "source": "quote",
                "source_label": "عرض السعر / يدوي",
                "editable": True,
                "invoice_number": None,
                "prices": [],
            })
    return rows


@transaction.atomic
def save_customer_quotes(*, tenant_id: int, customer_id: int, entries: list[dict]) -> int:
    """DEF-004: حفظ/تحديث/حذف عروض الأسعار اليدوية لعميل.

    كل عنصر: {"product": id, "unit_price": value}. قيمة فارغة/صفر/سالبة ⇒ حذف
    العرض. يُرجع عدد العروض المحفوظة (غير المحذوفة).
    """
    from sales.models import CustomerProductQuote

    saved = 0
    for e in entries or []:
        pid = e.get("product")
        if pid in (None, ""):
            continue
        try:
            pid = int(pid)
        except (TypeError, ValueError):
            continue
        raw = e.get("unit_price")
        try:
            price = Decimal(str(raw)) if raw not in (None, "") else None
        except (TypeError, ValueError):
            price = None
        if price is None or price <= 0:
            CustomerProductQuote.objects.filter(
                tenant_id=tenant_id, customer_id=customer_id, product_id=pid
            ).delete()
            continue
        CustomerProductQuote.objects.update_or_create(
            tenant_id=tenant_id, customer_id=customer_id, product_id=pid,
            defaults={"unit_price": price},
        )
        saved += 1
    return saved


