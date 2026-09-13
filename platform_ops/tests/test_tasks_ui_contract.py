"""عقدُ واجهةِ مهامِّ موظّفي كترا وملاحظاتِهم (#212 212-E2).

`npm test` هنا يشغّل `utils/*.test.ts` بـ`node --test`: دوالَّ خالصةً **لا تُصيّر
مكوّناً**، و`tsc` لا يفحص صنفَ Tailwind ولا أنّ زرّاً موصولٌ بنقطةٍ ولا أنّ لوحةً
مركَّبة. فالحراسةُ ساكنةٌ بالضرورة.

وثلاثةُ دروسٍ من هذه المواصفة مبنيّةٌ في هذا الملفّ:

1. **المسارُ يُعدّ من الـURLconf لا من قائمةٍ يدويّة** — جدولٌ نصّيٌّ لا يمسّه
   الخادمُ لا يسقط أبداً حين يُعاد تسميةُ مسار؛ يبقى أخضرَ وهو يصف ماضياً.
2. **الاستهلاكُ يُقاس بالنداء من مكوّن** لا بالتصدير في عميل الـAPI (درسُ 212-C:
   خمسُ دوالَّ مُصدَّرةٍ لا يستدعيها أحد، والحارسُ أخضر).
3. **ولكلّ حارسِ واجهةٍ نظيرٌ على الحمولة**: نصٌّ يثبت أنّ المكوّنَ يقرأ حقلاً لا
   يثبت أنّ الخادمَ يرسله. فـ`claimed_count` محروسٌ في المُسلسِل هنا أيضاً.
"""
from pathlib import Path
import re
from unittest import TestCase

from django.urls import get_resolver

from platform_ops.serializers import PlatformTaskSerializer, PlatformWorkspaceNoteSerializer

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend_v2"
STAFF = FRONTEND / "components" / "platform" / "staff"
TASKS_UI = STAFF / "tasks"
API = FRONTEND / "services" / "platformTasksApi.ts"
ADMIN = FRONTEND / "components" / "platform" / "PlatformTasksAdminPanel.tsx"
SHELL = STAFF / "StaffShell.tsx"
DASHBOARD = FRONTEND / "components" / "platform" / "PlatformOpsDashboard.tsx"

#: بادئاتُ 212-E وحدَها من بين مسارات `ops/` الكثيرة.
TASK_ROUTE_PREFIXES = (
    "api/platform/ops/tasks/",
    "api/platform/ops/assignments/",
    "api/platform/ops/submissions/",
    "api/platform/ops/employee-notes/",
    "api/platform/ops/workspace-notes/",
)

#: مسارُ الـURLconf ← دالّةُ العميل التي تنادِيه.
ROUTE_TO_FUNCTION = {
    "/api/platform/ops/tasks/": "listPlatformTasks",
    "/api/platform/ops/tasks/1/": "getPlatformTask",
    "/api/platform/ops/tasks/create/": "createPlatformTask",
    "/api/platform/ops/tasks/1/claim/": "claimPlatformTask",
    "/api/platform/ops/assignments/": "listPlatformTaskAssignments",
    "/api/platform/ops/assignments/1/": "listPlatformTaskAssignments",
    "/api/platform/ops/assignments/1/accept/": "acceptPlatformTaskAssignment",
    "/api/platform/ops/assignments/1/submit/": "submitPlatformTaskAssignment",
    "/api/platform/ops/submissions/": "listPlatformTaskSubmissions",
    "/api/platform/ops/submissions/1/": "listPlatformTaskSubmissions",
    "/api/platform/ops/submissions/1/review/": "reviewPlatformTaskSubmission",
    "/api/platform/ops/employee-notes/": "listPlatformEmployeeNotes",
    "/api/platform/ops/employee-notes/1/": "listPlatformEmployeeNotes",
    "/api/platform/ops/employee-notes/create/": "createPlatformEmployeeNote",
    "/api/platform/ops/workspace-notes/": "listPlatformWorkspaceNotes",
    "/api/platform/ops/workspace-notes/1/": "listPlatformWorkspaceNotes",
    "/api/platform/ops/workspace-notes/create/": "createPlatformWorkspaceNote",
}

