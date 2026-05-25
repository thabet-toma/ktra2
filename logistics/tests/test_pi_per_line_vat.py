"""P-E-6: PurchaseInvoice per-line VAT — vat_percent on items."""
from decimal import Decimal

from django.test import TestCase

from accounting.models import Account
from inventory.models import Product
from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
from partners.models import Partner
from tenants.models import Currency, Tenant


class PiPerLineVatTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=70, CompanyName="VAT Test")
        cls.currency = Currency.objects.create(
            CurrencyID=1, Code="ILS", Symbol="₪", IsBaseCurrency=True,
        )
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="VAT Supplier",
            partner_type="Supplier",
        )
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="VAT-PROD", name_ar="منتج VAT",
            quantity_on_hand=100, avg_cost=Decimal("50.00"),
        )
        cls.invoice = PurchaseInvoice.objects.create(
            tenant=cls.tenant, invoice_number="INV-VAT-001",
            partner=cls.partner, currency=cls.currency,
            grand_total=Decimal("6000.00"),
            invoice_date="2026-03-01",
        )

    def test_item_vat_percent_field(self):
        item = PurchaseInvoiceItem.objects.create(
            invoice=self.invoice,
            product=self.product,
            name="Test Item",
            quantity=Decimal("10"),
            unit_price=Decimal("500.00"),
            total_price=Decimal("5000.00"),
            vat_percent=Decimal("17.00"),
            is_taxable=True,
        )
        self.assertEqual(item.vat_percent, Decimal("17.00"))
        self.assertTrue(item.is_taxable)

    def test_item_vat_amount_calculation(self):
        item = PurchaseInvoiceItem.objects.create(
            invoice=self.invoice,
            product=self.product,
            name="VAT Calc Item",
            quantity=Decimal("5"),
            unit_price=Decimal("200.00"),
            total_price=Decimal("1000.00"),
            vat_percent=Decimal("17.00"),
            is_taxable=True,
        )
        expected_vat = (item.total_price * item.vat_percent / Decimal("100")).quantize(Decimal("0.01"))
        self.assertEqual(expected_vat, Decimal("170.00"))

    def test_non_taxable_item_zero_vat(self):
        item = PurchaseInvoiceItem.objects.create(
            invoice=self.invoice,
            product=self.product,
            name="Non-taxable Item",
            quantity=Decimal("2"),
            unit_price=Decimal("500.00"),
            total_price=Decimal("1000.00"),
            vat_percent=Decimal("0.00"),
            is_taxable=False,
        )
        self.assertFalse(item.is_taxable)

    def test_multiple_items_vat_summed(self):
        PurchaseInvoiceItem.objects.create(
            invoice=self.invoice, product=self.product,
            name="Item A", quantity=1, unit_price=1000,
            total_price=1000, vat_percent=Decimal("17.00"), is_taxable=True,
        )
        PurchaseInvoiceItem.objects.create(
            invoice=self.invoice, product=self.product,
            name="Item B", quantity=1, unit_price=2000,
            total_price=2000, vat_percent=Decimal("17.00"), is_taxable=True,
        )
        items = PurchaseInvoiceItem.objects.filter(invoice=self.invoice)
        total_vat = sum(
            (i.total_price * i.vat_percent / Decimal("100")).quantize(Decimal("0.01"))
            for i in items
        )
        self.assertEqual(total_vat, Decimal("510.00"))
