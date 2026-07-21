"""قائمة الصفقات تعرض «تحولت إلى فاتورة» — رابط لرقم الفاتورة بجانب الحالة.

الصفقة المحوَّلة يجب أن تعرض رقم فاتورتها الناتجة في القائمة (لا التفصيل فقط)،
وإلا لا يظهر شيء بجانب الحالة.
"""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.services import create_fiscal_year
from logistics.models import LogisticsDeal, PurchaseInvoice
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company


class DealListLinkedInvoiceTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="dli", password="x", email="dli@x.co")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة رابط الفاتورة", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="مورد", partner_type="Supplier")
        cls.deal = LogisticsDeal.objects.create(
            tenant=cls.tenant, partner=cls.partner, ref_number="D-0200",
            order_date="2026-06-01", currency=cls.ils,
            short_name="صفقة محوَّلة",
        )
        cls.deal_plain = LogisticsDeal.objects.create(
            tenant=cls.tenant, partner=cls.partner, ref_number="D-0201",
            order_date="2026-06-02", currency=cls.ils,
            short_name="صفقة بلا فاتورة",
        )

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _rows(self, resp):
        d = resp.json()
        return d.get("results", d) if isinstance(d, dict) else d

    def test_list_exposes_linked_invoice(self):
        PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number="INV-0003", partner=self.partner,
            currency=self.ils, invoice_date="2026-06-20", deal=self.deal,
        )
        resp = self.client.get("/api/logistics/deals/", **self._auth())
        self.assertEqual(resp.status_code, 200, resp.content)
        row = next(r for r in self._rows(resp) if r["ref_number"] == "D-0200")
        self.assertIsNotNone(row["linked_invoice"])
        self.assertEqual(row["linked_invoice"]["invoice_number"], "INV-0003")

    def test_deal_without_invoice_has_no_link(self):
        resp = self.client.get("/api/logistics/deals/", **self._auth())
        row = next(r for r in self._rows(resp) if r["ref_number"] == "D-0201")
        self.assertIsNone(row["linked_invoice"])
