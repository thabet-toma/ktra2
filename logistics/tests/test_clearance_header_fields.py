"""P-F-1: Clearance header Aseel enrichment fields."""
from decimal import Decimal

from django.test import TestCase

from logistics.models import (
    LogisticsClearance,
    LogisticsClearanceLine,
    LogisticsDeal,
    LogisticsShipment,
)
from partners.models import Partner
from tenants.models import Currency, Tenant


class ClearanceHeaderFieldsTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=80, CompanyName="CL Hdr Test")
        cls.currency = Currency.objects.create(
            CurrencyID=1, Code="ILS", Symbol="₪", IsBaseCurrency=True,
        )
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="CL Partner",
            partner_type="Supplier",
        )
        cls.deal = LogisticsDeal.objects.create(
            tenant=cls.tenant, ref_number="D-CL-HDR",
            partner=cls.partner, order_date="2026-04-01",
            currency=cls.currency, total_amount=5000,
        )
        cls.shipment = LogisticsShipment.objects.create(
            tenant=cls.tenant, shipment_number="SH-CL-HDR",
        )

    def setUp(self):
        self.broker = Partner.objects.create(
            tenant=self.tenant, name="Broker Co",
            partner_type="Supplier",
        )

    def test_clearance_with_all_header_fields(self):
        clearance = LogisticsClearance.objects.create(
            tenant=self.tenant,
            shipment=self.shipment,
            book_number=1,
            customs_broker=self.broker,
            declaration_number="DEC-001",
            clearance_date="2026-04-15",
            status='Processing',
            notes="ملاحظات التخليص",
            transaction_time="10:30:00",
            second_date="2026-04-10",
            licensed_dealer_no="LIC-12345",
            settlement_invoice_number="STL-001",
            currency=self.currency,
            exchange_rate=Decimal("1.0"),
            subtotal_no_vat=Decimal("4000.00"),
            vat_total=Decimal("680.00"),
            grand_total=Decimal("4680.00"),
            editable=True,
        )
        self.assertEqual(clearance.book_number, 1)
        self.assertEqual(clearance.customs_broker, self.broker)
        self.assertEqual(clearance.declaration_number, "DEC-001")
        self.assertEqual(clearance.licensed_dealer_no, "LIC-12345")
        self.assertEqual(clearance.settlement_invoice_number, "STL-001")
        self.assertEqual(clearance.subtotal_no_vat, Decimal("4000.00"))
        self.assertEqual(clearance.vat_total, Decimal("680.00"))
        self.assertEqual(clearance.grand_total, Decimal("4680.00"))
        self.assertTrue(clearance.editable)

    def test_clearance_editable_flag(self):
        clearance = LogisticsClearance.objects.create(
            tenant=self.tenant, shipment=self.shipment,
            status='Cleared', currency=self.currency,
            customs_broker=self.broker, editable=False,
        )
        self.assertFalse(clearance.editable)
