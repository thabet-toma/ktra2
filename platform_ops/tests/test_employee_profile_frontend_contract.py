"""عقدُ الواجهة لملفّ الموظّف الـ360 (التذكرتان 211-Q، 211-J).

نفسُ نمط `test_meetings_frontend_contract.py`: مفاتيحُ `PlatformEmployeeSerializer`
معلَنةٌ في واجهة TypeScript المقابلة، والتبويباتُ الأربعةُ مركَّبةٌ فعلاً في الدرج،
والدرجُ مركَّبٌ فعلاً في `PlatformOpsDashboard.tsx` — `tsc` لا يفحص شكلَ ما يصل من
الشبكة و`npm test` لا يُصيّر مكوّناً، فما لا يحرسه اختبارٌ ساكنٌ لا يحرسه شيء.
"""
from pathlib import Path

from django.test import TestCase

from platform_ops.serializers import PlatformEmployeeSerializer
from platform_ops.tests.test_my_agent_frontend_contract import _interface_fields


class EmployeeProfileFrontendContractTest(TestCase):
    def setUp(self):
        repo_root = Path(__file__).resolve().parents[2]
        self.api_source = (
            repo_root / "frontend_v2" / "services" / "platformEmployeeProfileApi.ts"
        ).read_text(encoding="utf-8")
        self.drawer_source = (
            repo_root / "frontend_v2" / "components" / "platform" / "EmployeeProfileDrawer.tsx"
        ).read_text(encoding="utf-8")
        self.dashboard_source = (
            repo_root / "frontend_v2" / "components" / "platform" / "PlatformOpsDashboard.tsx"
        ).read_text(encoding="utf-8")
        self.employee_card_source = (
            repo_root / "frontend_v2" / "components" / "platform" / "EmployeeCard.tsx"
        ).read_text(encoding="utf-8")
        self.room_source = (
            repo_root / "frontend_v2" / "components" / "platform" / "WorkspaceRoom.tsx"
        ).read_text(encoding="utf-8")
        self.my_card_source = (
            repo_root / "frontend_v2" / "components" / "platform" / "MyProfileCard.tsx"
        ).read_text(encoding="utf-8")
        self.workspace_source = (
            repo_root / "frontend_v2" / "components" / "platform" / "PlatformEmployeeWorkspace.tsx"
        ).read_text(encoding="utf-8")

    def test_platform_employee_row_matches_serializer_fields_exactly(self):
        self.assertEqual(
            _interface_fields(self.api_source, "PlatformEmployeeRow"),
            set(PlatformEmployeeSerializer.Meta.fields),
            "واجهة PlatformEmployeeRow يجب أن تطابق حقول PlatformEmployeeSerializer تماماً.",
        )

    def test_the_drawer_declares_all_four_tabs(self):
        for tab_key in ("general", "performance", "wallet", "activity"):
            self.assertIn(f'"{tab_key}"', self.drawer_source, f"التبويب «{tab_key}» غائبٌ عن الدرج.")

    def test_the_drawer_mounts_all_four_tab_sections(self):
        for tab_key in ("general", "performance", "wallet", "activity"):
            self.assertIn(f'tab === "{tab_key}"', self.drawer_source, f"قسمُ التبويب «{tab_key}» غيرُ مركَّبٍ فعلاً.")

    def test_the_drawer_is_mounted_in_the_dashboard(self):
        self.assertIn("EmployeeProfileDrawer", self.dashboard_source)
        self.assertRegex(
            self.dashboard_source,
            r"<EmployeeProfileDrawer\b",
            "الدرجُ مستوردٌ ولا يُركَّب فعلياً في PlatformOpsDashboard.tsx.",
        )

    def test_clicking_the_employee_card_face_opens_the_drawer(self):
        self.assertIn("onOpenProfile", self.employee_card_source)
        self.assertIn("onOpenProfile", self.dashboard_source)

    def test_clicking_a_room_seat_opens_the_drawer_not_only_the_old_activity_modal(self):
        self.assertRegex(
            self.dashboard_source,
            r"onSelectEmployee=\{\(employeeId\) => \{[\s\S]*?setProfileDrawer",
            "نقرُ مقعدٍ في الغرفة يجب أن يفتح الدرج.",
        )


