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

from decimal import Decimal

from django.core.exceptions import ValidationError

from logistics.landed_cost import payment_ils, payment_usd_rate
from tenants.models import Currency

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
        {"account": debit_account_id, "debit": amount, "credit": Decimal("0"),
         "partner": partner_id, "description": description},
        {"account": box_account.id, "debit": Decimal("0"), "credit": amount,
         "description": description},
    ]
    return lines, base, Decimal('1')


def usd_rate_entered(payment) -> bool:
    """سعرٌ أدخله أحد — لا `payment_usd_rate` التي تسقط إلى 3.5 للعرض والتقديرات."""
    rate = getattr(payment, 'usd_to_ils', None)
    return rate is not None and Decimal(str(rate)) > 0


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
