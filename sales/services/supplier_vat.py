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
from .calc import resolve_cheques_payable_account
from .flow import allocate_customer_payment

def post_supplier_payment(payment: 'SupplierPayment', *, user=None) -> 'SupplierPayment':
    """ترحيل سند صرف لمورد: Dr AP / Cr Cash."""
    from sales.models import SupplierPayment as SP
    if payment.is_posted:
        raise ValidationError("سند الصرف مرحّل مسبقاً.")
    if payment.partner.tenant_id != payment.tenant_id:
        raise ValidationError("المورد لا يتبع نفس الشركة.")
    validate_fiscal_period(payment.tenant_id, payment.payment_date)

    from logistics.services import _resolve_ap_account
    ap_account = _resolve_ap_account(payment.partner)

    # T-ONEPAY: شيكات داخل السند — مبلغها جزء من مبلغ السند لا إضافة عليه، ولا
    # يخرج من الصندوق بل يصير التزاماً على «شيكات برسم الدفع» حتى يُصرف.
    total = Decimal(str(payment.amount)).quantize(DEC)
    payment_cheques = list(payment.cheques.all()) if payment.pk else []
    cheques_total = sum(
        (Decimal(str(c.amount or 0)) for c in payment_cheques), Decimal("0")
    ).quantize(DEC)
    if cheques_total > total + DEC:
        raise ValidationError(
            f"مجموع الشيكات ({cheques_total}) يتجاوز مبلغ السند ({total})."
        )
    cash_part = (total - cheques_total).quantize(DEC)

    credit_lines: list[dict] = []
    if cash_part > 0:
        credit_lines.append({
            "account": payment.cash_or_bank_account_id,
            # T-CASH2: حساب الصندوق/البنك لا يَحمل المورد — وإلا حُسبت
            # حركة النقدية ضمن ذمم المورد فلا يُصفّر السند رصيده. فقط
            # سطر الذمم (AP) يَحمل الشريك.
            "partner": None,
            "debit": Decimal("0"),
            "credit": cash_part,
            "description": f"من الصندوق — {payment.partner.name}",
        })
    if cheques_total > 0:
        payable_acc = resolve_cheques_payable_account(payment.tenant_id)
        credit_lines.append({
            "account": payable_acc.id,
            "partner": None,
            "debit": Decimal("0"),
            "credit": cheques_total,
            "description": f"شيكات صادرة — {payment.partner.name}",
        })

    with transaction.atomic():
        jh = post_journal(
            tenant_id=payment.tenant_id,
            transaction_date=payment.payment_date,
            reference_type='SUPPLIER_PAYMENT',
            reference_id=payment.id,
            description=f"سند صرف — {payment.partner.name} ({payment.amount})",
            lines_data=[
                {
                    "account": ap_account.id,
                    "partner": payment.partner_id,
                    "debit": total,
                    "credit": Decimal("0"),
                    "description": f"دفع مورد — {payment.partner.name}",
                },
                *credit_lines,
            ],
            currency=payment.currency,
            exchange_rate=payment.exchange_rate,
            user=user,
        )
        payment.journal = jh
        payment.is_posted = True
        payment.save(update_fields=["journal", "is_posted"])
        # الشيكات الصادرة تخرج من المسودة بترحيل السند (كما في الجانب الوارد).
        if payment_cheques:
            from accounting.models import Cheque
            Cheque.objects.filter(
                supplier_payment=payment, status="Draft"
            ).update(status="Under_Collection")
        create_audit_log(
            tenant=payment.tenant,
            user=user,
            action="POST",
            model_name="SupplierPayment",
            object_id=payment.id,
            change_details=f"Posted supplier payment journal={jh.id}",
        )
    return payment


