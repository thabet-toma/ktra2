"""يعبّئ `amount_currency`/`currency_code` لأسطر ذمم الأطراف القائمة — أساس كشف الدولار.

قراءة فقط افتراضياً: يطبع ما سيُعبَّأ لكل نوع قيد وما يبقى بلا مصدرٍ دولاريّ واضح،
ورصيد كل طرفٍ بالدولار بعد التعبئة. `--apply` يكتب (ذرّياً) — ولا يمسّ مبلغاً ولا رصيداً
بالشيكل ولا سطراً معبّأً قبلاً. السطر بلا مصدر واضح يبقى NULL ويُذكر، لا يُخمَّن.

المصادر (أسطر الطرف المرحّلة فقط):
  قيدٌ بعملةٍ أجنبية بسعرٍ غير 1   ⇒ الاسميّ نفسه (مدين − دائن) بعملة القيد.
  LOGISTICS_PAYMENT(_UNPOST)       ⇒ دولار الدفعة (`amount`) بإشارة السطر — الأصل
                                     الخاطئ وعكسه والمصحَّح يتعادلون كما في الشيكل.
                                     والمحذوفة ليّناً منها (قيداها باقيان في الدفاتر).
    …ودفعةٌ حُذف صفّها نهائياً    ⇒ الاسميّ دولاراً — بشرط قيدٍ بعملة الأساس بسعر 1
                                     وصفقةِ أرشيف: المسمّاة في وصفه («صفقة: D-…»)، وإلّا
                                     فكلّ صفقات الطرف أرشيف. غير ذلك بلا مصدر.
  SHIPMENT_FREIGHT_ACCRUAL          ⇒ شيكل السطر ÷ `freight_exchange_rate` (ما رُحِّل
                                     فعلاً، لا تكلفة الشحن الحيّة إن عُدِّلت بعده).
  PURCHASE_INVOICE (دولية بصفقة)    ⇒ مبلغ الصفقة الدولاري، موزَّعاً على أسطر المورد.
  PURCHASE_RETURN (أصلها دولية)     ⇒ مبلغ الصفقة × شيكل السطر ÷ دائن المورد في الأصل.
  LOGISTICS_DEAL (الأرشيف)          ⇒ الرقم نفسه: دولارٌ مسجَّل بوحدة الشيكل بسعر 1.
  JOURNAL_REVERSAL                  ⇒ سالبُ سطر الأصل المقابل (الحساب والطرف والمبلغ).
  غيرها (تخليص، نقل محلي، سندات بالشيكل، يدوي، افتتاحي) ⇒ بلا مصدر — تقرير.

    python manage.py backfill_foreign_party_currency --tenant 1
    python manage.py backfill_foreign_party_currency --tenant 1 --partner 35
    python manage.py backfill_foreign_party_currency --tenant 1 --apply   # بعد نسخة احتياطية
"""
import logging
import re
from collections import defaultdict
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Sum

from accounting.services import JournalLine, set_lines_amount_currency
from logistics.models import LogisticsDeal, LogisticsPayment, LogisticsShipment, PurchaseInvoice
from logistics.payment_posting import archive_deal_ids
from tenants.models import Currency

logger = logging.getLogger(__name__)
Q2 = Decimal('0.01')
USD = 'USD'
PAYMENT_TYPES = ('LOGISTICS_PAYMENT', 'LOGISTICS_PAYMENT_UNPOST')
# «دفعة … | صفقة: D-0042 | المورد: …» — وصف قيد دفعة الصفقة (`logistics/views/deals.py`).
_DEAL_REF_RE = re.compile(r'صفقة:\s*([^|]+?)\s*(?:\||$)')


def _sign(line) -> int:
    net = Decimal(str(line['base_debit'] or 0)) - Decimal(str(line['base_credit'] or 0))
    return (net > 0) - (net < 0)


def _base_abs(line) -> Decimal:
    return abs(Decimal(str(line['base_debit'] or 0)) - Decimal(str(line['base_credit'] or 0)))


