"""حارس عزل وحدة متابعة الموظفين (`employee_ops`) — بالاتّجاهين.

**لماذا يوجد هذا الملف:** الوحدة معزولة عمداً حمايةً لاستقرار المنصة — عطلٌ في
متابعة الموظفين يجب ألّا يوقف الفواتير ولا حركة المخزون ولا المحاسبة. والعزلُ
يُبنى ولا يُضاف: زحفُ الاعتماد بعد ستّة أشهر لا يراه أحد بلا حارس.

قاعدتان:

1. **الوارد** — لا ملفّ خارج الوحدة يستوردها. (التسجيل في `INSTALLED_APPS`
   و`include()` ذكرٌ **نصّيّ** لا استيراد، وهو مقصود ومسموح.)
2. **الصادر** — لا تستورد الوحدة من المنصّة إلا ما في القائمة البيضاء الصريحة.

**والقائمة البيضاء تُذكر بما هو مستعملٌ اليوم فقط.** قائمةٌ موسَّعةٌ سلفاً تُفرِغ
الحارس من معناه: كلُّ اسمٍ يُضاف إليها يجب أن يكون قراراً يُناقَش، لا سطراً يمرّ.

**ولماذا هذا الحارس مع وجود `.importlinter`:** ذلك يُشغَّل بأمرٍ منفصل
(`lint-imports`) **ليس في بوّابة pytest**، وهو يحرس الاتّجاه الصادر وحده. القاعدة
الأولى هنا (لا أحد يستوردنا) لا يعبّر عنها عقدٌ هناك، والبوّابةُ هي ما يُشغَّل فعلاً.
"""
import ast
import re
from pathlib import Path

from django.test import SimpleTestCase

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

#: مجلدات لا تُفحَص إطلاقاً: مولَّدة أو غير متتبَّعة أو خارج المشروع.
PRUNED_DIRS = {
    "venv", ".venv", "node_modules", "__pycache__", ".git", ".claude",
    ".multica", ".pytest_cache", "dist", "test-results", ".clone",
    ".agent_context", "playwright-report",
}

#: حزم المستودع — ما جذرُه واحدٌ منها يخضع للقائمة البيضاء، وما عداه (المكتبة
#: القياسية وجانغو وDRF) خارج نطاق الحارس.
PLATFORM_PACKAGES = frozenset({
    "accountant_portal", "accounting", "after_sales", "bridge", "core",
    "device_registry", "docshare", "hr", "import_file", "inventory",
    "logistics", "partners", "realestate", "sales", "store", "tenants",
})

#: القائمة البيضاء الصريحة — **ما تستورده الوحدة فعلاً اليوم، لا ما قد تحتاجه**.
ALLOWLISTED_PLATFORM_MODULES = frozenset({
    "core.access",        # `require_perm`
    # سجلّ النشاط **غير الحاظر**: عقدُ `core.models.ActivityLog` يمنع الكتابة
    # المباشرة، وفشلُ تسجيلٍ داخل معاملةٍ كان سيُسقط إنشاءَ الموظف.
    "core.activity",      # `log_activity`
    "core.api_defaults",  # `ApiAuthAndUser`
    # مدى التاريخ **المصدرُ الموحَّد**: `timestamp__date=...` يُعيد صفر صفوفٍ بصمت
    # على MySQL حين تكون جداولُ المناطق الزمنيّة فارغة، وهذه الدالّة تتجنّبه.
    "core.date_ranges",   # `filter_local_date_range`
    # مخنقُ الرفع الوحيد في المنصة. بوابةُ التوظيف تحتاج رفعاً، و**مسارُ رفعٍ
    # ثانٍ** كان يعني محاسبةَ تخزينٍ ناقصةً للشركة: هناك وحده يُكتب
    # `core.TenantAsset`. والوحدةُ تستدعيه بعد فحصِها الصارم لا قبله.
    "core.media_views",   # `upload_media_file` و`MediaUploadError`
    "core.models",        # `TenantModule` في الاختبارات
    "core.modules",       # `require_module`
    # حدُّ المقاعد يعيش في محرّك الحدود بحكم بنيته، والوحدة تستدعيه عند الإنشاء
    # والدعوة والقبول. **يُستورَد صراحةً**: إخفاءُ الاستيراد عن الحارس
    # (`importlib.import_module`) أسوأُ من إعلانه — يجعل الحارس يكذب بدل أن يحرس.
    "core.plans",         # `enforce_limits` وتوابعها
    "hr.models",          # `Employee`
    "tenants.models",     # `Tenant` والعضويّة
    "tenants.services",   # `create_company` في الاختبارات
})

#: تعبير القاعدة الأولى: استيرادٌ حقيقيّ للوحدة، لا ذكرٌ نصّيّ لاسمها.
INBOUND_IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+employee_ops\b")


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
        # الاستيرادُ الديناميكيّ يُفحص كالساكن. **ليس افتراضاً**: وكيلٌ مفوَّضٌ
        # احتاج `core.plans` فكتب `importlib.import_module("core.plans")` بدل أن
        # يُعلنها، فمرّ من الحارس. إخفاءُ الاستيراد أسوأُ من إعلانه — يجعل
        # الحارسَ يكذب بدل أن يحرس.
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


