"""مصفوفةُ حضور المتقدّمين — «نظرةً واحدةً على حضور كلِّ واحد» (#213-ج).

طلبُ المالك بصورةٍ مرفقة: جدولٌ صفُّه شخصٌ وعمودُه اجتماع، يُقرأ مرّةً فيُعرَف منه
انتظامُ كلِّ مرشَّح؛ والضغطُ على رأس عمودٍ يفتح اجتماعَه، وعلى صفٍّ يفتح ملفَّ
صاحبه — «كلّ شي كليكبل». وزرّا «تحديث» و«تصدير» في الصورة.

وما يُحرَس هنا أربعةُ أشياءَ لا يمسكها المُسلسِلُ ولا `tsc`:

1. **هويّةُ الصفّ** من العمود المولَّد لا من الاسم — متشابها الاسم رجلان.
2. **الفراغُ ليس غياباً**: من لم يُدعَ إلى اجتماعٍ لا خليّةَ له فيه.
3. **المعرّفاتُ في الحمولة**: بلا `meeting` في الخليّة و`applicant` في الصفّ لا
   يكون شيءٌ قابلاً للضغط، ويبقى الجدولُ صورةً.
4. **الاستعلاماتُ لا تنمو مع الصفوف**: المصفوفةُ حاصلُ ضربٍ، فاستعلامٌ لكلّ خليّةٍ
   كان سيقتل الشاشةَ عند أوّل شهرٍ حقيقيّ.
"""
import csv
import io
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from platform_ops.models import (
    ApplicantMeeting,
    ApplicantMeetingAttendee,
    JobApplicant,
    JobPosting,
    PlatformRecruiter,
)
from platform_ops.services import (
    ATTENDANCE_MATRIX_MAX_SPAN_DAYS,
    build_applicant_attendance_matrix,
)

MATRIX = "/api/platform/ops/applicant-meetings/attendance-matrix/"
EXPORT = f"{MATRIX}export/"


class _MatrixFixture(TestCase):
    """اجتماعان ومتقدّمان وضيف — و«نور» حضرت الأوّلَ وغابت عن الثاني."""

    def setUp(self):
        self.client = APIClient()
        self.recruiter = User.objects.create_user(username="matrix-recruiter", password="x")
        PlatformRecruiter.objects.create(user=self.recruiter, is_active=True)
        self.client.force_authenticate(user=self.recruiter)

        self.job = JobPosting.objects.create(
            title="مدخل بيانات", description="إدخال مستندات", token="tok-matrix-1",
        )
        self.noor = JobApplicant.objects.create(
            job=self.job, name="نور الهدى", phone="0790000011", reference_code="REF-X1",
        )
        self.samer = JobApplicant.objects.create(
            job=self.job, name="سامر", phone="0790000012", reference_code="REF-X2",
        )

        now = timezone.now()
        self.first = ApplicantMeeting.objects.create(
            title="مقابلة أولى", start=now - timedelta(days=3), end=now - timedelta(days=3, hours=-1),
        )
        self.second = ApplicantMeeting.objects.create(
            title="مقابلة ثانية", start=now - timedelta(days=1), end=now - timedelta(days=1, hours=-1),
        )

        ApplicantMeetingAttendee.objects.create(
            meeting=self.first, applicant=self.noor,
            status=ApplicantMeetingAttendee.Status.ATTENDED, note="جاهزة.",
        )
        ApplicantMeetingAttendee.objects.create(
            meeting=self.second, applicant=self.noor,
            status=ApplicantMeetingAttendee.Status.ABSENT,
        )
        # سامرٌ في الثاني وحدَه — فخليّتُه في الأوّل يجب أن **تغيب** لا أن تقول «لم يحضر».
        ApplicantMeetingAttendee.objects.create(
            meeting=self.second, applicant=self.samer,
            status=ApplicantMeetingAttendee.Status.INVITED,
        )
        ApplicantMeetingAttendee.objects.create(
            meeting=self.first, guest_name="ضيفٌ بتوصية",
            status=ApplicantMeetingAttendee.Status.ATTENDED,
        )

    def _rows(self, response):
        return {row["name"]: row for row in response.data["rows"]}


