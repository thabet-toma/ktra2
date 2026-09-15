"""ملفُّ المهمّة الكامل: مرفقاتٌ وخيطُ حديثٍ ولوحُ المدير وشارةُ الإجباريّة (#213-ب).

طلبُ المالك ثلاثةُ أشياءَ مترابطة: أن يُرفق السوبر أدمن شرحاً بالملفّات، وأن يرفع
الموظّفُ ملفّاتِه وملاحظاتِه **قبل التسليم وقبل الاستلام**، وأن «ينفتح ملفٌّ كاملٌ
للمهمّة» يُقرأ فيه التعليقُ وردُّه في ترتيبٍ واحد. وفوقها: المُسنَدةُ شخصيّاً
مقبولةٌ بالافتراض «ما في مجال ما يستلمها»، والجماعيّةُ يختار المديرُ إجباريّتَها.

وما يُحرَس هنا أخطرُ من وجود النقاط: **من يرى ماذا**. خيطُ المهمّة يجمع كاتبين
ومُرفِقين متعدّدين على مهمّةٍ قد تكون مُسندةً لعشرة، فترشيحُه بالرائي هو الفرقُ
بين «ملفّ مهمّة» و«تسريبُ عمل زميل».
"""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from platform_ops.models import (
    PlatformEmployee,
    PlatformEmployeeNote,
    PlatformTask,
    PlatformTaskAssignment,
    PlatformTaskAttachment,
)
from platform_ops.services import (
    PlatformOpsError,
    add_platform_employee_note,
    add_platform_workspace_note,
    attach_to_platform_task,
    create_platform_task,
    review_platform_task_submission,
    submit_platform_task,
)

User = get_user_model()

TASKS = "/api/platform/ops/tasks/"


class _TaskFileFixture(TestCase):
    """مديرٌ وموظّفان على **نفس المهمّة** — العزلُ هنا بين زميلين لا بين شركتين."""

    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_superuser(
            username="file_manager", email="file_manager@platform.local", password="x",
        )
        cls.user_a = User.objects.create_user(username="file_staff_a", password="x")
        cls.user_b = User.objects.create_user(username="file_staff_b", password="x")
        cls.employee_a = PlatformEmployee.objects.create(
            user=cls.user_a, status=PlatformEmployee.Status.ACTIVE,
        )
        cls.employee_b = PlatformEmployee.objects.create(
            user=cls.user_b, status=PlatformEmployee.Status.ACTIVE,
        )
        cls.task = create_platform_task(
            actor=cls.manager,
            title="ترحيلُ دفاتر شركة الجرابعه",
            audience=PlatformTask.AUDIENCE_SPECIFIC,
            employee_ids=[cls.employee_a.pk, cls.employee_b.pk],
        )
        cls.assignment_a = PlatformTaskAssignment.objects.get(
            task=cls.task, employee=cls.employee_a,
        )
        cls.assignment_b = PlatformTaskAssignment.objects.get(
            task=cls.task, employee=cls.employee_b,
        )

    def setUp(self):
        self.client = APIClient()

    def _upload(self, user, task=None, filename="sheet.xlsx", name=""):
        upload = SimpleUploadedFile(
            filename, b"bytes", content_type="application/vnd.ms-excel",
        )
        self.client.force_authenticate(user)
        payload = {"file": upload}
        if name:
            payload["name"] = name
        with patch("platform_ops.views.upload_media_file") as mocked:
            mocked.return_value = f"https://res.cloudinary.com/demo/{filename}"
            response = self.client.post(
                f"{TASKS}{(task or self.task).pk}/attachments/", payload, format="multipart",
            )
        return response, mocked


# ==============================================================================
# الإجباريّة — «ما في مجال ما يستلمها» ومقابلُها الاختياريّ
# ==============================================================================


