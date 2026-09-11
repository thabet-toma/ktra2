"""اختبارات أوامر العمل (المرحلة الثالثة: م٣).

تغطي هذه الاختبارات:
1. كل انتقال مسموح ينجح، وكل انتقال ممنوع يرفع الاستثناء الصحيح صراحة.
2. waiting_customer يوقف الأجل فعلاً (اختبار فترة واحدة واختبار فترتين متتاليتين).
3. الأجل يُقاس من received_at لا من بدء الموظف.
4. لقطة السياسة (policy_snapshot) لا تتغير بتعديل الإعدادات بعد الإنشاء.
5. التسليم لقطة: تحرير المصدر بعد التسليم لا يغير ما سُلم.
6. visibility إلزامي على التعليق، والتعليق الداخلي لا يُسرب في أي مسار عرض للزبون.
7. العزل بالشركة: أوامر شركة لا تظهر في استعلام شركة أخرى.
8. مسؤول واحد فقط عن أمر العمل (لا إسناد متعدد).
9. العزل على سطح الـAPI نفسِه: موظّفُ المنصّة يرى شركاتِ ارتباطاتِه وحدَها.
10. طولُ العمود يتّسع لأطولِ مفتاحِ رمزٍ في كلّ حقلِ choices جديد.
11. تأكيدُ **الحكم** لا المدّة: أمرٌ انتظر ٤٨ ساعةً لا يُحتسَب متأخّراً.
"""
import copy
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from rest_framework.test import APIClient

from tenants.models import Tenant

from platform_ops.models import (
    Engagement,
    PlatformEmployee,
    ServiceSubscription,
    WorkOrder,
    WorkOrderComment,
    WorkOrderDeliverable,
)
from platform_ops.services import (
    DEFAULT_WORK_ORDER_SLA_POLICY,
    WORK_ORDER_TRANSITIONS,
    WorkOrderError,
    WorkOrderTransitionError,
    add_work_order_comment,
    assign_work_order,
    calculate_work_order_sla,
    create_work_order,
    list_work_order_comments,
    review_work_order_deliverable,
    submit_work_order_deliverable,
    transition_work_order_status,
)

User = get_user_model()


