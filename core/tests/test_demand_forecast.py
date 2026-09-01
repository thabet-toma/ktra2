"""#32: السلسلة الأسبوعية وتنبّؤ هولت. #34: مقابضها لكل شركة.

يُثبت هنا: أن `holt_forecast` تعطي بالضبط ما يعطيه القلم والورقة على حالة
المالك (ثمانية أسابيع صفر ثم أربعة وأربعة)، وأن أسبوع الصفر جزءٌ من السلسلة
لا فجوة، وأن الأسبوع الجاري غير المكتمل لا يدخلها أبداً، وأن أمر الإدارة
مُعاوَد الاستدعاء بلا أثر ومعزولٌ بين الشركات وثابت الكلفة بعدد المنتجات.
وأن α/β وعمق السلسلة مقابض تُقرأ لكل شركةٍ من `logistics.PurchaseSettings` —
لا ثوابت وحدة (#34).
"""
import datetime
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext

from core.replenishment import (
    holt_forecast,
    last_completed_week_start,
    weekly_demand_series,
)
from inventory.models import Product, ProductDemandForecast, StockMovement
from logistics.models import PurchaseSettings
from tenants.services import create_company

ZERO = Decimal("0")


class HoltForecastPureFunctionTest(TestCase):
    """بلا استعلام — تُختبر بالورقة والقلم كما `suggest_levels`."""

    def test_owner_case_eight_zero_weeks_then_two_of_four(self):
        """ثمانية أسابيع صفر ثم أربعة وأربعة (ط1/ط2 على الخريطة).

        بالورقة والقلم — α=0.25، β=0.15، التهيئة L=متوسط أوّل أسبوعين=0، T=0:
        الأسابيع 1..8 كلّها صفر تُبقي L=0 وT=0 (صفرٌ إلى صفر بلا تغيّر).
        الأسبوع 9 (=4): L = 0.25×4 + 0.75×(0+0) = 1
                        T = 0.15×(1−0) + 0.85×0 = 0.15
        الأسبوع 10 (=4): التوقّع السابق = 1+0.15 = 1.15
                         L = 0.25×4 + 0.75×1.15 = 1 + 0.8625 = 1.8625
                         T = 0.15×(1.8625−1) + 0.85×0.15 = 0.129375+0.1275 = 0.256875
        أخطاء التوقّع الثمانية (من الأسبوع الثالث فصاعداً): ستّة أصفار، ثم
        |4−0|=4، ثم |4−1.15|=2.85 ⇒ MAD = 6.85 ÷ 8 = 0.85625
        """
        weekly = [ZERO] * 8 + [Decimal("4"), Decimal("4")]
        flat_average = sum(weekly) / Decimal(len(weekly))
        assert flat_average == Decimal("0.8"), flat_average

        result = holt_forecast(weekly)
        assert result["weeks_observed"] == 10
        assert result["level"] == Decimal("1.8625"), result["level"]
        assert result["trend"] == Decimal("0.256875"), result["trend"]
        assert result["mad"] == Decimal("0.85625"), result["mad"]

        # الحجّة نفسها في القرار ط2: هولت يعترف بالتغيّر بدل أن يدفنه في المتوسط.
        assert result["level"] > flat_average
        assert result["trend"] > ZERO

    def test_zero_weeks_are_not_dropped_from_the_series(self):
        """نفس آخر أسبوعين، بعدد أسابيع صفرٍ مختلف قبلهما ⇒ ناتجان مختلفان —
        فإسقاط أسبوع الصفر من السلسلة يغيّر الناتج، وهذا بيت القصيد في التذكرة."""
        with_zeros = holt_forecast([ZERO] * 8 + [Decimal("4"), Decimal("4")])
        without_zeros = holt_forecast([Decimal("4"), Decimal("4")])
        assert with_zeros["level"] != without_zeros["level"]
        assert with_zeros["trend"] != without_zeros["trend"]

    def test_thin_history_under_six_weeks_has_no_trend(self):
        """صنفٌ عمره ثلاثة أسابيع: المستوى = متوسّط آخر أسبوعين، والاتجاه صفر."""
        result = holt_forecast([Decimal("2"), Decimal("6"), Decimal("10")])
        assert result["weeks_observed"] == 3
        assert result["level"] == Decimal("8")   # متوسط 6 و10 — آخر أسبوعين
        assert result["trend"] == ZERO

    def test_single_week_history(self):
        result = holt_forecast([Decimal("5")])
        assert result == {
            "level": Decimal("5"), "trend": ZERO, "weeks_observed": 1, "mad": None,
        }

    def test_no_history_returns_zeroes(self):
        result = holt_forecast([])
        assert result == {"level": ZERO, "trend": ZERO, "weeks_observed": 0, "mad": None}

    def test_mad_absent_under_four_error_samples(self):
        # خمسة أسابيع ⇒ ثلاثة أخطاء توقّع فقط (من الأسبوع الثالث) — أقلّ من أربعة.
        weekly = [Decimal("1")] * 5
        result = holt_forecast(weekly)
        assert result["mad"] is None

    def test_alpha_knob_changes_the_stored_level(self):
        """#34: α مقبضٌ فعلي — نفس السلسلة بقيمتين مختلفتين تعطي رقمين مختلفين.

        α أعلى يعني وزناً أكبر للأسبوع الأخير (4) ووزناً أقلّ لتقدير السلسلة
        الراكدة قبله (صفر)، فمستوى α=0.6 يجب أن يفوق مستوى α=0.1 على نفس البيانات.
        """
        weekly = [ZERO] * 8 + [Decimal("4"), Decimal("4")]
        low_alpha = holt_forecast(weekly, alpha=Decimal("0.10"), beta=Decimal("0.15"))
        high_alpha = holt_forecast(weekly, alpha=Decimal("0.60"), beta=Decimal("0.15"))
        assert low_alpha["level"] != high_alpha["level"]
        assert high_alpha["level"] > low_alpha["level"], (high_alpha, low_alpha)

    def test_beta_knob_changes_the_stored_trend(self):
        weekly = [ZERO] * 8 + [Decimal("4"), Decimal("4")]
        low_beta = holt_forecast(weekly, alpha=Decimal("0.25"), beta=Decimal("0.05"))
        high_beta = holt_forecast(weekly, alpha=Decimal("0.25"), beta=Decimal("0.80"))
        assert low_beta["trend"] != high_beta["trend"]


