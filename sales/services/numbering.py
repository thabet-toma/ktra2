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
from django.utils import timezone

logger = logging.getLogger("sales.services")

DEC = Decimal("0.01")



def suggest_fifo_allocations(
    *,
    tenant_id: int,
    partner_id: int,
    amount: Decimal,
) -> list[dict]:
    """اقتراح توزيع دفعة على الفواتير من الأقدم (FIFO) حسب المتبقي."""
    remaining = Decimal(str(amount)).quantize(DEC)
    if remaining <= 0:
        return []
    invs = (
        SalesInvoice.objects.filter(
            tenant_id=tenant_id,
            customer_id=partner_id,
            status=SalesInvoice.STATUS_POSTED,
        )
        .order_by("invoice_date", "id")
    )
    out: list[dict] = []
    for inv in invs:
        if remaining <= 0:
            break
        due = (inv.grand_total - Decimal(str(inv.amount_paid))).quantize(DEC)
        if due <= 0:
            continue
        take = min(due, remaining)
        out.append(
            {
                "invoice": inv.id,
                "invoice_number": inv.invoice_number,
                "amount": str(take),
            }
        )
        remaining -= take
    return out


def _invoice_number_prefix(tenant_id: int, book_number: int, branch=None) -> str:
    """task11 M4: بادئة رقم الفاتورة — رمز الفرع يدخل البادئة لفصل تسلسلات
    الفروع بصرياً ورقمياً. الفرع الرئيسي/بدون فرع يحافظ على الصيغة القديمة."""
    parts = [f"SI-{tenant_id}"]
    if branch is not None and not branch.is_main:
        parts.append(branch.code)
    if book_number != 0:
        parts.append(f"B{book_number}")
    return "-".join(parts) + "-"


def next_invoice_number(tenant_id: int, book_number: int = 0, branch=None) -> str:
    """Thin wrapper حول next_document_number() — N8-T4 + task11 M4 (فرع).

    book_number=0 → manual (any number accepted), generate with tenant prefix.
    book_number>0 → use book prefix for isolated per-book sequence.
    branch (Branch|None) → تسلسل مستقل لكل فرع (None/رئيسي = مستوى الشركة).
    """
    from accounting.services import next_document_number

    branch_id = branch.pk if (branch is not None and not branch.is_main) else None
    seq = next_document_number(
        tenant_id, 'sales_invoice', book_number=book_number, branch_id=branch_id)
    return f"{_invoice_number_prefix(tenant_id, book_number, branch)}{seq}"


def next_quotation_number(tenant_id: int, book_number: int = 0) -> str:
    """رقم عرض السعر التالي — thin wrapper حول next_document_number (تسلسل مستقل
    لعروض الأسعار). الرقم يُولَّد خادمياً (الواجهة لا تُدخله)."""
    from accounting.services import next_document_number

    seq = next_document_number(tenant_id, 'sales_quotation', book_number=book_number)
    return f"QUO-{seq}"


def preview_next_invoice_number(tenant_id: int, book_number: int = 0, branch=None) -> str:
    """Gets the next invoice number for preview without incrementing/persisting it."""
    from tenants.models import TenantBook

    branch_id = branch.pk if (branch is not None and not branch.is_main) else None
    book = TenantBook.objects.filter(
        tenant_id=tenant_id,
        branch_id=branch_id,
        document_type='sales_invoice',
        book_number=book_number
    ).first()

    next_num = (book.last_used_number + 1) if book else 1
    return f"{_invoice_number_prefix(tenant_id, book_number, branch)}{next_num}"


def next_order_number(tenant_id: int) -> str:
    """رقم الطلبية التالي — تسلسل مستقل عن العروض والفواتير."""
    from accounting.services import next_document_number

    seq = next_document_number(tenant_id, 'sales_order', book_number=0)
    return f"ORD-{seq}"


# ─────────────────────────────────────────────────────────────────────────
# T-ORDERS — عروض الأسعار وطلبيات الزبائن (صلاحية، حجز، عربون، إلغاء)
# ─────────────────────────────────────────────────────────────────────────

def _sales_settings(tenant_id: int):
    from sales.models import SalesSettings

    return SalesSettings.objects.filter(tenant_id=tenant_id).first()


