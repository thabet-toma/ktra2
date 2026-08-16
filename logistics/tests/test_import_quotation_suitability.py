"""T-IMPOFFER — عرض سعر الاستيراد: مصدر الطلب، مبلغ الشحن، وقرار الملاءمة.

المالك: «عرض السعر بالاستيراد لازم أقدر أحوّله لصفقة، وإله حالات مبيّنة —
ملائم/غير ملائم مع سبب، وغير الملائم يكون مشطوب. كمان فش مبلغ الشحن، وبدي
خانة رابط علي بابا ورقم تواصل مع المورد، وبدي أرفع ملف العرض.»

القرار ليس تسميةً فقط: «غير ملائم» بلا سبب لا يُقبل — العرض المرفوض بلا سبب
لا يعلّم أحداً شيئاً بعد شهر.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from inventory.models import Product
from logistics.models import LogisticsDeal, SupplierQuotation
from partners.models import Partner
from tenants.models import Currency, Tenant, UserCompanyMembership


class ImportQuotationSuitabilityTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=983, CompanyName='Import Offers Co')
        cls.currency = Currency.objects.create(
            Code='IQT', Name='Import quote currency', IsBaseCurrency=False,
        )
        cls.user = User.objects.create_user(username='import-offers', password='x')
        UserCompanyMembership.objects.create(
            user=cls.user, tenant=cls.tenant, role='manager',
        )
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name='Foreign Factory', partner_type='Supplier',
            supplier_scope=Partner.SUPPLIER_SCOPE_INTERNATIONAL,
        )
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku='IQ-ITEM-1', name_ar='صنف عرض استيراد',
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def payload(self, **overrides):
        body = {
            'scope': 'import',
            'supplier': self.supplier.id,
            'quotation_date': '2026-07-30',
            'currency': self.currency.pk,
            'exchange_rate': '1.000000',
            'discount_amount': '0',
            'tax_rate': '0',
            'shipping_cost_estimate': '150.00',
            'is_shipping_included': False,
            'alibaba_link': 'https://www.alibaba.com/product-detail/x.html',
            'supplier_contact': '+8613800000000',
            'attachments': [
                {'name': 'offer.pdf', 'url': 'https://cdn.example/offer.pdf',
                 'type': 'application/pdf', 'size': 2048},
            ],
            'lines': [{
                'product': self.product.id,
                'seq': 1,
                'quantity': '10.000',
                'unit_price': '20.0000',
            }],
        }
        body.update(overrides)
        return body

    def create_quote(self, **overrides):
        response = self.client.post(
            '/api/logistics/supplier-quotations/', self.payload(**overrides),
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response

    def test_source_fields_and_attachments_round_trip(self):
        created = self.create_quote()
        self.assertEqual(
            created.data['alibaba_link'],
            'https://www.alibaba.com/product-detail/x.html',
        )
        self.assertEqual(created.data['supplier_contact'], '+8613800000000')
        self.assertEqual(len(created.data['attachments']), 1)
        self.assertEqual(created.data['attachments'][0]['name'], 'offer.pdf')

        fetched = self.client.get(
            f"/api/logistics/supplier-quotations/{created.data['id']}/",
        )
        self.assertEqual(fetched.status_code, 200)
        self.assertEqual(fetched.data['attachments'][0]['url'],
                         'https://cdn.example/offer.pdf')

    def test_order_name_description_and_multiple_attachments_round_trip_in_order(self):
        attachments = [
            {'name': 'terms.pdf', 'url': 'https://cdn.example/terms.pdf',
             'type': 'application/pdf', 'size': 1200},
            {'name': 'front.jpg', 'url': 'https://cdn.example/front.jpg',
             'type': 'image/jpeg', 'size': 2400},
            {'name': 'side.png', 'url': 'https://cdn.example/side.png',
             'type': 'image/png', 'size': 1800},
        ]
        created = self.create_quote(
            order_name='طلبية أثاث مكتبي',
            order_description='مكاتب من خشب زان مع خزائن جانبية',
            attachments=attachments,
        )

        self.assertEqual(created.data['order_name'], 'طلبية أثاث مكتبي')
        self.assertEqual(
            created.data['order_description'],
            'مكاتب من خشب زان مع خزائن جانبية',
        )
        self.assertEqual(
            [item['url'] for item in created.data['attachments']],
            [item['url'] for item in attachments],
        )

    def test_list_search_matches_order_name_and_description(self):
        first = self.create_quote(
            order_name='طلبية أثاث مكتبي',
            order_description='مكاتب من خشب زان',
        )
        self.create_quote(
            order_name='طلبية إنارة',
            order_description='مصابيح سقفية',
        )

        by_name = self.client.get(
            '/api/logistics/supplier-quotations/?scope=import&search=أثاث',
        )
        self.assertEqual(by_name.status_code, 200, by_name.content)
        self.assertEqual([row['id'] for row in by_name.data], [first.data['id']])

        by_description = self.client.get(
            '/api/logistics/supplier-quotations/?scope=import&search=خشب زان',
        )
        self.assertEqual(by_description.status_code, 200, by_description.content)
        self.assertEqual(
            [row['id'] for row in by_description.data],
            [first.data['id']],
        )

    def test_shipping_estimate_is_added_to_grand_total(self):
        created = self.create_quote()
        # 10 × 20 = 200 بنوداً + 150 شحناً غير مشمول
        self.assertEqual(Decimal(created.data['subtotal']), Decimal('200.00'))
        self.assertEqual(Decimal(created.data['grand_total']), Decimal('350.00'))

        included = self.create_quote(is_shipping_included=True)
        self.assertEqual(Decimal(included.data['grand_total']), Decimal('200.00'))

    def test_unsuitable_requires_a_reason(self):
        created = self.create_quote()
        quote_id = created.data['id']

        without_reason = self.client.patch(
            f'/api/logistics/supplier-quotations/{quote_id}/',
            {'status': 'rejected'}, format='json',
        )
        self.assertEqual(without_reason.status_code, 400)
        self.assertIn('decision_reason', without_reason.data)

        with_reason = self.client.patch(
            f'/api/logistics/supplier-quotations/{quote_id}/',
            {'status': 'rejected', 'decision_reason': 'السعر أعلى من السوق بـ20%'},
            format='json',
        )
        self.assertEqual(with_reason.status_code, 200, with_reason.content)
        self.assertEqual(with_reason.data['decision_reason'],
                         'السعر أعلى من السوق بـ20%')

    def test_local_purchase_offer_keeps_the_reason_optional(self):
        """حارس نطاق: مطلب المالك كان عن الاستيراد — لا نغيّر شاشة الشراء المحلي."""
        local = self.client.post(
            '/api/logistics/supplier-quotations/',
            self.payload(scope='local', tax_rate='0'), format='json',
        )
        self.assertEqual(local.status_code, 201, local.content)
        rejected = self.client.patch(
            f"/api/logistics/supplier-quotations/{local.data['id']}/",
            {'status': 'rejected'}, format='json',
        )
        self.assertEqual(rejected.status_code, 200, rejected.content)

    def test_reason_is_cleared_when_offer_becomes_suitable(self):
        created = self.create_quote()
        quote_id = created.data['id']
        self.client.patch(
            f'/api/logistics/supplier-quotations/{quote_id}/',
            {'status': 'rejected', 'decision_reason': 'مدة التسليم طويلة'},
            format='json',
        )
        accepted = self.client.patch(
            f'/api/logistics/supplier-quotations/{quote_id}/',
            {'status': 'accepted'}, format='json',
        )
        self.assertEqual(accepted.status_code, 200, accepted.content)
        self.assertEqual(accepted.data['decision_reason'], '')

    def test_conversion_carries_source_link_and_shipping_to_the_deal(self):
        created = self.create_quote()
        quote_id = created.data['id']
        self.client.patch(
            f'/api/logistics/supplier-quotations/{quote_id}/',
            {'status': 'accepted'}, format='json',
        )
        # T113-1: الصفقة تُحفظ من المحرّر ومعها مصدرها — لا تحويل بضغطة.
        converted = self.client.post('/api/logistics/deals/', {
            'source_quotation': quote_id,
            'partner': self.supplier.id,
            'order_date': '2026-07-30',
            'currency': self.currency.pk,
            'shipping_cost_estimate': '150.00',
            'is_shipping_included': False,
            'alibaba_link': 'https://www.alibaba.com/product-detail/x.html',
            'items': [{
                'product': self.product.id, 'seq': 1,
                'quantity': '2.000', 'unit_price': '100.0000',
            }],
        }, format='json')
        self.assertEqual(converted.status_code, 201, converted.content)
        deal = LogisticsDeal.objects.get(source_quotation_id=quote_id)
        self.assertEqual(deal.alibaba_link,
                         'https://www.alibaba.com/product-detail/x.html')
        self.assertEqual(deal.shipping_cost_estimate, Decimal('150.00'))
        # النسب يُشتق من العرض خادمياً لا من حمولة العميل.
        self.assertEqual(deal.original_offer_number, created.data['quotation_number'])
        self.assertEqual(deal.price_offer_id, str(quote_id))

        # المستند المحوَّل يعرض رقم الصفقة الناتجة كي لا يبدو التحويل صامتاً.
        reread = self.client.get(f'/api/logistics/supplier-quotations/{quote_id}/')
        self.assertEqual(reread.data['converted_deal']['ref_number'], deal.ref_number)
        self.assertEqual(
            SupplierQuotation.objects.get(pk=quote_id).status,
            SupplierQuotation.STATUS_CONVERTED,
        )
