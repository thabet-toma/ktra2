"""اختبارات المرحلة الخامسة (م٥) — المقاييس الستة وPolicyProfile والدرجة المركبة وPerformanceSnapshot.

تختبر المتطلبات الصارمة للمرحلة الخامسة:
1. «بيانات غير كافية» تظهر فعلاً تحت الحد الأدنى للعينة — والخدمة تعيد الحالة صراحة (status='insufficient_data', composite_score=None).
2. إعادة توزيع الوزن: سقوط محور غير منطبق يبقي المجموع 100% بالضبط (اختبار بمحور ساقط ثم بمحورين).
3. لقطة السياسة: تعديل PolicyProfile لا يغير درجة شهر ملتقط ولا أجل أمر سابق.
4. التقاط اللقطة idempotent: تشغيل مرتين للشهر نفسه ينتج لقطة واحدة وأثراً واحداً.
5. العرض والدخول لا يُعدّان عملاً: نشاط العرض والقراءة لا يحرك أي مقياس.
6. الإنشاء يدخل الأداء بعد الاعتماد لا قبله.
7. الإلغاء لا يخصم: أمر ملغى يظهر في معدل إعادة العمل ولا ينقص الدرجة المركبة.
8. الاستعلام العابر لا يقبل قائمة شركات من الطلب — محاولة صريحة تُرفض بـ 400 والشركات تبقى مشتقة من الارتباطات.
9. طول العمود مقابل أطول رمز لكل حقل choices جديد (PerformanceSnapshot.status).
10. التحقق من المقاييس الستة المغلقة بأسمائها ومقاماتها المعلنة.
"""
from datetime import date, datetime, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from tenants.models import Tenant

from platform_ops.models import (
    Engagement,
    PerformanceSnapshot,
    PlatformEmployee,
    PolicyProfile,
    ServiceSubscription,
    WorkOrder,
    WorkOrderDeliverable,
)
from platform_ops.services import (
    ALL_PERFORMANCE_AXES,
    ALL_SIX_METRICS,
    AXIS_ATTENDANCE_REGULARITY,
    AXIS_CUSTOMER_RATING,
    AXIS_PRODUCTIVITY,
    AXIS_QUALITY,
    AXIS_SALES_VALUE,
    AXIS_SLA_COMPLIANCE,
    AXIS_SPEED_EFFICIENCY,
    DEFAULT_AXIS_WEIGHTS,
    METRIC_COMPLETED_WORK_VOLUME,
    METRIC_FIRST_TIME_APPROVAL,
    METRIC_PROCESSED_SALES_VALUE,
    METRIC_REWORK_RATE,
    METRIC_SLA_COMPLIANCE,
    calculate_employee_performance,
    capture_performance_snapshot,
    create_work_order,
    rank_employees_performance,
    redistribute_axis_weights,
    review_work_order_deliverable,
    submit_work_order_deliverable,
    transition_work_order_status,
)

User = get_user_model()


class PerformanceChoiceColumnWidthTest(SimpleTestCase):
    """طول العمود مقابل أطول مفتاح رمز — حقل choices الجديد."""

    def test_performance_snapshot_status_fits_its_longest_key(self):
        """عمود status في PerformanceSnapshot يتسع لأطول رمز."""
        field = PerformanceSnapshot._meta.get_field("status")
        keys = list(PerformanceSnapshot.Status.values)
        longest = max(keys, key=len)
        self.assertGreaterEqual(
            field.max_length,
            len(longest),
            f"PerformanceSnapshot.status: العمود {field.max_length} وأطول رمز '{longest}' طوله {len(longest)}.",
        )


