"""اختبارات مهام وتسليمات ومراجعة وحدة متابعة الموظفين (المرحلة ٣)."""
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from core.access import FIELD_STAFF_ROLE
from core.models import TenantModule
from core.modules import invalidate_module_cache
from employee_ops.models import (
    Task,
    TaskAssignment,
    TaskSubmission,
    TaskSubmissionAttachment,
    TaskSubmissionItem,
)
from hr.models import Employee
from tenants.models import Currency, UserCompanyMembership
from tenants.services import create_company


class EmployeeOpsTasksTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True})

        # مستخدمو ومديرو الشركتين
        cls.manager_a = User.objects.create_user(username="mgr_task_a", password="x")
        cls.manager_b = User.objects.create_user(username="mgr_task_b", password="x")

        cls.tenant_a = create_company("شركة المهام أ", cls.manager_a)
        cls.tenant_b = create_company("شركة المهام ب", cls.manager_b)

        # تفعيل الوحدة لكلا الشركتين
        TenantModule.objects.create(tenant=cls.tenant_a, module_key="employee_ops", enabled=True)
        TenantModule.objects.create(tenant=cls.tenant_b, module_key="employee_ops", enabled=True)
        invalidate_module_cache(cls.tenant_a.pk)
        invalidate_module_cache(cls.tenant_b.pk)

        # موظفو الشركة أ
        cls.staff_a1 = User.objects.create_user(username="staff_a1", password="x")
        cls.staff_a2 = User.objects.create_user(username="staff_a2", password="x")
        cls.staff_a3 = User.objects.create_user(username="staff_a3", password="x")
        cls.staff_unassigned = User.objects.create_user(username="staff_unassigned", password="x")

        UserCompanyMembership.objects.create(user=cls.staff_a1, tenant=cls.tenant_a, role=FIELD_STAFF_ROLE)
        UserCompanyMembership.objects.create(user=cls.staff_a2, tenant=cls.tenant_a, role=FIELD_STAFF_ROLE)
        UserCompanyMembership.objects.create(user=cls.staff_a3, tenant=cls.tenant_a, role=FIELD_STAFF_ROLE)
        UserCompanyMembership.objects.create(user=cls.staff_unassigned, tenant=cls.tenant_a, role=FIELD_STAFF_ROLE)

        cls.employee_a1 = Employee.objects.create(
            tenant=cls.tenant_a, user=cls.staff_a1, name="موظف أ1", code="101", is_active=True
        )
        cls.employee_a2 = Employee.objects.create(
            tenant=cls.tenant_a, user=cls.staff_a2, name="موظف أ2", code="102", is_active=True
        )
        cls.employee_a3 = Employee.objects.create(
            tenant=cls.tenant_a, user=cls.staff_a3, name="موظف أ3", code="103", is_active=True
        )
        cls.employee_a_unassigned = Employee.objects.create(
            tenant=cls.tenant_a, user=cls.staff_unassigned, name="موظف غير مسند", code="104", is_active=True
        )

        # موظف الشركة ب
        cls.staff_b1 = User.objects.create_user(username="staff_b1", password="x")
        UserCompanyMembership.objects.create(user=cls.staff_b1, tenant=cls.tenant_b, role=FIELD_STAFF_ROLE)
        cls.employee_b1 = Employee.objects.create(
            tenant=cls.tenant_b, user=cls.staff_b1, name="موظف ب1", code="201", is_active=True
        )

    def test_submission_from_a_non_assignee_is_refused(self):
        """موظف في نفس الشركة غير مسند إليه: 403 ولا صف تسليم ينشأ."""
        task = Task.objects.create(
            tenant=self.tenant_a,
            title="مهمة فحص موقع",
            status=Task.STATUS_NEW,
        )
        TaskAssignment.objects.create(
            tenant=self.tenant_a,
            task=task,
            employee=self.employee_a1,
        )

        self.client.force_authenticate(user=self.staff_unassigned)
        res = self.client.post(
            f"/api/employee-ops/tasks/{task.id}/submit/",
            {"body": "محاولة تسليم غير مصرح بها"},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res.status_code, 403)
        self.assertFalse(TaskSubmission.objects.filter(task=task).exists())

    def test_each_assignee_has_an_independent_status_and_timer(self):
        """مهمة لثلاثة: تسليم الأول لا يغير حالة الثاني ولا مؤقته."""
        task = Task.objects.create(
            tenant=self.tenant_a,
            title="مهمة متعددة لثلاثة",
            status=Task.STATUS_NEW,
        )
        a1 = TaskAssignment.objects.create(tenant=self.tenant_a, task=task, employee=self.employee_a1)
        a2 = TaskAssignment.objects.create(tenant=self.tenant_a, task=task, employee=self.employee_a2)
        a3 = TaskAssignment.objects.create(tenant=self.tenant_a, task=task, employee=self.employee_a3)

        # الموظف الأول يبدأ ويسلم
        self.client.force_authenticate(user=self.staff_a1)
        res_start = self.client.post(
            f"/api/employee-ops/tasks/{task.id}/start/",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res_start.status_code, 200)

        res_submit = self.client.post(
            f"/api/employee-ops/tasks/{task.id}/submit/",
            {"body": "تسليم الموظف الأول"},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res_submit.status_code, 201)

        a1.refresh_from_db()
        a2.refresh_from_db()
        a3.refresh_from_db()

        self.assertEqual(a1.status, TaskAssignment.STATUS_SUBMITTED)
        self.assertIsNotNone(a1.work_started_at)

        # الموظفان الثاني والثالث لم تتغير حالتهما ولم تبدأ مؤقتاتهما
        self.assertEqual(a2.status, TaskAssignment.STATUS_NOT_STARTED)
        self.assertIsNone(a2.work_started_at)
        self.assertEqual(a2.total_work_seconds, 0)

        self.assertEqual(a3.status, TaskAssignment.STATUS_NOT_STARTED)
        self.assertIsNone(a3.work_started_at)
        self.assertEqual(a3.total_work_seconds, 0)

    def test_task_completes_only_when_every_assignment_is_approved(self):
        """قبول اثنين من ثلاثة يبقي المهمة WAITING_FOR_REVIEW؛ والثالث يكملها ويضبط completed_at."""
        task = Task.objects.create(
            tenant=self.tenant_a,
            title="مهمة الاعتماد الجماعي",
            status=Task.STATUS_NEW,
        )
        TaskAssignment.objects.create(tenant=self.tenant_a, task=task, employee=self.employee_a1)
        TaskAssignment.objects.create(tenant=self.tenant_a, task=task, employee=self.employee_a2)
        TaskAssignment.objects.create(tenant=self.tenant_a, task=task, employee=self.employee_a3)

        # الثلاثة يقدمون تسليماتهم
        for staff in (self.staff_a1, self.staff_a2, self.staff_a3):
            self.client.force_authenticate(user=staff)
            res = self.client.post(
                f"/api/employee-ops/tasks/{task.id}/submit/",
                {"body": f"تسليم {staff.username}"},
                format="json",
                HTTP_X_TENANT_ID=str(self.tenant_a.pk),
            )
            self.assertEqual(res.status_code, 201)

        task.refresh_from_db()
        self.assertEqual(task.status, Task.STATUS_WAITING_FOR_REVIEW)

        submissions = list(TaskSubmission.objects.filter(task=task).order_by("id"))
        self.assertEqual(len(submissions), 3)

        # المدير يعتمد الأول: قبول كامل
        self.client.force_authenticate(user=self.manager_a)
        res_rev1 = self.client.post(
            f"/api/employee-ops/submissions/{submissions[0].id}/review/",
            {"decision": "approved_full", "reviewer_notes": "عمل ممتاز"},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res_rev1.status_code, 200)

        task.refresh_from_db()
        self.assertEqual(task.status, Task.STATUS_WAITING_FOR_REVIEW)
        self.assertIsNone(task.completed_at)

        # المدير يعتمد الثاني: قبول جزئي
        res_rev2 = self.client.post(
            f"/api/employee-ops/submissions/{submissions[1].id}/review/",
            {"decision": "approved_partial", "reviewer_notes": "مقبول مع ملاحظات"},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res_rev2.status_code, 200)

        task.refresh_from_db()
        self.assertEqual(task.status, Task.STATUS_WAITING_FOR_REVIEW)
        self.assertIsNone(task.completed_at)

        # المدير يعتمد الثالث: تكتمل المهمة ويضبط completed_at
        res_rev3 = self.client.post(
            f"/api/employee-ops/submissions/{submissions[2].id}/review/",
            {"decision": "approved_full", "reviewer_notes": "اكتمل الباقي"},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res_rev3.status_code, 200)

        task.refresh_from_db()
        self.assertEqual(task.status, Task.STATUS_COMPLETED)
        self.assertIsNotNone(task.completed_at)

    def test_rejection_requires_a_written_reason(self):
        """رفض بلا سبب: 400، والقرار لا يحفظ."""
        task = Task.objects.create(tenant=self.tenant_a, title="مهمة للمراجعة")
        TaskAssignment.objects.create(tenant=self.tenant_a, task=task, employee=self.employee_a1)

        self.client.force_authenticate(user=self.staff_a1)
        sub_res = self.client.post(
            f"/api/employee-ops/tasks/{task.id}/submit/",
            {"body": "تسليم"},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        submission_id = sub_res.data["id"]

        self.client.force_authenticate(user=self.manager_a)
        # محاولة رفض بدون reviewer_notes
        res_fail = self.client.post(
            f"/api/employee-ops/submissions/{submission_id}/review/",
            {"decision": "rejected", "reviewer_notes": "   "},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res_fail.status_code, 400)
        self.assertIn("reviewer_notes", res_fail.data)

        sub = TaskSubmission.objects.get(pk=submission_id)
        self.assertEqual(sub.decision, TaskSubmission.DECISION_PENDING)

        # رفض مع سبب صحيح
        res_ok = self.client.post(
            f"/api/employee-ops/submissions/{submission_id}/review/",
            {"decision": "rejected", "reviewer_notes": "التقرير ناقص ويحتاج توثيق"},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res_ok.status_code, 200)
        sub.refresh_from_db()
        self.assertEqual(sub.decision, TaskSubmission.DECISION_REJECTED)
        self.assertEqual(sub.reviewer_notes, "التقرير ناقص ويحتاج توثيق")

    def test_resubmission_after_rejection_reuses_the_same_task(self):
        """تسليم ثان بعد الرفض: Task.objects.count لم يتغير، والتسليمان كلاهما محفوظ والأول مرفوض."""
        task = Task.objects.create(tenant=self.tenant_a, title="مهمة قابلة للإعادة")
        TaskAssignment.objects.create(tenant=self.tenant_a, task=task, employee=self.employee_a1)

        # التسليم الأول
        self.client.force_authenticate(user=self.staff_a1)
        res1 = self.client.post(
            f"/api/employee-ops/tasks/{task.id}/submit/",
            {"body": "التسليم الأول"},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        sub1_id = res1.data["id"]

        # المدير يرفض التسليم الأول
        self.client.force_authenticate(user=self.manager_a)
        self.client.post(
            f"/api/employee-ops/submissions/{sub1_id}/review/",
            {"decision": "rejected", "reviewer_notes": "يرجى تعديل البنود"},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )

        initial_tasks_count = Task.objects.filter(tenant=self.tenant_a).count()

        # تسليم ثان من نفس الموظف على نفس المهمة
        self.client.force_authenticate(user=self.staff_a1)
        res2 = self.client.post(
            f"/api/employee-ops/tasks/{task.id}/submit/",
            {"body": "التسليم الثاني بعد التعديل"},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res2.status_code, 201)
        sub2_id = res2.data["id"]

        self.assertEqual(Task.objects.filter(tenant=self.tenant_a).count(), initial_tasks_count)
        self.assertEqual(TaskSubmission.objects.filter(task=task).count(), 2)

        sub1 = TaskSubmission.objects.get(pk=sub1_id)
        sub2 = TaskSubmission.objects.get(pk=sub2_id)
        self.assertEqual(sub1.decision, TaskSubmission.DECISION_REJECTED)
        self.assertEqual(sub2.decision, TaskSubmission.DECISION_PENDING)

    def test_timer_start_is_idempotent_and_stop_accumulates(self):
        """start مرتين لا يضاعف، وstop بعدهما يضيف مرة واحدة."""
        task = Task.objects.create(tenant=self.tenant_a, title="مهمة المؤقت")
        assignment = TaskAssignment.objects.create(tenant=self.tenant_a, task=task, employee=self.employee_a1)

        self.client.force_authenticate(user=self.staff_a1)

        # البدء الأول
        res1 = self.client.post(
            f"/api/employee-ops/tasks/{task.id}/start/",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res1.status_code, 200)
        assignment.refresh_from_db()
        t0 = assignment.work_started_at
        self.assertIsNotNone(t0)

        # محاكاة مرور 60 ثانية بإرجاع work_started_at للماضي
        assignment.work_started_at = t0 - timedelta(seconds=60)
        assignment.save(update_fields=["work_started_at"])

        # البدء الثاني (idempotent: لا يمس work_started_at)
        res2 = self.client.post(
            f"/api/employee-ops/tasks/{task.id}/start/",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res2.status_code, 200)
        assignment.refresh_from_db()
        self.assertEqual(assignment.work_started_at, t0 - timedelta(seconds=60))

        # إيقاف المؤقت
        res_stop = self.client.post(
            f"/api/employee-ops/tasks/{task.id}/stop/",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res_stop.status_code, 200)
        assignment.refresh_from_db()
        self.assertIsNone(assignment.work_started_at)
        self.assertGreaterEqual(assignment.total_work_seconds, 60)
        self.assertLess(assignment.total_work_seconds, 70)

        # دورة ثانية: start ثم stop يراكم على الإجمالي السابق
        first_total = assignment.total_work_seconds
        assignment.work_started_at = timezone.now() - timedelta(seconds=30)
        assignment.save(update_fields=["work_started_at"])

        self.client.post(
            f"/api/employee-ops/tasks/{task.id}/stop/",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        assignment.refresh_from_db()
        self.assertGreaterEqual(assignment.total_work_seconds, first_total + 30)

    def test_more_than_five_attachments_is_refused(self):
        """6 مرفقات: 400 برسالة عربية، و5 تنجح."""
        task = Task.objects.create(tenant=self.tenant_a, title="مهمة المرفقات")
        TaskAssignment.objects.create(tenant=self.tenant_a, task=task, employee=self.employee_a1)

        self.client.force_authenticate(user=self.staff_a1)

        six_attachments = [
            {"url": f"https://example.com/file_{i}.pdf", "name": f"مرفق {i}"}
            for i in range(6)
        ]
        res_fail = self.client.post(
            f"/api/employee-ops/tasks/{task.id}/submit/",
            {"body": "تسليم بمرفقات كثيرة", "attachments": six_attachments},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res_fail.status_code, 400)
        self.assertIn("attachments", res_fail.data)
        self.assertIn("5", str(res_fail.data["attachments"]))
        self.assertFalse(TaskSubmission.objects.filter(task=task).exists())

        five_attachments = six_attachments[:5]
        res_ok = self.client.post(
            f"/api/employee-ops/tasks/{task.id}/submit/",
            {"body": "تسليم بـ 5 مرفقات", "attachments": five_attachments},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res_ok.status_code, 201)
        sub = TaskSubmission.objects.get(pk=res_ok.data["id"])
        self.assertEqual(sub.attachments.count(), 5)

    def test_submission_items_survive_a_round_trip(self):
        """بند برابط وسعر وملاحظة وصورتين يقرأ كما كتب."""
        task = Task.objects.create(tenant=self.tenant_a, title="مهمة بحث عن منتجات")
        TaskAssignment.objects.create(tenant=self.tenant_a, task=task, employee=self.employee_a1)

        self.client.force_authenticate(user=self.staff_a1)
        item_data = {
            "product_link": "https://example.com/item/123",
            "product_price": "249.50",
            "notes": "متوفر بلونين مع ضمان سنتين",
            "attachment_url": "https://example.com/spec.pdf",
            "attachment_name": "مواصفات.pdf",
            "images": [
                "https://example.com/img_a.jpg",
                "https://example.com/img_b.jpg",
            ],
        }

        res_submit = self.client.post(
            f"/api/employee-ops/tasks/{task.id}/submit/",
            {"body": "نتيجة البحث", "items": [item_data]},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res_submit.status_code, 201)
        sub_id = res_submit.data["id"]

        # قراءة التسليم عبر API
        res_get = self.client.get(
            f"/api/employee-ops/submissions/{sub_id}/",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res_get.status_code, 200)
        items = res_get.data["items"]
        self.assertEqual(len(items), 1)
        it = items[0]
        self.assertEqual(it["product_link"], "https://example.com/item/123")
        self.assertEqual(Decimal(str(it["product_price"])), Decimal("249.50"))
        self.assertEqual(it["notes"], "متوفر بلونين مع ضمان سنتين")
        self.assertEqual(it["attachment_url"], "https://example.com/spec.pdf")
        self.assertEqual(it["attachment_name"], "مواصفات.pdf")
        self.assertEqual(it["images"], ["https://example.com/img_a.jpg", "https://example.com/img_b.jpg"])

    def test_tenant_isolation_on_tasks_and_submissions(self):
        """مدير الشركة (أ) لا يرى ولا يراجع مهمة ولا تسليما في الشركة (ب) — 404 لا 403."""
        task_b = Task.objects.create(tenant=self.tenant_b, title="مهمة شركة ب")
        TaskAssignment.objects.create(tenant=self.tenant_b, task=task_b, employee=self.employee_b1)
        sub_b = TaskSubmission.objects.create(
            tenant=self.tenant_b,
            task=task_b,
            employee=self.employee_b1,
            body="تسليم في ب",
        )

        self.client.force_authenticate(user=self.manager_a)

        # فحص الوصول لمهمة شركة ب
        self.assertEqual(
            self.client.get(
                f"/api/employee-ops/tasks/{task_b.id}/",
                HTTP_X_TENANT_ID=str(self.tenant_a.pk),
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.patch(
                f"/api/employee-ops/tasks/{task_b.id}/",
                {"title": "محاولة تعديل"},
                format="json",
                HTTP_X_TENANT_ID=str(self.tenant_a.pk),
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.delete(
                f"/api/employee-ops/tasks/{task_b.id}/",
                HTTP_X_TENANT_ID=str(self.tenant_a.pk),
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/employee-ops/tasks/{task_b.id}/start/",
                HTTP_X_TENANT_ID=str(self.tenant_a.pk),
            ).status_code,
            404,
        )

        # فحص الوصول لتسليم شركة ب
        self.assertEqual(
            self.client.get(
                f"/api/employee-ops/submissions/{sub_b.id}/",
                HTTP_X_TENANT_ID=str(self.tenant_a.pk),
            ).status_code,
            404,
        )
        self.assertEqual(
            self.client.post(
                f"/api/employee-ops/submissions/{sub_b.id}/review/",
                {"decision": "approved_full"},
                format="json",
                HTTP_X_TENANT_ID=str(self.tenant_a.pk),
            ).status_code,
            404,
        )

    def test_assigning_an_employee_from_another_company_is_refused(self):
        """400، ولا مهمة تنشأ عند محاولة إسناد موظف من شركة أخرى."""
        self.client.force_authenticate(user=self.manager_a)
        res = self.client.post(
            "/api/employee-ops/tasks/",
            {
                "title": "مهمة إسناد عابر للشركات",
                "assignee_ids": [self.employee_b1.id],
            },
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res.status_code, 400)
        self.assertIn("assignee_ids", res.data)
        self.assertFalse(Task.objects.filter(title="مهمة إسناد عابر للشركات").exists())

    def test_narrow_role_sees_only_its_own_submissions(self):
        """حامل self يقرأ GET /submissions/ فيرى تسليماته وحدها، ولا يرى تسليم زميله."""
        task = Task.objects.create(tenant=self.tenant_a, title="مهمة مشتركة")
        TaskAssignment.objects.create(tenant=self.tenant_a, task=task, employee=self.employee_a1)
        TaskAssignment.objects.create(tenant=self.tenant_a, task=task, employee=self.employee_a2)

        sub1 = TaskSubmission.objects.create(
            tenant=self.tenant_a, task=task, employee=self.employee_a1, body="تسليم أ1"
        )
        sub2 = TaskSubmission.objects.create(
            tenant=self.tenant_a, task=task, employee=self.employee_a2, body="تسليم أ2"
        )

        self.client.force_authenticate(user=self.staff_a1)
        res = self.client.get(
            "/api/employee-ops/submissions/",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res.status_code, 200)
        returned_ids = [s["id"] for s in res.data]
        self.assertIn(sub1.id, returned_ids)
        self.assertNotIn(sub2.id, returned_ids)

        # بينما المدير يرى الطابور كاملاً
        self.client.force_authenticate(user=self.manager_a)
        res_mgr = self.client.get(
            "/api/employee-ops/submissions/",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res_mgr.status_code, 200)
        all_ids = [s["id"] for s in res_mgr.data]
        self.assertIn(sub1.id, all_ids)
        self.assertIn(sub2.id, all_ids)

    def test_narrow_role_cannot_review(self):
        """POST /submissions/{id}/review/ بـ self = 403."""
        task = Task.objects.create(tenant=self.tenant_a, title="مهمة للمراجعة")
        TaskAssignment.objects.create(tenant=self.tenant_a, task=task, employee=self.employee_a1)
        sub = TaskSubmission.objects.create(
            tenant=self.tenant_a, task=task, employee=self.employee_a1, body="تسليم"
        )

        self.client.force_authenticate(user=self.staff_a1)
        res = self.client.post(
            f"/api/employee-ops/submissions/{sub.id}/review/",
            {"decision": "approved_full", "reviewer_notes": "محاولة مراجعة لنفسي"},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res.status_code, 403)
        sub.refresh_from_db()
        self.assertEqual(sub.decision, TaskSubmission.DECISION_PENDING)

    def test_every_task_endpoint_is_404_when_the_module_is_disabled(self):
        """كلُّ نقطةٍ تختفي بإطفاء الوحدة — **بمعرّفاتٍ موجودةٍ فعلاً**.

        بمعرّفٍ وهميّ (`999`) يأتي الـ404 من `get_object_or_404` سواءٌ حرس
        `require_module` أم لم يحرس، فيمرّ الاختبارُ أخضر ولو نُزع الحارس. المهمّةُ
        والتسليمُ هنا موجودان في **نفس** الشركة المُطفأة، فلا مصدرَ للـ404 إلا البوّابة.
        """
        mgr_off = User.objects.create_user(username="mgr_off", password="x")
        tenant_off = create_company("شركة الوحدة المعطلة", mgr_off)
        emp_off = Employee.objects.create(
            tenant=tenant_off, user=mgr_off, name="موظف معطل", code="901", is_active=True
        )
        task_off = Task.objects.create(tenant=tenant_off, title="مهمة قائمة", status=Task.STATUS_NEW)
        TaskAssignment.objects.create(tenant=tenant_off, task=task_off, employee=emp_off)
        sub_off = TaskSubmission.objects.create(
            tenant=tenant_off, task=task_off, employee=emp_off, body="تسليم قائم",
        )
        invalidate_module_cache(tenant_off.pk)

        self.client.force_authenticate(user=mgr_off)
        headers = {"HTTP_X_TENANT_ID": str(tenant_off.pk)}

        endpoints = [
            ("get", "/api/employee-ops/tasks/"),
            ("post", "/api/employee-ops/tasks/"),
            ("get", "/api/employee-ops/tasks/mine/"),
            ("get", f"/api/employee-ops/tasks/{task_off.id}/"),
            ("patch", f"/api/employee-ops/tasks/{task_off.id}/"),
            ("delete", f"/api/employee-ops/tasks/{task_off.id}/"),
            ("post", f"/api/employee-ops/tasks/{task_off.id}/start/"),
            ("post", f"/api/employee-ops/tasks/{task_off.id}/stop/"),
            ("post", f"/api/employee-ops/tasks/{task_off.id}/submit/"),
            ("get", "/api/employee-ops/submissions/"),
            ("get", f"/api/employee-ops/submissions/{sub_off.id}/"),
            ("post", f"/api/employee-ops/submissions/{sub_off.id}/review/"),
        ]

        for method, url in endpoints:
            with self.subTest(method=method, url=url):
                func = getattr(self.client, method)
                res = func(url, **headers)
                self.assertEqual(
                    res.status_code,
                    404,
                    f"النقطة {method.upper()} {url} لم ترد بـ 404 عند تعطيل الوحدة (ردت بـ {res.status_code})",
                )

    def test_task_list_query_count_does_not_grow_with_rows(self):
        """assertNumQueries ثابت عند 3 مهام وعند 12 مهمة."""
        tenant_perf = create_company("شركة قياس الاستعلامات", self.manager_a)
        TenantModule.objects.create(tenant=tenant_perf, module_key="employee_ops", enabled=True)
        invalidate_module_cache(tenant_perf.pk)

        emp1 = Employee.objects.create(tenant=tenant_perf, name="موظف 1", code="301", is_active=True)
        emp2 = Employee.objects.create(tenant=tenant_perf, name="موظف 2", code="302", is_active=True)

        # إنشاء 3 مهام بإسناداتها
        for i in range(3):
            t = Task.objects.create(
                tenant=tenant_perf, title=f"مهمة {i}", created_by=self.manager_a
            )
            TaskAssignment.objects.create(tenant=tenant_perf, task=t, employee=emp1)
            TaskAssignment.objects.create(tenant=tenant_perf, task=t, employee=emp2)

        self.client.force_authenticate(user=self.manager_a)

        # تسخين أي جلسة أو إذن مؤقت
        warmup = self.client.get("/api/employee-ops/tasks/", HTTP_X_TENANT_ID=str(tenant_perf.pk))
        self.assertEqual(warmup.status_code, 200)

        with CaptureQueriesContext(connection) as ctx_3:
            res3 = self.client.get("/api/employee-ops/tasks/", HTTP_X_TENANT_ID=str(tenant_perf.pk))
        self.assertEqual(res3.status_code, 200)
        queries_3 = len(ctx_3)

        # إضافة 9 مهام أخرى ليصبح المجموع 12
        for i in range(3, 12):
            t = Task.objects.create(
                tenant=tenant_perf, title=f"مهمة {i}", created_by=self.manager_a
            )
            TaskAssignment.objects.create(tenant=tenant_perf, task=t, employee=emp1)
            TaskAssignment.objects.create(tenant=tenant_perf, task=t, employee=emp2)

        with self.assertNumQueries(queries_3):
            res12 = self.client.get("/api/employee-ops/tasks/", HTTP_X_TENANT_ID=str(tenant_perf.pk))
        self.assertEqual(res12.status_code, 200)
        self.assertEqual(len(res12.data), 12)

    # ── حرّاسُ دورة الحياة: خمسةُ أبوابٍ كانت مفتوحةً في التسليم الأوّل ──────────

    def _task_with_one_assignee(self, title="مهمة حارس"):
        task = Task.objects.create(tenant=self.tenant_a, title=title, status=Task.STATUS_NEW)
        TaskAssignment.objects.create(tenant=self.tenant_a, task=task, employee=self.employee_a1)
        return task

    def _submit_as_a1(self, task, body="عملٌ منجَز"):
        self.client.force_authenticate(user=self.staff_a1)
        return self.client.post(
            f"/api/employee-ops/tasks/{task.id}/submit/",
            {"body": body},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )

    def _review(self, submission_id, decision, notes=""):
        self.client.force_authenticate(user=self.manager_a)
        return self.client.post(
            f"/api/employee-ops/submissions/{submission_id}/review/",
            {"decision": decision, "reviewer_notes": notes},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )

    def test_a_submission_is_reviewed_once_and_only_once(self):
        """قرارُ المراجعة نهائيّ — لا يُقلَب على نفس التسليم.

        بدون هذا الحارس يمنح محرّكُ النقاط (المرحلة التالية) على **كلّ** قرار،
        فتُمنح النقطةُ مرّتين لعملٍ واحد. وإلغاءُ القبول له مسارُه: قيدٌ مضادّ.
        """
        task = self._task_with_one_assignee()
        sub_id = self._submit_as_a1(task).data["id"]

        self.assertEqual(self._review(sub_id, "approved_full").status_code, 200)
        second = self._review(sub_id, "rejected", "غيّرتُ رأيي")
        self.assertEqual(second.status_code, 400)

        submission = TaskSubmission.objects.get(pk=sub_id)
        self.assertEqual(submission.decision, TaskSubmission.DECISION_APPROVED_FULL)
        self.assertEqual(submission.reviewer_notes, "")

    def test_no_second_submission_while_the_first_awaits_review(self):
        """طابورٌ فيه تسليمان لعملٍ واحد يجعل المدير يراجع ما استُبدل."""
        task = self._task_with_one_assignee()
        self.assertEqual(self._submit_as_a1(task).status_code, 201)
        again = self._submit_as_a1(task, "تسليمٌ ثانٍ")
        self.assertEqual(again.status_code, 400)
        self.assertEqual(TaskSubmission.objects.filter(task=task).count(), 1)

    def test_no_submission_after_approval_but_resubmission_after_rejection(self):
        """إعادةُ التسليم بعد **الرفض** مقصودة؛ وبعد القبول ممنوعة."""
        task = self._task_with_one_assignee()
        sub_id = self._submit_as_a1(task).data["id"]
        self.assertEqual(self._review(sub_id, "rejected", "ناقص").status_code, 200)

        retry = self._submit_as_a1(task, "أصلحتُ الملاحظات")
        self.assertEqual(retry.status_code, 201)
        self.assertEqual(TaskSubmission.objects.filter(task=task).count(), 2)

        self.assertEqual(self._review(retry.data["id"], "approved_full").status_code, 200)
        after_approval = self._submit_as_a1(task, "تسليمٌ بعد القبول")
        self.assertEqual(after_approval.status_code, 400)
        self.assertEqual(TaskSubmission.objects.filter(task=task).count(), 2)

    def test_timer_cannot_reopen_a_completed_assignment(self):
        """مؤقّتٌ يُشغَّل على إسنادٍ قُبِل يُعيده «قيد التنفيذ» فيكذب على لوحة المدير."""
        task = self._task_with_one_assignee()
        sub_id = self._submit_as_a1(task).data["id"]
        self.assertEqual(self._review(sub_id, "approved_full").status_code, 200)

        self.client.force_authenticate(user=self.staff_a1)
        res = self.client.post(
            f"/api/employee-ops/tasks/{task.id}/start/",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res.status_code, 400)
        self.assertEqual(
            TaskAssignment.objects.get(task=task, employee=self.employee_a1).status,
            TaskAssignment.STATUS_COMPLETED,
        )

    def test_an_assignee_who_submitted_cannot_be_removed_from_the_task(self):
        """نزعُه يحذف صفَّ حالته ويترك تسليماتِه معلّقةً على مهمّةٍ ليست له — عملٌ يختفي."""
        task = self._task_with_one_assignee()
        self._submit_as_a1(task)

        self.client.force_authenticate(user=self.manager_a)
        res = self.client.patch(
            f"/api/employee-ops/tasks/{task.id}/",
            {"assignee_ids": [self.employee_a2.id]},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res.status_code, 400)
        self.assertTrue(
            TaskAssignment.objects.filter(task=task, employee=self.employee_a1).exists()
        )

    def test_a_task_with_submissions_cannot_be_deleted(self):
        """الحذفُ يمحو عملَ الموظف ومراجعةَ المدير معاً — والمهمّةُ الفارغةُ تُحذف."""
        empty = Task.objects.create(tenant=self.tenant_a, title="فارغة", status=Task.STATUS_NEW)
        task = self._task_with_one_assignee("لها تسليم")
        self._submit_as_a1(task)

        self.client.force_authenticate(user=self.manager_a)
        headers = {"HTTP_X_TENANT_ID": str(self.tenant_a.pk)}
        self.assertEqual(
            self.client.delete(f"/api/employee-ops/tasks/{task.id}/", **headers).status_code, 400
        )
        self.assertTrue(Task.objects.filter(pk=task.pk).exists())
        self.assertEqual(
            self.client.delete(f"/api/employee-ops/tasks/{empty.id}/", **headers).status_code, 204
        )
        self.assertFalse(Task.objects.filter(pk=empty.pk).exists())

    def test_task_is_rejected_only_when_every_assignee_is_rejected(self):
        """`REJECTED` كانت حالةً معلَنةً لا يبلغها شيء — فالمرفوضةُ تُعرض «قيد التنفيذ»."""
        task = Task.objects.create(tenant=self.tenant_a, title="مهمة سترفض", status=Task.STATUS_NEW)
        TaskAssignment.objects.create(tenant=self.tenant_a, task=task, employee=self.employee_a1)
        TaskAssignment.objects.create(tenant=self.tenant_a, task=task, employee=self.employee_a2)

        sub1 = self._submit_as_a1(task).data["id"]
        self.assertEqual(self._review(sub1, "rejected", "ناقص").status_code, 200)
        task.refresh_from_db()
        self.assertEqual(
            task.status, Task.STATUS_IN_PROGRESS,
            "رُفض واحدٌ من اثنين فصارت المهمّة مرفوضة — الرفضُ الجزئيّ ليس رفضاً.",
        )

        self.client.force_authenticate(user=self.staff_a2)
        sub2 = self.client.post(
            f"/api/employee-ops/tasks/{task.id}/submit/",
            {"body": "تسليم الثاني"},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        ).data["id"]
        self.assertEqual(self._review(sub2, "rejected", "ناقص كذلك").status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.status, Task.STATUS_REJECTED)
        self.assertIsNone(task.completed_at)

        # وإعادةُ التسليم تُخرجها من الرفض تلقائياً — الاشتقاق لا حالةٌ محفوظة.
        self._submit_as_a1(task, "أصلحتُ")
        task.refresh_from_db()
        self.assertEqual(task.status, Task.STATUS_WAITING_FOR_REVIEW)

    def test_completed_at_never_survives_a_return_to_the_queue(self):
        """صفٌّ «بانتظار المراجعة» يحمل تاريخَ اكتمالٍ رقمٌ يكذب على كلّ قارئ."""
        task = self._task_with_one_assignee("مهمة تعود للطابور")
        sub_id = self._submit_as_a1(task).data["id"]
        self.assertEqual(self._review(sub_id, "approved_full").status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.status, Task.STATUS_COMPLETED)
        self.assertIsNotNone(task.completed_at)

        # مُسنَدٌ جديدٌ يُضاف ⇒ لم تعد مكتملة، ولا يجوز أن يبقى تاريخُ الاكتمال.
        self.client.force_authenticate(user=self.manager_a)
        res = self.client.patch(
            f"/api/employee-ops/tasks/{task.id}/",
            {"assignee_ids": [self.employee_a1.id, self.employee_a2.id]},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant_a.pk),
        )
        self.assertEqual(res.status_code, 200)
        task.refresh_from_db()
        self.assertEqual(task.status, Task.STATUS_IN_PROGRESS)
        self.assertIsNone(task.completed_at)

    def test_an_assignee_opens_their_own_task_and_no_other(self):
        """الموظفُ كان يرى `mine` ولا يستطيع فتح بندٍ منها — و٤٠٤ لا ٤٠٣ لمهمّةٍ ليست له."""
        mine = self._task_with_one_assignee("مهمّتي")
        other = Task.objects.create(tenant=self.tenant_a, title="مهمّة غيري", status=Task.STATUS_NEW)
        TaskAssignment.objects.create(tenant=self.tenant_a, task=other, employee=self.employee_a2)

        self.client.force_authenticate(user=self.staff_a1)
        headers = {"HTTP_X_TENANT_ID": str(self.tenant_a.pk)}
        ok = self.client.get(f"/api/employee-ops/tasks/{mine.id}/", **headers)
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.data["id"], mine.id)
        self.assertIsNotNone(ok.data["my_assignment"])

        self.assertEqual(
            self.client.get(f"/api/employee-ops/tasks/{other.id}/", **headers).status_code, 404
        )

    def test_submission_payload_size_is_capped_beyond_attachments(self):
        """سقفُ المرفقات وحده كان يُلتفّ عليه بالبنود وصورِها."""
        task = self._task_with_one_assignee("مهمة الحمولة")
        self.client.force_authenticate(user=self.staff_a1)
        headers = {"HTTP_X_TENANT_ID": str(self.tenant_a.pk)}

        too_many_images = self.client.post(
            f"/api/employee-ops/tasks/{task.id}/submit/",
            {"items": [{"images": [f"https://x/{i}.jpg" for i in range(6)]}]},
            format="json", **headers,
        )
        self.assertEqual(too_many_images.status_code, 400)

        too_many_items = self.client.post(
            f"/api/employee-ops/tasks/{task.id}/submit/",
            {"items": [{"product_link": f"https://x/{i}"} for i in range(51)]},
            format="json", **headers,
        )
        self.assertEqual(too_many_items.status_code, 400)

        bad_url = self.client.post(
            f"/api/employee-ops/tasks/{task.id}/submit/",
            {"attachments": [{"url": "ليس رابطاً"}]},
            format="json", **headers,
        )
        self.assertEqual(bad_url.status_code, 400)
        self.assertFalse(TaskSubmission.objects.filter(task=task).exists())
