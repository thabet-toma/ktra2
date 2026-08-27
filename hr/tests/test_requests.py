"""M5 — الإجازات والطلبات ودورة الاعتماد والسلف.

أخطر ثلاثة أشياء تحرسها هذه الاختبارات:
1. **لا موظفٌ يقدّم طلباً باسم زميله** ولا يقرأ طلباته.
2. **الرفض يقطع السلسلة** — مستوى ثانٍ يُسأل بعد رفض الأول يفتح باب اعتمادٍ
   يناقض رفضاً قائماً.
3. **الرصيد يُحجَز بالطلب قيد المراجعة** — وإلا مرّت ثلاثة طلبات بكامل الرصيد
   لأن كلاً منها وحده يكفيه.
"""
from datetime import date, time, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from bridge.models import FirestoreMirrorDoc
from core.models import TenantModule
from hr.leave import available_days, leave_balance
from hr.models import (
    Advance, ApprovalRule, ApprovalStep, AttendanceDay, Employee, EmployeeRequest,
    Holiday, LeaveBalanceAdjustment, LeaveType, Shift, ShiftAssignment,
)
from tenants.models import Tenant, UserCompanyMembership

REQUESTS = "/api/hr/requests/"
LEAVE_TYPES = "/api/hr/leave-types/"
HOLIDAYS = "/api/hr/holidays/"
RULES = "/api/hr/approval-rules/"
BALANCES = "/api/hr/leave-adjustments/balances/"
ADVANCES = "/api/hr/advances/"


