"""حرّاسٌ ساكنةٌ على جدول مقارنة الخطط (#212 212-F).

`npm test` هنا يشغّل `utils/*.test.ts` بـ`node --test`: دوالَّ خالصةً لا تُصيّر
مكوّناً — فدالّةُ التقسيم مُختبَرةٌ هناك فعلاً، وكلُّ ما دونها (الرأسُ اللاصق،
والعمودُ اللاصق، وإبرازُ عمودِ الخطّة، وعلامةُ النفي) لا يراه اختبارٌ ولا `tsc`.
فيُحرَس نصّاً، ومعه الشيءُ الذي **لا تراه الواجهةُ وحدَها**: أنّ كلَّ حدٍّ
يُصدره الخادمُ له قسمٌ يظهر فيه.
"""
from pathlib import Path
import re
from unittest import TestCase

from core.plans import LIMITS

ROOT = Path(__file__).resolve().parents[2]
PAGE = ROOT / "frontend_v2" / "components" / "PricingPage.tsx"
DISPLAY = ROOT / "frontend_v2" / "utils" / "planPricingDisplay.ts"


class EveryServerLimitHasASectionTest(TestCase):
    def test_every_limit_key_prefix_is_named_in_the_section_map(self):
        """حدٌّ يُضاف في `core/plans.py` غداً يجب أن يُسمّى قسمُه هنا.

        وبلا هذا الحارس يسقط في «مزايا أخرى» في آخر الجدول بلا أن يعلم أحد —
        ظاهرٌ نعم، لكن في قسمٍ لا يقصده بائعٌ ولا مشترٍ.
        """
        source = DISPLAY.read_text(encoding="utf-8")
        block = re.search(
            r"LIMIT_SECTION_LABELS_BY_PREFIX[^=]*=\s*\{(.*?)\};", source, re.DOTALL,
        )
        self.assertIsNotNone(block, "خريطةُ الأقسام غير موجودةٍ في `planPricingDisplay.ts`.")
        mapped = set(re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*:", block.group(1), re.MULTILINE))

        prefixes = {key.split(".", 1)[0] for key in LIMITS}
        missing = sorted(prefixes - mapped)
        self.assertFalse(
            missing,
            "بادئاتُ حدودٍ يُصدرها الخادمُ بلا قسمٍ في جدول المقارنة: "
            f"{missing} — ستظهر في «مزايا أخرى» بلا أن يقصدها أحد.",
        )

    def test_the_page_reads_the_sections_not_the_flat_rows(self):
        source = PAGE.read_text(encoding="utf-8")
        self.assertIn("buildPlanComparisonSections", source)
        for flat in ("buildLimitComparisonRows", "buildModuleComparisonRows"):
            self.assertNotIn(
                flat, source,
                f"الصفحةُ ما زالت تبني الجدولَ مسطَّحاً بـ`{flat}` — لا أقسامَ يقرؤها المشتري.",
            )


class TheMatrixKeepsItsAnchorsTest(TestCase):
    """رأسٌ وعمودٌ لاصقان: من نزل في أحدَ عشرَ حدّاً وسبعِ وحداتٍ يجب أن يبقى
    يعرف أيَّ خطّةٍ يقرأ وأيَّ ميزةٍ."""

    def setUp(self):
        self.source = PAGE.read_text(encoding="utf-8")

    def test_the_header_row_is_sticky(self):
        self.assertRegex(
            self.source, r"<thead[^>]*className=\"[^\"]*sticky[^\"]*top-0",
            "رأسُ الجدول غيرُ لاصق — من نزل في الجدول لم يعد يرى أيَّ خطّةٍ يقرأ.",
        )

    def test_the_sticky_header_has_a_scroll_container_with_a_height_cap(self):
        """**شرطُ عملِ اللصق لا زينة**: `overflow-x-auto` يجعل المحورَ الرأسيَّ
        `auto` بحكم المواصفة، فاللصقُ يصير بأعلى الحاوية؛ وحاويةٌ بلا سقفِ
        ارتفاعٍ لا تتمرّر رأسيّاً، فالرأسُ «لاصقٌ» في الكود وجامدٌ في الشاشة.
        """
        self.assertRegex(
            self.source, r"className=\"[^\"]*max-h-\[[^\]]+\][^\"]*overflow-auto",
            "حاويةُ الجدول بلا سقفِ ارتفاعٍ وتمريرٍ رأسيّ — الرأسُ اللاصقُ لا يلصق بشيء.",
        )

    def test_the_first_column_is_sticky_and_opaque(self):
        """`dir=\"rtl\"`: العمودُ الأوّلُ يلصق يميناً. وخلفيّةٌ شفّافةٌ تمرّ من تحتها
        نصوصُ الخلايا عند التمرير الأفقيّ — وهو أوّلُ ما يُفسد جدولاً لاصقاً."""
        cells = re.findall(r"className=\"([^\"]*sticky[^\"]*right-0[^\"]*)\"", self.source)
        self.assertTrue(cells, "العمودُ الأوّلُ غيرُ لاصق — يضيع اسمُ الميزة في الجوّال.")
        transparent = [cell for cell in cells if not re.search(r"\bbg-(?!transparent)", cell)]
        self.assertFalse(
            transparent,
            f"خلايا لاصقةٌ بخلفيّةٍ شفّافة: {transparent} — يمرّ النصُّ من تحتها عند التمرير.",
        )


class TheMatrixReadsUnambiguouslyTest(TestCase):
    def setUp(self):
        self.source = PAGE.read_text(encoding="utf-8")

    def test_the_unavailable_cell_is_a_cross_not_a_dash(self):
        """نصُّ المالك: «يكون **إكس** أو العدد». والشرطةُ تُقرأ «لا معلومة»."""
        self.assertIn(
            "✕", self.source,
            "الخليّةُ غيرُ المتاحةِ ليست «إكس» — والشرطةُ تُقرأ «لا معلومة» لا «غير متاح».",
        )
        self.assertNotRegex(
            self.source, r">\s*—\s*<",
            "ما زالت شرطةٌ مرسومةً في خليّة — وهي التي طلب المالكُ استبدالَها.",
        )

    def test_the_recommended_column_is_highlighted_inside_the_table_too(self):
        """الإبرازُ في البطاقة وحدَها يترك الجدولَ — وهو مكانُ القرار — بلا دليل."""
        table_start = self.source.index("<table")
        occurrences = self.source[table_start:].count("HIGHLIGHTED_PLAN_KEY")
        self.assertGreaterEqual(
            occurrences, 2,
            "عمودُ الخطّة المُوصى بها غيرُ مُبرَزٍ داخل الجدول (الرأسُ والخلايا).",
        )

    def test_the_plan_key_is_not_written_twice_as_a_literal(self):
        literals = re.findall(r"['\"]Pro['\"]", self.source)
        self.assertLessEqual(
            len(literals), 1,
            "مفتاحُ الخطّة مكتوبٌ حرفيّاً أكثرَ من مرّة — يتباعد عن `HIGHLIGHTED_PLAN_KEY`.",
        )


class TheMatrixObeysTheRepoStyleRulesTest(TestCase):
    def setUp(self):
        self.source = PAGE.read_text(encoding="utf-8")

    def test_no_inline_styles_and_no_locale_formatters(self):
        self.assertNotIn("style={{", self.source, "أنماطٌ سطريّةٌ — القاعدةُ Tailwind وحدَه.")
        self.assertNotIn(
            "toLocaleString", self.source,
            "`toLocaleString` بالعربية تُخرج أرقاماً هنديّة — الأرقامُ عبر `formatNumber`.",
        )

    def test_every_light_surface_has_a_dark_counterpart(self):
        """الصفحةُ تُعرَض في الوضعين، وسطحٌ فاتحٌ بلا نظيرٍ داكنٍ يعطي نصّاً
        فاتحاً على أرضيّةٍ فاتحة."""
        # **المقارنةُ بنفس المُحدِّد لا بالسلسلة `dark:bg-`**: نظيرُ `odd:bg-white`
        # هو `dark:odd:bg-...` لا `dark:bg-...`، فشرطٌ ساذجٌ هنا يسقط على كودٍ
        # سليمٍ — ثمّ يُطفَأ بعد أوّل سقوطٍ كاذبٍ فلا يحرس شيئاً بعدها.
        offenders = []
        for cls_attr in re.findall(r'className="([^"]*)"', self.source):
            for variant in re.findall(r"(?:^|\s)((?:[a-z-]+:)*)bg-white\b", cls_attr):
                # صنفٌ مُحدَّدٌ بـ`dark:` أصلاً هو **النظيرُ** لا المخالف
                # (`dark:even:bg-white/[0.03]` سطحٌ داكنٌ بأبيضَ شفّاف).
                if variant.startswith("dark:"):
                    continue
                if f"dark:{variant}bg-" not in cls_attr:
                    offenders.append(f"{variant}bg-white في: {cls_attr[:60]}")
        self.assertFalse(
            offenders, f"أصنافٌ بخلفيّةٍ فاتحةٍ بلا نظيرٍ داكن: {offenders}",
        )
