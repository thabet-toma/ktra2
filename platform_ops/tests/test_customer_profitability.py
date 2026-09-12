"""ربحيّةُ العميل ومطابقةُ الخطة (§٩ من #210).

المواصفةُ لا تطلب رقماً فحسب بل **رقماً قابلاً للفتح**: «كل رقم قابل للفتح إلى
مصادره». فمعظمُ هذا الملفّ يختبر أنّ التكلفةَ مشتقّةٌ من مصدرٍ قائمٍ لا مُخترَعة،
وأنّ الاقتراحَ لا يُنفّذ نفسَه.
"""
import datetime
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from platform_ops.models import (
    Engagement,
    PlatformEmployee,
    ServiceSubscription,
    ServiceUsageEvent,
)
from platform_ops.services import (
    PLAN_FIT_EXTRA_UNITS,
    PLAN_FIT_REQUEST_DATA,
    PLAN_FIT_UPGRADE,
    PROFITABILITY_LOSING,
    PROFITABILITY_PROFITABLE,
    PROFITABILITY_REPRICE,
    PROFITABILITY_WATCH,
    classify_profitability,
    compute_customer_profitability,
)
from platform_ops.tests.test_pilot_performance_wallet import PilotScenarioBase


class CustomerProfitabilityTest(PilotScenarioBase):
    def setUp(self):
        super().setUp()
        now = timezone.now()
        self.year, self.month = now.year, now.month
        ServiceSubscription.objects.filter(pk=self.sub.pk).update(
            monthly_fee=Decimal("300.00"), included_quota=1, overage_unit_price=Decimal("20.00"),
        )
        self.sub.refresh_from_db()

    # ── أدوات ───────────────────────────────────────────────────────────────
    def _usage(self, *, units, employee=None, chargeable=True, creditable=True, approved_at=None):
        """حدثُ استخدامٍ واحدٌ من المسار الحقيقيّ، ثمّ تُشكَّل أرقامُه للحالة المختبَرة."""
        _, _, events = self._approve_one_deliverable(received_at=timezone.now() - datetime.timedelta(minutes=5))
        event = events[0]
        ServiceUsageEvent.objects.filter(pk=event.pk).update(
            units=Decimal(str(units)),
            chargeable_to_customer=chargeable,
            creditable_to_employee=creditable,
            employee=employee if employee is not None else self.employee,
            approved_at=approved_at or event.approved_at,
        )
        event.refresh_from_db()
        return event

    def _row(self, tenant_id=None, **kwargs):
        rows = compute_customer_profitability(
            period_year=self.year, period_month=self.month, **kwargs,
        )
        wanted = tenant_id or self.tenant.pk
        return next(row for row in rows if row["tenant_id"] == wanted)

    # ── الإيراد ─────────────────────────────────────────────────────────────
    def test_revenue_is_the_monthly_fee_plus_overage_at_the_subscription_price(self):
        """«يقارن إيراد الخدمة الفعلي» — والفعليُّ مقروءٌ من الاشتراك لا مُقدَّر."""
        self._usage(units=3)
        row = self._row()
        self.assertEqual(row["chargeable_units"], 3.0)
        self.assertEqual(row["overage_units"], 2.0, "حصّةٌ واحدةٌ مشمولةٌ وثلاثُ وحداتٍ مستهلَكة.")
        self.assertEqual(row["revenue"], 340.0, "300 رسمٌ + وحدتا تجاوزٍ × 20.")

    def test_units_not_chargeable_to_the_customer_do_not_raise_revenue(self):
        self._usage(units=5, chargeable=False)
        self.assertEqual(self._row()["revenue"], 300.0)

    # ── التكلفة البشريّة ────────────────────────────────────────────────────
    def test_human_cost_is_the_salary_divided_by_everything_the_employee_produced(self):
        """تكلفةُ الوحدةِ راتبٌ ÷ كلّ إنتاج الشهر، لا راتبٌ ÷ إنتاجِ هذه الشركة."""
        other = self._second_service_tenant()
        self._usage(units=2)
        self._usage_for(other, units=8)
        mine = self._row()
        theirs = self._row(tenant_id=other.pk)
        salary = float(self._expected_salary())
        self.assertAlmostEqual(mine["human_cost"] + theirs["human_cost"], salary, places=2)
        self.assertAlmostEqual(mine["human_cost"], salary * 0.2, places=2)
        self.assertAlmostEqual(theirs["human_cost"], salary * 0.8, places=2)

    def test_an_employee_who_produced_nothing_costs_no_tenant(self):
        """لا قسمةَ على صفر، ولا راتبٌ يُلصَق بشركةٍ لم تستهلك منه شيئاً."""
        idle_user = self._make_user("idle_agent")
        PlatformEmployee.objects.create(
            user=idle_user, specialty="data_entry", status=PlatformEmployee.Status.ACTIVE,
            capacity_target=Decimal("0.00"),
        )
        self._usage(units=4)
        row = self._row()
        self.assertEqual(
            [c["employee_id"] for c in row["contributors"]], [self.employee.pk],
            "الموظّفُ الخاملُ لا يظهر مساهماً ولا تدخل تكلفتُه الصفَّ.",
        )

    def test_units_not_creditable_to_the_employee_carry_no_human_cost(self):
        self._usage(units=4, creditable=False)
        row = self._row()
        self.assertEqual(row["human_cost"], 0.0)
        self.assertEqual(row["contributors"], [])

    def test_every_number_opens_to_its_sources(self):
        """«كل رقم قابل للفتح إلى مصادره» — المساهمون يعيدون بناء التكلفة."""
        self._usage(units=3)
        row = self._row()
        self.assertTrue(row["contributors"])
        self.assertAlmostEqual(
            sum(c["cost"] for c in row["contributors"]) + row["allocated_expenses"],
            row["total_cost"], places=2,
        )

    # ── النفقات المخصَّصة ───────────────────────────────────────────────────
    def test_allocated_expenses_are_an_input_that_defaults_to_zero(self):
        """لا مصدرَ لها في المستودع، فلا تُخترَع: صفرٌ حتى تُمرَّر."""
        self._usage(units=1)
        self.assertEqual(self._row()["allocated_expenses"], 0.0)
        loaded = self._row(allocated_expenses_per_tenant=Decimal("120.00"))
        self.assertEqual(loaded["allocated_expenses"], 120.0)
        self.assertAlmostEqual(loaded["total_cost"] - self._row()["total_cost"], 120.0, places=2)

    # ── التصنيف ─────────────────────────────────────────────────────────────
    def test_classification_is_by_ratio_not_by_amount(self):
        """فرقٌ قدرُه ٥٠ ليس واحداً على إيرادِ ٣٠٠ وإيرادِ ٣٠٠٠."""
        self.assertEqual(classify_profitability(revenue=Decimal("300"), total_cost=Decimal("250")), PROFITABILITY_WATCH)
        self.assertEqual(classify_profitability(revenue=Decimal("3000"), total_cost=Decimal("2950")), PROFITABILITY_REPRICE)

    def test_zero_revenue_with_a_cost_is_losing_not_watch(self):
        self.assertEqual(classify_profitability(revenue=Decimal("0"), total_cost=Decimal("10")), PROFITABILITY_LOSING)
        self.assertEqual(classify_profitability(revenue=Decimal("0"), total_cost=Decimal("0")), PROFITABILITY_PROFITABLE)

    def test_the_four_states_the_spec_names_are_the_only_ones_emitted(self):
        self._usage(units=2)
        states = {row["state"] for row in compute_customer_profitability(period_year=self.year, period_month=self.month)}
        self.assertTrue(states <= {
            PROFITABILITY_PROFITABLE, PROFITABILITY_WATCH, PROFITABILITY_REPRICE, PROFITABILITY_LOSING,
        })

    # ── الشهر ───────────────────────────────────────────────────────────────
    def test_a_month_counts_only_its_own_units(self):
        """`approved_at` عمودُ وقت: الشهرُ مدىً محلّيٌّ صريحٌ لا `__month`."""
        old = timezone.now() - datetime.timedelta(days=70)
        self._usage(units=9, approved_at=old)
        self.assertEqual(self._row()["chargeable_units"], 0.0)

    def test_a_reversed_event_subtracts_instead_of_adding(self):
        """`REVERSAL` يخزّن وحداتِه موجبةً — فجمعُها بلا إشارةٍ يشحن تجاوزاً لم يقع."""
        from platform_ops.services import reverse_usage_event

        event = self._usage(units=3)
        self.assertEqual(self._row()["chargeable_units"], 3.0)
        reverse_usage_event(usage_event=event, reason="اعتراضٌ مقبول", actor=self.admin)
        row = self._row()
        self.assertEqual(row["chargeable_units"], 0.0, "العكسُ يطرح لا يضيف.")
        self.assertEqual(row["overage_units"], 0.0)
        self.assertEqual(row["revenue"], 300.0, "لا تجاوزَ على وحداتٍ عُكست.")

    def test_an_employee_whose_whole_output_was_reversed_divides_by_no_zero(self):
        """صافيَ الوحدات صفرٌ — فلا تكلفةَ وحدةٍ تُحسب ولا استثناءَ يُرفع."""
        from platform_ops.services import reverse_usage_event

        event = self._usage(units=4)
        reverse_usage_event(usage_event=event, reason="عكسٌ كامل", actor=self.admin)
        row = self._row()
        self.assertEqual(row["human_cost"], 0.0)
        self.assertEqual(row["contributors"], [])

    # ── الاقتراحات ──────────────────────────────────────────────────────────
    def test_one_month_over_quota_suggests_extra_units_and_two_suggest_an_upgrade(self):
        """«ترقية عند استهلاك مرتفع متكرر» — التكرارُ هو الفارق لا المقدار."""
        self._usage(units=3)
        codes = {s["code"] for s in self._row()["suggestions"]}
        self.assertIn(PLAN_FIT_EXTRA_UNITS, codes)
        self.assertNotIn(PLAN_FIT_UPGRADE, codes, "شهرٌ واحدٌ حدثٌ لا نمط.")

        last_month = timezone.now().replace(day=1) - datetime.timedelta(days=5)
        self._usage(units=3, approved_at=last_month)
        codes = {s["code"] for s in self._row()["suggestions"]}
        self.assertIn(PLAN_FIT_UPGRADE, codes)
        self.assertNotIn(PLAN_FIT_EXTRA_UNITS, codes, "الترقيةُ تحلّ محلَّ شراء الوحدات لا تُضاف إليه.")

    def test_work_waiting_on_the_customer_suggests_asking_for_data(self):
        """«طلب بيانات من العميل» مشتقٌّ من تعاون الزبون القائم لا من عدٍّ جديد."""
        from platform_ops.models import WorkOrder
        from platform_ops.services import create_work_order, transition_work_order_status

        wo = create_work_order(tenant=self.tenant, title="بانتظار العميل", received_at=timezone.now())
        transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.SCREENING)
        transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.WAITING_CUSTOMER)
        suggestion = next(s for s in self._row()["suggestions"] if s["code"] == PLAN_FIT_REQUEST_DATA)
        self.assertGreaterEqual(suggestion["evidence"]["waiting_customer"], 1, "الدليلُ عددٌ لا عبارة.")

    def test_a_healthy_in_quota_company_gets_no_suggestions(self):
        """الاقتراحُ استثناءٌ لا زينةٌ على كلّ صفّ."""
        self.assertEqual(self._row()["suggestions"], [])

    # ── النقطة ──────────────────────────────────────────────────────────────
    def test_endpoint_is_manager_only(self):
        """الصفُّ يحمل تكلفةً مشتقّةً من الرواتب — فهو خارجُ لوحة الموظفين."""
        url = reverse("platform-ops-profitability")
        client = APIClient()
        client.force_authenticate(user=self.staff_user)
        self.assertEqual(client.get(url).status_code, status.HTTP_403_FORBIDDEN)
        client.force_authenticate(user=self.admin)
        self.assertEqual(client.get(url).status_code, status.HTTP_200_OK)

    def test_the_suggestion_does_not_execute_itself(self):
        """«لا ينفذ نفسه ولا يغير سعراً أو اشتراكاً» — قراءةٌ محضة."""
        self._usage(units=3)
        url = reverse("platform-ops-profitability")
        client = APIClient()
        client.force_authenticate(user=self.admin)
        before = ServiceSubscription.objects.get(pk=self.sub.pk)
        response = client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(any(row["suggestions"] for row in response.data["rows"]))
        after = ServiceSubscription.objects.get(pk=self.sub.pk)
        self.assertEqual(
            (after.plan, after.included_quota, after.monthly_fee, after.status),
            (before.plan, before.included_quota, before.monthly_fee, before.status),
        )
        self.assertEqual(client.post(url, {}, format="json").status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_invalid_allocated_expenses_are_refused_not_silently_zeroed(self):
        url = reverse("platform-ops-profitability")
        client = APIClient()
        client.force_authenticate(user=self.admin)
        response = client.get(url, {"allocated_expenses": "abc"})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["code"], "invalid_allocated_expenses")
        self.assertEqual(
            client.get(url, {"allocated_expenses": "-1"}).status_code, status.HTTP_400_BAD_REQUEST,
        )

    # ── مساعداتٌ للشركة الثانية ─────────────────────────────────────────────
    def _make_user(self, username):
        from django.contrib.auth.models import User

        return User.objects.create_user(username=username, email=f"{username}@platform.local", password="x")

    def _expected_salary(self):
        from platform_ops.services import (
            get_active_employee_compensation_policy,
            get_default_compensation_policy_dict,
        )

        policy = get_active_employee_compensation_policy(self.employee.pk)
        if policy is not None:
            return Decimal(str(policy.base_salary))
        return Decimal(str(get_default_compensation_policy_dict()["base_salary"]))

    def _second_service_tenant(self):
        from partners.models import Partner
        from inventory.models import Product
        from tenants.models import Tenant

        tenant = Tenant.objects.create(TenantID=4102, CompanyName="شركة الـpilot الثانية")
        ServiceSubscription.objects.create(
            tenant=tenant, status=ServiceSubscription.Status.ACTIVE, plan="standard",
            included_quota=1000, consumed_quota=0, monthly_fee=Decimal("300.00"),
            overage_unit_price=Decimal("20.00"),
        )
        Engagement.objects.create(employee=self.employee, tenant=tenant, status=Engagement.Status.ACTIVE)
        self._second_customer = Partner.objects.create(tenant=tenant, name="عميل ثانٍ", partner_type="Customer")
        self._second_product = Product.objects.create(
            tenant=tenant, sku="PILOT-SVC-2", name_ar="خدمة pilot ٢", is_service=True,
        )
        return tenant

    def _usage_for(self, tenant, *, units):
        """حدثُ استخدامٍ لشركةٍ أخرى — بتبديلِ سياق القاعدة لا بنسخِ مسارِها."""
        original = (self.tenant, self.customer, self.product)
        self.tenant, self.customer, self.product = tenant, self._second_customer, self._second_product
        try:
            return self._usage(units=units)
        finally:
            self.tenant, self.customer, self.product = original
