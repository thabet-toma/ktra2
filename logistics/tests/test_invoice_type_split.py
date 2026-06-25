"""فصل الفاتورة الدولية (الاستيراد) عن المحلية + تقسيم المخزن (المرحلة 2).

- invoice_type: محلية افتراضياً؛ الدولية تتطلب صلاحية الاستيراد (نموذج المرحلة 1).
- قائمة الفواتير تُخفي الدولية عمّن لا يملك الصلاحية + فلتر invoice_type.
- حركات المخزون: origin (local/international) مشتق من reference_type + فلتر.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from inventory.models import Product, StockMovement
from logistics.models import PurchaseInvoice
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company
from accounting.services import create_fiscal_year


class InvoiceTypeSplitTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="pimgr", password="x", email="pimgr@x.co")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة الفصل", cls.user)  # user = manager
        create_fiscal_year(cls.tenant, 2026)
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="مورد", partner_type="Supplier")

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _enable_import(self):
        self.tenant.import_enabled = True
        self.tenant.save(update_fields=["import_enabled"])

    def _create_payload(self, **over):
        data = {"partner": self.partner.pk, "currency": "ILS",
                "invoice_date": "2026-06-20", "items": []}
        data.update(over)
        return data

    def _rows(self, resp):
        d = resp.json()
        return d.get("results", d) if isinstance(d, dict) else d

    # ── نوع الفاتورة عند الإنشاء ──
    def test_local_is_default(self):
        resp = self.client.post("/api/logistics/purchase-invoices/",
                                self._create_payload(), format="json", **self._auth())
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.json()["invoice_type"], "local")

    def test_international_blocked_when_company_disabled(self):
        resp = self.client.post("/api/logistics/purchase-invoices/",
                                self._create_payload(invoice_type="international"),
                                format="json", **self._auth())
        self.assertEqual(resp.status_code, 403, resp.content)

    def test_international_allowed_when_enabled(self):
        self._enable_import()
        resp = self.client.post("/api/logistics/purchase-invoices/",
                                self._create_payload(invoice_type="international"),
                                format="json", **self._auth())
        self.assertEqual(resp.status_code, 201, resp.content)
        self.assertEqual(resp.json()["invoice_type"], "international")

    # ── قائمة الفواتير: الإخفاء والفلتر ──
    def _seed_two(self):
        loc = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number="INV-L1", partner=self.partner,
            currency=self.ils, invoice_date="2026-06-20", invoice_type="local")
        intl = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number="INV-I1", partner=self.partner,
            currency=self.ils, invoice_date="2026-06-20", invoice_type="international")
        return loc, intl

    def test_list_hides_international_for_non_import_user(self):
        self._seed_two()  # tenant disabled → manager has no import access
        rows = self._rows(self.client.get("/api/logistics/purchase-invoices/", **self._auth()))
        types = {r["invoice_type"] for r in rows}
        self.assertEqual(types, {"local"})

    def test_list_shows_both_for_import_user(self):
        self._enable_import()
        self._seed_two()
        rows = self._rows(self.client.get("/api/logistics/purchase-invoices/", **self._auth()))
        types = {r["invoice_type"] for r in rows}
        self.assertEqual(types, {"local", "international"})

    def test_invoice_type_filter(self):
        self._enable_import()
        self._seed_two()
        rows = self._rows(self.client.get(
            "/api/logistics/purchase-invoices/?invoice_type=international", **self._auth()))
        self.assertTrue(rows and all(r["invoice_type"] == "international" for r in rows))


class StockOriginSplitTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="stk", password="x")
        Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة المخزن", cls.user)
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="S-1", name_ar="صنف",
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _mv(self, ref_type):
        return StockMovement.objects.create(
            tenant=self.tenant, product=self.product, movement_type="IN",
            quantity=Decimal("1"), reference_type=ref_type, movement_date="2026-06-20")

    def _rows(self, resp):
        d = resp.json()
        return d.get("results", d) if isinstance(d, dict) else d

    def test_origin_property(self):
        self.assertEqual(self._mv("SHIPMENT").origin, "international")
        self.assertEqual(self._mv("PURCHASE_INVOICE").origin, "local")
        self.assertEqual(self._mv("MANUAL").origin, "other")

    def test_origin_filter_international(self):
        self._mv("SHIPMENT"); self._mv("PURCHASE_INVOICE"); self._mv("MANUAL")
        rows = self._rows(self.client.get(
            "/api/inventory/stock-movements/?origin=international", **self._auth()))
        self.assertTrue(rows and all(r["origin"] == "international" for r in rows))

    def test_origin_filter_local(self):
        self._mv("SHIPMENT"); self._mv("PURCHASE_INVOICE")
        rows = self._rows(self.client.get(
            "/api/inventory/stock-movements/?origin=local", **self._auth()))
        self.assertTrue(rows and all(r["origin"] == "local" for r in rows))
