"""اختبارات التذكرة 210-B: فحص صحة الدفاتر والتشغيل، والإسناد والطاقة، واكتساب العميل.

تغطي هذا الملف وحده (لا `test_engagement_lifecycle.py` ولا `test_subscription_management.py`
اللذان يغطيان دورة الحياة الأصلية والاشتراك):
1. دورة حياة فحص الصحة: مسودة → تعديل → اعتماد، والرفض الواضح عند نقص الدليل أو التعقيد.
2. بوابة الإسناد العادي على فحصٍ تأسيسي معتمد، واستثناء onboarding الموسوم والمؤرَّخ.
3. الطاقة: الرفض عند تجاوز `capacity_target`، والقبول بسبب تجاوز صريح.
4. النقل: معاملة واحدة تُبقي التاريخ (`predecessor`, `ended_at`, `end_reason`) ولا تمسّ الاكتساب.
5. اكتساب العميل: صفٌّ واحد لكل شركة، مستقلٌّ عمّن يخدمها الآن.
6. تدقيق الأحداث: كل فعل جديد يكتب `PlatformOperationEvent` بفاعلٍ ومعرّف ارتباط.
7. العزل: كل مسار API جديد تحت `/api/platform/ops/` يرفض غير السوبر أدمن بـ403.
"""
import datetime
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.test import APIClient

from tenants.models import Tenant, UserCompanyMembership

from platform_ops.models import (
    CompanyHealthCheck,
    CompanyHealthCheckItem,
    CustomerAcquisition,
    Engagement,
    PlatformEmployee,
    PlatformOperationEvent,
    ServiceSubscription,
    WorkOrder,
)
from platform_ops.services import (
    AcquisitionError,
    EngagementConflict,
    EngagementError,
    HealthCheckConflict,
    HealthCheckError,
    approve_health_check,
    assign_platform_employee,
    compare_health_baseline,
    convert_health_check_item_to_work_order,
    create_health_check_draft,
    get_customer_acquisition,
    latest_approved_baseline,
    list_assignment_candidates,
    refresh_health_check_auto_items,
    set_customer_acquisition,
    suspend_engagement,
    transfer_engagement,
    update_health_check,
    update_health_check_item,
)

User = get_user_model()


def _approve_baseline(tenant, actor=None, complexity=CompanyHealthCheck.Complexity.LOW):
    """يبني فحصاً تأسيسياً معتمداً سريعاً لشركة اختبار — بوابة الإسناد العادي منذ 210-B.

    مُعرَّفٌ هنا وحدَه ويستورده ملفّا الاشتراك ودورة الحياة، فدورةُ حياة الفحص ملكُ هذا
    الملفّ (نمطُ `_interface_fields` المستوردة بين ملفّي عقد الواجهة).
    """
    check = create_health_check_draft(tenant=tenant, actor=actor)
    update_health_check(check=check, complexity=complexity)
    check.items.filter(mandatory=True, evidence_value__isnull=True, evidence_note="").update(
        evidence_note="بيانات اختبار",
    )
    return approve_health_check(check=check, actor=actor)


class HealthCheckLifecycleServiceTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username="hc_admin", email="hc_admin@platform.local", password="x")
        self.tenant = Tenant.objects.create(TenantID=9100, CompanyName="Health Co")
        self.ineligible_tenant = Tenant.objects.create(TenantID=9101, CompanyName="No Sub Co")
        ServiceSubscription.objects.create(
            tenant=self.tenant, status=ServiceSubscription.Status.ACTIVE, plan="growth", included_quota=500,
        )

    def test_create_draft_seeds_full_catalog_with_auto_items_filled(self):
        check = create_health_check_draft(tenant=self.tenant, actor=self.admin)
        self.assertEqual(check.status, CompanyHealthCheck.Status.DRAFT)
        items = {item.code: item for item in check.items.all()}
        self.assertEqual(len(items), 7)
        auto_codes = {"unposted_sales_documents", "receivables_aging", "inventory_provisional_layers"}
        for code in auto_codes:
            self.assertEqual(items[code].source, CompanyHealthCheckItem.Source.AUTO)
            self.assertIsNotNone(items[code].evidence_value)
        for code in set(items) - auto_codes:
            self.assertEqual(items[code].source, CompanyHealthCheckItem.Source.MANUAL)
            self.assertEqual(items[code].status, CompanyHealthCheckItem.ItemStatus.FOLLOW_UP)

    def test_create_draft_refused_for_ineligible_tenant(self):
        with self.assertRaises(HealthCheckError) as ctx:
            create_health_check_draft(tenant=self.ineligible_tenant, actor=self.admin)
        self.assertEqual(ctx.exception.code, "subscription_not_eligible")

    def test_approve_refused_without_complexity(self):
        check = create_health_check_draft(tenant=self.tenant, actor=self.admin)
        with self.assertRaises(HealthCheckError) as ctx:
            approve_health_check(check=check, actor=self.admin)
        self.assertEqual(ctx.exception.code, "complexity_required")

    def test_approve_refused_when_mandatory_item_lacks_evidence(self):
        check = create_health_check_draft(tenant=self.tenant, actor=self.admin)
        update_health_check(check=check, complexity=CompanyHealthCheck.Complexity.LOW)
        with self.assertRaises(HealthCheckError) as ctx:
            approve_health_check(check=check, actor=self.admin)
        self.assertEqual(ctx.exception.code, "evidence_missing")

    def test_approve_succeeds_and_is_idempotent_refusal_on_second_call(self):
        approved = _approve_baseline(self.tenant, actor=self.admin)
        self.assertEqual(approved.status, CompanyHealthCheck.Status.APPROVED)
        self.assertEqual(approved.approved_by_id, self.admin.pk)
        self.assertIsNotNone(approved.approved_at)
        event = PlatformOperationEvent.objects.get(
            domain=PlatformOperationEvent.Domain.HEALTH_CHECK,
            action=PlatformOperationEvent.Action.HEALTH_CHECK_APPROVED,
            subject_id=approved.pk,
        )
        self.assertEqual(event.actor_id, self.admin.pk)
        self.assertEqual(event.tenant_id, self.tenant.pk)

        with self.assertRaises(HealthCheckConflict) as ctx:
            approve_health_check(check=approved, actor=self.admin)
        self.assertEqual(ctx.exception.code, "already_approved")
        self.assertEqual(ctx.exception.status_code, 409)

    def test_update_and_refresh_refused_once_approved(self):
        approved = _approve_baseline(self.tenant, actor=self.admin)
        with self.assertRaises(HealthCheckConflict) as ctx:
            update_health_check(check=approved, notes="بعد الاعتماد")
        self.assertEqual(ctx.exception.code, "health_check_immutable")
        with self.assertRaises(HealthCheckConflict):
            refresh_health_check_auto_items(check=approved)
        item = approved.items.first()
        with self.assertRaises(HealthCheckConflict) as ctx:
            update_health_check_item(item=item, status=CompanyHealthCheckItem.ItemStatus.HEALTHY)
        self.assertEqual(ctx.exception.code, "health_check_immutable")

    def test_convert_item_to_work_order_is_idempotent_and_rejects_healthy_items(self):
        check = create_health_check_draft(tenant=self.tenant, actor=self.admin)
        follow_up_item = check.items.filter(status=CompanyHealthCheckItem.ItemStatus.FOLLOW_UP).first()
        first = convert_health_check_item_to_work_order(item=follow_up_item, actor=self.admin)
        follow_up_item.refresh_from_db()
        second = convert_health_check_item_to_work_order(item=follow_up_item, actor=self.admin)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(WorkOrder.objects.filter(tenant=self.tenant).count(), 1)

        healthy_item = check.items.exclude(pk=follow_up_item.pk).first()
        healthy_item.status = CompanyHealthCheckItem.ItemStatus.NOT_APPLICABLE
        healthy_item.save(update_fields=["status"])
        with self.assertRaises(HealthCheckError) as ctx:
            convert_health_check_item_to_work_order(item=healthy_item, actor=self.admin)
        self.assertEqual(ctx.exception.code, "item_not_convertible")

    def test_compare_baseline_has_no_employee_attribution_and_diffs_by_code(self):
        empty = compare_health_baseline(tenant=self.tenant)
        self.assertIsNone(empty["baseline"])
        self.assertIsNone(empty["current"])
        self.assertEqual(empty["changes"], [])

        first = _approve_baseline(self.tenant, actor=self.admin)
        second_draft = create_health_check_draft(tenant=self.tenant, actor=self.admin)
        item = second_draft.items.filter(mandatory=False, source=CompanyHealthCheckItem.Source.MANUAL).first()
        update_health_check_item(item=item, status=CompanyHealthCheckItem.ItemStatus.HEALTHY)
        update_health_check(check=second_draft, complexity=CompanyHealthCheck.Complexity.LOW)
        second_draft.items.filter(mandatory=True, evidence_value__isnull=True, evidence_note="").update(
            evidence_note="بيانات اختبار",
        )
        second = approve_health_check(check=second_draft, actor=self.admin)

        result = compare_health_baseline(tenant=self.tenant)
        self.assertEqual(result["baseline"].pk, first.pk)
        self.assertEqual(result["current"].pk, second.pk)
        codes_changed = {row["code"] for row in result["changes"]}
        self.assertIn(item.code, codes_changed)
        for row in result["changes"]:
            self.assertNotIn("employee", row)
            self.assertNotIn("assigned_to", row)

    def test_latest_approved_baseline_picks_most_recent(self):
        first = _approve_baseline(self.tenant, actor=self.admin)
        second_draft = create_health_check_draft(tenant=self.tenant, actor=self.admin)
        update_health_check(check=second_draft, complexity=CompanyHealthCheck.Complexity.HIGH)
        second_draft.items.filter(mandatory=True, evidence_value__isnull=True, evidence_note="").update(
            evidence_note="بيانات اختبار",
        )
        second = approve_health_check(check=second_draft, actor=self.admin)
        self.assertEqual(latest_approved_baseline(self.tenant).pk, second.pk)
        self.assertNotEqual(first.pk, second.pk)


class AssignmentCapacityServiceTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username="cap_admin", email="cap_admin@platform.local", password="x")
        self.employee_user = User.objects.create_user(username="cap_emp", email="cap_emp@platform.local", password="x")
        self.employee = PlatformEmployee.objects.create(
            user=self.employee_user, specialty="data_entry", capacity_target=3,
            status=PlatformEmployee.Status.ACTIVE,
        )
        self.other_employee_user = User.objects.create_user(username="cap_emp2", email="cap_emp2@platform.local", password="x")
        self.other_employee = PlatformEmployee.objects.create(
            user=self.other_employee_user, specialty="data_entry", capacity_target=10,
            status=PlatformEmployee.Status.ACTIVE,
        )
        self.tenant = Tenant.objects.create(TenantID=9200, CompanyName="Assign Co")
        ServiceSubscription.objects.create(
            tenant=self.tenant, status=ServiceSubscription.Status.ACTIVE, plan="growth", included_quota=500,
        )

    def test_standard_assignment_refused_without_approved_baseline(self):
        with self.assertRaises(EngagementError) as ctx:
            assign_platform_employee(employee=self.employee, tenant=self.tenant, assigned_by=self.admin)
        self.assertEqual(ctx.exception.code, "baseline_required")

    def test_onboarding_assignment_allowed_without_baseline_and_dated(self):
        engagement = assign_platform_employee(
            employee=self.employee, tenant=self.tenant, assigned_by=self.admin,
            kind=Engagement.Kind.ONBOARDING,
        )
        self.assertEqual(engagement.kind, Engagement.Kind.ONBOARDING)
        self.assertIsNotNone(engagement.onboarding_expires_at)
        self.assertGreater(engagement.onboarding_expires_at, engagement.assigned_at)
        event = PlatformOperationEvent.objects.get(
            domain=PlatformOperationEvent.Domain.ENGAGEMENT,
            action=PlatformOperationEvent.Action.ASSIGNED,
            subject_id=engagement.pk,
        )
        self.assertEqual(event.actor_id, self.admin.pk)

    def test_assignment_refused_when_capacity_exceeded_then_accepted_with_override(self):
        _approve_baseline(self.tenant, actor=self.admin, complexity=CompanyHealthCheck.Complexity.HIGH)
        self.employee.capacity_target = 1
        self.employee.save(update_fields=["capacity_target"])
        with self.assertRaises(EngagementConflict) as ctx:
            assign_platform_employee(employee=self.employee, tenant=self.tenant, assigned_by=self.admin)
        self.assertEqual(ctx.exception.code, "capacity_exceeded")
        self.assertEqual(ctx.exception.status_code, 409)

        engagement = assign_platform_employee(
            employee=self.employee, tenant=self.tenant, assigned_by=self.admin,
            capacity_override_reason="تجاوز مؤقت بموافقة الإدارة",
        )
        self.assertEqual(engagement.capacity_override_reason, "تجاوز مؤقت بموافقة الإدارة")

    def test_transfer_keeps_history_and_does_not_touch_acquisition(self):
        _approve_baseline(self.tenant, actor=self.admin, complexity=CompanyHealthCheck.Complexity.LOW)
        original = assign_platform_employee(employee=self.employee, tenant=self.tenant, assigned_by=self.admin)
        set_customer_acquisition(tenant=self.tenant, acquired_by=self.other_employee, actor=self.admin)
        acquisition_before = get_customer_acquisition(self.tenant)

        transferred = transfer_engagement(
            engagement=original, to_employee=self.other_employee, reason="إعادة توزيع الحمل", actor=self.admin,
        )
        self.assertEqual(transferred.predecessor_id, original.pk)
        self.assertEqual(transferred.employee_id, self.other_employee.pk)
        self.assertEqual(transferred.status, Engagement.Status.ACTIVE)

        original.refresh_from_db()
        self.assertEqual(original.status, Engagement.Status.REVOKED)
        self.assertIsNotNone(original.ended_at)
        self.assertIn("إعادة توزيع الحمل", original.end_reason)

        acquisition_after = get_customer_acquisition(self.tenant)
        self.assertEqual(acquisition_before.pk, acquisition_after.pk)
        self.assertEqual(acquisition_after.acquired_by_id, self.other_employee.pk)

        event = PlatformOperationEvent.objects.get(
            domain=PlatformOperationEvent.Domain.ENGAGEMENT,
            action=PlatformOperationEvent.Action.TRANSFERRED,
            subject_id=transferred.pk,
        )
        self.assertEqual(event.details["from_engagement_id"], original.pk)
        self.assertEqual(event.details["to_employee_id"], self.other_employee.pk)

    def test_employee_with_unset_capacity_target_is_assignable_without_an_override(self):
        """صفرُ `capacity_target` يعني «لم تُضبط» لا «طاقةَ صفر».

        وهو افتراضُ النموذج ولا واجهةَ كتابةٍ تضبطه، فلو قُرئ حرفياً لرُفض كلُّ
        إسنادٍ لكلّ موظفٍ حقيقيٍّ بـ`capacity_exceeded` وطُلب سببُ تجاوزٍ دائماً.
        """
        _approve_baseline(self.tenant, actor=self.admin, complexity=CompanyHealthCheck.Complexity.HIGH)
        fresh_employee = PlatformEmployee.objects.create(
            user=User.objects.create_user(
                username="cap_unset", email="cap_unset@platform.local", password="x",
            ),
            specialty="data_entry",
            status=PlatformEmployee.Status.ACTIVE,
        )
        self.assertEqual(fresh_employee.capacity_target, Decimal("0.00"))

        engagement = assign_platform_employee(
            employee=fresh_employee, tenant=self.tenant, assigned_by=self.admin,
        )
        self.assertEqual(engagement.status, Engagement.Status.ACTIVE)
        self.assertEqual(engagement.capacity_override_reason, "")
        candidate = next(
            row for row in list_assignment_candidates(tenant=self.tenant)
            if row["employee"].pk == fresh_employee.pk
        )
        self.assertFalse(candidate["would_exceed_capacity"])

    def test_transfer_refuses_a_suspended_engagement_instead_of_reactivating_it(self):
        """النقل كان يُخرج ارتباطاً نشطاً من معلَّقٍ بصمت فيعود الموظف يخدم شركةً عُلّقت."""
        _approve_baseline(self.tenant, actor=self.admin, complexity=CompanyHealthCheck.Complexity.LOW)
        original = assign_platform_employee(employee=self.employee, tenant=self.tenant, assigned_by=self.admin)
        suspend_engagement(engagement=original, reason="توقف مؤقت", actor=self.admin)

        with self.assertRaises(EngagementConflict) as ctx:
            transfer_engagement(
                engagement=original, to_employee=self.other_employee, reason="إعادة توزيع", actor=self.admin,
            )
        self.assertEqual(ctx.exception.code, "not_active")

        original.refresh_from_db()
        self.assertEqual(original.status, Engagement.Status.SUSPENDED)
        self.assertFalse(
            Engagement.objects.filter(tenant=self.tenant, status=Engagement.Status.ACTIVE).exists()
        )

    def test_transfer_keeps_the_original_onboarding_deadline_rather_than_restarting_it(self):
        """وإلا صار «لا إسناد تشغيلي بلا أساس معتمد» قابلاً للتجاوز بنقلٍ متكرّر بلا نهاية."""
        original = assign_platform_employee(
            employee=self.employee, tenant=self.tenant, assigned_by=self.admin,
            kind=Engagement.Kind.ONBOARDING,
        )
        original.onboarding_expires_at = original.onboarding_expires_at - datetime.timedelta(days=10)
        original.save(update_fields=["onboarding_expires_at"])
        deadline = original.onboarding_expires_at

        transferred = transfer_engagement(
            engagement=original, to_employee=self.other_employee, reason="إعادة توزيع", actor=self.admin,
        )
        self.assertEqual(transferred.kind, Engagement.Kind.ONBOARDING)
        self.assertEqual(transferred.onboarding_expires_at, deadline)

    def test_transfer_requires_reason_and_rejects_same_employee(self):
        _approve_baseline(self.tenant, actor=self.admin, complexity=CompanyHealthCheck.Complexity.LOW)
        original = assign_platform_employee(employee=self.employee, tenant=self.tenant, assigned_by=self.admin)
        with self.assertRaises(EngagementError) as ctx:
            transfer_engagement(engagement=original, to_employee=self.other_employee, reason="", actor=self.admin)
        self.assertEqual(ctx.exception.code, "reason_required")
        with self.assertRaises(EngagementError) as ctx:
            transfer_engagement(engagement=original, to_employee=self.employee, reason="لا فرق", actor=self.admin)
        self.assertEqual(ctx.exception.code, "same_employee")

    def test_list_assignment_candidates_reports_projected_load_and_capacity_flag(self):
        _approve_baseline(self.tenant, actor=self.admin, complexity=CompanyHealthCheck.Complexity.HIGH)
        candidates = {row["employee"].pk: row for row in list_assignment_candidates(tenant=self.tenant)}
        self.assertIn(self.employee.pk, candidates)
        self.assertEqual(candidates[self.employee.pk]["projected_load_if_assigned"], 3)
        self.assertFalse(candidates[self.employee.pk]["would_exceed_capacity"])

    def test_candidate_listing_query_count_does_not_grow_with_employees_or_engagements(self):
        """الشاشةُ تقيس كلّ موظفٍ على كلّ شركات ارتباطاته: عددُ الاستعلامات يبقى ثابتاً."""
        _approve_baseline(self.tenant, actor=self.admin, complexity=CompanyHealthCheck.Complexity.LOW)
        with CaptureQueriesContext(connection) as baseline_queries:
            list_assignment_candidates(tenant=self.tenant)

        for index in range(3):
            extra_employee = PlatformEmployee.objects.create(
                user=User.objects.create_user(
                    username=f"cap_bulk_{index}", email=f"cap_bulk_{index}@platform.local", password="x",
                ),
                specialty="data_entry",
                capacity_target=10,
                status=PlatformEmployee.Status.ACTIVE,
            )
            for served in range(2):
                Engagement.objects.create(
                    employee=extra_employee,
                    tenant=Tenant.objects.create(
                        TenantID=9210 + index * 10 + served, CompanyName=f"Served {index}-{served}",
                    ),
                    status=Engagement.Status.ACTIVE,
                )

        with CaptureQueriesContext(connection) as grown_queries:
            list_assignment_candidates(tenant=self.tenant)

        self.assertEqual(len(grown_queries), len(baseline_queries))


class CustomerAcquisitionServiceTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser(username="acq_admin", email="acq_admin@platform.local", password="x")
        self.employee_user = User.objects.create_user(username="acq_emp", email="acq_emp@platform.local", password="x")
        self.employee = PlatformEmployee.objects.create(
            user=self.employee_user, specialty="sales", status=PlatformEmployee.Status.ACTIVE,
        )
        self.other_user = User.objects.create_user(username="acq_emp2", email="acq_emp2@platform.local", password="x")
        self.other_employee = PlatformEmployee.objects.create(
            user=self.other_user, specialty="sales", status=PlatformEmployee.Status.ACTIVE,
        )
        self.tenant = Tenant.objects.create(TenantID=9300, CompanyName="Acquisition Co")

    def test_set_creates_then_updates_the_same_row(self):
        created = set_customer_acquisition(tenant=self.tenant, acquired_by=self.employee, actor=self.admin)
        self.assertEqual(CustomerAcquisition.objects.filter(tenant=self.tenant).count(), 1)
        updated = set_customer_acquisition(tenant=self.tenant, acquired_by=self.other_employee, actor=self.admin, note="تحديث")
        self.assertEqual(created.pk, updated.pk)
        self.assertEqual(CustomerAcquisition.objects.filter(tenant=self.tenant).count(), 1)
        self.assertEqual(updated.acquired_by_id, self.other_employee.pk)

    def test_refused_for_missing_employee(self):
        with self.assertRaises(AcquisitionError) as ctx:
            set_customer_acquisition(tenant=self.tenant, acquired_by=999999, actor=self.admin)
        self.assertEqual(ctx.exception.code, "employee_not_found")

    def test_get_returns_none_before_any_record(self):
        self.assertIsNone(get_customer_acquisition(self.tenant))


