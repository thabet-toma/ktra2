"""حارس عزل وحدة عمليات المنصة (`platform_ops`) — بالاتّجاهين.

قاعدتان:
1. الوارد — لا ملفّ خارج الوحدة يستوردها. (التسجيل في `INSTALLED_APPS` و`include()` ذكرٌ نصّيّ لا استيراد.)
2. الصادر — لا تستورد الوحدة من المنصّة إلا ما في القائمة البيضاء الصريحة لما هو مستعملٌ في المرحلة الأولى فعلاً.
"""
import ast
from pathlib import Path
import shutil
import tempfile

from django.test import SimpleTestCase

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

#: مجلدات لا تُفحَص إطلاقاً: مولَّدة أو غير متتبَّعة أو خارج المشروع.
PRUNED_DIRS = {
    "venv", ".venv", "node_modules", "__pycache__", ".git", ".claude",
    ".multica", ".pytest_cache", "dist", "test-results", ".clone",
    ".agent_context", "playwright-report",
}

#: حزم المنصة التي تخضع للفحص.
PLATFORM_PACKAGES = frozenset({
    "accountant_portal", "accounting", "after_sales", "bridge", "core",
    "device_registry", "docshare", "employee_ops", "hr", "import_file",
    "inventory", "logistics", "partners", "realestate", "sales", "store",
    "tenants",
})

#: القائمة البيضاء الصريحة — ما تستورده الوحدة فعلاً في المرحلتين الأولى والثانية.
ALLOWLISTED_PLATFORM_MODULES = frozenset({
    "core.platform_admin_api",  # IsPlatformAdmin لحراسة الصلاحيات
    "core.signals",             # company_member_changed إشارة تغيير عضوية الشركة
    "tenants.models",           # Tenant وUserCompanyMembership
})

def check_source_for_disallowed_imports(source: str, filepath: str = "<string>") -> list[str]:
    """تفحص نص كود بايثون وتستخرج أي استيراد لحزم المنصة خارج القائمة البيضاء."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    def allowed(dotted: str) -> bool:
        return any(
            dotted == entry or dotted.startswith(f"{entry}.")
            for entry in ALLOWLISTED_PLATFORM_MODULES
        )

    violations = []
    for node in ast.walk(tree):
        # الاستيراد الديناميكي
        if isinstance(node, ast.Call):
            func = node.func
            name = None
            if isinstance(func, ast.Attribute) and func.attr == "import_module":
                name = "importlib.import_module"
            elif isinstance(func, ast.Name) and func.id == "__import__":
                name = "__import__"
            if name and node.args and isinstance(node.args[0], ast.Constant):
                target = node.args[0].value
                if (
                    isinstance(target, str)
                    and target.split(".")[0] in PLATFORM_PACKAGES
                    and not allowed(target)
                ):
                    violations.append(f"{filepath}:{node.lineno} → {name}({target!r})")
            continue
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in PLATFORM_PACKAGES and not allowed(alias.name):
                    violations.append(f"{filepath}:{node.lineno} → import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.level or not node.module:
                continue  # استيراد نسبي داخل الوحدة نفسها
            if node.module.split(".")[0] not in PLATFORM_PACKAGES:
                continue
            for alias in node.names:
                if allowed(node.module) or allowed(f"{node.module}.{alias.name}"):
                    continue
                violations.append(
                    f"{filepath}:{node.lineno} → from {node.module} import {alias.name}"
                )
    return violations


def check_source_for_inbound_imports(source: str, filepath: str = "<string>") -> list[str]:
    """تستخرج كل استيراد صريح أو ديناميكي لـplatform_ops من ملف خارجي."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    importlib_module_names = set()
    import_module_function_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "importlib":
                    importlib_module_names.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module == "importlib":
            for alias in node.names:
                if alias.name == "import_module":
                    import_module_function_names.add(alias.asname or alias.name)

    offenders = []
    for node in ast.walk(tree):
        target = None
        rendered = None
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] == "platform_ops":
                    offenders.append(
                        f"{filepath}:{node.lineno} → import {alias.name}"
                    )
            continue
        if isinstance(node, ast.ImportFrom):
            if not node.level and node.module and node.module.split(".")[0] == "platform_ops":
                offenders.append(
                    f"{filepath}:{node.lineno} → from {node.module} import ..."
                )
            continue
        if isinstance(node, ast.Call):
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "import_module"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id in importlib_module_names
            ):
                rendered = "importlib.import_module"
            elif isinstance(node.func, ast.Name):
                if node.func.id == "__import__":
                    rendered = "__import__"
                elif node.func.id in import_module_function_names:
                    rendered = node.func.id
            if rendered and node.args and isinstance(node.args[0], ast.Constant):
                target = node.args[0].value
            if isinstance(target, str) and target.split(".")[0] == "platform_ops":
                offenders.append(
                    f"{filepath}:{node.lineno} → {rendered}({target!r})"
                )
    return offenders


def _walk_py_files(root: Path):
    """كل ملفات .py تحت root مع تقليم PRUNED_DIRS."""
    if root.is_file():
        if root.suffix == ".py":
            yield root
        return
    if not root.is_dir():
        return
    for entry in sorted(root.iterdir()):
        if entry.name in PRUNED_DIRS:
            continue
        yield from _walk_py_files(entry)


