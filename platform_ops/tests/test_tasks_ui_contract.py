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

from platform_ops.models import PlatformEmployee, PlatformTaskAttachment
from platform_ops.serializers import (
    PlatformEmployeeNoteSerializer,
    PlatformTaskSerializer,
    PlatformWorkspaceNoteSerializer,
)

ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend_v2"
STAFF = FRONTEND / "components" / "platform" / "staff"
TASKS_UI = STAFF / "tasks"
API = FRONTEND / "services" / "platformTasksApi.ts"
ADMIN = FRONTEND / "components" / "platform" / "PlatformTasksAdminPanel.tsx"
SHELL = STAFF / "StaffShell.tsx"
DASHBOARD = FRONTEND / "components" / "platform" / "PlatformOpsDashboard.tsx"
#: بطاقةُ الشخص ودرجُ ملفّه — موضعا 212-O1 · O2.
CARD = FRONTEND / "components" / "platform" / "EmployeeCard.tsx"
PROFILE_DRAWER = FRONTEND / "components" / "platform" / "EmployeeProfileDrawer.tsx"

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
    # #213-ب: ملفُّ المهمّة — مرفقاتُه وخيطُه، ولوحُ المدير.
    "/api/platform/ops/tasks/1/attachments/": "uploadPlatformTaskAttachment",
    "/api/platform/ops/tasks/1/attachments/1/download/": "getPlatformTaskAttachmentFile",
    "/api/platform/ops/tasks/1/thread/": "getPlatformTaskThread",
    "/api/platform/ops/tasks/board/": "getPlatformTaskBoard",
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
        # صفُّ التبويبات صار `CcTabs` يقرأ قائمةً معطاة، فلم يعد لكلّ تبويبٍ
        # نداءُ `setActiveTab("…")` باسمه. والمقيسُ الآن الوصلُ نفسُه: المفتاحُ
        # موجودٌ في القائمة، والقائمةُ مركَّبةٌ بمبدِّلٍ يكتب الحالة. وكتابةُ فرعٍ
        # ميّتٍ يحمل النصَّ القديمَ لإرضاء هذا السطر مرّت فعلاً — فلا يُقاس النصّ.
        self.assertIn('{ key: "staff_tasks"', dashboard, "لا تبويبَ لمهامّ الموظّفين في قائمة التبويبات.")
        self.assertRegex(
            dashboard,
            r"<CcTabs[\s\S]{0,300}onChange=\{\(key\) => setActiveTab",
            "قائمةُ التبويبات غيرُ موصولةٍ بمبدِّل الحالة — تبويبٌ لا يُفتح.",
        )


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

    # النصُّ **معروضاً على الشاشة ومشروطاً بالقرار المختار**، لا موجوداً في الملفّ:
    # السقوطُ الذي يحرسه هذان التأكيدان وقع فعلاً — حُذف التحذيرُ الظاهرُ قبل الضغط
    # وبقيت عبارتُه في نخبِ النجاح وحوارِ التأكيد **بعده**، فمرّ `assertIn` على
    # الملفّ كلِّه بينما المديرُ صار لا يعرف أثرَ قرارِه إلّا وقد وقع.
    # ‏`>[^<>{}]*` يقصُر المطابقةَ على نصِّ JSX: نصٌّ داخل `toast(...)` يفصله عن أقرب
    # `>` قبله قوسٌ معقوفٌ من جسم الدالّة، فلا يطابق.
    def test_the_partial_approval_says_the_work_continues_before_the_click(self):
        self.assertRegex(
            self.admin,
            r"reviewDecision === 'APPROVED_PARTIAL' &&[^{}]*>[^<>{}]*العمل مستمرّ",
            "«مقبول بس لسّا ما خلص» لا يقول للمدير — قبل الضغط — إنّ الإسنادَ يعود "
            "قيدَ التنفيذ.",
        )

    def test_the_rejection_says_the_task_returns_open_before_the_click(self):
        self.assertRegex(
            self.admin,
            r"reviewDecision === 'REJECTED' &&[^{}]*>[^<>{}]*الرفض يعيد[^<>{}]*المجمّع",
            "تحذيرُ الرفض لا يقول — قبل الضغط — إنّ المهمّةَ تعود مفتوحة، وهو قرارُ "
            "المالك الصريح.",
        )