@override_settings(TIME_ZONE="Asia/Hebron", USE_TZ=True)
class RequestsTestBase(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(CompanyName="شركة الطلبات")
        self.license = TenantModule.objects.create(
            tenant=self.tenant, module_key="hr_suite", enabled=True)
        self.manager = User.objects.create_user("req-manager", password="x")
        UserCompanyMembership.objects.create(
            user=self.manager, tenant=self.tenant, role="manager")
        self.worker_user = User.objects.create_user("req-worker", password="x")
        UserCompanyMembership.objects.create(
            user=self.worker_user, tenant=self.tenant, role="ess")
        self.employee = Employee.objects.create(
            tenant=self.tenant, code="E1", name="سامي", monthly_salary=3000,
            user=self.worker_user, hire_date=date(2024, 1, 1))
        self.annual = LeaveType.objects.create(
            tenant=self.tenant, name="سنوية", is_paid=True, annual_grant=Decimal("14"))
        self.client.force_authenticate(self.manager)

    def headers(self):
        return {"HTTP_X_TENANT_ID": str(self.tenant.pk)}

    def as_worker(self):
        self.client.force_authenticate(self.worker_user)

    def as_manager(self):
        self.client.force_authenticate(self.manager)

    def rows(self, response):
        data = response.data
        return data["results"] if isinstance(data, dict) and "results" in data else data

    def make_leave_request(self, *, days=3, start=None, submit=True, leave_type=None):
        start = start or date(timezone.localdate().year, 5, 4)
        payload = {
            "employee": self.employee.pk,
            "kind": EmployeeRequest.KIND_LEAVE,
            "leave_type": (leave_type or self.annual).pk,
            "date_from": start.isoformat(),
            "date_to": (start + timedelta(days=days - 1)).isoformat(),
            "description": "سفر",
        }
        response = self.client.post(REQUESTS, payload, format="json", **self.headers())
        self.assertEqual(response.status_code, 201, response.content)
        if submit:
            submitted = self.client.post(
                f"{REQUESTS}{response.data['id']}/submit/", {}, format="json", **self.headers())
            self.assertEqual(submitted.status_code, 200, submitted.content)
            return submitted.data
        return response.data


class LeaveBalanceTest(RequestsTestBase):
    def test_annual_grant_is_the_starting_balance(self):
        balance = leave_balance(self.employee, self.annual)
        self.assertEqual(balance["accrued"], Decimal("14"))
        self.assertEqual(balance["remaining"], Decimal("14"))

    def test_monthly_accrual_counts_service_months_in_the_year(self):
        monthly = LeaveType.objects.create(
            tenant=self.tenant, name="شهرية", monthly_accrual=Decimal("1.5"))
        balance = leave_balance(
            self.employee, monthly, year=2026, today=date(2026, 4, 20))
        # كانون الثاني..نيسان = أربعة شهور.
        self.assertEqual(balance["accrued"], Decimal("6.0"))

    def test_accrual_starts_at_the_hire_date_not_the_year(self):
        """موظفٌ عُيّن في تموز لا يستحقّ عن شهورٍ لم يعمل فيها."""
        newcomer = Employee.objects.create(
            tenant=self.tenant, code="E9", name="جديد", monthly_salary=2000,
            hire_date=date(2026, 7, 10))
        monthly = LeaveType.objects.create(
            tenant=self.tenant, name="شهرية", monthly_accrual=Decimal("1"))
        balance = leave_balance(newcomer, monthly, year=2026, today=date(2026, 9, 30))
        self.assertEqual(balance["accrued"], Decimal("3"))

    def test_approved_leave_reduces_the_balance(self):
        request_row = self.make_leave_request(days=3)
        self.client.post(
            f"{REQUESTS}{request_row['id']}/approve/", {}, format="json", **self.headers())
        balance = leave_balance(self.employee, self.annual)
        self.assertEqual(balance["taken"], Decimal("3"))
        self.assertEqual(balance["remaining"], Decimal("11"))

    def test_manual_adjustment_moves_the_balance(self):
        LeaveBalanceAdjustment.objects.create(
            tenant=self.tenant, employee=self.employee, leave_type=self.annual,
            date=timezone.localdate(), days=Decimal("-4"), notes="رصيد مرحّل")
        self.assertEqual(leave_balance(self.employee, self.annual)["remaining"], Decimal("10"))

    def test_pending_requests_reserve_the_balance(self):
        """ثلاثة طلبات بكامل الرصيد كانت تمرّ لأن كلاً منها وحده يكفيه."""
        self.make_leave_request(days=10, start=date(timezone.localdate().year, 5, 4))
        self.assertEqual(available_days(self.employee, self.annual), Decimal("4"))

    def test_request_beyond_the_balance_is_refused_at_the_door(self):
        response = self.client.post(
            REQUESTS,
            {"employee": self.employee.pk, "kind": EmployeeRequest.KIND_LEAVE,
             "leave_type": self.annual.pk, "date_from": "2026-05-01", "date_to": "2026-06-30"},
            format="json", **self.headers())
        self.assertEqual(response.status_code, 400, response.content)
        self.assertIn("date_to", response.data)

    def test_max_days_per_request_is_enforced(self):
        capped = LeaveType.objects.create(
            tenant=self.tenant, name="عارضة", annual_grant=Decimal("30"),
            max_days_per_request=2)
        response = self.client.post(
            REQUESTS,
            {"employee": self.employee.pk, "kind": EmployeeRequest.KIND_LEAVE,
             "leave_type": capped.pk, "date_from": "2026-05-01", "date_to": "2026-05-05"},
            format="json", **self.headers())
        self.assertEqual(response.status_code, 400, response.content)

    def test_balances_endpoint_reports_every_active_type(self):
        response = self.client.get(BALANCES, **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        row = response.data[0]
        self.assertEqual(row["employee"], self.employee.pk)
        self.assertEqual(Decimal(row["balances"][0]["remaining"]), Decimal("14"))


class ApprovalFlowTest(RequestsTestBase):
    def test_single_level_approval_by_default(self):
        """شركةٌ لم تضبط قواعدها تستطيع تشغيل الطلبات، لا أن تجدها معلّقة."""
        row = self.make_leave_request()
        self.assertEqual(row["status"], EmployeeRequest.STATUS_PENDING)
        self.assertEqual(len(row["steps"]), 1)

        approved = self.client.post(
            f"{REQUESTS}{row['id']}/approve/", {"note": "موافق"},
            format="json", **self.headers())
        self.assertEqual(approved.status_code, 200, approved.content)
        self.assertEqual(approved.data["status"], EmployeeRequest.STATUS_APPROVED)

    def test_two_level_approval_needs_both(self):
        boss = User.objects.create_user("req-boss", password="x")
        UserCompanyMembership.objects.create(
            user=boss, tenant=self.tenant, role="manager")
        ApprovalRule.objects.create(tenant=self.tenant, level=1, approver_user=self.manager)
        ApprovalRule.objects.create(tenant=self.tenant, level=2, approver_user=boss)

        row = self.make_leave_request()
        self.assertEqual(len(row["steps"]), 2)

        first = self.client.post(
            f"{REQUESTS}{row['id']}/approve/", {}, format="json", **self.headers())
        self.assertEqual(first.data["status"], EmployeeRequest.STATUS_PENDING,
                         "مستوى واحد لا يكفي")

        self.client.force_authenticate(boss)
        second = self.client.post(
            f"{REQUESTS}{row['id']}/approve/", {}, format="json", **self.headers())
        self.assertEqual(second.data["status"], EmployeeRequest.STATUS_APPROVED)

    def test_rejection_stops_the_chain(self):
        boss = User.objects.create_user("req-boss2", password="x")
        UserCompanyMembership.objects.create(user=boss, tenant=self.tenant, role="manager")
        ApprovalRule.objects.create(tenant=self.tenant, level=1, approver_user=self.manager)
        ApprovalRule.objects.create(tenant=self.tenant, level=2, approver_user=boss)

        row = self.make_leave_request()
        rejected = self.client.post(
            f"{REQUESTS}{row['id']}/reject/", {"note": "الموسم مزدحم"},
            format="json", **self.headers())
        self.assertEqual(rejected.data["status"], EmployeeRequest.STATUS_REJECTED)

        # المستوى الثاني لا يبتّ في مرفوض.
        self.client.force_authenticate(boss)
        after = self.client.post(
            f"{REQUESTS}{row['id']}/approve/", {}, format="json", **self.headers())
        self.assertIn(after.status_code, (400, 403), after.content)
        self.assertEqual(
            ApprovalStep.objects.filter(status=ApprovalStep.STATUS_APPROVED).count(), 0)

    def test_a_named_approver_cannot_be_bypassed_by_permission(self):
        """تسميةُ المعتمِد قرارٌ تنظيمي — تجاوزُه بالصلاحية يُفرغه من معناه."""
        named = User.objects.create_user("req-named", password="x")
        UserCompanyMembership.objects.create(user=named, tenant=self.tenant, role="manager")
        ApprovalRule.objects.create(tenant=self.tenant, level=1, approver_user=named)

        row = self.make_leave_request()
        response = self.client.post(
            f"{REQUESTS}{row['id']}/approve/", {}, format="json", **self.headers())
        self.assertEqual(response.status_code, 403, response.content)

        self.client.force_authenticate(named)
        allowed = self.client.post(
            f"{REQUESTS}{row['id']}/approve/", {}, format="json", **self.headers())
        self.assertEqual(allowed.status_code, 200, allowed.content)

    def test_the_most_specific_rule_wins_per_level(self):
        from hr.models import Department
        from hr.requests import matching_rules

        department = Department.objects.create(tenant=self.tenant, name="المبيعات")
        self.employee.department = department
        self.employee.save(update_fields=["department"])
        specific_user = User.objects.create_user("req-dept", password="x")
        UserCompanyMembership.objects.create(
            user=specific_user, tenant=self.tenant, role="manager")

        ApprovalRule.objects.create(tenant=self.tenant, level=1, approver_user=self.manager)
        ApprovalRule.objects.create(
            tenant=self.tenant, level=1, department=department, approver_user=specific_user)

        row = EmployeeRequest.objects.create(
            tenant=self.tenant, employee=self.employee, kind=EmployeeRequest.KIND_LEAVE,
            leave_type=self.annual, date_from=date(2026, 5, 1), date_to=date(2026, 5, 2))
        rules = matching_rules(row)
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0].approver_user_id, specific_user.pk)

    def test_a_rule_for_another_kind_does_not_apply(self):
        from hr.requests import matching_rules

        ApprovalRule.objects.create(
            tenant=self.tenant, level=1, kind=EmployeeRequest.KIND_ADVANCE,
            approver_user=self.manager)
        row = EmployeeRequest.objects.create(
            tenant=self.tenant, employee=self.employee, kind=EmployeeRequest.KIND_LEAVE,
            leave_type=self.annual, date_from=date(2026, 5, 1), date_to=date(2026, 5, 2))
        self.assertEqual(matching_rules(row), [])

    def test_draft_cannot_be_approved_before_submission(self):
        row = self.make_leave_request(submit=False)
        response = self.client.post(
            f"{REQUESTS}{row['id']}/approve/", {}, format="json", **self.headers())
        self.assertIn(response.status_code, (400, 403), response.content)

    def test_status_cannot_be_written_by_patch(self):
        """حقلُ حالةٍ قابلٌ للكتابة كان يتخطّى سلسلة الاعتماد كلها."""
        row = self.make_leave_request(submit=False)
        response = self.client.patch(
            f"{REQUESTS}{row['id']}/", {"status": EmployeeRequest.STATUS_APPROVED},
            format="json", **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["status"], EmployeeRequest.STATUS_DRAFT)

    def test_cancel_frees_the_reserved_balance(self):
        row = self.make_leave_request(days=10)
        self.assertEqual(available_days(self.employee, self.annual), Decimal("4"))
        self.client.post(f"{REQUESTS}{row['id']}/cancel/", {}, format="json", **self.headers())
        self.assertEqual(available_days(self.employee, self.annual), Decimal("14"))

    def test_approved_request_cannot_be_cancelled_here(self):
        row = self.make_leave_request()
        self.client.post(f"{REQUESTS}{row['id']}/approve/", {}, format="json", **self.headers())
        response = self.client.post(
            f"{REQUESTS}{row['id']}/cancel/", {}, format="json", **self.headers())
        self.assertEqual(response.status_code, 400, response.content)


