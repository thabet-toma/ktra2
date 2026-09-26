"""«تعديل الاستحقاق» — قيد فرقٍ بدل حذف القيد (قرار المالك 2026-09-26).

كان زرّ «تراجع عن الاستحقاق» يحذف القيد ثم يُرحَّل من جديد، فيضيع الأثر ويتغيّر رقم
القيد وتاريخه. الآن يبقى قيد الاستحقاق الأصلي كما هو، ويُرحَّل قيدٌ ثانٍ بالفرق بين
ما رُحِّل (الأصل + تعديلاته السابقة) وما يجب أن يكون من المستند بعد تعديله:

    الهدف  = أسطر الاستحقاق من المستند الآن (`accruals.*_accrual_lines` — مصدرُ الترحيل نفسه)
    الحالي = صافي أسطر قيود الاستحقاق المرحّلة بالعملة الأساسية لكل (حساب، طرف)
    القيد  = الهدف − الحالي، بمرجع `ACCRUAL_ADJUST_TYPE[kind]` على المستند نفسه

ويتبعه تلقائياً تعديل تكلفة البضاعة (`landed_revaluation`): الفواتير المرحّلة بقيد
تسوية، والمسودات بإعادة البناء. كلّه ذرّيٌّ في معاملةٍ واحدة. و`preview=True` يحسب
الأثر كاملاً ثم يتراجع عنه — بلا قيدٍ مرحّلٍ ولا رقمٍ مستهلَك.

المرجع: Odoo يعدّل الاستحقاق بقيدٍ لا بحذفه، ويوزّع فرق تكلفة الاستيراد على المخزون
الباقي و«ت.ب.م» للمبيع (landed costs). زدنا عليه: الفرق يُقاس على **كلّ** قيود المستند
فتعديلٌ ثانٍ وثالث يبقى صحيحاً، ومعاينةٌ مطابقة لما سيُرحَّل حرفياً.
"""
from __future__ import annotations

import logging
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from logistics.domain.party_accruals import (
    ACCRUAL_ADJUST_TYPE, Q2, ZERO, _label, accrual_journal_ids, accrual_status, shipment_id_of,
)

logger = logging.getLogger(__name__)

NO_CHANGE_MESSAGE = 'لا فرق — المستحق بعد التعديل مساوٍ لما رُحِّل.'


class _PreviewRollback(Exception):
    """يُرمى داخل المعاملة لإلغاء كل ما كُتب في المعاينة."""


def _money(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Q2)


def _target_lines(kind: str, obj, freight_rate=None):
    """(أسطر الهدف بعملة المستند، سعر المستند، رمز عملة أجنبية أو None)."""
    from logistics.accruals import (
        _as_decimal, clearance_accrual_lines, freight_accrual_lines, local_shipment_accrual_lines,
    )

    if kind == 'clearance':
        lines, _total = clearance_accrual_lines(obj)
        currency, rate = obj.currency, _as_decimal(obj.exchange_rate, '1')
    elif kind == 'local':
        lines, _amount = local_shipment_accrual_lines(obj)
        currency, rate = obj.currency, _as_decimal(obj.exchange_rate, '1')
    else:
        lines, _ils, _usd, _rate = freight_accrual_lines(obj, freight_rate)
        currency, rate = None, Decimal('1')
    rate = rate if rate > 0 else Decimal('1')
    foreign = None
    if currency is not None and not currency.IsBaseCurrency and rate != 1:
        foreign = currency.Code.upper()[:3]
    return lines, rate, foreign


def _current_totals(journal_ids) -> dict:
    """{(حساب، طرف): [صافي الأساس (مدين − دائن)، صافي الأجنبي، رمزه]} لقيود المستند."""
    from accounting.api import journal_lines_net_by_account_partner

    return {
        key: [_money(base), _money(foreign), code]
        for key, (base, foreign, code) in journal_lines_net_by_account_partner(journal_ids).items()
    }


