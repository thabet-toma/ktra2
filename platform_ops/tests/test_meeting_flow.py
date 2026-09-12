"""تدفّقُ اجتماعات المنصّة الكامل: الإنشاءُ والدعوةُ والدخولُ والاعتذارُ والبتُّ (211-F).

`test_meetings.py` يحرس النموذجَين وحدَهما (فرادةٌ، قيدُ قاعدةٍ، حالاتٌ خمس)؛ هذا
الملفُّ يغطي ما فوقهما — طبقةَ الخدمة والواجهة: الفعلَ الذي طلبه المالك حرفياً
(«يحطّ دخول ... ويصير حاضر ويتسجّل بسجلّ حضور الاجتماعات»، و«يحطّ ملاحظة ليش ما
بدّه يحضر»)، ومَن يملك أن يفعل ماذا.
"""
import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from platform_ops.models import (
    PlatformActivityLog,
    PlatformEmployee,
    PlatformMeeting,
    PlatformMeetingAttendance,
)
from platform_ops.services import (
    MEETING_CHECK_IN_EARLY_WINDOW_MINUTES,
    PlatformOpsError,
    cancel_platform_meeting,
    check_in_to_meeting,
    decide_meeting_excuse,
    invite_employees_to_meeting,
    submit_meeting_excuse,
)

User = get_user_model()


class _MeetingFlowFixture(TestCase):
    """مديرٌ وثلاثةُ موظّفين واجتماعٌ واحدٌ يُدعى إليه اثنان منهم فقط — (ج) خارج القائمة عمداً."""

    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_superuser(
            username="meet_manager", email="meet_manager@platform.local", password="x",
        )
        cls.user_a = User.objects.create_user(username="meet_staff_a", password="x")
        cls.user_b = User.objects.create_user(username="meet_staff_b", password="x")
        cls.user_c = User.objects.create_user(username="meet_staff_c", password="x")
        cls.employee_a = PlatformEmployee.objects.create(user=cls.user_a, status=PlatformEmployee.Status.ACTIVE)
        cls.employee_b = PlatformEmployee.objects.create(user=cls.user_b, status=PlatformEmployee.Status.ACTIVE)
        cls.employee_c = PlatformEmployee.objects.create(user=cls.user_c, status=PlatformEmployee.Status.ACTIVE)

        cls.now = timezone.now()
        cls.meeting = PlatformMeeting.objects.create(
            title="اجتماعُ الفريق",
            start=cls.now,
            end=cls.now + datetime.timedelta(hours=1),
            meeting_link="https://meet.example.test/team",
            created_by=cls.manager,
        )
        invite_employees_to_meeting(meeting=cls.meeting, employee_ids=[cls.employee_a.pk, cls.employee_b.pk])
        cls.attendance_a = PlatformMeetingAttendance.objects.get(meeting=cls.meeting, employee=cls.employee_a)
        cls.attendance_b = PlatformMeetingAttendance.objects.get(meeting=cls.meeting, employee=cls.employee_b)

    def setUp(self):
        self.client = APIClient()


