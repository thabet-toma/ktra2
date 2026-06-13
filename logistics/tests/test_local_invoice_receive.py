"""فاتورة شراء محلية: استلام البضاعة للمخزن ينعكس على المستودع + قيد + حالة.

يغطي المطلب: «فاتورة محلية لها حالة مستلمة/غير مستلمة، وخيار استلام يحدد
الكمية والمستودع وينعكس على المخزن».
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, JournalHeader
from inventory.models import Product, StockMovement, Warehouse
from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company
from accounting.services import create_fiscal_year


class LocalInvoiceReceiveTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="recv", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة الاستلام", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.warehouse = Warehouse.objects.get(tenant=cls.tenant, is_default=True)
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="مورد محلي", partner_type="Supplier")
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="LOC-1", name_ar="صنف محلي",
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _make_invoice(self, *, shipment=None, qty="10", price="500", vat="0"):
        inv = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number=f"INV-{PurchaseInvoice.objects.count()+1:04d}",
            partner=self.partner, currency=self.ils, invoice_date="2026-06-11",
            exchange_rate=Decimal("1"), shipment=shipment,
            grand_total=Decimal("0"))
        item = PurchaseInvoiceItem.objects.create(
            invoice=inv, product=self.product, name="صنف محلي",
            quantity=Decimal(qty), unit_price=Decimal(price),
            total_price=(Decimal(qty) * Decimal(price)),
            is_taxable=(Decimal(vat) > 0), vat_percent=Decimal(vat))
        return inv, item

    def test_full_receive_reflects_stock_status_and_journal(self):
        inv, item = self._make_invoice(qty="10", price="500")
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/receive/",
            {"lines": [{"item_id": item.pk, "quantity": 10, "warehouse_id": self.warehouse.pk}]},
            format="json", **self._auth())
        assert res.status_code == 200, res.content
        assert res.json()["receipt_status"] == "received"

        self.product.refresh_from_db()
        assert self.product.quantity_on_hand == Decimal("10.0000")
        assert self.product.avg_cost == Decimal("500.0000")

        mv = StockMovement.objects.get(
            reference_type="PURCHASE_INVOICE", reference_id=inv.pk)
        assert mv.movement_type == "IN"
        assert mv.warehouse_id == self.warehouse.pk

        inv.refresh_from_db()
        assert inv.receipt_status == PurchaseInvoice.RECEIPT_FULL
        assert inv.is_posted
        jh = JournalHeader.objects.get(
            tenant=self.tenant, reference_type="PURCHASE_INVOICE", reference_id=inv.pk)
        inv_acc = Account.objects.get(tenant=self.tenant, code="1104")
        assert jh.lines.filter(account=inv_acc, debit=Decimal("5000.00")).exists()

    def test_zero_value_receive_reflects_stock_without_journal(self):
        # فاتورة كمية فقط (بلا أسعار) — الاستلام ينعكس على المخزن بلا قيد محاسبي
        inv = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number="INV-Z1",
            partner=self.partner, currency=self.ils, invoice_date="2026-06-11",
            exchange_rate=Decimal("1"), grand_total=Decimal("0"))
        item = PurchaseInvoiceItem.objects.create(
            invoice=inv, product=self.product, name="بلا سعر",
            quantity=Decimal("7"), unit_price=Decimal("0"), total_price=Decimal("0"))
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/receive/",
            {"lines": [{"item_id": item.pk, "quantity": 7, "warehouse_id": self.warehouse.pk}]},
            format="json", **self._auth())
        assert res.status_code == 200, res.content
        assert res.json()["receipt_status"] == "received"
        assert res.json()["journal_id"] is None
        self.product.refresh_from_db()
        assert self.product.quantity_on_hand == Decimal("7.0000")
        assert not JournalHeader.objects.filter(
            tenant=self.tenant, reference_type="PURCHASE_INVOICE", reference_id=inv.pk
        ).exists()

    def test_unit_cost_falls_back_to_total_price(self):
        # سعر الوحدة صفر لكن إجمالي السطر موجود ⇒ تُشتق التكلفة من الإجمالي
        inv = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number="INV-FB1",
            partner=self.partner, currency=self.ils, invoice_date="2026-06-11",
            exchange_rate=Decimal("1"), grand_total=Decimal("0"))
        item = PurchaseInvoiceItem.objects.create(
            invoice=inv, product=self.product, name="سعر من الإجمالي",
            quantity=Decimal("10"), unit_price=Decimal("0"), total_price=Decimal("300"))
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/receive/",
            {"lines": [{"item_id": item.pk, "quantity": 10, "warehouse_id": self.warehouse.pk}]},
            format="json", **self._auth())
        assert res.status_code == 200, res.content
        self.product.refresh_from_db()
        assert self.product.avg_cost == Decimal("30.0000")
        assert JournalHeader.objects.filter(
            tenant=self.tenant, reference_type="PURCHASE_INVOICE", reference_id=inv.pk
        ).exists()

    def test_partial_receive_marks_partial(self):
        inv, item = self._make_invoice(qty="10", price="100")
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/receive/",
            {"lines": [{"item_id": item.pk, "quantity": 4, "warehouse_id": self.warehouse.pk}]},
            format="json", **self._auth())
        assert res.status_code == 200, res.content
        assert res.json()["receipt_status"] == "partially_received"
        item.refresh_from_db()
        assert item.received_quantity == Decimal("4.0000")
        self.product.refresh_from_db()
        assert self.product.quantity_on_hand == Decimal("4.0000")

    def test_cannot_receive_more_than_remaining(self):
        inv, item = self._make_invoice(qty="5", price="100")
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/receive/",
            {"lines": [{"item_id": item.pk, "quantity": 9, "warehouse_id": self.warehouse.pk}]},
            format="json", **self._auth())
        assert res.status_code == 400, res.content
        self.product.refresh_from_db()
        assert self.product.quantity_on_hand == Decimal("0.0000")

    def test_imported_invoice_rejected(self):
        from logistics.models import LogisticsShipment
        shp = LogisticsShipment.objects.create(
            tenant=self.tenant, shipment_number="SHP-1")
        inv, item = self._make_invoice(shipment=shp, qty="3", price="100")
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/receive/",
            {"lines": [{"item_id": item.pk, "quantity": 3, "warehouse_id": self.warehouse.pk}]},
            format="json", **self._auth())
        assert res.status_code == 400, res.content
        assert "مستوردة" in res.json().get("error", "")

    def test_foreign_warehouse_rejected(self):
        other_user = User.objects.create_user(username="other", password="x")
        other_tenant = create_company("شركة أخرى", other_user)
        foreign_wh = Warehouse.objects.get(tenant=other_tenant, is_default=True)
        inv, item = self._make_invoice(qty="2", price="100")
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/receive/",
            {"lines": [{"item_id": item.pk, "quantity": 2, "warehouse_id": foreign_wh.pk}]},
            format="json", **self._auth())
        assert res.status_code == 400, res.content
        self.product.refresh_from_db()
        assert self.product.quantity_on_hand == Decimal("0.0000")

    def test_warehouse_list_tenant_isolated(self):
        other_user = User.objects.create_user(username="o2", password="x")
        create_company("شركة ثالثة", other_user)
        res = self.client.get("/api/inventory/warehouses/", **self._auth())
        assert res.status_code == 200, res.content
        data = res.json()
        rows = data["results"] if isinstance(data, dict) else data
        assert all(w["tenant"] == self.tenant.TenantID for w in rows)
        assert len(rows) >= 1
