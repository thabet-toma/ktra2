"""M2 — واجهة الحضور الإدارية: البصمة لا تُعدَّل، واليوم مشتقّ لا مُدخَل."""
from datetime import date, datetime, time
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.test import APITestCase

from core.models import TenantModule
from hr.attendance import record_punch
from hr.models import (
    AttendanceDay, CheckEvent, Employee, Shift, ShiftAssignment, WorkLocation,
)
from tenants.models import Tenant, UserCompanyMembership

HEBRON = ZoneInfo("Asia/Hebron")

LOCATIONS = "/api/hr/work-locations/"
SHIFTS = "/api/hr/shifts/"
ASSIGNMENTS = "/api/hr/shift-assignments/"
EVENTS = "/api/hr/check-events/"
DAYS = "/api/hr/attendance-days/"

OFFICE_LAT, OFFICE_LNG = Decimal("31.532570"), Decimal("35.095390")
NEAR_LAT, NEAR_LNG = Decimal("31.533100"), Decimal("35.095390")


def at(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=HEBRON)


@override_settings(TIME_ZONE="Asia/Hebron", USE_TZ=True)
class AttendanceApiTestBase(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(CompanyName="شركة الدوام")
        self.manager = User.objects.create_user("att-manager", password="x")
        UserCompanyMembership.objects.create(
            user=self.manager, tenant=self.tenant, role="manager")
        TenantModule.objects.create(
            tenant=self.tenant, module_key="hr_suite", enabled=True)
        self.employee = Employee.objects.create(
            tenant=self.tenant, code="E1", name="سامي", monthly_salary=3000)
        self.client.force_authenticate(self.manager)

    def headers(self):
        return {"HTTP_X_TENANT_ID": str(self.tenant.pk)}

    def rows(self, response):
        data = response.data
        return data["results"] if isinstance(data, dict) and "results" in data else data


class WorkLocationApiTest(AttendanceApiTestBase):
    def test_create_requires_coordinates_when_geo_is_enforced(self):
        response = self.client.post(
            LOCATIONS, {"name": "المقر", "require_geo": True}, format="json", **self.headers())
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("latitude", response.data)

    def test_half_a_coordinate_pair_is_rejected(self):
        response = self.client.post(
            LOCATIONS, {"name": "المقر", "require_geo": False, "latitude": "31.5"},
            format="json", **self.headers())
        self.assertEqual(response.status_code, 400, response.content)

    def test_unparsable_ip_entry_is_reported_not_swallowed(self):
        response = self.client.post(
            LOCATIONS,
            {"name": "المقر", "latitude": str(OFFICE_LAT), "longitude": str(OFFICE_LNG),
             "ip_allowlist": "192.168.1.0/24\nليس عنواناً"},
            format="json", **self.headers())
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("ip_allowlist", response.data)

    def test_radius_bounds_are_enforced(self):
        for radius in (5, 50_000):
            with self.subTest(radius=radius):
                response = self.client.post(
                    LOCATIONS,
                    {"name": f"موقع {radius}", "latitude": str(OFFICE_LAT),
                     "longitude": str(OFFICE_LNG), "radius_m": radius},
                    format="json", **self.headers())
                self.assertEqual(response.status_code, 400, response.content)

    def test_location_with_punches_cannot_be_deleted(self):
        location = WorkLocation.objects.create(
            tenant=self.tenant, name="المقر", latitude=OFFICE_LAT, longitude=OFFICE_LNG)
        record_punch(
            self.employee, kind=CheckEvent.KIND_IN, moment=at(2026, 3, 2, 9),
            latitude=NEAR_LAT, longitude=NEAR_LNG)

        response = self.client.delete(f"{LOCATIONS}{location.pk}/", **self.headers())
        self.assertEqual(response.status_code, 400, response.content)


class ShiftApiTest(AttendanceApiTestBase):
    def payload(self, **overrides):
        data = {
            "name": "صباحي", "start1": "09:00", "end1": "17:00",
            "grace_minutes": 10, "weekly_off_days": [4],
        }
        data.update(overrides)
        return data

    def test_create_and_read_back(self):
        response = self.client.post(SHIFTS, self.payload(), format="json", **self.headers())
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["weekly_off_days"], [4])

    def test_half_a_second_period_is_rejected(self):
        """نصفُ فترةٍ يُسقط حساب اليوم بصمت — يُمنع عند الباب."""
        response = self.client.post(
            SHIFTS, self.payload(name="ناقصة", start2="16:00"), format="json", **self.headers())
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("start2", response.data)

    def test_weekly_off_days_are_validated_and_deduplicated(self):
        bad = self.client.post(
            SHIFTS, self.payload(name="خاطئة", weekly_off_days=[9]),
            format="json", **self.headers())
        self.assertEqual(bad.status_code, 400, bad.content)

        ok = self.client.post(
            SHIFTS, self.payload(name="مكرّرة", weekly_off_days=[4, 4, 5]),
            format="json", **self.headers())
        self.assertEqual(ok.status_code, 201, ok.content)
        self.assertEqual(ok.data["weekly_off_days"], [4, 5])

    def test_identical_start_and_end_is_rejected(self):
        response = self.client.post(
            SHIFTS, self.payload(name="صفرية", start1="09:00", end1="09:00"),
            format="json", **self.headers())
        self.assertEqual(response.status_code, 400, response.content)

    def test_assigned_shift_cannot_be_deleted(self):
        shift = Shift.objects.create(
            tenant=self.tenant, name="صباحي", start1=time(9), end1=time(17))
        ShiftAssignment.objects.create(
            tenant=self.tenant, employee=self.employee, shift=shift, start_date=date(2026, 1, 1))

        response = self.client.delete(f"{SHIFTS}{shift.pk}/", **self.headers())
        self.assertEqual(response.status_code, 400, response.content)