def _target_totals(lines, rate: Decimal, foreign) -> dict:
    out: dict = {}
    for row in lines:
        key = (row['account'], row.get('partner'))
        nominal = Decimal(str(row.get('debit') or 0)) - Decimal(str(row.get('credit') or 0))
        entry = out.setdefault(key, [ZERO, ZERO, None])
        entry[0] += (nominal * rate).quantize(Q2)
        if row.get('amount_currency') is not None:
            entry[1] += _money(row['amount_currency'])
            entry[2] = (row.get('currency_code') or '').upper()[:3] or None
        elif foreign:
            entry[1] += nominal.quantize(Q2)
            entry[2] = foreign
    return out


def _line(account, partner, base: Decimal, currency_amount: Decimal, code, description) -> dict:
    row = {
        'account': account, 'partner': partner,
        'debit': base if base > 0 else ZERO, 'credit': -base if base < 0 else ZERO,
        'description': description[:500],
    }
    if code and currency_amount:
        row.update(amount_currency=currency_amount, currency_code=code)
    return row


def difference_lines(current: dict, target: dict, description: str) -> list[dict]:
    """أسطر قيد الفرق بالعملة الأساسية.

    سطرٌ واحد لكل (حساب، طرف) تغيّر — إلا حين يخالف فرقُ الأجنبي فرقَ الأساس إشارةً
    (دولارٌ نزل وسعرٌ صعد): عندها عكسُ الحالي وإثباتُ الهدف لذلك المفتاح وحده، فيبقى
    كشف الطرف بالدولار صادقاً دون سطرٍ بإشارتين متعاكستين.
    """
    lines = []
    for key in sorted(set(current) | set(target), key=lambda k: (k[1] is not None, k[0], k[1] or 0)):
        cur_base, cur_fx, cur_code = current.get(key, [ZERO, ZERO, None])
        tgt_base, tgt_fx, tgt_code = target.get(key, [ZERO, ZERO, None])
        code = tgt_code or cur_code
        base, fx = tgt_base - cur_base, tgt_fx - cur_fx
        if not base and not fx:
            continue
        account, partner = key
        signs_agree = not code or not fx or (base > 0) == (fx > 0)
        if base and signs_agree:
            lines.append(_line(account, partner, base, fx, code, description))
            continue
        if cur_base:
            lines.append(_line(account, partner, -cur_base, -cur_fx, code, f"عكس — {description}"))
        if tgt_base:
            lines.append(_line(account, partner, tgt_base, tgt_fx, code, description))
    imbalance = sum((r['debit'] - r['credit'] for r in lines), ZERO)
    if imbalance and lines:
        if abs(imbalance) > Decimal('0.05'):
            raise ValidationError(f'قيد تعديل الاستحقاق غير متوازن بفرق {imbalance}.')
        # كسور تحويل العملة على أكبر سطرٍ بلا طرف.
        free = [r for r in lines if not r['partner']] or lines
        biggest = max(free, key=lambda r: r['debit'] + r['credit'])
        net = biggest['debit'] - biggest['credit'] - imbalance
        biggest['debit'], biggest['credit'] = (net, ZERO) if net > 0 else (ZERO, -net)
    return [r for r in lines if r['debit'] or r['credit']]


