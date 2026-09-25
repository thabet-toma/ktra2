"""
قيد دفعة الاستيراد (LogisticsPayment) — مصدر واحد لدفعة الصفقة ودفعة وكيل الشحن.

الدفعة بالدولار دائماً: `amount` دولار و`usd_to_ils` سعره — هكذا تحسبها تكلفة
البضاعة في الفاتورة الدولية (`landed_cost.payment_ils`). قبل هذا:
- دفعة الصفقة تتحوّل للشيكل فقط إن كانت عملة الصفقة غير الأساسية، وصفقات الإنتاج
  تحمل ILS ⇒ القيد يُدين المورد بالرقم الدولاري كأنه شيكل (1,650$ ⇒ 1,650 ₪).
- والفرع غير الـFIFO يمرّر أسطراً بالشيكل مع عملة الدولار وسعره، و
  `JournalLine.save` يضرب السطر بالسعر ⇒ الأساس يتحوّل مرتين (1,000$ ⇒ 12,250 ₪).

هنا: السطر بالدولار الاسمي وسعر القيد = usd_to_ils ⇒ الأساس = amount × usd_to_ils،
أو (صندوق FIFO) أسطر بالشيكل وسعر 1 كما يبنيها `build_fx_payment_lines`.
إلّا صفقة الأرشيف (`archive_deal_ids`): قيدها ودفعاتها بالرقم الدولاري بسعر 1، فإعادة
ترحيل دفعتها بنفس الوحدة (`_archive_payment_journal`) — وبالشيكل تجعل المورد مديناً لنا.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.core.exceptions import ValidationError

from logistics.landed_cost import payment_ils, payment_usd_rate
from tenants.models import Currency

logger = logging.getLogger(__name__)

USD_RATE_REQUIRED_MESSAGE = 'أدخل سعر الدولار للشيكل على الدفعة (أكبر من صفر) قبل ترحيلها.'


def archive_deal_ids(tenant_id, deal_ids=None) -> set:
    """صفقات الأرشيف — مجموعة (ب) في `audit_deal_payment_currency`، تعريفٌ واحد لها.

    صفقةٌ لها قيد LOGISTICS_DEAL مرحّل (المسار القديم: دائن المورد بالرقم الدولاري
    كأنه شيكل بسعر 1) ولا فاتورة دولية مرحّلة لها. دفعاتها رُحّلت بنفس الوحدة فرصيد
    المورد متوازن بها — وبالشيكل ينكسر. صفقةٌ بفاتورة دولية مجموعة (أ) ولو كان لها
    قيد صفقة: الفاتورة دائنة بالشيكل.
    """
    from accounting.services import JournalHeader
    from logistics.models import PurchaseInvoice

    journals = JournalHeader.objects.filter(
        tenant_id=tenant_id, reference_type='LOGISTICS_DEAL', is_posted=True)
    invoices = PurchaseInvoice.objects.filter(
        tenant_id=tenant_id, invoice_type=PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL,
        is_posted=True, deal__isnull=False)
    if deal_ids is not None:
        journals = journals.filter(reference_id__in=deal_ids)
        invoices = invoices.filter(deal_id__in=deal_ids)
    return (set(journals.values_list('reference_id', flat=True))
            - set(invoices.values_list('deal_id', flat=True)))


def is_archive_deal(deal) -> bool:
    return deal.pk in archive_deal_ids(deal.tenant_id, [deal.pk])


ARCHIVE_FIRST_POST_MESSAGE = (
    'صفقة أرشيف: قيدها القديم يدائن المورد بالرقم الدولاري كأنه شيكل، فدفعةٌ جديدة '
    'عليها لا تُرحَّل — بالشيكل تجعل المورد مديناً لنا، وبوحدة الأرشيف تكتب في الصندوق '
    'مبلغاً غير حقيقي. سجّلها بقيد يومية يدوي بعد مراجعة المحاسب.'
)


def _archive_payment_journal(payment, *, debit_account_id, partner_id, box_account, description):
    """دفعة صفقة أرشيف: الرقم الدولاري بسعر 1 — وحدة قيد الصفقة ودفعاتها الأصلية.

    يُسمح فقط بإعادة ترحيل دفعةٍ رُحّلت قبلاً (إلغاء ترحيل ثم إعادة): يعيد قيدها كما
    كان فيبقى رصيد المورد والصندوق كما كانا، أيّاً كان `usd_to_ils` (السعر لا يدخل هنا
    — يقرؤه `landed_cost` لتكلفة البضاعة وحدها). دفعةٌ لم تُرحَّل قط: لا وحدةَ صحيحة
    لها في دفاتر هذه الصفقة ⇒ رفضٌ مقروء بدل خطأٍ صامت.
    """
    from accounting.services import JournalHeader

    posted_before = JournalHeader.objects.filter(
        tenant_id=payment.deal.tenant_id, reference_type='LOGISTICS_PAYMENT',
        reference_id=payment.pk,
    ).exists()
    if not posted_before:
        raise ValidationError(ARCHIVE_FIRST_POST_MESSAGE)
    amount = Decimal(str(payment.amount or 0))
    base = Currency.objects.filter(IsBaseCurrency=True).first()
    lines = [
        # الرقم دولارٌ مسجَّلٌ بوحدة الشيكل: مبلغُه الأجنبيّ هو نفسه.
        {"account": debit_account_id, "debit": amount, "credit": Decimal("0"),
         "partner": partner_id, "description": description,
         "amount_currency": amount, "currency_code": "USD"},
        {"account": box_account.id, "debit": Decimal("0"), "credit": amount,
         "description": description},
    ]
    return lines, base, Decimal('1')


def usd_rate_entered(payment) -> bool:
    """سعرٌ أدخله أحد — لا `payment_usd_rate` التي تسقط إلى 3.5 للعرض والتقديرات."""
    rate = getattr(payment, 'usd_to_ils', None)
    return rate is not None and Decimal(str(rate)) > 0


AGENT_ACCOUNT_MESSAGE = (
    "تعذّر ربط وكيل الشحن بحساب محاسبي تلقائياً. "
    "تحقق من شجرة الحسابات (حسابات أب 2101 أو 2102) أو من مجموعة الشريك في المحاسبة، "
    "أو عيّن نوع الشريك «FreightForwarder» لوكيل الشحن."
)


def agent_payment_blockers(payment) -> list[str]:
    """موانع ترحيل دفعة وكيل شحن (بلا صفقة) — قراءة فقط، لأمر `post_pending_agent_payments`
    ولتقرير ما قبل الترحيل. الفارغة = قابلة للترحيل؛ `post_shipment_agent_payment` يفحص
    المانع نفسه ويرفض."""
    from logistics.accruals import DELETED_SHIPMENT_MESSAGE

    shipment = payment.shipment
    reasons = []
    if payment.is_posted:
        reasons.append('مرحّلة بالفعل')
    if shipment is None or getattr(shipment, 'is_deleted', False):
        reasons.append(DELETED_SHIPMENT_MESSAGE)
    elif not shipment.shipping_agent_id:
        reasons.append('الشحنة لا تملك وكيل شحن محدد')
    if not usd_rate_entered(payment):
        reasons.append(USD_RATE_REQUIRED_MESSAGE)
    if Decimal(str(payment.amount or 0)) <= 0:
        reasons.append('المبلغ صفر')
    return reasons


def post_shipment_agent_payment(payment, *, box_account, user=None):
    """ترحيل دفعة وكيل شحن (بلا صفقة): Dr ذمّة الوكيل / Cr الصندوق — مصدرٌ واحد لزرّ
    الترحيل (`post_agent_payment`) والدفع من الصندوق (`pay_agent_from_cashbox`) وأمر
    `post_pending_agent_payments`. ذرّية بنفسها وتُستدعى داخل معاملة المستدعي فيرتدّ معها
    إنشاء الدفعة؛ ترمي `ValidationError` ولا تكتب شيئاً إن رُفضت. تعيد القيد.
    """
    from django.db import transaction
    from django.utils import timezone

    from accounting.api import ensure_partner_account
    from accounting.services import post_journal
    from logistics.accruals import DELETED_SHIPMENT_MESSAGE
    from logistics.models import LogisticsPayment, LogisticsShipment
    from logistics.payment_posting_cap import shipment_agent_posting_cap_check
    from partners.models import Partner

    with transaction.atomic():
        shipment = (
            LogisticsShipment.all_objects.select_related('tenant', 'shipping_agent')
            .select_for_update().get(pk=payment.shipment_id)
        )
        if shipment.is_deleted:
            raise ValidationError(DELETED_SHIPMENT_MESSAGE)
        locked = LogisticsPayment.objects.select_for_update().get(
            pk=payment.pk, shipment=shipment, deal__isnull=True,
        )
        if locked.is_posted:
            raise ValidationError('هذه الدفعة مرحلة بالفعل')
        if not shipment.shipping_agent_id:
            raise ValidationError('الشحنة لا تملك وكيل شحن محدد')
        # نفس إشارة الشريك: إنشاء حساب دائن تلقائياً تحت 2101/2102 إن أمكن
        ensure_partner_account(shipment.shipping_agent)
        agent = Partner.objects.select_related('linked_account').get(pk=shipment.shipping_agent_id)
        if not agent.linked_account_id:
            raise ValidationError(AGENT_ACCOUNT_MESSAGE)
        ok_cap, cap_err = shipment_agent_posting_cap_check(shipment, locked.amount)
        if not ok_cap:
            raise ValidationError(cap_err)

        description = f"دفعة {locked.title} | شحنة: {shipment.display_label}"
        # نفس بنّاء قيد دفعة الصفقة (صندوق الدولار FIFO أو الدولار الاسمي بسعره).
        lines_data, journal_currency, journal_rate = build_usd_payment_journal(
            locked, debit_account_id=agent.linked_account_id, partner_id=agent.id,
            box_account=box_account, tenant=shipment.tenant, description=description)
        journal = post_journal(
            tenant_id=shipment.tenant_id,
            transaction_date=locked.transfer_date or timezone.localdate(),
            reference_type='LOGISTICS_PAYMENT',
            reference_id=locked.id,
            description=f"{description} | وكيل شحن: {agent.name}",
            lines_data=lines_data,
            currency=journal_currency,
            exchange_rate=journal_rate,
            user=user,
        )
        locked.is_posted = True
        locked.journal = journal
        locked.bank_account = box_account
        locked.save()
    logger.info('shipment agent payment posted shipment=%s payment=%s journal=%s amount=%s',
                shipment.pk, locked.pk, journal.pk, locked.amount)
    return journal


def build_usd_payment_journal(payment, *, debit_account_id, partner_id, box_account,
                              tenant, description, use_fifo=True):
    """(lines_data, currency, exchange_rate) لقيد: مدين الذمة / دائن الصندوق.

    use_fifo=False يتخطّى طبقات صندوق الدولار (أمر التصحيح يعيد ترحيل دفعة قديمة
    على نفس حساباتها — طبقاتها لم تُستهلك في الأصل ولا تُستهلك بأثر رجعي).
    """
    if not usd_rate_entered(payment):
        raise ValidationError(USD_RATE_REQUIRED_MESSAGE)
    if payment.deal_id and is_archive_deal(payment.deal):
        return _archive_payment_journal(
            payment, debit_account_id=debit_account_id, partner_id=partner_id,
            box_account=box_account, description=description)
    foreign_amount = Decimal(str(payment.amount or 0))
    local_amount = payment_ils(payment)
    usd = Currency.objects.filter(Code__iexact='USD').first()
    base = Currency.objects.filter(IsBaseCurrency=True).first()

    if use_fifo:
        from accounting.fx_fifo import build_fx_payment_lines, fifo_link_for_box
        fifo_link = fifo_link_for_box(box_account, tenant)
        if fifo_link:
            lines = build_fx_payment_lines(
                fifo_link=fifo_link, foreign_amount=foreign_amount, local_amount=local_amount,
                debit_account_id=debit_account_id, box_account_id=box_account.id,
                partner_id=partner_id, description=description, tenant=tenant)
            # القيد بالشيكل وسطر الذمة وحده يحمل دولار الدفعة (كشف الطرف بالدولار).
            for line in lines:
                if line.get("partner") == partner_id:
                    line.update(amount_currency=foreign_amount, currency_code="USD")
            return lines, (base or usd), Decimal('1')

    if usd and base and usd.pk != base.pk:
        amount, currency, rate = foreign_amount, usd, payment_usd_rate(payment)
    else:
        amount, currency, rate = local_amount, (base or usd), Decimal('1')
    lines = [
        {"account": debit_account_id, "debit": amount, "credit": Decimal("0"),
         "partner": partner_id, "description": description},
        # الصندوقُ بلا الطرف: موسوماً يُلغي مدينَ الذمة في رصيده.
        {"account": box_account.id, "debit": Decimal("0"), "credit": amount,
         "description": description},
    ]
    return lines, currency, rate
