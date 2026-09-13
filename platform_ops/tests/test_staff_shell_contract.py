from pathlib import Path
import re
from unittest import TestCase


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
)
LIGHT_PANEL_CLASS = re.compile(
    r"(?<![\w-])(?:(?:hover):)?(?:"
    r"bg-(?:white(?:/\d+)?|(?:slate|gray)-(?:50|100|200)|(?:blue|sky|amber|rose|emerald)-(?:50|100|200))"
    r"|text-(?:slate-(?:400|500|600|700|800|900)|gray-\d+|(?:blue|sky|amber|rose|emerald)-(?:500|600|700|800))"
    r"|border-(?:slate-(?:100|200|300)|gray-\d+|(?:blue|sky|amber|rose|emerald)-(?:100|200|300|400))"
    r"|divide-slate-(?:100|200)"
    r"|ring-(?:slate-(?:100|200)|white)"
    r")(?![\w-])"
)


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
        }
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
        match = re.search(r"\.staff-shell\s*\{(?P<body>.*?)\}", source, re.DOTALL)
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
        for light_class in sorted(light_classes):
            escaped_class = light_class.replace(":", r"\:").replace("/", r"\/")
            selector = f".staff-shell .{escaped_class}"
            if light_class.startswith("hover:"):
                selector += ":hover"
            self.assertIn(selector, stylesheet, f"missing dark override for {light_class}")
