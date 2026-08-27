"""Phase 7 (T-I1/T-I2): مستندات المخزون — تحويل بين المستودعات + جرد.

يثبت أن الترحيل يصحّح المخزون ويُنشئ القيود/الحركات الصحيحة:
- التحويل: صافي أثر صفري على إجمالي الشركة، حركتان موسومتان بالمستودعين.
- الجرد: تسوية الرصيد ليطابق العدّ + قيد فرق (مخزون ↔ ت.ب.م).
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APITestCase

from accounting.models import Account, FiscalPeriod, JournalLine
from core.models import ActivityLog
from inventory.models import (
    Product, ProductCategory, Warehouse, StockMovement,
    WarehouseTransfer, WarehouseTransferLine, Stocktake, StocktakeLine,
)
from inventory.services import (
    post_warehouse_transfer, unpost_warehouse_transfer, post_stocktake,
)
from tenants.models import Tenant, UserCompanyMembership
from tenants.services import create_company


class WarehouseTransferTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=701, CompanyName="TRF Co")
        cls.wh_a = Warehouse.objects.create(tenant=cls.tenant, name="مستودع A", code="A")
        cls.wh_b = Warehouse.objects.create(tenant=cls.tenant, name="مستودع B", code="B")
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="TRF-1", name_ar="منتج تحويل",
            quantity_on_hand=Decimal("100"), avg_cost=Decimal("10"),
        )

    def _make_transfer(self, qty="30"):
        t = WarehouseTransfer.objects.create(
            tenant=self.tenant, transfer_date="2026-07-01",
            source_warehouse=self.wh_a, dest_warehouse=self.wh_b,
        )
        WarehouseTransferLine.objects.create(transfer=t, product=self.product, quantity=Decimal(qty))
        return t

    def test_transfer_is_net_zero_on_company_totals(self):
        t = self._make_transfer("30")
        post_warehouse_transfer(t)
        self.product.refresh_from_db()
        # نقل موقعي: الإجمالي والمتوسط لا يتغيّران.
        self.assertEqual(self.product.quantity_on_hand, Decimal("100.0000"))
        self.assertEqual(self.product.avg_cost, Decimal("10.0000"))

    def test_transfer_creates_two_tagged_movements(self):
        t = self._make_transfer("30")
        post_warehouse_transfer(t)
        movs = StockMovement.objects.filter(reference_type="WAREHOUSE_TRANSFER", reference_id=t.id)
        self.assertEqual(movs.count(), 2)
        out = movs.get(movement_type="OUT")
        inn = movs.get(movement_type="IN")
        self.assertEqual(out.warehouse_id, self.wh_a.id)
        self.assertEqual(inn.warehouse_id, self.wh_b.id)
        self.assertEqual(out.quantity, Decimal("30.0000"))
        self.assertEqual(inn.quantity, Decimal("30.0000"))
        t.refresh_from_db()
        self.assertTrue(t.is_posted)
        self.assertTrue(t.transfer_number)

    def test_same_warehouse_rejected(self):
        t = WarehouseTransfer.objects.create(
            tenant=self.tenant, transfer_date="2026-07-01",
            source_warehouse=self.wh_a, dest_warehouse=self.wh_a,
        )
        WarehouseTransferLine.objects.create(transfer=t, product=self.product, quantity=Decimal("5"))
        with self.assertRaises(ValidationError):
            post_warehouse_transfer(t)

    def test_double_post_rejected(self):
        t = self._make_transfer("10")
        post_warehouse_transfer(t)
        with self.assertRaises(ValidationError):
            post_warehouse_transfer(t)

    def test_unpost_restores_and_clears_flag(self):
        t = self._make_transfer("30")
        post_warehouse_transfer(t)
        unpost_warehouse_transfer(t)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity_on_hand, Decimal("100.0000"))
        t.refresh_from_db()
        self.assertFalse(t.is_posted)
        # 2 حركات ترحيل + 2 حركات عكس = 4
        self.assertEqual(
            StockMovement.objects.filter(reference_type="WAREHOUSE_TRANSFER", reference_id=t.id).count(), 4)


class StocktakeTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=702, CompanyName="JRD Co")
        cls.inv_acct = Account.objects.create(
            tenant=cls.tenant, code="1104", name="المخزون", account_type="Asset", is_active=True)
        cls.cogs_acct = Account.objects.create(
            tenant=cls.tenant, code="5101", name="ت.ب.م", account_type="Expense", is_active=True)
        cls.cat = ProductCategory.objects.create(
            tenant=cls.tenant, name="فئة جرد",
            inventory_account=cls.inv_acct, cogs_account=cls.cogs_acct)
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="JRD-1", name_ar="منتج جرد", category=cls.cat,
            quantity_on_hand=Decimal("100"), avg_cost=Decimal("10"))
        FiscalPeriod.objects.create(
            tenant=cls.tenant, name="2026",
            start_date="2026-01-01", end_date="2026-12-31", is_closed=False)

    def _make_stocktake(self, counted):
        s = Stocktake.objects.create(tenant=self.tenant, stocktake_date="2026-07-01")
        StocktakeLine.objects.create(stocktake=s, product=self.product, counted_quantity=Decimal(counted))
        return s

    def test_surplus_increases_stock_and_posts_journal(self):
        s = self._make_stocktake("120")  # فائض +20 × 10 = 200
        post_stocktake(s)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity_on_hand, Decimal("120.0000"))
        s.refresh_from_db()
        self.assertTrue(s.is_posted)
        self.assertIsNotNone(s.journal)
        # Dr مخزون 200 / Cr ت.ب.م 200
        inv_line = JournalLine.objects.get(journal=s.journal, account=self.inv_acct)
        cogs_line = JournalLine.objects.get(journal=s.journal, account=self.cogs_acct)
        self.assertEqual(inv_line.debit, Decimal("200.00"))
        self.assertEqual(cogs_line.credit, Decimal("200.00"))
        line = s.lines.first()
        self.assertEqual(line.system_quantity, Decimal("100.0000"))
        self.assertEqual(line.variance, Decimal("20.0000"))

    def test_shortage_decreases_stock_and_posts_journal(self):
        s = self._make_stocktake("90")  # عجز -10 × 10 = 100
        post_stocktake(s)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity_on_hand, Decimal("90.0000"))
        s.refresh_from_db()
        inv_line = JournalLine.objects.get(journal=s.journal, account=self.inv_acct)
        cogs_line = JournalLine.objects.get(journal=s.journal, account=self.cogs_acct)
        self.assertEqual(cogs_line.debit, Decimal("100.00"))
        self.assertEqual(inv_line.credit, Decimal("100.00"))

    def test_no_variance_posts_no_journal(self):
        s = self._make_stocktake("100")  # لا فرق
        post_stocktake(s)
        s.refresh_from_db()
        self.assertTrue(s.is_posted)
        self.assertIsNone(s.journal)
        self.product.refresh_from_db()
        self.assertEqual(self.product.quantity_on_hand, Decimal("100.0000"))

    def test_movement_tagged_stocktake(self):
        s = self._make_stocktake("120")
        post_stocktake(s)
        mov = StockMovement.objects.get(reference_type="STOCKTAKE", reference_id=s.id)
        self.assertEqual(mov.movement_type, "ADJUST_IN")
        self.assertEqual(mov.quantity, Decimal("20.0000"))


class WarehouseDetailApiTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="warehouse-owner", password="x")
        cls.foreign_owner = User.objects.create_user(
            username="warehouse-foreign-owner", password="x",
        )
        cls.viewer = User.objects.create_user(username="warehouse-viewer", password="x")
        cls.tenant = create_company("شركة تفاصيل المستودع", cls.owner)
        cls.foreign_tenant = create_company("شركة مستودع أخرى", cls.foreign_owner)
        UserCompanyMembership.objects.create(
            user=cls.viewer, tenant=cls.tenant, role="viewer",
        )
        cls.warehouse = Warehouse.objects.create(
            tenant=cls.tenant, name="مستودع الفرع", code="WH-BRANCH",
        )
        cls.foreign_warehouse = Warehouse.objects.create(
            tenant=cls.foreign_tenant, name="مستودع سري", code="WH-SECRET",
        )
        cls.first_product = Product.objects.create(
            tenant=cls.tenant, sku="WH-001", name_ar="المنتج الأول",
            avg_cost=Decimal("10"),
        )
        cls.second_product = Product.objects.create(
            tenant=cls.tenant, sku="WH-002", name_ar="المنتج الثاني",
            avg_cost=Decimal("2.5"),
        )
        cls.zero_product = Product.objects.create(
            tenant=cls.tenant, sku="WH-003", name_ar="منتج رصيده صفر",
            avg_cost=Decimal("50"),
        )
        cls.other_warehouse = Warehouse.objects.create(
            tenant=cls.tenant, name="مستودع آخر", code="WH-OTHER",
        )

        def movement(product, movement_type, quantity, warehouse=None):
            StockMovement.objects.create(
                tenant=cls.tenant,
                warehouse=warehouse or cls.warehouse,
                product=product,
                movement_type=movement_type,
                quantity=Decimal(quantity),
                movement_date="2026-07-26",
            )

        movement(cls.first_product, "IN", "10")
        movement(cls.first_product, "OUT", "3")
        movement(cls.first_product, "RETURN_IN", "2")
        movement(cls.first_product, "ADJUST_OUT", "1")
        movement(cls.second_product, "IN", "4")
        movement(cls.zero_product, "IN", "1")
        movement(cls.zero_product, "OUT", "1")
        movement(cls.first_product, "IN", "99", warehouse=cls.other_warehouse)

    def setUp(self):
        self.client.force_authenticate(user=self.owner)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def test_stock_action_returns_warehouse_items_and_moving_average_value(self):
        response = self.client.get(
            f"/api/inventory/warehouses/{self.warehouse.id}/stock/",
        )

        self.assertEqual(response.status_code, 200, response.content)
        payload = response.json()
        self.assertEqual(payload["warehouse"]["id"], self.warehouse.id)
        self.assertEqual(payload["item_count"], 2)
        self.assertEqual(payload["total_value"], "90.00")
        self.assertEqual(payload["valuation_method"], "moving_average_cost")

        rows = {row["sku"]: row for row in payload["items"]}
        self.assertEqual(set(rows), {"WH-001", "WH-002"})
        self.assertEqual(rows["WH-001"]["quantity"], "8.0000")
        self.assertEqual(rows["WH-001"]["avg_cost"], "10.0000")
        self.assertEqual(rows["WH-001"]["stock_value"], "80.00")
        self.assertEqual(rows["WH-002"]["quantity"], "4.0000")
        self.assertEqual(rows["WH-002"]["stock_value"], "10.00")
        self.assertTrue(ActivityLog.objects.filter(
            tenant=self.tenant,
            action="view",
            entity_type="warehouse",
            entity_id=self.warehouse.id,
        ).exists())

    def test_warehouse_name_can_be_changed_then_seen_in_detail(self):
        response = self.client.patch(
            f"/api/inventory/warehouses/{self.warehouse.id}/",
            {"name": "  مستودع رام الله  "},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["name"], "مستودع رام الله")
        self.assertTrue(ActivityLog.objects.filter(
            tenant=self.tenant,
            action="update",
            entity_type="warehouse",
            entity_id=self.warehouse.id,
            metadata__name_changed=True,
        ).exists())

        detail = self.client.get(
            f"/api/inventory/warehouses/{self.warehouse.id}/stock/",
        )
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertEqual(detail.json()["warehouse"]["name"], "مستودع رام الله")

    def test_stock_action_hides_other_tenant_warehouse(self):
        response = self.client.get(
            f"/api/inventory/warehouses/{self.foreign_warehouse.id}/stock/",
        )
        self.assertEqual(response.status_code, 404)

    def test_stock_value_requires_inventory_cost_permission(self):
        self.client.force_authenticate(user=self.viewer)
        response = self.client.get(
            f"/api/inventory/warehouses/{self.warehouse.id}/stock/",
        )
        self.assertEqual(response.status_code, 403)


class StockValuationActionTest(TestCase):
    """P0-5: تقييم المخزون الخادمي — التجميعات تطابق دلالة الشاشة حرفياً."""

    @classmethod
    def setUpTestData(cls):
        from django.contrib.auth.models import User
        from rest_framework.authtoken.models import Token
        from tenants.services import create_company

        cls.user = User.objects.create_user(username="valuator", password="x")
        cls.tenant = create_company("شركة التقييم", cls.user)
        cls.token = Token.objects.create(user=cls.user)
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="VAL-1", name_ar="منتج التقييم",
            quantity_on_hand=Decimal("7"), avg_cost=Decimal("12"))
        mk = StockMovement.objects.create
        # IN بـ10 ثم IN بـ20 ثم OUT بـ15 ثم ADJUST_IN بـ0 (لا يدخل المتوسط)
        mk(tenant=cls.tenant, product=cls.product, movement_type="IN",
           quantity=Decimal("5"), unit_cost=Decimal("10"),
           movement_date="2026-01-10")
        mk(tenant=cls.tenant, product=cls.product, movement_type="IN",
           quantity=Decimal("5"), unit_cost=Decimal("20"),
           movement_date="2026-02-10")
        mk(tenant=cls.tenant, product=cls.product, movement_type="OUT",
           quantity=Decimal("3"), unit_cost=Decimal("15"),
           movement_date="2026-03-10")
        mk(tenant=cls.tenant, product=cls.product, movement_type="ADJUST_IN",
           quantity=Decimal("1"), unit_cost=Decimal("0"),
           movement_date="2026-03-15")

    def _get(self, **params):
        from rest_framework.test import APIClient
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        return client.get(
            "/api/inventory/stock-movements/valuation/", params,
            HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def test_aggregates_match_screen_semantics(self):
        res = self._get()
        self.assertEqual(res.status_code, 200, res.content[:300])
        row = next(r for r in res.data["rows"] if r["sku"] == "VAL-1")
        self.assertEqual(Decimal(row["first_in_cost"]), Decimal("10"))   # FIFO
        self.assertEqual(Decimal(row["last_in_cost"]), Decimal("0"))     # LIFO — آخر داخل ADJUST_IN
        self.assertEqual(Decimal(row["avg_in_cost"]), Decimal("15"))     # (10+20)/2، صفر الكلفة مستبعد
        self.assertEqual(Decimal(row["avg_out_cost"]), Decimal("15"))
        # صافي الحركات: +5 +5 -3 +1 = 8 (ADJUST_IN داخل، مثل includes("IN"))
        self.assertEqual(Decimal(row["moves_qty_delta"]), Decimal("8"))

    def test_as_of_filters_the_aggregates(self):
        res = self._get(as_of="2026-01-31")
        row = next(r for r in res.data["rows"] if r["sku"] == "VAL-1")
        self.assertEqual(Decimal(row["last_in_cost"]), Decimal("10"))
        self.assertEqual(Decimal(row["moves_qty_delta"]), Decimal("5"))
        self.assertIsNone(row["avg_out_cost"])

    def test_movement_list_is_paginated_by_default(self):
        """P0-5: قائمة الحركات تعيد غلاف {results,count} بلا ?page=."""
        from rest_framework.test import APIClient
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        res = client.get(
            "/api/inventory/stock-movements/",
            HTTP_X_TENANT_ID=str(self.tenant.TenantID))
        self.assertEqual(res.status_code, 200)
        self.assertIn("results", res.data)
        self.assertEqual(res.data["count"], 4)
