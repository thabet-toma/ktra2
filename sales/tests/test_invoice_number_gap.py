"""T-NUMGAP — عدّاد رقم الفاتورة يتخطّى الفجوة بدل 500 على المستخدم.

اكتُشف بالقياس الحيّ على جهاز المالك: «مدفوعة» على فاتورة جديدة تنتهي بـ
`IntegrityError: Duplicate entry '1-SI-1-2'` لأن `TenantBook.last_used_number`
متخلّفٌ عن فواتير موجودة فعلاً (أُدخلت بأرقامٍ يدوية أو باستيرادٍ قديم لا يمرّ
بالعدّاد). إعادة المحاولة **الواحدة** القديمة تسقط على الرقم المحجوز التالي
فيصل التصادم إلى المستخدم 500 — و«أحياناً يعمل» لأن الفشل رهن حجم الفجوة.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.services import create_fiscal_year
from inventory.models import Product
from partners.models import Partner
from sales.models import SalesInvoice
from tenants.models import Currency, TenantBook
from tenants.services import create_company


class InvoiceNumberGapTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="numgap", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة الفجوة", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="زبون الفجوة", partner_type="Customer")
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="GAP-1", name_ar="منتج",
            quantity_on_hand=Decimal("10"), avg_cost=Decimal("1"))

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.headers = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _manual_invoice(self, number):
        """فاتورة بأرقام يدوية لا تمرّ بالعدّاد — كما يفعل استيرادٌ قديم."""
        return SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number=number, customer=self.customer,
            currency=self.ils, invoice_date="2026-06-01",
            grand_total=Decimal("10"))

    def _create_via_api(self):
        return self.client.post(
            "/api/sales/invoices/",
            {
                "customer": self.customer.pk,
                "currency": self.ils.pk,
                "invoice_date": "2026-06-10",
                "invoice_type": "credit",
                "lines": [{"product": self.product.pk, "quantity": "1",
                           "unit_price": "10.00"}],
            },
            format="json", **self.headers)

    def test_counter_walks_past_a_multi_number_gap(self):
        """فجوةٌ بثلاثة أرقام محجوزة — المحاولةُ الواحدة القديمة كانت تنكسر
        على ثانيها ويصل «Duplicate entry» إلى المستخدم بدل فاتورته."""
        t = self.tenant.TenantID
        for n in (1, 2, 3):
            self._manual_invoice(f"SI-{t}-{n}")
        # العدّاد لم يرَ شيئاً من ذلك (دفتر 0 الافتراضي إمّا غائب أو صفر —
        # `create_company` تسبق بإنشاء دفاتر 1..10 فلا تُقاس هنا).
        assert not TenantBook.objects.filter(
            tenant_id=t, document_type="sales_invoice", book_number=0,
            last_used_number__gt=0).exists()

        res = self._create_via_api()

        assert res.status_code == 201, res.content
        assert res.json()["invoice_number"] == f"SI-{t}-4"
        # والعدّاد صار أمام الفجوة لا خلفها — الفواتير التالية بلا تصادم.
        book = TenantBook.objects.get(
            tenant_id=t, document_type="sales_invoice", book_number=0)
        assert book.last_used_number == 4

    def test_client_sent_duplicate_still_refused(self):
        """رقمٌ أرسله العميل صراحةً وتصادم — قرارُه يُرفض ولا يُستبدل بصمت."""
        t = self.tenant.TenantID
        self._manual_invoice(f"SI-{t}-7")
        res = self.client.post(
            "/api/sales/invoices/",
            {
                "customer": self.customer.pk,
                "currency": self.ils.pk,
                "invoice_date": "2026-06-10",
                "invoice_type": "credit",
                "invoice_number": f"SI-{t}-7",
                "lines": [{"product": self.product.pk, "quantity": "1",
                           "unit_price": "10.00"}],
            },
            format="json", **self.headers)
        assert res.status_code >= 400
        assert SalesInvoice.objects.filter(
            tenant_id=t, invoice_number=f"SI-{t}-7").count() == 1