class TheTaskFileScreensSayTheTruthTest(TestCase):
    """أربعةُ حرّاسٍ وُلدوا من قراءة الفرق النهائيّ لعمل الوكيل (#213-ب).

    كلُّها مرّت من تحت بوّابةٍ خضراء: `tsc` لا يقرأ نصّاً عربيّاً على شارة،
    ولا يعرف أنّ حالةً واحدةً تحمل معرّفَي جدولين، ولا أنّ صفّاً بلا عنصرٍ
    قابلٍ للتبئير يقطع من لا يستعمل الفأرة.
    """

    def setUp(self):
        self.admin = ADMIN.read_text(encoding="utf-8")
        self.staff = (TASKS_UI / "StaffTasksPanel.tsx").read_text(encoding="utf-8")
        self.drawer = (TASKS_UI / "TaskFileDrawer.tsx").read_text(encoding="utf-8")

    def test_the_brief_files_go_up_with_the_task_not_after_it(self):
        """«يرفق صور وملفات شرح **مع** المهمة» — لا بعد إنشائها بشاشتين.

        الإسنادُ يقع لحظةَ الإنشاء ويصل الموظّفَ فوراً؛ فنموذجٌ بلا حقل ملفٍّ
        يعني أنّ البلاغَ يسبق الشرحَ دائماً، ويبقى الموظّفُ ينظر إلى مهمّةٍ بلا
        ما يشرحها حتى يعود المديرُ ويفتح ملفَّها.
        """
        violations = []
        if 'type="file" multiple' not in self.admin:
            violations.append("نموذجُ الإنشاء بلا حقلِ ملفّات شرح")
        if not re.search(r"uploadPlatformTaskAttachment\(created\.id", self.admin):
            violations.append("الملفّاتُ لا تُرفَع على المهمّة التي أنشأها الطلبُ نفسُه")
        self.assertEqual(violations, [], f"الشرحُ يأتي بعد المهمّة لا معها: {violations}")

    def test_mandatory_is_not_read_as_personal(self):
        """«شخصيّةٌ لا عامّة» نطاقُ الإسناد، و«لا تُردّ» إجباريّتُه — شرطان.

        و`is_mandatory` صادقةٌ للجماعيّةِ التي وسمها المديرُ إجباريّةً أيضاً،
        فقراءتُها «شخصيّة» تجعل البطاقةَ تقول «جماعية» و«شخصية» في سطرٍ واحد.
        """
        badge = re.search(r"\{assignment\.is_mandatory \? '([^']*)' : '([^']*)'\}", self.staff)
        self.assertIsNotNone(badge, "شارةُ الإجباريّة غابت عن بطاقة المهمّة.")
        for word in ("شخصي", "خاصة"):
            self.assertNotIn(
                word, badge.group(1),
                "شارةُ الإجباريّة تقول إنّ المهمّةَ شخصيّة — والجماعيّةُ تكون إجباريّةً "
                "أيضاً، فالشخصيّةُ تُقرأ من `task_audience` وحدَه.",
            )
        self.assertIn(
            "assignment.task_audience === 'INDIVIDUAL'", self.staff,
            "لا شيءَ يقرأ نطاقَ الإسناد — فلا سبيلَ للتمييز بين شخصيّةٍ وعامّة.",
        )

    def test_employee_status_is_compared_against_the_value_the_server_sends(self):
        """رمزُ الحالة صغيرٌ (`active`) — ومقارنتُه بكبيرٍ تكذب على كلّ صفّ.

        كان `employeeLabel` يقارن `'ACTIVE'` و`'SUSPENDED'`، وقيمُ
        `PlatformEmployee.Status` صغيرةٌ ولا `suspended` فيها أصلاً — فوسم
        **كلُّ** موظّفٍ «(خارج الخدمة)» في منتقي إنشاء المهمّة، بلا خطأٍ ولا
        حارسٍ أحمر.
        """
        values = {value for value, _label in PlatformEmployee.Status.choices}
        offenders = [
            literal for literal in re.findall(r"employee\.status === '([^']+)'", self.admin)
            if literal not in values
        ]
        offenders += [
            literal for literal in re.findall(r"employee_status !== '([^']+)'", self.admin)
            if literal not in values
        ]
        self.assertEqual(
            offenders, [],
            f"حالةُ موظّفٍ تُقارَن بقيمةٍ لا يرسلها الخادم: {offenders} — "
            f"والقيمُ {sorted(values)}.",
        )

    def test_one_busy_key_does_not_mix_two_tables_ids(self):
        """حالةُ `busy` واحدةٌ: إسنادٌ رقمُه ٥ ومهمّةٌ رقمُها ٥ ليسا شيئاً واحداً.

        وأوّلُ صياغةٍ لهذا الحارس منعت نصّاً بعينه (`busy === assignment.task`)
        **وكان قد أُصلح أصلاً**، بينما الخلطُ باقٍ في `claim` بصيغةٍ أخرى — تأكيدٌ
        أخضرُ فوق عطبٍ حيّ. فالمرساةُ الآن **الشكلُ**: لا معرّفٍ عارٍ في `busy`.
        """
        violations = []
        if "useState<string | null>(null)" not in self.staff:
            violations.append("‏`busy` ما زال رقماً — ولا رقمَ يميّز جدولَه")
        for bare in ("busy === assignment.id", "busy === task.id",
                     "setBusy(assignment.id)", "setBusy(task.id)"):
            if bare in self.staff:
                violations.append(f"معرّفٌ عارٍ في `busy`: {bare}")
        self.assertEqual(
            violations, [],
            f"‏`busy` يخلط معرّفَي جدولين فيُعطَّل زرٌّ في بطاقةٍ لا شأنَ لها: {violations}",
        )

    def test_the_submission_picker_offers_only_files_it_can_send(self):
        """`submit_platform_task` تنقل `WORK` وحدَها — فغيرُها يُتجاهَل بصمت.

        **والقيمةُ تُقرأ من النموذج لا تُكتب في الحارس**: أوّلُ صياغةٍ لهذا
        التأكيد ثبّتت النصَّ `'WORK'` حرفيّاً، و`Kind.WORK` قيمتُها `"work"`
        صغيرةً — فرشّح الدرجُ على قيمةٍ لا وجودَ لها، وصار المنتقي فارغاً أبداً
        **والحارسُ أخضرُ يحرس العطب**. وقراءةُ القيمة من `TextChoices` تجعل
        الحارسَ يسقط لو تغيّرت في أيّ من الطرفين.
        """
        work = PlatformTaskAttachment.Kind.WORK.value
        self.assertIn(
            f"PlatformTaskAttachmentKind = '{work}'", self.drawer,
            f"قيمةُ دور «ملفّ العمل» في الدرج تخالف `Kind.WORK` (`{work}`) — "
            "ترشيحٌ كاذبٌ دائماً يُفرغ منتقي ملفّات التسليم بلا خطأ.",
        )
        self.assertIn(
            "attachment.kind === WORK_KIND", self.drawer,
            "منتقي ملفّات التسليم يعرض ملفّاً سبق أن رافق تسليماً: يُختار ويُرسَل "
            "ولا يحدث شيء — لا خطأٌ ولا أثر.",
        )

    def test_every_clickable_row_has_a_focusable_control(self):
        """صفٌّ كلُّه `onClick` بلا عنصرٍ قابلٍ للتبئير فأرةٌ وحدَها."""
        # **‏`<button` شرطُ التأكيد لا مجرّدُ نصِّ المُعالِج**: `<span onClick=...>`
        # يحمل نفسَ النصّ وهو غيرُ قابلٍ للتبئير — فالتأكيدُ على النصّ وحدَه كان
        # يمرّ على ما يسمّيه عطباً. والمطابقةُ تبدأ من الوسم وتصل إلى المُعالِج
        # بلا وسمٍ آخرَ بينهما.
        violations = []
        for handler, what in (
            (r"openTask\(task\); \}", "صفُّ المهمّة"),
            (r"setBoardEmployee\(\(current\) => current === row\.employee \? null : row\.employee\); \}",
             "صفُّ اللوح"),
        ):
            # ‏`[^<]*` لا `[^<>]*`: سهمُ الدالّة `=>` يحمل `>`، واستبعادُه يقطع
            # المطابقةَ داخل الوسم نفسِه. و`<` وحدَه هو ما يفصل وسماً عن وسم.
            if not re.search(rf"<button[^<]*{handler}", self.admin):
                violations.append(f"{what} بلا `<button>` يُبلَغ بلوحة المفاتيح")
        self.assertEqual(violations, [], f"جدولٌ يُفتَح بالفأرة وحدَها: {violations}")


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


