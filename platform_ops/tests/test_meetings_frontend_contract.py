"""عقدُ الواجهة لاجتماعات المنصّة (التذكرة 211-G — الخادمُ جاهزٌ منذ 211-F).

نفسُ نمط `test_pilot_axes_frontend_contract.py`/`test_health_assignment_frontend_contract.py`:
كلُّ مفتاحٍ يُرجعه المُسلسِلان معلَنٌ في واجهة TypeScript، وكلُّ قيمةِ حالةٍ لها
تسميةٌ عربيّةٌ في الواجهة — `tsc` لا يفحص شكلَ ما يصل من الشبكة.
"""
import re
from pathlib import Path

from django.test import TestCase

from platform_ops.models import PlatformMeeting, PlatformMeetingAttendance
from platform_ops.serializers import (
    PlatformMeetingAttendanceSerializer,
    PlatformMeetingSerializer,
)
from platform_ops.services import MEETING_CHECK_IN_EARLY_WINDOW_MINUTES
from platform_ops.tests.test_my_agent_frontend_contract import _interface_fields


class MeetingsFrontendContractTest(TestCase):
    def setUp(self):
        repo_root = Path(__file__).resolve().parents[2]
        self.api_source = (
            repo_root / "frontend_v2" / "services" / "platformMeetingsApi.ts"
        ).read_text(encoding="utf-8")
        self.manager_panel_source = (
            repo_root / "frontend_v2" / "components" / "platform" / "MeetingsPanel.tsx"
        ).read_text(encoding="utf-8")
        self.employee_panel_source = (
            repo_root / "frontend_v2" / "components" / "platform" / "MyMeetingsPanel.tsx"
        ).read_text(encoding="utf-8")

    def test_meeting_row_matches_serializer_fields_exactly(self):
        self.assertEqual(
            _interface_fields(self.api_source, "PlatformMeetingRow"),
            set(PlatformMeetingSerializer.Meta.fields),
            "واجهة PlatformMeetingRow يجب أن تطابق حقول PlatformMeetingSerializer تماماً.",
        )

    def test_attendance_row_matches_serializer_fields_exactly(self):
        self.assertEqual(
            _interface_fields(self.api_source, "PlatformMeetingAttendanceRow"),
            set(PlatformMeetingAttendanceSerializer.Meta.fields),
            "واجهة PlatformMeetingAttendanceRow يجب أن تطابق حقول PlatformMeetingAttendanceSerializer تماماً.",
        )

    def test_meeting_status_labels_match_server_choices_exactly(self):
        match = re.search(r"MEETING_STATUS_LABEL[^=]*=\s*\{(.*?)\};", self.api_source, re.DOTALL)
        self.assertIsNotNone(match, "لم يُعثر على MEETING_STATUS_LABEL.")
        frontend_labels = dict(re.findall(r'"?(\w*)"?:\s*"([^"]+)"', match.group(1)))
        self.assertEqual(frontend_labels, dict(PlatformMeeting.Status.choices))

    def test_attendance_status_labels_match_server_choices_exactly(self):
        match = re.search(
            r"MEETING_ATTENDANCE_STATUS_LABEL[^=]*=\s*\{(.*?)\};", self.api_source, re.DOTALL,
        )
        self.assertIsNotNone(match, "لم يُعثر على MEETING_ATTENDANCE_STATUS_LABEL.")
        frontend_labels = dict(re.findall(r'"?(\w*)"?:\s*"([^"]+)"', match.group(1)))
        self.assertEqual(frontend_labels, dict(PlatformMeetingAttendance.Status.choices))

    def test_frontend_declares_every_endpoint(self):
        for name in (
            "listPlatformMeetings",
            "createPlatformMeeting",
            "updatePlatformMeeting",
            "cancelPlatformMeeting",
            "inviteEmployeesToMeeting",
            "listMeetingAttendance",
            "decideMeetingExcuse",
            "checkInToMeeting",
            "submitMeetingExcuse",
        ):
            self.assertIn(name, self.api_source, name)
        for path in (
            "platform/ops/meetings/",
            "meetings/create/",
            "/update/",
            "/cancel/",
            "/invite/",
            "/attendance/",
            "/decide-excuse/",
            "/check-in/",
            "/excuse/",
        ):
            self.assertIn(path, self.api_source, path)

    def test_check_in_returns_meeting_link_from_server_response_not_local_row(self):
        # «يودّيه عرابط الاجتماع» — الرابطُ من ردّ الخادم لحظة الدخول لا من صفّ القائمة المحلّي.
        self.assertIn("meeting_link: string", self.api_source)
        self.assertRegex(
            self.employee_panel_source,
            r"window\.open\(\s*result\.meeting_link",
            "زرُّ تسجيل الدخول يجب أن يفتح `result.meeting_link` من ردّ `checkInToMeeting` لا من صفّ الاجتماع.",
        )

    def test_check_in_window_minutes_matches_the_server_constant(self):
        match = re.search(
            r"CHECK_IN_EARLY_WINDOW_MINUTES\s*=\s*(\d+)", self.employee_panel_source,
        )
        self.assertIsNotNone(match, "لم يُعثر على ثابت نافذة تسجيل الدخول في الواجهة.")
        self.assertEqual(int(match.group(1)), MEETING_CHECK_IN_EARLY_WINDOW_MINUTES)

    def test_excuse_note_is_mandatory_in_employee_panel(self):
        self.assertIn("سببُ الاعتذار إلزاميّ", self.employee_panel_source)

    def test_attendance_book_shows_explicit_counts(self):
        # «مين ما حضر» يُجاب برقمٍ لا باستنتاج.
        self.assertIn("مدعوّون", self.manager_panel_source)
        self.assertIn("counts.attended", self.manager_panel_source)
        self.assertIn("counts.absent", self.manager_panel_source)

    def test_the_absence_count_is_never_derived_by_subtracting_attendees(self):
        """«غاب» = الحالةُ `absent` وحدَها، لا «المدعوّون ناقصَ الحاضرين».

        الطرحُ يلصق صفةَ الغياب بصاحب العذر **المقبول** وبمن لم يُبتَّ في عذره —
        وهو بعينه الخلطُ الذي فُصلت لأجله الحالاتُ الخمس في 211-E، ودرجةُ الحضور
        تدخل تسعيرَ راتب. والسلوكُ نفسُه يفحصه `utils/meetingAttendanceTally.test.ts`
        فعلياً؛ هذا يمنع رجوعَ الحساب إلى داخل المكوّن حيث لا يراه اختبار.
        """
        # موضعُ **النداء** لا مجرّدُ الاستيراد: استيرادٌ باقٍ فوق حسابٍ يدويٍّ
        # عاد إلى المكوّن يُرضي أيَّ فحصِ تضمينٍ ساذج.
        self.assertRegex(
            self.manager_panel_source,
            r"useMemo\(\s*\(\)\s*=>\s*tallyAttendance\(",
            "عدُّ الدفتر يجب أن يمرّ بالدالّة الخالصة المفحوصة لا بحسابٍ داخل المكوّن.",
        )
        self.assertNotRegex(
            self.manager_panel_source,
            r"total\s*-\s*attended",
            "عودةٌ إلى طرح الحاضرين من المدعوّين — يُحسب صاحبُ العذر المقبول غائباً.",
        )

    def test_check_in_is_never_locked_by_the_browser_clock(self):
        """نافذةُ الدخول تلميحٌ لا قفل — الخادمُ وحدَه يرفض، وساعتُه هي المرجع.

        تعطيلُ الزرّ بحسابٍ من ساعة المتصفّح يحبس موظّفاً بساعةِ جهازٍ مغلوطةٍ
        خارجَ اجتماعه بلا مخرجٍ ولا رسالةٍ تشرح — وتسجيلُ الحضور يرفع درجتَه
        ويُنزّلها. (نفسُ سببِ قراءةِ الاتّصال من حساب الخادم في `roomPresence.ts`.)
        """
        disabled_expressions = re.findall(r"disabled=\{([^}]*)\}", self.employee_panel_source)
        self.assertTrue(disabled_expressions, "لم يُعثر على أيّ زرّ في شاشة الموظّف.")
        clock_locked = [expr for expr in disabled_expressions if "availability" in expr]
        self.assertFalse(
            clock_locked,
            f"زرٌّ مُعطَّلٌ بحساب ساعة المتصفّح بدل ترك الخادم يحكم: {clock_locked}",
        )

    def test_decide_excuse_actions_are_offered_only_for_pending_status(self):
        self.assertRegex(
            self.manager_panel_source,
            r'row\.status === "excused_pending" && \(',
            "أزرارُ قبول/رفض العذر يجب أن تظهر لصفّ «معلّق» وحده.",
        )
