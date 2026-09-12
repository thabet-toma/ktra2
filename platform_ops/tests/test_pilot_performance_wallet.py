"""اختبارات سياسة تقييم الـpilot (40/30/20/10)، المحفظة، وعمولة الاكتساب (التذكرة 210-D).

تغطي معايير النجاح الحرفية من التذكرة:
1. لقطة شهرية مفسرة لا تتغير بعد تعديل السياسة (تجميد `policy_snapshot`/`axes_data`).
2. العميل نفسه يستحق ثلاثة أسطر عمولة مؤهلة ثم صفر في الرابع.
3. الإغلاق المكرر لا يكرر أي سطر (idempotency).
بالإضافة إلى: مجموع الأوزان يجب أن يساوي 100% لحظة الكتابة، منع تعديل نسخة
مفعّلة، منع تداخل الإصدارات، حالة `PENDING` بسبب «الدفع غير مسجل»، وحجب
الإغلاق بتسليمات معلَّقة (blockers).
"""
import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from inventory.models import Product
from partners.models import Partner
from sales.models import SalesInvoice, SalesInvoiceLine
from tenants.models import Currency, Tenant

from platform_ops.models import (
    AcquisitionCommissionLine,
    CustomerAcquisition,
    Engagement,
    EmployeeSalaryLine,
    MonthlyCompensationClose,
    PerformanceEvaluationPolicy,
    PerformanceSnapshot,
    PlatformActivityLog,
    PlatformEmployee,
    ServiceDocumentType,
    ServiceSubscription,
    SubscriptionBillingRecord,
    WalletLineStatus,
    WorkOrder,
    WorkOrderDeliverable,
)
from platform_ops.services import (
    ALL_PILOT_PERFORMANCE_AXES,
    DEFAULT_PILOT_AXIS_WEIGHTS,
    MonthCloseBlockedError,
    PerformanceEvaluationPolicyConflict,
    PerformanceEvaluationPolicyError,
    activate_performance_evaluation_policy,
    activate_service_unit_catalog,
    approve_work_order_deliverable_with_usage,
    assign_work_order,
    calculate_employee_pilot_performance,
    capture_pilot_performance_snapshot,
    close_compensation_month,
    create_performance_evaluation_policy_draft,
    create_service_unit_catalog_draft,
    create_work_order,
    link_work_order_document,
    submit_work_order_deliverable,
    transition_work_order_status,
    update_performance_evaluation_policy_draft,
    update_service_unit_catalog_entries,
)

User = get_user_model()


class PilotAxisWeightsShapeTest(SimpleTestCase):
    """محاور الـpilot الأربعة مستقلة تماماً عن محاور #207 الخمسة."""

    def test_four_pilot_axes_sum_to_100(self):
        self.assertEqual(len(ALL_PILOT_PERFORMANCE_AXES), 4)
        self.assertEqual(sum(DEFAULT_PILOT_AXIS_WEIGHTS.values()), Decimal("100.00"))

    def test_pilot_axis_keys_do_not_collide_with_207_axis_keys(self):
        from platform_ops.services import ALL_PERFORMANCE_AXES
        self.assertEqual(set(ALL_PILOT_PERFORMANCE_AXES) & set(ALL_PERFORMANCE_AXES), set())


class PerformanceEvaluationPolicyDraftTest(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username="pep_admin", email="pep@platform.local", password="x")

    def test_draft_default_weights_sum_to_100(self):
        draft = create_performance_evaluation_policy_draft(actor=self.admin)
        self.assertEqual(draft.status, PerformanceEvaluationPolicy.Status.DRAFT)
        self.assertEqual(sum(Decimal(v) for v in draft.weights.values()), Decimal("100.00"))
        self.assertEqual(draft.version, 1)

    def test_rejects_weights_not_summing_to_100(self):
        with self.assertRaises(PerformanceEvaluationPolicyError) as ctx:
            create_performance_evaluation_policy_draft(
                actor=self.admin,
                weights={
                    "task_completion": 50, "quality_accuracy": 30,
                    "sla_adherence": 20, "customer_satisfaction": 10,
                },
            )
        self.assertEqual(ctx.exception.code, "weights_must_total_100")

    def test_activation_requires_reason(self):
        draft = create_performance_evaluation_policy_draft(actor=self.admin)
        with self.assertRaises(PerformanceEvaluationPolicyError) as ctx:
            activate_performance_evaluation_policy(policy=draft, actor=self.admin, activation_reason="")
        self.assertEqual(ctx.exception.code, "activation_reason_required")

    def test_active_version_cannot_be_edited_must_be_cloned(self):
        draft = create_performance_evaluation_policy_draft(actor=self.admin)
        active = activate_performance_evaluation_policy(policy=draft, actor=self.admin, activation_reason="v1")
        with self.assertRaises(PerformanceEvaluationPolicyConflict):
            update_performance_evaluation_policy_draft(policy=active, actor=self.admin, min_sample_size=3)

    def test_overlapping_effective_from_is_rejected(self):
        draft1 = create_performance_evaluation_policy_draft(actor=self.admin)
        activate_performance_evaluation_policy(policy=draft1, actor=self.admin, activation_reason="v1")
        future = timezone.now() + datetime.timedelta(days=10)
        draft2 = create_performance_evaluation_policy_draft(actor=self.admin)
        activate_performance_evaluation_policy(
            policy=draft2, actor=self.admin, activation_reason="v2", effective_from=future,
        )
        draft3 = create_performance_evaluation_policy_draft(actor=self.admin)
        with self.assertRaises(PerformanceEvaluationPolicyConflict):
            activate_performance_evaluation_policy(
                policy=draft3, actor=self.admin, activation_reason="v3", effective_from=future,
            )