class ShiftAssignmentApiTest(AttendanceApiTestBase):
    def setUp(self):
        super().setUp()
        self.shift = Shift.objects.create(
            tenant=self.tenant, name="صباحي", start1=time(9), end1=time(17))

    def test_end_before_start_is_rejected(self):
        response = self.client.post(
            ASSIGNMENTS,
            {"employee": self.employee.pk, "shift": self.shift.pk,
             "start_date": "2026-03-10", "end_date": "2026-03-01"},
            format="json", **self.headers())
        self.assertEqual(response.status_code, 400, response.content)

    def test_assigning_a_shift_recomputes_already_known_days(self):
        """يومٌ حُسب «بلا وردية» يجب أن يتبع الجدول فور ضبطه."""
        record_punch(
            self.employee, kind=CheckEvent.KIND_IN, moment=at(2026, 3, 2, 9, 30))
        day = AttendanceDay.objects.get(employee=self.employee, date=date(2026, 3, 2))
        self.assertEqual(day.status, AttendanceDay.STATUS_UNSCHEDULED)

        response = self.client.post(
            ASSIGNMENTS,
            {"employee": self.employee.pk, "shift": self.shift.pk,
             "start_date": "2026-03-01", "end_date": "2026-03-31"},
            format="json", **self.headers())
        self.assertEqual(response.status_code, 201, response.content)

        day.refresh_from_db()
        self.assertEqual(day.status, AttendanceDay.STATUS_LATE)
        self.assertEqual(day.late_minutes, 30)

    def test_foreign_employee_is_rejected_on_write(self):
        other = Tenant.objects.create(CompanyName="شركة أخرى")
        stranger = Employee.objects.create(
            tenant=other, code="X1", name="غريب", monthly_salary=1000)
        response = self.client.post(
            ASSIGNMENTS,
            {"employee": stranger.pk, "shift": self.shift.pk, "start_date": "2026-03-01"},
            format="json", **self.headers())
        self.assertEqual(response.status_code, 400, response.content)


class CheckEventApiTest(AttendanceApiTestBase):
    def test_manual_punch_is_recorded_and_recomputes_its_day(self):
        response = self.client.post(
            EVENTS,
            {"employee": self.employee.pk, "kind": "in", "ts": at(2026, 3, 2, 9).isoformat(),
             "notes": "بصم بالورقة"},
            format="json", **self.headers())
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["source"], CheckEvent.SOURCE_MANUAL)
        self.assertTrue(response.data["accepted"])
        self.assertTrue(
            AttendanceDay.objects.filter(employee=self.employee, date=date(2026, 3, 2)).exists())

    def test_events_cannot_be_edited_or_deleted(self):
        event = record_punch(
            self.employee, kind=CheckEvent.KIND_IN, moment=at(2026, 3, 2, 9))
        for method in ("patch", "put", "delete"):
            with self.subTest(method=method):
                call = getattr(self.client, method)
                response = call(f"{EVENTS}{event.pk}/", {}, format="json", **self.headers())
                self.assertEqual(response.status_code, 405, response.content)

    def test_void_drops_the_event_from_the_computation_but_keeps_the_row(self):
        entry = record_punch(
            self.employee, kind=CheckEvent.KIND_IN, moment=at(2026, 3, 2, 9))
        record_punch(self.employee, kind=CheckEvent.KIND_OUT, moment=at(2026, 3, 2, 17))
        day = AttendanceDay.objects.get(employee=self.employee, date=date(2026, 3, 2))
        self.assertEqual(day.worked_minutes, 480)

        response = self.client.post(f"{EVENTS}{entry.pk}/void/", {}, format="json", **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        day.refresh_from_db()
        self.assertEqual(day.worked_minutes, 0)
        self.assertTrue(CheckEvent.objects.filter(pk=entry.pk).exists())

    def test_voiding_twice_is_refused(self):
        entry = record_punch(
            self.employee, kind=CheckEvent.KIND_IN, moment=at(2026, 3, 2, 9))
        self.client.post(f"{EVENTS}{entry.pk}/void/", {}, format="json", **self.headers())
        again = self.client.post(f"{EVENTS}{entry.pk}/void/", {}, format="json", **self.headers())
        self.assertEqual(again.status_code, 400, again.content)

    def test_rejected_events_can_be_listed_on_their_own(self):
        WorkLocation.objects.create(
            tenant=self.tenant, name="المقر", latitude=OFFICE_LAT, longitude=OFFICE_LNG,
            radius_m=100)
        record_punch(
            self.employee, kind=CheckEvent.KIND_IN, moment=at(2026, 3, 2, 9),
            latitude=Decimal("31.60"), longitude=OFFICE_LNG)

        response = self.client.get(
            f"{EVENTS}?accepted=0&from=2026-03-01&to=2026-03-31", **self.headers())
        rows = self.rows(response)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["reject_reason"], CheckEvent.REJECT_OUT_OF_RANGE)
        self.assertTrue(rows[0]["reject_label"])


