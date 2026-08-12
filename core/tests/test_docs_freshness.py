"""حارس طزاجة وثائق التنقّل — يمنع الخريطة من التعفّن بصمت.

**لماذا يوجد هذا الملف:** المرحلة 0 بنت توثيقاً مضغوطاً (`ARCHITECTURE.md` +
`docs/modules/`) ليقرأه الوكيل بدل 8,104 أسطر من `PROJECT_MAP.md`. البنية نجحت،
لكن لا شيء كان يحفظ دقّتها: خلال جلستين تراكم **11 مرجعاً لملفات لم تعد موجودة**
(المرحلة 3 حوّلت أربعة ملفات عملاقة إلى حِزَم)، ثلاثة منها داخل `ARCHITECTURE.md`
نفسه — بما فيها صفٌّ في جدول «أين أبدأ؟» الذي هو كامل غرض الملف.

والأثر غير خطّي: **سطر واحد خاطئ يُسقط الثقة بالخريطة كلها.** الوكيل يجرّب
`core/reports.py`، لا يجده، فيستنتج أن الوثيقة غير موثوقة ويعود لقراءة الكود —
أي أن «ضريبة السياق» التي بُنيت الخريطة لإلغائها تعود من الباب الخلفي.

**قرار السياسة — الرموز لا الأسطر:** الوثائق تشير بـ`` `file.py` (`symbol`) ``
لا `file.py:NNN`. رقم السطر ينزاح مع كل تعديل على الملف المُشار إليه (ثلاث
انزياحات كانت مؤكَّدة في `ARCHITECTURE.md` وحده)، فحراسته إمّا صارمة ⇒ احتكاك
دائم، أو متساهلة ⇒ يبقى كاذباً بصمت. الرمز مستقرّ، ويجده الوكيل بـ`grep` فوراً.
نقتل فئة العطل بدل أن نحرسها. أرقام الأسطر مسموحة داخل كتل `AUTO` المولَّدة فقط.

**البساطة شرط بقاء:** أنماط الالتقاط أدناه بسيطة عمداً — حارس هشّ بإنذارات كاذبة
يُعطَّل بعد شهر. المرجع يُفحَص فقط إذا بدأ بجذر معروف (app أو `docs/` أو
`frontend_v2/`)، فالمسارات النسبية في الوثائق (`services/restApi.ts` نسبةً إلى
`frontend_v2/`، و`tests/test_x.py` نسبةً إلى الـapp) لا تُلتقط ولا تُنذر كذباً.

السابقة في هذا المشروع: `.importlinter` يحرس المعمار آلياً بنفس المنطق — وقد
حُدِّث للمرحلة 3 بشكل صحيح بينما الوثائق وحدها لم تُحدَّث.
"""
import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

#: وثائق التنقّل التي يقرأها الوكيل. `docs/history/` مستثنى عمداً — سجلّ تاريخي
#: يصف الماضي، ومن الطبيعي أن يذكر ملفات لم تعد موجودة.
def _scanned_docs():
    docs = [
        REPO_ROOT / "CLAUDE.md",
        REPO_ROOT / "AGENTS.md",
        REPO_ROOT / "ARCHITECTURE.md",
        REPO_ROOT / "docs" / "DEPENDENCIES.md",
    ]
    docs.extend(sorted((REPO_ROOT / "docs" / "modules").glob("*.md")))
    return [d for d in docs if d.exists()]


#: يُفحَص المرجع فقط إن بدأ بأحد هذه الجذور — انظر «البساطة شرط بقاء» أعلاه.
def _local_apps():
    """أسماء الـapps المحلية.

    ثلاثة apps مسجَّلة بصيغة `after_sales.apps.AfterSalesConfig` لا بالاسم
    المجرّد؛ فلترةٌ ساذجة بـ`"." not in app` كانت تُسقطها بصمت — فتُعفى من فحص
    التغطية بلا أن يلاحظ أحد. المرجع هو وجود المجلد لا شكل التسجيل.
    """
    apps = set()
    for entry in settings.INSTALLED_APPS:
        if entry.startswith("django.") or entry.startswith("rest_framework"):
            continue
        name = entry.split(".")[0]
        if (REPO_ROOT / name).is_dir():
            apps.add(name)
    return apps


