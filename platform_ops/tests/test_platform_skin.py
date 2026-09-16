"""حارسُ قشرة سطح المنصّة السماويّة (#211 م٣).

قرارُ المالك صريحٌ ومحدود: السماويُّ يغطّي **كامل** موديول المنصّة ولا يتجاوزه
إلى شاشات شركات الزبائن. والقرارُ من النوع الذي **يُنقَض بلا قصد**: سطرٌ واحدٌ
في `index.css` خارج نطاق الغلاف يصبغ التطبيقَ كلَّه، ولا اختبارَ ديناميكيٌّ يراه
— `npm test` هنا يشغّل `utils/*.test.ts` بـ`node --test`، دوالَّ خالصةً لا تُصيّر
مكوّناً واحداً فلا ترى صنفَ CSS ولا خاصيّةَ JSX. فالحراسةُ ساكنةٌ بالضرورة.
"""
from pathlib import Path
import re

from django.test import SimpleTestCase

FRONTEND = Path(__file__).resolve().parents[2] / "frontend_v2"
INDEX_CSS = FRONTEND / "styles" / "index.css"
PLATFORM_COMPONENTS = FRONTEND / "components" / "platform"
STAFF_CRM_COMPONENTS = PLATFORM_COMPONENTS / "staff" / "crm"

# هذه لهجاتُ حالة وأزرارُ فعلٍ مقصودة فوق الجلد الداكن، لا أسطحٌ فاتحة متسرّبة.
# يبقى الاستثناء ضيّقاً ومكتوبَ السبب كي لا يصير توسيع المسح تجاوزاً أعمى.
# **فارغٌ منذ الموجة ٥-هـ**: لوحاتُ CRM صارت تلبس رموزَ `cc-*` فسقطت الأصنافُ
# الستّة كلُّها (`bg-amber-300` و`border-*-400`…)، وحارسُ الاستثناء المتقادم
# أدناه يُسقط أيَّ اسمٍ يُترك هنا بلا لابس. والآليّةُ باقيةٌ لأوّل لهجةٍ مقصودة.
INTENTIONAL_CRM_LIGHT_CLASSES: dict[str, str] = {}

#: الشاشاتُ الجذريّةُ لسطح المنصّة السماويّ — ما عداها لوحاتٌ تسكن داخلها فترث
#: الغلاف. وقشرةُ الموظّف (`staff/StaffShell.tsx`) **ليست** منها عمداً: سطحٌ
#: داكنٌ مستقلٌّ بغلافه `.staff-shell`، ويحرسه
#: `test_staff_shell_contract.py` بتأكيدٍ صريحٍ أنّه لا يلبس `platform-surface`.
ROOT_SCREENS = (
    "PlatformOpsDashboard.tsx",
    "PlatformEmployeeWorkspace.tsx",
    "StaffLoginPage.tsx",
)

#: الشاشاتُ الجذريّةُ التي تلبس **الغلافَ الداكنَ** بنفسها (لا ترثه من أمٍّ).
DARK_ROOT_SCREENS = (
    "PlatformOpsDashboard.tsx",
    "BillingRecordsScreen.tsx",
    "PlatformEmployeeWorkspace.tsx",
)

#: أغلفةُ سطح المنصّة المسموحُ لتجاوزات السُلَّم أن تُقصَر بها، ولكلٍّ سببُه.
#: **الغرضُ المحروسُ ليس اسمَ الغلاف بل الحصر**: قاعدةٌ بلا غلافٍ من هذه تصبغ
#: شاشاتِ الزبائن. وإضافةُ غلافٍ هنا لا تُسكِت الحارسَ مجّاناً —
#: `test_every_confined_scope_is_a_real_platform_surface` يُلزم أن يكون الغلافُ
#: ملبوساً فعلاً بملفٍّ تحت `components/platform/`.
CONFINED_SCOPES = {
    ".platform-surface": "سطحُ المنصّة السماويُّ (#211 م٣) — لوحةُ القيادة ومساحةُ الموظّف.",
    ".staff-shell": "قشرةُ الموظّف الداكنةُ المستقلّة (#212 212-A) — تُعيد تلوينَ اللوحاتِ "
                    "السِّتَّ المُعادَ استعمالُها، وتُبقي ما بقي فيها من أصنافٍ فاتحةٍ داكناً حيث تُركَّب.",
    ".ops-shell": "قشرةُ مركز القيادة الداكنة (#212 212-G) — تقرأ جلدَ قشرة الموظّف نفسَه بلا نسخةٍ ثانيةٍ من قيمه، وتصبغ اثنين وأربعين ملفّاً كثيرٌ منها محجوزٌ لمهمّةٍ أخرى لا يُلمَس.",
}


