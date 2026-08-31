"""T-DRAFTPARTY: مورد ومنتجات **مبدئية** داخل عرض السعر.

القاعدة: العرض يقبل اسم مورد لم يُسجَّل واسم منتج غير موجود، ولا يُنشئ منهما شيئاً
في دفتر الشركاء ولا في فهرس المنتجات.

المسار المحلي (طلبية/فاتورة) ما يزال يُجسّدهما لحظة التحويل بمطابقة الاسم أولاً.
مسار **الصفقة** لم يعد كذلك منذ T113-1: العرض يُفتح محرّراً غير محفوظ، ويُحلّ
المورد والمنتج صراحةً قبل «حفظ» — فلا سجل ضمنيّ ولا سجل قبل الحفظ أصلاً.
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
            tenant=cls.tenant, sku='DRAFT-1', name_ar='منتج مسجَّل',
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
                'name_snapshot': 'منتج مكتوب يدوياً',
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
        # الشرط الجوهري: لا شريك جديد ولا منتج جديد قبل التحويل.
        self.assertEqual(Partner.objects.filter(tenant=self.tenant).count(), 1)
        self.assertEqual(Product.objects.filter(tenant=self.tenant).count(), 1)
        quotation = SupplierQuotation.objects.get(pk=response.data['id'])
        line = quotation.lines.get()
        self.assertIsNone(line.product_id)
        self.assertEqual(line.name_snapshot, 'منتج مكتوب يدوياً')
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

    def deal_payload(self, quotation_id, **overrides):
        payload = {
            'source_quotation': quotation_id,
            'partner': self.supplier.id,
            'order_date': '2026-07-26',
            'currency': self.currency.pk,
            'items': [{
                'product': self.product.id, 'seq': 1,
                'quantity': '2.000', 'unit_price': '10.0000',
                'name_snapshot': 'منتج مكتوب يدوياً',
            }],
        }
        payload.update(overrides)
        return payload

    def test_deal_creation_never_creates_a_partner_or_a_product(self):
        """T113-1 عكس القاعدة القديمة: مسار الصفقة لم يعد يُجسّد شيئاً ضمنياً.

        المورد والمنتج يُحلّان **صراحةً في المحرّر** قبل «حفظ»؛ الخادم لا يخترع
        شريكاً ولا منتجاً من اسمٍ مكتوب — فلا يتضاعف دفتر الشركاء بلا قرار.
        """
        created = self.create_quotation()
        quotation_id = created.data['id']

        response = self.client.post(
            '/api/logistics/deals/', self.deal_payload(quotation_id), format='json',
        )
        self.assertEqual(response.status_code, 201, response.content)

        self.assertEqual(Partner.objects.filter(tenant=self.tenant).count(), 1)
        self.assertEqual(Product.objects.filter(tenant=self.tenant).count(), 1)
        deal = LogisticsDeal.objects.get(source_quotation_id=quotation_id)
        self.assertEqual(deal.partner_id, self.supplier.id)
        self.assertEqual(deal.items.get().product_id, self.product.id)

    def test_deal_creation_leaves_the_quotation_as_it_was_written(self):
        """العرض أرشيف ما سُعِّر: الاسم المبدئي وبنوده تبقى كما كُتبت، والحالة وحدها تنقلب."""
        created = self.create_quotation()
        quotation_id = created.data['id']

        response = self.client.post(
            '/api/logistics/deals/', self.deal_payload(quotation_id), format='json',
        )
        self.assertEqual(response.status_code, 201, response.content)

        quotation = SupplierQuotation.objects.get(pk=quotation_id)
        self.assertIsNone(quotation.supplier_id)
        self.assertEqual(quotation.supplier_draft_name, 'مصنع لم نتعامل معه بعد')
        self.assertIsNone(quotation.lines.get().product_id)
        self.assertEqual(quotation.lines.get().name_snapshot, 'منتج مكتوب يدوياً')
        self.assertEqual(quotation.status, SupplierQuotation.STATUS_CONVERTED)

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


class QuotationMaterializationScanTest(APITestCase):
    """#21: مطابقة الاسم المطبَّع لا تُمسَح مرّةً لكل بند.

    التطبيع العربي بايثونيٌّ حتماً (لا SQL يوحّد الألف/الهمزة والتشكيل)، فمسحٌ
    داخل حلقة البنود يحمّل أصناف الشركة كلَّها لكل سطر — وهو نمط الانفجار الذي
    عضّ هذا المستودع مراراً. الفهرس يُبنى مرّةً، فعددُ مسحات جدول المنتجات لا
    يتغيّر بتغيّر عدد البنود.
    """

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=982, CompanyName='Scan Co')
        cls.user = User.objects.create_user(username='scan-quotes', password='x')
        UserCompanyMembership.objects.create(
            user=cls.user, tenant=cls.tenant, role='manager',
        )
        cls.currency = Currency.objects.create(
            Code='SCN', Name='Scan currency', IsBaseCurrency=False,
        )
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name='مورد المسح', partner_type='Supplier',
        )
        Product.objects.bulk_create([
            Product(tenant=cls.tenant, sku=f'SC-{i}', name_ar=f'صنف قائم {i}')
            for i in range(60)
        ])

    def _quotation_with(self, line_count):
        quotation = SupplierQuotation.objects.create(
            tenant=self.tenant, supplier=self.supplier,
            quotation_number=f'SQ-SCAN-{line_count}',
            quotation_date='2026-07-26', status='accepted',
            currency=self.currency, exchange_rate=Decimal('1'),
        )
        for seq in range(line_count):
            quotation.lines.create(
                tenant=self.tenant, seq=seq + 1,
                name_snapshot=f'صنف يدويّ {line_count}-{seq}',
                quantity=Decimal('1'), unit_price=Decimal('1'),
            )
        return quotation

    def _product_scans(self, quotation):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from logistics.services import materialize_quotation_draft_parties

        with CaptureQueriesContext(connection) as captured:
            materialize_quotation_draft_parties(quotation)
        return sum(
            1 for q in captured.captured_queries
            if q['sql'].lstrip().upper().startswith('SELECT')
            and 'products' in q['sql'].lower()
            and 'name_ar' in q['sql'].lower()
        )

    def test_name_scan_does_not_grow_with_line_count(self):
        few = self._product_scans(self._quotation_with(2))
        many = self._product_scans(self._quotation_with(8))
        assert few == many, (
            f'مسحُ الأسماء تضاعف مع البنود ({few} ← {many}) — الفهرس يُبنى لكل سطر.'
        )
        # وليس صفراً: صفرٌ يعني أن الحارس لا يقيس شيئاً أصلاً.
        assert few >= 1, 'الحارس لم يرصد مسحاً — تحقّق من مطابقة الاستعلام قبل الوثوق به.'