#: دالّةٌ مُصدَّرةٌ لا يستدعيها مكوّنٌ **عن قصد**، ولكلٍّ سببُها المكتوب.
UNUSED_BY_DESIGN: dict[str, str] = {
    "listPlatformEmployees":
        "تُستدعى فعلاً من لوحة المدير (منتقيا الموظّف للإسناد وللملاحظة). تبقى "
        "هنا صريحةً لأنّ مسارَ `employees/` ليس من مسارات 212-E فلا يعدّه الجدول "
        "أعلاه، فلو حُذف المنتقيان سقط التعدادُ الثاني لا هذا الاستثناء.",
}


def _task_routes() -> list[str]:
    """مسارات 212-E من محلِّل عناوين جانغو نفسِه — لا قائمةٌ تتقادم بصمت."""

    def walk(patterns, prefix=""):
        for entry in patterns:
            route = prefix + str(entry.pattern)
            if hasattr(entry, "url_patterns"):
                yield from walk(entry.url_patterns, route)
            else:
                yield route

    routes = []
    for route in walk(get_resolver().url_patterns):
        route = route.replace("^", "").replace("$", "")
        if not route.startswith(TASK_ROUTE_PREFIXES):
            continue
        if "format" in route:
            continue
        route = re.sub(r"<int:[^>]+>", "1", route)
        route = re.sub(r"<str:[^>]+>", "x", route)
        route = re.sub(r"\(\?P<\w+>[^)]*\)", "1", route)
        routes.append("/" + route)
    return sorted(set(routes))


def _component_sources() -> dict[str, str]:
    paths = sorted(TASKS_UI.glob("*.tsx")) + [ADMIN]
    return {path.name: path.read_text(encoding="utf-8") for path in paths}


def _exported_api_functions(source: str) -> list[str]:
    return re.findall(r"^export const (\w+)\s*=", source, flags=re.MULTILINE)


def _staff_shell_tasks_section() -> str:
    """قسمُ المفتاح `tasks:` من خريطة لوحات القشرة.

    النهايةُ **تُشتقُّ من الشكل** (المفتاحُ التالي على نفس المستوى) لا تُثبَّت على
    اسمِ مفتاحٍ بعينه: تثبيتُها على `companies:` يجعل الحارسَ يقبل لوحةً مركَّبةً
    في أيّ مكانٍ بمجرّد أن يُعاد ترتيبُ المفاتيح (فـ`find` يعيد `-1`).
    """
    shell = SHELL.read_text(encoding="utf-8")
    start = shell.find("tasks:")
    if start == -1:
        return ""
    following = re.search(r"\n    [A-Za-z_][A-Za-z0-9_]*:", shell[start:])
    return shell[start:start + following.start()] if following else shell[start:]


class TaskRoutesReachTheScreenTest(TestCase):
    def test_the_route_census_matches_the_urlconf_exactly(self):
        routes = set(_task_routes())
        mapped = set(ROUTE_TO_FUNCTION)
        self.assertGreaterEqual(len(routes), 13, f"عددُ مسارات 212-E أقلُّ من المتوقَّع: {sorted(routes)}")
        self.assertEqual(
            routes - mapped, set(),
            f"مسارٌ جديدٌ في الـURLconf بلا دالّةٍ في العميل: {sorted(routes - mapped)}",
        )
        self.assertEqual(
            mapped - routes, set(),
            f"مسارٌ في جدول هذا الاختبار لم يعد في الـURLconf: {sorted(mapped - routes)}",
        )

    def test_every_route_function_is_called_from_a_component(self):
        api_source = API.read_text(encoding="utf-8")
        components = _component_sources()
        missing_definition, missing_caller = [], []
        for route, function in sorted(ROUTE_TO_FUNCTION.items()):
            if not re.search(rf"export const {function}\s*=", api_source):
                missing_definition.append(f"{route} ← {function}")
                continue
            if function in UNUSED_BY_DESIGN:
                continue
            if not any(re.search(rf"\b{function}\s*\(", source) for source in components.values()):
                missing_caller.append(f"{route} ← {function}")
        self.assertEqual(missing_definition, [], f"مساراتٌ بلا دالّةٍ في عميل الـAPI: {missing_definition}")
        self.assertEqual(
            missing_caller, [],
            f"مساراتٌ في العميل لا **يستدعيها** مكوّن: {missing_caller} — بابٌ مسدود: "
            "الفعلُ يُرسَل ولا شاشةَ تُظهره.",
        )

    def test_every_exported_api_function_is_called_or_excused(self):
        """التعدادُ الثاني: دالّةٌ تشترك في مسارٍ مع غيرها لا تفلت من التعداد الأوّل."""
        components = _component_sources()
        orphans = [
            function for function in _exported_api_functions(API.read_text(encoding="utf-8"))
            if function not in UNUSED_BY_DESIGN
            and not any(re.search(rf"\b{function}\s*\(", source) for source in components.values())
        ]
        self.assertEqual(orphans, [], f"دوالُّ مُصدَّرةٌ لا يستدعيها مكوّنٌ ولا سببَ مكتوباً لذلك: {orphans}")

    def test_every_written_excuse_is_a_real_reason(self):
        for function, reason in UNUSED_BY_DESIGN.items():
            with self.subTest(function=function):
                self.assertGreater(len(reason.strip()), 40)


