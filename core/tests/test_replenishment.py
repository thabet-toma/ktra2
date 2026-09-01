"""T-REORDER: محرّك التجديد — المعادلات، وشحّ البيانات، وقرار «النوع».

يُثبت هنا ما لا تُثبته قراءة الكود: أن الرقم المقترَح هو بعينه ما تعطيه المعادلة
بالورقة والقلم، وأن المنتج الذي لا نعرفه بعد لا يُقترَح له صفرٌ صامت، وأن نفاد
موديلٍ قديمٍ يقف بجانبه موديلٌ جديد لا يُقرأ «اطلب».
"""
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.test import TestCase, override_settings
from rest_framework.test import APITestCase

from inventory.models import Product, ProductDemandForecast, StockMovement, SupplierProduct
from partners.models import Partner
from core.replenishment import (
    MIN_HISTORY_DAYS,
    REASON_NO_FORECAST,
    REASON_NO_SALES,
    REASON_SHORT_HISTORY,
    URGENCY_DEAD,
    URGENCY_DEFERRED,
    URGENCY_URGENT,
    _moq_map,
    replenishment_params,
    replenishment_rows,
    suggest_levels,
)
from tenants.models import UserCompanyMembership
from tenants.services import create_company

TODAY = datetime.date(2026, 6, 30)


class ReplenishmentEngineTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="repl_owner", password="x")
        cls.tenant = create_company("شركة التجديد", cls.owner)

    # ── أدوات ──
    def _product(self, sku, *, qty="0", group="", **kw):
        return Product.objects.create(
            tenant=self.tenant, sku=sku, name_ar=kw.pop("name", sku),
            variant_group=group, quantity_on_hand=Decimal(qty), **kw,
        )

    def _move(self, product, mtype, qty, days_ago):
        StockMovement.objects.create(
            tenant=self.tenant, product=product, movement_type=mtype,
            quantity=Decimal(str(qty)),
            movement_date=TODAY - datetime.timedelta(days=days_ago),
        )

    def _steady_seller(self, sku, *, qty="50", group=""):
        """90 وحدة صافية على 90 يوماً ⇒ ADU = 1، وذروة أسبوعية 14 ⇒ الذروة = 2."""
        p = self._product(sku, qty=qty, group=group)
        self._move(p, "IN", 1000, 89)          # أوّل حركة: يحدّد أيام السجل = 90
        for week in range(1, 7):               # ستّ أسابيع × 14 = 84
            self._move(p, "OUT", 14, week * 7)
        self._move(p, "OUT", 6, 49)            # الأسبوع السابع: 6 ⇒ المجموع 90
        return p

    def _rows(self, **kw):
        return replenishment_rows(self.tenant.TenantID, today=TODAY, **kw)

    def _row_for(self, product, **kw):
        return next(r for r in self._rows(**kw) if r["product_id"] == product.id)

    # ── (1) المعادلة كما تُحسب بالورقة ──
    def test_regular_seller_matches_hand_computed_levels(self):
        p = self._steady_seller("R-1")
        row = self._row_for(p)
        assert row["adu"] == Decimal("1"), row["adu"]
        assert row["lead_days"] == Decimal("14")      # لا طلبيات ⇒ الافتراضي
        # الأمان = (2 × 21) − (1 × 14) = 28 ؛ الأدنى = 14 + 28 = 42
        assert row["safety_stock"] == Decimal("28"), row["safety_stock"]
        assert row["suggested_min"] == 42, row["suggested_min"]
        # الأقصى = 42 + (1 × 30) = 72
        assert row["suggested_max"] == 72, row["suggested_max"]
        assert row["reason"] == ""

    def test_suggest_levels_is_pure_arithmetic(self):
        out = suggest_levels(
            adu=Decimal("1"), adu_peak=Decimal("2"),
            lead_days=Decimal("14"), lead_max_days=Decimal("21"), review_days=30,
        )
        assert out == {"safety_stock": Decimal("28"), "suggested_min": 42, "suggested_max": 72}

    # ── (2) سجلٌّ أقصر من الحدّ ⇒ لا اقتراح، وسببٌ مكتوب ──
    def test_short_history_yields_no_suggestion_with_a_reason(self):
        p = self._product("R-2", qty="10")
        self._move(p, "IN", 30, 5)
        self._move(p, "OUT", 10, 3)
        row = self._row_for(p)
        assert row["history_days"] < MIN_HISTORY_DAYS
        assert row["reason"] == REASON_SHORT_HISTORY
        assert row["suggested_min"] == 0
        assert row["adu"] == Decimal("0")

    # ── (3) رصيدٌ بلا حركةٍ في النافذة ⇒ راكد، لا «اطلب» ──
    def test_dead_stock_is_flagged_not_ordered(self):
        p = self._product("R-3", qty="20")
        self._move(p, "IN", 20, 200)
        row = self._row_for(p)
        assert row["reason"] == REASON_NO_SALES
        assert row["urgency"] == URGENCY_DEAD
        assert row["order_qty"] == Decimal("0")

    # ── (4) النوع مغطّى بموديلٍ أحدث ⇒ مؤجَّل + تسميةُ البديل ──
    def test_group_covered_by_newer_model_defers_the_order(self):
        old = self._steady_seller("R-4-OLD", qty="0", group="205/65/16")
        new = self._steady_seller("R-4-NEW", qty="400", group="205/65/16")
        row = self._row_for(old)
        assert row["status"] == "out_of_stock"
        assert row["alternatives"] == 1
        assert row["newest_alternative"] == new.name_ar
        assert row["urgency"] == URGENCY_DEFERRED, (
            row["urgency"], row["group_available"], row["group_effective_min"])

    # ── (5) النوع كلّه نفد ⇒ عاجل ──
    def test_whole_group_out_of_stock_is_urgent(self):
        old = self._steady_seller("R-5-OLD", qty="0", group="195/65/15")
        self._steady_seller("R-5-NEW", qty="0", group="195/65/15")
        row = self._row_for(old)
        assert row["urgency"] == URGENCY_URGENT
        assert row["alternatives"] == 0
        assert row["order_qty"] > Decimal("0")

    # ── (6) مرتجع البيع يخفض المعدّل ──
    def test_sales_return_lowers_the_daily_rate(self):
        p = self._steady_seller("R-6")
        self._move(p, "RETURN_IN", 6, 49)      # يلغي صرف الأسبوع السابع
        row = self._row_for(p)
        assert row["adu"] == Decimal("84") / Decimal("90"), row["adu"]
        # الأدنى يبقى 42: الذروة الأسبوعية لم تتغيّر (14) فمخزون الأمان يمتصّ
        # الفرق — والأثر يظهر في الأقصى الذي يمتدّ بمعدّل الصرف: 42 + 0.933×30 = 70.
        assert row["suggested_max"] == 70, row["suggested_max"]

    # ── (7) عدّ الاستعلامات ثابت مهما بلغ عدد المنتجات ──
    def test_query_count_does_not_grow_with_catalog_size(self):
        for i in range(20):
            self._steady_seller(f"R-7-{i}", group=f"G{i % 4}")
        with CaptureQueriesContext(connection) as small:
            replenishment_rows(self.tenant.TenantID, today=TODAY)
        for i in range(20, 60):
            self._steady_seller(f"R-7-{i}", group=f"G{i % 4}")
        with CaptureQueriesContext(connection) as large:
            rows = replenishment_rows(self.tenant.TenantID, today=TODAY)
        assert len(rows) >= 60
        assert len(large) == len(small), (len(small), len(large))

    # ── مستوى النوع: صفٌّ واحد لكل نوع ──
    def test_group_level_collapses_to_one_row_per_type(self):
        self._steady_seller("R-8-A", qty="0", group="215/60/17")
        self._steady_seller("R-8-B", qty="0", group="215/60/17")
        rows = self._rows(level="group")
        target = next(r for r in rows if r["group_key"] == "215/60/17")
        assert target["products_count"] == 2
        assert target["out_of_stock_count"] == 2
        # طلب النوع = ضعف طلب الفرد ⇒ ADU = 2
        assert target["adu"] == Decimal("2")
        assert target["urgency"] == URGENCY_URGENT
        # أرقام النوع مجاميعُ أفراده — فمجموع التفصيل يساوي رقم الصفّ
        items = [r for r in self._rows() if r["group_key"] == "215/60/17"]
        assert target["suggested_min"] == sum(r["suggested_min"] for r in items) == 84
        assert target["order_qty"] == sum((r["order_qty"] for r in items), Decimal("0"))


