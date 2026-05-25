"""P-E-1: DealItem extra fields — batch, expiry, warehouse persistence."""
from decimal import Decimal

from django.test import TestCase

from inventory.models import Product
from logistics.models import LogisticsDeal, LogisticsDealItem
from partners.models import Partner
from tenants.models import Currency, Tenant


class DealItemExtraFieldsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=60, CompanyName="DealItem Test")
        cls.currency = Currency.objects.create(
            CurrencyID=1, Code="ILS", Symbol="₪", IsBaseCurrency=True,
        )
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="Deal Partner",
            partner_type="Supplier",
        )
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="SKU-BATCH-001", name_ar="منتج اختبار",
            quantity_on_hand=100, avg_cost=Decimal("50.00"),
        )
        cls.deal = LogisticsDeal.objects.create(
            tenant=cls.tenant, ref_number="D-DI-001",
            partner=cls.partner, order_date="2026-02-01",
            currency=cls.currency, total_amount=10000,
        )

    def test_create_item_with_all_extra_fields(self):
        item = LogisticsDealItem.objects.create(
            deal=self.deal,
            product=self.product,
            quantity=Decimal("10"),
            unit_price=Decimal("100.00"),
            batch_number="B-2026-001",
            serial_number="SN-001",
            manufacture_number="MFG-001",
            expiry_date="2028-12-31",
            warehouse="المستودع الرئيسي",
            catalog_number="CAT-001",
        )
        self.assertEqual(item.batch_number, "B-2026-001")
        self.assertEqual(item.serial_number, "SN-001")
        self.assertEqual(item.manufacture_number, "MFG-001")
        # After create() without refresh_from_db, the attribute holds the raw
        # string we passed in; coerce both sides so this works regardless of
        # whether Django has parsed it back to a date yet.
        self.assertEqual(str(item.expiry_date), "2028-12-31")
        self.assertEqual(item.warehouse, "المستودع الرئيسي")
        self.assertEqual(item.catalog_number, "CAT-001")

    def test_item_defaults(self):
        item = LogisticsDealItem.objects.create(
            deal=self.deal,
            product=self.product,
            quantity=Decimal("5"),
            unit_price=Decimal("50.00"),
        )
        self.assertEqual(item.batch_number, "")
        self.assertEqual(item.serial_number, "")
        self.assertEqual(item.warehouse, "")
        self.assertEqual(item.catalog_number, "")
        self.assertIsNone(item.expiry_date)
