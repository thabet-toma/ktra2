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

Q2 = Decimal('0.01')
COMPONENTS = ('supplier', 'freight', 'clearance', 'local')


def _is_posted(p) -> bool:
    return bool(getattr(p, 'is_posted', False))


def _shipment_portion(total: Decimal, weights: List[Decimal], index: int) -> Decimal:
    if total <= 0 or index < 0:
        return Decimal('0.00')
    return lc.distribute_by_weights(total, weights)[index]


def import_invoice_payment_breakdown(invoice: PurchaseInvoice) -> Optional[Dict[str, Any]]:
    """{supplier|freight|clearance|local: {cost, paid, remaining}} + الإجماليات والحالة.

    None لغير الدولية أو لفاتورةٍ لم تكتمل مستنداتها (بلا تخليص) — يعرض المستدعي
    ملخّص السندات المعتاد. المدفوع لكل مكوّن يُسقَف بتكلفته في الإجمالي، فزيادةٌ
    في الشحن لا تُغطّي بضاعةً غير مدفوعة؛ والتفصيل يعرض المدفوع الفعلي.
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
    costs['supplier'] = (grand + fees - sum(costs.values(), Decimal('0'))).quantize(Q2)
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
    total_cost = sum((c['cost'] for c in components.values()), Decimal('0.00'))
    covered = sum(
        (min(c['paid'], c['cost']) for c in components.values()), Decimal('0.00'))

    from core.payments import document_payment_summary
    result = document_payment_summary(total_cost, covered)
    result.update({'payable_total': total_cost, 'components': components})
    return result
