"""M3 — الخدمة الذاتية: الموظف من الجلسة لا من الطلب، والقرار الجغرافي خادميّ.

أخطر ما تحرسه هذه الاختبارات أن **لا معرّف موظف يُقبل من العميل** في أي نقطة
هنا: مفتاحٌ واحدٌ مفتوح كان يجعل أي موظف يقرأ قسيمة راتب زميله بتغيير رقم.
"""
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from core.models import TenantModule
from hr.attendance import record_punch
from hr.models import (
    AttendanceDay, CheckEvent, Employee, Payslip, Shift, ShiftAssignment, WorkLocation,
)
from tenants.models import Tenant, UserCompanyMembership

HEBRON = ZoneInfo("Asia/Hebron")

ME = "/api/hr/ess/me/"
MY_DAY = "/api/hr/ess/my-day/"
MY_MONTH = "/api/hr/ess/my-month/"
MY_SCHEDULE = "/api/hr/ess/my-schedule/"
MY_PAYSLIPS = "/api/hr/ess/my-payslips/"
CHECK_IN = "/api/hr/ess/check-in/"
CHECK_OUT = "/api/hr/ess/check-out/"

OFFICE_LAT, OFFICE_LNG = Decimal("31.532570"), Decimal("35.095390")
NEAR_LAT, NEAR_LNG = Decimal("31.533100"), Decimal("35.095390")
FAR_LAT = Decimal("31.600000")


@override_settings(TIME_ZONE="Asia/Hebron", USE_TZ=True)
class EssTestBase(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(CompanyName="شركة الخدمة الذاتية")
        self.license = TenantModule.objects.create(
            tenant=self.tenant, module_key="hr_suite", enabled=True)
        self.user = User.objects.create_user("ess-employee", password="x")
        UserCompanyMembership.objects.create(
            user=self.user, tenant=self.tenant, role="ess")
        self.employee = Employee.objects.create(
            tenant=self.tenant, code="E1", name="سامي", monthly_salary=3000, user=self.user)
        self.location = WorkLocation.objects.create(
            tenant=self.tenant, name="المقر", latitude=OFFICE_LAT, longitude=OFFICE_LNG,
            radius_m=150)
        self.client.force_authenticate(self.user)

    def headers(self):
        return {"HTTP_X_TENANT_ID": str(self.tenant.pk)}

    def check_in(self, **payload):
        body = {"lat": str(NEAR_LAT), "lng": str(NEAR_LNG)}
        body.update(payload)
        return self.client.post(CHECK_IN, body, format="json", **self.headers())


class EssGateTest(EssTestBase):
    def test_every_ess_endpoint_is_404_without_a_module_license(self):
        self.license.delete()
        for url in (ME, MY_DAY, MY_MONTH, MY_SCHEDULE, MY_PAYSLIPS):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url, **self.headers()).status_code, 404)
        for url in (CHECK_IN, CHECK_OUT):
            with self.subTest(url=url):
                response = self.client.post(url, {}, format="json", **self.headers())
                self.assertEqual(response.status_code, 404, response.content)

    def test_user_without_an_employee_profile_gets_404_not_403(self):
        """مستخدمٌ بلا ملفّ موظف ليس ممنوعاً — لا وجود لبياناته أصلاً."""
        self.employee.user = None
        self.employee.save(update_fields=["user"])
        response = self.client.get(ME, **self.headers())
        self.assertEqual(response.status_code, 404, response.content)

    def test_inactive_employee_loses_self_service(self):
        self.employee.is_active = False
        self.employee.save(update_fields=["is_active"])
        self.assertEqual(self.client.get(ME, **self.headers()).status_code, 404)

    def test_ess_role_cannot_reach_the_admin_attendance_surface(self):
        """أضيق دورٍ في النظام يبصم لنفسه ولا يرى جدول زملائه."""
        response = self.client.get("/api/hr/attendance-days/", **self.headers())
        self.assertEqual(response.status_code, 403, response.content)


