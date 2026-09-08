"""محرّك النقاط ولوحة الشرف (المرحلة ٤).

**لماذا سجلٌّ لا صفٌّ يوميّ:** النظامُ الحيّ كان يحفظ صفّاً واحداً لكلّ (موظف، يوم)
يُعاد كتابتُه، فسؤالُ «من أين جاءت هذه النقطة؟» بلا جواب. وهنا قيدٌ لكلّ حدثٍ
بمصدره وتاريخه — والمجموعُ تجميعٌ فوقه لا رقمٌ محفوظٌ بجانبه.
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import IntegrityError, connection, transaction
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from core.access import FIELD_STAFF_ROLE
from core.models import TenantModule
from core.modules import invalidate_module_cache
from employee_ops.models import (
    EmployeeOpsSettings,
    PointEntry,
    Task,
    TaskAssignment,
    TaskSubmission,
)
from hr.models import Employee
from tenants.models import Currency, UserCompanyMembership
from tenants.services import create_company


class EmployeeOpsPointsTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True}
        )
        cls.manager_a = User.objects.create_user(username="pts_mgr_a", password="x")
        cls.manager_b = User.objects.create_user(username="pts_mgr_b", password="x")
        cls.tenant_a = create_company("شركة النقاط أ", cls.manager_a)
        cls.tenant_b = create_company("شركة النقاط ب", cls.manager_b)
        for tenant in (cls.tenant_a, cls.tenant_b):
            TenantModule.objects.create(
                tenant=tenant, module_key="employee_ops", enabled=True
            )
            invalidate_module_cache(tenant.pk)

        cls.staff1 = User.objects.create_user(username="pts_staff1", password="x")
        cls.staff2 = User.objects.create_user(username="pts_staff2", password="x")
        UserCompanyMembership.objects.create(
            user=cls.staff1, tenant=cls.tenant_a, role=FIELD_STAFF_ROLE
        )
        UserCompanyMembership.objects.create(
            user=cls.staff2, tenant=cls.tenant_a, role=FIELD_STAFF_ROLE
        )
        cls.emp1 = Employee.objects.create(
            tenant=cls.tenant_a, user=cls.staff1, name="موظف نقاط ١", code="501"
        )
        cls.emp2 = Employee.objects.create(
            tenant=cls.tenant_a, user=cls.staff2, name="موظف نقاط ٢", code="502"
        )
        cls.emp_b = Employee.objects.create(
            tenant=cls.tenant_b, name="موظف شركة ب", code="601"
        )

    # ── أدوات ────────────────────────────────────────────────────────────────

    def _headers(self, tenant=None):
        return {"HTTP_X_TENANT_ID": str((tenant or self.tenant_a).pk)}

    def _task_for(self, employee, title="مهمة نقاط"):
        task = Task.objects.create(
            tenant=employee.tenant, title=title, status=Task.STATUS_NEW
        )
        TaskAssignment.objects.create(
            tenant=employee.tenant, task=task, employee=employee
        )
        return task

    def _submit(self, task, user):
        self.client.force_authenticate(user=user)
        res = self.client.post(
            f"/api/employee-ops/tasks/{task.id}/submit/",
            {"body": "أنجزتُ"},
            format="json",
            **self._headers(task.tenant),
        )
        self.assertEqual(res.status_code, 201, res.data)
        return res.data["id"]

    def _review(self, submission_id, decision, notes="", tenant=None, user=None):
        self.client.force_authenticate(user=user or self.manager_a)
        return self.client.post(
            f"/api/employee-ops/submissions/{submission_id}/review/",
            {"decision": decision, "reviewer_notes": notes},
            format="json",
            **self._headers(tenant),
        )

    def _approve_flow(self, employee, user, decision="approved_full", title="مهمة"):
        task = self._task_for(employee, title)
        sub_id = self._submit(task, user)
        self.assertEqual(self._review(sub_id, decision, "تمام").status_code, 200)
        return task, sub_id

    # ── القرار يمنح النقطة ───────────────────────────────────────────────────

    def test_each_decision_grants_its_configured_points(self):
        """كامل ⇒ ١٠ · جزئيّ ⇒ ٥ · ورفضٌ ⇒ **لا صفَّ قيدٍ أصلاً** (لا صفٌّ بصفر)."""
        self._approve_flow(self.emp1, self.staff1, "approved_full", "كاملة")
        full = PointEntry.objects.get(employee=self.emp1)
        self.assertEqual(full.points, 10)
        self.assertEqual(full.source, PointEntry.SOURCE_TASK_FULL)

        self._approve_flow(self.emp2, self.staff2, "approved_partial", "جزئية")
        partial = PointEntry.objects.get(employee=self.emp2)
        self.assertEqual(partial.points, 5)
        self.assertEqual(partial.source, PointEntry.SOURCE_TASK_PARTIAL)

        task = self._task_for(self.emp1, "مرفوضة")
        sub_id = self._submit(task, self.staff1)
        self.assertEqual(self._review(sub_id, "rejected", "ناقص").status_code, 200)
        self.assertFalse(
            PointEntry.objects.filter(submission_id=sub_id).exists(),
            "الرفضُ أنشأ قيداً — والصفرُ لا صفَّ له.",
        )

    def test_points_use_the_company_settings_not_the_defaults(self):
        settings_obj = EmployeeOpsSettings.objects.create(
            tenant=self.tenant_a, points_full=20, points_partial=7
        )
        self.assertEqual(settings_obj.points_full, 20)
        self._approve_flow(self.emp1, self.staff1, "approved_full")
        self.assertEqual(PointEntry.objects.get(employee=self.emp1).points, 20)

    def test_point_is_dated_on_the_approval_day_not_the_submission_day(self):
        """تسليمُ أمسٍ وقبولُ اليوم يقع في **يوم اليوم** — الماضي لا يتبدّل."""
        task = self._task_for(self.emp1)
        sub_id = self._submit(task, self.staff1)
        yesterday = timezone.now() - timedelta(days=1)
        TaskSubmission.objects.filter(pk=sub_id).update(created_at=yesterday)

        self.assertEqual(self._review(sub_id, "approved_full", "ok").status_code, 200)
        entry = PointEntry.objects.get(submission_id=sub_id)
        self.assertEqual(entry.awarded_on, timezone.localdate())

    def test_changing_the_settings_does_not_rewrite_past_entries(self):
        """القيمةُ تُنسخ لحظةَ المنح — رفعُ الإعداد لا يُعيد كتابة الماضي."""
        self._approve_flow(self.emp1, self.staff1, "approved_full", "قبل الرفع")
        before = PointEntry.objects.get(employee=self.emp1)
        self.assertEqual(before.points, 10)

        self.client.force_authenticate(user=self.manager_a)
        self.assertEqual(
            self.client.patch(
                "/api/employee-ops/settings/",
                {"points_full": 20},
                format="json",
                **self._headers(),
            ).status_code,
            200,
        )
        before.refresh_from_db()
        self.assertEqual(before.points, 10)

        self._approve_flow(self.emp1, self.staff1, "approved_full", "بعد الرفع")
        self.assertEqual(
            sorted(PointEntry.objects.filter(employee=self.emp1).values_list("points", flat=True)),
            [10, 20],
        )

    # ── الإلغاء قيدٌ مضادّ لا حذف ────────────────────────────────────────────

    def _unreview(self, submission_id, reason="أخطأتُ"):
        self.client.force_authenticate(user=self.manager_a)
        return self.client.post(
            f"/api/employee-ops/submissions/{submission_id}/unreview/",
            {"reason": reason},
            format="json",
            **self._headers(),
        )

    def test_unreview_creates_a_counter_entry_and_keeps_the_original(self):
        """الأصليُّ يبقى بقيمته وتاريخه، والمضادُّ سالبٌ بتاريخ **الإلغاء**، والمجموع صفر."""
        _, sub_id = self._approve_flow(self.emp1, self.staff1)
        original = PointEntry.objects.get(submission_id=sub_id)
        old_date = timezone.localdate() - timedelta(days=3)
        PointEntry.objects.filter(pk=original.pk).update(awarded_on=old_date)

        self.assertEqual(self._unreview(sub_id).status_code, 200)

        original.refresh_from_db()
        self.assertEqual(original.points, 10)
        self.assertEqual(original.awarded_on, old_date, "الأصليُّ أُعيدت كتابتُه.")

        reversal = PointEntry.objects.get(source=PointEntry.SOURCE_REVERSAL)
        self.assertEqual(reversal.points, -10)
        self.assertEqual(reversal.awarded_on, timezone.localdate())
        self.assertEqual(reversal.reverses_id, original.pk)
        self.assertEqual(
            sum(PointEntry.objects.filter(employee=self.emp1).values_list("points", flat=True)),
            0,
        )

    def test_unreview_returns_the_submission_to_the_queue_and_allows_a_new_decision(self):
        _, sub_id = self._approve_flow(self.emp1, self.staff1)
        self.assertEqual(self._unreview(sub_id).status_code, 200)

        submission = TaskSubmission.objects.get(pk=sub_id)
        self.assertEqual(submission.decision, TaskSubmission.DECISION_PENDING)
        # **شاهدُ القرار الملغى يبقى**: من قبِل ومتى وبأيّ ملاحظة. تصفيرُها كان
        # يمحو الماضي — وهو نقيضُ السبب الذي وُجد القيدُ المضادّ لأجله.
        self.assertEqual(submission.reviewer_id, self.manager_a.pk)
        self.assertIsNotNone(submission.reviewed_at)
        self.assertEqual(
            TaskAssignment.objects.get(task=submission.task, employee=self.emp1).status,
            TaskAssignment.STATUS_SUBMITTED,
        )

        self.assertEqual(self._review(sub_id, "approved_partial", "أعدتُ").status_code, 200)
        self.assertEqual(PointEntry.objects.filter(employee=self.emp1).count(), 3)
        self.assertEqual(
            sum(PointEntry.objects.filter(employee=self.emp1).values_list("points", flat=True)),
            5,
        )

    def test_unreview_requires_a_written_reason(self):
        _, sub_id = self._approve_flow(self.emp1, self.staff1)
        before = PointEntry.objects.count()
        self.assertEqual(self._unreview(sub_id, reason="").status_code, 400)
        self.assertEqual(PointEntry.objects.count(), before)
        self.assertEqual(
            TaskSubmission.objects.get(pk=sub_id).decision,
            TaskSubmission.DECISION_APPROVED_FULL,
        )

    def test_unreview_cannot_run_twice_on_one_decision(self):
        """الإلغاءُ مرّةً واحدة لكلّ قرار — وإلا صار زرّاً يقلب المجموع ذهاباً وإياباً.

        (والحارسُ هو أنّ التسليم عاد `pending`؛ فلا قرارَ ليُلغى.)"""
        _, sub_id = self._approve_flow(self.emp1, self.staff1)
        self.assertEqual(self._unreview(sub_id).status_code, 200)
        second = self._unreview(sub_id, "مرّةً أخرى")
        self.assertEqual(second.status_code, 400)
        self.assertEqual(
            PointEntry.objects.filter(source=PointEntry.SOURCE_REVERSAL).count(), 1
        )

    # ── زرّ الحضور ───────────────────────────────────────────────────────────

    def _check_in(self, user=None):
        self.client.force_authenticate(user=user or self.staff1)
        return self.client.post(
            "/api/employee-ops/attendance/check-in/", **self._headers()
        )

    def test_attendance_gives_one_point_and_blocks_a_click_within_a_minute(self):
        first = self._check_in()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.data["points_awarded"], 1)

        second = self._check_in()
        self.assertEqual(second.status_code, 400)
        self.assertEqual(
            PointEntry.objects.filter(source=PointEntry.SOURCE_ATTENDANCE).count(),
            1,
            "الضغطةُ المرفوضة أنشأت صفّاً.",
        )

    def test_attendance_daily_cap_is_five_and_the_sixth_click_earns_zero(self):
        """يومٌ كاملٌ من الضغط لا يبلغ نصفَ مهمّةٍ مقبولة — وهو كلُّ غرض السقف."""
        for i in range(5):
            res = self._check_in()
            self.assertEqual(res.status_code, 200, res.data)
            self.assertEqual(res.data["points_awarded"], 1)
            # تجاوزُ حارس الدقيقة: نُقدّم آخرَ ضغطةٍ إلى الوراء بدل الانتظار.
            PointEntry.objects.filter(source=PointEntry.SOURCE_ATTENDANCE).update(
                created_at=timezone.now() - timedelta(minutes=5)
            )

        sixth = self._check_in()
        self.assertEqual(sixth.status_code, 200)
        self.assertEqual(sixth.data["points_awarded"], 0)
        self.assertEqual(sixth.data["today_points"], 5)
        self.assertTrue(sixth.data["capped"])
        self.assertEqual(
            PointEntry.objects.filter(
                source=PointEntry.SOURCE_ATTENDANCE, employee=self.emp1
            ).count(),
            6,
            "الضغطةُ السادسة لم تُسجَّل — «ضغط ولم يكسب» يجب أن يبقى مقروءاً.",
        )
        self.assertEqual(
            sum(
                PointEntry.objects.filter(
                    source=PointEntry.SOURCE_ATTENDANCE, employee=self.emp1
                ).values_list("points", flat=True)
            ),
            5,
        )

    # ── فخّ `hr.PointsHistory` ───────────────────────────────────────────────

    def test_two_companies_of_the_same_user_keep_separate_ledgers(self):
        """نفسُ المستخدم في شركتين وقيدان في نفس اليوم — لا تصادمَ ولا خلط.

        فخُّ `hr.PointsHistory`: فرادةٌ على `(user, date)` **بلا شركة**، فمن يعمل
        في شركتين يتصادم سجلُّه. وهنا **لا فرادةَ يوميّةً أصلاً** — السجلُّ دفترٌ
        يقبل قيوداً كثيرةً في اليوم — وكلُّ استعلامٍ مُنطاقٌ بالشركة.
        """
        UserCompanyMembership.objects.create(
            user=self.staff1, tenant=self.tenant_b, role=FIELD_STAFF_ROLE
        )
        emp_b_same_user = Employee.objects.create(
            tenant=self.tenant_b, user=self.staff1, name="نفسُه في ب", code="602"
        )
        today = timezone.localdate()
        for tenant, employee, pts in (
            (self.tenant_a, self.emp1, 3),
            (self.tenant_a, self.emp1, 4),   # قيدان في نفس اليوم لنفس الموظف
            (self.tenant_b, emp_b_same_user, 8),
        ):
            PointEntry.objects.create(
                tenant=tenant, employee=employee, points=pts,
                source=PointEntry.SOURCE_MANUAL, awarded_on=today, reason="قيد",
            )
        self.assertEqual(
            sum(PointEntry.objects.filter(tenant=self.tenant_a).values_list("points", flat=True)), 7
        )
        self.assertEqual(
            sum(PointEntry.objects.filter(tenant=self.tenant_b).values_list("points", flat=True)), 8
        )

    def test_migration_source_path_is_unique_within_a_company_not_across(self):
        """قيدُ `(tenant, source_path)` حيٌّ لا زينة — تُثبته الهجرةُ في المرحلة ٧.

        شركتان تستوردان وثيقةً بنفس المسار: تمرّان. والاستيرادُ مرّتين في الشركة
        نفسِها: يُردّ — وهو ما يجعل إعادةَ تشغيل الهجرة آمنة.
        """
        today = timezone.localdate()

        def _entry(tenant, employee, path):
            return PointEntry.objects.create(
                tenant=tenant, employee=employee, points=1,
                source=PointEntry.SOURCE_MANUAL, awarded_on=today,
                reason="مهاجَر", source_path=path,
            )

        _entry(self.tenant_a, self.emp1, "pointsHistory/u1/days/2026-09-01")
        _entry(self.tenant_b, self.emp_b, "pointsHistory/u1/days/2026-09-01")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _entry(self.tenant_a, self.emp2, "pointsHistory/u1/days/2026-09-01")

    # ── النقاط اليدويّة ──────────────────────────────────────────────────────

    def _manual(self, payload):
        self.client.force_authenticate(user=self.manager_a)
        return self.client.post(
            "/api/employee-ops/points/manual/", payload, format="json", **self._headers()
        )

    def test_manual_points_require_a_reason_and_accept_a_negative_value(self):
        no_reason = self._manual({"employee": self.emp1.id, "points": 5})
        self.assertEqual(no_reason.status_code, 400)
        self.assertFalse(PointEntry.objects.filter(source=PointEntry.SOURCE_MANUAL).exists())

        negative = self._manual(
            {"employee": self.emp1.id, "points": -4, "reason": "تصحيحُ خطأ"}
        )
        self.assertEqual(negative.status_code, 201)
        self.assertEqual(PointEntry.objects.get(source=PointEntry.SOURCE_MANUAL).points, -4)

    def test_manual_points_for_an_employee_of_another_company_are_refused(self):
        res = self._manual({"employee": self.emp_b.id, "points": 5, "reason": "محاولة"})
        self.assertEqual(res.status_code, 400)
        self.assertFalse(PointEntry.objects.filter(employee=self.emp_b).exists())

    # ── لوحة الشرف ───────────────────────────────────────────────────────────

    def _leaderboard(self, user=None, month=None):
        self.client.force_authenticate(user=user or self.staff1)
        url = "/api/employee-ops/leaderboard/"
        if month:
            url += f"?month={month}"
        return self.client.get(url, **self._headers())

    def test_leaderboard_is_monthly_and_returns_everyone_including_zeros(self):
        self._approve_flow(self.emp1, self.staff1, "approved_full")
        last_month = (timezone.localdate().replace(day=1) - timedelta(days=1))
        PointEntry.objects.create(
            tenant=self.tenant_a, employee=self.emp2, points=99,
            source=PointEntry.SOURCE_MANUAL, awarded_on=last_month, reason="شهرٌ ماضٍ",
        )

        res = self._leaderboard()
        self.assertEqual(res.status_code, 200)
        rows = {r["employee"]: r for r in res.data["results"]}
        self.assertEqual(rows[self.emp1.id]["points"], 10)
        self.assertEqual(
            rows[self.emp2.id]["points"], 0,
            "نقاطُ شهرٍ ماضٍ سرَّبت نفسها إلى لوحة هذا الشهر.",
        )
        self.assertEqual(res.data["highlight_count"], 5)
        self.assertEqual(res.data["month"], timezone.localdate().strftime("%Y-%m"))

        past = self._leaderboard(month=last_month.strftime("%Y-%m"))
        past_rows = {r["employee"]: r["points"] for r in past.data["results"]}
        self.assertEqual(past_rows[self.emp2.id], 99)

    def test_leaderboard_ties_share_a_rank(self):
        today = timezone.localdate()
        for emp in (self.emp1, self.emp2):
            PointEntry.objects.create(
                tenant=self.tenant_a, employee=emp, points=7,
                source=PointEntry.SOURCE_MANUAL, awarded_on=today, reason="تعادل",
            )
        rows = self._leaderboard().data["results"]
        self.assertEqual([r["rank"] for r in rows[:2]], [1, 1])

    def test_leaderboard_is_one_query_regardless_of_employee_count(self):
        """سقفٌ **مطلق** مع ثبات: كلٌّ وحده يمرّ بما لا يجوز.

        الثباتُ بلا سقفٍ يمرّ بخمسين استعلاماً ما دامت خمسين في الحالتين؛ والسقفُ
        بلا ثباتٍ يمرّ على عيّنةٍ صغيرة. واللوحةُ نفسُها استعلامٌ واحد — والباقي
        مصادقةٌ وصلاحيّاتٌ لا تنمو مع الصفوف.
        """
        self.client.force_authenticate(user=self.staff1)
        url = "/api/employee-ops/leaderboard/"

        with CaptureQueriesContext(connection) as small:
            self.assertEqual(self.client.get(url, **self._headers()).status_code, 200)

        for i in range(20):
            Employee.objects.create(
                tenant=self.tenant_a, name=f"موظف إضافي {i}", code=f"7{i:02d}"
            )

        with CaptureQueriesContext(connection) as large:
            res = self.client.get(url, **self._headers())
        self.assertEqual(res.status_code, 200)
        self.assertGreaterEqual(len(res.data["results"]), 22)

        self.assertEqual(len(small), len(large), "عددُ الاستعلامات ينمو مع الموظفين.")
        self.assertLessEqual(
            len(large), 10, f"اللوحةُ تُصدر {len(large)} استعلاماً — فيها استعلامٌ لكلّ صفّ.",
        )
        board_queries = [
            q for q in large.captured_queries if "employee_ops_pointentry" in q["sql"]
        ]
        self.assertEqual(len(board_queries), 1, "اللوحةُ ليست استعلاماً واحداً.")

    # ── الصلاحيات والعزل ────────────────────────────────────────────────────

    def test_narrow_role_sees_only_its_own_points_but_the_whole_leaderboard(self):
        """السجلُّ خاصّ واللوحةُ للجميع — نصُّ المواصفة."""
        self._approve_flow(self.emp1, self.staff1, "approved_full", "لواحد")
        self._approve_flow(self.emp2, self.staff2, "approved_full", "لاثنين")

        self.client.force_authenticate(user=self.staff1)
        mine = self.client.get("/api/employee-ops/points/", **self._headers())
        self.assertEqual(mine.status_code, 200)
        self.assertEqual({row["employee"] for row in mine.data}, {self.emp1.id})

        board = self._leaderboard().data["results"]
        self.assertIn(self.emp2.id, {row["employee"] for row in board})

        self.client.force_authenticate(user=self.manager_a)
        everyone = self.client.get("/api/employee-ops/points/", **self._headers())
        self.assertEqual(
            {row["employee"] for row in everyone.data}, {self.emp1.id, self.emp2.id}
        )

    def test_narrow_role_cannot_grant_manual_points_or_unreview(self):
        _, sub_id = self._approve_flow(self.emp1, self.staff1)
        self.client.force_authenticate(user=self.staff1)
        self.assertEqual(
            self.client.post(
                "/api/employee-ops/points/manual/",
                {"employee": self.emp1.id, "points": 100, "reason": "لنفسي"},
                format="json", **self._headers(),
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                f"/api/employee-ops/submissions/{sub_id}/unreview/",
                {"reason": "أريد إلغاءه"}, format="json", **self._headers(),
            ).status_code,
            403,
        )
        self.assertFalse(PointEntry.objects.filter(points=100).exists())

    def test_tenant_isolation_on_points_and_leaderboard(self):
        today = timezone.localdate()
        PointEntry.objects.create(
            tenant=self.tenant_b, employee=self.emp_b, points=50,
            source=PointEntry.SOURCE_MANUAL, awarded_on=today, reason="شركة ب",
        )
        self.client.force_authenticate(user=self.manager_a)
        rows = self.client.get("/api/employee-ops/points/", **self._headers()).data
        self.assertNotIn(self.emp_b.id, {r["employee"] for r in rows})

        board = self._leaderboard(user=self.manager_a).data["results"]
        self.assertNotIn(self.emp_b.id, {r["employee"] for r in board})

    def test_every_points_endpoint_is_404_when_the_module_is_disabled(self):
        """**بمعرّفاتٍ قائمةٍ في نفس الشركة المُطفأة** — الوهميُّ يردّ ٤٠٤ بلا حارس."""
        mgr_off = User.objects.create_user(username="pts_mgr_off", password="x")
        tenant_off = create_company("شركة نقاط مطفأة", mgr_off)
        emp_off = Employee.objects.create(
            tenant=tenant_off, user=mgr_off, name="موظف مطفأ", code="801"
        )
        task_off = Task.objects.create(
            tenant=tenant_off, title="مهمة مطفأة", status=Task.STATUS_NEW
        )
        TaskAssignment.objects.create(
            tenant=tenant_off, task=task_off, employee=emp_off
        )
        sub_off = TaskSubmission.objects.create(
            tenant=tenant_off, task=task_off, employee=emp_off, body="تسليم",
        )
        invalidate_module_cache(tenant_off.pk)

        self.client.force_authenticate(user=mgr_off)
        headers = {"HTTP_X_TENANT_ID": str(tenant_off.pk)}
        cases = [
            ("get", "/api/employee-ops/points/", None),
            ("get", "/api/employee-ops/points/summary/", None),
            ("post", "/api/employee-ops/points/manual/",
             {"employee": emp_off.id, "points": 1, "reason": "محاولة"}),
            ("post", "/api/employee-ops/attendance/check-in/", None),
            ("get", "/api/employee-ops/leaderboard/", None),
            ("post", f"/api/employee-ops/submissions/{sub_off.id}/unreview/",
             {"reason": "محاولة"}),
        ]
        for method, url, payload in cases:
            with self.subTest(url=url):
                func = getattr(self.client, method)
                res = func(url, payload, format="json", **headers) if payload else func(url, **headers)
                self.assertEqual(res.status_code, 404, f"{method.upper()} {url} → {res.status_code}")
        self.assertFalse(PointEntry.objects.filter(tenant=tenant_off).exists())

    def test_attendance_cap_never_pays_a_partial_award(self):
        """شركةٌ بنقطةِ حضورٍ ثلاثٍ وسقفِ خمس: ٣ ثمّ ٣ ⇒ الثانيةُ تتجاوز فتُمنع.

        `min(award, cap - today)` كان يمنح **٢** في الثانية — منحةٌ مبتورة لم
        تطلبها المواصفة («نقطةٌ لكلّ ضغطة») ولا يفهمها من يقرأ سجلّه.
        """
        EmployeeOpsSettings.objects.create(
            tenant=self.tenant_a, points_attendance=3, attendance_daily_cap=5
        )
        first = self._check_in()
        self.assertEqual(first.data["points_awarded"], 3)

        PointEntry.objects.filter(source=PointEntry.SOURCE_ATTENDANCE).update(
            created_at=timezone.now() - timedelta(minutes=5)
        )
        second = self._check_in()
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.data["points_awarded"], 0, "منحةٌ مبتورة.")
        self.assertEqual(second.data["today_points"], 3)
        self.assertTrue(second.data["capped"])

    def test_manual_points_are_always_dated_today(self):
        """المديرُ لا يكتب في شهرٍ أُغلق — الترتيبُ لا يتبدّل بأثرٍ رجعيّ."""
        res = self._manual({
            "employee": self.emp1.id, "points": 5, "reason": "مكافأة",
            "awarded_on": (timezone.localdate() - timedelta(days=40)).isoformat(),
        })
        self.assertEqual(res.status_code, 201)
        self.assertEqual(
            PointEntry.objects.get(source=PointEntry.SOURCE_MANUAL).awarded_on,
            timezone.localdate(),
        )