class AutoReorderModeTest(TestCase):
    """#33: المسار التلقائي — من المستوى/الاتجاه المخزَّنين إلى حدٍّ وكمية.

    كلّ حالة هنا مذكورةٌ بنصّها في معايير قبول التذكرة (ط1..ط10 على الخريطة).
    الإعدادات ثابتة على مهلة 14 يوماً ومراجعة 14 يوماً ⇒ أسابيع التغطية W=4 —
    رقمٌ يجعل الجذر التربيعي في مخزون الأمان صحيحاً (`sqrt(4)=2`) فتبقى
    الأرقام قابلة للتحقّق بالورقة والقلم كبقية اختبارات هذا الملف.
    """

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="auto_owner", password="x")
        cls.tenant = create_company("شركة المسار التلقائي", cls.owner)
        from logistics.models import PurchaseSettings

        PurchaseSettings.objects.create(
            tenant=cls.tenant, default_lead_time_days=14, review_period_days=14,
        )

    def _product(self, sku, *, qty="0", mode=Product.REORDER_MODE_AUTO):
        return Product.objects.create(
            tenant=self.tenant, sku=sku, name_ar=sku,
            quantity_on_hand=Decimal(qty), reorder_mode=mode,
        )

    def _forecast(self, product, *, level, trend, mad=None, weeks_observed=10):
        return ProductDemandForecast.objects.create(
            tenant=self.tenant, product=product,
            level=Decimal(str(level)), trend=Decimal(str(trend)),
            mad=None if mad is None else Decimal(str(mad)),
            weeks_observed=weeks_observed, last_week_start=TODAY,
        )

    def _row(self, product):
        rows = replenishment_rows(self.tenant.TenantID, today=TODAY)
        return next(r for r in rows if r["product_id"] == product.id)

    # ── الصيغة بالورقة والقلم: level=10 trend=2 mad=1 W=4 ──
    def test_auto_formula_matches_hand_computed_numbers(self):
        p = self._product("A-1")
        self._forecast(p, level=10, trend=2, mad=1)
        row = self._row(p)
        # الاتجاه غير مسقوف (2 < 10/3): need = 10×4 + 2×4×5/2 = 40+20 = 60
        # الأمان = 1.28×(1.25×1)×√4 = 3.2
        assert row["safety_stock"] == Decimal("3.2"), row["safety_stock"]
        assert row["suggested_min"] == 24, row["suggested_min"]      # 10×2+3.2⌈⌉
        assert row["suggested_max"] == 64, row["suggested_max"]      # 60+3.2⌈⌉
        assert row["order_qty"] == Decimal("64"), row["order_qty"]   # متاحٌ صفر
        assert row["reason"] == ""
        assert row["reorder_mode"] == "auto"
        assert row["coverage_weeks"] == Decimal("4")

    # ── (a) صنفٌ صاعد: الاقتراح أكبر ممّا يعطيه المتوسط المسطّح ──
    def test_rising_trend_suggests_more_than_flat_average(self):
        p = self._product("A-2")
        self._forecast(p, level=10, trend=2, mad=1)
        row = self._row(p)
        flat_need = row["weekly_sale"] * row["coverage_weeks"]           # 10×4=40
        actual_need = row["suggested_max"] - row["safety_stock"]          # 64−3.2=60.8
        assert actual_need > flat_need, (actual_need, flat_need)
        assert row["trend_label"] == "طالع"

    # ── (b) طلبية شراء مؤكَّدة تغطّي الاحتياج ⇒ لا تظهر في التقرير (تقرير) ──
    # يُثبَت في core/tests/test_reports_replenishment.py (طبقة التقرير هي من
    # تخفي؛ المحرّك يبقيها — ط10).
    def test_confirmed_purchase_order_is_subtracted_from_the_engine_row(self):
        from logistics.models import Currency, PurchaseOrder, PurchaseOrderLine
        from partners.models import Partner

        p = self._product("A-3")
        self._forecast(p, level=10, trend=0, mad=0)   # need=40, safety=0
        currency = Currency.objects.create(Code="ILA", Name="شيكل")
        supplier = Partner.objects.create(
            tenant=self.tenant, name="مورّد أ٣", partner_type="Supplier")
        order = PurchaseOrder.objects.create(
            tenant=self.tenant, order_number="PO-A3", supplier=supplier,
            order_date=TODAY, currency=currency, status=PurchaseOrder.STATUS_CONFIRMED,
        )
        PurchaseOrderLine.objects.create(
            tenant=self.tenant, order=order, product=p,
            quantity=Decimal("40"), unit_price=Decimal("1"), line_total=Decimal("40"),
        )
        row = self._row(p)
        # «هالنقطة أهم شي بالتقرير كله»: قيد الطلب يُطرح فيصفّر الاقتراح.
        assert row["on_order"] == Decimal("40")
        assert row["order_qty"] == Decimal("0"), row["order_qty"]

    # ── (c) لم يبع ولا قطعة: راكدٌ لا عاجل، وكميته صفر ──
    def test_never_sold_is_flagged_dead_with_zero_quantity(self):
        p = self._product("A-4", qty="50")
        StockMovement.objects.create(
            tenant=self.tenant, product=p, movement_type="IN",
            quantity=Decimal("50"), movement_date=TODAY - datetime.timedelta(days=100),
        )
        self._forecast(p, level=0, trend=0, mad=0)
        row = self._row(p)
        assert row["reason"] == REASON_NO_SALES
        assert row["urgency"] == URGENCY_DEAD
        assert row["order_qty"] == Decimal("0")

    # ── (d) بيعةٌ شاذّة لا تضاعف الحدّ — سقف الاتجاه الصاعد يمسك ──
    def test_trend_cap_holds_against_a_freak_sale(self):
        p = self._product("A-5")
        # مستوىً يقبل قسمةً نظيفة على 3، واتجاهٌ متطرّف (100) يتجاوز السقف بكثير.
        self._forecast(p, level=9, trend=100, mad=0)
        row = self._row(p)
        # مسقوفٌ عند 9/3=3: need = 9×4 + 3×4×5/2 = 36+30 = 66 لا 1036 (بلا سقف).
        assert row["suggested_max"] == 66, row["suggested_max"]

    # ── (e) مبيعاتٌ متراجعة: الكمية المقترحة تنزل، والاتجاه بلا سقفٍ نازلاً ──
    def test_declining_trend_lowers_the_suggestion(self):
        flat = self._product("A-6-FLAT")
        self._forecast(flat, level=10, trend=0, mad=0)
        declining = self._product("A-6-DOWN")
        self._forecast(declining, level=10, trend=-1, mad=0)

        flat_row = self._row(flat)
        down_row = self._row(declining)
        assert down_row["trend_label"] == "نازل"
        assert down_row["suggested_max"] < flat_row["suggested_max"]
        assert down_row["order_qty"] < flat_row["order_qty"]

    # ── (g) بلا تنبّؤٍ محفوظ: لا انهيار ولا صفرٌ صامت — سببٌ مكتوب ──
    def test_auto_without_a_stored_forecast_returns_a_reason_not_a_crash(self):
        p = self._product("A-7")
        row = self._row(p)
        assert row["reason"] == REASON_NO_FORECAST
        assert row["suggested_min"] == 0
        assert row["order_qty"] == Decimal("0")

    # ── فقدان MAD (أقل من أربعة أخطاء) لا يمنع رقماً — قاعدة الذروة تحلّ محلّه ──
    def test_missing_mad_falls_back_to_peak_based_safety(self):
        p = self._product("A-8", qty="0")
        # سجلٌّ يمنح adu/adu_peak حقيقيين للمسار الاحتياطي.
        for week in range(1, 7):
            StockMovement.objects.create(
                tenant=self.tenant, product=p, movement_type="OUT",
                quantity=Decimal("14"), movement_date=TODAY - datetime.timedelta(days=week * 7))
        StockMovement.objects.create(
            tenant=self.tenant, product=p, movement_type="IN",
            quantity=Decimal("1000"), movement_date=TODAY - datetime.timedelta(days=89))
        self._forecast(p, level=10, trend=0, mad=None)
        row = self._row(p)
        assert row["reason"] == ""
        assert row["safety_stock"] > Decimal("0"), row["safety_stock"]

    # ── (f) يدوي: لا تغيّره أرقام التنبّؤ المحفوظة إطلاقاً ──
    def test_manual_mode_ignores_a_stored_forecast_entirely(self):
        p = self._steady_seller_for_manual("A-9")
        self._forecast(p, level=999, trend=999, mad=1)   # لو تسرّب هذا لظهر فوراً
        row = self._row(p)
        assert row["reorder_mode"] == "manual"
        # نفس معادلة المسار اليدوي بالضبط — الأمان والأدنى مطابقان لاختبار
        # `ReplenishmentEngineTest.test_regular_seller_matches_hand_computed_levels`
        # حرفياً؛ الأقصى يختلف رقمياً هنا فقط لأن هذه الشركة تراجع كل 14 يوماً
        # لا 30 (`PurchaseSettings` في `setUpTestData`)، لا لأي تسرّبٍ من التنبّؤ:
        # 42 + 1×14 = 56.
        assert row["safety_stock"] == Decimal("28"), row["safety_stock"]
        assert row["suggested_min"] == 42, row["suggested_min"]
        assert row["suggested_max"] == 56, row["suggested_max"]

    def _steady_seller_for_manual(self, sku):
        p = Product.objects.create(
            tenant=self.tenant, sku=sku, name_ar=sku, quantity_on_hand=Decimal("0"),
        )
        StockMovement.objects.create(
            tenant=self.tenant, product=p, movement_type="IN",
            quantity=Decimal("1000"), movement_date=TODAY - datetime.timedelta(days=89))
        for week in range(1, 7):
            StockMovement.objects.create(
                tenant=self.tenant, product=p, movement_type="OUT",
                quantity=Decimal("14"), movement_date=TODAY - datetime.timedelta(days=week * 7))
        StockMovement.objects.create(
            tenant=self.tenant, product=p, movement_type="OUT",
            quantity=Decimal("6"), movement_date=TODAY - datetime.timedelta(days=49))
        return p

    # ── عدّ الاستعلامات: التنبّؤات تُقرأ دفعةً واحدة، لا لكل صفّ ──
    def test_query_count_does_not_grow_with_auto_catalog_size(self):
        for i in range(10):
            p = self._product(f"A-Q-{i}")
            self._forecast(p, level=5, trend=1, mad=1)
        with CaptureQueriesContext(connection) as small:
            replenishment_rows(self.tenant.TenantID, today=TODAY)
        for i in range(10, 40):
            p = self._product(f"A-Q-{i}")
            self._forecast(p, level=5, trend=1, mad=1)
        with CaptureQueriesContext(connection) as large:
            rows = replenishment_rows(self.tenant.TenantID, today=TODAY)
        assert len(rows) >= 40
        assert len(large) == len(small), (len(small), len(large))