class EssIdentityTest(EssTestBase):
    def test_me_returns_this_employee_only(self):
        response = self.client.get(ME, **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["id"], self.employee.pk)
        # غير المربوط بموقعٍ بعينه تُقبل بصمته عند أي موقع نشط — والشاشة تحتاج
        # المرشَّحات كي تقول له «اقترب من المقر».
        self.assertIsNone(response.data["work_location"])
        self.assertEqual(
            [s["name"] for s in response.data["check_in_sites"]], ["المقر"])
        self.assertTrue(response.data["requires_geo"])

    def test_a_bound_employee_sees_only_their_own_site(self):
        WorkLocation.objects.create(
            tenant=self.tenant, name="المستودع", latitude=OFFICE_LAT,
            longitude=OFFICE_LNG, radius_m=150)
        self.employee.work_location = self.location
        self.employee.save(update_fields=["work_location"])

        response = self.client.get(ME, **self.headers())
        self.assertEqual(response.data["work_location"]["name"], "المقر")
        self.assertEqual(
            [s["name"] for s in response.data["check_in_sites"]], ["المقر"])

    def test_a_second_employee_never_leaks_into_my_payload(self):
        other_user = User.objects.create_user("ess-other", password="x")
        UserCompanyMembership.objects.create(
            user=other_user, tenant=self.tenant, role="ess")
        colleague = Employee.objects.create(
            tenant=self.tenant, code="E2", name="زميل", monthly_salary=4000, user=other_user)
        Payslip.objects.create(
            tenant=self.tenant, employee=colleague, period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31), net=Decimal("4000"), status=Payslip.STATUS_POSTED)

        response = self.client.get(MY_PAYSLIPS, **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data, [], "قسيمة الزميل لا تظهر لأحد غيره")

    def test_only_posted_payslips_are_visible(self):
        Payslip.objects.create(
            tenant=self.tenant, employee=self.employee, period_start=date(2026, 3, 1),
            period_end=date(2026, 3, 31), net=Decimal("3000"), status=Payslip.STATUS_DRAFT)
        self.assertEqual(self.client.get(MY_PAYSLIPS, **self.headers()).data, [])

        Payslip.objects.create(
            tenant=self.tenant, employee=self.employee, period_start=date(2026, 2, 1),
            period_end=date(2026, 2, 28), net=Decimal("3000"), status=Payslip.STATUS_POSTED)
        rows = self.client.get(MY_PAYSLIPS, **self.headers()).data
        self.assertEqual(len(rows), 1)


class EssPunchTest(EssTestBase):
    def test_check_in_inside_the_radius_is_accepted(self):
        response = self.check_in()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.data["accepted"])
        self.assertIsNotNone(response.data["today"]["open_session"])

    def test_check_in_outside_the_radius_is_refused_with_a_readable_reason(self):
        """الرفض قرارُ سياسةٍ يُشرح للموظف، لا خطأٌ في طلبه — فـ200 لا 4xx."""
        response = self.check_in(lat=str(FAR_LAT))
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.data["accepted"])
        self.assertEqual(response.data["reject_reason"], CheckEvent.REJECT_OUT_OF_RANGE)
        self.assertTrue(response.data["reject_label"])
        self.assertIsNone(response.data["today"]["open_session"])
        # والمحاولة محفوظة رغم رفضها.
        self.assertEqual(CheckEvent.objects.filter(accepted=False).count(), 1)

    def test_missing_coordinates_are_refused_when_the_site_requires_geo(self):
        response = self.client.post(CHECK_IN, {}, format="json", **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.data["accepted"])
        self.assertEqual(response.data["reject_reason"], CheckEvent.REJECT_NO_GEO)

    def test_double_check_in_is_blocked(self):
        """زرٌّ مضغوطٌ مرّتين أو تبويبان مفتوحان كانا يفتحان جلستين."""
        self.assertTrue(self.check_in().data["accepted"])
        again = self.check_in()
        self.assertEqual(again.status_code, 400, again.content)

    def test_check_out_without_an_open_session_is_blocked(self):
        response = self.client.post(
            CHECK_OUT, {"lat": str(NEAR_LAT), "lng": str(NEAR_LNG)},
            format="json", **self.headers())
        self.assertEqual(response.status_code, 400, response.content)

    def test_check_out_closes_the_session(self):
        self.check_in()
        response = self.client.post(
            CHECK_OUT, {"lat": str(NEAR_LAT), "lng": str(NEAR_LNG)},
            format="json", **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.data["accepted"])
        self.assertIsNone(response.data["today"]["open_session"])

    def test_a_rejected_punch_does_not_block_the_next_attempt(self):
        """من رُفضت بصمته لأنه خارج النطاق يجب أن يستطيع إعادتها من مكانه."""
        self.check_in(lat=str(FAR_LAT))
        second = self.check_in()
        self.assertEqual(second.status_code, 200, second.content)
        self.assertTrue(second.data["accepted"])

    def test_photo_requirement_is_enforced_server_side(self):
        self.location.require_photo = True
        self.location.save(update_fields=["require_photo"])
        refused = self.check_in()
        self.assertFalse(refused.data["accepted"])
        self.assertEqual(refused.data["reject_reason"], CheckEvent.REJECT_PHOTO_REQUIRED)

        accepted = self.check_in(photo_url="https://example.test/selfie.jpg")
        self.assertTrue(accepted.data["accepted"])

    def test_the_live_counter_start_comes_from_the_server(self):
        """العدّاد يقيس ما يصير مالاً، فبدايته خادميّة والواجهة تَعُدّ منها."""
        self.check_in()
        response = self.client.get(MY_DAY, **self.headers())
        session = response.data["open_session"]
        self.assertIsNotNone(session)
        self.assertIn("since", session)
        self.assertIn("server_now", session)
        self.assertGreaterEqual(session["server_now"], session["since"])


