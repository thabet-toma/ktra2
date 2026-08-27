"""M4 — استيراد سجل الحضور من CSV، وتقارير الوحدة خلف ترخيصها.

قارئ الملف مُختبَرٌ **وحده** (`parse_attendance_csv`) لأن قارئاً مدفوناً في
نقطة HTTP لا يُختبر إلا برفع ملف، فتبقى حالاته الحدّية بلا حارس.
"""
from datetime import date, time
from decimal import Decimal
from io import BytesIO

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APITestCase

from core.models import TenantModule
from hr.attendance_api import parse_attendance_csv
from hr.models import AttendanceDay, CheckEvent, Employee, Shift, ShiftAssignment
from tenants.models import Tenant, UserCompanyMembership

IMPORT_URL = "/api/hr/attendance-days/import/"


class ParseAttendanceCsvTest(TestCase):
    def test_plain_rows_without_a_header(self):
        rows, errors = parse_attendance_csv("E1,2026-03-02,09:00,17:00\n")
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["code"], "E1")
        self.assertEqual(rows[0]["date"], date(2026, 3, 2))
        self.assertEqual(rows[0]["time_in"].time(), time(9, 0))
        self.assertEqual(rows[0]["time_out"].time(), time(17, 0))

    def test_english_header_is_recognised(self):
        rows, errors = parse_attendance_csv(
            "code,date,time_in,time_out\nE1,2026-03-02,08:30,16:30\n")
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["time_in"].time(), time(8, 30))

    def test_arabic_header_is_recognised(self):
        """الملف يخرج من Excel كتبه محاسب عربي — لا يُطالَب بترجمته."""
        rows, errors = parse_attendance_csv(
            "رقم الموظف,التاريخ,الدخول,الخروج\nE1,2026-03-02,09:00,17:00\n")
        self.assertEqual(errors, [])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["code"], "E1")

    def test_reordered_header_is_honoured(self):
        rows, errors = parse_attendance_csv(
            "date,code,time_out,time_in\n2026-03-02,E9,17:00,09:00\n")
        self.assertEqual(errors, [])
        self.assertEqual(rows[0]["code"], "E9")
        self.assertEqual(rows[0]["time_in"].time(), time(9, 0))

    def test_overnight_row_rolls_the_checkout_to_the_next_day(self):
        """خروجٌ أبكر من دخوله في اليوم نفسه = وردية عبرت منتصف الليل."""
        rows, _errors = parse_attendance_csv("E1,2026-03-02,22:00,06:00\n")
        self.assertEqual(rows[0]["time_in"].date(), date(2026, 3, 2))
        self.assertEqual(rows[0]["time_out"].date(), date(2026, 3, 3))

    def test_only_a_check_in_is_accepted(self):
        rows, errors = parse_attendance_csv("E1,2026-03-02,09:00,\n")
        self.assertEqual(errors, [])
        self.assertIsNone(rows[0]["time_out"])

    def test_a_bad_row_does_not_sink_the_file(self):
        """ملفٌ من مئة صفٍّ يُرفض كلّه لأجل صفٍّ واحد يترك صاحبه بلا طريق."""
        rows, errors = parse_attendance_csv(
            "E1,2026-03-02,09:00,17:00\n"
            "E2,ليس تاريخاً,09:00,17:00\n"
            "E3,2026-03-02,لا وقت,17:00\n"
            ",2026-03-02,09:00,17:00\n"
            "E4,2026-03-02,,\n"
            "E5,2026-03-03,08:00,16:00\n")
        self.assertEqual([r["code"] for r in rows], ["E1", "E5"])
        self.assertEqual(len(errors), 4)
        self.assertEqual([e["row"] for e in errors], [2, 3, 4, 5])

    def test_blank_lines_are_skipped(self):
        rows, errors = parse_attendance_csv("\n\nE1,2026-03-02,09:00,17:00\n\n")
        self.assertEqual(len(rows), 1)
        self.assertEqual(errors, [])

    def test_seconds_in_the_clock_are_accepted(self):
        rows, errors = parse_attendance_csv("E1,2026-03-02,09:00:30,17:00:00\n")
        self.assertEqual(errors, [])
        self.assertEqual(rows[0]["time_in"].time(), time(9, 0, 30))