class ReplenishmentParamsForecastKnobsTest(TestCase):
    """#34: خمسة مقابض جديدة تُقرأ من `logistics.PurchaseSettings` — أو
    الافتراضات حين لا صفّ إعداداتٍ للشركة، ومعزولةٌ بين الشركات."""

    def test_tenant_without_settings_row_uses_defaults(self):
        owner = User.objects.create_user(username="knobs_default_owner", password="x")
        tenant = create_company("شركة بلا إعدادات تجديد", owner)
        params = replenishment_params(tenant.TenantID)
        assert params.forecast_alpha == Decimal("0.25")
        assert params.forecast_beta == Decimal("0.15")
        assert params.forecast_history_weeks == 26
        assert params.forecast_trend_cap_ratio == Decimal("0.33")
        assert params.forecast_safety_factor == Decimal("1.28")

    def test_tenant_settings_do_not_leak_to_another_tenant(self):
        from logistics.models import PurchaseSettings

        tuned_owner = User.objects.create_user(username="knobs_tuned_owner", password="x")
        tuned = create_company("شركة مقابض مضبوطة", tuned_owner)
        PurchaseSettings.objects.create(
            tenant=tuned, forecast_alpha=Decimal("0.80"), forecast_beta=Decimal("0.70"),
            forecast_history_weeks=12, forecast_trend_cap_ratio=Decimal("0.50"),
            forecast_safety_factor=Decimal("2.00"),
        )
        bystander_owner = User.objects.create_user(username="knobs_bystander_owner", password="x")
        bystander = create_company("شركة أخرى بلا إعدادات مقابض", bystander_owner)

        tuned_params = replenishment_params(tuned.TenantID)
        bystander_params = replenishment_params(bystander.TenantID)
        assert tuned_params.forecast_alpha == Decimal("0.80")
        assert tuned_params.forecast_history_weeks == 12
        # الشركة الأخرى بلا صفّ إعداداتٍ خاصّ بها لم تتأثر بإعدادات الأولى.
        assert bystander_params.forecast_alpha == Decimal("0.25")
        assert bystander_params.forecast_history_weeks == 26


