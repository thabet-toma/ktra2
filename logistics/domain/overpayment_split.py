"""فصل الدفعة الزائدة على مستحقٍّ لوجستي إلى «دفعة تحت الحساب».

دفعة تخليصٍ أو إرساليةٍ أكبر من متبقّي مستحقّها تُسجَّل على المستند بالمتبقّي،
والزائد سند صرفٍ مستقل للطرف نفسه بنفس التاريخ والصندوق، **بلا توزيع**: يبقى
رصيداً للطرف يوزّعه المستخدم لاحقاً (`party_accruals.allocate_voucher_to_accruals`).
الدفتر لا يتغيّر (Dr ذمّة الطرف / Cr الصندوق بالمبلغ كلّه) — يتغيّر فقط أين يُرى
الزائد: كان «مدفوعاً أكثر» عالقاً على التخليص فلا يستهلكه مستحقٌّ آخر.

- عند الترحيل: `split_incoming` + `create_on_account_voucher` من `pay_from_cashbox`
  (`views/clearance.py`، `views/transport.py`).
- للموجود: `split_posted_overpayment` من أمر `split_logistics_overpayments` — يعكس
  قيد الدفعة (لا حذف) ويعيد ترحيلها بالمستحق وينشئ السند بالزائد.

بالعملة الأساسية وحدها: دفعةٌ بعملةٍ أجنبية تبقى كما هي (فرق الصرف يجعل «الزائد»
بالعملة الأجنبية رقماً غير مستقرّ). استحقاق الشحن الدولي (دفعات الوكيل بالدولار)
خارج الفصل للسبب نفسه — الأمر يعرضه تقريراً فقط.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction

from logistics.domain.party_accruals import ZERO, _accrual_meta, _label, _money, accrual_status

#: تسمية المستند في ملاحظة السند وسجلّ التدقيق («تخليص #3 — SH-0013»).
accrual_label = _label

logger = logging.getLogger(__name__)

ON_ACCOUNT_NOTE = "دفعة تحت الحساب — زيادة دفعة {label}"

#: الصنف ← (مرجع إعادة الترحيل، مرجع العكس) لقيود الأمر.
SPLIT_REFERENCES = {
    'clearance': ('CLEARANCE_PAYMENT_SPLIT', 'CLEARANCE_PAYMENT_SPLIT_REVERSAL'),
    'local': ('LOCAL_SHIPMENT_PAYMENT_SPLIT', 'LOCAL_SHIPMENT_PAYMENT_SPLIT_REVERSAL'),
}


def split_incoming(kind: str, obj, amount) -> tuple[Decimal, Decimal]:
    """(ما يُسجَّل على المستند، الزائد) لدفعةٍ جديدة بالعملة الأساسية.

    مستحقٌّ غير مرحَّل ⇒ لا فصل: الدفعة المقدّمة قبل الإفراج تبقى على مستندها كما
    كانت (قرار المالك 2026-07-19 في `payment_posting_cap.py`).
    """
    amount = _money(amount)
    _party_id, accrual_journal_id, _ = _accrual_meta(kind, obj)
    if not accrual_journal_id:
        return amount, ZERO
    recorded = min(amount, accrual_status(kind, obj)['remaining'])
    return recorded, amount - recorded


def create_on_account_voucher(*, tenant, partner, amount, currency, payment_date,
                              cash_account_id, doc_label: str, user=None):
    """سند صرفٍ مرحَّل «تحت الحساب» بالزائد — بلا توزيع ولا استهلاك تلقائي."""
    from sales.models import SupplierPayment
    from sales.services import post_supplier_payment

    voucher = SupplierPayment.objects.create(
        tenant=tenant, partner=partner, payment_date=payment_date, amount=_money(amount),
        currency=currency, exchange_rate=Decimal('1'), cash_or_bank_account_id=cash_account_id,
        notes=ON_ACCOUNT_NOTE.format(label=doc_label),
    )
    post_supplier_payment(voucher, user=user)
    logger.info("logistics.overpayment_voucher partner=%s voucher=%s amount=%s doc=%s",
                partner.pk, voucher.pk, voucher.amount, doc_label)
    return voucher


def _posted_payments(kind: str, obj):
    """دفعات الطرف المرحّلة على المستند، الأحدث أولاً."""
    if kind == 'clearance':
        qs = obj.payments.filter(customs_broker_id=obj.customs_broker_id)
    else:
        qs = obj.payments.all()
    return list(
        qs.filter(is_posted=True, journal__isnull=False)
        .select_related('journal', 'currency').order_by('-payment_date', '-id')
    )


def _simple_lines(payment, party_id):
    """(سطر ذمّة الطرف، سطر الصندوق) لقيدٍ بسيط بالعملة الأساسية، أو سبب الرفض."""
    journal = payment.journal
    if (journal.reference_type or '').endswith('_SPLIT'):
        return None, "فُصلت مسبقاً"
    if Decimal(str(journal.exchange_rate or 1)) != Decimal('1'):
        return None, "بعملة أجنبية — تُترك كما هي"
    lines = list(journal.lines.all())
    amount = _money(payment.amount)
    party = [l for l in lines if l.partner_id == party_id and _money(l.debit) == amount and not l.credit]
    box = [l for l in lines if not l.partner_id and _money(l.credit) == amount and not l.debit]
    if len(lines) != 2 or len(party) != 1 or len(box) != 1:
        return None, "قيدٌ مركّب (صندوق FIFO أو أسطر إضافية) — يُراجَع يدوياً"
    return (party[0], box[0]), None


def split_posted_overpayment(kind: str, obj, *, apply: bool = False, user=None) -> dict | None:
    """يفصل زائد المستند المرحَّل عن أحدث دفعاته. None = لا زائد.

    ``{kind, doc, label, payment, amount, excess, new_amount, action, reason, voucher}``
    — ``action`` ∈ ``report`` / ``split`` / ``skip``.
    """
    from accounting.api import reverse_journal
    from accounting.services import create_audit_log, post_journal

    party_id, accrual_journal_id, _ = _accrual_meta(kind, obj)
    if kind not in SPLIT_REFERENCES or not accrual_journal_id:
        return None
    excess = accrual_status(kind, obj)['overpaid']
    if excess <= 0:
        return None
    row = {'kind': kind, 'doc': obj.pk, 'label': _label(kind, obj), 'excess': excess,
           'payment': None, 'amount': None, 'new_amount': None, 'voucher': None,
           'action': 'skip', 'reason': ''}
    payments = _posted_payments(kind, obj)
    if not payments:
        row['reason'] = "الزائد من سندات موزَّعة لا من دفعات المستند"
        return row
    payment = payments[0]
    row.update(payment=payment.pk, amount=_money(payment.amount))
    if excess >= _money(payment.amount):
        row['reason'] = "الزائد يتجاوز أحدث دفعة — يُراجَع يدوياً"
        return row
    lines, reason = _simple_lines(payment, party_id)
    if lines is None:
        row['reason'] = reason
        return row
    party_line, box_line = lines
    new_amount = _money(payment.amount) - excess
    row.update(new_amount=new_amount, action='split' if apply else 'report')
    if not apply:
        return row

    split_ref, reversal_ref = SPLIT_REFERENCES[kind]
    model_name = type(payment).__name__
    with transaction.atomic():
        original = payment.journal
        reverse_journal(
            original, reference_type=reversal_ref, reference_id=payment.pk,
            transaction_date=payment.payment_date, copy_currency=True,
            description=f"[فصل دفعة زائدة] عكس القيد #{original.pk} — {row['label']}",
            line_description_prefix=f"عكس #{original.pk}: ",
        )
        journal = post_journal(
            tenant_id=payment.tenant_id, transaction_date=payment.payment_date,
            reference_type=split_ref, reference_id=payment.pk,
            description=f"{original.description} — بعد فصل الزائد {excess}"[:500],
            lines_data=[
                {'account': party_line.account_id, 'partner': party_id, 'debit': new_amount,
                 'credit': Decimal('0'), 'description': party_line.description},
                {'account': box_line.account_id, 'partner': None, 'debit': Decimal('0'),
                 'credit': new_amount, 'description': box_line.description},
            ],
            currency=original.currency, exchange_rate=Decimal('1'), user=user,
        )
        payment.amount = new_amount
        payment.journal = journal
        payment.save(update_fields=['amount', 'journal'])
        voucher = create_on_account_voucher(
            tenant=payment.tenant, partner=party_line.partner, amount=excess,
            currency=payment.currency, payment_date=payment.payment_date,
            cash_account_id=box_line.account_id, doc_label=row['label'], user=user,
        )
        create_audit_log(
            tenant=payment.tenant, user=user, action="SPLIT_OVERPAYMENT",
            model_name=model_name, object_id=payment.pk,
            change_details=(
                f"{row['label']}: {row['amount']} → {new_amount} (journal {original.pk} reversed, "
                f"re-posted {journal.pk}); excess {excess} → on-account voucher #{voucher.pk}"
            ),
        )
    row['voucher'] = voucher.pk
    logger.info("logistics.overpayment_split %s payment=%s %s→%s voucher=%s",
                kind, payment.pk, row['amount'], new_amount, voucher.pk)
    return row


__all__ = ['ON_ACCOUNT_NOTE', 'accrual_label', 'split_incoming', 'create_on_account_voucher', 'split_posted_overpayment']