class WorkOrderPhaseThreeTest(TestCase):
    """مجموعة اختبارات المرحلة الثالثة لأوامر العمل في platform_ops."""

    def setUp(self):
        self.tenant_a = Tenant.objects.create(TenantID=1001, CompanyName="Alpha Logistics Co")
        self.tenant_b = Tenant.objects.create(TenantID=1002, CompanyName="Beta Trading Co")

        self.sub_a = ServiceSubscription.objects.create(
            tenant=self.tenant_a,
            status=ServiceSubscription.Status.ACTIVE,
            plan="enterprise",
        )
        self.sub_b = ServiceSubscription.objects.create(
            tenant=self.tenant_b,
            status=ServiceSubscription.Status.ACTIVE,
            plan="standard",
        )

        self.user_staff = User.objects.create_user(
            username="agent_kareem",
            email="kareem@platform.local",
            password="x",
            first_name="كريم",
            last_name="العمليات",
        )
        self.employee = PlatformEmployee.objects.create(
            user=self.user_staff,
            specialty="data_entry",
            capacity_target=120,
            status=PlatformEmployee.Status.ACTIVE,
        )

        self.user_inactive = User.objects.create_user(
            username="agent_inactive",
            email="inactive@platform.local",
            password="x",
        )
        self.inactive_employee = PlatformEmployee.objects.create(
            user=self.user_inactive,
            specialty="review",
            capacity_target=50,
            status=PlatformEmployee.Status.OFFBOARDED,
        )

        self.user_client = User.objects.create_user(
            username="client_user",
            email="client@alpha.local",
            password="x",
        )

    # --------------------------------------------------------------------------
    # 1. آلة الحالات — كل انتقال مسموح ينجح، وكل انتقال ممنوع يرفع استثناءً صريحاً
    # --------------------------------------------------------------------------

    def test_complete_forward_lifecycle_transitions_succeed(self):
        """مسار العمل الكامل من received إلى closed ينجح خطوة بخطوة."""
        wo = create_work_order(
            tenant=self.tenant_a,
            title="إدخال فواتير الشراء لشهر أغسطس",
            kind=WorkOrder.Kind.DATA_ENTRY,
            source=WorkOrder.Source.CHANNEL,
        )
        self.assertEqual(wo.status, WorkOrder.Status.RECEIVED)

        # received -> screening
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.SCREENING)
        self.assertEqual(wo.status, WorkOrder.Status.SCREENING)

        # screening -> data_entry
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.DATA_ENTRY)
        self.assertEqual(wo.status, WorkOrder.Status.DATA_ENTRY)

        # data_entry -> review
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.REVIEW)
        self.assertEqual(wo.status, WorkOrder.Status.REVIEW)

        # review -> approval
        t_approved = timezone.now()
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.APPROVAL, now=t_approved)
        self.assertEqual(wo.status, WorkOrder.Status.APPROVAL)
        self.assertIsNotNone(wo.approved_at)
        self.assertEqual(wo.approved_at, t_approved)

        # approval -> closed
        t_closed = timezone.now() + timedelta(minutes=10)
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.CLOSED, now=t_closed)
        self.assertEqual(wo.status, WorkOrder.Status.CLOSED)
        self.assertIsNotNone(wo.closed_at)

    def test_waiting_customer_and_return_from_all_operational_states(self):
        """الدخول إلى waiting_customer والاستئناف مسموح من المحطات الأربع (screening, data_entry, review, approval)."""
        operational_states = [
            WorkOrder.Status.SCREENING,
            WorkOrder.Status.DATA_ENTRY,
            WorkOrder.Status.REVIEW,
            WorkOrder.Status.APPROVAL,
        ]

        for state in operational_states:
            wo = create_work_order(
                tenant=self.tenant_a,
                title=f"أمر تجربة الانتظار من {state}",
                kind=WorkOrder.Kind.DATA_ENTRY,
            )
            # الانتقال حتى الحالة المستهدفة
            if state == WorkOrder.Status.SCREENING:
                wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.SCREENING)
            elif state == WorkOrder.Status.DATA_ENTRY:
                wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.SCREENING)
                wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.DATA_ENTRY)
            elif state == WorkOrder.Status.REVIEW:
                wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.SCREENING)
                wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.DATA_ENTRY)
                wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.REVIEW)
            elif state == WorkOrder.Status.APPROVAL:
                wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.SCREENING)
                wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.DATA_ENTRY)
                wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.REVIEW)
                wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.APPROVAL)

            self.assertEqual(wo.status, state)

            # دخول انتظار العميل
            t_pause = timezone.now()
            wo = transition_work_order_status(
                work_order=wo,
                target_status=WorkOrder.Status.WAITING_CUSTOMER,
                now=t_pause,
            )
            self.assertEqual(wo.status, WorkOrder.Status.WAITING_CUSTOMER)
            self.assertEqual(wo.return_status, state)
            self.assertEqual(wo.waiting_entered_at, t_pause)

            # الخروج بالاستئناف لنفس الحالة
            t_resume = t_pause + timedelta(minutes=45)
            wo = transition_work_order_status(
                work_order=wo,
                target_status=state,
                now=t_resume,
            )
            self.assertEqual(wo.status, state)
            self.assertEqual(wo.return_status, "")
            self.assertIsNone(wo.waiting_entered_at)
            self.assertEqual(wo.waiting_seconds_total, 45 * 60)

    def test_waiting_customer_to_cancelled_succeeds_and_is_terminal(self):
        """الخروج من waiting_customer إلى cancelled ينجح والحالة نهائية."""
        wo = create_work_order(tenant=self.tenant_a, title="أمر سيلغى")
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.SCREENING)
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.WAITING_CUSTOMER)
        self.assertEqual(wo.status, WorkOrder.Status.WAITING_CUSTOMER)

        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.CANCELLED)
        self.assertEqual(wo.status, WorkOrder.Status.CANCELLED)

        # cancelled نهائية — أي انتقال بعدها ممنوع
        for forbidden in WorkOrder.Status.values:
            with self.assertRaises(WorkOrderTransitionError) as ctx:
                transition_work_order_status(work_order=wo, target_status=forbidden)
            self.assertEqual(ctx.exception.code, "invalid_transition")

    def test_closed_is_terminal(self):
        """الحالة closed نهائية ولا تقبل أي انتقال بعدها."""
        wo = create_work_order(tenant=self.tenant_a, title="أمر سيغلق")
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.SCREENING)
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.DATA_ENTRY)
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.REVIEW)
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.APPROVAL)
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.CLOSED)
        self.assertEqual(wo.status, WorkOrder.Status.CLOSED)

        for forbidden in WorkOrder.Status.values:
            with self.assertRaises(WorkOrderTransitionError) as ctx:
                transition_work_order_status(work_order=wo, target_status=forbidden)
            self.assertEqual(ctx.exception.code, "invalid_transition")

    def test_forbidden_transitions_explicitly_raise_errors(self):
        """الانتقالات غير المسموح بها ترفع WorkOrderTransitionError صراحة."""
        wo = create_work_order(tenant=self.tenant_a, title="فحص الممنوعات")
        self.assertEqual(wo.status, WorkOrder.Status.RECEIVED)

        # من received: لا يجوز القفز لـ data_entry أو closed أو waiting_customer أو cancelled
        forbidden_from_received = [
            WorkOrder.Status.DATA_ENTRY,
            WorkOrder.Status.REVIEW,
            WorkOrder.Status.APPROVAL,
            WorkOrder.Status.CLOSED,
            WorkOrder.Status.WAITING_CUSTOMER,
            WorkOrder.Status.CANCELLED,
        ]
        for bad_target in forbidden_from_received:
            with self.assertRaises(WorkOrderTransitionError) as ctx:
                transition_work_order_status(work_order=wo, target_status=bad_target)
            self.assertEqual(ctx.exception.code, "invalid_transition")

        # ننتقل لـ screening
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.SCREENING)
        # من screening: لا يجوز العودة لـ received أو القفز لـ approval أو closed
        for bad_target in [WorkOrder.Status.RECEIVED, WorkOrder.Status.REVIEW, WorkOrder.Status.APPROVAL, WorkOrder.Status.CLOSED]:
            with self.assertRaises(WorkOrderTransitionError) as ctx:
                transition_work_order_status(work_order=wo, target_status=bad_target)
            self.assertEqual(ctx.exception.code, "invalid_transition")

    def test_resuming_from_waiting_customer_to_different_status_is_forbidden(self):
        """لا يجوز الخروج من waiting_customer إلى حالة غير التي جاء منها."""
        wo = create_work_order(tenant=self.tenant_a, title="أمر دخل الانتظار من data_entry")
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.SCREENING)
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.DATA_ENTRY)
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.WAITING_CUSTOMER)
        self.assertEqual(wo.return_status, WorkOrder.Status.DATA_ENTRY)

        # محاولة استئناف العمل إلى approval أو screening بدلاً من data_entry
        with self.assertRaises(WorkOrderTransitionError) as ctx:
            transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.APPROVAL)
        self.assertEqual(ctx.exception.code, "invalid_return_status")

        with self.assertRaises(WorkOrderTransitionError) as ctx:
            transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.SCREENING)
        self.assertEqual(ctx.exception.code, "invalid_return_status")

    # --------------------------------------------------------------------------
    # 2. الأجل وإيقافه — فترتان متتاليتان وحساب دقيق
    # --------------------------------------------------------------------------

    def test_waiting_customer_pauses_sla_across_two_sequential_periods(self):
        """waiting_customer يوقف عداد الأجل فعلاً عبر فترتي انتظار متتاليتين."""
        t0 = timezone.now()
        wo = create_work_order(
            tenant=self.tenant_a,
            title="أمر مع فترتي انتظار",
            kind=WorkOrder.Kind.DATA_ENTRY,
            received_at=t0,
        )
        self.assertEqual(wo.waiting_seconds_total, 0)
        initial_deadline = wo.deadline_at

        # 1. دخل screening بعد 30 دقيقة
        t1 = t0 + timedelta(minutes=30)
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.SCREENING, now=t1)

        # 2. فترة الانتظار الأولى: دامت ساعة كاملة (60 دقيقة)
        t_pause1 = t1 + timedelta(minutes=10)
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.WAITING_CUSTOMER, now=t_pause1)
        t_resume1 = t_pause1 + timedelta(hours=1)
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.SCREENING, now=t_resume1)
        self.assertEqual(wo.waiting_seconds_total, 3600)
        self.assertEqual(wo.deadline_at, initial_deadline + timedelta(seconds=3600))

        # 3. تقدم لـ data_entry
        t2 = t_resume1 + timedelta(minutes=20)
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.DATA_ENTRY, now=t2)

        # 4. فترة الانتظار الثانية: دامت ساعتين (120 دقيقة = 7200 ثانية)
        t_pause2 = t2 + timedelta(minutes=10)
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.WAITING_CUSTOMER, now=t_pause2)
        t_resume2 = t_pause2 + timedelta(hours=2)
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.DATA_ENTRY, now=t_resume2)
        # الإجمالي المتراكم: 3600 + 7200 = 10800 ثانية (3 ساعات)
        self.assertEqual(wo.waiting_seconds_total, 10800)
        self.assertEqual(wo.deadline_at, initial_deadline + timedelta(seconds=10800))

        # 5. تقدم لـ review ثم approval
        t3 = t_resume2 + timedelta(minutes=30)
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.REVIEW, now=t3)
        t_approved = t3 + timedelta(minutes=30)
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.APPROVAL, now=t_approved)

        # الزمن الجداري الكلي من t0 إلى t_approved
        total_wall_seconds = (t_approved - t0).total_seconds()
        # الزمن الفعلي المحتسب = الزمن الجداري ناقص 3 ساعات انتظار (10800 ثانية)
        effective_seconds = wo.calculate_effective_duration_seconds()
        self.assertEqual(effective_seconds, int(total_wall_seconds - 10800))

        # التحقق من دالة حساب SLA
        sla_info = calculate_work_order_sla(work_order=wo)
        self.assertEqual(sla_info["waiting_seconds_total"], 10800)
        self.assertEqual(sla_info["effective_duration_seconds"], int(total_wall_seconds - 10800))
        self.assertEqual(sla_info["approved_at"], t_approved)

    # --------------------------------------------------------------------------
    # 3. الأجل من received_at لا من بدء الموظف
    # --------------------------------------------------------------------------

    def test_sla_measured_from_received_at_not_staff_assignment(self):
        """الأجل يُقاس بدقة من ساعة الاستلام received_at لا من ساعة إسناد الموظف."""
        t_received = timezone.now() - timedelta(hours=6)
        wo = create_work_order(
            tenant=self.tenant_a,
            title="طلب زبون ورد في الصباح",
            kind=WorkOrder.Kind.DATA_ENTRY,
            received_at=t_received,
        )

        # الموظف أُسند بعد 5 ساعات من الاستلام
        t_assigned = t_received + timedelta(hours=5)
        assign_work_order(work_order=wo, assignee=self.employee)
        wo.refresh_from_db()

        # إتمام العمل والاعتماد بعد ساعة من الإسناد (أي 6 ساعات من الاستلام)
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.SCREENING)
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.DATA_ENTRY)
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.REVIEW)
        t_approved = t_received + timedelta(hours=6)
        wo = transition_work_order_status(work_order=wo, target_status=WorkOrder.Status.APPROVAL, now=t_approved)

        effective_seconds = wo.calculate_effective_duration_seconds()
        # المدة المحتسبة 6 ساعات (21600 ثانية) وليست ساعة واحدة من وقت الإسناد (3600 ثانية)
        self.assertEqual(effective_seconds, 6 * 3600)
        self.assertNotEqual(effective_seconds, 1 * 3600)

    # --------------------------------------------------------------------------
    # 4. لقطة السياسة (policy_snapshot) لا تتغير بتعديل الإعدادات بعد الإنشاء
    # --------------------------------------------------------------------------

    def test_policy_snapshot_is_immutable_against_runtime_configuration_changes(self):
        """لقطة سياسة الأجل لا تتغير بتعديل الإعدادات بعد الإنشاء."""
        wo = create_work_order(
            tenant=self.tenant_a,
            title="أمر عمل بالسياسة الافتراضية",
            kind=WorkOrder.Kind.DATA_ENTRY,
        )
        self.assertEqual(wo.policy_snapshot["sla_hours"], 24)
        self.assertEqual(wo.policy_snapshot["kind"], "data_entry")
        original_deadline = wo.deadline_at

        # محاكاة تعديل السياسة في الذاكرة / المستقبل
        original_default = DEFAULT_WORK_ORDER_SLA_POLICY["sla_hours_by_kind"]["data_entry"]
        try:
            DEFAULT_WORK_ORDER_SLA_POLICY["sla_hours_by_kind"]["data_entry"] = 72

            # أمر العمل المنشأ سابقاً يحتفظ بلقطته 24
            wo.refresh_from_db()
            self.assertEqual(wo.policy_snapshot["sla_hours"], 24)
            # والأجلُ المحسوبُ منها لا يتحرّك أيضاً — اللقطةُ تحرس الرقمَ ونتيجتَه معاً
            self.assertEqual(wo.deadline_at, original_deadline)

            # أمر العمل الجديد يأخذ السياسة الجديدة 72
            wo_new = create_work_order(
                tenant=self.tenant_a,
                title="أمر عمل بعد تعديل السياسة",
                kind=WorkOrder.Kind.DATA_ENTRY,
            )
            self.assertEqual(wo_new.policy_snapshot["sla_hours"], 72)
        finally:
            # إعادة القيمة الأصلية لحماية الاختبارات الأخرى
            DEFAULT_WORK_ORDER_SLA_POLICY["sla_hours_by_kind"]["data_entry"] = original_default

    # --------------------------------------------------------------------------
    # 5. التسليم لقطة ثابتة (Deliverable Snapshot)
    # --------------------------------------------------------------------------

    def test_deliverable_snapshot_is_decoupled_from_source_mutation(self):
        """محتوى التسليم يُحفظ كلقطة مستقلة ولا يتأثر بتعديل المصدر لاحقاً."""
        wo = create_work_order(tenant=self.tenant_a, title="أمر تسليم تقرير")

        source_payload = {
            "entries_count": 50,
            "total_amount": 15000.50,
            "batches": ["b1", "b2"],
        }

        deliverable = submit_work_order_deliverable(
            work_order=wo,
            kind=WorkOrderDeliverable.Kind.STRUCTURED_REPORT,
            content="تقرير تسليم فواتير المشتريات",
            payload=source_payload,
            file_url="https://files.ktra.local/reports/august_invoices.xlsx",
            submitted_by=self.user_staff,
        )

        # تعديل القاموس الأصلي خارجياً بعد التسليم
        source_payload["entries_count"] = 9999
        source_payload["batches"].append("tampered_batch")

        deliverable.refresh_from_db()
        self.assertEqual(deliverable.payload["entries_count"], 50)
        self.assertEqual(deliverable.content_snapshot["payload"]["entries_count"], 50)
        self.assertEqual(deliverable.content_snapshot["payload"]["batches"], ["b1", "b2"])
        self.assertEqual(deliverable.review_status, WorkOrderDeliverable.ReviewStatus.PENDING)

    def test_deliverable_review_approval_and_rejection_flow(self):
        """مراجعة التسليم: القبول، والرفض مع سبب إلزامي."""
        wo = create_work_order(tenant=self.tenant_a, title="أمر مراجعة تسليم")
        deliv1 = submit_work_order_deliverable(
            work_order=wo,
            kind=WorkOrderDeliverable.Kind.NOTE,
            content="ملاحظة إنجاز",
        )

        # قبول التسليم
        deliv1 = review_work_order_deliverable(
            deliverable=deliv1,
            review_status=WorkOrderDeliverable.ReviewStatus.APPROVED,
            reviewed_by=self.user_staff,
        )
        self.assertEqual(deliv1.review_status, WorkOrderDeliverable.ReviewStatus.APPROVED)
        self.assertEqual(deliv1.reviewed_by, self.user_staff)
        self.assertIsNotNone(deliv1.reviewed_at)

        # تسليم ثانٍ يُرفض
        deliv2 = submit_work_order_deliverable(
            work_order=wo,
            kind=WorkOrderDeliverable.Kind.ATTACHMENT,
            file_url="https://files.ktra.local/corrupted.pdf",
        )
        # الرفض بلا سبب يرفع خطأ
        with self.assertRaises(WorkOrderError) as ctx:
            review_work_order_deliverable(
                deliverable=deliv2,
                review_status=WorkOrderDeliverable.ReviewStatus.REJECTED,
                reviewed_by=self.user_staff,
                rejection_reason="",
            )
        self.assertEqual(ctx.exception.code, "rejection_reason_required")

        # الرفض مع سبب
        deliv2 = review_work_order_deliverable(
            deliverable=deliv2,
            review_status=WorkOrderDeliverable.ReviewStatus.REJECTED,
            reviewed_by=self.user_staff,
            rejection_reason="الملف تالف وغير قابل للقراءة.",
        )
        self.assertEqual(deliv2.review_status, WorkOrderDeliverable.ReviewStatus.REJECTED)
        self.assertEqual(deliv2.rejection_reason, "الملف تالف وغير قابل للقراءة.")

    # --------------------------------------------------------------------------
    # 6. visibility إلزامي على التعليق والداخلي لا يُسرب للزبون
    # --------------------------------------------------------------------------

    def test_comment_visibility_is_mandatory_and_internal_is_never_leaked(self):
        """حقل visibility إلزامي على كل تعليق والتعليق الداخلي محجوب عن استعلام الزبون."""
        wo = create_work_order(tenant=self.tenant_a, title="أمر فيه تعليقات متنوعة")

        # إضافة تعليق بدون visibility أو بقيمة خاطئة ترفع خطأ
        with self.assertRaises(WorkOrderError) as ctx:
            add_work_order_comment(
                work_order=wo,
                author=self.user_staff,
                content="ملاحظة غير مصنفة",
                visibility="",
            )
        self.assertEqual(ctx.exception.code, "visibility_required")

        with self.assertRaises(WorkOrderError) as ctx:
            add_work_order_comment(
                work_order=wo,
                author=self.user_staff,
                content="ملاحظة غير مصنفة",
                visibility="confidential",
            )
        self.assertEqual(ctx.exception.code, "visibility_required")

        # إضافة تعليق داخلي
        c_internal = add_work_order_comment(
            work_order=wo,
            author=self.user_staff,
            content="ملاحظة داخلية بين فريق المنصة: الزبون يطلب تعديل الأسعار.",
            visibility=WorkOrderComment.Visibility.INTERNAL,
        )

        # إضافة تعليق مرئي للزبون
        c_client = add_work_order_comment(
            work_order=wo,
            author=self.user_staff,
            content="يرجى تزويدنا بصورة الفاتورة رقم 104 لاستكمال الإدخال.",
            visibility=WorkOrderComment.Visibility.CLIENT_VISIBLE,
        )

        # مسار العرض للزبون
        client_comments = list_work_order_comments(work_order=wo, for_client=True)
        self.assertEqual(client_comments.count(), 1)
        self.assertIn(c_client, client_comments)
        self.assertNotIn(c_internal, client_comments)

        # المسار الداخلي يرى التعليقين
        internal_comments = list_work_order_comments(work_order=wo, for_client=False)
        self.assertEqual(internal_comments.count(), 2)
        self.assertIn(c_internal, internal_comments)
        self.assertIn(c_client, internal_comments)

    # --------------------------------------------------------------------------
    # 7. العزل بالشركة (Tenant Isolation)
    # --------------------------------------------------------------------------

    def test_tenant_isolation_work_orders_never_leak_across_companies(self):
        """أوامر شركة لا تظهر في استعلام شركة أخرى إطلاقاً."""
        wo_a1 = create_work_order(tenant=self.tenant_a, title="طلب شركة أ الأول")
        wo_a2 = create_work_order(tenant=self.tenant_a, title="طلب شركة أ الثاني")
        wo_b1 = create_work_order(tenant=self.tenant_b, title="طلب شركة ب")

        # استعلام شركة أ
        qs_a = WorkOrder.objects.filter(tenant=self.tenant_a)
        self.assertEqual(qs_a.count(), 2)
        self.assertIn(wo_a1, qs_a)
        self.assertIn(wo_a2, qs_a)
        self.assertNotIn(wo_b1, qs_a)

        # استعلام شركة ب
        qs_b = WorkOrder.objects.filter(tenant=self.tenant_b)
        self.assertEqual(qs_b.count(), 1)
        self.assertIn(wo_b1, qs_b)
        self.assertNotIn(wo_a1, qs_b)
        self.assertNotIn(wo_a2, qs_b)

        # المسلمات والتعليقات معزولة بالشركة أيضاً
        deliv_a = submit_work_order_deliverable(work_order=wo_a1, kind=WorkOrderDeliverable.Kind.NOTE, content="تسليم أ")
        self.assertEqual(deliv_a.tenant, self.tenant_a)
        self.assertEqual(WorkOrderDeliverable.objects.filter(tenant=self.tenant_b).count(), 0)

        comm_a = add_work_order_comment(
            work_order=wo_a1,
            author=self.user_staff,
            content="تعليق أ",
            visibility=WorkOrderComment.Visibility.INTERNAL,
        )
        self.assertEqual(comm_a.tenant, self.tenant_a)
        self.assertEqual(WorkOrderComment.objects.filter(tenant=self.tenant_b).count(), 0)

    # --------------------------------------------------------------------------
    # 8. مسؤول واحد فقط عن أمر العمل (Single Assignee)
    # --------------------------------------------------------------------------

    def test_single_assignee_rule_and_inactive_employee_rejection(self):
        """مسؤول واحد فقط عن أمر العمل ورفض إسناد موظف غير نشط."""
        wo = create_work_order(
            tenant=self.tenant_a,
            title="طلب في الطابور أولاً",
            assignee=None,
        )
        self.assertIsNone(wo.assignee)

        # إسناد موظف نشط
        wo = assign_work_order(work_order=wo, assignee=self.employee)
        self.assertEqual(wo.assignee, self.employee)

        # محاولة إسناد موظف خارج الخدمة (offboarded) تفشل
        with self.assertRaises(WorkOrderError) as ctx:
            assign_work_order(work_order=wo, assignee=self.inactive_employee)
        self.assertEqual(ctx.exception.code, "assignee_not_active")

        # إعادة الإسناد إلى None (العودة للطابور)
        wo = assign_work_order(work_order=wo, assignee=None)
        self.assertIsNone(wo.assignee)


