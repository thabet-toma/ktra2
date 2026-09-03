"""ISSUE #116 (مواصفة #108 §٨) — المقارنة والترسية: مستويان.

سطح DRF وحده، على نمط `test_purchase_rfq.py` (ISSUE #112). يغطي:
- الترسية: تنتج أمر شراء أو فاتورة شراء بحسب `PurchaseSettings.use_purchase_orders`.
- المصفوفة (`comparison/`): بندٌ بلا سعرٍ تقديريّ يعود بلا نسبة (فارغ لا صفر)،
  بندٌ لم يُسعّره موردٌ بعينه لا يُحتسَب صفراً في إجماليّه، توحيد العملات
  بسعر صرفٍ صريح، ولا حقل شحنٍ في المخرَج إطلاقاً.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from inventory.models import Product
from logistics.models import (
    PurchaseInvoice,
    PurchaseOrder,
    PurchaseRFQ,
    PurchaseRFQRecipient,
    PurchaseSettings,
    SupplierQuotation,
    SupplierQuotationLine,
)
from logistics.services import submit_rfq_supplier_quote
from partners.models import Partner
from tenants.models import Currency, Tenant, UserCompanyMembership


class RfqAwardAndComparisonTestBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=891, CompanyName='RFQ Award Co')
        cls.other_tenant = Tenant.objects.create(TenantID=892, CompanyName='Other RFQ Award Co')
        cls.base_currency = Currency.objects.create(
            Code='ILS', Name='New Shekel', IsBaseCurrency=True,
        )
        cls.usd = Currency.objects.create(Code='USD', Name='US Dollar', IsBaseCurrency=False)
        cls.user = User.objects.create_user(username='rfq-award-owner', password='x')
        UserCompanyMembership.objects.create(user=cls.user, tenant=cls.tenant, role='manager')
        UserCompanyMembership.objects.create(user=cls.user, tenant=cls.other_tenant, role='manager')
        cls.supplier_a = Partner.objects.create(
            tenant=cls.tenant, name='Supplier A', partner_type='Supplier',
        )
        cls.supplier_b = Partner.objects.create(
            tenant=cls.tenant, name='Supplier B', partner_type='Supplier',
        )
        cls.product1 = Product.objects.create(
            tenant=cls.tenant, sku='RFQ-AW-1', name_ar='صنف أول',
        )
        cls.product2 = Product.objects.create(
            tenant=cls.tenant, sku='RFQ-AW-2', name_ar='صنف ثانٍ',
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def create_and_send_rfq(self, *, estimated_prices=(None, None), suppliers=None):
        """طلبيةٌ ببندين، تُرسَل مباشرةً للموردين المُمرَّرين."""
        suppliers = suppliers if suppliers is not None else [self.supplier_a]
        payload = {
            'scope': 'local',
            'rfq_date': '2026-09-01',
            'lines': [
                {
                    'product': self.product1.id, 'seq': 1, 'quantity': '5.000',
                    'unit_of_measure': 'حبة',
                    'estimated_price': str(estimated_prices[0]) if estimated_prices[0] is not None else None,
                },
                {
                    'product': self.product2.id, 'seq': 2, 'quantity': '2.000',
                    'unit_of_measure': 'كرتون',
                    'estimated_price': str(estimated_prices[1]) if estimated_prices[1] is not None else None,
                },
            ],
        }
        created = self.client.post('/api/logistics/purchase-rfqs/', payload, format='json')
        self.assertEqual(created.status_code, 201, created.content)
        rfq_id = created.data['id']
        send = self.client.post(
            f'/api/logistics/purchase-rfqs/{rfq_id}/send/',
            {'supplier_ids': [s.id for s in suppliers]}, format='json',
        )
        self.assertEqual(send.status_code, 200, send.content)
        return created.data


class RfqAwardProducesRightDocumentTest(RfqAwardAndComparisonTestBase):
    def test_award_produces_purchase_invoice_when_purchase_orders_disabled(self):
        data = self.create_and_send_rfq()
        rfq_id = data['id']
        line_ids = [line['id'] for line in data['lines']]
        recipient = PurchaseRFQRecipient.objects.get(rfq_id=rfq_id, supplier=self.supplier_a)
        submit_rfq_supplier_quote(
            recipient, name='Rep A',
            prices={line_ids[0]: Decimal('10'), line_ids[1]: Decimal('20')},
        )

        award = self.client.post(
            f'/api/logistics/purchase-rfqs/{rfq_id}/award/',
            {'supplier': self.supplier_a.id}, format='json',
        )
        self.assertEqual(award.status_code, 200, award.content)
        self.assertEqual(award.data['status'], 'awarded')
        self.assertEqual(award.data['awarded_document']['type'], 'purchase_invoice')
        self.assertEqual(award.data['awarded_supplier_id'], self.supplier_a.id)
        invoice_id = award.data['awarded_document']['id']
        self.assertTrue(PurchaseInvoice.objects.filter(pk=invoice_id, tenant=self.tenant).exists())
        # عرضُ الفائز صار مقبولاً — مسارُ التحويل يفرض ذلك.
        recipient.refresh_from_db()
        self.assertEqual(recipient.quotation.status, SupplierQuotation.STATUS_CONVERTED)

    def test_award_produces_purchase_order_when_purchase_orders_enabled(self):
        PurchaseSettings.objects.create(tenant=self.tenant, use_purchase_orders=True)
        data = self.create_and_send_rfq()
        rfq_id = data['id']
        line_ids = [line['id'] for line in data['lines']]
        recipient = PurchaseRFQRecipient.objects.get(rfq_id=rfq_id, supplier=self.supplier_a)
        submit_rfq_supplier_quote(
            recipient, name='Rep A',
            prices={line_ids[0]: Decimal('10'), line_ids[1]: Decimal('20')},
        )

        award = self.client.post(
            f'/api/logistics/purchase-rfqs/{rfq_id}/award/',
            {'supplier': self.supplier_a.id}, format='json',
        )
        self.assertEqual(award.status_code, 200, award.content)
        self.assertEqual(award.data['awarded_document']['type'], 'purchase_order')
        order_id = award.data['awarded_document']['id']
        self.assertTrue(PurchaseOrder.objects.filter(pk=order_id, tenant=self.tenant).exists())

    def test_award_rejects_supplier_not_a_recipient(self):
        data = self.create_and_send_rfq()
        rfq_id = data['id']
        award = self.client.post(
            f'/api/logistics/purchase-rfqs/{rfq_id}/award/',
            {'supplier': self.supplier_b.id}, format='json',
        )
        self.assertEqual(award.status_code, 400, award.content)

    def test_cannot_award_an_already_awarded_rfq_twice(self):
        data = self.create_and_send_rfq()
        rfq_id = data['id']
        line_ids = [line['id'] for line in data['lines']]
        recipient = PurchaseRFQRecipient.objects.get(rfq_id=rfq_id, supplier=self.supplier_a)
        submit_rfq_supplier_quote(
            recipient, name='Rep A',
            prices={line_ids[0]: Decimal('10'), line_ids[1]: Decimal('20')},
        )
        first = self.client.post(
            f'/api/logistics/purchase-rfqs/{rfq_id}/award/',
            {'supplier': self.supplier_a.id}, format='json',
        )
        self.assertEqual(first.status_code, 200, first.content)
        second = self.client.post(
            f'/api/logistics/purchase-rfqs/{rfq_id}/award/',
            {'supplier': self.supplier_a.id}, format='json',
        )
        self.assertEqual(second.status_code, 400, second.content)


class RfqComparisonTest(RfqAwardAndComparisonTestBase):
    def test_line_without_estimate_returns_no_estimate_and_still_shows_supplier_price(self):
        # بندٌ ١ بلا سعرٍ تقديريّ، بندٌ ٢ بتقديريّ ١٥.
        data = self.create_and_send_rfq(estimated_prices=(None, Decimal('15')))
        rfq_id = data['id']
        line_ids = [line['id'] for line in data['lines']]
        recipient = PurchaseRFQRecipient.objects.get(rfq_id=rfq_id, supplier=self.supplier_a)
        submit_rfq_supplier_quote(
            recipient, name='Rep A',
            prices={line_ids[0]: Decimal('12'), line_ids[1]: Decimal('18')},
        )

        response = self.client.get(f'/api/logistics/purchase-rfqs/{rfq_id}/comparison/')
        self.assertEqual(response.status_code, 200, response.content)

        lines_by_id = {ln['id']: ln for ln in response.data['lines']}
        self.assertIsNone(lines_by_id[line_ids[0]]['estimated_price'])
        self.assertEqual(lines_by_id[line_ids[1]]['estimated_price'], '15.0000')

        supplier_row = response.data['suppliers'][0]
        self.assertEqual(supplier_row['supplier_id'], self.supplier_a.id)
        # السعر موجودٌ رغم غياب التقديري — يُعرَض عارياً بلا نسبة (حسابُ
        # النسبة واجهيّ صرف، ولا تُحمَل هنا أصلاً).
        self.assertEqual(supplier_row['prices'][str(line_ids[0])], '12.0000')
        self.assertEqual(supplier_row['prices'][str(line_ids[1])], '18.0000')
        for price_entry in supplier_row['prices'].values():
            self.assertNotIn('delta_percent', response.content.decode())

    def test_supplier_who_has_not_replied_gets_no_column(self):
        data = self.create_and_send_rfq(suppliers=[self.supplier_a, self.supplier_b])
        rfq_id = data['id']
        line_ids = [line['id'] for line in data['lines']]
        recipient_a = PurchaseRFQRecipient.objects.get(rfq_id=rfq_id, supplier=self.supplier_a)
        submit_rfq_supplier_quote(
            recipient_a, name='Rep A',
            prices={line_ids[0]: Decimal('10'), line_ids[1]: Decimal('20')},
        )
        # المورد ب لم يردّ بعد.

        response = self.client.get(f'/api/logistics/purchase-rfqs/{rfq_id}/comparison/')
        self.assertEqual(response.status_code, 200, response.content)
        supplier_ids = {row['supplier_id'] for row in response.data['suppliers']}
        self.assertEqual(supplier_ids, {self.supplier_a.id})

    def test_unpriced_line_is_blank_not_zero_and_excluded_from_supplier_total(self):
        """عرضٌ يُنشأ مباشرةً بعدد بنودٍ أقل من الطلبية — يُحاكي مورداً لم
        يُسعّر بنداً بعينه (السيناريو الذي يمنعه `submit_rfq_supplier_quote`
        نفسه ببنية الطلبية العادية، لكن الحقل يحتمله وحدَه)."""
        data = self.create_and_send_rfq(estimated_prices=(Decimal('10'), Decimal('20')))
        rfq_id = data['id']
        line_ids = [line['id'] for line in data['lines']]
        recipient = PurchaseRFQRecipient.objects.get(rfq_id=rfq_id, supplier=self.supplier_a)

        quotation = SupplierQuotation.objects.create(
            tenant=self.tenant, rfq_id=rfq_id, scope='local', supplier=self.supplier_a,
            quotation_number='PQ-PARTIAL-1', quotation_date='2026-09-01',
            currency=self.base_currency, exchange_rate=Decimal('1'),
        )
        # سطرٌ واحد فقط (seq=1) — البند الثاني بلا سعرٍ من هذا المورد.
        SupplierQuotationLine.objects.create(
            tenant=self.tenant, quotation=quotation, seq=1,
            name_snapshot='صنف أول', quantity=Decimal('5.000'),
            unit_price=Decimal('9'), line_total=Decimal('45'),
        )
        recipient.quotation = quotation
        recipient.save(update_fields=['quotation'])

        response = self.client.get(f'/api/logistics/purchase-rfqs/{rfq_id}/comparison/')
        self.assertEqual(response.status_code, 200, response.content)
        supplier_row = response.data['suppliers'][0]
        self.assertEqual(supplier_row['prices'][str(line_ids[0])], '9.0000')
        self.assertIsNone(supplier_row['prices'][str(line_ids[1])])
        # الإجمالي = 5 × 9 فقط — البند الثاني غائبٌ لا صفريّ القيمة.
        self.assertEqual(supplier_row['goods_total_base'], '45.00')

    def test_currency_unification_with_explicit_exchange_rate(self):
        data = self.create_and_send_rfq(estimated_prices=(Decimal('37'), None))
        rfq_id = data['id']
        line_ids = [line['id'] for line in data['lines']]
        recipient = PurchaseRFQRecipient.objects.get(rfq_id=rfq_id, supplier=self.supplier_a)

        # عرضٌ بالدولار وسعر صرفٍ صريح 3.7 — يُتوقَّع تحويل السعر والإجمالي
        # إلى العملة الأساسية بضربه في سعر الصرف، لا سعر اليوم.
        quotation = SupplierQuotation.objects.create(
            tenant=self.tenant, rfq_id=rfq_id, scope='local', supplier=self.supplier_a,
            quotation_number='PQ-USD-1', quotation_date='2026-09-01',
            currency=self.usd, exchange_rate=Decimal('3.7'),
        )
        SupplierQuotationLine.objects.create(
            tenant=self.tenant, quotation=quotation, seq=1,
            name_snapshot='صنف أول', quantity=Decimal('5.000'),
            unit_price=Decimal('10'), line_total=Decimal('50'),
        )
        SupplierQuotationLine.objects.create(
            tenant=self.tenant, quotation=quotation, seq=2,
            name_snapshot='صنف ثانٍ', quantity=Decimal('2.000'),
            unit_price=Decimal('4'), line_total=Decimal('8'),
        )
        recipient.quotation = quotation
        recipient.save(update_fields=['quotation'])

        response = self.client.get(f'/api/logistics/purchase-rfqs/{rfq_id}/comparison/')
        self.assertEqual(response.status_code, 200, response.content)
        supplier_row = response.data['suppliers'][0]
        self.assertEqual(supplier_row['currency_code'], 'USD')
        self.assertEqual(supplier_row['exchange_rate'], '3.700000')
        # 10 * 3.7 = 37.00 بالأساسية
        self.assertEqual(supplier_row['prices'][str(line_ids[0])], '37.0000')
        # 4 * 3.7 = 14.80 بالأساسية
        self.assertEqual(supplier_row['prices'][str(line_ids[1])], '14.8000')
        # الإجمالي = (5×37) + (2×14.8) = 185 + 29.6 = 214.60 — بالأساسية لا الدولار.
        self.assertEqual(supplier_row['goods_total_base'], '214.60')

    def test_no_shipping_field_anywhere_in_comparison_response(self):
        """قرار المالك 2026-09-03: إجماليٌّ واحدٌ — البضاعة فقط — لا حقل شحنٍ إطلاقاً."""
        data = self.create_and_send_rfq(estimated_prices=(Decimal('10'), Decimal('20')))
        rfq_id = data['id']
        line_ids = [line['id'] for line in data['lines']]
        recipient = PurchaseRFQRecipient.objects.get(rfq_id=rfq_id, supplier=self.supplier_a)
        submit_rfq_supplier_quote(
            recipient, name='Rep A',
            prices={line_ids[0]: Decimal('9'), line_ids[1]: Decimal('19')},
        )

        response = self.client.get(f'/api/logistics/purchase-rfqs/{rfq_id}/comparison/')
        self.assertEqual(response.status_code, 200, response.content)
        raw = response.content.decode()
        self.assertNotIn('shipping', raw)
        self.assertIn('goods_total_base', raw)
        supplier_row = response.data['suppliers'][0]
        self.assertEqual(set(supplier_row.keys()), {
            'supplier_id', 'supplier_name', 'quotation_id', 'quotation_number',
            'currency_code', 'exchange_rate', 'replied_at', 'prices', 'goods_total_base',
        })

    def test_comparison_from_another_tenant_is_not_readable(self):
        data = self.create_and_send_rfq()
        rfq_id = data['id']
        self.client.credentials(HTTP_X_TENANT_ID=str(self.other_tenant.TenantID))
        response = self.client.get(f'/api/logistics/purchase-rfqs/{rfq_id}/comparison/')
        self.assertEqual(response.status_code, 404)