def default_quotation_valid_until(tenant_id: int, from_date=None):
    """تاريخ انتهاء صلاحية العرض افتراضياً (إعداد الشركة، 14 يوماً افتراضاً).

    0 يوم = بلا انتهاء (None) — لمن لا يريد صلاحية على عروضه.
    """
    from datetime import date as _date, timedelta

    base = from_date or timezone.localdate()
    ss = _sales_settings(tenant_id)
    days = ss.quotation_valid_days if ss else 14
    if not days:
        return None
    return base + timedelta(days=int(days))


def default_order_reserved_until(tenant_id: int, from_date=None):
    """آخر يوم يحجز فيه الطلب الكمية (إعداد الشركة، 7 أيام افتراضاً)."""
    from datetime import date as _date, timedelta

    base = from_date or timezone.localdate()
    ss = _sales_settings(tenant_id)
    days = ss.order_reserve_days if ss else 7
    if not days:
        return None
    return base + timedelta(days=int(days))


def document_delete_allowed(tenant_id: int) -> bool:
    """هل يُسمح بحذف العروض/الطلبيات لهذه الشركة (الإلغاء متاح دائماً)؟"""
    ss = _sales_settings(tenant_id)
    return True if ss is None else bool(ss.allow_document_delete)


def _active_reservation_lines(tenant_id: int, product_ids=None):
    """بنود الحجز السارية — تعريف واحد يخدم الخريطة والحارس والتقرير معاً."""
    from datetime import date as _date

    from sales.models import SalesOrder, SalesOrderLine

    qs = SalesOrderLine.objects.filter(
        tenant_id=tenant_id,
        order__status=SalesOrder.STATUS_CONFIRMED,
        order__reserved_until__gte=timezone.localdate(),
    )
    if product_ids is not None:
        qs = qs.filter(product_id__in=list(product_ids))
    return qs


def reserved_quantity_map(
    tenant_id: int, product_ids=None, *, exclude_customer_id: int | None = None,
) -> dict:
    """الكمية المحجوزة لكل منتج = بنود طلبيات مؤكَّدة لم ينتهِ حجزها.

    مشتقّة بالكامل من الطلبيات (لا عمود على المنتج): الانتهاء يحرّر الكمية من
    تلقاء نفسه بلا مهمة خلفية، والإلغاء/التحويل يخرجان من الحالة المؤكَّدة.

    `exclude_customer_id`: يتجاهل حجوزات زبون بعينه — حجزُه لا يمنعه هو.
    """
    from django.db.models import Sum

    qs = _active_reservation_lines(tenant_id, product_ids)
    if exclude_customer_id is not None:
        qs = qs.exclude(order__customer_id=exclude_customer_id)
    rows = qs.values("product_id").annotate(total=Sum("quantity"))
    return {r["product_id"]: r["total"] for r in rows if r["total"]}


def reserved_stock_rows(
    tenant_id: int, *, product_id=None, customer_id=None, date_from=None, date_to=None,
) -> list[dict]:
    """«تقرير المحجوزات»: سطر لكل بند طلبية مؤكَّدة ما زال حجزه سارياً.

    يقرأ من نفس مصدر `reserved_quantity_map` كي لا ينحرف التقرير عن الحارس:
    ما يمنعه الترحيل هو بعينه ما يظهر هنا.

    `date_from`/`date_to`: نافذة **«الحجز حتى»** — «ما ينتهي هذا الأسبوع» سؤال
    تشغيلي لا يُجاب بقراءة كل الصفوف بالعين.
    """
    from datetime import date as _date

    qs = (
        _active_reservation_lines(tenant_id, [product_id] if product_id else None)
        .select_related("order", "order__customer", "product")
        .order_by("order__reserved_until", "order__order_number", "id")
    )
    if customer_id:
        qs = qs.filter(order__customer_id=customer_id)
    if date_from:
        qs = qs.filter(order__reserved_until__gte=date_from)
    if date_to:
        qs = qs.filter(order__reserved_until__lte=date_to)
    lines = list(qs)
    reserved_totals = reserved_quantity_map(
        tenant_id, product_ids={line.product_id for line in lines} or None)
    today = timezone.localdate()
    rows = []
    for line in lines:
        product = line.product
        on_hand = Decimal(str(product.quantity_on_hand or 0))
        reserved_total = Decimal(str(reserved_totals.get(line.product_id, 0)))
        rows.append({
            "order_id": line.order_id,
            "order_number": line.order.order_number,
            "order_date": line.order.order_date,
            "reserved_until": line.order.reserved_until,
            "days_left": (line.order.reserved_until - today).days
            if line.order.reserved_until else None,
            "customer_id": line.order.customer_id,
            "customer_name": line.order.customer.name,
            "product_id": line.product_id,
            "product_sku": product.sku,
            "product_name": product.name_ar or product.name_en or product.sku,
            "quantity": str(line.quantity),
            "unit_price": str(line.unit_price),
            "line_total": str(line.line_total),
            "quantity_on_hand": str(on_hand),
            "reserved_quantity": str(reserved_total),
            "available_quantity": str(on_hand - reserved_total),
        })
    logger.debug(
        "reserved_stock.report tenant=%s rows=%s product=%s customer=%s window=%s..%s",
        tenant_id, len(rows), product_id, customer_id, date_from, date_to,
    )
    return rows


