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
            if product.is_service or product.allow_negative_stock:
                continue
            available = (
                Decimal(str(product.quantity_on_hand or 0))
                - Decimal(str(existing_reservations.get(product_id, 0)))
            )
            if quantity > available:
                shortages.append(
                    f"{product}: المطلوب {quantity} والمتاح بعد الحجوزات {available}"
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


def post_credit_debit_note(note: CreditDebitNote, *, user=None) -> CreditDebitNote:
    """Post a credit/debit note via the canonical `post_journal()`.

    Account resolution (in priority order):
      • Revenue: related_invoice.revenue_account → SalesSettings default → first Revenue account.
      • AR:      related_invoice.accounts_receivable_account → customer.linked_account
                 → customer.group.account_receivable → SalesSettings default.

    Journal lines (both note types balance Dr=Cr=note.amount):
      • Credit note: Dr Revenue (reverse sale) / Cr AR (release receivable).
      • Debit  note: Dr AR (extra receivable) / Cr Revenue (extra sale).

    Idempotent via `post_journal()`'s `(reference_type, reference_id)` lock.
    """
    if note.status == CreditDebitNote.STATUS_POSTED:
        raise ValidationError("الإشعار مرحَّل مسبقاً.")
    if note.status == CreditDebitNote.STATUS_CANCELLED:
        raise ValidationError("لا يمكن ترحيل إشعار ملغي.")
    amt = Decimal(str(note.amount or 0)).quantize(DEC)
    if amt <= 0:
        raise ValidationError("مبلغ الإشعار يجب أن يكون أكبر من صفر.")

    # ── Resolve revenue account ─────────────────────────────────────────
    revenue_account_id = None
    if note.related_invoice_id and note.related_invoice.revenue_account_id:
        revenue_account_id = note.related_invoice.revenue_account_id
    if not revenue_account_id:
        revenue_account_id = _default_revenue_account(note.tenant_id).id

    # ── Resolve AR account (mirror `_resolve_ar_account` semantics) ────
    ar_account_id = None
    if note.related_invoice_id and note.related_invoice.accounts_receivable_account_id:
        ar_account_id = note.related_invoice.accounts_receivable_account_id
    if not ar_account_id:
        cust: Partner = note.customer
        if cust.linked_account_id:
            ar_account_id = cust.linked_account_id
        elif cust.group_id:
            g = PartnerGroup.objects.filter(pk=cust.group_id).first()
            if g and g.account_receivable_id:
                ar_account_id = g.account_receivable_id
        if not ar_account_id:
            ss = SalesSettings.objects.filter(tenant_id=note.tenant_id).first()
            if ss and ss.default_ar_account_id:
                ar_account_id = ss.default_ar_account_id
    if not ar_account_id:
        raise ValidationError(
            "لا يوجد حساب ذمم: عيّن حساباً مرتبطاً بالعميل أو في إعدادات المبيعات."
        )

    # ── Build journal lines per note type ──────────────────────────────
    if note.note_type == CreditDebitNote.TYPE_CREDIT:
        dr_acc, cr_acc = revenue_account_id, ar_account_id
        dr_desc, cr_desc = "تخفيض إيراد", "إشعار دائن للعميل"
    else:  # debit
        dr_acc, cr_acc = ar_account_id, revenue_account_id
        dr_desc, cr_desc = "إشعار مدين للعميل", "زيادة إيراد"

    journal_lines = [
        {
            "account": dr_acc,
            "partner": note.customer_id if dr_acc == ar_account_id else None,
            "debit": amt,
            "credit": Decimal("0"),
            "description": dr_desc,
        },
        {
            "account": cr_acc,
            "partner": note.customer_id if cr_acc == ar_account_id else None,
            "debit": Decimal("0"),
            "credit": amt,
            "description": cr_desc,
        },
    ]

    # ── Currency: inherit from related invoice if any, else first tenant currency
    currency = None
    exchange_rate = Decimal("1")
    if note.related_invoice_id:
        currency = note.related_invoice.currency
        exchange_rate = Decimal(str(note.related_invoice.exchange_rate or 1))

    with transaction.atomic():
        jh = post_journal(
            tenant_id=note.tenant_id,
            transaction_date=note.note_date,
            reference_type="CREDIT_DEBIT_NOTE",
            reference_id=note.id,
            description=f"إشعار {note.get_note_type_display()} — {note.note_number}",
            lines_data=journal_lines,
            currency=currency,
            exchange_rate=exchange_rate,
            user=user,
        )
        note.journal = jh
        note.status = CreditDebitNote.STATUS_POSTED
        note.save(update_fields=["journal", "status"])

        create_audit_log(
            tenant=note.tenant,
            user=user,
            action="POST",
            model_name="CreditDebitNote",
            object_id=note.id,
            change_details=f"Posted {note.get_note_type_display()} — journal={jh.id}",
        )

    return note


# ── N8-T12: Supplier Payment ──────────────────────────────────

