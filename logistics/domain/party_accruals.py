"""مستحقّات الأطراف اللوجستية — **مصدرٌ واحد** لـ«المستحق/المدفوع/المتبقّي».

ثلاثة أصناف، لكلٍّ قيد استحقاقٍ مرحَّل يُدائن ذمّة الطرف:

- ``clearance`` ← `LogisticsClearance.journal` (المخلّص `customs_broker`)
- ``freight``   ← `LogisticsShipment.freight_journal` (وكيل الشحن `shipping_agent`)
- ``local``     ← `LocalShipment.journal` (الناقل `carrier`)

الأرقام تُقرأ من **أسطر القيود الموسومة بالطرف** بالعملة الأساسية
(`base_credit`/`base_debit`) لا من حقول المستند: الاستحقاق المرحَّل هو ما يدين به
الدفتر فعلاً، ودفعةٌ بعملة أجنبية أو قسمٌ منها لطرفٍ آخر (شحنُ الناقل داخل دفعة
التخليص) يُحسب كما رُحِّل لا كما كُتب في النموذج. فلا فرق عملة ولا تصنيف ملاحظات.

    المستحق  = Σ(دائن − مدين) لأسطر الطرف في قيد الاستحقاق وقيود تعديله
    المدفوع  = Σ(مدين − دائن) لأسطر الطرف في قيود دفعات المستند نفسه المرحّلة
    الموزَّع = Σ `LogisticsAccrualAllocation.amount_base` لسندات صرفٍ مرحّلة وإشعاراتٍ
               مدينةٍ مرحّلة (خصمٌ من الطرف يُوزَّع كالسند — `sales/services/note_allocation.py`)
    المتبقّي = max(المستحق − المدفوع − الموزَّع، 0)

يستعملها منتقي التوزيع وFIFO والتحقّق عند التوزيع، وفصلُ الدفعة الزائدة عند
الترحيل وأمرُ `split_logistics_overpayments`، و3ب (`import_settlement`) يضيف منها
حصّة سندات الصرف الموزَّعة إلى كل حوض.

«تعديل الاستحقاق» (`domain/accrual_adjust.py`) لا يحذف القيد: يرحّل قيد فرقٍ بمرجع
`ACCRUAL_ADJUST_TYPE[kind]` على المستند نفسه، فالمستحق = الأصل + كل تعديلاته. وما
زاد من المدفوع بعد تخفيض المستحق «فائضٌ» (`surplus`) لا «دفعة تحت الحساب»: الأولى
دفعةٌ أكبر من المستحق لحظة الدفع، والثاني ما صار زائداً لأن المستحق نزل بعدها.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum

logger = logging.getLogger(__name__)

Q2 = Decimal('0.01')
ZERO = Decimal('0.00')
KINDS = ('clearance', 'freight', 'local')

#: الصنف ← (حقل FK في `LogisticsAccrualAllocation`، تسمية المستند)
_ALLOCATION_FIELD = {'clearance': 'clearance', 'freight': 'shipment', 'local': 'local_shipment'}
#: التوزيع يُحتسب ما دام مصدره مرحَّلاً — سند صرفٍ أو إشعارٌ مدين.
_POSTED_SOURCE = Q(payment__is_posted=True) | Q(note__status='posted')

#: الصنف ← مرجع قيد «تعديل الاستحقاق» (قيد فرقٍ على المستند نفسه، `reference_id` = المستند).
ACCRUAL_ADJUST_TYPE = {
    'clearance': 'LOGISTICS_CLEARANCE_ADJUST',
    'freight': 'SHIPMENT_FREIGHT_ACCRUAL_ADJUST',
    'local': 'LOCAL_SHIPMENT_ADJUST',
}


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Q2)


def _party_net(journal_ids, partner_id, *, credit_side: bool) -> Decimal:
    """صافي أسطر الطرف في قيود بعينها بالعملة الأساسية — دائناً أو مديناً."""
    from accounting.api import journal_lines_party_net

    ids = [j for j in journal_ids if j]
    if not ids or not partner_id:
        return ZERO
    net = journal_lines_party_net(ids, partner_id)  # Σ(base_credit − base_debit)
    return _money(net if credit_side else -net)


def _accrual_meta(kind: str, obj):
    """(party_id, accrual_journal_id, own_payment_journal_ids) للمستند."""
    if kind == 'clearance':
        payments = obj.payments.filter(is_posted=True, journal__isnull=False)
        return obj.customs_broker_id, obj.journal_id, list(payments.values_list('journal_id', flat=True))
    if kind == 'freight':
        payments = obj.agent_payments.filter(deal__isnull=True, is_posted=True, journal__isnull=False)
        journal_id = obj.freight_journal_id if obj.freight_is_posted else None
        return obj.shipping_agent_id, journal_id, list(payments.values_list('journal_id', flat=True))
    if kind == 'local':
        payments = obj.payments.filter(is_posted=True, journal__isnull=False)
        journal_id = obj.journal_id if obj.is_posted else None
        return obj.carrier_id, journal_id, list(payments.values_list('journal_id', flat=True))
    raise ValueError(f"صنف مستحق غير معروف: {kind}")


def adjustment_journal_ids(kind: str, obj) -> list[int]:
    """قيود «تعديل الاستحقاق» المرحّلة على المستند، الأقدم أولاً."""
    return _adjustments_by_doc(kind, obj.tenant_id, [obj.pk]).get(obj.pk, [])


def _adjustments_by_doc(kind: str, tenant_id: int, doc_ids) -> dict:
    """{المستند: [قيود تعديله]} لمستندات صنفٍ واحد — استعلامٌ واحد."""
    from accounting.api import posted_journal_ids_by_reference

    return posted_journal_ids_by_reference(tenant_id, ACCRUAL_ADJUST_TYPE[kind], doc_ids)


#: الصنف ← حقل الربط في `sales.CreditDebitNote`.
_NOTE_LINK_FIELD = {'clearance': 'related_clearance', 'freight': 'related_shipment', 'local': 'related_local_shipment'}


def note_journal_ids(kind: str, obj) -> list[int]:
    """قيود الإشعارات **الدائنة** المرحّلة المربوطة بالمستند — مبلغٌ إضافيٌّ للطرف يرفع مستحقّه.

    المدين (خصمٌ منه) لا يُقرأ من ربطه: يُطفئ المستحق بتوزيعه (`LogisticsAccrualAllocation.note`)
    كالسند، والترحيل يوزّعه على مستنده المربوط تلقائياً.
    """
    from sales.models import CreditDebitNote

    return list(CreditDebitNote.objects.filter(
        tenant_id=obj.tenant_id, status=CreditDebitNote.STATUS_POSTED, journal__isnull=False,
        note_type=CreditDebitNote.TYPE_CREDIT, **{_NOTE_LINK_FIELD[kind]: obj},
    ).values_list('journal_id', flat=True))


def accrual_journal_ids(kind: str, obj) -> list[int]:
    """قيد الاستحقاق وقيود تعديله — فارغة إن لم يُرحَّل الاستحقاق."""
    _party_id, accrual_journal_id, _ = _accrual_meta(kind, obj)
    if not accrual_journal_id:
        return []
    return [accrual_journal_id, *adjustment_journal_ids(kind, obj)]


def allocated_base(kind: str, objs) -> Decimal:
    """ما وُزِّع من سندات صرفٍ وإشعاراتٍ **مرحّلة** على مستندات صنفٍ واحد (بالعملة الأساسية)."""
    from logistics.models import LogisticsAccrualAllocation

    ids = [o.pk for o in objs if o is not None]
    if not ids:
        return ZERO
    total = LogisticsAccrualAllocation.objects.filter(
        _POSTED_SOURCE, **{f"{_ALLOCATION_FIELD[kind]}_id__in": ids},
    ).aggregate(t=Sum('amount_base'))['t']
    return _money(total)


def accrual_status(kind: str, obj, *, exclude_payment_journal_id=None) -> dict:
    """{due, due_original, paid, allocated, remaining, overpaid, surplus} لمستندٍ واحد
    بالعملة الأساسية.

    `allocated`: سندات الصرف والإشعارات المدينة الموزَّعة عليه. والإشعار الدائن المربوط
    (مبلغٌ إضافيٌّ للطرف) يزيد `due`.

    `due` بعد تعديلات الاستحقاق و`due_original` قبلها. `surplus` (الفائض) هو ما صار
    من الزائد زائداً **لأن المستحق خُفِّض**: min(الزائد، مقدار التخفيض). وباقي الزائد
    دفعةٌ تجاوزت المستحق لحظة دفعها — «تحت الحساب».

    `exclude_payment_journal_id`: يستثني قيد دفعةٍ بعينها — يستعمله فصلُ الزائد
    ليحسب ما بقي **قبل** تلك الدفعة.
    """
    party_id, accrual_journal_id, pay_journals = _accrual_meta(kind, obj)
    if exclude_payment_journal_id:
        pay_journals = [j for j in pay_journals if j != exclude_payment_journal_id]
    if accrual_journal_id:
        due_original = _party_net([accrual_journal_id], party_id, credit_side=True)
        adjustments = adjustment_journal_ids(kind, obj)
        due = (due_original + _party_net(adjustments, party_id, credit_side=True)) if adjustments else due_original
    else:
        due = due_original = ZERO
    paid = _party_net(pay_journals, party_id, credit_side=False)
    allocated = allocated_base(kind, [obj])
    # الإشعار الدائن المربوط: Cr ذمّة الطرف ← يزيد المستحق.
    due += _party_net(note_journal_ids(kind, obj), party_id, credit_side=True)
    settled = paid + allocated
    overpaid = max(settled - due, ZERO)
    return {
        'due': due,
        'due_original': due_original,
        'paid': paid,
        'allocated': allocated,
        'remaining': max(due - settled, ZERO),
        'overpaid': overpaid,
        'surplus': min(overpaid, max(due_original - due, ZERO)),
    }


def accrual_remaining(kind: str, obj, **kwargs) -> Decimal:
    return accrual_status(kind, obj, **kwargs)['remaining']


def document_settlement(kind: str, obj, *, draft_due, draft_paid, rate=None) -> dict:
    """{amount_paid, remaining_balance, advance_balance, payment_status} لشاشة المستند.

    بعد ترحيل الاستحقاق: من `accrual_status` — أسطر القيود ومعها سندات الصرف الموزَّعة،
    الرقم نفسه الذي يفصل به `overpayment_split` الزائد ويتحقّق به التوزيع. قبله لا قيد
    يُقرأ، فالمستحق تقديرُ المستند (`draft_due`: بنوده) ناقص دفعاته المرحّلة.
    `rate`: سعر المستند — الأرقام بعملته (الإرسالية بعملة الشحنة، ودفعتها كذلك).
    """
    _party_id, accrual_journal_id, _ = _accrual_meta(kind, obj)
    if accrual_journal_id:
        status = accrual_status(kind, obj)
        divisor = Decimal(str(rate or 1)) or Decimal('1')
        due, paid, remaining, advance = (
            (value / divisor).quantize(Q2) for value in (
                status['due'], status['paid'] + status['allocated'],
                status['remaining'], status['overpaid'],
            )
        )
    else:
        due, paid = _money(draft_due), _money(draft_paid)
        remaining, advance = max(due - paid, ZERO), max(paid - due, ZERO)
    if due > 0 and remaining <= Q2:
        payment_status = 'paid'
    elif paid > 0:
        payment_status = 'partially_paid'
    else:
        payment_status = 'unpaid'
    return {
        'amount_paid': str(paid), 'remaining_balance': str(remaining),
        'advance_balance': str(advance), 'payment_status': payment_status,
    }


def shipment_label_of(kind: str, obj) -> str:
    """وسم الشحنة الدولية للمستحق (`LogisticsShipment.display_label`) — فارغ لإرساليةٍ بلا شحنة."""
    if kind == 'clearance':
        ship = getattr(obj, 'shipment', None)
        return ship.display_label if ship is not None else ''
    if kind == 'freight':
        return obj.display_label
    return obj.shipment_label


def shipment_id_of(kind: str, obj):
    """الشحنة الدولية للمستحق — None لإرساليةٍ بلا شحنة ولا تخليص."""
    if kind == 'freight':
        return obj.pk
    if kind == 'clearance':
        return obj.shipment_id
    clearance = getattr(obj, 'clearance', None)
    return obj.shipment_id or (clearance.shipment_id if clearance is not None else None)


def _label(kind: str, obj) -> str:
    if kind == 'clearance':
        ship = shipment_label_of(kind, obj)
        return f"تخليص #{obj.pk}" + (f" — {ship}" if ship else "")
    if kind == 'freight':
        return f"شحن {obj.display_label}"
    return f"إرسالية {obj.display_label}"


VOUCHER_ALLOCATION_KIND_LABEL = 'سند صرف — توزيع'
NOTE_ALLOCATION_KIND_LABEL = 'إشعار مدين — توزيع'


def document_voucher_rows(kind: str, obj, *, rate=None) -> list[dict]:
    """سندات الصرف والإشعارات المدينة **المرحّلة** الموزَّعة على المستند — صفوفٌ لتبويب
    «الدفعات» بجانب دفعاته المباشرة. المبلغ بعملة المستند (الأساس ÷ `rate`) كما يقسم
    `document_settlement`، فمجموع التبويب = `amount_paid` في رأسه. صفّ الإشعار يحمل
    `note_id`/`note_number` و`voucher_id=None`.
    """
    from logistics.models import LogisticsAccrualAllocation

    divisor = Decimal(str(rate or 1)) or Decimal('1')
    label = shipment_label_of(kind, obj)
    allocations = (
        LogisticsAccrualAllocation.objects
        .filter(_POSTED_SOURCE, tenant_id=obj.tenant_id, **{_ALLOCATION_FIELD[kind]: obj})
        .select_related('payment', 'payment__currency', 'note', 'note__currency')
        .order_by('-id')
    )
    rows = []
    for a in allocations:
        source = a.payment or a.note
        date = a.payment.payment_date if a.payment_id else a.note.note_date
        rows.append({
            'id': f"alloc-{a.id}",
            'row_type': 'voucher_allocation',
            'allocation_id': a.id,
            'voucher_id': a.payment_id,
            'note_id': a.note_id,
            'note_number': a.note.note_number if a.note_id else None,
            'kind_label': VOUCHER_ALLOCATION_KIND_LABEL if a.payment_id else NOTE_ALLOCATION_KIND_LABEL,
            'payment_purpose': kind,
            'payment_date': date.isoformat() if date else None,
            'amount': str((Decimal(str(a.amount_base)) / divisor).quantize(Q2)),
            'amount_base': str(a.amount_base),
            'voucher_amount': str(a.amount),
            'currency_code': getattr(source.currency, 'Code', None),
            'is_posted': True,
            'journal': source.journal_id,
            'journal_id_display': source.journal_id,
            'notes': (a.payment.notes if a.payment_id else a.note.reason) or '',
            'shipment_label': label,
        })
    rows.sort(key=lambda r: r['payment_date'] or '', reverse=True)
    return rows


#: نوع مرجع القيد ← (الصنف، ما يعرّفه المرجع). `payment` = دفعة المستند المباشرة.
_REFERENCE_DOCS = {
    'LOGISTICS_CLEARANCE': ('clearance', 'doc'),
    'LOGISTICS_CLEARANCE_ADJUST': ('clearance', 'doc'),
    'CLEARANCE_PAYMENT': ('clearance', 'payment'),
    'CLEARANCE_PAYMENT_UNPOST': ('clearance', 'payment'),
    'CLEARANCE_PAYMENT_SPLIT': ('clearance', 'payment'),
    'CLEARANCE_PAYMENT_SPLIT_REVERSAL': ('clearance', 'payment'),
    'LOCAL_SHIPMENT': ('local', 'doc'),
    'LOCAL_SHIPMENT_ADJUST': ('local', 'doc'),
    'LOCAL_SHIPMENT_PAYMENT': ('local', 'payment'),
    'LOCAL_SHIPMENT_PAYMENT_SPLIT': ('local', 'payment'),
    'LOCAL_SHIPMENT_PAYMENT_SPLIT_REVERSAL': ('local', 'payment'),
    'SHIPMENT_FREIGHT_ACCRUAL': ('freight', 'doc'),
    'SHIPMENT_FREIGHT_ACCRUAL_ADJUST': ('freight', 'doc'),
    'LOGISTICS_SHIPMENT': ('freight', 'doc'),
    'LOGISTICS_PAYMENT': ('freight', 'payment'),
}


def _reference_accruals(tenant_id: int, wanted: dict) -> dict:
    """{(reference_type, reference_id): (الصنف، المستحق)} — المستحق نفسه أو مستحقّ الدفعة
    المباشرة، بالدفعة (استعلامٌ لكل صنف لا لكل صف). ما لا مستند له لا يظهر."""
    from logistics.models import (
        LocalShipment,
        LocalShipmentPayment,
        LogisticsClearance,
        LogisticsClearancePayment,
        LogisticsPayment,
        LogisticsShipment,
    )

    def ids(kind: str, role: str) -> set:
        return {i for t, (k, r) in _REFERENCE_DOCS.items() if (k, r) == (kind, role) for i in wanted.get(t, ())}

    ship_deals = 'deals__partner'
    docs = {
        'clearance': {c.pk: c for c in LogisticsClearance.objects.filter(
            tenant_id=tenant_id, pk__in=ids('clearance', 'doc'),
        ).select_related('shipment').prefetch_related(f'shipment__{ship_deals}')},
        'local': {ls.pk: ls for ls in LocalShipment.objects.filter(
            tenant_id=tenant_id, pk__in=ids('local', 'doc'),
        ).select_related('shipment', 'clearance__shipment').prefetch_related(
            f'shipment__{ship_deals}', f'clearance__shipment__{ship_deals}')},
        'freight': {s.pk: s for s in LogisticsShipment.all_objects.filter(
            tenant_id=tenant_id, pk__in=ids('freight', 'doc'),
        ).prefetch_related(ship_deals)},
    }
    payments = {
        'clearance': {p.pk: p.clearance for p in LogisticsClearancePayment.objects.filter(
            tenant_id=tenant_id, pk__in=ids('clearance', 'payment'),
        ).select_related('clearance__shipment').prefetch_related(f'clearance__shipment__{ship_deals}')},
        'local': {p.pk: p.local_shipment for p in LocalShipmentPayment.objects.filter(
            tenant_id=tenant_id, pk__in=ids('local', 'payment'),
        ).select_related('local_shipment__shipment', 'local_shipment__clearance__shipment').prefetch_related(
            f'local_shipment__shipment__{ship_deals}', f'local_shipment__clearance__shipment__{ship_deals}')},
        # دفعة الوكيل (شحنةٌ بلا صفقة) وحدها — دفعة الصفقة للمورد وتتبع فاتورتها.
        'freight': {p.pk: p.shipment for p in LogisticsPayment.all_objects.filter(
            tenant_id=tenant_id, pk__in=ids('freight', 'payment'), shipment__isnull=False, deal__isnull=True,
        ).select_related('shipment').prefetch_related(f'shipment__{ship_deals}')},
    }
    out = {}
    for ref_type, (kind, role) in _REFERENCE_DOCS.items():
        source = docs[kind] if role == 'doc' else payments[kind]
        for ref_id in wanted.get(ref_type, ()):
            if source.get(ref_id) is not None:
                out[(ref_type, ref_id)] = (kind, source[ref_id])
    return out


def _voucher_accruals(tenant_id: int, payment_ids, *, source: str = 'payment') -> dict:
    """{سند الصرف: [(الصنف، المستحق، المبلغ بالأساس)]} من `LogisticsAccrualAllocation` — بالدفعة.
    `source='note'`: المفتاح الإشعار المدين الموزَّع بدل السند."""
    from logistics.models import LogisticsAccrualAllocation

    ship_deals = 'deals__partner'
    out: dict[int, list] = {}
    if not payment_ids:
        return out
    for alloc in LogisticsAccrualAllocation.objects.filter(
        tenant_id=tenant_id, **{f'{source}_id__in': payment_ids},
    ).select_related(
        'clearance__shipment', 'shipment', 'local_shipment__shipment', 'local_shipment__clearance__shipment',
    ).prefetch_related(
        f'clearance__shipment__{ship_deals}', f'shipment__{ship_deals}',
        f'local_shipment__shipment__{ship_deals}', f'local_shipment__clearance__shipment__{ship_deals}',
    ).order_by('id'):
        kind = 'clearance' if alloc.clearance_id else ('freight' if alloc.shipment_id else 'local')
        obj = alloc.clearance or alloc.shipment or alloc.local_shipment
        out.setdefault(getattr(alloc, f'{source}_id'), []).append((kind, obj, _money(alloc.amount_base)))
    return out


#: الصنف ← نوع مرجع قيد استحقاقه — مفتاح مرساة المستحق في كشف الحساب.
ACCRUAL_ANCHOR_TYPE = {
    'clearance': 'LOGISTICS_CLEARANCE',
    'local': 'LOCAL_SHIPMENT',
    'freight': 'SHIPMENT_FREIGHT_ACCRUAL',
}


def _anchor_of(kind: str, obj) -> dict:
    """مرساة المستحق: مفتاحها ووسمها («SH-0017 — شحنة رقع») ورقمها المختصر لعدّ المستندات."""
    if kind == 'local':
        label, short = obj.display_label, obj.shipment_number or f"#{obj.pk}"
    else:
        ship = obj if kind == 'freight' else getattr(obj, 'shipment', None)
        label = shipment_label_of(kind, obj) or f"#{obj.pk}"
        short = (ship.shipment_number if ship is not None else '') or f"#{obj.pk}"
    return {'key': f"{ACCRUAL_ANCHOR_TYPE[kind]}:{obj.pk}", 'label': label, 'short': short}


def journal_reference_shipment_labels(tenant_id: int, refs) -> dict:
    """{(reference_type, reference_id): وسم الشحنة الحيّ} لأسطر كشف الحساب — بالدفعة.

    الوصف المحفوظ في القيد نصُّ لحظة الترحيل (رقم الشحنة وحده في القديم)؛ هذا يقرأ
    المستند المرجعي الآن: التخليص ودفعاته، الإرسالية ودفعاتها، استحقاق الشحن ودفعات
    الوكيل، فاتورة الشراء، وسند الصرف بما وُزِّع عليه. ما لا مستند له لا يظهر.
    """
    from logistics.models import LogisticsPayment, PurchaseInvoice

    wanted: dict[str, set] = {}
    for ref_type, ref_id in refs:
        if ref_type and ref_id:
            wanted.setdefault(ref_type, set()).add(ref_id)

    out = {}
    for ref, (kind, obj) in _reference_accruals(tenant_id, wanted).items():
        # الإرسالية برقمها ووسم شحنتها («LS-0003 · SH-0019 — …») — قد تكون بلا شحنة.
        label = obj.display_label if kind == 'local' else shipment_label_of(kind, obj)
        if label:
            out[ref] = label

    ship_deals = 'deals__partner'
    # دفعة الصفقة (للمورد) تحمل شحنتها إن رُبطت بها — وسمٌ فقط، فمرساتها فاتورتها.
    for p in LogisticsPayment.all_objects.filter(
        tenant_id=tenant_id, pk__in=wanted.get('LOGISTICS_PAYMENT', ()),
        shipment__isnull=False, deal__isnull=False,
    ).select_related('shipment').prefetch_related(f'shipment__{ship_deals}'):
        out[('LOGISTICS_PAYMENT', p.pk)] = p.shipment.display_label

    for inv in PurchaseInvoice.objects.filter(
        tenant_id=tenant_id, pk__in=wanted.get('PURCHASE_INVOICE', ()), shipment__isnull=False,
    ).select_related('shipment').prefetch_related(f'shipment__{ship_deals}'):
        out[('PURCHASE_INVOICE', inv.pk)] = inv.shipment.display_label

    for voucher_id, targets in _voucher_accruals(tenant_id, wanted.get('SUPPLIER_PAYMENT', ())).items():
        labels = []
        for kind, obj, _amount in targets:
            label = shipment_label_of(kind, obj)
            if label and label not in labels:
                labels.append(label)
        if labels:
            out[('SUPPLIER_PAYMENT', voucher_id)] = '، '.join(labels)
    return out


def journal_reference_accrual_links(tenant_id: int, refs) -> dict:
    """روابط كشف الحساب للمستحقّات اللوجستية — بالدفعة لا لكل صف.

    يُرجع:
      - ``anchors``: {(reference_type, reference_id): مرساة} لقيد المستحق نفسه ولقيود دفعاته
        المباشرة (دفعة التخليص/الإرسالية/الوكيل، وقيود الفصل وعكسها).
      - ``vouchers``: {سند الصرف: [مرساة + ``amount`` بالأساس]} من `LogisticsAccrualAllocation`.
      - ``notes``: {الإشعار المدين: [مرساة + ``amount``]} — توزيعاته بالمثل.
      - ``deal_invoices``: {دفعة الصفقة: [فاتورتها الدولية المرحّلة]} — مرساتها الفاتورة.
    المرساة: ``{'key': 'LOGISTICS_CLEARANCE:13', 'label': 'SH-0017 — شحنة رقع', 'short': 'SH-0017'}``.
    """
    from logistics.models import LogisticsPayment, PurchaseInvoice

    wanted: dict[str, set] = {}
    for ref_type, ref_id in refs:
        if ref_type and ref_id:
            wanted.setdefault(ref_type, set()).add(ref_id)

    anchors = {
        ref: _anchor_of(kind, obj)
        for ref, (kind, obj) in _reference_accruals(tenant_id, wanted).items()
    }
    vouchers = {
        voucher_id: [{**_anchor_of(kind, obj), 'amount': amount} for kind, obj, amount in targets]
        for voucher_id, targets in _voucher_accruals(tenant_id, wanted.get('SUPPLIER_PAYMENT', ())).items()
    }
    notes = {
        note_id: [{**_anchor_of(kind, obj), 'amount': amount} for kind, obj, amount in targets]
        for note_id, targets in _voucher_accruals(
            tenant_id, wanted.get('CREDIT_DEBIT_NOTE', ()), source='note').items()
    }
    # الإشعار المربوط بمستحقٍّ يرسو عليه كدفعته — الدائن دائماً، والمدين حين لا توزيع له.
    note_ids = wanted.get('CREDIT_DEBIT_NOTE')
    if note_ids:
        from sales.models import CreditDebitNote

        ship_deals = 'deals__partner'
        for note in CreditDebitNote.objects.filter(
            tenant_id=tenant_id, pk__in=note_ids,
        ).exclude(
            related_clearance__isnull=True, related_shipment__isnull=True, related_local_shipment__isnull=True,
        ).select_related(
            'related_clearance__shipment', 'related_shipment',
            'related_local_shipment__shipment', 'related_local_shipment__clearance__shipment',
        ).prefetch_related(
            f'related_clearance__shipment__{ship_deals}', f'related_shipment__{ship_deals}',
            f'related_local_shipment__shipment__{ship_deals}',
            f'related_local_shipment__clearance__shipment__{ship_deals}',
        ):
            for kind, field in _NOTE_LINK_FIELD.items():
                obj = getattr(note, field)
                if obj is not None:
                    anchors[('CREDIT_DEBIT_NOTE', note.pk)] = _anchor_of(kind, obj)
                    break

    deal_invoices: dict[int, list[int]] = {}
    deal_payment_ids = wanted.get('LOGISTICS_PAYMENT', set()) | wanted.get('LOGISTICS_PAYMENT_UNPOST', set())
    if deal_payment_ids:
        payment_deal = dict(LogisticsPayment.all_objects.filter(
            tenant_id=tenant_id, pk__in=deal_payment_ids, deal__isnull=False,
        ).values_list('pk', 'deal_id'))
        by_deal: dict[int, list[int]] = {}
        for inv_id, deal_id in PurchaseInvoice.objects.filter(
            tenant_id=tenant_id, deal_id__in=set(payment_deal.values()), is_posted=True,
        ).order_by('id').values_list('pk', 'deal_id'):
            by_deal.setdefault(deal_id, []).append(inv_id)
        deal_invoices = {pay_id: by_deal.get(deal_id, []) for pay_id, deal_id in payment_deal.items()}
    return {'anchors': anchors, 'vouchers': vouchers, 'notes': notes, 'deal_invoices': deal_invoices}


#: الصنف ← حقل الطرف الدائن على المستند.
_PARTY_FIELD = {'clearance': 'customs_broker', 'freight': 'shipping_agent', 'local': 'carrier'}


def _party_accrual_docs(tenant_id: int, partner_id: int | None):
    """مستحقّات الطرف المرحّلة — أو مستحقّات كل أطراف الشركة حين `partner_id=None`."""
    from logistics.models import LocalShipment, LogisticsClearance, LogisticsShipment

    def party(kind: str) -> dict:
        field = _PARTY_FIELD[kind]
        if partner_id is None:
            return {f'{field}__isnull': False}
        return {f'{field}_id': partner_id}

    yield from (
        ('clearance', c) for c in LogisticsClearance.objects.filter(
            tenant_id=tenant_id, journal__isnull=False, **party('clearance'),
        ).select_related('journal', 'shipment', 'customs_broker').prefetch_related('shipment__deals__partner')
    )
    yield from (
        ('freight', s) for s in LogisticsShipment.objects.filter(
            tenant_id=tenant_id, freight_is_posted=True, freight_journal__isnull=False,
            **party('freight'),
        ).select_related('freight_journal', 'shipping_agent').prefetch_related('deals__partner')
    )
    yield from (
        ('local', ls) for ls in LocalShipment.objects.filter(
            tenant_id=tenant_id, is_posted=True, journal__isnull=False, **party('local'),
        ).select_related('journal', 'carrier', 'shipment', 'clearance__shipment').prefetch_related(
            'shipment__deals__partner', 'clearance__shipment__deals__partner')
    )


#: الصنف ← حقل قيد الاستحقاق على المستند.
_ACCRUAL_JOURNAL = {'clearance': 'journal', 'freight': 'freight_journal', 'local': 'journal'}


def _accrual_date(kind: str, obj):
    return getattr(getattr(obj, _ACCRUAL_JOURNAL[kind]), 'transaction_date', None)


def party_accrued_total(tenant_id: int, partner_id: int):
    """(مجموع مستحقّات الطرف المرحّلة، تاريخ آخرها) — «إجمالي مشتريات» المخلّص والوكيل
    والناقل في كرته. دائنُ الطرف في قيود الاستحقاق نفسها التي تقرأ منها `accrual_status`،
    باستعلامٍ واحدٍ على القيود لا استعلاماتٍ لكل مستند."""
    journal_ids, last = [], None
    docs: dict[str, list[int]] = {}
    for kind, obj in _party_accrual_docs(tenant_id, partner_id):
        journal_ids.append(getattr(obj, f'{_ACCRUAL_JOURNAL[kind]}_id'))
        docs.setdefault(kind, []).append(obj.pk)
        date = _accrual_date(kind, obj)
        if date and (last is None or date > last):
            last = date
    # تعديلات الاستحقاق جزءٌ منه — استعلامٌ لكل صنف.
    for kind, ids in docs.items():
        for adjust_ids in _adjustments_by_doc(kind, tenant_id, ids).values():
            journal_ids.extend(adjust_ids)
    return _party_net(journal_ids, partner_id, credit_side=True), last


def party_on_account_summary(tenant_id: int, partner_id: int) -> dict:
    """رقما رأس كشف الطرف الدائن: «دفعات تحت الحساب» و«فائض» — بالعملة الأساسية.

    تحت الحساب = غير الموزَّع من سندات صرفه وإشعاراته المدينة المرحّلة + ما زاد على
    مستحقٍّ لوجستي لحظة الدفع. الفائض = ما صار زائداً على مستحقٍّ لأن المستحق خُفِّض بعد الدفع
    (`accrual_status`). مجموعهما رصيدٌ لصالحنا لم يُستهلك؛ رصيد الكشف لا يتغيّر بهما.
    """
    from logistics.models import LogisticsAccrualAllocation
    from sales.models import SupplierPayment, SupplierPaymentAllocation

    # `voucher_unallocated` لكل سند بثلاثة استعلامات ثابتة لا اثنين لكل سند.
    vouchers = list(SupplierPayment.objects.filter(
        tenant_id=tenant_id, partner_id=partner_id, is_posted=True,
    ).only('id', 'amount', 'exchange_rate'))
    used: dict[int, Decimal] = {}
    for model in (SupplierPaymentAllocation, LogisticsAccrualAllocation):
        for pid, total in model.objects.filter(payment__in=[v.pk for v in vouchers]).values(
            'payment_id').annotate(t=Sum('amount')).values_list('payment_id', 't'):
            used[pid] = used.get(pid, ZERO) + _money(total)
    on_account = ZERO
    for voucher in vouchers:
        free = max(_money(voucher.amount) - used.get(voucher.pk, ZERO), ZERO)
        if free > 0:
            on_account += _payment_base(voucher, free)
    on_account += sum((base for _note, _free, base in party_unallocated_notes(tenant_id, partner_id)), ZERO)
    surplus = ZERO
    for kind, obj in _party_accrual_docs(tenant_id, partner_id):
        status = accrual_status(kind, obj)
        surplus += status['surplus']
        on_account += status['overpaid'] - status['surplus']
    return {'on_account': _money(on_account), 'surplus': _money(surplus)}


def party_unallocated_notes(tenant_id: int, partner_id: int) -> list[tuple]:
    """[(الإشعار، غير الموزَّع بعملته، بالأساس)] لإشعارات الدائن المدينة المرحّلة — خصمٌ منه لم
    يُطفئ مستنداً بعد، فهو رصيدٌ لنا عنده كالسند غير الموزَّع. بثلاثة استعلامات ثابتة."""
    from logistics.models import LogisticsAccrualAllocation
    from sales.models import CreditDebitNote, CreditDebitNoteAllocation

    notes = list(CreditDebitNote.objects.filter(
        tenant_id=tenant_id, partner_id=partner_id, status=CreditDebitNote.STATUS_POSTED,
        note_type=CreditDebitNote.TYPE_DEBIT,
    ).select_related('currency').order_by('note_date', 'id'))
    used: dict[int, Decimal] = {}
    for model in (CreditDebitNoteAllocation, LogisticsAccrualAllocation):
        for nid, total in model.objects.filter(note__in=[n.pk for n in notes]).values(
            'note_id').annotate(t=Sum('amount')).values_list('note_id', 't'):
            used[nid] = used.get(nid, ZERO) + _money(total)
    out = []
    for note in notes:
        free = max(_money(note.amount) - used.get(note.pk, ZERO), ZERO)
        if free > 0:
            out.append((note, free, _payment_base(note, free)))
    return out


def party_open_accruals(tenant_id: int, partner_id: int, *, include_settled: bool = False) -> list[dict]:
    """مستحقّات الطرف المرحّلة مرتّبةً بتاريخ الاستحقاق (الأقدم أولاً — ترتيب FIFO)."""
    rows = []
    for kind, obj in _party_accrual_docs(tenant_id, partner_id):
        status = accrual_status(kind, obj)
        if not include_settled and status['remaining'] <= 0:
            continue
        date = _accrual_date(kind, obj)
        rows.append({
            'kind': kind,
            'id': obj.pk,
            'label': _label(kind, obj),
            'shipment_label': shipment_label_of(kind, obj),
            'shipment_id': shipment_id_of(kind, obj),
            'date': date.isoformat() if date else None,
            **{k: str(v) for k, v in status.items()},
        })
    rows.sort(key=lambda r: (r['date'] or '9999-12-31', KINDS.index(r['kind']), r['id']))
    return rows


def tenant_open_accruals(tenant_id: int) -> list[tuple]:
    """[(الطرف، اسمه، تاريخ الاستحقاق، المتبقّي)] لكل مستحقٍّ لوجستي غير مسدَّد في الشركة —
    جانب المخلّص والوكيل والناقل من أعمار الذمم الدائنة (`core/reports/financial.py` — `_aging`).
    المتبقّي من `accrual_status` نفسها التي تقرأ منها البطاقة والتوزيع."""
    out = []
    for kind, obj in _party_accrual_docs(tenant_id, None):
        remaining = accrual_status(kind, obj)['remaining']
        if remaining <= 0:
            continue
        party = getattr(obj, _PARTY_FIELD[kind])
        out.append((party.pk, party.name, _accrual_date(kind, obj), remaining))
    return out


def suggest_accrual_fifo(tenant_id: int, partner_id: int, amount) -> list[dict]:
    """توزيع مبلغ (بالعملة الأساسية) على مستحقّات الطرف من الأقدم — مرآة
    `suggest_supplier_fifo_allocations` لفواتير الشراء."""
    left = _money(amount)
    out = []
    for row in party_open_accruals(tenant_id, partner_id):
        if left <= 0:
            break
        take = min(Decimal(row['remaining']), left)
        out.append({'kind': row['kind'], 'id': row['id'], 'label': row['label'], 'amount': str(take)})
        left -= take
    return out


def _payment_base(payment, amount: Decimal) -> Decimal:
    rate = Decimal(str(payment.exchange_rate or 1)) or Decimal('1')
    return (amount * rate).quantize(Q2)


def voucher_unallocated(payment) -> Decimal:
    """ما لم يُوزَّع من السند بعملته — على فواتير الشراء والمستحقّات اللوجستية معاً."""
    from logistics.models import LogisticsAccrualAllocation
    from sales.models import SupplierPaymentAllocation

    used = (
        _money(SupplierPaymentAllocation.objects.filter(payment=payment).aggregate(t=Sum('amount'))['t'])
        + _money(LogisticsAccrualAllocation.objects.filter(payment=payment).aggregate(t=Sum('amount'))['t'])
    )
    return max(_money(payment.amount) - used, ZERO)


def _load_accrual(kind: str, pk: int, tenant_id: int, *, lock: bool = True):
    from logistics.models import LocalShipment, LogisticsClearance, LogisticsShipment

    model = {'clearance': LogisticsClearance, 'freight': LogisticsShipment, 'local': LocalShipment}.get(kind)
    if model is None:
        raise ValidationError(f"صنف مستحق غير معروف: {kind}")
    qs = model.objects.select_for_update() if lock else model.objects
    obj = qs.filter(pk=pk, tenant_id=tenant_id).first()
    if obj is None:
        raise ValidationError(f"المستند {kind} #{pk} غير موجود في هذه الشركة.")
    return obj


def accrual_snapshot(tenant_id: int, kind: str, pk: int) -> dict:
    """حالة مستحقٍّ واحد للواجهة — تنبيه «سيُفصل X كدفعة تحت الحساب» قبل الدفع."""
    obj = _load_accrual(kind, pk, tenant_id, lock=False)
    _party_id, accrual_journal_id, _ = _accrual_meta(kind, obj)
    return {
        'kind': kind, 'id': obj.pk, 'label': _label(kind, obj),
        'accrual_posted': bool(accrual_journal_id),
        **{k: str(v) for k, v in accrual_status(kind, obj).items()},
    }


def allocate_voucher_to_accruals(payment, allocations: list[dict], *, user=None):
    """توزيع سند صرفٍ مرحَّل على مستحقّات طرفه اللوجستية — ربطٌ بلا قيد.

    ترحيل السند دَيَّن ذمّة الطرف أصلاً (Dr ذمّة / Cr صندوق)، فالتوزيع يحدّد فقط
    أيّ مستحقٍّ استهلك أيّ جزء — مرآة `allocate_supplier_payment` لفواتير الشراء.
    `allocations`: ``[{"kind": "clearance"|"freight"|"local", "id": <pk>, "amount": <بعملة السند>}]``
    """
    from accounting.services import create_audit_log
    from logistics.models import LogisticsAccrualAllocation
    from sales.models import SupplierPayment

    rows = []
    for a in allocations or []:
        try:
            rows.append((str(a['kind']), int(a['id']), _money(a.get('amount'))))
        except (KeyError, TypeError, ValueError, ArithmeticError):
            raise ValidationError("صفّ توزيع غير صالح.")
    if not rows:
        raise ValidationError("لا توزيعات مُرسَلة.")
    if any(amount <= 0 for _k, _i, amount in rows):
        raise ValidationError("مبلغ التوزيع يجب أن يكون أكبر من صفر.")

    with transaction.atomic():
        payment = SupplierPayment.objects.select_for_update().get(pk=payment.pk)
        if not payment.is_posted:
            raise ValidationError("رحّل سند الصرف أولاً — التوزيع على المستحقّات لسندٍ مرحَّل.")
        total_new = sum((amount for _k, _i, amount in rows), ZERO)
        free = voucher_unallocated(payment)
        if total_new > free + Q2:
            raise ValidationError(
                f"مجموع التوزيعات ({total_new}) يتجاوز غير الموزَّع من السند ({free}).")
        for kind, pk, amount in rows:
            obj = _load_accrual(kind, pk, payment.tenant_id)
            party_id, accrual_journal_id, _ = _accrual_meta(kind, obj)
            if not accrual_journal_id:
                raise ValidationError(f"{_label(kind, obj)} غير مرحَّل الاستحقاق.")
            if party_id != payment.partner_id:
                raise ValidationError(f"{_label(kind, obj)} لا يخصّ طرف السند.")
            base = _payment_base(payment, amount)
            remaining = accrual_remaining(kind, obj)
            if base > remaining + Q2:
                raise ValidationError(
                    f"مبلغ التوزيع ({base}) يتجاوز المتبقّي على {_label(kind, obj)} ({remaining}).")
            LogisticsAccrualAllocation.objects.create(
                tenant_id=payment.tenant_id, payment=payment,
                **{_ALLOCATION_FIELD[kind]: obj}, amount=amount, amount_base=base,
            )
            logger.info("supplier_payment.accrual_allocate payment=%s %s=%s amount=%s base=%s",
                        payment.id, kind, pk, amount, base)
        create_audit_log(
            tenant=payment.tenant, user=user, action="ALLOCATE",
            model_name="SupplierPayment", object_id=payment.id,
            change_details=f"Allocated {total_new} to {len(rows)} logistics accrual(s)",
        )
    return payment


def allocate_note_to_accrual(note, kind: str, pk: int, amount: Decimal, *, base: Decimal) -> str:
    """توزيع إشعارٍ مدينٍ مرحَّل على مستحقٍّ لوجستي لطرفه — داخل معاملة `allocate_note`
    (`sales/services/note_allocation.py`) التي تحرس غير الموزَّع. يُرجع وسم المستحق."""
    from logistics.models import LogisticsAccrualAllocation

    obj = _load_accrual(kind, pk, note.tenant_id)
    party_id, accrual_journal_id, _ = _accrual_meta(kind, obj)
    if not accrual_journal_id:
        raise ValidationError(f"{_label(kind, obj)} غير مرحَّل الاستحقاق.")
    if party_id != note.partner_id:
        raise ValidationError(f"{_label(kind, obj)} لا يخصّ طرف الإشعار.")
    remaining = accrual_remaining(kind, obj)
    # تقريب المبلغ إلى القرش ثم ضربه بالسعر قد يتجاوز المتبقّي بكسرٍ دون قرشٍ بعملة الإشعار.
    slack = (Q2 * (Decimal(str(note.exchange_rate or 1)) or Decimal('1'))).quantize(Q2) + Q2
    if base > remaining + slack:
        raise ValidationError(
            f"مبلغ التوزيع ({base}) يتجاوز المتبقّي على {_label(kind, obj)} ({remaining}).")
    LogisticsAccrualAllocation.objects.create(
        tenant_id=note.tenant_id, note=note, **{_ALLOCATION_FIELD[kind]: obj},
        amount=amount, amount_base=min(base, remaining),
    )
    return _label(kind, obj)


def note_accrual_allocation_rows(note) -> list[dict]:
    """توزيعات الإشعار على المستحقّات اللوجستية للعرض — مرآة صفوف `note_allocation_rows`."""
    from logistics.models import LogisticsAccrualAllocation

    return [
        {'allocation_kind': 'accrual', 'allocation_id': a.pk, 'kind': kind, 'id': obj.pk,
         'label': _label(kind, obj), 'amount': str(a.amount)}
        for a in LogisticsAccrualAllocation.objects.filter(note=note).select_related(
            'clearance__shipment', 'shipment', 'local_shipment',
        ).prefetch_related('clearance__shipment__deals__partner', 'shipment__deals__partner').order_by('id')
        for kind, obj in [(
            'clearance' if a.clearance_id else ('freight' if a.shipment_id else 'local'),
            a.clearance or a.shipment or a.local_shipment,
        )]
    ]


def deallocate_voucher_accrual(payment, allocation_id: int, *, user=None):
    """فكّ توزيعٍ واحد — المبلغ يعود «تحت الحساب» على السند."""
    from accounting.services import create_audit_log
    from logistics.models import LogisticsAccrualAllocation

    with transaction.atomic():
        alloc = LogisticsAccrualAllocation.objects.select_for_update().filter(
            pk=allocation_id, payment=payment,
        ).first()
        if alloc is None:
            raise ValidationError("التوزيع غير موجود على هذا السند.")
        amount = alloc.amount
        alloc.delete()
        create_audit_log(
            tenant=payment.tenant, user=user, action="DEALLOCATE",
            model_name="SupplierPayment", object_id=payment.id,
            change_details=f"Deallocated {amount} from logistics accrual allocation #{allocation_id}",
        )
    return payment


__all__ = [
    'KINDS', 'accrual_status', 'accrual_remaining', 'accrual_snapshot', 'allocated_base', 'document_settlement',
    'document_voucher_rows', 'journal_reference_shipment_labels', 'party_open_accruals', 'shipment_label_of',
    'suggest_accrual_fifo', 'voucher_unallocated', 'allocate_voucher_to_accruals',
    'deallocate_voucher_accrual', 'journal_reference_accrual_links', 'ACCRUAL_ANCHOR_TYPE',
    'tenant_open_accruals', 'party_accrued_total', 'shipment_id_of',
    'ACCRUAL_ADJUST_TYPE', 'accrual_journal_ids', 'adjustment_journal_ids', 'party_on_account_summary',
    'note_journal_ids', 'party_unallocated_notes', 'allocate_note_to_accrual', 'note_accrual_allocation_rows',
]