def unpost_supplier_payment(payment: 'SupplierPayment', *, user=None) -> dict:
    """التراجع عن ترحيل سند صرف: حذف قيوده وإعادة شيكاته إلى مسودة — مرآة
    `unpost_customer_payment`.

    بخلاف الجانب الوارد لا مبالغ تُعكس على فواتير الشراء: «المدفوع» هناك مشتق
    لا مخزَّن — `purchase_invoice_payment_summary` ونظيرتها SQL
    (`annotate_purchase_invoice_payment_summary`) كلتاهما تفلتران على
    `is_posted=True`، فقلبُ الراية يكفي المكانين معاً وتعود الفواتير الموزَّع
    عليها «غير مسدَّدة» تلقائياً. التوزيعات تبقى (ربط بلا قيد) فتُحتسب من جديد
    عند إعادة الترحيل.
    """
    from sales.models import SupplierPayment as SP
    if not payment.is_posted:
        raise ValidationError("السند غير مرحّل.")
    with transaction.atomic():
        payment = SP.objects.select_for_update().get(pk=payment.pk)
        if not payment.is_posted:
            raise ValidationError("السند غير مرحّل.")
        result = unpost_document(
            tenant_id=payment.tenant_id,
            reference_id=payment.id,
            journal_reference_types=["SUPPLIER_PAYMENT"],
            user=user,
            document_label=f"سند صرف #{payment.id}",
        )
        payment.is_posted = False
        payment.journal = None
        payment.save(update_fields=["is_posted", "journal"])

        # الشيكات الصادرة تعود مسودةً (عكسُ ما فعله الترحيل تماماً).
        from accounting.models import Cheque
        Cheque.objects.filter(
            supplier_payment=payment, status="Under_Collection"
        ).update(status="Draft")

        create_audit_log(
            tenant=payment.tenant,
            user=user,
            action="UNPOST",
            model_name="SupplierPayment",
            object_id=payment.id,
            change_details=(
                f"Unposted supplier payment {payment.id}: "
                f"{result['journals_deleted']} journal(s)"
            ),
        )
    logger.info(
        "Unposted supplier payment %s (journals=%s).",
        payment.id, result["journals_deleted"],
    )
    return result


def allocate_supplier_payment(
    payment: 'SupplierPayment', allocations: list[dict], *, user=None
) -> 'SupplierPayment':
    """T-ONACC (المورد): توزيع سند صرف على فواتير شراء — مرآة
    `allocate_customer_payment`.

    بعد الترحيل التوزيع **ربط فقط بلا قيد جديد**: ذمم المورد دُينت وقت الترحيل
    (Dr AP / Cr صندوق) فالتوزيع لا يغيّر أي رصيد دفتري — يحدّد فقط أي فاتورة
    استهلكت أي جزء من السند (يقود `purchase_invoice_payment_summary`).
    """
    from logistics.models import PurchaseInvoice
    from logistics.services import purchase_invoice_payment_summary
    from sales.models import SupplierPayment as SP, SupplierPaymentAllocation

    rows = [
        (int(a["invoice"]), Decimal(str(a.get("amount") or "0")))
        for a in (allocations or [])
    ]
    if not rows:
        raise ValidationError("لا توزيعات مُرسَلة.")
    if any(amt <= 0 for _inv_id, amt in rows):
        raise ValidationError("مبلغ التوزيع يجب أن يكون أكبر من صفر.")

    with transaction.atomic():
        payment = SP.objects.select_for_update().get(pk=payment.pk)
        already = (
            SupplierPaymentAllocation.objects.filter(payment=payment).aggregate(
                t=Sum("amount")
            )["t"]
            or Decimal("0")
        )
        total_new = sum((amt for _inv_id, amt in rows), Decimal("0"))
        if already + total_new > Decimal(str(payment.amount)) + DEC:
            raise ValidationError(
                f"مجموع التوزيعات ({already + total_new}) يتجاوز مبلغ السند "
                f"({payment.amount}). المتاح للتوزيع: {Decimal(str(payment.amount)) - already}."
            )

        invoices = {
            inv.pk: inv
            for inv in PurchaseInvoice.objects.select_for_update().filter(
                pk__in={inv_id for inv_id, _amt in rows}, tenant_id=payment.tenant_id
            )
        }
        for inv_id, amt in rows:
            inv = invoices.get(inv_id)
            if inv is None:
                raise ValidationError(f"فاتورة الشراء #{inv_id} غير موجودة في هذه الشركة.")
            if inv.partner_id != payment.partner_id:
                raise ValidationError(
                    f"فاتورة الشراء #{inv.invoice_number} لا تخص نفس المورد."
                )
            if not inv.is_posted:
                raise ValidationError(f"فاتورة الشراء #{inv.invoice_number} غير مرحّلة.")

            if payment.currency_id == inv.currency_id:
                amount_in_inv_curr, conv_rate = amt, Decimal("1")
            else:
                amount_in_inv_curr, conv_rate = convert_amount(
                    amount=amt,
                    from_currency_id=payment.currency_id,
                    to_currency_id=inv.currency_id,
                    tenant_id=payment.tenant_id,
                    effective_date=payment.payment_date,
                )
            remaining = purchase_invoice_payment_summary(inv)["remaining_balance"]
            if amount_in_inv_curr > remaining + DEC:
                raise ValidationError(
                    f"مبلغ التوزيع ({amount_in_inv_curr}) يتجاوز المتبقي على "
                    f"فاتورة الشراء #{inv.invoice_number} ({remaining})."
                )

            SupplierPaymentAllocation.objects.create(
                tenant_id=payment.tenant_id,
                payment=payment,
                invoice=inv,
                amount=amt,
                amount_in_invoice_currency=amount_in_inv_curr,
                conversion_rate=conv_rate,
            )
            # ملخّص الدفع مُخزَّن على الكائن — نُبطله كي يعكس التوزيع الجديد.
            inv._payment_summary_cache = None
            logger.info(
                "Supplier payment %s allocated %s → purchase invoice %s",
                payment.id, amt, inv.invoice_number,
            )

        create_audit_log(
            tenant=payment.tenant,
            user=user,
            action="ALLOCATE",
            model_name="SupplierPayment",
            object_id=payment.id,
            change_details=(
                f"Allocated {total_new} to {len(rows)} purchase invoice(s); "
                f"total allocated={already + total_new} of {payment.amount}"
            ),
        )

    return payment


