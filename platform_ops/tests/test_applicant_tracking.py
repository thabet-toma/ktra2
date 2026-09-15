"""‏#215 — صفحةُ متابعةِ المتقدّم: الدفترُ، والبابُ العامُّ بعاملين، وسطحُ الفريق.

كلُّ تأكيدٍ هنا مكتوبٌ على عطبٍ يستطيع أن يقع فعلاً:

- **الفشلُ الموحَّد**: لو ميّز الردُّ بين «رمزٌ معدوم» و«هاتفٌ خاطئ» لصارت
  الصفحةُ عرّافاً يؤكّد وجودَ الرموز — والرابطُ منشورٌ على فيسبوك عمداً.
- **تقليلُ الحمولة**: الاسمُ والهاتفُ والبريدُ و`notes` و`rating` و`cv_url` لا
  يخرج شيءٌ منها من بابٍ عامّ (OWASP API3).
- **الدفترُ يُكتب تحت القفل**: انتقالٌ بلا صفٍّ يعني تاريخاً ممحوّاً بلا شكوى.
- **العدُّ عمودٌ في استعلامٍ قائم**: `unread_reply_count` لكلّ صفٍّ باستعلامٍ
  مستقلٍّ هو عطبُ N+1 نفسُه الذي أُصلح في هذا المستودع مرّتين.
"""
import datetime

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.db import connection
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from platform_ops.models import (
    ApplicantMeeting,
    ApplicantMeetingAttendee,
    JobApplicant,
    JobApplicantUpdate,
)
from platform_ops.services import (
    APPLICANT_PUBLIC_STATUS_LABELS,
    TRACKING_DENIED_DETAIL,
    TRACKING_FAILURE_LIMIT,
    ApplicantReplyClosed,
    TrackingDenied,
    TrackingSessionExpired,
    applicant_public_status_label,
    applicant_upcoming_meetings,
    create_job_posting,
    create_platform_recruiter,
    issue_tracking_session,
    normalize_tracking_code,
    phones_match,
    publish_applicant_notice,
    record_applicant_reply,
    resolve_applicant_tracking,
    resolve_tracking_session,
    submit_application,
    transition_applicant_status,
)


