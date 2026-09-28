"""#225: إعادة احتساب التكلفة الواصلة تحدّث بنود الفاتورة الدولية في مكانها.

كانت `recalculate_landed_for_shipment` تنفّذ `inv.items.all().delete()` ثم تعيد
إنشاء البنود، فتضيع الأرقام التسلسلية وحقول المستخدم، وتُصفَّر كميات الاستلام
(بلا إعادة مزامنة) فتُعرض بضاعةٌ دخلت أصلاً للاستلام مرّةً ثانية — ويتضاعف
المخزون. الثلاثة المُعاد إنتاجها هنا: مسودة، مضاعفة مخزون، ومرحّلة مع
`auto_repost`.

تشغيل: python -m pytest logistics/tests/test_recalculate_landed_items.py -q
"""
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from rest_framework.test import APITestCase

from accounting.models import Account
from accounting.services import create_fiscal_year
from inventory.models import Product, ProductSerial, StockMovement, Warehouse
from inventory.serials import SERIAL_MODE_OPTIONAL
from inventory.services import receive_shipment_stock
from logistics.models import (
    LocalShipment,
    LogisticsClearance,
    LogisticsDeal,
    LogisticsDealItem,
    LogisticsPayment,
    LogisticsShipment,
    LogisticsShipmentDeal,
    PurchaseInvoice,
    PurchaseInvoiceItem,
)
from logistics.services import get_or_create_purchase_settings
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company

D = lambda v: Decimal(str(v))


class RecalculateLandedItemsTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="recalc-items", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        Currency.objects.create(Code="USD", Name="دولار")
        cls.tenant = create_company("شركة إعادة الاحتساب", cls.user)
        cls.tenant.import_enabled = True
        cls.tenant.save(update_fields=["import_enabled"])
        create_fiscal_year(cls.tenant, 2026)
        cls.ap = Account.objects.get(tenant=cls.tenant, code="2101")
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="مصنع الكوابل", partner_type="Supplier",
            linked_account=cls.ap)
        cls.deal = LogisticsDeal.objects.create(
            tenant=cls.tenant, ref_number="D-0042", partner=cls.partner,
            order_date="2026-06-01", total_amount=D("2000"),
            description="شحنة الكوابل", total_cbm=D("5"))
        cls.shipment = LogisticsShipment.objects.create(
            tenant=cls.tenant, shipment_number="SH-0001",
            shipment_name="شحنة الكوابل", total_shipping_cost_usd=D("100"))
        LogisticsShipmentDeal.objects.create(shipment=cls.shipment, deal=cls.deal)
        LogisticsPayment.objects.create(
            shipment=cls.shipment, amount=D("100"), usd_to_ils=D("3.6"),
            status="Confirmed")
        LogisticsPayment.objects.create(
            deal=cls.deal, amount=D("2000"), usd_to_ils=D("3.7"), status="Confirmed")
        cls.clearance = LogisticsClearance.objects.create(
            tenant=cls.tenant, shipment=cls.shipment, declaration_number="CL-1")
        # نمط «بدون» يفرّغ الأرقام من الحمولة عند الحفظ، فلا يُقاس حفظُها أصلاً.
        ps = get_or_create_purchase_settings(cls.tenant)
        ps.serial_entry_mode = SERIAL_MODE_OPTIONAL
        ps.save(update_fields=["serial_entry_mode"])

    # ── أدوات ──────────────────────────────────────────────────────────────
    def _auth(self):
        self.client.force_authenticate(user=self.user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _product(self, sku, *, serialized=False):
        return Product.objects.create(
            tenant=self.tenant, sku=sku, name_ar=f"منتج {sku}",
            is_serialized=serialized, quantity_on_hand=D("0"), avg_cost=D("0"))

    def _deal_item(self, product, qty, price):
        return LogisticsDealItem.objects.create(
            deal=self.deal, product=product, quantity=D(qty), unit_price=D(price))

    def _import(self):
        return self.client.post(
            "/api/logistics/purchase-invoices/import-from-clearance/",
            {"clearance_id": self.clearance.id, "deal_ids": [self.deal.id],
             "deal_remaining_rate": "3.7", "shipment_remaining_rate": "3.65"},
            format="json", **self._auth())

    def _invoice(self):
        return PurchaseInvoice.objects.get(tenant=self.tenant, deal=self.deal)

    def _recalculate(self, **body):
        return self.client.post(
            "/api/logistics/purchase-invoices/recalculate-landed-cost/",
            {"shipment_id": self.shipment.id, **body}, format="json", **self._auth())

    def _post(self, inv, **body):
        return self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/post-to-accounting/", body,
            format="json", **self._auth())

    def _receive(self, inv, lines):
        return self.client.post(
            f"/api/logistics/purchase-invoices/{inv.pk}/receive/", {"lines": lines},
            format="json", **self._auth())

    def _add_capitalized_local_transport(self, amount="450"):
        """تكلفة نقلٍ محليّ تُرسمل ⇒ تتغيّر التكلفة الواصلة فتلزم إعادة الاحتساب."""
        LocalShipment.objects.create(
            tenant=self.tenant, shipment=self.shipment, clearance=self.clearance,
            carrier=self.partner, amount=D(amount), currency=self.ils,
            exchange_rate=D("1"), status="delivered", capitalize_to_inventory=True)

    def _patch_items(self, inv, serials_by_item):
        """يكتب أرقاماً تسلسلية على بنودٍ قائمة عبر نفس مسار المحرِّر (PATCH بالمعرّف)."""
        detail = self.client.get(
            f"/api/logistics/purchase-invoices/{inv.pk}/", **self._auth())
        assert detail.status_code == 200, detail.content
        items = [
            {
                "id": row["id"], "product": row["product"], "name": row["name"],
                "quantity": row["quantity"], "unit_price": row["unit_price"],
                "total_price": row["total_price"],
                "serials": serials_by_item.get(row["id"], row.get("serials") or []),
            }
            for row in detail.json()["items"]
        ]
        return self.client.patch(
            f"/api/logistics/purchase-invoices/{inv.pk}/", {"items": items},
            format="json", **self._auth())

    # ── (1) مسودة: المعرّفات وحقول المستخدم ────────────────────────────────
    def test_recalculate_keeps_draft_item_ids_and_user_serials(self):
        cable = self._product("R-CABLE")
        plug = self._product("R-PLUG")
        self._deal_item(cable, "10", "100")
        self._deal_item(plug, "1", "1000")
        assert self._import().status_code == 201

        inv = self._invoice()
        ids_before = sorted(inv.items.values_list("id", flat=True))
        cable_item = inv.items.get(product=cable)
        patched = self._patch_items(inv, {cable_item.id: ["SN-1", "SN-2"]})
        assert patched.status_code == 200, patched.content
        landed_before = inv.items.get(product=cable).landed_line_total_ils

        self._add_capitalized_local_transport()
        res = self._recalculate()
        assert res.status_code == 200, res.content

        inv.refresh_from_db()
        assert sorted(inv.items.values_list("id", flat=True)) == ids_before
        cable_item = inv.items.get(product=cable)
        assert cable_item.id == ids_before[0]
        assert cable_item.serials == ["SN-1", "SN-2"]
        # والحقول المحسوبة تحدّثت فعلاً (وإلا مرّ الاختبار بلا إعادة احتساب).
        assert cable_item.landed_line_total_ils > landed_before

    # ── (2) مضاعفة المخزون ─────────────────────────────────────────────────
    def test_recalculate_keeps_legacy_synced_draft_from_being_received_twice(self):
        """مسودة دخلت بضاعتها بحركات `SHIPMENT` القديمة: إعادة الاحتساب كانت
        تُصفّر `received_quantity` فتُقبل عليها كميةٌ ثانية ويصير الرصيد 20."""
        cable = self._product("R-LEGACY")
        self._deal_item(cable, "10", "200")
        receive_shipment_stock(self.shipment)
        assert self._import().status_code == 201

        inv = self._invoice()
        assert inv.receipt_status == PurchaseInvoice.RECEIPT_FULL
        assert inv.items.get().received_quantity == D("10")

        self._add_capitalized_local_transport()
        assert self._recalculate().status_code == 200

        inv.refresh_from_db()
        item = inv.items.get()
        assert item.received_quantity == D("10"), "الكمية المستلَمة لا تُصفَّر"
        assert inv.receipt_status == PurchaseInvoice.RECEIPT_FULL

        assert self._post(inv).status_code == 201
        second = self._receive(inv, [{"item_id": item.id, "quantity": "10"}])
        assert second.status_code == 400, second.content
        assert "تتجاوز المتبقي" in second.json()["error"]
        cable.refresh_from_db()
        assert cable.quantity_on_hand == D("10"), "الرصيد لا يتضاعف"

    # ── (3) مرحّلة مع auto_repost: الوحدات المرقّمة ─────────────────────────
    def test_auto_repost_keeps_serial_units_bound_to_the_same_item(self):
        phone = self._product("R-SERIAL", serialized=True)
        self._deal_item(phone, "3", "600")
        assert self._import().status_code == 201

        inv = self._invoice()
        item_id = inv.items.get().id
        serials = ["SN-A1", "SN-A2", "SN-A3"]
        assert self._patch_items(inv, {item_id: serials}).status_code == 200
        assert self._post(inv).status_code == 201
        assert ProductSerial.objects.filter(purchase_item_id=item_id).count() == 3

        self._add_capitalized_local_transport()
        recalc = self._recalculate(auto_repost=True)
        assert recalc.status_code == 200, recalc.content
        assert recalc.json()["reconciliation"]["reposted"] == 1

        inv.refresh_from_db()
        item = inv.items.get()
        assert item.id == item_id, "معرّف البند ثابت"
        assert item.serials == serials
        units = ProductSerial.objects.filter(tenant=self.tenant, product=phone)
        assert units.count() == 3
        assert {u.purchase_item_id for u in units} == {item_id}

    # ── بنود تُضاف وتُحذف ──────────────────────────────────────────────────
    def test_recalculate_adds_a_new_deal_product_and_deletes_an_untouched_one(self):
        cable = self._product("R-ADD-1")
        plug = self._product("R-ADD-2")
        self._deal_item(cable, "10", "100")
        removed_item = self._deal_item(plug, "1", "1000")
        assert self._import().status_code == 201
        inv = self._invoice()
        assert inv.items.count() == 2

        removed_item.is_deleted = True
        removed_item.save(update_fields=["is_deleted"])
        added = self._product("R-ADD-3")
        self._deal_item(added, "2", "500")
        assert self._recalculate().status_code == 200

        inv.refresh_from_db()
        assert set(inv.items.values_list("product_id", flat=True)) == {cable.id, added.id}

    def test_recalculate_rejects_dropping_a_received_line_and_writes_nothing(self):
        """البند المستلَم لا يُحذف بصمت — العملية كلها تُرفض (400) ولا يُكتب شيء."""
        cable = self._product("R-KEEP")
        keep_item = self._deal_item(cable, "10", "200")
        receive_shipment_stock(self.shipment)
        assert self._import().status_code == 201
        inv = self._invoice()
        before = {
            "ids": sorted(inv.items.values_list("id", flat=True)),
            "subtotal": inv.subtotal,
            "landed": sorted(inv.items.values_list("landed_line_total_ils", flat=True)),
        }

        keep_item.is_deleted = True
        keep_item.save(update_fields=["is_deleted"])
        self._add_capitalized_local_transport()
        res = self._recalculate()
        assert res.status_code == 400, res.content
        assert cable.name_ar in res.json()["error"]

        inv.refresh_from_db()
        assert sorted(inv.items.values_list("id", flat=True)) == before["ids"]
        assert inv.subtotal == before["subtotal"]
        assert sorted(
            inv.items.values_list("landed_line_total_ils", flat=True)
        ) == before["landed"]

    def test_duplicate_product_lines_are_matched_in_order_and_do_not_swap(self):
        cable = self._product("R-DUP")
        self._deal_item(cable, "10", "100")
        self._deal_item(cable, "4", "250")
        assert self._import().status_code == 201
        inv = self._invoice()
        first, second = list(inv.items.order_by("id"))
        assert (first.quantity, second.quantity) == (D("10"), D("4"))
        assert self._patch_items(
            inv, {first.id: ["FIRST"], second.id: ["SECOND"]}).status_code == 200

        self._add_capitalized_local_transport()
        assert self._recalculate().status_code == 200

        first.refresh_from_db()
        second.refresh_from_db()
        assert (first.quantity, second.quantity) == (D("10"), D("4"))
        assert (first.serials, second.serials) == (["FIRST"], ["SECOND"])

    # ── أداة الكشف ─────────────────────────────────────────────────────────
    def _second_deal(self, product, qty, price):
        """صفقةٌ ثانية على الشحنة نفسها، مدفوعةٌ بالكامل فتقبل الاستيراد."""
        deal = LogisticsDeal.objects.create(
            tenant=self.tenant, ref_number="D-0043", partner=self.partner,
            order_date="2026-06-02", total_amount=D(qty) * D(price),
            description="الصفقة الثانية", total_cbm=D("5"))
        LogisticsShipmentDeal.objects.create(shipment=self.shipment, deal=deal)
        LogisticsPayment.objects.create(
            deal=deal, amount=D(qty) * D(price), usd_to_ils=D("3.7"), status="Confirmed")
        LogisticsDealItem.objects.create(
            deal=deal, product=product, quantity=D(qty), unit_price=D(price))
        return deal

    def test_audit_command_lists_damaged_drafts_and_doubled_stock_without_writing(self):
        cable = self._product("R-AUDIT")
        plug = self._product("R-AUDIT-2")
        self._deal_item(cable, "10", "200")
        draft_deal = self._second_deal(plug, "5", "100")
        receive_shipment_stock(self.shipment)
        imported = self.client.post(
            "/api/logistics/purchase-invoices/import-from-clearance/",
            {"clearance_id": self.clearance.id,
             "deal_ids": [self.deal.id, draft_deal.id],
             "deal_remaining_rate": "3.7", "shipment_remaining_rate": "3.65"},
            format="json", **self._auth())
        assert imported.status_code == 201, imported.content
        doubled_inv = self._invoice()
        draft_inv = PurchaseInvoice.objects.get(tenant=self.tenant, deal=draft_deal)

        # الضرر كما تركه الخلل: كميات مستلَمة مصفَّرة وحالةٌ تقول «مستلمة».
        PurchaseInvoiceItem.objects.filter(
            invoice__in=[doubled_inv, draft_inv]).update(received_quantity=0)
        assert self._post(doubled_inv).status_code == 201
        warehouse = Warehouse.objects.get(tenant=self.tenant, is_default=True)
        received = self._receive(doubled_inv, [
            {"item_id": doubled_inv.items.get().id, "quantity": "10",
             "warehouse_id": warehouse.id},
        ])
        assert received.status_code == 200, received.content
        cable.refresh_from_db()
        assert cable.quantity_on_hand == D("20"), "المخزون تضاعف فعلاً"

        movements_before = StockMovement.objects.count()
        quantities_before = dict(
            PurchaseInvoiceItem.objects.values_list("id", "received_quantity"))
        out = StringIO()
        call_command("audit_import_double_receipt", tenant=self.tenant.TenantID, stdout=out)
        text = out.getvalue()

        at_risk, doubled = text.split("(ب)", 1)
        assert draft_inv.invoice_number in at_risk.split("(أ)")[1]
        assert doubled_inv.invoice_number in doubled
        assert cable.name_ar in doubled

        assert StockMovement.objects.count() == movements_before
        assert dict(
            PurchaseInvoiceItem.objects.values_list("id", "received_quantity")
        ) == quantities_before, "الأداة لا تكتب شيئاً"
        cable.refresh_from_db()
        assert cable.quantity_on_hand == D("20")
