"""عدّاداتُ قائمة الموظفين وفلاترُ التسليمات (المرحلة ٦ — ما تحتاجه الشاشات).

**العطبُ الذي تحرسه هذه الاختبارات:** الشاشةُ اليوميّةُ كانت تبني صفَّ كلّ موظف
بنداءِ كرتِه على حدة — خمسون موظفاً = خمسون طلبَ HTTP على شاشةِ الدخول، وهو
العطبُ الذي عضّ «كرت المجموعة» سابقاً. فالعدّاداتُ صارت تُحسب في استعلام القائمة
نفسِه، وهنا يُثبَت أنّها **صحيحة** لا سريعةٌ وحدها: تجميعان على علاقتين مختلفتين
في استعلامٍ واحدٍ يتضاعفان إن كُتبا ضمّاً بدل استعلامٍ فرعيّ.
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase

from core.models import ActivityLog, TenantModule
from core.modules import invalidate_module_cache
from employee_ops.models import PointEntry, Task, TaskAssignment, TaskSubmission
from hr.models import Employee
from tenants.models import Currency, UserCompanyMembership
from tenants.services import create_company


class EmployeeListCountersTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True}
        )
        cls.manager = User.objects.create_user(username="cnt_mgr", password="x")
        cls.tenant = create_company("شركة العدّادات", cls.manager)
        TenantModule.objects.create(
            tenant=cls.tenant, module_key="employee_ops", enabled=True
        )
        invalidate_module_cache(cls.tenant.pk)

        cls.staff_user = User.objects.create_user(username="cnt_staff", password="x")
        UserCompanyMembership.objects.create(
            user=cls.staff_user, tenant=cls.tenant, role="staff"
        )
        cls.emp = Employee.objects.create(
            tenant=cls.tenant, user=cls.staff_user, name="موظف العدّادات", code="C01"
        )

    def setUp(self):
        self.client.force_authenticate(user=self.manager)

    def _row(self, employee_id):
        # الشركةُ في الترويسة صراحةً: حالما توجد شركةٌ ثانيةٌ في المشوار يعجز
        # المحلِّلُ عن حسمها من العضويّة وحدها فيردّ 404.
        res = self.client.get(
            "/api/employee-ops/employees/", HTTP_X_TENANT_ID=str(self.tenant.pk)
        )
        self.assertEqual(res.status_code, 200)
        for row in res.data:
            if row["id"] == employee_id:
                return row
        self.fail("الموظف %s غائبٌ عن القائمة" % employee_id)

    def _task(self, *, due_date=None, title="مهمّة"):
        return Task.objects.create(
            tenant=self.tenant, title=title, due_date=due_date, created_by=self.manager
        )

    def test_counters_do_not_inflate_each_other(self):
        """ثلاثُ مهامّ ونقطتان: التجميعُ ضمّاً كان يضرب كلَّ عدّادٍ في الآخر.

        بلا استعلاماتٍ فرعيّة يصير `open_tasks` ستّةً (٣×٢) و`month_points`
        مجموعَ النقاط ثلاثَ مرّات. الأرقامُ مختارةٌ ليختلف الصحيحُ عن المتضخّم.
        """
        today = timezone.localdate()
        for i in range(3):
            task = self._task(due_date=today + timedelta(days=1), title="مهمّة %s" % i)
            TaskAssignment.objects.create(
                tenant=self.tenant, task=task, employee=self.emp
            )
        for points in (7, 5):
            PointEntry.objects.create(
                tenant=self.tenant,
                employee=self.emp,
                points=points,
                awarded_on=today,
                reason="اختبار",
            )

        row = self._row(self.emp.pk)
        self.assertEqual(row["open_tasks"], 3)
        self.assertEqual(row["month_points"], 12)

    def test_overdue_counts_only_what_is_past_due(self):
        today = timezone.localdate()
        for task in (
            self._task(due_date=today - timedelta(days=2), title="متأخّرة"),
            self._task(due_date=today, title="اليوم"),
            self._task(due_date=None, title="بلا موعد"),
        ):
            TaskAssignment.objects.create(
                tenant=self.tenant, task=task, employee=self.emp
            )

        row = self._row(self.emp.pk)
        self.assertEqual(row["open_tasks"], 3)
        # اليومُ ليس متأخّراً، وبلا موعدٍ لا يتأخّر أبداً.
        self.assertEqual(row["overdue_tasks"], 1)

    def test_completed_assignment_leaves_the_open_count(self):
        task = self._task(due_date=timezone.localdate() - timedelta(days=1))
        assignment = TaskAssignment.objects.create(
            tenant=self.tenant, task=task, employee=self.emp
        )
        self.assertEqual(self._row(self.emp.pk)["open_tasks"], 1)

        assignment.status = TaskAssignment.STATUS_COMPLETED
        assignment.save(update_fields=["status"])
        row = self._row(self.emp.pk)
        self.assertEqual(row["open_tasks"], 0)
        self.assertEqual(row["overdue_tasks"], 0)

    def test_counters_never_cross_the_tenant_line(self):
        """صفوفٌ تحمل شركةً أخرى **على موظفنا نفسِه** — وهي وحدها ما يختبر الفلتر.

        صفٌّ على موظفٍ آخر يُستبعد بـ`employee=OuterRef("pk")` وحدَه، فيبقى
        الاختبارُ أخضرَ ولو حُذف `tenant=` من الاستعلامات الثلاثة. أي أنّه يحرس
        شيئاً آخر ويحمل اسمَ هذا. فالصفوفُ هنا على `self.emp` بشركةٍ غريبة.
        """
        other_mgr = User.objects.create_user(username="cnt_mgr_b", password="x")
        other = create_company("شركة أخرى", other_mgr)
        today = timezone.localdate()

        task = self._task(due_date=today - timedelta(days=1))
        TaskAssignment.objects.create(tenant=other, task=task, employee=self.emp)
        PointEntry.objects.create(
            tenant=other,
            employee=self.emp,
            points=99,
            awarded_on=today,
            reason="نقاطُ شركةٍ أخرى",
        )
        ActivityLog.objects.create(
            tenant=other, user=self.staff_user, action="login", entity_type="session"
        )

        row = self._row(self.emp.pk)
        self.assertEqual(row["open_tasks"], 0, "إسنادُ شركةٍ أخرى لا يُعدّ")
        self.assertEqual(row["overdue_tasks"], 0)
        self.assertEqual(row["month_points"], 0, "نقاطُ شركةٍ أخرى لا تُجمَع")
        self.assertIsNone(row["last_activity"], "نشاطُ شركةٍ أخرى لا يُقرأ")

    def test_last_activity_reports_the_newest_event_in_this_tenant(self):
        """المسارُ الموجب: بلا هذا يبقى `last_activity` مُختبَراً بحالة NULL وحدها."""
        older = ActivityLog.objects.create(
            tenant=self.tenant,
            user=self.staff_user,
            action="login",
            entity_type="session",
        )
        newer = ActivityLog.objects.create(
            tenant=self.tenant,
            user=self.staff_user,
            action="create",
            entity_type="task",
        )
        ActivityLog.objects.filter(pk=older.pk).update(
            timestamp=timezone.now() - timedelta(days=3)
        )

        reported = self._row(self.emp.pk)["last_activity"]
        self.assertIsNotNone(reported)
        newer.refresh_from_db()
        self.assertEqual(reported[:19], newer.timestamp.isoformat()[:19])

    def test_membership_not_account_decides_who_can_be_invited(self):
        """العائدُ إلى العمل: يحتفظ بـ`user` وتُحذف عضويّتُه.

        `has_account` يبقى صحيحاً فيبدو كمن لا يحتاج دعوة، بينما الخادمُ يقبل
        دعوتَه. `has_membership` هو ما يجيب السؤالَ الصحيح.
        """
        row = self._row(self.emp.pk)
        self.assertTrue(row["has_account"])
        self.assertTrue(row["has_membership"])

        UserCompanyMembership.objects.filter(
            tenant=self.tenant, user=self.staff_user
        ).delete()

        row = self._row(self.emp.pk)
        self.assertTrue(row["has_account"], "السجلّ يحتفظ بحسابه")
        self.assertFalse(row["has_membership"], "ولا عضويّةَ له فيستحقّ دعوةً")

    def test_last_activity_is_null_without_a_login_account(self):
        no_login = Employee.objects.create(
            tenant=self.tenant, name="بلا حساب", code="C02"
        )
        self.assertIsNone(self._row(no_login.pk)["last_activity"])


class SubmissionListFiltersTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True}
        )
        cls.manager = User.objects.create_user(username="flt_mgr", password="x")
        cls.tenant = create_company("شركة الفلاتر", cls.manager)
        TenantModule.objects.create(
            tenant=cls.tenant, module_key="employee_ops", enabled=True
        )
        invalidate_module_cache(cls.tenant.pk)

        cls.staff_user = User.objects.create_user(username="flt_staff", password="x")
        UserCompanyMembership.objects.create(
            user=cls.staff_user, tenant=cls.tenant, role="staff"
        )
        cls.emp = Employee.objects.create(
            tenant=cls.tenant, user=cls.staff_user, name="موظف الفلاتر", code="F01"
        )
        cls.task_a = Task.objects.create(
            tenant=cls.tenant, title="مهمّة أ", created_by=cls.manager
        )
        cls.task_b = Task.objects.create(
            tenant=cls.tenant, title="مهمّة ب", created_by=cls.manager
        )
        for task in (cls.task_a, cls.task_b):
            TaskAssignment.objects.create(
                tenant=cls.tenant, task=task, employee=cls.emp
            )
        cls.sub_a = TaskSubmission.objects.create(
            tenant=cls.tenant, task=cls.task_a, employee=cls.emp, body="تسليم أ"
        )
        cls.sub_b = TaskSubmission.objects.create(
            tenant=cls.tenant, task=cls.task_b, employee=cls.emp, body="تسليم ب"
        )

    def setUp(self):
        self.client.force_authenticate(user=self.manager)

    def test_task_filter_returns_only_that_task(self):
        res = self.client.get(
            "/api/employee-ops/submissions/?task=%s" % self.task_a.pk,
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual([row["id"] for row in res.data], [self.sub_a.pk])

    def test_unfiltered_still_returns_everything(self):
        res = self.client.get(
            "/api/employee-ops/submissions/", HTTP_X_TENANT_ID=str(self.tenant.pk)
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            sorted(row["id"] for row in res.data),
            sorted([self.sub_a.pk, self.sub_b.pk]),
        )

    def test_decision_filter_selects_the_pending_queue(self):
        self.sub_b.decision = TaskSubmission.DECISION_APPROVED_FULL
        self.sub_b.save(update_fields=["decision"])

        res = self.client.get(
            "/api/employee-ops/submissions/?decision=pending",
            HTTP_X_TENANT_ID=str(self.tenant.pk),
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual([row["id"] for row in res.data], [self.sub_a.pk])

    def test_garbage_filters_are_refused_not_ignored(self):
        """فلترٌ مجهولٌ يُتجاهَل يعني قائمةً كاملةً تُقدَّم على أنّها مفلترة."""
        self.assertEqual(
            self.client.get(
                "/api/employee-ops/submissions/?task=abc",
                HTTP_X_TENANT_ID=str(self.tenant.pk),
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.get(
                "/api/employee-ops/submissions/?decision=nope",
                HTTP_X_TENANT_ID=str(self.tenant.pk),
            ).status_code,
            400,
        )