class BothPanelsAreMountedTest(TestCase):
    """لوحةٌ مبنيّةٌ غيرُ مركَّبةٍ شاشةٌ ميّتة — وقد حدث مرّتين في هذه المواصفة."""

    def test_the_staff_panel_is_mounted_inside_the_tasks_tab(self):
        section = _staff_shell_tasks_section()
        self.assertNotEqual(section, "", "لم يُعثر على المفتاح `tasks:` في خريطة لوحات القشرة.")
        self.assertIn(
            "<StaffTasksPanel", section,
            "تبويبُ مهامِّ الموظّف لا يُصيّر `StaffTasksPanel` — لوحةٌ مبنيّةٌ لا تُرى.",
        )

    def test_the_admin_panel_is_mounted_in_the_command_centre(self):
        dashboard = DASHBOARD.read_text(encoding="utf-8")
        self.assertIn("<PlatformTasksAdminPanel", dashboard)
        self.assertIn(
            'activeTab === "staff_tasks"', dashboard,
            "لوحةُ المدير مستوردةٌ بلا تبويبٍ يعرضها.",
        )
        self.assertIn('setActiveTab("staff_tasks")', dashboard, "لا زرَّ يفتح تبويبَ مهامّ الموظّفين.")


class TheOwnersRulesShowOnTheScreenTest(TestCase):
    """قاعدةُ الخادم تظهر قبل الضغط لا تُفاجئ بعده."""

    def setUp(self):
        self.admin = ADMIN.read_text(encoding="utf-8")
        self.staff = (TASKS_UI / "StaffTasksPanel.tsx").read_text(encoding="utf-8")

    def test_review_notes_are_required_on_the_two_decisions_that_demand_them(self):
        for decision in ("APPROVED_FULL", "APPROVED_PARTIAL", "REJECTED"):
            self.assertIn(decision, self.admin, f"قرارُ المراجعة `{decision}` غائبٌ عن الشاشة.")
        field_start = self.admin.find('id="task-reviewer-notes"')
        self.assertNotEqual(field_start, -1, "حقلُ ملاحظات المراجعة بلا معرِّفٍ يُحرَس.")
        self.assertIn(
            "required", self.admin[max(0, field_start - 400):field_start + 100],
            "حقلُ الملاحظات غيرُ إلزاميٍّ في الواجهة والخادمُ يرفض بدونه — رسالةُ "
            "خطأٍ بعد الضغط مكان منعٍ قبله.",
        )

    def test_the_employee_sees_the_managers_decision_and_notes(self):
        """الرفضُ يحذف إسنادَ المجمَع، فقرارٌ معروضٌ على الإسناد وحدَه يختفي معه.

        وموظّفٌ أُعيد إليه عملُه ولا يرى السببَ هو بعينه العيبُ الذي تمنعه هذه
        المرحلة، فيُحرَس أنّ سجلَّ التسليمات نفسَه يحمل القرارَ وملاحظتَه.
        """
        missing = [
            needle for needle in ("reviewer_notes", "decision_display", "submissions.map")
            if needle not in self.staff
        ]
        self.assertEqual(
            missing, [],
            f"شاشةُ الموظّف لا تعرض {missing} — ورفضُ مهمّةِ مجمَعٍ يحذف الإسنادَ، "
            "فقرارٌ معروضٌ عليه وحدَه يختفي معه ويبقى الموظّفُ بلا سبب. "
            "(`submissions.map` سجلُّ التسليمات المستقلُّ عن الإسناد.)",
        )

    def test_the_partial_approval_says_the_work_continues(self):
        self.assertIn(
            "العمل مستمرّ", self.admin,
            "«مقبول بس لسّا ما خلص» لا يقول للمدير إنّ الإسنادَ يعود قيدَ التنفيذ.",
        )

    def test_the_rejection_says_the_task_returns_open(self):
        self.assertRegex(
            self.admin, r"الرفض يعيد[^<]*المجمّع",
            "تأكيدُ الرفض لا يقول إنّ المهمّةَ تعود مفتوحة — وهو قرارُ المالك الصريح.",
        )


