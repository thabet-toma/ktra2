"""بنود كل قيد استحقاقٍ لوجستي — لقطةٌ لكل قيد، ومنها تفصيلُ ما غيّره كل تعديل.

بنود التخليص (`LogisticsClearanceLine`) حالتُه الحالية وحدها، و«تعديل الاستحقاق»
(`domain/accrual_adjust.py`) يكتب فوقها ويرحّل قيد فرق: فكانت بنود الأصل تضيع، ولا يُعرف
في أي مكان أيُّ بندٍ تغيّر (الإنتاج: تخليصات SH-0014/15/16 سطرٌ «إجمالي» قبل التعديل وبعده).

`AccrualLineSnapshot` لكل قيد في سلسلة المستند (`party_accruals.accrual_journal_ids`):

    الأصلي   ← يُكتب مع قيد الاستحقاق (`accruals.post_*_accrual`)، مجموعه = دائن الطرف فيه
    التعديل  ← يُكتب مع قيد الفرق (`accrual_adjust.adjust_accrual`)، مجموعه = المستحق بعده
    الفرق    ← بين لقطتين متتاليتين بندًا بندًا (`diff_rows`) — مجموعه = مبلغ قيد التعديل

المبالغ بالعملة الأساسية: ما يحمله الدفتر وكشف الطرف. ولقطةٌ لا تفصيل لها (`detailed=False`:
سطر «إجمالي» من قيدٍ سبق الميزة، أو مبلغ الشحن/الإرسالية الواحد) تُعبّأ بنودها لاحقاً
(`fill_snapshot`) بمجموعٍ مطابقٍ بالقرش — تفاصيلُ لا قيد، بسجلّ تدقيق.

المرجع: Odoo يحفظ أسطر «تكاليف الاستيراد» مع قيدها، وتعديلُها مستندٌ جديد لا كتابةٌ فوق
القديم. زدنا: فرقُ كل تعديلٍ بندًا بندًا (جديد/محذوف/نقص/زيادة) في رحلة الاستيراد وفي كشف
الطرف من مصدرٍ واحد، وتفصيلٌ يُضاف بأثرٍ رجعي لقيدٍ قديم دون أن يُمسّ.
"""
from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db.models import Sum

from logistics.domain.party_accruals import Q2, ZERO, _ALLOCATION_FIELD, accrual_journal_ids

logger = logging.getLogger(__name__)

TOTAL_TYPE = 'total'
TOTAL_LABEL = 'إجمالي'
#: فرق تقريب العملة الذي يُحسم على أكبر بند — فوقه لا تُطابق البنودُ القيدَ فيُحفظ «إجمالي».
_ROUNDING_TOLERANCE = Decimal('0.05')
_KIND_FIELD = _ALLOCATION_FIELD  # clearance / shipment / local_shipment


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Q2)


def _base_rate(obj) -> Decimal:
    """سعر المستند إلى العملة الأساسية — 1 لمستندٍ بالعملة الأساسية."""
    currency = getattr(obj, 'currency', None)
    if currency is None or currency.IsBaseCurrency:
        return Decimal('1')
    rate = Decimal(str(obj.exchange_rate or 1))
    return rate if rate > 0 else Decimal('1')


def document_lines(kind: str, obj) -> list[dict]:
    """بنود المستند الآن بالعملة الأساسية {label, type, amount} — ما يرحّله استحقاقه.

    التخليص: بنوده بمرشّح قيد الاستحقاق نفسه (`accruals.clearance_accrual_lines`)؛ الشحن
    والإرسالية: مبلغٌ واحد (سعر الشحن × الحجم بالدولار، ومبلغ الإرسالية)."""
    from logistics.accruals import SHIPPING_COST_LINE_LABEL

    if kind == 'clearance':
        rate = _base_rate(obj)
        out = []
        for line in obj.lines.order_by('seq', 'pk'):
            amount = _money(Decimal(str(line.debit or 0)) - Decimal(str(line.credit or 0)))
            if amount <= 0 or line.description == SHIPPING_COST_LINE_LABEL:
                continue
            out.append({'label': (line.description or line.get_line_type_display())[:255],
                        'type': line.line_type or 'other', 'amount': _money(amount * rate)})
        return out
    if kind == 'freight':
        usd = _money(obj.total_shipping_cost_usd)
        rate = Decimal(str(obj.freight_exchange_rate or 0))
        return [{'label': f"شحن دولي — {usd}$ × {rate.normalize()}", 'type': 'freight',
                 'amount': _money(usd * rate)}]
    rate = _base_rate(obj)
    return [{'label': f"نقل محلي — {obj.display_label}"[:255], 'type': 'local',
             'amount': _money(Decimal(str(obj.amount or 0)) * rate)}]


