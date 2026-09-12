"""T-PLANPRICE: سعر الخطة — الافتراضي، التجاوز، والنقطة العامة بلا مصادقة.

يحرس هذا الملف تسريبين مختلفين: (١) أن تُعلَن للعميل حدودٌ أو وحداتٌ لا يفرضها
الخادم فعلاً — لأن `public_plan_rows` تُبنى من نسخة يدوية بدل القراءة من
`PLAN_DEFAULTS`/`MODULES`. (٢) أن يُسرَّب رقمٌ يخصّ شركةً بعينها على نقطةٍ
عامّةٍ يقرؤها زائرٌ مجهول.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from core.models import PlanPricing
from core.modules import MODULES
from core.plans import (
    DATA_ENTRY_ADDON,
    LIMITS,
    PLAN_CURRENCY,
    PLAN_DEFAULTS,
    PLAN_LABELS,
    PLAN_PRICING_DEFAULTS,
    PUBLIC_PLAN_ORDER,
    invalidate_plan_pricing_cache,
    plan_price,
    public_plan_rows,
)
from tenants.models import Tenant


class PlanPriceDefaultsTest(APITestCase):
    def setUp(self):
        invalidate_plan_pricing_cache()

    def test_every_displayed_plan_has_a_default_price(self):
        for plan in PUBLIC_PLAN_ORDER:
            self.assertEqual(plan_price(plan), PLAN_PRICING_DEFAULTS[plan])

    def test_trial_has_no_price_and_is_absent_from_public_rows(self):
        self.assertIsNone(plan_price("Trial"))
        keys = {row["key"] for row in public_plan_rows()}
        self.assertNotIn("Trial", keys)

    def test_override_beats_default_and_deleting_it_restores_the_default(self):
        PlanPricing.objects.create(plan_key="Basic", monthly_price=Decimal("77.50"))
        invalidate_plan_pricing_cache()
        self.assertEqual(plan_price("Basic"), Decimal("77.50"))

        PlanPricing.objects.filter(plan_key="Basic").delete()
        invalidate_plan_pricing_cache()
        self.assertEqual(plan_price("Basic"), PLAN_PRICING_DEFAULTS["Basic"])

    def test_public_rows_limits_match_plan_defaults_key_by_key(self):
        rows = {row["key"]: row for row in public_plan_rows()}
        for plan in PUBLIC_PLAN_ORDER:
            row_limits = {entry["key"]: entry["value"] for entry in rows[plan]["limits"]}
            for key in LIMITS:
                self.assertEqual(row_limits[key], PLAN_DEFAULTS[plan].get(key))

    def test_public_rows_modules_match_modules_registry(self):
        rows = {row["key"]: row for row in public_plan_rows()}
        for plan in PUBLIC_PLAN_ORDER:
            row_modules = {entry["key"] for entry in rows[plan]["modules"]}
            expected = {
                key for key, definition in MODULES.items() if plan in definition["plans"]
            }
            self.assertEqual(row_modules, expected)


class PlanTablesStayInStepTest(APITestCase):
    """خطّةٌ تُسعَّر ولا تُوصَل بالجداول الأخرى **تختفي من الصفحة بصمت**.

    أربعةُ جداولَ تصف الخطّةَ نفسَها (`PLAN_PRICING_DEFAULTS` للسعر،
    و`PLAN_LABELS` للاسم، و`PUBLIC_PLAN_ORDER` للعرض، و`PLAN_DEFAULTS`
    للحدود). إضافةُ خطّةٍ إلى واحدٍ ونسيانُ الباقي لا ترفع خطأً ولا تُسقط
    اختباراً: الصفحةُ تعرض خطّتين بدل ثلاث، أو خطّةً باسمها الإنجليزيّ، أو
    خطّةً بلا حدودٍ تظهر «بلا حدّ» في كلّ سطر — وهي أسوأُ الثلاث.
    """

    def test_every_priced_plan_is_named_ordered_and_has_limits(self):
        for plan in PLAN_PRICING_DEFAULTS:
            self.assertIn(plan, PLAN_LABELS, "خطّةٌ مسعَّرةٌ بلا اسمٍ عربيّ.")
            self.assertIn(plan, PUBLIC_PLAN_ORDER, "خطّةٌ مسعَّرةٌ لا تُعرَض.")
            self.assertIn(plan, PLAN_DEFAULTS, "خطّةٌ مسعَّرةٌ بلا حدود.")

    def test_every_displayed_plan_is_priced(self):
        for plan in PUBLIC_PLAN_ORDER:
            self.assertIn(plan, PLAN_PRICING_DEFAULTS, "خطّةٌ معروضةٌ بلا سعر.")

    def test_the_hidden_trial_is_never_displayed(self):
        self.assertIn("Trial", PLAN_DEFAULTS, "شرطُ الاختبار: التجريبيّةُ قائمة.")
        self.assertNotIn("Trial", PUBLIC_PLAN_ORDER)
        self.assertNotIn("Trial", PLAN_PRICING_DEFAULTS)


class PublicPricingEndpointTest(APITestCase):
    def setUp(self):
        invalidate_plan_pricing_cache()

    def test_reachable_with_no_authentication_at_all(self):
        response = self.client.get("/api/pricing/plans/")
        self.assertEqual(response.status_code, 200, response.content)

    def test_a_stale_token_does_not_turn_the_public_page_into_a_401(self):
        """توكنٌ قديمٌ في `localStorage` يُرسَل مع كلّ طلبٍ من الواجهة.

        `AllowAny` وحدَها لا تكفي: المصادقةُ تسبق الصلاحيّة، ولائحةُ DRF
        الافتراضيّة تبدأ بـ`DeviceTokenAuthentication` فتردّ 401 قبل أن تُسأل
        الصلاحيّةُ أصلاً. والنتيجةُ زائرٌ جاء يقرأ السعرَ فقيل له «انتهت
        الجلسة» — ولا يفتح الصفحةَ إلاّ من مسح تخزينَ متصفّحه.
        """
        self.client.credentials(HTTP_AUTHORIZATION="Token 0000deadbeef0000")
        response = self.client.get("/api/pricing/plans/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("plans", response.json())

    def test_response_carries_no_company_specific_key(self):
        response = self.client.get("/api/pricing/plans/")
        body = response.json()
        self.assertNotIn("tenant", body)
        self.assertNotIn("tenant_id", body)
        for row in body["plans"]:
            self.assertNotIn("tenant", row)
            self.assertNotIn("tenant_id", row)

    def test_the_whole_page_costs_one_query_not_one_per_plan(self):
        """قراءةُ التجاوزات **مرّةً واحدة** لا مرّةً لكلّ خطّة.

        موازنةُ عدّ استعلامِ طلبٍ بطلبٍ آخرَ لعدد الخطط نفسِه **لا تستطيع
        السقوط**: تنفيذٌ يستعلم لكلّ خطّةٍ يعطي العددَ نفسَه في الطلبين. فالعدُّ
        هنا مطلقٌ لا نسبيّ.

        وليست هذه رفاهيةَ أداء: النقطةُ **عامّةٌ بلا مصادقة**، وكاشُ Redis
        مضبوطٌ بـ`IGNORE_EXCEPTIONS` فانقطاعُه يُسقط القراءةَ إلى القاعدة
        صامتاً — فيصير كلُّ زائرٍ ثلاثةَ استعلاماتٍ بدل واحد. واختباراتُ هذا
        المستودع تعمل على `DummyCache`، أي على المسار غير المكشوف بالضبط.
        """
        for plan in PUBLIC_PLAN_ORDER:
            PlanPricing.objects.create(plan_key=plan, monthly_price=Decimal("1"))
        invalidate_plan_pricing_cache()

        with self.assertNumQueries(1):
            response = self.client.get("/api/pricing/plans/")
        self.assertEqual(response.status_code, 200, response.content)

    def test_the_payload_actually_carries_the_effective_price(self):
        """السعرُ نفسُه في الحمولة — لا حدودَه وحدَها.

        كلُّ ما سبق يتحقّق من الحدود والوحدات؛ ومفتاحُ `price` لو سقط أو أُعيدت
        تسميتُه لبقيت الاختباراتُ خضراءَ بينما تعرض صفحةُ الأسعار العامّة
        **بطاقاتٍ بلا سعر**. والتجاوزُ يجب أن يصل الحمولةَ لا أن يقف عند
        `plan_price` وحدَها.
        """
        PlanPricing.objects.create(plan_key="Pro", monthly_price=Decimal("111"))
        invalidate_plan_pricing_cache()

        body = self.client.get("/api/pricing/plans/").json()
        prices = {row["key"]: row["price"] for row in body["plans"]}
        self.assertEqual(Decimal(str(prices["Pro"])), Decimal("111"))
        self.assertEqual(
            Decimal(str(prices["Basic"])), PLAN_PRICING_DEFAULTS["Basic"],
        )
        self.assertEqual(body["currency"], PLAN_CURRENCY)

        addon = body["data_entry_addon"]
        self.assertEqual(Decimal(str(addon["price"])), DATA_ENTRY_ADDON["price"])
        self.assertEqual(
            addon["included_operations"], DATA_ENTRY_ADDON["included_operations"],
        )
        # سعرُ العمليّة الزائدة لم يحسمه المالك — يصل `null` لتُخفيه الواجهة،
        # ولا يصل صفراً يُقرأ «مجّانيّة».
        self.assertIsNone(addon["extra_operation_price"])


class PlatformPlanPricingApiTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username="pricing-root", email="pricing-root@example.com", password="x",
        )
        cls.member = User.objects.create_user(username="pricing-member", password="x")
        Tenant.objects.create(
            CompanyName="شركة الأسعار", SubscriptionPlan="Basic", Status="Active",
        )

    def setUp(self):
        invalidate_plan_pricing_cache()

    def url(self):
        return "/api/platform/plan-pricing/"

    def test_non_super_admin_is_denied(self):
        self.client.force_authenticate(self.member)
        self.assertEqual(self.client.get(self.url()).status_code, 403)

    def test_super_admin_reads_defaults(self):
        self.client.force_authenticate(self.superuser)
        response = self.client.get(self.url())
        self.assertEqual(response.status_code, 200, response.content)
        rows = {row["plan_key"]: row for row in response.data["results"]}
        self.assertEqual(set(rows), set(PLAN_PRICING_DEFAULTS))
        self.assertFalse(rows["Basic"]["has_override"])
        self.assertEqual(rows["Basic"]["effective_price"], PLAN_PRICING_DEFAULTS["Basic"])

    def test_super_admin_sets_then_restores_by_equaling_the_default(self):
        self.client.force_authenticate(self.superuser)

        setting = self.client.put(
            self.url(),
            {"plan_key": "Basic", "monthly_price": "75"},
            format="json",
        )
        self.assertEqual(setting.status_code, 200, setting.content)
        self.assertEqual(plan_price("Basic"), Decimal("75"))

        restoring = self.client.put(
            self.url(),
            {"plan_key": "Basic", "monthly_price": str(PLAN_PRICING_DEFAULTS["Basic"])},
            format="json",
        )
        self.assertEqual(restoring.status_code, 200, restoring.content)
        self.assertFalse(PlanPricing.objects.filter(plan_key="Basic").exists())
        self.assertEqual(plan_price("Basic"), PLAN_PRICING_DEFAULTS["Basic"])

    def test_negative_price_is_rejected(self):
        self.client.force_authenticate(self.superuser)
        response = self.client.put(
            self.url(),
            {"plan_key": "Basic", "monthly_price": "-1"},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
