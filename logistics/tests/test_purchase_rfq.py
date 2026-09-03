"""ISSUE #112 — PurchaseRFQ: نماذج ودورة حياة الطلبية (طلب عروض أسعار).

سطح DRF وحده (`docs/agents` سابقة: test_supplier_quotations.py،
test_stage_machine.py، test_tenant_isolation.py) — لا اختبار دوال مباشرة.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from inventory.models import Product
from logistics.models import PurchaseRFQ, PurchaseRFQRecipient, SupplierQuotation
from partners.models import Partner
from tenants.models import Currency, Tenant, UserCompanyMembership


class PurchaseRFQAPITestBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=881, CompanyName='RFQ Co')
        cls.other_tenant = Tenant.objects.create(TenantID=882, CompanyName='Other RFQ Co')
        # ISSUE #116: الترسية تحتاج عملة أساسية موجودة — `submit_rfq_supplier_quote`
        # يختار عملة العرض المتولّد منها إن لم تُمرَّر صراحةً.
        cls.currency = Currency.objects.create(Code='ILS', Name='New Shekel', IsBaseCurrency=True)
        cls.user = User.objects.create_user(username='rfq-owner', password='x')
        UserCompanyMembership.objects.create(user=cls.user, tenant=cls.tenant, role='manager')
        UserCompanyMembership.objects.create(user=cls.user, tenant=cls.other_tenant, role='manager')
        cls.supplier_a = Partner.objects.create(
            tenant=cls.tenant, name='Supplier A', partner_type='Supplier',
        )
        cls.supplier_b = Partner.objects.create(
            tenant=cls.tenant, name='Supplier B', partner_type='Supplier',
        )
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name='Not A Supplier', partner_type='Customer',
        )
        cls.other_supplier = Partner.objects.create(
            tenant=cls.other_tenant, name='Other Supplier', partner_type='Supplier',
        )
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku='RFQ-1', name_ar='منتج طلبية',
        )
        cls.other_product = Product.objects.create(
            tenant=cls.other_tenant, sku='RFQ-OTHER-1', name_ar='منتج آخر',
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def payload(self, **overrides):
        payload = {
            'scope': 'local',
            'rfq_date': '2026-08-01',
            'reply_deadline': '2026-08-10',
            'notes': 'طلبية تجريبية',
            'lines': [{
                'product': self.product.id,
                'seq': 1,
                'quantity': '5.000',
                'unit_of_measure': 'حبة',
                'specs': 'مواصفة تجريبية',
            }],
        }
        payload.update(overrides)
        return payload

    def create_rfq(self, **overrides):
        response = self.client.post(
            '/api/logistics/purchase-rfqs/', self.payload(**overrides), format='json',
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.data


class PurchaseRFQCreateTest(PurchaseRFQAPITestBase):
    def test_create_with_lines_without_any_price_reads_back_as_written(self):
        data = self.create_rfq()
        self.assertIsNone(data['rfq_number'])
        self.assertEqual(data['status'], 'draft')
        self.assertEqual(len(data['lines']), 1)
        line = data['lines'][0]
        self.assertNotIn('unit_price', line)
        self.assertNotIn('price', line)
        self.assertIsNone(line['estimated_price'])
        self.assertEqual(line['unit_of_measure'], 'حبة')

        rfq = PurchaseRFQ.objects.get(pk=data['id'])
        self.assertEqual(rfq.tenant, self.tenant)
        self.assertIsNone(rfq.rfq_number)
        self.assertEqual(rfq.lines.get().name_snapshot, 'منتج طلبية')

        detail = self.client.get(f"/api/logistics/purchase-rfqs/{data['id']}/")
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertEqual(detail.data['lines'][0]['quantity'], '5.000')

    def test_line_with_free_text_name_and_no_registered_product_is_accepted(self):
        lines = [{
            'seq': 1,
            'name_snapshot': 'صنفٌ غير مسجَّل',
            'quantity': '2.000',
            'unit_of_measure': 'كرتون',
        }]
        data = self.create_rfq(lines=lines)
        self.assertIsNone(data['lines'][0]['product'])
        self.assertEqual(data['lines'][0]['name_snapshot'], 'صنفٌ غير مسجَّل')

    def test_line_without_product_or_name_is_rejected(self):
        lines = [{'seq': 1, 'quantity': '2.000'}]
        response = self.client.post(
            '/api/logistics/purchase-rfqs/', self.payload(lines=lines), format='json',
        )
        self.assertEqual(response.status_code, 400, response.content)

    def test_no_hs_code_field_exists_regardless_of_scope(self):
        local_data = self.create_rfq(scope='local')
        import_data = self.create_rfq(scope='import')
        for data in (local_data, import_data):
            self.assertNotIn('hs_code', data['lines'][0])

    def test_product_from_another_tenant_is_rejected(self):
        lines = [{
            'product': self.other_product.id, 'seq': 1, 'quantity': '1.000',
        }]
        response = self.client.post(
            '/api/logistics/purchase-rfqs/', self.payload(lines=lines), format='json',
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn('lines', response.data)


class PurchaseRFQLifecycleTest(PurchaseRFQAPITestBase):
    def test_sent_rfq_rejects_line_edit_but_accepts_new_recipient(self):
        data = self.create_rfq()
        rfq_id = data['id']

        send = self.client.post(f'/api/logistics/purchase-rfqs/{rfq_id}/send/')
        self.assertEqual(send.status_code, 200, send.content)
        self.assertEqual(send.data['status'], 'sent')
        self.assertIsNotNone(send.data['rfq_number'])

        line_edit = self.client.patch(
            f'/api/logistics/purchase-rfqs/{rfq_id}/',
            {'lines': [{'seq': 1, 'quantity': '99.000', 'name_snapshot': 'تلاعب'}]},
            format='json',
        )
        self.assertEqual(line_edit.status_code, 400, line_edit.content)
        self.assertEqual(
            PurchaseRFQ.objects.get(pk=rfq_id).lines.get().quantity, Decimal('5.000'),
        )

        add_recipient = self.client.post(
            f'/api/logistics/purchase-rfqs/{rfq_id}/recipients/',
            {'supplier': self.supplier_a.id}, format='json',
        )
        self.assertEqual(add_recipient.status_code, 201, add_recipient.content)
        self.assertEqual(
            PurchaseRFQRecipient.objects.filter(rfq_id=rfq_id).count(), 1,
        )

    def test_sent_rfq_allows_editing_notes_and_deadline(self):
        data = self.create_rfq()
        rfq_id = data['id']
        self.client.post(f'/api/logistics/purchase-rfqs/{rfq_id}/send/')

        response = self.client.patch(
            f'/api/logistics/purchase-rfqs/{rfq_id}/',
            {'notes': 'ملاحظة بعد الإرسال', 'reply_deadline': '2026-09-01'},
            format='json',
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data['notes'], 'ملاحظة بعد الإرسال')

    def test_draft_to_sent_to_awarded_transitions_are_allowed(self):
        """ISSUE #116: الترسية تحتاج مورداً ردّ فعلياً — تُنتج فاتورة شراء
        افتراضياً (`use_purchase_orders` مطفأ)."""
        from logistics.services import submit_rfq_supplier_quote

        data = self.create_rfq()
        rfq_id = data['id']
        line_id = data['lines'][0]['id']

        send = self.client.post(
            f'/api/logistics/purchase-rfqs/{rfq_id}/send/',
            {'supplier_ids': [self.supplier_a.id]}, format='json',
        )
        self.assertEqual(send.status_code, 200, send.content)

        recipient = PurchaseRFQRecipient.objects.get(rfq_id=rfq_id, supplier=self.supplier_a)
        submit_rfq_supplier_quote(recipient, name='Rep A', prices={line_id: Decimal('10')})

        award = self.client.post(
            f'/api/logistics/purchase-rfqs/{rfq_id}/award/',
            {'supplier': self.supplier_a.id}, format='json',
        )
        self.assertEqual(award.status_code, 200, award.content)
        self.assertEqual(award.data['status'], 'awarded')
        self.assertEqual(award.data['awarded_document']['type'], 'purchase_invoice')
        self.assertIsNotNone(award.data['awarded_document']['id'])

    def test_cannot_award_a_draft_rfq(self):
        data = self.create_rfq()
        award = self.client.post(f"/api/logistics/purchase-rfqs/{data['id']}/award/")
        self.assertEqual(award.status_code, 400, award.content)

    def test_award_requires_a_supplier(self):
        data = self.create_rfq()
        rfq_id = data['id']
        self.client.post(f'/api/logistics/purchase-rfqs/{rfq_id}/send/')
        award = self.client.post(f'/api/logistics/purchase-rfqs/{rfq_id}/award/')
        self.assertEqual(award.status_code, 400, award.content)
        self.assertIn('supplier', award.data)

    def test_cannot_award_to_a_supplier_who_has_not_replied(self):
        data = self.create_rfq()
        rfq_id = data['id']
        self.client.post(
            f'/api/logistics/purchase-rfqs/{rfq_id}/send/',
            {'supplier_ids': [self.supplier_a.id]}, format='json',
        )
        award = self.client.post(
            f'/api/logistics/purchase-rfqs/{rfq_id}/award/',
            {'supplier': self.supplier_a.id}, format='json',
        )
        self.assertEqual(award.status_code, 400, award.content)

    def test_cannot_send_a_non_draft_rfq_twice(self):
        data = self.create_rfq()
        rfq_id = data['id']
        self.client.post(f'/api/logistics/purchase-rfqs/{rfq_id}/send/')
        second_send = self.client.post(f'/api/logistics/purchase-rfqs/{rfq_id}/send/')
        self.assertEqual(second_send.status_code, 400, second_send.content)

    def test_cannot_cancel_an_awarded_rfq(self):
        from logistics.services import submit_rfq_supplier_quote

        data = self.create_rfq()
        rfq_id = data['id']
        line_id = data['lines'][0]['id']
        self.client.post(
            f'/api/logistics/purchase-rfqs/{rfq_id}/send/',
            {'supplier_ids': [self.supplier_a.id]}, format='json',
        )
        recipient = PurchaseRFQRecipient.objects.get(rfq_id=rfq_id, supplier=self.supplier_a)
        submit_rfq_supplier_quote(recipient, name='Rep A', prices={line_id: Decimal('10')})
        award = self.client.post(
            f'/api/logistics/purchase-rfqs/{rfq_id}/award/',
            {'supplier': self.supplier_a.id}, format='json',
        )
        self.assertEqual(award.status_code, 200, award.content)
        cancel = self.client.post(f'/api/logistics/purchase-rfqs/{rfq_id}/cancel/')
        self.assertEqual(cancel.status_code, 400, cancel.content)

    def test_cancel_allowed_from_draft_and_from_sent(self):
        draft_data = self.create_rfq()
        cancel_draft = self.client.post(
            f"/api/logistics/purchase-rfqs/{draft_data['id']}/cancel/",
        )
        self.assertEqual(cancel_draft.status_code, 200, cancel_draft.content)
        self.assertEqual(cancel_draft.data['status'], 'cancelled')

        sent_data = self.create_rfq()
        self.client.post(f"/api/logistics/purchase-rfqs/{sent_data['id']}/send/")
        cancel_sent = self.client.post(
            f"/api/logistics/purchase-rfqs/{sent_data['id']}/cancel/",
        )
        self.assertEqual(cancel_sent.status_code, 200, cancel_sent.content)

    def test_recipient_must_be_a_registered_supplier_of_current_tenant(self):
        data = self.create_rfq()
        rfq_id = data['id']

        not_supplier = self.client.post(
            f'/api/logistics/purchase-rfqs/{rfq_id}/recipients/',
            {'supplier': self.customer.id}, format='json',
        )
        self.assertEqual(not_supplier.status_code, 400, not_supplier.content)

        foreign_supplier = self.client.post(
            f'/api/logistics/purchase-rfqs/{rfq_id}/recipients/',
            {'supplier': self.other_supplier.id}, format='json',
        )
        self.assertEqual(foreign_supplier.status_code, 400, foreign_supplier.content)


class PurchaseRFQNumberingTest(PurchaseRFQAPITestBase):
    def test_number_allocated_on_first_send_and_abandoned_draft_burns_none(self):
        first = self.create_rfq()
        abandoned = self.create_rfq()  # مسودّة تُترك بلا إرسال أبداً
        self.assertIsNone(first['rfq_number'])
        self.assertIsNone(abandoned['rfq_number'])

        send_first = self.client.post(f"/api/logistics/purchase-rfqs/{first['id']}/send/")
        self.assertEqual(send_first.status_code, 200, send_first.content)
        self.assertEqual(send_first.data['rfq_number'], 'RFQ-0001')

        second = self.create_rfq()
        send_second = self.client.post(f"/api/logistics/purchase-rfqs/{second['id']}/send/")
        self.assertEqual(send_second.status_code, 200, send_second.content)
        # المسودّة المهجورة بينهما لم تحرق رقماً — الثانية المُرسَلة فعلياً تحمل 0002 لا 0003.
        self.assertEqual(send_second.data['rfq_number'], 'RFQ-0002')

    def test_send_requires_at_least_one_line(self):
        response = self.client.post(
            '/api/logistics/purchase-rfqs/',
            self.payload(lines=[{
                'product': self.product.id, 'seq': 1, 'quantity': '1.000',
            }]),
            format='json',
        )
        rfq_id = response.data['id']
        # نُفرغ البنود مباشرةً عبر النموذج لمحاكاة طلبية بلا بند (المسلسِل يمنع هذا عادةً).
        PurchaseRFQ.objects.get(pk=rfq_id).lines.all().delete()
        send = self.client.post(f'/api/logistics/purchase-rfqs/{rfq_id}/send/')
        self.assertEqual(send.status_code, 400, send.content)


class PurchaseRFQReplyCounterTest(PurchaseRFQAPITestBase):
    def test_replies_counter_is_derived_not_stored(self):
        data = self.create_rfq()
        rfq_id = data['id']
        self.client.post(f'/api/logistics/purchase-rfqs/{rfq_id}/send/')
        self.client.post(
            f'/api/logistics/purchase-rfqs/{rfq_id}/recipients/',
            {'supplier': self.supplier_a.id}, format='json',
        )
        self.client.post(
            f'/api/logistics/purchase-rfqs/{rfq_id}/recipients/',
            {'supplier': self.supplier_b.id}, format='json',
        )

        detail = self.client.get(f'/api/logistics/purchase-rfqs/{rfq_id}/')
        self.assertEqual(detail.data['recipients_count'], 2)
        self.assertEqual(detail.data['replies_count'], 0)

        # ردّ مورد واحد يُحاكى مباشرةً — توليد العرض الفعلي عبر docshare خارج هذه التذكرة.
        recipient = PurchaseRFQRecipient.objects.filter(
            rfq_id=rfq_id, supplier=self.supplier_a,
        ).get()
        from django.utils import timezone
        recipient.replied_at = timezone.now()
        recipient.save(update_fields=['replied_at'])

        detail_after = self.client.get(f'/api/logistics/purchase-rfqs/{rfq_id}/')
        self.assertEqual(detail_after.data['recipients_count'], 2)
        self.assertEqual(detail_after.data['replies_count'], 1)


class PurchaseRFQTenantIsolationTest(PurchaseRFQAPITestBase):
    def test_rfq_from_another_tenant_is_not_readable(self):
        data = self.create_rfq()
        rfq_id = data['id']

        self.client.credentials(HTTP_X_TENANT_ID=str(self.other_tenant.TenantID))
        detail = self.client.get(f'/api/logistics/purchase-rfqs/{rfq_id}/')
        self.assertEqual(detail.status_code, 404)

        listing = self.client.get('/api/logistics/purchase-rfqs/')
        self.assertEqual(listing.status_code, 200, listing.content)
        rows = listing.data['results'] if isinstance(listing.data, dict) else listing.data
        ids = [row['id'] for row in rows]
        self.assertNotIn(rfq_id, ids)

    def test_no_tenant_header_returns_empty_queryset_not_a_leak(self):
        self.create_rfq()
        self.client.credentials()  # بلا ترويسة X-Tenant-Id
        listing = self.client.get('/api/logistics/purchase-rfqs/')
        self.assertIn(listing.status_code, (200, 400))
        if listing.status_code == 200:
            rows = listing.data['results'] if isinstance(listing.data, dict) else listing.data
            self.assertEqual(len(rows), 0)


class PurchaseRFQShareWiringTest(PurchaseRFQAPITestBase):
    """ISSUE #115: `send/` و`recipients/` يمنحان كلّ مستقبِلٍ رابطه الخاص."""

    def test_send_with_supplier_ids_wires_a_share_per_recipient(self):
        data = self.create_rfq()
        rfq_id = data['id']

        send = self.client.post(
            f'/api/logistics/purchase-rfqs/{rfq_id}/send/',
            {'supplier_ids': [self.supplier_a.id, self.supplier_b.id]},
            format='json',
        )
        self.assertEqual(send.status_code, 200, send.content)

        recipients = list(PurchaseRFQRecipient.objects.filter(rfq_id=rfq_id))
        self.assertEqual(len(recipients), 2)
        for recipient in recipients:
            self.assertIsNotNone(recipient.share_id)

        # كلٌّ منهما توكِنٌ مستقلّ — لا رابطاً واحداً مُعاد استعماله للاثنين.
        tokens = {r.share.token for r in recipients}
        self.assertEqual(len(tokens), 2)
        for recipient in recipients:
            self.assertEqual(recipient.share.doc_type, 'purchase_rfq')
            self.assertEqual(recipient.share.doc_id, rfq_id)

    def test_recipient_added_after_send_gets_a_share_too(self):
        data = self.create_rfq()
        rfq_id = data['id']
        self.client.post(f'/api/logistics/purchase-rfqs/{rfq_id}/send/')

        add_recipient = self.client.post(
            f'/api/logistics/purchase-rfqs/{rfq_id}/recipients/',
            {'supplier': self.supplier_a.id}, format='json',
        )
        self.assertEqual(add_recipient.status_code, 201, add_recipient.content)
        self.assertIsNotNone(add_recipient.data['share'])

        recipient = PurchaseRFQRecipient.objects.get(rfq_id=rfq_id, supplier=self.supplier_a)
        self.assertIsNotNone(recipient.share_id)

    def test_recipient_added_before_send_gets_a_share_once_sent(self):
        data = self.create_rfq()
        rfq_id = data['id']

        # مستقبِلٌ يُضاف والطلبية ما تزال مسودّة — حالةٌ نادرة يسمح بها الحارس.
        add_recipient = self.client.post(
            f'/api/logistics/purchase-rfqs/{rfq_id}/recipients/',
            {'supplier': self.supplier_a.id}, format='json',
        )
        self.assertEqual(add_recipient.status_code, 201, add_recipient.content)
        recipient = PurchaseRFQRecipient.objects.get(rfq_id=rfq_id, supplier=self.supplier_a)
        self.assertIsNone(recipient.share_id)

        send = self.client.post(f'/api/logistics/purchase-rfqs/{rfq_id}/send/')
        self.assertEqual(send.status_code, 200, send.content)

        recipient.refresh_from_db()
        self.assertIsNotNone(recipient.share_id)


class SupplierQuotationRfqLinkTest(PurchaseRFQAPITestBase):
    def test_supplier_quotation_optional_rfq_field_defaults_to_none(self):
        """SupplierQuotation.rfq اختياري — عروضٌ مستقلّة قائمة تبقى صحيحة بلا ربط."""
        quotation = SupplierQuotation.objects.create(
            tenant=self.tenant,
            quotation_number='PQ-STANDALONE-1',
            scope='local',
            supplier=self.supplier_a,
            quotation_date='2026-08-01',
            currency_id=self._currency_id(),
        )
        self.assertIsNone(quotation.rfq_id)

    def _currency_id(self):
        from tenants.models import Currency
        return Currency.objects.create(Code='RFQ', Name='RFQ currency').pk
