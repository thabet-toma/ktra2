"""ISSUE #291 — حارسُ «لا أثر لطبقة المكتب القديمة» على الخادم.

حذفُ النماذج لا يمنع عودتها: يكفي استيرادٌ واحد أو مسارٌ واحد ليعود البابُ الذي
أُغلق. هذا حارسُ نصٍّ على نمط حرّاس المستودع (`core/tests/test_throttle_guards.py`)،
لا اختبارَ سلوك — والسلوكُ المحذوف لا يُختبر.

ثلاثةُ فحوص:
  1. النماذجُ الستّة ليست في سِجلّ التطبيقات (`apps.get_model` يرفع `LookupError`).
  2. عَلَمُ سطح المكتب (`ACCOUNTANT_PRACTICE_ENABLED`) ليس إعداداً.
  3. لا ملفَّ بايثون يستورد النماذجَ أو يذكر سطح المكتب — في الكود ولا في الاختبارات.

**الهجراتُ مستثناة بقصد**: `0003`/`0005`/`0006` المطبَّقة تسمّي النماذج بحقّ،
وتعديلُها ممنوع. والملفُّ نفسه مستثنى: يسمّي الأنماطَ فيسقط عليها لو فحص نفسه.
"""
import re
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.test import SimpleTestCase

REPO = Path(__file__).resolve().parent.parent.parent
# الاستثناءُ بأجزاء المسار **نسبةً إلى REPO** لا بنصّه المطلق: من يشغّل المجموعة
# داخل `.agents/worktrees/<فرع>` كان مساره المطلق يحمل «worktrees» فيُستثنى كلُّ
# شيء ولا يفحص الحارس شيئاً (وهو ما يسقط `core/tests/test_throttle_guards.py` هنا).
_SKIP_PARTS = frozenset({"venv", "node_modules", "site-packages", "migrations", ".agents"})
_SELF = Path(__file__).resolve()

_DELETED_MODELS = (
    "PracticeClient",
    "PracticeClientArchive",
    "PracticeDocument",
    "PracticeProgram",
    "PracticeSettings",
    "PracticeTask",
)

# استيرادُ نموذجٍ محذوف — بسطرٍ واحد أو داخل قوسين على أسطر — أو الوصول إليه
# عبر `apps.get_model`/المدير، أو استعمالُه مباشرةً بلا استيراد.
_MODEL_REFERENCE = re.compile(
    r"from\s+accountant_portal\.models\s+import\s*\(?[\s\S]{0,600}?\bPractice"
    r"(?:Client|ClientArchive|Document|Program|Settings|Task)\b|"
    r"accountant_portal\.models\.Practice|"
    r"get_model\(\s*['\"]accountant_portal['\"]\s*,\s*['\"]Practice|"
    r"\bPractice(?:Client|ClientArchive|Document|Program|Settings|Task)\.objects\b"
)

# سطحُ المكتب المحذوف: وحدتُه، ومساراتُه (مطلقةً أو نسبيةً داخل `urls.py`)،
# وعَلَمُه، ودالّةُ لوحته.
_PRACTICE_SURFACE = re.compile(
    r"accountant_portal\.practice\b|"
    r"accountant_portal import practice|"
    r"practice_views|"
    r"PracticeOverviewView|"
    r"practice_overview|"
    r"ACCOUNTANT_PRACTICE_ENABLED|"
    r"['\"]practice/|"
    r"/api/accountant/practice/"
)


def _python_sources():
    for path in REPO.rglob("*.py"):
        if _SKIP_PARTS.intersection(path.relative_to(REPO).parts):
            continue
        if path.resolve() == _SELF:
            continue
        yield path


class LegacyOfficeRemovedTest(SimpleTestCase):
    def test_deleted_models_are_gone_from_the_app_registry(self):
        for name in _DELETED_MODELS:
            with self.assertRaises(
                LookupError, msg=f"{name} ما زال في سِجلّ التطبيقات.",
            ):
                apps.get_model("accountant_portal", name)

    def test_practice_surface_flag_is_not_a_setting(self):
        self.assertFalse(
            hasattr(settings, "ACCOUNTANT_PRACTICE_ENABLED"),
            "عَلَمُ سطح المكتب القديم عاد إلى الإعدادات.",
        )

    def test_no_source_references_the_deleted_models_or_surface(self):
        offenders = []
        scanned = 0
        for path in _python_sources():
            scanned += 1
            text = path.read_text(encoding="utf-8", errors="ignore")
            if _MODEL_REFERENCE.search(text) or _PRACTICE_SURFACE.search(text):
                offenders.append(str(path.relative_to(REPO)))
        # حارسٌ لا يقرأ شيئاً يمرّ أخضرَ أبداً — نثبت أن الماسح عمل.
        self.assertGreater(scanned, 100, "الماسح لم يقرأ ملفّاتٍ كافية — تعطّل الفحص.")
        self.assertEqual(
            offenders, [],
            f"أثرٌ باقٍ من طبقة المكتب القديمة: {offenders}",
        )
