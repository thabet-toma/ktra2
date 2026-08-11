"""تفصيل حركة التعديل في سجل النشاط — «ماذا فعل» لا «عدّل المستند».

تعديل فاتورة مبيعات يجب أن يسجّل: أي بند أُضيف، أيّها حُذف، وأي سعر/كمية تغيّر
ومن أي قيمة إلى أي قيمة — نصّاً مقروءاً في `description` وقائمة مبنيّة في
`metadata['changes']` تعرضها الواجهة.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from core.models import ActivityLog
from inventory.models import Product
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine
from tenants.models import Currency
from tenants.services import create_company


class SalesInvoiceActivityDetailTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="act-detail", password="x")
        cls.currency = Currency.objects.create(
            Code="ILS", Name="شيكل", Symbol="₪", IsBaseCurrency=True)
        cls.tenant = create_company("شركة التفصيل", cls.owner)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="عميل التفصيل", partner_type="Customer")
        cls.tire = Product.objects.create(
            tenant=cls.tenant, sku="TIRE-1", name_ar="إطار 205", quantity_on_hand=100)
        cls.oil = Product.objects.create(
            tenant=cls.tenant, sku="OIL-1", name_ar="زيت محرك", quantity_on_hand=100)
        cls.filter_ = Product.objects.create(
            tenant=cls.tenant, sku="FLT-1", name_ar="فلتر هواء", quantity_on_hand=100)

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.invoice = SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number="SI-DET-1", customer=self.customer,
            currency=self.currency, invoice_date="2026-08-01",
            invoice_type=SalesInvoice.INVOICE_CREDIT, stock_on_post=False,
        )
        self.tire_line = SalesInvoiceLine.objects.create(
            tenant=self.tenant, invoice=self.invoice, product=self.tire,
            quantity=Decimal("2"), unit_price=Decimal("100"))
        self.oil_line = SalesInvoiceLine.objects.create(
            tenant=self.tenant, invoice=self.invoice, product=self.oil,
            quantity=Decimal("1"), unit_price=Decimal("50"))

    def _patch(self, payload):
        return self.client.patch(
            f"/api/sales/invoices/{self.invoice.id}/", payload, format="json",
            HTTP_X_TENANT_ID=str(self.tenant.TenantID),
        )

    def _activity(self):
        return ActivityLog.objects.filter(
            tenant=self.tenant, entity_type="sales_invoice",
            entity_id=self.invoice.id, action="update",
        ).latest("id")

    def test_price_change_records_old_and_new_value(self):
        res = self._patch({"lines": [
            {"id": self.tire_line.id, "product": self.tire.id,
             "quantity": "2", "unit_price": "120"},
            {"id": self.oil_line.id, "product": self.oil.id,
             "quantity": "1", "unit_price": "50"},
        ]})
        assert res.status_code == 200, res.content[:400]
        activity = self._activity()
        assert "«إطار 205»: السعر من 100 إلى 120" in activity.description
        assert activity.metadata["changes"] == [{
            "kind": "line_changed",
            "label": "إطار 205",
            "changes": [{"field": "unit_price", "label": "السعر",
                         "old": "100", "new": "120"}],
        }]

    def test_added_and_removed_items_are_named_in_the_log(self):
        """استبدال صنف بآخر = «حذف زيت» + «أضاف فلتر» باسميهما وكمية/سعر المضاف."""
        res = self._patch({"lines": [
            {"id": self.tire_line.id, "product": self.tire.id,
             "quantity": "2", "unit_price": "100"},
            {"product": self.filter_.id, "quantity": "3", "unit_price": "70"},
        ]})
        assert res.status_code == 200, res.content[:400]
        activity = self._activity()
        assert "حذف صنف «زيت محرك»" in activity.description
        assert "أضاف صنف «فلتر هواء» (الكمية 3 · السعر 70)" in activity.description
        assert [c["kind"] for c in activity.metadata["changes"]] == [
            "line_removed", "line_added"]

    def test_same_item_replaced_reads_as_a_change_not_add_and_remove(self):
        """نفس الصنف بكمية/سعر جديدين = تغيير على البند، لا حذف وإضافة."""
        res = self._patch({"lines": [
            {"id": self.tire_line.id, "product": self.tire.id,
             "quantity": "2", "unit_price": "100"},
            {"product": self.oil.id, "quantity": "3", "unit_price": "70"},
        ]})
        assert res.status_code == 200, res.content[:400]
        activity = self._activity()
        assert "«زيت محرك»: الكمية من 1 إلى 3، السعر من 50 إلى 70" in activity.description
        assert [c["kind"] for c in activity.metadata["changes"]] == ["line_changed"]

    def test_header_change_records_readable_field_names(self):
        res = self._patch({"invoice_discount": "10"})
        assert res.status_code == 200, res.content[:400]
        activity = self._activity()
        assert "خصم الفاتورة من «0» إلى «10»" in activity.description
        assert activity.metadata["changes"][0]["field"] == "invoice_discount"

    def test_untouched_invoice_keeps_the_plain_description(self):
        res = self._patch({"notes": self.invoice.notes or ""})
        assert res.status_code == 200, res.content[:400]
        activity = self._activity()
        assert activity.description == "تعديل فاتورة مبيعات"
        assert activity.metadata == {}