def adjust_accrual(kind: str, obj, *, apply_changes, adjust_date=None, freight_rate=None,
                   user=None, preview: bool = False) -> dict:
    """يعدّل مستند الاستحقاق (`apply_changes()`) ويرحّل قيد الفرق وتعديل تكلفة البضاعة.

    `obj` مقفلٌ (`select_for_update`) من المستدعي، و`apply_changes` تكتب تعديله. يُرجع
    ملخّصاً للواجهة؛ مع `preview=True` لا يبقى شيءٌ مكتوباً.
    """
    from accounting.services import post_journal
    from logistics.accruals import assert_shipment_alive
    from logistics.domain import landed_revaluation
    from logistics.landed_cost import recalculate_landed_for_shipment
    from tenants.models import Currency

    adjust_date = adjust_date or timezone.localdate()
    result: dict = {}
    try:
        with transaction.atomic():
            journals = accrual_journal_ids(kind, obj)
            if not journals:
                raise ValidationError('الاستحقاق غير مرحّل — أثبته أولاً، ثم عدّله.')
            ship = obj if kind == 'freight' else getattr(obj, 'shipment', None)
            assert_shipment_alive(ship)
            before = accrual_status(kind, obj)
            shipment_id = shipment_id_of(kind, obj)
            snapshots = landed_revaluation.capture(obj.tenant_id, shipment_id)

            apply_changes()

            lines, rate, foreign = _target_lines(kind, obj, freight_rate)
            label = _label(kind, obj)
            adj_lines = difference_lines(
                _current_totals(journals), _target_totals(lines, rate, foreign),
                f"تعديل استحقاق {label}")
            journal = None
            if adj_lines and not preview:
                base_currency = (Currency.objects.filter(IsBaseCurrency=True).first()
                                 or Currency.objects.filter(Code__iexact='ILS').first())
                journal = post_journal(
                    tenant_id=obj.tenant_id, transaction_date=adjust_date,
                    reference_type=ACCRUAL_ADJUST_TYPE[kind], reference_id=obj.pk,
                    description=f"تعديل استحقاق {label}"[:500], lines_data=adj_lines,
                    currency=base_currency, exchange_rate=Decimal('1'), user=user,
                    idempotent=False,
                )
            if preview:
                revaluations = [p.summary() for p in landed_revaluation.plan(snapshots)]
            else:
                revaluations = [p.summary() for p in landed_revaluation.apply(
                    snapshots, adjust_date=adjust_date, user=user)]
            if not adj_lines and not revaluations:
                raise ValidationError(NO_CHANGE_MESSAGE)
            drafts = 0
            if shipment_id and not preview:
                drafts = recalculate_landed_for_shipment(
                    tenant=obj.tenant, shipment_id=shipment_id)['updated']
            party_id = next((r['partner'] for r in lines if r.get('partner')), None)
            due_after = before['due'] + sum(
                (r['credit'] - r['debit'] for r in adj_lines if r['partner'] == party_id), ZERO)
            paid = before['paid'] + before['allocated']
            result = {
                'kind': kind, 'id': obj.pk, 'label': label, 'preview': preview,
                'journal_id': journal.pk if journal else None,
                'due_before': str(before['due']), 'due_after': str(due_after),
                'difference': str(due_after - before['due']),
                'paid': str(paid),
                'surplus_after': str(min(max(paid - due_after, ZERO),
                                         max(before['due_original'] - due_after, ZERO))),
                'lines': [
                    {'account': r['account'], 'partner': r['partner'], 'debit': str(r['debit']),
                     'credit': str(r['credit']), 'description': r['description']}
                    for r in adj_lines
                ],
                'revaluations': revaluations,
                'drafts_updated': drafts,
            }
            if preview:
                raise _PreviewRollback()
    except _PreviewRollback:
        return result
    logger.info(
        'accrual adjusted kind=%s doc=%s journal=%s due %s→%s revaluations=%s',
        kind, obj.pk, result['journal_id'], result['due_before'], result['due_after'],
        [r['invoice_number'] for r in result['revaluations']],
    )
    return result


def request_options(data) -> tuple:
    """(معاينة؟، تاريخ قيد الفرق) من جسم الطلب — التاريخ اليوم افتراضاً."""
    from django.utils.dateparse import parse_date

    preview = str(data.get('preview', '')).strip().lower() in ('1', 'true', 'yes', 'on')
    raw = str(data.get('date') or '').strip()
    adjust_date = None
    if raw:
        adjust_date = parse_date(raw[:10])
        if adjust_date is None:
            raise ValidationError('تاريخ قيد التعديل غير صالح.')
    return preview, adjust_date


def error_text(exc) -> str:
    """نصّ خطأٍ مقروء من ValidationError جانغو أو DRF أو AccrualSkipped."""
    messages = getattr(exc, 'messages', None)
    if messages:
        return '؛ '.join(str(m) for m in messages)
    detail = getattr(exc, 'detail', None)
    if isinstance(detail, dict):
        return '؛ '.join(
            f"{v[0] if isinstance(v, list) and v else v}" for v in detail.values())
    if isinstance(detail, list):
        return '؛ '.join(str(v) for v in detail)
    return str(detail or exc)