class MandatoryAssignmentTest(_TaskFileFixture):
    def test_an_individually_assigned_task_is_accepted_the_moment_it_is_created(self):
        task = create_platform_task(
            actor=self.manager, title="مهمّةٌ شخصيّة",
            audience=PlatformTask.AUDIENCE_INDIVIDUAL, employee_ids=[self.employee_a.pk],
        )
        assignment = PlatformTaskAssignment.objects.get(task=task, employee=self.employee_a)
        self.assertEqual(assignment.status, PlatformTaskAssignment.STATUS_ACCEPTED)
        self.assertIsNotNone(assignment.accepted_at)

    def test_an_individual_task_stays_mandatory_even_when_the_payload_says_otherwise(self):
        """«الفرديّةُ إجباريّةٌ» قاعدةُ خدمةٍ لا خيارَ واجهة — فالحمولةُ لا تنقضها."""
        task = create_platform_task(
            actor=self.manager, title="فرديّةٌ يُطلَب تخييرُها",
            audience=PlatformTask.AUDIENCE_INDIVIDUAL, employee_ids=[self.employee_a.pk],
            is_mandatory=False,
        )
        self.assertTrue(task.is_mandatory)
        self.assertEqual(
            PlatformTaskAssignment.objects.get(task=task, employee=self.employee_a).status,
            PlatformTaskAssignment.STATUS_ACCEPTED,
        )

    def test_an_optional_group_task_is_offered_and_waits_for_its_owner(self):
        task = create_platform_task(
            actor=self.manager, title="ورشةُ تدريبٍ اختياريّة",
            audience=PlatformTask.AUDIENCE_SPECIFIC,
            employee_ids=[self.employee_a.pk, self.employee_b.pk], is_mandatory=False,
        )
        self.assertFalse(task.is_mandatory)
        statuses = set(
            PlatformTaskAssignment.objects.filter(task=task).values_list("status", flat=True)
        )
        self.assertEqual(statuses, {PlatformTaskAssignment.STATUS_OFFERED})
        task.refresh_from_db()
        self.assertEqual(task.status, PlatformTask.STATUS_NEW)

    def test_a_mandatory_group_task_starts_in_progress_not_waiting(self):
        """إسنادٌ مقبولٌ يعني عملاً بدأ — و`NEW` كانت ستقول للمدير «لم يبدأ أحد»."""
        self.task.refresh_from_db()
        self.assertTrue(self.task.is_mandatory)
        self.assertNotEqual(self.task.status, PlatformTask.STATUS_NEW)

    def test_a_pool_task_is_never_mandatory(self):
        """المطالبةُ بمهمّةِ المجمَع تطوّعٌ بتعريفها، فإجباريّتُها تناقضٌ لفظيّ."""
        task = create_platform_task(
            actor=self.manager, title="مهمّةُ مجمَعٍ يُطلَب إلزامُها",
            audience=PlatformTask.AUDIENCE_OPEN, is_mandatory=True,
        )
        self.assertFalse(task.is_mandatory)

    def test_the_employee_payload_says_whether_the_task_is_mandatory(self):
        """الشارةُ تُقرأ من المهمّة: `ACCEPTED` وحدَها لا تفرّق بين وُلد مقبولاً وقَبِل بيده."""
        self.client.force_authenticate(self.user_a)
        response = self.client.get("/api/platform/ops/assignments/")
        self.assertEqual(response.status_code, 200, response.content)
        rows = {row["task"]: row for row in response.data}
        self.assertTrue(rows[self.task.pk]["is_mandatory"])
        self.assertEqual(rows[self.task.pk]["task_audience"], PlatformTask.AUDIENCE_SPECIFIC)

    def test_the_manager_can_create_an_optional_group_task_over_http(self):
        self.client.force_authenticate(self.manager)
        response = self.client.post(f"{TASKS}create/", {
            "title": "مهمّةٌ جماعيّةٌ اختياريّة",
            "audience": PlatformTask.AUDIENCE_SPECIFIC,
            "employee_ids": [self.employee_a.pk],
            "is_mandatory": False,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertFalse(response.data["is_mandatory"])
        self.assertEqual(
            PlatformTaskAssignment.objects.get(task=response.data["id"]).status,
            PlatformTaskAssignment.STATUS_OFFERED,
        )


# ==============================================================================
# المرفقات — الدورُ من الفاعل، والبايتاتُ لا تُرفَع لمن لا حقَّ له
# ==============================================================================


class AttachmentRoleTest(_TaskFileFixture):
    def test_the_managers_upload_becomes_the_task_brief_and_rides_on_every_card(self):
        response, mocked = self._upload(self.manager, filename="brief.pdf", name="الشرح")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["kind"], PlatformTaskAttachment.Kind.BRIEF)
        self.assertIsNone(response.data["employee"])
        self.assertEqual(response.data["name"], "الشرح")
        self.assertIsNone(mocked.call_args.kwargs["tenant"])

        self.client.force_authenticate(self.user_a)
        card = self.client.get(f"{TASKS}{self.task.pk}/")
        self.assertEqual(
            [row["id"] for row in card.data["brief_attachments"]], [response.data["id"]],
        )

    def test_the_employees_upload_is_work_even_when_the_payload_asks_for_brief(self):
        """الدورُ يُشتقّ من الفاعل: قبولُه من الشبكة يجعل موظّفاً يكتب شرحَ المدير."""
        upload = SimpleUploadedFile("mine.png", b"bytes", content_type="image/png")
        self.client.force_authenticate(self.user_a)
        with patch("platform_ops.views.upload_media_file") as mocked:
            mocked.return_value = "https://res.cloudinary.com/demo/mine.png"
            response = self.client.post(
                f"{TASKS}{self.task.pk}/attachments/",
                {"file": upload, "kind": PlatformTaskAttachment.Kind.BRIEF},
                format="multipart",
            )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["kind"], PlatformTaskAttachment.Kind.WORK)
        self.assertEqual(response.data["employee"], self.employee_a.pk)

    def test_an_employee_may_upload_before_accepting_the_task(self):
        """نصُّ الطلب: يرفع ملفّاتِه ويكتب ملاحظاتِه «حتى قبل الاستلام»."""
        task = create_platform_task(
            actor=self.manager, title="اختياريّةٌ لم تُقبَل بعد",
            audience=PlatformTask.AUDIENCE_SPECIFIC, employee_ids=[self.employee_a.pk],
            is_mandatory=False,
        )
        self.assertEqual(
            PlatformTaskAssignment.objects.get(task=task).status,
            PlatformTaskAssignment.STATUS_OFFERED,
        )
        response, _ = self._upload(self.user_a, task=task)
        self.assertEqual(response.status_code, 201, response.content)

    def test_a_pool_task_nobody_claimed_refuses_the_upload_before_storing_a_byte(self):
        """مهمّةُ المجمَع يراها كلُّ موظّف — فلولا الرفضُ المبكّر لصارت بابَ تخزينٍ مفتوحاً."""
        pool = create_platform_task(
            actor=self.manager, title="مهمّةُ مجمَعٍ بلا مطالب",
            audience=PlatformTask.AUDIENCE_OPEN,
        )
        response, mocked = self._upload(self.user_a, task=pool)
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(response.data["code"], "task_not_assigned_to_you")
        mocked.assert_not_called()
        self.assertEqual(PlatformTaskAttachment.objects.filter(task=pool).count(), 0)

    def test_a_task_of_a_stranger_is_not_even_visible_to_upload_on(self):
        stranger = User.objects.create_user(username="file_staff_c", password="x")
        employee_c = PlatformEmployee.objects.create(
            user=stranger, status=PlatformEmployee.Status.ACTIVE,
        )
        private = create_platform_task(
            actor=self.manager, title="مهمّةُ زميلٍ ثالث",
            audience=PlatformTask.AUDIENCE_INDIVIDUAL, employee_ids=[employee_c.pk],
        )
        response, mocked = self._upload(self.user_a, task=private)
        self.assertEqual(response.status_code, 404, response.content)
        mocked.assert_not_called()

    def test_the_service_refuses_a_brief_that_claims_an_owner(self):
        with self.assertRaises(PlatformOpsError) as ctx:
            attach_to_platform_task(
                task=self.task, actor=self.manager, url="https://x/y.pdf",
                kind=PlatformTaskAttachment.Kind.BRIEF, employee=self.employee_a,
            )
        self.assertEqual(ctx.exception.code, "brief_has_no_owner")

    def test_the_service_refuses_a_delivery_attachment_hung_on_a_colleagues_submission(self):
        submission_b = submit_platform_task(
            assignment=self.assignment_b, actor=self.user_b, body="تسليمُ (ب).",
        )
        with self.assertRaises(PlatformOpsError) as ctx:
            attach_to_platform_task(
                task=self.task, actor=self.user_a, url="https://x/y.pdf",
                kind=PlatformTaskAttachment.Kind.DELIVERY,
                employee=self.employee_a, submission=submission_b,
            )
        self.assertEqual(ctx.exception.code, "submission_mismatch")