def _walk_py_files(root: Path):
    """كلّ ملفّات `.py` تحت `root` مع تقليم `PRUNED_DIRS`.

    و`root` قد يكون ملفّاً مفرداً: `manage.py` في جذر المستودع كان يُتخطّى بصمت
    حين كانت الدالّة تعود فارغةً لغير المجلّدات — ثغرةٌ في الحارس نفسه.
    """
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
    """أسطرُ الاستيراد المخالفة للقاعدة الأولى تحت `repo_root`، خارج الوحدة نفسها."""
    offenders = []
    for entry in sorted(repo_root.iterdir()):
        if entry.name in PRUNED_DIRS or entry.name == "employee_ops":
            continue
        for path in _walk_py_files(entry):
            try:
                lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for lineno, line in enumerate(lines, 1):
                if INBOUND_IMPORT_RE.search(line):
                    rel = path.relative_to(repo_root).as_posix()
                    offenders.append(f"{rel}:{lineno} → {line.strip()}")
    return offenders


class EmployeeOpsIsolationGuardTest(SimpleTestCase):
    """حارس عزل الوحدة عن بقية المنصة."""

    def test_no_platform_module_imports_employee_ops(self):
        """لا يجوز لأي ملف خارج `employee_ops` استيرادها."""
        offenders = find_inbound_import_offenders(REPO_ROOT)
        self.assertEqual(
            offenders, [],
            "مخالفة لقاعدة العزل: وُجدت استيرادات لـ employee_ops من خارجها:\n  "
            + "\n  ".join(offenders),
        )

    def test_employee_ops_imports_only_allowlisted_platform_modules(self):
        """لا يجوز لـ `employee_ops` استيراد إلا ما في القائمة البيضاء المعلنة."""
        violations = []
        for path in _walk_py_files(REPO_ROOT / "employee_ops"):
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
            "الوحدة معزولة عمداً — إن لزمك استيرادٌ جديد فهو قرارٌ يُناقَش لا سطرٌ يُضاف:\n  "
            + "\n  ".join(violations),
        )

    def test_inbound_guard_catches_a_synthetic_violation(self):
        """الحارس الوارد يسقط على خرقٍ مصطنَع — **في الجذر وفي العمق معاً**.

        تأكيدٌ لا يستطيع السقوط ليس تأكيداً: بدون هذا الاختبار كان ماشي الشجرة
        يتخطّى ملفّات الجذر ويبقى أخضر.
        """
        import shutil
        import tempfile

        root = Path(tempfile.mkdtemp())
        try:
            (root / "manage.py").write_text(
                "import employee_ops\n", encoding="utf-8",
            )
            deep = root / "sales" / "sub"
            deep.mkdir(parents=True)
            (deep / "views.py").write_text(
                "from employee_ops.models import X\n", encoding="utf-8",
            )
            # ذكرٌ نصّيّ مسموح — يجب ألّا يُحسب مخالفة.
            (root / "settings.py").write_text(
                "APPS = ['employee_ops.apps.EmployeeOpsConfig']\n", encoding="utf-8",
            )
            # ملفّات الوحدة نفسها خارج القاعدة الأولى.
            (root / "employee_ops").mkdir()
            (root / "employee_ops" / "views.py").write_text(
                "from employee_ops.models import Y\n", encoding="utf-8",
            )

            offenders = find_inbound_import_offenders(root)
            self.assertEqual(
                sorted(o.split(":")[0] for o in offenders),
                ["manage.py", "sales/sub/views.py"],
                f"الحارس الوارد لم يلتقط ما يجب أو التقط ما لا يجب: {offenders}",
            )
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_outbound_guard_catches_a_synthetic_violation(self):
        """الحارس الصادر يسقط على استيرادٍ خارج القائمة البيضاء، ويقبل ما فيها."""
        violations = check_source_for_disallowed_imports(
            "from accounting.models import Account\nimport sales.services\n",
            filepath="synthetic.py",
        )
        self.assertEqual(len(violations), 2, violations)
        self.assertIn("accounting.models", violations[0])
        self.assertIn("sales.services", violations[1])

        self.assertEqual(
            check_source_for_disallowed_imports(
                "from core.access import require_perm\nfrom tenants.models import Tenant\n"
            ),
            [],
        )

    def test_dynamic_import_does_not_slip_past_the_guard(self):
        """`importlib.import_module("sales.services")` مخالفةٌ كالاستيراد الصريح.

        هذه الثغرةُ استُعملت فعلاً في هذا المستودع لا افتراضاً: احتاج منفِّذٌ
        `core.plans` فاستوردها ديناميكياً بدل أن يُعلنها في القائمة البيضاء.
        """
        violations = check_source_for_disallowed_imports(
            'import importlib\nx = importlib.import_module("sales.services")\n'
            'y = __import__("accounting.models")\n',
            filepath="synthetic.py",
        )
        self.assertEqual(len(violations), 2, violations)
        self.assertIn("sales.services", violations[0])
        self.assertIn("accounting.models", violations[1])

        # والمسموحُ ديناميكياً يبقى مسموحاً — الحارس يفحص الوجهة لا الأسلوب.
        self.assertEqual(
            check_source_for_disallowed_imports(
                'import importlib\nimportlib.import_module("core.plans")\n'
            ),
            [],
        )
