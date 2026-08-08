"""الرواتب — الثوابت التي يحرسها هذا الملف.

1. **ربط الشجرة**: إنشاء موظف يفتح له حساباً تحت «2112 رواتب مستحقة للموظفين»،
   والبند يُنشأ تحت «21 الالتزامات المتداولة» لأول شركة تحتاجه.
2. **التفريق بين النوعين**: الجزئي استحقاقه من ساعاته المسجّلة؛ والدائم راتبٌ
   ثابت تُخصم منه غياباته وتأخيراته بمعدّل مشتقّ.
3. **القيد**: اعتماد الكشف يُدين مصروف الرواتب ويُدائن حساب الموظف؛ والصرف
   يعكس الاتجاه على حساب الموظف مقابل الصندوق. الدفتر متوازن في الحالتين.
4. **الحراسة**: العزل بالشركة، وصلاحيات hr.payroll.*، ومنع تعديل/حذف كشف مرحّل،
   ومنع إلغاء ترحيل كشف صُرف منه.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, JournalLine
from accounting.services import create_fiscal_year
from hr.models import Employee, Payslip
from hr.payroll import PAYROLL_EXPENSE_CODE, PAYROLL_PARENT_CODE
from tenants.models import UserCompanyMembership
from tenants.services import create_company

EMPLOYEES_URL = "/api/hr/employees/"
WORK_LOGS_URL = "/api/hr/work-logs/"
ADJUSTMENTS_URL = "/api/hr/attendance-adjustments/"
PAYSLIPS_URL = "/api/hr/payslips/"
PAYMENTS_URL = "/api/hr/payroll-payments/"


class PayrollTestBase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.boss = User.objects.create_user(username="pr-boss", password="x")
        cls.viewer = User.objects.create_user(username="pr-viewer", password="x")
        cls.tenant = create_company("شركة الرواتب", cls.boss)
        create_fiscal_year(cls.tenant, 2026)
        UserCompanyMembership.objects.create(
            user=cls.viewer, tenant=cls.tenant, role="viewer")

    def _as(self, user=None):
        self.client.force_authenticate(user=user or self.boss)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _create_employee(self, **overrides):
        payload = {
            "name": "سامي",
            "pay_type": Employee.PAY_MONTHLY,
            "monthly_salary": "2600.00",
            "working_days_per_month": "26",
            "standard_hours_per_day": "8",
        }
        payload.update(overrides)
        res = self.client.post(EMPLOYEES_URL, payload, format="json", **self._as())
        assert res.status_code == 201, res.content
        return res.json()

    def _create_payslip(self, employee_id, start="2026-08-01", end="2026-08-31", **extra):
        payload = {"employee": employee_id, "period_start": start, "period_end": end}
        payload.update(extra)
        res = self.client.post(PAYSLIPS_URL, payload, format="json", **self._as())
        assert res.status_code == 201, res.content
        return res.json()


class PayrollTreeTest(PayrollTestBase):
    """البند وحسابات الموظفين تحته."""

    def test_creating_employee_opens_an_account_under_the_payroll_node(self):
        row = self._create_employee()
        parent = Account.objects.get(tenant=self.tenant, code=PAYROLL_PARENT_CODE)
        account = Account.objects.get(pk=row["account"])

        assert account.parent_id == parent.pk
        assert account.account_type == "Liability"
        assert account.name == "سامي"
        assert row["account_code"].startswith(PAYROLL_PARENT_CODE)

    def test_payroll_node_hangs_under_current_liabilities(self):
        self._create_employee()
        parent = Account.objects.get(tenant=self.tenant, code=PAYROLL_PARENT_CODE)
        assert parent.parent.code == "21"

    def test_renaming_the_employee_renames_the_tree_account(self):
        row = self._create_employee()
        res = self.client.patch(
            f"{EMPLOYEES_URL}{row['id']}/", {"name": "سامي عبد الله"},
            format="json", **self._as())
        assert res.status_code == 200, res.content
        assert Account.objects.get(pk=row["account"]).name == "سامي عبد الله"

    def test_two_employees_get_distinct_accounts(self):
        first = self._create_employee(name="أول")
        second = self._create_employee(name="ثانٍ")
        assert first["account"] != second["account"]
        assert first["account_code"] != second["account_code"]


class HourlyEmployeeTest(PayrollTestBase):
    """الجزئي: الاستحقاق من الساعات المسجّلة وحدها."""

    def _hourly(self):
        return self._create_employee(
            name="عامل بالساعة", pay_type=Employee.PAY_HOURLY,
            hourly_rate="20.00", monthly_salary="0")

    def test_hours_drive_the_payslip(self):
        employee = self._hourly()
        for day, hours in (("2026-08-03", "6"), ("2026-08-04", "7.5")):
            res = self.client.post(
                WORK_LOGS_URL, {"employee": employee["id"], "date": day, "hours": hours},
                format="json", **self._as())
            assert res.status_code == 201, res.content

        slip = self._create_payslip(employee["id"])
        assert slip["worked_hours"] == "13.50"
        assert slip["gross"] == "270.00"   # 13.5 × 20
        assert slip["net"] == "270.00"

    def test_hours_outside_the_period_are_ignored(self):
        employee = self._hourly()
        self.client.post(
            WORK_LOGS_URL, {"employee": employee["id"], "date": "2026-07-20", "hours": "8"},
            format="json", **self._as())
        slip = self._create_payslip(employee["id"])
        assert slip["worked_hours"] == "0.00"

    def test_hourly_employee_requires_an_agreed_rate(self):
        res = self.client.post(
            EMPLOYEES_URL,
            {"name": "بلا أجر", "pay_type": Employee.PAY_HOURLY, "hourly_rate": "0"},
            format="json", **self._as())
        assert res.status_code == 400
        assert "hourly_rate" in res.json()

    def test_same_day_twice_is_a_correction_not_an_addition(self):
        employee = self._hourly()
        payload = {"employee": employee["id"], "date": "2026-08-03", "hours": "6"}
        assert self.client.post(WORK_LOGS_URL, payload, format="json", **self._as()).status_code == 201
        again = self.client.post(WORK_LOGS_URL, payload, format="json", **self._as())
        assert again.status_code == 400


class MonthlyEmployeeTest(PayrollTestBase):
    """الدائم: راتبٌ ثابت تُخصم منه الغيابات والتأخيرات."""

    def test_absence_and_late_are_deducted_at_derived_rates(self):
        employee = self._create_employee()  # 2600 ÷ 26 يوماً = 100/يوم، 8 ساعات
        self.client.post(
            ADJUSTMENTS_URL,
            {"employee": employee["id"], "date": "2026-08-05", "kind": "absence", "days": "2"},
            format="json", **self._as())
        self.client.post(
            ADJUSTMENTS_URL,
            {"employee": employee["id"], "date": "2026-08-06", "kind": "late", "minutes": 120},
            format="json", **self._as())

        slip = self._create_payslip(employee["id"])
        assert slip["gross"] == "2600.00"
        assert slip["absence_days"] == "2.00"
        assert slip["absence_deduction"] == "200.00"       # 2 × 100
        assert slip["late_minutes"] == 120
        assert slip["late_deduction"] == "25.00"           # 120 × (100 ÷ 480)
        assert slip["net"] == "2375.00"

    def test_excused_records_are_logged_without_deduction(self):
        employee = self._create_employee()
        self.client.post(
            ADJUSTMENTS_URL,
            {"employee": employee["id"], "date": "2026-08-05", "kind": "absence",
             "days": "1", "is_deductible": False},
            format="json", **self._as())
        slip = self._create_payslip(employee["id"])
        assert slip["absence_days"] == "1.00"
        assert slip["absence_deduction"] == "0.00"
        assert slip["net"] == "2600.00"

    def test_allowances_and_other_deductions_move_the_net(self):
        employee = self._create_employee()
        slip = self._create_payslip(
            employee["id"], allowances="150.00", other_deductions="50.00")
        assert slip["net"] == "2700.00"

    def test_monthly_employee_requires_a_salary(self):
        res = self.client.post(
            EMPLOYEES_URL, {"name": "بلا راتب", "pay_type": Employee.PAY_MONTHLY},
            format="json", **self._as())
        assert res.status_code == 400
        assert "monthly_salary" in res.json()

    def test_blank_rate_of_the_other_pay_type_is_ignored_not_rejected(self):
        """نموذج الموظف يعرض حقول نوعه وحده، فالحقل الآخر قد يصل فارغاً.

        كان `DecimalField` يردّه بـ«الرجاء إدخال رقم صالح» بلا اسم حقل — خطأ
        على حقلٍ لم يعرضه النموذج للمستخدم أصلاً.
        """
        res = self.client.post(
            EMPLOYEES_URL,
            {"name": "فادي", "pay_type": Employee.PAY_MONTHLY,
             "monthly_salary": "8000", "hourly_rate": "",
             "working_days_per_month": "26", "standard_hours_per_day": "8"},
            format="json", **self._as())
        assert res.status_code == 201, res.content
        assert res.json()["monthly_salary"] == "8000.00"

        hourly = self.client.post(
            EMPLOYEES_URL,
            {"name": "بالساعة", "pay_type": Employee.PAY_HOURLY,
             "hourly_rate": "20", "monthly_salary": ""},
            format="json", **self._as())
        assert hourly.status_code == 201, hourly.content
        assert hourly.json()["hourly_rate"] == "20.00"

    def test_blank_hours_and_days_fall_back_to_the_model_defaults(self):
        res = self.client.post(
            EMPLOYEES_URL,
            {"name": "بالافتراضي", "pay_type": Employee.PAY_MONTHLY,
             "monthly_salary": "2600", "working_days_per_month": "",
             "standard_hours_per_day": ""},
            format="json", **self._as())
        assert res.status_code == 201, res.content
        assert res.json()["working_days_per_month"] == "26.00"
        assert res.json()["standard_hours_per_day"] == "8.00"

    def test_switching_pay_type_does_not_wipe_the_other_rate(self):
        """التعديل بحقول النوع وحدها يترك أجر النوع الآخر كما هو."""
        row = self._create_employee(name="متنقّل")
        res = self.client.patch(
            f"{EMPLOYEES_URL}{row['id']}/",
            {"pay_type": Employee.PAY_HOURLY, "hourly_rate": "30"},
            format="json", **self._as())
        assert res.status_code == 200, res.content
        assert res.json()["hourly_rate"] == "30.00"
        assert res.json()["monthly_salary"] == "2600.00"


class PayslipPostingTest(PayrollTestBase):
    """القيد المحاسبي لاعتماد الكشف وصرفه."""

    def _posted_slip(self):
        employee = self._create_employee()
        slip = self._create_payslip(employee["id"])
        res = self.client.post(f"{PAYSLIPS_URL}{slip['id']}/post_slip/", {},
                               format="json", **self._as())
        assert res.status_code == 200, res.content
        return employee, res.json()

    def test_posting_debits_the_expense_and_credits_the_employee(self):
        employee, slip = self._posted_slip()
        assert slip["status"] == "posted"

        lines = JournalLine.objects.filter(
            tenant=self.tenant, journal__reference_type="PAYROLL_PAYSLIP",
            journal__reference_id=slip["id"])
        assert lines.count() == 2

        expense = Account.objects.get(tenant=self.tenant, code=PAYROLL_EXPENSE_CODE)
        debit_line = lines.get(account=expense)
        credit_line = lines.get(account_id=employee["account"])
        assert debit_line.debit == Decimal("2600.00")
        assert credit_line.credit == Decimal("2600.00")
        assert sum(line.debit for line in lines) == sum(line.credit for line in lines)

    def test_employee_balance_reflects_what_is_owed_then_paid(self):
        employee, slip = self._posted_slip()

        listed = self.client.get(EMPLOYEES_URL, **self._as()).json()
        assert listed[0]["balance"] == "2600.00"

        res = self.client.post(
            PAYMENTS_URL,
            {"employee": employee["id"], "payslip": slip["id"],
             "date": "2026-09-01", "amount": "1000.00"},
            format="json", **self._as())
        assert res.status_code == 201, res.content

        payment_lines = JournalLine.objects.filter(
            tenant=self.tenant, journal__reference_type="PAYROLL_PAYMENT",
            journal__reference_id=res.json()["id"])
        assert payment_lines.get(account_id=employee["account"]).debit == Decimal("1000.00")
        assert sum(line.debit for line in payment_lines) == sum(
            line.credit for line in payment_lines)

        listed = self.client.get(EMPLOYEES_URL, **self._as()).json()
        assert listed[0]["balance"] == "1600.00"

    def test_posted_slip_is_frozen_until_unposted(self):
        _, slip = self._posted_slip()
        patched = self.client.patch(
            f"{PAYSLIPS_URL}{slip['id']}/", {"allowances": "10.00"},
            format="json", **self._as())
        assert patched.status_code == 400
        deleted = self.client.delete(f"{PAYSLIPS_URL}{slip['id']}/", **self._as())
        assert deleted.status_code == 400

    def test_unposting_removes_the_journal_and_reopens_the_slip(self):
        _, slip = self._posted_slip()
        res = self.client.post(f"{PAYSLIPS_URL}{slip['id']}/unpost/", {},
                               format="json", **self._as())
        assert res.status_code == 200, res.content
        assert res.json()["status"] == "draft"
        assert not JournalLine.objects.filter(
            journal__reference_type="PAYROLL_PAYSLIP",
            journal__reference_id=slip["id"]).exists()

    def test_unposting_is_blocked_while_a_payment_exists(self):
        employee, slip = self._posted_slip()
        self.client.post(
            PAYMENTS_URL,
            {"employee": employee["id"], "payslip": slip["id"],
             "date": "2026-09-01", "amount": "500.00"},
            format="json", **self._as())
        res = self.client.post(f"{PAYSLIPS_URL}{slip['id']}/unpost/", {},
                               format="json", **self._as())
        assert res.status_code == 400

    def test_deleting_a_payment_removes_its_journal(self):
        employee, slip = self._posted_slip()
        payment = self.client.post(
            PAYMENTS_URL,
            {"employee": employee["id"], "payslip": slip["id"],
             "date": "2026-09-01", "amount": "500.00"},
            format="json", **self._as()).json()
        res = self.client.delete(f"{PAYMENTS_URL}{payment['id']}/", **self._as())
        assert res.status_code == 204
        assert not JournalLine.objects.filter(
            journal__reference_type="PAYROLL_PAYMENT",
            journal__reference_id=payment["id"]).exists()

    def test_employee_with_history_cannot_be_deleted(self):
        employee, _ = self._posted_slip()
        res = self.client.delete(f"{EMPLOYEES_URL}{employee['id']}/", **self._as())
        assert res.status_code == 400


class PayrollGuardsTest(PayrollTestBase):
    """العزل والصلاحيات."""

    def test_viewer_cannot_open_payroll_at_all(self):
        res = self.client.get(EMPLOYEES_URL, **self._as(self.viewer))
        assert res.status_code == 403

    def test_viewer_cannot_create_an_employee(self):
        res = self.client.post(
            EMPLOYEES_URL, {"name": "خلسة", "monthly_salary": "100"},
            format="json", **self._as(self.viewer))
        assert res.status_code == 403

    def test_another_company_employee_is_rejected_on_write(self):
        outsider_boss = User.objects.create_user(username="pr-other", password="x")
        other = create_company("شركة أخرى", outsider_boss)
        UserCompanyMembership.objects.create(
            user=self.boss, tenant=other, role="manager")

        self.client.force_authenticate(user=self.boss)
        foreign = self.client.post(
            EMPLOYEES_URL, {"name": "غريب", "monthly_salary": "1000"}, format="json",
            HTTP_X_TENANT_ID=str(other.TenantID)).json()

        res = self.client.post(
            WORK_LOGS_URL,
            {"employee": foreign["id"], "date": "2026-08-03", "hours": "5"},
            format="json", **self._as())
        assert res.status_code == 400

    def test_employees_of_other_companies_are_not_listed(self):
        self._create_employee(name="داخلي")
        outsider_boss = User.objects.create_user(username="pr-other2", password="x")
        other = create_company("شركة ثالثة", outsider_boss)
        Employee.objects.create(tenant=other, name="خارجي", monthly_salary=Decimal("100"))

        names = [row["name"] for row in self.client.get(EMPLOYEES_URL, **self._as()).json()]
        assert names == ["داخلي"]


class PayslipPreviewTest(PayrollTestBase):
    """المعاينة تُظهر نفس أرقام الحفظ — مصدر احتساب واحد لا اثنان."""

    def test_preview_matches_the_saved_slip(self):
        employee = self._create_employee()
        self.client.post(
            ADJUSTMENTS_URL,
            {"employee": employee["id"], "date": "2026-08-05", "kind": "absence", "days": "1"},
            format="json", **self._as())

        preview = self.client.get(
            f"{PAYSLIPS_URL}preview/?employee={employee['id']}"
            f"&period_start=2026-08-01&period_end=2026-08-31",
            **self._as()).json()
        slip = self._create_payslip(employee["id"])

        assert preview["net"] == slip["net"] == "2500.00"
        assert Payslip.objects.get(pk=slip["id"]).status == Payslip.STATUS_DRAFT
