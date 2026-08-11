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


def should_auto_post_payment(tenant, request_data: Any = None) -> bool:
    """T-AUTOPOST: هل يُرحَّل السند فور الحفظ؟ (سند قبض العميل وسند صرف المورد).

    مصدر حقيقة واحد للطرفين: الراية الصريحة `auto_post` في جسم الطلب تسمو على
    إعداد الشركة `SalesSettings.auto_post_payments` (الافتراضي: مُفعَّل — لا معنى
    لمسودة سند دفع). نفس عقد `auto_post` المستخدم في فواتير المبيعات.
    """
    flag = (request_data or {}).get("auto_post") if hasattr(request_data, "get") else None
    if flag is True or str(flag).lower() == "true":
        return True
    if flag is False or str(flag).lower() == "false":
        return False
    if tenant is None:
        return False
    from sales.services import get_or_create_sales_settings

    ss = get_or_create_sales_settings(tenant)
    return bool(ss and ss.auto_post_payments)


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


def document_payment_summary(total, paid) -> dict[str, Any]:
    """ملخص دفع موحّد للمستندات: مدفوع/جزئي/غير مدفوع مع متبقٍ غير سالب."""
    total_dec = Decimal(str(total or 0)).quantize(Decimal("0.01"))
    paid_dec = Decimal(str(paid or 0)).quantize(Decimal("0.01"))
    if total_dec <= 0:
        status = "unpaid"
        paid_dec = Decimal("0.00")
    else:
        paid_dec = min(max(paid_dec, Decimal("0.00")), total_dec)
        status = (
            "paid" if paid_dec >= total_dec
            else "partially_paid" if paid_dec > 0
            else "unpaid"
        )
    remaining = max(total_dec - paid_dec, Decimal("0.00"))
    return {
        "amount_paid": paid_dec,
        "remaining_balance": remaining,
        "payment_status": status,
        "payment_status_display": {
            "paid": "مدفوعة بالكامل",
            "partially_paid": "مدفوعة جزئياً",
            "unpaid": "غير مدفوعة",
        }[status],
    }


def document_partner_balance_summary(
    current_balance,
    remaining_balance,
    exchange_rate,
    *,
    is_posted: bool,
    direction: int = 1,
) -> dict[str, Decimal]:
    """رصيد الشريك قبل/بعد احتساب المتبقي الحالي للمستند بالعملة الأساسية."""
    current = Decimal(str(current_balance or 0)).quantize(Decimal("0.01"))
    remaining = Decimal(str(remaining_balance or 0))
    rate = Decimal(str(exchange_rate or 1))
    effect = (remaining * rate * Decimal(direction)).quantize(Decimal("0.01"))
    before = current - effect if is_posted else current
    after = current if is_posted else current + effect
    return {
        "balance_before": before.quantize(Decimal("0.01")),
        "balance_after": after.quantize(Decimal("0.01")),
        "balance_current": current,
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


def apply_default_cash_account(serializer, attrs: dict, field: str = "cash_or_bank_account") -> dict:
    """T-DEFACC: يملأ حساب الصندوق/البنك للسند من افتراضي الشركة حين لا يُرسَل.

    سند القبض وسند الصرف كانا يُرفضان بـ«هذا الحقل مطلوب» متى نسيت الشاشة تمرير
    الحساب، مع أن للشركة صندوقاً افتراضياً في الإعدادات. مشترك بين
    `sales.CustomerPaymentSerializer` و`logistics.SupplierPaymentSerializer`
    فلا تتفرّق القاعدة نسختين.
    """
    from rest_framework import serializers as drf_serializers

    from accounting.services import resolve_default_cash_account
    from core.tenant_utils import get_tenant

    if attrs.get(field):
        return attrs
    instance = getattr(serializer, "instance", None)
    if instance is not None and getattr(instance, f"{field}_id", None):
        return attrs

    request = serializer.context.get("request")
    tenant = get_tenant(request) if request is not None else None
    tenant_id = getattr(tenant, "TenantID", None) or getattr(instance, "tenant_id", None)
    account = resolve_default_cash_account(tenant_id) if tenant_id else None
    if account is None:
        raise drf_serializers.ValidationError({
            field: "حدّد الصندوق/البنك، أو عيّن صندوقاً افتراضياً في إعدادات المبيعات.",
        })
    attrs[field] = account
    return attrs