class AxisWeightRedistributionTest(SimpleTestCase):
    """اختبار إعادة توزيع الأوزان عند سقوط المحاور غير المنطبقة."""

    def test_all_axes_sum_to_exact_one_hundred_percent(self):
        """محاور التقييم مجتمعة مجموع أوزانها 100% بالضبط."""
        weights = redistribute_axis_weights(
            DEFAULT_AXIS_WEIGHTS,
            set(ALL_PERFORMANCE_AXES),
        )
        self.assertEqual(len(weights), len(ALL_PERFORMANCE_AXES))
        self.assertEqual(sum(weights.values()), Decimal("100.00"))

        # أوزانٌ خامٌّ مجموعُها لا يساوي ١٠٠ — التطبيعُ هو ما يُختبَر هنا
        odd = {axis: Decimal(str(i + 1)) for i, axis in enumerate(ALL_PERFORMANCE_AXES)}
        normalized = redistribute_axis_weights(odd, set(ALL_PERFORMANCE_AXES))
        self.assertEqual(len(normalized), len(ALL_PERFORMANCE_AXES))
        self.assertEqual(sum(normalized.values()), Decimal("100.00"))
        # والترتيبُ النسبيُّ محفوظ: الأثقلُ خاماً يبقى الأثقلَ بعد التطبيع
        heaviest_raw = max(odd, key=lambda k: odd[k])
        self.assertEqual(max(normalized, key=lambda k: normalized[k]), heaviest_raw)

    def test_an_applicable_axis_missing_from_the_policy_weights_keeps_its_default(self):
        """محورٌ منطبقٌ لا تذكره السياسةُ يأخذ وزنَه الافتراضيّ لا صفراً.

        كان يُسقَط من التوزيع فيبقى «منطبقاً» بوزنٍ صفريّ: المجموعُ يظلّ ١٠٠ فيمرّ
        الاختبارُ المفروض، والتفصيلُ يعرض محوراً منطبقاً لا يساهم بشيء — تناقضٌ صامت.
        """
        partial = {AXIS_QUALITY: Decimal("50.00")}
        weights = redistribute_axis_weights(partial, set(ALL_PERFORMANCE_AXES))
        self.assertEqual(len(weights), len(ALL_PERFORMANCE_AXES))
        self.assertEqual(sum(weights.values()), Decimal("100.00"))
        for axis in ALL_PERFORMANCE_AXES:
            self.assertGreater(weights[axis], Decimal("0.00"), f"المحور {axis} بوزن صفريّ")

    def test_redistribution_with_one_dropped_axis_sums_to_exact_one_hundred_percent(self):
        """سقوط محور واحد (مثل تقييم الزبون دون عينة كافية) يعيد توزيع وزنه ليبقى المجموع 100.00% بالضبط."""
        applicable = set(ALL_PERFORMANCE_AXES) - {AXIS_CUSTOMER_RATING}
        weights = redistribute_axis_weights(DEFAULT_AXIS_WEIGHTS, applicable)
        self.assertEqual(len(weights), len(ALL_PERFORMANCE_AXES) - 1)
        self.assertNotIn(AXIS_CUSTOMER_RATING, weights)
        total = sum(weights.values())
        self.assertEqual(
            total,
            Decimal("100.00"),
            f"مجموع الأوزان بعد سقوط محور واحد ليس 100%: {total} (الأوزان: {weights})",
        )

    def test_redistribution_with_two_dropped_axes_sums_to_exact_one_hundred_percent(self):
        """سقوط محورين (مثل تقييم الزبون والانضباط) يعيد توزيع وزنهما ليبقى المجموع 100.00% بالضبط."""
        applicable = set(ALL_PERFORMANCE_AXES) - {AXIS_CUSTOMER_RATING, AXIS_ATTENDANCE_REGULARITY}
        weights = redistribute_axis_weights(DEFAULT_AXIS_WEIGHTS, applicable)
        self.assertEqual(len(weights), len(ALL_PERFORMANCE_AXES) - 2)
        self.assertNotIn(AXIS_CUSTOMER_RATING, weights)
        self.assertNotIn(AXIS_ATTENDANCE_REGULARITY, weights)
        total = sum(weights.values())
        self.assertEqual(
            total,
            Decimal("100.00"),
            f"مجموع الأوزان بعد سقوط محورين ليس 100%: {total} (الأوزان: {weights})",
        )


