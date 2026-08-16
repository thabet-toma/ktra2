from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from inventory.models import Product
from logistics.models import (
    LogisticsDeal,
    SupplierQuotation,
)
from partners.models import Partner
from tenants.models import Currency, Tenant, UserCompanyMembership


class SupplierQuotationAPITest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=991, CompanyName='Quote Co')
        cls.other_tenant = Tenant.objects.create(TenantID=992, CompanyName='Other Quote Co')
        cls.currency = Currency.objects.create(
            Code='QUS', Name='Quote currency', IsBaseCurrency=False,
        )
        cls.user = User.objects.create_user(username='supplier-quotes', password='x')
        UserCompanyMembership.objects.create(
            user=cls.user, tenant=cls.tenant, role='manager',
        )
        UserCompanyMembership.objects.create(
            user=cls.user, tenant=cls.other_tenant, role='manager',
        )
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name='Factory A', partner_type='Supplier',
        )
        cls.other_supplier = Partner.objects.create(
            tenant=cls.other_tenant, name='Factory B', partner_type='Supplier',
        )
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku='QUOTE-1', name_ar='صنف عرض',
        )
        cls.other_product = Product.objects.create(
            tenant=cls.other_tenant, sku='QUOTE-OTHER-1', name_ar='صنف آخر',
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def payload(self, **overrides):
        payload = {
            'scope': 'import',
            'supplier': self.supplier.id,
            'quotation_date': '2026-07-26',
            'valid_until': '2026-08-26',
            'status': 'accepted',
            'currency': self.currency.pk,
            'exchange_rate': '3.650000',
            'discount_amount': '2.00',
            'tax_rate': '0',
            'shipping_cost_estimate': '3.00',
            'is_shipping_included': False,
            'incoterms': 'FOB',
            'shipping_method': 'Sea',
            'payment_method': 'T/T',
            'production_days': 20,
            'delivery_days': 30,
            'total_cbm': '1.250',
            'total_weight_kg': '40.000',
            'notes': 'عرض استيراد تجريبي',
            'lines': [{
                'product': self.product.id,
                'seq': 1,
                'quantity': '2.500',
                'unit_price': '10.0000',
                'description_line': 'تفصيل الصنف',
            }],
        }
        payload.update(overrides)
        return payload

    def test_create_recalculates_totals_and_generates_number(self):
        response = self.client.post(
            '/api/logistics/supplier-quotations/',
            self.payload(),
            format='json',
        )

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data['quotation_number'], 'IQ-0001')
        self.assertEqual(Decimal(response.data['subtotal']), Decimal('25.00'))
        self.assertEqual(Decimal(response.data['tax_amount']), Decimal('0.00'))
        self.assertEqual(Decimal(response.data['grand_total']), Decimal('26.00'))
        quotation = SupplierQuotation.objects.get(pk=response.data['id'])
        self.assertEqual(quotation.tenant, self.tenant)
        self.assertEqual(quotation.lines.get().name_snapshot, 'صنف عرض')

    def test_related_supplier_and_products_are_tenant_scoped(self):
        supplier_response = self.client.post(
            '/api/logistics/supplier-quotations/',
            self.payload(supplier=self.other_supplier.id),
            format='json',
        )
        self.assertEqual(supplier_response.status_code, 400, supplier_response.content)
        self.assertIn('supplier', supplier_response.data)

        lines = self.payload()['lines']
        lines[0]['product'] = self.other_product.id
        product_response = self.client.post(
            '/api/logistics/supplier-quotations/',
            self.payload(lines=lines),
            format='json',
        )
        self.assertEqual(product_response.status_code, 400, product_response.content)
        self.assertIn('lines', product_response.data)

    def deal_payload(self, quotation_id, **overrides):
        """حمولة «حفظ» في محرّر الصفقة: الصفقة كاملة ومعها عرضها المصدر (T113-1)."""
        payload = {
            'source_quotation': quotation_id,
            'partner': self.supplier.id,
            'order_date': '2026-07-26',
            'currency': self.currency.pk,
            'currency_rate': '3.650000',
            'discount_amount': '2.00',
            'shipping_cost_estimate': '3.00',
            'is_shipping_included': False,
            'items': [{
                'product': self.product.id,
                'seq': 1,
                'quantity': '2.500',
                'unit_price': '10.0000',
                'name_snapshot': 'صنف عرض',
                'description_line': 'تفصيل الصنف',
            }],
        }
        payload.update(overrides)
        return payload

    def test_import_conversion_is_atomic_and_idempotent(self):
        create_response = self.client.post(
            '/api/logistics/supplier-quotations/',
            self.payload(),
            format='json',
        )
        self.assertEqual(create_response.status_code, 201, create_response.content)
        quotation_id = create_response.data['id']

        first = self.client.post(
            '/api/logistics/deals/', self.deal_payload(quotation_id), format='json',
        )
        self.assertEqual(first.status_code, 201, first.content)
        deal_id = first.data['id']

        # الحفظ الثاني لنفس المصدر (تبويب ثانٍ) يرتد ومعه رقم الصفقة القائمة.
        second = self.client.post(
            '/api/logistics/deals/', self.deal_payload(quotation_id), format='json',
        )
        self.assertEqual(second.status_code, 400, second.content)
        self.assertIn(first.data['ref_number'], str(second.data['source_quotation']))
        self.assertEqual(
            LogisticsDeal.objects.filter(source_quotation_id=quotation_id).count(), 1,
        )

        quotation = SupplierQuotation.objects.get(pk=quotation_id)
        deal = LogisticsDeal.objects.get(pk=deal_id)
        self.assertEqual(quotation.status, SupplierQuotation.STATUS_CONVERTED)
        self.assertEqual(deal.stage, LogisticsDeal.STAGE_DRAFT)
        self.assertEqual(deal.partner, self.supplier)
        self.assertEqual(deal.total_amount, Decimal('26.00'))
        self.assertEqual(deal.items.get().product, self.product)
        self.assertEqual(deal.items.get().name_snapshot, 'صنف عرض')

    def test_conversion_rejects_local_or_unaccepted_quote(self):
        local = self.client.post(
            '/api/logistics/supplier-quotations/',
            self.payload(scope='local', tax_rate='16.00'),
            format='json',
        )
        self.assertEqual(local.status_code, 201, local.content)
        local_convert = self.client.post(
            '/api/logistics/deals/',
            self.deal_payload(local.data['id']),
            format='json',
        )
        self.assertEqual(local_convert.status_code, 400, local_convert.content)
        self.assertIn('source_quotation', local_convert.data)

        draft = self.client.post(
            '/api/logistics/supplier-quotations/',
            self.payload(status='draft'),
            format='json',
        )
        self.assertEqual(draft.status_code, 201, draft.content)
        draft_convert = self.client.post(
            '/api/logistics/deals/',
            self.deal_payload(draft.data['id']),
            format='json',
        )
        self.assertEqual(draft_convert.status_code, 400, draft_convert.content)
        self.assertIn('source_quotation', draft_convert.data)
        self.assertEqual(LogisticsDeal.objects.count(), 0)