class AttachmentDownloadTest(_TaskFileFixture):
    def _attach(self, *, kind, employee=None, url="https://res.cloudinary.com/demo/f.pdf"):
        return attach_to_platform_task(
            task=self.task, actor=self.manager if employee is None else employee.user,
            url=url, kind=kind, name="ملفّ", content_type="application/pdf",
            employee=employee,
        )

    def _download(self, user, attachment, task=None):
        self.client.force_authenticate(user)
        with patch("platform_ops.views.stream_stored_asset") as mocked:
            mocked.return_value = _ok()
            response = self.client.get(
                f"{TASKS}{(task or self.task).pk}/attachments/{attachment.pk}/download/",
            )
        return response, mocked

    def test_the_brief_is_readable_by_everyone_the_task_was_assigned_to(self):
        brief = self._attach(kind=PlatformTaskAttachment.Kind.BRIEF)
        response, mocked = self._download(self.user_b, brief)
        self.assertEqual(response.status_code, 200)
        mocked.assert_called_once()

    def test_a_colleague_cannot_download_the_work_file_of_another_employee(self):
        mine = self._attach(
            kind=PlatformTaskAttachment.Kind.WORK, employee=self.employee_a,
        )
        response, mocked = self._download(self.user_b, mine)
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(response.data["code"], "not_your_attachment")
        mocked.assert_not_called()

    def test_the_owner_and_the_manager_both_read_the_work_file(self):
        mine = self._attach(
            kind=PlatformTaskAttachment.Kind.WORK, employee=self.employee_a,
        )
        for user in (self.user_a, self.manager):
            with self.subTest(user=user.username):
                response, _ = self._download(user, mine)
                self.assertEqual(response.status_code, 200)

    def test_an_attachment_of_another_task_is_not_reachable_through_this_ones_url(self):
        """النطاقُ يحرس المهمّةَ، والبحثُ **داخلها** يحرس المرفق — والثاني لا يغني عنه الأوّل."""
        other = create_platform_task(
            actor=self.manager, title="مهمّةٌ أخرى لنفس الموظّف",
            audience=PlatformTask.AUDIENCE_INDIVIDUAL, employee_ids=[self.employee_a.pk],
        )
        foreign = attach_to_platform_task(
            task=other, actor=self.manager, url="https://res.cloudinary.com/demo/other.pdf",
            kind=PlatformTaskAttachment.Kind.BRIEF,
        )
        response, mocked = self._download(self.user_a, foreign)
        self.assertEqual(response.status_code, 404, response.content)
        self.assertEqual(response.data["code"], "attachment_not_found")
        mocked.assert_not_called()


