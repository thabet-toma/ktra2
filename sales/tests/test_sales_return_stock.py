"""P-H-2: Sales return stock reconciliation — RETURN_IN/OUT movements."""
from decimal import Decimal

from django.test import TestCase

from inventory.models import Product, StockMovement
from inventory.services import record_stock_movement


class SalesReturnStockTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        from tenants.models import Tenant
        cls.tenant = Tenant.objects.create(TenantID=100, CompanyName="Ret Stock Test")

    def setUp(self):
        self.product = Product.objects.create(
            tenant=self.tenant, sku="RET-PROD", name_ar="منتج مرتجع",
            quantity_on_hand=Decimal("10"),
            avg_cost=Decimal("100.00"),
        )

    def test_sale_return_in_updates_wac_correctly(self):
        record_stock_movement(
            product=self.product,
            movement_type="RETURN_IN",
            quantity=Decimal("3"),
            unit_cost=Decimal("100.00"),
            movement_date="2026-06-01",
            tenant=self.tenant,
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity_on_hand, Decimal("13"))
        self.assertEqual(self.product.avg_cost, Decimal("100.00"))

    def test_purchase_return_out_reduces_stock(self):
        record_stock_movement(
            product=self.product,
            movement_type="RETURN_OUT",
            quantity=Decimal("3"),
            unit_cost=Decimal("100.00"),
            movement_date="2026-06-01",
            tenant=self.tenant,
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity_on_hand, Decimal("7"))

    def test_return_in_with_zero_cost_uses_avg(self):
        record_stock_movement(
            product=self.product,
            movement_type="RETURN_IN",
            quantity=Decimal("2"),
            unit_cost=Decimal("0"),
            movement_date="2026-06-01",
            tenant=self.tenant,
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.avg_cost, Decimal("100.00"))

    def test_return_creates_stock_movement_record(self):
        mv = record_stock_movement(
            product=self.product,
            movement_type="RETURN_IN",
            quantity=Decimal("5"),
            unit_cost=Decimal("100.00"),
            movement_date="2026-06-01",
            tenant=self.tenant,
        )
        self.assertIsNotNone(mv.id)
        self.assertEqual(mv.movement_type, "RETURN_IN")
        self.assertEqual(mv.quantity_before, Decimal("10"))
        self.assertEqual(mv.quantity_after, Decimal("15"))