def _nominal(line) -> Decimal:
    return (Decimal(str(line['debit'] or 0)) - Decimal(str(line['credit'] or 0))).quantize(Q2)


def plan_backfill(tenant_id: int, partner_id: int | None = None) -> dict:
    """{'updates': {line_id: (amount, code)}, 'mapped': {type: n}, 'unmapped': {type: [lines]}}."""
    base_codes = set(Currency.objects.filter(IsBaseCurrency=True).values_list('Code', flat=True))
    qs = JournalLine.objects.filter(
        tenant_id=tenant_id, partner__isnull=False, journal__is_posted=True,
        amount_currency__isnull=True,
    )
    if partner_id:
        qs = qs.filter(partner_id=partner_id)
    lines = list(qs.order_by('journal__transaction_date', 'journal_id', 'id').values(
        'id', 'journal_id', 'account_id', 'partner_id', 'debit', 'credit', 'base_debit',
        'base_credit', 'journal__reference_type', 'journal__reference_id',
        'journal__exchange_rate', 'journal__currency__Code', 'journal__transaction_date',
        'journal__description',
    ))

    def ids_of(ref_type):
        return {l['journal__reference_id'] for l in lines
                if l['journal__reference_type'] in ref_type and l['journal__reference_id']}

    # all_objects: الدفعة المحذوفة ليّناً قيداها باقيان في الدفاتر، ودولارها في صفّها.
    payments = dict(LogisticsPayment.all_objects.filter(
        tenant_id=tenant_id, id__in=ids_of(PAYMENT_TYPES),
    ).values_list('id', 'amount'))
    # دفعةٌ لا صفّ لها أصلاً (حُذفت نهائياً): صفقات طرفها {المرجع: أرشيف؟}.
    orphan_partners = {l['partner_id'] for l in lines if l['journal__reference_type'] in PAYMENT_TYPES
                       and l['journal__reference_id'] not in payments}
    orphan_deals: dict[int, dict[str, bool]] = defaultdict(dict)
    if orphan_partners:
        deals = list(LogisticsDeal.all_objects.filter(
            tenant_id=tenant_id, partner_id__in=orphan_partners,
        ).values_list('id', 'partner_id', 'ref_number'))
        archive = archive_deal_ids(tenant_id, [d[0] for d in deals])
        for deal_id, pid, ref in deals:
            orphan_deals[pid][(ref or '').strip()] = deal_id in archive

    def on_archive_deal(line) -> bool:
        deals = orphan_deals.get(line['partner_id']) or {}
        named = _DEAL_REF_RE.search(line['journal__description'] or '')
        if named:
            return deals.get(named.group(1).strip()) is True
        return bool(deals) and all(deals.values())
    freight_rates = dict(LogisticsShipment.all_objects.filter(
        tenant_id=tenant_id, id__in=ids_of(('SHIPMENT_FREIGHT_ACCRUAL',)),
    ).values_list('id', 'freight_exchange_rate'))
    invoices = {
        inv.id: inv for inv in PurchaseInvoice.objects.filter(
            tenant_id=tenant_id, id__in=ids_of(('PURCHASE_INVOICE', 'PURCHASE_RETURN')),
        ).select_related('deal', 'original_invoice__deal')
    }
    # دائن المورد في قيد الفاتورة الدولية الأصل — مقام نسبة المرتجع.
    supplier_credit = {}
    for inv in invoices.values():
        source = inv.original_invoice if inv.is_return else inv
        if source is None or source.journal_id is None or source.id in supplier_credit:
            continue
        supplier_credit[source.id] = JournalLine.objects.filter(
            tenant_id=tenant_id, journal_id=source.journal_id, partner_id=source.partner_id,
            base_credit__gt=0,
        ).aggregate(s=Sum('base_credit'))['s'] or Decimal('0')

    updates: dict[int, tuple[Decimal, str]] = {}
    mapped: dict[str, int] = defaultdict(int)
    unmapped: dict[str, list] = defaultdict(list)
    reversals = []

    def put(line, amount, code, kind):
        amount = Decimal(str(amount)).quantize(Q2)
        if amount == 0 or (amount > 0) - (amount < 0) != _sign(line):
            unmapped[f'{kind} (إشارة/صفر)'].append(line)
            return
        updates[line['id']] = (amount, code)
        mapped[kind] += 1

    for line in lines:
        ref_type = line['journal__reference_type'] or 'بلا نوع'
        ref_id = line['journal__reference_id']
        code = (line['journal__currency__Code'] or '').upper()
        rate = Decimal(str(line['journal__exchange_rate'] or 1))
        if code and code not in base_codes and rate != 1:
            put(line, _nominal(line), code[:3], f'قيد بعملة {code}')
        elif ref_type in PAYMENT_TYPES and payments.get(ref_id):
            put(line, _sign(line) * Decimal(str(payments[ref_id])), USD, ref_type)
        elif (ref_type in PAYMENT_TYPES and ref_id not in payments
                and (not code or code in base_codes) and rate == 1 and on_archive_deal(line)):
            put(line, _nominal(line), USD, f'{ref_type} (محذوفة نهائياً، صفقة أرشيف)')
        elif ref_type == 'SHIPMENT_FREIGHT_ACCRUAL' and (freight_rates.get(ref_id) or 0) > 0:
            put(line, _sign(line) * _base_abs(line) / Decimal(str(freight_rates[ref_id])), USD, ref_type)
        elif ref_type in ('PURCHASE_INVOICE', 'PURCHASE_RETURN') and ref_id in invoices:
            inv = invoices[ref_id]
            source = inv.original_invoice if inv.is_return else inv
            deal = getattr(source, 'deal', None) if source is not None else None
            credit = supplier_credit.get(getattr(source, 'id', None)) or Decimal('0')
            if (source is None or source.invoice_type != PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL
                    or deal is None or not deal.total_amount or credit <= 0
                    or line['partner_id'] != source.partner_id):
                unmapped[ref_type].append(line)
                continue
            usd = Decimal(str(deal.total_amount)) * _base_abs(line) / credit
            put(line, _sign(line) * usd, USD, f'{ref_type} دولية')
        elif ref_type == 'LOGISTICS_DEAL':
            put(line, _nominal(line), USD, ref_type)
        elif ref_type == 'JOURNAL_REVERSAL' and ref_id:
            reversals.append(line)
        else:
            unmapped[ref_type].append(line)

    if reversals:
        originals = defaultdict(list)
        for row in JournalLine.objects.filter(
            tenant_id=tenant_id, journal_id__in={l['journal__reference_id'] for l in reversals},
        ).values('id', 'journal_id', 'account_id', 'partner_id', 'base_debit', 'base_credit',
                 'amount_currency', 'currency_code'):
            if row['amount_currency'] is None and row['id'] in updates:
                row['amount_currency'], row['currency_code'] = updates[row['id']]
            originals[row['journal_id']].append(row)
        for line in reversals:
            match = next((
                o for o in originals.get(line['journal__reference_id'], [])
                if o['account_id'] == line['account_id'] and o['partner_id'] == line['partner_id']
                and o['amount_currency'] is not None and _base_abs(o) == _base_abs(line)
                and _sign(o) == -_sign(line)
            ), None)
            if match is None:
                unmapped['JOURNAL_REVERSAL'].append(line)
            else:
                put(line, -Decimal(str(match['amount_currency'])), match['currency_code'],
                    'JOURNAL_REVERSAL')

    # «بلا مصدر» يعني شيئاً لطرفٍ له نشاطٌ دولاريّ وحده؛ أسطر العملاء والموردين
    # المحليين بالشيكل أصلاً — تُعدّ ولا تُسرد.
    foreign_partners = {l['partner_id'] for l in lines if l['id'] in updates} | set(
        JournalLine.objects.filter(
            tenant_id=tenant_id, amount_currency__isnull=False,
            partner_id__in={l['partner_id'] for l in lines},
        ).values_list('partner_id', flat=True).distinct())
    local_lines = 0
    for kind in list(unmapped):
        kept = [l for l in unmapped[kind] if l['partner_id'] in foreign_partners]
        local_lines += len(unmapped[kind]) - len(kept)
        if kept:
            unmapped[kind] = kept
        else:
            del unmapped[kind]
    return {
        'updates': updates, 'mapped': dict(mapped), 'unmapped': dict(unmapped),
        'lines': [l for l in lines if l['partner_id'] in foreign_partners],
        'local_lines': local_lines,
    }