def _known_roots():
    return _local_apps() | {"docs", "frontend_v2", "tools", "load_tests"}


#: apps بلا وثيقة موديول — كلٌّ بسببه. الإعفاء قرار معلَن لا سهو.
MODULE_DOC_EXEMPTIONS = {
    "bridge": "جسر Firestore القديم (982 سطراً) — يُلمَس نادراً ومغطّى في ARCHITECTURE",
    "after_sales": "وحدة مرخّصة صغيرة (1,489 سطراً) — عقدها موصوف في ARCHITECTURE",
    "device_registry": "وحدة مرخّصة صغيرة (1,026 سطراً) — محايدة مالياً بالكامل",
    "realestate": "معزول وصغير (562 سطراً) بلا تشابك مع الدورة المحاسبية",
}

# ── أنماط الالتقاط (نمط واحد لكل شيء — لا تُعقّدها) ──────────────────────────
#: مسار ملف داخل backticks، مع رقم سطر اختياري: `core/tenant_utils.py` أو
#: `accounting/services.py:479`
PATH_RE = re.compile(r"`([A-Za-z_][\w./-]*\.(?:py|ts|tsx|md|cfg|ini|yml|json|txt))(?::(\d+))?`")
#: مجلد/حزمة داخل backticks: `logistics/views/`
DIR_RE = re.compile(r"`([A-Za-z_][\w./-]*/)`")
#: رمز يتبع مساراً مباشرةً: `accounting/services.py` (`post_journal`)
SYMBOL_RE = re.compile(
    r"`([A-Za-z_][\w./-]*\.py)(?::\d+)?`\s*\(`([A-Za-z_]\w*)`\)"
)
#: كتل الحقائق المولَّدة — أرقام الأسطر والأعداد مسموحة داخلها وحدها.
AUTO_BLOCK_RE = re.compile(r"<!--\s*AUTO:[\w-]+:START\s*-->.*?<!--\s*AUTO:[\w-]+:END\s*-->", re.S)
#: عدد اختبارات مثبّت بيد: «1,025 اختباراً»
TEST_COUNT_RE = re.compile(r"\b\d{1,3},\d{3}\s*اختبار")

#: سطور تذكر مساراً **لتنفي وجوده** («لا يوجد `hr/services.py`») — ذكرها صحيح
#: وغيابُ الملف هو المقصود، فلا تُفحَص.
NEGATION_RE = re.compile(r"لا يوجد|غير موجود|لم يعد|محذوف|أُزيل")
#: صفوف جداول الـendpoints تحمل مساراتٍ شبيهة بالمجلدات (`partners/lookup/`)
#: لكنها عناوين HTTP لا مواضع على القرص.
HTTP_VERB_RE = re.compile(r"\b(GET|POST|PUT|PATCH|DELETE)\b")


def _is_filesystem_claim(line):
    """هل يدّعي هذا السطر وجود ملف على القرص؟

    ينفي ذلك حالتان موثّقتان: نفيٌ صريح للوجود، وصفُّ جدول endpoints.
    """
    return not (NEGATION_RE.search(line) or HTTP_VERB_RE.search(line))


def _strip_auto_blocks(text):
    """يُفرغ كتل AUTO مع الحفاظ على أرقام الأسطر (لتقارير أدقّ)."""
    return AUTO_BLOCK_RE.sub(lambda m: "\n" * m.group(0).count("\n"), text)


def _iter_lines(doc):
    text = _strip_auto_blocks(doc.read_text(encoding="utf-8"))
    for number, line in enumerate(text.splitlines(), start=1):
        yield number, line


def _rel(doc):
    return doc.relative_to(REPO_ROOT).as_posix()