#: **أوسعُ من تعبير `test_staff_shell_contract.py` عن قصد**: ذاك يمسح ستَّ لوحاتٍ
#: مُعادَ استعمالُها، وهذا يمسح اثنين وأربعين ملفّاً تلبس لوحاتٍ أكثر — أحمرَ
#: التحذير، وبنفسجيَّ الإشعارات، وبرتقاليَّ الربحيّة، ودرجاتٍ بشفّافيّة. وبالتعبير
#: الضيّق مرّ الحارسُ أخضرَ وفي الشاشة أحدَ عشرَ صنفاً فاتحاً بلا تجاوز.
#: تُلتَقط **بادئةُ الـvariant كاملةً** لا `hover:` وحدَها: النقطتان ليستا في
#: `[\w-]`، فبادئةٌ غيرُ ملتقطةٍ تجعل `group-hover:text-blue-700` يُطابَق
#: `text-blue-700` ويُرضيه تجاوزُ الصنف العاري، والصنفُ الحقيقيُّ بلا تجاوز.
LIGHT_PLATFORM_CLASS = re.compile(
    r"(?<![\w:./\[-])(?:(?!dark:)[a-z][a-z0-9-]*:)*(?:"
    r"bg-(?:white(?:/\d+)?"
    r"|(?:slate|gray|zinc|neutral|stone)-(?:50|100|200|300)(?:/\d+)?"
    r"|(?:blue|sky|cyan|teal|indigo|violet|purple|fuchsia|pink|rose|red|orange|amber|yellow|lime|green|emerald)"
    r"-(?:50|100|200|300)(?:/\d+)?)"
    r"|text-(?:(?:slate|gray|zinc|neutral|stone)-(?:400|500|600|700|800|900)"
    r"|(?:blue|sky|cyan|teal|indigo|violet|purple|fuchsia|pink|rose|red|orange|amber|yellow|lime|green|emerald)"
    r"-(?:500|600|700|800|900))"
    r"|border-(?:(?:slate|gray|zinc|neutral|stone)-(?:100|200|300)"
    r"|(?:blue|sky|cyan|teal|indigo|violet|purple|fuchsia|pink|rose|red|orange|amber|yellow|lime|green|emerald)"
    r"-(?:100|200|300|400))"
    r"|divide-(?:slate|gray)-(?:100|200|300)"
    r"|ring-(?:slate-(?:100|200)|white)"
    r")(?![\w-])"
)


def _all_selectors(css: str) -> list[str]:
    r"""كلُّ محدِّدٍ في الملفّ، مفضوضةً فواصلُه.

    تُقرأ **مقدِّمةُ كلِّ كتلةٍ** لا الأسطرُ الحاملةُ لـ`{`: محدِّداتُ الجلد
    مزوَّجةٌ على سطرَين (`.staff-shell .x,` ثم `.ops-shell .x {`)، فقراءةُ سطر
    القوس وحدَه تُخفي نصفَها — ويمرّ `.bg-slate-50,` بلا غلافٍ في مجموعةٍ صامتاً
    فيصبغ المبيعاتَ والمخزونَ والمحاسبة. وتُنزع التعليقاتُ أوّلاً كي لا يصير
    قوسٌ داخلَ تعليقٍ حدَّ كتلة.
    """
    stripped = re.sub(r"/\*.*?\*/", " ", css, flags=re.DOTALL)
    selectors = []
    for prelude in re.findall(r"([^{}]*)\{", stripped):
        if prelude.lstrip().startswith("@"):
            continue
        selectors.extend(part.strip() for part in prelude.split(",") if part.strip())
    return selectors


def _scoped_selectors(css: str, scope: str) -> list[str]:
    """المحدِّداتُ التي تبدأ بغلافٍ بعينه."""
    return [selector for selector in _all_selectors(css) if selector.startswith(scope)]


