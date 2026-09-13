from pathlib import Path
import re
from unittest import TestCase

from platform_ops.tests.test_platform_skin import LIGHT_PLATFORM_CLASS, _scoped_selectors


ROOT = Path(__file__).resolve().parents[2]
FRONTEND = ROOT / "frontend_v2"
STAFF = FRONTEND / "components" / "platform" / "staff"

REUSED_STAFF_PANELS = (
    "WorkOrdersPanel.tsx",
    "EmployeeSelfWalletCard.tsx",
    "EmployeeCompaniesPanel.tsx",
    "ChampionsPanel.tsx",
    "MyProfileCard.tsx",
    "MyMeetingsPanel.tsx",
    # الجرسُ لوحةٌ معادُ استعمالُها كأخواتها: `StaffTopBar.tsx` يركّبه في قشرة
    # الموظّف، ومركزُ القيادة ومساحةُ العمل يركّبانه كذلك. وبقاؤه خارجَ القائمة
    # ترك أصنافَه الفاتحةَ بلا حارسٍ **داخلَ قشرةٍ داكنة**: قائمةٌ منسدلةٌ
    # بنفسجيّةٌ ساطعةٌ وسطَ الليل. صُبغت في 212-G مع جلد القيادة، فتُحرَس هنا.
    "PlatformNotificationBell.tsx",
)
#: **تعبيرٌ واحدٌ لقاعدتَي CSS واحدة.** صارت محدِّداتُ الجلد تحمل الغلافَين معاً
#: (`.staff-shell, .ops-shell`)، فتعبيرٌ ضيّقٌ هنا وواسعٌ هناك يعني أنّ صنفاً
#: تلبسه لوحةٌ مشتركةٌ يُحرَس في قشرةٍ ويُفلت من الأخرى — وهو ما حدث فعلاً مع
#: الجرس: بنفسجيُّ قائمته لم يكن يراه أيُّ مسح. فيُستورَد التعبيرُ من مصدره.
LIGHT_PANEL_CLASS = LIGHT_PLATFORM_CLASS


