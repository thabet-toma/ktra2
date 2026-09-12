"""عقدُ شكل لوحة المنصّة (التذكرة 211-S): الرقمُ الكبير، الدونات، أشرطةُ
المستهدفات، والشريطُ السفليّ العائم.

نفسُ نمط `test_employee_profile_frontend_contract.py` — ما لا يحرسه `tsc` ولا
`npm test`: أنّ كلَّ رقمٍ في الشريط العلويّ مشتقٌّ من مفتاحٍ حقيقيٍّ في حمولة
`get_platform_dashboard_summary`، لا رقمٍ مخترَع ولا ماليٍّ، وأنّ المكوّنات
مركَّبةٌ فعلاً لا مستوردةً فقط.
"""
import inspect
from pathlib import Path

from django.test import TestCase

from platform_ops import services


class DashboardShellContractTest(TestCase):
    def setUp(self):
        repo_root = Path(__file__).resolve().parents[2]
        self.hero_strip_source = (
            repo_root / "frontend_v2" / "components" / "platform" / "DashboardHeroStrip.tsx"
        ).read_text(encoding="utf-8")
        self.bar_width_source = (
            repo_root / "frontend_v2" / "utils" / "barWidth.ts"
        ).read_text(encoding="utf-8")
        self.target_bars_source = (
            repo_root / "frontend_v2" / "components" / "platform" / "TeamTargetBars.tsx"
        ).read_text(encoding="utf-8")
        self.dashboard_source = (
            repo_root / "frontend_v2" / "components" / "platform" / "PlatformOpsDashboard.tsx"
        ).read_text(encoding="utf-8")
        self.summary_source = inspect.getsource(services.get_platform_dashboard_summary)

    def test_hero_strip_numbers_come_from_real_summary_keys(self):
        for key in ("active_work_orders_count", "overdue_work_orders_count"):
            self.assertIn(
                f'"{key}"', self.summary_source,
                f"مفتاحُ الحمولة «{key}» غيرُ موجودٍ فعلاً في get_platform_dashboard_summary.",
            )
            self.assertIn(
                f"employee.{key}", self.hero_strip_source,
                f"الشريطُ العلويُّ لا يقرأ «{key}» من كائن الموظّف نفسِه.",
            )

    def test_hero_strip_presence_donut_uses_the_existing_count_present_util(self):
        self.assertIn("presentCount", self.hero_strip_source)
        self.assertIn("totalCount", self.hero_strip_source)
        self.assertIn("countPresent(roomOccupants)", self.dashboard_source)
        self.assertIn("presentCount={countPresent(roomOccupants)}", self.dashboard_source)
        self.assertIn("totalCount={roomOccupants.length}", self.dashboard_source)

    def test_hero_strip_donut_guards_against_division_by_zero(self):
        self.assertRegex(
            self.hero_strip_source,
            r"totalCount\s*>\s*0\s*\?[\s\S]{0,80}presentCount\s*/\s*totalCount",
            "الدونات تقسم البسط على المقام بلا حراسةٍ من مقامٍ صفريّ.",
        )

    def test_no_component_invents_a_financial_or_sales_figure(self):
        forbidden = ("مبيعات", "ريال", "إيراد")
        for source, filename in (
            (self.hero_strip_source, "DashboardHeroStrip.tsx"),
            (self.target_bars_source, "TeamTargetBars.tsx"),
            (self.dashboard_source, "PlatformOpsDashboard.tsx"),
        ):
            for word in forbidden:
                self.assertNotIn(
                    word, source,
                    f"«{word}» ظهرت في {filename} — لوحةُ عمليات كترا لا تحمل رقمَ مبيعاتٍ إطلاقاً.",
                )

    def test_team_target_bars_treats_zero_capacity_target_as_unset_not_zero_capacity(self):
        self.assertRegex(
            self.target_bars_source,
            r"capacity_target\s*>\s*0\s*\?[\s\S]{0,120}:\s*null",
            "شريطُ المستهدفات يجب أن يعامل capacity_target === 0 كـ«لم تُضبط» لا يقسم عليه.",
        )
        self.assertIn("لم تُضبط", self.target_bars_source)

    def test_team_target_bars_clips_the_bar_width_but_keeps_the_overflow_number(self):
        """القصُّ في السُلَّم المشترك، والفائضُ باقٍ في الرقم داخل المكوّن.

        كان السُلَّمُ يسكن `TeamTargetBars.tsx` نفسَه حتى لزم شريطٌ ثانٍ في
        «خطّتي»، فانتقل إلى `utils/barWidth.ts` أداةً واحدة. والحارسُ يتبع القصَّ
        إلى حيث هو بدل أن يبقى يفتّش عنه في ملفٍّ لم يعد يملكه — تأكيدٌ يحرس
        موضعاً قديماً يسقط عند إعادة تنظيمٍ سليمةٍ ويمرّ عند عطبٍ حقيقيّ.
        """
        self.assertIn("Math.min(100", self.bar_width_source)
        self.assertIn(
            "barWidthClass", self.target_bars_source,
            "شريطُ المستهدفات لا يستعمل سُلَّمَ العرض المشترك — نسخةٌ ثانيةٌ تتباعد بصمت.",
        )
        self.assertRegex(
            self.target_bars_source,
            r"isOverloaded[\s\S]{0,800}formatNumber\(percent",
            "الرقمُ يجب أن يبقى يعرض الفائض فوق ١٠٠٪ لا أن يُقصّ معه.",
        )

    def test_team_target_bars_caps_visible_rows_with_a_show_all_toggle(self):
        self.assertIn("ROWS_COLLAPSED", self.target_bars_source)
        self.assertIn("showAll", self.target_bars_source)

    def test_the_hero_strip_and_target_bars_are_mounted_not_just_imported(self):
        self.assertRegex(self.dashboard_source, r"<DashboardHeroStrip\b")
        self.assertRegex(self.dashboard_source, r"<TeamTargetBars\b")

    def test_the_bottom_nav_is_hidden_on_wide_screens_and_mounted(self):
        self.assertRegex(
            self.dashboard_source,
            r"<nav[^>]*\bmd:hidden\b",
            "الشريطُ السفليّ يجب أن يكون مخفيّاً بـ`md:hidden` في العرض الواسع.",
        )
        self.assertIn("fixed bottom-0", self.dashboard_source)

    def test_the_bottom_nav_has_exactly_the_four_required_tabs_with_aria_labels(self):
        for label in ("نظرة عامّة", "أوامر العمل", "مساحة العمل", "الاجتماعات"):
            self.assertIn(f'aria-label="{label}"', self.dashboard_source)

    def test_the_wide_tab_row_is_hidden_on_narrow_screens_instead_of_duplicating(self):
        self.assertIn("hidden md:inline-flex", self.dashboard_source)

    def test_the_hero_numbers_are_not_drawn_before_the_payload_arrives(self):
        """صفرٌ بخطٍّ عريضٍ أثناء التحميل خبرٌ كاذب.

        البطاقاتُ تقرأ `data?.employees || []`، فحمولةٌ لم تصل بعد — أو فشل
        تحميلُها — تُعطي مجموعاً صفراً يُقرأ «لا أمرَ عملٍ نشطاً ولا متأخّراً».
        وهذه لوحةُ تدخّلٍ: الغيابُ أصدقُ من رقمٍ لم يُحسَب.
        """
        self.assertRegex(
            self.dashboard_source,
            r"\{data && \([\s\S]{0,400}<DashboardHeroStrip",
            "الشريطُ العلويُّ يُرسَم قبل وصول الحمولة فيعرض أصفاراً مخترَعة.",
        )
        self.assertNotRegex(
            self.dashboard_source,
            r"<DashboardHeroStrip[\s\S]{0,200}employees=\{data\?\.",
            "البطاقةُ ما زالت تقرأ حمولةً قد لا تكون وصلت (`data?.`).",
        )
