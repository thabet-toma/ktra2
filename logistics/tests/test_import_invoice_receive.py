"""الفاتورة الدولية تُستلَم كالفاتورة المحلية تماماً.

كانت بضاعة الاستيراد تدخل المخزن عند تحوّل الشحنة إلى «Cleared» (إشارة
`auto_receive_stock_on_shipment_cleared`) — بلا مستودع، وبسعر الصفقة إن سبقت
الفاتورة، ودون أن تلمس `received_quantity`/`receipt_status`؛ فتظهر الفاتورة
«مرحّلة» وبضاعتها في المخزن وعليها «غير مستلمة» (بلاغ المالك، INV-0003).

الآن: إعداد «الاستلام مع الترحيل» والسؤال عند الترحيل ونافذة الاستلام
والإرسالية — كلّها للدولية أيضاً، بتكلفة الوحدة المستوردة (landed) وعبر وسيط
الاستلام GR/IR كالمحلية.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.db.models import Sum
from rest_framework.test import APITestCase

from accounting.models import Account, JournalHeader, JournalLine
from accounting.services import create_fiscal_year
from inventory.models import Product, StockMovement, Warehouse
from inventory.services import receive_shipment_stock
from logistics.models import (
    GoodsReceipt,
    LogisticsDeal,
    LogisticsDealItem,
    LogisticsShipment,
    LogisticsShipmentDeal,
    PurchaseInvoice,
    PurchaseInvoiceItem,
)
from logistics.services import (
    GR_IR_ACCOUNT_CODE,
    get_or_create_purchase_settings,
    sync_import_receipt_from_shipment_stock,
)
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

D = lambda v: Decimal(str(v))


class ImportInvoiceReceiveTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="imprcv", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة استلام الاستيراد", cls.user)
        cls.tenant.import_enabled = True
        cls.tenant.save(update_fields=["import_enabled"])
        create_fiscal_year(cls.tenant, 2026)
        cls.warehouse = Warehouse.objects.get(tenant=cls.tenant, is_default=True)
        cls.ap = Account.objects.get(tenant=cls.tenant, code="2101")
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="مصنع صيني", partner_type="Supplier",
            linked_account=cls.ap)
        cls.p1 = Product.objects.create(
            tenant=cls.tenant, sku="IR-1", name_ar="إطار",
            quantity_on_hand=D("0"), avg_cost=D("0"))
        cls.p2 = Product.objects.create(
            tenant=cls.tenant, sku="IR-2", name_ar="جنط",
            quantity_on_hand=D("0"), avg_cost=D("0"))

    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _set_receive_on_post(self, value):
        ps = get_or_create_purchase_settings(self.tenant)
        ps.receive_on_post = value
        ps.save(update_fields=["receive_on_post"])

    def _make_import(self, lines=(("p1", "10", "100", "6000"),), shipment_status="Clearing"):
        """صفقة + شحنة + فاتورة دولية. lines: (منتج, كمية, سعر الصفقة, إجمالي landed)."""
        n = LogisticsDeal.objects.count() + 1
        deal = LogisticsDeal.objects.create(
            tenant=self.tenant, ref_number=f"IRD-{n:04d}",
            partner=self.partner, order_date="2026-07-01", total_amount=D("1000"))
        shipment = LogisticsShipment.objects.create(
            tenant=self.tenant, shipment_number=f"IRS-{n:04d}", status=shipment_status)
        LogisticsShipmentDeal.objects.create(shipment=shipment, deal=deal)
        grand = sum((D(l[3]) for l in lines), D("0"))
        inv = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number=f"IRI-{n:04d}",
            invoice_type=PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL,
            partner=self.partner, currency=self.ils, invoice_date="2026-07-02",
            exchange_rate=D("1"), grand_total=grand, deal=deal, shipment=shipment)
        for key, qty, price, landed in lines:
            product = getattr(self, key)
            LogisticsDealItem.objects.create(
                deal=deal, product=product, quantity=D(qty), unit_price=D(price))
            PurchaseInvoiceItem.objects.create(
                invoice=inv, product=product, name=product.name_ar,
                quantity=D(qty), unit_price=D(price), total_price=D(qty) * D(price),
                landed_unit_price_ils=(D(landed) / D(qty)).quantize(D("0.0001")),
                landed_line_total_ils=D(landed))
        return deal, shipment, inv

    def _post(self, inv, **body):
        return self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/", body,
            format="json", **self._auth())

    def _receive(self, inv, lines):
        return self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/receive/", {"lines": lines},
            format="json", **self._auth())

    def _grir_net(self, inv):
        acc = Account.objects.get(tenant=self.tenant, code=GR_IR_ACCOUNT_CODE)
        agg = JournalLine.objects.filter(
            tenant=self.tenant, account=acc, journal__reference_id=inv.pk,
            journal__reference_type__in=("PURCHASE_INVOICE", "PURCHASE_GRN"),
        ).aggregate(d=Sum("debit"), c=Sum("credit"))
        return (agg["d"] or D("0")) - (agg["c"] or D("0"))

    def _ap_credit(self, inv):
        return JournalLine.objects.filter(
            tenant=self.tenant, account=self.ap, journal__reference_id=inv.pk,
        ).aggregate(c=Sum("credit"))["c"] or D("0")

    # ── الاستلام مع الترحيل ────────────────────────────────────────────────
    def test_post_with_receive_on_post_receives_import_at_landed_cost(self):
        _deal, _sh, inv = self._make_import()
        res = self._post(inv)
        assert res.status_code == 201, res.content

        inv.refresh_from_db()
        assert inv.receipt_status == PurchaseInvoice.RECEIPT_FULL
        item = inv.items.get()
        assert item.received_quantity == D("10")
        mv = StockMovement.objects.get(reference_type="PURCHASE_INVOICE", reference_id=inv.pk)
        assert mv.warehouse_id == self.warehouse.id
        # تكلفة الوحدة = landed (600) لا سعر الصفقة (100).
        assert mv.unit_cost.quantize(D("0.01")) == D("600.00")
        assert GoodsReceipt.objects.filter(invoice=inv, auto_created=True).count() == 1
        # الوسيط صُفّي، وذمم المورد دُوئنت مرّةً واحدة.
        assert self._grir_net(inv) == D("0.00")
        assert self._ap_credit(inv) == D("6000.00")

    def test_landed_weights_split_cost_not_deal_price(self):
        """سعرا صفقة متساويان ولاندد مختلف ⇒ التكلفة تتبع landed."""
        _deal, _sh, inv = self._make_import(lines=(
            ("p1", "10", "100", "1000"), ("p2", "10", "100", "5000"),
        ))
        assert self._post(inv).status_code == 201
        costs = {
            mv.product_id: mv.unit_cost.quantize(D("0.01"))
            for mv in StockMovement.objects.filter(
                reference_type="PURCHASE_INVOICE", reference_id=inv.pk)
        }
        assert costs == {self.p1.id: D("100.00"), self.p2.id: D("500.00")}

    # ── الاستلام لاحقاً ────────────────────────────────────────────────────
    def test_post_without_receive_then_receive_later(self):
        self._set_receive_on_post(False)
        _deal, _sh, inv = self._make_import()
        assert self._post(inv).status_code == 201
        inv.refresh_from_db()
        assert inv.is_posted and inv.receipt_status == PurchaseInvoice.RECEIPT_NOT
        assert not StockMovement.objects.filter(
            reference_type="PURCHASE_INVOICE", reference_id=inv.pk).exists()
        assert self._grir_net(inv) == D("6000.00")

        item = inv.items.get()
        res = self._receive(inv, [
            {"item_id": item.id, "quantity": "4", "warehouse_id": self.warehouse.id}])
        assert res.status_code == 200, res.content
        assert res.json()["receipt_status"] == "partially_received"
        res = self._receive(inv, [
            {"item_id": item.id, "quantity": "6", "warehouse_id": self.warehouse.id}])
        assert res.status_code == 200, res.content
        assert res.json()["receipt_status"] == "received"

        self.p1.refresh_from_db()
        assert self.p1.quantity_on_hand == D("10")
        assert self._grir_net(inv) == D("0.00")
        assert self._ap_credit(inv) == D("6000.00")
        assert GoodsReceipt.objects.filter(invoice=inv).count() == 2

    def test_post_override_asks_per_invoice(self):
        """الإعداد مطفأ والسؤال أجاب «نعم» ⇒ تُستلَم هذه الفاتورة وحدها."""
        self._set_receive_on_post(False)
        _deal, _sh, inv = self._make_import()
        assert self._post(inv, receive_on_post=True).status_code == 201
        inv.refresh_from_db()
        assert inv.receipt_status == PurchaseInvoice.RECEIPT_FULL

    def test_unposted_import_cannot_be_received(self):
        _deal, _sh, inv = self._make_import()
        item = inv.items.get()
        res = self._receive(inv, [
            {"item_id": item.id, "quantity": "10", "warehouse_id": self.warehouse.id}])
        assert res.status_code == 400
        assert "رحّل" in str(res.content.decode())
        assert not StockMovement.objects.filter(product=self.p1).exists()

    def test_unpost_reverses_import_receipt(self):
        _deal, _sh, inv = self._make_import()
        assert self._post(inv).status_code == 201
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/unpost/", {},
            format="json", **self._auth())
        assert res.status_code == 200, res.content
        inv.refresh_from_db()
        assert not inv.is_posted
        assert inv.receipt_status == PurchaseInvoice.RECEIPT_NOT
        self.p1.refresh_from_db()
        assert self.p1.quantity_on_hand == D("0")

    # ── الشحنة لم تعد تُدخل البضاعة ────────────────────────────────────────
    def test_shipment_cleared_no_longer_enters_stock(self):
        _deal, shipment, _inv = self._make_import()
        shipment.status = "Cleared"
        shipment.save()
        assert not StockMovement.objects.filter(
            reference_type="SHIPMENT", reference_id=shipment.pk).exists()

    # ── البيانات القديمة: بضاعة دخلت من الشحنة ─────────────────────────────
    def test_legacy_shipment_stock_marks_invoice_received_and_posts_direct(self):
        """INV-0003: حركات SHIPMENT موجودة ⇒ الفاتورة «مستلمة»، والترحيل لا
        يمرّ بالوسيط ولا يُدخل البضاعة مرّةً ثانية."""
        _deal, shipment, inv = self._make_import()
        receive_shipment_stock(shipment)
        sync_import_receipt_from_shipment_stock(inv)
        inv.refresh_from_db()
        assert inv.receipt_status == PurchaseInvoice.RECEIPT_FULL
        assert inv.items.get().received_quantity == D("10")

        assert self._post(inv).status_code == 201
        self.p1.refresh_from_db()
        assert self.p1.quantity_on_hand == D("10")
        assert not StockMovement.objects.filter(
            reference_type="PURCHASE_INVOICE", reference_id=inv.pk).exists()
        assert not JournalHeader.objects.filter(
            tenant=self.tenant, reference_type="PURCHASE_GRN", reference_id=inv.pk).exists()
        assert self._ap_credit(inv) == D("6000.00")

        # إلغاء الترحيل لا يُنسيها أنّ بضاعتها في المخزن.
        res = self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/unpost/", {},
            format="json", **self._auth())
        assert res.status_code == 200, res.content
        inv.refresh_from_db()
        assert inv.receipt_status == PurchaseInvoice.RECEIPT_FULL

    def test_legacy_sync_matches_deal_by_exact_ref(self):
        """حركات صفقةٍ أخرى على الشحنة نفسها لا تُحسب لهذه الفاتورة."""
        deal, shipment, inv = self._make_import()
        other = LogisticsDeal.objects.create(
            tenant=self.tenant, ref_number=f"{deal.ref_number}9",
            partner=self.partner, order_date="2026-07-01", total_amount=D("1"))
        LogisticsDealItem.objects.create(
            deal=other, product=self.p1, quantity=D("3"), unit_price=D("1"))
        LogisticsShipmentDeal.objects.create(shipment=shipment, deal=other)
        # صفقةٌ ثانية وحدها دخلت (بيانات قديمة جزئية).
        LogisticsDealItem.objects.filter(deal=deal).update(is_deleted=True)
        receive_shipment_stock(shipment)
        sync_import_receipt_from_shipment_stock(inv)
        inv.refresh_from_db()
        assert inv.receipt_status == PurchaseInvoice.RECEIPT_NOT
        assert inv.items.get().received_quantity == D("0")

    def test_legacy_notes_without_trailing_separator_match_exact_deal(self):
        """`backfill_stock` كتب «شحنة S | صفقة REF» بلا « | تكلفة: ...» — تُحسب
        لصفقتها، ولا يطابق REF صفقةَ REF0 ولا العكس (الإنتاج: INV-0010..0013)."""
        from inventory.services import record_stock_movement

        deal, shipment, inv = self._make_import()
        long_ref = f"{deal.ref_number}0"
        other = LogisticsDeal.objects.create(
            tenant=self.tenant, ref_number=long_ref, partner=self.partner,
            order_date="2026-07-01", total_amount=D("1"))
        LogisticsShipmentDeal.objects.create(shipment=shipment, deal=other)
        other_inv = PurchaseInvoice.objects.create(
            tenant=self.tenant, invoice_number=f"{inv.invoice_number}-B",
            invoice_type=PurchaseInvoice.INVOICE_TYPE_INTERNATIONAL,
            partner=self.partner, currency=self.ils, invoice_date="2026-07-02",
            exchange_rate=D("1"), grand_total=D("300"), deal=other, shipment=shipment)
        PurchaseInvoiceItem.objects.create(
            invoice=other_inv, product=self.p1, name="إطار", quantity=D("3"),
            unit_price=D("100"), total_price=D("300"),
            landed_unit_price_ils=D("100"), landed_line_total_ils=D("300"))

        # 6 لا 10: لو طابق REF حركةَ REF0 لصار 9 — السقف (10) لا يُخفيه.
        for ref, qty in ((deal.ref_number, "6"), (long_ref, "3")):
            record_stock_movement(
                product=self.p1, movement_type="IN", quantity=D(qty),
                unit_cost=D("100"), reference_type="SHIPMENT",
                reference_id=shipment.pk, partner=self.partner,
                movement_date="2026-07-03",
                notes=f"[backfill] شحنة {shipment.shipment_number} | صفقة {ref}",
                tenant=self.tenant)

        sync_import_receipt_from_shipment_stock(inv)
        sync_import_receipt_from_shipment_stock(other_inv)
        inv.refresh_from_db()
        other_inv.refresh_from_db()
        assert inv.items.get().received_quantity == D("6")
        assert inv.receipt_status == PurchaseInvoice.RECEIPT_PARTIAL
        assert other_inv.items.get().received_quantity == D("3")
        assert other_inv.receipt_status == PurchaseInvoice.RECEIPT_FULL

        # الهجرة 0089 نسخةٌ على النماذج التاريخية — تُحرَس بالبيانات نفسها.
        import importlib
        from django.apps import apps as django_apps
        PurchaseInvoiceItem.objects.filter(invoice__in=[inv, other_inv]).update(
            received_quantity=0)
        PurchaseInvoice.objects.filter(pk__in=[inv.pk, other_inv.pk]).update(
            receipt_status=PurchaseInvoice.RECEIPT_NOT)
        mig = importlib.import_module(
            "logistics.migrations.0089_sync_import_receipts_legacy_notes")
        mig.sync_receipts(django_apps, None)
        mig.sync_receipts(django_apps, None)  # idempotent
        assert inv.items.get().received_quantity == D("6")
        assert other_inv.items.get().received_quantity == D("3")
        inv.refresh_from_db()
        other_inv.refresh_from_db()
        assert inv.receipt_status == PurchaseInvoice.RECEIPT_PARTIAL
        assert other_inv.receipt_status == PurchaseInvoice.RECEIPT_FULL