@override_settings(TIME_ZONE="Asia/Hebron", USE_TZ=True)
class AttendanceImportApiTest(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(CompanyName="شركة الاستيراد")
        self.license = TenantModule.objects.create(
            tenant=self.tenant, module_key="hr_suite", enabled=True)
        self.manager = User.objects.create_user("import-manager", password="x")
        UserCompanyMembership.objects.create(
            user=self.manager, tenant=self.tenant, role="manager")
        self.employee = Employee.objects.create(
            tenant=self.tenant, code="E1", name="سامي", monthly_salary=3000)
        shift = Shift.objects.create(
            tenant=self.tenant, name="صباحي", start1=time(9), end1=time(17))
        ShiftAssignment.objects.create(
            tenant=self.tenant, employee=self.employee, shift=shift,
            start_date=date(2026, 1, 1))
        self.client.force_authenticate(self.manager)

    def headers(self):
        return {"HTTP_X_TENANT_ID": str(self.tenant.pk)}

    def upload(self, text, **extra):
        payload = {
            "file": SimpleUploadedFile("attendance.csv", text.encode("utf-8"), "text/csv"),
            **extra,
        }
        return self.client.post(IMPORT_URL, payload, format="multipart", **self.headers())

    def test_import_creates_punches_and_recomputes_days(self):
        response = self.upload(
            "code,date,time_in,time_out\n"
            "E1,2026-03-02,09:00,17:00\n"
            "E1,2026-03-03,09:30,17:00\n"
            "E1,2026-03-04,09:00,15:00\n")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["created"], 6)
        self.assertEqual(response.data["days"], 3)
        self.assertEqual(response.data["error_count"], 0)

        self.assertEqual(
            CheckEvent.objects.filter(source=CheckEvent.SOURCE_IMPORT).count(), 6)
        days = {row.date: row for row in AttendanceDay.objects.all()}
        self.assertEqual(days[date(2026, 3, 2)].worked_minutes, 480)
        self.assertEqual(days[date(2026, 3, 3)].status, AttendanceDay.STATUS_LATE)
        self.assertEqual(days[date(2026, 3, 3)].late_minutes, 30)
        self.assertEqual(days[date(2026, 3, 4)].early_leave_minutes, 120)

    def test_dry_run_reports_without_writing(self):
        """الاستيراد الأعمى في سجلٍّ لا يُحذف منه شيء خطأٌ لا يُتراجَع عنه."""
        response = self.upload("E1,2026-03-02,09:00,17:00\n", dry_run="true")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.data["dry_run"])
        self.assertEqual(response.data["created"], 2)
        self.assertEqual(CheckEvent.objects.count(), 0)
        self.assertEqual(AttendanceDay.objects.count(), 0)

    def test_unknown_employee_code_is_reported_by_row(self):
        response = self.upload(
            "E1,2026-03-02,09:00,17:00\n"
            "E404,2026-03-02,09:00,17:00\n")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["created"], 2)
        self.assertEqual(response.data["error_count"], 1)
        self.assertIn("E404", response.data["errors"][0]["message"])

    def test_employee_of_another_company_is_not_matched(self):
        other = Tenant.objects.create(CompanyName="شركة أخرى")
        Employee.objects.create(
            tenant=other, code="E7", name="غريب", monthly_salary=1000)
        response = self.upload("E7,2026-03-02,09:00,17:00\n")
        self.assertEqual(response.data["created"], 0)
        self.assertEqual(response.data["error_count"], 1)

    def test_missing_file_is_a_readable_400(self):
        response = self.client.post(IMPORT_URL, {}, format="multipart", **self.headers())
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("file", response.data)

    def test_import_is_404_without_the_module_licence(self):
        self.license.delete()
        response = self.upload("E1,2026-03-02,09:00,17:00\n")
        self.assertEqual(response.status_code, 404, response.content)


