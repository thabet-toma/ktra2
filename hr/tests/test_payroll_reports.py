"""كشفا الرواتب والساعات — الثابت الذي يحرسه هذا الملف.

الكشفان يقرآن من نفس السجلات التي يقرأ منها محرّك الرواتب، بمرشّحات مستقلة عنه.
فالحارس الأول والأهم هنا **مطابقة الرقمين**: ما يظهر في كشف الساعات لكل موظف هو
عين ما احتُسب عليه في كشفه — أي انحراف مستقبلي في أحد الطرفين يكسر الاختبار.

والمقياس يتبع نوع الموظف لأن الاحتساب نفسه يتبعه (`hr/payroll.py::compute_payslip`):
الجزئي يُحاسَب على **ساعاته**، والدائم على **غيابه وتأخيره** وساعاته صفر دائماً.
مطابقة ساعات الدائم مطلبٌ غير قابل للتحقق إلا بتغيير احتساب المال — وهو خارج
نطاق تقرير.
"""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from hr.models import AttendanceAdjustment, Employee, Payslip, WorkLog
from hr.payroll import compute_payslip
from tenants.models import UserCompanyMembership
from tenants.services import create_company

TIMESHEET_URL = "/api/reports/timesheet-daily/"
PAYSLIPS_URL = "/api/reports/payslips/"

PERIOD_START = date(2026, 8, 1)
PERIOD_END = date(2026, 8, 31)


def _day_key(day: date) -> str:
    """مفتاح عمود اليوم — ترتيبه في الفترة، كما يبنيه التقرير."""
    return f"d{(day - PERIOD_START).days + 1}"


class TimesheetReportTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.boss = User.objects.create_user(username="ts-boss", password="x")
        cls.viewer = User.objects.create_user(username="ts-viewer", password="x")
        cls.tenant = create_company("شركة الكشوف", cls.boss)
        UserCompanyMembership.objects.create(
            user=cls.viewer, tenant=cls.tenant, role="viewer")

        def employee(name, pay_type, **extra):
            # الرقم صريح: `code` فريد لكل شركة، والفراغ الافتراضي يتصادم.
            employee.n = getattr(employee, "n", 0) + 1
            return Employee.objects.create(
                tenant=cls.tenant, name=name, pay_type=pay_type,
                code=f"E{employee.n}", **extra)

        # ثلاثة بالساعة واثنان شهريان — الخمسة الذين طلبهم المالك.
        cls.hourly_a = employee("عمر", Employee.PAY_HOURLY, hourly_rate=Decimal("5"))
        cls.hourly_b = employee("ليلى", Employee.PAY_HOURLY, hourly_rate=Decimal("7"))
        cls.hourly_c = employee("زيد", Employee.PAY_HOURLY, hourly_rate=Decimal("6"))
        cls.monthly_d = employee(
            "سامي", Employee.PAY_MONTHLY, monthly_salary=Decimal("2600"))
        cls.monthly_e = employee(
            "هدى", Employee.PAY_MONTHLY, monthly_salary=Decimal("3000"))

        def log(employee_obj, day, hours):
            WorkLog.objects.create(
                tenant=cls.tenant, employee=employee_obj,
                date=date(2026, 8, day), hours=Decimal(hours))

        log(cls.hourly_a, 3, "8")
        log(cls.hourly_a, 4, "7.5")
        log(cls.hourly_a, 5, "9")       # ساعة فوق الدوام المعياري (8)
        log(cls.hourly_b, 3, "6")
        # زيد بلا ساعات — يظهر بصفر لا يختفي.
        # ساعة خارج الفترة: لا تدخل الكشف ولا الاحتساب.
        log(cls.hourly_a, 1, "4")
        WorkLog.objects.create(
            tenant=cls.tenant, employee=cls.hourly_a,
            date=date(2026, 7, 20), hours=Decimal("12"))

        def adjust(employee_obj, day, kind, **extra):
            AttendanceAdjustment.objects.create(
                tenant=cls.tenant, employee=employee_obj,
                date=date(2026, 8, day), kind=kind, **extra)

        adjust(cls.monthly_d, 10, AttendanceAdjustment.KIND_ABSENCE, days=Decimal("1"))
        adjust(cls.monthly_d, 11, AttendanceAdjustment.KIND_LATE, minutes=30)
        # غياب غير قابل للخصم: يُسجَّل في الكشف ويُعدّ يوماً، ولا يُخصم مالاً.
        adjust(cls.monthly_d, 12, AttendanceAdjustment.KIND_ABSENCE,
               days=Decimal("0.5"), is_deductible=False)

    def setUp(self):
        self.client.force_authenticate(user=self.boss)

    def _run(self, user=None, **params):
        if user is not None:
            self.client.force_authenticate(user=user)
        params.setdefault("from", PERIOD_START.isoformat())
        params.setdefault("to", PERIOD_END.isoformat())
        return self.client.get(
            TIMESHEET_URL, params, HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def _rows_by_employee(self, res):
        return {row["employee"]: row for row in res.data["rows"]}

    # ── معيار النجاح: الكشفان لا يفترقان ─────────────────────────────
    def test_the_timesheet_totals_match_what_each_type_is_paid_on(self):
        """الحارس الأساسي — ولكلٍّ مقياسه الذي يُحاسَب به فعلاً.

        الجزئي: مجموع ساعاته في الكشف == `worked_hours` في احتسابه.
        الدائم: أيام غيابه ودقائق تأخيره == `absence_days` و`late_minutes`.
        """
        res = self._run()
        self.assertEqual(res.status_code, 200, res.data)
        rows = self._rows_by_employee(res)
        self.assertEqual(len(rows), 5, "الموظفون الخمسة كلهم في الكشف")

        for employee in (self.hourly_a, self.hourly_b, self.hourly_c):
            computed = compute_payslip(employee, PERIOD_START, PERIOD_END)
            self.assertEqual(
                Decimal(rows[employee.name]["total_hours"]),
                Decimal(computed["worked_hours"]),
                f"ساعات {employee.name} في الكشف تخالف ما احتُسب عليه",
            )

        for employee in (self.monthly_d, self.monthly_e):
            computed = compute_payslip(employee, PERIOD_START, PERIOD_END)
            row = rows[employee.name]
            self.assertEqual(
                Decimal(row["absence_days"]), Decimal(computed["absence_days"]),
                f"أيام غياب {employee.name} في الكشف تخالف ما احتُسب عليه",
            )
            self.assertEqual(
                int(row["late_minutes"]), int(computed["late_minutes"]),
                f"دقائق تأخير {employee.name} في الكشف تخالف ما احتُسب عليه",
            )

    def test_a_day_outside_the_period_is_in_neither_number(self):
        """الحارس أعلاه بلا هذا يمرّ على كشفٍ يجرّ كل تاريخ الموظف."""
        res = self._run()
        row = self._rows_by_employee(res)[self.hourly_a.name]
        # 8 + 7.5 + 9 + 4 داخل آب، و12 في تموز خارجها.
        self.assertEqual(Decimal(row["total_hours"]), Decimal("28.5"))

    # ── الشبكة اليومية ───────────────────────────────────────────────
    def test_each_day_is_a_column_and_the_hours_land_in_it(self):
        res = self._run()
        headers = [c["key"] for c in res.data["columns"]]
        self.assertEqual(headers[0], "employee")
        self.assertEqual(len([k for k in headers if k.startswith("d")]), 31)

        row = self._rows_by_employee(res)[self.hourly_a.name]
        self.assertEqual(row[_day_key(date(2026, 8, 3))], "8")
        self.assertEqual(row[_day_key(date(2026, 8, 4))], "7.5")
        self.assertEqual(row[_day_key(date(2026, 8, 6))], "")

    def test_absence_and_lateness_are_marked_on_their_day(self):
        """الدائم لا ساعات له — خانته تحمل سبب الخصم كي تُراجَع بالعين."""
        row = self._rows_by_employee(self._run())[self.monthly_d.name]
        self.assertEqual(row[_day_key(date(2026, 8, 10))], "غ")
        self.assertEqual(row[_day_key(date(2026, 8, 11))], "ت 30")
        self.assertEqual(row[_day_key(date(2026, 8, 12))], "غ 0.5")

    def test_overtime_is_what_exceeded_the_agreed_daily_hours(self):
        row = self._rows_by_employee(self._run())[self.hourly_a.name]
        self.assertEqual(Decimal(row["overtime_hours"]), Decimal("1"))

    def test_the_totals_row_sums_the_summary_columns(self):
        totals = self._run().data["totals"]
        self.assertEqual(Decimal(totals["total_hours"]), Decimal("34.5"))
        self.assertEqual(Decimal(totals["absence_days"]), Decimal("1.5"))

    # ── الحراسة ──────────────────────────────────────────────────────
    def test_a_period_longer_than_a_month_is_refused_with_a_message(self):
        """31 عموداً سقفٌ للقراءة والطباعة — والرفض رسالة لا عطل."""
        res = self._run(**{"to": (PERIOD_START + timedelta(days=45)).isoformat()})
        self.assertEqual(res.status_code, 400, res.data)
        self.assertIn("31", res.data["error"])

    def test_thirty_one_days_exactly_is_accepted(self):
        self.assertEqual(self._run().status_code, 200)

    def test_a_viewer_without_the_payroll_permission_is_refused(self):
        self.assertEqual(self._run(user=self.viewer).status_code, 403)

    def test_the_timesheet_is_scoped_to_the_active_company(self):
        other_boss = User.objects.create_user(username="ts-other", password="x")
        other = create_company("شركة الجيران", other_boss)
        neighbour = Employee.objects.create(
            tenant=other, name="جار", pay_type=Employee.PAY_HOURLY,
            hourly_rate=Decimal("9"))
        WorkLog.objects.create(
            tenant=other, employee=neighbour, date=date(2026, 8, 3),
            hours=Decimal("11"))

        names = [row["employee"] for row in self._run().data["rows"]]
        self.assertNotIn("جار", names)
        self.assertEqual(Decimal(self._run().data["totals"]["total_hours"]),
                         Decimal("34.5"))

    def test_the_daily_columns_do_not_cost_a_query_per_employee(self):
        """شبكة 5×31 خانة تُبنى من استعلامين، لا من استعلام لكل موظف."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        with CaptureQueriesContext(connection) as few:
            self.assertEqual(self._run().status_code, 200)
        for i in range(6, 16):
            Employee.objects.create(
                tenant=self.tenant, name=f"موظف {i}", code=f"E{i}",
                pay_type=Employee.PAY_HOURLY, hourly_rate=Decimal("5"))
        with CaptureQueriesContext(connection) as many:
            self.assertEqual(self._run().status_code, 200)
        self.assertEqual(
            len(many), len(few),
            f"عدد الاستعلامات نما مع عدد الموظفين: {len(few)} → {len(many)}")


class PayslipsReportTest(APITestCase):
    """كشف الرواتب — الخصومات مفكّكة لأن المراجع يسأل «خصم ماذا»."""

    @classmethod
    def setUpTestData(cls):
        cls.boss = User.objects.create_user(username="ps-boss", password="x")
        cls.tenant = create_company("شركة المسير", cls.boss)
        cls.employee = Employee.objects.create(
            tenant=cls.tenant, name="سامي", code="E1",
            pay_type=Employee.PAY_MONTHLY, monthly_salary=Decimal("2600"))
        Payslip.objects.create(
            tenant=cls.tenant, employee=cls.employee,
            period_start=PERIOD_START, period_end=PERIOD_END,
            pay_type=Employee.PAY_MONTHLY, rate=Decimal("2600"),
            worked_hours=Decimal("0"), absence_days=Decimal("2"),
            late_minutes=45, gross=Decimal("2600"), allowances=Decimal("100"),
            absence_deduction=Decimal("200"), late_deduction=Decimal("18.75"),
            other_deductions=Decimal("30"), net=Decimal("2451.25"),
        )

    def setUp(self):
        self.client.force_authenticate(user=self.boss)

    def _run(self):
        return self.client.get(
            PAYSLIPS_URL,
            {"from": PERIOD_START.isoformat(), "to": PERIOD_END.isoformat()},
            HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def test_the_row_breaks_the_deductions_apart(self):
        res = self._run()
        self.assertEqual(res.status_code, 200, res.data)
        row = res.data["rows"][0]
        self.assertEqual(Decimal(row["absence_deduction"]), Decimal("200"))
        self.assertEqual(Decimal(row["late_deduction"]), Decimal("18.75"))
        self.assertEqual(Decimal(row["other_deductions"]), Decimal("30"))
        self.assertEqual(Decimal(row["absence_days"]), Decimal("2"))
        self.assertEqual(Decimal(row["net"]), Decimal("2451.25"))

    def test_every_money_column_lands_in_the_totals_row(self):
        totals = self._run().data["totals"]
        for key in ("gross", "allowances", "absence_deduction",
                    "late_deduction", "other_deductions", "net"):
            self.assertIn(key, totals)
        self.assertEqual(Decimal(totals["net"]), Decimal("2451.25"))