def _fit(kind: str, lines: list[dict], total: Decimal) -> tuple[list[dict], bool]:
    """(بنود مجموعها = `total` بالقرش، مفصّلة؟). فرق تقريبٍ صغير على أكبر بند؛ وبنودٌ لا تطابق
    القيد (تغيّر المستند بعده) لا تُنسب إليه — سطر «إجمالي» بلا تفصيل."""
    lines = [dict(row) for row in lines if row['amount']]
    gap = total - sum((row['amount'] for row in lines), ZERO)
    if not lines or abs(gap) > _ROUNDING_TOLERANCE:
        return [{'label': TOTAL_LABEL, 'type': TOTAL_TYPE, 'amount': total}], False
    if gap:
        biggest = max(lines, key=lambda row: abs(row['amount']))
        biggest['amount'] += gap
    # الشحن والإرسالية مبلغٌ واحد — «بلا تفصيل» فيُفصَّل إن شاء المستخدم.
    return lines, kind == 'clearance'


def _stored(lines: list[dict]) -> list[dict]:
    return [{'label': row['label'], 'type': row['type'], 'amount': str(_money(row['amount']))}
            for row in lines]


def _party_credit(journal_ids) -> Decimal:
    """Σ(دائن − مدين) بالأساس لأسطر الطرف (الموسومة) في قيود السلسلة — المستحق بعدها."""
    from accounting.models import JournalLine

    if not journal_ids:
        return ZERO
    agg = JournalLine.objects.filter(
        journal_id__in=journal_ids, partner_id__isnull=False,
    ).aggregate(c=Sum('base_credit'), d=Sum('base_debit'))
    return _money(Decimal(str(agg['c'] or 0)) - Decimal(str(agg['d'] or 0)))


def _create(kind: str, obj, journal_id: int, role: str, total: Decimal, lines, detailed: bool, user):
    from logistics.models import AccrualLineSnapshot

    snapshot, created = AccrualLineSnapshot.objects.get_or_create(
        journal_id=journal_id,
        defaults={
            'tenant_id': obj.tenant_id, 'kind': kind, _KIND_FIELD[kind]: obj, 'role': role,
            'lines': _stored(lines), 'total': total, 'detailed': detailed,
            'created_by': user if getattr(user, 'is_authenticated', False) else None,
        },
    )
    if created:
        logger.info('accrual snapshot kind=%s doc=%s journal=%s role=%s total=%s detailed=%s',
                    kind, obj.pk, journal_id, role, total, detailed)
    return snapshot


def record_original_snapshot(kind: str, obj, journal, user=None):
    """لقطة قيد الاستحقاق الأوّل من بنود المستند لحظة ترحيله."""
    from logistics.models import AccrualLineSnapshot

    total = _party_credit([journal.pk])
    lines, detailed = _fit(kind, document_lines(kind, obj), total)
    return _create(kind, obj, journal.pk, AccrualLineSnapshot.ROLE_ORIGINAL, total, lines, detailed, user)


def ensure_snapshots(kind: str, obj, user=None, *, latest_from_document: bool = False) -> int:
    """يكمّل لقطات سلسلة المستند المرحّلة قبل الميزة — سطر «إجمالي» بمستحقّ كل قيد.

    `latest_from_document`: آخر قيدٍ في السلسلة يأخذ بنود المستند الآن إن طابقت مستحقّه —
    «لقطة قبل» التعديل (المستند لم يُعدَّل بعد). يُرجع عدد ما أُنشئ."""
    from logistics.models import AccrualLineSnapshot

    journals = accrual_journal_ids(kind, obj)
    have = set(AccrualLineSnapshot.objects.filter(journal_id__in=journals).values_list('journal_id', flat=True))
    created = 0
    for index, journal_id in enumerate(journals):
        if journal_id in have:
            continue
        total = _party_credit(journals[:index + 1])
        lines = [{'label': TOTAL_LABEL, 'type': TOTAL_TYPE, 'amount': total}]
        detailed = False
        if latest_from_document and index == len(journals) - 1:
            lines, detailed = _fit(kind, document_lines(kind, obj), total)
        role = AccrualLineSnapshot.ROLE_ORIGINAL if index == 0 else AccrualLineSnapshot.ROLE_ADJUSTMENT
        _create(kind, obj, journal_id, role, total, lines, detailed, user)
        created += 1
    return created