class TheAssignedTaskCanBeOpenedTest(TestCase):
    """«لمّا أُسند مهمّة ما بقدر أفتحها» — بلاغُ المالك، وكان صحيحاً (212-M1 · M2).

    كان «جدولُ المهامّ» جدولاً للقراءة: لا `onClick` على صفٍّ ولا شاشةَ تفصيل.
    والشيءُ الوحيدُ القابلُ للفتح **تسليمٌ**، وهو لا يوجد إلّا بعد أن يُسلّم
    الموظّف — فمن لحظةِ الإسناد إلى لحظةِ التسليم لا شيءَ يُفتَح إطلاقاً.

    ومعه (M2) كان العمودُ يعرض **عدداً** بجانب «موظّفٌ واحد» — وهي عبارةُ
    *نطاق* الإسناد لا اسمُ أحد — فقرأها المالكُ اسمَ الموظّف ولم يكن اسماً.
    الجدولُ كلُّه لم يكن يقول لمن أُسندت المهمّة.
    """

    def setUp(self):
        self.admin = ADMIN.read_text(encoding="utf-8")

    def test_the_row_opens_a_detail_view(self):
        violations = []
        if "onClick={() => openTask(task)}" not in self.admin:
            violations.append("صفُّ الجدول لا يفتح المهمّة")
        # ‏**المرساةُ الشرطُ لا اسمُ الوسم**: صار الدرجُ مكوّناً مشتركاً بين المدير
        # والموظّف (#213-ب) بدل قسمٍ مكتوبٍ داخل اللوحة، فتثبيتُ الحارس على
        # `<section` كان يُسقطه على تسميةٍ لا على سلوك.
        if not re.search(r"\{selectedTask && <\w", self.admin):
            violations.append("لا درجَ تفصيلٍ للمهمّة المفتوحة")
        if "setSelectedTaskId(null)" not in self.admin:
            violations.append("لا مخرجَ من الدرج — حالةٌ لا يُرجَع منها")
        # وأنّ ما يفتحها عنصرٌ يُبلَغ بلوحة المفاتيح محروسٌ في
        # `TheTaskFileScreensSayTheTruthTest` — بالوسم لا بنصّ المُعالِج.
        self.assertEqual(violations, [], f"المهمّةُ ما زالت لا تُفتَح: {violations}")

    def test_the_detail_view_names_the_people_and_shows_their_state(self):
        """الدرجُ يقرأ حقولَ الإسناد الحقيقيّة لا عدداً مشتقّاً.

        والدرجُ اليومَ ملفٌّ مشتركٌ (`TaskFileDrawer`) تفتحه لوحةُ المدير وشاشةُ
        الموظّف معاً، فالحقلُ يُطلَب في **مصادر اللوحة مجتمعةً** لا في ملفٍّ بعينه.
        """
        sources = _component_sources()
        required = ("assignment.employee_name", "assignment.status_display", "submission.employee_name")
        missing = [
            field for field in required
            if not any(field in source for source in sources.values())
        ]
        self.assertEqual(missing, [], f"درجُ المهمّة لا يعرض: {missing}")

    def test_the_table_says_who_not_only_how_many(self):
        violations = []
        if "assignment.employee_name" not in self.admin:
            violations.append("الجدولُ لا يقرأ اسمَ المُسنَد إليه")
        if "formatNumber(taskAssignments.length)" in self.admin:
            violations.append("عادَ عمودُ الأسماء عدّاً مجرّداً")
        # «الجمهور» **رأسَ عمودٍ** كان يُقرأ اسمَ موظّف؛ الصادقُ «نطاق الإسناد».
        # والتسميةُ نفسُها في نموذج الإنشاء سليمةٌ (اختيارُ نطاق)، فالمرساةُ
        # وسمُ الرأس بعينه لا الكلمةُ أينما وقعت.
        if '<th className="p-2">الجمهور</th>' in self.admin:
            violations.append("رأسُ عمودِ الجدول ما زال «الجمهور» فيُقرأ اسماً")
        self.assertEqual(violations, [], f"الجدولُ لا يقول لمن أُسندت: {violations}")


