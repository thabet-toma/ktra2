"""T-REORDER: تقريرا المخزون بعد ربطهما بمحرّك التجديد.

ما يُثبَت هنا ثلاثة أشياء لا يراها قارئ الكود:
  1. أن «تحت حدّ الطلب» صار يرى منتجاً نفد **ولا حدَّ يدوي له** — وهو ما كان
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
            """يمنح المنتج تاريخاً كافياً ومعدّلاً موجباً (نفس نمط اختبار المحرّك)."""
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
        cls.orphan = product("OUT-NO-LIMIT", "0", name="منتج نفد بلا حدّ")
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


class AutoReorderReportVisibilityTest(APITestCase):
    """#33/ط10: صفٌّ تلقائيٌّ لا يطلب شيئاً يسقط من العرض الافتراضي — لا يُحذف،
    وفلتر «راكد» يبقى يُظهره عمداً. المسار اليدوي لا يتأثر (`OTHER-MANUAL`)."""

    @classmethod
    def setUpTestData(cls):
        from inventory.models import ProductDemandForecast
        from logistics.models import Currency, PurchaseOrder, PurchaseOrderLine, PurchaseSettings
        from partners.models import Partner

        cls.user = User.objects.create_user(username="auto_visibility", password="x")
        cls.tenant = create_company("شركة رؤية المسار التلقائي", cls.user)
        PurchaseSettings.objects.create(
            tenant=cls.tenant, default_lead_time_days=14, review_period_days=14)
        today = datetime.date.today()

        # منتجٌ يدويٌّ عاديٌّ بلا مبيعات — بلا صفّ تنبّؤ، يبقى مرئياً كسابق عهده
        # (ط10 مقصورةٌ على `auto` — المسار اليدوي عرضه اليوم لا يتغيّر حرفاً).
        cls.manual_no_signal = Product.objects.create(
            tenant=cls.tenant, sku="OTHER-MANUAL", name_ar="منتج يدوي بلا إشارة",
            quantity_on_hand=Decimal("3"),
        )

        # صنفٌ تلقائيٌّ عليه طلبية شراءٍ مؤكَّدة تغطّي احتياجه بالكامل.
        cls.covered = Product.objects.create(
            tenant=cls.tenant, sku="AUTO-COVERED", name_ar="صنفٌ مغطّىً بطلبية",
            quantity_on_hand=Decimal("0"), reorder_mode=Product.REORDER_MODE_AUTO,
        )
        ProductDemandForecast.objects.create(
            tenant=cls.tenant, product=cls.covered,
            level=Decimal("10"), trend=Decimal("0"), mad=Decimal("0"),
            weeks_observed=10, last_week_start=today,
        )
        currency = Currency.objects.create(Code="ILB", Name="شيكل")
        supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورّد التغطية", partner_type="Supplier")
        order = PurchaseOrder.objects.create(
            tenant=cls.tenant, order_number="PO-COVER", supplier=supplier,
            order_date=today, currency=currency, status=PurchaseOrder.STATUS_CONFIRMED,
        )
        PurchaseOrderLine.objects.create(
            tenant=cls.tenant, order=order, product=cls.covered,
            quantity=Decimal("40"), unit_price=Decimal("1"), line_total=Decimal("40"),
        )

        # صنفٌ تلقائيٌّ لم يبع ولا قطعة — راكد.
        cls.dead = Product.objects.create(
            tenant=cls.tenant, sku="AUTO-DEAD", name_ar="صنفٌ تلقائيٌّ راكد",
            quantity_on_hand=Decimal("20"), reorder_mode=Product.REORDER_MODE_AUTO,
        )
        StockMovement.objects.create(
            tenant=cls.tenant, product=cls.dead, movement_type="IN",
            quantity=Decimal("20"), movement_date=today - datetime.timedelta(days=100),
        )
        ProductDemandForecast.objects.create(
            tenant=cls.tenant, product=cls.dead,
            level=Decimal("0"), trend=Decimal("0"), mad=Decimal("0"),
            weeks_observed=10, last_week_start=today,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def test_covered_and_dead_auto_rows_are_absent_by_default(self):
        data = _run(self.client, "stock-replenishment", self.tenant.TenantID)
        skus = {r["sku"] for r in data["rows"]}
        assert "AUTO-COVERED" not in skus, skus
        assert "AUTO-DEAD" not in skus, skus
        # اليدوي بلا إشارة يبقى ظاهراً كسابق عهده — لم يتغيّر حرفٌ فيه.
        assert "OTHER-MANUAL" in skus, skus

    def test_dead_row_is_reachable_under_the_dead_filter(self):
        data = _run(self.client, "stock-replenishment", self.tenant.TenantID, urgency="dead")
        skus = {r["sku"] for r in data["rows"]}
        assert "AUTO-DEAD" in skus, skus
        assert "AUTO-COVERED" not in skus, skus   # مغطّىً لا راكد — لا ينتمي لهذا الفلتر