def find_inbound_import_offenders(repo_root: Path) -> list[str]:
    """أسطر الاستيراد المخالفة للقاعدة الأولى تحت repo_root، خارج الوحدة نفسها."""
    offenders = []
    for entry in sorted(repo_root.iterdir()):
        if entry.name in PRUNED_DIRS or entry.name == "platform_ops":
            continue
        for path in _walk_py_files(entry):
            try:
                source = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            rel = path.relative_to(repo_root).as_posix()
            offenders.extend(check_source_for_inbound_imports(source, rel))
    return offenders


class PlatformOpsIsolationGuardTest(SimpleTestCase):
    """حارس عزل وحدة عمليات المنصة."""

    def test_no_platform_module_imports_platform_ops(self):
        """لا يجوز لأي ملف خارج `platform_ops` استيرادها."""
        offenders = find_inbound_import_offenders(REPO_ROOT)
        self.assertEqual(
            offenders, [],
            "مخالفة لقاعدة العزل: وُجدت استيرادات لـ platform_ops من خارجها:\n  "
            + "\n  ".join(offenders),
        )

    def test_platform_ops_imports_only_allowlisted_platform_modules(self):
        """لا يجوز لـ `platform_ops` استيراد إلا ما في القائمة البيضاء المعلنة للمرحلة الأولى."""
        violations = []
        for path in _walk_py_files(REPO_ROOT / "platform_ops"):
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            violations.extend(
                check_source_for_disallowed_imports(
                    content, filepath=path.relative_to(REPO_ROOT).as_posix()
                )
            )
        self.assertEqual(
            violations, [],
            "الوحدة معزولة عمداً — القائمة البيضاء محدودة بما تحتاجه المرحلة الأولى فقط:\n  "
            + "\n  ".join(violations),
        )

    def test_inbound_guard_catches_a_synthetic_violation(self):
        """الحارس الوارد يسقط على خرق مصطنع."""
        root = Path(tempfile.mkdtemp())
        try:
            (root / "manage.py").write_text(
                "import platform_ops\n", encoding="utf-8",
            )
            deep = root / "sales" / "sub"
            deep.mkdir(parents=True)
            (deep / "views.py").write_text(
                "from platform_ops.models import PlatformEmployee\n", encoding="utf-8",
            )
            # ذكر نصي مسموح
            (root / "settings.py").write_text(
                "APPS = ['platform_ops.apps.PlatformOpsConfig']\n", encoding="utf-8",
            )
            # ملفات الوحدة نفسها خارج القاعدة الأولى
            (root / "platform_ops").mkdir()
            (root / "platform_ops" / "views.py").write_text(
                "from platform_ops.models import PlatformEmployee\n", encoding="utf-8",
            )

            offenders = find_inbound_import_offenders(root)
            self.assertEqual(
                sorted(o.split(":")[0] for o in offenders),
                ["manage.py", "sales/sub/views.py"],
                f"الحارس الوارد لم يلتقط ما يجب أو التقط ما لا يجب: {offenders}",
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_inbound_guard_catches_dynamic_imports(self):
        """الاستيراد الديناميكي من خارج الوحدة خرقٌ كالصريح تماماً."""
        root = Path(tempfile.mkdtemp())
        try:
            (root / "worker.py").write_text(
                'import importlib\n'
                'from importlib import import_module as load_module\n'
                'x = importlib.import_module("platform_ops.models")\n'
                'y = __import__("platform_ops.services")\n'
                'z = load_module("platform_ops.permissions")\n',
                encoding="utf-8",
            )

            offenders = find_inbound_import_offenders(root)
            self.assertEqual(len(offenders), 3, offenders)
            self.assertTrue(all(item.startswith("worker.py:") for item in offenders))
            self.assertTrue(any("platform_ops.models" in item for item in offenders))
            self.assertTrue(any("platform_ops.services" in item for item in offenders))
            self.assertTrue(any("platform_ops.permissions" in item for item in offenders))
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_outbound_guard_catches_a_synthetic_violation(self):
        """الحارس الصادر يسقط على استيراد خارج القائمة البيضاء، ويقبل ما فيها."""
        violations = check_source_for_disallowed_imports(
            "from accounting.models import Account\nimport employee_ops.models\n",
            filepath="synthetic.py",
        )
        self.assertEqual(len(violations), 2, violations)
        self.assertIn("accounting.models", violations[0])
        self.assertIn("employee_ops.models", violations[1])

        self.assertEqual(
            check_source_for_disallowed_imports(
                "from core.platform_admin_api import IsPlatformAdmin\nfrom tenants.models import Tenant\n"
            ),
            [],
        )

    def test_dynamic_import_does_not_slip_past_the_guard(self):
        """الاستيراد الديناميكي لحزم غير مسموحة مخالفة كالاستيراد الصريح."""
        violations = check_source_for_disallowed_imports(
            'import importlib\nx = importlib.import_module("employee_ops.models")\n'
            'y = __import__("accounting.models")\n',
            filepath="synthetic.py",
        )
        self.assertEqual(len(violations), 2, violations)
        self.assertIn("employee_ops.models", violations[0])
        self.assertIn("accounting.models", violations[1])

        # والمسموح ديناميكياً يبقى مسموحاً
        self.assertEqual(
            check_source_for_disallowed_imports(
                'import importlib\nimportlib.import_module("tenants.models")\n'
            ),
            [],
        )
