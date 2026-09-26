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
- بعد «تعديل الاستحقاق» إلى أقلّ من المدفوع: `release_adjusted_overpayment` — الزائد كلّه
  (الفائض معه) يعود «تحت الحساب»: توزيعات السندات والإشعارات على المستند تُقلَّص أولاً
  (بلا قيد)، ثم ما بقي من دفعات المستند المباشرة بالفصل نفسه أعلاه.

بالعملة الأساسية وحدها: دفعةٌ بعملةٍ أجنبية تبقى كما هي (فرق الصرف يجعل «الزائد»
بالعملة الأجنبية رقماً غير مستقرّ). استحقاق الشحن الدولي (دفعات الوكيل بالدولار)
خارج الفصل للسبب نفسه — الأمر يعرضه تقريراً فقط.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.db import transaction

from logistics.domain.party_accruals import (
    _ALLOCATION_FIELD, _POSTED_SOURCE, ZERO, _accrual_meta, _label, _money, accrual_status,
)

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
                              cash_account_id, doc_label: str, user=None, adjust_surplus=ZERO):
    """سند صرفٍ مرحَّل «تحت الحساب» بالزائد — بلا توزيع ولا استهلاك تلقائي.

    `adjust_surplus`: ما منه زائدٌ لأن المستحق خُفِّض (فائضٌ لا دفعة — `SupplierPayment.adjust_surplus`).
    """
    from sales.models import SupplierPayment
    from sales.services import post_supplier_payment

    voucher = SupplierPayment.objects.create(
        tenant=tenant, partner=partner, payment_date=payment_date, amount=_money(amount),
        currency=currency, exchange_rate=Decimal('1'), cash_or_bank_account_id=cash_account_id,
        notes=ON_ACCOUNT_NOTE.format(label=doc_label), adjust_surplus=_money(adjust_surplus),
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


def split_posted_overpayment(kind: str, obj, *, apply: bool = False, user=None,
                             include_surplus: bool = False, adjust_surplus=ZERO) -> dict | None:
    """يفصل زائد المستند المرحَّل عن أحدث دفعاته. None = لا زائد.

    ``{kind, doc, label, payment, amount, excess, new_amount, action, reason, voucher}``
    — ``action`` ∈ ``report`` / ``split`` / ``skip``. ``include_surplus``: الفائض (زائدٌ لأن
    المستحق خُفِّض) يُفصل أيضاً — «تعديل الاستحقاق»، و`adjust_surplus` ما منه فائضٌ على السند الجديد.
    """
    from accounting.api import reverse_journal
    from accounting.services import create_audit_log, post_journal

    party_id, accrual_journal_id, _ = _accrual_meta(kind, obj)
    if kind not in SPLIT_REFERENCES or not accrual_journal_id:
        return None
    # الفائض (زائدٌ لأن المستحق خُفِّض بعد الدفع) يبقى على مستنده للأمر — ويُفصل بعد التعديل.
    status = accrual_status(kind, obj)
    excess = status['overpaid'] - (ZERO if include_surplus else status['surplus'])
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
            adjust_surplus=min(_money(adjust_surplus), excess),
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


def _mark_adjust_surplus(payment_id: int, amount: Decimal) -> None:
    """يزيد `adjust_surplus` للسند بما عاد إليه فائضاً — بعملته."""
    from django.db.models import F

    from sales.models import SupplierPayment

    SupplierPayment.objects.filter(pk=payment_id).update(adjust_surplus=F('adjust_surplus') + amount)


def release_adjusted_overpayment(kind: str, obj, *, user=None) -> dict | None:
    """بعد «تعديل الاستحقاق»: ما زاد من المدفوع على المستحق الجديد يعود «تحت الحساب». None = لا زائد.

    1. توزيعات السندات والإشعارات المرحّلة على المستند، الأحدث أولاً — تُقلَّص أو تُحذف فيعود
       المبلغ غيرَ موزَّعٍ على مصدره. بلا قيد: الدفتر قيّدها على ذمّة الطرف أصلاً.
    2. ما بقي من دفعات المستند المباشرة — `split_posted_overpayment` بالفائض معه.
    ما كان «فائضاً» (زائداً لأن المستحق خُفِّض) يبقى فائضاً بعد عودته: الإشعار فائضٌ بطبعه،
    والسند يحمله في `adjust_surplus` — وما زاد لحظة الدفع يبقى «دفعةً تحت الحساب».
    ما تعذّر فصله (عملة أجنبية، قيدٌ مركّب، شحنٌ دولي) يبقى «فائضاً» على المستند ويُذكر سببه.
    يعمل داخل معاملة المستدعي. ``{excess, released: [وسوم], voucher, left, reason}``.
    """
    from logistics.models import LogisticsAccrualAllocation

    status = accrual_status(kind, obj)
    excess = status['overpaid']
    if excess <= 0:
        return None
    surplus_left = status['surplus']
    out = {'excess': str(excess), 'released': [], 'voucher': None, 'left': '0.00', 'reason': ''}
    allocations = (
        LogisticsAccrualAllocation.objects.select_for_update()
        .filter(_POSTED_SOURCE, tenant_id=obj.tenant_id, **{_ALLOCATION_FIELD[kind]: obj})
        .select_related('note').order_by('-id')
    )
    left = excess
    for alloc in allocations:
        if left <= 0:
            break
        base = _money(alloc.amount_base)
        take = min(base, left)
        if take <= 0:
            continue
        source = f"إشعار {alloc.note.note_number}" if alloc.note_id else f"سند صرف #{alloc.payment_id}"
        if take >= base:
            released_amount = _money(alloc.amount)
            alloc.delete()
        else:
            new_base = base - take
            new_amount = (Decimal(str(alloc.amount)) * new_base / base).quantize(Decimal('0.01'))
            released_amount = _money(alloc.amount) - new_amount
            alloc.amount, alloc.amount_base = new_amount, new_base
            alloc.save(update_fields=['amount', 'amount_base'])
        marked = min(take, surplus_left)
        if marked > 0 and alloc.payment_id:
            _mark_adjust_surplus(alloc.payment_id, (released_amount * marked / take).quantize(Decimal('0.01')))
        surplus_left -= marked
        out['released'].append(f"{source} ({released_amount})")
        left -= take
    if left > 0:
        row = split_posted_overpayment(kind, obj, apply=True, user=user, include_surplus=True,
                                       adjust_surplus=min(surplus_left, left))
        if row and row['action'] == 'split':
            out['voucher'] = row['voucher']
            out['released'].append(f"دفعة المستند #{row['payment']} ({row['excess']}) ← سند صرف #{row['voucher']}")
        elif row:
            out['left'] = str(row['excess'])
            out['reason'] = row['reason']
        elif kind not in SPLIT_REFERENCES:
            out['left'] = str(left)
            out['reason'] = "دفعات الشحن الدولي لا تُفصل — تبقى «فائضاً» على المستند"
    logger.info("logistics.adjust_overpayment %s doc=%s excess=%s released=%s left=%s",
                kind, obj.pk, excess, len(out['released']), out['left'])
    return out


__all__ = [
    'ON_ACCOUNT_NOTE', 'accrual_label', 'split_incoming', 'create_on_account_voucher', 'split_posted_overpayment',
    'release_adjusted_overpayment',
]
