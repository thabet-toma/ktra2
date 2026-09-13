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

#: الشاشاتُ الجذريّةُ لسطح المنصّة السماويّ — ما عداها لوحاتٌ تسكن داخلها فترث
#: الغلاف. وقشرةُ الموظّف (`staff/StaffShell.tsx`) **ليست** منها عمداً: سطحٌ
#: داكنٌ مستقلٌّ بغلافه `.staff-shell`، ويحرسه
#: `test_staff_shell_contract.py` بتأكيدٍ صريحٍ أنّه لا يلبس `platform-surface`.
ROOT_SCREENS = (
    "PlatformOpsDashboard.tsx",
    "PlatformEmployeeWorkspace.tsx",
    "StaffLoginPage.tsx",
)

#: أغلفةُ سطح المنصّة المسموحُ لتجاوزات السُلَّم أن تُقصَر بها، ولكلٍّ سببُه.
#: **الغرضُ المحروسُ ليس اسمَ الغلاف بل الحصر**: قاعدةٌ بلا غلافٍ من هذه تصبغ
#: شاشاتِ الزبائن. وإضافةُ غلافٍ هنا لا تُسكِت الحارسَ مجّاناً —
#: `test_every_confined_scope_is_a_real_platform_surface` يُلزم أن يكون الغلافُ
#: ملبوساً فعلاً بملفٍّ تحت `components/platform/`.
CONFINED_SCOPES = {
    ".platform-surface": "سطحُ المنصّة السماويُّ (#211 م٣) — لوحةُ القيادة ومساحةُ الموظّف.",
    ".staff-shell": "قشرةُ الموظّف الداكنةُ المستقلّة (#212 212-A) — تُعيد تلوينَ اللوحاتِ "
                    "السِّتَّ المُعادَ استعمالُها دون لمسِ ملفّاتها فتبقى فاتحةً في سطح المنصّة.",
}


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
            if is_ramp_rule and not any(
                selector.startswith(scope) for scope in CONFINED_SCOPES
            ):
                offenders.append(selector)
        self.assertEqual(
            offenders, [],
            "تجاوزُ سُلَّمٍ خارجَ أغلفةِ المنصّة المعلَنة "
            f"({', '.join(sorted(CONFINED_SCOPES))}) — يصبغ شاشاتِ الزبائن كلَّها: "
            f"{offenders}",
        )

    def test_every_confined_scope_is_a_real_platform_surface(self):
        """غلافٌ يُعلَن هنا يجب أن يكون ملبوساً فعلاً في سطح المنصّة.

        بلا هذا التأكيد يصير `CONFINED_SCOPES` بابَ تهريب: من ضايقه الحارسُ
        أعلاه يكفيه أن يعلن غلافَه الجديدَ فيمرّ — ولو كان ذلك الغلافُ مكتوباً
        على شاشةِ مبيعاتٍ لا على شاشةِ منصّة. فالإعلانُ هنا يلزمه دليلٌ في الكود.
        """
        sources = {
            path: path.read_text(encoding="utf-8")
            for path in sorted(PLATFORM_COMPONENTS.rglob("*.tsx"))
        }
        for scope, reason in CONFINED_SCOPES.items():
            with self.subTest(scope=scope):
                # اسمُ الملفّ لا محتواه في رسالة الفشل: تجميعُ كلِّ الـTSX في
                # `assertIn` يطبع نصفَ مجلّدٍ عند السقوط فتصير الرسالةُ عائقاً.
                wearers = [p.name for p, src in sources.items() if scope.lstrip(".") in src]
                self.assertTrue(
                    wearers,
                    f"الغلافُ {scope} معلَنٌ في `CONFINED_SCOPES` ولا يلبسه أيُّ ملفٍّ "
                    f"من ملفّات `components/platform/` الـ{len(sources)} — إعلانٌ "
                    "يُسكِت الحارسَ بلا سطحٍ يقابله.",
                )
                self.assertGreater(
                    len(reason.strip()), 25,
                    f"الغلافُ {scope} بلا سببٍ مكتوب — الاستثناءُ قرارٌ يُبرَّر لا سطرٌ يمرّ.",
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
