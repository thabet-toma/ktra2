"""T-REORDER: تقريرا المخزون بعد ربطهما بمحرّك التجديد.

ما يُثبَت هنا ثلاثة أشياء لا يراها قارئ الكود:
  1. أن «تحت حدّ الطلب» صار يرى صنفاً نفد **ولا حدَّ يدوي له** — وهو ما كان
     يُسقطه شرطُ `min_stock_level > 0` القديم، أي أغلب الكتالوج.
  2. أن مجموع تنقيب صفّ النوع يساوي رقم الصفّ عموداً بعمود.
  3. أن الموديل الجديد من النوع نفسه يقلب القرار من «عاجل» إلى «مؤجَّل».
"""
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from inventory.models import Product, StockMovement
from tenants.services import create_company


def _run(client, key, tenant_id, **params):
    res = client.get(f"/api/reports/{key}/", params, HTTP_X_TENANT_ID=str(tenant_id))
    assert res.status_code == 200, res.content[:400]
    return res.json()


class ReplenishmentReportTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="repl_reports", password="x")
        cls.tenant = create_company("شركة تقارير التجديد", cls.user)
        cls.today = datetime.date.today()

        def product(sku, qty, group="", name=None):
            return Product.objects.create(
                tenant=cls.tenant, sku=sku, name_ar=name or sku,
                variant_group=group, quantity_on_hand=Decimal(qty),
                avg_cost=Decimal("10"),
            )

        def sells(p, *, first_days_ago=89):
            """يمنح الصنف تاريخاً كافياً ومعدّلاً موجباً (نفس نمط اختبار المحرّك)."""
            StockMovement.objects.create(
                tenant=cls.tenant, product=p, movement_type="IN",
                quantity=Decimal("1000"),
                movement_date=cls.today - datetime.timedelta(days=first_days_ago),
            )
            for week in range(1, 7):
                StockMovement.objects.create(
                    tenant=cls.tenant, product=p, movement_type="OUT",
                    quantity=Decimal("14"),
                    movement_date=cls.today - datetime.timedelta(days=week * 7),
                )

        # نفد، وبلا حدٍّ أدنى يدوي — الحالة التي كان التقرير القديم يعمى عنها.
        cls.orphan = product("OUT-NO-LIMIT", "0", name="صنف نفد بلا حدّ")
        sells(cls.orphan)
        # نوعٌ فيه موديلان: قديمٌ نفد وجديدٌ عليه رصيد.
        cls.old_model = product("OLD-205", "0", group="205/65/16", name="موديل قديم")
        sells(cls.old_model)
        cls.new_model = product("NEW-205", "400", group="205/65/16", name="موديل جديد")
        sells(cls.new_model)

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    # ── (1) ما نفد بلا حدٍّ يدوي صار يظهر ──
    def test_low_stock_sees_item_that_ran_out_without_a_manual_limit(self):
        data = _run(self.client, "low-stock", self.tenant.TenantID)
        by_sku = {r["sku"]: r for r in data["rows"]}
        assert "OUT-NO-LIMIT" in by_sku, list(by_sku)
        row = by_sku["OUT-NO-LIMIT"]
        assert row["status"] == "نفذ"
        assert row["min_source"] == "محسوب"
        assert Decimal(row["min_stock_level"]) > 0

    # ── (2) الموديل الجديد يقلب القرار ──
    def test_newer_model_in_the_same_type_defers_the_order(self):
        data = _run(self.client, "stock-replenishment", self.tenant.TenantID)
        by_sku = {r["sku"]: r for r in data["rows"]}
        assert by_sku["OLD-205"]["urgency"] == "مؤجَّل"
        assert by_sku["OLD-205"]["newest_alternative"] == "موديل جديد"
        assert by_sku["OLD-205"]["alternatives"] == 1
        # وحدَه بلا نوعٍ يغطّيه ⇒ عاجل
        assert by_sku["OUT-NO-LIMIT"]["urgency"] == "عاجل"

    # ── (3) مجموع التنقيب = رقم صفّ النوع ──
    def test_group_row_equals_the_sum_of_its_drill_rows(self):
        data = _run(self.client, "stock-replenishment", self.tenant.TenantID, level="group")
        row = next(r for r in data["rows"] if r["group_key"] == "205/65/16")
        assert row["products_count"] == 2

        res = self.client.get(
            "/api/reports/stock-replenishment/drill/",
            {"level": "group", "group_key": "205/65/16"},
            HTTP_X_TENANT_ID=str(self.tenant.TenantID),
        )
        assert res.status_code == 200, res.content[:400]
        detail = res.json()["rows"]
        assert len(detail) == 2
        for column in ("available", "on_order", "order_qty", "suggested_min"):
            assert Decimal(row[column]) == sum(
                (Decimal(d[column]) for d in detail), Decimal("0")
            ), column

    # ── الداشبورد يقول ما يقوله التقرير ──
    def test_dashboard_counter_matches_the_report(self):
        """كان عدّاد «نفذ» يفلتر `min_stock_level > 0` قبل العدّ فيخفي معظم النافد.

        المصدر واحد الآن، فالرقمان يجب أن يتطابقا على نفس البيانات — وهذا
        الاختبار هو ما يمنع تباعدهما ثانيةً.
        """
        res = self.client.get("/api/dashboard/", HTTP_X_TENANT_ID=str(self.tenant.TenantID))
        assert res.status_code == 200, res.content[:300]
        inventory = res.json()["inventory"]

        report = _run(self.client, "low-stock", self.tenant.TenantID)["rows"]
        assert inventory["out_of_stock"] == sum(
            1 for r in report if r["status"] == "نفذ"
        ) == 2      # OUT-NO-LIMIT و OLD-205، وكلاهما بلا حدٍّ يدوي
        assert inventory["low_stock"] == sum(1 for r in report if r["status"] == "منخفض")

    # ── العزل: شركة أخرى لا ترى شيئاً من هذا ──
    def test_other_company_sees_nothing(self):
        other_user = User.objects.create_user(username="repl_outsider", password="x")
        other = create_company("شركة أخرى للتجديد", other_user)
        self.client.force_authenticate(user=other_user)
        data = _run(self.client, "stock-replenishment", other.TenantID)
        assert data["rows"] == []