class InvitationIdempotencyTest(_MeetingFlowFixture):
    def test_inviting_the_same_employee_twice_is_idempotent(self):
        """لا استثناء، ولا صفٌّ ثانٍ — دعوةٌ مكرّرة فعلٌ بشريٌّ عاديّ لا خطأ."""
        before = PlatformMeetingAttendance.objects.filter(meeting=self.meeting).count()
        invite_employees_to_meeting(meeting=self.meeting, employee_ids=[self.employee_a.pk])
        after = PlatformMeetingAttendance.objects.filter(meeting=self.meeting).count()
        self.assertEqual(before, after, "دعوةٌ مكرّرة أنشأت صفّاً ثانياً — الفرادةُ انكسرت في طبقة الخدمة.")
        self.attendance_a.refresh_from_db()
        self.assertEqual(self.attendance_a.status, PlatformMeetingAttendance.Status.ABSENT)

    def test_inviting_a_mix_of_new_and_already_invited_only_adds_the_new_ones(self):
        invite_employees_to_meeting(
            meeting=self.meeting, employee_ids=[self.employee_a.pk, self.employee_c.pk],
        )
        self.assertTrue(
            PlatformMeetingAttendance.objects.filter(meeting=self.meeting, employee=self.employee_c).exists(),
        )
        self.assertEqual(
            PlatformMeetingAttendance.objects.filter(meeting=self.meeting).count(), 3,
            "موظّفان أصليّان + واحدٌ جديد = ثلاثة، لا أربعة (لا تكرار للموظّف أ).",
        )

    def test_a_row_inserted_after_the_pre_filter_does_not_discard_the_rest_of_the_batch(self):
        """سباقٌ حقيقيّ: صفُّ (أ) يظهر بين القراءة والإدراج — فلا يضيع (ج) معه.

        القراءةُ المسبقةُ تستبعد المدعوَّ سلفاً فلا تصطدم الدفعةُ في الحالة
        العاديّة؛ والاصطدامُ لا يقع إلاّ حين يُدرَج صفٌّ **بعد** تلك القراءة. يُحاكى
        ذلك بإعماء القراءة عن صفِّ (أ)، فيدخل (أ) و(ج) معاً في دفعةٍ يصطدم أوّلُها.

        بالتقاط `IntegrityError` حول الدفعة كانت نقطةُ الحفظ تُرجِع **العبارةَ
        بتمامها** فيضيع (ج) معه بصمتٍ والطلبُ ناجح؛ ومع `ignore_conflicts` تتخطّى
        القاعدةُ الصفَّ المصطدمَ وحدَه.
        """
        real_filter = PlatformMeetingAttendance.objects.filter
        hidden_pk = self.employee_a.pk

        def filter_blind_to_a(*args, **kwargs):
            queryset = real_filter(*args, **kwargs)
            if "employee_id__in" in kwargs:
                return queryset.exclude(employee_id=hidden_pk)
            return queryset

        with mock.patch.object(PlatformMeetingAttendance.objects, "filter", filter_blind_to_a):
            invite_employees_to_meeting(
                meeting=self.meeting, employee_ids=[self.employee_a.pk, self.employee_c.pk],
            )

        self.assertTrue(
            PlatformMeetingAttendance.objects.filter(meeting=self.meeting, employee=self.employee_c).exists(),
            "المدعوُّ الجديد (ج) ضاع لأنّ مدعوّاً آخرَ في الدفعة اصطدم — الدفعةُ كلُّها تراجعت.",
        )
        self.assertEqual(
            PlatformMeetingAttendance.objects.filter(meeting=self.meeting).count(), 3,
            "أ وب الأصليّان + ج = ثلاثة؛ والصفُّ المصطدمُ لم يتكرّر.",
        )

    def test_empty_invite_list_is_rejected(self):
        with self.assertRaises(PlatformOpsError) as ctx:
            invite_employees_to_meeting(meeting=self.meeting, employee_ids=[])
        self.assertEqual(ctx.exception.code, "employee_ids_required")


class CancellationAuditTest(_MeetingFlowFixture):
    """الإلغاءُ يُقيَّد على دفتر كلِّ مدعوٍّ، والفاعلُ معه — و«كلّه محفوظ» يشمله."""

    def test_cancelling_writes_one_log_per_invitee_naming_the_actor(self):
        before = PlatformActivityLog.objects.filter(entity_type="platform_meeting").count()
        cancel_platform_meeting(meeting=self.meeting, actor=self.manager)
        rows = PlatformActivityLog.objects.filter(
            entity_type="platform_meeting", entity_id=str(self.meeting.pk),
        )
        self.assertEqual(
            rows.count(), 2, "مدعوّان (أ وب) — سجلّان، فلو كان الفاعلُ مهمَلاً لما كُتب أيٌّ منهما.",
        )
        self.assertEqual(
            {row.employee_id for row in rows}, {self.employee_a.pk, self.employee_b.pk},
        )
        for row in rows:
            self.assertEqual(row.details.get("actor_user_id"), self.manager.pk)
        self.assertEqual(before + 2, PlatformActivityLog.objects.filter(entity_type="platform_meeting").count())

    def test_cancelling_twice_does_not_write_the_log_twice(self):
        """الحارسُ على الحالة يشمل التقييد — وإلاّ امتلأ دفترُ الموظّف بإلغاءٍ واحدٍ مكرّر."""
        cancel_platform_meeting(meeting=self.meeting, actor=self.manager)
        cancel_platform_meeting(meeting=self.meeting, actor=self.manager)
        self.assertEqual(
            PlatformActivityLog.objects.filter(
                entity_type="platform_meeting", entity_id=str(self.meeting.pk),
            ).count(),
            2,
        )


