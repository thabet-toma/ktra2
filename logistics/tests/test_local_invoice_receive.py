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
            tenant=cls.tenant, sku="LOC-1", name_ar="منتج محلي",
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
            invoice=inv, product=self.product, name="منتج محلي",
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

    def test_credit_receive_credits_supplier_ap(self):
        # Section B: استلام فاتورة آجلة يدائن ذمم المورد (2101) لا الصندوق
        inv, item = self._make_invoice(qty="2", price="100")  # gross 200
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/receive/",
            {"lines": [{"item_id": item.pk, "quantity": 2, "warehouse_id": self.warehouse.pk}]},
            format="json", **self._auth())
        assert res.status_code == 200, res.content
        inv.refresh_from_db()
        from logistics.services import _resolve_ap_account
        ap = _resolve_ap_account(inv.partner)
        assert inv.journal.lines.filter(account=ap, credit=Decimal("200.00")).exists(), \
            "استلام الفاتورة الآجلة يجب أن يدائن ذمم المورد"

    def test_cash_receive_routes_through_supplier_ap(self):
        # Feature 2: استلام فاتورة نقدية يدائن ذمم المورد بالكامل ولا يُسوّي الصندوق
        # (الدفع للمورد يصبح وصل دفع مستقل بعد الاستلام).
        cash = Account.objects.create(
            tenant=self.tenant, code="1101-R", name="الصندوق الرئيسي",
            account_type="Asset", is_active=True)
        inv, item = self._make_invoice(qty="1", price="55")  # gross 55
        inv.payment_type = PurchaseInvoice.PAYMENT_TYPE_CASH
        inv.cash_or_bank_account = cash
        inv.save(update_fields=["payment_type", "cash_or_bank_account"])

        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/receive/",
            {"lines": [{"item_id": item.pk, "quantity": 1, "warehouse_id": self.warehouse.pk}]},
            format="json", **self._auth())
        assert res.status_code == 200, res.content
        inv.refresh_from_db()
        jl = list(inv.journal.lines.all())
        assert sum(l.debit for l in jl) == sum(l.credit for l in jl)  # متوازن
        from logistics.services import _resolve_ap_account
        ap = _resolve_ap_account(inv.partner)
        ap_lines = [l for l in jl if l.account_id == ap.id]
        # ذمم المورد تُدائن بكامل القيمة ولا تُسوّى داخل قيد الاستلام
        assert sum(l.credit for l in ap_lines) == Decimal("55.00")
        assert sum(l.debit for l in ap_lines) == Decimal("0")
        # لا سطر صندوق في قيد الاستلام
        assert sum(l.credit for l in jl if l.account_id == cash.id) == Decimal("0")

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

    # ── تعديل بنود فاتورة استُلمت بضاعتها ──────────────────────────────────
    # الاستلام الصفري (كميات بلا أسعار) لا يُنشئ قيداً فتبقى الفاتورة مسودةً
    # قابلةً للتعديل وهي ممتلئة بضاعةً — النافذة الوحيدة التي لا يغطّيها حارس
    # «المستند المرحّل لا يُعدَّل».

    def _received_invoice(self, qty="10", price="0"):
        inv, item = self._make_invoice(qty=qty, price=price)
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/receive/",
            {"lines": [{"item_id": item.pk, "quantity": qty, "warehouse_id": self.warehouse.pk}]},
            format="json", **self._auth())
        assert res.status_code == 200, res.content
        inv.refresh_from_db()
        item.refresh_from_db()
        assert not inv.is_posted, "الاستلام الصفري لا يُرحّل — هذه هي النافذة"
        assert item.received_quantity == Decimal(qty)
        return inv, item

    def _patch_items(self, inv, items):
        return self.client.patch(
            f"/api/logistics/purchase-invoices/{inv.pk}/",
            {"items": items}, format="json", **self._auth())

    def _line(self, item, **over):
        row = {"id": item.pk, "product": item.product_id, "name": item.name,
               "quantity": str(item.quantity), "unit_price": str(item.unit_price),
               "total_price": str(item.total_price)}
        row.update(over)
        return row

    def test_edit_by_id_preserves_received_quantity_and_receipt_line(self):
        """التعديل بالمعرّف يُبقي الكمية المستلَمة وسطر الإرسالية على البند نفسه."""
        from logistics.models import GoodsReceiptLine

        inv, item = self._received_invoice()
        gr_line = GoodsReceiptLine.objects.get(item=item)

        res = self._patch_items(inv, [self._line(item, name="اسم مصحَّح",
                                                 notes="ملاحظة", quantity="12")])
        assert res.status_code == 200, res.content

        item.refresh_from_db()
        assert item.name == "اسم مصحَّح"
        assert item.quantity == Decimal("12.0000")
        assert item.received_quantity == Decimal("10.0000"), "الكمية المستلَمة لا تُمسح"
        assert inv.items.count() == 1
        assert inv.items.first().pk == item.pk, "البند لم يُحذف ويُعاد إنشاؤه"
        gr_line.refresh_from_db()
        assert gr_line.item_id == item.pk, "سطر الإرسالية بقي معلّقاً على بنده"

    def test_removing_received_line_rejected(self):
        """حذف بندٍ استُلمت بضاعته مرفوض — الحركة المخزنية تبقى بلا فاتورة."""
        from logistics.models import GoodsReceiptLine

        inv, item = self._received_invoice()
        gr_line = GoodsReceiptLine.objects.get(item=item)

        res = self._patch_items(inv, [{"product": self.product.pk, "name": "بند بديل",
                                       "quantity": "5", "unit_price": "0", "total_price": "0"}])
        assert res.status_code == 400, res.content
        assert "لا يُحذف" in res.json()["detail"]

        item.refresh_from_db()
        assert item.received_quantity == Decimal("10.0000")
        assert inv.items.count() == 1
        assert GoodsReceiptLine.objects.filter(pk=gr_line.pk).exists()
        inv.refresh_from_db()
        assert inv.receipt_status == PurchaseInvoice.RECEIPT_FULL

    def test_quantity_below_received_rejected(self):
        inv, item = self._received_invoice()
        res = self._patch_items(inv, [self._line(item, quantity="4")])
        assert res.status_code == 400, res.content
        assert "أقل من المستلَم" in res.json()["detail"]
        item.refresh_from_db()
        assert item.quantity == Decimal("10.0000")

    def test_price_and_product_change_on_received_line_rejected(self):
        other = Product.objects.create(
            tenant=self.tenant, sku="LOC-2", name_ar="منتج آخر",
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))
        inv, item = self._received_invoice()

        res = self._patch_items(inv, [self._line(item, unit_price="500", total_price="5000")])
        assert res.status_code == 400, res.content
        assert "سعر" in res.json()["detail"]

        res = self._patch_items(inv, [self._line(item, product=other.pk)])
        assert res.status_code == 400, res.content
        assert "منتج" in res.json()["detail"]

        item.refresh_from_db()
        assert item.unit_price == Decimal("0.0000")
        assert item.product_id == self.product.pk

    def test_add_line_beside_received_line_allowed(self):
        """الاستلام الجزئي حالة مشروعة: بندٌ جديد يُضاف بلا مساس بالمستلَم."""
        inv, item = self._received_invoice()
        res = self._patch_items(inv, [
            self._line(item),
            {"product": self.product.pk, "name": "بند إضافي",
             "quantity": "3", "unit_price": "0", "total_price": "0"},
        ])
        assert res.status_code == 200, res.content
        assert inv.items.count() == 2
        item.refresh_from_db()
        assert item.received_quantity == Decimal("10.0000")

    def test_item_id_from_another_invoice_rejected(self):
        """معرّف غريب يُرفض بدل أن يُنشئ بنداً صامتاً ويحذف بند الفاتورة."""
        inv, item = self._make_invoice(qty="2", price="10")
        other_inv, other_item = self._make_invoice(qty="2", price="10")
        res = self._patch_items(inv, [self._line(other_item)])
        assert res.status_code == 400, res.content
        assert "لا ينتمي لهذه الفاتورة" in res.json()["detail"]
        assert inv.items.count() == 1
        assert inv.items.first().pk == item.pk

    def test_unreceived_line_still_removable(self):
        """دلالة الحذف محفوظة: بندٌ غائبٌ عن الحمولة يُحذف ما لم يُستلَم."""
        inv, item = self._make_invoice(qty="10", price="0")
        extra = PurchaseInvoiceItem.objects.create(
            invoice=inv, product=self.product, name="بند مؤقت",
            quantity=Decimal("1"), unit_price=Decimal("0"), total_price=Decimal("0"))
        res = self._patch_items(inv, [self._line(item)])
        assert res.status_code == 200, res.content
        assert inv.items.count() == 1
        assert not PurchaseInvoiceItem.objects.filter(pk=extra.pk).exists()

    def test_duplicate_item_id_rejected(self):
        """المعرّف مرّتين = سطرٌ يبتلع الآخر بصمت — يُرفض بدل أن يُفقَد بند."""
        inv, item = self._make_invoice(qty="4", price="10")
        res = self._patch_items(inv, [self._line(item), self._line(item, quantity="9")])
        assert res.status_code == 400, res.content
        assert "مكرَّر" in res.json()["detail"]
        item.refresh_from_db()
        assert item.quantity == Decimal("4.0000")