class TheMatrixShapeTest(_MatrixFixture):
    def test_one_row_per_person_and_one_column_per_meeting(self):
        response = self.client.get(MATRIX)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            [meeting["id"] for meeting in response.data["meetings"]],
            [self.first.pk, self.second.pk],
            "الأعمدةُ مرتَّبةٌ بالوقت تصاعديّاً — كما يُقرأ الجدولُ من اليمين.",
        )
        self.assertEqual(len(response.data["rows"]), 3)

    def test_a_person_never_invited_to_a_meeting_has_no_cell_in_it(self):
        """«لم يُدعَ» ليست «لم يحضر» — وخلطُهما يحسب غياباً على من لم يُطلَب."""
        row = self._rows(self.client.get(MATRIX))["سامر"]
        self.assertNotIn(str(self.first.pk), row["cells"])
        self.assertIn(str(self.second.pk), row["cells"])
        self.assertEqual(row["absent"], 0)
        self.assertEqual(row["invited"], 1)

    def test_the_row_counts_read_the_persons_whole_record_at_a_glance(self):
        row = self._rows(self.client.get(MATRIX))["نور الهدى"]
        self.assertEqual((row["attended"], row["absent"], row["invited"], row["total"]), (1, 1, 0, 2))

    def test_every_cell_carries_the_ids_that_make_it_clickable(self):
        row = self._rows(self.client.get(MATRIX))["نور الهدى"]
        cell = row["cells"][str(self.first.pk)]
        self.assertEqual(cell["meeting"], self.first.pk)
        self.assertEqual(row["applicant"], self.noor.pk)
        self.assertIn("attendee", cell)
        self.assertEqual(cell["note"], "جاهزة.")

    def test_a_free_guest_has_a_name_but_no_profile_to_open(self):
        """الضيفُ الحرُّ بلا صفٍّ في `JobApplicant` — فرابطٌ إلى ملفّه رابطٌ ميّت."""
        row = self._rows(self.client.get(MATRIX))["ضيفٌ بتوصية"]
        self.assertIsNone(row["applicant"])
        self.assertEqual(row["identity_key"], "g:ضيفٌ بتوصية")

    def test_two_applicants_of_the_same_name_stay_two_rows(self):
        """التجميعُ على `identity_key` لا على الاسم — وإلّا قُرئ انتظامُ رجلٍ لآخر."""
        twin = JobApplicant.objects.create(
            job=self.job, name="سامر", phone="0790000013", reference_code="REF-X3",
        )
        ApplicantMeetingAttendee.objects.create(
            meeting=self.first, applicant=twin,
            status=ApplicantMeetingAttendee.Status.ATTENDED,
        )
        rows = [row for row in self.client.get(MATRIX).data["rows"] if row["name"] == "سامر"]
        self.assertEqual(len(rows), 2)
        self.assertEqual(
            {row["identity_key"] for row in rows},
            {f"a:{self.samer.pk}", f"a:{twin.pk}"},
        )


class TheWindowTest(_MatrixFixture):
    def test_the_window_bounds_which_meetings_become_columns(self):
        response = self.client.get(MATRIX, {
            "from": (timezone.localdate() - timedelta(days=2)).isoformat(),
            "to": timezone.localdate().isoformat(),
        })
        self.assertEqual(
            [meeting["id"] for meeting in response.data["meetings"]], [self.second.pk],
        )
        self.assertNotIn(
            "ضيفٌ بتوصية", self._rows(response),
            "ضيفُ الاجتماع الأوّل خارج النافذة فلا صفَّ له.",
        )

    def test_a_malformed_date_is_refused_not_silently_ignored(self):
        """`parse_date` تعيد `None` للمشوّه كما للغائب — فبلا تفريقٍ يقرأ الطالبُ نافذةً غيرَ نافذته."""
        response = self.client.get(MATRIX, {"from": "2026-13-40"})
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("from", response.data)

    def test_a_backwards_window_is_refused(self):
        response = self.client.get(MATRIX, {"from": "2026-05-01", "to": "2026-04-01"})
        self.assertEqual(response.status_code, 400, response.content)

    def test_a_window_wider_than_the_cap_is_refused(self):
        start = timezone.localdate() - timedelta(days=ATTENDANCE_MATRIX_MAX_SPAN_DAYS + 5)
        response = self.client.get(MATRIX, {
            "from": start.isoformat(), "to": timezone.localdate().isoformat(),
        })
        self.assertEqual(response.status_code, 400, response.content)

    def test_the_default_window_covers_both_the_recent_past_and_what_is_scheduled(self):
        upcoming = ApplicantMeeting.objects.create(
            title="مقابلة قادمة",
            start=timezone.now() + timedelta(days=10),
            end=timezone.now() + timedelta(days=10, hours=1),
        )
        ids = [meeting["id"] for meeting in self.client.get(MATRIX).data["meetings"]]
        self.assertIn(upcoming.pk, ids)
        self.assertIn(self.first.pk, ids)