class HealthAndAssignmentIsolationApiTests(TestCase):
    """كل مسارٍ جديدٍ تحت `/api/platform/ops/` لهذه التذكرة يرفض غير السوبر أدمن بـ403."""

    def setUp(self):
        self.client = APIClient()
        self.admin = User.objects.create_superuser(username="iso_admin", email="iso_admin@platform.local", password="x")
        self.staff_user = User.objects.create_user(username="iso_staff", email="iso_staff@platform.local", password="x")
        PlatformEmployee.objects.create(user=self.staff_user, specialty="data_entry", status=PlatformEmployee.Status.ACTIVE)
        self.plain_user = User.objects.create_user(username="iso_plain", email="iso_plain@platform.local", password="x")
        self.tenant = Tenant.objects.create(TenantID=9400, CompanyName="Isolation Co")
        ServiceSubscription.objects.create(
            tenant=self.tenant, status=ServiceSubscription.Status.ACTIVE, plan="growth", included_quota=500,
        )
        self.company_member = User.objects.create_user(
            username="iso_company_member", email="iso_company_member@platform.local", password="x",
        )
        UserCompanyMembership.objects.create(user=self.company_member, tenant=self.tenant, role="manager")

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_non_superadmin_gets_403_on_every_health_and_engagement_route(self):
        check = create_health_check_draft(tenant=self.tenant, actor=self.admin)
        health = "/api/platform/ops/health-checks"
        engagements = "/api/platform/ops/engagements"
        endpoints = [
            ("get", f"{health}/"),
            ("get", f"{health}/{check.pk}/"),
            ("post", f"{health}/create-draft/"),
            ("post", f"{health}/{check.pk}/update/"),
            ("post", f"{health}/{check.pk}/refresh/"),
            ("post", f"{health}/{check.pk}/approve/"),
            ("post", f"{health}/{check.pk}/update-item/"),
            ("post", f"{health}/{check.pk}/item-to-work-order/"),
            ("get", f"{health}/compare/"),
            ("get", f"{engagements}/"),
            ("post", f"{engagements}/assign/"),
            # `candidates` فعلٌ GET: طلبُ POST عليه كان يُردّ 403 من طبقة الصلاحية
            # قبل أن يُرفض أصلاً بـ405، فلا يفحص المسارَ الذي يسمّيه الاختبار.
            ("get", f"{engagements}/candidates/?company={self.tenant.pk}"),
            ("get", "/api/platform/ops/acquisition/"),
            ("post", "/api/platform/ops/acquisition/"),
        ]
        # مسارٌ جديدٌ بلا حارس يُسقط هذا العدّ — راجع أيضاً EngagementViewSet.transfer/suspend/resume/revoke
        # ولها اختبار منفصل أدناه (تحتاج ارتباطاً قائماً).
        for user in (self.staff_user, self.plain_user, self.company_member):
            self._auth(user)
            for method, url in endpoints:
                with self.subTest(user=user.username, method=method, url=url):
                    response = getattr(self.client, method)(url, {}, format="json")
                    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        unauth_client = APIClient()
        for method, url in endpoints:
            with self.subTest(user="anonymous", method=method, url=url):
                response = getattr(unauth_client, method)(url, {}, format="json")
                self.assertIn(response.status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

        # لم يُسمح لأحد بإسناد فعلي رغم كل هذه المحاولات
        self.assertFalse(Engagement.objects.filter(tenant=self.tenant).exists())

    def test_non_superadmin_gets_403_on_engagement_detail_actions(self):
        _approve_baseline(self.tenant, actor=self.admin)
        employee_user = User.objects.create_user(username="iso_target_emp", email="iso_target_emp@platform.local", password="x")
        employee = PlatformEmployee.objects.create(
            user=employee_user, specialty="data_entry", capacity_target=10, status=PlatformEmployee.Status.ACTIVE,
        )
        engagement = assign_platform_employee(employee=employee, tenant=self.tenant, assigned_by=self.admin)
        engagements = "/api/platform/ops/engagements"
        endpoints = [
            ("post", f"{engagements}/{engagement.pk}/transfer/"),
            ("post", f"{engagements}/{engagement.pk}/suspend/"),
            ("post", f"{engagements}/{engagement.pk}/resume/"),
            ("post", f"{engagements}/{engagement.pk}/revoke/"),
        ]
        for user in (self.staff_user, self.plain_user):
            self._auth(user)
            for method, url in endpoints:
                with self.subTest(user=user.username, method=method, url=url):
                    response = getattr(self.client, method)(url, {}, format="json")
                    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        engagement.refresh_from_db()
        self.assertEqual(engagement.status, Engagement.Status.ACTIVE)

    def test_superadmin_can_use_the_full_happy_path_through_the_api(self):
        self._auth(self.admin)
        draft_resp = self.client.post(
            "/api/platform/ops/health-checks/create-draft/", {"tenant": self.tenant.pk}, format="json",
        )
        self.assertEqual(draft_resp.status_code, status.HTTP_201_CREATED, draft_resp.data)
        check_id = draft_resp.data["id"]

        update_resp = self.client.post(
            f"/api/platform/ops/health-checks/{check_id}/update/",
            {"complexity": CompanyHealthCheck.Complexity.LOW}, format="json",
        )
        self.assertEqual(update_resp.status_code, status.HTTP_200_OK, update_resp.data)

        mandatory_items = [
            row for row in update_resp.data["items"]
            if row["mandatory"] and row["evidence_value"] is None and not row["evidence_note"]
        ]
        for mandatory_item in mandatory_items:
            item_resp = self.client.post(
                f"/api/platform/ops/health-checks/{check_id}/update-item/",
                {"item": mandatory_item["id"], "evidence_note": "تحقّقتُ يدوياً"}, format="json",
            )
            self.assertEqual(item_resp.status_code, status.HTTP_200_OK, item_resp.data)

        approve_resp = self.client.post(f"/api/platform/ops/health-checks/{check_id}/approve/", {}, format="json")
        self.assertEqual(approve_resp.status_code, status.HTTP_200_OK, approve_resp.data)
        self.assertEqual(approve_resp.data["status"], CompanyHealthCheck.Status.APPROVED)

        employee_user = User.objects.create_user(username="api_happy_emp", email="api_happy_emp@platform.local", password="x")
        employee = PlatformEmployee.objects.create(
            user=employee_user, specialty="data_entry", capacity_target=10, status=PlatformEmployee.Status.ACTIVE,
        )
        assign_resp = self.client.post(
            "/api/platform/ops/engagements/assign/",
            {"tenant": self.tenant.pk, "employee": employee.pk}, format="json",
        )
        self.assertEqual(assign_resp.status_code, status.HTTP_201_CREATED, assign_resp.data)

        acquisition_resp = self.client.post(
            "/api/platform/ops/acquisition/",
            {"tenant": self.tenant.pk, "acquired_by": employee.pk}, format="json",
        )
        self.assertEqual(acquisition_resp.status_code, status.HTTP_200_OK, acquisition_resp.data)

        refused_resp = self.client.post(
            "/api/platform/ops/health-checks/create-draft/",
            {"tenant": Tenant.objects.create(TenantID=9401, CompanyName="No Sub Co 2").pk}, format="json",
        )
        self.assertEqual(refused_resp.status_code, status.HTTP_400_BAD_REQUEST, refused_resp.data)
        self.assertEqual(refused_resp.data["code"], "subscription_not_eligible")
