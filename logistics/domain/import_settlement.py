"""تسوية الفاتورة الدولية: تكاليفها الأربع مقابل دفعاتها الأربع (3ب).

الفاتورة الدولية تحمل أربع تكاليف ولكلٍّ دائنُها ودفعاتُه:
  المورد   ← بضاعة الصفقة: دفعات الصفقة المرحّلة + سندات الفاتورة نفسها
  الشحن    ← حصّتها من شحن الشحنة: دفعات الوكيل المرحّلة للشحنة
  التخليص  ← حصّتها من التخليص: دفعات التخليص المرحّلة
  المحلي   ← حصّتها من النقل: دفعات الإرساليات المرحّلة (ودفعات الناقل على التخليص)
سندات الفاتورة وحدها لا ترى إلا المورد، فكانت الفاتورة «غير مدفوعة» وكلّ ما
عليها مسدَّد.

الشحن والتخليص والنقل مشتركة بين صفقات الشحنة: دفعاتها تُوزَّع بالأوزان نفسها
التي وُزّعت بها تكلفتها في `landed_cost.build_purchase_invoice_row` — الحجم
للشحن، والقيمة للتخليص، ومصدرُ النقل يحدّد وزنه — وعبر
`distribute_by_weights` (أكبر باقٍ) على **كل** صفقات الشحنة، فمجموع ما يُنسب
من دفعةٍ لفواتيرها = الدفعة مرّةً واحدة بالضبط، ولا تأخذ الفاتورة نصيب صفقةٍ
لم تُفوتَر بعد.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional

from django.db.models import Q

from logistics import landed_cost as lc
from logistics.domain.party_accruals import allocated_base
from logistics.models import (
    LocalShipment,
    LocalShipmentPayment,
    LogisticsClearance,
    LogisticsShipmentDeal,
    PurchaseInvoice,
)

logger = logging.getLogger(__name__)

Q2 = Decimal('0.01')
COMPONENTS = ('supplier', 'freight', 'clearance', 'local')


def _is_posted(p) -> bool:
    return bool(getattr(p, 'is_posted', False))


def _shipment_portion(total: Decimal, weights: List[Decimal], index: int) -> Decimal:
    if total <= 0 or index < 0:
        return Decimal('0.00')
    return lc.distribute_by_weights(total, weights)[index]


def import_invoice_payment_breakdown(invoice: PurchaseInvoice) -> Optional[Dict[str, Any]]:
    """{supplier|freight|clearance|local: {cost, paid, remaining}} + `cost_rows` + الإجماليات والحالة.

    None لغير الدولية أو لفاتورةٍ لم تكتمل مستنداتها (بلا تخليص) — يعرض المستدعي
    ملخّص السندات المعتاد. المدفوع لكل مكوّن يُسقَف بتكلفته في الإجمالي، فزيادةٌ
    في الشحن لا تُغطّي بضاعةً غير مدفوعة؛ والتفصيل يعرض المدفوع الفعلي.

    **«إجمالي التكلفة» رقمٌ واحد** (قرار المالك): `payable_total` = مجموع `cost_rows`
    (`_cost_rows` — المكوّنات الأربع + عمولات التحويل + الرسوم المرسملة + الضريبة)،
    والمدفوع والحالة من السطور نفسها. كان مجموعَ المكوّنات الأربع وحدها، فغابت عنه
    العمولة التي دخلت القيد (INV-0023: المربّع 11,952.50 والقيد 12,088.58).
    """
    if (
        invoice.invoice_type != PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL
        or invoice.is_return or not invoice.deal_id or not invoice.shipment_id
    ):
        return None
    shares = lc.import_invoice_cost_shares(invoice)
    if shares is None:
        return None

    from logistics.services import (
        import_deal_payments_ap_debit,
        import_invoice_tax_payable,
        purchase_invoice_fees_total,
        purchase_invoice_recorded_paid,
    )

    shipment = invoice.shipment
    clearance = invoice.clearance or LogisticsClearance.objects.filter(
        tenant_id=invoice.tenant_id, shipment_id=invoice.shipment_id,
    ).first()
    rate = lc._d(invoice.import_shipment_remaining_rate, '3.6') or Decimal('3.6')

    links = list(
        LogisticsShipmentDeal.objects.filter(shipment=shipment)
        .select_related('deal').order_by('id')
    )
    deal_ids = [link.deal_id for link in links]
    index = deal_ids.index(invoice.deal_id) if invoice.deal_id in deal_ids else -1
    value_w = [lc.deal_share_on_shipment(link.deal, shipment) for link in links]
    volume_w = [lc.deal_volume_share_on_shipment(link.deal, shipment) for link in links]
    local_source = shares['local_source']
    local_w = volume_w if local_source == 'local_shipment' else value_w

    # الشحن الدولي: دفعات الوكيل المرحّلة غير المربوطة بصفقة.
    _usd, freight_paid_total = lc.sum_settled_usd_ils(
        shipment.agent_payments.filter(deal__isnull=True), is_paid=_is_posted,
    )
    clearance_paid_total = Decimal('0')
    local_paid_total = Decimal('0')
    if clearance is not None:
        clearance_paid_total = lc.sum_clearance_payments_ils(clearance, rate, posted_only=True)
        if local_source == 'clearance_lines':
            local_paid_total += lc.sum_clearance_payments_ils(
                clearance, rate, posted_only=True, carrier=True)
    if local_source == 'local_shipment':
        # فلتر حوض النقل نفسه (`domain.inland.transport_pool_ils`).
        pool = LocalShipment.objects.filter(
            Q(shipment=shipment) | (Q(clearance=clearance) if clearance else Q()),
            capitalize_to_inventory=True,
        ).exclude(status='cancelled')
        for pay in LocalShipmentPayment.objects.filter(
            local_shipment__in=pool, is_posted=True,
        ):
            local_paid_total += (
                lc._d(pay.amount) * (lc._d(pay.exchange_rate, '1') or Decimal('1'))
            ).quantize(Q2)
        local_paid_total += allocated_base('local', list(pool))
    # سندات صرفٍ وُزِّعت على هذه المستحقّات (`party_accruals`) مدفوعٌ لها أيضاً —
    # بلا هذا يبقى تخليصٌ سدّده سندُ المخلّص «غير مدفوع» في 3ب.
    freight_paid_total += allocated_base('freight', [shipment])
    if clearance is not None:
        clearance_paid_total += allocated_base('clearance', [clearance])

    fees = purchase_invoice_fees_total(invoice)
    grand = lc._d(invoice.grand_total).quantize(Q2)
    costs = {
        'freight': shares['freight'],
        'clearance': shares['clearance'],
        'local': shares['local'],
    }
    # ضريبتها على «ضريبة الاستيراد المستحقة» لا على المورد (`import_invoice_tax_payable`).
    costs['supplier'] = (
        grand + fees - import_invoice_tax_payable(invoice) - sum(costs.values(), Decimal('0'))
    ).quantize(Q2)
    paid = {
        # دفعات الصفقة + سندات الفاتورة نفسها — مصدران منفصلان في الدفاتر فلا ازدواج.
        'supplier': import_deal_payments_ap_debit(invoice) + purchase_invoice_recorded_paid(invoice),
        'freight': _shipment_portion(freight_paid_total, volume_w, index),
        'clearance': _shipment_portion(clearance_paid_total, value_w, index),
        'local': _shipment_portion(local_paid_total, local_w, index),
    }

    # حصص التكلفة تُقرَّب كلٌّ على حدة (نسبة بأربع خانات) والدفعة تُوزَّع بأكبر
    # باقٍ — فقد يفترقان بأغورة. مكوّنٌ سُدِّد حوضُه في الشحنة كلّه مسدَّدٌ في
    # كل فاتورة، لا «جزئية» بأغورة.
    pool_paid_total = {
        'freight': (freight_paid_total, shares['freight_pool']),
        'clearance': (clearance_paid_total, shares['clearance_pool']),
        'local': (local_paid_total, shares['local_pool']),
    }
    components: Dict[str, Dict[str, Decimal]] = {}
    for key in COMPONENTS:
        cost = max(costs[key], Decimal('0.00'))
        got = paid[key].quantize(Q2)
        if key in pool_paid_total:
            total_paid, pool = pool_paid_total[key]
            if pool > 0 and total_paid >= pool:
                got = max(got, cost)
        components[key] = {
            'cost': cost,
            'paid': got,
            'remaining': max(cost - got, Decimal('0.00')),
        }
    rows = _cost_rows(invoice, components)
    total_cost = sum((r['cost'] for r in rows), Decimal('0.00')).quantize(Q2)
    covered = sum((r['paid'] for r in rows), Decimal('0.00')).quantize(Q2)

    from core.payments import document_payment_summary
    result = document_payment_summary(total_cost, covered)
    result.update({'payable_total': total_cost, 'components': components, 'cost_rows': rows})
    return result


def import_invoice_display_payment(invoice: PurchaseInvoice) -> Optional[Dict[str, Any]]:
    """ما تعرضه الشاشات مدفوعاً ومتبقّياً وحالةً للفاتورة الدولية — مصدرٌ واحد.

    `import_invoice_payment_breakdown` مخزَّنةً على الكائن: التفصيل والتأخّر ورصيد
    المورد وفلتر القائمة يقرؤونها في الطلب نفسه بلا إعادة حساب. None لغير الدولية
    أو لما لم تكتمل مستنداتها — فيقرأ المستدعي ملخّص المورد
    (`purchase_invoice_payment_summary`). عطبٌ في الحساب لا يُسقط الشاشة: يُسجَّل
    ويعود None.
    """
    if invoice.invoice_type != PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL or invoice.is_return:
        return None
    if hasattr(invoice, '_import_display_payment'):
        return invoice._import_display_payment
    try:
        data = import_invoice_payment_breakdown(invoice)
    except Exception:
        logger.exception('import payment breakdown failed invoice=%s', invoice.pk)
        data = None
    invoice._import_display_payment = data
    return data


def _fee_paid_by_account(invoice, fees) -> Dict[int, Decimal]:
    """{fee.pk: مدفوع} لرسوم الفاتورة المرحّلة ذات الطرف الدائن — FIFO على حساب الرسم.

    حساب الرسم (ذمّةٌ باسمه أو حساب جهته) مشتركٌ بين فواتير: سندات الصرف عليه تُسدّد
    أقدم دائنٍ أولاً (تاريخ القيد ثم رقمه)، فمدفوعُ هذه الفاتورة ما وصلها من مجموع
    المدين (`_journal_credit_paid`)، ويُوزَّع على رسومها على الحساب نفسه بنسبة مبالغها.
    """
    out: Dict[int, Decimal] = {}
    if not invoice.is_posted or not invoice.journal_id:
        return out
    groups: Dict[tuple, List] = {}
    for fee in fees:
        if fee.credit_partner_id:
            key = (fee.credit_partner.linked_account_id, fee.credit_partner_id)
        elif fee.credit_account_id:
            key = (fee.credit_account_id, None)
        else:
            continue
        groups.setdefault(key, []).append(fee)
    for (account_id, partner_id), group in groups.items():
        mine = _journal_credit_paid(invoice, account_id, partner_id)
        total = sum((Decimal(str(f.amount or 0)) for f in group), Decimal('0'))
        for fee in group:
            amount = Decimal(str(fee.amount or 0))
            out[fee.pk] = ((mine * amount / total) if total > 0 else Decimal('0')).quantize(Q2)
    return out


def _journal_credit_paid(invoice, account_id, partner_id=None) -> Decimal:
    """ما سُدِّد من دائن قيد الفاتورة على حسابٍ مشترك بين فواتير — FIFO: سندات الصرف عليه
    تُسدّد أقدم دائنٍ أولاً (تاريخ القيد ثم رقمه)، فمدفوعها ما وصلها من مجموع المدين."""
    from django.db.models import Sum

    from accounting.services import JournalLine

    lines = JournalLine.objects.filter(
        tenant_id=invoice.tenant_id, account_id=account_id, journal__is_posted=True,
    )
    if partner_id:
        lines = lines.filter(partner_id=partner_id)
    debit_total = Decimal(str(lines.aggregate(d=Sum('base_debit'))['d'] or 0))
    mine = Decimal('0')
    for journal_id, credit in (
        lines.filter(base_credit__gt=0)
        .order_by('journal__transaction_date', 'journal_id', 'id')
        .values_list('journal_id', 'base_credit')
    ):
        take = min(debit_total, Decimal(str(credit)))
        debit_total -= take
        if journal_id == invoice.journal_id:
            mine += take
    return mine


def _cost_rows(invoice: PurchaseInvoice, components: Dict[str, Dict[str, Decimal]]) -> List[Dict[str, Any]]:
    """سطور «إجمالي التكلفة»: المورد، الشحن، التخليص، النقل، عمولات التحويل، كل رسمٍ
    مرسمَل، الضريبة — لكلٍّ تكلفته ومدفوعه (مسقوفاً بها) ومتبقّيه.

    حصّة المورد في `components` تشمل رسومه (وضريبةً رحّلها قيدٌ قديم دائنةً له)، فتُفصل هنا:
    مدفوعه يُسدّد البضاعة أولاً ثم رسومه المرسملة ثم تلك الضريبة، ومجموع سطوره = حصّته.
    والضريبة على «ضريبة الاستيراد المستحقة» مدفوعها من سندات حسابها. كل رسمٍ مرسمَل
    (`services.purchase_fee_capitalized`: المسودة الدولية دائماً)؛ ورسمٌ رحّله قيدٌ قديم
    مصروفاً يبقى للمورد داخل سطره إن كان دائنَه، ولا سطر له إن كان بحسابه. العمولة
    مدفوعةٌ بطبيعتها (خرجت من الصندوق مع الدفعة)،
    والرسم ذو الطرف الدائن مدفوعه من سندات حسابه (`_fee_paid_by_account`).
    """
    from accounting.services import resolve_import_tax_payable_account
    from logistics.payment_posting import import_invoice_booked_commission
    from logistics.services import import_invoice_tax_payable, purchase_fee_capitalized

    tax = lc._d(invoice.tax_amount).quantize(Q2)
    tax_payable = import_invoice_tax_payable(invoice)
    tax_paid = Decimal('0')
    if tax_payable > 0 and invoice.is_posted and invoice.journal_id:
        account, _created = resolve_import_tax_payable_account(invoice.tenant_id, create=False)
        if account is not None:
            tax_paid = _journal_credit_paid(invoice, account.id)
    fees = [f for f in invoice.fees.select_related('credit_partner').order_by('id')
            if purchase_fee_capitalized(invoice, f)]
    supplier_fees = [f for f in fees if not f.has_credit_party]
    party_paid = _fee_paid_by_account(invoice, [f for f in fees if f.has_credit_party])

    supplier_paid = min(components['supplier']['paid'], components['supplier']['cost'])
    goods = max(
        components['supplier']['cost'] - (tax - tax_payable)
        - sum((lc._d(f.amount) for f in supplier_fees), Decimal('0')),
        Decimal('0.00'),
    ).quantize(Q2)

    def row(key, label, cost, paid):
        cost = lc._d(cost).quantize(Q2)
        paid = min(lc._d(paid), cost).quantize(Q2)
        return {'key': key, 'label': label, 'cost': cost, 'paid': paid,
                'remaining': (cost - paid).quantize(Q2)}

    def take(amount):
        nonlocal supplier_paid
        got = min(supplier_paid, lc._d(amount))
        supplier_paid -= got
        return got

    rows = [row('supplier', 'المورد', goods, take(goods))]
    for key, label in (('freight', 'الشحن الدولي'), ('clearance', 'التخليص'),
                       ('local', 'النقل المحلي')):
        rows.append(row(key, label, components[key]['cost'], components[key]['paid']))
    commission, _account = import_invoice_booked_commission(invoice)
    if commission > 0:
        rows.append(row('commission', 'عمولات التحويل', commission, commission))
    for fee in fees:
        paid = take(fee.amount) if not fee.has_credit_party else party_paid.get(fee.pk, Decimal('0'))
        rows.append(row(f'fee:{fee.pk}', fee.description or 'رسم', fee.amount, paid))
    if tax > 0:
        rows.append(row('tax', 'الضريبة', tax, take(tax - tax_payable) + tax_paid))
    return rows


def import_invoice_unit_costs(invoice: PurchaseInvoice, breakdown: Dict[str, Any]) -> List[Dict[str, Any]]:
    """التكلفة النهائية للوحدة (التفصيل وحده): «إجمالي التكلفة» كلّه — ضريبته ورسومه
    وعمولاته تكلفة بضاعة (`services.import_invoice_capitalizes_all`) — موزّعاً كما يوزّعه
    قيد الاستلام نفسه (`goods_clearing_unit_costs`)، فـΣ(كمية × وحدة) = مدين البضاعة في
    القيد = مدين المخزون في قيد الاستلام. مرحّلةٌ قبل القرار: بلا ما رحّله قيدها مدخلاتٍ."""
    from logistics.services import goods_clearing_unit_costs, import_invoice_capitalized_tax

    tax = sum((r['cost'] for r in breakdown['cost_rows'] if r['key'] == 'tax'), Decimal('0'))
    off_cost_tax = max(tax - import_invoice_capitalized_tax(invoice), Decimal('0'))
    inventory_cost = max(breakdown['payable_total'] - off_cost_tax, Decimal('0'))
    shares = goods_clearing_unit_costs(invoice, inventory_cost)
    return [
        {'item_id': it.pk, 'name': it.name or (it.product.name if it.product_id else ''),
         'quantity': lc._d(it.quantity), 'unit_cost': shares[it.pk][0].quantize(Decimal('0.0001'))}
        for it in invoice.items.select_related('product').order_by('id') if it.pk in shares
    ]