class PilotScenarioBase(TestCase):
    """بيئة أمرِ عملٍ ← تسليمٍ ← اعتمادٍ ← حدث استخدامٍ — بنفس نمط `UsageLedgerTestBase`."""

    def setUp(self):
        self.tenant = Tenant.objects.create(TenantID=4101, CompanyName="شركة اختبار الـpilot")
        self.admin = User.objects.create_superuser(username="pilot_admin", email="pa@platform.local", password="x")
        self.staff_user = User.objects.create_user(username="pilot_agent", email="pag@platform.local", password="x")
        self.employee = PlatformEmployee.objects.create(
            user=self.staff_user, specialty="data_entry", status=PlatformEmployee.Status.ACTIVE,
            capacity_target=Decimal("0.00"),
        )
        Engagement.objects.create(employee=self.employee, tenant=self.tenant, status=Engagement.Status.ACTIVE)

        self.sub = ServiceSubscription.objects.create(
            tenant=self.tenant, status=ServiceSubscription.Status.ACTIVE, plan="standard",
            included_quota=1000, consumed_quota=0,
        )
        catalog_draft = create_service_unit_catalog_draft(actor=self.admin)
        update_service_unit_catalog_entries(
            catalog=catalog_draft,
            entries=[{
                "document_type": ServiceDocumentType.SALES_INVOICE,
                "base_units": Decimal("1.00"), "per_line_weight": Decimal("0.00"),
            }],
            actor=self.admin,
        )
        self.catalog = activate_service_unit_catalog(catalog=catalog_draft, actor=self.admin, activation_reason="pilot")

        self.currency, _ = Currency.objects.get_or_create(
            Code="ILS", defaults={"Name": "شيكل", "Symbol": "₪", "IsBaseCurrency": True},
        )
        self.customer = Partner.objects.create(tenant=self.tenant, name="عميل الـpilot", partner_type="Customer")
        self.product = Product.objects.create(tenant=self.tenant, sku="PILOT-SVC-1", name_ar="خدمة pilot", is_service=True)
        self._invoice_seq = 0

    def _approve_one_deliverable(self, *, received_at, reject=False, rejection_category=""):
        """يُنتج أمرَ عملٍ واحداً معتمَداً (أو مرفوضاً) بحدث استخدامٍ واحد إن اعتُمد."""
        self._invoice_seq += 1
        wo = create_work_order(tenant=self.tenant, title=f"أمر عمل pilot {self._invoice_seq}", received_at=received_at)
        wo = assign_work_order(work_order=wo, assignee=self.employee)
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.SCREENING, now=received_at)
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.DATA_ENTRY, now=received_at)
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.REVIEW, now=received_at)

        invoice = SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number=f"INV-PILOT-{self._invoice_seq}", customer=self.customer,
            invoice_date=received_at.date(), currency=self.currency,
        )
        SalesInvoiceLine.objects.create(
            tenant=self.tenant, invoice=invoice, product=self.product,
            quantity=Decimal("1"), unit_price=Decimal("10"),
        )
        link = link_work_order_document(
            work_order=wo, document_type=ServiceDocumentType.SALES_INVOICE, document_id=invoice.pk, line_count=1,
        )
        deliverable = submit_work_order_deliverable(work_order=wo, document_link_ids=[link.pk], submitted_by=self.staff_user)

        if reject:
            from platform_ops.services import review_work_order_deliverable
            deliverable = review_work_order_deliverable(
                deliverable=deliverable, review_status=WorkOrderDeliverable.ReviewStatus.REJECTED,
                reviewed_by=self.admin, rejection_reason="خطأ", rejection_category=rejection_category,
            )
            return wo, deliverable, []

        deliverable, events = approve_work_order_deliverable_with_usage(deliverable=deliverable, reviewed_by=self.admin)
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.APPROVAL)
        return wo, deliverable, events


class PilotPerformanceCalculationTest(PilotScenarioBase):
    def test_insufficient_data_below_min_sample_size(self):
        now = timezone.now()
        self._approve_one_deliverable(received_at=now - datetime.timedelta(minutes=5))
        result = calculate_employee_pilot_performance(
            employee=self.employee, period_year=now.year, period_month=now.month,
        )
        self.assertEqual(result["status"], PerformanceSnapshot.Status.INSUFFICIENT_DATA)
        self.assertIsNone(result["composite_score"])

    def test_quality_axis_excludes_non_employee_fault_rejections(self):
        now = timezone.now()
        min_sample = 2
        self._approve_one_deliverable(received_at=now - datetime.timedelta(minutes=5))
        self._approve_one_deliverable(
            received_at=now - datetime.timedelta(minutes=5),
            reject=True, rejection_category=WorkOrderDeliverable.RejectionCategory.CUSTOMER_NEW_INFO,
        )
        result = calculate_employee_pilot_performance(
            employee=self.employee, period_year=now.year, period_month=now.month,
            policy_dict={"min_sample_size": min_sample, "weights": {k: float(v) for k, v in DEFAULT_PILOT_AXIS_WEIGHTS.items()}},
        )
        quality_axis = result["axes"]["quality_accuracy"]
        # الرفضُ بسبب معلومات عميلٍ جديدة مستبعدٌ تماماً من المقام لا مُحتسَبٌ خطأً.
        self.assertEqual(quality_axis["denominator"], 1)
        self.assertEqual(quality_axis["numerator"], 1)
        self.assertEqual(quality_axis["score"], Decimal("100.00"))

    def test_task_completion_uses_assigned_work_when_capacity_not_configured(self):
        now = timezone.now()
        self._approve_one_deliverable(received_at=now - datetime.timedelta(minutes=5))
        self._approve_one_deliverable(received_at=now - datetime.timedelta(minutes=5))
        result = calculate_employee_pilot_performance(
            employee=self.employee, period_year=now.year, period_month=now.month,
        )
        completion_axis = result["axes"]["task_completion"]
        # capacity_target == 0 يعني «لم تُضبط بعد» — المقام هو العمل المسنَد وحده (2).
        self.assertEqual(completion_axis["denominator"], 2.0)
        self.assertEqual(completion_axis["numerator"], 2.0)

    def test_composite_score_equals_sum_of_axis_contributions(self):
        now = timezone.now()
        for _ in range(5):
            self._approve_one_deliverable(received_at=now - datetime.timedelta(minutes=5))
        result = calculate_employee_pilot_performance(
            employee=self.employee, period_year=now.year, period_month=now.month,
        )
        self.assertEqual(result["status"], PerformanceSnapshot.Status.CALCULATED)
        total_contrib = sum(
            axis["weighted_contribution"] for axis in result["axes"].values() if axis["applicable"]
        )
        self.assertEqual(result["composite_score"], min(Decimal("100.00"), total_contrib))


class PilotSnapshotFreezeTest(PilotScenarioBase):
    """معيار النجاح ١: لقطة شهرية مفسرة لا تتغير بعد تعديل السياسة."""

    def test_snapshot_is_frozen_after_policy_changes(self):
        now = timezone.now()
        for _ in range(5):
            self._approve_one_deliverable(received_at=now - datetime.timedelta(minutes=5))

        draft = create_performance_evaluation_policy_draft(actor=self.admin)
        policy_v1 = activate_performance_evaluation_policy(policy=draft, actor=self.admin, activation_reason="v1")

        snapshot = capture_pilot_performance_snapshot(
            employee=self.employee, period_year=now.year, period_month=now.month,
            evaluation_policy=policy_v1, captured_by=self.admin,
        )
        original_score = snapshot.composite_score
        original_axes = snapshot.axes_data

        # ثانياً: مسودة جديدة بأوزان مختلفة تماماً ثم تُفعَّل لاحقاً.
        draft2 = create_performance_evaluation_policy_draft(
            actor=self.admin,
            weights={"task_completion": 10, "quality_accuracy": 10, "sla_adherence": 10, "customer_satisfaction": 70},
        )
        activate_performance_evaluation_policy(
            policy=draft2, actor=self.admin, activation_reason="v2",
            effective_from=timezone.now() + datetime.timedelta(days=1),
        )

        snapshot.refresh_from_db()
        self.assertEqual(snapshot.composite_score, original_score)
        self.assertEqual(snapshot.axes_data, original_axes)
        self.assertEqual(snapshot.evaluation_policy_id, policy_v1.pk)

        # idempotent: إعادة الالتقاط بلا force_refresh تعيد نفس الصف بلا تغيير.
        again = capture_pilot_performance_snapshot(
            employee=self.employee, period_year=now.year, period_month=now.month,
        )
        self.assertEqual(again.pk, snapshot.pk)
        self.assertEqual(again.composite_score, original_score)