class TheQueryBudgetTest(_MatrixFixture):
    def test_the_matrix_does_not_issue_a_query_per_cell(self):
        """ثبوتُ العدد مع نموّ الشبكة — لا رقمٌ حرفيٌّ يُعدَّل كلّما أُضيف حقل."""
        few = self._count()
        for index in range(5):
            meeting = ApplicantMeeting.objects.create(
                title=f"مقابلة {index}",
                start=timezone.now() - timedelta(days=5, hours=index),
                end=timezone.now() - timedelta(days=5, hours=index - 1),
            )
            for applicant in (self.noor, self.samer):
                ApplicantMeetingAttendee.objects.create(
                    meeting=meeting, applicant=applicant,
                    status=ApplicantMeetingAttendee.Status.ATTENDED,
                )
        many = self._count()
        self.assertEqual(few, many, f"المصفوفةُ تستعلم لكلّ خليّة: {few} ← {many}.")

    def _count(self) -> int:
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(MATRIX)
        self.assertEqual(response.status_code, 200, response.content)
        return len(ctx.captured_queries)


class TheExportTest(_MatrixFixture):
    def _csv_rows(self, response):
        text = response.content.decode("utf-8-sig")
        return list(csv.reader(io.StringIO(text)))

    def test_the_export_is_the_same_grid_as_a_file(self):
        response = self.client.get(EXPORT)
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response["Content-Type"])
        self.assertIn("attachment;", response["Content-Disposition"])

        rows = self._csv_rows(response)
        self.assertEqual(rows[0][-2:], ["مقابلة أولى", "مقابلة ثانية"])
        by_name = {row[0]: row for row in rows[1:]}
        self.assertEqual(by_name["نور الهدى"][-2:], ["حضر", "لم يحضر"])
        # الخليّةُ الغائبةُ فراغٌ — نفسُ قاعدةِ الشاشة في الملفّ.
        self.assertEqual(by_name["سامر"][-2:], ["", "مدعوّ"])

    def test_the_file_starts_with_a_bom_so_excel_reads_arabic(self):
        """بلا BOM يقرأ إكسل على ويندوز الملفَّ بترميز النظام فتصير العربيّةُ رموزاً."""
        self.assertTrue(self.client.get(EXPORT).content.startswith(b"\xef\xbb\xbf"))

    def test_the_export_honours_the_same_window(self):
        response = self.client.get(EXPORT, {
            "from": (timezone.localdate() - timedelta(days=2)).isoformat(),
            "to": timezone.localdate().isoformat(),
        })
        self.assertEqual(self._csv_rows(response)[0][-1:], ["مقابلة ثانية"])


class TheExportIsDataNotAProgramTest(_MatrixFixture):
    """اسمٌ يبدأ بـ`=` في ملفٍّ يفتحه مسؤولُ التوظيف بنقرة.

    الاسمُ يكتبه المتقدّمُ في نموذج التوظيف العامّ، ويخرج إلى CSV. وإكسل
    وLibreOffice يقرآن خليّةً تبدأ بـ`=` أو `+` أو `-` أو `@` **صيغةً تُنفَّذ**.
    """

    def test_a_name_that_starts_like_a_formula_stays_text(self):
        ApplicantMeetingAttendee.objects.create(meeting=self.first, guest_name="=1+1")
        self.client.force_authenticate(self.recruiter)
        response = self.client.get(EXPORT)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.content.decode("utf-8-sig")
        self.assertIn("'=1+1", body, "اسمٌ يبدأ بـ`=` خرج صيغةً لا نصّاً.")
        self.assertNotIn(chr(10) + "=1+1", body, "خليّةٌ تبدأ بـ`=` بلا تهريب.")


class TheDoorTest(_MatrixFixture):
    def test_a_stranger_gets_nothing(self):
        """البابُ `IsPlatformRecruiter` نفسُه الذي يحرس بقيّةَ شاشة التوظيف."""
        outsider = User.objects.create_user(username="matrix-outsider", password="x")
        client = APIClient()
        client.force_authenticate(user=outsider)
        for url in (MATRIX, EXPORT):
            with self.subTest(url=url):
                self.assertEqual(client.get(url).status_code, 403)

    def test_the_super_admin_reads_it_like_the_recruiter(self):
        admin = User.objects.create_superuser(
            username="matrix-admin", email="matrix-admin@platform.local", password="x",
        )
        client = APIClient()
        client.force_authenticate(user=admin)
        self.assertEqual(client.get(MATRIX).status_code, 200)


class TheServiceIsTheOneRuleTest(_MatrixFixture):
    def test_the_view_adds_no_rule_of_its_own(self):
        """نفسُ النتيجة من الخدمة مباشرةً ومن الباب — فالقاعدةُ في موضعٍ واحد."""
        direct = build_applicant_attendance_matrix()
        through_http = self.client.get(MATRIX).data
        self.assertEqual(
            [row["identity_key"] for row in direct["rows"]],
            [row["identity_key"] for row in through_http["rows"]],
        )
        self.assertEqual(direct["from"], through_http["from"])
