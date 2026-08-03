"""نسب مستندات الشراء (T-PLINEAGE): عرض السعر → فاتورة مباشرةً، والرابط بالاتجاهين.

الفجوتان اللتان يحرسهما هذا الملف:
1. عرض الشراء المقبول كان يُحوَّل إلى **طلبية فقط** — لا طريق مباشر إلى فاتورة.
2. المستند الناتج لم يكن موصولاً بمصدره: الفاتورة لا تقول من أين جاءت، والعرض
   لا يقول أين انتهى. الآن الطرفان يحملان رقم الآخر ومعرّفه.
"""
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from inventory.models import Product, StockMovement
from logistics.models import PurchaseInvoice, PurchaseOrder, SupplierQuotation
from partners.models import Partner
from tenants.models import Currency, Tenant, UserCompanyMembership


class PurchaseDocumentLineageTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=991, CompanyName='Lineage Co')
        cls.currency = Currency.objects.create(
            Code='LNG', Name='Lineage currency', IsBaseCurrency=False,
        )
        cls.user = User.objects.create_user(username='lineage-boss', password='x')
        UserCompanyMembership.objects.create(
            user=cls.user, tenant=cls.tenant, role='manager',
        )
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name='مورد النسب', partner_type='Supplier',
        )
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku='LNG-1', name_ar='صنف النسب',
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def _quote(self, **overrides):
        payload = {
            'scope': 'local',
            'supplier': self.supplier.id,
            'quotation_date': '2026-07-26',
            'valid_until': '2026-08-10',
            'status': 'accepted',
            'currency': self.currency.pk,
            'exchange_rate': '1.000000',
            'discount_amount': '0',
            'tax_rate': '0',
            'shipping_cost_estimate': '0',
            'is_shipping_included': True,
            'lines': [{
                'product': self.product.id,
                'seq': 1,
                'quantity': '3.000',
                'unit_price': '10.0000',
            }],
        }
        payload.update(overrides)
        response = self.client.post(
            '/api/logistics/supplier-quotations/', payload, format='json',
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.data['id']

    # ── عرض السعر → فاتورة مباشرةً ────────────────────────────────────
    def test_accepted_quotation_converts_straight_to_a_draft_invoice(self):
        quote_id = self._quote()
        url = (
            f'/api/logistics/supplier-quotations/{quote_id}/'
            'convert-to-purchase-invoice/'
        )
        first = self.client.post(url, {}, format='json')
        self.assertEqual(first.status_code, 201, first.content)
        invoice_id = first.data['invoice']['id']

        invoice = PurchaseInvoice.objects.get(pk=invoice_id)
        self.assertEqual(invoice.status, 'draft')
        self.assertFalse(invoice.is_posted)
        self.assertIsNone(invoice.journal_id)
        self.assertEqual(invoice.items.count(), 1)
        self.assertEqual(Decimal(invoice.grand_total), Decimal('30.00'))
        self.assertEqual(
            StockMovement.objects.filter(reference_id=invoice.id).count(), 0,
        )
        self.assertEqual(
            SupplierQuotation.objects.get(pk=quote_id).status,
            SupplierQuotation.STATUS_CONVERTED,
        )
        # لا طلبية وسيطة تُختلق: التحويل المباشر طريق واحد لا طريقان.
        self.assertEqual(PurchaseOrder.objects.count(), 0)

        repeated = self.client.post(url, {}, format='json')
        self.assertEqual(repeated.status_code, 200, repeated.content)
        self.assertEqual(repeated.data['invoice']['id'], invoice_id)
        self.assertEqual(PurchaseInvoice.objects.count(), 1)

    def test_quotation_already_turned_into_an_order_is_not_invoiced_twice(self):
        quote_id = self._quote()
        order = self.client.post(
            f'/api/logistics/supplier-quotations/{quote_id}/convert-to-purchase-order/',
            {}, format='json',
        )
        self.assertEqual(order.status_code, 201, order.content)
        blocked = self.client.post(
            f'/api/logistics/supplier-quotations/{quote_id}/convert-to-purchase-invoice/',
            {}, format='json',
        )
        self.assertEqual(blocked.status_code, 400)
        self.assertEqual(PurchaseInvoice.objects.count(), 0)

    def test_draft_quotation_cannot_be_invoiced(self):
        quote_id = self._quote(status='draft')
        response = self.client.post(
            f'/api/logistics/supplier-quotations/{quote_id}/convert-to-purchase-invoice/',
            {}, format='json',
        )
        self.assertEqual(response.status_code, 400)

    # ── الرابط بالاتجاهين ──────────────────────────────────────────────
    def test_quotation_exposes_the_invoice_it_produced(self):
        quote_id = self._quote()
        created = self.client.post(
            f'/api/logistics/supplier-quotations/{quote_id}/convert-to-purchase-invoice/',
            {}, format='json',
        )
        detail = self.client.get(f'/api/logistics/supplier-quotations/{quote_id}/')
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertEqual(
            detail.data['converted_invoice']['id'], created.data['invoice']['id'],
        )
        self.assertEqual(
            detail.data['converted_invoice']['invoice_number'],
            created.data['invoice']['invoice_number'],
        )
        self.assertIsNone(detail.data['converted_order'])

    def test_quotation_exposes_the_order_it_produced(self):
        quote_id = self._quote()
        created = self.client.post(
            f'/api/logistics/supplier-quotations/{quote_id}/convert-to-purchase-order/',
            {}, format='json',
        )
        detail = self.client.get(f'/api/logistics/supplier-quotations/{quote_id}/')
        self.assertEqual(
            detail.data['converted_order']['order_number'],
            created.data['order']['order_number'],
        )
        self.assertIsNone(detail.data['converted_invoice'])

    def test_invoice_names_the_quotation_it_came_from(self):
        quote_id = self._quote()
        created = self.client.post(
            f'/api/logistics/supplier-quotations/{quote_id}/convert-to-purchase-invoice/',
            {}, format='json',
        )
        invoice_id = created.data['invoice']['id']
        detail = self.client.get(f'/api/logistics/purchase-invoices/{invoice_id}/')
        self.assertEqual(detail.status_code, 200, detail.content)
        source = detail.data['source_document']
        self.assertEqual(source['kind'], 'quotation')
        self.assertEqual(source['id'], quote_id)
        self.assertEqual(
            source['number'],
            SupplierQuotation.objects.get(pk=quote_id).quotation_number,
        )

    def test_invoice_names_the_order_it_came_from(self):
        quote_id = self._quote()
        order = self.client.post(
            f'/api/logistics/supplier-quotations/{quote_id}/convert-to-purchase-order/',
            {}, format='json',
        ).data['order']
        self.client.post(
            f"/api/logistics/purchase-orders/{order['id']}/confirm/", {}, format='json',
        )
        created = self.client.post(
            f"/api/logistics/purchase-orders/{order['id']}/convert-to-invoice/",
            {}, format='json',
        )
        invoice_id = created.data['invoice']['id']
        detail = self.client.get(f'/api/logistics/purchase-invoices/{invoice_id}/')
        source = detail.data['source_document']
        self.assertEqual(source['kind'], 'order')
        self.assertEqual(source['id'], order['id'])
        self.assertEqual(source['number'], order['order_number'])
        # نسب كامل: الطلبية جاءت من عرض، فيُذكر العرض أيضاً.
        self.assertEqual(source['origin_kind'], 'quotation')
        self.assertEqual(source['origin_id'], quote_id)

    def test_invoice_without_a_source_reports_none(self):
        invoice = PurchaseInvoice.objects.create(
            tenant=self.tenant,
            invoice_number='INV-STANDALONE',
            invoice_date='2026-07-26',
            invoice_type=PurchaseInvoice.INVOICE_TYPE_LOCAL,
            partner=self.supplier,
            currency=self.currency,
        )
        detail = self.client.get(f'/api/logistics/purchase-invoices/{invoice.pk}/')
        self.assertIsNone(detail.data['source_document'])