class CompensationMonthCloseTest(PilotScenarioBase):
    """معياران ٢ و٣: عمولة العميل ثلاثة أشهر ثم صفر، والإغلاق المكرر بلا تكرار."""

    def _next_month(self, year, month):
        if month == 12:
            return year + 1, 1
        return year, month + 1

    def _make_acquisition_with_trial_ended(self, months_ago=4):
        acquisition = CustomerAcquisition.objects.create(
            tenant=self.tenant, acquired_by=self.employee, acquired_at=timezone.now().date(),
        )
        self.sub.trial_ends_at = timezone.now() - datetime.timedelta(days=30 * months_ago)
        self.sub.status = ServiceSubscription.Status.ACTIVE
        self.sub.save(update_fields=["trial_ends_at", "status"])
        return acquisition

    def _paid_billing_record(self, period_start, period_end, amount=Decimal("300.00")):
        invoice = SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number=f"INV-BILL-{period_start.isoformat()}", customer=self.customer,
            invoice_date=period_end, currency=self.currency, grand_total=amount, amount_paid=amount,
        )
        return SubscriptionBillingRecord.objects.create(
            subscription=self.sub, period_start=period_start, period_end=period_end,
            invoice=invoice, monthly_fee=amount, total_amount=amount,
        )

    def test_customer_earns_exactly_three_commission_lines_then_zero_on_the_fourth(self):
        acquisition = self._make_acquisition_with_trial_ended(months_ago=4)
        year, month = timezone.now().year, timezone.now().month
        for i in range(4):
            self._paid_billing_record(datetime.date(year, month, 1), _month_end(year, month))
            close, created = close_compensation_month(period_year=year, period_month=month, actor=self.admin)
            self.assertTrue(created)
            year, month = self._next_month(year, month)

        lines = list(AcquisitionCommissionLine.objects.filter(acquisition=acquisition).order_by("commission_month_index"))
        self.assertEqual(len(lines), 3)
        self.assertEqual([line.commission_month_index for line in lines], [1, 2, 3])
        for line in lines:
            self.assertEqual(line.status, WalletLineStatus.ELIGIBLE)
            self.assertEqual(line.amount, Decimal("100.00"))

    def test_reversed_month_frees_its_slot_so_a_later_month_still_earns(self):
        """السطرُ المعكوس لا يستهلك شهراً من الثلاثة.

        العكسُ يعني أنّ العمولةَ لم تُستحق أصلاً (اشتراكٌ أُلغي، اكتسابٌ خاطئ)؛ فعدُّه
        ضمن المستهلك يحرم الموظّفَ شهراً استحقّه ولم يُقبض. وكان العدُّ يضمّ
        `REVERSED` فيتوقّف الإنشاء عند الشهر الرابع ولو كان أحدُ الثلاثة معكوساً.
        """
        from platform_ops.services import reverse_wallet_line

        acquisition = self._make_acquisition_with_trial_ended(months_ago=6)
        year, month = timezone.now().year, timezone.now().month
        for _ in range(3):
            self._paid_billing_record(datetime.date(year, month, 1), _month_end(year, month))
            close_compensation_month(period_year=year, period_month=month, actor=self.admin)
            year, month = self._next_month(year, month)
        self.assertEqual(AcquisitionCommissionLine.objects.filter(acquisition=acquisition).count(), 3)

        second = AcquisitionCommissionLine.objects.get(acquisition=acquisition, commission_month_index=2)
        reverse_wallet_line(kind="commission", line=second, reason="الاشتراك أُلغي لاحقاً", actor=self.admin)

        # الشهرُ الرابعُ يُنشئ سطراً الآن لأنّ المعكوسَ أفرغ خانتَه؛ والمستهلكُ غيرُ
        # المعكوس اثنان فقط، فترتيبُ السطر الجديد الثالث لا الرابع.
        self._paid_billing_record(datetime.date(year, month, 1), _month_end(year, month))
        close_compensation_month(period_year=year, period_month=month, actor=self.admin)
        fresh = AcquisitionCommissionLine.objects.get(
            acquisition=acquisition, period_year=year, period_month=month,
        )
        self.assertEqual(fresh.commission_month_index, 3)
        self.assertEqual(fresh.status, WalletLineStatus.ELIGIBLE)
        # والمعكوسُ باقٍ لم يُحذف ولم تُكتب فوقه حالتُه.
        second.refresh_from_db()
        self.assertEqual(second.status, WalletLineStatus.REVERSED)

    def test_customer_who_paid_without_any_trial_still_earns_commission(self):
        """«انتهت تجربة العميل» لا تعني «كانت له تجربة».

        `activate_paid_subscription` لا تضبط `trial_ends_at` إطلاقاً، فعميلٌ فُعِّل
        مدفوعاً مباشرةً يبقى الحقلُ فيه فارغاً — ورفضُ العمولة حينها يحرم جالبَه
        منها إلى الأبد. والحراسةُ باقيةٌ: (ب) دفعٌ مسجَّل و(ج) خدمةٌ نشطة.
        """
        acquisition = CustomerAcquisition.objects.create(
            tenant=self.tenant, acquired_by=self.employee, acquired_at=timezone.now().date(),
        )
        self.sub.trial_ends_at = None
        self.sub.status = ServiceSubscription.Status.ACTIVE
        self.sub.save(update_fields=["trial_ends_at", "status"])

        year, month = timezone.now().year, timezone.now().month
        self._paid_billing_record(datetime.date(year, month, 1), _month_end(year, month))
        close_compensation_month(period_year=year, period_month=month, actor=self.admin)

        line = AcquisitionCommissionLine.objects.get(
            acquisition=acquisition, period_year=year, period_month=month,
        )
        self.assertEqual(line.commission_month_index, 1)
        self.assertEqual(line.amount, Decimal("100.00"))
        self.assertEqual(line.status, WalletLineStatus.ELIGIBLE)

    def test_pending_when_payment_not_registered(self):
        self._make_acquisition_with_trial_ended(months_ago=1)
        year, month = timezone.now().year, timezone.now().month
        close_compensation_month(period_year=year, period_month=month, actor=self.admin)
        line = AcquisitionCommissionLine.objects.get(period_year=year, period_month=month)
        self.assertEqual(line.status, WalletLineStatus.PENDING)
        self.assertEqual(line.pending_reason, "الدفع غير مسجل")

    def test_repeated_close_does_not_duplicate_any_line(self):
        self._make_acquisition_with_trial_ended(months_ago=1)
        year, month = timezone.now().year, timezone.now().month
        self._paid_billing_record(datetime.date(year, month, 1), _month_end(year, month))

        close1, created1 = close_compensation_month(period_year=year, period_month=month, actor=self.admin)
        self.assertTrue(created1)
        salary_count_after_first = EmployeeSalaryLine.objects.count()
        commission_count_after_first = AcquisitionCommissionLine.objects.count()

        close2, created2 = close_compensation_month(period_year=year, period_month=month, actor=self.admin)
        self.assertFalse(created2)
        self.assertEqual(close2.pk, close1.pk)
        self.assertEqual(EmployeeSalaryLine.objects.count(), salary_count_after_first)
        self.assertEqual(AcquisitionCommissionLine.objects.count(), commission_count_after_first)
        self.assertEqual(MonthlyCompensationClose.objects.filter(period_year=year, period_month=month).count(), 1)

    def test_close_blocked_by_pending_deliverables_submitted_in_period(self):
        now = timezone.now()
        self._approve_one_deliverable(
            received_at=now - datetime.timedelta(minutes=5),
            reject=False,
        )
        # مُسلَّمٌ ثانٍ يبقى بانتظار المراجعة — لا يُعتمد ولا يُرفض.
        wo = create_work_order(tenant=self.tenant, title="أمر pilot معلق", received_at=now)
        wo = assign_work_order(work_order=wo, assignee=self.employee)
        submit_work_order_deliverable(work_order=wo, submitted_by=self.staff_user)

        with self.assertRaises(MonthCloseBlockedError) as ctx:
            close_compensation_month(period_year=now.year, period_month=now.month, actor=self.admin)
        self.assertEqual(ctx.exception.code, "pending_deliverables")
        self.assertEqual(MonthlyCompensationClose.objects.count(), 0)

    def test_salary_line_created_for_active_employee_from_default_policy(self):
        year, month = timezone.now().year, timezone.now().month
        close_compensation_month(period_year=year, period_month=month, actor=self.admin)
        line = EmployeeSalaryLine.objects.get(employee=self.employee, period_year=year, period_month=month)
        self.assertEqual(line.amount, Decimal("500.00"))  # الافتراضي في جدول القيم — لا سياسة مخصصة بعد
        self.assertEqual(line.status, WalletLineStatus.ELIGIBLE)
        self.assertEqual(line.sequence, 0)

    def test_trial_status_after_trial_end_earns_no_commission(self):
        """الشرط (ج) «خدمةٌ نشطةٌ» — و`TRIAL` ليست نشاطاً ولو انقضى `trial_ends_at`.

        صفٌّ بقيت حالتُه `trial` بعد انقضاء التجربة حالةٌ بائتةٌ لا اشتراكٌ مدفوع،
        فعدُّه يمنح عمولةً عن شهرٍ لم تُفعَّل فيه الخدمة أصلاً.
        """
        CustomerAcquisition.objects.create(
            tenant=self.tenant, acquired_by=self.employee, acquired_at=timezone.now().date(),
        )
        self.sub.trial_ends_at = timezone.now() - datetime.timedelta(days=60)
        self.sub.status = ServiceSubscription.Status.TRIAL
        self.sub.save(update_fields=["trial_ends_at", "status"])

        year, month = timezone.now().year, timezone.now().month
        close_compensation_month(period_year=year, period_month=month, actor=self.admin)
        self.assertFalse(AcquisitionCommissionLine.objects.exists())

    def test_split_billing_over_one_month_still_reads_as_paid(self):
        """شهرٌ فُوتر على سجلَّين: **أيُّ** سجلٍّ متقاطعٍ مسدَّدٍ بالكامل = مدفوع.

        قراءةُ أحدثِ سجلٍّ وحدَه كانت تُنتج `PENDING` لشهرٍ مدفوعٍ بالكامل، فيبقى
        السطرُ معلَّقاً حتى يتدخّل مديرٌ يدويّاً.
        """
        acquisition = self._make_acquisition_with_trial_ended(months_ago=2)
        year, month = timezone.now().year, timezone.now().month
        last = _month_end(year, month)
        mid = datetime.date(year, month, 15)

        # السجلّ الأحدث (النصف الثاني) غيرُ مسدَّد، والأقدم (النصف الأول) مسدَّد.
        paid_invoice = SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number=f"INV-SPLIT-A-{year}{month}", customer=self.customer,
            invoice_date=mid, currency=self.currency,
            grand_total=Decimal("300.00"), amount_paid=Decimal("300.00"),
        )
        SubscriptionBillingRecord.objects.create(
            subscription=self.sub, period_start=datetime.date(year, month, 1), period_end=mid,
            invoice=paid_invoice, monthly_fee=Decimal("300.00"), total_amount=Decimal("300.00"),
        )
        SubscriptionBillingRecord.objects.create(
            subscription=self.sub, period_start=datetime.date(year, month, 16), period_end=last,
            invoice=None, monthly_fee=Decimal("0.00"), total_amount=Decimal("0.00"),
        )

        close_compensation_month(period_year=year, period_month=month, actor=self.admin)
        line = AcquisitionCommissionLine.objects.get(acquisition=acquisition, period_year=year, period_month=month)
        self.assertEqual(line.status, WalletLineStatus.ELIGIBLE)
        self.assertEqual(line.pending_reason, "")

    def test_default_compensation_dict_tracks_field_defaults_not_a_second_copy(self):
        """قيمُ «لا سياسة منشورة بعد» تُقرأ من تعريف الحقل لا من نسخةٍ ثانية.

        لو كُتبت حرفيّاً لصار للراتب والعمولة مصدرا حقيقةٍ اثنان، وتعديلُ default
        الحقل وحدَه يُبقي هذا المسارَ يدفع الرقمَ القديمَ بصمت.
        """
        from platform_ops.models import EmployeeCompensationPolicy as Policy
        from platform_ops.services import get_default_compensation_policy_dict

        # **مقارنةُ الدالّة بـ`get_field(...).default` وحدَها حلقةٌ مفرغة**: الدالّةُ صارت
        # تقرأ ذلك المصدرَ عينَه، فالتأكيدُ يصدُق مهما كان — ويصدُق أيضاً لو أُرجعت
        # الحرفيّاتُ ما دامت تساوي الافتراضيّاتَ اليوم، وهو بالضبط الانحرافُ الذي
        # يَدّعي الاختبارُ حراستَه. فيُثبَّت أوّلاً على قيم §٧ المعلَنة، ثم **يُغيَّر
        # افتراضُ الحقل** ويُطلب من الدالّة أن تتبعه — ولا تتبعه نسخةٌ ثانيةٌ أبداً.
        declared_in_spec = {
            "base_salary": Decimal("500.00"),
            "daily_hours": Decimal("3.00"),
            "weekly_days": Decimal("6"),
            "acquisition_commission_amount": Decimal("100.00"),
            "acquisition_commission_months": Decimal("3"),
            "accrual_day_of_month": Decimal("1"),
        }
        defaults = get_default_compensation_policy_dict()
        for field_name, expected in declared_in_spec.items():
            with self.subTest(field=field_name):
                self.assertEqual(Decimal(str(defaults[field_name])), expected)

        # الجزءُ الذي يستطيع السقوط: افتراضٌ مُغيَّرٌ يجب أن يظهر في الخرج.
        field = Policy._meta.get_field("base_salary")
        original_default = field.default
        try:
            field.default = Decimal("777.00")
            drifted = get_default_compensation_policy_dict()
        finally:
            field.default = original_default
        self.assertEqual(
            Decimal(str(drifted["base_salary"])), Decimal("777.00"),
            "الدالّة لا تقرأ تعريفَ الحقل — ثمّة نسخةٌ ثانيةٌ من الافتراضيّات في الكود.",
        )
        # وقد عادت القيمةُ الأصليةُ فلا تتسرّب إلى اختبارٍ آخر.
        self.assertEqual(
            Decimal(str(get_default_compensation_policy_dict()["base_salary"])), Decimal("500.00"),
        )


