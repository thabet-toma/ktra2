"""تفصيل حركة تعديل فاتورة الشراء في سجل النشاط (مرآة فاتورة البيع).

نفس عقد `core.activity`: البند المضاف/المحذوف باسمه، وتغيّر السعر/الكمية بقيمتيه
القديمة والجديدة — نصّاً في `description` وقائمةً في `metadata['changes']`.
"""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from core.models import ActivityLog
from inventory.models import Product
from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company


class PurchaseInvoiceActivityDetailTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="pi-act", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة تفصيل الشراء", cls.user)
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="مورد التفصيل", partner_type="Supplier")
        cls.tire = Product.objects.create(
            tenant=cls.tenant, sku="P-TIRE", name_ar="إطار 205")
        cls.oil = Product.objects.create(
            tenant=cls.tenant, sku="P-OIL", name_ar="زيت محرك")

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.invoice = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number="PI-DET-1", partner=self.partner,
            currency=self.ils, invoice_date="2026-08-01",
        )
        self.item = PurchaseInvoiceItem.objects.create(
            invoice=self.invoice, product=self.tire, name="إطار 205",
            quantity=2, unit_price=100, total_price=200,
        )

    def _patch(self, payload):
        return self.client.patch(
            f"/api/logistics/purchase-invoices/{self.invoice.id}/", payload,
            format="json", HTTP_X_TENANT_ID=str(self.tenant.TenantID),
        )

    def _activity(self):
        return ActivityLog.objects.filter(
            tenant=self.tenant, entity_type="purchase_invoice",
            entity_id=self.invoice.id, action="update",
        ).latest("id")

    def test_price_change_records_old_and_new_value(self):
        res = self._patch({"items": [
            {"product": self.tire.id, "name": "إطار 205",
             "quantity": "2", "unit_price": "120", "total_price": "240"},
        ]})
        assert res.status_code == 200, res.content[:400]
        activity = self._activity()
        assert "«إطار 205»: السعر من 100 إلى 120" in activity.description
        assert activity.metadata["changes"][0]["kind"] == "line_changed"

    def test_replacing_an_item_names_both_sides(self):
        res = self._patch({"items": [
            {"product": self.oil.id, "name": "زيت محرك",
             "quantity": "1", "unit_price": "50", "total_price": "50"},
        ]})
        assert res.status_code == 200, res.content[:400]
        description = self._activity().description
        assert "حذف منتج «إطار 205»" in description
        assert "أضاف منتج «زيت محرك»" in description

    def test_untouched_invoice_keeps_the_plain_description(self):
        res = self._patch({"notes": self.invoice.notes or ""})
        assert res.status_code == 200, res.content[:400]
        assert self._activity().description == "تعديل فاتورة شراء"
