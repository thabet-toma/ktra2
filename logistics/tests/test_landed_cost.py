"""
اختبارات ثبات landed cost:
sum(landed_line_total_ils) == deal_val_ils + allocated_freight + allocated_clearance

تشغيل: python manage.py test logistics.tests.test_landed_cost
"""
from decimal import Decimal

from django.test import SimpleTestCase

from logistics.landed_cost import (
    Q2,
    compute_deal_invoice_lines,
    distribute_by_weights,
)


class _MockItemsQS:
    """محاكاة QuerySet للأصناف — يدعم select_related().all() و __iter__."""
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
        """صنف واحد: لا انحراف ممكن."""
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