class AttendanceDayApiTest(AttendanceApiTestBase):
    def setUp(self):
        super().setUp()
        self.shift = Shift.objects.create(
            tenant=self.tenant, name="صباحي", start1=time(9), end1=time(17))
        ShiftAssignment.objects.create(
            tenant=self.tenant, employee=self.employee, shift=self.shift,
            start_date=date(2026, 1, 1))

    def test_days_are_never_created_or_edited_directly(self):
        """اليوم مشتقّ: لا إنشاء ولا تعديل ولا حذف — التصحيح يمرّ بـ`override/`."""
        created = self.client.post(DAYS, {}, format="json", **self.headers())
        self.assertEqual(created.status_code, 405, created.content)

        record_punch(self.employee, kind=CheckEvent.KIND_IN, moment=at(2026, 3, 2, 9))
        day = AttendanceDay.objects.get(employee=self.employee, date=date(2026, 3, 2))
        for method in ("patch", "put", "delete"):
            with self.subTest(method=method):
                response = getattr(self.client, method)(
                    f"{DAYS}{day.pk}/", {}, format="json", **self.headers())
                self.assertEqual(response.status_code, 405, response.content)

    def test_window_longer_than_the_cap_is_refused(self):
        response = self.client.get(f"{DAYS}?from=2026-01-01&to=2026-12-31", **self.headers())
        self.assertEqual(response.status_code, 400, response.content)

    def test_month_filter_returns_that_month(self):
        record_punch(self.employee, kind=CheckEvent.KIND_IN, moment=at(2026, 3, 2, 9))
        response = self.client.get(f"{DAYS}?month=2026-03", **self.headers())
        rows = self.rows(response)
        self.assertEqual([r["date"] for r in rows], ["2026-03-02"])

    def test_override_marks_the_day_and_survives_recomputation(self):
        record_punch(self.employee, kind=CheckEvent.KIND_IN, moment=at(2026, 3, 2, 11))
        day = AttendanceDay.objects.get(employee=self.employee, date=date(2026, 3, 2))
        self.assertEqual(day.late_minutes, 120)

        response = self.client.post(
            f"{DAYS}{day.pk}/override/",
            {"status": AttendanceDay.STATUS_PRESENT, "late_minutes": 0,
             "notes": "إذن مسبق من المدير"},
            format="json", **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.data["is_manual_override"])

        recompute = self.client.post(
            f"{DAYS}recompute/", {"from": "2026-03-01", "to": "2026-03-05"},
            format="json", **self.headers())
        self.assertEqual(recompute.status_code, 200, recompute.content)
        day.refresh_from_db()
        self.assertEqual(day.late_minutes, 0, "التصحيح المعلَن لا تكتسحه إعادة الحساب")

    def test_lifting_the_override_returns_the_day_to_its_punches(self):
        record_punch(self.employee, kind=CheckEvent.KIND_IN, moment=at(2026, 3, 2, 11))
        day = AttendanceDay.objects.get(employee=self.employee, date=date(2026, 3, 2))
        self.client.post(
            f"{DAYS}{day.pk}/override/", {"late_minutes": 0}, format="json", **self.headers())

        response = self.client.post(
            f"{DAYS}{day.pk}/override/", {"is_manual_override": False},
            format="json", **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.data["is_manual_override"])
        self.assertEqual(response.data["late_minutes"], 120)

    def test_recompute_fills_absences_for_a_window(self):
        response = self.client.post(
            f"{DAYS}recompute/", {"from": "2026-03-02", "to": "2026-03-04"},
            format="json", **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["recomputed"], 3)
        self.assertEqual(
            AttendanceDay.objects.filter(status=AttendanceDay.STATUS_ABSENT).count(), 3)

    def test_isolation_hides_another_company_days(self):
        other = Tenant.objects.create(CompanyName="شركة أخرى")
        stranger = Employee.objects.create(
            tenant=other, code="X1", name="غريب", monthly_salary=1000)
        record_punch(stranger, kind=CheckEvent.KIND_IN, moment=at(2026, 3, 2, 9))

        response = self.client.get(f"{DAYS}?month=2026-03", **self.headers())
        self.assertEqual(self.rows(response), [])