class CommissionSurvivesServiceTransferTest(PilotScenarioBase):
    """معيار «لا خلط بين جالب العميل وموظف خدمته» — ثلاثُ قواعدَ لكلٍّ اختبارُها."""

    def setUp(self):
        super().setUp()
        self.new_user = User.objects.create_user(
            username="pilot_successor", email="ps@platform.local", password="x",
        )
        self.new_employee = PlatformEmployee.objects.create(
            user=self.new_user, specialty="data_entry", status=PlatformEmployee.Status.ACTIVE,
        )
        self.acquisition = CustomerAcquisition.objects.create(
            tenant=self.tenant, acquired_by=self.employee, acquired_at=timezone.now().date(),
        )
        self.sub.trial_ends_at = timezone.now() - datetime.timedelta(days=90)
        self.sub.status = ServiceSubscription.Status.ACTIVE
        self.sub.save(update_fields=["trial_ends_at", "status"])

    def _paid(self, year, month):
        invoice = SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number=f"INV-XFER-{year}-{month}", customer=self.customer,
            invoice_date=_month_end(year, month), currency=self.currency,
            grand_total=Decimal("300.00"), amount_paid=Decimal("300.00"),
        )
        SubscriptionBillingRecord.objects.create(
            subscription=self.sub, period_start=datetime.date(year, month, 1), period_end=_month_end(year, month),
            invoice=invoice, monthly_fee=Decimal("300.00"), total_amount=Decimal("300.00"),
        )

    def _transfer_service_to_the_new_employee(self):
        from platform_ops.services import transfer_engagement
        old = Engagement.objects.get(employee=self.employee, tenant=self.tenant)
        return transfer_engagement(
            engagement=old, to_employee=self.new_employee, actor=self.admin, reason="نقل خدمة للاختبار",
        )

    def test_commission_stays_with_the_original_acquirer_after_transfer(self):
        year, month = timezone.now().year, timezone.now().month
        self._paid(year, month)
        self._transfer_service_to_the_new_employee()
        close_compensation_month(period_year=year, period_month=month, actor=self.admin)

        line = AcquisitionCommissionLine.objects.get(acquisition=self.acquisition)
        # الجالبُ هو المستفيد دوماً — لا موظّف الخدمة الحالي.
        self.assertEqual(line.employee_id, self.employee.pk)
        self.assertNotEqual(line.employee_id, self.new_employee.pk)

    def test_transfer_does_not_restart_the_three_month_window(self):
        year, month = timezone.now().year, timezone.now().month
        self._paid(year, month)
        close_compensation_month(period_year=year, period_month=month, actor=self.admin)

        year2, month2 = (year + 1, 1) if month == 12 else (year, month + 1)
        self._paid(year2, month2)
        self._transfer_service_to_the_new_employee()
        close_compensation_month(period_year=year2, period_month=month2, actor=self.admin)

        indexes = list(
            AcquisitionCommissionLine.objects
            .filter(acquisition=self.acquisition).order_by("commission_month_index")
            .values_list("commission_month_index", flat=True)
        )
        # النقلُ لا يُعيد العدّ إلى ١: الشهرُ الثاني يبقى ٢.
        self.assertEqual(indexes, [1, 2])
        self.assertTrue(
            all(
                line.employee_id == self.employee.pk
                for line in AcquisitionCommissionLine.objects.filter(acquisition=self.acquisition)
            )
        )