def record_adjustment_snapshot(kind: str, obj, journal, user=None):
    """لقطة «بعد» قيد التعديل: بنود المستند المعدَّل، ومجموعها المستحق بعد القيد."""
    from logistics.models import AccrualLineSnapshot

    journals = accrual_journal_ids(kind, obj)
    upto = journals[:journals.index(journal.pk) + 1] if journal.pk in journals else journals
    total = _party_credit(upto)
    lines, detailed = _fit(kind, document_lines(kind, obj), total)
    return _create(kind, obj, journal.pk, AccrualLineSnapshot.ROLE_ADJUSTMENT, total, lines, detailed, user)


# ── القراءة: السجل والفرق ─────────────────────────────────────────────────────

def _key(row) -> tuple:
    return (str(row.get('type') or ''), ' '.join(str(row.get('label') or '').split()))


def diff_rows(before: list[dict], after: list[dict]) -> list[dict]:
    """البند / قبل / بعد / الفرق بين لقطتين — المطابقة بالنوع والوصف، فالمكرّر يُجمع.

    `status`: new (لم يكن)، removed (حُذف)، changed، same. ترتيب «بعد» ثم المحذوف."""
    def totals(rows):
        out: dict = {}
        for row in rows:
            key = _key(row)
            entry = out.setdefault(key, {'label': row.get('label') or '', 'type': row.get('type') or '',
                                         'amount': ZERO})
            entry['amount'] += _money(row.get('amount'))
        return out

    old, new = totals(before), totals(after)
    out = []
    for key in [*new, *(k for k in old if k not in new)]:
        was, now = old.get(key), new.get(key)
        before_amount = was['amount'] if was else ZERO
        after_amount = now['amount'] if now else ZERO
        status = ('new' if was is None else 'removed' if now is None
                  else 'same' if before_amount == after_amount else 'changed')
        source = now or was
        out.append({'label': source['label'], 'type': source['type'],
                    'before': str(before_amount), 'after': str(after_amount),
                    'difference': str(after_amount - before_amount), 'status': status})
    return out


def _payload(snapshot, previous) -> dict:
    is_adjustment = previous is not None and snapshot.role != snapshot.ROLE_ORIGINAL
    journal = snapshot.journal
    return {
        'id': snapshot.pk, 'kind': snapshot.kind, 'role': snapshot.role,
        'journal_id': snapshot.journal_id,
        'date': journal.transaction_date.isoformat() if journal.transaction_date else None,
        'total': str(_money(snapshot.total)),
        'difference': str(_money(snapshot.total) - _money(previous.total)) if is_adjustment else None,
        'detailed': snapshot.detailed,
        'lines': snapshot.lines,
        'diff': diff_rows(previous.lines, snapshot.lines) if is_adjustment else None,
        'created_at': snapshot.created_at.isoformat() if snapshot.created_at else None,
    }


def _ordered(snapshots) -> list:
    """الأصلي أولاً ثم التعديلات بتاريخ قيدها ورقمه — ترتيب السلسلة."""
    return sorted(snapshots, key=lambda s: (s.role != s.ROLE_ORIGINAL,
                                            s.journal.transaction_date, s.journal_id))


def _document_key(snapshot) -> tuple:
    return (snapshot.kind, getattr(snapshot, f"{_KIND_FIELD[snapshot.kind]}_id"))


def history(kind: str, obj) -> list[dict]:
    """سجل الاستحقاق للمستند: الأصلي ثم كل تعديلٍ بفرقه عمّا قبله — قيود سلسلته الحيّة وحدها."""
    from logistics.models import AccrualLineSnapshot

    snapshots = _ordered(AccrualLineSnapshot.objects.filter(
        tenant_id=obj.tenant_id, kind=kind, **{_KIND_FIELD[kind]: obj},
        journal_id__in=accrual_journal_ids(kind, obj),
    ).select_related('journal'))
    return [_payload(s, snapshots[i - 1] if i else None) for i, s in enumerate(snapshots)]