class PerformanceMetricsAndPolicyTest(TestCase):
    """اختبارات المقاييس الستة وسياسات التقييم والدرجة المركبة واللقطة الشهرية."""

    def setUp(self):
        self.tenant_a = Tenant.objects.create(TenantID=1051, CompanyName="Alpha Trading")
        self.tenant_b = Tenant.objects.create(TenantID=1052, CompanyName="Beta Logistics")
        self.tenant_unrelated = Tenant.objects.create(TenantID=1053, CompanyName="Unrelated Co")

        ServiceSubscription.objects.create(tenant=self.tenant_a, status=ServiceSubscription.Status.ACTIVE)
        ServiceSubscription.objects.create(tenant=self.tenant_b, status=ServiceSubscription.Status.ACTIVE)
        ServiceSubscription.objects.create(tenant=self.tenant_unrelated, status=ServiceSubscription.Status.ACTIVE)

        self.manager_user = User.objects.create_superuser(
            username="platform_mgr",
            email="mgr@ktra.local",
            password="pass",
        )
        self.staff_user = User.objects.create_user(
            username="platform_staff_khalil",
            email="khalil@ktra.local",
            password="pass",
        )
        self.employee = PlatformEmployee.objects.create(
            user=self.staff_user,
            specialty="data_entry",
            capacity_target=Decimal("20.00"),
            status=PlatformEmployee.Status.ACTIVE,
        )

        # ارتباطات الموظف المشروعة مع شركتين
        Engagement.objects.create(
            employee=self.employee,
            tenant=self.tenant_a,
            status=Engagement.Status.ACTIVE,
        )
        Engagement.objects.create(
            employee=self.employee,
            tenant=self.tenant_b,
            status=Engagement.Status.ACTIVE,
        )

        self.client = APIClient()

    def _complete_work_order(self, tenant, title, received_at, approved_at, kind=WorkOrder.Kind.DATA_ENTRY, is_rejected=False):
        """مساعد لإنشاء أمر عمل وإيصاله للاعتماد مع تسليمات ومراجعة."""
        wo = create_work_order(
            tenant=tenant,
            title=title,
            kind=kind,
            received_at=received_at,
        )
        wo.assignee = self.employee
        wo.save(update_fields=["assignee"])

        # transitions
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.SCREENING, now=received_at)
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.DATA_ENTRY, now=received_at)

        # deliverable
        deliv = submit_work_order_deliverable(
            work_order=wo,
            kind=WorkOrderDeliverable.Kind.NOTE,
            content="مخرجات العمل",
            submitted_by=self.staff_user,
        )

        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.REVIEW, now=received_at)

        if is_rejected:
            # مراجعة أولى بالرفض
            review_work_order_deliverable(
                deliverable=deliv,
                review_status=WorkOrderDeliverable.ReviewStatus.REJECTED,
                reviewed_by=self.manager_user,
                rejection_reason="بيانات ناقصة بحاجة لإعادة تدقيق",
            )
            # تسليمة ثانية مقبولة
            deliv2 = submit_work_order_deliverable(
                work_order=wo,
                kind=WorkOrderDeliverable.Kind.NOTE,
                content="مخرجات مصححة",
                submitted_by=self.staff_user,
            )
            review_work_order_deliverable(
                deliverable=deliv2,
                review_status=WorkOrderDeliverable.ReviewStatus.APPROVED,
                reviewed_by=self.manager_user,
            )
        else:
            review_work_order_deliverable(
                deliverable=deliv,
                review_status=WorkOrderDeliverable.ReviewStatus.APPROVED,
                reviewed_by=self.manager_user,
            )

        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.APPROVAL, now=approved_at)
        return wo

    # --------------------------------------------------------------------------
    # 1. اختبار كفاية العينة («بيانات غير كافية» تحت الحد الأدنى)
    # --------------------------------------------------------------------------

    def test_insufficient_data_verdict_when_below_minimum_sample_size(self):
        """الخدمة تُعيد حالة 'insufficient_data' و composite_score=None صراحة تحت الحد الأدنى."""
        # الحد الأدنى الافتراضي 5، سننشئ 3 أوامر عمل فقط
        base_time = timezone.now() - timedelta(days=10)
        for i in range(3):
            self._complete_work_order(
                tenant=self.tenant_a,
                title=f"أمر منجز {i+1}",
                received_at=base_time + timedelta(hours=i * 5),
                approved_at=base_time + timedelta(hours=i * 5 + 2),
            )

        perf = calculate_employee_performance(employee=self.employee)
        self.assertEqual(perf["sample_size"], 3)
        self.assertEqual(perf["min_sample_size"], 5)
        self.assertEqual(
            perf["status"],
            PerformanceSnapshot.Status.INSUFFICIENT_DATA,
            "الخدمة يجب أن تعيد حالة insufficient_data صراحة عندما تكون العينة ناقصة.",
        )
        self.assertIsNone(
            perf["composite_score"],
            "الدرجة المركبة يجب أن تكون None وليست رقماً مضللاً عند عدم كفاية البيانات.",
        )
        self.assertEqual(perf["status_message"], "بيانات غير كافية")

    def test_ranking_excludes_insufficient_data_from_rank_number(self):
        """الموظفون بعينة ناقصة يُستبعدون من الترتيب الرقمي (rank=None)."""
        base_time = timezone.now() - timedelta(days=10)
        # موظف 1 لديه 2 أمر عمل فقط (ناقص)
        for i in range(2):
            self._complete_work_order(
                tenant=self.tenant_a,
                title=f"أمر ناقص {i+1}",
                received_at=base_time + timedelta(hours=i * 2),
                approved_at=base_time + timedelta(hours=i * 2 + 1),
            )

        # موظف 2 لديه 6 أوامر عمل (كافٍ)
        staff_2 = User.objects.create_user(username="agent_salma", password="x")
        emp_2 = PlatformEmployee.objects.create(
            user=staff_2,
            specialty="data_entry",
            capacity_target=Decimal("10.00"),
            status=PlatformEmployee.Status.ACTIVE,
        )
        Engagement.objects.create(employee=emp_2, tenant=self.tenant_a, status=Engagement.Status.ACTIVE)

        for i in range(6):
            wo = create_work_order(tenant=self.tenant_a, title=f"أمر سلمى {i+1}", received_at=base_time)
            wo.assignee = emp_2
            wo.save()
            for st in (WorkOrder.Status.SCREENING, WorkOrder.Status.DATA_ENTRY, WorkOrder.Status.REVIEW, WorkOrder.Status.APPROVAL):
                wo = transition_work_order_status(work_order=wo, target_status=st, now=base_time + timedelta(hours=1))

        ranking = rank_employees_performance()
        salma_entry = next(r for r in ranking if r["employee_id"] == emp_2.id)
        khalil_entry = next(r for r in ranking if r["employee_id"] == self.employee.id)

        self.assertEqual(salma_entry["rank"], 1)
        self.assertIsNone(
            khalil_entry["rank"],
            "الموظف بعينة ناقصة يجب ألا يُعطى رقماً في الترتيب بل rank=None.",
        )

    # --------------------------------------------------------------------------
    # 2. لقطة السياسة (تعديل PolicyProfile لا يغير الماضي)
    # --------------------------------------------------------------------------

    def test_policy_profile_modification_does_not_change_past_snapshot_or_work_orders(self):
        """تعديل أوزان أو أهداف PolicyProfile لاحقاً لا يغير درجة شهر تم التقاطه ولا أجل أمر سابق."""
        # 1. إنشاء ملف سياسة לתخصص data_entry
        policy = PolicyProfile.objects.create(
            specialty="data_entry",
            name="سياسة الإدخال 2026",
            weights={
                AXIS_QUALITY: 30,
                AXIS_SLA_COMPLIANCE: 25,
                AXIS_PRODUCTIVITY: 25,
                AXIS_SPEED_EFFICIENCY: 20,
                AXIS_SALES_VALUE: 0,
            },
            min_sample_size=3,
        )

        # 2. إنشاء 4 أوامر عمل لشهر أغسطس 2026
        aug_start = timezone.make_aware(datetime(2026, 8, 5, 10, 0))
        for i in range(4):
            self._complete_work_order(
                tenant=self.tenant_a,
                title=f"أمر أغسطس {i+1}",
                received_at=aug_start + timedelta(hours=i * 4),
                approved_at=aug_start + timedelta(hours=i * 4 + 2),
            )

        # 3. التقاط لقطة أداء لشهر أغسطس 2026
        snapshot = capture_performance_snapshot(
            employee=self.employee,
            period_year=2026,
            period_month=8,
            captured_by=self.manager_user,
        )
        self.assertEqual(snapshot.status, PerformanceSnapshot.Status.CALCULATED)
        initial_score = snapshot.composite_score
        self.assertIsNotNone(initial_score)
        initial_policy_snapshot = snapshot.policy_snapshot

        # 4. تعديل PolicyProfile تعديلاً جذرياً
        policy.weights = {
            AXIS_QUALITY: 10,
            AXIS_SLA_COMPLIANCE: 10,
            AXIS_PRODUCTIVITY: 10,
            AXIS_SPEED_EFFICIENCY: 10,
            AXIS_SALES_VALUE: 60,
        }
        policy.min_sample_size = 50  # لو طبق على الماضي لأصبحت العينة غير كافية
        policy.save()

        # 5. التحقق من أن اللقطة الملتقطة لم تتغير إطلاقاً
        snapshot.refresh_from_db()
        self.assertEqual(
            snapshot.composite_score,
            initial_score,
            "تعديل السياسة لاحقاً غيّر الدرجة المركبة لشهر تم التقاطه وتجميده!",
        )
        self.assertEqual(snapshot.status, PerformanceSnapshot.Status.CALCULATED)
        self.assertEqual(
            snapshot.policy_snapshot["weights"],
            initial_policy_snapshot["weights"],
            "لقطة السياسة المحفوظة في اللقطة الشهرية تأثرت بتعديل PolicyProfile!",
        )

    # --------------------------------------------------------------------------
    # 3. التقاط اللقطة دالة idempotent
    # --------------------------------------------------------------------------

    def test_capture_performance_snapshot_is_idempotent(self):
        """تشغيل capture_performance_snapshot مرتين لنفس الشهر والموظف ينتج لقطة واحدة ولا يضاعف أثراً."""
        base_time = timezone.make_aware(datetime(2026, 7, 10, 10, 0))
        for i in range(5):
            self._complete_work_order(
                tenant=self.tenant_a,
                title=f"أمر يوليو {i+1}",
                received_at=base_time + timedelta(hours=i * 2),
                approved_at=base_time + timedelta(hours=i * 2 + 1),
            )

        snap1 = capture_performance_snapshot(
            employee=self.employee,
            period_year=2026,
            period_month=7,
            captured_by=self.manager_user,
        )

        snap2 = capture_performance_snapshot(
            employee=self.employee,
            period_year=2026,
            period_month=7,
            captured_by=self.manager_user,
        )

        self.assertEqual(snap1.id, snap2.id)
        count = PerformanceSnapshot.objects.filter(
            employee=self.employee,
            period_year=2026,
            period_month=7,
        ).count()
        self.assertEqual(count, 1, "تشغيل التقاط اللقطة مرتين أنشأ صفين في قاعدة البيانات!")

    # --------------------------------------------------------------------------
    # 4. العرض والدخول لا يُعدّان عملاً
    # --------------------------------------------------------------------------

    def test_viewing_and_login_activity_does_not_count_as_work(self):
        """استعراض أوامر العمل وتسجيل الدخول لا يحرّك أي مقياس من مقاييس الأداء."""
        self.client.force_authenticate(user=self.staff_user)
        # تسجيل دخول واستعراض قائمة أوامر العمل 5 مرات
        for _ in range(5):
            resp = self.client.get("/api/platform/ops/work-orders/")
            self.assertEqual(resp.status_code, status.HTTP_200_OK)

        perf = calculate_employee_performance(employee=self.employee)
        self.assertEqual(
            perf["sample_size"],
            0,
            "نشاط العرض والدخول حُسب كإنجاز عمل في حجم العينة!",
        )
        self.assertEqual(perf["metrics"][METRIC_COMPLETED_WORK_VOLUME]["numerator"], 0)
        self.assertEqual(perf["status"], PerformanceSnapshot.Status.INSUFFICIENT_DATA)

    # --------------------------------------------------------------------------
    # 5. الإنشاء يدخل الأداء بعد الاعتماد لا قبله
    # --------------------------------------------------------------------------

    def test_work_order_enters_performance_only_after_approval(self):
        """أمر العمل في الفرز أو الإدخال أو المراجعة أو مع تسليمة معلقة لا يدخل الأداء إلا بعد الاعتماد."""
        rec_at = timezone.now() - timedelta(hours=10)
        wo = create_work_order(tenant=self.tenant_a, title="أمر قيد التنفيذ", received_at=rec_at)
        wo.assignee = self.employee
        wo.save()

        # في حالة RECEIVED
        perf = calculate_employee_performance(employee=self.employee)
        self.assertEqual(perf["sample_size"], 0)

        # في حالة SCREENING ثم DATA_ENTRY
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.SCREENING)
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.DATA_ENTRY)
        perf = calculate_employee_performance(employee=self.employee)
        self.assertEqual(perf["sample_size"], 0)

        # تقديم تسليمة (REVIEW_STATUS = PENDING)
        submit_work_order_deliverable(
            work_order=wo,
            kind=WorkOrderDeliverable.Kind.NOTE,
            content="مخرجات لم تعتمد بعد",
            submitted_by=self.staff_user,
        )
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.REVIEW)
        perf = calculate_employee_performance(employee=self.employee)
        self.assertEqual(
            perf["sample_size"],
            0,
            "أمر العمل دخل في حساب الأداء قبل اعتماده!",
        )

        # الاعتماد
        app_at = timezone.now() - timedelta(hours=2)
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.APPROVAL, now=app_at)
        perf = calculate_employee_performance(employee=self.employee)
        self.assertEqual(
            perf["sample_size"],
            1,
            "أمر العمل المعتمد لم يدخل في الأداء بعد اعتماده!",
        )

    # --------------------------------------------------------------------------
    # 6. الإلغاء لا يخصم من الدرجة المركبة
    # --------------------------------------------------------------------------

    def test_cancellation_does_not_penalize_composite_score(self):
        """أمر العمل الملغى يظهر في معدل إعادة العمل المنفصل ولا ينقص الدرجة المركبة."""
        base_time = timezone.now() - timedelta(days=5)
        # 5 أوامر عمل معتمدة بنسبة 100%
        for i in range(5):
            self._complete_work_order(
                tenant=self.tenant_a,
                title=f"أمر ممتاز {i+1}",
                received_at=base_time + timedelta(hours=i * 2),
                approved_at=base_time + timedelta(hours=i * 2 + 1),
            )

        perf_before = calculate_employee_performance(employee=self.employee)
        self.assertEqual(perf_before["status"], PerformanceSnapshot.Status.CALCULATED)
        score_before = perf_before["composite_score"]
        self.assertEqual(perf_before["rework_rate"], Decimal("0.00"))

        # إنشاء وإلغاء أمرين
        for i in range(2):
            c_wo = create_work_order(tenant=self.tenant_a, title=f"أمر ملغى {i+1}", received_at=base_time)
            c_wo.assignee = self.employee
            c_wo.save()
            transition_work_order_status(work_order=c_wo, target_status=WorkOrder.Status.SCREENING)
            transition_work_order_status(work_order=c_wo, target_status=WorkOrder.Status.WAITING_CUSTOMER)
            transition_work_order_status(work_order=c_wo, target_status=WorkOrder.Status.CANCELLED)

        perf_after = calculate_employee_performance(employee=self.employee)
        self.assertEqual(
            perf_after["composite_score"],
            score_before,
            "الدرجة المركبة نقصت بسبب أوامر العمل الملغاة؛ الإلغاء يجب ألا يخصم آلياً من الدرجة.",
        )
        self.assertGreater(
            perf_after["rework_rate"],
            Decimal("0.00"),
            "معدل إعادة العمل لم يرصد أوامر العمل الملغاة.",
        )
        self.assertEqual(perf_after["metrics"][METRIC_REWORK_RATE]["numerator"], 2)

    # --------------------------------------------------------------------------
    # 7. الاستعلام العابر للشركات لا يقبل قائمة شركات من الطلب
    # --------------------------------------------------------------------------

    def test_cross_tenant_query_rejects_explicit_tenant_list_from_request(self):
        """محاولة تمرير معرّف أو قائمة شركات صريحة في الطلب تُرفض فوراً بـ 400."""
        self.client.force_authenticate(user=self.manager_user)

        # 1. على مسار الأداء عبر query params
        resp = self.client.get(
            f"/api/platform/ops/employees/{self.employee.id}/performance/?tenant={self.tenant_unrelated.pk}"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data.get("code"), "cross_tenant_query_disallowed_from_request")

        resp2 = self.client.get(
            f"/api/platform/ops/employees/{self.employee.id}/performance/?tenants={self.tenant_a.pk},{self.tenant_b.pk}"
        )
        self.assertEqual(resp2.status_code, status.HTTP_400_BAD_REQUEST)

        resp3 = self.client.get(
            f"/api/platform/ops/employees/{self.employee.id}/performance/?tenant_ids={self.tenant_a.pk}"
        )
        self.assertEqual(resp3.status_code, status.HTTP_400_BAD_REQUEST)

        # 2. على مسار التقاط اللقطة عبر payload
        resp_post = self.client.post(
            "/api/platform/ops/performance-snapshots/capture/",
            data={
                "employee": self.employee.id,
                "period_year": 2026,
                "period_month": 9,
                "tenants": [self.tenant_unrelated.pk],
            },
            format="json",
        )
        self.assertEqual(resp_post.status_code, status.HTTP_400_BAD_REQUEST)

    def test_cross_tenant_query_only_aggregates_engaged_tenants(self):
        """الاستعلام العابر يجمع فقط شركات الارتباطات المشروعة، ويتجاهل أي أمر بشركة غير مرتبطة."""
        base_time = timezone.now() - timedelta(days=2)
        # 3 أوامر بشركة أ (مرتبط بها)
        for i in range(3):
            self._complete_work_order(
                tenant=self.tenant_a,
                title=f"أمر شركة أ {i+1}",
                received_at=base_time + timedelta(hours=i * 2),
                approved_at=base_time + timedelta(hours=i * 2 + 1),
            )
        # أمران بشركة ب (مرتبط بها)
        for i in range(2):
            self._complete_work_order(
                tenant=self.tenant_b,
                title=f"أمر شركة ب {i+1}",
                received_at=base_time + timedelta(hours=i * 2),
                approved_at=base_time + timedelta(hours=i * 2 + 1),
            )
        # أمر مسند للموظف بشركة غير مرتبطة (تسريب محتمل لو لم يُفلتر بالارتباط)
        unrelated_wo = create_work_order(
            tenant=self.tenant_unrelated,
            title="أمر شركة غير مرتبطة",
            received_at=base_time,
        )
        unrelated_wo.assignee = self.employee
        unrelated_wo.save()
        for st in (WorkOrder.Status.SCREENING, WorkOrder.Status.DATA_ENTRY, WorkOrder.Status.REVIEW, WorkOrder.Status.APPROVAL):
            unrelated_wo = transition_work_order_status(work_order=unrelated_wo, target_status=st, now=base_time + timedelta(hours=1))

        perf = calculate_employee_performance(employee=self.employee)
        # المجموع يجب أن يكون 5 (3 من أ + 2 من ب)، والأمر السادس من الشركة غير المرتبطة يجب استبعاده
        self.assertEqual(
            perf["sample_size"],
            5,
            "الاستعلام العابر ضمّ أوامر لشركة لا يرتبط بها الموظف!",
        )

    # --------------------------------------------------------------------------
    # 8. التحقق من المقاييس الستة المعلنة ومقاماتها الصادقة
    # --------------------------------------------------------------------------

    def test_all_six_metrics_present_with_declared_denominators(self):
        """كل مقياس من المقاييس الستة موجود مع بسط ومقام معلن وصادق."""
        base_time = timezone.now() - timedelta(days=3)
        # أمر 1: معتمد من أول مراجعة وضمن الأجل
        self._complete_work_order(
            tenant=self.tenant_a,
            title="أمر أول مراجعة",
            received_at=base_time,
            approved_at=base_time + timedelta(hours=1),
            is_rejected=False,
        )
        # أمر 2: رُفض في المراجعة الأولى ثم اعتمد (ليس أول مراجعة)
        self._complete_work_order(
            tenant=self.tenant_a,
            title="أمر مع مراجعة ثانية",
            received_at=base_time + timedelta(hours=2),
            approved_at=base_time + timedelta(hours=5),
            is_rejected=True,
        )
        # أمر 3: مبيعات
        wo_sales = create_work_order(
            tenant=self.tenant_a,
            title="أمر مبيعات",
            kind=WorkOrder.Kind.SALES,
            received_at=base_time + timedelta(hours=6),
        )
        wo_sales.assignee = self.employee
        # القيمةُ الماليّةُ من **مُسلَّمٍ اعتُمد** لا من حمولة الزبون: حمولةُ القناة
        # يكتبها المرسِلُ الخارجيّ، فمقياسٌ يقرأ منها يمليه الطرفُ المستفيد.
        wo_sales.intake_payload = {"sales_value": "999999.00"}
        wo_sales.save()
        deliv_sales = submit_work_order_deliverable(
            work_order=wo_sales,
            kind=WorkOrderDeliverable.Kind.STRUCTURED_REPORT,
            payload={"sales_value": "15000.00"},
            submitted_by=self.staff_user,
        )
        review_work_order_deliverable(
            deliverable=deliv_sales,
            review_status=WorkOrderDeliverable.ReviewStatus.APPROVED,
            reviewed_by=self.manager_user,
        )
        for st in (WorkOrder.Status.SCREENING, WorkOrder.Status.DATA_ENTRY, WorkOrder.Status.REVIEW, WorkOrder.Status.APPROVAL):
            wo_sales = transition_work_order_status(work_order=wo_sales, target_status=st, now=base_time + timedelta(hours=7))

        perf = calculate_employee_performance(employee=self.employee)
        metrics = perf["metrics"]

        # التأكد من وجود المفاتيح الستة بالتمام والكمال
        for m_key in ALL_SIX_METRICS:
            self.assertIn(m_key, metrics, f"المقياس {m_key} مفقود من مخرجات التحليل!")

        # فحص نسبة القبول من أول مراجعة
        fta = metrics[METRIC_FIRST_TIME_APPROVAL]
        self.assertEqual(fta["name"], "نسبة القبول من أول مراجعة")
        self.assertEqual(fta["numerator"], 2)  # الأمر 1 وأمر المبيعات
        self.assertEqual(fta["denominator"], 3)
        self.assertIn("sample_size", fta)

        # فحص قيمة المبيعات المعالجة
        sales_m = metrics[METRIC_PROCESSED_SALES_VALUE]
        self.assertEqual(sales_m["name"], "قيمة مبيعات عالجها")
        self.assertEqual(sales_m["total_value"], Decimal("15000.00"))
        self.assertTrue(sales_m.get("is_display_only"))
        # والرقمُ الذي ادّعته الحمولةُ الخارجيّةُ لم يدخل الحساب إطلاقاً
        self.assertNotEqual(sales_m["total_value"], Decimal("999999.00"))