class AttendanceReportsTest(APITestCase):
    """تقارير الوحدة تختفي بغياب ترخيصها — فهرساً وتشغيلاً."""

    KEYS = ("hr-attendance-grid", "hr-attendance-summary", "hr-check-events")

    def setUp(self):
        self.tenant = Tenant.objects.create(CompanyName="شركة التقارير")
        self.license = TenantModule.objects.create(
            tenant=self.tenant, module_key="hr_suite", enabled=True)
        self.manager = User.objects.create_user("report-manager", password="x")
        UserCompanyMembership.objects.create(
            user=self.manager, tenant=self.tenant, role="manager")
        self.employee = Employee.objects.create(
            tenant=self.tenant, code="E1", name="سامي", monthly_salary=3000)
        AttendanceDay.objects.create(
            tenant=self.tenant, employee=self.employee, date=date(2026, 3, 2),
            status=AttendanceDay.STATUS_LATE, worked_minutes=450, late_minutes=30,
            overtime_minutes=0, absence_days=Decimal("0"))
        AttendanceDay.objects.create(
            tenant=self.tenant, employee=self.employee, date=date(2026, 3, 3),
            status=AttendanceDay.STATUS_ABSENT, absence_days=Decimal("1"))
        self.client.force_authenticate(self.manager)

    def headers(self):
        return {"HTTP_X_TENANT_ID": str(self.tenant.pk)}

    def test_catalog_lists_them_when_licensed(self):
        response = self.client.get("/api/reports/", **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        keys = {
            row["key"]
            for category in response.data["categories"]
            for row in category["reports"]
        }
        for key in self.KEYS:
            self.assertIn(key, keys)

    def test_catalog_hides_them_without_a_licence(self):
        self.license.delete()
        response = self.client.get("/api/reports/", **self.headers())
        keys = {
            row["key"]
            for category in response.data["categories"]
            for row in category["reports"]
        }
        for key in self.KEYS:
            with self.subTest(key=key):
                self.assertNotIn(key, keys)

    def test_running_them_is_404_without_a_licence(self):
        self.license.delete()
        for key in self.KEYS:
            with self.subTest(key=key):
                response = self.client.get(
                    f"/api/reports/{key}/?from=2026-03-01&to=2026-03-31", **self.headers())
                self.assertEqual(response.status_code, 404, response.content)

    def test_summary_rate_counts_only_expected_working_days(self):
        response = self.client.get(
            "/api/reports/hr-attendance-summary/?from=2026-03-01&to=2026-03-31",
            **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        row = response.data["rows"][0]
        self.assertEqual(row["present_days"], 1)
        self.assertEqual(row["absent_days"], 1)
        self.assertEqual(row["attendance_rate"], 50.0)
        self.assertEqual(row["worked_hours"], 7.5)

    def test_grid_marks_the_day_with_its_status(self):
        response = self.client.get(
            "/api/reports/hr-attendance-grid/?from=2026-03-01&to=2026-03-31",
            **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        row = response.data["rows"][0]
        self.assertEqual(row["d2"], "ت 30")
        self.assertEqual(row["d3"], "غ")
        self.assertEqual(row["absence_days"], 1.0)

    def test_summary_without_any_expected_day_leaves_the_rate_blank(self):
        """نسبةٌ من صفر كذبة — تبقى فارغة لا صفراً ولا مئة."""
        AttendanceDay.objects.all().delete()
        AttendanceDay.objects.create(
            tenant=self.tenant, employee=self.employee, date=date(2026, 3, 6),
            status=AttendanceDay.STATUS_OFF)
        response = self.client.get(
            "/api/reports/hr-attendance-summary/?from=2026-03-01&to=2026-03-31",
            **self.headers())
        self.assertEqual(response.data["rows"][0]["attendance_rate"], "")
