"""ملاحظاتُ الموظفين وكرتُ الموظف وتبويبُ نشاطه (المرحلة ٥).

**العطبُ القائم الذي تُصلحه هذه المرحلة:** «ملاحظات الموظفين» اليوم حقلُ نصٍّ واحدٌ
على سجلّ المستخدم يُدهَس بكلّ حفظ — بلا كاتبٍ ولا تاريخ. وملاحظةُ مديرٍ عن موظفٍ
بلا قائلٍ ولا وقتٍ لا تصلح دليلاً على شيء.
"""
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APITestCase

from core.access import FIELD_STAFF_ROLE
from core.models import ActivityLog, TenantModule
from core.modules import invalidate_module_cache
from employee_ops.models import (
    EmployeeNote,
    PointEntry,
    Task,
    TaskAssignment,
)
from employee_ops.services import ACTIVITY_TAB_LIMIT
from hr.models import Employee
from tenants.models import Currency, UserCompanyMembership
from tenants.services import create_company


class EmployeeOpsNotesAndCardTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "IsBaseCurrency": True}
        )
        cls.manager_a = User.objects.create_user(username="note_mgr_a", password="x")
        cls.manager_a2 = User.objects.create_user(username="note_mgr_a2", password="x")
        cls.manager_b = User.objects.create_user(username="note_mgr_b", password="x")
        cls.tenant_a = create_company("شركة الملاحظات أ", cls.manager_a)
        cls.tenant_b = create_company("شركة الملاحظات ب", cls.manager_b)
        for tenant in (cls.tenant_a, cls.tenant_b):
            TenantModule.objects.create(
                tenant=tenant, module_key="employee_ops", enabled=True
            )
            invalidate_module_cache(tenant.pk)

        UserCompanyMembership.objects.create(
            user=cls.manager_a2, tenant=cls.tenant_a, role="manager"
        )
        cls.staff = User.objects.create_user(username="note_staff", password="x")
        UserCompanyMembership.objects.create(
            user=cls.staff, tenant=cls.tenant_a, role=FIELD_STAFF_ROLE
        )
        cls.emp = Employee.objects.create(
            tenant=cls.tenant_a, user=cls.staff, name="موظف الملاحظات", code="901"
        )
        cls.emp_no_login = Employee.objects.create(
            tenant=cls.tenant_a, name="موظف بلا حساب", code="902"
        )
        cls.emp_b = Employee.objects.create(
            tenant=cls.tenant_b, name="موظف شركة ب", code="903"
        )

    def _h(self, tenant=None):
        return {"HTTP_X_TENANT_ID": str((tenant or self.tenant_a).pk)}

    def _post_note(self, body, employee=None, user=None, tenant=None):
        self.client.force_authenticate(user=user or self.manager_a)
        return self.client.post(
            "/api/employee-ops/notes/",
            {"employee": (employee or self.emp).id, "body": body},
            format="json",
            **self._h(tenant),
        )

    # ── الملاحظات ────────────────────────────────────────────────────────────

    def test_a_note_carries_its_author_from_the_session_not_the_payload(self):
        """كاتبٌ يُمرَّر من العميل يعني ملاحظةً منسوبةً لغير قائلها."""
        self.client.force_authenticate(user=self.manager_a)
        res = self.client.post(
            "/api/employee-ops/notes/",
            {"employee": self.emp.id, "body": "منضبط", "author": self.manager_a2.pk},
            format="json",
            **self._h(),
        )
        self.assertEqual(res.status_code, 201, res.data)
        note = EmployeeNote.objects.get(pk=res.data["id"])
        self.assertEqual(note.author_id, self.manager_a.pk)
        self.assertIsNotNone(note.created_at)

    def test_notes_accumulate_and_never_overwrite_one_another(self):
        """ثلاثُ ملاحظاتٍ ⇒ ثلاثةُ صفوف. الحقلُ الواحدُ القديم كان يُدهَس بكلّ حفظ."""
        for text in ("الأولى", "الثانية", "الثالثة"):
            self.assertEqual(self._post_note(text).status_code, 201)
        bodies = list(
            EmployeeNote.objects.filter(employee=self.emp).values_list("body", flat=True)
        )
        self.assertEqual(len(bodies), 3)
        self.assertIn("الأولى", bodies)

    def test_an_empty_note_is_refused(self):
        for body in ("", "   ", "\n\t "):
            with self.subTest(body=repr(body)):
                self.assertEqual(self._post_note(body).status_code, 400)
        self.assertFalse(EmployeeNote.objects.exists())

    def test_a_note_can_never_be_edited_or_deleted(self):
        """**لا تعديلَ ولا حذف** — والسببُ ليس صلابةً بل معنى الملاحظة.

        العيبُ الذي وُجد هذا الجدولُ لإزالته حقلٌ «يُدهَس بكلّ حفظ»؛ وتحريرُ النصّ
        في مكانه هو الدهسُ نفسُه بنطاقٍ أضيق. والمواصفة تريدها **دليلاً لا
        انطباعاً** ولم تطلب أيّاً منهما. من أخطأ يكتب ملاحظةً تصحّحه.
        """
        note_id = self._post_note("انطباعي أنا").data["id"]
        self.client.force_authenticate(user=self.manager_a)

        for method in ("patch", "delete", "put"):
            with self.subTest(method=method):
                res = getattr(self.client, method)(
                    f"/api/employee-ops/notes/{note_id}/",
                    {"body": "بدّلتُ كلامي"},
                    format="json",
                    **self._h(),
                )
                self.assertIn(res.status_code, (404, 405))

        note = EmployeeNote.objects.get(pk=note_id)
        self.assertEqual(note.body, "انطباعي أنا")

    def test_writing_a_note_leaves_no_trace_in_the_general_activity_screen(self):
        """حدثُ «كُتبت ملاحظةٌ عن فلان» يتسرّب لمن يقرأ النشاط العامّ بلا صلاحية الوحدة.

        §٩ تمنع إضافةَ نقاطِ تسجيلٍ في v1؛ والأهمّ أنّ **وجودَ** رأيٍ سرّيٍّ عن
        موظفٍ باسمه معلومةٌ بذاتها، ولو بقي نصُّ الملاحظة محجوباً.
        """
        before = ActivityLog.objects.count()
        self.assertEqual(self._post_note("رأيٌ سرّيّ").status_code, 201)
        self.assertEqual(ActivityLog.objects.count(), before)

    def test_notes_are_newest_first(self):
        ids = [self._post_note(f"ملاحظة {i}").data["id"] for i in range(3)]
        self.client.force_authenticate(user=self.manager_a)
        listed = self.client.get(
            f"/api/employee-ops/notes/?employee={self.emp.id}", **self._h()
        )
        self.assertEqual([row["id"] for row in listed.data], list(reversed(ids)))

    def test_tenant_isolation_on_notes(self):
        """مديرُ (أ) لا يكتب على موظفِ (ب) ولا يقرأ ملاحظاته."""
        self.assertEqual(
            self._post_note("اختراق", employee=self.emp_b).status_code, 404
        )
        self.assertFalse(EmployeeNote.objects.filter(employee=self.emp_b).exists())

        self.client.force_authenticate(user=self.manager_b)
        foreign = self.client.post(
            "/api/employee-ops/notes/",
            {"employee": self.emp_b.id, "body": "ملاحظةُ ب"},
            format="json",
            **self._h(self.tenant_b),
        )
        self.assertEqual(foreign.status_code, 201)

        self.client.force_authenticate(user=self.manager_a)
        self.assertEqual(
            self.client.get(
                f"/api/employee-ops/notes/?employee={self.emp_b.id}", **self._h()
            ).status_code,
            404,
        )

    def test_narrow_role_cannot_read_or_write_notes(self):
        """الوحدةُ مرخَّصة فوجودُها ليس سرّاً — والسرُّ ما فيها: ٤٠٣ لا ٤٠٤."""
        self._post_note("ملاحظةُ المدير")
        self.client.force_authenticate(user=self.staff)
        self.assertEqual(
            self.client.get(
                f"/api/employee-ops/notes/?employee={self.emp.id}", **self._h()
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.post(
                "/api/employee-ops/notes/",
                {"employee": self.emp.id, "body": "أكتب عن نفسي"},
                format="json",
                **self._h(),
            ).status_code,
            403,
        )

    # ── تبويبُ النشاط ────────────────────────────────────────────────────────

    def _log(self, user, tenant, days_ago=0, label="حدث"):
        entry = ActivityLog.objects.create(
            tenant=tenant, user=user, action="create",
            entity_type="test", entity_label=label,
        )
        if days_ago:
            ActivityLog.objects.filter(pk=entry.pk).update(
                timestamp=timezone.now() - timedelta(days=days_ago)
            )
        return entry

    def test_activity_tab_returns_only_this_employee_events_within_the_range(self):
        other_user = User.objects.create_user(username="note_other", password="x")
        UserCompanyMembership.objects.create(
            user=other_user, tenant=self.tenant_a, role=FIELD_STAFF_ROLE
        )
        self._log(self.staff, self.tenant_a, days_ago=1, label="داخل المدى")
        self._log(self.staff, self.tenant_a, days_ago=40, label="خارج المدى")
        self._log(other_user, self.tenant_a, days_ago=1, label="لزميلٍ آخر")

        self.client.force_authenticate(user=self.manager_a)
        since = (timezone.localdate() - timedelta(days=7)).isoformat()
        res = self.client.get(
            f"/api/employee-ops/employees/{self.emp.id}/activity/?date_from={since}",
            **self._h(),
        )
        self.assertEqual(res.status_code, 200)
        labels = [row["entity_label"] for row in res.data["results"]]
        self.assertEqual(labels, ["داخل المدى"])

    def test_activity_tab_is_empty_for_an_employee_without_a_login(self):
        """موظفٌ بلا حسابٍ: قائمةٌ فارغةٌ **لا خطأ**."""
        self.client.force_authenticate(user=self.manager_a)
        res = self.client.get(
            f"/api/employee-ops/employees/{self.emp_no_login.id}/activity/", **self._h()
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["results"], [])

    def test_activity_tab_is_capped(self):
        """جدولٌ كبير، والتبويبُ تصفّحٌ لا تصدير."""
        ActivityLog.objects.bulk_create([
            ActivityLog(
                tenant=self.tenant_a, user=self.staff, action="create",
                entity_type="test", entity_label=f"حدث {i}",
            )
            for i in range(ACTIVITY_TAB_LIMIT + 50)
        ])
        self.client.force_authenticate(user=self.manager_a)
        res = self.client.get(
            f"/api/employee-ops/employees/{self.emp.id}/activity/", **self._h()
        )
        self.assertEqual(len(res.data["results"]), ACTIVITY_TAB_LIMIT)
        self.assertEqual(res.data["limit"], ACTIVITY_TAB_LIMIT)

    def test_activity_tab_does_not_leak_another_company_events(self):
        """نفسُ المستخدم عضوٌ في شركتين — ومديرُ (أ) يرى أحداثَ (أ) وحدها."""
        UserCompanyMembership.objects.create(
            user=self.staff, tenant=self.tenant_b, role=FIELD_STAFF_ROLE
        )
        self._log(self.staff, self.tenant_a, label="حدثٌ في أ")
        self._log(self.staff, self.tenant_b, label="حدثٌ في ب")

        self.client.force_authenticate(user=self.manager_a)
        res = self.client.get(
            f"/api/employee-ops/employees/{self.emp.id}/activity/", **self._h()
        )
        self.assertEqual(
            [row["entity_label"] for row in res.data["results"]], ["حدثٌ في أ"]
        )

    # ── كرتُ الموظف ─────────────────────────────────────────────────────────

    def _assign(self, due_date=None, title="مهمة"):
        task = Task.objects.create(
            tenant=self.tenant_a, title=title, status=Task.STATUS_NEW, due_date=due_date
        )
        TaskAssignment.objects.create(
            tenant=self.tenant_a, task=task, employee=self.emp
        )
        return task

    def test_card_returns_counts_that_match_reality(self):
        self._assign(due_date=timezone.localdate() + timedelta(days=3), title="قادمة")
        self._assign(due_date=timezone.localdate() - timedelta(days=2), title="متأخّرة")
        done = self._assign(title="منتهية")
        TaskAssignment.objects.filter(task=done).update(
            status=TaskAssignment.STATUS_COMPLETED
        )
        PointEntry.objects.create(
            tenant=self.tenant_a, employee=self.emp, points=10,
            source=PointEntry.SOURCE_MANUAL, awarded_on=timezone.localdate(),
            reason="مكافأة",
        )

        self.client.force_authenticate(user=self.manager_a)
        res = self.client.get(
            f"/api/employee-ops/employees/{self.emp.id}/card/", **self._h()
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["open_tasks"], 2)
        self.assertEqual(res.data["overdue_tasks"], 1)
        self.assertEqual(res.data["month_points"], 10)
        self.assertTrue(res.data["has_account"])
        self.assertEqual(res.data["name"], "موظف الملاحظات")

    def test_card_query_count_does_not_grow_with_tasks(self):
        """سقفٌ **مطلق** مع ثبات: كلٌّ وحده يمرّ بما لا يجوز."""
        for i in range(3):
            self._assign(title=f"مهمة {i}")
        self.client.force_authenticate(user=self.manager_a)
        url = f"/api/employee-ops/employees/{self.emp.id}/card/"

        with CaptureQueriesContext(connection) as small:
            self.assertEqual(self.client.get(url, **self._h()).status_code, 200)
        for i in range(9):
            self._assign(title=f"مهمة إضافية {i}")
        with CaptureQueriesContext(connection) as large:
            self.assertEqual(self.client.get(url, **self._h()).status_code, 200)

        self.assertEqual(len(small), len(large), "عددُ الاستعلامات ينمو مع المهامّ.")
        self.assertLessEqual(
            len(large), 12, f"الكرتُ يُصدر {len(large)} استعلاماً — استعلامٌ لكلّ مهمّة.",
        )

    def test_notes_and_card_and_activity_are_404_when_the_module_is_disabled(self):
        """بمعرّفاتٍ قائمةٍ في نفس الشركة المُطفأة — الوهميُّ يردّ ٤٠٤ بلا حارس."""
        self._post_note("قبل الإطفاء")
        TenantModule.objects.filter(
            tenant=self.tenant_a, module_key="employee_ops"
        ).update(enabled=False)
        invalidate_module_cache(self.tenant_a.pk)

        self.client.force_authenticate(user=self.manager_a)
        # **لا `notes/{id}/` هنا**: لا فعلَ `retrieve` على هذه المجموعة، فتردّ
        # ٤٠٤ والوحدةُ مشتغلةٌ أيضاً — حالةٌ تمرّ ولو نُزع حارسُ الترخيص كلُّه.
        cases = [
            ("get", f"/api/employee-ops/notes/?employee={self.emp.id}"),
            ("get", f"/api/employee-ops/employees/{self.emp.id}/card/"),
            ("get", f"/api/employee-ops/employees/{self.emp.id}/activity/"),
        ]
        for method, url in cases:
            with self.subTest(url=url):
                self.assertEqual(
                    getattr(self.client, method)(url, **self._h()).status_code, 404
                )
        self.assertEqual(
            self.client.post(
                "/api/employee-ops/notes/",
                {"employee": self.emp.id, "body": "بعد الإطفاء"},
                format="json",
                **self._h(),
            ).status_code,
            404,
        )
        self.assertEqual(EmployeeNote.objects.count(), 1)

    def test_a_bad_activity_range_is_400_not_500(self):
        """`filter_local_date_range` تتوقّع تاريخاً لا نصّاً — والنصُّ الخام كان ٥٠٠."""
        self.client.force_authenticate(user=self.manager_a)
        res = self.client.get(
            f"/api/employee-ops/employees/{self.emp.id}/activity/?date_from=ليس-تاريخاً",
            **self._h(),
        )
        self.assertEqual(res.status_code, 400)