class TheStoredPhotoActuallyReachesTheBoardTest(EmployeeProfileFrontendContractTest):
    """الحقلُ المحفوظُ الذي لا يُعرَض ليس ميزةً — وهذا بعينه ما طلبه المالك يراه.

    كان `photo_url` يُكتب عبر نقطته ويُقرأ في درج الملفّ وحدَه، بينما الغرفةُ
    وبطاقةُ اللوحة — الشاشتان اللتان في نموذج المالك البصريّ — تُرسمان من حمولة
    اللوحة ولا تحملها. فصورةٌ مرفوعةٌ تبقى وجهاً بأحرفٍ أولى على المقعد.
    """

    def test_the_room_seat_renders_the_real_photo_when_one_exists(self):
        self.assertRegex(
            self.room_source,
            r"occupant\.photoUrl\s*\?[\s\S]{0,200}<img",
            "مقعدُ الغرفة لا يعرض صورةَ الموظّف — الأحرفُ الأولى وحدَها.",
        )

    def test_the_employee_card_renders_the_real_photo_when_one_exists(self):
        self.assertRegex(
            self.employee_card_source,
            r"employee\.photo_url\s*\?[\s\S]{0,200}<img",
            "بطاقةُ اللوحة لا تعرض صورةَ الموظّف.",
        )

    def test_the_dashboard_passes_the_photo_into_the_room(self):
        self.assertRegex(
            self.dashboard_source,
            r"photoUrl:\s*employee\.photo_url",
            "الصورةُ لا تُمرَّر من حمولة اللوحة إلى ساكن الغرفة.",
        )

    def test_the_seat_role_line_prefers_the_job_title_over_the_policy_key(self):
        """`specialty` مفتاحُ سياسةِ تقييمٍ لا عنوانُ عرض — لا يُكتب على وجهِ موظّف."""
        self.assertRegex(
            self.dashboard_source,
            r"role:\s*employee\.job_title\s*\|\|\s*employee\.specialty",
            "سطرُ الدور في الغرفة يعرض مفتاحَ السياسة بدل المسمّى الوظيفيّ.",
        )


class TheEmployeeCanSetTheirOwnFaceTest(EmployeeProfileFrontendContractTest):
    """إذنٌ خادميٌّ بلا بابٍ في الواجهة إذنٌ ميّت.

    الخادمُ يسمح لصاحب الصفّ بضبط `photo_url` و`phone` دون `job_title`؛ ودرجُ
    الملفّ يُفتح من لوحة المدير وحدَها. فلولا بطاقةٌ في مساحة الموظّف نفسِه لبقي
    رفعُ الصورة حكراً على المدير — وصورةُ الموظّف أوّلُ ما يظهر على مقعده.
    """

    def test_the_self_card_is_mounted_in_the_employee_space(self):
        self.assertRegex(
            self.workspace_source,
            r"<MyProfileCard[\s/>]",
            "بطاقةُ الموظّف غيرُ مركَّبةٍ في مساحته.",
        )

    def test_the_self_card_uploads_a_photo_and_saves_a_phone(self):
        self.assertIn("uploadEmployeePhoto", self.my_card_source)
        self.assertIn("setEmployeeProfileCard", self.my_card_source)

    def test_the_self_card_never_sends_a_job_title(self):
        """المسمّى تعيينُ صاحب العمل — والخادمُ يردّ 403؛ فزرٌّ يُرسله زرُّ إحباط."""
        self.assertNotIn(
            "job_title:", self.my_card_source,
            "بطاقةُ الموظّف ترسل المسمّى الوظيفيّ — والخادمُ يرفضه 403.",
        )


class WalletLineColourSeparatesReversedFromPaidTest(EmployeeProfileFrontendContractTest):
    """ستُّ حالاتٍ لا اثنتان: المعكوسُ كان يُطبع بأخضر المصروف.

    سطرٌ عُكس (أُلغي) يظهر بلون السطر المصروف يعني مبلغاً سُحب من الموظّف يُقرأ
    مالاً في يده — والمحفظةُ تسعيرُ راتب.
    """

    def test_every_wallet_status_has_its_own_class_and_reversed_is_not_paid(self):
        import re

        block = re.search(
            r"WALLET_STATUS_CLASS:[^=]*=\s*\{(.*?)\};", self.drawer_source, re.DOTALL,
        )
        self.assertIsNotNone(block, "لم يُعثر على خريطة ألوان حالات المحفظة.")
        classes = dict(re.findall(r'(\w+):\s*"([^"]*)"', block.group(1)))
        self.assertEqual(
            set(classes),
            {"pending", "eligible", "approved", "payable", "paid", "reversed"},
            "خريطةُ الألوان لا تغطّي حالات المحفظة الستّ كما في `WalletLineStatus`.",
        )
        self.assertNotEqual(
            classes["reversed"], classes["paid"],
            "السطرُ المعكوس يُطبع بلون المصروف — مبلغٌ سُحب يُقرأ مالاً في اليد.",
        )