class EssMonthTest(EssTestBase):
    def setUp(self):
        super().setUp()
        self.shift = Shift.objects.create(
            tenant=self.tenant, name="صباحي", start1=time(9), end1=time(17),
            weekly_off_days=[4])
        ShiftAssignment.objects.create(
            tenant=self.tenant, employee=self.employee, shift=self.shift,
            start_date=date(2026, 1, 1))

    def punch(self, day, hour, kind=CheckEvent.KIND_IN):
        record_punch(
            self.employee, kind=kind,
            moment=datetime(2026, 3, day, hour, tzinfo=HEBRON),
            latitude=NEAR_LAT, longitude=NEAR_LNG)

    def test_month_summary_counts_only_expected_working_days(self):
        """العطلة الأسبوعية ليست حضوراً ولا غياباً — وإقحامها يخفض نسبة المنتظم."""
        self.punch(2, 9)
        self.punch(2, 17, kind=CheckEvent.KIND_OUT)
        from hr.attendance import recompute_attendance_day

        recompute_attendance_day(self.employee, date(2026, 3, 3))  # غياب
        recompute_attendance_day(self.employee, date(2026, 3, 6))  # جمعة

        response = self.client.get(f"{MY_MONTH}?month=2026-03", **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        summary = response.data["summary"]
        self.assertEqual(summary["present_days"], 1)
        self.assertEqual(summary["absent_days"], 1)
        self.assertEqual(summary["expected_days"], 2, "الجمعة خارج المتوقَّع")
        self.assertEqual(summary["attendance_rate"], 50.0)

    def test_month_without_any_expected_day_has_no_rate(self):
        """نسبةٌ من صفر كذبةٌ — تُعاد `null` لا 0٪ ولا 100٪."""
        response = self.client.get(f"{MY_MONTH}?month=2026-05", **self.headers())
        self.assertIsNone(response.data["summary"]["attendance_rate"])

    def test_bad_month_format_is_a_readable_400(self):
        response = self.client.get(f"{MY_MONTH}?month=2026", **self.headers())
        self.assertEqual(response.status_code, 400, response.content)

    def test_schedule_marks_the_current_assignment(self):
        response = self.client.get(MY_SCHEDULE, **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(response.data), 1)
        self.assertTrue(response.data[0]["is_current"])
        self.assertEqual(response.data[0]["weekly_off_days"], [4])


class EssAccessGrantTest(APITestCase):
    """فتح حساب خدمة ذاتية للموظف — الفعل الإداري الذي يُدخِله الوحدة."""

    def setUp(self):
        self.tenant = Tenant.objects.create(CompanyName="شركة الربط")
        TenantModule.objects.create(tenant=self.tenant, module_key="hr_suite", enabled=True)
        self.manager = User.objects.create_user("link-manager", password="x")
        UserCompanyMembership.objects.create(
            user=self.manager, tenant=self.tenant, role="manager")
        self.employee = Employee.objects.create(
            tenant=self.tenant, code="E1", name="سامي", monthly_salary=3000)
        self.client.force_authenticate(self.manager)

    def headers(self):
        return {"HTTP_X_TENANT_ID": str(self.tenant.pk)}

    def url(self):
        return f"/api/hr/employees/{self.employee.pk}/ess-access/"

    def test_creating_an_account_links_it_and_grants_the_employee_role(self):
        response = self.client.post(
            self.url(), {"username": "sami"}, format="json", **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.data["ess_user_created"])

        self.employee.refresh_from_db()
        self.assertIsNotNone(self.employee.user)
        membership = UserCompanyMembership.objects.get(
            user=self.employee.user, tenant=self.tenant)
        self.assertEqual(membership.role, "ess")

    def test_the_new_account_has_no_usable_password(self):
        """كلمةٌ تعبر استجابةَ API تُكتب في سجلٍّ ما وتبقى فيه."""
        self.client.post(self.url(), {"username": "sami"}, format="json", **self.headers())
        self.employee.refresh_from_db()
        self.assertFalse(self.employee.user.has_usable_password())

    def test_a_user_cannot_be_linked_to_two_employees_in_one_company(self):
        User.objects.create_user("shared", password="x")
        self.client.post(self.url(), {"username": "shared"}, format="json", **self.headers())
        second = Employee.objects.create(
            tenant=self.tenant, code="E2", name="ليان", monthly_salary=2000)

        response = self.client.post(
            f"/api/hr/employees/{second.pk}/ess-access/", {"username": "shared"},
            format="json", **self.headers())
        self.assertEqual(response.status_code, 400, response.content)

    def test_detach_removes_the_link_without_touching_the_account(self):
        self.client.post(self.url(), {"username": "sami"}, format="json", **self.headers())
        response = self.client.post(
            self.url(), {"detach": True}, format="json", **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        self.employee.refresh_from_db()
        self.assertIsNone(self.employee.user)
        self.assertTrue(User.objects.filter(username="sami").exists())

    def test_the_action_is_404_without_the_module_licence(self):
        """السطح قديمٌ مفتوح، لكن هذا الفعل من الوحدة — فيغيب بغيابها."""
        TenantModule.objects.filter(tenant=self.tenant).delete()
        response = self.client.post(
            self.url(), {"username": "sami"}, format="json", **self.headers())
        self.assertEqual(response.status_code, 404, response.content)
