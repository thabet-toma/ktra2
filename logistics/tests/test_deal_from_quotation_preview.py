"""T113-1 — «عرضٌ قبل الحفظ»: لا يُخلق أي سجل قبل ضغطة «حفظ».

المالك: التحويل من عرض سعر استيراد إلى صفقة كان يقع بضغطة واحدة — صفقة مؤكَّدة
ومورد ومنتج يُخلقون معاً بلا مراجعة. المعيار الجديد: «تحويل إلى صفقة» يفتح
**معاينة** فقط (قراءات لا كتابات)، والصفقة تُولد لحظة الحفظ وحدها، وعندها
تطالب بعرضها المصدر فتقلبه «محوَّلاً» في المعاملة نفسها.

ما يثبته هذا الملف: المعاينة لا تخلّف أثراً · الحفظ ينشئ صفقة واحدة بالضبط ·
الحفظ الثاني لنفس العرض يرتد ومعه رقم الصفقة القائمة · حرّاس العزل والنطاق
والحالة · ولا شريك ولا منتج يُخلق ضمنياً في أي من الخطوتين.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from core.models import ActivityLog
from inventory.models import Product
from logistics.models import LogisticsDeal, SupplierQuotation
from partners.models import Partner
from tenants.models import Currency, Tenant, UserCompanyMembership


class DealFromQuotationPreviewTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=977, CompanyName='Preview Co')
        cls.other_tenant = Tenant.objects.create(
            TenantID=978, CompanyName='Other Preview Co',
        )
        cls.currency = Currency.objects.create(
            Code='PRV', Name='Preview currency', IsBaseCurrency=False,
        )
        cls.user = User.objects.create_user(username='deal-preview', password='x')
        UserCompanyMembership.objects.create(
            user=cls.user, tenant=cls.tenant, role='manager',
        )
        UserCompanyMembership.objects.create(
            user=cls.user, tenant=cls.other_tenant, role='manager',
        )
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name='مصنع مسجَّل', partner_type='Supplier',
            supplier_scope=Partner.SUPPLIER_SCOPE_INTERNATIONAL,
        )
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku='PRV-1', name_ar='منتج مسجَّل',
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    # ── أدوات ──────────────────────────────────────────────────────────────
    def quotation_payload(self, **overrides):
        """عرض استيراد مقبول بمورد **مبدئي** وبند **مبدئي** — أصعب حالة للمعيار."""
        payload = {
            'scope': 'import',
            'supplier': None,
            'supplier_draft_name': 'مصنع سمعنا عنه',
            'quotation_date': '2026-08-01',
            'status': 'accepted',
            'currency': self.currency.pk,
            'exchange_rate': '3.650000',
            'discount_amount': '2.00',
            'tax_rate': '0',
            'shipping_cost_estimate': '3.00',
            'is_shipping_included': False,
            'lines': [{
                'seq': 1,
                'name_snapshot': 'منتج مكتوب في رسالة',
                'quantity': '2.500',
                'unit_price': '10.0000',
            }],
        }
        payload.update(overrides)
        return payload

    def create_quotation(self, **overrides):
        response = self.client.post(
            '/api/logistics/supplier-quotations/',
            self.quotation_payload(**overrides), format='json',
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.data

    def deal_payload(self, quotation_id, **overrides):
        """ما يرسله المحرّر عند «حفظ»: مورد ومنتجات **محلولة** + العرض المصدر."""
        payload = {
            'source_quotation': quotation_id,
            'partner': self.supplier.id,
            'order_date': '2026-08-01',
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
                'name_snapshot': 'منتج مكتوب في رسالة',
            }],
        }
        payload.update(overrides)
        return payload

    @staticmethod
    def convert_log_count():
        return ActivityLog.objects.filter(
            action='convert', entity_type='supplier_quotation',
        ).count()

    def party_counts(self):
        return (
            Partner.objects.filter(tenant=self.tenant).count(),
            Product.objects.filter(tenant=self.tenant).count(),
        )

    # ── المعاينة ───────────────────────────────────────────────────────────
    def test_preview_reads_create_nothing(self):
        quotation = self.create_quotation()
        before = self.party_counts()

        detail = self.client.get(
            f"/api/logistics/supplier-quotations/{quotation['id']}/",
        )
        self.assertEqual(detail.status_code, 200, detail.content)
        next_ref = self.client.get('/api/logistics/deals/next-ref/')
        self.assertEqual(next_ref.status_code, 200, next_ref.content)
        self.assertTrue(next_ref.data['ref_number'].startswith('D-'))
        # الرقم معاينة لا حجز: قراءتان متتاليتان تعطيان الرقم نفسه.
        self.assertEqual(
            self.client.get('/api/logistics/deals/next-ref/').data['ref_number'],
            next_ref.data['ref_number'],
        )

        self.assertEqual(LogisticsDeal.objects.count(), 0)
        self.assertEqual(self.party_counts(), before)
        self.assertEqual(
            SupplierQuotation.objects.get(pk=quotation['id']).status,
            SupplierQuotation.STATUS_ACCEPTED,
        )
        self.assertEqual(self.convert_log_count(), 0)

    # ── الحفظ ──────────────────────────────────────────────────────────────
    def test_save_with_source_creates_exactly_one_deal_and_flips(self):
        quotation = self.create_quotation()

        response = self.client.post(
            '/api/logistics/deals/', self.deal_payload(quotation['id']), format='json',
        )
        self.assertEqual(response.status_code, 201, response.content)

        self.assertEqual(LogisticsDeal.objects.count(), 1)
        deal = LogisticsDeal.objects.get(pk=response.data['id'])
        self.assertEqual(deal.source_quotation_id, quotation['id'])
        self.assertEqual(deal.total_amount, Decimal('26.00'))

        reread = self.client.get(
            f"/api/logistics/supplier-quotations/{quotation['id']}/",
        )
        self.assertEqual(reread.data['status'], SupplierQuotation.STATUS_CONVERTED)
        self.assertEqual(reread.data['converted_deal']['ref_number'], deal.ref_number)

        # النسب من العرض خادمياً — لا من حمولة العميل.
        self.assertEqual(deal.original_offer_number, quotation['quotation_number'])
        self.assertEqual(deal.price_offer_id, str(quotation['id']))
        self.assertEqual(self.convert_log_count(), 1)

    def test_client_cannot_forge_the_offer_lineage(self):
        """رقم العرض ومعرّفه شهادة نسب: قيمة العميل تُتجاهل ويُكتب ما في العرض."""
        quotation = self.create_quotation()

        response = self.client.post('/api/logistics/deals/', self.deal_payload(
            quotation['id'],
            price_offer_id='999999',
            original_offer_number='IQ-مزوَّر',
        ), format='json')
        self.assertEqual(response.status_code, 201, response.content)

        deal = LogisticsDeal.objects.get(pk=response.data['id'])
        self.assertEqual(deal.price_offer_id, str(quotation['id']))
        self.assertEqual(deal.original_offer_number, quotation['quotation_number'])

    def test_second_save_is_rejected_with_existing_ref(self):
        quotation = self.create_quotation()
        first = self.client.post(
            '/api/logistics/deals/', self.deal_payload(quotation['id']), format='json',
        )
        self.assertEqual(first.status_code, 201, first.content)

        second = self.client.post(
            '/api/logistics/deals/', self.deal_payload(quotation['id']), format='json',
        )
        self.assertEqual(second.status_code, 400, second.content)
        message = str(second.data['source_quotation'])
        self.assertIn(first.data['ref_number'], message)
        self.assertIn(quotation['quotation_number'], message)
        self.assertEqual(LogisticsDeal.objects.count(), 1)
        self.assertEqual(self.convert_log_count(), 1)

    # ── الحرّاس ────────────────────────────────────────────────────────────
    def test_source_quotation_guards(self):
        self.client.credentials(HTTP_X_TENANT_ID=str(self.other_tenant.TenantID))
        foreign = self.client.post(
            '/api/logistics/supplier-quotations/',
            self.quotation_payload(), format='json',
        )
        self.assertEqual(foreign.status_code, 201, foreign.content)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

        foreign_save = self.client.post(
            '/api/logistics/deals/', self.deal_payload(foreign.data['id']),
            format='json',
        )
        self.assertEqual(foreign_save.status_code, 400, foreign_save.content)
        self.assertIn('source_quotation', foreign_save.data)

        local = self.create_quotation(scope='local')
        local_save = self.client.post(
            '/api/logistics/deals/', self.deal_payload(local['id']), format='json',
        )
        self.assertEqual(local_save.status_code, 400, local_save.content)
        self.assertIn('source_quotation', local_save.data)

        draft = self.create_quotation(status='draft')
        draft_save = self.client.post(
            '/api/logistics/deals/', self.deal_payload(draft['id']), format='json',
        )
        self.assertEqual(draft_save.status_code, 400, draft_save.content)
        self.assertIn('source_quotation', draft_save.data)

        self.assertEqual(LogisticsDeal.objects.count(), 0)

        # التعديل لا يعيد كتابة النسب: المصدر يُربط عند الإنشاء فقط.
        accepted = self.create_quotation()
        created = self.client.post(
            '/api/logistics/deals/', self.deal_payload(accepted['id']), format='json',
        )
        self.assertEqual(created.status_code, 201, created.content)
        another = self.create_quotation()
        patched = self.client.patch(
            f"/api/logistics/deals/{created.data['id']}/",
            {'source_quotation': another['id']}, format='json',
        )
        self.assertEqual(patched.status_code, 400, patched.content)
        self.assertEqual(
            LogisticsDeal.objects.get(pk=created.data['id']).source_quotation_id,
            accepted['id'],
        )
        self.assertEqual(
            SupplierQuotation.objects.get(pk=another['id']).status,
            SupplierQuotation.STATUS_ACCEPTED,
        )

    def test_other_tenant_partner_or_product_is_rejected(self):
        """نفس الواجهة كانت تقبل شريكاً ومنتجاً من شركة أخرى بلا فحص (THA-307)."""
        other_supplier = Partner.objects.create(
            tenant=self.other_tenant, name='مصنع شركة أخرى', partner_type='Supplier',
        )
        other_product = Product.objects.create(
            tenant=self.other_tenant, sku='PRV-OTHER-1', name_ar='منتج شركة أخرى',
        )
        quotation = self.create_quotation()

        partner_save = self.client.post(
            '/api/logistics/deals/',
            self.deal_payload(quotation['id'], partner=other_supplier.id),
            format='json',
        )
        self.assertEqual(partner_save.status_code, 400, partner_save.content)
        self.assertIn('partner', partner_save.data)

        payload = self.deal_payload(quotation['id'])
        payload['items'][0]['product'] = other_product.id
        product_save = self.client.post(
            '/api/logistics/deals/', payload, format='json',
        )
        self.assertEqual(product_save.status_code, 400, product_save.content)
        self.assertIn('items', product_save.data)
        self.assertEqual(LogisticsDeal.objects.count(), 0)

    # ── المعيار الجوهري ────────────────────────────────────────────────────
    def test_no_implicit_partner_or_product_anywhere(self):
        quotation = self.create_quotation()
        before = self.party_counts()

        self.client.get(f"/api/logistics/supplier-quotations/{quotation['id']}/")
        self.client.get('/api/logistics/deals/next-ref/')
        after_preview = self.party_counts()

        saved = self.client.post(
            '/api/logistics/deals/', self.deal_payload(quotation['id']), format='json',
        )
        self.assertEqual(saved.status_code, 201, saved.content)
        after_save = self.party_counts()

        self.assertEqual(before, after_preview)
        self.assertEqual(before, after_save)
