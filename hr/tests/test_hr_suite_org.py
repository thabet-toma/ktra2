"""M1 — وحدة الموارد البشرية الموسّعة: البوابة والهيكل التنظيمي.

اختبار البوابة هنا لا يعدّد مساراتٍ كُتبت بيد: يمشي على راوتر الوحدة نفسه،
فأي ViewSet يُضاف لاحقاً وينسى وراثة `HrSuiteViewSetBase` يسقط الاختبار فوراً
بدل أن يفلت سطحٌ غير محروس إلى الإنتاج.
"""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from core.models import TenantModule
from hr.models import Department, Employee, JobTitle
from hr.suite import MODULE_KEY, HrSuiteViewSetBase
from hr.urls import suite_router
from tenants.models import Branch, Tenant, UserCompanyMembership

DEPARTMENTS = "/api/hr/departments/"
JOB_TITLES = "/api/hr/job-titles/"


def enable_module(tenant):
    return TenantModule.objects.create(tenant=tenant, module_key=MODULE_KEY, enabled=True)


class HrSuiteTestBase(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(CompanyName="شركة الموارد")
        self.manager = User.objects.create_user("hr-manager", password="x")
        UserCompanyMembership.objects.create(
            user=self.manager, tenant=self.tenant, role="manager")
        self.license = enable_module(self.tenant)
        self.client.force_authenticate(self.manager)

    def headers(self, tenant=None):
        return {"HTTP_X_TENANT_ID": str((tenant or self.tenant).pk)}

    def make_department(self, name="المبيعات", **extra):
        response = self.client.post(
            DEPARTMENTS, {"name": name, **extra}, format="json", **self.headers())
        self.assertEqual(response.status_code, 201, response.content)
        return response.data


class SuiteGateTest(HrSuiteTestBase):
    def test_every_suite_viewset_inherits_the_licence_gate(self):
        """الوراثة هي البوابة — ViewSet خارجها سطحٌ مكشوف مهما بدا بريئاً."""
        for prefix, viewset, basename in suite_router.registry:
            with self.subTest(prefix=prefix):
                self.assertTrue(
                    issubclass(viewset, HrSuiteViewSetBase),
                    f"{basename}: كل ViewSet في راوتر الوحدة يرث HrSuiteViewSetBase",
                )

    def test_every_suite_endpoint_is_404_without_a_module_license(self):
        department = self.make_department()
        self.license.delete()

        for prefix, _viewset, _basename in suite_router.registry:
            base = f"/api/hr/{prefix}/"
            detail = f"{base}{department['id']}/"
            calls = [
                ("get", base, None),
                ("post", base, {"name": "قسم مهرَّب"}),
                ("get", detail, None),
                ("patch", detail, {"name": "منتحَل"}),
                ("delete", detail, None),
            ]
            for method, url, body in calls:
                with self.subTest(method=method, url=url):
                    response = getattr(self.client, method)(
                        url, body, format="json", **self.headers()) if body is not None \
                        else getattr(self.client, method)(url, **self.headers())
                    self.assertEqual(response.status_code, 404, response.content)

    def test_licensed_tenant_reaches_the_endpoint(self):
        response = self.client.get(DEPARTMENTS, **self.headers())
        self.assertEqual(response.status_code, 200, response.content)


class DepartmentApiTest(HrSuiteTestBase):
    def test_create_and_list_with_employee_count(self):
        department = self.make_department("المحاسبة")
        Employee.objects.create(
            tenant=self.tenant, code="E1", name="سامي", department_id=department["id"],
            monthly_salary=1000)
        Employee.objects.create(
            tenant=self.tenant, code="E2", name="ليان", department_id=department["id"],
            monthly_salary=1000, is_active=False)

        response = self.client.get(DEPARTMENTS, **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual(len(rows), 1)
        # العدّ للنشطين وحدهم — الموظف المعطَّل لا يمنع تعطيل القسم ولا يُعدّ فيه.
        self.assertEqual(rows[0]["employees_count"], 1)

    def test_duplicate_name_is_a_readable_400(self):
        self.make_department("التشغيل")
        response = self.client.post(
            DEPARTMENTS, {"name": "التشغيل"}, format="json", **self.headers())
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("name", response.data)

    def test_department_cannot_be_its_own_ancestor(self):
        parent = self.make_department("الإدارة")
        child = self.client.post(
            DEPARTMENTS, {"name": "التسويق", "parent": parent["id"]},
            format="json", **self.headers()).data

        response = self.client.patch(
            f"{DEPARTMENTS}{parent['id']}/", {"parent": child["id"]},
            format="json", **self.headers())
        self.assertEqual(response.status_code, 400, response.content)

    def test_delete_is_blocked_while_the_department_is_in_use(self):
        department = self.make_department("المستودع")
        employee = Employee.objects.create(
            tenant=self.tenant, name="رامي", department_id=department["id"],
            monthly_salary=900)

        response = self.client.delete(f"{DEPARTMENTS}{department['id']}/", **self.headers())
        self.assertEqual(response.status_code, 400, response.content)

        employee.delete()
        self.client.post(
            DEPARTMENTS, {"name": "فرعي", "parent": department["id"]},
            format="json", **self.headers())
        response = self.client.delete(f"{DEPARTMENTS}{department['id']}/", **self.headers())
        self.assertEqual(response.status_code, 400, response.content)

    def test_delete_succeeds_when_free(self):
        department = self.make_department("مؤقّت")
        response = self.client.delete(f"{DEPARTMENTS}{department['id']}/", **self.headers())
        self.assertEqual(response.status_code, 204, response.content)
        self.assertFalse(Department.objects.filter(pk=department["id"]).exists())


class OrgIsolationTest(HrSuiteTestBase):
    """العزل لا يكفي على القائمة — المعرّف يصل من الجسم كذلك."""

    def setUp(self):
        super().setUp()
        self.other = Tenant.objects.create(CompanyName="شركة أخرى")
        enable_module(self.other)
        UserCompanyMembership.objects.create(
            user=self.manager, tenant=self.other, role="manager")
        self.foreign_department = Department.objects.create(
            tenant=self.other, name="قسم الغير")
        self.foreign_branch = Branch.objects.create(
            tenant=self.other, name="فرع الغير", code="OTH")

    def test_list_never_shows_another_company_rows(self):
        self.make_department("قسمي")
        response = self.client.get(DEPARTMENTS, **self.headers())
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual([r["name"] for r in rows], ["قسمي"])

    def test_foreign_parent_is_rejected_on_write(self):
        response = self.client.post(
            DEPARTMENTS, {"name": "قسم جديد", "parent": self.foreign_department.pk},
            format="json", **self.headers())
        self.assertEqual(response.status_code, 400, response.content)

    def test_foreign_branch_is_rejected_on_write(self):
        response = self.client.post(
            DEPARTMENTS, {"name": "قسم جديد", "branch": self.foreign_branch.pk},
            format="json", **self.headers())
        self.assertEqual(response.status_code, 400, response.content)


class JobTitleApiTest(HrSuiteTestBase):
    def test_create_and_filter_by_department(self):
        department = self.make_department("الفنيّون")
        self.client.post(
            JOB_TITLES, {"name": "فنّي أول", "department": department["id"]},
            format="json", **self.headers())
        self.client.post(JOB_TITLES, {"name": "سائق"}, format="json", **self.headers())

        response = self.client.get(
            f"{JOB_TITLES}?department={department['id']}", **self.headers())
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        self.assertEqual([r["name"] for r in rows], ["فنّي أول"])

    def test_delete_is_blocked_while_used_by_an_employee(self):
        title = self.client.post(
            JOB_TITLES, {"name": "محاسب"}, format="json", **self.headers()).data
        Employee.objects.create(
            tenant=self.tenant, name="هدى", job_title_ref_id=title["id"], monthly_salary=1200)

        response = self.client.delete(f"{JOB_TITLES}{title['id']}/", **self.headers())
        self.assertEqual(response.status_code, 400, response.content)
        self.assertTrue(JobTitle.objects.filter(pk=title["id"]).exists())


class EmployeeOrgFieldsTest(HrSuiteTestBase):
    """حقول الهيكل تُكتب من نقطة الموظف القائمة — وهي غير محروسة بالترخيص عمداً."""

    def test_employee_accepts_and_returns_org_fields(self):
        department = self.make_department("الشحن")
        response = self.client.post(
            "/api/hr/employees/",
            {"name": "زياد", "pay_type": "monthly", "monthly_salary": "1500",
             "department": department["id"]},
            format="json", **self.headers())
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["department"], department["id"])
        self.assertEqual(response.data["department_name"], "الشحن")

    def test_employee_endpoint_still_works_without_the_module_license(self):
        """الرواتب سطحٌ قديم مفتوح — الترخيص الجديد لا يُطفئ شركةً تشتغل عليه."""
        self.license.delete()
        response = self.client.get("/api/hr/employees/", **self.headers())
        self.assertEqual(response.status_code, 200, response.content)


class EmployeeSeatLimitTest(HrSuiteTestBase):
    """حدّ الخطة على الموظفين — نظيرُ حدّ الأعضاء وليس بديلَه."""

    def test_limit_blocks_creation_past_the_plan(self):
        from core.models import TenantLimit

        TenantLimit.objects.create(tenant=self.tenant, limit_key="hr.employees", max_value=1)
        first = self.client.post(
            "/api/hr/employees/",
            {"name": "أول", "pay_type": "monthly", "monthly_salary": "1000"},
            format="json", **self.headers())
        self.assertEqual(first.status_code, 201, first.content)

        second = self.client.post(
            "/api/hr/employees/",
            {"name": "ثانٍ", "pay_type": "monthly", "monthly_salary": "1000"},
            format="json", **self.headers())
        self.assertEqual(second.status_code, 400, second.content)
        self.assertIn("plan_limit", second.data)

    def test_a_disabled_employee_frees_the_seat(self):
        """الموظف المعطَّل سجلٌّ تاريخي لا مقعدٌ مشغول."""
        from core.models import TenantLimit
        from core.plans import current_usage, invalidate_limit_cache

        TenantLimit.objects.create(tenant=self.tenant, limit_key="hr.employees", max_value=1)
        created = self.client.post(
            "/api/hr/employees/",
            {"name": "أول", "pay_type": "monthly", "monthly_salary": "1000"},
            format="json", **self.headers())
        self.assertEqual(created.status_code, 201, created.content)

        Employee.objects.filter(pk=created.data["id"]).update(is_active=False)
        invalidate_limit_cache(self.tenant.pk)
        self.assertEqual(current_usage(self.tenant, "hr.employees"), 0)