class Command(BaseCommand):
    help = 'تعبئة المبلغ الدولاري لأسطر ذمم الأطراف القائمة (قراءة أولاً، ثم --apply).'

    def add_arguments(self, parser):
        parser.add_argument('--tenant', type=int, required=True)
        parser.add_argument('--partner', type=int, default=None, help='طرفٌ واحد للمراجعة')
        parser.add_argument('--apply', action='store_true', help='اكتب — بعد نسخة احتياطية')

    def handle(self, *args, **opts):
        tenant_id, partner_id = opts['tenant'], opts['partner']
        if tenant_id <= 0:
            raise CommandError('--tenant مطلوب.')
        plan = plan_backfill(tenant_id, partner_id)
        updates = plan['updates']
        out = self.stdout.write

        out(f'أسطر ذمم أطرافٍ لها نشاطٌ دولاريّ بلا مبلغ أجنبي: {len(plan["lines"])} — '
            f'تُعبَّأ: {len(updates)} · أسطر أطرافٍ بالشيكل وحده (لا تُمسّ): {plan["local_lines"]}')
        for kind, n in sorted(plan['mapped'].items()):
            out(f'  ✓ {kind}: {n}')
        for kind, rows in sorted(plan['unmapped'].items()):
            base = sum((Decimal(str(r['base_debit'] or 0)) - Decimal(str(r['base_credit'] or 0))
                        for r in rows), Decimal('0'))
            out(f'  ✗ {kind}: {len(rows)} سطر بلا مصدر دولاري (صافي بالشيكل {base.quantize(Q2)})')

        # رصيد كل طرفٍ بالدولار بعد التعبئة (مدين − دائن؛ سالبٌ = له).
        by_partner = defaultdict(lambda: [Decimal('0'), 0])
        for line in plan['lines']:
            if line['id'] in updates:
                by_partner[line['partner_id']][0] += updates[line['id']][0]
            else:
                by_partner[line['partner_id']][1] += 1
        for row in JournalLine.objects.filter(
            tenant_id=tenant_id, journal__is_posted=True, amount_currency__isnull=False,
            partner_id__in=list(by_partner),
        ).values('partner_id').annotate(s=Sum('amount_currency')):
            by_partner[row['partner_id']][0] += row['s'] or Decimal('0')
        if by_partner:
            out('الرصيد بالدولار بعد التعبئة (مدين − دائن؛ سالبٌ = له) · أسطر بلا مصدر:')
        for pid, (usd, missing) in sorted(by_partner.items()):
            out(f'  طرف #{pid}: {usd.quantize(Q2)} · {missing}')

        if not opts['apply']:
            out(self.style.WARNING('قراءة فقط — لم يُكتب شيء. أعد بـ--apply بعد نسخة احتياطية.'))
            return
        written = set_lines_amount_currency(tenant_id, updates)
        logger.info('backfill_foreign_party_currency tenant=%s partner=%s written=%s unmapped=%s',
                    tenant_id, partner_id, written,
                    {k: len(v) for k, v in plan['unmapped'].items()})
        out(self.style.SUCCESS(f'كُتب {written} سطراً.'))
