"""حالة عرض السعر ودفتر ملاحظاته (T-OFFERSTATE).

الفجوتان اللتان يحرسهما هذا الملف:

1. **الحالة المختارة داخل العرض لم تكن هي الحالة المخزَّنة**: «بانتظار معلومات»
   و«قيد المناقشة» كانتا تُسقَطان كلتاهما على `sent`، فتقرأ القائمة «مُرسَل
   للمورد» مهما اخترتَ بالداخل. الآن لكلٍّ حالة حقيقية في الخادم، و«بانتظار
   معلومات» تلزمها كتابة **بانتظار ماذا** (نفس قاعدة «غير ملائم» تلزمه سبب).
2. **ملاحظة واحدة بلا تاريخ**: `notes` نصٌّ واحد يُدهس عند كل تعديل. `notes_log`
   دفتر ملاحظات مؤرَّخ — والتاريخ من الخادم لا من ساعة المتصفح.
"""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from core.models import ActivityLog
from inventory.models import Product
from logistics.models import SupplierQuotation
from partners.models import Partner
from tenants.models import Currency, Tenant, UserCompanyMembership


class QuotationStatusAndNotesTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=993, CompanyName='Offer State Co')
        cls.currency = Currency.objects.create(
            Code='OST', Name='Offer state currency', IsBaseCurrency=False,
        )
        cls.user = User.objects.create_user(username='offer-state', password='x')
        UserCompanyMembership.objects.create(
            user=cls.user, tenant=cls.tenant, role='manager',
        )
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name='مصنع الحالات', partner_type='Supplier',
            supplier_scope=Partner.SUPPLIER_SCOPE_INTERNATIONAL,
        )
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku='OST-1', name_ar='منتج الحالات',
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def payload(self, **overrides):
        body = {
            'scope': 'import',
            'supplier': self.supplier.id,
            'quotation_date': '2026-08-01',
            'currency': self.currency.pk,
            'exchange_rate': '1.000000',
            'discount_amount': '0',
            'tax_rate': '0',
            'shipping_cost_estimate': '0',
            'is_shipping_included': True,
            'lines': [{
                'product': self.product.id,
                'seq': 1,
                'quantity': '1.000',
                'unit_price': '10.0000',
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

    # ── الحالة تُخزَّن كما اختيرت ─────────────────────────────────────
    def test_pending_info_is_a_real_status_not_collapsed_to_sent(self):
        created = self.create_quote(
            status='pending_info', decision_reason='بانتظار شهادة المنشأ',
        )
        self.assertEqual(created.data['status'], 'pending_info')
        stored = SupplierQuotation.objects.get(pk=created.data['id'])
        self.assertEqual(stored.status, SupplierQuotation.STATUS_PENDING_INFO)
        fetched = self.client.get(
            f"/api/logistics/supplier-quotations/{created.data['id']}/",
        )
        self.assertEqual(fetched.data['status'], 'pending_info')
        self.assertEqual(fetched.data['decision_reason'], 'بانتظار شهادة المنشأ')

    def test_under_discussion_is_a_real_status(self):
        created = self.create_quote(status='under_discussion')
        self.assertEqual(created.data['status'], 'under_discussion')
        self.assertEqual(
            SupplierQuotation.objects.get(pk=created.data['id']).status,
            SupplierQuotation.STATUS_UNDER_DISCUSSION,
        )

    def test_pending_info_requires_saying_what_is_awaited(self):
        created = self.create_quote()
        quote_id = created.data['id']
        without = self.client.patch(
            f'/api/logistics/supplier-quotations/{quote_id}/',
            {'status': 'pending_info'}, format='json',
        )
        self.assertEqual(without.status_code, 400)
        self.assertIn('decision_reason', without.data)

        with_reason = self.client.patch(
            f'/api/logistics/supplier-quotations/{quote_id}/',
            {'status': 'pending_info', 'decision_reason': 'بانتظار عيّنة من المصنع'},
            format='json',
        )
        self.assertEqual(with_reason.status_code, 200, with_reason.content)
        self.assertEqual(with_reason.data['decision_reason'], 'بانتظار عيّنة من المصنع')

    def test_moving_to_suitable_clears_the_awaited_note(self):
        created = self.create_quote(
            status='pending_info', decision_reason='بانتظار عيّنة',
        )
        accepted = self.client.patch(
            f"/api/logistics/supplier-quotations/{created.data['id']}/",
            {'status': 'accepted'}, format='json',
        )
        self.assertEqual(accepted.status_code, 200, accepted.content)
        self.assertEqual(accepted.data['decision_reason'], '')

    def test_status_change_is_written_to_the_activity_log_with_its_reason(self):
        created = self.create_quote()
        self.client.patch(
            f"/api/logistics/supplier-quotations/{created.data['id']}/",
            {'status': 'pending_info', 'decision_reason': 'بانتظار كتالوج'},
            format='json',
        )
        entries = ActivityLog.objects.filter(
            entity_type='supplier_quotation', entity_id=created.data['id'],
            action='update',
        )
        self.assertTrue(
            any('بانتظار كتالوج' in (e.description or '') for e in entries),
            list(entries.values_list('description', flat=True)),
        )

    # ── دفتر الملاحظات المؤرَّخ ───────────────────────────────────────
    def test_notes_log_keeps_several_dated_notes(self):
        created = self.create_quote(notes_log=[
            {'text': 'المورد وعد بخصم 5%'},
            {'text': 'طلبنا صور إضافية'},
        ])
        entries = created.data['notes_log']
        self.assertEqual([e['text'] for e in entries],
                         ['المورد وعد بخصم 5%', 'طلبنا صور إضافية'])
        # التاريخ والكاتب من الخادم — لا من ساعة المتصفح.
        self.assertTrue(all(e.get('at') for e in entries))
        self.assertTrue(all(e.get('by') == 'offer-state' for e in entries))

    def test_existing_note_keeps_its_original_date_when_a_new_one_is_added(self):
        created = self.create_quote(notes_log=[{'text': 'ملاحظة أولى'}])
        first_at = created.data['notes_log'][0]['at']
        updated = self.client.patch(
            f"/api/logistics/supplier-quotations/{created.data['id']}/",
            {'notes_log': created.data['notes_log'] + [{'text': 'ملاحظة ثانية'}]},
            format='json',
        )
        self.assertEqual(updated.status_code, 200, updated.content)
        entries = updated.data['notes_log']
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0]['at'], first_at)
        self.assertTrue(entries[1]['at'])

    def test_notes_log_rejects_a_malformed_payload(self):
        not_a_list = self.client.post(
            '/api/logistics/supplier-quotations/',
            self.payload(notes_log={'text': 'x'}), format='json',
        )
        self.assertEqual(not_a_list.status_code, 400)
        self.assertIn('notes_log', not_a_list.data)

        empty_text = self.client.post(
            '/api/logistics/supplier-quotations/',
            self.payload(notes_log=[{'text': '   '}]), format='json',
        )
        self.assertEqual(empty_text.status_code, 400)
        self.assertIn('notes_log', empty_text.data)
