"""قائمة الفواتير تعرض اسم الصفقة المحوَّلة، لا رقمها فقط.

المستخدم يعرف الصفقة باسمها؛ القائمة كانت ترجع `deal_ref` (D-0113) فقط.
"""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.services import create_fiscal_year
from logistics.models import LogisticsDeal, PurchaseInvoice
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company


class InvoiceListDealTitleTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="ldt", password="x", email="ldt@x.co")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة اسم الصفقة", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="مورد", partner_type="Supplier")
        cls.deal = LogisticsDeal.objects.create(
            tenant=cls.tenant, partner=cls.partner, ref_number="D-0113",
            order_date="2026-06-01", currency=cls.ils,
            short_name="بطاريات ليثيوم — الدفعة الثانية",
        )

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _rows(self, resp):
        d = resp.json()
        return d.get("results", d) if isinstance(d, dict) else d

    def test_list_exposes_deal_title(self):
        PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number="INV-D1", partner=self.partner,
            currency=self.ils, invoice_date="2026-06-20", deal=self.deal,
        )
        resp = self.client.get("/api/logistics/purchase-invoices/", **self._auth())
        self.assertEqual(resp.status_code, 200, resp.content)
        row = next(r for r in self._rows(resp) if r["invoice_number"] == "INV-D1")
        self.assertEqual(row["deal_title"], "بطاريات ليثيوم — الدفعة الثانية")
        self.assertEqual(row["deal_ref"], "D-0113")

    def test_invoice_without_deal_has_empty_title(self):
        PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number="INV-D2", partner=self.partner,
            currency=self.ils, invoice_date="2026-06-20",
        )
        resp = self.client.get("/api/logistics/purchase-invoices/", **self._auth())
        row = next(r for r in self._rows(resp) if r["invoice_number"] == "INV-D2")
        self.assertEqual(row["deal_title"], "")