class WalletLineIntegrityTest(PilotScenarioBase):
    """لا حذفَ لسطرٍ مالي، ولا سطرَ تسويةٍ يعتمد نفسَه."""

    def setUp(self):
        super().setUp()
        year, month = timezone.now().year, timezone.now().month
        self.year, self.month = year, month
        close_compensation_month(period_year=year, period_month=month, actor=self.admin)
        self.salary = EmployeeSalaryLine.objects.get(
            employee=self.employee, period_year=year, period_month=month,
        )

    def test_adjustment_line_is_born_pending_and_unapproved(self):
        """سطرُ التسوية يمرّ بسلسلة الاعتماد ولا يقفز فوقها.

        وُلد سابقاً `ELIGIBLE` مختوماً بـ`approved_by`/`approved_at`، فمن يملك
        «تسوية» كان يمنح نفسَه مبلغاً معتمَداً بلا اعتمادٍ منفصل.
        """
        from platform_ops.services import adjust_wallet_line

        adjustment = adjust_wallet_line(
            kind="salary", line=self.salary, amount=Decimal("75.00"),
            reason="تصحيح أيام دوام", actor=self.admin,
        )
        self.assertEqual(adjustment.status, WalletLineStatus.PENDING)
        self.assertIsNone(adjustment.approved_by_id)
        self.assertIsNone(adjustment.approved_at)
        self.assertEqual(adjustment.adjustment_of_id, self.salary.pk)
        self.assertEqual(adjustment.sequence, 1)
        # والأصلُ لم يُمسّ ولم يُحذف.
        self.salary.refresh_from_db()
        self.assertEqual(self.salary.sequence, 0)
        self.assertEqual(EmployeeSalaryLine.objects.filter(pk=self.salary.pk).count(), 1)

    def test_reversed_line_cannot_be_reversed_twice_and_paid_cannot_be_reversed(self):
        from platform_ops.services import WalletConflict, reverse_wallet_line, transition_wallet_line

        reversed_line = reverse_wallet_line(
            kind="salary", line=self.salary, reason="خطأ في الاحتساب", actor=self.admin,
        )
        self.assertEqual(reversed_line.status, WalletLineStatus.REVERSED)
        with self.assertRaises(WalletConflict) as ctx:
            reverse_wallet_line(kind="salary", line=reversed_line, reason="مرة ثانية", actor=self.admin)
        self.assertEqual(ctx.exception.code, "already_reversed")

        # سطرٌ مصروفٌ لا يُعكس — يُصحَّح بسطر تسويةٍ ظاهر.
        other = EmployeeSalaryLine.objects.create(
            employee=self.employee, period_year=self.year, period_month=self.month, sequence=9,
            amount=Decimal("500.00"), status=WalletLineStatus.APPROVED,
            idempotency_key="platform_ops:wallet:test:paid-line",
        )
        payable = transition_wallet_line(kind="salary", line=other, to_status=WalletLineStatus.PAYABLE)
        paid = transition_wallet_line(kind="salary", line=payable, to_status=WalletLineStatus.PAID)
        with self.assertRaises(WalletConflict) as ctx2:
            reverse_wallet_line(kind="salary", line=paid, reason="محاولة عكس مصروف", actor=self.admin)
        self.assertEqual(ctx2.exception.code, "cannot_reverse_paid")

    def test_reversal_and_adjustment_each_write_an_activity_naming_the_actor(self):
        """تغييرُ مبلغٍ مستحقٍّ لا يمرّ بلا أثرٍ يسمّي فاعلَه.

        الصفُّ يحمل السببَ ولا يحمل مَن فعل ولا متى؛ و`PlatformActivityLog` بنيةٌ
        موظَّفيّةٌ بلا عمود فاعل، فيُعلَّق السجلُّ على موظّف السطر ويُثبَّت الفاعلُ
        في `details.actor_user_id` صراحةً.
        """
        from platform_ops.services import adjust_wallet_line, reverse_wallet_line

        before = PlatformActivityLog.objects.count()
        adjust_wallet_line(
            kind="salary", line=self.salary, amount=Decimal("40.00"),
            reason="تسوية أيام", actor=self.admin,
        )
        reverse_wallet_line(
            kind="salary", line=self.salary, reason="خطأ في الاحتساب", actor=self.admin,
        )
        self.assertEqual(PlatformActivityLog.objects.count(), before + 2)

        rows = list(
            PlatformActivityLog.objects
            .filter(entity_type="wallet_line:salary").order_by("pk")
        )
        self.assertEqual(len(rows), 2)
        operations = {row.details.get("operation") for row in rows}
        self.assertEqual(operations, {"adjust_wallet_line", "reverse_wallet_line"})
        for row in rows:
            self.assertEqual(row.employee_id, self.employee.pk)
            self.assertEqual(row.details.get("actor_user_id"), self.admin.pk)

    def test_closed_month_is_not_recomputed_when_policy_changes_later(self):
        """تعديلُ سياسةٍ لاحقةٍ لا يعيد حساب شهرٍ مُغلَق (§٧)."""
        from platform_ops.services import (
            activate_performance_evaluation_policy,
            create_performance_evaluation_policy_draft,
        )

        before = list(
            EmployeeSalaryLine.objects
            .filter(period_year=self.year, period_month=self.month)
            .order_by("pk").values_list("pk", "amount", "status")
        )
        draft = create_performance_evaluation_policy_draft(
            actor=self.admin,
            weights={"task_completion": 70, "quality_accuracy": 10, "sla_adherence": 10, "customer_satisfaction": 10},
        )
        activate_performance_evaluation_policy(policy=draft, actor=self.admin, activation_reason="سياسة لاحقة")

        close, created = close_compensation_month(
            period_year=self.year, period_month=self.month, actor=self.admin,
        )
        self.assertFalse(created)
        after = list(
            EmployeeSalaryLine.objects
            .filter(period_year=self.year, period_month=self.month)
            .order_by("pk").values_list("pk", "amount", "status")
        )
        self.assertEqual(before, after)


