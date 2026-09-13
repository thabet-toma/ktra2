"""مهامّ موظّفي المنصّة وملاحظاتُهم (212-E) — لا تُخلَط بـ`employee_ops.Task`.

`PlatformTask` مهامُّ فريق كترا الداخليّ (بلا `tenant`، استثناءٌ موثَّقٌ كنظيرَتها
`PlatformEmployee`)؛ و`employee_ops.Task` مهامُّ موظّفي شركةِ زبونٍ (بـ`tenant` FK).
القرارُ الحاسمُ هنا من المالك: **المهمّةُ المرفوضةُ تعود مفتوحة** — لا حالةَ
`REJECTED` نهائيّةً؛ الرفضُ يعيد الإسنادَ `RETURNED` (مُسندة) أو يحذفه (مجمَع).
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from platform_ops.models import (
    PlatformActivityLog,
    PlatformEmployee,
    PlatformEmployeeNote,
    PlatformTask,
    PlatformTaskAssignment,
    PlatformTaskSubmission,
)
from platform_ops.services import (
    PlatformOpsError,
    accept_platform_task_assignment,
    add_platform_employee_note,
    add_platform_workspace_note,
    claim_platform_task,
    create_platform_task,
    review_platform_task_submission,
    submit_platform_task,
)

User = get_user_model()


class _PlatformTaskFixture(TestCase):
    """مديرٌ وثلاثةُ موظّفين نشطين وموظّفٌ موقوفٌ رابع — يُستبعَد من `ALL` وحده."""

    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_superuser(
            username="task_manager", email="task_manager@platform.local", password="x",
        )
        cls.user_a = User.objects.create_user(username="task_staff_a", password="x")
        cls.user_b = User.objects.create_user(username="task_staff_b", password="x")
        cls.user_c = User.objects.create_user(username="task_staff_c", password="x")
        cls.user_suspended = User.objects.create_user(username="task_staff_susp", password="x")

        cls.employee_a = PlatformEmployee.objects.create(user=cls.user_a, status=PlatformEmployee.Status.ACTIVE)
        cls.employee_b = PlatformEmployee.objects.create(user=cls.user_b, status=PlatformEmployee.Status.ACTIVE)
        cls.employee_c = PlatformEmployee.objects.create(user=cls.user_c, status=PlatformEmployee.Status.ACTIVE)
        cls.employee_suspended = PlatformEmployee.objects.create(
            user=cls.user_suspended, status=PlatformEmployee.Status.ON_LEAVE,
        )

    def setUp(self):
        self.client = APIClient()


class CreateAllAudienceTest(_PlatformTaskFixture):
    def test_all_creates_assignment_for_every_active_employee_and_skips_suspended(self):
        task = create_platform_task(actor=self.manager, title="جردٌ شهريّ", audience=PlatformTask.AUDIENCE_ALL)
        assigned_employee_ids = set(
            PlatformTaskAssignment.objects.filter(task=task).values_list("employee_id", flat=True)
        )
        self.assertEqual(
            assigned_employee_ids, {self.employee_a.pk, self.employee_b.pk, self.employee_c.pk},
            "مهمّةُ `ALL` يجب أن تُسنَد لكلّ موظّفٍ نشطٍ ولا تُسنَد للموقوف.",
        )
        self.assertNotIn(self.employee_suspended.pk, assigned_employee_ids)


class OpenPoolTaskTest(_PlatformTaskFixture):
    def test_open_task_is_created_with_no_assignments(self):
        task = create_platform_task(
            actor=self.manager, title="مهمّةُ مجمَع", audience=PlatformTask.AUDIENCE_OPEN, claim_limit=1,
        )
        self.assertEqual(task.status, PlatformTask.STATUS_OPEN)
        self.assertEqual(PlatformTaskAssignment.objects.filter(task=task).count(), 0)

    def test_second_claim_is_rejected_once_claim_limit_is_reached(self):
        task = create_platform_task(
            actor=self.manager, title="مهمّةُ مجمَع بحدّ واحد", audience=PlatformTask.AUDIENCE_OPEN, claim_limit=1,
        )
        claim_platform_task(task=task, employee=self.employee_a)
        with self.assertRaises(PlatformOpsError) as ctx:
            claim_platform_task(task=task, employee=self.employee_b)
        self.assertEqual(ctx.exception.code, "claim_limit_reached")
        self.assertEqual(
            PlatformTaskAssignment.objects.filter(task=task).count(), 1,
            "المطالبةُ المرفوضة لا يجوز أن تُنشئ صفَّ إسنادٍ.",
        )


class SubmissionFlowTest(_PlatformTaskFixture):
    def setUp(self):
        super().setUp()
        self.task = create_platform_task(
            actor=self.manager, title="مهمّةٌ فرديّة", audience=PlatformTask.AUDIENCE_INDIVIDUAL,
            employee_ids=[self.employee_a.pk],
        )
        self.assignment = PlatformTaskAssignment.objects.get(task=self.task, employee=self.employee_a)

    def test_accept_then_submit_creates_exactly_one_pending_submission(self):
        accept_platform_task_assignment(assignment=self.assignment, actor=self.user_a)
        submit_platform_task(assignment=self.assignment, actor=self.user_a, body="انتهيتُ من الجزء الأوّل.")
        pending = PlatformTaskSubmission.objects.filter(
            task=self.task, employee=self.employee_a, decision=PlatformTaskSubmission.DECISION_PENDING,
        )
        self.assertEqual(pending.count(), 1)
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, PlatformTaskAssignment.STATUS_SUBMITTED)

    def test_second_submit_before_review_is_rejected(self):
        accept_platform_task_assignment(assignment=self.assignment, actor=self.user_a)
        submit_platform_task(assignment=self.assignment, actor=self.user_a, body="التسليمُ الأوّل.")
        with self.assertRaises(PlatformOpsError) as ctx:
            submit_platform_task(assignment=self.assignment, actor=self.user_a, body="التسليمُ الثاني.")
        # بوّابةُ الحالة هي المانعُ: أوّلُ تسليمٍ نقل الإسنادَ إلى `SUBMITTED`.
        self.assertEqual(ctx.exception.code, "cannot_submit")
        self.assertEqual(
            PlatformTaskSubmission.objects.filter(task=self.task, employee=self.employee_a).count(), 1,
            "تسليمٌ ثانٍ قبل مراجعة الأوّل لا يجوز أن يُنشئ صفّاً ثانياً.",
        )


class ServiceLayerOwnershipTest(_PlatformTaskFixture):
    """الملكيّةُ محروسةٌ في **الخدمة** لا في الـview وحدَه.

    درسُ 212-C: طبقةٌ واحدةٌ تحرس البابَ الذي كُتبت له وحدَه، والخدمةُ تُنادى من
    أمرِ إدارةٍ أو مهمّةٍ مجدولةٍ أو بابٍ ثانٍ يُكتَب غداً. وكان `actor` هنا
    يُؤخَذ ويُكتَب في السجلّ **ولا يُفحَص**.
    """

    def setUp(self):
        super().setUp()
        self.task = create_platform_task(
            actor=self.manager, title="مهمّةُ (أ)", audience=PlatformTask.AUDIENCE_INDIVIDUAL,
            employee_ids=[self.employee_a.pk],
        )
        self.assignment = PlatformTaskAssignment.objects.get(task=self.task, employee=self.employee_a)

    def test_a_colleague_cannot_accept_another_employees_assignment(self):
        with self.assertRaises(PlatformOpsError) as ctx:
            accept_platform_task_assignment(assignment=self.assignment, actor=self.user_b)
        self.assertEqual(ctx.exception.code, "not_your_assignment")
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status, PlatformTaskAssignment.STATUS_OFFERED)

    def test_a_colleague_cannot_submit_another_employees_assignment(self):
        accept_platform_task_assignment(assignment=self.assignment, actor=self.user_a)
        with self.assertRaises(PlatformOpsError) as ctx:
            submit_platform_task(assignment=self.assignment, actor=self.user_b, body="تسليمٌ باسم غيري.")
        self.assertEqual(ctx.exception.code, "not_your_assignment")
        self.assertEqual(PlatformTaskSubmission.objects.filter(task=self.task).count(), 0)

    def test_even_the_manager_does_not_submit_on_an_employees_behalf(self):
        """تسليمٌ بتوقيعِ غيرِ صاحبه يُفسد التقييمَ الذي يُحسَب على صاحبه."""
        accept_platform_task_assignment(assignment=self.assignment, actor=self.user_a)
        with self.assertRaises(PlatformOpsError) as ctx:
            submit_platform_task(assignment=self.assignment, actor=self.manager, body="تسليمٌ من المدير.")
        self.assertEqual(ctx.exception.code, "not_your_assignment")


class SuspendedEmployeeCannotClaimTest(_PlatformTaskFixture):
    def test_a_non_active_employee_cannot_claim_a_pool_task(self):
        """`ALL` تستبعد غيرَ النشط، فالمجمَعُ بلا الشرطِ نفسِه بابٌ خلفيّ."""
        task = create_platform_task(
            actor=self.manager, title="مهمّةُ مجمَع", audience=PlatformTask.AUDIENCE_OPEN,
        )
        with self.assertRaises(PlatformOpsError) as ctx:
            claim_platform_task(task=task, employee=self.employee_suspended)
        self.assertEqual(ctx.exception.code, "employee_not_active")
        self.assertEqual(PlatformTaskAssignment.objects.filter(task=task).count(), 0)


class ManagerNoteOnATaskTest(_PlatformTaskFixture):
    """ملاحظةُ المدير تُكتَب **على المهمّة** لا على صاحبها وحده (212-M3).

    كان لها مكانان ولا واحدَ منهما المهمّة: `PlatformEmployeeNote` على الموظّف،
    و`reviewer_notes` على **التسليم** أي لا وجودَ لها قبل أن يُسلّم. فمن لحظةِ
    الإسناد إلى لحظةِ التسليم لم يكن للمدير مكانٌ يكتب فيه كلمةً واحدة — بينما
    الموظّفُ يكتب على مهمّته منذ 212-E.
    """

    def setUp(self):
        super().setUp()
        self.task = create_platform_task(
            actor=self.manager, title="مهمّةٌ عليها حديث",
            audience=PlatformTask.AUDIENCE_INDIVIDUAL, employee_ids=[self.employee_a.pk],
        )
        self.other_task = create_platform_task(
            actor=self.manager, title="مهمّةُ زميلٍ آخر",
            audience=PlatformTask.AUDIENCE_INDIVIDUAL, employee_ids=[self.employee_b.pk],
        )

    def test_a_note_on_an_assigned_task_is_kept_with_its_task(self):
        note = add_platform_employee_note(
            employee=self.employee_a, author=self.manager, body="ركّز على البند الثاني.", task=self.task,
        )
        self.assertEqual(note.task_id, self.task.pk)

    def test_a_note_on_a_task_that_is_not_this_employees_is_refused(self):
        """ملاحظةٌ على مهمّةِ غيره تسكن خيطاً لا يفتحه، وتُريه مهمّةً ليست له."""
        with self.assertRaises(PlatformOpsError) as caught:
            add_platform_employee_note(
                employee=self.employee_a, author=self.manager,
                body="ملاحظةٌ في غير محلّها.", task=self.other_task,
            )
        self.assertEqual(caught.exception.code, "task_not_assigned_to_employee")

    def test_a_note_without_a_task_stays_a_note_about_the_employee(self):
        note = add_platform_employee_note(
            employee=self.employee_a, author=self.manager, body="أداؤه هذا الشهر ممتاز.",
        )
        self.assertIsNone(note.task_id)

    def test_the_endpoint_refuses_a_task_that_does_not_exist(self):
        self.client.force_authenticate(self.manager)
        response = self.client.post(
            "/api/platform/ops/employee-notes/create/",
            {"employee": self.employee_a.pk, "body": "على مهمّةٍ وهميّة.", "task": 10 ** 7},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json().get("code"), "task_not_found")

    def test_the_task_filter_narrows_and_never_widens(self):
        """المرشِّحُ يختار مهمّةً، **ولا يمنح رؤيةً**: الموظّفُ يرى ما له وحدَه.

        وما يمسكه هذا التأكيدُ بالضبط هو **بقاءُ تضييقِ الرؤية** مع المرشِّح:
        نفسُ المهمّةِ تعطي المديرَ ملاحظتَين وتعطي صاحبَها واحدةً — فإسقاطُ شرط
        `visibility=EMPLOYEE` يُسقِطه. ولا يدّعي الحارسُ أنّ **ترتيبَ** الشرطين
        هو المهمّ: `.filter()` مكرَّرةٌ على النموذج نفسِه تُنتج الاستعلامَ ذاتَه
        مهما تقدّم أحدُهما. ما يقتل هنا هو **استبدالُ** مجموعة الاستعلام لا
        تضييقُها — أن يُكتَب `qs = PlatformEmployeeNote.objects.filter(task=…)`
        بدل `qs = qs.filter(task_id=…)`؛ وذلك ما يسقط به هذا التأكيدُ أيضاً.
        """
        add_platform_employee_note(
            employee=self.employee_a, author=self.manager, body="لك أنت.",
            task=self.task, visibility=PlatformEmployeeNote.VISIBILITY_EMPLOYEE,
        )
        add_platform_employee_note(
            employee=self.employee_a, author=self.manager, body="للإدارة وحدها.",
            task=self.task, visibility=PlatformEmployeeNote.VISIBILITY_MANAGER_ONLY,
        )

        self.client.force_authenticate(self.manager)
        manager_bodies = {
            row["body"] for row in self.client.get(
                f"/api/platform/ops/employee-notes/?task={self.task.pk}"
            ).json()
        }
        self.assertEqual(manager_bodies, {"لك أنت.", "للإدارة وحدها."})

        self.client.force_authenticate(self.user_a)
        employee_rows = self.client.get(
            f"/api/platform/ops/employee-notes/?task={self.task.pk}"
        ).json()
        self.assertEqual([row["body"] for row in employee_rows], ["لك أنت."])
        self.assertEqual(employee_rows[0]["task"], self.task.pk)
        self.assertEqual(employee_rows[0]["task_title"], self.task.title)

    def test_a_non_numeric_task_filter_is_a_bad_request_not_a_server_error(self):
        self.client.force_authenticate(self.manager)
        response = self.client.get("/api/platform/ops/employee-notes/?task=abc")
        self.assertEqual(response.status_code, 400)


class ManagerNoteIsAuditedTest(_PlatformTaskFixture):
    def test_a_managers_note_on_an_employee_is_written_to_the_activity_log(self):
        """فعلٌ إداريٌّ على شخصٍ آخرَ يُقرأ في السجلّ — لا في جدولِ الملاحظات وحدَه."""
        note = add_platform_employee_note(
            employee=self.employee_a, author=self.manager, body="نبّهتُه على التأخّر.",
        )
        entry = PlatformActivityLog.objects.filter(
            entity_type="platform_employee_note", entity_id=note.pk,
        ).first()
        self.assertIsNotNone(entry, "ملاحظةُ المديرِ لم تُسجَّل في سجلّ النشاط.")
        self.assertEqual(entry.details.get("actor_user_id"), self.manager.pk)


class ReviewDecisionTest(_PlatformTaskFixture):
    def setUp(self):
        super().setUp()
        self.task = create_platform_task(
            actor=self.manager, title="مهمّةٌ للمراجعة", audience=PlatformTask.AUDIENCE_INDIVIDUAL,
            employee_ids=[self.employee_a.pk],
        )
        self.assignment = PlatformTaskAssignment.objects.get(task=self.task, employee=self.employee_a)
        accept_platform_task_assignment(assignment=self.assignment, actor=self.user_a)
        self.submission = submit_platform_task(assignment=self.assignment, actor=self.user_a, body="جاهزةٌ للمراجعة.")

    def test_approved_partial_returns_assignment_to_in_progress_not_completed(self):
        """«مقبولٌ بس لسّا ما خلص» — نصُّ المالك حرفيّاً؛ لا يُقفَل الإسناد."""
        review_platform_task_submission(
            submission=self.submission, actor=self.manager,
            decision=PlatformTaskSubmission.DECISION_APPROVED_PARTIAL,
            reviewer_notes="أحسنتَ، لكن ينقصُ القسمُ الثالث.",
        )
        self.assignment.refresh_from_db()
        self.task.refresh_from_db()
        self.assertEqual(self.assignment.status, PlatformTaskAssignment.STATUS_IN_PROGRESS)
        self.assertIsNone(self.task.completed_at)

    def test_rejecting_notes_are_required(self):
        with self.assertRaises(PlatformOpsError) as ctx:
            review_platform_task_submission(
                submission=self.submission, actor=self.manager,
                decision=PlatformTaskSubmission.DECISION_REJECTED, reviewer_notes="",
            )
        self.assertEqual(ctx.exception.code, "reviewer_notes_required")

    def test_approved_partial_notes_are_also_required(self):
        with self.assertRaises(PlatformOpsError) as ctx:
            review_platform_task_submission(
                submission=self.submission, actor=self.manager,
                decision=PlatformTaskSubmission.DECISION_APPROVED_PARTIAL, reviewer_notes="   ",
            )
        self.assertEqual(ctx.exception.code, "reviewer_notes_required")

    def test_rejected_submission_on_an_assigned_task_returns_the_assignment(self):
        review_platform_task_submission(
            submission=self.submission, actor=self.manager,
            decision=PlatformTaskSubmission.DECISION_REJECTED, reviewer_notes="ينقصُ إثباتٌ للتوقيع.",
        )
        self.assignment.refresh_from_db()
        self.assertEqual(
            self.assignment.status, PlatformTaskAssignment.STATUS_RETURNED,
            "المهمّةُ المرفوضةُ المُسندة يجب أن تعود RETURNED لا أن تُقفَل.",
        )

    def test_rejected_submission_on_a_pool_task_reopens_the_pool_for_others(self):
        pool_task = create_platform_task(
            actor=self.manager, title="مهمّةُ مجمَعٍ للمراجعة", audience=PlatformTask.AUDIENCE_OPEN,
        )
        assignment = claim_platform_task(task=pool_task, employee=self.employee_b)
        submission = submit_platform_task(assignment=assignment, actor=self.user_b, body="انتهيتُ.")

        review_platform_task_submission(
            submission=submission, actor=self.manager,
            decision=PlatformTaskSubmission.DECISION_REJECTED, reviewer_notes="لم يطابق المطلوب.",
        )

        self.assertFalse(
            PlatformTaskAssignment.objects.filter(task=pool_task, employee=self.employee_b).exists(),
            "رفضُ تسليمِ مهمّةِ مجمَعٍ يجب أن يحذف الإسنادَ فتعود المهمّةُ إلى المجمَع.",
        )
        pool_task.refresh_from_db()
        self.assertEqual(pool_task.status, PlatformTask.STATUS_OPEN)
        # وتُطالِب موظّفةٌ أخرى بها بنجاح — دليلٌ سلوكيٌّ على أنّها فعلاً عادت مجمَعاً.
        new_assignment = claim_platform_task(task=pool_task, employee=self.employee_c)
        self.assertEqual(new_assignment.employee_id, self.employee_c.pk)


class ListsDoNotIssueAQueryPerRowTest(_PlatformTaskFixture):
    """شاشةُ المدير تُفتَح على إسنادات الفريق كلِّه — واستعلامٌ لكلّ صفٍّ يكبر معها.

    والحمولاتُ تعرض عنوانَ المهمّة واسمَ الموظّف واسمَ المراجِع، فبلا
    `select_related` كان كلُّ صفٍّ يُصدِر استعلاماً أو اثنين — وهو العيبُ الذي
    صيّر ٣٥٠١ استعلامٍ ثلاثةً في هذا المستودع.
    """

    def setUp(self):
        super().setUp()
        self.task = create_platform_task(
            actor=self.manager, title="مهمّةُ الجميع", audience=PlatformTask.AUDIENCE_ALL,
        )
        for user, employee in (
            (self.user_a, self.employee_a), (self.user_b, self.employee_b), (self.user_c, self.employee_c),
        ):
            assignment = PlatformTaskAssignment.objects.get(task=self.task, employee=employee)
            accept_platform_task_assignment(assignment=assignment, actor=user)
            submit_platform_task(assignment=assignment, actor=user, body="تسليم.")

    def _count(self, url: str) -> int:
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self.client.force_authenticate(self.manager)
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200, response.content)
        return len(ctx.captured_queries)

    def test_the_assignments_list_does_not_scale_its_queries_with_the_rows(self):
        # ثلاثةُ صفوفٍ: بلا `select_related` تسعةُ استعلاماتٍ أو أكثر.
        self.assertLessEqual(
            self._count("/api/platform/ops/assignments/"), 6,
            "قائمةُ الإسنادات تُصدِر استعلاماً لكلّ صفّ.",
        )

    def test_the_submissions_list_does_not_scale_its_queries_with_the_rows(self):
        self.assertLessEqual(
            self._count("/api/platform/ops/submissions/"), 6,
            "قائمةُ التسليمات تُصدِر استعلاماً لكلّ صفّ.",
        )


class RejectedPoolSubmissionReviewedTwiceTest(_PlatformTaskFixture):
    """مراجعةُ تسليمٍ مرفوضٍ في مهمّةِ مجمَعٍ مرّةً ثانيةً: خطأُ مجالٍ لا انهيارُ خادم.

    رفضُ تسليمِ مهمّةِ مجمَعٍ **يحذف الإسناد** (تعود إلى المجمَع بقرار المالك)،
    فالبحثُ عن ذلك الإسنادِ قبل فحصِ «رُوجع سلفاً» كان يرفع `DoesNotExist` غيرَ
    معالجةٍ — أي 500 مكان 400 مفهومة.
    """

    def test_reviewing_the_same_rejected_pool_submission_again_raises_a_domain_error(self):
        task = create_platform_task(
            actor=self.manager, title="مهمّةُ مجمَعٍ تُرفَض", audience=PlatformTask.AUDIENCE_OPEN,
        )
        assignment = claim_platform_task(task=task, employee=self.employee_a)
        submission = submit_platform_task(assignment=assignment, actor=self.user_a, body="تسليمٌ أوّل.")
        review_platform_task_submission(
            submission=submission, actor=self.manager,
            decision=PlatformTaskSubmission.DECISION_REJECTED, reviewer_notes="ناقصٌ جدّاً.",
        )
        self.assertEqual(
            PlatformTaskAssignment.objects.filter(task=task).count(), 0,
            "رفضُ تسليمِ مهمّةِ مجمَعٍ يجب أن يعيدها إلى المجمَع بلا إسناد.",
        )
        with self.assertRaises(PlatformOpsError) as ctx:
            review_platform_task_submission(
                submission=submission, actor=self.manager,
                decision=PlatformTaskSubmission.DECISION_APPROVED_FULL,
            )
        self.assertEqual(ctx.exception.code, "already_reviewed")


class CompletedAtOnLastAssignmentTest(_PlatformTaskFixture):
    def test_completed_at_is_set_only_when_the_last_assignment_completes(self):
        task = create_platform_task(
            actor=self.manager, title="مهمّةٌ لموظّفَين", audience=PlatformTask.AUDIENCE_SPECIFIC,
            employee_ids=[self.employee_a.pk, self.employee_b.pk],
        )
        assignment_a = PlatformTaskAssignment.objects.get(task=task, employee=self.employee_a)
        assignment_b = PlatformTaskAssignment.objects.get(task=task, employee=self.employee_b)

        accept_platform_task_assignment(assignment=assignment_a, actor=self.user_a)
        submission_a = submit_platform_task(assignment=assignment_a, actor=self.user_a, body="جاهز.")
        review_platform_task_submission(
            submission=submission_a, actor=self.manager, decision=PlatformTaskSubmission.DECISION_APPROVED_FULL,
        )
        task.refresh_from_db()
        self.assertIsNone(
            task.completed_at, "إسنادٌ واحدٌ اكتمل من اثنين — المهمّةُ ليست مكتملةً بعد.",
        )

        accept_platform_task_assignment(assignment=assignment_b, actor=self.user_b)
        submission_b = submit_platform_task(assignment=assignment_b, actor=self.user_b, body="جاهز.")
        review_platform_task_submission(
            submission=submission_b, actor=self.manager, decision=PlatformTaskSubmission.DECISION_APPROVED_FULL,
        )
        task.refresh_from_db()
        self.assertIsNotNone(
            task.completed_at, "اكتمالُ **آخرِ** إسنادٍ يجب أن يضبط `completed_at`.",
        )
        self.assertEqual(task.status, PlatformTask.STATUS_COMPLETED)


class PoolClaimCountIsServerTruthTest(_PlatformTaskFixture):
    """عددُ المطالبين يأتي من الحمولة — والواجهةُ لا تستطيع عدَّه بنفسها.

    قائمةُ إسنادات الموظّف مقصورةٌ عليه، وبطاقةُ المجمَع لا تُعرَض إلا لمن لا
    إسنادَ له فيها: فالعدُّ في المتصفّح **صفرٌ بحكم البناء** لا معلومةٌ ناقصة.
    """

    def test_the_manager_sees_the_real_claim_count(self):
        task = create_platform_task(
            actor=self.manager, title="مهمّةُ مجمَعٍ بحدّ ثلاثة",
            audience=PlatformTask.AUDIENCE_OPEN, claim_limit=3,
        )
        claim_platform_task(task=task, employee=self.employee_a)
        claim_platform_task(task=task, employee=self.employee_b)

        self.client.force_authenticate(self.manager)
        response = self.client.get("/api/platform/ops/tasks/")
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        row = next(item for item in rows if item["id"] == task.pk)
        self.assertEqual(row["claimed_count"], 2, row)

    def test_the_third_employee_sees_the_two_claims_of_his_colleagues(self):
        """**الفخُّ الذي يحرسه هذا الاختبار**: عدٌّ يُحسَب من زاوية المستدعي.

        الموظّفُ الثالثُ لا يرى إسنادَي زميلَيه بحكم النطاق، فأيُّ عدٍّ مبنيٍّ على
        ما يراه — في الواجهة أو في مُسلسِلٍ يقرأ `request.user` — يُخرج صفراً
        يبدو معلومةً وهو عدمُها. والرقمُ من صفوف المهمّة نفسِها لا من نطاق قارئها.
        """
        task = create_platform_task(
            actor=self.manager, title="مهمّةُ مجمَعٍ يراها الثالث",
            audience=PlatformTask.AUDIENCE_OPEN, claim_limit=3,
        )
        claim_platform_task(task=task, employee=self.employee_a)
        claim_platform_task(task=task, employee=self.employee_b)

        self.client.force_authenticate(self.user_c)
        response = self.client.get("/api/platform/ops/tasks/")
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        row = next(item for item in rows if item["id"] == task.pk)
        self.assertEqual(
            row["claimed_count"], 2,
            "الموظّفُ الثالثُ يجب أن يرى مطالبةَ زميلَيه وإن لم يرَ إسنادَيهما.",
        )

    def test_a_freshly_created_task_carries_the_count_too(self):
        """حمولةُ الإنشاء تخرج من كائنٍ بلا حسابٍ مسبق — فلا تُسقِط الحقلَ ولا ترفع خطأً."""
        self.client.force_authenticate(self.manager)
        response = self.client.post(
            "/api/platform/ops/tasks/create/",
            {"title": "مهمّةٌ للتوّ", "audience": PlatformTask.AUDIENCE_INDIVIDUAL,
             "employee_ids": [self.employee_a.pk]},
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["claimed_count"], 1, response.data)

    def test_the_count_does_not_add_a_query_per_row(self):
        for index in range(4):
            pool = create_platform_task(
                actor=self.manager, title=f"مجمَعٌ {index}", audience=PlatformTask.AUDIENCE_OPEN,
            )
            claim_platform_task(task=pool, employee=self.employee_a)

        self.client.force_authenticate(self.manager)
        # استعلامٌ واحدٌ لا غير: العدُّ استعلامٌ فرعيٌّ **داخل** جملة الاختيار،
        # فأربعُ مهامٍّ وأربعُ مطالباتٍ تُقرَأ كما تُقرَأ واحدة.
        with self.assertNumQueries(1):
            self.client.get("/api/platform/ops/tasks/")


class WorkspaceNotesReachTheManagerNamedTest(_PlatformTaskFixture):
    """ملاحظةُ الموظّف على مهمّته وُجدت ليقرأها السوبر أدمن — ومعرَّفٌ عدديٌّ لا يُقرأ."""

    def test_the_manager_sees_the_writer_and_the_task_title(self):
        task = create_platform_task(
            actor=self.manager, title="مهمّةٌ فيها ملاحظة", audience=PlatformTask.AUDIENCE_INDIVIDUAL,
            employee_ids=[self.employee_a.pk],
        )
        add_platform_workspace_note(employee=self.employee_a, body="اتّصلتُ بالزبون مرّتين.", task=task)

        self.client.force_authenticate(self.manager)
        response = self.client.get("/api/platform/ops/workspace-notes/")
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0]["employee_name"], self.user_a.username)
        self.assertEqual(rows[0]["task_title"], "مهمّةٌ فيها ملاحظة")

    def test_a_general_note_carries_an_empty_task_title(self):
        add_platform_workspace_note(employee=self.employee_a, body="ملاحظةٌ عمومية.", task=None)

        self.client.force_authenticate(self.manager)
        response = self.client.get("/api/platform/ops/workspace-notes/")
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertIsNone(rows[0]["task"])
        self.assertEqual(rows[0]["task_title"], "")


class _HttpScopeFixture(_PlatformTaskFixture):
    """تركيبُ مهمّتين فرديّتين لموظّفَين — **بلا اختباراتٍ في هذا الصنف**.

    وصنفُ تركيبٍ مُختبَرٌ في الوقت نفسِه يورّث اختباراتِه لكلّ من يرثه: كانت
    `SubmissionsScopeTest` ترث `test_staff_cannot_review_a_submission` وتقبل
    الإسنادَ في `setUp` أيضاً، فيسقط اختبارُ الأبِ على «هذا الإسنادُ ليس بانتظار
    القبول» — سقوطٌ لا علاقةَ له بما يحرسه اسمُه.
    """

    def setUp(self):
        super().setUp()
        self.task_a = create_platform_task(
            actor=self.manager, title="مهمّةٌ خاصّةٌ بـ(أ)", audience=PlatformTask.AUDIENCE_INDIVIDUAL,
            employee_ids=[self.employee_a.pk],
        )
        self.task_b = create_platform_task(
            actor=self.manager, title="مهمّةٌ خاصّةٌ بـ(ب)", audience=PlatformTask.AUDIENCE_INDIVIDUAL,
            employee_ids=[self.employee_b.pk],
        )
        self.assignment_a = PlatformTaskAssignment.objects.get(task=self.task_a, employee=self.employee_a)
        self.assignment_b = PlatformTaskAssignment.objects.get(task=self.task_b, employee=self.employee_b)

class HttpScopeTest(_HttpScopeFixture):
    """التضييقُ على مستوى الـHTTP — يُحرَس أيضاً بـ`test_staff_scope_guard.py`."""

    def test_staff_cannot_see_a_colleague_task(self):
        self.client.force_authenticate(self.user_a)
        response = self.client.get("/api/platform/ops/tasks/")
        ids = {row["id"] for row in response.data["results"]} if isinstance(response.data, dict) else {
            row["id"] for row in response.data
        }
        self.assertIn(self.task_a.pk, ids)
        self.assertNotIn(self.task_b.pk, ids)

    def test_staff_cannot_create_a_task(self):
        self.client.force_authenticate(self.user_a)
        response = self.client.post(
            "/api/platform/ops/tasks/create/",
            {"title": "محاولةُ إنشاءٍ من موظّف", "audience": PlatformTask.AUDIENCE_ALL},
        )
        self.assertEqual(response.status_code, 403, response.content)

    def test_manager_can_create_a_task(self):
        self.client.force_authenticate(self.manager)
        response = self.client.post(
            "/api/platform/ops/tasks/create/",
            {"title": "مهمّةٌ من المدير", "audience": PlatformTask.AUDIENCE_OPEN, "claim_limit": 2},
        )
        self.assertEqual(response.status_code, 201, response.content)

    def test_staff_cannot_submit_a_colleague_assignment(self):
        self.client.force_authenticate(self.user_a)
        response = self.client.post(
            f"/api/platform/ops/assignments/{self.assignment_b.pk}/submit/", {"body": "محاولةٌ"},
        )
        self.assertIn(response.status_code, (403, 404), response.content)

    def test_staff_cannot_review_a_submission(self):
        accept_platform_task_assignment(assignment=self.assignment_a, actor=self.user_a)
        submission = submit_platform_task(assignment=self.assignment_a, actor=self.user_a, body="جاهز.")
        self.client.force_authenticate(self.user_a)
        response = self.client.post(
            f"/api/platform/ops/submissions/{submission.pk}/review/",
            {"decision": PlatformTaskSubmission.DECISION_APPROVED_FULL},
        )
        self.assertEqual(response.status_code, 403, response.content)


class TasksDetailScopeTest(_HttpScopeFixture):
    def test_detail_404s_on_a_colleague_task(self):
        self.client.force_authenticate(self.user_a)
        self.assertEqual(
            self.client.get(f"/api/platform/ops/tasks/{self.task_b.pk}/").status_code, 404,
        )
        self.assertEqual(
            self.client.get(f"/api/platform/ops/tasks/{self.task_a.pk}/").status_code, 200,
        )

    def test_manager_sees_both_tasks(self):
        self.client.force_authenticate(self.manager)
        response = self.client.get("/api/platform/ops/tasks/")
        ids = {row["id"] for row in response.data["results"]} if isinstance(response.data, dict) else {
            row["id"] for row in response.data
        }
        self.assertIn(self.task_a.pk, ids)
        self.assertIn(self.task_b.pk, ids)


class AssignmentsScopeTest(_HttpScopeFixture):
    def _ids(self, response):
        payload = response.data
        rows = payload["results"] if isinstance(payload, dict) and "results" in payload else payload
        return {row["id"] for row in rows}

    def test_list_hides_a_colleague_assignment(self):
        self.client.force_authenticate(self.user_a)
        ids = self._ids(self.client.get("/api/platform/ops/assignments/"))
        self.assertIn(self.assignment_a.pk, ids)
        self.assertNotIn(self.assignment_b.pk, ids)

    def test_detail_404s_on_a_colleague_assignment(self):
        self.client.force_authenticate(self.user_a)
        self.assertEqual(
            self.client.get(f"/api/platform/ops/assignments/{self.assignment_b.pk}/").status_code, 404,
        )
        self.assertEqual(
            self.client.get(f"/api/platform/ops/assignments/{self.assignment_a.pk}/").status_code, 200,
        )

    def test_manager_sees_both_assignments(self):
        self.client.force_authenticate(self.manager)
        ids = self._ids(self.client.get("/api/platform/ops/assignments/"))
        self.assertIn(self.assignment_a.pk, ids)
        self.assertIn(self.assignment_b.pk, ids)


class SubmissionsScopeTest(_HttpScopeFixture):
    def setUp(self):
        super().setUp()
        accept_platform_task_assignment(assignment=self.assignment_a, actor=self.user_a)
        accept_platform_task_assignment(assignment=self.assignment_b, actor=self.user_b)
        self.submission_a = submit_platform_task(assignment=self.assignment_a, actor=self.user_a, body="أ جاهز.")
        self.submission_b = submit_platform_task(assignment=self.assignment_b, actor=self.user_b, body="ب جاهز.")

    def _ids(self, response):
        payload = response.data
        rows = payload["results"] if isinstance(payload, dict) and "results" in payload else payload
        return {row["id"] for row in rows}

    def test_list_hides_a_colleague_submission(self):
        self.client.force_authenticate(self.user_a)
        ids = self._ids(self.client.get("/api/platform/ops/submissions/"))
        self.assertIn(self.submission_a.pk, ids)
        self.assertNotIn(self.submission_b.pk, ids)

    def test_detail_404s_on_a_colleague_submission(self):
        self.client.force_authenticate(self.user_a)
        self.assertEqual(
            self.client.get(f"/api/platform/ops/submissions/{self.submission_b.pk}/").status_code, 404,
        )
        self.assertEqual(
            self.client.get(f"/api/platform/ops/submissions/{self.submission_a.pk}/").status_code, 200,
        )

    def test_manager_sees_both_submissions(self):
        self.client.force_authenticate(self.manager)
        ids = self._ids(self.client.get("/api/platform/ops/submissions/"))
        self.assertIn(self.submission_a.pk, ids)
        self.assertIn(self.submission_b.pk, ids)


class WorkspaceNotesScopeTest(_HttpScopeFixture):
    def setUp(self):
        super().setUp()
        self.note_a = add_platform_workspace_note(employee=self.employee_a, body="ملاحظةُ (أ).")
        self.note_b = add_platform_workspace_note(employee=self.employee_b, body="ملاحظةُ (ب).")

    def _ids(self, response):
        payload = response.data
        rows = payload["results"] if isinstance(payload, dict) and "results" in payload else payload
        return {row["id"] for row in rows}

    def test_list_hides_a_colleague_note(self):
        self.client.force_authenticate(self.user_a)
        ids = self._ids(self.client.get("/api/platform/ops/workspace-notes/"))
        self.assertIn(self.note_a.pk, ids)
        self.assertNotIn(self.note_b.pk, ids)

    def test_detail_404s_on_a_colleague_note(self):
        self.client.force_authenticate(self.user_a)
        self.assertEqual(
            self.client.get(f"/api/platform/ops/workspace-notes/{self.note_b.pk}/").status_code, 404,
        )
        self.assertEqual(
            self.client.get(f"/api/platform/ops/workspace-notes/{self.note_a.pk}/").status_code, 200,
        )

    def test_manager_sees_both_notes(self):
        self.client.force_authenticate(self.manager)
        ids = self._ids(self.client.get("/api/platform/ops/workspace-notes/"))
        self.assertIn(self.note_a.pk, ids)
        self.assertIn(self.note_b.pk, ids)


class EmployeeNotesDetailScopeTest(_PlatformTaskFixture):
    def test_detail_404s_on_a_colleague_note(self):
        self.client.force_authenticate(self.manager)
        note_a = self.client.post(
            "/api/platform/ops/employee-notes/create/",
            {"employee": self.employee_a.pk, "body": "ملاحظةٌ عن (أ).", "visibility": "EMPLOYEE"},
        ).data
        note_b = self.client.post(
            "/api/platform/ops/employee-notes/create/",
            {"employee": self.employee_b.pk, "body": "ملاحظةٌ عن (ب).", "visibility": "EMPLOYEE"},
        ).data

        self.client.force_authenticate(self.user_a)
        self.assertEqual(
            self.client.get(f"/api/platform/ops/employee-notes/{note_b['id']}/").status_code, 404,
        )
        self.assertEqual(
            self.client.get(f"/api/platform/ops/employee-notes/{note_a['id']}/").status_code, 200,
        )

    def test_manager_sees_every_note(self):
        self.client.force_authenticate(self.manager)
        self.client.post(
            "/api/platform/ops/employee-notes/create/",
            {"employee": self.employee_a.pk, "body": "ملاحظةٌ عن (أ).", "visibility": "EMPLOYEE"},
        )
        self.client.post(
            "/api/platform/ops/employee-notes/create/",
            {"employee": self.employee_b.pk, "body": "ملاحظةٌ عن (ب).", "visibility": "MANAGER_ONLY"},
        )
        response = self.client.get("/api/platform/ops/employee-notes/")
        bodies = {row["body"] for row in response.data["results"]} if isinstance(response.data, dict) else {
            row["body"] for row in response.data
        }
        self.assertIn("ملاحظةٌ عن (أ).", bodies)
        self.assertIn("ملاحظةٌ عن (ب).", bodies)


class EmployeeNotesEmployeeFilterTest(_PlatformTaskFixture):
    """‏`?employee=` — يضيّق القائمةَ في الخادم، **ولا يوسّع رؤيةَ أحد**.

    درجُ ملفِّ الموظّف يعرض ما على موظّفٍ واحد. وبلا مرشّحٍ خادميٍّ كان عليه أن
    يجلب ملاحظاتِ **كلِّ** الموظّفين ويُسقِط ما ليس لهذا الملفِّ في المتصفّح:
    حمولةٌ تكبر بعدد الفريق لعرض سطرَين، ونصُّ ملاحظةٍ عن زميلٍ يعبر الشبكةَ
    بلا داعٍ.

    والخطرُ المقابلُ أنّ مُعامِلاً كهذا يصير **بابَ توسيع**: موظّفٌ يكتب معرّفَ
    زميله فيقرأ ما عليه. فيُقاس الاتّجاهان معاً هنا.
    """

    def _bodies(self, response):
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        return {row["body"] for row in rows}

    def setUp(self):
        super().setUp()
        self.client.force_authenticate(self.manager)
        for employee, body, visibility in (
            (self.employee_a, "ملاحظةٌ ظاهرةٌ لـ(أ).", "EMPLOYEE"),
            (self.employee_a, "ملاحظةُ إدارةٍ عن (أ).", "MANAGER_ONLY"),
            (self.employee_b, "ملاحظةٌ ظاهرةٌ لـ(ب).", "EMPLOYEE"),
        ):
            self.client.post(
                "/api/platform/ops/employee-notes/create/",
                {"employee": employee.pk, "body": body, "visibility": visibility},
            )

    def test_the_filter_narrows_the_managers_list_to_one_employee(self):
        response = self.client.get(
            "/api/platform/ops/employee-notes/", {"employee": self.employee_a.pk}
        )
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            self._bodies(response),
            {"ملاحظةٌ ظاهرةٌ لـ(أ).", "ملاحظةُ إدارةٍ عن (أ)."},
            "المرشّحُ لم يضيّق: ملاحظاتُ زميلٍ في ملفِّ غيرِه.",
        )

    def test_the_filter_does_not_widen_what_an_employee_may_read(self):
        """المرشّحُ يُطبَّق **بعد** تضييق غير المدير لا قبلَه.

        لو طُبِّق قبلَه لكان موظّفٌ يكتب معرّفَ زميله فيقرأ ما عليه — تسريبٌ
        يفتحه مُعامِلٌ أُضيف للعرض.
        """
        self.client.force_authenticate(self.user_a)
        colleague = self.client.get(
            "/api/platform/ops/employee-notes/", {"employee": self.employee_b.pk}
        )
        self.assertEqual(colleague.status_code, 200, colleague.data)
        self.assertEqual(self._bodies(colleague), set(), "موظّفٌ قرأ ملاحظاتِ زميله بمُعامِلٍ.")

        mine = self.client.get(
            "/api/platform/ops/employee-notes/", {"employee": self.employee_a.pk}
        )
        self.assertEqual(
            self._bodies(mine), {"ملاحظةٌ ظاهرةٌ لـ(أ)."},
            "وملاحظةُ الإدارة `MANAGER_ONLY` لا تخرج بالمرشّح كذلك.",
        )

    def test_a_non_numeric_employee_is_a_bad_request_not_a_server_error(self):
        """قيمةٌ غير رقميّة تصل `filter(employee_id=…)` فترفع `ValueError` ⇒ 500.

        ورمزُ ٥٠٠ على مُعامِلٍ خاطئ يُقرأ «النظامُ معطوب» لا «طلبُك خاطئ».
        """
        response = self.client.get("/api/platform/ops/employee-notes/", {"employee": "abc"})
        self.assertEqual(response.status_code, 400, response.data)

    def test_no_filter_still_returns_the_whole_book_for_a_manager(self):
        """وغيابُ المُعامِل لا يعني فراغاً: لوحةُ المهامّ تسأل بلا مرشّحٍ."""
        response = self.client.get("/api/platform/ops/employee-notes/")
        self.assertEqual(len(self._bodies(response)), 3)


class EmployeeNoteVisibilityTest(_PlatformTaskFixture):
    def test_staff_cannot_see_a_manager_only_note_or_a_colleague_note(self):
        self.client.force_authenticate(self.manager)
        visible = self.client.post(
            "/api/platform/ops/employee-notes/create/",
            {"employee": self.employee_a.pk, "body": "أداءٌ جيّد.", "visibility": "EMPLOYEE"},
        )
        hidden = self.client.post(
            "/api/platform/ops/employee-notes/create/",
            {"employee": self.employee_a.pk, "body": "ملاحظةُ تطويرٍ داخليّة.", "visibility": "MANAGER_ONLY"},
        )
        colleague_note = self.client.post(
            "/api/platform/ops/employee-notes/create/",
            {"employee": self.employee_b.pk, "body": "ملاحظةٌ عن (ب).", "visibility": "EMPLOYEE"},
        )
        self.assertEqual(visible.status_code, 201, visible.content)
        self.assertEqual(hidden.status_code, 201, hidden.content)
        self.assertEqual(colleague_note.status_code, 201, colleague_note.content)

        self.client.force_authenticate(self.user_a)
        response = self.client.get("/api/platform/ops/employee-notes/")
        bodies = {row["body"] for row in response.data["results"]} if isinstance(response.data, dict) else {
            row["body"] for row in response.data
        }
        self.assertIn("أداءٌ جيّد.", bodies)
        self.assertNotIn("ملاحظةُ تطويرٍ داخليّة.", bodies)
        self.assertNotIn("ملاحظةٌ عن (ب).", bodies)

    def test_staff_cannot_write_an_employee_note(self):
        self.client.force_authenticate(self.user_a)
        response = self.client.post(
            "/api/platform/ops/employee-notes/create/",
            {"employee": self.employee_a.pk, "body": "محاولةٌ من موظّف."},
        )
        self.assertEqual(response.status_code, 403, response.content)


class WorkspaceNoteOwnershipTest(_PlatformTaskFixture):
    def test_a_note_on_a_task_not_assigned_to_the_writer_is_rejected(self):
        task = create_platform_task(
            actor=self.manager, title="مهمّةٌ بعيدة", audience=PlatformTask.AUDIENCE_INDIVIDUAL,
            employee_ids=[self.employee_b.pk],
        )
        with self.assertRaises(PlatformOpsError) as ctx:
            add_platform_workspace_note(employee=self.employee_a, body="محاولةٌ.", task=task)
        self.assertEqual(ctx.exception.code, "task_not_assigned_to_you")

    def test_a_general_workspace_note_needs_no_task(self):
        note = add_platform_workspace_note(employee=self.employee_a, body="ملاحظةٌ عمومية.")
        self.assertIsNone(note.task)
