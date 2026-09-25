"""مستحقّات الأطراف اللوجستية — **مصدرٌ واحد** لـ«المستحق/المدفوع/المتبقّي».

ثلاثة أصناف، لكلٍّ قيد استحقاقٍ مرحَّل يُدائن ذمّة الطرف:

- ``clearance`` ← `LogisticsClearance.journal` (المخلّص `customs_broker`)
- ``freight``   ← `LogisticsShipment.freight_journal` (وكيل الشحن `shipping_agent`)
- ``local``     ← `LocalShipment.journal` (الناقل `carrier`)

الأرقام تُقرأ من **أسطر القيود الموسومة بالطرف** بالعملة الأساسية
(`base_credit`/`base_debit`) لا من حقول المستند: الاستحقاق المرحَّل هو ما يدين به
الدفتر فعلاً، ودفعةٌ بعملة أجنبية أو قسمٌ منها لطرفٍ آخر (شحنُ الناقل داخل دفعة
التخليص) يُحسب كما رُحِّل لا كما كُتب في النموذج. فلا فرق عملة ولا تصنيف ملاحظات.

    المستحق  = Σ(دائن − مدين) لأسطر الطرف في قيد الاستحقاق
    المدفوع  = Σ(مدين − دائن) لأسطر الطرف في قيود دفعات المستند نفسه المرحّلة
    الموزَّع = Σ `LogisticsAccrualAllocation.amount_base` لسندات صرفٍ مرحّلة
    المتبقّي = max(المستحق − المدفوع − الموزَّع، 0)

يستعملها منتقي التوزيع وFIFO والتحقّق عند التوزيع، وفصلُ الدفعة الزائدة عند
الترحيل وأمرُ `split_logistics_overpayments`، و3ب (`import_settlement`) يضيف منها
حصّة سندات الصرف الموزَّعة إلى كل حوض.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

logger = logging.getLogger(__name__)

Q2 = Decimal('0.01')
ZERO = Decimal('0.00')
KINDS = ('clearance', 'freight', 'local')

#: الصنف ← (حقل FK في `LogisticsAccrualAllocation`، تسمية المستند)
_ALLOCATION_FIELD = {'clearance': 'clearance', 'freight': 'shipment', 'local': 'local_shipment'}


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


def allocated_base(kind: str, objs) -> Decimal:
    """ما وُزِّع من سندات صرفٍ **مرحّلة** على مستندات صنفٍ واحد (بالعملة الأساسية)."""
    from logistics.models import LogisticsAccrualAllocation

    ids = [o.pk for o in objs if o is not None]
    if not ids:
        return ZERO
    total = LogisticsAccrualAllocation.objects.filter(
        **{f"{_ALLOCATION_FIELD[kind]}_id__in": ids}, payment__is_posted=True,
    ).aggregate(t=Sum('amount_base'))['t']
    return _money(total)


def accrual_status(kind: str, obj, *, exclude_payment_journal_id=None) -> dict:
    """{due, paid, allocated, remaining, overpaid} لمستندٍ واحد بالعملة الأساسية.

    `exclude_payment_journal_id`: يستثني قيد دفعةٍ بعينها — يستعمله فصلُ الزائد
    ليحسب ما بقي **قبل** تلك الدفعة.
    """
    party_id, accrual_journal_id, pay_journals = _accrual_meta(kind, obj)
    if exclude_payment_journal_id:
        pay_journals = [j for j in pay_journals if j != exclude_payment_journal_id]
    due = _party_net([accrual_journal_id], party_id, credit_side=True) if accrual_journal_id else ZERO
    paid = _party_net(pay_journals, party_id, credit_side=False)
    allocated = allocated_base(kind, [obj])
    settled = paid + allocated
    return {
        'due': due,
        'paid': paid,
        'allocated': allocated,
        'remaining': max(due - settled, ZERO),
        'overpaid': max(settled - due, ZERO),
    }


def accrual_remaining(kind: str, obj, **kwargs) -> Decimal:
    return accrual_status(kind, obj, **kwargs)['remaining']


def _label(kind: str, obj) -> str:
    if kind == 'clearance':
        ship = getattr(obj, 'shipment', None)
        return f"تخليص #{obj.pk}" + (f" — {ship.shipment_number}" if ship and ship.shipment_number else "")
    if kind == 'freight':
        return f"شحن {obj.shipment_number or f'#{obj.pk}'}"
    return f"إرسالية {obj.shipment_number or f'#{obj.pk}'}"


def _party_accrual_docs(tenant_id: int, partner_id: int):
    from logistics.models import LocalShipment, LogisticsClearance, LogisticsShipment

    yield from (
        ('clearance', c) for c in LogisticsClearance.objects.filter(
            tenant_id=tenant_id, customs_broker_id=partner_id, journal__isnull=False,
        ).select_related('journal', 'shipment')
    )
    yield from (
        ('freight', s) for s in LogisticsShipment.objects.filter(
            tenant_id=tenant_id, shipping_agent_id=partner_id,
            freight_is_posted=True, freight_journal__isnull=False,
        ).select_related('freight_journal')
    )
    yield from (
        ('local', ls) for ls in LocalShipment.objects.filter(
            tenant_id=tenant_id, carrier_id=partner_id, is_posted=True, journal__isnull=False,
        ).select_related('journal')
    )


def _accrual_date(kind: str, obj):
    journal = {'clearance': 'journal', 'freight': 'freight_journal', 'local': 'journal'}[kind]
    return getattr(getattr(obj, journal), 'transaction_date', None)


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
            'date': date.isoformat() if date else None,
            **{k: str(v) for k, v in status.items()},
        })
    rows.sort(key=lambda r: (r['date'] or '9999-12-31', KINDS.index(r['kind']), r['id']))
    return rows


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
    'KINDS', 'accrual_status', 'accrual_remaining', 'accrual_snapshot', 'allocated_base', 'party_open_accruals',
    'suggest_accrual_fifo', 'voucher_unallocated', 'allocate_voucher_to_accruals',
    'deallocate_voucher_accrual',
]
