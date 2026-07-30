"""إعداد «الاستلام مع الترحيل» (PurchaseSettings.receive_on_post).

مُعطَّلاً: الترحيل محاسبي فقط (البضاعة معلّقة في وسيط الاستلام GR/IR)، ثم
تُستلَم البنود بكمياتها من نافذة الاستلام فيُصفَّر الوسيط ولا تُدائَن ذمم
المورد ثانيةً. مفعّلاً (الافتراضي): السلوك السابق كما هو.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.db.models import Sum
from rest_framework.test import APITestCase

from accounting.models import Account, JournalHeader, JournalLine
from accounting.services import create_fiscal_year
from inventory.models import Product, StockMovement, Warehouse
from logistics.models import PurchaseInvoice, PurchaseInvoiceItem
from logistics.services import get_or_create_purchase_settings
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company


class ReceiveOnPostSettingTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="rcvpost", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة الاستلام المؤجَّل", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.warehouse = Warehouse.objects.get(tenant=cls.tenant, is_default=True)
        cls.ap = Account.objects.get(tenant=cls.tenant, code="2101")
        cls.inv_acc = Account.objects.get(tenant=cls.tenant, code="1104")
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="مورد محلي", partner_type="Supplier",
            linked_account=cls.ap)
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="RCV-1", name_ar="صنف",
            quantity_on_hand=Decimal("0"), avg_cost=Decimal("0"))

    def setUp(self):
        self.product.refresh_from_db()

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _set_receive_on_post(self, value):
        ps = get_or_create_purchase_settings(self.tenant)
        ps.receive_on_post = value
        ps.save(update_fields=["receive_on_post"])

    def _make_local_invoice(self, qty="10", price="500"):
        grand = Decimal(qty) * Decimal(price)
        inv = PurchaseInvoice.objects.create(
            tenant=self.tenant,
            invoice_number=f"INV-{PurchaseInvoice.objects.count() + 1:04d}",
            partner=self.partner, currency=self.ils, invoice_date="2026-06-11",
            exchange_rate=Decimal("1"), grand_total=grand)
        item = PurchaseInvoiceItem.objects.create(
            invoice=inv, product=self.product, name="صنف",
            quantity=Decimal(qty), unit_price=Decimal(price), total_price=grand)
        return inv, item

    def _grir_account(self):
        return Account.objects.get(tenant=self.tenant, code="2106")

    def _grir_net(self, invoice):
        agg = JournalLine.objects.filter(
            tenant=self.tenant, account=self._grir_account(),
            journal__reference_id=invoice.pk,
        ).aggregate(d=Sum("debit"), c=Sum("credit"))
        return (agg["d"] or Decimal("0")) - (agg["c"] or Decimal("0"))

    def _ap_credit(self, invoice):
        agg = JournalLine.objects.filter(
            tenant=self.tenant, account=self.ap, journal__reference_id=invoice.pk,
        ).aggregate(c=Sum("credit"))
        return agg["c"] or Decimal("0")

    def test_default_setting_still_receives_on_post(self):
        """الافتراضي مفعّل ⇒ لا تغيير على السلوك القائم."""
        inv, _item = self._make_local_invoice()
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/", {},
            format="json", **self._auth())
        assert res.status_code == 201, res.content
        inv.refresh_from_db()
        assert inv.receipt_status == PurchaseInvoice.RECEIPT_FULL
        self.product.refresh_from_db()
        assert self.product.quantity_on_hand == Decimal("10.0000")
        assert self._grir_net(inv) == Decimal("0.00")

    def test_disabled_setting_posts_without_touching_stock(self):
        self._set_receive_on_post(False)
        inv, _item = self._make_local_invoice()
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/", {},
            format="json", **self._auth())
        assert res.status_code == 201, res.content

        inv.refresh_from_db()
        assert inv.is_posted
        assert inv.receipt_status == PurchaseInvoice.RECEIPT_NOT
        self.product.refresh_from_db()
        assert self.product.quantity_on_hand == Decimal("0.0000")
        assert not StockMovement.objects.filter(
            reference_type="PURCHASE_INVOICE", reference_id=inv.pk).exists()
        assert not JournalHeader.objects.filter(
            tenant=self.tenant, reference_type="PURCHASE_GRN", reference_id=inv.pk).exists()
        # البضاعة معلّقة في الوسيط بانتظار الاستلام
        assert self._grir_net(inv) == Decimal("5000.00")

    def test_deferred_receive_clears_clearing_without_double_ap(self):
        """استلام فاتورة مرحّلة يدين المخزون ويدائن الوسيط — لا ذمم مورد ثانية."""
        self._set_receive_on_post(False)
        inv, item = self._make_local_invoice()
        self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/", {},
            format="json", **self._auth())
        ap_after_post = self._ap_credit(inv)
        assert ap_after_post == Decimal("5000.00")

        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/receive/",
            {"lines": [{"item_id": item.pk, "quantity": 10,
                        "warehouse_id": self.warehouse.pk}]},
            format="json", **self._auth())
        assert res.status_code == 200, res.content
        assert res.json()["receipt_status"] == "received"

        self.product.refresh_from_db()
        assert self.product.quantity_on_hand == Decimal("10.0000")
        assert self.product.avg_cost == Decimal("500.0000")
        # الوسيط صُفِّر، وذمم المورد لم تُدائَن مرة ثانية
        assert self._grir_net(inv) == Decimal("0.00")
        assert self._ap_credit(inv) == ap_after_post
        grn = JournalHeader.objects.get(
            tenant=self.tenant, reference_type="PURCHASE_GRN", reference_id=inv.pk)
        assert grn.lines.filter(account=self.inv_acc, debit=Decimal("5000.00")).exists()
        assert grn.lines.filter(
            account=self._grir_account(), credit=Decimal("5000.00")).exists()

    def test_deferred_partial_receive_then_completion_zeroes_clearing(self):
        self._set_receive_on_post(False)
        inv, item = self._make_local_invoice(qty="3", price="100")  # 300
        self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/", {},
            format="json", **self._auth())

        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/receive/",
            {"lines": [{"item_id": item.pk, "quantity": 1,
                        "warehouse_id": self.warehouse.pk}]},
            format="json", **self._auth())
        assert res.status_code == 200, res.content
        assert res.json()["receipt_status"] == "partially_received"
        assert self._grir_net(inv) == Decimal("200.00")

        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/receive/",
            {"lines": [{"item_id": item.pk, "quantity": 2,
                        "warehouse_id": self.warehouse.pk}]},
            format="json", **self._auth())
        assert res.status_code == 200, res.content
        assert res.json()["receipt_status"] == "received"
        assert self._grir_net(inv) == Decimal("0.00")
        self.product.refresh_from_db()
        assert self.product.quantity_on_hand == Decimal("3.0000")

    def test_receive_on_post_creates_auto_receipt_document(self):
        """الاستلام مع الترحيل يوثَّق بإرسالية تلقائية بكامل الكمية."""
        inv, item = self._make_local_invoice(qty="10", price="500")
        self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/", {},
            format="json", **self._auth())

        res = self.client.get(
            f"/api/logistics/goods-receipts/?invoice={inv.pk}", **self._auth())
        assert res.status_code == 200, res.content
        data = res.json()
        rows = data["results"] if isinstance(data, dict) else data
        assert len(rows) == 1
        assert rows[0]["auto_created"] is True
        assert rows[0]["invoice_number"] == inv.invoice_number
        assert rows[0]["receipt_number"].startswith("GRN-")
        assert Decimal(rows[0]["total_quantity"]) == Decimal("10")

    def test_receipt_document_created_per_partial_receive(self):
        """كل استلام جزئي = إرسالية مستقلة ببنودها وكمياتها."""
        self._set_receive_on_post(False)
        inv, item = self._make_local_invoice(qty="10", price="100")
        self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/", {},
            format="json", **self._auth())

        for qty in (4, 6):
            res = self.client.post(
                f"/api/logistics/purchase-invoices/{inv.pk}/receive/",
                {"lines": [{"item_id": item.pk, "quantity": qty,
                            "warehouse_id": self.warehouse.pk}]},
                format="json", **self._auth())
            assert res.status_code == 200, res.content

        res = self.client.get(
            f"/api/logistics/goods-receipts/?invoice={inv.pk}", **self._auth())
        rows = res.json()
        rows = rows["results"] if isinstance(rows, dict) else rows
        assert len(rows) == 2
        assert {Decimal(r["total_quantity"]) for r in rows} == {Decimal("4"), Decimal("6")}
        assert all(r["auto_created"] is False for r in rows)
        # أرقام الإرساليات فريدة ومتسلسلة
        assert len({r["receipt_number"] for r in rows}) == 2

    def test_create_receipt_from_receipts_screen_receives_stock(self):
        """إنشاء إرسالية من شاشة الإرساليات = استلام فعلي (مخزون + قيد)."""
        self._set_receive_on_post(False)
        inv, item = self._make_local_invoice(qty="5", price="200")
        self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/", {},
            format="json", **self._auth())

        res = self.client.post(
            "/api/logistics/goods-receipts/",
            {"invoice": inv.pk, "receipt_date": "2026-06-12", "notes": "دفعة أولى",
             "lines": [{"item_id": item.pk, "quantity": 2,
                        "warehouse_id": self.warehouse.pk}]},
            format="json", **self._auth())
        assert res.status_code == 201, res.content
        body = res.json()
        assert body["invoice"] == inv.pk
        assert body["receipt_date"] == "2026-06-12"
        assert len(body["lines"]) == 1
        assert Decimal(body["lines"][0]["quantity"]) == Decimal("2")
        assert Decimal(body["lines"][0]["ordered_quantity"]) == Decimal("5")

        self.product.refresh_from_db()
        assert self.product.quantity_on_hand == Decimal("2.0000")
        inv.refresh_from_db()
        assert inv.receipt_status == PurchaseInvoice.RECEIPT_PARTIAL

    def test_receivable_lines_endpoint_feeds_the_editor(self):
        self._set_receive_on_post(False)
        inv, item = self._make_local_invoice(qty="8", price="50")
        self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/", {},
            format="json", **self._auth())
        self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/receive/",
            {"lines": [{"item_id": item.pk, "quantity": 3,
                        "warehouse_id": self.warehouse.pk}]},
            format="json", **self._auth())

        res = self.client.get(
            f"/api/logistics/purchase-invoices/{inv.pk}/receivable-lines/", **self._auth())
        assert res.status_code == 200, res.content
        data = res.json()
        assert data["invoice_number"] == inv.invoice_number
        assert len(data["lines"]) == 1
        row = data["lines"][0]
        assert Decimal(row["quantity"]) == Decimal("8")
        assert Decimal(row["received_quantity"]) == Decimal("3")
        assert Decimal(row["remaining_quantity"]) == Decimal("5")

    def test_unpost_removes_receipt_documents(self):
        inv, item = self._make_local_invoice(qty="2", price="100")
        self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/", {},
            format="json", **self._auth())
        assert inv.receipts.count() == 1

        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/unpost/", {},
            format="json", **self._auth())
        assert res.status_code == 200, res.content
        assert inv.receipts.count() == 0

    # ── سند الاستلام المستقل (بلا فاتورة مرتبطة) ──
    def test_standalone_receipt_receives_stock_against_clearing(self):
        res = self.client.post(
            "/api/logistics/goods-receipts/",
            {"partner": self.partner.pk, "receipt_date": "2026-06-20",
             "supplier_ref": "بوليصة 77", "notes": "وصلت قبل الفاتورة",
             "lines": [{"product_id": self.product.pk, "quantity": 6,
                        "unit_price": 100, "warehouse_id": self.warehouse.pk}]},
            format="json", **self._auth())
        assert res.status_code == 201, res.content
        body = res.json()
        assert body["is_standalone"] is True
        assert body["invoice"] is None
        assert body["supplier_ref"] == "بوليصة 77"
        assert body["doc_label"] == "سند استلام"

        self.product.refresh_from_db()
        assert self.product.quantity_on_hand == Decimal("6.0000")
        # مدين المخزون / دائن وسيط «بضاعة مستلَمة لم تُفوتَر»
        jh = JournalHeader.objects.get(
            tenant=self.tenant, reference_type="GOODS_RECEIPT", reference_id=body["id"])
        assert jh.lines.filter(account=self.inv_acc, debit=Decimal("600.00")).exists()
        assert jh.lines.filter(
            account=self._grir_account(), credit=Decimal("600.00")).exists()

    def test_standalone_receipt_blocked_when_setting_disabled(self):
        ps = get_or_create_purchase_settings(self.tenant)
        ps.allow_standalone_receipt = False
        ps.save(update_fields=["allow_standalone_receipt"])
        res = self.client.post(
            "/api/logistics/goods-receipts/",
            {"partner": self.partner.pk,
             "lines": [{"product_id": self.product.pk, "quantity": 1,
                        "unit_price": 10, "warehouse_id": self.warehouse.pk}]},
            format="json", **self._auth())
        assert res.status_code == 400, res.content
        self.product.refresh_from_db()
        assert self.product.quantity_on_hand == Decimal("0.0000")

    def test_standalone_receipt_requires_partner(self):
        res = self.client.post(
            "/api/logistics/goods-receipts/",
            {"lines": [{"product_id": self.product.pk, "quantity": 1,
                        "unit_price": 10, "warehouse_id": self.warehouse.pk}]},
            format="json", **self._auth())
        assert res.status_code == 400, res.content

    # ── تعديل/إلغاء الإرسالية ──
    def test_edit_receipt_reverses_old_effect_and_applies_new(self):
        self._set_receive_on_post(False)
        inv, item = self._make_local_invoice(qty="10", price="100")
        self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/", {},
            format="json", **self._auth())
        created = self.client.post(
            "/api/logistics/goods-receipts/",
            {"invoice": inv.pk,
             "lines": [{"item_id": item.pk, "quantity": 4,
                        "warehouse_id": self.warehouse.pk}]},
            format="json", **self._auth())
        assert created.status_code == 201, created.content
        receipt_id = created.json()["id"]
        self.product.refresh_from_db()
        assert self.product.quantity_on_hand == Decimal("4.0000")

        res = self.client.put(
            f"/api/logistics/goods-receipts/{receipt_id}/",
            {"invoice": inv.pk, "notes": "تصحيح الكمية",
             "lines": [{"item_id": item.pk, "quantity": 7,
                        "warehouse_id": self.warehouse.pk}]},
            format="json", **self._auth())
        assert res.status_code == 200, res.content

        # لا ازدواج: 7 لا 11
        self.product.refresh_from_db()
        assert self.product.quantity_on_hand == Decimal("7.0000")
        item.refresh_from_db()
        assert item.received_quantity == Decimal("7.0000")
        # الوسيط يعكس المستلَم فقط (10×100 مفوترة − 700 مستلمة)
        assert self._grir_net(inv) == Decimal("300.00")
        assert inv.receipts.count() == 1

    def test_delete_receipt_reverses_its_effect_only(self):
        self._set_receive_on_post(False)
        inv, item = self._make_local_invoice(qty="10", price="100")
        self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/", {},
            format="json", **self._auth())
        first = self.client.post(
            "/api/logistics/goods-receipts/",
            {"invoice": inv.pk, "lines": [{"item_id": item.pk, "quantity": 3,
                                           "warehouse_id": self.warehouse.pk}]},
            format="json", **self._auth()).json()
        self.client.post(
            "/api/logistics/goods-receipts/",
            {"invoice": inv.pk, "lines": [{"item_id": item.pk, "quantity": 2,
                                           "warehouse_id": self.warehouse.pk}]},
            format="json", **self._auth())
        self.product.refresh_from_db()
        assert self.product.quantity_on_hand == Decimal("5.0000")

        res = self.client.delete(
            f"/api/logistics/goods-receipts/{first['id']}/", **self._auth())
        assert res.status_code == 200, res.content

        # أُلغيت الأولى وحدها: يبقى أثر الثانية (2)
        self.product.refresh_from_db()
        assert self.product.quantity_on_hand == Decimal("2.0000")
        item.refresh_from_db()
        assert item.received_quantity == Decimal("2.0000")
        inv.refresh_from_db()
        assert inv.receipt_status == PurchaseInvoice.RECEIPT_PARTIAL
        assert inv.receipts.count() == 1

    def test_edit_blocked_when_setting_disabled(self):
        inv, _item = self._make_local_invoice(qty="2", price="50")
        self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/", {},
            format="json", **self._auth())
        receipt = inv.receipts.first()
        ps = get_or_create_purchase_settings(self.tenant)
        ps.allow_edit_receipt = False
        ps.save(update_fields=["allow_edit_receipt"])

        res = self.client.delete(
            f"/api/logistics/goods-receipts/{receipt.pk}/", **self._auth())
        assert res.status_code == 400, res.content
        assert inv.receipts.count() == 1

    def test_receipt_lines_expose_remaining(self):
        self._set_receive_on_post(False)
        inv, item = self._make_local_invoice(qty="10", price="100")
        self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/", {},
            format="json", **self._auth())
        created = self.client.post(
            "/api/logistics/goods-receipts/",
            {"invoice": inv.pk, "lines": [{"item_id": item.pk, "quantity": 4,
                                           "warehouse_id": self.warehouse.pk}]},
            format="json", **self._auth()).json()

        assert Decimal(created["total_remaining"]) == Decimal("6")
        line = created["lines"][0]
        assert Decimal(line["ordered_quantity"]) == Decimal("10")
        assert Decimal(line["quantity"]) == Decimal("4")
        assert Decimal(line["received_total"]) == Decimal("4")
        assert Decimal(line["remaining_quantity"]) == Decimal("6")

    def test_document_label_follows_settings(self):
        ps = get_or_create_purchase_settings(self.tenant)
        ps.receipt_doc_label = "إشعار استلام"
        ps.save(update_fields=["receipt_doc_label"])
        inv, _item = self._make_local_invoice(qty="1", price="10")
        self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/", {},
            format="json", **self._auth())
        res = self.client.get(
            f"/api/logistics/goods-receipts/?invoice={inv.pk}", **self._auth())
        rows = res.json()
        rows = rows["results"] if isinstance(rows, dict) else rows
        assert rows[0]["doc_label"] == "إشعار استلام"

    def test_unpost_after_deferred_receive_clears_everything(self):
        self._set_receive_on_post(False)
        inv, item = self._make_local_invoice(qty="4", price="250")
        self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/", {},
            format="json", **self._auth())
        self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/receive/",
            {"lines": [{"item_id": item.pk, "quantity": 4,
                        "warehouse_id": self.warehouse.pk}]},
            format="json", **self._auth())

        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/unpost/", {},
            format="json", **self._auth())
        assert res.status_code == 200, res.content
        inv.refresh_from_db()
        assert not inv.is_posted
        assert inv.receipt_status == PurchaseInvoice.RECEIPT_NOT
        item.refresh_from_db()
        assert item.received_quantity == Decimal("0.0000")
        self.product.refresh_from_db()
        assert self.product.quantity_on_hand == Decimal("0.0000")
        assert self._grir_net(inv) == Decimal("0.00")
        assert not JournalHeader.objects.filter(
            tenant=self.tenant, reference_id=inv.pk,
            reference_type__in=["PURCHASE_INVOICE", "PURCHASE_GRN"]).exists()
