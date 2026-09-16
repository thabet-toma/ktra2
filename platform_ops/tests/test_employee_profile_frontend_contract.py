"""عقدُ الواجهة لملفّ الموظّف الـ360 (التذكرتان 211-Q، 211-J).

نفسُ نمط `test_meetings_frontend_contract.py`: مفاتيحُ `PlatformEmployeeSerializer`
معلَنةٌ في واجهة TypeScript المقابلة، والتبويباتُ الأربعةُ مركَّبةٌ فعلاً في الدرج،
والدرجُ مركَّبٌ فعلاً في `PlatformOpsDashboard.tsx` — `tsc` لا يفحص شكلَ ما يصل من
الشبكة و`npm test` لا يُصيّر مكوّناً، فما لا يحرسه اختبارٌ ساكنٌ لا يحرسه شيء.
"""
import re
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

    #: تبويباتٌ لا يجوز أن تختفي — الاشتقاقُ وحدَه يبقى أخضرَ لو حُذف تبويبٌ.
    REQUIRED_TABS = ("general", "performance", "wallet", "notes", "activity")

    def _declared_tabs(self) -> list[str]:
        """مفاتيحُ التبويبات **مشتقّةً من `TABS` في الـTSX** لا مسرودةً هنا.

        كانت مسرودةً أربعاً بيدٍ، فتبويبٌ خامسٌ يُعلَن غداً ولا يُركَّب يمرّ
        أخضرَ — وهو بعينه درسُ 212-C: «المفاتيحُ تُشتقُّ من المصدر لا تُسرَد في
        الحارس».
        """
        block = re.search(
            r"const TABS: \{ key: ProfileTab; label: string \}\[\] = \[(?P<body>[^\]]*)\]",
            self.drawer_source,
        )
        self.assertIsNotNone(block, "مصفوفةُ `TABS` في الدرج اختفت أو تغيّر شكلُها.")
        keys = re.findall(r'key:\s*"([a-z_]+)"', block.group("body"))
        self.assertTrue(keys, "لم يُقرأ مفتاحٌ واحدٌ من `TABS`.")
        return keys

    def test_every_tab_the_drawer_declares_is_mounted(self):
        missing = [
            key for key in self._declared_tabs()
            if f'tab === "{key}"' not in self.drawer_source
        ]
        self.assertEqual(
            missing, [],
            f"تبويباتٌ مُعلَنةٌ بلا قسمٍ يُركَّب: {missing} — زرٌّ يُضغَط فلا يظهر شيء.",
        )

    def test_no_required_tab_disappeared_from_the_drawer(self):
        declared = set(self._declared_tabs())
        gone = [key for key in self.REQUIRED_TABS if key not in declared]
        self.assertEqual(
            gone, [],
            f"تبويباتٌ واجبةٌ حُذفت من الدرج: {gone} — والاشتقاقُ وحدَه لا يمسك الحذف.",
        )

    def test_the_notes_tab_asks_the_server_for_this_employee_alone(self):
        """‏`listPlatformEmployeeNotes(employeeId)` — بالمعرّف لا بلا معرّف.

        بلا الوسيط تعيد النقطةُ ملاحظاتِ **كلِّ** الموظّفين، فيظهر في ملفِّ
        موظّفٍ ما كُتب على زملائه: معلومةٌ خاطئةٌ في شاشةٍ تعمل، ولا خطأَ يُعلن
        عنها. والترشيحُ في المتصفّح ليس علاجاً — الحمولةُ عبرت الشبكةَ أصلاً.
        """
        call = re.search(r"listPlatformEmployeeNotes\((?P<args>[^)]*)\)", self.drawer_source)
        self.assertIsNotNone(call, "درجُ الملفّ لا ينادي قائمةَ ملاحظات الموظّف إطلاقاً.")
        self.assertIn(
            "employeeId", call.group("args"),
            f"النداءُ بلا معرّفِ الموظّف: `listPlatformEmployeeNotes({call.group('args')})` — "
            "ملفُّ موظّفٍ يعرض ملاحظاتِ الفريق كلِّه.",
        )

    def test_writing_a_note_is_behind_the_manager_capability(self):
        """ونموذجُ الكتابة خلف صفةٍ صريحة.

        الخادمُ يرفض غيرَ المدير بـ403، لكنّ نموذجاً معروضاً لمن يُرفَض فعلُه
        بابٌ مسدود: يكتب الموظّفُ ملاحظتَه ثمّ يُقذَف برسالة منع.
        """
        self.assertRegex(
            self.drawer_source,
            r"canManage\s*&&\s*\(\s*<form onSubmit=\{saveNote\}",
            "نموذجُ إضافة الملاحظة غيرُ محروسٍ بـ`canManage`.",
        )

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
        """الصورةُ صارت داخلَ `CcAvatar`، فيُقاس الطرفان لا نصُّ البطاقة وحدَه.

        كانت البطاقةُ تكتب `<img>` بيدها فكفى تعبيرٌ واحدٌ عليها. ومنذ موجةِ
        تصميم مركز القيادة تُمرِّر الحقلَ إلى مكوّنٍ مشترك — فتأكيدٌ على نصِّ
        البطاقة وحدَها يمرّ على **تعليقٍ** يحمل الشكلَ القديم (حدث فعلاً). فيُقاس
        هنا الوصلُ: البطاقةُ تمرّر `photo_url`، والمكوّنُ يُصيّر `<img>` عند وجوده.
        """
        self.assertRegex(
            self.employee_card_source,
            r"<CcAvatar[\s\S]{0,200}photoUrl=\{employee\.photo_url\}",
            "بطاقةُ اللوحة لا تمرّر صورةَ الموظّف إلى `CcAvatar`.",
        )
        avatar_source = (
            Path(__file__).resolve().parents[2]
            / "frontend_v2" / "components" / "platform" / "ui" / "CcAvatar.tsx"
        ).read_text(encoding="utf-8")
        self.assertRegex(
            avatar_source,
            r"photoUrl\s*\?[\s\S]{0,200}<img",
            "`CcAvatar` لا يُصيّر الصورةَ الحقيقيّةَ عند وجود الرابط.",
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