class StaffShellContractTests(TestCase):
    def test_the_staff_shell_is_mounted_outside_the_company_application(self):
        source = (FRONTEND / "index.tsx").read_text(encoding="utf-8")
        match = re.search(r'<Route path="/staff/\*" element=\{(.+?)\} />', source)
        self.assertIsNotNone(match)
        self.assertNotIn("ApplicationBoundary", match.group(1))
        self.assertNotIn("CompanyProvider", match.group(1))

    def test_the_staff_shell_never_imports_the_company_sidebar(self):
        for source_path in STAFF.glob("*.tsx"):
            source = source_path.read_text(encoding="utf-8")
            self.assertNotIn("components/Sidebar", source)
            self.assertNotIn("AppLayout", source)
            self.assertNotIn("from \"../../../App\"", source)
            self.assertNotIn("from \"../../../App.tsx\"", source)

    def test_the_staff_door_lands_in_its_own_shell(self):
        source = (FRONTEND / "components" / "platform" / "StaffLoginPage.tsx").read_text(encoding="utf-8")
        self.assertIn('"/staff/home"', source)
        self.assertNotIn('"/platform/employee-space"', source)

    def test_the_platform_employee_sidebar_door_enters_the_staff_shell(self):
        source = (FRONTEND / "components" / "Sidebar.tsx").read_text(encoding="utf-8")
        marker = "{!user.isSuperAdmin && platformStaff.is_platform_employee && ("
        start = source.find(marker)
        self.assertNotEqual(start, -1, "مدخل موظف المنصّة فقد شرط العزل الصريح.")
        door = source[start:source.find("\n          )}", start)]
        violations = []
        if '"/staff/home"' not in door:
            violations.append("مدخل الموظف لا يوجّه إلى /staff/home")
        if 'setView("platform-employee-space")' in door:
            violations.append("مدخل الموظف ما زال يفتح المساحة القديمة")
        self.assertEqual(violations, [], f"مخالفات باب الموظف: {violations}")

    def test_the_platform_employee_sidebar_door_keeps_its_isolation_condition(self):
        source = (FRONTEND / "components" / "Sidebar.tsx").read_text(encoding="utf-8")
        required_condition = "!user.isSuperAdmin && platformStaff.is_platform_employee"
        violations = []
        if required_condition not in source:
            violations.append("شرط !user.isSuperAdmin مع is_platform_employee غير موجود حرفياً")
        self.assertEqual(violations, [], f"مخالفات عزل باب الموظف: {violations}")

    def test_the_staff_shell_contains_every_panel_mounted_by_the_legacy_workspace(self):
        workspace_source = (FRONTEND / "components" / "platform" / "PlatformEmployeeWorkspace.tsx").read_text(encoding="utf-8")
        mounted_components = set(re.findall(r"<([A-Z][A-Za-z0-9_]*)\b", workspace_source))
        local_imports = set(
            re.findall(
                r"import\s+(?:\{\s*)?([A-Z][A-Za-z0-9_]*)[^\n]*?from\s+[\"']\./",
                workspace_source,
            )
        )
        legacy_panels = sorted(mounted_components & local_imports)
        self.assertTrue(legacy_panels, "تعذّر اشتقاق لوحات المساحة القديمة من مصدرها.")

        staff_surface_source = "\n".join(
            source_path.read_text(encoding="utf-8") for source_path in STAFF.rglob("*.tsx")
        )
        missing = [
            panel
            for panel in legacy_panels
            if not re.search(rf"<{re.escape(panel)}\b", staff_surface_source)
        ]
        self.assertEqual(
            missing,
            [],
            f"لوحات المساحة القديمة غير مركّبة في قشرة /staff: {missing}",
        )

    def test_the_staff_shell_offers_a_way_back_to_the_company_system(self):
        """البابُ إلى `/staff` لا يجوز أن يكون باتّجاهٍ واحد.

        زرُّ الشريط الجانبيّ في التطبيق ينتقل انتقالاً كاملاً (212-I)، وهذه
        القشرةُ **لا تحمل شريطَ التطبيق** بقرارٍ يحرسه
        `test_the_staff_shell_never_imports_the_company_sidebar` — فبلا مخرجٍ
        صريحٍ تصير ضغطةٌ واحدةٌ خروجاً من نظام الشركة بلا رجعةٍ إلّا بكتابة
        العنوان. وهذا ما تمنعه بوّابةُ الجودة الرابعة نصّاً.

        ويُقاس على القشرة كلِّها لا على ملفٍّ بعينه: نقلُ الزرّ من الشريط إلى
        الترويسة إصلاحٌ مقبولٌ، وحذفُه ليس كذلك.
        """
        # يُؤكَّد على **أسماء الملفّات** لا على نصِّها: `assertRegex` على القشرة
        # مجموعةً طبعت ١١٢ كيلوبايتاً في خبر الفشل فغرق الخبرُ في الكومة. قيس.
        exit_pattern = re.compile(r"""window\.location\.assign\(\s*['"]/['"]\s*\)""")
        searched = sorted(path.name for path in STAFF.rglob("*.tsx"))
        carriers = [
            path.name for path in STAFF.rglob("*.tsx")
            if exit_pattern.search(path.read_text(encoding="utf-8"))
        ]
        self.assertNotEqual(
            carriers, [],
            "لا مخرجَ من قشرة الموظّف إلى نظام الشركة — بابٌ باتّجاهٍ واحد. "
            f"فُحِص {len(searched)} ملفّاً: {searched}",
        )

    def test_the_staff_shell_uses_tailwind_not_inline_styles(self):
        for source_path in STAFF.glob("*.tsx"):
            self.assertNotIn("style={{", source_path.read_text(encoding="utf-8"))

    def test_every_navigation_entry_has_a_panel_behind_it(self):
        nav_source = (FRONTEND / "utils" / "staffNav.ts").read_text(encoding="utf-8")
        shell_source = (STAFF / "StaffShell.tsx").read_text(encoding="utf-8")
        expected_panels = {
            "home": "StaffHomeDashboard",
            "tasks": "WorkOrdersPanel",
            "companies": "EmployeeCompaniesPanel",
            "meetings": "MyMeetingsPanel",
            "performance": "EmployeeSelfWalletCard",
            "profile": "MyProfileCard",
            "crm": "CrmPanel",
        }
        # **والمفاتيحُ تُشتقُّ من الشريط لا تُسرَد هنا وحدَها.** كان هذا التعدادُ
        # يمرّ على قاموسِه الخاصِّ فحسب، فحين أُضيف تبويبُ «العملاء» سابعاً إلى
        # `staffNav.ts` بقي أخضرَ ولم يرَه — أي أنّ اسمَه «لكلِّ تبويبٍ لوحةٌ
        # خلفه» لم يكن يستطيع السقوطَ لأجلِ ما يسمّيه. فيُطلَب أدناه أن تكون
        # مجموعةُ مفاتيح الشريط هي مجموعةَ المفاتيح المُعدَّدة نفسَها.
        nav_keys = set(re.findall(r"key:\s*'([a-z_]+)'", nav_source))
        self.assertEqual(
            nav_keys, set(expected_panels),
            f"تبويبٌ في `staffNav.ts` بلا لوحةٍ مُعدَّدةٍ هنا: "
            f"{sorted(nav_keys - set(expected_panels))} — أو لوحةٌ مُعدَّدةٌ بلا "
            f"تبويب: {sorted(set(expected_panels) - nav_keys)}.",
        )
        # **الربطُ لا مجرَّدُ الوجود**: تأكيدٌ بأنّ `<WorkOrdersPanel` موجودٌ في
        # الملفّ يبقى أخضرَ لو وُصِلت اللوحةُ بالتبويب الخطأ. فتُقتطَع أدناه فقرةُ
        # كلِّ مفتاحٍ من خريطة `panels` ويُطلَب أن تحمل لوحتَها هي.
        order = list(expected_panels)
        for index, key in enumerate(order):
            panel = expected_panels[key]
            self.assertRegex(nav_source, rf"key:\s*['\"]{key}['\"]")
            start = shell_source.find(f"{key}:")
            self.assertNotEqual(
                start, -1, f"مفتاحُ التبويب `{key}` غيرُ موجودٍ في خريطة لوحات القشرة.",
            )
            nxt = shell_source.find(f"{order[index + 1]}:", start) if index + 1 < len(order) else -1
            section = shell_source[start:nxt] if nxt != -1 else shell_source[start:]
            self.assertRegex(
                section, rf"<{panel}[\s/>]",
                f"التبويبُ `{key}` لا يعرض `{panel}` — لوحةٌ موصولةٌ بالتبويب الخطأ "
                "تُبقي تأكيدَ «اللوحةُ موجودةٌ في الملفّ» أخضرَ وهي في مكانٍ آخر.",
            )
        self.assertRegex(shell_source, r"<ChampionsPanel[\s/>]")

    def test_the_session_timer_ticks_every_minute_and_is_cleaned_up(self):
        source = (STAFF / "StaffTopBar.tsx").read_text(encoding="utf-8")
        self.assertRegex(source, r"setInterval\([\s\S]*?,\s*(?:60000|60\s*\*\s*1000)\)")
        self.assertIn("clearInterval", source)

    def test_dates_and_numbers_go_through_the_repo_formatters(self):
        for source_path in STAFF.glob("*.tsx"):
            source = source_path.read_text(encoding="utf-8")
            self.assertNotIn("toLocaleDateString", source)
            self.assertNotIn("toLocaleString", source)

    def test_the_staff_shell_wears_the_dark_skin_not_the_sky_platform_skin(self):
        for source_path in STAFF.glob("*.tsx"):
            self.assertNotIn("platform-surface", source_path.read_text(encoding="utf-8"))
        self.assertIn("staff-shell", (STAFF / "StaffShell.tsx").read_text(encoding="utf-8"))

    def test_the_staff_shell_ships_no_light_variant(self):
        for source_path in STAFF.glob("*.tsx"):
            self.assertNotIn("dark:", source_path.read_text(encoding="utf-8"))

    def test_the_staff_palette_tokens_are_declared(self):
        source = (FRONTEND / "styles" / "index.css").read_text(encoding="utf-8")
        match = re.search(r"\.staff-shell\s*,\s*\.ops-shell\s*\{(?P<body>.*?)\}", source, re.DOTALL)
        self.assertIsNotNone(match)
        body = match.group("body")
        for token in (
            "--staff-bg",
            "--staff-panel",
            "--staff-rail",
            "--staff-line",
            "--staff-text",
            "--staff-muted",
            "--staff-accent",
            "--staff-accent-2",
        ):
            self.assertRegex(body, rf"{re.escape(token)}\s*:")
        self.assertNotIn("--color-", body)

    def test_every_light_class_the_reused_panels_wear_has_a_dark_override(self):
        stylesheet = (FRONTEND / "styles" / "index.css").read_text(encoding="utf-8")
        light_classes = set()
        for panel in REUSED_STAFF_PANELS:
            source = (FRONTEND / "components" / "platform" / panel).read_text(encoding="utf-8")
            light_classes.update(match.group(0) for match in LIGHT_PANEL_CLASS.finditer(source))

        self.assertTrue(light_classes)
        # يُؤكَّد على **قائمةِ المخالفات** لا على نصِّ الـCSS: `assertIn` على ملفٍّ
        # كاملٍ تطبع مئةً وثلاثين كيلوبايتاً فيضيع الخبرُ في الكومة. ويُطلَب رمزُ
        # الصنف داخلَ محدِّدٍ يبدأ بالغلاف لا سلسلةٌ حرفيّةٌ بشكل `.staff-shell .x`:
        # تجاوزُ `group-hover:` يلزمه سلفٌ وسيطٌ فالمطابقةُ الحرفيّةُ تطلب المستحيل.
        scoped = _scoped_selectors(stylesheet, ".staff-shell")
        missing = []
        for light_class in sorted(light_classes):
            escaped_class = light_class.replace(":", r"\:").replace("/", r"\/")
            if not any(f".{escaped_class}" in selector for selector in scoped):
                missing.append(light_class)
        self.assertEqual(
            missing, [],
            f"أصنافٌ فاتحةٌ تلبسها لوحاتُ قشرة الموظّف بلا تجاوزٍ داكن: {missing} — "
            "رقعةٌ بيضاءُ وسطَ شاشةٍ داكنة.",
        )
