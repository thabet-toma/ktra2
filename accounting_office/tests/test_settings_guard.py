"""حارس «لا قراءة خام للإعدادات خارج المحلّل» — #271.

**القاعدة الملزِمة:** المحلّل وحده يعرف بأيّ ترتيبٍ تُقرأ الإعدادات. أيُّ كودٍ
يقرأ `OfficeSettingValue` أو `ClientSettingOverride` مباشرةً يبني محلّلاً
موازياً — ونسختان من قاعدة «شغلة ← زبون ← مكتب ← افتراضي» تفترقان عند أول
تعديل، بصمت.

**لماذا مسحُ المصدر لا اختبار سلوك:** القراءة الخام لا تُخطئ اليوم — تُخطئ
غداً حين يُنقل المحلّل أو يُضاف مستوى. الحارس يمنع الكتابة من أصله، لا يكتشف
أثرها.

**والنطاق المستودع كلُّه لا مجلد الـapp**: القارئُ الخام قد يُكتب في app آخر
أو في أمر إداري، فيمرّ من مسحٍ محدود. المجلداتُ المستثناة معلَنة أدناه، ومنها
`.agents` (worktrees غير متتبَّعة) كي لا يقرأ الحارسُ نسخاً لا يملكها المستودع.

والحارسُ **يثبت أنه يسقط**: `test_the_guard_falls_on_a_synthetic_violation`
يفشل لو صار المسح أعمى.
"""
import pathlib
import re
import tempfile

from django.test import SimpleTestCase

APP_DIR = pathlib.Path(__file__).resolve().parent.parent
REPO_ROOT = APP_DIR.parent

#: نموذجا التخزين. ذِكرُهما مسموحٌ في مكانين فقط: تعريفُهما، ومن يقرؤهما.
SETTINGS_MODELS = ("OfficeSettingValue", "ClientSettingOverride")

#: الملفات المسموح لها بمعرفة النموذجين — وحدةُ المحلّل ونماذجُها.
ALLOWED_FILES = {
    APP_DIR / "models.py",
    APP_DIR / "services.py",
}

#: مجلدات لا تُفحَص: مولَّدة، أو غير متتبَّعة، أو خارج بايثون الخادم.
PRUNED_DIRS = {
    "tests", "migrations", "__pycache__",
    # نسخُ عملٍ متداخلة غير متتبَّعة في هذا المستودع (`.agents/worktrees/…`) —
    # مسحُها يقيس كوداً لا يملكه هذا الفرع.
    ".agents",
    # بيئاتٌ وأصولٌ ليست كود الخادم.
    "venv", ".venv", "node_modules", "frontend_v2",
    ".git", ".claude", "dist", "build", "staticfiles", "media",
}


def _module_files(root: pathlib.Path = REPO_ROOT):
    root = pathlib.Path(root)
    for path in sorted(root.rglob("*.py")):
        if any(part in PRUNED_DIRS for part in path.relative_to(root).parts):
            continue
        yield path


def mentions_settings_model(source: str) -> list[str]:
    """أسماءُ نموذجَي التخزين المذكورة في نصٍّ ما — نواةُ المسح، تُختبَر وحدها."""
    return [
        name for name in SETTINGS_MODELS
        if re.search(rf"\b{name}\b", source)
    ]


def find_raw_settings_readers(root: pathlib.Path = REPO_ROOT) -> list[str]:
    """ملفاتٌ في المستودع تذكر نموذجَي الإعدادات وليست من وحدة المحلّل."""
    root = pathlib.Path(root)
    offenders = []
    for path in _module_files(root):
        if path in ALLOWED_FILES:
            continue
        try:
            source = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        offenders.extend(
            f"{path.relative_to(root).as_posix()} → {name}"
            for name in mentions_settings_model(source)
        )
    return offenders


class RawSettingsReadGuardTest(SimpleTestCase):
    def test_no_module_outside_the_resolver_names_a_settings_model(self):
        offenders = find_raw_settings_readers()
        self.assertEqual(
            offenders, [],
            "قراءةٌ خامٌّ لجدول إعدادات خارج وحدة المحلّل — استعمل "
            "`accounting_office/services.py` (`resolve_setting`) ودوالّ الكتابة معها:\n  "
            + "\n  ".join(offenders),
        )

    def test_the_guard_covers_the_whole_repository_not_only_the_app(self):
        """النطاقُ مستودعٌ كامل: قارئٌ في app آخر يجب أن يُسقط الحارس.

        تُبنى شجرةٌ في مجلدٍ مؤقّت (لا كتابة تحت المستودع، فلا سباق بين عمّال
        xdist): قارئٌ في app آخر **يُمسَك**، ونسخُ `.agents` غير المتتبَّعة
        و`node_modules` **تُقلَّم**.
        """
        source = "from accounting_office.models import OfficeSettingValue\n"
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = pathlib.Path(tmp)
            for relative in (
                "other_app/reader.py",
                ".agents/worktrees/x/reader.py",
                "node_modules/y/reader.py",
            ):
                probe = tmp_root / relative
                probe.parent.mkdir(parents=True, exist_ok=True)
                probe.write_text(source, encoding="utf-8")
            offenders = find_raw_settings_readers(tmp_root)
        self.assertEqual(offenders, ["other_app/reader.py → OfficeSettingValue"])

    def test_the_guard_falls_on_a_synthetic_violation(self):
        """لو صار المسح أعمى (نمطٌ خاطئ أو قائمةٌ فارغة) يسقط هذا الاختبار."""
        self.assertEqual(
            mentions_settings_model("from accounting_office.models import OfficeSettingValue"),
            ["OfficeSettingValue"],
        )
        self.assertEqual(
            mentions_settings_model("rows = ClientSettingOverride.objects.all()"),
            ["ClientSettingOverride"],
        )
        # الاستثناءُ ملفان بالضبط، وفيهما ذِكرُ النموذجين فعلاً — وإلا كان
        # الاستثناء باباً مفتوحاً بلا سبب.
        self.assertEqual(len(ALLOWED_FILES), 2)
        for path in ALLOWED_FILES:
            self.assertTrue(path.exists(), path)
            self.assertTrue(mentions_settings_model(path.read_text(encoding="utf-8")), path)
