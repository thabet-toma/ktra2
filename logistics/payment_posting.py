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
"""
from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError

from logistics.landed_cost import payment_ils, payment_usd_rate
from tenants.models import Currency


def build_usd_payment_journal(payment, *, debit_account_id, partner_id, box_account,
                              tenant, description, use_fifo=True):
    """(lines_data, currency, exchange_rate) لقيد: مدين الذمة / دائن الصندوق.

    use_fifo=False يتخطّى طبقات صندوق الدولار (أمر التصحيح يعيد ترحيل دفعة قديمة
    على نفس حساباتها — طبقاتها لم تُستهلك في الأصل ولا تُستهلك بأثر رجعي).
    """
    if payment_usd_rate(payment) <= 0:
        raise ValidationError('أدخل سعر الدولار للشيكل على الدفعة (أكبر من صفر) قبل ترحيلها.')
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
