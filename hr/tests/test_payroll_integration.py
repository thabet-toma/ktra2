"""M6/M7 — العقود، وتكامل الحضور بالرواتب، والسلف، ومسير الرواتب.

**أخطر ما هنا محاسبة السلفة**، وقاعدتها تُثبَّت باختبارٍ صريح:

    صرف السلفة:   مدين حساب الموظف / دائن الصندوق
    ترحيل القسيمة: مدين 5201 / دائن حساب الموظف بـ**`net` كاملاً**
    القسط:        **بلا قيد** — يتصافى داخل حساب الموظف نفسه

أيُّ «قيد سداد» إضافي هنا عدٌّ مزدوج يُبخس المصروف ويضاعف السداد.
"""
from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.test import APITestCase

from accounting.models import Account, FiscalPeriod, JournalHeader, JournalLine
from core.models import TenantModule
from hr.contracts import effective_terms, expiring_contracts, overtime_multiplier
from hr.models import (
    Advance, AttendanceDay, Contract, ContractComponent, Employee, EmployeeRequest,
    PayrollPayment, PayrollRun, Payslip, PayslipAdvance, Shift, ShiftAssignment,
)
from hr.payroll import compute_payslip, post_payslip, unpost_payslip
from tenants.models import Tenant, UserCompanyMembership
from tenants.services import create_company

CONTRACTS = "/api/hr/contracts/"
RUNS = "/api/hr/payroll-runs/"
ADVANCES = "/api/hr/advances/"
REQUESTS = "/api/hr/requests/"

PERIOD_START = date(2026, 3, 1)
PERIOD_END = date(2026, 3, 31)


@override_settings(TIME_ZONE="Asia/Hebron", USE_TZ=True)
class PayrollIntegrationBase(APITestCase):
    def setUp(self):
        self.manager = User.objects.create_user("pay-manager", password="x")
        # شركة كاملة بشجرة حسابات — الرواتب تحتاج 5201 وصندوقاً.
        self.tenant = create_company("شركة الرواتب", self.manager)
        TenantModule.objects.create(
            tenant=self.tenant, module_key="hr_suite", enabled=True)
        self.employee = Employee.objects.create(
            tenant=self.tenant, code="E1", name="سامي",
            pay_type=Employee.PAY_MONTHLY, monthly_salary=Decimal("2600"),
            working_days_per_month=Decimal("26"), standard_hours_per_day=Decimal("8"),
            hire_date=date(2024, 1, 1))
        # كل قيدٍ يحتاج فترةً مالية مفتوحة تغطّيه (`accounting` يحرسها) —
        # والفترات تُنشأ من شاشتها لا من `create_company`.
        FiscalPeriod.objects.create(
            tenant=self.tenant, name="2026", start_date=date(2026, 1, 1),
            end_date=date(2026, 12, 31), status="Open")
        self.client.force_authenticate(self.manager)

    def headers(self):
        return {"HTTP_X_TENANT_ID": str(self.tenant.pk)}

    def make_shift(self, **overrides):
        values = dict(
            tenant=self.tenant, name="صباحي", start1=time(9), end1=time(17),
            overtime_multiplier=Decimal("1.5"), overtime_after_minutes=0)
        values.update(overrides)
        shift = Shift.objects.create(**values)
        ShiftAssignment.objects.create(
            tenant=self.tenant, employee=self.employee, shift=shift,
            start_date=date(2024, 1, 1))
        return shift

    def make_contract(self, **overrides):
        values = dict(
            tenant=self.tenant, employee=self.employee, start_date=date(2026, 1, 1),
            pay_type=Employee.PAY_MONTHLY, monthly_salary=Decimal("3000"),
            status=Contract.STATUS_ACTIVE)
        values.update(overrides)
        return Contract.objects.create(**values)

    def make_payslip(self):
        from hr.payroll import apply_computation

        slip = Payslip(
            tenant=self.tenant, employee=self.employee,
            period_start=PERIOD_START, period_end=PERIOD_END)
        apply_computation(slip)
        slip.save()
        return slip


