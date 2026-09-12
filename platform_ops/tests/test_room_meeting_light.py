"""الضوءُ الأصفر «في اجتماعٍ الآن» في حمولة اللوحة التفاعلية (#211 211-H).

تعريفُ `is_in_meeting` دقيقٌ بثلاثة قيود، كلٌّ منها يُسقط اللوحةَ في خطأ صامتٍ
مختلفٍ لو غاب:

- **«حضر» لا «مدعوّ»** — صفوفُ الحضور تُنشأ سلفاً لكلّ مدعوٍّ بحالة «غائب»
  (211-E)، فالعدُّ بالدعوة يُشعل الأصفرَ في وجه من لم يحضر إطلاقاً.
- **نافذةُ الاجتماع الحقيقية `start..end`** لا نافذةُ السماح بتسجيل الدخول
  المبكّرة (`MEETING_CHECK_IN_EARLY_WINDOW_MINUTES`) — من سجّل دخوله قبل
  الموعد بعشر دقائق ليس في اجتماعٍ بعد.
- **الملغى لا يُحتسب** — كما يتعامل `check_in_to_meeting` بالضبط مع
  `PlatformMeeting.Status.CANCELLED`.

وقيدُ أداءٍ منفصل: استعلامُ عضويّة الاجتماع واحدٌ لكلّ الموظّفين لا استعلامٌ
داخل الحلقة — هذه لوحةٌ تُفتَح كلَّ دقيقة على عشراتِ الموظّفين.
"""
import datetime

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from platform_ops.models import (
    Engagement,
    PlatformEmployee,
    PlatformMeeting,
    PlatformMeetingAttendance,
    ServiceSubscription,
)
from platform_ops.services import get_platform_dashboard_summary
from tenants.models import Tenant

User = get_user_model()


