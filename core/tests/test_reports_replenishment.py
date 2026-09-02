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


class StaleForecastNoticeTest(APITestCase):
    """#34/ط5: تنبّؤٌ عمره أحد عشر يوماً ⇒ تحذيرٌ فوق الجدول؛ عمره ثلاثة أيام ⇒
    لا تحذير. العلاج الممنوع (إعادة الحساب من التقرير نفسه) غير موجودٍ هنا
    أصلاً — التقرير يقرأ `computed_at` المخزَّن ولا يستدعي أمر الحساب أبداً."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="stale_notice", password="x")
        cls.tenant = create_company("شركة تحذير الأرقام القديمة", cls.user)
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="STALE-1", name_ar="صنف تلقائي",
            quantity_on_hand=Decimal("0"), reorder_mode=Product.REORDER_MODE_AUTO,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def _forecast_aged(self, days):
        from django.utils import timezone

        from inventory.models import ProductDemandForecast

        row = ProductDemandForecast.objects.create(
            tenant=self.tenant, product=self.product,
            level=Decimal("5"), trend=Decimal("0"), mad=Decimal("0"),
            weeks_observed=10, last_week_start=datetime.date.today(),
        )
        # `computed_at` عمودٌ `auto_now` — `.update()` وحدها تتجاوزه لمحاكاة
        # تنبّؤٍ قديم فعلاً بلا انتظار أسبوعٍ حقيقي.
        ProductDemandForecast.objects.filter(pk=row.pk).update(
            computed_at=timezone.now() - datetime.timedelta(days=days),
        )

    def test_eleven_day_old_forecast_shows_a_notice(self):
        self._forecast_aged(11)
        data = _run(self.client, "stock-replenishment", self.tenant.TenantID)
        assert data["notice"], data

    def test_three_day_old_forecast_shows_no_notice(self):
        self._forecast_aged(3)
        data = _run(self.client, "stock-replenishment", self.tenant.TenantID)
        assert data["notice"] is None, data["notice"]

    def test_no_forecast_at_all_shows_no_notice(self):
        """الأمر لم يُشغَّل بعد على هذه الشركة إطلاقاً — لا رقم لقياس قِدَمه."""
        data = _run(self.client, "stock-replenishment", self.tenant.TenantID)
        assert data["notice"] is None, data["notice"]

    def test_other_reports_are_not_affected_by_the_notice_field(self):
        """الحقل اختياريٌّ (`ReportSpec.notice=None` افتراضاً) — تقريرٌ لا
        يعلنه يعود بـ`None` بلا أثر."""
        self._forecast_aged(11)
        data = _run(self.client, "low-stock", self.tenant.TenantID)
        assert data.get("notice") is None


class SupplierMoqReportVisibilityTest(APITestCase):
    """#34/ط9: علامة رفع الكمية إلى حدّ المورّد الأدنى تظهر في صفّ التقرير."""

    @classmethod
    def setUpTestData(cls):
        from inventory.models import SupplierProduct
        from partners.models import Partner

        cls.user = User.objects.create_user(username="moq_report", password="x")
        cls.tenant = create_company("شركة تقرير حدّ المورّد", cls.user)
        cls.today = datetime.date.today()

        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="MOQ-REPORT-1", name_ar="صنفٌ بحدّ مورّد",
            quantity_on_hand=Decimal("50"),
        )
        StockMovement.objects.create(
            tenant=cls.tenant, product=cls.product, movement_type="IN",
            quantity=Decimal("1000"), movement_date=cls.today - datetime.timedelta(days=89),
        )
        for week in range(1, 7):
            StockMovement.objects.create(
                tenant=cls.tenant, product=cls.product, movement_type="OUT",
                quantity=Decimal("14"), movement_date=cls.today - datetime.timedelta(days=week * 7),
            )
        cls.supplier = Partner.objects.create(
            tenant=cls.tenant, name="مورّد التقرير", partner_type="Supplier")
        SupplierProduct.objects.create(
            tenant=cls.tenant, supplier=cls.supplier, product=cls.product,
            supplier_sku="RPT-SKU", min_order_qty=Decimal("50"),
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def test_raised_row_carries_a_visible_note(self):
        data = _run(self.client, "stock-replenishment", self.tenant.TenantID)
        row = next(r for r in data["rows"] if r["sku"] == "MOQ-REPORT-1")
        assert row["moq_note"], row
        assert "50" in row["moq_note"]


class ReplenishmentShortViewTest(APITestCase):
    """#45: يفتح التقرير على أربعة أعمدة (الاسم والحدّ الأدنى الحاكم والمتاح
    والمقترح طلبه)، و«تفاصيل» تكشف الباقي. الملاك عدّ عشرين عموداً على ثلاث
    عشرة صفحة مطبوعة لِـ«قيد الطلب» وحدها — فلا خامس يتسلّل هنا لاحقاً."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="repl_short_view", password="x")
        cls.tenant = create_company("شركة العرض المختصر", cls.user)
        cls.today = datetime.date.today()
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="SHORT-1", name_ar="صنفٌ للعرض المختصر",
            quantity_on_hand=Decimal("5"), min_stock_level=Decimal("20"),
        )
        StockMovement.objects.create(
            tenant=cls.tenant, product=cls.product, movement_type="IN",
            quantity=Decimal("1000"), movement_date=cls.today - datetime.timedelta(days=89),
        )
        for week in range(1, 7):
            StockMovement.objects.create(
                tenant=cls.tenant, product=cls.product, movement_type="OUT",
                quantity=Decimal("14"), movement_date=cls.today - datetime.timedelta(days=week * 7),
            )

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    # ── (1) بلا `details` ⇒ أربعة أعمدة بالضبط ──
    def test_default_has_exactly_four_columns(self):
        data = _run(self.client, "stock-replenishment", self.tenant.TenantID)
        keys = {c["key"] for c in data["columns"]}
        assert len(data["columns"]) == 4, data["columns"]
        assert keys == {"name", "effective_min", "available", "order_qty"}, keys

    # ── (2) مع `details` ⇒ كل الأعمدة المعلَنة في الـspec نفسها ──
    def test_details_returns_every_declared_column(self):
        from core.reports._framework import REPORTS

        spec = REPORTS["stock-replenishment"]
        data = _run(self.client, "stock-replenishment", self.tenant.TenantID, details="1")
        keys = [c["key"] for c in data["columns"]]
        assert keys == [c.key for c in spec.columns], keys

    # ── (3) إجماليات المختصر على أعمدته وحدها ──
    def test_short_view_totals_cover_only_its_columns(self):
        data = _run(self.client, "stock-replenishment", self.tenant.TenantID)
        assert set(data["totals"].keys()) == {"available", "order_qty"}, data["totals"]

    # ── (4) نفس الصفوف بين الوضعين — عرضٌ أضيق لا رقمٌ مختلف ──
    def test_rows_are_identical_between_short_and_details(self):
        short = _run(self.client, "stock-replenishment", self.tenant.TenantID)
        full = _run(self.client, "stock-replenishment", self.tenant.TenantID, details="1")
        assert short["rows"] == full["rows"]

    # ── (5) التنقيب يعمل في الوضعين ──
    def test_drill_works_in_both_modes(self):
        item_row = _run(self.client, "stock-replenishment", self.tenant.TenantID, details="1")["rows"][0]
        group_key = item_row["group_key"]
        for details in ("", "1"):
            res = self.client.get(
                "/api/reports/stock-replenishment/drill/",
                {"group_key": group_key, "details": details},
                HTTP_X_TENANT_ID=str(self.tenant.TenantID),
            )
            assert res.status_code == 200, res.content[:400]
            assert res.json()["rows"], res.json()

    # ── (6) حارسٌ ضد التسرّب: تقريرٌ آخر بلا `columns_for` لا يتأثر ──
    def test_other_report_columns_are_unaffected(self):
        data = _run(self.client, "low-stock", self.tenant.TenantID, details="1")
        keys = [c["key"] for c in data["columns"]]
        assert keys == [
            "sku", "name", "status", "quantity", "min_stock_level",
            "min_source", "shortage", "group_available", "newest_alternative", "urgency",
        ], keys
