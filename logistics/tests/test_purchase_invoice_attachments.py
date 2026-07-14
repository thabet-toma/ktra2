"""W7c — مرفقات فاتورة/مرجع الشراء تُحفظ خادمياً وتُعاد في السيريالايزر.

بلاغ المالك: الصورة المرفوعة على مرجع الشراء «لا تظهر». الجذر المؤكَّد من الكود:
`AttachmentsSection` (المشترك) يرفع الصور إلى Cloudinary ويكتبها في `formData.quote_images`،
لكن فاتورة الشراء لم يكن لها **أي** مسار حفظ خادمي للمرفقات ولا عرضٌ لها في السيريالايزر
(المكوّن بُني للصفقات/عروض الأسعار وأُعيد استخدامه على فاتورة الشراء بلا ربط خلفي).
هنا: (أ) القراءة — GET يُعيد quote_images/quote_pdfs من SystemAttachment، و(ب) الحفظ —
PATCH يكتب الروابط في SystemAttachment (related_table='purchase_invoices').

SystemAttachment مُدار خارجياً (managed=False) فلا يُبنى جدوله في قاعدة الاختبار — نُموّهه
(نفس نمط inventory/tests/test_product_api.py) ونتحقّق من استدعاءات create/القراءة.
"""
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token

from tenants.models import Tenant, Currency, UserCompanyMembership
from partners.models import Partner
from logistics.models import PurchaseInvoice


class _Base(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=941, CompanyName='Att Co')
        cls.cur, _ = Currency.objects.get_or_create(
            Code='ILS', defaults={'Symbol': '₪', 'IsBaseCurrency': True})
        cls.user = User.objects.create_user(username='att_user', password='x')
        Token.objects.create(user=cls.user)
        UserCompanyMembership.objects.create(user=cls.user, tenant=cls.tenant, role='manager')
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name='Supplier A', partner_type='Supplier')

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def _mk_invoice(self, number='PI-1'):
        return PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number=number, invoice_date='2026-07-01',
            partner=self.partner, currency=self.cur, grand_total=Decimal('0'))

    def _url(self, inv):
        return f'/api/logistics/purchase-invoices/{inv.id}/'


class ReadBackTest(_Base):
    def test_get_exposes_existing_image_attachment(self):
        inv = self._mk_invoice()
        row = SimpleNamespace(file_type='Image', file_path='https://res.cloudinary.com/x/img1.jpg')
        with patch('core.models.SystemAttachment') as MockSA:
            MockSA.objects.filter.return_value.order_by.return_value = [row]
            resp = self.client.get(self._url(inv))
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        self.assertIn('https://res.cloudinary.com/x/img1.jpg', resp.data.get('quote_images', []))

    def test_pdf_not_listed_as_image(self):
        inv = self._mk_invoice('PI-2')
        row = SimpleNamespace(file_type='PDF', file_path='https://res.cloudinary.com/x/doc1.pdf')
        with patch('core.models.SystemAttachment') as MockSA:
            MockSA.objects.filter.return_value.order_by.return_value = [row]
            resp = self.client.get(self._url(inv))
        self.assertEqual(resp.status_code, 200, resp.content[:300])
        self.assertNotIn('https://res.cloudinary.com/x/doc1.pdf', resp.data.get('quote_images', []))
        pdf_urls = [p.get('url') for p in resp.data.get('quote_pdfs', [])]
        self.assertIn('https://res.cloudinary.com/x/doc1.pdf', pdf_urls)


class PersistTest(_Base):
    def test_patch_persists_image_url_to_attachment(self):
        inv = self._mk_invoice('PI-3')
        url = 'https://res.cloudinary.com/x/new.jpg'
        with patch('core.models.SystemAttachment') as MockSA:
            MockSA.objects.filter.return_value.exists.return_value = False
            MockSA.objects.filter.return_value.order_by.return_value = []
            resp = self.client.patch(
                self._url(inv), {'quote_images': [url]}, format='json')
        self.assertIn(resp.status_code, (200, 202), resp.content[:300])
        img_calls = [
            c.kwargs for c in MockSA.objects.create.call_args_list
            if c.kwargs.get('file_type') == 'Image'
        ]
        self.assertEqual(len(img_calls), 1)
        self.assertEqual(img_calls[0]['file_path'], url)
        self.assertEqual(img_calls[0]['related_table'], 'purchase_invoices')
        self.assertEqual(img_calls[0]['related_id'], inv.id)

    def test_patch_persists_pdf_url_to_attachment(self):
        inv = self._mk_invoice('PI-4')
        url = 'https://res.cloudinary.com/x/cat.pdf'
        with patch('core.models.SystemAttachment') as MockSA:
            MockSA.objects.filter.return_value.exists.return_value = False
            MockSA.objects.filter.return_value.order_by.return_value = []
            resp = self.client.patch(
                self._url(inv),
                {'quote_pdfs': [{'name': 'cat.pdf', 'url': url}]}, format='json')
        self.assertIn(resp.status_code, (200, 202), resp.content[:300])
        pdf_calls = [
            c.kwargs for c in MockSA.objects.create.call_args_list
            if c.kwargs.get('file_type') == 'PDF'
        ]
        self.assertEqual(len(pdf_calls), 1)
        self.assertEqual(pdf_calls[0]['file_path'], url)
        self.assertEqual(pdf_calls[0]['related_table'], 'purchase_invoices')