class RoomMeetingLightTest(TestCase):
    """`is_in_meeting` في بطاقة الموظّف داخل `get_platform_dashboard_summary`."""

    def setUp(self):
        self.manager = User.objects.create_superuser(
            username="meeting_light_mgr", email="meeting_light_mgr@ktra.local", password="x"
        )
        self.tenant = Tenant.objects.create(TenantID=4301, CompanyName="Meeting Light Co")
        ServiceSubscription.objects.create(
            tenant=self.tenant, status=ServiceSubscription.Status.ACTIVE, plan="growth"
        )
        self.now = timezone.now()

    def _make_employee(self, username):
        user = User.objects.create_user(
            username=username, email=f"{username}@ktra.local", password="x"
        )
        emp = PlatformEmployee.objects.create(
            user=user, specialty="data_entry", status=PlatformEmployee.Status.ACTIVE
        )
        Engagement.objects.create(
            employee=emp, tenant=self.tenant, status=Engagement.Status.ACTIVE
        )
        return emp

    def _make_meeting(self, *, start_offset_minutes, end_offset_minutes,
                       meeting_status=PlatformMeeting.Status.SCHEDULED):
        return PlatformMeeting.objects.create(
            title="اجتماعُ اختبار",
            start=self.now + datetime.timedelta(minutes=start_offset_minutes),
            end=self.now + datetime.timedelta(minutes=end_offset_minutes),
            meeting_link="https://meet.example.com/room",
            status=meeting_status,
            created_by=self.manager,
        )

    def _card_for(self, summary, emp):
        for card in summary["employees"]:
            if card["id"] == emp.pk:
                return card
        self.fail(f"لا بطاقةَ للموظّف {emp.pk} في حمولة اللوحة.")

    # --- السلوكُ الوظيفي ------------------------------------------------

    def test_employee_who_attended_an_ongoing_meeting_is_in_meeting(self):
        emp = self._make_employee("meet_attended")
        meeting = self._make_meeting(start_offset_minutes=-10, end_offset_minutes=20)
        PlatformMeetingAttendance.objects.create(
            meeting=meeting, employee=emp,
            status=PlatformMeetingAttendance.Status.ATTENDED,
            checked_in_at=self.now,
        )
        summary = get_platform_dashboard_summary(user=self.manager, now=self.now)
        self.assertTrue(self._card_for(summary, emp)["is_in_meeting"])

    def test_invited_but_still_absent_is_not_in_meeting(self):
        """أهمُّ اختبارٍ في الملفّ: بلا هذا التمييز يصير الأصفرُ «مدعوٌّ» لا «حاضر».

        صفُّ الحضور يُنشأ لحظةَ الدعوة بحالته الافتراضية «غائب» (211-E)، فموظّفٌ
        مدعوٌّ لم يفتح رابطَ الاجتماع ولم يسجّل دخولَه يجب ألاّ يضيء أصفر.
        """
        emp = self._make_employee("meet_invited_only")
        meeting = self._make_meeting(start_offset_minutes=-10, end_offset_minutes=20)
        PlatformMeetingAttendance.objects.create(meeting=meeting, employee=emp)
        summary = get_platform_dashboard_summary(user=self.manager, now=self.now)
        self.assertFalse(self._card_for(summary, emp)["is_in_meeting"])

    def test_meeting_that_already_ended_is_not_in_meeting(self):
        emp = self._make_employee("meet_ended")
        meeting = self._make_meeting(start_offset_minutes=-60, end_offset_minutes=-1)
        PlatformMeetingAttendance.objects.create(
            meeting=meeting, employee=emp,
            status=PlatformMeetingAttendance.Status.ATTENDED,
            checked_in_at=self.now - datetime.timedelta(minutes=50),
        )
        summary = get_platform_dashboard_summary(user=self.manager, now=self.now)
        self.assertFalse(self._card_for(summary, emp)["is_in_meeting"])

    def test_meeting_not_started_yet_is_not_in_meeting_even_inside_early_check_in_window(self):
        """داخل نافذة الدخول المبكّرة (١٥ دقيقة) لكن قبل `start` الحقيقيّ — ليس في اجتماعٍ بعد."""
        emp = self._make_employee("meet_early_checkin")
        meeting = self._make_meeting(start_offset_minutes=10, end_offset_minutes=40)
        PlatformMeetingAttendance.objects.create(
            meeting=meeting, employee=emp,
            status=PlatformMeetingAttendance.Status.ATTENDED,
            checked_in_at=self.now,
        )
        summary = get_platform_dashboard_summary(user=self.manager, now=self.now)
        self.assertFalse(self._card_for(summary, emp)["is_in_meeting"])

    def test_cancelled_meeting_does_not_count_even_with_an_attended_row(self):
        emp = self._make_employee("meet_cancelled")
        meeting = self._make_meeting(
            start_offset_minutes=-10, end_offset_minutes=20,
            meeting_status=PlatformMeeting.Status.CANCELLED,
        )
        PlatformMeetingAttendance.objects.create(
            meeting=meeting, employee=emp,
            status=PlatformMeetingAttendance.Status.ATTENDED,
            checked_in_at=self.now - datetime.timedelta(minutes=20),
        )
        summary = get_platform_dashboard_summary(user=self.manager, now=self.now)
        self.assertFalse(self._card_for(summary, emp)["is_in_meeting"])

    # --- الحدّان بالضبط ---------------------------------------------------

    def test_boundary_now_equals_start_is_in_meeting(self):
        emp = self._make_employee("meet_start_edge")
        meeting = self._make_meeting(start_offset_minutes=0, end_offset_minutes=30)
        PlatformMeetingAttendance.objects.create(
            meeting=meeting, employee=emp,
            status=PlatformMeetingAttendance.Status.ATTENDED,
            checked_in_at=self.now,
        )
        summary = get_platform_dashboard_summary(user=self.manager, now=self.now)
        self.assertTrue(self._card_for(summary, emp)["is_in_meeting"])

    def test_boundary_now_equals_end_is_in_meeting(self):
        emp = self._make_employee("meet_end_edge")
        meeting = self._make_meeting(start_offset_minutes=-30, end_offset_minutes=0)
        PlatformMeetingAttendance.objects.create(
            meeting=meeting, employee=emp,
            status=PlatformMeetingAttendance.Status.ATTENDED,
            checked_in_at=self.now - datetime.timedelta(minutes=30),
        )
        summary = get_platform_dashboard_summary(user=self.manager, now=self.now)
        self.assertTrue(self._card_for(summary, emp)["is_in_meeting"])

    # --- الأداء -------------------------------------------------------

    def test_meeting_membership_is_one_query_regardless_of_employee_count(self):
        """استعلامُ العضويّة واحدٌ بموظّفٍ واحدٍ وواحدٌ بخمسة — لا يكبر مع الحلقة.

        قيسٌ بعددٍ مطلقٍ (١) في كلا التشغيلين لا موازنةُ تشغيلٍ بتشغيل: موازنةٌ
        كهذه تمرّ حتى لو كبر العددان معاً، فلا تستطيع السقوط أبداً.
        """
        emp = self._make_employee("meet_query_single")
        meeting = self._make_meeting(start_offset_minutes=-10, end_offset_minutes=20)
        PlatformMeetingAttendance.objects.create(
            meeting=meeting, employee=emp,
            status=PlatformMeetingAttendance.Status.ATTENDED,
            checked_in_at=self.now,
        )

        with CaptureQueriesContext(connection) as ctx_one:
            get_platform_dashboard_summary(user=self.manager, now=self.now)
        queries_with_one_employee = [
            q for q in ctx_one.captured_queries
            if "platform_ops_platformmeetingattendance" in q["sql"].lower()
        ]
        self.assertEqual(
            len(queries_with_one_employee), 1,
            "استعلامُ عضويّة الاجتماع بموظّفٍ واحدٍ يجب أن يكون واحداً بالضبط.",
        )

        for i in range(4):
            other = self._make_employee(f"meet_query_extra_{i}")
            PlatformMeetingAttendance.objects.create(
                meeting=meeting, employee=other,
                status=PlatformMeetingAttendance.Status.ATTENDED,
                checked_in_at=self.now,
            )

        with CaptureQueriesContext(connection) as ctx_five:
            get_platform_dashboard_summary(user=self.manager, now=self.now)
        queries_with_five_employees = [
            q for q in ctx_five.captured_queries
            if "platform_ops_platformmeetingattendance" in q["sql"].lower()
        ]
        self.assertEqual(
            len(queries_with_five_employees), 1,
            "استعلامُ عضويّة الاجتماع كبُر مع عدد الموظّفين — عاد الاستعلامُ إلى داخل الحلقة.",
        )