class WorkOrderApiScopeTest(TestCase):
    """العزلُ على سطح الـAPI — لا على استعلامٍ يكتبه الاختبارُ بنفسه.

    اختبارُ العزل في `WorkOrderPhaseThreeTest` يُصفّي بـ`filter(tenant=…)` بيدِه،
    فهو يُثبت أنّ Django تعرف الفلترةَ لا أنّ **النقطةَ** تفلتر. وهذا ما يجب أن
    يسقط لو عاد `queryset` بلا فلتر: موظّفُ منصّةٍ مرتبطٌ بشركةٍ واحدةٍ يرى أوامرَ
    الشركات كلِّها.
    """

    def setUp(self):
        self.client = APIClient()
        self.tenant_a = Tenant.objects.create(TenantID=971, CompanyName="Scope A Co")
        self.tenant_b = Tenant.objects.create(TenantID=972, CompanyName="Scope B Co")
        # 210-A §١: أوامرُ العمل لا تدخلها إلا شركةٌ مؤهَّلة — الشركتان مشتركتان كي يبقى
        # هذا الاختبارُ عن العزل بالارتباط وحده لا عن الأهلية.
        for tenant in (self.tenant_a, self.tenant_b):
            ServiceSubscription.objects.create(tenant=tenant, status=ServiceSubscription.Status.ACTIVE)

        self.staff_user = User.objects.create_user(
            username="scoped_staff", email="scoped_staff@platform.local", password="x"
        )
        self.employee = PlatformEmployee.objects.create(
            user=self.staff_user,
            specialty="data_entry",
            status=PlatformEmployee.Status.ACTIVE,
        )
        Engagement.objects.create(
            employee=self.employee,
            tenant=self.tenant_a,
            status=Engagement.Status.ACTIVE,
        )

        self.admin_user = User.objects.create_superuser(
            username="scope_admin", email="scope_admin@platform.local", password="x"
        )

        self.wo_a = create_work_order(tenant=self.tenant_a, title="أمر شركة أ")
        self.wo_b = create_work_order(tenant=self.tenant_b, title="أمر شركة ب")

    def _ids(self, response):
        payload = response.data
        rows = payload["results"] if isinstance(payload, dict) and "results" in payload else payload
        return {row["id"] for row in rows}

    def test_platform_employee_sees_only_work_orders_of_engaged_companies(self):
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get("/api/platform/ops/work-orders/")
        self.assertEqual(response.status_code, 200, response.content)

        ids = self._ids(response)
        self.assertIn(self.wo_a.pk, ids)
        self.assertNotIn(self.wo_b.pk, ids, "تسريبٌ عابرٌ للشركات: الموظّفُ يرى شركةً لا ارتباطَ له بها.")

    def test_revoked_engagement_removes_the_company_from_the_employee_scope(self):
        """الارتباطُ الملغى يسحب الرؤيةَ فوراً — الوصولُ خطرٌ قائمٌ لا سجلٌّ تاريخيّ."""
        Engagement.objects.filter(employee=self.employee).update(
            status=Engagement.Status.REVOKED
        )
        self.client.force_authenticate(user=self.staff_user)
        response = self.client.get("/api/platform/ops/work-orders/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self._ids(response), set())

    def test_platform_manager_sees_every_company(self):
        """مديرُ المنصّة يرى الكلَّ — الفلترةُ على الموظّف لا عليه."""
        self.client.force_authenticate(user=self.admin_user)
        response = self.client.get("/api/platform/ops/work-orders/")
        self.assertEqual(response.status_code, 200, response.content)

        ids = self._ids(response)
        self.assertIn(self.wo_a.pk, ids)
        self.assertIn(self.wo_b.pk, ids)


class WorkOrderChoiceColumnWidthTest(SimpleTestCase):
    """طولُ العمود مقابل أطولِ مفتاحِ رمز.

    عمودٌ أضيقُ من أطولِ رمزٍ **يُلغي القيدَ بصمتٍ على MySQL** ولا تكشفه SQLite —
    السابقتان الحيّتان `ActivityLog.action` و`docshare.doc_type`. فيُقاس صراحةً.
    """

    def test_every_new_choices_column_fits_its_longest_key(self):
        fields = [
            (WorkOrder, "kind"),
            (WorkOrder, "source"),
            (WorkOrder, "status"),
            (WorkOrder, "return_status"),
            (WorkOrderDeliverable, "kind"),
            (WorkOrderDeliverable, "review_status"),
            (WorkOrderComment, "visibility"),
        ]
        for model, name in fields:
            with self.subTest(model=model.__name__, field=name):
                field = model._meta.get_field(name)
                keys = [key for key, _ in (field.choices or [])]
                if not keys:
                    # `return_status` بلا choices لكنّه يخزّن قيمَ حالةِ أمر العمل.
                    keys = list(WorkOrder.Status.values)
                longest = max(keys, key=len)
                self.assertGreaterEqual(
                    field.max_length,
                    len(longest),
                    f"{model.__name__}.{name}: العمود {field.max_length} وأطولُ رمزٍ "
                    f"'{longest}' طولُه {len(longest)} — القيدُ يسقط بصمتٍ على MySQL.",
                )


class WorkOrderOverdueVerdictTest(TestCase):
    """الحكمُ لا المدّة: «أمرٌ يقضي ٤٨ ساعةً في `waiting_customer` لا يُحتسَب متأخّراً».

    المواصفةُ سمّت هذا الاختبارَ بالاسم، والاختباراتُ الأخرى تقيس المدّةَ ولا تسأل
    عن `is_overdue` — وهو الحقلُ الذي يُبنى عليه شريطُ التدخُّل. فيُسأل صراحةً.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(TenantID=973, CompanyName="Overdue Co")
        ServiceSubscription.objects.create(
            tenant=self.tenant, status=ServiceSubscription.Status.ACTIVE, plan="growth"
        )

    def test_forty_eight_hours_of_customer_wait_is_not_counted_as_overdue(self):
        received = timezone.now() - timedelta(hours=50)
        wo = create_work_order(
            tenant=self.tenant,
            title="أمر انتظر الزبونَ يومين",
            kind=WorkOrder.Kind.DATA_ENTRY,   # أجلُه ٢٤ ساعة
            received_at=received,
        )
        self.assertEqual(wo.policy_snapshot["sla_hours"], 24)

        wo = transition_work_order_status(
            work_order=wo,
            target_status=WorkOrder.Status.SCREENING,
            now=received + timedelta(minutes=30),
        )
        wo = transition_work_order_status(
            work_order=wo,
            target_status=WorkOrder.Status.WAITING_CUSTOMER,
            now=received + timedelta(hours=1),
        )
        # ٤٨ ساعةً كاملةً بانتظار الزبون
        wo = transition_work_order_status(
            work_order=wo,
            target_status=WorkOrder.Status.SCREENING,
            now=received + timedelta(hours=49),
        )
        self.assertEqual(wo.waiting_seconds_total, 48 * 3600)

        approved_at = received + timedelta(hours=50)
        wo = transition_work_order_status(
            work_order=wo,
            target_status=WorkOrder.Status.DATA_ENTRY,
            now=received + timedelta(hours=49, minutes=30),
        )
        wo = transition_work_order_status(
            work_order=wo,
            target_status=WorkOrder.Status.REVIEW,
            now=received + timedelta(hours=49, minutes=45),
        )
        wo = transition_work_order_status(
            work_order=wo, target_status=WorkOrder.Status.APPROVAL, now=approved_at
        )

        sla = calculate_work_order_sla(work_order=wo)
        # الزمنُ الجداريُّ ٥٠ ساعةً وهو ضِعفا الأجل — والحكمُ مع ذلك «غيرُ متأخّر»
        self.assertEqual(sla["effective_duration_seconds"], 2 * 3600)
        self.assertFalse(
            sla["is_overdue"],
            "انتظارُ الزبون حُسب على المنصّة: أمرٌ انتظره يومين عُدَّ متأخّراً.",
        )
        # والأجلُ المخزَّنُ تمدّد بالقدر نفسِه فلا يتناقض الحكمان
        self.assertEqual(wo.deadline_at, received + timedelta(hours=24 + 48))
        self.assertLess(wo.approved_at, wo.deadline_at)

    def test_the_same_order_without_the_wait_is_counted_as_overdue(self):
        """تأكيدٌ يستطيع السقوط: بلا انتظارٍ، الخمسون ساعةً تجاوزٌ صريح."""
        received = timezone.now() - timedelta(hours=50)
        wo = create_work_order(
            tenant=self.tenant,
            title="أمر تأخّر علينا",
            kind=WorkOrder.Kind.DATA_ENTRY,
            received_at=received,
        )
        for target, offset in (
            (WorkOrder.Status.SCREENING, timedelta(hours=1)),
            (WorkOrder.Status.DATA_ENTRY, timedelta(hours=2)),
            (WorkOrder.Status.REVIEW, timedelta(hours=40)),
            (WorkOrder.Status.APPROVAL, timedelta(hours=50)),
        ):
            wo = transition_work_order_status(
                work_order=wo, target_status=target, now=received + offset
            )

        sla = calculate_work_order_sla(work_order=wo)
        self.assertEqual(sla["effective_duration_seconds"], 50 * 3600)
        self.assertTrue(sla["is_overdue"])