# ── N8-T13: VatStatement builder ─────────────────────────────

def build_vat_statement(
    tenant_id: int,
    period_from,
    period_to,
    *,
    user=None,
):
    """يُولّد كشف ض.ق.م دوري — يَجمع الفواتير المرحَّلة في الفترة بـvat_statement IS NULL.

    P-H-6: مَلفوف بـtransaction.atomic() + select_for_update على الفواتير المؤهَّلة
    لمنع سباق مُولِّدَيْن مُتزامنَيْن. كما يَرفض الفترات المتداخلة مع كشوف موجودة.
    """
    from sales.models import VatStatement
    from accounting.services import next_document_number

    with transaction.atomic():
        # P-H-6: reject overlapping period windows for the same tenant.
        # Combined with the DB-level UniqueConstraint on
        # (tenant, period_from, period_to) this catches both exact-match
        # races and accidental overlap.
        overlap = VatStatement.objects.filter(
            tenant_id=tenant_id,
            period_from__lte=period_to,
            period_to__gte=period_from,
        ).first()
        if overlap:
            raise ValidationError(
                f"يوجد كشف ضريبة يُغطّي هذه الفترة بالفعل: «{overlap.statement_number}» "
                f"({overlap.period_from} → {overlap.period_to})."
            )

        # Lock the candidate invoices so a concurrent generator cannot
        # claim the same rows under a different statement.
        invoices = list(
            SalesInvoice.objects.select_for_update().filter(
                tenant_id=tenant_id,
                status=SalesInvoice.STATUS_POSTED,
                invoice_date__gte=period_from,
                invoice_date__lte=period_to,
                vat_statement__isnull=True,
            ).select_related('currency')
        )

        total_sales_vat = Decimal('0.00')
        total_purchase_vat = Decimal('0.00')

        # task11 R2-A2: المراجيع تُخصم لا تُضاف — مرجع البيع يخفّض ضريبة
        # المخرجات ومرجع الشراء يخفّض ضريبة المدخلات (كانت تُجمع موجبة
        # فيتضخم الكشف من الجهتين).
        for inv in invoices:
            amt = Decimal(str(inv.tax_amount or 0))
            if inv.invoice_kind == SalesInvoice.INVOICE_KIND_SALE:
                total_sales_vat += amt
            elif inv.invoice_kind == SalesInvoice.INVOICE_KIND_SALE_RETURN:
                total_sales_vat -= amt
            elif inv.invoice_kind == SalesInvoice.INVOICE_KIND_PURCHASE:
                total_purchase_vat += amt
            else:  # purchase_return
                total_purchase_vat -= amt

        net_vat = (total_sales_vat - total_purchase_vat).quantize(Decimal('0.01'))
        stmt_no = f"VAT-{next_document_number(tenant_id, 'vat_statement')}"

        stmt = VatStatement.objects.create(
            tenant_id=tenant_id,
            statement_number=stmt_no,
            period_from=period_from,
            period_to=period_to,
            total_sales_vat=total_sales_vat.quantize(Decimal('0.01')),
            total_purchase_vat=total_purchase_vat.quantize(Decimal('0.01')),
            net_vat=net_vat,
            created_by=user,
        )

        # Re-issue the update by pk to use the lock acquired above.
        invoice_ids = [inv.pk for inv in invoices]
        updated = SalesInvoice.objects.filter(pk__in=invoice_ids).update(vat_statement=stmt)

        create_audit_log(
            tenant=stmt.tenant,
            user=user,
            action="CREATE",
            model_name="VatStatement",
            object_id=stmt.id,
            change_details=f"Created VAT statement {stmt_no}: {updated} invoices linked, net={net_vat}",
        )
        return stmt


