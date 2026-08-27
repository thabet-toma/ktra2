"""
اختبارات ثبات landed cost:
sum(landed_line_total_ils) == deal_val_ils + allocated_freight + allocated_clearance

تشغيل: python manage.py test logistics.tests.test_landed_cost
"""
from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase

from logistics.landed_cost import (
    Q2,
    compute_deal_invoice_lines,
    distribute_by_weights,
    sum_local_shipping_from_clearance_cost_lines_ils,
    clearance_local_transport_superseded_by_localshipment,
)


class _MockItemsQS:
    """محاكاة QuerySet للمنتجات — يدعم select_related().all() و __iter__."""
    def __init__(self, items=None):
        self._items = items or []
    def __iter__(self):
        return iter(self._items)
    def all(self):
        return self._items
    def select_related(self, *args):
        return self
    def filter(self, **kwargs):
        return self
    def exists(self):
        return bool(self._items)
    def count(self):
        return len(self._items)


class LandedCostInvariantTest(SimpleTestCase):
    """يؤكد أن مجموع بنود الفاتورة يساوي بالضبط:
    قيمة الصفقة + حصة الشحن الدولي + حصة التخليص.
    """

    def _make_deal(self, total_amount, items=None):
        from types import SimpleNamespace
        return SimpleNamespace(
            pk=1, id=1, tenant_id=1, ref_number='D-001',
            total_amount=Decimal(str(total_amount)),
            discount_amount=Decimal('0'),
            shipping_cost_estimate=Decimal('0'),
            is_shipping_included=False,
            tax_type='percentage', tax_rate=Decimal('0'), tax_amount=Decimal('0'),
            subtotal=Decimal(str(total_amount)),
            order_date=None, description='Test Deal', notes=None,
            supplier_invoice_number=None, factory_name=None,
            partner_id=1, currency_id=1,
            items=_MockItemsQS(items),
            original_offer_number=None,
        )

    def test_synthetic_line_invariant(self):
        """بدون بنود منتجات: السطر التركيبي يجب أن يطابق deal_val_ils."""
        deal = self._make_deal(10000)
        deal_val_ils = Decimal('36000.00')  # 10000 * 3.6
        ship_val_ils = Decimal('7200.00')   # 2000 * 3.6
        clearance_pool = Decimal('2520.00')  # 700 * 3.6
        share_clearance = Decimal('1.0')     # صفقة واحدة
        share_freight = Decimal('1.0')

        lines, meta = compute_deal_invoice_lines(
            deal=deal,
            deal_val_ils=deal_val_ils,
            ship_val_ils=ship_val_ils,
            clearance_pool=clearance_pool,
            share_clearance=share_clearance,
            share_freight=share_freight,
            internal_shipping_usd=Decimal('0'),
            shipping_included=False,
            clearance_local_lines_pool_ils=Decimal('0'),
        )

        total_landed = sum((ln.landed_line_total_ils for ln in lines), Decimal('0'))
        allocated_freight = meta['deal_ship_allocated_ils']
        allocated_clearance = meta['deal_clearance_allocated_ils']
        expected = (deal_val_ils + allocated_freight + allocated_clearance).quantize(Q2)

        drift = abs(total_landed - expected)
        self.assertLessEqual(drift, Decimal('0.01'),
            f"Synthetic invariant broken: sum={total_landed} != expected={expected}. Drift={drift}")

    def test_multi_line_invariant(self):
        """بنود متعددة: المجموع يجب أن يطابق الإجمالي مع تسوية الانحراف."""
        from types import SimpleNamespace
        items = [
            SimpleNamespace(
                pk=1, product_id=1, product=SimpleNamespace(name_ar='أ', name_en='A', sku='S-A'),
                quantity=Decimal('100'), unit_price=Decimal('50.00'), notes=None,
            ),
            SimpleNamespace(
                pk=2, product_id=2, product=SimpleNamespace(name_ar='ب', name_en='B', sku='S-B'),
                quantity=Decimal('50'), unit_price=Decimal('100.00'), notes=None,
            ),
        ]
        deal = self._make_deal(10000, items)  # 100*50 + 50*100 = 10000
        deal_val_ils = Decimal('36000.00')
        ship_val_ils = Decimal('7200.00')
        clearance_pool = Decimal('2520.00')
        share_clearance = Decimal('1.0')
        share_freight = Decimal('1.0')

        lines, meta = compute_deal_invoice_lines(
            deal=deal,
            deal_val_ils=deal_val_ils,
            ship_val_ils=ship_val_ils,
            clearance_pool=clearance_pool,
            share_clearance=share_clearance,
            share_freight=share_freight,
            internal_shipping_usd=Decimal('0'),
            shipping_included=False,
            clearance_local_lines_pool_ils=Decimal('0'),
        )

        total_landed = sum((ln.landed_line_total_ils for ln in lines), Decimal('0'))
        allocated_freight = meta['deal_ship_allocated_ils']
        allocated_clearance = meta['deal_clearance_allocated_ils']
        expected = (deal_val_ils + allocated_freight + allocated_clearance).quantize(Q2)

        drift = abs(total_landed - expected)
        self.assertLessEqual(drift, Decimal('0.01'),
            f"Multi-line invariant broken: sum={total_landed} != expected={expected}. Drift={drift}")

    def test_distribute_by_weights_balances(self):
        """distribute_by_weights يجب أن يوزع المبلغ بالضبط دون انحراف."""
        total = Decimal('1000.00')
        weights = [Decimal('300'), Decimal('200'), Decimal('500')]
        parts = distribute_by_weights(total, weights)
        self.assertEqual(sum(parts, Decimal('0')), total)

    def test_zero_weights_equal_share(self):
        """أوزان صفرية → توزيع متساوٍ."""
        total = Decimal('999.99')
        weights = [Decimal('0'), Decimal('0'), Decimal('0')]
        parts = distribute_by_weights(total, weights)
        self.assertEqual(sum(parts, Decimal('0')), total)
        self.assertEqual(len(parts), 3)

    def test_single_item_no_drift(self):
        """منتج واحد: لا انحراف ممكن."""
        from types import SimpleNamespace
        items = [
            SimpleNamespace(
                pk=1, product_id=1, product=SimpleNamespace(name_ar='وحيد', name_en='Single', sku='S-1'),
                quantity=Decimal('1'), unit_price=Decimal('5000.00'), notes=None,
            ),
        ]
        deal = self._make_deal(5000, items)
        deal_val_ils = Decimal('18000.00')
        ship_val_ils = Decimal('7200.00')
        clearance_pool = Decimal('2520.00')
        share_clearance = Decimal('1.0')
        share_freight = Decimal('1.0')

        lines, meta = compute_deal_invoice_lines(
            deal=deal,
            deal_val_ils=deal_val_ils,
            ship_val_ils=ship_val_ils,
            clearance_pool=clearance_pool,
            share_clearance=share_clearance,
            share_freight=share_freight,
            internal_shipping_usd=Decimal('0'),
            shipping_included=False,
            clearance_local_lines_pool_ils=Decimal('0'),
        )

        total_landed = sum((ln.landed_line_total_ils for ln in lines), Decimal('0'))
        allocated_freight = meta['deal_ship_allocated_ils']
        allocated_clearance = meta['deal_clearance_allocated_ils']
        expected = (deal_val_ils + allocated_freight + allocated_clearance).quantize(Q2)

        self.assertEqual(total_landed, expected,
            f"Single item drift: {total_landed} != {expected}")

    def test_shipping_included_excludes_internal(self):
        """عندما shipping_included=True، لا يُضاف الشحن الداخلي."""
        deal = self._make_deal(10000)
        deal_val_ils = Decimal('36000.00')
        ship_val_ils = Decimal('7200.00')
        clearance_pool = Decimal('2520.00')
        share_clearance = Decimal('1.0')
        share_freight = Decimal('1.0')

        lines, meta = compute_deal_invoice_lines(
            deal=deal,
            deal_val_ils=deal_val_ils,
            ship_val_ils=ship_val_ils,
            clearance_pool=clearance_pool,
            share_clearance=share_clearance,
            share_freight=share_freight,
            internal_shipping_usd=Decimal('500'),
            shipping_included=True,
            clearance_local_lines_pool_ils=Decimal('0'),
        )

        total_landed = sum((ln.landed_line_total_ils for ln in lines), Decimal('0'))
        allocated_freight = meta['deal_ship_allocated_ils']
        allocated_clearance = meta['deal_clearance_allocated_ils']
        expected = (deal_val_ils + allocated_freight + allocated_clearance).quantize(Q2)

        drift = abs(total_landed - expected)
        self.assertLessEqual(drift, Decimal('0.01'),
            f"Shipping-included invariant broken: sum={total_landed} != expected={expected}. Drift={drift}")

    def test_internal_shipping_not_double_counted(self):
        """«شحن داخل الصين» جزء من إجمالي الصفقة أصلاً (بضاعة 5380 + شحن 120 = 5500)،
        فيجب خصمه من حوض البضاعة لا إضافته فوق الإجمالي المحوّل."""
        from types import SimpleNamespace
        items = [
            SimpleNamespace(
                pk=1, product_id=1,
                product=SimpleNamespace(name_ar='انفيرتر', name_en='Inverter', sku='5773'),
                quantity=Decimal('20'), unit_price=Decimal('269.00'), notes=None,
            ),
        ]
        deal = self._make_deal(5500, items)  # 20*269 = 5380 بضاعة + 120 شحن داخل الصين
        deal.shipping_cost_estimate = Decimal('120')
        deal_val_ils = Decimal('17820.00')  # 5500 * 3.24
        ship_val_ils = Decimal('708.58')
        clearance_pool = Decimal('2431.70')
        share_clearance = Decimal('1.0')
        share_freight = Decimal('1.0')

        lines, meta = compute_deal_invoice_lines(
            deal=deal,
            deal_val_ils=deal_val_ils,
            ship_val_ils=ship_val_ils,
            clearance_pool=clearance_pool,
            share_clearance=share_clearance,
            share_freight=share_freight,
            internal_shipping_usd=Decimal('120'),
            shipping_included=False,
            clearance_local_lines_pool_ils=Decimal('0'),
        )

        # 17820 * (120/5500) = 388.80 — يظهر مرة واحدة ضمن اللوجستيات
        self.assertEqual(meta['internal_shipping_ils'], Decimal('388.80'))
        # البضاعة وحدها = 5380 * 3.24
        self.assertEqual(meta['subtotal_merch_ils'], Decimal('17431.20'))

        total_landed = sum((ln.landed_line_total_ils for ln in lines), Decimal('0'))
        expected = (
            deal_val_ils
            + meta['deal_ship_allocated_ils']
            + meta['deal_clearance_allocated_ils']
        ).quantize(Q2)
        self.assertEqual(total_landed, expected,
            f"Internal shipping double-counted: sum={total_landed} != expected={expected}")