class TrendCapAndSafetyFactorKnobsTest(TestCase):
    """#34: تغيير `forecast_trend_cap_ratio`/`forecast_safety_factor` يغيّر نتيجة
    المسار التلقائي فعلاً — نفس مستوى/اتجاه/MAD على شركتين بمقبضين مختلفين
    يعطيان رقمين مختلفين، مثبَتَين بالورقة والقلم."""

    def _tenant_with(self, *, name, **settings_kwargs):
        from logistics.models import PurchaseSettings

        owner = User.objects.create_user(username=f"knob_calc_{name}", password="x")
        tenant = create_company(f"شركة حساب مقابض {name}", owner)
        PurchaseSettings.objects.create(
            tenant=tenant, default_lead_time_days=14, review_period_days=14,
            **settings_kwargs,
        )
        return tenant

    def test_custom_ratio_and_factor_change_the_auto_path_numbers(self):
        default_tenant = self._tenant_with(name="default")
        custom_tenant = self._tenant_with(
            name="custom",
            forecast_trend_cap_ratio=Decimal("0.10"), forecast_safety_factor=Decimal("2.56"),
        )

        def _row(tenant):
            p = Product.objects.create(
                tenant=tenant, sku="KNOB-CALC", name_ar="صنف حساب المقابض",
                quantity_on_hand=Decimal("0"), reorder_mode=Product.REORDER_MODE_AUTO,
            )
            ProductDemandForecast.objects.create(
                tenant=tenant, product=p, level=Decimal("10"), trend=Decimal("2"),
                mad=Decimal("1"), weeks_observed=10, last_week_start=TODAY,
            )
            rows = replenishment_rows(tenant.TenantID, today=TODAY)
            return next(r for r in rows if r["product_id"] == p.id)

        default_row = _row(default_tenant)
        custom_row = _row(custom_tenant)

        # الافتراضي (سقف 0.33 وعامل أمان 1.28) — مطابقٌ حرفياً لاختبار المحرّك
        # `AutoReorderModeTest.test_auto_formula_matches_hand_computed_numbers`.
        assert default_row["safety_stock"] == Decimal("3.2"), default_row["safety_stock"]
        assert default_row["suggested_max"] == 64, default_row["suggested_max"]

        # المخصَّص: سقفٌ أضيق (0.10×10=1.0 < الاتجاه=2) يُمسك الاتجاه عند 1.0 لا
        # 2، وعامل أمانٍ أعلى (2.56):
        #   need = 10×4 + 1.0×4×5/2 = 40+10 = 50 ؛ safety = 2.56×(1.25×1)×√4 = 6.4
        #   suggested_max = ⌈50+6.4⌉ = 57
        assert custom_row["safety_stock"] == Decimal("6.4"), custom_row["safety_stock"]
        assert custom_row["suggested_max"] == 57, custom_row["suggested_max"]

        assert custom_row["safety_stock"] != default_row["safety_stock"]
        assert custom_row["suggested_max"] != default_row["suggested_max"]