class TheCountsComeFromTheServerTest(TestCase):
    """نظيرُ الحمولةِ لحارسِ الواجهة.

    عدُّ المطالبين في الواجهة من قائمة إسنادات الموظّف **صفرٌ بحكم البناء**:
    القائمةُ مقصورةٌ عليه، وبطاقةُ المجمَع لا تُعرَض إلا لمن لا إسنادَ له. فالرقمُ
    من الخادم، ويُحرَس في الطرفين.
    """

    def test_the_task_payload_carries_the_claimed_count(self):
        self.assertIn(
            "claimed_count", PlatformTaskSerializer.Meta.fields,
            "حمولةُ المهمّة بلا `claimed_count` — الواجهةُ تقرأ حقلاً لا يُرسَل.",
        )

    def test_the_pool_card_reads_that_field_and_not_a_local_tally(self):
        staff = (TASKS_UI / "StaffTasksPanel.tsx").read_text(encoding="utf-8")
        self.assertTrue(
            "task.claimed_count" in staff,
            "بطاقةُ المجمَع لا تقرأ `task.claimed_count` من الحمولة.",
        )
        self.assertNotRegex(
            staff, r"assignments\.filter\([^)]*\)\.length",
            "عدٌّ محلّيٌّ من قائمة الإسنادات — وهي مقصورةٌ على الموظّف فالناتجُ صفرٌ دائماً.",
        )

    def test_the_workspace_note_payload_names_its_writer_and_task(self):
        """لوحةُ المدير تعرض كاتبَ الملاحظة ومهمّتَها — ومعرَّفٌ عدديٌّ لا يُقرأ."""
        for field in ("employee_name", "task_title"):
            self.assertIn(field, PlatformWorkspaceNoteSerializer.Meta.fields, f"`{field}` غائبٌ عن الحمولة.")


class TaskPanelsFollowRepoStyleTest(TestCase):
    def test_no_browser_dialogs(self):
        offenders = []
        for name, source in _component_sources().items():
            for call in ("window.prompt(", "window.confirm(", "window.alert(", " alert(", "\talert("):
                if call in source:
                    offenders.append(f"{name}: {call.strip()}")
        self.assertEqual(
            offenders, [],
            f"حوارُ متصفّحٍ مكان `useToast`/`useConfirm`: {offenders} — لا يُنسَّق ولا "
            "يحمل RTL، ويحجبه بعضُ المتصفّحات صامتاً فيبدو الزرُّ معطوباً.",
        )

    def test_no_inline_styles_and_no_locale_formatters(self):
        offenders = []
        for name, source in _component_sources().items():
            for forbidden in ("style={{", "toLocaleString", "toLocaleDateString", "toLocaleTimeString"):
                if forbidden in source:
                    offenders.append(f"{name}: {forbidden}")
        self.assertEqual(
            offenders, [],
            f"أنماطٌ سطريّةٌ أو تنسيقٌ محلّيٌّ (يُخرج تقويماً هجريّاً بالعربية): {offenders}",
        )

    def test_the_staff_panel_keeps_the_dark_shell_tokens(self):
        staff = (TASKS_UI / "StaffTasksPanel.tsx").read_text(encoding="utf-8")
        for token in ("var(--staff-panel)", "var(--staff-line)", "var(--staff-text)", "var(--staff-muted)"):
            self.assertIn(token, staff, f"لوحةُ الموظّف لا تستعمل `{token}` — القشرةُ داكنةٌ بقرار المالك.")
        offenders = [cls for cls in re.findall(r'className="([^"]*)"', staff) if "bg-white" in cls]
        self.assertEqual(offenders, [], f"سطحٌ فاتحٌ داخل القشرة الداكنة: {offenders}")