class TheManagerWritesOnTheTaskItselfTest(TestCase):
    """ملاحظةُ المدير كان لها مكانان، ولا واحدَ منهما المهمّة (212-M3).

    `PlatformEmployeeNote` على **الموظّف**، و`reviewer_notes` على **التسليم** أي
    لا وجودَ لها قبل أن يُسلّم. والموظّفُ يكتب على مهمّته منذ 212-E. فصار للحقل
    `task` نظيرٌ عند المدير، وللاثنين خيطٌ واحدٌ مرتَّبٌ بالوقت.
    """

    def test_the_payload_carries_the_task_of_the_note(self):
        """حارسُ واجهةٍ بلا نظيرٍ على الحمولة يحرس نصّاً لا سلوكاً."""
        fields = set(PlatformEmployeeNoteSerializer().fields)
        self.assertTrue(
            {"task", "task_title"} <= fields,
            f"حمولةُ الملاحظة بلا مهمّتها: {sorted(fields)}",
        )

    def test_the_managers_note_is_written_on_the_task_and_read_in_one_thread(self):
        """**المرساةُ هي الشرطُ لا اسمُ الدالّة** — وقد تحرّك الاسمُ مرّتين (#213-ب).

        كان هذا الاختبارُ يطلب حرفيّاً `threadFor(selectedTask.id)`: دمجاً محلّيّاً
        في لوحة المدير لملاحظتين اثنتين. وصار الخادمُ يعطي الخيطَ كاملاً
        (`tasks/<pk>/thread/`) بمرفقاتِه وتسليماتِه وقراراتِ مراجعته، والدمجُ
        المحلّيُّ **أضعفُ** منه لا أقوى. فالتمسّكُ بالاسم القديم كان سيفرض إبقاءَ
        دالّةٍ ميّتةٍ إلى جانب البديل لمجرّد إرضاء نصٍّ في اختبار — وهو أسوأُ ما
        يفعله حارسٌ ساكن.

        والشرطُ المحروسُ لم يتغيّر حرفاً: أن تُكتَب ملاحظةُ المدير **على المهمّة**،
        وأن يُقرأ الطرفان في **خيطٍ واحدٍ مرتَّب**. والبحثُ في مكوّنات المهامّ كلِّها
        لا في لوحة المدير وحدَها، لأنّ الدرجَ المشترَك يخدم الجمهورين معاً.
        """
        sources = _component_sources()
        violations = []
        if not any(
            # بلا حسّاسيّةِ حالةٍ: الوسيطُ الرابعُ يُكتَب `selectedTask.id` أو
            # `currentTask.id`، و`\\btask` كانت تطلب حرفاً صغيراً بعد حدِّ كلمةٍ
            # فلا تطابق أيّاً منهما — حارسٌ يسقط على التسمية لا على الشرط.
            re.search(r"createPlatformEmployeeNote\([^;]*task", source, re.IGNORECASE)
            for source in sources.values()
        ):
            violations.append("نموذجُ ملاحظةِ المدير لا يُرسل معرّفَ المهمّة")
        if not any("getPlatformTaskThread(" in source for source in sources.values()):
            violations.append("لا خيطَ يجمع ملاحظاتِ الطرفين على المهمّة")
        self.assertEqual(violations, [], f"الملاحظةُ لا تُكتَب على المهمّة: {violations}")

    def test_the_employee_reads_it_where_the_task_is(self):
        """ملاحظةٌ على مهمّةٍ تُقرأ عند المهمّة، لا في قائمةٍ أسفلَ الشاشة."""
        staff = (TASKS_UI / "StaffTasksPanel.tsx").read_text(encoding="utf-8")
        violations = []
        if "managerNotesFor(assignment.task)" not in staff:
            violations.append("بطاقةُ الإسناد لا تعرض ملاحظةَ المدير على مهمّتها")
        if "note.task ? note.task_title" not in staff:
            violations.append("القائمةُ العامّة لا تقول على أيّ مهمّةٍ كُتبت الملاحظة")
        self.assertEqual(violations, [], f"ملاحظةُ المدير لا تصل الموظّفَ عند مهمّته: {violations}")


