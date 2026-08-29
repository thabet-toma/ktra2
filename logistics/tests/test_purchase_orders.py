from decimal import Decimal
from importlib import import_module

from django.apps import apps
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from inventory.models import Product, StockMovement
from bridge.models import FirestoreMirrorDoc
from logistics.models import PurchaseInvoice, PurchaseOrder, SupplierQuotation
from partners.models import Partner
from tenants.models import Currency, Tenant, UserCompanyMembership


class PurchaseOrderAPITest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=981, CompanyName='Purchase Orders Co')
        cls.other_tenant = Tenant.objects.create(TenantID=982, CompanyName='Other PO Co')
        cls.currency = Currency.objects.create(
            Code='POT', Name='Purchase order currency', IsBaseCurrency=False,
        )
        cls.user = User.objects.create_user(username='purchase-orders', password='x')
        UserCompanyMembership.objects.create(
            user=cls.user, tenant=cls.tenant, role='manager',
        )
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name='Local Supplier', partner_type='Supplier',
        )
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name='Not Supplier', partner_type='Customer',
        )
        cls.other_supplier = Partner.objects.create(
            tenant=cls.other_tenant, name='Foreign Supplier', partner_type='Supplier',
        )
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku='PO-ITEM-1', name_ar='منتج طلبية',
        )
        cls.other_product = Product.objects.create(
            tenant=cls.other_tenant, sku='PO-ITEM-X', name_ar='منتج أجنبي',
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def order_payload(self, **overrides):
        payload = {
            'supplier': self.supplier.id,
            'order_date': '2026-07-26',
            'expected_delivery_date': '2026-08-10',
            'currency': self.currency.pk,
            'exchange_rate': '1.000000',
            'discount_amount': '2.00',
            'tax_rate': '10.00',
            'shipping_cost': '3.00',
            'is_shipping_included': False,
            'shipping_method': 'Local',
            'payment_method': 'Credit',
            'delivery_days': 15,
            'notes': 'طلبية محلية',
            'lines': [{
                'product': self.product.id,
                'seq': 1,
                'quantity': '2.000',
                'unit_price': '10.0000',
            }],
        }
        payload.update(overrides)
        return payload

    def quote_payload(self):
        return {
            'scope': 'local',
            'supplier': self.supplier.id,
            'quotation_date': '2026-07-26',
            'valid_until': '2026-08-10',
            'status': 'accepted',
            'currency': self.currency.pk,
            'exchange_rate': '1.000000',
            'discount_amount': '0',
            'tax_rate': '10',
            'shipping_cost_estimate': '0',
            'is_shipping_included': True,
            'lines': [{
                'product': self.product.id,
                'seq': 1,
                'quantity': '2.000',
                'unit_price': '10.0000',
            }],
        }

    def test_create_recalculates_totals_and_validates_related_tenant(self):
        response = self.client.post(
            '/api/logistics/purchase-orders/',
            self.order_payload(),
            format='json',
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data['order_number'], 'PO-0001')
        self.assertEqual(Decimal(response.data['subtotal']), Decimal('20.00'))
        self.assertEqual(Decimal(response.data['tax_amount']), Decimal('1.80'))
        self.assertEqual(Decimal(response.data['grand_total']), Decimal('22.80'))

        foreign_supplier = self.client.post(
            '/api/logistics/purchase-orders/',
            self.order_payload(supplier=self.other_supplier.id),
            format='json',
        )
        self.assertEqual(foreign_supplier.status_code, 400)
        self.assertIn('supplier', foreign_supplier.data)

        lines = self.order_payload()['lines']
        lines[0]['product'] = self.other_product.id
        foreign_product = self.client.post(
            '/api/logistics/purchase-orders/',
            self.order_payload(lines=lines),
            format='json',
        )
        self.assertEqual(foreign_product.status_code, 400)
        self.assertIn('lines', foreign_product.data)

        customer = self.client.post(
            '/api/logistics/purchase-orders/',
            self.order_payload(supplier=self.customer.id),
            format='json',
        )
        self.assertEqual(customer.status_code, 400)
        self.assertIn('supplier', customer.data)

    def test_local_quotation_conversion_is_idempotent(self):
        quote = self.client.post(
            '/api/logistics/supplier-quotations/',
            self.quote_payload(),
            format='json',
        )
        self.assertEqual(quote.status_code, 201, quote.content)
        url = (
            f"/api/logistics/supplier-quotations/{quote.data['id']}/"
            'convert-to-purchase-order/'
        )
        first = self.client.post(url, {}, format='json')
        self.assertEqual(first.status_code, 201, first.content)
        order_id = first.data['order']['id']
        second = self.client.post(url, {}, format='json')
        self.assertEqual(second.status_code, 200, second.content)
        self.assertEqual(second.data['order']['id'], order_id)
        self.assertEqual(PurchaseOrder.objects.count(), 1)
        self.assertEqual(
            SupplierQuotation.objects.get(pk=quote.data['id']).status,
            SupplierQuotation.STATUS_CONVERTED,
        )

    def test_confirm_rule_lives_in_the_service_not_in_the_view(self):
        """قاعدة التأكيد في `confirm_purchase_order` وحدها — لا نسخةَ في الـview.

        للطلبية طريقان إلى التأكيد: الشاشة عبر `PurchaseOrderViewSet.confirm`،
        والمورّد نفسه من رابط المشاركة العام عبر `docshare`. نسخُ الشروط في
        الموضعين يعني قاعدتين تنحرفان عند أول تعديل يُنسى في إحداهما.

        كان هذا الحارس يسكن `docshare/tests/test_order_decisions.py` — وهو
        مستدعي الطريق الثاني — فكان يستورد `logistics.views` من `docshare`
        ويكسر عقد «داخليات الـapps ليست واجهات عامة» في `.importlinter`. لكن
        ما يقيسه بنيةُ `logistics` نفسها، فمكانه هنا: الـapp يحرس تركيبه
        الداخلي بنفسه بلا أن يمدّ أحدٌ يده إلى داخليات جاره. وأثرُ ذلك على
        الرابط العام مقيسٌ هناك سلوكياً (القبول يغيّر الحالة فعلاً).
        """
        import inspect

        from logistics.services import confirm_purchase_order
        from logistics.views import procurement

        self.assertTrue(callable(confirm_purchase_order))
        source = inspect.getsource(procurement.PurchaseOrderViewSet.confirm)
        self.assertIn("confirm_purchase_order(", source)
        self.assertNotIn("STATUS_CONFIRMED", source, "قاعدة التأكيد عادت إلى الـview")

    def test_confirm_and_convert_creates_draft_invoice_without_posting_or_stock(self):
        created = self.client.post(
            '/api/logistics/purchase-orders/',
            self.order_payload(discount_amount='0', tax_rate='0', shipping_cost='0'),
            format='json',
        )
        self.assertEqual(created.status_code, 201, created.content)
        order_id = created.data['id']

        early = self.client.post(
            f'/api/logistics/purchase-orders/{order_id}/convert-to-invoice/',
            {},
            format='json',
        )
        self.assertEqual(early.status_code, 400)

        confirmed = self.client.post(
            f'/api/logistics/purchase-orders/{order_id}/confirm/',
            {},
            format='json',
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.content)
        converted = self.client.post(
            f'/api/logistics/purchase-orders/{order_id}/convert-to-invoice/',
            {},
            format='json',
        )
        self.assertEqual(converted.status_code, 201, converted.content)
        invoice_id = converted.data['invoice']['id']
        repeated = self.client.post(
            f'/api/logistics/purchase-orders/{order_id}/convert-to-invoice/',
            {},
            format='json',
        )
        self.assertEqual(repeated.status_code, 200, repeated.content)
        self.assertEqual(repeated.data['invoice']['id'], invoice_id)

        invoice = PurchaseInvoice.objects.get(pk=invoice_id)
        self.assertEqual(invoice.invoice_type, PurchaseInvoice.INVOICE_TYPE_LOCAL)
        self.assertEqual(invoice.status, 'draft')
        self.assertFalse(invoice.is_posted)
        self.assertIsNone(invoice.journal_id)
        self.assertEqual(invoice.receipt_status, PurchaseInvoice.RECEIPT_NOT)
        self.assertEqual(invoice.items.count(), 1)
        self.assertEqual(StockMovement.objects.filter(reference_id=invoice.id).count(), 0)

    def test_legacy_mapper_documents_migrate_without_deleting_source(self):
        quote_doc = FirestoreMirrorDoc.objects.create(
            path='price_offers/legacy-pq-1',
            tenant=self.tenant,
            data={
                'offerNumber': 'LEGACY-PQ-1',
                'offerType': 'incoming_offer',
                'supplierId': str(self.supplier.id),
                'offerDate': '2026-07-01',
                'currency': self.currency.Code,
                'status': 'under_discussion',
                'items': [{
                    'itemId': str(self.product.id),
                    'name': 'لقطة منتج',
                    'quantity': 2,
                    'unitPrice': 7,
                }],
            },
        )
        order_doc = FirestoreMirrorDoc.objects.create(
            path='price_offers/legacy-po-1',
            tenant=self.tenant,
            data={
                'offerNumber': 'LEGACY-PO-1',
                'offerType': 'outgoing_order',
                'supplierId': str(self.supplier.id),
                'offerDate': '2026-07-02',
                'currency': self.currency.Code,
                'items': [{
                    'itemId': str(self.product.id),
                    'quantity': 1,
                    'unitPrice': 9,
                }],
            },
        )

        migration = import_module(
            'logistics.migrations.0060_migrate_legacy_procurement_documents'
        )
        migration.migrate_documents(apps, None)

        self.assertTrue(SupplierQuotation.objects.filter(
            tenant=self.tenant,
            quotation_number='LEGACY-PQ-1',
            scope='local',
        ).exists())
        self.assertTrue(PurchaseOrder.objects.filter(
            tenant=self.tenant,
            order_number='LEGACY-PO-1',
        ).exists())
        self.assertTrue(FirestoreMirrorDoc.objects.filter(pk=quote_doc.pk).exists())
        self.assertTrue(FirestoreMirrorDoc.objects.filter(pk=order_doc.pk).exists())