class SupplierMinOrderQuantityTest(TestCase):
    """#34/ط9: `inventory.SupplierProduct.min_order_qty` يرفع كميةً مقترحة
    دونه ويُؤشِّر على السطر — ولا يخترع طلباً لصنفٍ كان اقتراحه صفراً."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="moq_owner", password="x")
        cls.tenant = create_company("شركة حدّ المورّد الأدنى", cls.owner)

    def _product(self, sku, *, qty="50"):
        return Product.objects.create(
            tenant=self.tenant, sku=sku, name_ar=sku, quantity_on_hand=Decimal(qty),
        )

    def _move(self, product, mtype, qty, days_ago):
        StockMovement.objects.create(
            tenant=self.tenant, product=product, movement_type=mtype,
            quantity=Decimal(str(qty)), movement_date=TODAY - datetime.timedelta(days=days_ago),
        )

    def _steady_seller(self, sku, *, qty="50"):
        """نفس بناء `ReplenishmentEngineTest._steady_seller`: أدنى=42 وأقصى=72،
        فمتاحٌ ب50 يعطي طلباً مقترَحاً = 22 قبل أي حدّ مورّد."""
        p = self._product(sku, qty=qty)
        self._move(p, "IN", 1000, 89)
        for week in range(1, 7):
            self._move(p, "OUT", 14, week * 7)
        self._move(p, "OUT", 6, 49)
        return p

    def _supplier(self, name):
        return Partner.objects.create(tenant=self.tenant, name=name, partner_type="Supplier")

    def _row_for(self, product, **kw):
        rows = replenishment_rows(self.tenant.TenantID, today=TODAY, **kw)
        return next(r for r in rows if r["product_id"] == product.id)

    def test_quantity_below_moq_is_raised_and_flagged(self):
        p = self._steady_seller("MOQ-1")
        supplier = self._supplier("مورّد الحدّ")
        SupplierProduct.objects.create(
            tenant=self.tenant, supplier=supplier, product=p,
            supplier_sku="SKU-1", min_order_qty=Decimal("50"),
        )
        row = self._row_for(p)
        assert row["order_qty"] == Decimal("50"), row["order_qty"]   # 22 مرفوعةً إلى 50
        assert row["moq_raised"] is True
        assert row["min_order_qty"] == Decimal("50")

    def test_product_without_a_linked_supplier_is_unaffected(self):
        p = self._steady_seller("MOQ-2")
        row = self._row_for(p)
        assert row["order_qty"] == Decimal("22"), row["order_qty"]
        assert row["moq_raised"] is False
        assert row["min_order_qty"] is None

    def test_quantity_already_above_moq_is_not_touched(self):
        p = self._steady_seller("MOQ-3")
        supplier = self._supplier("مورّد بحدٍّ صغير")
        SupplierProduct.objects.create(
            tenant=self.tenant, supplier=supplier, product=p,
            supplier_sku="SKU-3", min_order_qty=Decimal("5"),
        )
        row = self._row_for(p)
        assert row["order_qty"] == Decimal("22")
        assert row["moq_raised"] is False

    def test_zero_suggested_quantity_is_never_raised_to_the_moq(self):
        """مخزونٌ مكتمل (اقتراحه صفر أصلاً) لا يصير طلباً وهمياً لمجرّد أن
        للمورّد حدّاً أدنى — الحدّ يرفع اقتراحاً قائماً لا يخترع طلباً."""
        p = self._steady_seller("MOQ-4", qty="72")   # متاحٌ = الأقصى ⇒ اقتراح صفر
        supplier = self._supplier("مورّد لا يُستدعى")
        SupplierProduct.objects.create(
            tenant=self.tenant, supplier=supplier, product=p,
            supplier_sku="SKU-4", min_order_qty=Decimal("10"),
        )
        row = self._row_for(p)
        assert row["order_qty"] == Decimal("0")
        assert row["moq_raised"] is False

    def test_partner_filter_uses_that_suppliers_minimum_not_the_lowest(self):
        p = self._steady_seller("MOQ-5")
        supplier_a = self._supplier("مورّد أ")
        supplier_b = self._supplier("مورّد ب")
        SupplierProduct.objects.create(
            tenant=self.tenant, supplier=supplier_a, product=p,
            supplier_sku="SKU-5A", min_order_qty=Decimal("30"),
        )
        SupplierProduct.objects.create(
            tenant=self.tenant, supplier=supplier_b, product=p,
            supplier_sku="SKU-5B", min_order_qty=Decimal("100"),
        )

        # بلا فلتر مورّد ⇒ الأقلّ تقييداً بين الاثنين (30).
        unfiltered = self._row_for(p)
        assert unfiltered["min_order_qty"] == Decimal("30")
        assert unfiltered["order_qty"] == Decimal("30")

        # فلتر المورّد «ب» ⇒ حدّه هو (100) لا الأقلّ بين الموردين.
        filtered_b = self._row_for(p, supplier_id=supplier_b.id)
        assert filtered_b["min_order_qty"] == Decimal("100")
        assert filtered_b["order_qty"] == Decimal("100")

        filtered_a = self._row_for(p, supplier_id=supplier_a.id)
        assert filtered_a["min_order_qty"] == Decimal("30")

    def test_moq_lookup_is_a_single_query_for_the_whole_company(self):
        products = [self._steady_seller(f"MOQ-Q-{i}") for i in range(5)]
        for i, p in enumerate(products):
            supplier = self._supplier(f"مورّد {i}")
            SupplierProduct.objects.create(
                tenant=self.tenant, supplier=supplier, product=p,
                supplier_sku=f"SKU-Q-{i}", min_order_qty=Decimal("30"),
            )
        with CaptureQueriesContext(connection) as ctx:
            moq_map = _moq_map(self.tenant.TenantID, [p.id for p in products])
        assert len(moq_map) == 5
        assert len(ctx) == 1, len(ctx)


class ApplyReplenishmentApiTest(APITestCase):
    """نقطة التطبيق: تكتب، فتُحرَس بصلاحية الكتابة وبحدّ الشركة."""

    URL = "/api/inventory/products/apply-replenishment/"

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="apply_owner", password="x")
        cls.tenant = create_company("شركة التطبيق", cls.owner)
        cls.stranger = User.objects.create_user(username="apply_stranger", password="x")
        cls.other = create_company("شركة الغير", cls.stranger)

        cls.seller = Product.objects.create(
            tenant=cls.tenant, sku="AP-1", name_ar="منتج يبيع",
            quantity_on_hand=Decimal("50"),
        )
        today = datetime.date.today()
        StockMovement.objects.create(
            tenant=cls.tenant, product=cls.seller, movement_type="IN",
            quantity=Decimal("1000"),
            movement_date=today - datetime.timedelta(days=89),
        )
        for week in range(1, 7):
            StockMovement.objects.create(
                tenant=cls.tenant, product=cls.seller, movement_type="OUT",
                quantity=Decimal("14"),
                movement_date=today - datetime.timedelta(days=week * 7),
            )
        StockMovement.objects.create(     # الأسبوع السابع ⇒ المجموع 90 على 90 يوماً
            tenant=cls.tenant, product=cls.seller, movement_type="OUT",
            quantity=Decimal("6"), movement_date=today - datetime.timedelta(days=49),
        )
        cls.newborn = Product.objects.create(
            tenant=cls.tenant, sku="AP-2", name_ar="منتج حديث",
            quantity_on_hand=Decimal("5"),
        )
        StockMovement.objects.create(
            tenant=cls.tenant, product=cls.newborn, movement_type="IN",
            quantity=Decimal("5"), movement_date=today - datetime.timedelta(days=3),
        )
        cls.foreign = Product.objects.create(
            tenant=cls.other, sku="AP-X", name_ar="منتج شركة أخرى",
            quantity_on_hand=Decimal("7"), min_stock_level=3,
        )

    def _post(self, ids, tenant=None, user=None):
        self.client.force_authenticate(user=user or self.owner)
        return self.client.post(
            self.URL, {"product_ids": ids}, format="json",
            HTTP_X_TENANT_ID=str((tenant or self.tenant).TenantID),
        )

    def test_applies_the_suggested_pair_and_says_what_it_skipped(self):
        res = self._post([self.seller.id, self.newborn.id])
        assert res.status_code == 200, res.content[:300]
        body = res.json()
        assert body["applied"] == 1
        self.seller.refresh_from_db()
        assert self.seller.min_stock_level == 42
        assert self.seller.max_stock_level == 72
        # المنتج الحديث لا يُكتب عليه صفر — «لا أعرف بعد» ليست «لا تطلب».
        self.newborn.refresh_from_db()
        assert self.newborn.min_stock_level is None
        assert [s["product_id"] for s in body["skipped"]] == [self.newborn.id]
        assert REASON_SHORT_HISTORY in body["skipped"][0]["reason"]

    def test_viewer_role_is_refused(self):
        viewer = User.objects.create_user(username="apply_viewer", password="x")
        UserCompanyMembership.objects.create(
            user=viewer, tenant=self.tenant, role="viewer")
        res = self._post([self.seller.id], user=viewer)
        assert res.status_code == 403, res.status_code

    def test_other_company_product_is_untouched(self):
        res = self._post([self.foreign.id])
        assert res.status_code == 200, res.content[:300]
        assert res.json()["applied"] == 0
        self.foreign.refresh_from_db()
        assert self.foreign.min_stock_level == 3
        assert self.foreign.max_stock_level is None

    def test_empty_selection_is_a_client_error_not_a_silent_success(self):
        res = self._post([])
        assert res.status_code == 400, res.status_code


class BulkSetGroupApiTest(APITestCase):
    """«النوع» بلا مدخلٍ جماعي = حقلٌ يبقى فارغاً أبداً، وبفراغه يسقط التجميع كلّه."""

    URL = "/api/inventory/products/bulk-set-group/"

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="grp_owner", password="x")
        cls.tenant = create_company("شركة النوع", cls.owner)
        cls.stranger = User.objects.create_user(username="grp_stranger", password="x")
        cls.other = create_company("شركة أخرى للنوع", cls.stranger)
        cls.a = Product.objects.create(tenant=cls.tenant, sku="G-1", name_ar="ايفون 14 عادي")
        cls.b = Product.objects.create(tenant=cls.tenant, sku="G-2", name_ar="ايفون 14 برو")
        cls.untouched = Product.objects.create(tenant=cls.tenant, sku="G-3", name_ar="شاحن")
        cls.foreign = Product.objects.create(
            tenant=cls.other, sku="G-X", name_ar="منتج الغير", variant_group="أصلي")

    def _post(self, body, user=None, tenant=None):
        self.client.force_authenticate(user=user or self.owner)
        return self.client.post(
            self.URL, body, format="json",
            HTTP_X_TENANT_ID=str((tenant or self.tenant).TenantID),
        )

    def test_sets_the_type_on_the_selected_items_only(self):
        res = self._post({"product_ids": [self.a.id, self.b.id], "variant_group": "ايفون 14"})
        assert res.status_code == 200, res.content[:300]
        assert res.json()["updated"] == 2
        self.a.refresh_from_db()
        self.b.refresh_from_db()
        self.untouched.refresh_from_db()
        assert self.a.variant_group == self.b.variant_group == "ايفون 14"
        assert self.untouched.variant_group == ""

    def test_absent_field_is_not_touched(self):
        self._post({"product_ids": [self.a.id], "variant_group": "ايفون 14"})
        res = self._post({"product_ids": [self.a.id], "brand": "أبل"})
        assert res.status_code == 200, res.content[:300]
        self.a.refresh_from_db()
        assert self.a.brand == "أبل"
        assert self.a.variant_group == "ايفون 14"   # لم يُمرَّر ⇒ لم يُمَسّ

    def test_body_without_any_field_is_refused(self):
        res = self._post({"product_ids": [self.a.id]})
        assert res.status_code == 400, res.status_code

    def test_viewer_role_is_refused(self):
        viewer = User.objects.create_user(username="grp_viewer", password="x")
        UserCompanyMembership.objects.create(user=viewer, tenant=self.tenant, role="viewer")
        res = self._post({"product_ids": [self.a.id], "variant_group": "س"}, user=viewer)
        assert res.status_code == 403, res.status_code

    def test_other_company_product_is_untouched(self):
        res = self._post({"product_ids": [self.foreign.id], "variant_group": "مسروق"})
        assert res.status_code == 200, res.content[:300]
        assert res.json()["updated"] == 0
        self.foreign.refresh_from_db()
        assert self.foreign.variant_group == "أصلي"

    # ── الدليل الحقيقي: تعيين النوع يُشغِّل البدائل من طرفٍ لطرف ──
    def test_setting_the_type_turns_alternatives_on_end_to_end(self):
        """قبل التعيين لا بديل لأن كل منتجٍ نوعٌ بذاته؛ وبعده يصيران نوعاً واحداً."""
        Product.objects.filter(pk=self.b.pk).update(quantity_on_hand=Decimal("40"))
        before = {r["product_id"]: r for r in replenishment_rows(self.tenant.TenantID)}
        assert before[self.a.id]["alternatives"] == 0
        assert before[self.a.id]["group_key"] == "ايفون 14 عادي"   # الاسم، لا نوع

        self._post({"product_ids": [self.a.id, self.b.id], "variant_group": "ايفون 14"})

        after = {r["product_id"]: r for r in replenishment_rows(self.tenant.TenantID)}
        assert after[self.a.id]["group_key"] == "ايفون 14"
        assert after[self.a.id]["alternatives"] == 1
        assert after[self.a.id]["newest_alternative"] == "ايفون 14 برو"
        assert after[self.a.id]["group_available"] == Decimal("40")


@override_settings(CACHES={"default": {
    "BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "reorder-test",
}})
class ReportCacheInvalidationTest(APITestCase):
    """كاش التقارير 60ث: بلا إبطاله يبدو زرّ «تثبيت الحدود» معطّلاً."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="cache_owner", password="x")
        cls.tenant = create_company("شركة الكاش", cls.owner)
        cls.product = Product.objects.create(
            tenant=cls.tenant, sku="C-1", name_ar="منتج الكاش",
            quantity_on_hand=Decimal("5"),
        )
        today = datetime.date.today()
        StockMovement.objects.create(
            tenant=cls.tenant, product=cls.product, movement_type="IN",
            quantity=Decimal("500"), movement_date=today - datetime.timedelta(days=89),
        )
        for week in range(1, 7):
            StockMovement.objects.create(
                tenant=cls.tenant, product=cls.product, movement_type="OUT",
                quantity=Decimal("14"), movement_date=today - datetime.timedelta(days=week * 7),
            )

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        self.client.force_authenticate(user=self.owner)

    def _run(self):
        res = self.client.get(
            "/api/reports/stock-replenishment/",
            HTTP_X_TENANT_ID=str(self.tenant.TenantID),
        )
        assert res.status_code == 200, res.content[:300]
        return res.json()["rows"][0]

    def test_applying_levels_busts_the_report_cache(self):
        first = self._run()
        assert first["manual_min"] == ""          # لا حدّ يدوي بعد

        res = self.client.post(
            "/api/inventory/products/apply-replenishment/",
            {"product_ids": [self.product.id]}, format="json",
            HTTP_X_TENANT_ID=str(self.tenant.TenantID),
        )
        assert res.status_code == 200, res.content[:300]
        assert res.json()["applied"] == 1

        second = self._run()
        # بلا الإبطال تعود هذه القيمة "" من الكاش لستّين ثانية.
        assert second["manual_min"] == first["suggested_min"], (first, second)

    def test_plain_rerun_still_hits_the_cache(self):
        """الإبطال جرّاحيّ: لا يُلغي الكاش، فإعادة التشغيل بلا كتابة تبقى مخدومة."""
        from django.test.utils import CaptureQueriesContext
        from django.db import connection

        self._run()
        with CaptureQueriesContext(connection) as ctx:
            self._run()
        assert len(ctx) <= 3, len(ctx)   # مصادقة/عضوية فقط — لا استعلامات التقرير