class SalesValueSourceTest(TestCase):
    """مَن يملك الرقمَ الماليَّ في «قيمةُ مبيعاتٍ عالجها».

    كانت القيمةُ تُقرأ من `intake_payload` — وهو JSON يكتبه المرسِلُ عبر القناة.
    ومنذ م٤ صار `amount` مسموحاً في الحمولة عن قصدٍ لأنّ الفاتورةَ تحمله. فاجتماعُ
    القرارين يجعل **حاملَ مفتاح القناة قادراً على رفع درجةِ موظّف** بكتابة رقمٍ أكبر.
    فيُحرَس المصدر: مُسلَّمٌ كتبه موظّفُنا **واعتمده مراجعٌ ثانٍ**، لا غير.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(TenantID=3101, CompanyName="Sales Source Co")
        ServiceSubscription.objects.create(
            tenant=self.tenant, status=ServiceSubscription.Status.ACTIVE, plan="growth"
        )
        self.staff_user = User.objects.create_user(
            username="sales_src_staff", email="sales_src@ktra.local", password="x"
        )
        self.reviewer = User.objects.create_superuser(
            username="sales_src_mgr", email="sales_src_mgr@ktra.local", password="x"
        )
        self.employee = PlatformEmployee.objects.create(
            user=self.staff_user, specialty="sales", status=PlatformEmployee.Status.ACTIVE
        )
        Engagement.objects.create(
            employee=self.employee, tenant=self.tenant, status=Engagement.Status.ACTIVE
        )

    def _approved_order(self, *, payload_claim=None):
        wo = create_work_order(
            tenant=self.tenant, title="أمر", kind=WorkOrder.Kind.SALES
        )
        wo.assignee = self.employee
        if payload_claim is not None:
            wo.intake_payload = payload_claim
        wo.save()
        for st in (
            WorkOrder.Status.SCREENING,
            WorkOrder.Status.DATA_ENTRY,
            WorkOrder.Status.REVIEW,
            WorkOrder.Status.APPROVAL,
        ):
            wo = transition_work_order_status(work_order=wo, target_status=st)
        return wo

    def test_a_channel_payload_cannot_inflate_the_sales_metric(self):
        """الحمولةُ الخارجيّةُ تدّعي مليوناً — والمقياسُ يبقى صفراً."""
        self._approved_order(payload_claim={"amount": "1000000.00", "sales_value": "999999"})

        perf = calculate_employee_performance(employee=self.employee)
        self.assertEqual(
            perf["processed_sales_value"],
            Decimal("0.00"),
            "حمولةُ القناة رفعت مقياسَ أداءٍ — الطرفُ الخارجيُّ يملي درجةَ موظّفنا.",
        )

    def test_only_an_approved_deliverable_feeds_the_sales_metric(self):
        """مُسلَّمٌ بانتظار المراجعة أو مرفوضٌ لا يُحتسَب؛ والمعتمَدُ وحدَه يُحتسَب."""
        wo_pending = self._approved_order()
        submit_work_order_deliverable(
            work_order=wo_pending,
            kind=WorkOrderDeliverable.Kind.STRUCTURED_REPORT,
            payload={"sales_value": "500.00"},
            submitted_by=self.staff_user,
        )

        wo_rejected = self._approved_order()
        deliv_rejected = submit_work_order_deliverable(
            work_order=wo_rejected,
            kind=WorkOrderDeliverable.Kind.STRUCTURED_REPORT,
            payload={"sales_value": "700.00"},
            submitted_by=self.staff_user,
        )
        review_work_order_deliverable(
            deliverable=deliv_rejected,
            review_status=WorkOrderDeliverable.ReviewStatus.REJECTED,
            reviewed_by=self.reviewer,
            rejection_reason="رقمٌ لا يطابق المستند.",
        )

        # لا شيءَ حتى الآن: لا مُسلَّمَ معتمَد
        self.assertEqual(
            calculate_employee_performance(employee=self.employee)["processed_sales_value"],
            Decimal("0.00"),
        )

        wo_approved = self._approved_order()
        deliv_approved = submit_work_order_deliverable(
            work_order=wo_approved,
            kind=WorkOrderDeliverable.Kind.STRUCTURED_REPORT,
            payload={"sales_value": "1200.00"},
            submitted_by=self.staff_user,
        )
        review_work_order_deliverable(
            deliverable=deliv_approved,
            review_status=WorkOrderDeliverable.ReviewStatus.APPROVED,
            reviewed_by=self.reviewer,
        )

        self.assertEqual(
            calculate_employee_performance(employee=self.employee)["processed_sales_value"],
            Decimal("1200.00"),
        )


class SnapshotIsActuallyFrozenTest(TestCase):
    """اللقطةُ الشهريّةُ **مجمَّدة** — والتجميدُ يُختبَر لا يُوعَد به.

    كان معدّلُ إعادة العمل يُنسَب للشهر عبر `updated_at` وهو `auto_now`: أيُّ لمسةٍ
    لاحقةٍ لصفٍّ ملغىً تنقله إلى شهرٍ آخر، فيتغيّر رقمُ شهرٍ التُقطت لقطتُه بلا أن
    يمسّه أحد. والوثيقةُ تسمّيها «لقطة مجمدة».
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(TenantID=3201, CompanyName="Frozen Co")
        ServiceSubscription.objects.create(
            tenant=self.tenant, status=ServiceSubscription.Status.ACTIVE, plan="growth"
        )
        self.staff_user = User.objects.create_user(
            username="frozen_staff", email="frozen@ktra.local", password="x"
        )
        self.employee = PlatformEmployee.objects.create(
            user=self.staff_user, specialty="data_entry", status=PlatformEmployee.Status.ACTIVE
        )
        Engagement.objects.create(
            employee=self.employee, tenant=self.tenant, status=Engagement.Status.ACTIVE
        )

    def _cancelled_order_at(self, moment):
        wo = create_work_order(tenant=self.tenant, title="أمر ملغى", received_at=moment)
        wo.assignee = self.employee
        wo.save(update_fields=["assignee"])
        wo = transition_work_order_status(
            work_order=wo, target_status=WorkOrder.Status.SCREENING, now=moment
        )
        wo = transition_work_order_status(
            work_order=wo, target_status=WorkOrder.Status.WAITING_CUSTOMER, now=moment
        )
        return transition_work_order_status(
            work_order=wo, target_status=WorkOrder.Status.CANCELLED, now=moment
        )

    def test_touching_a_cancelled_order_later_does_not_move_it_between_months(self):
        march = timezone.make_aware(datetime(2026, 3, 10, 9, 0))
        cancelled = self._cancelled_order_at(march)
        self.assertEqual(cancelled.cancelled_at, march)

        before = calculate_employee_performance(
            employee=self.employee, period_year=2026, period_month=3
        )
        self.assertEqual(before["metrics"][METRIC_REWORK_RATE]["numerator"], 1)

        # لمسةٌ لاحقةٌ ترفع `updated_at` إلى اليوم — ولا تنقل الأمرَ عن آذار
        cancelled.description = "ملاحظةٌ أُضيفت لاحقاً"
        cancelled.save(update_fields=["description", "updated_at"])
        cancelled.refresh_from_db()
        self.assertGreater(cancelled.updated_at, march)

        after = calculate_employee_performance(
            employee=self.employee, period_year=2026, period_month=3
        )
        self.assertEqual(
            after["metrics"][METRIC_REWORK_RATE]["numerator"],
            1,
            "لمسةُ صفٍّ نقلت أمراً ملغىً عن شهره — اللقطةُ ليست مجمَّدة.",
        )

        # ولا يظهر في الشهر الذي لُمس فيه
        touched_month = timezone.localtime(cancelled.updated_at)
        elsewhere = calculate_employee_performance(
            employee=self.employee,
            period_year=touched_month.year,
            period_month=touched_month.month,
        )
        if (touched_month.year, touched_month.month) != (2026, 3):
            self.assertEqual(elsewhere["metrics"][METRIC_REWORK_RATE]["numerator"], 0)


