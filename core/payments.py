"""
طبقة تجريد موحّدة للدفعات — مصدر حقيقة واحد للتحقق والعرض.

لا تغيّر نماذج البيانات الحالية. توفر:
- PaymentContext: حاوية موحّدة لأي نوع دفعة
- validate_payment(): فحص مشترك (مبلغ > 0، تاريخ، حساب صندوق)
- get_payment_summary(): ملخص موحّد للواجهة
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.core.exceptions import ValidationError


@dataclass(frozen=True)
class PaymentContext:
    """تمثيل موحّد لأي دفعة بغض النظر عن مصدرها."""
    payment_type: str          # 'deal', 'shipment_agent', 'clearance', 'customer'
    payment_id: int
    tenant_id: int
    partner_id: int | None
    amount: Decimal
    currency_id: int | None
    payment_date: Any          # date object
    cash_account_id: int | None
    is_posted: bool
    journal_id: int | None
    notes: str | None
    # حقول إضافية خاصة بالنوع
    extra: dict[str, Any] | None = None

    @classmethod
    def from_deal_payment(cls, payment) -> PaymentContext:
        """LogisticsPayment متعدّد الأشكال: مرتبط إمّا بـ deal أو بـ shipment
        (دفعة وكيل شحن). نكتشف الحالة فلا يخرج tenant_id=0 لدفعات الوكيل.
        """
        from logistics.models import LogisticsPayment
        if not isinstance(payment, LogisticsPayment):
            raise TypeError("Expected LogisticsPayment")

        if payment.deal_id:
            return cls(
                payment_type='deal',
                payment_id=payment.pk,
                tenant_id=payment.deal.tenant_id,
                partner_id=payment.deal.partner_id,
                amount=Decimal(str(payment.amount or 0)),
                currency_id=payment.deal.currency_id,
                payment_date=payment.transfer_date,
                cash_account_id=payment.bank_account_id,
                is_posted=payment.is_posted,
                journal_id=payment.journal_id,
                notes=payment.title,
            )
        if payment.shipment_id:
            shp = payment.shipment
            return cls(
                payment_type='shipment_agent',
                payment_id=payment.pk,
                tenant_id=shp.tenant_id,
                partner_id=shp.shipping_agent_id,
                amount=Decimal(str(payment.amount or 0)),
                currency_id=None,
                payment_date=payment.transfer_date,
                cash_account_id=payment.bank_account_id,
                is_posted=payment.is_posted,
                journal_id=payment.journal_id,
                notes=payment.title,
                extra={'shipment_id': payment.shipment_id},
            )
        raise ValueError(
            f"LogisticsPayment #{payment.pk} غير مرتبط بصفقة ولا بشحنة."
        )

    # دفعات الوكيل تستخدم نفس النموذج (LogisticsPayment عبر shipment)؛
    # alias صريح ليكون استدعاء النوع واضحاً عند نقطة الاستخدام.
    from_agent_payment = from_deal_payment

    @classmethod
    def from_customer_payment(cls, payment) -> PaymentContext:
        from sales.models import CustomerPayment
        if not isinstance(payment, CustomerPayment):
            raise TypeError("Expected CustomerPayment")
        return cls(
            payment_type='customer',
            payment_id=payment.pk,
            tenant_id=payment.tenant_id,
            partner_id=payment.partner_id,
            amount=Decimal(str(payment.amount or 0)),
            currency_id=payment.currency_id,
            payment_date=payment.payment_date,
            cash_account_id=payment.cash_or_bank_account_id,
            is_posted=payment.is_posted,
            journal_id=payment.journal_id,
            notes=payment.notes or None,
        )

    @classmethod
    def from_clearance_payment(cls, payment) -> PaymentContext:
        from logistics.models import LogisticsClearancePayment
        if not isinstance(payment, LogisticsClearancePayment):
            raise TypeError("Expected LogisticsClearancePayment")
        return cls(
            payment_type='clearance',
            payment_id=payment.pk,
            tenant_id=payment.tenant_id,
            partner_id=payment.customs_broker_id,
            amount=Decimal(str(payment.amount or 0)),
            currency_id=payment.currency_id,
            payment_date=payment.payment_date,
            cash_account_id=None,  # cash_box_external_id
            is_posted=payment.is_posted,
            journal_id=payment.journal_id,
            notes=payment.notes,
            extra={'cash_box_external_id': payment.cash_box_external_id},
        )


def validate_payment(ctx: PaymentContext) -> list[str]:
    """فحص مشترك لكل أنواع الدفعات. يُرجع قائمة أخطاء (فارغة = صالح).

    T3-01: الحارس `not ctx.partner_id` يسمو على دفعات التخليص عندما
    customs_broker=None (null=True في النموذج) وعلى دفعات الشحن
    international عندما shipping_agent=None. هذا سلوك مقصود — الدفع
    للشحن الدولي لا يشترط وكيلاً، والتخليص بدون broker مسموح (المستخدم
    يسجّل التكلفة بدون طرف). لا يُرفض partner_id=None لهذه الأنواع.
    """
    errors: list[str] = []
    if ctx.amount <= 0:
        errors.append("المبلغ يجب أن يكون أكبر من صفر.")
    if not ctx.payment_date:
        errors.append("تاريخ الدفعة مطلوب.")
    if ctx.tenant_id in (0, None):
        errors.append("الشركة (tenant) غير محددة.")
    # partner required for deal payments (deal.partner always set) and
    # customer payments (partner required). Skipped for clearance (broker may
    # be None) and shipment-agent (shipping_agent may be None).
    if ctx.payment_type in ('deal', 'customer') and not ctx.partner_id:
        errors.append("الطرف (partner) غير محدد.")
    return errors


def get_payment_summary(ctx: PaymentContext) -> dict[str, Any]:
    """ملخص موحّد للواجهة — نفس الحقول لكل نوع دفعة."""
    return {
        'payment_type': ctx.payment_type,
        'payment_id': ctx.payment_id,
        'partner_id': ctx.partner_id,
        'amount': str(ctx.amount),
        'currency_id': ctx.currency_id,
        'payment_date': str(ctx.payment_date) if ctx.payment_date else None,
        'is_posted': ctx.is_posted,
        'journal_id': ctx.journal_id,
        'notes': ctx.notes,
    }


def post_payment(
    ctx: PaymentContext,
    *,
    description: str,
    debit_account_id: int,
    credit_account_id: int,
    partner_id: int | None = None,
    lines_extra: list[dict] | None = None,
    user=None,
):
    """T4-02: مركز ترحيل الدفعات — يبني lines_data ويستدعي post_journal().

    المسار الوحيد لإنشاء قيد دفعة (توحيد I4-09 مع الترحيل الفعلي).
    يفرض idempotency + فحص فترة مالية + same-tenant lines عبر post_journal().
    """
    from accounting.services import post_journal
    from decimal import Decimal

    lines_data = [
        {
            "account": debit_account_id,
            "partner": partner_id,
            "debit": ctx.amount,
            "credit": Decimal("0"),
            "description": description,
        },
        {
            "account": credit_account_id,
            "partner": partner_id,
            "debit": Decimal("0"),
            "credit": ctx.amount,
            "description": description,
        },
    ]
    if lines_extra:
        lines_data.extend(lines_extra)

    ref_type_map = {
        'deal': 'LOGISTICS_PAYMENT',
        'shipment_agent': 'LOGISTICS_PAYMENT',
        'clearance': 'CLEARANCE_PAYMENT',
        'customer': 'CUSTOMER_PAYMENT',
    }

    return post_journal(
        tenant_id=ctx.tenant_id,
        transaction_date=ctx.payment_date,
        reference_type=ref_type_map.get(ctx.payment_type, 'PAYMENT'),
        reference_id=ctx.payment_id,
        description=description[:500],
        lines_data=lines_data,
        user=user,
    )
