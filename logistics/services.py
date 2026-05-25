"""P-H-1: Business-logic services for logistics app.

Mirrors sales/services.py patterns for attached payment vouchers (M2-T3).
"""

from decimal import Decimal, ROUND_HALF_UP

from django.core.exceptions import ValidationError
from django.db import transaction

from accounting.models import Cheque

DEC = Decimal("0.01")


def attach_pi_payment_voucher(
    invoice,
    *,
    cash_amount: Decimal | str | float = 0,
    cash_account_id: int | None = None,
    cheques: list[dict] | None = None,
    user=None,
):
    """يربط سند مالي (نقدي + شيكات) بفاتورة الشراء قبل الترحيل.

    Mirror of sales/services.py:attach_payment_voucher for PurchaseInvoice.

    - Replace-semantics: each call replaces previously-attached Draft cheques.
    - The journal is NOT posted here — post handler reads the attached data.
    - Idempotent when called multiple times pre-post.

    cheques: list of dicts with keys:
        cheque_number (str), amount (Decimal/str), bank_name (str, optional),
        due_date (date/str, optional), issue_date (date/str, optional),
        payee_name (str, optional), notes (str, optional).
    """
    if invoice.is_posted:
        raise ValidationError("لا يمكن تعديل السند بعد ترحيل فاتورة الشراء.")

    cash_amount = Decimal(str(cash_amount or 0)).quantize(DEC)
    if cash_amount < 0:
        raise ValidationError("مبلغ النقدي لا يمكن أن يكون سالباً.")

    cheques = cheques or []
    for i, c in enumerate(cheques):
        if not str(c.get("cheque_number", "")).strip():
            raise ValidationError(f"الشيك #{i+1}: رقم الشيك مطلوب.")
        try:
            amt = Decimal(str(c.get("amount", 0)))
        except Exception:
            raise ValidationError(f"الشيك #{i+1}: مبلغ غير صالح.")
        if amt <= 0:
            raise ValidationError(f"الشيك #{i+1}: المبلغ يجب أن يكون أكبر من صفر.")

    cheques_total = sum(
        (Decimal(str(c.get("amount", 0))) for c in cheques), Decimal("0")
    ).quantize(DEC)

    grand = Decimal(str(invoice.grand_total or 0)).quantize(DEC)
    if (cash_amount + cheques_total) > grand:
        raise ValidationError(
            f"مجموع السند ({cash_amount} نقدي + {cheques_total} شيكات) "
            f"يتجاوز مبلغ الفاتورة {grand}."
        )

    if cash_amount > 0 and not cash_account_id:
        raise ValidationError("لا بدّ من تحديد حساب الصندوق عند وجود مبلغ نقدي.")

    with transaction.atomic():
        invoice.attached_cash_amount = cash_amount
        invoice.save(update_fields=["attached_cash_amount"])

        # Replace previously-linked Draft cheques
        Cheque.objects.filter(
            purchase_invoice=invoice, status="Draft"
        ).delete()
        for c in cheques:
            Cheque.objects.create(
                tenant_id=invoice.tenant_id,
                purchase_invoice=invoice,
                partner=invoice.partner,
                direction="Outgoing",
                status="Draft",
                cheque_number=str(c.get("cheque_number")).strip(),
                bank_name=(c.get("bank_name") or "")[:100],
                amount=Decimal(str(c.get("amount"))).quantize(DEC),
                currency_id=invoice.currency_id,
                due_date=c.get("due_date") or None,
                issue_date=c.get("issue_date") or None,
                payee_name=(c.get("payee_name") or "")[:150],
                notes=c.get("notes") or "",
                created_by=user if user and not getattr(user, "is_anonymous", False) else None,
            )
