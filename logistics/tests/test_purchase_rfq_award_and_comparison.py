"""ISSUE #116 (مواصفة #108 §٨) — المقارنة والترسية: مستويان.

سطح DRF وحده، على نمط `test_purchase_rfq.py` (ISSUE #112). يغطي:
- الترسية: تنتج أمر شراء أو فاتورة شراء بحسب `PurchaseSettings.use_purchase_orders`.
- المصفوفة (`comparison/`): بندٌ بلا سعرٍ تقديريّ يعود بلا نسبة (فارغ لا صفر)،
  بندٌ لم يُسعّره موردٌ بعينه لا يُحتسَب صفراً في إجماليّه، توحيد العملات
  بسعر صرفٍ صريح، ولا حقل شحنٍ في المخرَج إطلاقاً.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone
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

    def create_and_send_rfq(self, *, estimated_prices=(None, None), suppliers=None, scope='local'):
        """طلبيةٌ ببندين، تُرسَل مباشرةً للموردين المُمرَّرين."""
        suppliers = suppliers if suppliers is not None else [self.supplier_a]
        payload = {
            'scope': scope,
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

    def test_award_on_import_scope_accepts_offer_and_stops_no_conversion(self):
        """ISSUE #133 غ١ (قرار المالك 2026-09-04): بالاستيراد الطلبيةُ والعرضُ
        الشيءُ نفسُه — الترسية تقبل عرض الفائز وتُغلق الطلبية عليه، ولا تحوّل
        شيئاً. التحويل إلى صفقة يمرّ لاحقاً بمسار «تحويل إلى صفقة» على العرض
        المقبول — لا منطق تحويل هنا.
        """
        from logistics.models import LogisticsDeal

        data = self.create_and_send_rfq(
            estimated_prices=(Decimal('10'), Decimal('20')), scope='import',
        )
        rfq_id = data['id']
        self.assertEqual(data['scope'], 'import')
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
        self.assertEqual(award.data['awarded_supplier_id'], self.supplier_a.id)
        self.assertIsNone(award.data['awarded_document'])

        recipient.refresh_from_db()
        self.assertEqual(recipient.quotation.status, SupplierQuotation.STATUS_ACCEPTED)
        # لا صفقة ولا فاتورة ولا أمر شراء نتج عن الترسية بالاستيراد.
        self.assertFalse(LogisticsDeal.objects.filter(tenant=self.tenant).exists())
        self.assertFalse(PurchaseInvoice.objects.filter(tenant=self.tenant).exists())
        self.assertFalse(PurchaseOrder.objects.filter(tenant=self.tenant).exists())

    def test_award_on_purchase_scope_still_produces_invoice_regression_guard(self):
        """حارسُ انحدارٍ: الشراء المحلّي يبقى ينتج فاتورة كما كان — التفريع
        بين النطاقين في `award` لا يجوز أن يمسّ مسار الشراء المحلّي."""
        data = self.create_and_send_rfq(scope='local')
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
        self.assertIsNotNone(award.data['awarded_document'])
        self.assertEqual(award.data['awarded_document']['type'], 'purchase_invoice')

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
            # ISSUE #122: شارةُ مصدر الإدخال. مواصفة #147 (المرحلة 5أ): النصّ
            # العربيّ الجاهز بجانبها — الواجهة تقرأه بدل تكرار `choices` الحقل.
            'entry_source', 'entry_source_display',
            # ISSUE #133 غ٣ (مواصفة #130 §١): ملاحظةُ المورّد على كلّ بند
            # (`notes`) وملاحظتُه العامة على الطلبية كلّها (`general_note`) —
            # سببُ وجود المصفوفة أصلاً «هذا ما عندي بدل ما طلبت». وتعليقنا
            # الداخليّ (`internal_notes`) يظهر هنا أيضاً — هذه شاشةٌ مصادَقٌ
            # عليها لا السطح العام، ومعه `quotation_line_ids` ليربط بند
            # الطلبية بسطر العرض الذي يُكتَب عليه التعليق.
            'notes', 'general_note', 'internal_notes', 'quotation_line_ids',
        })

    def test_comparison_from_another_tenant_is_not_readable(self):
        data = self.create_and_send_rfq()
        rfq_id = data['id']
        self.client.credentials(HTTP_X_TENANT_ID=str(self.other_tenant.TenantID))
        response = self.client.get(f'/api/logistics/purchase-rfqs/{rfq_id}/comparison/')
        self.assertEqual(response.status_code, 404)

    # ── ISSUE #133 غ٣ (مواصفة #130 §١، مراجعة الجولة الثانية) ──────────────
    #
    # الملاحظتان يجب أن تصلا معاً إلى المصفوفة — سببُ وجودها أصلاً — ونقطةُ
    # الكتابة الوحيدة للتعليق الداخليّ (`set_line_internal_note`) يجب ألّا
    # تمسّ نصّ المورّد بحرف، لأنها تعيش على السطر نفسه لا على نسخةٍ منه.

    def test_comparison_carries_both_the_suppliers_note_and_our_internal_reply(self):
        data = self.create_and_send_rfq(estimated_prices=(Decimal('10'), Decimal('20')))
        rfq_id = data['id']
        line_ids = [line['id'] for line in data['lines']]
        recipient = PurchaseRFQRecipient.objects.get(rfq_id=rfq_id, supplier=self.supplier_a)
        submit_rfq_supplier_quote(
            recipient, name='Rep A',
            prices={line_ids[0]: Decimal('9'), line_ids[1]: Decimal('19')},
            notes={line_ids[0]: 'عندنا مقاسٌ أكبر بقليل فقط'},
            general_note='لا نورّد خارج المدينة',
        )

        response = self.client.get(f'/api/logistics/purchase-rfqs/{rfq_id}/comparison/')
        self.assertEqual(response.status_code, 200, response.content)
        supplier_row = response.data['suppliers'][0]
        self.assertEqual(
            supplier_row['notes'][str(line_ids[0])], 'عندنا مقاسٌ أكبر بقليل فقط',
        )
        self.assertIsNone(supplier_row['notes'][str(line_ids[1])])
        self.assertEqual(supplier_row['general_note'], 'لا نورّد خارج المدينة')
        # لا تعليق داخليّ بعد — نصٌّ فارغ وكاتبٌ فارغ، لا مفتاحٌ غائب.
        self.assertEqual(supplier_row['internal_notes'][str(line_ids[0])]['text'], '')
        self.assertEqual(supplier_row['internal_notes'][str(line_ids[0])]['by'], '')

    def test_writing_an_internal_note_leaves_the_suppliers_text_byte_for_byte_unchanged(self):
        data = self.create_and_send_rfq(estimated_prices=(Decimal('10'), Decimal('20')))
        rfq_id = data['id']
        line_ids = [line['id'] for line in data['lines']]
        recipient = PurchaseRFQRecipient.objects.get(rfq_id=rfq_id, supplier=self.supplier_a)
        submit_rfq_supplier_quote(
            recipient, name='Rep A',
            prices={line_ids[0]: Decimal('9'), line_ids[1]: Decimal('19')},
            notes={line_ids[0]: 'نصّ المورّد الأصلي — لا يُمَسّ'},
        )
        quotation = recipient.quotation
        quotation_line = quotation.lines.get(rfq_line_id=line_ids[0])

        comparison_before = self.client.get(
            f'/api/logistics/purchase-rfqs/{rfq_id}/comparison/',
        ).data
        quotation_line_id = (
            comparison_before['suppliers'][0]['quotation_line_ids'][str(line_ids[0])]
        )
        self.assertEqual(quotation_line_id, quotation_line.pk)

        # نقطة الكتابة الوحيدة للتعليق الداخليّ — من المصفوفة حيث يقرأ
        # المشتري ملاحظة المورّد ويردّ عليها، لا من محرّر العروض.
        response = self.client.post(
            f'/api/logistics/supplier-quotations/{quotation.pk}/lines/{quotation_line_id}/internal-note/',
            {'internal_note': 'نتحقّق من هذا مع المستودع قبل الترسية'},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            response.data['internal_note'], 'نتحقّق من هذا مع المستودع قبل الترسية',
        )
        self.assertEqual(response.data['internal_note_by_name'], 'rfq-award-owner')
        self.assertIsNotNone(response.data['internal_note_at'])
        # والنصّ المقفَل غائبٌ عن جسم الاستجابة كتابةً — يعود للقراءة فقط.
        self.assertEqual(response.data['supplier_note'], 'نصّ المورّد الأصلي — لا يُمَسّ')

        quotation_line.refresh_from_db()
        self.assertEqual(quotation_line.supplier_note, 'نصّ المورّد الأصلي — لا يُمَسّ')
        self.assertEqual(
            quotation_line.internal_note, 'نتحقّق من هذا مع المستودع قبل الترسية',
        )
        self.assertEqual(quotation_line.internal_note_by_id, self.user.pk)

        # وتظهر الآن في المصفوفة أيضاً — بجانب نصّ المورّد لا بدلاً عنه.
        comparison_after = self.client.get(
            f'/api/logistics/purchase-rfqs/{rfq_id}/comparison/',
        ).data
        supplier_row = comparison_after['suppliers'][0]
        self.assertEqual(
            supplier_row['notes'][str(line_ids[0])], 'نصّ المورّد الأصلي — لا يُمَسّ',
        )
        self.assertEqual(
            supplier_row['internal_notes'][str(line_ids[0])]['text'],
            'نتحقّق من هذا مع المستودع قبل الترسية',
        )
        self.assertEqual(
            supplier_row['internal_notes'][str(line_ids[0])]['by'], 'rfq-award-owner',
        )

    def test_saving_the_offer_from_the_editor_keeps_the_note_and_its_stamp(self):
        """ISSUE #133 غ٣: محرِّرُ العروض يرسل `internal_note` في **كلّ** حفظ،
        لأنّ `update()` يحذف كلّ سطرٍ ويعيد إنشاءه من الحمولة — فإسقاطُه هناك
        يمحو التعليقَ بصمت. وهذا المسارُ الثاني للكتابة (غيرُ نقطة
        `internal-note/`) يحرسه هذا الاختبار في ثلاث نقاط:

        أنّ نصّ المورّد ينجو من الهدم وإعادة البناء، وأنّ حفظاً **لا يغيّر
        التعليق** لا يعيد ختمه (وإلّا صار كلُّ حفظٍ يكذب فينسب تعليقاً قديماً
        إلى تاريخٍ جديد)، وأنّ تغييرَه فعلاً يُختَم من جديد.
        """
        data = self.create_and_send_rfq(estimated_prices=(Decimal('10'), Decimal('20')))
        line_ids = [line['id'] for line in data['lines']]
        recipient = PurchaseRFQRecipient.objects.get(
            rfq_id=data['id'], supplier=self.supplier_a,
        )
        submit_rfq_supplier_quote(
            recipient, name='Rep A',
            prices={line_ids[0]: Decimal('9'), line_ids[1]: Decimal('19')},
            notes={line_ids[0]: 'نصّ المورّد — يعبر الهدم سليماً'},
        )
        quotation = recipient.quotation
        line = quotation.lines.get(rfq_line_id=line_ids[0])
        self.client.post(
            f'/api/logistics/supplier-quotations/{quotation.pk}/lines/{line.pk}/internal-note/',
            {'internal_note': 'نتحقّق مع المستودع'}, format='json',
        )
        line.refresh_from_db()
        stamped_at, stamped_by = line.internal_note_at, line.internal_note_by_id
        self.assertIsNotNone(stamped_at)

        def save_from_editor(internal_note):
            """حفظٌ من المحرِّر: كلُّ السطور بحمولتها كاملةً، بلا `supplier_note`
            (نصُّ المورّد لا يُرسَل من الشاشة أبداً)."""
            payload = {
                'supplier': self.supplier_a.id,
                'quotation_date': str(timezone.localdate()),
                'currency': quotation.currency_id,
                'exchange_rate': str(quotation.exchange_rate),
                'lines': [
                    {
                        'product': ln.product_id,
                        'seq': ln.seq,
                        'quantity': str(ln.quantity),
                        'unit_price': str(ln.unit_price),
                        'rfq_line': ln.rfq_line_id,
                        'internal_note': (
                            internal_note if ln.rfq_line_id == line_ids[0]
                            else ln.internal_note
                        ),
                    }
                    for ln in quotation.lines.order_by('seq')
                ],
            }
            response = self.client.put(
                f'/api/logistics/supplier-quotations/{quotation.pk}/',
                payload, format='json',
            )
            self.assertEqual(response.status_code, 200, response.content)
            return quotation.lines.get(rfq_line_id=line_ids[0])

        # حفظٌ بلا تغييرٍ للتعليق — النصّان كما هما، والختمُ لا يُعاد.
        saved = save_from_editor('نتحقّق مع المستودع')
        self.assertEqual(saved.supplier_note, 'نصّ المورّد — يعبر الهدم سليماً')
        self.assertEqual(saved.internal_note, 'نتحقّق مع المستودع')
        self.assertEqual(saved.internal_note_at, stamped_at)
        self.assertEqual(saved.internal_note_by_id, stamped_by)

        # وحفظٌ يغيّره فعلاً — يُختَم من جديد، ونصّ المورّد يبقى مع ذلك سليماً.
        saved = save_from_editor('تحقّقنا: المقاس مقبول')
        self.assertEqual(saved.internal_note, 'تحقّقنا: المقاس مقبول')
        self.assertNotEqual(saved.internal_note_at, stamped_at)
        self.assertEqual(saved.supplier_note, 'نصّ المورّد — يعبر الهدم سليماً')


class RfqOfferEnteredFromTheEditorTest(RfqAwardAndComparisonTestBase):
    """ISSUE #122 — المورّدُ الذي سعّر هاتفياً: عرضٌ يُولَد من صفّ مستقبِله.

    لا نافذةَ تسعيرٍ مستقلّة ولا نقطةَ API ثانية: يُفتَح **محرِّرُ العروض
    نفسُه** عرضاً جديداً غيرَ محفوظ، مُعبَّأً ببنود الطلبية وكمياتها وبأسعارٍ
    فارغة. فالتسعيرُ الجزئيّ (يُحذَف سطرُ ما لا يحمله المورّد) والعملةُ
    والتصحيحُ كلُّها تسقط من المحرِّر القائم — والذي تكسبه القاعدة هو النَسَب:
    `rfq_recipient` عند الإنشاء، و`rfq_line` على كلّ سطر.
    """

    def create_and_send_rfq_with_three_lines(self, suppliers=None):
        suppliers = suppliers if suppliers is not None else [self.supplier_a]
        payload = {
            'scope': 'local',
            'rfq_date': '2026-09-01',
            'lines': [
                {'product': self.product1.id, 'seq': 1, 'quantity': '5.000',
                 'unit_of_measure': 'حبة'},
                {'product': self.product2.id, 'seq': 2, 'quantity': '2.000',
                 'unit_of_measure': 'كرتون'},
                {'seq': 3, 'quantity': '3.000', 'name_snapshot': 'صنف ثالث',
                 'unit_of_measure': 'حبة'},
            ],
        }
        created = self.client.post('/api/logistics/purchase-rfqs/', payload, format='json')
        self.assertEqual(created.status_code, 201, created.content)
        send = self.client.post(
            f'/api/logistics/purchase-rfqs/{created.data["id"]}/send/',
            {'supplier_ids': [s.id for s in suppliers]}, format='json',
        )
        self.assertEqual(send.status_code, 200, send.content)
        return created.data

    def post_offer(self, *, recipient, supplier, lines, **overrides):
        payload = {
            'scope': 'local',
            'supplier': supplier.id,
            'quotation_date': '2026-09-02',
            'currency': self.base_currency.pk,
            'exchange_rate': '1',
            'rfq_recipient': recipient.id,
            'lines': lines,
        }
        payload.update(overrides)
        return self.client.post(
            '/api/logistics/supplier-quotations/', payload, format='json',
        )

    def test_offer_born_from_a_recipient_becomes_that_suppliers_column_and_can_be_awarded(self):
        data = self.create_and_send_rfq(estimated_prices=(Decimal('10'), Decimal('20')))
        rfq_id = data['id']
        line_ids = [line['id'] for line in data['lines']]
        recipient = PurchaseRFQRecipient.objects.get(rfq_id=rfq_id, supplier=self.supplier_a)

        response = self.post_offer(
            recipient=recipient, supplier=self.supplier_a,
            lines=[
                {'product': self.product1.id, 'seq': 1, 'quantity': '5.000',
                 'unit_price': '9', 'rfq_line': line_ids[0]},
                {'product': self.product2.id, 'seq': 2, 'quantity': '2.000',
                 'unit_price': '19', 'rfq_line': line_ids[1]},
            ],
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data['rfq'], rfq_id)
        self.assertEqual(response.data['entry_source'], 'manual')

        # المستقبِلُ صار «ردّ»: بعرضٍ وبوقتِ ردّ.
        recipient.refresh_from_db()
        self.assertEqual(recipient.quotation_id, response.data['id'])
        self.assertIsNotNone(recipient.replied_at)

        # ويظهر في المصفوفة كأيّ مورّدٍ ردّ.
        comparison = self.client.get(f'/api/logistics/purchase-rfqs/{rfq_id}/comparison/')
        self.assertEqual(comparison.status_code, 200, comparison.content)
        supplier_row = comparison.data['suppliers'][0]
        self.assertEqual(supplier_row['supplier_id'], self.supplier_a.id)
        self.assertEqual(supplier_row['prices'][str(line_ids[0])], '9.0000')
        self.assertEqual(supplier_row['goods_total_base'], '83.00')  # 5×9 + 2×19

        # وتصحّ الترسيةُ عليه بلا استثناء.
        award = self.client.post(
            f'/api/logistics/purchase-rfqs/{rfq_id}/award/',
            {'supplier': self.supplier_a.id}, format='json',
        )
        self.assertEqual(award.status_code, 200, award.content)
        self.assertEqual(award.data['awarded_supplier_id'], self.supplier_a.id)

    def test_offer_whose_middle_line_was_deleted_lines_prices_up_against_the_right_items(self):
        """الحارسُ الذي يبرّر `rfq_line` وحدَه.

        المورّدُ لا يحمل الصنف الثاني فيُحذف سطرُه من المحرِّر وتُرقَّم البقيةُ
        ١ و٢. المطابقةُ بـ`seq` كانت تضع سعرَ **الصنف الثالث** تحت الثاني —
        كذبةٌ صامتة في الشاشة التي بُنيت لتمنع الكذب.
        """
        data = self.create_and_send_rfq_with_three_lines()
        rfq_id = data['id']
        line_ids = [line['id'] for line in data['lines']]
        recipient = PurchaseRFQRecipient.objects.get(rfq_id=rfq_id, supplier=self.supplier_a)

        response = self.post_offer(
            recipient=recipient, supplier=self.supplier_a,
            lines=[
                {'product': self.product1.id, 'seq': 1, 'quantity': '5.000',
                 'unit_price': '9', 'rfq_line': line_ids[0]},
                # البند الثاني محذوف — والثالثُ ورث الترتيبَ ٢.
                {'seq': 2, 'quantity': '3.000', 'name_snapshot': 'صنف ثالث',
                 'unit_price': '30', 'rfq_line': line_ids[2]},
            ],
        )
        self.assertEqual(response.status_code, 201, response.content)

        comparison = self.client.get(f'/api/logistics/purchase-rfqs/{rfq_id}/comparison/')
        self.assertEqual(comparison.status_code, 200, comparison.content)
        supplier_row = comparison.data['suppliers'][0]
        prices = supplier_row['prices']
        self.assertEqual(prices[str(line_ids[0])], '9.0000')
        self.assertIsNone(prices[str(line_ids[1])])   # لا يحمله — فراغٌ لا سعر
        self.assertEqual(prices[str(line_ids[2])], '30.0000')
        # 5×9 + 3×30 = 135 — البند المحذوف غائبٌ لا صفريّ القيمة.
        self.assertEqual(supplier_row['goods_total_base'], '135.00')

    def test_correcting_the_offer_later_does_not_lose_the_line_lineage(self):
        """المورّدُ عاد بسعرٍ جديد فصُحّح عرضُه — والنَسَبُ يجب أن ينجو.

        `update` على الخادم **يحذف البنود ويعيد بناءها** من الحمولة، فحفظٌ ثانٍ
        لا يحمل `rfq_line` يمحو النَسَبَ بصمت وترتدّ المصفوفةُ إلى مطابقة `seq`
        الكاذبة. والحفظُ الثاني هو الحالةُ الشائعة لا النادرة: تصحيحُ سعرٍ سُمع
        خطأً على الهاتف.
        """
        data = self.create_and_send_rfq_with_three_lines()
        rfq_id = data['id']
        line_ids = [line['id'] for line in data['lines']]
        recipient = PurchaseRFQRecipient.objects.get(rfq_id=rfq_id, supplier=self.supplier_a)

        created = self.post_offer(
            recipient=recipient, supplier=self.supplier_a,
            lines=[
                {'product': self.product1.id, 'seq': 1, 'quantity': '5.000',
                 'unit_price': '9', 'rfq_line': line_ids[0]},
                {'seq': 2, 'quantity': '3.000', 'name_snapshot': 'صنف ثالث',
                 'unit_price': '30', 'rfq_line': line_ids[2]},
            ],
        )
        self.assertEqual(created.status_code, 201, created.content)

        patched = self.client.patch(
            f"/api/logistics/supplier-quotations/{created.data['id']}/",
            {'lines': [
                {'product': self.product1.id, 'seq': 1, 'quantity': '5.000',
                 'unit_price': '8', 'rfq_line': line_ids[0]},
                {'seq': 2, 'quantity': '3.000', 'name_snapshot': 'صنف ثالث',
                 'unit_price': '28', 'rfq_line': line_ids[2]},
            ]},
            format='json',
        )
        self.assertEqual(patched.status_code, 200, patched.content)

        comparison = self.client.get(f'/api/logistics/purchase-rfqs/{rfq_id}/comparison/')
        prices = comparison.data['suppliers'][0]['prices']
        self.assertEqual(prices[str(line_ids[0])], '8.0000')
        self.assertIsNone(prices[str(line_ids[1])])
        # لو ضاع النَسَبُ لسقطت المطابقةُ إلى `seq` فوضعت ٢٨ تحت البند الثاني.
        self.assertEqual(prices[str(line_ids[2])], '28.0000')

    def test_comparison_distinguishes_who_priced_it_himself_from_who_we_entered_for(self):
        data = self.create_and_send_rfq(suppliers=[self.supplier_a, self.supplier_b])
        rfq_id = data['id']
        line_ids = [line['id'] for line in data['lines']]
        recipient_a = PurchaseRFQRecipient.objects.get(rfq_id=rfq_id, supplier=self.supplier_a)
        recipient_b = PurchaseRFQRecipient.objects.get(rfq_id=rfq_id, supplier=self.supplier_b)

        # (أ) سعّر بنفسه من رابطه، و(ب) أدخلناه عنه من المحرِّر.
        submit_rfq_supplier_quote(
            recipient_a, name='Rep A',
            prices={line_ids[0]: Decimal('10'), line_ids[1]: Decimal('20')},
        )
        response = self.post_offer(
            recipient=recipient_b, supplier=self.supplier_b,
            lines=[
                {'product': self.product1.id, 'seq': 1, 'quantity': '5.000',
                 'unit_price': '11', 'rfq_line': line_ids[0]},
                {'product': self.product2.id, 'seq': 2, 'quantity': '2.000',
                 'unit_price': '21', 'rfq_line': line_ids[1]},
            ],
        )
        self.assertEqual(response.status_code, 201, response.content)

        comparison = self.client.get(f'/api/logistics/purchase-rfqs/{rfq_id}/comparison/')
        sources = {
            row['supplier_id']: row['entry_source'] for row in comparison.data['suppliers']
        }
        self.assertEqual(sources[self.supplier_a.id], 'supplier_link')
        self.assertEqual(sources[self.supplier_b.id], 'manual')

    def test_offer_in_a_currency_other_than_base_is_converted_in_the_matrix(self):
        data = self.create_and_send_rfq(estimated_prices=(Decimal('37'), None))
        rfq_id = data['id']
        line_ids = [line['id'] for line in data['lines']]
        recipient = PurchaseRFQRecipient.objects.get(rfq_id=rfq_id, supplier=self.supplier_a)

        response = self.post_offer(
            recipient=recipient, supplier=self.supplier_a,
            currency=self.usd.pk, exchange_rate='3.7',
            lines=[
                {'product': self.product1.id, 'seq': 1, 'quantity': '5.000',
                 'unit_price': '10', 'rfq_line': line_ids[0]},
            ],
        )
        self.assertEqual(response.status_code, 201, response.content)

        comparison = self.client.get(f'/api/logistics/purchase-rfqs/{rfq_id}/comparison/')
        supplier_row = comparison.data['suppliers'][0]
        self.assertEqual(supplier_row['currency_code'], 'USD')
        # عشرةُ دولاراتٍ = ٣٧ بالأساسية — لا «١٢ دولاراً أقلّ من ٤٥ شيكلاً».
        self.assertEqual(supplier_row['prices'][str(line_ids[0])], '37.0000')
        self.assertEqual(supplier_row['goods_total_base'], '185.00')
