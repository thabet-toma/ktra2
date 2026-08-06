"""T-DRAFTPARTY: مورد وأصناف **مبدئية** داخل عرض السعر.

القاعدة: العرض يقبل اسم مورد لم يُسجَّل واسم صنف غير موجود، ولا يُنشئ منهما شيئاً
في دفتر الشركاء ولا في فهرس الأصناف — الإنشاء يقع **لحظة التحويل** فقط، وبمطابقة
الاسم أولاً كي لا يتضاعف مورد أو صنف قائم.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from inventory.models import Product
from logistics.models import LogisticsDeal, PurchaseOrder, SupplierQuotation
from partners.models import Partner
from tenants.models import Currency, Tenant, UserCompanyMembership


class QuotationDraftPartiesTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=981, CompanyName='Draft Co')
        cls.currency = Currency.objects.create(
            Code='DRF', Name='Draft currency', IsBaseCurrency=False,
        )
        cls.user = User.objects.create_user(username='draft-quotes', password='x')
        UserCompanyMembership.objects.create(
            user=cls.user, tenant=cls.tenant, role='manager',
        )
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name='مورد مسجَّل', partner_type='Supplier',
        )
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku='DRAFT-1', name_ar='صنف مسجَّل',
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def payload(self, **overrides):
        payload = {
            'scope': 'import',
            'supplier': None,
            'supplier_draft_name': 'مصنع لم نتعامل معه بعد',
            'quotation_date': '2026-07-26',
            'status': 'accepted',
            'currency': self.currency.pk,
            'exchange_rate': '3.650000',
            'discount_amount': '0',
            'tax_rate': '0',
            'shipping_cost_estimate': '0',
            'is_shipping_included': False,
            'lines': [{
                'seq': 1,
                'name_snapshot': 'صنف مكتوب يدوياً',
                'quantity': '2.000',
                'unit_price': '10.0000',
            }],
        }
        payload.update(overrides)
        return payload

    def create_quotation(self, **overrides):
        response = self.client.post(
            '/api/logistics/supplier-quotations/',
            self.payload(**overrides),
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response

    def test_draft_supplier_and_product_are_saved_without_creating_records(self):
        response = self.create_quotation()

        self.assertIsNone(response.data['supplier'])
        self.assertEqual(response.data['supplier_name'], 'مصنع لم نتعامل معه بعد')
        self.assertTrue(response.data['is_draft_supplier'])
        # الشرط الجوهري: لا شريك جديد ولا صنف جديد قبل التحويل.
        self.assertEqual(Partner.objects.filter(tenant=self.tenant).count(), 1)
        self.assertEqual(Product.objects.filter(tenant=self.tenant).count(), 1)
        quotation = SupplierQuotation.objects.get(pk=response.data['id'])
        line = quotation.lines.get()
        self.assertIsNone(line.product_id)
        self.assertEqual(line.name_snapshot, 'صنف مكتوب يدوياً')
        self.assertEqual(Decimal(response.data['grand_total']), Decimal('20.00'))

    def test_quotation_without_any_party_is_rejected(self):
        response = self.client.post(
            '/api/logistics/supplier-quotations/',
            self.payload(supplier=None, supplier_draft_name=''),
            format='json',
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn('supplier', response.data)

    def test_line_without_product_or_name_is_rejected(self):
        response = self.client.post(
            '/api/logistics/supplier-quotations/',
            self.payload(lines=[{
                'seq': 1, 'quantity': '1.000', 'unit_price': '5.0000',
            }]),
            format='json',
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn('lines', response.data)

    def test_registered_supplier_clears_any_draft_name(self):
        response = self.create_quotation(
            supplier=self.supplier.id, supplier_draft_name='اسم مبدئي زائد',
        )
        quotation = SupplierQuotation.objects.get(pk=response.data['id'])
        self.assertEqual(quotation.supplier_id, self.supplier.id)
        self.assertEqual(quotation.supplier_draft_name, '')
        self.assertFalse(response.data['is_draft_supplier'])

    def test_import_conversion_materializes_supplier_and_product(self):
        created = self.create_quotation()
        quotation_id = created.data['id']

        response = self.client.post(
            f'/api/logistics/supplier-quotations/{quotation_id}/convert-to-import-deal/',
            {}, format='json',
        )
        self.assertEqual(response.status_code, 201, response.content)

        quotation = SupplierQuotation.objects.get(pk=quotation_id)
        self.assertIsNotNone(quotation.supplier_id)
        self.assertEqual(quotation.supplier.name, 'مصنع لم نتعامل معه بعد')
        self.assertEqual(
            quotation.supplier.supplier_scope, Partner.SUPPLIER_SCOPE_INTERNATIONAL,
        )
        self.assertEqual(quotation.supplier_draft_name, '')
        line = quotation.lines.get()
        self.assertIsNotNone(line.product_id)
        self.assertEqual(line.product.name_ar, 'صنف مكتوب يدوياً')
        deal = LogisticsDeal.objects.get(source_quotation_id=quotation_id)
        self.assertEqual(deal.partner_id, quotation.supplier_id)
        self.assertEqual(deal.items.get().product_id, line.product_id)

    def test_conversion_reuses_existing_records_matched_by_name(self):
        created = self.create_quotation(
            supplier_draft_name='مورد مسجَّل',
            lines=[{
                'seq': 1,
                'name_snapshot': 'صنف مسجَّل',
                'quantity': '1.000',
                'unit_price': '7.0000',
            }],
        )
        quotation_id = created.data['id']

        response = self.client.post(
            f'/api/logistics/supplier-quotations/{quotation_id}/convert-to-import-deal/',
            {}, format='json',
        )
        self.assertEqual(response.status_code, 201, response.content)

        quotation = SupplierQuotation.objects.get(pk=quotation_id)
        self.assertEqual(quotation.supplier_id, self.supplier.id)
        self.assertEqual(quotation.lines.get().product_id, self.product.id)
        self.assertEqual(Partner.objects.filter(tenant=self.tenant).count(), 1)
        self.assertEqual(Product.objects.filter(tenant=self.tenant).count(), 1)

    def test_local_order_conversion_materializes_too(self):
        created = self.create_quotation(scope='local')
        quotation_id = created.data['id']

        response = self.client.post(
            f'/api/logistics/supplier-quotations/{quotation_id}/convert-to-purchase-order/',
            {}, format='json',
        )
        self.assertEqual(response.status_code, 201, response.content)

        order = PurchaseOrder.objects.get(quotation_id=quotation_id)
        quotation = SupplierQuotation.objects.get(pk=quotation_id)
        self.assertEqual(order.supplier_id, quotation.supplier_id)
        self.assertEqual(
            quotation.supplier.supplier_scope, Partner.SUPPLIER_SCOPE_LOCAL,
        )
        self.assertEqual(order.lines.get().product_id, quotation.lines.get().product_id)
        self.assertIsNotNone(order.lines.get().product_id)