class DocsFreshnessTest(SimpleTestCase):
    """كل إخفاق هنا يعني: وكيل سيقرأ الوثيقة، يتبع المرجع، ولا يجده."""

    def test_referenced_paths_exist(self):
        """كل ملف/مجلد تذكره وثيقة تنقّل موجود فعلاً على القرص."""
        roots = _known_roots()
        broken = []
        for doc in _scanned_docs():
            for number, line in _iter_lines(doc):
                if not _is_filesystem_claim(line):
                    continue
                refs = [m.group(1) for m in PATH_RE.finditer(line)]
                refs += [m.group(1) for m in DIR_RE.finditer(line)]
                for ref in refs:
                    if ref.split("/")[0] not in roots:
                        continue  # مسار نسبي — خارج نطاق الفحص عمداً
                    if not (REPO_ROOT / ref).exists():
                        broken.append(f"{_rel(doc)}:{number} → {ref}")
        self.assertEqual(
            broken, [],
            "مراجع لملفات غير موجودة (غالباً حِزَم المرحلة 3):\n  "
            + "\n  ".join(broken),
        )

    def test_referenced_symbols_are_defined(self):
        """الرمز المذكور بعد مسار **يظهر** فعلاً في ذلك الملف.

        هذا بديل حراسة أرقام الأسطر: الرمز يبقى صحيحاً مهما انزاح موضعه.

        «يظهر» لا «معرَّف» عمداً: الوثائق توثّق مواضع **الاستعمال** أيضاً
        (`partners/views.py` يستدعي `partner_account_statement` المعرَّف في
        `accounting/services.py`). ما يهمّ الحارسَ أن الرمز لم يُحذَف أو
        يُعَد تسميته — وحينها يختفي من الملف كلياً.
        """
        roots = _known_roots()
        missing = []
        for doc in _scanned_docs():
            for number, line in _iter_lines(doc):
                for match in SYMBOL_RE.finditer(line):
                    ref, symbol = match.group(1), match.group(2)
                    if ref.split("/")[0] not in roots:
                        continue
                    target = REPO_ROOT / ref
                    if not target.is_file():
                        continue  # يمسكه اختبار المسارات
                    source = target.read_text(encoding="utf-8", errors="replace")
                    if not re.search(rf"\b{re.escape(symbol)}\b", source):
                        missing.append(f"{_rel(doc)}:{number} → {symbol} ليس في {ref}")
        self.assertEqual(
            missing, [],
            "رموز موثّقة غير معرَّفة في ملفاتها:\n  " + "\n  ".join(missing),
        )

    def test_no_hardcoded_line_numbers(self):
        """سياسة «الرموز لا الأسطر» — `file.py:479` ينزاح، `file.py` (`sym`) لا.

        أرقام الأسطر مسموحة داخل كتل AUTO المولَّدة وحدها.
        """
        roots = _known_roots()
        offenders = []
        for doc in _scanned_docs():
            for number, line in _iter_lines(doc):
                for match in PATH_RE.finditer(line):
                    ref, line_no = match.group(1), match.group(2)
                    if line_no and ref.split("/")[0] in roots:
                        offenders.append(f"{_rel(doc)}:{number} → {ref}:{line_no}")
        self.assertEqual(
            offenders, [],
            "أرقام أسطر مثبّتة بيد — استبدلها بـ`الملف` (`الرمز`):\n  "
            + "\n  ".join(offenders),
        )

    def test_every_local_app_has_a_module_doc_or_a_reason(self):
        """لا app يبقى بلا خريطة صامتاً — إمّا وثيقة أو إعفاء مُعلَّل."""
        modules_dir = REPO_ROOT / "docs" / "modules"
        undocumented = []
        for app in sorted(_local_apps()):
            if (modules_dir / f"{app}.md").exists():
                continue
            if app in MODULE_DOC_EXEMPTIONS:
                continue
            undocumented.append(app)
        self.assertEqual(
            undocumented, [],
            "apps بلا وثيقة موديول ولا إعفاء مُعلَّل "
            "(أضف docs/modules/<app>.md أو سجّل السبب في MODULE_DOC_EXEMPTIONS):\n  "
            + "\n  ".join(undocumented),
        )

    def test_production_code_has_one_source_of_today(self):
        """`date.today()` ممنوعة في كود الإنتاج — `timezone.localdate()` وحدها.

        الاثنتان تُرجعان `date` لكنهما تختلفان: الأولى تاريخ **نظام الخادم**،
        والثانية تاريخ **العمل** بحسب `TIME_ZONE`. خلطهما جعل مستنداً يُنشأ
        بعد منتصف الليل يُؤرَّخ بيوم أمس (والخادم في UTC والعمل في UTC+2/+3)،
        وأسقط `test_dashboard_isolation` بين 00:00 و03:00 فقط — عطلٌ لا يظهر
        إلا لمن يعمل ليلاً، وهذا أسوأ أنواع الأعطال.

        الاختبارات مستثناة: بعضها يثبّت تواريخ صريحة عمداً.
        """
        skip = re.compile(r"(^|/)(tests?)/|test_|/migrations/|^load_tests/|^venv/|^\.claude/")
        offenders = []
        for path in REPO_ROOT.rglob("*.py"):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if skip.search(rel) or "node_modules" in rel:
                continue
            for number, line in enumerate(
                path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
            ):
                if re.search(r"\bdate\.today\(\)", line):
                    offenders.append(f"{rel}:{number}")
        self.assertEqual(
            offenders, [],
            "استعمل `timezone.localdate()` بدل `date.today()`:\n  "
            + "\n  ".join(offenders),
        )

    def test_exemptions_are_real_apps(self):
        """إعفاء لـapp محذوف = قائمة تتعفّن هي الأخرى."""
        stale = sorted(set(MODULE_DOC_EXEMPTIONS) - _local_apps())
        self.assertEqual(stale, [], f"إعفاءات لـapps غير موجودة: {stale}")

    def test_generated_blocks_are_current(self):
        """كتل AUTO مطابقة للكود — نمط `makemigrations --check`.

        يُستدعى هنا لا في CI وحدها لأن CI لا تعمل على كل الفروع؛ `manage.py test`
        هو البوابة التي يمرّ منها كل تغيير فعلاً.
        """
        from django.core.management import call_command
        from django.core.management.base import CommandError

        try:
            call_command("sync_docs", check=True, verbosity=0)
        except CommandError as exc:
            self.fail(f"{exc}\nشغّل: python manage.py sync_docs")

    def test_pytest_collects_every_app_test_dir(self):
        """كل `<app>/tests` مذكور في `pytest.ini` — وإلا فاختبارات لا تعمل في CI.

        `manage.py test` يكتشف الاختبارات تلقائياً، لكن **CI يشغّل pytest**
        و`testpaths` قائمةٌ صريحة تُحدَّث باليد. سقطت منها ثلاث apps
        (`accountant_portal`, `after_sales`, `device_registry`) = 176 اختباراً
        (15% من المجموعة) لم تعمل في CI قط رغم خضرتها محلياً — نفس فئة العطل
        التي جعلت `tenants` namespace package فأخفت 75 اختباراً، وأخطرها أن
        الغياب يبدو كنجاح.
        """
        import configparser

        parser = configparser.ConfigParser()
        parser.read(REPO_ROOT / "pytest.ini", encoding="utf-8")
        listed = set(parser["pytest"]["testpaths"].split())
        on_disk = {
            f"{app}/tests"
            for app in _local_apps()
            if (REPO_ROOT / app / "tests").is_dir()
        }
        self.assertEqual(
            sorted(on_disk - listed), [],
            "مجلدات اختبارات لا يجمعها pytest ⇒ خضراء محلياً وغائبة عن CI "
            "(أضِفها إلى testpaths في pytest.ini):\n  "
            + "\n  ".join(sorted(on_disk - listed)),
        )
        self.assertEqual(
            sorted(listed - on_disk), [],
            "مسارات في testpaths بلا مجلد على القرص:\n  "
            + "\n  ".join(sorted(listed - on_disk)),
        )

    def test_no_hardcoded_test_counts(self):
        """عدد الاختبارات يتغيّر كل جلسة — يُولَّد داخل AUTO أو لا يُذكر."""
        offenders = []
        for doc in _scanned_docs():
            for number, line in _iter_lines(doc):
                if TEST_COUNT_RE.search(line):
                    offenders.append(f"{_rel(doc)}:{number} → {line.strip()[:80]}")
        self.assertEqual(
            offenders, [],
            "أعداد اختبارات مثبّتة بيد خارج كتل AUTO:\n  " + "\n  ".join(offenders),
        )