class PilotChoiceColumnWidthTest(SimpleTestCase):
    """طولُ العمود مقابل أطولِ مفتاحٍ لكلّ حقل choices جديد في 210-D.

    عمودٌ أقصرُ من أطولِ مفتاحه **يُلغي القيدَ بصمتٍ** على MySQL ولا يكشفه SQLite.
    """

    def test_every_new_choices_column_fits_its_longest_key(self):
        from platform_ops.models import (
            AcquisitionCommissionLine as CommissionLine,
            EmployeeCompensationPolicy,
            EmployeeCompensationPolicyEvent,
            EmployeeSalaryLine as SalaryLine,
            PerformanceEvaluationPolicy,
            PerformanceEvaluationPolicyEvent,
        )
        fields = [
            (PerformanceEvaluationPolicy, "status"),
            (PerformanceEvaluationPolicyEvent, "action"),
            (EmployeeCompensationPolicy, "status"),
            (EmployeeCompensationPolicyEvent, "action"),
            (SalaryLine, "status"),
            (CommissionLine, "status"),
        ]
        for model, name in fields:
            with self.subTest(model=model.__name__, field=name):
                field = model._meta.get_field(name)
                keys = [key for key, _ in (field.choices or [])]
                self.assertTrue(keys)
                longest = max(keys, key=len)
                self.assertGreaterEqual(field.max_length, len(longest))


def _month_end(year, month):
    import calendar
    _, last_day = calendar.monthrange(year, month)
    return datetime.date(year, month, last_day)


class PilotApiSurfaceTest(PilotScenarioBase):
    """عزلٌ ومسارٌ سعيد عبر الـAPI الحقيقي لأسطح 210-D الجديدة."""

    def setUp(self):
        super().setUp()
        from rest_framework.test import APIClient
        self.client = APIClient()

    def test_non_admin_cannot_manage_evaluation_policy(self):
        self.client.force_authenticate(self.staff_user)
        resp = self.client.post("/api/platform/ops/performance-evaluation-policies/draft/", {}, format="json")
        self.assertEqual(resp.status_code, 403)

    def test_admin_can_draft_and_activate_evaluation_policy(self):
        self.client.force_authenticate(self.admin)
        resp = self.client.post("/api/platform/ops/performance-evaluation-policies/draft/", {}, format="json")
        self.assertEqual(resp.status_code, 201, resp.data)
        policy_id = resp.data["id"]
        resp = self.client.post(
            f"/api/platform/ops/performance-evaluation-policies/{policy_id}/activate/",
            {"activation_reason": "إطلاق الـpilot"}, format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["status"], "active")

    def test_employee_reads_own_wallet_not_others(self):
        year, month = timezone.now().year, timezone.now().month
        close_compensation_month(period_year=year, period_month=month, actor=self.admin)
        other_user = User.objects.create_user(username="pilot_other", email="po@platform.local", password="x")
        other_employee = PlatformEmployee.objects.create(user=other_user, status=PlatformEmployee.Status.ACTIVE)

        self.client.force_authenticate(self.staff_user)
        resp = self.client.get(f"/api/platform/ops/employees/{self.employee.pk}/wallet/?year={year}&month={month}")
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["salary_lines"][0]["amount"], "500.00")

        # `PlatformEmployeeViewSet.get_queryset` يحصر غير المدير بصفّه هو فقط —
        # فموظفٌ آخر غير موجودٍ أصلاً ضمن نطاقه (404)، بنفس اصطلاح `performance`/`activity`.
        resp_forbidden = self.client.get(f"/api/platform/ops/employees/{other_employee.pk}/wallet/?year={year}&month={month}")
        self.assertEqual(resp_forbidden.status_code, 404)

    def test_wallet_refuses_an_explicit_tenant_argument_from_the_request(self):
        """المحفظة تقرأ سطوراً مشتقّةً من ارتباطات الموظّف، فتلزمها قاعدةُ العزل نفسُها.

        `performance` كانت تحرس هذا و`wallet` لا — ووسيطُ شركةٍ صريحٌ يُرفض بـ400
        لا يُتجاهل بصمت، لأنّ التجاهلَ الصامتَ يُقنع الطالبَ أنّ نطاقَه طُبِّق.
        """
        year, month = timezone.now().year, timezone.now().month
        close_compensation_month(period_year=year, period_month=month, actor=self.admin)
        self.client.force_authenticate(self.admin)

        for key in ("tenant", "tenants", "tenant_ids", "tenant_id"):
            resp = self.client.get(
                f"/api/platform/ops/employees/{self.employee.pk}/wallet/"
                f"?year={year}&month={month}&{key}={self.tenant.pk}"
            )
            self.assertEqual(resp.status_code, 400, f"{key}: {resp.data}")
            self.assertEqual(resp.data["code"], "cross_tenant_query_disallowed_from_request")

        # وبلا الوسيط تعمل كما كانت.
        ok = self.client.get(
            f"/api/platform/ops/employees/{self.employee.pk}/wallet/?year={year}&month={month}"
        )
        self.assertEqual(ok.status_code, 200, ok.data)

    def test_month_close_endpoint_is_idempotent_and_admin_only(self):
        self.client.force_authenticate(self.staff_user)
        resp = self.client.post(
            "/api/platform/ops/compensation/close/", {"period_year": 2026, "period_month": 1}, format="json",
        )
        self.assertEqual(resp.status_code, 403)

        self.client.force_authenticate(self.admin)
        year, month = timezone.now().year, timezone.now().month
        resp1 = self.client.post(
            "/api/platform/ops/compensation/close/", {"period_year": year, "period_month": month}, format="json",
        )
        self.assertEqual(resp1.status_code, 201, resp1.data)
        resp2 = self.client.post(
            "/api/platform/ops/compensation/close/", {"period_year": year, "period_month": month}, format="json",
        )
        self.assertEqual(resp2.status_code, 200, resp2.data)
        self.assertEqual(resp1.data["id"], resp2.data["id"])