def guard_reserved_stock(
    invoice: SalesInvoice,
    lines: list[SalesInvoiceLine],
    products_by_id: dict[int, Product],
) -> None:
    """T-RESERVEGUARD: يمنع ترحيل فاتورة تسحب كمية محجوزة لطلبية **زبون آخر**.

    الحجز كان عرضاً بلا أثر: تُحجز الكمية بطلبية مؤكَّدة، ثم تُرحَّل فاتورة لزبون
    ثانٍ فتخصمها ويبقى صاحب الطلبية بوعدٍ لا رصيد له. الحارس هنا يقارن كمية
    الفاتورة بالمتاح **بعد** حجوزات الآخرين، ويسمّي الطلبيات الحاجزة.

    مُعفى منه: المراجيع، الخدمات، المنتجات التي تسمح بالسالب، وفاتورة صاحب الحجز
    نفسه. ويتوقف كلياً عند إطفاء `block_reserved_stock_sale`.
    """
    from collections import defaultdict

    kind = invoice.invoice_kind or SalesInvoice.INVOICE_KIND_SALE
    if kind != SalesInvoice.INVOICE_KIND_SALE or not invoice.stock_on_post:
        return
    ss = SalesSettings.objects.filter(tenant_id=invoice.tenant_id).first()
    if ss is not None and not ss.block_reserved_stock_sale:
        return

    requested = defaultdict(lambda: Decimal("0"))
    for line in lines:
        product = products_by_id.get(line.product_id) or line.product
        if getattr(product, "is_service", False) or getattr(product, "allow_negative_stock", False):
            continue
        requested[line.product_id] += Decimal(str(line.quantity or 0))
    if not requested:
        return

    others = reserved_quantity_map(
        invoice.tenant_id,
        product_ids=requested.keys(),
        exclude_customer_id=invoice.customer_id,
    )
    if not others:
        return

    shortages = []
    for product_id, quantity in requested.items():
        reserved = Decimal(str(others.get(product_id, 0)))
        if not reserved:
            continue
        product = products_by_id.get(product_id)
        available = Decimal(str(product.quantity_on_hand or 0)) - reserved
        if quantity <= available:
            continue
        blocking = _active_reservation_lines(invoice.tenant_id, [product_id]).exclude(
            order__customer_id=invoice.customer_id
        ).select_related("order", "order__customer")
        holders = "، ".join(
            f"{line.order.order_number} ({line.order.customer.name})" for line in blocking
        )
        shortages.append(
            f"«{product.name_ar or product.name_en or product.sku}»: المطلوب {quantity} "
            f"والمتاح بعد الحجز {available} — محجوز بـ{holders}"
        )
    if not shortages:
        return

    logger.warning(
        "Blocked invoice %s over reserved stock — %s",
        invoice.invoice_number, "؛ ".join(shortages),
    )
    raise ValidationError(
        "لا يمكن ترحيل الفاتورة: الكمية محجوزة لطلبية زبون آخر. "
        + "؛ ".join(shortages)
        + ". ألغِ الحجز أو عدّل الكمية أو أطفئ «منع بيع الكمية المحجوزة» من إعدادات المبيعات."
    )