class ApplicantTrackingBaseTests(TestCase):
    """أرضيّةٌ مشتركة: إعلانٌ ومتقدّمٌ واحدٌ حقيقيّان."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.admin_user = User.objects.create_user(
            username="admin215", password="Str0ng!Pass215", is_superuser=True, is_staff=True
        )
        self.recruiter_user = User.objects.create_user(
            username="recruiter215", password="Str0ng!Pass215"
        )
        create_platform_recruiter(user=self.recruiter_user)
        self.job = create_job_posting(
            title="محاسب",
            description="وصفُ الوظيفة",
            created_by=self.admin_user,
        )
        self.applicant = submit_application(
            job=self.job,
            name="سميّة عبد الله",
            phone="0791234567",
            email="s@example.com",
        )

    def tearDown(self):
        cache.clear()

    @property
    def track_url(self):
        return f"/api/careers/jobs/{self.job.token}/track/"

    def open_session(self):
        res = self.client.post(
            self.track_url,
            {"reference_code": self.applicant.reference_code, "phone": "0791234567"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        return res.data["session"]


class ApplicantUpdateLedgerTests(ApplicantTrackingBaseTests):
    """‏215-أ: الدفترُ نفسُه."""

    def test_applying_opens_the_ledger_with_a_first_line(self):
        """صفحةٌ تُفتَح على فراغٍ لا تقول لصاحبها إن كان طلبُه وصل أصلاً."""
        rows = list(JobApplicantUpdate.objects.filter(applicant=self.applicant))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].kind, JobApplicantUpdate.Kind.STATUS)
        self.assertEqual(rows[0].author_kind, JobApplicantUpdate.AuthorKind.SYSTEM)
        self.assertEqual(rows[0].to_status, JobApplicant.Status.NEW)
        self.assertTrue(rows[0].is_public)

    def test_every_status_move_leaves_a_row_read_from_the_database(self):
        """الحالةُ عمودٌ يُكتب فوقه: بلا هذا الصفّ لا تاريخَ للمراحل إطلاقاً.

        والقراءةُ **من القاعدة** لا من الكائن العائد: حقلٌ يُسنَد في الذاكرة
        ولا يصل القاعدة عطبٌ وقع في هذا الموديول فعلاً (`update_fields`).
        """
        transition_applicant_status(
            applicant=self.applicant,
            target_status=JobApplicant.Status.SCREENING,
            actor=self.recruiter_user,
        )
        row = (
            JobApplicantUpdate.objects.filter(
                applicant_id=self.applicant.pk, kind=JobApplicantUpdate.Kind.STATUS
            )
            .order_by("-id")
            .first()
        )
        self.assertIsNotNone(row)
        self.assertEqual(row.from_status, JobApplicant.Status.NEW)
        self.assertEqual(row.to_status, JobApplicant.Status.SCREENING)
        self.assertEqual(row.author_id, self.recruiter_user.pk)

    def test_the_rejected_applicant_is_not_told_the_word_rejected(self):
        """نفسُ الحقيقة بلا كلمةٍ تبقى على شاشته."""
        label = applicant_public_status_label(JobApplicant.Status.REJECTED)
        self.assertNotIn("مرفوض", label)
        self.assertEqual(label, APPLICANT_PUBLIC_STATUS_LABELS[JobApplicant.Status.REJECTED])

    def test_every_declared_status_has_a_public_label(self):
        """حالةٌ تُضاف غداً بلا نصٍّ تُعرَض رمزاً إنجليزيّاً خامّاً على عربيّ."""
        for value, _ in JobApplicant.Status.choices:
            self.assertIn(value, APPLICANT_PUBLIC_STATUS_LABELS, value)

    def test_a_notice_without_a_body_is_refused(self):
        with self.assertRaises(ValidationError):
            publish_applicant_notice(applicant=self.applicant, body="   ")

    def test_replying_is_closed_once_the_application_is_closed(self):
        """بابٌ مفتوحٌ لا يُجاب أسوأُ من بابٍ مغلقٍ بوضوح."""
        transition_applicant_status(
            applicant=self.applicant, target_status=JobApplicant.Status.REJECTED
        )
        self.applicant.refresh_from_db()
        with self.assertRaises(ApplicantReplyClosed):
            record_applicant_reply(applicant=self.applicant, body="لماذا؟")

    def test_answering_marks_the_applicants_reply_read(self):
        """من كتب جواباً فقد قرأ السؤال — وزرٌّ منفصلٌ يُنسى فيصرخ العدّاد أبداً."""
        reply = record_applicant_reply(applicant=self.applicant, body="سؤال")
        self.assertIsNone(reply.read_at)
        publish_applicant_notice(
            applicant=self.applicant, body="جواب", actor=self.recruiter_user
        )
        reply.refresh_from_db()
        self.assertIsNotNone(reply.read_at)

    def test_only_upcoming_scheduled_meetings_reach_the_applicant(self):
        """اجتماعٌ ملغىً أو منقضٍ يُربك من يقرأ، ولا يخدمه في شيء."""
        now = timezone.now()
        upcoming = ApplicantMeeting.objects.create(
            title="مقابلة أولى",
            start=now + datetime.timedelta(days=2),
            end=now + datetime.timedelta(days=2, hours=1),
            location="https://meet.example/abc",
        )
        past = ApplicantMeeting.objects.create(
            title="مقابلة قديمة",
            start=now - datetime.timedelta(days=5),
            end=now - datetime.timedelta(days=5) + datetime.timedelta(hours=1),
        )
        cancelled = ApplicantMeeting.objects.create(
            title="اجتماع ملغى",
            start=now + datetime.timedelta(days=3),
            end=now + datetime.timedelta(days=3, hours=1),
            status=ApplicantMeeting.Status.CANCELLED,
        )
        for meeting in (upcoming, past, cancelled):
            ApplicantMeetingAttendee.objects.create(meeting=meeting, applicant=self.applicant)

        titles = [m.title for m in applicant_upcoming_meetings(self.applicant)]
        self.assertEqual(titles, ["مقابلة أولى"])

    def test_one_row_per_meeting_even_with_another_attendee(self):
        """`distinct` ليس زينةً: ضيفٌ ثانٍ في الاجتماع يضاعف الصفَّ بلا هذا."""
        now = timezone.now()
        meeting = ApplicantMeeting.objects.create(
            title="مقابلة جماعية",
            start=now + datetime.timedelta(days=1),
            end=now + datetime.timedelta(days=1, hours=1),
        )
        ApplicantMeetingAttendee.objects.create(meeting=meeting, applicant=self.applicant)
        ApplicantMeetingAttendee.objects.create(meeting=meeting, guest_name="ضيف")
        self.assertEqual(applicant_upcoming_meetings(self.applicant).count(), 1)


class TrackingIdentityTests(ApplicantTrackingBaseTests):
    """‏215-ب: مطابقةُ الهويّة — الرمزُ والهاتف."""

    def test_the_phone_is_matched_the_way_people_write_it(self):
        """«+962791234567» و«٠٧٩١٢٣٤٥٦٧» رقمُ صاحبِ الطلب نفسِه."""
        self.assertTrue(phones_match("+962791234567", "0791234567"))
        self.assertTrue(phones_match("٠٧٩١٢٣٤٥٦٧", "0791234567"))
        self.assertTrue(phones_match("079 123 4567", "0791234567"))
        self.assertFalse(phones_match("0799999999", "0791234567"))
        self.assertFalse(phones_match("", "0791234567"))

    def test_the_code_is_read_the_way_it_is_copied(self):
        self.assertEqual(normalize_tracking_code(" a3f9-1c2d "), "A3F91C2D")

    def test_a_code_from_another_job_is_refused(self):
        """الرمزُ يُطلَب تحت وظيفته — ومفتاحُ البحث ليس الرمزَ وحدَه."""
        other_job = create_job_posting(
            title="مندوب", description="وصف", created_by=self.admin_user
        )
        with self.assertRaises(TrackingDenied):
            resolve_applicant_tracking(
                job_token=other_job.token,
                reference_code=self.applicant.reference_code,
                phone="0791234567",
            )

    @override_settings(
        CACHES={
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "track-failure-counter",
            }
        }
    )
    def test_the_failure_counter_closes_a_known_code(self):
        """خانقُ العنوان لا يوقف من يجرّب رمزاً واحداً من ألف عنوان.

        **وذاكرةُ الاختبارات `DummyCache`** (`core/test_settings.py`): بلا هذا
        التجاوز يمرّ الاختبارُ على عدّادٍ لا يعدّ — ويكون حارساً لا يستطيع
        السقوطَ للسبب الذي يحمله اسمُه.
        """
        for _ in range(TRACKING_FAILURE_LIMIT):
            with self.assertRaises(TrackingDenied):
                resolve_applicant_tracking(
                    job_token=self.job.token,
                    reference_code=self.applicant.reference_code,
                    phone="0700000000",
                )
        # وحتى الهاتفُ الصحيحُ يُردّ بعد بلوغ الحدّ
        with self.assertRaises(TrackingDenied):
            resolve_applicant_tracking(
                job_token=self.job.token,
                reference_code=self.applicant.reference_code,
                phone="0791234567",
            )

    def test_a_tampered_session_is_not_a_session(self):
        session = issue_tracking_session(self.applicant)
        with self.assertRaises(TrackingSessionExpired):
            resolve_tracking_session(session + "x")
        with self.assertRaises(TrackingSessionExpired):
            resolve_tracking_session("")
        self.assertEqual(resolve_tracking_session(session).pk, self.applicant.pk)


class TrackingPublicSurfaceTests(ApplicantTrackingBaseTests):
    """‏215-ب: السطحُ العامُّ عبر HTTP."""

    #: مفاتيحُ ملفِّ المتقدّم الداخليّ. **و`phone` ليست منها في صفّ التحديث**:
    #: تلك رقمُ تواصلٍ يكتبه الفريقُ ليُتَّصل به، لا رقمُ المتقدّم نفسِه —
    #: والفرقُ بين الاثنين هو الفرقُ بين خدمةٍ وتسريب.
    FORBIDDEN_KEYS = {"name", "phone", "email", "about", "notes", "rating", "cv_url", "cv_name"}

    #: مفاتيحُ صفّ التحديث العامّ، محصورةً. أيُّ مفتاحٍ يُضاف غداً يسقط هنا
    #: قبل أن يصل قارئاً — وهي الحمايةُ التي لا تملكها قائمةُ ممنوعاتٍ ثابتة.
    UPDATE_KEYS = {"id", "kind", "author_kind", "body", "link", "phone", "created_at"}

    def _assert_no_personal_keys(self, node, path="root"):
        if isinstance(node, dict):
            for key, value in node.items():
                self.assertNotIn(
                    key,
                    self.FORBIDDEN_KEYS,
                    f"حمولةٌ عامّةٌ تحمل «{key}» في {path}",
                )
                self._assert_no_personal_keys(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, item in enumerate(node):
                self._assert_no_personal_keys(item, f"{path}[{index}]")

    def _assert_no_personal_values(self, payload):
        """والقيمةُ تُفحَص كما يُفحَص المفتاح: إعادةُ تسميةِ حقلٍ تتجاوز الأوّل."""
        import json

        blob = json.dumps(payload, ensure_ascii=False, default=str)
        for secret in (self.applicant.name, self.applicant.email):
            self.assertNotIn(secret, blob, f"القيمةُ «{secret}» خرجت من بابٍ عامّ")

    def test_opening_the_tracking_page_returns_only_what_the_applicant_needs(self):
        res = self.client.post(
            self.track_url,
            {"reference_code": self.applicant.reference_code.lower(), "phone": "٠٧٩١٢٣٤٥٦٧"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data["session"])
        self.assertEqual(res.data["applicant"]["reference_code"], self.applicant.reference_code)
        self.assertEqual(
            res.data["applicant"]["status_display"],
            APPLICANT_PUBLIC_STATUS_LABELS[JobApplicant.Status.NEW],
        )
        self.assertTrue(res.data["applicant"]["can_reply"])
        self.assertEqual(len(res.data["updates"]), 1)
        self._assert_no_personal_keys(res.data["applicant"], "applicant")
        self._assert_no_personal_keys(res.data["job"], "job")
        self._assert_no_personal_values(res.data)
        for row in res.data["updates"]:
            self.assertEqual(set(row.keys()), self.UPDATE_KEYS)

    def test_every_wrong_door_answers_with_the_same_bytes(self):
        """أيُّ فرقٍ هنا يجعل الصفحةَ تؤكّد وجودَ الرموز لمن يجرّبها."""
        wrong_phone = self.client.post(
            self.track_url,
            {"reference_code": self.applicant.reference_code, "phone": "0700000000"},
            format="json",
        )
        unknown_code = self.client.post(
            self.track_url,
            {"reference_code": "ZZZZZZZZ", "phone": "0791234567"},
            format="json",
        )
        missing_field = self.client.post(
            self.track_url, {"reference_code": self.applicant.reference_code}, format="json"
        )
        empty_body = self.client.post(self.track_url, {}, format="json")

        for res in (wrong_phone, unknown_code, missing_field, empty_body):
            self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertEqual(res.data, {"detail": TRACKING_DENIED_DETAIL})

    def test_the_ledger_hides_what_was_not_published(self):
        publish_applicant_notice(
            applicant=self.applicant,
            body="ملاحظةٌ محجوبة",
            actor=self.recruiter_user,
            is_public=False,
        )
        res = self.client.post(
            self.track_url,
            {"reference_code": self.applicant.reference_code, "phone": "0791234567"},
            format="json",
        )
        bodies = [row["body"] for row in res.data["updates"]]
        self.assertNotIn("ملاحظةٌ محجوبة", bodies)
        # ولا يُعاد العلَمُ نفسُه: وجودُه يدعو القارئَ للسؤال عمّا لا يراه
        for row in res.data["updates"]:
            self.assertNotIn("is_public", row)

    def test_the_meeting_reaches_its_own_attendee_only(self):
        now = timezone.now()
        meeting = ApplicantMeeting.objects.create(
            title="مقابلة أولى",
            start=now + datetime.timedelta(days=2),
            end=now + datetime.timedelta(days=2, hours=1),
            location="https://meet.example/abc",
        )
        ApplicantMeetingAttendee.objects.create(meeting=meeting, applicant=self.applicant)
        stranger = submit_application(
            job=self.job, name="آخر", phone="0788888888"
        )

        mine = self.client.post(
            self.track_url,
            {"reference_code": self.applicant.reference_code, "phone": "0791234567"},
            format="json",
        )
        theirs = self.client.post(
            self.track_url,
            {"reference_code": stranger.reference_code, "phone": "0788888888"},
            format="json",
        )
        self.assertEqual([m["title"] for m in mine.data["meetings"]], ["مقابلة أولى"])
        self.assertEqual(theirs.data["meetings"], [])

    def test_the_applicant_can_write_back_and_reads_it_next_time(self):
        session = self.open_session()
        posted = self.client.post(
            "/api/careers/track/reply/",
            {"session": session, "body": "هل المقابلة حضوريّة؟"},
            format="json",
        )
        self.assertEqual(posted.status_code, status.HTTP_201_CREATED)
        self.assertEqual(posted.data["author_kind"], JobApplicantUpdate.AuthorKind.APPLICANT)

        refreshed = self.client.post(
            "/api/careers/track/refresh/", {"session": session}, format="json"
        )
        bodies = [row["body"] for row in refreshed.data["updates"]]
        self.assertIn("هل المقابلة حضوريّة؟", bodies)

    def test_an_empty_or_oversized_reply_is_refused(self):
        session = self.open_session()
        blank = self.client.post(
            "/api/careers/track/reply/", {"session": session, "body": "   "}, format="json"
        )
        huge = self.client.post(
            "/api/careers/track/reply/", {"session": session, "body": "ا" * 4001}, format="json"
        )
        self.assertEqual(blank.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(huge.status_code, status.HTTP_400_BAD_REQUEST)

    def test_a_closed_application_refuses_the_reply_with_403(self):
        session = self.open_session()
        transition_applicant_status(
            applicant=self.applicant, target_status=JobApplicant.Status.REJECTED
        )
        res = self.client.post(
            "/api/careers/track/reply/", {"session": session, "body": "سؤال"}, format="json"
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        # واللوحةُ تبقى مقروءةً بعد الإغلاق، ويُطفأ زرُّ الكتابة وحدَه
        board = self.client.post(
            "/api/careers/track/refresh/", {"session": session}, format="json"
        )
        self.assertEqual(board.status_code, status.HTTP_200_OK)
        self.assertFalse(board.data["applicant"]["can_reply"])

    def test_a_dead_session_sends_the_applicant_back_to_the_form_not_to_a_crash(self):
        for url in ("/api/careers/track/refresh/", "/api/careers/track/reply/"):
            res = self.client.post(url, {"session": "not-a-session", "body": "x"}, format="json")
            self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED, url)
            self.assertIn("detail", res.data)

    def test_the_public_tracking_surface_declares_no_authentication(self):
        """كلُّ `AllowAny` في حزمةٍ واحدةٍ ليراجعه الأمنُ دفعةً واحدة."""
        from platform_ops.public_hiring import views as public_views

        for name in (
            "PublicApplicantTrackView",
            "PublicApplicantTrackRefreshView",
            "PublicApplicantReplyView",
        ):
            view = getattr(public_views, name)
            self.assertEqual(view.authentication_classes, [], name)
            self.assertTrue(view.throttle_classes, name)
            self.assertTrue(getattr(view, "throttle_scope", ""), name)


class TrackingRecruiterSurfaceTests(ApplicantTrackingBaseTests):
    """‏215-ج: سطحُ فريق التوظيف."""

    def test_the_recruiter_writes_a_notice_the_applicant_reads(self):
        self.client.force_authenticate(user=self.recruiter_user)
        res = self.client.post(
            f"/api/platform/ops/job-applicants/{self.applicant.pk}/notice/",
            {"body": "وصلتنا سيرتُك.", "phone": "0790000000"},
            format="json",
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.client.force_authenticate(user=None)

        board = self.client.post(
            self.track_url,
            {"reference_code": self.applicant.reference_code, "phone": "0791234567"},
            format="json",
        )
        rows = [row for row in board.data["updates"] if row["body"] == "وصلتنا سيرتُك."]
        self.assertEqual(len(rows), 1)
        # الرابطُ والرقمُ حقلان مستقلّان عن النصّ: رقمٌ داخل جملةٍ لا يصير زرَّ اتّصال
        self.assertEqual(rows[0]["phone"], "0790000000")

    def test_the_ledger_endpoint_is_closed_to_everyone_but_the_recruiter(self):
        outsider = User.objects.create_user(username="outsider215", password="Str0ng!Pass215")
        for url in (
            f"/api/platform/ops/job-applicants/{self.applicant.pk}/updates/",
            f"/api/platform/ops/job-applicants/{self.applicant.pk}/notice/",
        ):
            self.client.force_authenticate(user=None)
            anon = self.client.get(url)
            self.assertIn(
                anon.status_code,
                (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN),
                url,
            )
            self.client.force_authenticate(user=outsider)
            denied = self.client.get(url)
            self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN, url)

    def test_the_unread_badge_costs_no_extra_query_per_row(self):
        """عدٌّ لكلّ صفٍّ هو عطبُ N+1 نفسُه الذي أُصلح هنا مرّتين."""
        self.client.force_authenticate(user=self.recruiter_user)
        record_applicant_reply(applicant=self.applicant, body="سؤال")

        with CaptureQueriesContext(connection) as first:
            res_one = self.client.get("/api/platform/ops/job-applicants/")
        self.assertEqual(res_one.status_code, status.HTTP_200_OK)

        for index in range(5):
            extra = submit_application(
                job=self.job, name=f"متقدّم {index}", phone=f"07800000{index:02d}"
            )
            record_applicant_reply(applicant=extra, body="سؤال")

        with CaptureQueriesContext(connection) as second:
            res_many = self.client.get("/api/platform/ops/job-applicants/")
        self.assertEqual(res_many.status_code, status.HTTP_200_OK)

        self.assertEqual(
            len(second.captured_queries),
            len(first.captured_queries),
            "عددُ الاستعلامات يزيد بزيادة الصفوف — العدُّ خرج من الاستعلام القائم",
        )
        rows = res_many.data["results"] if isinstance(res_many.data, dict) else res_many.data
        mine = [row for row in rows if row["reference_code"] == self.applicant.reference_code]
        self.assertEqual(mine[0]["unread_reply_count"], 1)

    def test_a_link_that_is_not_http_is_refused(self):
        """`objects.create()` لا يشغّل مدقّقاتِ `URLField`، والقيمةُ تصير `href`.

        فلولا الفحصُ في الخدمة لاستقرّ `javascript:` في عمودٍ يبدو محروساً
        بنوعه، ثمّ صُيّر رابطاً في صفحةٍ عامّة.
        """
        with self.assertRaises(ValidationError):
            publish_applicant_notice(
                applicant=self.applicant,
                body="اضغط هنا",
                link="javascript:alert(1)",
                actor=self.recruiter_user,
            )
        ok = publish_applicant_notice(
            applicant=self.applicant,
            body="الرابط",
            link="https://meet.example/abc",
            actor=self.recruiter_user,
        )
        self.assertEqual(ok.link, "https://meet.example/abc")

    def test_opening_the_ledger_marks_the_replies_read(self):
        """شارةٌ لا تُطفأ إلا بالردّ تبقى تصرخ على رسالةٍ قُرئت فعلاً."""
        record_applicant_reply(applicant=self.applicant, body="سؤال")
        self.client.force_authenticate(user=self.recruiter_user)

        res = self.client.get(
            f"/api/platform/ops/job-applicants/{self.applicant.pk}/updates/"
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(
            JobApplicantUpdate.objects.filter(
                applicant=self.applicant,
                author_kind=JobApplicantUpdate.AuthorKind.APPLICANT,
                read_at__isnull=True,
            ).count(),
            0,
        )
