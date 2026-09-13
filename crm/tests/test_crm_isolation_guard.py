"""قائمةٌ بيضاءُ صريحةٌ بنماذج `crm` التي بلا `tenant`، وسببُ كلٍّ — على نمط
`platform_ops/tests/test_isolation_guard.py`: لا حُكمَ ضمنيّاً، والإضافةُ قرارٌ
يُكتب هنا لا سطرٌ يمرّ صامتاً."""
import ast
from pathlib import Path

from django.apps import apps
from django.test import SimpleTestCase

#: كلُّ نماذج crm بلا tenant عمداً — الوحدةُ كلُّها عن زبائن كترا نفسِها لا
#: زبائن شركةٍ على المنصّة (نفسُ حجّة `platform_ops.JobPosting`/`PlatformMeeting`).
EXPECTED_TENANT_LESS_MODELS = {
    "Lead": "الزبونُ المحتمَل زبونُ كترا نفسِها قبل أن يصير شركةً على المنصّة.",
    "LeadPhone": "تابعةٌ لـLead، ومفتاحُ فرادتها (`e164`) يجب أن يبقى عابراً للشركات.",
    "LeadActivity": "تابعةٌ لـLead — سجلُّ تواصلٍ مع زبونٍ لا شركة.",
    "LeadTransfer": "تابعةٌ لـLead — تحويلٌ بين موظّفَي منصّةٍ لا بين شركتين.",
    "LeadImportBatch": "دفعةُ رفعٍ يُنشئها مديرُ عمليات المنصّة، لا تخصّ شركةً بعينها.",
}


class CrmIsolationGuardTest(SimpleTestCase):
    def test_no_crm_model_carries_a_tenant_field(self):
        offenders = []
        for model in apps.get_app_config("crm").get_models():
            field_names = {f.name for f in model._meta.get_fields()}
            if "tenant" in field_names:
                offenders.append(model.__name__)
        self.assertEqual(
            offenders, [],
            f"نموذجٌ في crm يحمل tenant رغم أنّ الوحدة كلّها بلا tenant عمداً: {offenders}",
        )

    def test_the_whitelist_matches_every_model_in_the_app_exactly(self):
        actual = {model.__name__ for model in apps.get_app_config("crm").get_models()}
        expected = set(EXPECTED_TENANT_LESS_MODELS)
        self.assertEqual(
            actual, expected,
            "نموذجٌ جديدٌ أُضيف بلا تحديث القائمة البيضاء (أو حُذف نموذجٌ منها):\n"
            f"  في الكود ولا في القائمة: {sorted(actual - expected)}\n"
            f"  في القائمة ولا في الكود: {sorted(expected - actual)}",
        )

    def test_every_reason_is_a_real_non_empty_sentence(self):
        for model_name, reason in EXPECTED_TENANT_LESS_MODELS.items():
            with self.subTest(model=model_name):
                self.assertGreater(len(reason.strip()), 10)


#: تطبيقاتُ الشركات — نظامُ الزبائن الذي **يجب أن يظلّ يعمل** لو حُذف عنقودُ
#: المنصّة (`platform_ops` + `crm`) كلُّه من المستودع.
BUSINESS_APPS = frozenset({
    "accountant_portal", "accounting", "after_sales", "bridge", "core",
    "device_registry", "docshare", "employee_ops", "hr", "import_file",
    "inventory", "logistics", "partners", "realestate", "sales", "store",
    "tenants",
})

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

PRUNED_DIRS = {
    "venv", ".venv", "node_modules", "__pycache__", ".git", ".claude",
    ".multica", ".pytest_cache", "dist", "test-results", ".clone",
    ".agent_context", "playwright-report", "django_cache",
}


def _inbound_crm_imports(source: str, filepath: str) -> list[str]:
    """كلُّ استيرادٍ لـ`crm` — صريحاً أو ديناميكيّاً — في ملفٍّ واحد."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            offenders += [
                f"{filepath}:{node.lineno} → import {alias.name}"
                for alias in node.names
                if alias.name.split(".")[0] == "crm"
            ]
        elif isinstance(node, ast.ImportFrom):
            if not node.level and node.module and node.module.split(".")[0] == "crm":
                offenders.append(f"{filepath}:{node.lineno} → from {node.module} import ...")
        elif isinstance(node, ast.Call):
            func = node.func
            named = (
                (isinstance(func, ast.Attribute) and func.attr == "import_module")
                or (isinstance(func, ast.Name) and func.id in {"__import__", "import_module"})
            )
            if named and node.args and isinstance(node.args[0], ast.Constant):
                target = node.args[0].value
                if isinstance(target, str) and target.split(".")[0] == "crm":
                    offenders.append(f"{filepath}:{node.lineno} → import_module({target!r})")
    return offenders


class CrmIsNotImportedByTheBusinessAppsTest(SimpleTestCase):
    """الاتّجاهُ الثاني للعزل — المقابلُ لِما يحرسه `platform_ops` عن نفسِه.

    `crm` **يستورد** `platform_ops` بإعلانٍ صريح (عنقودُ المنصّة، انظر
    `PLATFORM_CLUSTER_APPS` هناك). والثمنُ المقبولُ لذلك شرطٌ واحدٌ يُحرَس هنا:
    ألّا يستورده أحدٌ من تطبيقات الشركات — فيبقى العنقودُ كلُّه قابلاً للحذف
    دون أن يتوقّف نظامُ الزبائن. أوّلُ استيرادٍ من `sales` أو `accounting`
    لـ`crm` يُلغي هذه الضمانةَ صامتاً لولا هذا الاختبار.
    """

    def test_no_business_app_imports_crm(self):
        offenders = []
        for app in sorted(BUSINESS_APPS):
            root = REPO_ROOT / app
            if not root.is_dir():
                continue
            stack = [root]
            while stack:
                current = stack.pop()
                for entry in sorted(current.iterdir()):
                    if entry.name in PRUNED_DIRS:
                        continue
                    if entry.is_dir():
                        stack.append(entry)
                    elif entry.suffix == ".py":
                        offenders += _inbound_crm_imports(
                            entry.read_text(encoding="utf-8", errors="replace"),
                            entry.relative_to(REPO_ROOT).as_posix(),
                        )
        self.assertEqual(
            offenders, [],
            "تطبيقُ شركاتٍ صار يستورد `crm`، فسقطت ضمانةُ «النظامُ يعمل بلا عنقود "
            "المنصّة»:\n  " + "\n  ".join(offenders),
        )

