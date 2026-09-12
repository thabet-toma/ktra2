"""حارسُ قشرة سطح المنصّة السماويّة (#211 م٣).

قرارُ المالك صريحٌ ومحدود: السماويُّ يغطّي **كامل** موديول المنصّة ولا يتجاوزه
إلى شاشات شركات الزبائن. والقرارُ من النوع الذي **يُنقَض بلا قصد**: سطرٌ واحدٌ
في `index.css` خارج نطاق الغلاف يصبغ التطبيقَ كلَّه، ولا اختبارَ ديناميكيٌّ يراه
— `npm test` هنا يشغّل `utils/*.test.ts` بـ`node --test`، دوالَّ خالصةً لا تُصيّر
مكوّناً واحداً فلا ترى صنفَ CSS ولا خاصيّةَ JSX. فالحراسةُ ساكنةٌ بالضرورة.
"""
from pathlib import Path

from django.test import SimpleTestCase

FRONTEND = Path(__file__).resolve().parents[2] / "frontend_v2"
INDEX_CSS = FRONTEND / "styles" / "index.css"
PLATFORM_COMPONENTS = FRONTEND / "components" / "platform"

#: الشاشاتُ الجذريّةُ لسطح المنصّة — ما عداها لوحاتٌ تسكن داخلها فترث الغلاف.
ROOT_SCREENS = (
    "PlatformOpsDashboard.tsx",
    "PlatformEmployeeWorkspace.tsx",
    "StaffLoginPage.tsx",
)


class PlatformSkinIsConfinedTest(SimpleTestCase):
    """القشرةُ تغطّي سطحَ المنصّة كلَّه، ولا تتجاوزه إلى شاشات الزبائن."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css = INDEX_CSS.read_text(encoding="utf-8")

    def test_every_platform_root_screen_wears_the_surface_class(self):
        """الغلافُ على الجذر: اللوحاتُ الداخليّةُ ترثه، فلو سقط عن جذرٍ بقيت شاشةٌ كاملةٌ زرقاء."""
        for name in ROOT_SCREENS:
            path = PLATFORM_COMPONENTS / name
            self.assertTrue(path.exists(), f"شاشةٌ جذريّةٌ مفقودة: {name}")
            source = path.read_text(encoding="utf-8")
            self.assertTrue(
                "platform-surface" in source,
                f"{name} لا تحمل `platform-surface` — شاشةٌ من سطح المنصّة بقيت على الأزرق الأصليّ.",
            )

    def test_no_ramp_override_escapes_the_surface_scope(self):
        """**الحارسُ الأهمّ**: كلُّ تجاوزٍ للسُلَّم مقصورٌ بالغلاف.

        قاعدةٌ واحدةٌ بلا البادئة تصبغ التطبيقَ كلَّه — المبيعاتِ والمخزونَ
        والمحاسبةَ — وهو بعينه ما رفضه المالك بقوله «لا تعمّمو».
        """
        offenders = []
        for raw in self.css.splitlines():
            line = raw.strip()
            if "{" not in line:
                continue
            selector = line.split("{", 1)[0].strip()
            if not selector:
                continue
            # قواعدُ السُلَّم وحدَها هي المقصودة: ما يستهدف صنفَ لونٍ من Tailwind.
            is_ramp_rule = any(
                token in selector
                for token in (".bg-slate-", ".text-slate-", ".border-slate-", ".divide-slate-",
                              ".bg-blue-", ".text-blue-", ".border-blue-", ".ring-blue-",
                              ".bg-sky-", ".text-sky-", ".border-sky-", ".ring-sky-")
            )
            if is_ramp_rule and not selector.startswith(".platform-surface"):
                offenders.append(selector)
        self.assertEqual(
            offenders, [],
            "تجاوزُ سُلَّمٍ خارجَ `.platform-surface` — يصبغ شاشاتِ الزبائن كلَّها: "
            f"{offenders}",
        )

    def test_the_global_primary_stays_the_company_blue(self):
        """رمزُ اللون الأساسيُّ في `@theme` يبقى أزرقَ الشركات.

        هذا هو القرارُ نفسُه مكتوباً كتأكيد: تحويلُ `--color-primary` في الجذر
        إلى السماويّ هو الطريقُ الأقصرُ إلى التعميم الذي رُفض — وسطرٌ واحدٌ يفعله.
        """
        theme_block = self.css.split("@theme", 1)[1].split("}", 1)[0]
        self.assertTrue(
            "--color-primary: #2563eb;" in theme_block,
            "‏`--color-primary` في `@theme` لم يعد أزرقَ الشركات — القشرةُ تسرّبت إلى الجذر.",
        )

    def test_the_surface_block_defines_the_three_status_lights(self):
        """أضواءُ الحالة الثلاثةُ معناها ثابتٌ عبر الغرفة وبطاقات الموظّفين.

        تعريفُها رمزاً واحداً يمنع أن يصير الأخضرُ في الغرفة غيرَه في البطاقة.
        """
        for token in ("--pf-online", "--pf-meeting", "--pf-offline"):
            self.assertTrue(
                token in self.css, f"رمزُ حالةٍ مفقود: {token}",
            )
