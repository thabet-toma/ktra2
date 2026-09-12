"""اختبارات نموذجَي اجتماع المنصة وحضوره (م٥ من #211).

تغطي:
1. فرادة (اجتماع، موظف) — صفٌّ ثانٍ لنفس الزوج يسقط بـIntegrityError حقيقي.
2. الحالات الخمس تتمايز بمرشِّح queryset: معلّق ≠ مقبول ≠ غائبٌ صرف.
3. الاجتماع الملغى يُستعلَم عنه بحالته.
4. بداية قبل نهاية مفروضة بقيد قاعدة بيانات لا `clean()` فقط.
"""
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from platform_ops.models import PlatformEmployee, PlatformMeeting, PlatformMeetingAttendance

User = get_user_model()


class PlatformMeetingModelsTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(
            username="super_meet", email="super_meet@platform.local", password="x",
        )
        self.user_a = User.objects.create_user(username="staff_meet_a", password="x")
        self.user_b = User.objects.create_user(username="staff_meet_b", password="x")
        self.employee_a = PlatformEmployee.objects.create(user=self.user_a, status=PlatformEmployee.Status.ACTIVE)
        self.employee_b = PlatformEmployee.objects.create(user=self.user_b, status=PlatformEmployee.Status.ACTIVE)

        now = timezone.now()
        self.meeting = PlatformMeeting.objects.create(
            title="اجتماع الفريق الأسبوعي",
            agenda="مراجعة الأداء",
            start=now + timedelta(hours=1),
            end=now + timedelta(hours=2),
            meeting_link="https://meet.example.com/weekly",
            created_by=self.admin,
        )

    def test_duplicate_attendance_row_raises_integrity_error(self):
        """صفّان لنفس (اجتماع، موظف) يخالفان قيداً حقيقياً — لولا القيد لنجحا كلاهما بصمت.

        لو حُذف `UniqueConstraint` سينجح الإنشاء الثاني دون أي استثناء، فيتضاعف
        وزن الموظف في محور الانتظام لاحقاً؛ هذا الاختبار يسقط في تلك الحالة بالضبط.
        """
        PlatformMeetingAttendance.objects.create(
            meeting=self.meeting, employee=self.employee_a,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PlatformMeetingAttendance.objects.create(
                    meeting=self.meeting, employee=self.employee_a,
                )

    def test_five_statuses_round_trip_and_are_queryable_distinctly(self):
        """المعلّق يُميَّز عن المقبول والمرفوض والغياب الصِّرف بمرشِّح queryset واحد.

        لو دُمج «معلّق» و«مقبول» في قيمة واحدة (كما يحدث ببوليان بدل TextChoices)
        لظهر عذرٌ لم يُبتّ فيه ضمن استعلام «المقبول» فيُسقط عقوبة لم تُقرَّر بعد؛
        هذا الاختبار يسقط لو حدث ذلك لأن العدّ سيختلف.
        """
        attended = PlatformMeetingAttendance.objects.create(
            meeting=self.meeting, employee=self.employee_a,
            status=PlatformMeetingAttendance.Status.ATTENDED,
            checked_in_at=timezone.now(),
        )
        pending = PlatformMeetingAttendance.objects.create(
            meeting=self.meeting, employee=self.employee_b,
            status=PlatformMeetingAttendance.Status.EXCUSED_PENDING,
            excuse_note="عندي التزام طبي",
        )

        other_meeting = PlatformMeeting.objects.create(
            title="اجتماع آخر",
            start=timezone.now() + timedelta(days=1),
            end=timezone.now() + timedelta(days=1, hours=1),
            meeting_link="https://meet.example.com/other",
            created_by=self.admin,
        )
        accepted = PlatformMeetingAttendance.objects.create(
            meeting=other_meeting, employee=self.employee_a,
            status=PlatformMeetingAttendance.Status.EXCUSED_ACCEPTED,
            excuse_note="سفر", excuse_decided_by=self.admin, excuse_decided_at=timezone.now(),
        )
        rejected = PlatformMeetingAttendance.objects.create(
            meeting=other_meeting, employee=self.employee_b,
            status=PlatformMeetingAttendance.Status.EXCUSED_REJECTED,
            excuse_note="لا شيء", excuse_decided_by=self.admin, excuse_decided_at=timezone.now(),
        )
        # اجتماعٌ ثالث بصفّ غياب صِرف بلا عذر إطلاقاً، لتمييزه عن المعلّق/المقبول/المرفوض.
        third_meeting = PlatformMeeting.objects.create(
            title="اجتماع ثالث",
            start=timezone.now() + timedelta(days=2),
            end=timezone.now() + timedelta(days=2, hours=1),
            meeting_link="https://meet.example.com/third",
            created_by=self.admin,
        )
        plain_absent = PlatformMeetingAttendance.objects.create(
            meeting=third_meeting, employee=self.employee_a,
        )

        pending_qs = PlatformMeetingAttendance.objects.filter(
            status=PlatformMeetingAttendance.Status.EXCUSED_PENDING,
        )
        self.assertEqual(list(pending_qs), [pending])

        accepted_qs = PlatformMeetingAttendance.objects.filter(
            status=PlatformMeetingAttendance.Status.EXCUSED_ACCEPTED,
        )
        self.assertEqual(list(accepted_qs), [accepted])

        rejected_qs = PlatformMeetingAttendance.objects.filter(
            status=PlatformMeetingAttendance.Status.EXCUSED_REJECTED,
        )
        self.assertEqual(list(rejected_qs), [rejected])

        absent_qs = PlatformMeetingAttendance.objects.filter(
            status=PlatformMeetingAttendance.Status.ABSENT,
        )
        self.assertEqual(list(absent_qs), [plain_absent])
        self.assertNotIn(pending, absent_qs)
        self.assertNotIn(accepted, absent_qs)
        self.assertNotIn(rejected, absent_qs)

        attended_qs = PlatformMeetingAttendance.objects.filter(
            status=PlatformMeetingAttendance.Status.ATTENDED,
        )
        self.assertEqual(list(attended_qs), [attended])

    def test_cancelled_meeting_is_queryable_by_status(self):
        """الاجتماع الملغى يُستعلَم عنه بحالته — لولا الحقل لاستحال تمييزه عن مجدول منتهٍ."""
        self.meeting.status = PlatformMeeting.Status.CANCELLED
        self.meeting.save(update_fields=["status"])

        cancelled_qs = PlatformMeeting.objects.filter(status=PlatformMeeting.Status.CANCELLED)
        self.assertIn(self.meeting, cancelled_qs)

        scheduled_qs = PlatformMeeting.objects.filter(status=PlatformMeeting.Status.SCHEDULED)
        self.assertNotIn(self.meeting, scheduled_qs)

    def test_start_before_end_enforced_by_db_constraint(self):
        """نهاية قبل البداية تسقط بقيد قاعدة البيانات — وليس بمجرد `full_clean()`.

        استُخدم `CheckConstraint` لا `clean()` وحده لأن `clean()` لا يحمي
        `bulk_create` ولا الكتابة المباشرة عبر `objects.create()`؛ هذا الاختبار
        يستدعي `create()` مباشرة دون `full_clean()` فلن يسقط لو كان الحارس
        الوحيد `clean()` بلا قيد فعلي على القاعدة.
        """
        now = timezone.now()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                PlatformMeeting.objects.create(
                    title="اجتماع بترتيب زمني خاطئ",
                    start=now + timedelta(hours=2),
                    end=now + timedelta(hours=1),
                    meeting_link="https://meet.example.com/bad",
                    created_by=self.admin,
                )