class CheckInTest(_MeetingFlowFixture):
    def test_employee_checks_in_and_gets_the_link_back(self):
        self.client.force_authenticate(self.user_a)
        response = self.client.post(f"/api/platform/ops/meetings/{self.meeting.pk}/check-in/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        self.assertEqual(response.data["meeting_link"], self.meeting.meeting_link)
        self.assertEqual(response.data["status"], PlatformMeetingAttendance.Status.ATTENDED)
        self.attendance_a.refresh_from_db()
        self.assertEqual(self.attendance_a.status, PlatformMeetingAttendance.Status.ATTENDED)
        self.assertIsNotNone(self.attendance_a.checked_in_at)

    def test_ledger_shows_the_caller_as_attended_and_the_other_invitee_as_absent(self):
        self.client.force_authenticate(self.user_a)
        self.client.post(f"/api/platform/ops/meetings/{self.meeting.pk}/check-in/")
        self.client.force_authenticate(self.manager)
        response = self.client.get(f"/api/platform/ops/meetings/{self.meeting.pk}/attendance/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        rows = {row["employee"]: row["status"] for row in response.data}
        self.assertEqual(rows[self.employee_a.pk], PlatformMeetingAttendance.Status.ATTENDED)
        self.assertEqual(rows[self.employee_b.pk], PlatformMeetingAttendance.Status.ABSENT)

    def test_cannot_check_in_to_a_cancelled_meeting(self):
        cancel_platform_meeting(meeting=self.meeting, actor=self.manager)
        with self.assertRaises(PlatformOpsError) as ctx:
            check_in_to_meeting(meeting=self.meeting, employee=self.employee_a)
        self.assertEqual(ctx.exception.code, "meeting_cancelled")
        self.attendance_a.refresh_from_db()
        self.assertEqual(
            self.attendance_a.status, PlatformMeetingAttendance.Status.ABSENT,
            "الرفضُ يجب أن يمنع أيّ كتابةٍ على الصفّ — لا حضورَ جزئيّاً.",
        )

    def test_cannot_check_in_before_the_window_opens(self):
        too_early = self.meeting.start - datetime.timedelta(
            minutes=MEETING_CHECK_IN_EARLY_WINDOW_MINUTES + 1,
        )
        with self.assertRaises(PlatformOpsError) as ctx:
            check_in_to_meeting(meeting=self.meeting, employee=self.employee_a, now=too_early)
        self.assertEqual(ctx.exception.code, "outside_check_in_window")

    def test_cannot_check_in_after_the_meeting_has_ended(self):
        too_late = self.meeting.end + datetime.timedelta(minutes=1)
        with self.assertRaises(PlatformOpsError) as ctx:
            check_in_to_meeting(meeting=self.meeting, employee=self.employee_a, now=too_late)
        self.assertEqual(ctx.exception.code, "outside_check_in_window")

    def test_check_in_exactly_at_the_early_window_boundary_succeeds(self):
        """حدُّ النافذة نفسُه لا مركزُها — لإثبات أنّ الحدّ صحيحٌ لا تقريبيّ."""
        just_inside = self.meeting.start - datetime.timedelta(
            minutes=MEETING_CHECK_IN_EARLY_WINDOW_MINUTES,
        )
        attendance = check_in_to_meeting(meeting=self.meeting, employee=self.employee_a, now=just_inside)
        self.assertEqual(attendance.status, PlatformMeetingAttendance.Status.ATTENDED)

    def test_employee_cannot_check_in_on_a_colleague_behalf(self):
        """لا معاملَ «موظّف» في الطلب أصلاً — الهويّةُ من الجلسة، فحقلٌ دخيلٌ لا يُطاع.

        (ب) يرسل بياناتٍ تحاول انتحال (أ)؛ لا يقرأ `check_in` من جسم الطلب شيئاً
        سوى `request.user`، فيبقى الأثرُ على صفّ المستدعي نفسِه (ب) لا صفّ (أ).
        """
        self.client.force_authenticate(self.user_b)
        response = self.client.post(
            f"/api/platform/ops/meetings/{self.meeting.pk}/check-in/",
            {"employee": self.employee_a.pk},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        self.attendance_a.refresh_from_db()
        self.attendance_b.refresh_from_db()
        self.assertEqual(
            self.attendance_a.status, PlatformMeetingAttendance.Status.ABSENT,
            "تسريب: صفُّ (أ) تأثّر بطلبٍ أرسله (ب).",
        )
        self.assertEqual(self.attendance_b.status, PlatformMeetingAttendance.Status.ATTENDED)

    def test_check_in_returns_404_for_an_uninvited_employee(self):
        """(ج) غيرُ مدعوٍّ أصلاً — لا صفَّ حضورٍ له، فـ`get_queryset` المضيَّقة تخفي الاجتماع كلَّه."""
        self.client.force_authenticate(self.user_c)
        response = self.client.post(f"/api/platform/ops/meetings/{self.meeting.pk}/check-in/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND, response.content)

    def test_manager_cannot_check_in_without_an_employee_profile(self):
        """المديرُ ليس موظّفَ منصّةٍ بالضرورة — لا صفَّ `PlatformEmployee` له هنا فيُرفَض بوضوح."""
        self.client.force_authenticate(self.manager)
        response = self.client.post(f"/api/platform/ops/meetings/{self.meeting.pk}/check-in/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.content)
        self.assertEqual(response.data["code"], "not_a_platform_employee")


class ExcuseTest(_MeetingFlowFixture):
    def test_employee_submits_excuse_becomes_pending(self):
        self.client.force_authenticate(self.user_a)
        response = self.client.post(
            f"/api/platform/ops/meetings/{self.meeting.pk}/excuse/", {"note": "التزامٌ طبّي."},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        self.assertEqual(response.data["status"], PlatformMeetingAttendance.Status.EXCUSED_PENDING)
        self.attendance_a.refresh_from_db()
        self.assertEqual(self.attendance_a.status, PlatformMeetingAttendance.Status.EXCUSED_PENDING)
        self.assertEqual(self.attendance_a.excuse_note, "التزامٌ طبّي.")

    def test_employee_cannot_move_their_own_excuse_to_accepted_by_any_route(self):
        """لا مسارَ فيه — لا حقلَ `status`/`accepted` مكشوفاً لغير المدير في أيّ نقطة."""
        self.client.force_authenticate(self.user_a)
        submit = self.client.post(
            f"/api/platform/ops/meetings/{self.meeting.pk}/excuse/",
            {"note": "سفرٌ مفاجئ.", "status": "excused_accepted", "accepted": True},
        )
        self.assertEqual(submit.status_code, status.HTTP_200_OK, submit.content)
        self.attendance_a.refresh_from_db()
        self.assertEqual(
            self.attendance_a.status, PlatformMeetingAttendance.Status.EXCUSED_PENDING,
            "حقولٌ دخيلةٌ في جسم الطلب رفعت الحالةَ مباشرةً إلى مقبول.",
        )
        # والمسارُ الوحيدُ الذي يقبل حالةً مقبولة (`decide-excuse`) مغلقٌ على غير المدير.
        decide = self.client.post(
            f"/api/platform/ops/meetings/{self.meeting.pk}/decide-excuse/",
            {"attendance": self.attendance_a.pk, "accepted": True},
        )
        self.assertEqual(decide.status_code, status.HTTP_403_FORBIDDEN, decide.content)
        self.attendance_a.refresh_from_db()
        self.assertEqual(self.attendance_a.status, PlatformMeetingAttendance.Status.EXCUSED_PENDING)

    def test_cannot_submit_a_new_excuse_on_a_cancelled_meeting(self):
        cancel_platform_meeting(meeting=self.meeting, actor=self.manager)
        with self.assertRaises(PlatformOpsError) as ctx:
            submit_meeting_excuse(meeting=self.meeting, employee=self.employee_a, note="سببٌ.")
        self.assertEqual(ctx.exception.code, "meeting_cancelled")
        self.attendance_a.refresh_from_db()
        self.assertEqual(self.attendance_a.status, PlatformMeetingAttendance.Status.ABSENT)

    def test_excuse_requires_a_note(self):
        with self.assertRaises(PlatformOpsError) as ctx:
            submit_meeting_excuse(meeting=self.meeting, employee=self.employee_a, note="   ")
        self.assertEqual(ctx.exception.code, "excuse_note_required")
        self.attendance_a.refresh_from_db()
        self.assertEqual(self.attendance_a.status, PlatformMeetingAttendance.Status.ABSENT)


class DecideExcuseTest(_MeetingFlowFixture):
    def setUp(self):
        super().setUp()
        submit_meeting_excuse(meeting=self.meeting, employee=self.employee_a, note="سفرٌ عائليّ.")
        self.attendance_a.refresh_from_db()

    def test_manager_accepts_an_excuse_and_records_decider_and_time(self):
        self.client.force_authenticate(self.manager)
        response = self.client.post(
            f"/api/platform/ops/meetings/{self.meeting.pk}/decide-excuse/",
            {"attendance": self.attendance_a.pk, "accepted": True},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        self.attendance_a.refresh_from_db()
        self.assertEqual(self.attendance_a.status, PlatformMeetingAttendance.Status.EXCUSED_ACCEPTED)
        self.assertEqual(self.attendance_a.excuse_decided_by_id, self.manager.pk)
        self.assertIsNotNone(self.attendance_a.excuse_decided_at)

    def test_manager_rejects_an_excuse_and_records_decider_and_time(self):
        self.client.force_authenticate(self.manager)
        response = self.client.post(
            f"/api/platform/ops/meetings/{self.meeting.pk}/decide-excuse/",
            {"attendance": self.attendance_a.pk, "accepted": False},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        self.attendance_a.refresh_from_db()
        self.assertEqual(self.attendance_a.status, PlatformMeetingAttendance.Status.EXCUSED_REJECTED)
        self.assertEqual(self.attendance_a.excuse_decided_by_id, self.manager.pk)
        self.assertIsNotNone(self.attendance_a.excuse_decided_at)

    def test_deciding_an_already_decided_excuse_is_rejected(self):
        decide_meeting_excuse(attendance=self.attendance_a, accepted=True, actor=self.manager)
        with self.assertRaises(PlatformOpsError) as ctx:
            decide_meeting_excuse(attendance=self.attendance_a, accepted=False, actor=self.manager)
        self.assertEqual(ctx.exception.code, "excuse_not_pending")

    def test_staff_cannot_decide_excuses(self):
        self.client.force_authenticate(self.user_b)
        response = self.client.post(
            f"/api/platform/ops/meetings/{self.meeting.pk}/decide-excuse/",
            {"attendance": self.attendance_a.pk, "accepted": True},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.content)
        self.attendance_a.refresh_from_db()
        self.assertEqual(self.attendance_a.status, PlatformMeetingAttendance.Status.EXCUSED_PENDING)


class LedgerCountsTest(_MeetingFlowFixture):
    def test_n_invited_and_k_attended_reports_n_minus_k_absentees(self):
        """ثلاثةٌ مدعوّون بعد ضمّ (ج)، اثنان يحضران، فالدفترُ يُظهر غائباً واحداً بالضبط."""
        invite_employees_to_meeting(meeting=self.meeting, employee_ids=[self.employee_c.pk])
        check_in_to_meeting(meeting=self.meeting, employee=self.employee_a)
        check_in_to_meeting(meeting=self.meeting, employee=self.employee_c)

        self.client.force_authenticate(self.manager)
        response = self.client.get(f"/api/platform/ops/meetings/{self.meeting.pk}/attendance/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.content)
        statuses = [row["status"] for row in response.data]
        self.assertEqual(len(statuses), 3)
        self.assertEqual(statuses.count(PlatformMeetingAttendance.Status.ATTENDED), 2)
        self.assertEqual(statuses.count(PlatformMeetingAttendance.Status.ABSENT), 1)

    def test_staff_cannot_read_the_full_ledger(self):
        """دفترُ الحضور الكامل لمدير العمليات وحده — لا فرقَ بين قراءة صفّه وصفّ غيره هنا: كلّه محجوب."""
        self.client.force_authenticate(self.user_a)
        response = self.client.get(f"/api/platform/ops/meetings/{self.meeting.pk}/attendance/")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN, response.content)