class RequestVisibilityTest(RequestsTestBase):
    def setUp(self):
        super().setUp()
        self.colleague_user = User.objects.create_user("req-colleague", password="x")
        UserCompanyMembership.objects.create(
            user=self.colleague_user, tenant=self.tenant, role="ess")
        self.colleague = Employee.objects.create(
            tenant=self.tenant, code="E2", name="زميل", monthly_salary=2500,
            user=self.colleague_user)
        EmployeeRequest.objects.create(
            tenant=self.tenant, employee=self.colleague, kind=EmployeeRequest.KIND_LEAVE,
            leave_type=self.annual, date_from=date(2026, 5, 1), date_to=date(2026, 5, 2))

    def test_a_worker_sees_only_their_own_requests(self):
        EmployeeRequest.objects.create(
            tenant=self.tenant, employee=self.employee, kind=EmployeeRequest.KIND_OTHER,
            description="طلبي")
        self.as_worker()
        response = self.client.get(REQUESTS, **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        rows = self.rows(response)
        self.assertEqual({r["employee"] for r in rows}, {self.employee.pk})

    def test_a_worker_cannot_file_a_request_for_a_colleague(self):
        """بلا هذا الحارس يقدّم موظفٌ إجازةً باسم زميله بتغيير رقمٍ في الحمولة."""
        self.as_worker()
        response = self.client.post(
            REQUESTS,
            {"employee": self.colleague.pk, "kind": EmployeeRequest.KIND_OTHER,
             "description": "باسم غيري"},
            format="json", **self.headers())
        # يُقبل الطلب لكنه يُنسب لصاحب الجلسة لا لمن سُمّي.
        if response.status_code == 201:
            self.assertEqual(response.data["employee"], self.employee.pk)
        else:
            self.assertEqual(response.status_code, 403, response.content)

    def test_a_worker_cannot_approve(self):
        row = EmployeeRequest.objects.create(
            tenant=self.tenant, employee=self.employee, kind=EmployeeRequest.KIND_OTHER,
            status=EmployeeRequest.STATUS_PENDING)
        ApprovalStep.objects.create(request=row, level=1)
        self.as_worker()
        response = self.client.post(
            f"{REQUESTS}{row.pk}/approve/", {}, format="json", **self.headers())
        self.assertEqual(response.status_code, 403, response.content)

    def test_manager_sees_everyone(self):
        response = self.client.get(REQUESTS, **self.headers())
        rows = self.rows(response)
        self.assertEqual(len(rows), 1)

    def test_inbox_scope_shows_only_pending(self):
        row = self.make_leave_request()
        response = self.client.get(f"{REQUESTS}?scope=inbox", **self.headers())
        keys = {r["id"] for r in self.rows(response)}
        self.assertIn(row["id"], keys)
        self.assertEqual(
            {r["status"] for r in self.rows(response)}, {EmployeeRequest.STATUS_PENDING})

    def test_another_company_requests_never_appear(self):
        other = Tenant.objects.create(CompanyName="شركة أخرى")
        stranger = Employee.objects.create(
            tenant=other, code="X1", name="غريب", monthly_salary=1000)
        EmployeeRequest.objects.create(
            tenant=other, employee=stranger, kind=EmployeeRequest.KIND_OTHER)
        response = self.client.get(REQUESTS, **self.headers())
        self.assertTrue(all(r["employee"] != stranger.pk for r in self.rows(response)))


class LeaveAffectsAttendanceTest(RequestsTestBase):
    def setUp(self):
        super().setUp()
        shift = Shift.objects.create(
            tenant=self.tenant, name="صباحي", start1=time(9), end1=time(17),
            weekly_off_days=[4])
        ShiftAssignment.objects.create(
            tenant=self.tenant, employee=self.employee, shift=shift,
            start_date=date(2024, 1, 1))

    def test_approved_leave_turns_absence_into_leave(self):
        from hr.attendance import recompute_attendance_day

        day = date(timezone.localdate().year, 5, 4)
        row = recompute_attendance_day(self.employee, day)
        self.assertEqual(row.status, AttendanceDay.STATUS_ABSENT)
        self.assertEqual(row.absence_days, Decimal("1"))

        request_row = self.make_leave_request(days=2, start=day)
        self.client.post(
            f"{REQUESTS}{request_row['id']}/approve/", {}, format="json", **self.headers())

        row.refresh_from_db()
        self.assertEqual(row.status, AttendanceDay.STATUS_LEAVE)
        self.assertEqual(row.absence_days, Decimal("0"), "الإجازة المدفوعة لا تُخصم")

    def test_unpaid_leave_is_recorded_as_leave_but_still_deducted(self):
        """الحقيقتان مختلفتان: سجلٌّ إداريّ «إجازة»، ومالٌ «يوم مخصوم»."""
        from hr.attendance import recompute_attendance_day

        unpaid = LeaveType.objects.create(
            tenant=self.tenant, name="بلا أجر", is_paid=False,
            annual_grant=Decimal("30"))
        day = date(timezone.localdate().year, 5, 11)
        request_row = self.make_leave_request(days=1, start=day, leave_type=unpaid)
        self.client.post(
            f"{REQUESTS}{request_row['id']}/approve/", {}, format="json", **self.headers())

        row = recompute_attendance_day(self.employee, day)
        self.assertEqual(row.status, AttendanceDay.STATUS_LEAVE)
        self.assertEqual(row.absence_days, Decimal("1"))

    def test_a_public_holiday_is_never_an_absence(self):
        from hr.attendance import recompute_attendance_day

        day = date(timezone.localdate().year, 5, 18)
        Holiday.objects.create(tenant=self.tenant, date=day, name="عيد")
        row = recompute_attendance_day(self.employee, day)
        self.assertEqual(row.status, AttendanceDay.STATUS_HOLIDAY)
        self.assertEqual(row.absence_days, Decimal("0"))

    def test_a_pending_leave_does_not_excuse_absence(self):
        """طلبٌ قيد المراجعة لا يُعفي صاحبه من الحضور بعد."""
        from hr.attendance import recompute_attendance_day

        day = date(timezone.localdate().year, 5, 25)
        self.make_leave_request(days=1, start=day)
        row = recompute_attendance_day(self.employee, day)
        self.assertEqual(row.status, AttendanceDay.STATUS_ABSENT)


class NotificationTest(RequestsTestBase):
    def test_submitting_notifies_the_approver(self):
        self.make_leave_request()
        docs = FirestoreMirrorDoc.objects.filter(path__startswith="notifications/")
        self.assertGreaterEqual(docs.count(), 1)
        payload = docs.first().data
        self.assertEqual(payload["type"], "hr_request_submitted")
        self.assertFalse(payload["isRead"])
        self.assertEqual(payload["targetView"], "hr-requests")

    def test_decision_notifies_the_requester(self):
        row = self.make_leave_request()
        FirestoreMirrorDoc.objects.all().delete()
        self.client.post(
            f"{REQUESTS}{row['id']}/approve/", {"note": "موافق"},
            format="json", **self.headers())

        docs = FirestoreMirrorDoc.objects.filter(path__startswith="notifications/")
        self.assertEqual(docs.count(), 1)
        payload = docs.first().data
        self.assertEqual(payload["type"], "hr_request_decided")
        self.assertEqual(payload["userId"], str(self.worker_user.pk))

    def test_notifications_are_scoped_to_the_company(self):
        self.make_leave_request()
        doc = FirestoreMirrorDoc.objects.filter(path__startswith="notifications/").first()
        self.assertEqual(doc.tenant_id, self.tenant.pk)

    def test_an_employee_without_an_account_is_not_notified_and_does_not_error(self):
        self.employee.user = None
        self.employee.save(update_fields=["user"])
        row = self.make_leave_request()
        FirestoreMirrorDoc.objects.all().delete()
        response = self.client.post(
            f"{REQUESTS}{row['id']}/approve/", {}, format="json", **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(FirestoreMirrorDoc.objects.count(), 0)


class AdvanceTest(RequestsTestBase):
    def make_advance_request(self, *, amount="600", installments=3):
        response = self.client.post(
            REQUESTS,
            {"employee": self.employee.pk, "kind": EmployeeRequest.KIND_ADVANCE,
             "amount": amount, "installments": installments, "description": "ظرف طارئ"},
            format="json", **self.headers())
        self.assertEqual(response.status_code, 201, response.content)
        self.client.post(
            f"{REQUESTS}{response.data['id']}/submit/", {}, format="json", **self.headers())
        approved = self.client.post(
            f"{REQUESTS}{response.data['id']}/approve/", {}, format="json", **self.headers())
        self.assertEqual(approved.status_code, 200, approved.content)
        return approved.data

    def test_approving_an_advance_request_creates_the_advance(self):
        self.make_advance_request()
        advance = Advance.objects.get(employee=self.employee)
        self.assertEqual(advance.total, Decimal("600.00"))
        self.assertEqual(advance.monthly_installment, Decimal("200.00"))
        self.assertEqual(advance.remaining, Decimal("600.00"))
        self.assertEqual(advance.status, Advance.STATUS_OPEN)

    def test_approval_moves_no_money(self):
        """من يعتمد الطلب ليس بالضرورة من يملك الصندوق."""
        from accounting.models import JournalHeader

        before = JournalHeader.objects.count()
        self.make_advance_request()
        self.assertEqual(JournalHeader.objects.count(), before)
        self.assertFalse(Advance.objects.get(employee=self.employee).is_disbursed)

    def test_advances_cannot_be_created_directly(self):
        response = self.client.post(
            ADVANCES, {"employee": self.employee.pk, "total": "500"},
            format="json", **self.headers())
        self.assertEqual(response.status_code, 405, response.content)

    def test_a_zero_amount_advance_is_refused(self):
        response = self.client.post(
            REQUESTS,
            {"employee": self.employee.pk, "kind": EmployeeRequest.KIND_ADVANCE,
             "amount": "0"},
            format="json", **self.headers())
        self.assertEqual(response.status_code, 400, response.content)

    def test_an_undisbursed_advance_can_be_cancelled(self):
        self.make_advance_request()
        advance = Advance.objects.get(employee=self.employee)
        response = self.client.post(
            f"{ADVANCES}{advance.pk}/cancel/", {}, format="json", **self.headers())
        self.assertEqual(response.status_code, 200, response.content)
        advance.refresh_from_db()
        self.assertEqual(advance.status, Advance.STATUS_CANCELLED)
        self.assertEqual(advance.remaining, Decimal("0"))