def breakdowns_for_journals(tenant_id: int, journal_ids) -> dict:
    """{القيد: لقطته بفرقها} لقيود استحقاقٍ وتعديلٍ في كشف الطرف — مصدر سجل الاستحقاق نفسه.

    استعلامان بالدفعة: لقطات القيود، ثم كل لقطات مستنداتها (للّقطة السابقة)."""
    from logistics.models import AccrualLineSnapshot

    ids = {j for j in journal_ids if j}
    if not ids:
        return {}
    hits = list(AccrualLineSnapshot.objects.filter(tenant_id=tenant_id, journal_id__in=ids))
    if not hits:
        return {}
    wanted: dict[str, set] = {}
    for snapshot in hits:
        kind, doc_id = _document_key(snapshot)
        wanted.setdefault(kind, set()).add(doc_id)
    chains: dict[tuple, list] = {}
    for kind, doc_ids in wanted.items():
        for snapshot in AccrualLineSnapshot.objects.filter(
            tenant_id=tenant_id, kind=kind, **{f"{_KIND_FIELD[kind]}_id__in": doc_ids},
        ).select_related('journal'):
            chains.setdefault(_document_key(snapshot), []).append(snapshot)
    out = {}
    for chain in chains.values():
        chain = _ordered(chain)
        for index, snapshot in enumerate(chain):
            if snapshot.journal_id in ids:
                out[snapshot.journal_id] = _payload(snapshot, chain[index - 1] if index else None)
    return out


# ── التعبئة بأثرٍ رجعي ────────────────────────────────────────────────────────

def _clean_lines(raw) -> list[dict]:
    if not isinstance(raw, list) or not raw:
        raise ValidationError('أدخل بنداً واحداً على الأقل.')
    out = []
    for index, row in enumerate(raw, start=1):
        if not isinstance(row, dict):
            raise ValidationError(f'البند {index} غير صالح.')
        label = ' '.join(str(row.get('label') or '').split())[:255]
        if not label:
            raise ValidationError(f'البند {index}: أدخل وصفه.')
        try:
            amount = _money(row.get('amount'))
        except (InvalidOperation, ValueError, TypeError):
            raise ValidationError(f'البند «{label}»: المبلغ غير صالح.')
        if not amount:
            raise ValidationError(f'البند «{label}»: المبلغ صفر.')
        out.append({'label': label, 'type': (str(row.get('type') or 'other').strip() or 'other')[:32],
                    'amount': amount})
    return out


def fill_snapshot(snapshot, raw_lines, user=None):
    """يعبّئ بنود لقطةٍ بلا تفصيل — مجموعها = مبلغها بالقرش وإلا رفض. لا قيد يُكتب ولا يُعدَّل."""
    from accounting.services import create_audit_log

    if snapshot.detailed:
        raise ValidationError('بنود هذا الاستحقاق محفوظةٌ من ترحيله — لا تُستبدل.')
    lines = _clean_lines(raw_lines)
    total = sum((row['amount'] for row in lines), ZERO)
    if total != _money(snapshot.total):
        raise ValidationError(
            f'مجموع البنود {total} لا يساوي مبلغ الاستحقاق {_money(snapshot.total)}.')
    snapshot.lines = _stored(lines)
    snapshot.detailed = True
    snapshot.save(update_fields=['lines', 'detailed'])
    create_audit_log(
        tenant=snapshot.tenant, user=user if getattr(user, 'is_authenticated', False) else None,
        action='ACCRUAL_SNAPSHOT_FILLED', model_name='AccrualLineSnapshot', object_id=snapshot.pk,
        change_details=(f"بنود {snapshot.get_kind_display()} — قيد #{snapshot.journal_id}: "
                        + '، '.join(f"{row['label']} {row['amount']}" for row in lines))[:1000],
    )
    logger.info('accrual snapshot filled id=%s journal=%s lines=%s', snapshot.pk,
                snapshot.journal_id, len(lines))
    return snapshot