class SubmissionCarriesItsFilesTest(_TaskFileFixture):
    def test_the_chosen_work_files_move_onto_the_submission(self):
        first = attach_to_platform_task(
            task=self.task, actor=self.user_a, url="https://x/1.pdf",
            kind=PlatformTaskAttachment.Kind.WORK, employee=self.employee_a,
        )
        second = attach_to_platform_task(
            task=self.task, actor=self.user_a, url="https://x/2.pdf",
            kind=PlatformTaskAttachment.Kind.WORK, employee=self.employee_a,
        )
        submission = submit_platform_task(
            assignment=self.assignment_a, actor=self.user_a, body="خلصت.",
            attachment_ids=[first.pk],
        )
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.kind, PlatformTaskAttachment.Kind.DELIVERY)
        self.assertEqual(first.submission_id, submission.pk)
        self.assertEqual(second.kind, PlatformTaskAttachment.Kind.WORK)
        self.assertIsNone(second.submission_id)

    def test_a_colleagues_file_id_in_the_payload_is_ignored_not_stolen(self):
        """ولا يُرفَض التسليمُ كلُّه لأجله: التسليمُ وقع، وإبطالُه يُضيّع عملاً تمّ."""
        his = attach_to_platform_task(
            task=self.task, actor=self.user_b, url="https://x/his.pdf",
            kind=PlatformTaskAttachment.Kind.WORK, employee=self.employee_b,
        )
        submission = submit_platform_task(
            assignment=self.assignment_a, actor=self.user_a, body="تسليمي.",
            attachment_ids=[his.pk],
        )
        his.refresh_from_db()
        self.assertEqual(his.kind, PlatformTaskAttachment.Kind.WORK)
        self.assertIsNone(his.submission_id)
        self.assertEqual(submission.attachments.count(), 0)

    def test_submitting_over_http_passes_the_chosen_files(self):
        mine = attach_to_platform_task(
            task=self.task, actor=self.user_a, url="https://x/mine.pdf",
            kind=PlatformTaskAttachment.Kind.WORK, employee=self.employee_a,
        )
        self.client.force_authenticate(self.user_a)
        response = self.client.post(
            f"/api/platform/ops/assignments/{self.assignment_a.pk}/submit/",
            {"body": "مع الملفّ.", "attachment_ids": [mine.pk]}, format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        mine.refresh_from_db()
        self.assertEqual(mine.kind, PlatformTaskAttachment.Kind.DELIVERY)


# ==============================================================================
# الخيط — «ينفتح ملفٌّ كاملٌ للمهمّة»، وكلٌّ يرى ما له
# ==============================================================================


class TaskThreadTest(_TaskFileFixture):
    def setUp(self):
        super().setUp()
        self.brief = attach_to_platform_task(
            task=self.task, actor=self.manager, url="https://x/brief.pdf",
            kind=PlatformTaskAttachment.Kind.BRIEF, name="الشرح",
        )
        self.my_file = attach_to_platform_task(
            task=self.task, actor=self.user_a, url="https://x/mine.pdf",
            kind=PlatformTaskAttachment.Kind.WORK, employee=self.employee_a,
        )
        self.his_file = attach_to_platform_task(
            task=self.task, actor=self.user_b, url="https://x/his.pdf",
            kind=PlatformTaskAttachment.Kind.WORK, employee=self.employee_b,
        )
        add_platform_workspace_note(
            employee=self.employee_a, body="سؤالي عن الحساب ٢٢١٢.", task=self.task,
        )
        add_platform_workspace_note(
            employee=self.employee_b, body="ملاحظةُ زميلي.", task=self.task,
        )
        self.public_note = add_platform_employee_note(
            employee=self.employee_a, author=self.manager, body="خُذ الرصيدَ الافتتاحيَّ من المرفق.",
            visibility=PlatformEmployeeNote.VISIBILITY_EMPLOYEE, task=self.task,
        )
        self.private_note = add_platform_employee_note(
            employee=self.employee_a, author=self.manager, body="تقييمٌ داخليٌّ عن (أ).",
            visibility=PlatformEmployeeNote.VISIBILITY_MANAGER_ONLY, task=self.task,
        )
        self.submission_a = submit_platform_task(
            assignment=self.assignment_a, actor=self.user_a, body="سلّمت.",
        )
        review_platform_task_submission(
            submission=self.submission_a, actor=self.manager,
            decision="APPROVED_PARTIAL", reviewer_notes="ناقصٌ كشفُ البنك.",
        )

    def _thread(self, user):
        self.client.force_authenticate(user)
        response = self.client.get(f"{TASKS}{self.task.pk}/thread/")
        self.assertEqual(response.status_code, 200, response.content)
        return response.data["events"]

    def test_the_manager_reads_the_whole_file_including_the_private_note(self):
        bodies = [event["body"] for event in self._thread(self.manager)]
        self.assertIn("تقييمٌ داخليٌّ عن (أ).", bodies)
        self.assertIn("ملاحظةُ زميلي.", bodies)
        self.assertIn("ناقصٌ كشفُ البنك.", bodies)

    def test_the_employee_never_reads_a_manager_only_note_about_himself(self):
        bodies = [event["body"] for event in self._thread(self.user_a)]
        self.assertIn("خُذ الرصيدَ الافتتاحيَّ من المرفق.", bodies)
        self.assertNotIn("تقييمٌ داخليٌّ عن (أ).", bodies)

    def test_the_employee_never_reads_his_colleagues_side_of_the_task(self):
        events = self._thread(self.user_a)
        bodies = [event["body"] for event in events]
        self.assertNotIn("ملاحظةُ زميلي.", bodies)
        owners = {event.get("employee") for event in events}
        self.assertEqual(owners - {None}, {self.employee_a.pk})
        urls = [
            attachment["url"]
            for event in events for attachment in event.get("attachments", [])
        ]
        self.assertIn("https://x/mine.pdf", urls)
        self.assertNotIn("https://x/his.pdf", urls)

    def test_the_brief_belongs_to_everybody_on_the_task(self):
        urls = [
            attachment["url"]
            for event in self._thread(self.user_b) for attachment in event.get("attachments", [])
        ]
        self.assertIn("https://x/brief.pdf", urls)

    def test_the_events_read_in_time_order(self):
        stamps = [event["at"] for event in self._thread(self.manager)]
        self.assertEqual(stamps, sorted(stamps))

    def test_the_review_sits_in_the_thread_next_to_the_submission_it_answers(self):
        types = [event["type"] for event in self._thread(self.user_a)]
        self.assertLess(types.index("submission"), types.index("review"))

    def test_the_decision_travels_with_its_arabic_text_not_only_its_code(self):
        """‏`APPROVED_PARTIAL` رمزٌ لا يُعرَض لعربيّ.

        وبلا `decision_display` في الحدث تُضطرّ الشاشةُ إلى قاموسٍ ثانٍ يترجم
        `choices` — يتخلّف عنها أوّلَ ما يُضاف قرار، فيظهر الرمزُ الخامُ للمستخدم.
        """
        review = next(
            event for event in self._thread(self.user_a) if event["type"] == "review"
        )
        self.assertEqual(review["decision"], "APPROVED_PARTIAL")
        self.assertEqual(review["decision_display"], "قبول جزئي — ما زال العمل مستمراً")
        submission = next(
            event for event in self._thread(self.user_a) if event["type"] == "submission"
        )
        self.assertEqual(submission["decision_display"], "قبول جزئي — ما زال العمل مستمراً")

    def test_a_stranger_gets_nothing_from_the_thread(self):
        stranger = User.objects.create_user(username="file_staff_d", password="x")
        PlatformEmployee.objects.create(user=stranger, status=PlatformEmployee.Status.ACTIVE)
        self.client.force_authenticate(stranger)
        response = self.client.get(f"{TASKS}{self.task.pk}/thread/")
        self.assertEqual(response.status_code, 404, response.content)


# ==============================================================================
# اللوح — «شو معو مهام وشو استلم»
# ==============================================================================


class TaskBoardTest(_TaskFileFixture):
    def test_the_board_counts_each_employees_load_in_the_database(self):
        submit_platform_task(assignment=self.assignment_a, actor=self.user_a, body="سلّمت.")
        self.client.force_authenticate(self.manager)
        response = self.client.get(f"{TASKS}board/")
        self.assertEqual(response.status_code, 200, response.content)
        rows = {row["employee"]: row for row in response.data["rows"]}
        self.assertEqual(rows[self.employee_a.pk]["submitted"], 1)
        self.assertEqual(rows[self.employee_a.pk]["accepted"], 0)
        self.assertEqual(rows[self.employee_b.pk]["accepted"], 1)
        self.assertEqual(rows[self.employee_b.pk]["total"], 1)
        self.assertEqual(rows[self.employee_a.pk]["employee_name"], self.user_a.username)

    def test_a_suspended_employee_still_holding_work_does_not_vanish(self):
        """من خرج من الخدمة وبيده عملٌ هو أوّلُ من يُسأل عنه — لا آخِرُ من يُعرَض.

        كان اللوحُ يُرشَّح على «نشط» في طرفيه (الإسنادات والموظّفون)، فيختفي
        الموقوفُ ومعه مهامُّه — ومهامُّه لم تختفِ، بقيت معلّقةً بلا صاحبٍ ظاهر.
        """
        self.employee_a.status = PlatformEmployee.Status.OFFBOARDED
        self.employee_a.save(update_fields=["status"])
        self.client.force_authenticate(self.manager)
        response = self.client.get(f"{TASKS}board/")
        self.assertEqual(response.status_code, 200, response.content)
        rows = {row["employee"]: row for row in response.data["rows"]}
        self.assertIn(
            self.employee_a.pk, rows,
            "الموقوفُ سقط من اللوح ومعه ما بيده من عمل.",
        )
        self.assertEqual(rows[self.employee_a.pk]["employee_status"], "offboarded")
        self.assertEqual(rows[self.employee_a.pk]["employee_status_display"], "خارج الخدمة")

    def test_what_he_was_forced_to_take_is_counted_apart_from_what_he_accepted(self):
        """«شو استلم» ≠ «شو أُلزم».

        الإجباريّةُ تولد `ACCEPTED` بلا فعلٍ من صاحبها، فعمودُ «مقبولة» وحدَه
        يقرأ الإلزامَ قبولاً — وهو نقيضُ ما يسأل عنه المديرُ بالضبط.
        """
        self.client.force_authenticate(self.manager)
        rows = {
            row["employee"]: row
            for row in self.client.get(f"{TASKS}board/").data["rows"]
        }
        # `self.assignment_b` مهمّةٌ فرديّةٌ — فرديّةٌ ⇒ إجباريّةٌ بحكم الخدمة.
        self.assertEqual(rows[self.employee_b.pk]["accepted"], 1)
        self.assertEqual(
            rows[self.employee_b.pk]["mandatory"], 1,
            "اللوحُ لا يفصل ما أُسند بلا خيارٍ عمّا قَبِله صاحبُه بيده.",
        )

    def test_an_employee_cannot_read_the_board(self):
        self.client.force_authenticate(self.user_a)
        response = self.client.get(f"{TASKS}board/")
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(response.data["code"], "manager_only")

    def test_the_board_does_not_issue_a_query_per_employee(self):
        """ثبوتُ العدد مع نموّ الصفوف — لا رقمٌ حرفيٌّ يُعدَّل كلّما أُضيف حقل."""
        self.client.force_authenticate(self.manager)
        few = self._board_query_count()
        for index in range(6):
            extra_user = User.objects.create_user(username=f"file_bulk_{index}", password="x")
            extra = PlatformEmployee.objects.create(
                user=extra_user, status=PlatformEmployee.Status.ACTIVE,
            )
            create_platform_task(
                actor=self.manager, title=f"مهمّةٌ جماعيّةٌ {index}",
                audience=PlatformTask.AUDIENCE_INDIVIDUAL, employee_ids=[extra.pk],
            )
        many = self._board_query_count()
        self.assertEqual(few, many, f"اللوحُ يستعلم لكلّ موظّف: {few} ← {many}.")

    def _board_query_count(self) -> int:
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(f"{TASKS}board/")
        self.assertEqual(response.status_code, 200, response.content)
        return len(ctx.captured_queries)


def _ok():
    """ردٌّ بسيطٌ يقوم مقام تمرير البايتات — البايتاتُ نفسُها محروسةٌ في `core`."""
    from django.http import HttpResponse

    return HttpResponse(b"bytes", content_type="application/pdf")