class ContractTermsTest(PayrollIntegrationBase):
    def test_without_a_contract_the_employee_card_rules(self):
        """شركةٌ لم تبنِ عقودها يبقى راتبها يُحسب كما كان بالضبط."""
        terms = effective_terms(self.employee, PERIOD_END)
        self.assertEqual(terms.source, "employee")
        self.assertEqual(terms.monthly_salary, Decimal("2600"))

    def test_an_active_contract_overrides_the_card(self):
        self.make_contract()
        terms = effective_terms(self.employee, PERIOD_END)
        self.assertEqual(terms.source, "contract")
        self.assertEqual(terms.monthly_salary, Decimal("3000"))

    def test_a_draft_contract_does_not_override(self):
        self.make_contract(status=Contract.STATUS_DRAFT)
        self.assertEqual(effective_terms(self.employee, PERIOD_END).source, "employee")

    def test_a_contract_outside_its_dates_does_not_apply(self):
        self.make_contract(start_date=date(2026, 6, 1))
        self.assertEqual(effective_terms(self.employee, PERIOD_END).source, "employee")

    def test_payslip_uses_the_contract_salary(self):
        self.make_contract()
        numbers = compute_payslip(self.employee, PERIOD_START, PERIOD_END)
        self.assertEqual(numbers["gross"], Decimal("3000.00"))
        self.assertEqual(numbers["rate"], Decimal("3000.00"))

    def test_contract_components_flow_into_allowances_and_deductions(self):
        contract = self.make_contract()
        ContractComponent.objects.create(
            contract=contract, kind=ContractComponent.KIND_EARNING,
            name="بدل مواصلات", amount=Decimal("200"))
        ContractComponent.objects.create(
            contract=contract, kind=ContractComponent.KIND_DEDUCTION,
            name="تأمين", amount=Decimal("50"))

        numbers = compute_payslip(self.employee, PERIOD_START, PERIOD_END)
        self.assertEqual(numbers["allowances"], Decimal("200.00"))
        self.assertEqual(numbers["other_deductions"], Decimal("50.00"))
        self.assertEqual(numbers["net"], Decimal("3150.00"))

    def test_manual_allowance_adds_to_the_contract_component(self):
        contract = self.make_contract()
        ContractComponent.objects.create(
            contract=contract, kind=ContractComponent.KIND_EARNING,
            name="بدل", amount=Decimal("200"))
        numbers = compute_payslip(
            self.employee, PERIOD_START, PERIOD_END, allowances=Decimal("100"))
        self.assertEqual(numbers["allowances"], Decimal("300.00"))

    def test_activate_supersedes_the_previous_contract(self):
        """موظفٌ بعقدين نشطين = رقمان للراتب يختار بينهما ترتيبُ الصفوف."""
        first = self.make_contract()
        second = self.make_contract(
            status=Contract.STATUS_DRAFT, start_date=date(2026, 7, 1),
            monthly_salary=Decimal("3500"))

        response = self.client.post(
            f"{CONTRACTS}{second.pk}/activate/", {}, format="json", **self.headers())
        self.assertEqual(response.status_code, 200, response.content)

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(second.status, Contract.STATUS_ACTIVE)
        self.assertEqual(first.status, Contract.STATUS_EXPIRED)
        self.assertEqual(first.end_date, date(2026, 6, 30), "لا يومَ يغطّيه عقدان")

    def test_terminate_ends_the_contract_and_the_card_returns(self):
        contract = self.make_contract()
        response = self.client.post(
            f"{CONTRACTS}{contract.pk}/terminate/", {"end_date": "2026-02-28"},
            format="json", **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(effective_terms(self.employee, PERIOD_END).source, "employee")

    def test_an_active_contract_cannot_be_deleted(self):
        contract = self.make_contract()
        response = self.client.delete(f"{CONTRACTS}{contract.pk}/", **self.headers())
        self.assertEqual(response.status_code, 400, response.content)

    def test_status_cannot_be_written_by_patch(self):
        contract = self.make_contract(status=Contract.STATUS_DRAFT)
        response = self.client.patch(
            f"{CONTRACTS}{contract.pk}/", {"status": Contract.STATUS_ACTIVE},
            format="json", **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        contract.refresh_from_db()
        self.assertEqual(contract.status, Contract.STATUS_DRAFT)

    def test_expiry_alerts_list_contracts_inside_the_window(self):
        from django.utils import timezone

        soon = timezone.localdate() + timedelta(days=10)
        self.make_contract(end_date=soon)
        far = Employee.objects.create(
            tenant=self.tenant, code="E2", name="بعيد", monthly_salary=1000)
        Contract.objects.create(
            tenant=self.tenant, employee=far, start_date=date(2026, 1, 1),
            end_date=timezone.localdate() + timedelta(days=200),
            monthly_salary=Decimal("1000"), status=Contract.STATUS_ACTIVE)

        response = self.client.get(f"{CONTRACTS}alerts/?within=30", **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["contracts"][0]["employee"], self.employee.pk)

    def test_expiring_ignores_open_ended_contracts(self):
        self.make_contract(end_date=None)
        self.assertEqual(list(expiring_contracts(self.tenant.pk)), [])


class AttendanceToPayrollTest(PayrollIntegrationBase):
    def test_derived_absence_is_deducted(self):
        self.make_shift()
        AttendanceDay.objects.create(
            tenant=self.tenant, employee=self.employee, date=date(2026, 3, 3),
            status=AttendanceDay.STATUS_ABSENT, absence_days=Decimal("1"))

        numbers = compute_payslip(self.employee, PERIOD_START, PERIOD_END)
        self.assertEqual(numbers["absence_days"], Decimal("1.00"))
        # 2600 / 26 = 100
        self.assertEqual(numbers["absence_deduction"], Decimal("100.00"))
        self.assertEqual(numbers["net"], Decimal("2500.00"))

    def test_derived_lateness_is_deducted_by_the_minute(self):
        self.make_shift()
        AttendanceDay.objects.create(
            tenant=self.tenant, employee=self.employee, date=date(2026, 3, 4),
            status=AttendanceDay.STATUS_LATE, late_minutes=60)

        numbers = compute_payslip(self.employee, PERIOD_START, PERIOD_END)
        self.assertEqual(numbers["late_minutes"], 60)
        # أجر الدقيقة = 100 / (8×60) ⇒ ستون دقيقة = 12.50
        self.assertEqual(numbers["late_deduction"], Decimal("12.50"))

    def test_manual_adjustments_still_add_on_top(self):
        """اليدويّ تصحيحٌ يُجمع، لا يُلغيه المشتقّ ولا يُلغيه."""
        from hr.models import AttendanceAdjustment

        self.make_shift()
        AttendanceDay.objects.create(
            tenant=self.tenant, employee=self.employee, date=date(2026, 3, 3),
            status=AttendanceDay.STATUS_ABSENT, absence_days=Decimal("1"))
        AttendanceAdjustment.objects.create(
            tenant=self.tenant, employee=self.employee, date=date(2026, 3, 10),
            kind=AttendanceAdjustment.KIND_ABSENCE, days=Decimal("1"), is_deductible=True)

        numbers = compute_payslip(self.employee, PERIOD_START, PERIOD_END)
        self.assertEqual(numbers["absence_days"], Decimal("2.00"))
        self.assertEqual(numbers["absence_deduction"], Decimal("200.00"))

    def test_overtime_is_priced_by_the_shift_multiplier(self):
        """لم يكن للأجر الإضافي وجودٌ في المحرّك — كان يُستدلّ عليه ولا يُسعَّر."""
        self.make_shift()
        AttendanceDay.objects.create(
            tenant=self.tenant, employee=self.employee, date=date(2026, 3, 5),
            status=AttendanceDay.STATUS_PRESENT, worked_minutes=600,
            scheduled_minutes=480, overtime_minutes=120)

        numbers = compute_payslip(self.employee, PERIOD_START, PERIOD_END)
        self.assertEqual(numbers["overtime_minutes"], 120)
        # 120 دقيقة × (100/480) × 1.5 = 37.50
        self.assertEqual(numbers["overtime_pay"], Decimal("37.50"))
        self.assertEqual(numbers["net"], Decimal("2637.50"))

    def test_the_contract_multiplier_beats_the_shift(self):
        self.make_shift()
        self.make_contract(overtime_multiplier=Decimal("2"))
        self.assertEqual(
            overtime_multiplier(self.employee, PERIOD_END), Decimal("2"))

    def test_without_a_shift_or_contract_overtime_is_paid_plain(self):
        """صفرٌ هنا كان يبتلع أجراً استُحقّ — الساعة بلا مضاعفٍ ساعةُ عمل."""
        self.assertEqual(
            overtime_multiplier(self.employee, PERIOD_END), Decimal("1"))

    def test_excused_days_never_reach_the_deduction(self):
        """`AttendanceDay` يصفّر أيام الإجازة والعطلة، فلا تصل إلى المال."""
        self.make_shift()
        for day, status in (
            (date(2026, 3, 6), AttendanceDay.STATUS_OFF),
            (date(2026, 3, 7), AttendanceDay.STATUS_HOLIDAY),
            (date(2026, 3, 8), AttendanceDay.STATUS_LEAVE),
        ):
            AttendanceDay.objects.create(
                tenant=self.tenant, employee=self.employee, date=day,
                status=status, absence_days=Decimal("0"))

        numbers = compute_payslip(self.employee, PERIOD_START, PERIOD_END)
        self.assertEqual(numbers["absence_deduction"], Decimal("0.00"))
        self.assertEqual(numbers["net"], Decimal("2600.00"))

    def test_hourly_employee_still_paid_from_work_logs(self):
        """الجزئي لم يتغيّر عقده: ساعاتُه المسجّلة هي استحقاقه."""
        from hr.models import WorkLog

        self.employee.pay_type = Employee.PAY_HOURLY
        self.employee.hourly_rate = Decimal("20")
        self.employee.save(update_fields=["pay_type", "hourly_rate"])
        WorkLog.objects.create(
            tenant=self.tenant, employee=self.employee, date=date(2026, 3, 2),
            hours=Decimal("8"))

        numbers = compute_payslip(self.employee, PERIOD_START, PERIOD_END)
        self.assertEqual(numbers["gross"], Decimal("160.00"))
        self.assertEqual(numbers["absence_deduction"], Decimal("0.00"))

    def test_recomputation_is_stable(self):
        self.make_shift()
        AttendanceDay.objects.create(
            tenant=self.tenant, employee=self.employee, date=date(2026, 3, 3),
            status=AttendanceDay.STATUS_ABSENT, absence_days=Decimal("1"))
        first = compute_payslip(self.employee, PERIOD_START, PERIOD_END)
        for _ in range(3):
            self.assertEqual(
                compute_payslip(self.employee, PERIOD_START, PERIOD_END), first)


class AdvanceAccountingTest(PayrollIntegrationBase):
    """القاعدة التي لا تُكسر: القسط تصافٍ داخل حساب الموظف بلا قيدٍ ثانٍ."""

    def make_advance(self, total="600", installment="200"):
        return Advance.objects.create(
            tenant=self.tenant, employee=self.employee, date=date(2026, 2, 1),
            total=Decimal(total), monthly_installment=Decimal(installment),
            remaining=Decimal(total))

    def disburse(self, advance):
        response = self.client.post(
            f"{ADVANCES}{advance.pk}/disburse/", {}, format="json", **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        return response

    def employee_balance(self):
        from hr.payroll import employee_balance

        # النسخة تُحدَّث قبل القراءة: حسابُ الموظف يُنشأ في أول عملية تمسّه،
        # وكائنٌ محمَّلٌ قبلها يحمل `account=None`.
        self.employee.refresh_from_db()
        return employee_balance(self.employee)

    def test_disbursement_debits_the_employee_and_credits_cash(self):
        advance = self.make_advance()
        self.disburse(advance)

        self.employee.refresh_from_db()
        payment = PayrollPayment.objects.get(advance=advance)
        lines = JournalLine.objects.filter(
            journal__reference_type="PAYROLL_PAYMENT",
            journal__reference_id=payment.pk,
        )
        self.assertEqual(lines.count(), 2)
        employee_line = lines.get(account=self.employee.account)
        self.assertEqual(employee_line.debit, Decimal("600.00"))
        self.assertEqual(employee_line.credit, Decimal("0.00"))
        # ورصيده صار مديناً بستمئة (الرصيد = دائن − مدين).
        self.assertEqual(self.employee_balance(), Decimal("-600.00"))

    def test_an_undisbursed_advance_is_not_deducted(self):
        """سلفةٌ لم يُصرَف مالُها ليست دَيناً بعد."""
        self.make_advance()
        numbers = compute_payslip(self.employee, PERIOD_START, PERIOD_END)
        self.assertEqual(numbers["advance_deduction"], Decimal("0.00"))
        self.assertEqual(numbers["net_payable"], numbers["net"])

    def test_installment_reduces_payable_not_the_journal(self):
        advance = self.make_advance()
        self.disburse(advance)

        slip = self.make_payslip()
        self.assertEqual(slip.net, Decimal("2600.00"))
        self.assertEqual(slip.advance_deduction, Decimal("200.00"))
        self.assertEqual(slip.net_payable, Decimal("2400.00"))

        post_payslip(slip, user=self.manager)

        lines = JournalLine.objects.filter(
            journal__reference_type="PAYROLL_PAYSLIP", journal__reference_id=slip.pk)
        self.assertEqual(lines.count(), 2, "سطران لا ثلاثة — لا قيد سدادٍ ثالث")
        employee_line = lines.get(account=self.employee.account)
        self.assertEqual(
            employee_line.credit, Decimal("2600.00"),
            "القيد بكامل الصافي — القسط لا يُبخس المصروف")

    def test_the_debt_nets_inside_the_employee_account(self):
        """‎−600 (صرف) + 2600 (استحقاق) = 2000 — والقسط ظاهرٌ في الفرق."""
        advance = self.make_advance()
        self.disburse(advance)
        slip = self.make_payslip()
        post_payslip(slip, user=self.manager)

        self.assertEqual(self.employee_balance(), Decimal("2000.00"))
        advance.refresh_from_db()
        self.assertEqual(advance.remaining, Decimal("400.00"))

    def test_no_extra_journal_is_created_for_the_installment(self):
        advance = self.make_advance()
        self.disburse(advance)
        before = JournalHeader.objects.count()

        slip = self.make_payslip()
        post_payslip(slip, user=self.manager)
        # قيدٌ واحد فقط للقسيمة.
        self.assertEqual(JournalHeader.objects.count(), before + 1)

    def test_the_last_installment_settles_the_advance(self):
        advance = self.make_advance(total="200", installment="200")
        self.disburse(advance)
        slip = self.make_payslip()
        post_payslip(slip, user=self.manager)

        advance.refresh_from_db()
        self.assertEqual(advance.remaining, Decimal("0.00"))
        self.assertEqual(advance.status, Advance.STATUS_SETTLED)

    def test_installment_never_exceeds_the_remaining(self):
        advance = self.make_advance(total="150", installment="200")
        self.disburse(advance)
        numbers = compute_payslip(self.employee, PERIOD_START, PERIOD_END)
        self.assertEqual(numbers["advance_deduction"], Decimal("150.00"))

    def test_installment_never_exceeds_the_net(self):
        """موظفٌ يقبض صفراً بسبب سلفةٍ مشكلةٌ إنسانية قبل أن تكون محاسبية."""
        advance = self.make_advance(total="9000", installment="9000")
        self.disburse(advance)
        numbers = compute_payslip(self.employee, PERIOD_START, PERIOD_END)
        self.assertEqual(numbers["advance_deduction"], Decimal("2600.00"))
        self.assertEqual(numbers["net_payable"], Decimal("0.00"))

    def test_unposting_returns_exactly_what_was_taken(self):
        advance = self.make_advance()
        self.disburse(advance)
        slip = self.make_payslip()
        post_payslip(slip, user=self.manager)
        self.assertEqual(PayslipAdvance.objects.count(), 1)

        unpost_payslip(slip, user=self.manager)
        advance.refresh_from_db()
        self.assertEqual(advance.remaining, Decimal("600.00"))
        self.assertEqual(advance.status, Advance.STATUS_OPEN)
        self.assertEqual(PayslipAdvance.objects.count(), 0)

    def test_unposting_reopens_a_settled_advance(self):
        advance = self.make_advance(total="200", installment="200")
        self.disburse(advance)
        slip = self.make_payslip()
        post_payslip(slip, user=self.manager)
        advance.refresh_from_db()
        self.assertEqual(advance.status, Advance.STATUS_SETTLED)

        unpost_payslip(slip, user=self.manager)
        advance.refresh_from_db()
        self.assertEqual(advance.status, Advance.STATUS_OPEN)
        self.assertEqual(advance.remaining, Decimal("200.00"))

    def test_a_disbursed_advance_cannot_be_disbursed_twice(self):
        advance = self.make_advance()
        self.disburse(advance)
        again = self.client.post(
            f"{ADVANCES}{advance.pk}/disburse/", {}, format="json", **self.headers())
        self.assertEqual(again.status_code, 400, again.content)

    def test_a_disbursed_advance_cannot_be_cancelled(self):
        advance = self.make_advance()
        self.disburse(advance)
        response = self.client.post(
            f"{ADVANCES}{advance.pk}/cancel/", {}, format="json", **self.headers())
        self.assertEqual(response.status_code, 400, response.content)

    def test_computing_a_draft_ten_times_does_not_touch_the_advance(self):
        """الخصم يرتبط بالترحيل لا بالاحتساب — وإلا نقص الرصيد عشراً."""
        advance = self.make_advance()
        self.disburse(advance)
        for _ in range(10):
            compute_payslip(self.employee, PERIOD_START, PERIOD_END)
        advance.refresh_from_db()
        self.assertEqual(advance.remaining, Decimal("600.00"))


class PayrollRunTest(PayrollIntegrationBase):
    def setUp(self):
        super().setUp()
        self.second = Employee.objects.create(
            tenant=self.tenant, code="E2", name="ليان",
            pay_type=Employee.PAY_MONTHLY, monthly_salary=Decimal("1800"),
            working_days_per_month=Decimal("26"))
        from hr.payroll import ensure_employee_account

        ensure_employee_account(self.employee)
        ensure_employee_account(self.second)

    def make_run(self, **overrides):
        payload = {
            "name": "مسير آذار",
            "period_start": PERIOD_START.isoformat(),
            "period_end": PERIOD_END.isoformat(),
        }
        payload.update(overrides)
        response = self.client.post(RUNS, payload, format="json", **self.headers())
        self.assertEqual(response.status_code, 201, response.content)
        return response.data

    def test_compute_creates_a_payslip_per_employee(self):
        run = self.make_run()
        response = self.client.post(
            f"{RUNS}{run['id']}/compute/", {}, format="json", **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["created"], 2)
        self.assertEqual(Payslip.objects.filter(run_id=run["id"]).count(), 2)

    def test_recompute_updates_instead_of_duplicating(self):
        run = self.make_run()
        self.client.post(f"{RUNS}{run['id']}/compute/", {}, format="json", **self.headers())
        again = self.client.post(
            f"{RUNS}{run['id']}/compute/", {}, format="json", **self.headers())
        self.assertEqual(again.data["created"], 0)
        self.assertEqual(again.data["updated"], 2)
        self.assertEqual(Payslip.objects.count(), 2)

    def test_department_scope_limits_the_run(self):
        from hr.models import Department

        department = Department.objects.create(tenant=self.tenant, name="المبيعات")
        self.employee.department = department
        self.employee.save(update_fields=["department"])

        run = self.make_run(department=department.pk)
        response = self.client.post(
            f"{RUNS}{run['id']}/compute/", {}, format="json", **self.headers())
        self.assertEqual(response.data["created"], 1)

    def test_post_run_posts_every_draft(self):
        run = self.make_run()
        self.client.post(f"{RUNS}{run['id']}/compute/", {}, format="json", **self.headers())
        response = self.client.post(
            f"{RUNS}{run['id']}/post/", {}, format="json", **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["posted"], 2)
        self.assertEqual(response.data["status"], PayrollRun.STATUS_POSTED)
        self.assertEqual(
            Payslip.objects.filter(status=Payslip.STATUS_POSTED).count(), 2)

    def test_a_failing_payslip_does_not_sink_the_run(self):
        """ترحيلٌ يتوقّف عند أول فشل يترك المسير نصفه مرحَّلاً ولا يقول أين وقف."""
        self.second.monthly_salary = Decimal("0")
        self.second.pay_type = Employee.PAY_HOURLY
        self.second.hourly_rate = Decimal("0")
        self.second.save(update_fields=["monthly_salary", "pay_type", "hourly_rate"])

        run = self.make_run()
        self.client.post(f"{RUNS}{run['id']}/compute/", {}, format="json", **self.headers())
        response = self.client.post(
            f"{RUNS}{run['id']}/post/", {}, format="json", **self.headers())
        self.assertEqual(response.data["posted"], 1)
        self.assertEqual(len(response.data["failed"]), 1)
        self.assertEqual(response.data["failed"][0]["employee_name"], "ليان")

    def test_posted_run_cannot_be_recomputed_or_deleted(self):
        run = self.make_run()
        self.client.post(f"{RUNS}{run['id']}/compute/", {}, format="json", **self.headers())
        self.client.post(f"{RUNS}{run['id']}/post/", {}, format="json", **self.headers())

        recompute = self.client.post(
            f"{RUNS}{run['id']}/compute/", {}, format="json", **self.headers())
        self.assertEqual(recompute.status_code, 400, recompute.content)
        deleted = self.client.delete(f"{RUNS}{run['id']}/", **self.headers())
        self.assertEqual(deleted.status_code, 400, deleted.content)

    def test_unpost_run_reverts_every_payslip(self):
        run = self.make_run()
        self.client.post(f"{RUNS}{run['id']}/compute/", {}, format="json", **self.headers())
        self.client.post(f"{RUNS}{run['id']}/post/", {}, format="json", **self.headers())

        response = self.client.post(
            f"{RUNS}{run['id']}/unpost/", {}, format="json", **self.headers())
        self.assertEqual(response.data["reverted"], 2)
        self.assertEqual(
            Payslip.objects.filter(status=Payslip.STATUS_POSTED).count(), 0)

    def test_deleting_a_draft_run_frees_its_payslips(self):
        """القسيمة مستندٌ قائمٌ بذاته — الوعاء تنظيمٌ فوقها لا مالكٌ لها."""
        run = self.make_run()
        self.client.post(f"{RUNS}{run['id']}/compute/", {}, format="json", **self.headers())
        response = self.client.delete(f"{RUNS}{run['id']}/", **self.headers())
        self.assertEqual(response.status_code, 204, response.content)
        self.assertEqual(Payslip.objects.count(), 2)
        self.assertEqual(Payslip.objects.filter(run__isnull=False).count(), 0)

    def test_an_existing_posted_payslip_is_skipped_with_a_reason(self):
        slip = Payslip(
            tenant=self.tenant, employee=self.employee,
            period_start=PERIOD_START, period_end=PERIOD_END, net=Decimal("2600"))
        slip.save()
        post_payslip(slip, user=self.manager)

        run = self.make_run()
        response = self.client.post(
            f"{RUNS}{run['id']}/compute/", {}, format="json", **self.headers())
        self.assertEqual(response.data["created"], 1)
        self.assertEqual(len(response.data["skipped"]), 1)
        self.assertIn("مرحَّل", response.data["skipped"][0]["reason"])