class PerformanceApiPeriodValidationTest(TestCase):
    """فترةٌ نصفُ محدَّدةٍ كانت تُعيد **كلَّ الأزمان** بصمتٍ وكأنّها تلك السنة."""

    def setUp(self):
        self.client = APIClient()
        self.manager = User.objects.create_superuser(
            username="period_mgr", email="period_mgr@ktra.local", password="x"
        )
        self.staff_user = User.objects.create_user(
            username="period_staff", email="period_staff@ktra.local", password="x"
        )
        self.employee = PlatformEmployee.objects.create(
            user=self.staff_user, specialty="data_entry", status=PlatformEmployee.Status.ACTIVE
        )
        self.client.force_authenticate(user=self.manager)

    def _perf(self, query):
        return self.client.get(f"/api/platform/ops/employees/{self.employee.pk}/performance/{query}")

    def test_a_year_without_a_month_is_refused_not_silently_widened(self):
        response = self._perf("?year=2026")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_an_impossible_month_is_refused_not_a_server_error(self):
        response = self._perf("?year=2026&month=13")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_no_period_at_all_is_still_allowed(self):
        self.assertEqual(self._perf("").status_code, status.HTTP_200_OK)

    def test_capture_refuses_an_impossible_month_instead_of_raising(self):
        response = self.client.post(
            "/api/platform/ops/performance-snapshots/capture/",
            data={"employee": self.employee.pk, "period_year": 2026, "period_month": 13},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST, response.data)

    def test_capturing_an_existing_snapshot_answers_200_not_201(self):
        payload = {"employee": self.employee.pk, "period_year": 2026, "period_month": 3}
        first = self.client.post(
            "/api/platform/ops/performance-snapshots/capture/", data=payload, format="json"
        )
        self.assertEqual(first.status_code, status.HTTP_201_CREATED, first.data)

        second = self.client.post(
            "/api/platform/ops/performance-snapshots/capture/", data=payload, format="json"
        )
        self.assertEqual(
            second.status_code,
            status.HTTP_200_OK,
            "٢٠١ تعني «أُنشئ» — وإعادةُ لقطةٍ قائمةٍ ليست إنشاءً.",
        )
        self.assertEqual(PerformanceSnapshot.objects.count(), 1)