class T1_01_DoubleLocalTransportCapitalizationTest(SimpleTestCase):
    """T1-01: LocalShipment.capitalize_to_inventory + cost_lines local-shipping
    must NOT double-count the same transport cost in the landed pool."""

    def _mock_clearance(self, cost_lines):
        """M4: the sums now read `clearance.lines.all()` (not the removed cost_lines
        shim), so build mock line rows with debit/credit from the legacy amounts."""
        from types import SimpleNamespace
        from decimal import Decimal as _D
        lines = []
        for row in cost_lines:
            amt = _D(str(row.get('amount') or 0))
            lines.append(SimpleNamespace(
                description=row.get('label') or '',
                debit=amt if amt > 0 else _D('0'),
                credit=(-amt) if amt < 0 else _D('0'),
                line_type='other',
            ))
        return SimpleNamespace(lines=SimpleNamespace(all=lambda: lines))

    def test_not_superseded_counts_cost_lines(self):
        """لا LocalShipment مُرسمِل مرحّل → cost_lines تُحسب كما هي."""
        clr = self._mock_clearance([
            {'label': 'شحن محلي', 'amount': '1000.00', 'currency': 'ILS'},
        ])
        with patch('logistics.models.LocalShipment.objects') as mock_qs:
            mock_qs.filter.return_value.exists.return_value = False
            result = sum_local_shipping_from_clearance_cost_lines_ils(clr)
        self.assertEqual(result, Decimal('1000.00'))

    def test_superseded_returns_zero(self):
        """LocalShipment مُرسمِل مرحّل موجود → cost_lines تُستبعد (لا ازدواج)."""
        clr = self._mock_clearance([
            {'label': 'شحن محلي', 'amount': '1000.00', 'currency': 'ILS'},
        ])
        with patch('logistics.models.LocalShipment.objects') as mock_qs:
            mock_qs.filter.return_value.exists.return_value = True
            result = sum_local_shipping_from_clearance_cost_lines_ils(clr)
        self.assertEqual(result, Decimal('0'))

    def test_check_superseded_false_bypasses_guard(self):
        """تمرير _check_superseded=False يتجاوز الحارس حتى لو وُجد LocalShipment."""
        clr = self._mock_clearance([
            {'label': 'شحن محلي', 'amount': '1000.00', 'currency': 'ILS'},
        ])
        with patch('logistics.models.LocalShipment.objects') as mock_qs:
            mock_qs.filter.return_value.exists.return_value = True
            result = sum_local_shipping_from_clearance_cost_lines_ils(
                clr, _check_superseded=False,
            )
        self.assertEqual(result, Decimal('1000.00'))

    def test_helper_filters_on_posted_and_capitalized(self):
        """جوهر الحارس: الاستعلام يقيّد فعلاً بـ is_posted=True
        و capitalize_to_inventory=True (وإلا لا يمنع الازدواج فعلياً). الحارس صار
        يطابق أيضاً على شحنة التخليص (Q(clearance) | Q(shipment)) — التخليص يُمرَّر
        ضمن Q موضعي لا kwarg، والقيدان الماليان يبقيان kwargs."""
        from types import SimpleNamespace
        from django.db.models import Q
        mock_clearance = SimpleNamespace(id=5, shipment_id=7)
        with patch('logistics.models.LocalShipment.objects') as mock_qs:
            mock_qs.filter.return_value.exists.return_value = True
            clearance_local_transport_superseded_by_localshipment(mock_clearance)
        args, kwargs = mock_qs.filter.call_args
        self.assertIs(kwargs.get('is_posted'), True)
        self.assertIs(kwargs.get('capitalize_to_inventory'), True)
        # التخليص/الشحنة يُمرَّران عبر Q موضعي (شرط OR).
        self.assertTrue(any(isinstance(a, Q) for a in args))

    def test_helper_superseded_true(self):
        """helper يسترجع True عند وجود LocalShipment مرحّل ومُرسمِل."""
        from types import SimpleNamespace
        mock_clearance = SimpleNamespace(id=5)
        with patch('logistics.models.LocalShipment.objects') as mock_qs:
            mock_qs.filter.return_value.exists.return_value = True
            result = clearance_local_transport_superseded_by_localshipment(mock_clearance)
        self.assertTrue(result)

    def test_helper_superseded_false_no_localshipment(self):
        """helper يسترجع False عند عدم وجود LocalShipment."""
        from types import SimpleNamespace
        mock_clearance = SimpleNamespace(id=5)
        with patch('logistics.models.LocalShipment.objects') as mock_qs:
            mock_qs.filter.return_value.exists.return_value = False
            result = clearance_local_transport_superseded_by_localshipment(mock_clearance)
        self.assertFalse(result)