def _ops_shell_bodies(css: str) -> list[str]:
    r"""أجسامُ كتل `.ops-shell` — **بعد نزع التعليقات**.

    التعليقاتُ هنا تشرح قواعدَ CSS، فتكتبها بأقواسها؛ وقوسٌ إغلاقٍ داخلَ تعليقٍ
    يقطع جسمَ الكتلة عند التحليل فتختفي كلُّ تصريحةٍ بعده. حدث فعلاً: تعليقٌ
    يقتبس `… .ktra-input { background: … }` أخفى ثلاثةَ رموزٍ تليه، فسقط حارسٌ
    على عيبٍ لا وجودَ له.
    """
    stripped = re.sub(r"/\*.*?\*/", " ", css, flags=re.DOTALL)
    return re.findall(r"\.ops-shell\s*\{(?P<body>[^{}]*)\}", stripped)


class PlatformOpsDarkSkinContractTest(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css = INDEX_CSS.read_text(encoding="utf-8")

    def test_the_ops_dashboard_wears_the_dark_shell_alongside_the_platform_surface(self):
        # شاشةُ الفوترة تُركَّب في `App.tsx` **بلا غلافٍ** — فكانت بيضاءَ كاملةً وسط
        # موديولٍ داكن، وكلُّ تجاوزات `.ops-shell` في `index.css` لا تصلها. فالغلافُ
        # على جذرها هي، ويُحرَس هنا مع أخواتها.
        for name in DARK_ROOT_SCREENS:
            with self.subTest(screen=name):
                source = (PLATFORM_COMPONENTS / name).read_text(encoding="utf-8")
                self.assertRegex(
                    source,
                    r'className="[^"]*\bplatform-surface ops-shell\b[^"]*\bbg-cc-bg\b',
                    f"{name} لا يلبس الغلافَ الداكنَ على جذره — شاشةٌ بيضاءُ في موديولٍ داكن.",
                )

    def test_every_light_class_the_ops_components_wear_has_a_dark_override(self):
        light_classes = set()
        # لوحة CRM تعيش في `staff/crm/` لكنها تُركّب أيضاً في مركز القيادة؛
        # لذا سطح العمليات مسؤول عن جلدها الداكن مثل مكوّناته المباشرة.
        source_paths = [
            *PLATFORM_COMPONENTS.glob("*.tsx"),
            *STAFF_CRM_COMPONENTS.glob("*.tsx"),
        ]
        for source_path in source_paths:
            light_classes.update(
                match.group(0) for match in LIGHT_PLATFORM_CLASS.finditer(
                    source_path.read_text(encoding="utf-8")
                )
            )

        self.assertTrue(light_classes)
        stale_exceptions = set(INTENTIONAL_CRM_LIGHT_CLASSES) - light_classes
        self.assertEqual(
            stale_exceptions, set(),
            f"استثناءات CRM لم تعد تلبسها اللوحة: {sorted(stale_exceptions)} — احذف الاستثناء المتقادم.",
        )
        # يُؤكَّد على **قائمةِ المخالفات** لا على نصِّ الـCSS: `assertIn` على ملفٍّ
        # كاملٍ تطبع مئةً وثلاثين كيلوبايتاً في خبر الفشل فيضيع الخبرُ في الكومة.
        scoped = _scoped_selectors(self.css, ".ops-shell")
        missing = []
        for light_class in sorted(light_classes):
            escaped_class = light_class.replace(":", r"\:").replace("/", r"\/")
            # يُطلَب **رمزُ الصنف** داخلَ محدِّدٍ يبدأ بالغلاف، لا سلسلةٌ حرفيّةٌ
            # بشكل `.ops-shell .x`: تجاوزُ `group-hover:` يلزمه سلفٌ وسيطٌ
            # (`.ops-shell .group:hover .group-hover\:x`) فالمطابقةُ الحرفيّةُ
            # تطلب المستحيلَ، وتجاوزُ `hover:` يلحقه `:hover` فتقطعه.
            if (
                light_class not in INTENTIONAL_CRM_LIGHT_CLASSES
                and not any(f".{escaped_class}" in selector for selector in scoped)
            ):
                missing.append(light_class)
        self.assertEqual(
            missing, [],
            f"أصنافٌ فاتحةٌ يلبسها مركزُ القيادة بلا تجاوزٍ داكن: {missing} — "
            "رقعةٌ بيضاءُ وسطَ شاشةٍ داكنة.",
        )

    def test_the_ops_dark_skin_follows_the_platform_surface_ramp(self):
        """**الترتيبُ جزءٌ من الصحّة لا زينة.**

        جذرُ القيادة يلبس الغلافين معاً، وقواعدُ `.platform-surface` السماويّة
        تساوي قواعدَ الجلد نوعيّةً (0,2,0) — فالمتأخّرُ في الملفّ هو الفائز.
        وكتلةٌ نُقلت فوقَ السُلَّم تُعيد الشاشةَ بيضاءَ بلا أن يسقط اختبارُ صنف.

        ويُقاس **موضعُ القواعد نفسِها** لا موضعُ تعليقٍ فوقها: تعليقٌ باقٍ
        وقواعدُ مرفوعةٌ يُبقي الحارسَ أخضرَ على شاشةٍ بيضاء — ولذلك لا مرساةَ
        هنا على نصِّ تعليقٍ: صياغتُه حرّةٌ، وقد انكسرت مرساةٌ كهذه فعلاً حين
        صُحِّح رأسُ الكتلة.
        """
        # **أوّلُ** قاعدةِ جلدٍ بعد **آخرِ** قاعدةِ سُلَّم: مقارنةُ الآخرِ بالآخر
        # تُبقي الحارسَ أخضرَ إذا رُفعت كتلةٌ واحدةٌ فوق السُلَّم وبقيت أخرى تحتَه.
        first_skin, last_ramp = self.css.index(".ops-shell ."), self.css.rfind(".platform-surface .")
        self.assertGreater(
            first_skin, last_ramp,
            "قاعدةُ جلدٍ داكنٍ سبقت سُلَّمَ السماويّ في الملفّ "
            f"(أوّلُ جلدٍ عند {first_skin}، وآخرُ سُلَّمٍ عند {last_ramp}) — "
            "تخسر صامتةً وتعود الشاشةُ بيضاء.",
        )

    def test_the_root_paints_its_own_ground_not_only_its_children(self):
        """صنفٌ فاتحٌ على **حامل الغلاف نفسِه** لا يطابقه محدِّدُ سليل.

        جذرُ اللوحة يلبس `ops-shell` و`bg-slate-50` و`text-slate-800` معاً، وكلُّ
        قواعد الجلد من شكل `.ops-shell .x` — فالجذرُ وحدَه يبقى فاتحاً: صفحةٌ
        بيضاءُ تطفو عليها بطاقاتٌ داكنة. ولا يمسك ذلك مسحُ الأصناف، لأنّ الصنفَ
        **مغطّىً** فعلاً... لمن هو سليل.
        """
        source = (PLATFORM_COMPONENTS / "PlatformOpsDashboard.tsx").read_text(encoding="utf-8")
        root = re.search(r'className="([^"]*\bops-shell\b[^"]*)"', source)
        self.assertIsNotNone(root, "لم يُعثر على العنصر الحامل للغلاف.")

        bodies = _ops_shell_bodies(self.css)
        needed = {"bg-": "background-color", "text-": "color"}
        unpainted = []
        for light_class in LIGHT_PLATFORM_CLASS.finditer(root.group(1)):
            prefix = next((p for p in needed if light_class.group(0).startswith(p)), None)
            if prefix is None:
                continue
            prop = needed[prefix]
            compound = f".ops-shell.{light_class.group(0)}"
            painted = compound in self.css or any(
                re.search(rf"(?<![\w-]){prop}\s*:", body) for body in bodies
            )
            if not painted:
                unpainted.append(f"{light_class.group(0)} ← لا `{prop}` على `.ops-shell` نفسِه")
        self.assertEqual(
            unpainted, [],
            f"أصنافٌ فاتحةٌ على حامل الغلاف بلا صبغٍ: {unpainted}",
        )

    def test_the_ops_shell_redefines_the_ktra_input_tokens(self):
        """ويُطلَب أن تُشتقّ القيمةُ من جلد الموظّف لا مجرَّدُ وجودِ الرمز.

        بالوجود وحدَه يمرّ `--ktra-field: white` أخضرَ: الحارسُ اسمُه «تُعاد
        تعريفُها» ومقصودُه «تصير داكنة»، فأيّ قيمةٍ تُرضيه تجعله لا يسقط للسبب
        الذي يحمله اسمُه. والاشتقاقُ من `--staff-*` هو تعريفُ «داكن» هنا:
        قيمةٌ واحدةٌ في مكانٍ واحدٍ لا نسخةٌ ثانيةٌ من اللوحة.
        """
        bodies = _ops_shell_bodies(self.css)
        self.assertTrue(bodies)
        stray = []
        for token in (
            "--ktra-field",
            "--ktra-border",
            "--ktra-border-soft",
            "--ktra-ink",
            "--ktra-accent-bg",
            "--ktra-panel",
            "--ktra-ink-soft",
            "--color-text",
            "--color-border",
        ):
            values = [
                match.group("value").strip()
                for body in bodies
                for match in re.finditer(rf"{re.escape(token)}\s*:(?P<value>[^;]*);", body)
            ]
            if not values:
                stray.append(f"{token} ← غيرُ معرَّفٍ على `.ops-shell`")
            elif not all("var(--staff-" in value for value in values):
                stray.append(f"{token} ← قيمةٌ لا تُشتقّ من جلد الموظّف: {values}")
        self.assertEqual(
            stray, [],
            f"رموزٌ يقرأها مركزُ القيادة ولم تصر داكنةً: {stray}",
        )

    def test_every_skin_surface_token_the_ops_components_read_goes_dark(self):
        """**المصدرُ الرابعُ للفاتح: صنفُ مكوِّنٍ لا أداةُ Tailwind.**

        `ktra-input` ليس صنفَ لونٍ يمسحه تعبيرٌ نمطيّ، وليس لوناً حرفيّاً في
        قاعدةِ قاعة عمل — بل صنفُ مكوِّنٍ تصبغه أوراقُ جلدٍ ثلاثةٌ متتالية، وآخرُها
        `:root[data-skin="modern"]` **تثبّت رمزاً فاتحاً ولا تقرأ `--ktra-field`**
        الذي أعاد الغلافُ تعريفَه. فالرمزُ صحيحٌ داكنٌ والحقلُ أبيضُ، ولونُ النصّ
        فاتحٌ فوقه: تباينُ 1.06:1. ولا يمسك ذلك أيُّ حارسٍ يقرأ أصنافَ TSX.

        فيُقرأ الاتّجاهُ المعاكس: ما الذي **تقرأه** قواعدُ الجلد على أصنافٍ
        تلبسها شاشاتُ القيادة فعلاً؟ كلُّ `var(--color-*)` من تلك القواعد يجب أن
        يكون معرَّفاً على `.ops-shell` ومشتقّاً من جلد الموظّف.
        """
        worn = {
            match.group(0)
            for path in PLATFORM_COMPONENTS.rglob("*.tsx")
            for match in re.finditer(r"(?<![\w-])ktra-[a-z0-9-]+(?![\w-])",
                                     path.read_text(encoding="utf-8"))
        }
        self.assertTrue(worn, "لم تعد شاشاتُ القيادة تلبس أصنافَ مكوّنات `ktra-*`.")

        # الرموزُ التي تقرأها قواعدُ الجلد على تلك الأصناف بالذات.
        read_tokens = set()
        for selector, body in re.findall(r"([^{}]*)\{([^{}]*)\}",
                                         re.sub(r"/\*.*?\*/", " ", self.css, flags=re.DOTALL)):
            if "data-skin" not in selector:
                continue
            if not any(f".{name}" in selector for name in worn):
                continue
            read_tokens.update(re.findall(r"var\(\s*(--color-[a-z0-9-]+)", body))
        self.assertTrue(read_tokens, "لم تعد قواعدُ الجلد تقرأ رموزَ `--color-*`.")

        bodies = _ops_shell_bodies(self.css)
        # رموزُ النصّ والحدّ الدلاليّةُ تُقرأ في مواضعَ كثيرةٍ ولها تجاوزاتُها
        # أعلاه؛ المقصودُ هنا ما يصبغ **سطحاً** — وهو ما يصير رقعةً بيضاء.
        surfaces = sorted(token for token in read_tokens if "surface" in token)
        self.assertTrue(surfaces, "لا رمزَ سطحٍ في القراءة — تغيّر شكلُ ورقة الجلد.")

        stray = []
        for token in surfaces:
            values = [
                match.group("value").strip()
                for body in bodies
                for match in re.finditer(rf"{re.escape(token)}\s*:(?P<value>[^;]*);", body)
            ]
            if not values:
                stray.append(f"{token} ← تقرأه قاعدةُ جلدٍ على صنفٍ تلبسه القيادة، وغيرُ معرَّفٍ على `.ops-shell`")
            elif not all("var(--staff-" in value for value in values):
                stray.append(f"{token} ← قيمةٌ لا تُشتقّ من جلد الموظّف: {values}")
        self.assertEqual(
            stray, [],
            f"رموزُ أسطحٍ تصبغ مكوّناتِ القيادة ولم تصر داكنةً: {stray} — "
            "حقلٌ أبيضُ يُكتب عليه بنصٍّ فاتح: الكتابةُ تختفي.",
        )

    def test_the_room_grounds_written_in_literal_colours_go_dark(self):
        """**الصنفُ ليس المصدرَ الوحيدَ للفاتح**: هذا الملفّ نفسُه يكتب أبيضَ حرفيّاً.

        أرضيّاتُ قاعة العمل (`pf-room` و`pf-room-table` و`pf-room-screen`
        و`pf-seat-badge`) مكتوبةٌ هنا بـ`#ffffff` و`rgba(255,255,255,…)`، فلا
        يراها مسحُ الأصناف مهما وُسِّع تعبيرُه — وبحثٌ في TSX عن تدرّجٍ يعود
        فارغاً. وشارةُ المقعد أسوأُها: نصُّها `text-slate-900` صار فاتحاً فوق
        خلفيّةٍ بيضاءَ بقيت بيضاء، أي اسمُ موظّفٍ بتباينِ 1.1:1.
        """
        rooms = {"pf-room", "pf-room-table", "pf-room-screen", "pf-seat-badge"}
        literal = re.compile(r"#f{3,6}\b|#ffffff\b|rgba\(\s*255\s*,\s*255\s*,\s*255", re.IGNORECASE)
        unpainted = []
        for name in sorted(rooms):
            base = re.search(rf"\.{name}\s*\{{(?P<body>[^{{}}]*)\}}", self.css)
            self.assertIsNotNone(base, f"قاعدةُ `.{name}` اختفت أو أُعيدت تسميتُها.")
            if not literal.search(base.group("body")):
                continue  # لا أبيضَ حرفيّاً فيها، فلا شيءَ يُنقَض
            if not re.search(rf"\.ops-shell\s+\.{name}\s*\{{", self.css):
                unpainted.append(name)
        self.assertEqual(
            unpainted, [],
            f"أرضيّاتٌ بيضاءُ حرفيّةٌ في قاعة العمل بلا نظيرٍ داكنٍ داخلَ الغلاف: {unpainted} — "
            "بطاقةٌ بيضاءُ يُكتب عليها نصٌّ صار فاتحاً: اسمٌ يختفي.",
        )

    def test_the_bare_table_rules_read_no_light_token_inside_either_shell(self):
        """**المصدرُ الخامسُ للفاتح: عنصرٌ عارٍ بلا صنفٍ أصلاً.**

        صدرُ `index.css` يمسّ كلَّ `<table>` في التطبيق بمحدِّداتِ عناصرَ عاريةٍ
        **خارجَ الطبقات** — `thead tr` و`thead th` و`tbody tr:hover` — وكلٌّ منها
        يقرأ رمزاً من سُلَّم الجذر الفاتح. ولا صنفَ في TSX يمسكه أيُّ حارسٍ من
        الحرّاس الأربعة فوق: لا صنفَ هناك من الأصل.

        قِسْتُ الأثرَ حيّاً على `/staff/performance` بجدول `PilotAxesTable`:
        رأسُه `rgb(248, 250, 252)` وصفُّه عند التمرير `rgb(241, 245, 249)` —
        شريطان أبيضان على لوحٍ كحليّ. فالقياسُ هنا معكوسٌ كسابقه: كلُّ
        `var(--color-*)` تقرأه قاعدةُ جدولٍ عاريةٌ يجب أن يكون معرَّفاً داخلَ
        **القشرتين معاً** ومشتقّاً من جلد الموظّف.
        """
        stripped = re.sub(r"/\*.*?\*/", " ", self.css, flags=re.DOTALL)

        read_tokens = set()
        for selector, body in re.findall(r"([^{}]*)\{([^{}]*)\}", stripped):
            selector = selector.strip()
            if not selector or selector.startswith("@"):
                continue
            # محدِّدُ عنصرٍ عارٍ فحسب: لا صنفَ ولا معرّفَ ولا سمةَ ولا زائفاً
            # (عدا `:hover`) — أي ما يطابق كلَّ جدولٍ في التطبيق بلا استثناء.
            if not re.fullmatch(r"(?:table|thead|tbody|tfoot|tr|th|td)"
                                r"(?:(?::hover)?\s+(?:table|thead|tbody|tfoot|tr|th|td))*"
                                r"(?::hover)?", selector):
                continue
            read_tokens.update(re.findall(r"var\(\s*(--color-[a-z0-9-]+)", body))
        self.assertTrue(
            read_tokens,
            "لا قاعدةَ جدولٍ عاريةٍ تقرأ رمزَ `--color-*` — تغيّر صدرُ الملفّ، "
            "فأعد قراءتَه بدل إسكات الحارس.",
        )

        shells = (".staff-shell", ".ops-shell")
        bodies = {shell: [] for shell in shells}
        for selector, body in re.findall(r"([^{}]*)\{([^{}]*)\}", stripped):
            parts = {part.strip() for part in selector.split(",")}
            for shell in shells:
                if shell in parts:
                    bodies[shell].append(body)
        for shell in shells:
            self.assertTrue(bodies[shell], f"لم تعد `{shell}` كتلةً قائمةً بذاتها في الورقة.")

        stray = []
        for token in sorted(read_tokens):
            for shell in shells:
                values = [
                    match.group("value").strip()
                    for body in bodies[shell]
                    for match in re.finditer(rf"{re.escape(token)}\s*:(?P<value>[^;]*);", body)
                ]
                if not values:
                    stray.append(f"{token} ← تقرأه قاعدةُ جدولٍ عاريةٌ وغيرُ معرَّفٍ على `{shell}`")
                elif not all("var(--staff-" in value for value in values):
                    stray.append(f"{token} ← على `{shell}` قيمةٌ لا تُشتقّ من جلد الموظّف: {values}")
        self.assertEqual(
            stray, [],
            f"رموزٌ فاتحةٌ تصل إلى جداولِ القشرتين عبر محدِّداتِ عناصرَ عارية: {stray} — "
            "شريطٌ أبيضُ في رأس الجدول وومضةٌ بيضاءُ تحت المؤشّر على لوحٍ كحليّ.",
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
        for selector in _all_selectors(self.css):
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


class TheSkinIsNavyNotCharcoalTest(SimpleTestCase):
    """‏**اللونُ نفسُه محروسٌ، لا اشتقاقُه وحدَه** (212-T).

    الحرّاسُ الاثنا عشرَ أعلاه يفحصون الاشتقاقَ والترتيبَ والتغطية — ولا واحدٌ
    منهم يفحص **اللون**. فانزلقت لوحةُ الجلد إلى رماديٍّ فحميٍّ شبهِ محايد
    وبقيت المجموعةُ خضراءَ بكاملها، حتى شكا المالكُ بعينه: «طلع رايح داكن لدرجة
    السواد، أنا بدي أزرق». هذا الحارسُ هو ما كان ناقصاً.

    ويُقاس **المقياسُ الذي فرّق فعلاً** بين المعروض والمرجع: لا الإضاءةُ — كانت
    لوحةُ المرجع **أفتحَ** من المعروض — بل الزُرقة `B − (R+G)/2`. المعروضُ كان
    ‎+17…+26 والمرجعُ ‎+31…+43.5، وكِلاهما «داكن» بالإضاءة سواء.
    """

    #: الحدُّ مأخوذٌ من أضعف سطحٍ في صورة المالك المرجعيّة (‎+31) منقوصاً هامشاً
    #: صغيراً — لا رقمٌ مخترَع. وما دونه يُقرأ رماديّاً لا كحليّاً.
    MIN_BLUENESS = 30.0

    #: أدنى فرقِ إضاءةٍ بين سطحين متجاورين؛ دونه تذوب البطاقةُ في أرضيّتها.
    MIN_STEP = 4.0

    SURFACE_TOKENS = ("--staff-rail", "--staff-bg", "--staff-panel")

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.css = INDEX_CSS.read_text(encoding="utf-8")

    @staticmethod
    def _rgb(value):
        value = value.strip().lstrip("#")
        return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))

    @staticmethod
    def _blueness(rgb):
        red, green, blue = rgb
        return blue - (red + green) / 2

    @staticmethod
    def _luminance(rgb):
        red, green, blue = rgb
        return 0.2126 * red + 0.7152 * green + 0.0722 * blue

    def _token(self, name):
        """قيمةُ الرمز — **ويُشترط تعريفٌ واحدٌ لا غير**.

        بقراءة الأوّل وحدَه يصير تعريفٌ ثانٍ لاحقٌ (تحت `@media` أو `.dark`) هو
        ما تراه الشاشةُ وما لا يراه الحارس: فيعود العطبُ الذي وُضع هذا الملفُّ
        كلُّه ليمنعه، ساكتاً كما كان.
        """
        values = re.findall(rf"{re.escape(name)}\s*:\s*(#[0-9a-fA-F]{{6}})\s*;", self.css)
        self.assertEqual(
            len(values), 1,
            f"رمزُ الجلد `{name}` معرَّفٌ {len(values)} مرّةً بقيمةٍ ستّ عشريّة — "
            "الحارسُ يقرأ الأوّلَ والشاشةُ تلبس الأخير.",
        )
        return self._rgb(values[0])

    def test_every_skin_surface_is_navy_not_neutral_charcoal(self):
        """كلُّ سطحٍ في لوحة الجلد يحمل صبغةً زرقاءَ حقيقيّة."""
        violations = []
        for name in self.SURFACE_TOKENS:
            blueness = self._blueness(self._token(name))
            if blueness < self.MIN_BLUENESS:
                violations.append(f"{name} ← زُرقة {blueness:+.1f} دون {self.MIN_BLUENESS:+.1f}")
        self.assertEqual(
            violations, [],
            "أسطحُ جلدٍ انزلقت إلى الرماديّ المحايد: "
            f"{violations} — وهي شكوى المالك نفسُها في 212-T.",
        )

    def test_the_surfaces_keep_their_order_and_do_not_flatten_into_each_other(self):
        """الريلُ أعمقُ، واللوحةُ أعلى، وبينهما فرقٌ يُرى.

        الترتيبُ وحدَه لا يكفي: سُلَّمٌ صحيحُ الترتيب وفروقُه أعشارٌ يجعل البطاقةَ
        والأرضيّةَ سطحاً واحداً، وهو عطبٌ لا يراه أيُّ فحصِ اشتقاق.
        """
        ladder = [(name, self._luminance(self._token(name))) for name in self.SURFACE_TOKENS]
        violations = []
        for (lower_name, lower), (upper_name, upper) in zip(ladder, ladder[1:]):
            if upper <= lower:
                violations.append(f"{upper_name} ({upper:.1f}) ليس أفتحَ من {lower_name} ({lower:.1f})")
            elif upper - lower < self.MIN_STEP:
                violations.append(
                    f"{lower_name}→{upper_name} فرقُ {upper - lower:.1f} دون {self.MIN_STEP:.1f}"
                )
        self.assertEqual(
            violations, [], f"سُلَّمُ الأسطح انبسط أو انقلب: {violations}",
        )

    def test_the_body_text_stays_readable_on_the_panel_it_sits_on(self):
        """تغميقُ اللوحة أو تفتيحُ النصّ بلا حسابٍ يُخرج التباينَ عن الحدّ.

        ‏`--staff-text` نصُّ المتن و`--staff-muted` نصُّه الثانويّ، وكلاهما يُكتب
        فوق `--staff-panel` — فأيُّ تحريكٍ للوحة يمسّهما معاً.
        """
        def channel(value):
            value /= 255
            return value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4

        def relative(rgb):
            red, green, blue = (channel(v) for v in rgb)
            return 0.2126 * red + 0.7152 * green + 0.0722 * blue

        panel = relative(self._token("--staff-panel"))
        violations = []
        for name, minimum in (("--staff-text", 7.0), ("--staff-muted", 4.5)):
            ink = relative(self._token(name))
            high, low = max(ink, panel), min(ink, panel)
            ratio = (high + 0.05) / (low + 0.05)
            if ratio < minimum:
                violations.append(f"{name} على اللوحة {ratio:.2f}:1 دون {minimum}:1")
        self.assertEqual(violations, [], f"تباينُ نصٍّ سقط تحت الحدّ: {violations}")