class WeeklySeriesBuilderTest(TestCase):
    """`weekly_demand_series` — من حركة المخزون الخام إلى شبكة أسابيع كاملة."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="wds_owner", password="x")
        cls.tenant = create_company("شركة السلسلة الأسبوعية", cls.owner)

    def _move(self, tenant, product, mtype, qty, movement_date):
        StockMovement.objects.create(
            tenant=tenant, product=product, movement_type=mtype,
            quantity=Decimal(str(qty)), movement_date=movement_date,
        )

    def test_gap_week_is_filled_with_zero_not_dropped(self):
        today = datetime.date.today()
        last_week = last_completed_week_start(today)
        oldest_week = last_week - datetime.timedelta(weeks=9)
        product = Product.objects.create(
            tenant=self.tenant, sku="WS-1", name_ar="سلسلة١", quantity_on_hand=Decimal("0"),
        )
        self._move(self.tenant, product, "OUT", 4, oldest_week)
        self._move(self.tenant, product, "OUT", 4, last_week)

        series, computed_last_week = weekly_demand_series(self.tenant.TenantID, today=today)
        assert computed_last_week == last_week
        weekly = series[product.id]
        assert len(weekly) == 10, weekly
        assert weekly[0] == Decimal("4")
        assert weekly[-1] == Decimal("4")
        assert all(w == ZERO for w in weekly[1:-1]), weekly

    def test_current_incomplete_week_never_enters_the_series(self):
        today = datetime.date.today()
        last_week = last_completed_week_start(today)
        product = Product.objects.create(
            tenant=self.tenant, sku="WS-2", name_ar="سلسلة٢", quantity_on_hand=Decimal("0"),
        )
        self._move(self.tenant, product, "OUT", 3, last_week)
        self._move(self.tenant, product, "OUT", 999, today)   # الأسبوع الجاري

        series, _ = weekly_demand_series(self.tenant.TenantID, today=today)
        weekly = series[product.id]
        assert Decimal("999") not in weekly
        assert weekly[-1] == Decimal("3")

    def test_return_in_is_subtracted_from_its_week(self):
        today = datetime.date.today()
        last_week = last_completed_week_start(today)
        product = Product.objects.create(
            tenant=self.tenant, sku="WS-3", name_ar="سلسلة٣", quantity_on_hand=Decimal("0"),
        )
        self._move(self.tenant, product, "OUT", 5, last_week)
        self._move(self.tenant, product, "RETURN_IN", 2, last_week)

        series, _ = weekly_demand_series(self.tenant.TenantID, today=today)
        assert series[product.id][-1] == Decimal("3")

    def test_other_tenant_product_never_enters_the_series(self):
        stranger = User.objects.create_user(username="wds_stranger", password="x")
        other = create_company("شركة سلسلة أخرى", stranger)
        today = datetime.date.today()
        last_week = last_completed_week_start(today)

        mine = Product.objects.create(
            tenant=self.tenant, sku="WS-4", name_ar="خاصّي", quantity_on_hand=Decimal("0"),
        )
        theirs = Product.objects.create(
            tenant=other, sku="WS-X", name_ar="غريب", quantity_on_hand=Decimal("0"),
        )
        self._move(self.tenant, mine, "OUT", 2, last_week)
        self._move(other, theirs, "OUT", 9, last_week)

        series, _ = weekly_demand_series(self.tenant.TenantID, today=today)
        assert mine.id in series
        assert theirs.id not in series


class RecomputeDemandForecastCommandTest(TestCase):
    """أمر الإدارة: يكتب/يحدّث `ProductDemandForecast` — معاوَد الاستدعاء بلا أثر."""

    @classmethod
    def setUpTestData(cls):
        cls.owner = User.objects.create_user(username="cmd_owner", password="x")
        cls.tenant = create_company("شركة أمر التنبّؤ", cls.owner)
        cls.stranger = User.objects.create_user(username="cmd_stranger", password="x")
        cls.other = create_company("شركة أمر تنبّؤ أخرى", cls.stranger)

    def _move(self, tenant, product, mtype, qty, movement_date):
        StockMovement.objects.create(
            tenant=tenant, product=product, movement_type=mtype,
            quantity=Decimal(str(qty)), movement_date=movement_date,
        )

    def test_full_run_matches_the_hand_derived_owner_case(self):
        today = datetime.date.today()
        last_week = last_completed_week_start(today)
        oldest_week = last_week - datetime.timedelta(weeks=9)
        product = Product.objects.create(
            tenant=self.tenant, sku="CMD-OWNER", name_ar="حالة المالك",
            quantity_on_hand=Decimal("0"),
        )
        # الاستلام يثبّت بداية سجلّ المنتج — ثمانية أسابيع تليه بلا بيعٍ واحد،
        # ثم أسبوعان بأربعةٍ في كلٍّ منهما (نفس أرقام الاختبار الصافي أعلاه).
        self._move(self.tenant, product, "IN", 20, oldest_week)
        self._move(self.tenant, product, "OUT", 4, last_week - datetime.timedelta(weeks=1))
        self._move(self.tenant, product, "OUT", 4, last_week)

        call_command("recompute_demand_forecast", tenant=self.tenant.TenantID)

        row = ProductDemandForecast.objects.get(tenant=self.tenant, product=product)
        assert row.weeks_observed == 10
        assert row.level == Decimal("1.8625")
        assert row.trend == Decimal("0.256875")
        assert row.mad == Decimal("0.85625")
        assert row.last_week_start == last_week

    def test_sale_in_the_running_week_does_not_move_stored_numbers(self):
        today = datetime.date.today()
        last_week = last_completed_week_start(today)
        product = Product.objects.create(
            tenant=self.tenant, sku="CMD-RUN", name_ar="أسبوع جارٍ",
            quantity_on_hand=Decimal("0"),
        )
        self._move(self.tenant, product, "OUT", 2, last_week - datetime.timedelta(weeks=1))
        self._move(self.tenant, product, "OUT", 2, last_week)

        call_command("recompute_demand_forecast", tenant=self.tenant.TenantID)
        before = ProductDemandForecast.objects.get(tenant=self.tenant, product=product)
        before_level, before_trend = before.level, before.trend

        self._move(self.tenant, product, "OUT", 500, today)   # بيعٌ ضخم بالأسبوع الجاري
        call_command("recompute_demand_forecast", tenant=self.tenant.TenantID)

        after = ProductDemandForecast.objects.get(tenant=self.tenant, product=product)
        assert after.level == before_level, (after.level, before_level)
        assert after.trend == before_trend, (after.trend, before_trend)

    def test_rerun_without_new_movements_is_idempotent(self):
        today = datetime.date.today()
        last_week = last_completed_week_start(today)
        product = Product.objects.create(
            tenant=self.tenant, sku="CMD-IDEMPOTENT", name_ar="ثبات",
            quantity_on_hand=Decimal("0"),
        )
        self._move(self.tenant, product, "OUT", 3, last_week - datetime.timedelta(weeks=2))
        self._move(self.tenant, product, "OUT", 5, last_week)

        call_command("recompute_demand_forecast", tenant=self.tenant.TenantID)
        first = ProductDemandForecast.objects.get(tenant=self.tenant, product=product)
        first_values = (first.level, first.trend, first.weeks_observed, first.mad, first.last_week_start)

        call_command("recompute_demand_forecast", tenant=self.tenant.TenantID)
        second = ProductDemandForecast.objects.get(tenant=self.tenant, product=product)
        second_values = (
            second.level, second.trend, second.weeks_observed, second.mad, second.last_week_start,
        )
        assert ProductDemandForecast.objects.filter(tenant=self.tenant, product=product).count() == 1
        assert first_values == second_values, (first_values, second_values)

    def test_other_company_product_never_gets_a_row_when_scoped(self):
        today = datetime.date.today()
        last_week = last_completed_week_start(today)
        foreign = Product.objects.create(
            tenant=self.other, sku="CMD-X", name_ar="منتج شركة أخرى",
            quantity_on_hand=Decimal("0"),
        )
        self._move(self.other, foreign, "OUT", 9, last_week)

        call_command("recompute_demand_forecast", tenant=self.tenant.TenantID)

        assert not ProductDemandForecast.objects.filter(tenant=self.other).exists()

    def test_query_count_does_not_grow_with_product_count(self):
        today = datetime.date.today()
        last_week = last_completed_week_start(today)

        def _seed(tenant, count):
            for i in range(count):
                product = Product.objects.create(
                    tenant=tenant, sku=f"Q-{tenant.TenantID}-{i}", name_ar=f"صنف{i}",
                    quantity_on_hand=Decimal("0"),
                )
                self._move(tenant, product, "OUT", 4, last_week)

        small_owner = User.objects.create_user(username="q_small_owner", password="x")
        small_tenant = create_company("شركة صغيرة لعدّ الاستعلامات", small_owner)
        _seed(small_tenant, 10)

        large_owner = User.objects.create_user(username="q_large_owner", password="x")
        large_tenant = create_company("شركة كبيرة لعدّ الاستعلامات", large_owner)
        _seed(large_tenant, 100)

        with CaptureQueriesContext(connection) as small_ctx:
            call_command("recompute_demand_forecast", tenant=small_tenant.TenantID)
        with CaptureQueriesContext(connection) as large_ctx:
            call_command("recompute_demand_forecast", tenant=large_tenant.TenantID)

        assert ProductDemandForecast.objects.filter(tenant=small_tenant).count() == 10
        assert ProductDemandForecast.objects.filter(tenant=large_tenant).count() == 100
        assert len(large_ctx) == len(small_ctx), (len(small_ctx), len(large_ctx))

    # ── #34: الأمر يقرأ α/β وعمق السلسلة **لكل شركة** — لا افتراضاً واحداً دائماً ──

    def test_command_honours_per_tenant_alpha(self):
        """نفس سلسلة المالك بالحرف (ثمانية أصفار ثم 4،4) على شركتين بـα مختلف:
        α الأعلى يفوق α الأدنى في المستوى المخزَّن — إثباتٌ أن الأمر قرأ إعداد
        كلٍّ منهما لا ثابت `HOLT_ALPHA` وحده."""
        today = datetime.date.today()
        last_week = last_completed_week_start(today)
        oldest_week = last_week - datetime.timedelta(weeks=9)

        def _seed_owner_case(tenant, sku):
            product = Product.objects.create(
                tenant=tenant, sku=sku, name_ar=sku, quantity_on_hand=Decimal("0"),
            )
            self._move(tenant, product, "IN", 20, oldest_week)
            self._move(tenant, product, "OUT", 4, last_week - datetime.timedelta(weeks=1))
            self._move(tenant, product, "OUT", 4, last_week)
            return product

        low_owner = User.objects.create_user(username="alpha_low_owner", password="x")
        low_tenant = create_company("شركة ألفا منخفضة", low_owner)
        PurchaseSettings.objects.create(tenant=low_tenant, forecast_alpha=Decimal("0.10"))
        low_product = _seed_owner_case(low_tenant, "ALPHA-LOW")

        high_owner = User.objects.create_user(username="alpha_high_owner", password="x")
        high_tenant = create_company("شركة ألفا مرتفعة", high_owner)
        PurchaseSettings.objects.create(tenant=high_tenant, forecast_alpha=Decimal("0.90"))
        high_product = _seed_owner_case(high_tenant, "ALPHA-HIGH")

        call_command("recompute_demand_forecast", tenant=low_tenant.TenantID)
        call_command("recompute_demand_forecast", tenant=high_tenant.TenantID)

        low_row = ProductDemandForecast.objects.get(tenant=low_tenant, product=low_product)
        high_row = ProductDemandForecast.objects.get(tenant=high_tenant, product=high_product)
        assert low_row.level != high_row.level
        assert high_row.level > low_row.level, (high_row.level, low_row.level)

    def test_command_honours_per_tenant_history_weeks(self):
        """حركةٌ منذ 19 أسبوعاً: تدخل نافذة 26 أسبوعاً ولا تدخل نافذة 6 أسابيع —
        فسلسلة الشركة ذات النافذة الطويلة تُرصَد أطول، وهذا وحده يثبت أن الأمر
        قرأ `forecast_history_weeks` من إعدادات كلٍّ منهما."""
        today = datetime.date.today()
        last_week = last_completed_week_start(today)
        old_week = last_week - datetime.timedelta(weeks=19)

        def _seed(tenant, sku):
            product = Product.objects.create(
                tenant=tenant, sku=sku, name_ar=sku, quantity_on_hand=Decimal("0"),
            )
            self._move(tenant, product, "OUT", 6, old_week)
            self._move(tenant, product, "OUT", 3, last_week - datetime.timedelta(weeks=1))
            self._move(tenant, product, "OUT", 3, last_week)
            return product

        short_owner = User.objects.create_user(username="hist_short_owner", password="x")
        short_tenant = create_company("شركة سجلٍّ قصير", short_owner)
        PurchaseSettings.objects.create(tenant=short_tenant, forecast_history_weeks=6)
        short_product = _seed(short_tenant, "HIST-SHORT")

        long_owner = User.objects.create_user(username="hist_long_owner", password="x")
        long_tenant = create_company("شركة سجلٍّ طويل", long_owner)
        PurchaseSettings.objects.create(tenant=long_tenant, forecast_history_weeks=26)
        long_product = _seed(long_tenant, "HIST-LONG")

        call_command("recompute_demand_forecast", tenant=short_tenant.TenantID)
        call_command("recompute_demand_forecast", tenant=long_tenant.TenantID)

        short_row = ProductDemandForecast.objects.get(tenant=short_tenant, product=short_product)
        long_row = ProductDemandForecast.objects.get(tenant=long_tenant, product=long_product)
        assert short_row.weeks_observed == 6, short_row.weeks_observed
        assert long_row.weeks_observed == 20, long_row.weeks_observed
        assert short_row.weeks_observed < long_row.weeks_observed