class TaskAssignmentStartsAtThePersonTest(TestCase):
    """«زرّ أسند مهمّة على كلّ شخص» — نصُّ طلب المالك (212-O1).

    كان الإسنادُ **نموذجاً مركزيّاً واحداً**: تكتب المهمّةَ ثمّ تبحث عن اسم
    الشخص في قائمةٍ منسدلة. والمالكُ ينظر إلى وجهِ الشخص أمامه ويريد أن يُسند
    إليه من مكانه — فصار على بطاقة كلِّ واحدٍ بابٌ يفتح ملفَّه **على تبويب
    المهامّ** حيث نموذجُ إسنادٍ لا قائمةَ فيه: الشخصُ مُعيَّنٌ سلفاً.
    """

    def test_every_person_card_carries_the_door(self):
        violations = []
        card = CARD.read_text(encoding="utf-8")
        if "onOpenTasks(employee.id)" not in card:
            violations.append("بطاقةُ الشخص بلا بابٍ إلى مهامّه")
        dashboard = DASHBOARD.read_text(encoding="utf-8")
        if 'onOpenTasks={' not in dashboard:
            violations.append("اللوحةُ لا تصل البابَ بشيء — زرٌّ لا يفعل")
        if 'tab: "tasks"' not in dashboard:
            violations.append("البابُ لا يفتح تبويبَ المهامّ — نقرتان وبحثٌ عن التبويب")
        self.assertEqual(violations, [], f"الإسنادُ ما زال يبدأ من نموذجٍ مركزيّ: {violations}")

    def test_the_drawer_opens_on_the_tab_it_was_asked_for(self):
        """درجٌ يهبط على «عام» دائماً يجعل البابَ زينةً."""
        source = PROFILE_DRAWER.read_text(encoding="utf-8")
        violations = []
        if "initialTab" not in source:
            violations.append("الدرجُ لا يقبل تبويبَ البداية")
        if "useState<ProfileTab>(initialTab)" not in source:
            violations.append("الدرجُ يقبل التبويبَ ويتجاهله")
        if '{ key: "tasks"' not in source:
            violations.append("لا تبويبَ مهامٍّ في الدرج أصلاً")
        self.assertEqual(violations, [], f"البابُ يفتح على غير ما طُلب: {violations}")

    def test_the_form_names_no_employee_because_the_drawer_already_did(self):
        """‏`INDIVIDUAL` يلزمه موظّفٌ واحدٌ بالضبط — وهو صاحبُ الدرج."""
        source = PROFILE_DRAWER.read_text(encoding="utf-8")
        violations = []
        if 'audience: "INDIVIDUAL"' not in source:
            violations.append("النموذجُ لا يُسند إسناداً فرديّاً")
        if "employee_ids: [employeeId]" not in source:
            violations.append("النموذجُ لا يُسند إلى صاحب الدرج بعينه")
        self.assertEqual(violations, [], f"نموذجُ الإسناد لا يعرف صاحبَه: {violations}")

    def test_the_assign_form_is_not_shown_to_someone_who_cannot_assign(self):
        """الدرجُ يُركَّب في قشرة الموظّف أيضاً — ونموذجُ إسنادٍ يراه من لا يملكه
        وعدٌ كاذبٌ ينتهي بـ403."""
        source = PROFILE_DRAWER.read_text(encoding="utf-8")
        start = source.find("{tab === \"tasks\" &&")
        self.assertNotEqual(start, -1, "تبويبُ المهامّ غيرُ مُصيَّر.")
        end = source.find("{tab === \"wallet\" &&", start)
        section = source[start:end if end != -1 else len(source)]
        form = section.find("<form onSubmit={assignTask}")
        gate = section.find("{canManage && (")
        self.assertNotEqual(form, -1, "لا نموذجَ إسنادٍ في التبويب.")
        self.assertNotEqual(gate, -1, "نموذجُ الإسناد بلا شرطِ صلاحيّة.")
        self.assertLess(gate, form, "الشرطُ بعد النموذج — فالنموذجُ يُعرَض للجميع.")