class PilotCompletionDenominatorInUnitsTest(PilotScenarioBase):
    """المحور ١: البسطُ والمقامُ بالوحدات نفسِها — لا مقامٌ بعددِ الأوامر مقابلَ بسطٍ بالوحدات.

    البيئةُ الأساسُ تُثبّت `base_units=1.00` و`per_line_weight=0.00` و`line_count=1`،
    فتصير كلُّ أمرِ عملٍ وحدةً واحدةً بالضبط — وعندها يتساوى عددُ الصفوف ومجموعُ
    الوحدات رقمياً فيستحيل أن يظهر الخللُ أصلاً (ولذلك بقي
    `test_task_completion_uses_assigned_work_when_capacity_not_configured` أخضرَ
    قبل الإصلاح وبعده: لا يفرّق بين الصفوف والوحدات فلا يحرسُ شيئاً هنا).
    فتُفعَّل هنا نسخةُ كتالوجٍ بوزنِ سطرٍ موجب **قبل** إنشاء أيّ عمل، ليقرأ الطرفان
    النسخةَ نفسَها فلا يُصنَع فرقٌ مفتعلٌ بين نسختين يُنجح الاختبارَ لغير سببه.
    """

    def _activate_multi_unit_catalog(self, *, per_line_weight=Decimal("0.50")):
        draft = create_service_unit_catalog_draft(actor=self.admin)
        update_service_unit_catalog_entries(
            catalog=draft,
            entries=[{
                "document_type": ServiceDocumentType.SALES_INVOICE,
                "base_units": Decimal("1.00"), "per_line_weight": per_line_weight,
            }],
            actor=self.admin,
        )
        return activate_service_unit_catalog(
            catalog=draft, actor=self.admin, activation_reason="وزنُ سطرٍ موجبٌ للوحدات",
        )

    def _work_order_with_lines(self, *, received_at, line_count, approve):
        """أمرُ عملٍ بفاتورةٍ ذاتِ بنودٍ متعددة؛ `approve=False` يتركه مُسنَداً غيرَ مُسلَّم."""
        self._invoice_seq += 1
        wo = create_work_order(
            tenant=self.tenant, title=f"أمر عمل وحدات {self._invoice_seq}", received_at=received_at,
        )
        wo = assign_work_order(work_order=wo, assignee=self.employee)
        invoice = SalesInvoice.objects.create(
            tenant=self.tenant, invoice_number=f"INV-UNITS-{self._invoice_seq}", customer=self.customer,
            invoice_date=received_at.date(), currency=self.currency,
        )
        for _ in range(line_count):
            SalesInvoiceLine.objects.create(
                tenant=self.tenant, invoice=invoice, product=self.product,
                quantity=Decimal("1"), unit_price=Decimal("10"),
            )
        link = link_work_order_document(
            work_order=wo, document_type=ServiceDocumentType.SALES_INVOICE, document_id=invoice.pk,
        )
        # العددُ يُرصد من الفاتورة نفسِها لا يُصدَّق تصريحاً؛ فتوقُّعُ الوحدات أدناه
        # **مشتقٌّ** من هذا الرقم لا مُختَرَعٌ في رأس الاختبار.
        self.assertEqual(link.line_count, line_count)
        if not approve:
            return wo, link
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.SCREENING, now=received_at)
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.DATA_ENTRY, now=received_at)
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.REVIEW, now=received_at)
        deliverable = submit_work_order_deliverable(
            work_order=wo, document_link_ids=[link.pk], submitted_by=self.staff_user,
        )
        approve_work_order_deliverable_with_usage(deliverable=deliverable, reviewed_by=self.admin)
        return wo, link

    def test_half_the_assigned_units_scores_fifty_not_a_capped_hundred(self):
        self._activate_multi_unit_catalog()
        now = timezone.now()
        received = now - datetime.timedelta(minutes=5)
        self._work_order_with_lines(received_at=received, line_count=3, approve=True)
        self._work_order_with_lines(received_at=received, line_count=3, approve=False)

        result = calculate_employee_pilot_performance(
            employee=self.employee, period_year=now.year, period_month=now.month,
        )
        axis = result["axes"]["task_completion"]
        # 1.00 + 3×0.50 = 2.50 لكلّ أمر؛ أمرانِ مُسندانِ = 5.00، وواحدٌ أُنجز = 2.50.
        self.assertEqual(axis["numerator"], 2.5)
        self.assertEqual(axis["denominator"], 5.0)
        # المقامُ بعددِ الأوامر (2) كان يُنتج 2.50÷2 = 125% تُقصُّ بصمتٍ إلى 100:
        # درجةٌ كاملةٌ لموظّفٍ أنجز نصفَ ما أُسند إليه. والصحيحُ 50%.
        self.assertEqual(axis["score"], Decimal("50.00"))

    def test_work_beyond_capacity_is_surfaced_not_folded_into_a_hundred(self):
        self._activate_multi_unit_catalog()
        self.employee.capacity_target = Decimal("1.00")
        self.employee.save(update_fields=["capacity_target"])
        now = timezone.now()
        self._work_order_with_lines(
            received_at=now - datetime.timedelta(minutes=5), line_count=3, approve=True,
        )
        result = calculate_employee_pilot_performance(
            employee=self.employee, period_year=now.year, period_month=now.month,
        )
        axis = result["axes"]["task_completion"]
        # الدرجةُ تبقى مقصوصةً عند 100 لأنّ المركَّبَ الموزون لا يقبل أكثر…
        self.assertEqual(axis["score"], Decimal("100.00"))
        # …والنسبةُ الخامُ محفوظةٌ تُقرأ: 2.50 وحدةً على طاقةٍ 1.00 = 250%.
        self.assertEqual(axis["raw_percent"], 250.0)

    def test_onboarding_units_do_not_inflate_the_numerator_past_the_denominator(self):
        """البسطُ والمقامُ من الشركات نفسِها — وحدةُ `onboarding` لا تدخل أحدَهما وحدَه.

        §٥ تستبعد `onboarding` من الهدف؛ فمقامٌ محصورٌ بارتباطات `standard` وبسطٌ
        يجمع كلَّ وحدات الموظّف كان يُدخل وحداتِ التهيئة في البسط بلا نظيرٍ في
        المقام، فترتفع النسبةُ فوق المئة بلا عملٍ إضافيٍّ حقيقيّ.
        """
        self._activate_multi_unit_catalog()
        now = timezone.now()
        received = now - datetime.timedelta(minutes=5)
        self._work_order_with_lines(received_at=received, line_count=3, approve=True)

        # شركةٌ ثانيةٌ بارتباطِ `onboarding` — عملُها معتمَدٌ ويُنتج وحداتٍ للموظّف،
        # لكنّه مستبعدٌ من المقام بنصّ §٥.
        other = Tenant.objects.create(TenantID=4102, CompanyName="شركة تهيئة")
        Engagement.objects.create(
            employee=self.employee, tenant=other,
            kind=Engagement.Kind.ONBOARDING, status=Engagement.Status.ACTIVE,
        )
        ServiceSubscription.objects.create(
            tenant=other, status=ServiceSubscription.Status.ACTIVE, plan="standard",
            included_quota=1000, consumed_quota=0,
        )
        customer2 = Partner.objects.create(tenant=other, name="عميل تهيئة", partner_type="Customer")
        product2 = Product.objects.create(tenant=other, sku="ONB-SVC-1", name_ar="خدمة تهيئة", is_service=True)
        wo2 = create_work_order(tenant=other, title="أمر تهيئة", received_at=received)
        wo2 = assign_work_order(work_order=wo2, assignee=self.employee)
        invoice2 = SalesInvoice.objects.create(
            tenant=other, invoice_number="INV-ONB-1", customer=customer2,
            invoice_date=received.date(), currency=self.currency,
        )
        for _ in range(3):
            SalesInvoiceLine.objects.create(
                tenant=other, invoice=invoice2, product=product2,
                quantity=Decimal("1"), unit_price=Decimal("10"),
            )
        link2 = link_work_order_document(
            work_order=wo2, document_type=ServiceDocumentType.SALES_INVOICE, document_id=invoice2.pk,
        )
        wo2 = transition_work_order_status(work_order=wo2, target_status=WorkOrder.Status.SCREENING, now=received)
        wo2 = transition_work_order_status(work_order=wo2, target_status=WorkOrder.Status.DATA_ENTRY, now=received)
        wo2 = transition_work_order_status(work_order=wo2, target_status=WorkOrder.Status.REVIEW, now=received)
        deliv2 = submit_work_order_deliverable(
            work_order=wo2, document_link_ids=[link2.pk], submitted_by=self.staff_user,
        )
        approve_work_order_deliverable_with_usage(deliverable=deliv2, reviewed_by=self.admin)

        result = calculate_employee_pilot_performance(
            employee=self.employee, period_year=now.year, period_month=now.month,
        )
        axis = result["axes"]["task_completion"]
        # 2.50 للشركة القياسية وحدَها في الطرفين — لا 5.00 في البسط مقابل 2.50 في المقام.
        self.assertEqual(axis["numerator"], 2.5)
        self.assertEqual(axis["denominator"], 2.5)
        self.assertEqual(axis["score"], Decimal("100.00"))
        self.assertEqual(axis["raw_percent"], 100.0)

    def test_axis_detail_shows_both_the_policy_weight_and_the_effective_one(self):
        """§٥: «تعرض الشاشة … الوزن الأصلي والفعلي» — الفعليُّ وحدَه يكتم إسقاطَ محور."""
        self._activate_multi_unit_catalog()
        now = timezone.now()
        self._work_order_with_lines(
            received_at=now - datetime.timedelta(minutes=5), line_count=3, approve=True,
        )
        result = calculate_employee_pilot_performance(
            employee=self.employee, period_year=now.year, period_month=now.month,
        )
        satisfaction = result["axes"]["customer_satisfaction"]
        # لا تقييماتَ زبائن فالمحورُ غيرُ منطبقٍ: وزنُه الفعليُّ صفرٌ وقد أُعيد توزيعُه،
        # لكنّ وزنَه الأصليَّ في السياسة يبقى 10 ظاهراً للقارئ.
        self.assertFalse(satisfaction["applicable"])
        self.assertEqual(Decimal(str(satisfaction["weight_original"])), Decimal("10"))
        self.assertEqual(satisfaction["weight"], Decimal("0.00"))
        completion = result["axes"]["task_completion"]
        self.assertEqual(Decimal(str(completion["weight_original"])), Decimal("40"))
        # المنطبقُ أخذ نصيبَه من الوزن المُعاد توزيعه فصار فعليُّه أكبرَ من أصليِّه.
        self.assertGreater(completion["weight"], Decimal("40"))

    def test_link_without_a_catalogue_entry_is_counted_and_shown_not_dropped(self):
        """بندٌ بلا نظيرٍ في الكتالوج: يُعدُّ ويُعرض، ولا يُطرح من المقام صامتاً.

        الخيارُ المُتَّخذ في الإصلاح: لا يُرفع خطأٌ (فيُسقِط شاشةَ الأداء كلَّها بسبب
        نوعٍ واحدٍ غير مُكتلَج)، ولا يُبتلع صامتاً (فيصغّر المقامَ ويرفع الدرجةَ بغير
        حقّ) — بل يُعدُّ ويُعلَن. وهذا الاختبارُ هو ما يحرس ذلك الخيار.
        """
        self._activate_multi_unit_catalog()
        now = timezone.now()
        received = now - datetime.timedelta(minutes=5)
        self._work_order_with_lines(received_at=received, line_count=3, approve=True)

        # `journal_entry` نوعٌ صالحٌ في `ServiceDocumentType` وليس في الكتالوج المُفعَّل
        # (وفيه `sales_invoice` وحده)، و`_observe_document_line_count` تُعيد `None`
        # لغير فاتورة البيع فيبقى العددُ تصريحاً — ولا يُسلَّم الأمرُ فلا يُرفع خطأُ
        # الدفتر عن نوعٍ غيرِ مُكتلَج أصلاً.
        self._invoice_seq += 1
        bare_wo = create_work_order(
            tenant=self.tenant, title="أمر عمل بنوعٍ غيرِ مُكتلَج", received_at=received,
        )
        bare_wo = assign_work_order(work_order=bare_wo, assignee=self.employee)
        link_work_order_document(
            work_order=bare_wo, document_type=ServiceDocumentType.JOURNAL_ENTRY,
            document_id=987654, line_count=4,
        )

        result = calculate_employee_pilot_performance(
            employee=self.employee, period_year=now.year, period_month=now.month,
        )
        axis = result["axes"]["task_completion"]
        self.assertEqual(axis["uncatalogued_document_links"], 1)
        # المقامُ يبقى وحداتِ ما يُمكن احتسابُه (2.50) ولا يُزاد بتخمينٍ عن نوعٍ لا سعرَ له.
        self.assertEqual(axis["denominator"], 2.5)
