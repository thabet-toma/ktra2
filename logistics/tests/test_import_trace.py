"""M5 — backward cost trace for import invoices.

Full chain Invoice line → Deal → Shipment(freight) → Clearance(customs) → Transport,
so every cost on every line is traceable to its source (target §4.6).
"""
from decimal import Decimal

from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

from tenants.models import Tenant, Currency, UserCompanyMembership
from partners.models import Partner
from logistics.models import (
    LogisticsDeal, LogisticsDealItem, LogisticsShipment,
    LogisticsClearance, LogisticsClearanceLine, LocalShipment,
    PurchaseInvoice, PurchaseInvoiceItem,
)
from inventory.models import Product


class ImportTraceTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=970, CompanyName='M5 Co', import_enabled=True)
        cls.cur, _ = Currency.objects.get_or_create(
            Code='ILS', defaults={'Symbol': '₪', 'IsBaseCurrency': True})
        cls.user = User.objects.create_user(username='m5_user', password='x')
        Token.objects.create(user=cls.user)
        UserCompanyMembership.objects.create(user=cls.user, tenant=cls.tenant, role='manager')
        cls.partner = Partner.objects.create(tenant=cls.tenant, name='مصنع', partner_type='Supplier')
        cls.carrier = Partner.objects.create(tenant=cls.tenant, name='ناقل', partner_type='Supplier')
        cls.product = Product.objects.create(tenant=cls.tenant, sku='M5-1', name_ar='صنف')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def _build_flow(self):
        deal = LogisticsDeal.objects.create(
            tenant=self.tenant, ref_number='D-5001', partner=self.partner,
            order_date='2026-06-01', currency=self.cur, total_amount=Decimal('5000'),
            total_cbm=Decimal('4'))
        LogisticsDealItem.objects.create(
            deal=deal, product=self.product, quantity=Decimal('10'), unit_price=Decimal('500'))
        # Shipment via the create-from-deals action (freight cbm @ 100 → 400)
        resp = self.client.post(
            '/api/logistics/shipments/create-from-deals/',
            {'deal_ids': [deal.id], 'chargeable_unit': 'cbm', 'freight_rate': 100},
            format='json')
        self.assertEqual(resp.status_code, 201, resp.content)
        shipment = LogisticsShipment.objects.get(pk=resp.data['id'])
        clr = LogisticsClearance.objects.create(
            tenant=self.tenant, shipment=shipment, declaration_number='DECL-5')
        LogisticsClearanceLine.objects.create(
            clearance=clr, seq=1, line_type='vat', description='ضريبة',
            debit=Decimal('900'), credit=Decimal('0'))
        LocalShipment.objects.create(
            tenant=self.tenant, clearance=clr, shipment=shipment, carrier=self.carrier,
            amount=Decimal('200'), currency=self.cur, capitalize_to_inventory=True)
        inv = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number='IMP-5001', partner=self.partner,
            deal=deal, shipment=shipment, clearance=clr, currency=self.cur,
            invoice_type=PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL,
            grand_total=Decimal('7000'),
            import_shipment_remaining_rate=Decimal('3.6'), import_use_cost_lines=True)
        PurchaseInvoiceItem.objects.create(
            invoice=inv, product=self.product, name='صنف',
            quantity=Decimal('10'), unit_price=Decimal('500'),
            total_price=Decimal('5000'),
            landed_unit_price_ils=Decimal('700'), landed_line_total_ils=Decimal('7000'))
        return deal, shipment, clr, inv

    def test_trace_full_chain(self):
        deal, shipment, clr, inv = self._build_flow()
        resp = self.client.get(f'/api/logistics/purchase-invoices/{inv.id}/trace/')
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.data

        self.assertEqual(data['invoice']['id'], inv.id)
        self.assertEqual(data['deal']['ref_number'], 'D-5001')
        self.assertEqual(data['shipment']['chargeable_unit'], 'cbm')
        self.assertEqual(data['shipment']['deal_allocated_freight_usd'], 400.0)
        self.assertEqual(data['clearance']['declaration_number'], 'DECL-5')
        self.assertEqual(data['clearance']['pool_total_ils'], 900.0)
        # single deal → full customs pool
        self.assertEqual(data['clearance']['deal_allocated_customs_ils'], 900.0)

        self.assertEqual(len(data['transport']), 1)
        self.assertEqual(data['transport'][0]['amount'], 200.0)

        self.assertEqual(len(data['lines']), 1)
        line = data['lines'][0]
        self.assertEqual(line['merch_ils'], 5000.0)
        self.assertEqual(line['landed_total_ils'], 7000.0)
        self.assertEqual(line['logistics_ils'], 2000.0)  # 7000 − 5000

    def test_trace_local_invoice_minimal(self):
        """A plain local invoice (no deal/shipment) still traces its own lines."""
        inv = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number='LOC-1', partner=self.partner,
            currency=self.cur, grand_total=Decimal('100'))
        PurchaseInvoiceItem.objects.create(
            invoice=inv, name='خدمة', quantity=Decimal('1'),
            unit_price=Decimal('100'), total_price=Decimal('100'))
        resp = self.client.get(f'/api/logistics/purchase-invoices/{inv.id}/trace/')
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertIsNone(resp.data['deal'])
        self.assertIsNone(resp.data['shipment'])
        self.assertEqual(len(resp.data['lines']), 1)