class ThePersonTasksAreVisibleOnTheirDeskTest(TestCase):
    """«مهامّ كلّ واحد على طاولته» (212-O2).

    والعدّادُ **غيرُ أوامر العمل**: `active_work_orders_count` يعدّ `WorkOrder`
    و`open_platform_tasks_count` يعدّ `PlatformTaskAssignment` — نظامان لا
    يلتقيان، ورقمٌ واحدٌ عنهما كان يكذب على المدير.
    """

    def test_the_card_shows_the_open_task_count_of_that_person(self):
        card = CARD.read_text(encoding="utf-8")
        violations = []
        if "employee.open_platform_tasks_count" not in card:
            violations.append("البطاقةُ لا تعرض عددَ مهامّه")
        if "formatNumber(employee.open_platform_tasks_count" not in card:
            violations.append("العددُ لا يمرّ بـ`formatNumber` — قاعدةُ المستودع")
        self.assertEqual(violations, [], f"الطاولةُ لا تقول ما على كلّ واحد: {violations}")

    def test_the_drawer_lists_that_persons_assignments_by_filter_not_by_the_whole_table(self):
        source = PROFILE_DRAWER.read_text(encoding="utf-8")
        self.assertIn(
            "listPlatformTaskAssignments(employeeId)", source,
            "الدرجُ يسحب إسنادات المنصّة كلَّها ليعرض إسنادات واحد.",
        )

    def test_the_api_client_can_ask_for_one_employee(self):
        """حارسُ واجهةٍ بلا نظيرٍ على العميل يحرس نصّاً لا سلوكاً."""
        source = API.read_text(encoding="utf-8")
        self.assertRegex(
            source,
            r"listPlatformTaskAssignments = \(employee\?: number\)[\s\S]{0,200}query: \{ employee \}",
            "عميلُ الـAPI لا يمرّر معرّفَ الموظّف — فالمرشّحُ الخادميُّ بلا مستدعٍ.",
        )
