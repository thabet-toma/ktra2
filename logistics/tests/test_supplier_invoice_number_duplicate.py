"""A2-2 — رقم فاتورة المورد المكرَّر: تحذيرٌ قابلٌ للتجاوز لا قيدٌ في القاعدة.

`PurchaseInvoice.supplier_invoice_number` بلا تفرّد ولا فحص، فتُسجَّل فاتورة المورد
نفسها مرتين بصمت (دفعٌ مزدوج). قرار المالك: تحذير يمكن تجاوزه (نمط Odoo 17+ /
QuickBooks / Zoho) — الفحص نقطةٌ للقراءة يستشيرها المحرّر قبل الحفظ.
"""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from logistics.models import PurchaseInvoice
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

URL = "/api/logistics/purchase-invoices/check-supplier-invoice-number/"


class SupplierInvoiceNumberDuplicateTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="sinv-dup", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة رقم المورد", cls.user)
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورد أ", partner_type="Supplier")
        cls.other_supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورد ب", partner_type="Supplier")
        cls.existing = PurchaseInvoice.objects.create(
            tenant=cls.tenant, invoice_number="PI-100", partner=cls.supplier,
            currency=cls.ils, invoice_date="2026-06-10", supplier_invoice_number="INV-778",
        )

    def _check(self, **params):
        self.client.force_authenticate(user=self.user)
        return self.client.get(URL, params, HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def test_same_supplier_same_number_is_reported_with_the_existing_invoice(self):
        res = self._check(partner=self.supplier.pk, supplier_invoice_number=" INV-778 ")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertFalse(res.data["is_unique"])
        self.assertEqual(res.data["existing_invoice_id"], self.existing.pk)
        self.assertEqual(res.data["existing_invoice_number"], "PI-100")

    def test_other_supplier_with_the_same_number_is_not_a_duplicate(self):
        res = self._check(partner=self.other_supplier.pk, supplier_invoice_number="INV-778")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.data["is_unique"])

    def test_the_invoice_itself_is_excluded(self):
        res = self._check(
            partner=self.supplier.pk, supplier_invoice_number="INV-778", exclude=self.existing.pk,
        )
        self.assertTrue(res.data["is_unique"])

    def test_returns_do_not_count_as_duplicates(self):
        PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number="PR-1", partner=self.other_supplier,
            currency=self.ils, invoice_date="2026-06-12", supplier_invoice_number="RET-5",
            is_return=True,
        )
        res = self._check(partner=self.other_supplier.pk, supplier_invoice_number="RET-5")
        self.assertTrue(res.data["is_unique"])

    def test_empty_number_is_always_unique(self):
        res = self._check(partner=self.supplier.pk, supplier_invoice_number="  ")
        self.assertTrue(res.data["is_unique"])

    def test_another_tenants_invoice_is_not_visible(self):
        other_user = User.objects.create_user(username="sinv-dup-other", password="x")
        other = create_company("شركة أخرى برقم مورد", other_user)
        other_supplier = Partner.objects.create(
            tenant=other, name="مورد الغير", partner_type="Supplier")
        PurchaseInvoice.objects.create(
            tenant=other, invoice_number="PI-X", partner=other_supplier, currency=self.ils,
            invoice_date="2026-06-10", supplier_invoice_number="SHARED-1",
        )
        # نفس معرّف المورد الأجنبي من داخل شركتي — لا يُرى.
        res = self._check(partner=other_supplier.pk, supplier_invoice_number="SHARED-1")
        self.assertEqual(res.status_code, 200, res.content)
        self.assertTrue(res.data["is_unique"])
