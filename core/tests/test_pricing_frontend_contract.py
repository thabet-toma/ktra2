"""عقدُ واجهة الأسعار (211-N · 211-O · 211-P): ما لا يحرسه `tsc` ولا `npm test`.

نفسُ نمط `platform_ops/tests/test_dashboard_shell_contract.py` — قراءةُ مصدر
مكوّناتٍ TSX كنصٍّ والتحقّقُ من أنّ كلَّ رقمٍ فيها مشتقٌّ من مفتاحٍ حقيقيٍّ في
`core/public_pricing.py`/`core/plans.py`، لا رقمٍ مكتوبٍ يفترق عن الخادم في أوّل
تعديل سعر، وأنّ المكوّنات **مركَّبةٌ فعلاً** لا مستوردةً فقط.
"""
import re
from pathlib import Path

from django.test import TestCase


class PricingFrontendContractTest(TestCase):
    def setUp(self):
        repo_root = Path(__file__).resolve().parents[2]
        frontend = repo_root / "frontend_v2"
        self.pricing_page_source = (frontend / "components" / "PricingPage.tsx").read_text(encoding="utf-8")
        self.landing_source = (frontend / "components" / "LandingPage.tsx").read_text(encoding="utf-8")
        self.my_plan_card_source = (frontend / "components" / "MyPlanCard.tsx").read_text(encoding="utf-8")
        self.settings_page_source = (frontend / "components" / "SettingsPage.tsx").read_text(encoding="utf-8")
        self.index_source = (frontend / "index.tsx").read_text(encoding="utf-8")
        self.navbar_source = (frontend / "components" / "layout" / "PublicNavbar.tsx").read_text(encoding="utf-8")
        self.rest_api_source = (frontend / "services" / "restApi.ts").read_text(encoding="utf-8")
        self.session_events_source = (frontend / "utils" / "sessionEvents.ts").read_text(encoding="utf-8")
        self.accountant_office_app_source = (
            frontend / "components" / "accountant" / "office" / "AccountantOfficeApp.tsx"
        ).read_text(encoding="utf-8")
        self.app_layout_source = (
            frontend / "components" / "layout" / "AppLayout.tsx"
        ).read_text(encoding="utf-8")
        self.public_pricing_source = (repo_root / "core" / "public_pricing.py").read_text(encoding="utf-8")
        self.plans_source = (repo_root / "core" / "plans.py").read_text(encoding="utf-8")
        self.plan_usage_api_source = (
            repo_root / "core" / "plan_usage_api.py"
        ).read_text(encoding="utf-8")
        self.urls_source = (repo_root / "core" / "urls.py").read_text(encoding="utf-8")
        self.pricing_api_source = (
            frontend / "services" / "pricingApi.ts"
        ).read_text(encoding="utf-8")

    # ── مفاتيح الحمولة موجودةٌ فعلاً في الخادم ──────────────────────────────

    def test_every_payload_key_the_pages_read_exists_in_the_server_source(self):
        for key in (
            "currency", "plans", "data_entry_addon",
        ):
            self.assertIn(
                f'"{key}"', self.public_pricing_source,
                f"مفتاحُ الحمولة «{key}» غيرُ موجودٍ فعلاً في public_pricing_plans.",
            )
        for key in (
            "key", "label", "price", "currency_symbol", "limits", "modules",
            "period_label", "value", "unit",
        ):
            self.assertIn(
                f'"{key}"', self.plans_source,
                f"مفتاحُ الحمولة «{key}» غيرُ موجودٍ فعلاً في public_plan_rows.",
            )
        for key in ("included_operations", "extra_operation_price"):
            self.assertIn(
                f'"{key}"', self.plans_source,
                f"مفتاحُ الإضافة «{key}» غيرُ موجودٍ فعلاً في DATA_ENTRY_ADDON.",
            )

    def test_the_usage_bar_reads_keys_the_server_really_sends(self):
        """مفاتيحُ صفّ الاستهلاك موجودةٌ فعلاً في إسقاط `tenant_usage_rows`.

        `tsc` يفحص الواجهةَ المكتوبةَ في `pricingApi.ts` لا الحمولةَ الحقيقيّة:
        مفتاحٌ يُعاد تسميتُه في الخادم يبقى النوعُ صحيحاً والشريطُ يقرأ
        `undefined` — فيُرسَم صفراً بلا خطأٍ في وحدة التحكّم ولا اختبارٍ أحمر.
        """
        for key in ("limit", "usage", "period_label", "unit", "label", "key"):
            self.assertIn(
                f'"{key}"', self.plans_source,
                f"مفتاحُ «{key}» غيرُ موجودٍ فعلاً في tenant_usage_rows.",
            )
        for key in ("plan", "plan_label", "limits"):
            self.assertIn(
                f'"{key}"', self.plan_usage_api_source,
                f"مفتاحُ «{key}» غيرُ موجودٍ فعلاً في my_plan_usage.",
            )

    def test_the_usage_endpoint_the_client_calls_is_actually_registered(self):
        """المسارُ الذي ينادَى موجودٌ في `core/urls.py` — لا 404 صامتاً في بطاقة."""
        self.assertIn("my-plan/usage/", self.pricing_api_source)
        self.assertIn("api/my-plan/usage/", self.urls_source)

    def test_my_plan_card_reads_the_effective_limit_not_the_public_plan_default(self):
        """البطاقةُ تقرأ حدودَها من نقطة الاستهلاك لا من حمولة الأسعار العامّة.

        العامّةُ تعرف `PLAN_DEFAULTS` وحدَها ولا تعرف الشركة، فشركةٌ رُفع لها
        حدٌّ بـ`TenantLimit` كانت ترى رقمَ الخطّة لا رقمَها ثمّ تُمنَع عند رقمٍ
        غيرِ الذي قرأته. الرجوعُ إلى `planRow.limits` مصدراً أوّلَ هو بعينه ذلك
        العطب.
        """
        self.assertIn("useMyPlanUsage", self.my_plan_card_source)
        self.assertRegex(
            self.my_plan_card_source, r"usage\.limits\.map",
            "البطاقةُ لا تُصيّر صفوفَ الاستهلاك — الشريطُ غيرُ مركَّب.",
        )

    def test_the_usage_bar_width_is_a_tailwind_class_not_an_inline_style(self):
        """لا `style=` في البطاقة، وعرضُ الشريط من السُلَّم المشترك.

        قاعدتان لا يمسكهما `tsc` ولا `npm test` (لا أحدَهما يُصيّر JSX):
        الأنماطُ السطريّةُ ممنوعةٌ في هذا المستودع، **وصنفٌ مبنيٌّ وقتَ التشغيل
        مثل `w-[${n}%]` لا يراه ماسحُ Tailwind** فيبقى الشريطُ بعرض صفرٍ بلا أيّ
        خطأ — عطبٌ بصريٌّ صامتٌ تماماً.
        """
        self.assertNotIn(
            "style={{", self.my_plan_card_source,
            "نمطٌ سطريٌّ في بطاقة «خطّتي» — القاعدة Tailwind وحدَه.",
        )
        self.assertIn("barWidthClass", self.my_plan_card_source)

    # ── لا سعرَ مكتوبٌ حرفيّاً ────────────────────────────────────────────

    def test_no_plan_price_is_hardcoded_in_the_pricing_facing_components(self):
        """السعرُ ٦٠/١٠٠/٢٠٠/٣٠٠ يجب أن يصل عبر الحمولة لا رقماً في الملفّ.

        نمطان يفترق فيهما رقمٌ مكتوبٌ يداً عن Tailwind (`slate-200`، `.../60`):
        (١) نصٌّ JSX عاريٌ بين وسمين `>60<`، أو (٢) الرقمُ ملاصقاً لرمز العملة
        `₪` مباشرةً. كلاهما لا يظهر في استعمالٍ حقيقيٍّ لـTailwind.
        """
        forbidden = ("60", "100", "200", "300")
        bare_text_re = re.compile(r">\s*(?:%s)\s*<" % "|".join(forbidden))
        near_currency_re = re.compile(r"(?:%s)\s*₪|₪\s*(?:%s)" % ("|".join(forbidden), "|".join(forbidden)))
        for source, filename in (
            (self.pricing_page_source, "PricingPage.tsx"),
            (self.landing_source, "LandingPage.tsx"),
            (self.my_plan_card_source, "MyPlanCard.tsx"),
        ):
            self.assertIsNone(
                bare_text_re.search(source),
                f"{filename} يحمل رقم سعرٍ كنصٍّ JSX عاريٍ — يجب أن يصل عبر formatNumber من الحمولة.",
            )
            self.assertIsNone(
                near_currency_re.search(source),
                f"{filename} يحمل رقماً ملاصقاً لرمز العملة ₪ — سعرٌ مكتوبٌ حرفيّاً بدل الحمولة.",
            )

    def test_the_hidden_trial_plan_is_never_mentioned_on_the_public_pricing_page(self):
        self.assertNotIn("Trial", self.pricing_page_source)
        self.assertNotIn("تجريبي", self.pricing_page_source)

    # ── التسجيل والروابط ────────────────────────────────────────────────

    def test_pricing_route_is_registered_standalone_and_linked_from_the_navbar(self):
        self.assertRegex(self.index_source, r'path="/pricing"')
        self.assertRegex(self.navbar_source, r'to:\s*"/pricing"')

    # ── «خطّتي» مركَّبةٌ فعلاً ────────────────────────────────────────────

    def test_my_plan_card_is_mounted_not_just_imported_and_carries_its_anchor_id(self):
        self.assertRegex(self.settings_page_source, r"<MyPlanCard\b")
        self.assertRegex(self.settings_page_source, r'id="my-plan"')

    # ── حارسُ حدّ الخطّة على نمط EngagementRevokedGuard بالضبط ──────────────

    def test_the_plan_limit_guard_lives_in_the_main_shell_not_only_the_office(self):
        """الحارسُ في `AppLayout` — قشرةِ التطبيق الرئيس — لا في مكتب المحاسب وحدَه.

        `enforce_limits` يُرفَع من نقاط إنشاء فواتير البيع والشراء والمنتجات
        والأطراف والمستودعات وأعضاء الشركة، وكلُّها تُصيَّر داخل `AppLayout`.
        وحارسٌ يسكن `AccountantOfficeApp` وحدَه **لا يُصيَّر لهم إطلاقاً**: يبقى
        بلوغُ الحدّ toast يقول «رقِّ الخطة» بلا وجهة لكلّ مستخدمٍ في التطبيق
        الرئيس — وهم جمهورُ الحدّ كلُّه تقريباً، فتسقط 211-P عمليّاً وهي
        «مُنجَزة».
        """
        self.assertRegex(
            self.app_layout_source, r"<PlanLimitReachedGuard[\s/>]",
            "حارسُ حدّ الخطّة غيرُ مركَّبٍ في قشرة التطبيق الرئيس.",
        )
        # وقشرةُ مكتب المحاسب أيضاً — دفترُ العميل يبلغ حدَّه كما تبلغه الشركة.
        self.assertRegex(self.accountant_office_app_source, r"<EngagementRevokedGuard[\s/>]")
        self.assertRegex(self.accountant_office_app_source, r"<PlanLimitReachedGuard[\s/>]")

    def test_every_featured_limit_key_on_the_card_really_exists_on_the_server(self):
        """مفاتيحُ الحدود المختارةُ للبطاقة تُطابق `LIMITS` في `core/plans.py`.

        البطاقةُ تُرشّح حدودَها بقائمةِ مفاتيحَ **مكتوبةٍ في الواجهة**. ومفتاحٌ
        يُعاد تسميتُه في الخادم لا يكسر شيئاً هنا: `filter` يعيد أقلَّ، فتُعرَض
        البطاقةُ ناقصةَ سطرٍ بلا خطأٍ في وحدة التحكّم ولا اختبارٍ أحمر.
        """
        block = re.search(
            r"const FEATURED_LIMIT_KEYS = \[(.*?)\]", self.pricing_page_source, re.S,
        )
        self.assertIsNotNone(block, "لم تعد قائمةُ الحدود المختارة بهذا الاسم.")
        selected = re.findall(r"'([^']+)'", block.group(1))
        self.assertTrue(selected, "قائمةُ الحدود المختارة فارغة.")
        for key in selected:
            self.assertIn(
                'key="%s"' % key, self.plans_source,
                "الحدُّ «%s» مختارٌ في البطاقة ولا وجودَ له في LIMITS." % key,
            )

    def test_handle_response_error_emits_the_plan_limit_event(self):
        self.assertIn("emitPlanLimitReached", self.rest_api_source)
        self.assertIn("PLAN_LIMIT_REACHED_EVENT", self.session_events_source)
