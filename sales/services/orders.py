"""
ترحيل فواتير المبيعات، حركة المخزون، وتحصيل العملاء.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import timedelta
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
from inventory.services import product_display_name, record_stock_movement
from partners.models import Partner
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



# المرحلة 3: مراجع عبر وحدات الحزمة (نفس الملف سابقاً) — الرسم البياني لا-دوري.
from .numbering import default_order_reserved_until, next_invoice_number, next_order_number, reserved_quantity_map
from .calc import _default_revenue_account, _resolve_ar_account
from .flow import post_customer_payment
from django.utils import timezone

def _recalculate_order_totals(order) -> None:
    """يعيد حساب إجماليات الطلبية من بنودها (بلا ضريبة سطرية بعد — مسجّل)."""
    subtotal = Decimal("0.00")
    for line in order.lines.all():
        line_total = (
            Decimal(str(line.quantity)) * Decimal(str(line.unit_price))
            - Decimal(str(line.line_discount or 0))
        ).quantize(DEC)
        if line.line_total != line_total:
            line.line_total = line_total
            line.save(update_fields=["line_total"])
        subtotal += line_total
    order.subtotal = subtotal.quantize(DEC)
    order.grand_total = (
        subtotal - Decimal(str(order.discount_amount or 0)) + Decimal(str(order.tax_amount or 0))
    ).quantize(DEC)
    order.save(update_fields=["subtotal", "grand_total"])


def confirm_sales_order(order, *, user=None):
    """تأكيد الطلبية بعد حجز الكمية فعلياً ومنع تجاوز المتاح.

    تُقفل الطلبية والمنتجات داخل معاملة واحدة، ثم يُطرح حجز الطلبيات المؤكدة
    الأخرى من الرصيد الحالي. الخدمات والمنتجات التي تسمح بالسالب لا تعيق التأكيد.
    """
    from collections import defaultdict

    from sales.models import SalesOrder

    with transaction.atomic():
        locked = (
            SalesOrder.objects.select_for_update()
            .prefetch_related("lines__product")
            .get(pk=order.pk)
        )
        if locked.status in (SalesOrder.STATUS_CONVERTED, SalesOrder.STATUS_CANCELLED):
            raise ValidationError("لا يمكن تأكيد طلبية محوّلة أو ملغاة.")
        if locked.status == SalesOrder.STATUS_CONFIRMED:
            return locked

        requested = defaultdict(lambda: Decimal("0"))
        for line in locked.lines.all():
            requested[line.product_id] += Decimal(str(line.quantity))
        products = {
            product.pk: product
            for product in Product.objects.select_for_update().filter(
                tenant_id=locked.tenant_id, pk__in=requested.keys())
        }
        existing_reservations = reserved_quantity_map(
            locked.tenant_id, product_ids=requested.keys())
        shortages = []
        for product_id, quantity in requested.items():
            product = products.get(product_id)
            if product is None:
                shortages.append(f"المنتج #{product_id} غير متاح في الشركة الحالية")
                continue
            if product.is_service:
                continue
            available = (
                Decimal(str(product.quantity_on_hand or 0))
                - Decimal(str(existing_reservations.get(product_id, 0)))
            )
            if quantity > available:
                shortages.append(
                    f"{product_display_name(product)}: المطلوب {quantity} "
                    f"والمتاح بعد الحجوزات {available}"
                )
        if shortages:
            raise ValidationError(
                "لا يمكن تأكيد الطلبية لعدم كفاية الكمية: " + "؛ ".join(shortages)
            )

        locked.status = SalesOrder.STATUS_CONFIRMED
        locked.reserved_until = default_order_reserved_until(locked.tenant_id)
        locked.save(update_fields=["status", "reserved_until"])

    log_order_activity(
        locked, action="update", description="تأكيد طلبية وحجز الكمية", user=user)
    logger.info(
        "sales_order.confirm order=%s tenant=%s reserved_until=%s",
        locked.id, locked.tenant_id, locked.reserved_until,
    )
    return locked


def convert_quotation_to_order(quotation, *, user=None):
    """عرض سعر → طلبية مؤكَّدة تحجز الكمية حتى `reserved_until`.

    idempotent: العرض المحوَّل أو الملغى لا يُحوَّل ثانيةً.
    """
    from sales.models import SalesOrder, SalesOrderLine, SalesQuotation

    if quotation.status in (SalesQuotation.STATUS_CONVERTED, SalesQuotation.STATUS_CANCELLED):
        raise ValidationError(
            f"عرض السعر {quotation.quotation_number} بحالة "
            f"«{quotation.get_status_display()}» — لا يقبل التحويل."
        )

    tenant_id = quotation.tenant_id
    with transaction.atomic():
        order = SalesOrder.objects.create(
            tenant=quotation.tenant,
            order_number=next_order_number(tenant_id),
            customer=quotation.customer,
            order_date=quotation.quotation_date,
            reserved_until=default_order_reserved_until(tenant_id),
            status=SalesOrder.STATUS_CONFIRMED,
            currency=quotation.currency,
            exchange_rate=quotation.exchange_rate,
            discount_amount=quotation.discount_amount,
            tax_amount=quotation.tax_amount,
            quotation=quotation,
            notes=quotation.notes or "",
            created_by=user if (user and getattr(user, "is_authenticated", False)) else None,
        )
        for ln in quotation.lines.all():
            SalesOrderLine.objects.create(
                tenant=quotation.tenant,
                order=order,
                product=ln.product,
                quantity=ln.quantity,
                unit_price=ln.unit_price,
                line_discount=ln.line_discount,
                tax_rate=ln.tax_rate,
            )
        _recalculate_order_totals(order)
        quotation.status = SalesQuotation.STATUS_CONVERTED
        quotation.save(update_fields=["status"])

    log_order_activity(
        order, action="create", description="طلبية من عرض سعر", user=user)
    logger.info(
        "sales_order.from_quotation order=%s quotation=%s tenant=%s reserved_until=%s",
        order.id, quotation.id, tenant_id, order.reserved_until,
    )
    return order


def convert_order_to_invoice(order, *, user=None):
    """طلبية → فاتورة بيع (مسودة). التحويل ينهي الحجز — البضاعة صارت مفوترة."""
    from sales.models import SalesInvoice, SalesOrder
    from sales.serializers import SalesInvoiceSerializer

    if order.status == SalesOrder.STATUS_CONVERTED and order.invoice_id:
        raise ValidationError(
            f"الطلبية {order.order_number} محوّلة أصلاً إلى فاتورة "
            f"#{order.invoice.invoice_number}."
        )
    if order.status == SalesOrder.STATUS_CANCELLED:
        raise ValidationError(f"الطلبية {order.order_number} ملغاة — لا تُحوَّل.")

    lines_data = [
        {
            "product": ln.product_id,
            "quantity": ln.quantity,
            "unit_price": ln.unit_price,
            "line_discount": ln.line_discount,
            "tax_rate": ln.tax_rate_id,
        }
        for ln in order.lines.all()
    ]
    inv_ser = SalesInvoiceSerializer(data={
        "invoice_number": next_invoice_number(order.tenant_id),
        "customer": order.customer_id,
        "invoice_date": order.order_date,
        "currency": order.currency_id,
        "exchange_rate": order.exchange_rate,
        "invoice_type": "credit",
        "invoice_discount": order.discount_amount,
        "lines": lines_data,
    })
    if not inv_ser.is_valid():
        raise ValidationError(f"بيانات الفاتورة غير صالحة: {inv_ser.errors}")

    with transaction.atomic():
        invoice = inv_ser.save(
            tenant=order.tenant,
            created_by=user if (user and getattr(user, "is_authenticated", False)) else None,
        )
        order.invoice = invoice
        order.status = SalesOrder.STATUS_CONVERTED
        # انتهاء الحجز: الكمية لم تعد محجوزة بل مفوترة.
        order.reserved_until = None
        order.save(update_fields=["invoice", "status", "reserved_until"])

    log_order_activity(
        order, action="convert", description=f"تحويل طلبية إلى فاتورة {invoice.invoice_number}",
        user=user)
    logger.info(
        "sales_order.to_invoice order=%s invoice=%s tenant=%s",
        order.id, invoice.id, order.tenant_id,
    )
    return invoice


def cancel_sales_order(order, *, user=None, reason: str = ""):
    """إلغاء طلبية — تبقى في السجل ويُفرَج عن حجزها فوراً (لا حذف)."""
    from sales.models import SalesOrder

    if order.status == SalesOrder.STATUS_CONVERTED:
        raise ValidationError("الطلبية محوّلة إلى فاتورة — ألغِ الفاتورة بدلاً منها.")
    if order.status == SalesOrder.STATUS_CANCELLED:
        return order
    order.status = SalesOrder.STATUS_CANCELLED
    order.cancel_reason = (reason or "")[:250]
    order.reserved_until = None
    order.save(update_fields=["status", "cancel_reason", "reserved_until"])
    log_order_activity(order, action="cancel", description=reason or "إلغاء طلبية", user=user)
    logger.info("sales_order.cancel order=%s tenant=%s", order.id, order.tenant_id)
    return order


def cancel_quotation(quotation, *, user=None, reason: str = ""):
    """إلغاء عرض سعر — بديل الحذف: المستند وسجلّه يبقيان."""
    from sales.models import SalesQuotation

    if quotation.status == SalesQuotation.STATUS_CONVERTED:
        raise ValidationError("عرض السعر محوَّل — ألغِ المستند الناتج عنه بدلاً منه.")
    if quotation.status == SalesQuotation.STATUS_CANCELLED:
        return quotation
    quotation.status = SalesQuotation.STATUS_CANCELLED
    quotation.save(update_fields=["status"])
    from core.activity import log_activity
    log_activity(
        action="cancel", entity_type="sales_quotation", entity_id=quotation.id,
        entity_label=quotation.quotation_number, description=reason or "إلغاء عرض سعر",
        partner_ids=[quotation.customer_id], user=user, tenant=quotation.tenant,
    )
    logger.info("sales_quotation.cancel id=%s tenant=%s", quotation.id, quotation.tenant_id)
    return quotation


def record_order_deposit(order, *, amount, cash_account_id, user=None, payment_date=None):
    """عربون الطلبية = سند قبض «على الحساب» مرحَّل ومربوط بها.

    لا قيد خاص بالطلبية: العربون مالٌ قُبض فعلاً، فيمرّ من نفس محرّك سندات
    القبض (Dr صندوق / Cr ذمم العميل) ويظهر في كشف حسابه كأي دفعة مقدمة.
    """
    from datetime import date as _date

    from sales.models import CustomerPayment, SalesOrder

    amount = Decimal(str(amount or 0)).quantize(DEC)
    if amount <= 0:
        raise ValidationError("مبلغ العربون يجب أن يكون أكبر من صفر.")
    if not cash_account_id:
        raise ValidationError("اختر حساب الصندوق/البنك لقبض العربون.")

    with transaction.atomic():
        order = SalesOrder.objects.select_for_update().get(pk=order.pk)
        if order.status == SalesOrder.STATUS_CANCELLED:
            raise ValidationError("الطلبية ملغاة — لا يُسجَّل عليها عربون.")
        if order.status == SalesOrder.STATUS_CONVERTED:
            raise ValidationError(
                "الطلبية محوّلة إلى فاتورة — سجّل الدفعة على الفاتورة الناتجة."
            )
        already = (
            order.deposits.filter(is_posted=True).aggregate(total=Sum("amount"))["total"]
            or Decimal("0")
        )
        if already + amount > Decimal(str(order.grand_total or 0)) + DEC:
            raise ValidationError(
                f"العربون ({already + amount}) يتجاوز إجمالي الطلبية ({order.grand_total})."
            )
        payment = CustomerPayment.objects.create(
            tenant=order.tenant,
            partner=order.customer,
            payment_date=payment_date or timezone.localdate(),
            amount=amount,
            currency=order.currency,
            exchange_rate=order.exchange_rate,
            cash_or_bank_account_id=cash_account_id,
            sales_order=order,
            notes=f"عربون طلبية {order.order_number}"[:500],
        )
        post_customer_payment(payment, user=user)
        payment.refresh_from_db()
        order.deposit_amount = (already + amount).quantize(DEC)
        order.save(update_fields=["deposit_amount"])

    log_order_activity(
        order, action="payment", description=f"عربون {amount}", user=user)
    logger.info(
        "sales_order.deposit order=%s payment=%s tenant=%s",
        order.id, payment.id, order.tenant_id,
    )
    return payment


def log_order_activity(order, *, action: str, description: str = "", user=None) -> None:
    """سجل نشاط موحّد للطلبية — يظهر في السجل العام وفي كرت الزبون."""
    from core.activity import log_activity

    log_activity(
        action=action, entity_type="sales_order", entity_id=order.id,
        entity_label=order.order_number, description=description,
        partner_ids=[order.customer_id], user=user, tenant=order.tenant,
    )


def convert_quotation_to_invoice(quotation, user=None):
    """إنشاء SalesInvoice من SalesQuotation (T4-01).

    idempotent: عرض بـ status='converted' و invoice != None يُرفض.
    """
    from sales.models import SalesInvoice, SalesInvoiceLine, SalesQuotation
    from sales.serializers import SalesInvoiceSerializer

    if quotation.status == SalesQuotation.STATUS_CONVERTED and quotation.invoice_id:
        raise ValueError(
            f"عرض السعر {quotation.quotation_number} محوّل بالفعل إلى فاتورة "
            f"#{quotation.invoice.invoice_number}."
        )

    if quotation.status not in (SalesQuotation.STATUS_ACCEPTED, SalesQuotation.STATUS_DRAFT):
        raise ValueError(
            f"لا يمكن تحويل عرض بسالة '{quotation.status}' إلى فاتورة. "
            f"الحالات المقبولة: مسودة أو مقبول."
        )

    tenant = quotation.tenant
    invoice_number = next_invoice_number(tenant.TenantID)

    lines_data = []
    for ln in quotation.lines.all():
        lines_data.append({
            "product": ln.product_id,
            "quantity": ln.quantity,
            "unit_price": ln.unit_price,
            "line_discount": ln.line_discount,
            "tax_rate": ln.tax_rate_id,
        })

    # customer/currency حقول PrimaryKeyRelatedField ⇒ تُمرَّر كـ pk لا ككائن،
    # وtenant/created_by يُحقنان عبر save() تماماً كما يفعل الـ ViewSet (لا حقول
    # على الـ serializer). خلاف ذلك يرفض الـ serializer الكائنات:
    # "Incorrect type. Expected pk value, received Partner/Currency."
    inv_data = {
        "invoice_number": invoice_number,
        "customer": quotation.customer_id,
        "invoice_date": quotation.quotation_date,
        "currency": quotation.currency_id,
        "exchange_rate": quotation.exchange_rate,
        "invoice_type": "credit",
        # خصم العرض يعبر إلى فاتورته — كان يسقط هنا وحده (التحويل إلى طلبية
        # يحمله)، فيُفوتَر الزبون بأكثر ممّا عُرِض عليه وقَبِله.
        "invoice_discount": quotation.discount_amount,
        "lines": lines_data,
    }

    inv_ser = SalesInvoiceSerializer(data=inv_data)
    if not inv_ser.is_valid():
        raise ValueError(f"بيانات الفاتورة غير صالحة: {inv_ser.errors}")

    with transaction.atomic():
        invoice = inv_ser.save(
            tenant=tenant,
            created_by=user if (user and getattr(user, "is_authenticated", False)) else None,
        )
        quotation.status = SalesQuotation.STATUS_CONVERTED
        quotation.invoice = invoice
        quotation.save(update_fields=["status", "invoice"])

    return invoice


# ─────────────────────────────────────────────────────────────────────────
# ISSUE #53 — الأتعاب المتكرّرة (قرار 22): «كرّر فاتورة الشهر الماضي» بنقرةٍ
# واحدة بدل مجدولٍ زمني أو cron. لا كيان فوترةٍ جديد — نسخٌ إلى فاتورة بيع
# عادية بتاريخ اليوم ورقمٍ جديد من نفس الدفتر.
# ─────────────────────────────────────────────────────────────────────────

def _previous_month_bounds(today):
    first_of_this_month = today.replace(day=1)
    last_of_prev_month = first_of_this_month - timedelta(days=1)
    first_of_prev_month = last_of_prev_month.replace(day=1)
    return first_of_prev_month, last_of_prev_month


def last_month_invoice_for_customer(tenant_id, customer_id, today=None):
    """آخر فاتورة بيعٍ للعميل ضمن الشهر الميلادي السابق — أساس التكرار."""
    from sales.models import SalesInvoice

    today = today or timezone.localdate()
    date_from, date_to = _previous_month_bounds(today)
    return (
        SalesInvoice.objects.filter(
            tenant_id=tenant_id, customer_id=customer_id,
            invoice_kind=SalesInvoice.INVOICE_KIND_SALE,
            invoice_date__gte=date_from, invoice_date__lte=date_to,
        )
        .order_by("-invoice_date", "-id")
        .first()
    )


def duplicate_invoice_for_today(source, *, user=None, today=None):
    """ينسخ فاتورةً إلى مسودةٍ جديدة بتاريخ اليوم ورقمٍ جديد من نفس الدفتر.

    نفس مسار الإنشاء (`SalesInvoiceSerializer`) الذي يستعمله `convert_quotation_to_invoice`
    — لا كتابة مباشرة على `SalesInvoice`/`SalesInvoiceLine`، فيمرّ الترحيل اللاحق
    بنفس محرّك `post_sales_invoice` بلا فرق عن فاتورة أُدخلت يدوياً.
    """
    from sales.serializers import SalesInvoiceSerializer

    today = today or timezone.localdate()
    invoice_number = next_invoice_number(
        source.tenant_id, book_number=source.book_number, branch=source.branch,
    )
    lines_data = [{
        "product": ln.product_id,
        "quantity": ln.quantity,
        "unit_price": ln.unit_price,
        "line_discount": ln.line_discount,
        "tax_rate": ln.tax_rate_id,
    } for ln in source.lines.all()]

    inv_data = {
        "invoice_number": invoice_number,
        "customer": source.customer_id,
        "invoice_date": today,
        "currency": source.currency_id,
        "exchange_rate": source.exchange_rate,
        "invoice_type": source.invoice_type,
        "invoice_discount": source.invoice_discount,
        "discount_percent": source.discount_percent,
        "notes": source.notes or "",
        "lines": lines_data,
    }

    inv_ser = SalesInvoiceSerializer(data=inv_data)
    if not inv_ser.is_valid():
        raise ValueError(f"بيانات الفاتورة غير صالحة: {inv_ser.errors}")

    with transaction.atomic():
        invoice = inv_ser.save(
            tenant=source.tenant,
            branch=source.branch,
            created_by=user if (user and getattr(user, "is_authenticated", False)) else None,
        )
    return invoice


# ─────────────────────────────────────────────────────────────────────────
# M4-T4 — Credit / Debit notes posting
# ─────────────────────────────────────────────────────────────────────────

def next_credit_debit_note_number(tenant_id: int, note_type: str) -> str:
    """Thin wrapper حول next_document_number() — N8-T4.

    Prefix: `CN-` for credit, `DN-` for debit.
    """
    from accounting.services import next_document_number

    doc_type = 'credit_note' if note_type == CreditDebitNote.TYPE_CREDIT else 'debit_note'
    prefix = "CN" if note_type == CreditDebitNote.TYPE_CREDIT else "DN"
    seq = next_document_number(tenant_id, doc_type)
    return f"{prefix}-{seq:04d}"


#: نوع الدائن ← كود الحساب المقابل الافتراضي (مصروفه). المورد يسقط إلى تكلفة المبيعات.
_CREDITOR_COUNTER_CODES = {
    "CustomsBroker": "5307",
    "FreightForwarder": "5301",
    "LocalTransporter": "5305",
    "Carrier": "5305",
}
#: حسابات لا تكون مقابلاً: الذمم (قيدُ ذمّةٍ على ذمّة يُيتّم الرصيد) والمخزون (قيمته
#: تتبع طبقات الكلفة — قيدٌ عليه بلا طبقة يكسر تطابق الدفتر والطبقات)، والنقد والبنوك
#: (الإشعار ليس دفعاً: DN-0001 على الإنتاج أنقص الصندوق بلا حركة نقد).
_BLOCKED_COUNTER_SUB_TYPES = {"receivable", "payable", "inventory", "cash_box", "bank"}
NOTE_IS_NOT_PAYMENT = "الإشعار ليس دفعاً؛ للنقد استعمل سند صرف/قبض."


def _note_is_creditor(note) -> bool:
    from partners.models import is_creditor_party

    return is_creditor_party(note.partner)


def _note_party_account(note) -> Account:
    """ذمّة الطرف: الدائن من `_resolve_ap_account`، والعميل من ذمّة فاتورته ثم ذمّته."""
    if _note_is_creditor(note):
        from logistics.services import _resolve_ap_account

        return _resolve_ap_account(note.partner)
    if note.related_invoice_id and note.related_invoice.accounts_receivable_account_id:
        return note.related_invoice.accounts_receivable_account
    from .flow import _resolve_ar_account_for_partner

    return _resolve_ar_account_for_partner(note.partner)


def credit_debit_counter_account_error(account, tenant_id: int) -> str | None:
    """سبب رفض الحساب مقابلاً للإشعار، أو `None` إن صلح."""
    from accounting.account_classification import sub_type_for_account
    from accounting.api import money_account_kind

    if account is None:
        return "اختر الحساب المقابل."
    if account.tenant_id != tenant_id:
        return "الحساب المقابل من شركة أخرى."
    if not account.is_active:
        return f"الحساب «{account.code} {account.name}» غير نشط."
    if account.children.exists():
        return f"«{account.code} {account.name}» حساب مجمِّع — اختر حساباً فرعياً."
    if money_account_kind(account):
        return f"«{account.code} {account.name}» — {NOTE_IS_NOT_PAYMENT}"
    sub_type = sub_type_for_account(account)
    if sub_type == "inventory":
        return "حساب المخزون لا يُعدَّل بإشعار — قيمته تتبع طبقات الكلفة."
    if sub_type in _BLOCKED_COUNTER_SUB_TYPES or Partner.objects.filter(
        tenant_id=tenant_id, linked_account_id=account.id,
    ).exists():
        return f"«{account.code} {account.name}» حساب ذمم — الإشعار يقيد على ذمّة الطرف تلقائياً."
    return None


def _usable_counter(account, tenant_id):
    return account if account and credit_debit_counter_account_error(account, tenant_id) is None else None


def _code_account(tenant_id: int, code: str):
    return _usable_counter(Account.objects.filter(tenant_id=tenant_id, code=code).first(), tenant_id)


def _linked_document_counter(note):
    """حساب مصروف/إيراد المستند المربوط — `None` إن لم يُعرف منه."""
    tenant_id = note.tenant_id
    if note.related_invoice_id:
        return _usable_counter(note.related_invoice.revenue_account, tenant_id)
    if note.related_clearance_id:
        from logistics.accruals import _journal_debit_sources
        from logistics.domain.party_accruals import accrual_journal_ids

        sources = _journal_debit_sources(accrual_journal_ids("clearance", note.related_clearance))
        by_id = Account.objects.in_bulk([acc for acc, _w in sources])
        for acc_id, _weight in sorted(sources, key=lambda s: s[1], reverse=True):
            acc = by_id.get(acc_id)
            if acc and acc.account_type == "Expense" and _usable_counter(acc, tenant_id):
                return acc
        return None
    if note.related_local_shipment_id:
        return _usable_counter(note.related_local_shipment.expense_account, tenant_id)
    if note.related_purchase_invoice_id:
        from logistics.models import PurchaseInvoiceItem

        rows = (
            PurchaseInvoiceItem.objects.filter(
                invoice_id=note.related_purchase_invoice_id, expense_account__isnull=False,
            )
            .values("expense_account").annotate(total=Sum("total_price")).order_by("-total")
        )
        for row in rows:
            acc = _usable_counter(Account.objects.filter(pk=row["expense_account"]).first(), tenant_id)
            if acc:
                return acc
    return None


def default_note_counter_account(note) -> Account:
    """الحساب المقابل الافتراضي: مصروف/إيراد المستند المربوط، وإلا حسب نوع الطرف.

    عميل ← الإيرادات (سلوك M4-T4) · مخلّص 5307 · وكيل شحن 5301 · ناقل 5305 ·
    مورد ← تكلفة المبيعات (إعدادات المبيعات ثم 5101) — لا المخزون: الخصم على بضاعةٍ
    بيع أغلبها لا يُقيَّد على مخزونٍ بلا طبقات. آخر سقوط: أول مصروفٍ فرعيٍّ نشط.
    """
    tenant_id = note.tenant_id
    acc = _linked_document_counter(note)
    if acc:
        return acc
    if not _note_is_creditor(note):
        return _default_revenue_account(tenant_id)
    code = _CREDITOR_COUNTER_CODES.get(note.partner.partner_type)
    if code:
        acc = _code_account(tenant_id, code)
    else:
        ss = SalesSettings.objects.filter(tenant_id=tenant_id).select_related("default_cogs_account").first()
        acc = _usable_counter(ss.default_cogs_account if ss else None, tenant_id) or _code_account(tenant_id, "5101")
    if acc:
        return acc
    for candidate in Account.objects.filter(
        tenant_id=tenant_id, account_type="Expense", is_active=True, children__isnull=True,
    ).order_by("code"):
        if _usable_counter(candidate, tenant_id):
            return candidate
    raise ValidationError("لا يوجد حساب مصروف صالح مقابلاً للإشعار — اختر الحساب المقابل يدوياً.")


#: حقل الربط ← مالك المستند (يجب أن يكون طرف الإشعار نفسه).
_LINK_OWNER = {
    "related_invoice": lambda d: d.customer_id,
    "related_purchase_invoice": lambda d: d.partner_id,
    "related_clearance": lambda d: d.customs_broker_id,
    "related_local_shipment": lambda d: d.carrier_id,
    "related_shipment": lambda d: d.shipping_agent_id,
}
#: حقل الربط ← هل استحقاق المستند مرحَّل؟ (التسوية تطفئ مستحقّاً قائماً في الدفتر.)
_LINK_POSTED = {
    "related_purchase_invoice": lambda d: bool(d.is_posted),
    "related_clearance": lambda d: bool(d.journal_id),
    "related_local_shipment": lambda d: bool(d.is_posted),
    "related_shipment": lambda d: bool(d.freight_is_posted),
}


def validate_credit_debit_note(note) -> None:
    """قواعد الإشعار قبل الحفظ والترحيل: المبلغ والضريبة، ربطٌ واحد لنفس الطرف، والمقابل."""
    tenant_id = note.tenant_id
    if note.partner.tenant_id != tenant_id:
        raise ValidationError("الطرف لا يتبع نفس الشركة.")
    amount = Decimal(str(note.amount or 0)).quantize(DEC)
    tax = Decimal(str(note.tax_amount or 0)).quantize(DEC)
    if amount <= 0:
        raise ValidationError("مبلغ الإشعار يجب أن يكون أكبر من صفر.")
    if tax < 0 or tax >= amount:
        raise ValidationError("الضريبة جزءٌ من المبلغ: بين صفر والمبلغ الإجمالي.")
    if Decimal(str(note.exchange_rate or 0)) <= 0:
        raise ValidationError("سعر الصرف يجب أن يكون أكبر من صفر.")

    linked = note.linked_fields()
    if len(linked) > 1:
        raise ValidationError("اربط الإشعار بمستندٍ واحد فقط.")
    if linked:
        field = linked[0]
        doc = getattr(note, field)
        if doc.tenant_id != tenant_id or _LINK_OWNER[field](doc) != note.partner_id:
            raise ValidationError("المستند المربوط لا يخصّ هذا الطرف.")
        posted = _LINK_POSTED.get(field)
        if posted and not posted(doc):
            raise ValidationError("المستند المربوط غير مرحَّل بعد — رحّله أولاً.")
        if field == "related_purchase_invoice":
            if doc.is_return:
                raise ValidationError("اربط الإشعار بفاتورة الشراء الأصلية لا بمرتجعها.")
            if note.currency_id != doc.currency_id:
                raise ValidationError("عملة الإشعار يجب أن تطابق عملة فاتورة الشراء المربوطة.")

    if note.counter_account_id:
        error = credit_debit_counter_account_error(note.counter_account, tenant_id)
        if error:
            raise ValidationError(error)


#: حقل الربط ← صنف المستحق اللوجستي في `logistics.domain.party_accruals`.
_NOTE_ACCRUAL_KIND = (
    ("related_clearance", "clearance"),
    ("related_local_shipment", "local"),
    ("related_shipment", "freight"),
)


def _linked_settlement_remaining(note):
    """متبقّي المستند الذي يُطفئه الإشعار المدين المربوط — بعملة الإشعار؛ `None` بلا تسوية."""
    if note.related_purchase_invoice_id:
        from logistics.services import purchase_invoice_payment_summary

        return purchase_invoice_payment_summary(note.related_purchase_invoice)["remaining_balance"]
    for field, kind in _NOTE_ACCRUAL_KIND:
        if getattr(note, f"{field}_id"):
            from logistics.domain.party_accruals import accrual_remaining

            rate = Decimal(str(note.exchange_rate or 1))
            return (accrual_remaining(kind, getattr(note, field)) / rate).quantize(DEC)
    return None


def post_credit_debit_note(note: CreditDebitNote, *, user=None) -> CreditDebitNote:
    """ترحيل الإشعار على أيّ طرف عبر `post_journal()` — مرجع `CREDIT_DEBIT_NOTE`.

      • مدين: Dr ذمّة الطرف (المبلغ) / Cr المقابل (المبلغ − الضريبة) / Cr الضريبة.
      • دائن: Cr ذمّة الطرف / Dr المقابل / Dr الضريبة.
    الضريبة مخرجاتٌ للعميل (`resolve_output_vat_account`) ومدخلاتٌ للدائن (1105).
    العملة الأجنبية تملأ `amount_currency` تلقائياً من `post_journal`. المقابل الفارغ
    يُحلّ بـ`default_note_counter_account` ويُحفظ على الإشعار.
    """
    if note.status == CreditDebitNote.STATUS_POSTED:
        raise ValidationError("الإشعار مرحَّل مسبقاً.")
    if note.status == CreditDebitNote.STATUS_CANCELLED:
        raise ValidationError("لا يمكن ترحيل إشعار ملغي.")
    validate_credit_debit_note(note)

    amount = Decimal(str(note.amount)).quantize(DEC)
    tax = Decimal(str(note.tax_amount or 0)).quantize(DEC)
    creditor = _note_is_creditor(note)
    party_account = _note_party_account(note)
    counter = note.counter_account or default_note_counter_account(note)
    error = credit_debit_counter_account_error(counter, note.tenant_id)
    if error:
        raise ValidationError(error)

    is_debit = note.note_type == CreditDebitNote.TYPE_DEBIT
    party_label = note.partner.name
    if is_debit and creditor:
        # مرآة `allocate_voucher_to_accruals`: التسوية لا تتجاوز المتبقّي — الزائد
        # بلا ربطٍ يبقى رصيداً عاماً على الطرف بدل «مدفوعٍ» فوق المستحق.
        remaining = _linked_settlement_remaining(note)
        if remaining is not None and amount > remaining + DEC:
            raise ValidationError(
                f"الإشعار ({amount}) أكبر من متبقّي المستند المربوط ({remaining}) — "
                "خفّضه أو اتركه بلا ربط ليبقى رصيداً عاماً على الطرف."
            )

    def line(account_id, value, *, party_side, description, partner_id=None):
        on_debit = is_debit == party_side
        return {
            "account": account_id, "partner": partner_id,
            "debit": value if on_debit else Decimal("0"),
            "credit": Decimal("0") if on_debit else value,
            "description": description,
        }

    journal_lines = [
        line(party_account.id, amount, party_side=True, partner_id=note.partner_id,
             description=f"إشعار {'مدين' if is_debit else 'دائن'} — {party_label}"),
        line(counter.id, amount - tax, party_side=False,
             description=note.reason or f"إشعار {note.note_number}"),
    ]
    if tax > 0:
        if creditor:
            from logistics.services import _resolve_vat_input_account

            vat_account = _resolve_vat_input_account(note.tenant_id)
        else:
            from accounting.services import resolve_output_vat_account

            vat_account = resolve_output_vat_account(note.tenant_id)
            if not vat_account:
                raise ValidationError(
                    "ضريبة المخرجات تتطلب نسبة ضريبة مخرجات أو حساب «2104» من نوع Liability."
                )
        journal_lines.append(line(
            vat_account.id, tax, party_side=False,
            description=f"ضريبة {'مدخلات' if creditor else 'مخرجات'} — إشعار {note.note_number}",
        ))

    with transaction.atomic():
        jh = post_journal(
            tenant_id=note.tenant_id,
            transaction_date=note.note_date,
            reference_type="CREDIT_DEBIT_NOTE",
            reference_id=note.id,
            description=f"إشعار {note.get_note_type_display()} — {note.note_number} — {party_label}",
            lines_data=journal_lines,
            currency=note.currency,
            exchange_rate=Decimal(str(note.exchange_rate or 1)),
            user=user,
        )
        note.journal = jh
        note.counter_account = counter
        note.status = CreditDebitNote.STATUS_POSTED
        note.save(update_fields=["journal", "counter_account", "status", "updated_at"])

        create_audit_log(
            tenant=note.tenant,
            user=user,
            action="POST",
            model_name="CreditDebitNote",
            object_id=note.id,
            change_details=f"Posted {note.get_note_type_display()} — journal={jh.id}",
        )
    logger.info(
        "credit_debit_note.posted tenant=%s note=%s journal=%s creditor=%s",
        note.tenant_id, note.id, jh.id, creditor,
    )
    return note


def unpost_credit_debit_note(note: CreditDebitNote, *, user=None) -> CreditDebitNote:
    """إلغاء ترحيل الإشعار بالمسار الموحّد `unpost_document` — يعود مسودةً قابلةً للتعديل."""
    if note.status != CreditDebitNote.STATUS_POSTED:
        raise ValidationError("الإشعار غير مرحَّل.")
    with transaction.atomic():
        unpost_document(
            tenant_id=note.tenant_id,
            reference_id=note.id,
            journal_reference_types=["CREDIT_DEBIT_NOTE"],
            user=user,
            document_label=f"إشعار {note.note_number}",
        )
        note.journal = None
        note.status = CreditDebitNote.STATUS_DRAFT
        note.save(update_fields=["journal", "status", "updated_at"])
    logger.info("credit_debit_note.unposted tenant=%s note=%s", note.tenant_id, note.id)
    return note


def cancel_credit_debit_note(note: CreditDebitNote, *, user=None) -> CreditDebitNote:
    """إلغاء إشعارٍ مسودة — المرحَّل يُلغى ترحيله أولاً."""
    if note.status != CreditDebitNote.STATUS_DRAFT:
        raise ValidationError("يُلغى الإشعار وهو مسودة فقط — ألغِ ترحيله أولاً.")
    note.status = CreditDebitNote.STATUS_CANCELLED
    note.save(update_fields=["status", "updated_at"])
    create_audit_log(
        tenant=note.tenant, user=user, action="UPDATE", model_name="CreditDebitNote",
        object_id=note.id, change_details=f"Cancelled {note.note_number}",
    )
    return note


# ── N8-T12: Supplier Payment ──────────────────────────────────

