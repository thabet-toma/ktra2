"""
Server-side landed cost (ILS) for purchase invoices from shipment + clearance.
Uses Decimal arithmetic and penny balancing on line splits.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

from django.db import transaction

from tenants.models import Currency
from logistics.models import (
    LogisticsClearance,
    LogisticsClearancePayment,
    LogisticsDeal,
    LogisticsDealItem,
    LogisticsPayment,
    LogisticsShipment,
    LogisticsShipmentDeal,
    PurchaseInvoice,
    PurchaseInvoiceItem,
)
# Single source of truth — shared with serializers.py (T2-01 dedup).
from logistics.text_utils import (
    has_arabic as _has_arabic,
    is_english_payment_or_legal_boilerplate as _is_english_payment_or_legal_boilerplate,
)


Q2 = Decimal('0.01')
Q4 = Decimal('0.0001')

# يُخزَّن كسطر في cost_lines لكنه ليس جزءاً من «تكلفة التخليص» للتوزيع على الفواتير (مواءمة مع الواجهة و views.py).
SHIPPING_COST_LINE_LABEL = 'دفعة الشحن (الناقل)'
# بنود تُعرض كـ«شحن محلي» وتُستبعد من حوض حصة التخليص (تُوزَّع بنفس نسبة الصفقة مع الشحن الدولي في اللوجستيات).
LOCAL_SHIPPING_CLEARANCE_LINE_LABELS = frozenset({
    'شحن محلي',
    'الشحن المحلي',
    'شحن داخلي',
})



def _first_arabic_line_from_notes(notes: Optional[str]) -> Optional[str]:
    if not notes:
        return None
    for line in str(notes).splitlines():
        u = line.strip()
        if u and _has_arabic(u):
            return u
    return None


def invoice_title_from_deal(deal: LogisticsDeal, max_len: int = 255) -> str:
    """
    Arabic-first title aligned with frontend effectiveDealTitleForDisplay / dealSummaryDescriptionFromSql.
    Avoids using English PI terms (payment, packing, LCL…) as the invoice name.
    """
    desc = (deal.description or '').strip()
    notes = (deal.notes or '').strip()
    ref = (deal.ref_number or '').strip()
    offer = (getattr(deal, 'original_offer_number', None) or '').strip()

    if desc and _has_arabic(desc):
        return desc[:max_len]
    from_notes = _first_arabic_line_from_notes(notes)
    if from_notes:
        return from_notes[:max_len]
    # بيانات قديمة خزّنت الاسم العربي في «رقم العرض» — يتقدم على الوصف الإنجليزي
    if offer and _has_arabic(offer) and not re.match(r'^d-\d+$', offer, re.I):
        return offer[:max_len]
    if desc and not _is_english_payment_or_legal_boilerplate(desc):
        return desc[:max_len]
    if (
        offer
        and offer.lower() != ref.lower()
        and not re.match(r'^d-\d+$', offer, re.I)
        and not _is_english_payment_or_legal_boilerplate(offer)
    ):
        return offer[:max_len]
    return (ref or '—')[:max_len]


def _d(x: Any, default: str = '0') -> Decimal:
    if x is None:
        return Decimal(default)
    if isinstance(x, Decimal):
        return x
    try:
        return Decimal(str(x))
    except Exception:
        return Decimal(default)


def quantize_money(x: Decimal) -> Decimal:
    return x.quantize(Q2, rounding=ROUND_HALF_UP)


def quantize_unit(x: Decimal) -> Decimal:
    return x.quantize(Q4, rounding=ROUND_HALF_UP)


def get_ils_currency() -> Optional[Currency]:
    c = Currency.objects.filter(Code__iexact='ILS').first()
    if c:
        return c
    return Currency.objects.filter(IsBaseCurrency=True).first() or Currency.objects.order_by('CurrencyID').first()


def payment_settled(p: LogisticsPayment) -> bool:
    if getattr(p, 'confirmed_by_supplier', False):
        return True
    if (getattr(p, 'bank_swift_image', None) or '').strip():
        return True
    cb = (getattr(p, 'cash_box_external_id', None) or '').strip()
    if cb:
        return True
    st = (getattr(p, 'status', None) or '').lower()
    return st in ('confirmed', 'paid')


def sum_settled_usd_ils(payments) -> Tuple[Decimal, Decimal]:
    paid_usd = Decimal('0')
    paid_ils = Decimal('0')
    for p in payments or []:
        if not payment_settled(p):
            continue
        a = _d(p.amount)
        r = _d(getattr(p, 'usd_to_ils', None), '3.5')
        paid_usd += a
        paid_ils += (a * r).quantize(Q2, rounding=ROUND_HALF_UP)
    return paid_usd, paid_ils


def sum_settled_transfer_costs_ils(payments) -> Decimal:
    """عمولات/تكاليف تحويل الدفعات المنفّذة (USD) × سعر الشيكل لكل دفعة."""
    s = Decimal('0')
    for p in payments or []:
        if not payment_settled(p):
            continue
        tc = _d(getattr(p, 'transfer_cost', None), '0')
        if tc <= 0:
            continue
        r = _d(getattr(p, 'usd_to_ils', None), '3.5')
        s += (tc * r).quantize(Q2, rounding=ROUND_HALF_UP)
    return s.quantize(Q2, rounding=ROUND_HALF_UP)


def sum_settled_shipment_freight_transfer_commissions_ils(shipment: LogisticsShipment) -> Decimal:
    """عمولات تحويل دفعات شحن الشحنة (دفعات الوكيل بدون ربط بصفقة) — بالشيكل."""
    qs = shipment.agent_payments.filter(deal__isnull=True)
    return sum_settled_transfer_costs_ils(qs)


def deal_total_ils(deal: LogisticsDeal, remaining_rate: Decimal) -> Tuple[Decimal, Decimal, Decimal, Decimal]:
    """Returns (total_ils, paid_usd, paid_ils, unpaid_usd)."""
    total_usd = _d(deal.total_amount)
    qs = deal.payments.all()
    paid_usd, paid_ils = sum_settled_usd_ils(qs)
    unpaid = (total_usd - paid_usd).quantize(Q2, rounding=ROUND_HALF_UP)
    if unpaid < 0:
        unpaid = Decimal('0')
    total_ils = (paid_ils + unpaid * remaining_rate).quantize(Q2, rounding=ROUND_HALF_UP)
    return total_ils, paid_usd, paid_ils, unpaid


def shipment_freight_ils(shipment: LogisticsShipment, remaining_rate: Decimal) -> Tuple[Decimal, Decimal, Decimal, Decimal]:
    total_usd = _d(shipment.total_shipping_cost_usd)
    qs = shipment.agent_payments.filter(deal__isnull=True)
    paid_usd, paid_ils = sum_settled_usd_ils(qs)
    unpaid = (total_usd - paid_usd).quantize(Q2, rounding=ROUND_HALF_UP)
    if unpaid < 0:
        unpaid = Decimal('0')
    total_ils = (paid_ils + unpaid * remaining_rate).quantize(Q2, rounding=ROUND_HALF_UP)
    return total_ils, paid_usd, paid_ils, unpaid


def _clearance_cost_line_label(row: dict) -> str:
    return str(row.get('label') or '').strip()


def _excluded_from_clearance_pool_label(label: str) -> bool:
    if label == SHIPPING_COST_LINE_LABEL:
        return True
    return label in LOCAL_SHIPPING_CLEARANCE_LINE_LABELS


def sum_cost_lines_all_ils(clearance: LogisticsClearance) -> Decimal:
    """كل بنود التخليص بالشيكل (للمقارنة والعرض)."""
    s = Decimal('0')
    for row in clearance.cost_lines or []:
        if not isinstance(row, dict):
            continue
        try:
            s += _d(row.get('amount'))
        except Exception:
            continue
    return s.quantize(Q2, rounding=ROUND_HALF_UP)


def clearance_local_transport_superseded_by_localshipment(clearance) -> bool:
    """Return True when a posted LocalShipment linked to this clearance
    has capitalize_to_inventory=True — meaning local-transport cost is
    already being capitalized via its own journal entry, so the matching
    cost_lines rows must NOT be counted again in the landed-cost pool."""
    from logistics.models import LocalShipment
    return LocalShipment.objects.filter(
        clearance=clearance,
        capitalize_to_inventory=True,
        is_posted=True,
    ).exists()


def sum_local_shipping_from_clearance_cost_lines_ils(
    clearance: LogisticsClearance,
    _check_superseded: bool = True,
) -> Decimal:
    """مجموع أسطر «شحن محلي» داخل cost_lines (قبل ضرب نسبة الصفقة).

    When _check_superseded is True and a posted LocalShipment with
    capitalize_to_inventory=True exists for this clearance, returns 0
    to avoid double-counting the same transport cost in the landed pool.
    """
    if _check_superseded and clearance_local_transport_superseded_by_localshipment(clearance):
        return Decimal('0')
    s = Decimal('0')
    for row in clearance.cost_lines or []:
        if not isinstance(row, dict):
            continue
        if _clearance_cost_line_label(row) not in LOCAL_SHIPPING_CLEARANCE_LINE_LABELS:
            continue
        try:
            s += _d(row.get('amount'))
        except Exception:
            continue
    return s.quantize(Q2, rounding=ROUND_HALF_UP)


def sum_carrier_clearance_cost_line_ils(clearance: LogisticsClearance) -> Decimal:
    """سطر «دفعة الشحن (الناقل)» في التخليص — شحن جانب التخليص وليس ضمن حصة الجمارك."""
    s = Decimal('0')
    for row in clearance.cost_lines or []:
        if not isinstance(row, dict):
            continue
        if _clearance_cost_line_label(row) != SHIPPING_COST_LINE_LABEL:
            continue
        try:
            s += _d(row.get('amount'))
        except Exception:
            continue
    return s.quantize(Q2, rounding=ROUND_HALF_UP)


def sum_clearance_logistics_for_landed_share_ils(clearance: LogisticsClearance) -> Decimal:
    """شحن على التخليص يُوزَّع مع اللوجستيات (شحن محلي + دفعة الناقل) — خارج حوض التخليص."""
    return (
        sum_local_shipping_from_clearance_cost_lines_ils(clearance)
        + sum_carrier_clearance_cost_line_ils(clearance)
    ).quantize(Q2, rounding=ROUND_HALF_UP)


def sum_cost_lines_ils(clearance: LogisticsClearance) -> Decimal:
    """حوض «تكلفة التخليص» للتوزيع: كل البنود ما عدا شحن الناقل والشحن المحلي المسجّل كبنود."""
    s = Decimal('0')
    for row in clearance.cost_lines or []:
        if not isinstance(row, dict):
            continue
        lb = _clearance_cost_line_label(row)
        if _excluded_from_clearance_pool_label(lb):
            continue
        try:
            s += _d(row.get('amount'))
        except Exception:
            continue
    return s.quantize(Q2, rounding=ROUND_HALF_UP)


def _clearance_payment_is_carrier_shipping(p: LogisticsClearancePayment) -> bool:
    """دفعات الناقل المحمّلة على التخليص لكنها ليست رسوم جمركية (مواءمة pay_from_cashbox)."""
    n = str(getattr(p, 'notes', None) or '').lstrip()
    return n.startswith('[شحن]') or n.startswith('شحن')


def clearance_payment_amount_ils(
    p: LogisticsClearancePayment,
    usd_to_ils: Decimal,
) -> Decimal:
    amt = _d(p.amount)
    cur = getattr(p, 'currency', None)
    code = (getattr(cur, 'Code', None) or '').upper() if cur else ''
    if code == 'USD':
        return (amt * usd_to_ils).quantize(Q2, rounding=ROUND_HALF_UP)
    if code == 'ILS':
        return amt.quantize(Q2, rounding=ROUND_HALF_UP)
    # For other currencies, try to find an exchange rate; fallback 1:1 with warning
    try:
        from accounting.models import ExchangeRate
        ils_cur = get_ils_currency()
        if ils_cur and cur:
            er = (
                ExchangeRate.objects
                .filter(from_currency=cur, to_currency=ils_cur)
                .order_by('-effective_date')
                .first()
            )
            if er:
                return (amt * Decimal(str(er.rate))).quantize(Q2, rounding=ROUND_HALF_UP)
    except Exception:
        pass
    return amt.quantize(Q2, rounding=ROUND_HALF_UP)


def sum_clearance_payments_ils(clearance: LogisticsClearance, usd_to_ils: Decimal) -> Decimal:
    """دفعات التخليص فقط — دون دفعات الشحن الناقل الموسومة في الملاحظات."""
    s = Decimal('0')
    for p in clearance.payments.all():
        if _clearance_payment_is_carrier_shipping(p):
            continue
        s += clearance_payment_amount_ils(p, usd_to_ils)
    return s.quantize(Q2, rounding=ROUND_HALF_UP)


def clearance_pool_ils(
    clearance: LogisticsClearance,
    use_cost_lines: bool,
    usd_to_ils_for_unmarked_usd: Decimal,
) -> Tuple[Decimal, str]:
    """
    Returns (amount_ils, source_label).
    - إن طُلبت بنود التكلفة: مجموع البنود بالشيكل.
    - وإلا: إن وُجدت بنود بمبلغ > 0 تُستخدم كـ«تكلفة التخليص» للتوزيع؛ وإلا مجموع الدفعات المحوّلة.
    """
    lines_total = sum_cost_lines_ils(clearance)
    payments_total = sum_clearance_payments_ils(clearance, usd_to_ils_for_unmarked_usd)
    if use_cost_lines:
        return lines_total, 'cost_lines'
    if lines_total > 0:
        return lines_total, 'cost_lines'
    return payments_total, 'payments'


def deal_grand_total_usd_for_value_share(d: LogisticsDeal) -> Decimal:
    """
    إجمالي صفقة بالدولار لحساب حصة التخليص (قيمة) — مطابق لقائمة الصفقات في الواجهة:
    مجموع بنود الصفقة (كمية×سعر) وإلا subtotal، ثم −خصم + شحن تقديري إن لم يكن مضمّناً + ضريبة.
    إن كان المحسوب 0 يُستبدل بـ total_amount المخزّن.
    """
    calc = Decimal('0')
    try:
        for it in d.items.all():
            calc += (it.quantity * it.unit_price).quantize(Q4, rounding=ROUND_HALF_UP)
    except Exception:
        calc = Decimal('0')
    if calc <= 0:
        calc = _d(d.subtotal)
    discount = _d(d.discount_amount)
    ship_usd = Decimal('0') if d.is_shipping_included else _d(d.shipping_cost_estimate)
    net = (calc - discount).quantize(Q2, rounding=ROUND_HALF_UP)
    if net < 0:
        net = Decimal('0')
    taxable = (net + ship_usd).quantize(Q2, rounding=ROUND_HALF_UP)
    ttype = (getattr(d, 'tax_type', None) or 'percentage').lower()
    if ttype == 'amount':
        tax_amt = _d(d.tax_amount)
    else:
        tax_amt = (taxable * (_d(d.tax_rate) / Decimal('100'))).quantize(Q2, rounding=ROUND_HALF_UP)
    out = (taxable + tax_amt).quantize(Q2, rounding=ROUND_HALF_UP)
    if out <= 0:
        return _d(d.total_amount)
    return out


def deal_share_on_shipment(deal: LogisticsDeal, shipment: LogisticsShipment) -> Decimal:
    """حصة الصفقة من «قيمة» صفقات الشحنة (USD) — للتخليص والنقل من بنود التخليص."""
    links = list(
        LogisticsShipmentDeal.objects.filter(shipment=shipment)
        .select_related('deal')
        .prefetch_related('deal__items')
    )
    deal_pk = int(deal.pk)
    totals = []
    this_amt: Optional[Decimal] = None
    for link in links:
        t = deal_grand_total_usd_for_value_share(link.deal)
        totals.append(t)
        if int(link.deal_id) == deal_pk:
            this_amt = t
    if this_amt is None:
        this_amt = deal_grand_total_usd_for_value_share(deal)
    total = sum(totals, Decimal('0'))
    n = max(1, len(links))
    if total > 0:
        return (this_amt / total).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    return (Decimal('1') / Decimal(n)).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)


def _deal_measure_for_volume_share(deal: LogisticsDeal, shipment: LogisticsShipment) -> Decimal:
    """مطابق لتوزيع allocated_shipping على الشحنة: CBM أو وزن حسب pricing_method + unit_type."""
    method = (getattr(shipment, 'pricing_method', None) or 'total').lower()
    utype = (getattr(shipment, 'unit_type', None) or 'cbm').lower()
    if method == 'unit' and utype == 'weight':
        wkg = getattr(deal, 'total_weight_kg', None)
        if wkg is not None:
            return _d(wkg)
        return _d(getattr(deal, 'total_weight', None), '0')
    return _d(getattr(deal, 'total_cbm', None), '0')


def deal_volume_share_on_shipment(deal: LogisticsDeal, shipment: LogisticsShipment) -> Decimal:
    """حصة الصفقة من «حجم/وزن» صفقات الشحنة — لشحن دولي فقط (لا تُستخدم للتخليص)."""
    links = list(
        LogisticsShipmentDeal.objects.filter(shipment=shipment).select_related('deal')
    )
    deal_pk = int(deal.pk)
    measures = [_deal_measure_for_volume_share(link.deal, shipment) for link in links]
    wsum = sum(measures, Decimal('0'))
    this_m = Decimal('0')
    found = False
    for link in links:
        if int(link.deal_id) == deal_pk:
            this_m = _deal_measure_for_volume_share(link.deal, shipment)
            found = True
            break
    if not found:
        this_m = _deal_measure_for_volume_share(deal, shipment)
    n = max(1, len(links))
    if wsum > 0:
        return (this_m / wsum).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    return (Decimal('1') / Decimal(n)).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)


def distribute_by_weights(total: Decimal, weights: List[Decimal]) -> List[Decimal]:
    n = len(weights)
    if n == 0:
        return []
    wsum = sum(weights, Decimal('0'))
    if wsum <= 0:
        share = (total / Decimal(n)).quantize(Q2, rounding=ROUND_HALF_UP)
        parts = [share] * n
    else:
        raw = [(total * w / wsum) for w in weights]
        parts = [quantize_money(x) for x in raw]
    drift = (total - sum(parts, Decimal('0'))).quantize(Q2, rounding=ROUND_HALF_UP)
    if parts and drift != 0:
        parts[-1] = (parts[-1] + drift).quantize(Q2, rounding=ROUND_HALF_UP)
    return parts


@dataclass
class LandedLineResult:
    name: str
    product_id: Optional[int]
    quantity: Decimal
    unit_price_merch_ils: Decimal
    total_price_merch_ils: Decimal
    landed_unit_price_ils: Decimal
    landed_line_total_ils: Decimal
    hs_code: Optional[str]


def compute_deal_invoice_lines(
    deal: LogisticsDeal,
    deal_val_ils: Decimal,
    ship_val_ils: Decimal,
    clearance_pool: Decimal,
    share_clearance: Decimal,
    share_freight: Decimal,
    internal_shipping_usd: Decimal,
    shipping_included: bool,
    clearance_local_lines_pool_ils: Decimal = Decimal('0'),
) -> Tuple[List[LandedLineResult], Dict[str, Decimal]]:
    """Merchandise + logistics per line in ILS."""
    items = list(deal.items.select_related('product').all())
    deal_tot_usd = _d(deal.total_amount)
    internal_usd = _d(internal_shipping_usd)
    internal_ils = Decimal('0')
    if deal_tot_usd > 0:
        internal_ils = (deal_val_ils * (internal_usd / deal_tot_usd)).quantize(Q2, rounding=ROUND_HALF_UP)
    else:
        # Try real USD→ILS rate; fallback 3.6 only if unavailable
        try:
            from tenants.models import Currency
            usd_cur = Currency.objects.filter(Code__iexact='USD').first()
            ils_cur = get_ils_currency()
            if usd_cur and ils_cur:
                er = (
                    ExchangeRate.objects
                    .filter(tenant_id=deal.tenant_id, from_currency=usd_cur, to_currency=ils_cur)
                    .order_by('-effective_date')
                    .first()
                )
                rate = Decimal(str(er.rate)) if er else Decimal('3.6')
            else:
                rate = Decimal('3.6')
        except Exception:
            rate = Decimal('3.6')
        internal_ils = (internal_usd * rate).quantize(Q2, rounding=ROUND_HALF_UP)

    weights: List[Decimal] = []
    for it in items:
        line_usd = (it.quantity * it.unit_price).quantize(Q4, rounding=ROUND_HALF_UP)
        weights.append(line_usd if line_usd > 0 else Decimal('0'))

    # Use deal_val_ils directly — do NOT rescale by weight/total ratio
    # (deal.total_amount may include tax/shipping/discount not in item prices)
    merch_pool = deal_val_ils

    deal_ship_ils = (ship_val_ils * share_freight).quantize(Q2, rounding=ROUND_HALF_UP)
    deal_clear_ils = (clearance_pool * share_clearance).quantize(Q2, rounding=ROUND_HALF_UP)
    deal_local_clr_ils = (clearance_local_lines_pool_ils * share_clearance).quantize(Q2, rounding=ROUND_HALF_UP)
    internal_in_landed = Decimal('0') if shipping_included else internal_ils
    logistics_pool = (
        internal_in_landed + deal_ship_ils + deal_clear_ils + deal_local_clr_ils
    ).quantize(Q2, rounding=ROUND_HALF_UP)

    # No SQL line items (legacy deal / items only in Firestore / soft-deleted rows):
    # still emit one invoice row so totals match and the UI basket is not empty.
    if not items and (merch_pool > 0 or logistics_pool > 0):
        qty = Decimal('1')
        merch = merch_pool
        log = logistics_pool
        landed_line = (merch + log).quantize(Q2, rounding=ROUND_HALF_UP)
        landed_unit = (landed_line / qty).quantize(Q4, rounding=ROUND_HALF_UP)
        unit_m = (merch / qty).quantize(Q4, rounding=ROUND_HALF_UP) if qty > 0 else Decimal('0')
        tot_m = merch.quantize(Q2, rounding=ROUND_HALF_UP)
        title = invoice_title_from_deal(deal, max_len=220)
        name = (
            title
            if title and title != '—'
            else 'ملخص الصفقة (لا توجد بنود منتجات في النظام)'
        )[:255]
        results = [
            LandedLineResult(
                name=name,
                product_id=None,
                quantity=qty,
                unit_price_merch_ils=unit_m,
                total_price_merch_ils=tot_m,
                landed_unit_price_ils=landed_unit,
                landed_line_total_ils=landed_line,
                hs_code=None,
            )
        ]
        meta = {
            'deal_ship_allocated_ils': deal_ship_ils,
            'deal_clearance_allocated_ils': deal_clear_ils,
            'internal_shipping_ils': internal_ils,
            'local_shipping_from_clearance_ils': deal_local_clr_ils,
            'subtotal_merch_ils': tot_m,
            'synthetic_summary_line': Decimal('1'),
        }
        return results, meta

    line_merch = distribute_by_weights(merch_pool, weights)

    line_log = distribute_by_weights(logistics_pool, weights)

    results: List[LandedLineResult] = []
    subtotal = Decimal('0')
    for idx, it in enumerate(items):
        qty = it.quantity if it.quantity > 0 else Decimal('1')
        merch = line_merch[idx] if idx < len(line_merch) else Decimal('0')
        log = line_log[idx] if idx < len(line_log) else Decimal('0')
        landed_line = (merch + log).quantize(Q2, rounding=ROUND_HALF_UP)
        landed_unit = (landed_line / qty).quantize(Q4, rounding=ROUND_HALF_UP)
        unit_m = (merch / qty).quantize(Q4, rounding=ROUND_HALF_UP)
        tot_m = merch.quantize(Q2, rounding=ROUND_HALF_UP)
        subtotal += tot_m
        pname = ''
        if it.product:
            pname = (it.product.name_ar or it.product.name_en or it.product.sku or '')[:255]
        name = pname or (it.notes or f'Item {it.pk}')[:255]
        results.append(
            LandedLineResult(
                name=name,
                product_id=it.product_id,
                quantity=qty,
                unit_price_merch_ils=unit_m,
                total_price_merch_ils=tot_m,
                landed_unit_price_ils=landed_unit,
                landed_line_total_ils=landed_line,
                hs_code=None,
            )
        )
    meta = {
        'deal_ship_allocated_ils': deal_ship_ils,
        'deal_clearance_allocated_ils': deal_clear_ils,
        'internal_shipping_ils': internal_ils,
        'local_shipping_from_clearance_ils': deal_local_clr_ils,
        'subtotal_merch_ils': subtotal.quantize(Q2, rounding=ROUND_HALF_UP),
    }
    return results, meta


def build_conversion_metadata(
    *,
    deal: LogisticsDeal,
    shipment: LogisticsShipment,
    clearance: LogisticsClearance,
    share_value: Decimal,
    share_volume: Decimal,
    deal_val_ils: Decimal,
    ship_val_ils: Decimal,
    clearance_pool: Decimal,
    clearance_source: str,
    deal_remaining: Decimal,
    ship_remaining: Decimal,
    implied_deal_rate: Decimal,
    implied_ship_rate: Decimal,
    cost_lines_total: Decimal,
    payments_total_ils: Decimal,
) -> Dict[str, Any]:
    return {
        'allocation_method': 'server_pro_rata',
        'dual_share_allocations': True,
        'clearance_cost_basis': clearance_source,
        'clearance_id': clearance.id,
        'shipment_id': shipment.id,
        'remaining_balance_rate_deal': float(deal_remaining),
        'remaining_balance_rate_shipment': float(ship_remaining),
        'deal_share_by_value': float(share_value),
        'deal_share_by_volume': float(share_volume),
        # توافق خلفي: كان يُعبأ بنسبة القيمة — أصبحت نسبة الحجم (شحن دولي)
        'deal_share_of_shipment': float(share_volume),
        'deal_total_ils': float(deal_val_ils),
        'shipment_total_ils': float(ship_val_ils),
        'clearance_pool_ils': float(clearance_pool),
        'cost_lines_total_ils': float(cost_lines_total),
        'clearance_payments_total_ils': float(payments_total_ils),
        'deal_effective_rate': float(implied_deal_rate),
        'shipment_effective_rate': float(implied_ship_rate),
    }


def build_local_payments_json(deal_clear_ils: Decimal) -> Dict[str, Any]:
    return {
        'calculationMethod': 'detailed',
        'customsClearanceFees': float(deal_clear_ils.quantize(Q2, rounding=ROUND_HALF_UP)),
        'customsDuties': 0.0,
        'portFees': 0.0,
        'internalShippingFees': 0.0,
        'palestinianTaxCustoms': 0.0,
        'includedInPrice': False,
    }


def compute_tax_and_grand(
    *,
    subtotal: Decimal,
    discount: Decimal,
    shipping_cost_ils: Decimal,
    shipping_included: bool,
    tax_rate: Decimal,
    tax_type: str,
    tax_amount_fixed: Decimal,
    local_payments_sum: Decimal,
) -> Tuple[Decimal, Decimal]:
    after_disc = (subtotal - discount).quantize(Q2, rounding=ROUND_HALF_UP)
    if after_disc < 0:
        after_disc = Decimal('0')
    ship_part = Decimal('0') if shipping_included else shipping_cost_ils
    taxable = (after_disc + ship_part).quantize(Q2, rounding=ROUND_HALF_UP)
    ttype = (tax_type or 'percentage').lower()
    if ttype == 'amount':
        tax_amt = tax_amount_fixed.quantize(Q2, rounding=ROUND_HALF_UP)
    else:
        tax_amt = (taxable * (tax_rate / Decimal('100'))).quantize(Q2, rounding=ROUND_HALF_UP)
    grand = (taxable + tax_amt + local_payments_sum).quantize(Q2, rounding=ROUND_HALF_UP)
    return tax_amt, grand


def preview_landed_import(
    *,
    clearance: LogisticsClearance,
    deal_ids: List[int],
    deal_remaining_rate: Decimal,
    shipment_remaining_rate: Decimal,
    use_cost_lines: bool,
) -> Dict[str, Any]:
    shipment = clearance.shipment
    ship_val_ils, ship_paid_usd, ship_paid_ils, ship_unpaid_usd = shipment_freight_ils(
        shipment, shipment_remaining_rate
    )
    # حوض توزيع الحصص = نفس إجمالي الشحن بالشيكل (مدفوع بأسعار دفعاته + المتبقي×سعر المتبقي)، لا إجمالي USD×سعر واحد
    ship_pool_share = ship_val_ils
    ship_total_usd = _d(shipment.total_shipping_cost_usd)
    cost_lines_total = sum_cost_lines_all_ils(clearance)
    local_clr_lines_total = sum_clearance_logistics_for_landed_share_ils(clearance)
    payments_total = sum_clearance_payments_ils(clearance, shipment_remaining_rate)
    clearance_pool, src = clearance_pool_ils(clearance, use_cost_lines, shipment_remaining_rate)
    deals_out = []
    for did in deal_ids:
        try:
            deal = LogisticsDeal.objects.get(pk=did)
        except LogisticsDeal.DoesNotExist:
            continue
        if not LogisticsShipmentDeal.objects.filter(shipment=shipment, deal_id=deal.id).exists():
            continue
        share_value = deal_share_on_shipment(deal, shipment)
        share_volume = deal_volume_share_on_shipment(deal, shipment)
        deal_val_ils, _, _, _ = deal_total_ils(deal, deal_remaining_rate)
        deal_clear = (clearance_pool * share_value).quantize(Q2, rounding=ROUND_HALF_UP)
        deal_ship = (ship_pool_share * share_volume).quantize(Q2, rounding=ROUND_HALF_UP)
        deal_local_clr = (local_clr_lines_total * share_value).quantize(Q2, rounding=ROUND_HALF_UP)
        deals_out.append({
            'deal_id': deal.id,
            'ref_number': deal.ref_number,
            'share': float(share_value),
            'share_by_volume': float(share_volume),
            'deal_total_ils': float(deal_val_ils),
            'allocated_clearance_ils': float(deal_clear),
            'allocated_freight_ils': float(deal_ship),
            'allocated_local_shipping_from_clearance_lines_ils': float(deal_local_clr),
        })
    mismatch = abs(cost_lines_total - payments_total) > Decimal('0.02')
    freight_tol = Decimal('0.02')
    return {
        'shipment_id': shipment.id,
        'clearance_id': clearance.id,
        'clearance_source': src,
        'cost_lines_total_ils': float(cost_lines_total),
        'clearance_payments_total_ils': float(payments_total),
        'shipment_freight_total_ils': float(ship_pool_share),
        'shipment_freight_total_usd': float(ship_total_usd),
        'shipment_freight_paid_usd': float(ship_paid_usd),
        'shipment_freight_paid_ils': float(ship_paid_ils),
        'shipment_freight_unpaid_usd': float(ship_unpaid_usd),
        'shipment_freight_fully_paid': ship_unpaid_usd <= freight_tol,
        'clearance_pool_ils': float(clearance_pool),
        'clearance_local_shipping_cost_lines_total_ils': float(local_clr_lines_total),
        'cost_lines_vs_payments_mismatch': mismatch,
        'deals': deals_out,
    }


def build_purchase_invoice_row(
    *,
    deal: LogisticsDeal,
    shipment: LogisticsShipment,
    clearance: LogisticsClearance,
    deal_remaining_rate: Decimal,
    shipment_remaining_rate: Decimal,
    use_cost_lines: bool,
    ils_currency: Currency,
) -> Dict[str, Any]:
    """Payload dict for PurchaseInvoiceSerializer (nested items)."""
    shipment = (
        LogisticsShipment.objects.prefetch_related('agent_payments')
        .filter(pk=shipment.pk)
        .first()
        or shipment
    )
    clearance = (
        LogisticsClearance.objects.prefetch_related('payments', 'payments__currency')
        .filter(pk=clearance.pk)
        .first()
        or clearance
    )
    deal = LogisticsDeal.objects.prefetch_related('payments', 'items__product').get(pk=deal.pk)

    share_value = deal_share_on_shipment(deal, shipment)
    share_volume = deal_volume_share_on_shipment(deal, shipment)
    deal_val_ils, deal_paid_usd, deal_paid_ils, deal_unpaid_usd = deal_total_ils(deal, deal_remaining_rate)
    ship_val_ils, ship_paid_usd, ship_paid_ils, ship_unpaid_usd = shipment_freight_ils(shipment, shipment_remaining_rate)
    ship_pool_share = ship_val_ils
    cost_lines_total = sum_cost_lines_all_ils(clearance)
    local_clr_lines_total = sum_clearance_logistics_for_landed_share_ils(clearance)
    payments_total = sum_clearance_payments_ils(clearance, shipment_remaining_rate)
    clearance_pool, clr_src = clearance_pool_ils(clearance, use_cost_lines, shipment_remaining_rate)

    deal_tot_usd = _d(deal.total_amount)
    implied_deal = (deal_val_ils / deal_tot_usd) if deal_tot_usd > 0 else deal_remaining_rate
    ship_tot_usd = _d(shipment.total_shipping_cost_usd)
    implied_ship = (ship_pool_share / ship_tot_usd) if ship_tot_usd > 0 else shipment_remaining_rate

    internal_usd = _d(deal.shipping_cost_estimate)
    lines, extra_meta = compute_deal_invoice_lines(
        deal=deal,
        deal_val_ils=deal_val_ils,
        ship_val_ils=ship_pool_share,
        clearance_pool=clearance_pool,
        share_clearance=share_value,
        share_freight=share_volume,
        internal_shipping_usd=internal_usd,
        shipping_included=bool(deal.is_shipping_included),
        clearance_local_lines_pool_ils=local_clr_lines_total,
    )
    deal_xfer_ils = sum_settled_transfer_costs_ils(deal.payments.all())
    ship_xfer_total_ils = sum_settled_shipment_freight_transfer_commissions_ils(shipment)
    deal_share_ship_xfer_ils = (ship_xfer_total_ils * share_volume).quantize(Q2, rounding=ROUND_HALF_UP)
    total_transfer_ils = (deal_xfer_ils + deal_share_ship_xfer_ils).quantize(Q2, rounding=ROUND_HALF_UP)
    extra_meta = {
        **extra_meta,
        'deal_transfer_commissions_ils': total_transfer_ils,
        'deal_transfer_commissions_from_deal_payments_ils': deal_xfer_ils,
        'shipment_transfer_commissions_total_ils': ship_xfer_total_ils,
        'deal_transfer_commissions_from_shipment_share_ils': deal_share_ship_xfer_ils,
    }
    items_payload = []
    for ln in lines:
        items_payload.append({
            'product': ln.product_id,
            'name': ln.name,
            'quantity': ln.quantity,
            'unit_price': ln.unit_price_merch_ils,
            'total_price': ln.total_price_merch_ils,
            'notes': None,
            'hs_code': ln.hs_code,
            'landed_unit_price_ils': ln.landed_unit_price_ils,
            'landed_line_total_ils': ln.landed_line_total_ils,
        })

    subtotal = sum((it['total_price'] for it in items_payload), Decimal('0')).quantize(Q2, rounding=ROUND_HALF_UP)
    discount = _d(deal.discount_amount)
    ship_alloc = extra_meta['deal_ship_allocated_ils']
    internal_full = extra_meta['internal_shipping_ils']
    deal_local_clr = extra_meta.get('local_shipping_from_clearance_ils', Decimal('0'))
    if not deal.is_shipping_included:
        ship_cost_line = (internal_full + ship_alloc + deal_local_clr).quantize(Q2, rounding=ROUND_HALF_UP)
    else:
        ship_cost_line = (ship_alloc + deal_local_clr).quantize(Q2, rounding=ROUND_HALF_UP)
    deal_clear = extra_meta['deal_clearance_allocated_ils']
    local_json = build_local_payments_json(deal_clear)
    local_sum = _d(local_json['customsClearanceFees'])

    tax_amt, grand = compute_tax_and_grand(
        subtotal=subtotal,
        discount=discount,
        shipping_cost_ils=ship_cost_line,
        shipping_included=bool(deal.is_shipping_included),
        tax_rate=_d(deal.tax_rate),
        tax_type=str(deal.tax_type or 'percentage'),
        tax_amount_fixed=_d(deal.tax_amount),
        local_payments_sum=local_sum,
    )

    conv = build_conversion_metadata(
        deal=deal,
        shipment=shipment,
        clearance=clearance,
        share_value=share_value,
        share_volume=share_volume,
        deal_val_ils=deal_val_ils,
        ship_val_ils=ship_pool_share,
        clearance_pool=clearance_pool,
        clearance_source=clr_src,
        deal_remaining=deal_remaining_rate,
        ship_remaining=shipment_remaining_rate,
        implied_deal_rate=implied_deal,
        implied_ship_rate=implied_ship,
        cost_lines_total=cost_lines_total,
        payments_total_ils=payments_total,
    )
    conv.update({
        'line_meta': {k: float(v) if isinstance(v, Decimal) else v for k, v in extra_meta.items()},
        'deal_transfer_commissions_ils': float(total_transfer_ils),
        'deal_transfer_commissions_from_deal_payments_ils': float(deal_xfer_ils),
        'shipment_transfer_commissions_total_ils': float(ship_xfer_total_ils),
        'deal_transfer_commissions_from_shipment_share_ils': float(deal_share_ship_xfer_ils),
        'deal_local_shipping_from_clearance_ils': float(deal_local_clr),
        'clearance_local_shipping_lines_total_ils': float(local_clr_lines_total),
        'deal_paid_usd': float(deal_paid_usd),
        'deal_paid_ils': float(deal_paid_ils),
        'deal_unpaid_usd': float(deal_unpaid_usd),
        'ship_paid_usd': float(ship_paid_usd),
        'ship_paid_ils': float(ship_paid_ils),
        'ship_unpaid_usd': float(ship_unpaid_usd),
    })

    inv_name = invoice_title_from_deal(deal, max_len=255)
    return {
        'invoice_name': inv_name,
        'invoice_date': deal.order_date,
        'partner': deal.partner_id,
        'deal': deal.id,
        'shipment': shipment.id,
        'clearance': clearance.id,
        'currency': ils_currency.CurrencyID,
        'exchange_rate': Decimal('1'),
        'subtotal': subtotal,
        'discount_amount': discount,
        'tax_rate': deal.tax_rate,
        'tax_amount': tax_amt,
        'tax_type': deal.tax_type or 'percentage',
        'shipping_cost': ship_cost_line,
        'shipping_included': deal.is_shipping_included,
        'grand_total': grand,
        'local_payments_json': local_json,
        'conversion_metadata_json': conv,
        'status': 'incomplete',
        'notes': (deal.notes or '')[:2000] if deal.notes else None,
        'supplier_invoice_number': deal.supplier_invoice_number,
        'factory_name': deal.factory_name,
        'items': items_payload,
    }


def import_invoices_from_clearance(
    *,
    tenant,
    clearance_id: int,
    deal_ids: List[int],
    deal_remaining_rate: Decimal,
    shipment_remaining_rate: Decimal,
    use_cost_lines: bool,
    next_invoice_number_cb,
    allow_unpaid_freight: bool = False,
) -> List[PurchaseInvoice]:
    """Create one PurchaseInvoice per deal; assigns sequential invoice numbers."""
    clearance = (
        LogisticsClearance.objects.select_related('shipment')
        .prefetch_related('payments', 'payments__currency')
        .get(pk=clearance_id, tenant=tenant)
    )
    shipment = clearance.shipment
    shipment_for_pay = (
        LogisticsShipment.objects.prefetch_related('agent_payments')
        .filter(pk=shipment.pk)
        .first()
        or shipment
    )
    _, _, _, ship_unpaid_usd = shipment_freight_ils(shipment_for_pay, shipment_remaining_rate)
    if ship_unpaid_usd > Decimal('0.02') and not allow_unpaid_freight:
        raise ValueError(
            'لا يمكن استيراد الفاتورة: يوجد مبلغ شحن دولي غير مدفوع بالدولار على الشحنة. '
            'سجّل دفعات وكيل الشحن المؤكّدة حتى يصبح المدفوع مساوياً لإجمالي تكلفة الشحن بالدولار، ثم أعد المحاولة.'
        )
    ils = get_ils_currency()
    if not ils:
        raise ValueError('No currency configured (ILS missing)')

    created: List[PurchaseInvoice] = []
    with transaction.atomic():
        for did in deal_ids:
            if not LogisticsShipmentDeal.objects.filter(shipment=shipment, deal_id=did).exists():
                continue
            deal = LogisticsDeal.objects.get(pk=did, tenant=tenant)
            payload = build_purchase_invoice_row(
                deal=deal,
                shipment=shipment,
                clearance=clearance,
                deal_remaining_rate=deal_remaining_rate,
                shipment_remaining_rate=shipment_remaining_rate,
                use_cost_lines=use_cost_lines,
                ils_currency=ils,
            )
            inv_num = next_invoice_number_cb()
            inv = PurchaseInvoice.objects.create(
                tenant=tenant,
                invoice_number=inv_num,
                invoice_name=payload.get('invoice_name'),
                invoice_date=payload.get('invoice_date'),
                partner_id=payload['partner'],
                deal_id=payload['deal'],
                shipment_id=payload['shipment'],
                # كان لا يُكتب أبداً فاختصار «فاتورة #N» في شاشة الاستيراد لا يظهر (T12-A4)
                converted_from_shipment_id=payload['shipment'],
                clearance_id=payload['clearance'],
                currency_id=payload['currency'],
                exchange_rate=payload['exchange_rate'],
                subtotal=payload['subtotal'],
                discount_amount=payload['discount_amount'],
                tax_rate=payload['tax_rate'],
                tax_amount=payload['tax_amount'],
                tax_type=payload['tax_type'],
                shipping_cost=payload['shipping_cost'],
                shipping_included=payload['shipping_included'],
                grand_total=payload['grand_total'],
                # حقول JSON حُذفت في 0035 (P-D-8) — معاملات الاستيراد بأعمدة منمّطة،
                # والفاتورة المنشأة من تخليص دولية دائماً (لا default='local')
                invoice_type=PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL,
                import_deal_remaining_rate=deal_remaining_rate,
                import_shipment_remaining_rate=shipment_remaining_rate,
                import_use_cost_lines=use_cost_lines,
                status=payload.get('status') or 'incomplete',
                notes=payload.get('notes'),
                supplier_invoice_number=payload.get('supplier_invoice_number'),
                factory_name=payload.get('factory_name'),
            )
            for row in payload['items']:
                PurchaseInvoiceItem.objects.create(
                    invoice=inv,
                    product_id=row.get('product'),
                    name=row['name'],
                    quantity=row['quantity'],
                    unit_price=row['unit_price'],
                    total_price=row['total_price'],
                    notes=row.get('notes'),
                    hs_code=row.get('hs_code'),
                    landed_unit_price_ils=row.get('landed_unit_price_ils'),
                    landed_line_total_ils=row.get('landed_line_total_ils'),
                )
            created.append(inv)
    return created


def recalculate_landed_for_shipment(
    *,
    tenant,
    shipment_id: int,
    deal_remaining_rate: Decimal,
    shipment_remaining_rate: Decimal,
    use_cost_lines: bool,
) -> Dict[str, Any]:
    """تحديث فواتير الشراء المرتبطة بالشحنة (غير المرحّلة فقط)."""
    qs = PurchaseInvoice.objects.filter(
        tenant=tenant,
        shipment_id=shipment_id,
    ).select_related('deal', 'shipment', 'clearance')
    if not qs.exists():
        return {
            'updated': 0,
            'skipped': 0,
            'skipped_posted': 0,
            'message': 'لا توجد فواتير مرتبطة بهذه الشحنة.',
        }

    updated = 0
    skipped = 0
    skipped_posted = 0
    with transaction.atomic():
        for inv in qs:
            if inv.is_posted:
                skipped_posted += 1
                continue
            if not inv.deal_id:
                skipped += 1
                continue
            clr = inv.clearance
            if not clr:
                try:
                    clr = LogisticsClearance.objects.get(shipment_id=shipment_id, tenant=tenant)
                except LogisticsClearance.DoesNotExist:
                    skipped += 1
                    continue
            deal = inv.deal
            shipment = inv.shipment
            payload = build_purchase_invoice_row(
                deal=deal,
                shipment=shipment,
                clearance=clr,
                deal_remaining_rate=deal_remaining_rate,
                shipment_remaining_rate=shipment_remaining_rate,
                use_cost_lines=use_cost_lines,
                ils_currency=inv.currency or get_ils_currency(),
            )
            inv.subtotal = payload['subtotal']
            inv.discount_amount = payload['discount_amount']
            inv.tax_amount = payload['tax_amount']
            inv.shipping_cost = payload['shipping_cost']
            inv.shipping_included = payload['shipping_included']
            inv.grand_total = payload['grand_total']
            inv.invoice_name = payload.get('invoice_name')
            inv.import_deal_remaining_rate = deal_remaining_rate
            inv.import_shipment_remaining_rate = shipment_remaining_rate
            inv.import_use_cost_lines = use_cost_lines
            inv.clearance_id = clr.id
            inv.save()
            inv.items.all().delete()
            for row in payload['items']:
                PurchaseInvoiceItem.objects.create(
                    invoice=inv,
                    product_id=row.get('product'),
                    name=row['name'],
                    quantity=row['quantity'],
                    unit_price=row['unit_price'],
                    total_price=row['total_price'],
                    notes=row.get('notes'),
                    hs_code=row.get('hs_code'),
                    landed_unit_price_ils=row.get('landed_unit_price_ils'),
                    landed_line_total_ils=row.get('landed_line_total_ils'),
                )
            updated += 1
    if updated:
        base = f'تم تحديث {updated} فاتورة.'
    else:
        base = 'لم تُحدَّث أي فاتورة.'
    reasons: List[str] = []
    if skipped_posted:
        reasons.append(
            f'{skipped_posted} مرحّلة (لا يُعاد حسابها؛ ألغِ الترحيل من المحاسبة إن أردت التعديل)'
        )
    if skipped:
        reasons.append(f'{skipped} بدون صفقة أو بدون تخليص')
    suffix = (' — ' + ' · '.join(reasons)) if reasons else ''
    return {
        'updated': updated,
        'skipped': skipped,
        'skipped_posted': skipped_posted,
        'message': base + suffix,
    }


def redistribute_shipment_deal_allocations(shipment: LogisticsShipment) -> int:
    """
    Persist USD allocation per deal on LogisticsShipmentDeal from CBM or weight.
    Returns number of links updated.
    """
    links = list(
        LogisticsShipmentDeal.objects.filter(shipment=shipment).select_related('deal')
    )
    if not links:
        return 0
    total_cost = _d(shipment.total_shipping_cost_usd)
    method = (shipment.pricing_method or 'total').lower()
    utype = (shipment.unit_type or 'cbm').lower()

    def weight_for_deal(d: LogisticsDeal) -> Decimal:
        if method == 'unit' and utype == 'weight':
            w = _d(d.total_weight_kg) if d.total_weight_kg is not None else _d(d.total_weight)
            return w
        return _d(d.total_cbm)

    weights = [weight_for_deal(l.deal) for l in links]
    wsum = sum(weights, Decimal('0'))
    n = len(links)
    if wsum <= 0:
        parts = distribute_by_weights(total_cost, [Decimal('1')] * n)
    else:
        parts = distribute_by_weights(total_cost, weights)

    count = 0
    for idx, link in enumerate(links):
        alloc = parts[idx] if idx < len(parts) else Decimal('0')
        alloc = alloc.quantize(Q2, rounding=ROUND_HALF_UP)
        if link.allocated_shipping_cost != alloc or link.extra_costs != Decimal('0'):
            link.allocated_shipping_cost = alloc
            link.extra_costs = Decimal('0')
            link.save(update_fields=['allocated_shipping_cost', 'extra_costs'])
            count += 1
    return count


def compute_live_purchase_invoice_read_payload(inv: PurchaseInvoice) -> Optional[Dict[str, Any]]:
    """
    إعادة بناء payload الفاتورة من صفقة/شحنة/تخليص حاليّين — للعرض عند GET فقط (لا يكتب DB).
    الفواتير المرحّلة تُعرض كما حُفظت للمحاسبة.
    """
    if getattr(inv, 'is_posted', False):
        return None
    if not inv.deal_id or not inv.shipment_id:
        return None
    # معاملات الاستيراد من الأعمدة المنمّطة (بديل conversion_metadata_json المحذوف في P-D-8)
    dr = _d(inv.import_deal_remaining_rate, '3.6') if inv.import_deal_remaining_rate else Decimal('3.6')
    sr = _d(inv.import_shipment_remaining_rate, '3.6') if inv.import_shipment_remaining_rate else Decimal('3.6')
    use_cl = bool(inv.import_use_cost_lines)

    ils = inv.currency or get_ils_currency()
    if not ils:
        return None
    deal = LogisticsDeal.objects.filter(pk=inv.deal_id, tenant_id=inv.tenant_id).first()
    shipment = LogisticsShipment.objects.filter(pk=inv.shipment_id, tenant_id=inv.tenant_id).first()
    clearance = None
    if inv.clearance_id:
        clearance = LogisticsClearance.objects.filter(pk=inv.clearance_id, tenant_id=inv.tenant_id).first()
    if clearance is None and inv.shipment_id:
        clearance = LogisticsClearance.objects.filter(
            shipment_id=inv.shipment_id, tenant_id=inv.tenant_id
        ).first()
    if not deal or not shipment or not clearance:
        return None
    try:
        return build_purchase_invoice_row(
            deal=deal,
            shipment=shipment,
            clearance=clearance,
            deal_remaining_rate=dr,
            shipment_remaining_rate=sr,
            use_cost_lines=use_cl,
            ils_currency=ils,
        )
    except Exception:
        return None


def _json_friendly_value(x: Any) -> Any:
    if isinstance(x, Decimal):
        return float(x)
    if isinstance(x, dict):
        return {k: _json_friendly_value(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_json_friendly_value(v) for v in x]
    return x
