"""اختبارات سطح إدارة اشتراكات خدمة المنصة والسياسات (التذكرة 210-A)."""

from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import re
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import IntegrityError
from django.db.models import ProtectedError
from django.test import TestCase
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from inventory.models import Product
from partners.models import Partner
from platform_ops.models import (
    Engagement,
    PlatformEmployee,
    PlatformOperationEvent,
    ServiceSubscription,
    ServiceSubscriptionEvent,
    ServiceSubscriptionPolicy,
    ServiceSubscriptionPolicyEvent,
    WorkOrder,
)
from platform_ops.services import (
    BillingConfigurationError,
    EngagementError,
    SubscriptionManagementConflict,
    SubscriptionManagementError,
    activate_paid_subscription,
    activate_subscription_policy,
    apply_due_subscription_cancellations,
    assign_platform_employee,
    billing_preflight,
    clone_subscription_policy_to_draft,
    create_subscription_policy_draft,
    deactivate_service_subscription,
    get_active_subscription_policy,
    get_platform_dashboard_summary,
    is_service_active,
    offboard_platform_employee,
    is_service_trial,
    preview_subscription_policy,
    resume_service_subscription,
    schedule_service_subscription_cancellation,
    search_platform_billing_customers,
    start_service_trial,
    suspend_engagement,
    suspend_service_subscription,
    update_subscription_commercial_settings,
    update_subscription_policy_draft,
    withdraw_scheduled_service_cancellation,
)
from platform_ops.tests.test_health_and_capacity import _approve_baseline
from tenants.models import Tenant, UserCompanyMembership


User = get_user_model()


def _service_product(tenant, sku: str = "SUB-FEE"):
    """صنف خدمي في شركة فوترة المنصة — تفعيل السياسة يلزمه صنف الرسم الشهري."""
    product, _ = Product.objects.get_or_create(
        tenant=tenant, sku=sku, defaults={"name_ar": f"صنف اشتراك {sku}", "is_service": True},
    )
    return product


def _make_platform_tenant_pair(prefix: int):
    """شركة مشتركة وشركة فوترة منصة منفصلة — نمط متكرر في كل اختبار هنا."""
    tenant = Tenant.objects.create(
        TenantID=prefix, CompanyName=f"Managed Company {prefix}", SubscriptionPlan="Trial",
    )
    platform_tenant = Tenant.objects.create(
        TenantID=prefix + 1, CompanyName=f"Platform Billing Company {prefix}", SubscriptionPlan="Enterprise",
    )
    return tenant, platform_tenant


def _activate_unit_catalog(actor=None):
    """كتالوجُ وحداتٍ سارٍ — **لا تُفعَّل خدمةٌ بلا واحد** (القصة ١٨ من #210).

    الكتالوج عامٌّ للمنصّة لا لكلّ شركة، فيكفي واحدٌ لكلّ اختبار؛ ويُعاد الساري
    إن وُجد بدل إنشاء نسخةٍ ثانيةٍ بلا داعٍ. الاستيراداتُ داخل الدالّة كي لا
    تتضخّم قوائمُ الاستيراد أعلاه بأسماءٍ لا يستعملها إلا هذا المُهيِّئ.
    """
    from platform_ops.models import ServiceDocumentType
    from platform_ops.services import (
        activate_service_unit_catalog,
        create_service_unit_catalog_draft,
        get_active_service_unit_catalog,
        update_service_unit_catalog_entries,
    )

    existing = get_active_service_unit_catalog()
    if existing is not None:
        return existing
    draft = create_service_unit_catalog_draft(actor=actor)
    update_service_unit_catalog_entries(
        catalog=draft,
        entries=[{
            "document_type": ServiceDocumentType.SALES_INVOICE,
            "base_units": Decimal("1.00"),
            "per_line_weight": Decimal("0.50"),
        }],
        actor=actor,
    )
    return activate_service_unit_catalog(
        catalog=draft, actor=actor, activation_reason="كتالوج وحداتٍ للاختبارات",
    )


class SubscriptionPolicyServiceTests(TestCase):
    def setUp(self):
        _activate_unit_catalog()
        self.admin = User.objects.create_superuser(
            username="policy_admin", email="policy_admin@example.test", password="x",
        )
        self.tenant, self.platform_tenant = _make_platform_tenant_pair(2200)
        self.customer = Partner.objects.create(
            tenant=self.platform_tenant, name="Policy Customer", partner_type="Customer",
        )

    def test_only_one_policy_version_is_active_at_a_time(self):
        first_draft = create_subscription_policy_draft(billing_tenant=self.platform_tenant, fixed_fee_product=_service_product(self.platform_tenant))
        first = activate_subscription_policy(policy=first_draft, actor=self.admin, change_reason="إطلاق pilot")
        self.assertEqual(get_active_subscription_policy().pk, first.pk)

        second_draft = create_subscription_policy_draft(billing_tenant=self.platform_tenant, fixed_fee_product=_service_product(self.platform_tenant), monthly_fee=Decimal("325.00"))
        activate_subscription_policy(policy=second_draft, actor=self.admin, change_reason="تعديل السعر")

        first.refresh_from_db()
        self.assertEqual(first.status, ServiceSubscriptionPolicy.Status.RETIRED)
        active_versions = ServiceSubscriptionPolicy.objects.filter(status=ServiceSubscriptionPolicy.Status.ACTIVE)
        self.assertEqual(active_versions.count(), 1)
        self.assertEqual(active_versions.first().pk, second_draft.pk)

    def test_activation_requires_non_empty_reason_and_stores_it(self):
        draft = create_subscription_policy_draft(billing_tenant=self.platform_tenant, fixed_fee_product=_service_product(self.platform_tenant))
        with self.assertRaises(SubscriptionManagementError) as ctx:
            activate_subscription_policy(policy=draft, actor=self.admin, change_reason="   ")
        self.assertEqual(ctx.exception.code, "change_reason_required")

        activated = activate_subscription_policy(policy=draft, actor=self.admin, change_reason="إطلاق pilot")
        self.assertEqual(activated.activation_reason, "إطلاق pilot")

    def test_active_and_retired_versions_are_never_edited_only_cloned(self):
        draft = create_subscription_policy_draft(billing_tenant=self.platform_tenant, fixed_fee_product=_service_product(self.platform_tenant))
        active = activate_subscription_policy(policy=draft, actor=self.admin, change_reason="إطلاق")
        with self.assertRaises(SubscriptionManagementConflict):
            update_subscription_policy_draft(policy=active, monthly_fee=Decimal("1.00"))

        clone = clone_subscription_policy_to_draft(policy=active, actor=self.admin)
        self.assertEqual(clone.status, ServiceSubscriptionPolicy.Status.DRAFT)
        self.assertEqual(clone.monthly_fee, active.monthly_fee)
        self.assertEqual(clone.overage_unit_price, active.overage_unit_price)
        self.assertNotEqual(clone.pk, active.pk)

    def test_preview_returns_diff_and_states_existing_subscriptions_are_untouched(self):
        base_draft = create_subscription_policy_draft(billing_tenant=self.platform_tenant, fixed_fee_product=_service_product(self.platform_tenant))
        activate_subscription_policy(policy=base_draft, actor=self.admin, change_reason="إطلاق")
        subscription = activate_paid_subscription(tenant=self.tenant, billing_customer=self.customer)

        new_draft = create_subscription_policy_draft(
            billing_tenant=self.platform_tenant, fixed_fee_product=_service_product(self.platform_tenant), monthly_fee=Decimal("450.00"), included_quota=500,
        )
        impact = preview_subscription_policy(policy=new_draft)
        self.assertIn("monthly_fee", impact["diff"])
        # المال نصٌّ دقيق لا Decimal يصير float في JSON.
        self.assertEqual(impact["diff"]["monthly_fee"], {"active": "300.00", "draft": "450.00"})
        self.assertIn("لا يتغيّر أي اشتراك قائم", impact["note"])

        subscription.refresh_from_db()
        self.assertEqual(subscription.monthly_fee, Decimal("300.00"))

    def test_plan_specific_version_beats_the_general_one_and_unknown_plans_fall_back(self):
        general = activate_subscription_policy(
            policy=create_subscription_policy_draft(
                billing_tenant=self.platform_tenant, fixed_fee_product=_service_product(self.platform_tenant),
            ),
            actor=self.admin, change_reason="عامة",
        )
        enterprise = activate_subscription_policy(
            policy=create_subscription_policy_draft(
                billing_tenant=self.platform_tenant, plan="enterprise", monthly_fee=Decimal("900.00"),
                fixed_fee_product=_service_product(self.platform_tenant),
            ),
            actor=self.admin, change_reason="خطة المؤسسات",
        )
        self.assertEqual(get_active_subscription_policy(plan="enterprise").pk, enterprise.pk)
        self.assertEqual(get_active_subscription_policy(plan="growth").pk, general.pk)
        self.assertEqual(get_active_subscription_policy().pk, general.pk)
        # نسختان ساريتان في نطاقين مختلفين لا تتداخلان.
        general.refresh_from_db()
        self.assertEqual(general.effective_state(), "current")

        trial = start_service_trial(tenant=self.tenant, plan="enterprise", actor=self.admin)
        self.assertEqual((trial.plan, trial.monthly_fee), ("enterprise", Decimal("900.00")))
        self.assertEqual(trial.subscription_policy_version, enterprise.version)
        self.assertEqual(trial.fixed_fee_product_id, enterprise.fixed_fee_product_id)

    def test_future_effective_date_schedules_the_version_and_overlap_is_refused(self):
        current = activate_subscription_policy(
            policy=create_subscription_policy_draft(
                billing_tenant=self.platform_tenant, fixed_fee_product=_service_product(self.platform_tenant),
            ),
            actor=self.admin, change_reason="حالية",
        )
        starts = timezone.now() + timedelta(days=10)
        scheduled = activate_subscription_policy(
            policy=create_subscription_policy_draft(
                billing_tenant=self.platform_tenant, monthly_fee=Decimal("350.00"),
                fixed_fee_product=_service_product(self.platform_tenant),
            ),
            actor=self.admin, change_reason="رفع مجدول", effective_from=starts,
        )
        current.refresh_from_db()
        self.assertEqual(scheduled.effective_state(), "scheduled")
        self.assertEqual(current.effective_to, starts)
        self.assertEqual(get_active_subscription_policy().pk, current.pk)
        self.assertEqual(get_active_subscription_policy(at=starts + timedelta(seconds=1)).pk, scheduled.pk)
        self.assertEqual(current.effective_state(at=starts + timedelta(seconds=1)), "retired")

        earlier = create_subscription_policy_draft(
            billing_tenant=self.platform_tenant, fixed_fee_product=_service_product(self.platform_tenant),
        )
        with self.assertRaises(SubscriptionManagementConflict) as ctx:
            activate_subscription_policy(
                policy=earlier, actor=self.admin, change_reason="تداخل", effective_from=starts - timedelta(days=1),
            )
        self.assertEqual(ctx.exception.code, "subscription_policy_overlap")
        with self.assertRaises(SubscriptionManagementError) as ctx:
            activate_subscription_policy(
                policy=earlier, actor=self.admin, change_reason="ماضٍ", effective_from=timezone.now() - timedelta(days=1),
            )
        self.assertEqual(ctx.exception.code, "effective_from_in_past")

    def test_activation_requires_valid_billing_products_from_the_billing_tenant(self):
        without_product = create_subscription_policy_draft(billing_tenant=self.platform_tenant)
        with self.assertRaises(SubscriptionManagementError) as ctx:
            activate_subscription_policy(policy=without_product, actor=self.admin, change_reason="بلا صنف")
        self.assertEqual(ctx.exception.code, "fixed_fee_product_required")

        physical = Product.objects.create(tenant=self.platform_tenant, sku="PHYS", name_ar="سلعة", is_service=False)
        with self.assertRaises(SubscriptionManagementError) as ctx:
            update_subscription_policy_draft(policy=without_product, fixed_fee_product=physical)
        self.assertEqual(ctx.exception.code, "fixed_fee_product_not_service")
        with self.assertRaises(SubscriptionManagementError) as ctx:
            update_subscription_policy_draft(policy=without_product, fixed_fee_product=_service_product(self.tenant))
        self.assertEqual(ctx.exception.code, "fixed_fee_product_cross_tenant")

        update_subscription_policy_draft(
            policy=without_product,
            fixed_fee_product=_service_product(self.platform_tenant),
            overage_unit_price=Decimal("2.00"),
        )
        with self.assertRaises(SubscriptionManagementError) as ctx:
            activate_subscription_policy(policy=without_product, actor=self.admin, change_reason="بلا صنف تجاوز")
        self.assertEqual(ctx.exception.code, "overage_product_required")

        update_subscription_policy_draft(
            policy=without_product, overage_product=_service_product(self.platform_tenant, "SUB-OVR"),
        )
        activated = activate_subscription_policy(policy=without_product, actor=self.admin, change_reason="مكتملة")
        self.assertEqual(activated.effective_state(), "current")

    def test_draft_without_values_takes_model_defaults(self):
        draft = create_subscription_policy_draft(billing_tenant=self.platform_tenant, fixed_fee_product=_service_product(self.platform_tenant))
        self.assertEqual(
            (draft.monthly_fee, draft.included_quota, draft.trial_days, draft.overage_unit_price),
            (Decimal("300.00"), 300, 7, Decimal("0.00")),
        )

    def test_every_policy_write_leaves_one_immutable_event_with_correlation_id(self):
        draft = create_subscription_policy_draft(
            billing_tenant=self.platform_tenant, fixed_fee_product=_service_product(self.platform_tenant), actor=self.admin, correlation_id="corr-create",
        )
        update_subscription_policy_draft(
            policy=draft, actor=self.admin, correlation_id="corr-update", monthly_fee=Decimal("310.00"),
        )
        first = activate_subscription_policy(
            policy=draft, actor=self.admin, change_reason="إطلاق", correlation_id="corr-activate-1",
        )
        clone = clone_subscription_policy_to_draft(policy=first, actor=self.admin, correlation_id="corr-clone")
        activate_subscription_policy(
            policy=clone, actor=self.admin, change_reason="نسخة ثانية", correlation_id="corr-activate-2",
        )

        first_events = list(
            ServiceSubscriptionPolicyEvent.objects.filter(policy=first).order_by("pk")
            .values_list("action", "correlation_id")
        )
        self.assertEqual(first_events, [
            ("created", "corr-create"),
            ("updated", "corr-update"),
            ("activated", "corr-activate-1"),
            ("retired", "corr-activate-2"),
        ])
        update_event = ServiceSubscriptionPolicyEvent.objects.get(policy=first, action="updated")
        self.assertEqual(update_event.details["before"]["monthly_fee"], "300.00")
        self.assertEqual(update_event.details["after"]["monthly_fee"], "310.00")

        clone_events = list(
            ServiceSubscriptionPolicyEvent.objects.filter(policy=clone).order_by("pk").values_list("action", flat=True)
        )
        self.assertEqual(clone_events, ["cloned", "activated"])
        self.assertEqual(
            ServiceSubscriptionPolicyEvent.objects.get(policy=clone, action="cloned").details["source_policy_id"],
            first.pk,
        )

        with self.assertRaises(ProtectedError):
            first.delete()

    def test_invalid_billing_tenant_id_returns_domain_error_not_500(self):
        with self.assertRaises(SubscriptionManagementError) as ctx:
            create_subscription_policy_draft(billing_tenant=999999)
        self.assertEqual(ctx.exception.code, "billing_tenant_not_found")
        self.assertEqual(ctx.exception.status_code, 400)


class SubscriptionLifecycleServiceTests(TestCase):
    def setUp(self):
        _activate_unit_catalog()
        self.admin = User.objects.create_superuser(
            username="lifecycle_admin", email="lifecycle_admin@example.test", password="x",
        )
        self.employee_user = User.objects.create_user(
            username="lifecycle_employee", email="lifecycle_employee@example.test", password="x",
        )
        self.employee = PlatformEmployee.objects.create(
            user=self.employee_user, specialty="data_entry", capacity_target=10,
            status=PlatformEmployee.Status.ACTIVE,
        )
        self.tenant, self.platform_tenant = _make_platform_tenant_pair(2300)
        self.customer = Partner.objects.create(
            tenant=self.platform_tenant, name="Managed Customer", partner_type="Customer",
        )
        self.second_customer = Partner.objects.create(
            tenant=self.platform_tenant, name="Second Managed Customer", partner_type="Customer",
        )
        self.same_tenant_customer = Partner.objects.create(
            tenant=self.tenant, name="Same Tenant Customer", partner_type="Customer",
        )
        self.unrelated_tenant = Tenant.objects.create(TenantID=2304, CompanyName="Unrelated Co")
        self.unrelated_customer = Partner.objects.create(
            tenant=self.unrelated_tenant, name="Unrelated Customer", partner_type="Customer",
        )
        draft = create_subscription_policy_draft(billing_tenant=self.platform_tenant, fixed_fee_product=_service_product(self.platform_tenant))
        self.policy = activate_subscription_policy(policy=draft, actor=self.admin, change_reason="إطلاق pilot")

    # ── بدء التجربة ──────────────────────────────────────────────
    def test_start_trial_creates_eligible_row_once_per_tenant_lifetime(self):
        before = timezone.now()
        subscription = start_service_trial(tenant=self.tenant, actor=self.admin, correlation_id="corr-trial")
        self.assertEqual(subscription.status, ServiceSubscription.Status.TRIAL)
        self.assertGreaterEqual(subscription.trial_started_at, before)
        self.assertEqual(subscription.trial_ends_at - subscription.trial_started_at, timedelta(days=7))
        self.assertTrue(is_service_active(self.tenant))
        self.assertTrue(is_service_trial(subscription))

        event = ServiceSubscriptionEvent.objects.get(subscription=subscription)
        self.assertEqual(event.action, ServiceSubscriptionEvent.Action.TRIAL_STARTED)
        self.assertEqual(event.correlation_id, "corr-trial")

        with self.assertRaises(SubscriptionManagementConflict) as ctx:
            start_service_trial(tenant=self.tenant, actor=self.admin)
        self.assertEqual(ctx.exception.code, "trial_already_used")

    def test_expired_trial_is_not_eligible(self):
        subscription = start_service_trial(tenant=self.tenant, actor=self.admin)
        subscription.trial_ends_at = timezone.now() - timedelta(hours=1)
        subscription.save(update_fields=["trial_ends_at"])
        self.assertFalse(is_service_active(self.tenant))
        with self.assertRaises(EngagementError):
            assign_platform_employee(employee=self.employee, tenant=self.tenant)

    # ── التفعيل المدفوع من كل مصدر مسموح ──────────────────────────
    def test_activate_paid_from_none_trial_and_cancelled_never_grants_second_trial(self):
        subscription = activate_paid_subscription(tenant=self.tenant, billing_customer=self.customer, actor=self.admin)
        self.assertEqual(subscription.status, ServiceSubscription.Status.ACTIVE)
        self.assertIsNone(subscription.trial_started_at)
        event = ServiceSubscriptionEvent.objects.get(subscription=subscription)
        self.assertEqual(event.action, ServiceSubscriptionEvent.Action.ACTIVATED)

        deactivate_service_subscription(
            subscription=subscription, new_status=ServiceSubscription.Status.CANCELLED, reason="انتهى pilot",
        )
        reactivated = activate_paid_subscription(tenant=self.tenant, billing_customer=self.customer, actor=self.admin)
        self.assertEqual(reactivated.status, ServiceSubscription.Status.ACTIVE)
        self.assertIsNone(reactivated.trial_started_at)

        second_tenant, _ = _make_platform_tenant_pair(2310)
        trial = start_service_trial(tenant=second_tenant, actor=self.admin)
        converted = activate_paid_subscription(tenant=second_tenant, billing_customer=self.customer, actor=self.admin)
        self.assertEqual(converted.status, ServiceSubscription.Status.ACTIVE)
        self.assertIsNotNone(converted.trial_started_at)
        convert_event = ServiceSubscriptionEvent.objects.filter(
            subscription=converted, action=ServiceSubscriptionEvent.Action.TRIAL_CONVERTED,
        )
        self.assertTrue(convert_event.exists())

    @patch("platform_ops.services.timezone.localdate", return_value=date(2026, 1, 30))
    def test_reactivation_uses_current_policy_snapshot_while_trial_conversion_keeps_its_snapshot(self, _localdate):
        paid = activate_paid_subscription(tenant=self.tenant, billing_customer=self.customer, actor=self.admin)
        paid.consumed_quota = 99
        paid.save(update_fields=["consumed_quota"])
        deactivate_service_subscription(
            subscription=paid,
            new_status=ServiceSubscription.Status.CANCELLED,
            reason="انتهت الدورة",
            actor=self.admin,
        )

        new_billing_tenant = Tenant.objects.create(TenantID=2390, CompanyName="New Billing Tenant")
        old_tenant_customer = self.customer
        new_customer = Partner.objects.create(
            tenant=new_billing_tenant,
            name="New Billing Customer",
            partner_type="Customer",
        )
        replacement_draft = create_subscription_policy_draft(
            billing_tenant=new_billing_tenant, fixed_fee_product=_service_product(new_billing_tenant),
            monthly_fee=Decimal("450.00"),
            included_quota=450,
            overage_unit_price=Decimal("4.50"),
            overage_product=_service_product(new_billing_tenant, "SUB-OVR"),
        )
        replacement_policy = activate_subscription_policy(
            policy=replacement_draft,
            actor=self.admin,
            change_reason="تحديث العرض التجاري",
        )

        with self.assertRaises(BillingConfigurationError) as refused:
            activate_paid_subscription(
                tenant=self.tenant,
                billing_customer=old_tenant_customer,
                actor=self.admin,
            )
        self.assertEqual(refused.exception.code, "billing_customer_wrong_platform_tenant")

        reactivated = activate_paid_subscription(
            tenant=self.tenant,
            billing_customer=new_customer,
            actor=self.admin,
        )
        self.assertEqual(reactivated.monthly_fee, Decimal("450.00"))
        self.assertEqual(reactivated.included_quota, 450)
        self.assertEqual(reactivated.overage_unit_price, Decimal("4.50"))
        self.assertEqual(reactivated.billing_tenant_id, new_billing_tenant.pk)
        self.assertEqual(reactivated.subscription_policy_version, replacement_policy.version)
        self.assertEqual(reactivated.consumed_quota, 0)
        self.assertEqual(reactivated.period_start, date(2026, 2, 1))
        self.assertEqual(reactivated.period_end, date(2026, 2, 28))

        trial_tenant = Tenant.objects.create(TenantID=2391, CompanyName="Trial Snapshot Tenant")
        trial = start_service_trial(tenant=trial_tenant, actor=self.admin)
        trial_snapshot = (
            trial.monthly_fee,
            trial.included_quota,
            trial.overage_unit_price,
            trial.billing_tenant_id,
            trial.subscription_policy_version,
        )
        later_draft = create_subscription_policy_draft(
            billing_tenant=self.platform_tenant, fixed_fee_product=_service_product(self.platform_tenant),
            monthly_fee=Decimal("510.00"),
            included_quota=510,
            overage_unit_price=Decimal("5.10"),
            overage_product=_service_product(self.platform_tenant, "SUB-OVR"),
        )
        activate_subscription_policy(policy=later_draft, actor=self.admin, change_reason="تعديل لاحق")
        # عميلٌ من شركة فوترة لقطة التجربة يُقبل رغم أن السياسة الأحدث غيّرت شركة الفوترة.
        converted = activate_paid_subscription(tenant=trial_tenant, billing_customer=new_customer, actor=self.admin)
        self.assertEqual(
            (
                converted.monthly_fee,
                converted.included_quota,
                converted.overage_unit_price,
                converted.billing_tenant_id,
                converted.subscription_policy_version,
            ),
            trial_snapshot,
        )

    @patch("platform_ops.services.timezone.localdate", return_value=date(2026, 1, 30))
    def test_paid_activation_starts_billing_in_the_following_calendar_month(self, _localdate):
        subscription = activate_paid_subscription(tenant=self.tenant, billing_customer=self.customer, actor=self.admin)
        self.assertEqual(subscription.period_start, date(2026, 2, 1))
        self.assertEqual(subscription.period_end, date(2026, 2, 28))
        err = billing_preflight(
            subscription=subscription,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 1, 31),
            fixed_fee_product_id=1,
        )
        self.assertEqual(err.code, "subscription_not_yet_billable")
        # الإلغاء في شهر التفعيل ينهي الخدمة قبل أول دورة مفوترة — لا شهر كامل إضافي.
        scheduled = schedule_service_subscription_cancellation(
            subscription=subscription, reason="إيقاف", actor=self.admin,
        )
        self.assertEqual(scheduled.scheduled_cancellation_date, date(2026, 1, 31))
        applied = apply_due_subscription_cancellations(
            now=timezone.make_aware(datetime(2026, 2, 1, 6, 0)),
        )
        self.assertEqual(applied["applied_subscription_ids"], [subscription.pk])

    def test_activate_paid_refuses_already_active_and_suspended_sources(self):
        subscription = activate_paid_subscription(tenant=self.tenant, billing_customer=self.customer, actor=self.admin)
        with self.assertRaises(SubscriptionManagementConflict) as ctx:
            activate_paid_subscription(tenant=self.tenant, billing_customer=self.customer, actor=self.admin)
        self.assertEqual(ctx.exception.code, "subscription_already_active")

        suspend_service_subscription(subscription=subscription, reason="إيقاف مؤقت", actor=self.admin)
        with self.assertRaises(SubscriptionManagementConflict) as ctx:
            activate_paid_subscription(tenant=self.tenant, billing_customer=self.customer, actor=self.admin)
        self.assertEqual(ctx.exception.code, "subscription_suspended")

    def test_first_activation_integrity_error_is_a_controlled_conflict_not_500(self):
        with patch.object(ServiceSubscription.objects, "create", side_effect=IntegrityError("race")):
            with self.assertRaises(SubscriptionManagementConflict) as ctx:
                activate_paid_subscription(tenant=self.tenant, billing_customer=self.customer, actor=self.admin)
        self.assertEqual(ctx.exception.code, "subscription_activation_conflict")
        self.assertEqual(ctx.exception.status_code, 409)

    # ── التعليق والاستئناف ─────────────────────────────────────────
    def test_suspend_only_from_trial_or_active_and_resume_restores_previous_status(self):
        with self.assertRaises(SubscriptionManagementError):
            suspend_service_subscription(subscription=None, reason="", actor=self.admin)

        trial = start_service_trial(tenant=self.tenant, actor=self.admin)
        suspended = suspend_service_subscription(subscription=trial, reason="تأخر سداد", actor=self.admin, correlation_id="corr-susp")
        self.assertEqual(suspended.status, ServiceSubscription.Status.SUSPENDED)
        self.assertEqual(suspended.pre_suspension_status, ServiceSubscription.Status.TRIAL)
        event = ServiceSubscriptionEvent.objects.get(subscription=suspended, action=ServiceSubscriptionEvent.Action.SUSPENDED)
        self.assertEqual(event.correlation_id, "corr-susp")

        with self.assertRaises(SubscriptionManagementConflict) as ctx:
            suspend_service_subscription(subscription=suspended, reason="مكرر", actor=self.admin)
        self.assertEqual(ctx.exception.code, "subscription_not_suspendable")

        resumed = resume_service_subscription(subscription=suspended, actor=self.admin)
        self.assertEqual(resumed.status, ServiceSubscription.Status.TRIAL)
        self.assertEqual(resumed.pre_suspension_status, "")

    def test_cancelled_subscription_is_never_resumable(self):
        subscription = activate_paid_subscription(tenant=self.tenant, billing_customer=self.customer, actor=self.admin)
        deactivate_service_subscription(
            subscription=subscription, new_status=ServiceSubscription.Status.CANCELLED, reason="إنهاء",
        )
        with self.assertRaises(SubscriptionManagementConflict) as ctx:
            resume_service_subscription(subscription=subscription, actor=self.admin)
        self.assertEqual(ctx.exception.code, "subscription_not_suspended")

    def test_suspension_suspends_engagements_without_deleting_history(self):
        subscription = activate_paid_subscription(tenant=self.tenant, billing_customer=self.customer, actor=self.admin)
        _approve_baseline(self.tenant, actor=self.admin)
        engagement = assign_platform_employee(employee=self.employee, tenant=self.tenant)
        suspend_service_subscription(subscription=subscription, reason="تأخر سداد", actor=self.admin)
        engagement.refresh_from_db()
        self.assertEqual(engagement.status, Engagement.Status.SUSPENDED)
        # تعليقُ الاشتراك يعلّق ارتباطاتٍ فعلاً، فلا يجوز أن يخلو سجلّ 210-B الموحّد منه.
        suspension_event = PlatformOperationEvent.objects.get(
            domain=PlatformOperationEvent.Domain.ENGAGEMENT,
            action=PlatformOperationEvent.Action.SUSPENDED,
            subject_id=engagement.pk,
        )
        self.assertEqual(suspension_event.actor_id, self.admin.pk)
        self.assertEqual(suspension_event.details["source"], "subscription_deactivation")
        with self.assertRaises(EngagementError):
            assign_platform_employee(employee=self.employee, tenant=self.tenant)

    def test_resume_restores_only_the_engagements_that_this_suspension_suspended(self):
        subscription = activate_paid_subscription(tenant=self.tenant, billing_customer=self.customer, actor=self.admin)
        _approve_baseline(self.tenant, actor=self.admin)
        restored = assign_platform_employee(employee=self.employee, tenant=self.tenant)
        other_employee = PlatformEmployee.objects.create(
            user=User.objects.create_user(username="resume_other", email="resume_other@example.test", password="x"),
            specialty="data_entry",
            capacity_target=10,
            status=PlatformEmployee.Status.ACTIVE,
        )
        stays_suspended = assign_platform_employee(employee=other_employee, tenant=self.tenant)
        suspend_engagement(engagement=stays_suspended, reason="قرار مدير قبل تعليق الاشتراك")

        suspend_service_subscription(subscription=subscription, reason="تأخر سداد", actor=self.admin)
        resume_service_subscription(subscription=subscription, actor=self.admin)

        restored.refresh_from_db()
        stays_suspended.refresh_from_db()
        # بلا استئناف الارتباطات تعود الشركة مؤهَّلةً وبلا أي ارتباط بصمت.
        self.assertEqual(restored.status, Engagement.Status.ACTIVE)
        # وما علّقه مديرٌ يدوياً قبل التعليق ليس من شأن استئناف الاشتراك.
        self.assertEqual(stays_suspended.status, Engagement.Status.SUSPENDED)
        event = ServiceSubscriptionEvent.objects.filter(
            subscription=subscription, action=ServiceSubscriptionEvent.Action.RESUMED,
        ).latest("pk")
        self.assertEqual(event.details["resumed_engagement_ids"], [restored.pk])
        self.assertEqual(event.details["failed_engagements"], [])
        # الاستئنافُ فعلُ فاعلٍ معروف: حدثُ الارتباط يحمله لا `None`.
        resume_event = PlatformOperationEvent.objects.get(
            domain=PlatformOperationEvent.Domain.ENGAGEMENT,
            action=PlatformOperationEvent.Action.RESUMED,
            subject_id=restored.pk,
        )
        self.assertEqual(resume_event.actor_id, self.admin.pk)

    def test_resume_records_engagements_it_could_not_restore_instead_of_failing_whole(self):
        subscription = activate_paid_subscription(tenant=self.tenant, billing_customer=self.customer, actor=self.admin)
        _approve_baseline(self.tenant, actor=self.admin)
        engagement = assign_platform_employee(employee=self.employee, tenant=self.tenant)
        suspend_service_subscription(subscription=subscription, reason="تأخر سداد", actor=self.admin)
        offboard_platform_employee(employee=self.employee, actor=self.admin)

        resumed = resume_service_subscription(subscription=subscription, actor=self.admin)

        self.assertEqual(resumed.status, ServiceSubscription.Status.ACTIVE)
        event = ServiceSubscriptionEvent.objects.filter(
            subscription=subscription, action=ServiceSubscriptionEvent.Action.RESUMED,
        ).latest("pk")
        self.assertEqual(event.details["resumed_engagement_ids"], [])
        self.assertEqual([row["engagement"] for row in event.details["failed_engagements"]], [engagement.pk])

    # ── الإلغاء المجدول والفوري وسحبه ──────────────────────────────
    def test_cancellation_defaults_to_scheduled_end_of_cycle_not_immediate(self):
        subscription = activate_paid_subscription(tenant=self.tenant, billing_customer=self.customer, actor=self.admin)
        # دورةٌ جارية فعلاً: الافتراضي نهايتها.
        subscription.period_start = timezone.localdate() - timedelta(days=5)
        subscription.period_end = timezone.localdate() + timedelta(days=10)
        subscription.save(update_fields=["period_start", "period_end"])

        scheduled = schedule_service_subscription_cancellation(
            subscription=subscription, reason="لن نجدد", actor=self.admin, correlation_id="corr-cancel",
        )
        self.assertEqual(scheduled.status, ServiceSubscription.Status.ACTIVE)
        self.assertEqual(scheduled.scheduled_cancellation_date, subscription.period_end)
        event = ServiceSubscriptionEvent.objects.get(
            subscription=scheduled, action=ServiceSubscriptionEvent.Action.CANCELLATION_SCHEDULED,
        )
        self.assertEqual(event.correlation_id, "corr-cancel")

        withdrawn = withdraw_scheduled_service_cancellation(subscription=scheduled, actor=self.admin)
        self.assertIsNone(withdrawn.scheduled_cancellation_date)
        with self.assertRaises(SubscriptionManagementError) as ctx:
            withdraw_scheduled_service_cancellation(subscription=withdrawn, actor=self.admin)
        self.assertEqual(ctx.exception.code, "no_scheduled_cancellation")

    def test_immediate_cancellation_uses_deactivate_path_now(self):
        subscription = activate_paid_subscription(tenant=self.tenant, billing_customer=self.customer, actor=self.admin)
        cancelled = schedule_service_subscription_cancellation(
            subscription=subscription, reason="خرق شروط", actor=self.admin, immediate=True,
        )
        self.assertEqual(cancelled.status, ServiceSubscription.Status.CANCELLED)
        self.assertIsNone(cancelled.scheduled_cancellation_date)

    def test_scheduled_cancellation_is_applied_once_by_command_service_and_not_by_dry_run(self):
        subscription = activate_paid_subscription(tenant=self.tenant, billing_customer=self.customer, actor=self.admin)
        past_date = timezone.localdate() - timedelta(days=1)
        subscription.scheduled_cancellation_date = past_date
        subscription.cancellation_reason = "دورة انتهت"
        subscription.save(update_fields=["scheduled_cancellation_date", "cancellation_reason"])

        result = apply_due_subscription_cancellations()
        self.assertEqual(result["applied_count"], 1)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, ServiceSubscription.Status.CANCELLED)

        # idempotent: تشغيلٌ ثانٍ لا يطبّق شيئاً على الصفّ الملغى بالفعل
        second_run = apply_due_subscription_cancellations()
        self.assertEqual(second_run["applied_count"], 0)

    def test_due_cancellation_keeps_the_scheduled_last_service_day_inclusive(self):
        subscription = activate_paid_subscription(tenant=self.tenant, billing_customer=self.customer, actor=self.admin)
        today = timezone.localdate()
        subscription.scheduled_cancellation_date = today
        subscription.cancellation_reason = "حد اليوم"
        subscription.save(update_fields=["scheduled_cancellation_date", "cancellation_reason"])

        same_day = apply_due_subscription_cancellations(
            now=timezone.make_aware(datetime.combine(today, datetime.min.time())),
        )
        self.assertEqual(same_day["applied_count"], 0)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, ServiceSubscription.Status.ACTIVE)

        subscription.scheduled_cancellation_date = today - timedelta(days=1)
        subscription.save(update_fields=["scheduled_cancellation_date"])
        yesterday = apply_due_subscription_cancellations(
            now=timezone.make_aware(datetime.combine(today, datetime.min.time())),
        )
        self.assertEqual(yesterday["applied_count"], 1)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, ServiceSubscription.Status.CANCELLED)

    def test_paid_activation_snapshots_billing_products_and_conversion_cannot_change_the_plan(self):
        paid = activate_paid_subscription(tenant=self.tenant, billing_customer=self.customer, actor=self.admin)
        self.assertEqual(paid.fixed_fee_product_id, self.policy.fixed_fee_product_id)

        trial_tenant, _ = _make_platform_tenant_pair(2330)
        trial = start_service_trial(tenant=trial_tenant, actor=self.admin)
        with self.assertRaises(SubscriptionManagementError) as ctx:
            activate_paid_subscription(
                tenant=trial_tenant, billing_customer=self.customer, plan="enterprise", actor=self.admin,
            )
        self.assertEqual(ctx.exception.code, "plan_fixed_by_trial")
        converted = activate_paid_subscription(
            tenant=trial_tenant, billing_customer=self.customer, plan=trial.plan, actor=self.admin,
        )
        self.assertEqual(converted.plan, trial.plan)

    def test_reactivation_keeps_the_replaced_commercial_terms_in_the_event(self):
        paid = activate_paid_subscription(tenant=self.tenant, billing_customer=self.customer, actor=self.admin)
        deactivate_service_subscription(
            subscription=paid, new_status=ServiceSubscription.Status.CANCELLED, reason="انتهت",
        )
        reactivated = activate_paid_subscription(
            tenant=self.tenant, billing_customer=self.second_customer, actor=self.admin,
        )
        event = ServiceSubscriptionEvent.objects.filter(
            subscription=reactivated, action=ServiceSubscriptionEvent.Action.ACTIVATED,
        ).order_by("-pk").first()
        self.assertEqual(event.details["previous_terms"]["monthly_fee"], "300.00")
        self.assertEqual(event.details["previous_terms"]["billing_customer_id"], self.customer.pk)

    def test_commercial_settings_need_a_reason_skip_unchanged_fields_and_refuse_cancelled_rows(self):
        subscription = activate_paid_subscription(tenant=self.tenant, billing_customer=self.customer, actor=self.admin)
        with self.assertRaises(SubscriptionManagementError) as ctx:
            update_subscription_commercial_settings(subscription=subscription, monthly_fee=Decimal("250.00"))
        self.assertEqual(ctx.exception.code, "reason_required")

        unchanged = update_subscription_commercial_settings(
            subscription=subscription, plan=subscription.plan, monthly_fee=subscription.monthly_fee,
        )
        self.assertEqual(unchanged.pk, subscription.pk)
        self.assertFalse(ServiceSubscriptionEvent.objects.filter(
            subscription=subscription, action=ServiceSubscriptionEvent.Action.SETTINGS_UPDATED,
        ).exists())

        update_subscription_commercial_settings(
            subscription=subscription, plan=subscription.plan, monthly_fee=Decimal("250.00"), reason="خصم",
        )
        event = ServiceSubscriptionEvent.objects.get(
            subscription=subscription, action=ServiceSubscriptionEvent.Action.SETTINGS_UPDATED,
        )
        self.assertEqual(set(event.details["changes"]), {"monthly_fee"})

        deactivate_service_subscription(
            subscription=subscription, new_status=ServiceSubscription.Status.CANCELLED, reason="إنهاء",
        )
        with self.assertRaises(SubscriptionManagementConflict) as ctx:
            update_subscription_commercial_settings(
                subscription=subscription, monthly_fee=Decimal("1.00"), reason="بعد الإلغاء",
            )
        self.assertEqual(ctx.exception.code, "subscription_cancelled")

    def test_cancelling_a_suspended_trial_defaults_to_the_trial_end(self):
        trial = start_service_trial(tenant=self.tenant, actor=self.admin)
        suspended = suspend_service_subscription(subscription=trial, reason="إيقاف", actor=self.admin)
        scheduled = schedule_service_subscription_cancellation(subscription=suspended, reason="لن نكمل", actor=self.admin)
        self.assertEqual(scheduled.scheduled_cancellation_date, timezone.localtime(trial.trial_ends_at).date())

    def test_one_failing_due_cancellation_does_not_stop_the_batch(self):
        first = activate_paid_subscription(tenant=self.tenant, billing_customer=self.customer, actor=self.admin)
        other_tenant, _ = _make_platform_tenant_pair(2340)
        second = activate_paid_subscription(tenant=other_tenant, billing_customer=self.customer, actor=self.admin)
        yesterday = timezone.localdate() - timedelta(days=1)
        ServiceSubscription.objects.filter(pk__in=[first.pk, second.pk]).update(
            scheduled_cancellation_date=yesterday, period_start=timezone.localdate() + timedelta(days=5),
        )
        real_deactivate = deactivate_service_subscription

        def flaky(*, subscription, **kwargs):
            if subscription.pk == first.pk:
                raise SubscriptionManagementConflict("simulated_conflict", "تعارض محاكى")
            return real_deactivate(subscription=subscription, **kwargs)

        with patch("platform_ops.services.deactivate_service_subscription", side_effect=flaky):
            result = apply_due_subscription_cancellations()
        self.assertEqual(result["applied_subscription_ids"], [second.pk])
        self.assertEqual(result["failed"], [{"subscription_id": first.pk, "code": "simulated_conflict"}])
        first.refresh_from_db()
        self.assertEqual(first.status, ServiceSubscription.Status.ACTIVE)

    def test_due_cancellation_waits_until_the_cycle_holding_the_last_service_day_is_billed(self):
        """تشغيلٌ محصور بشركة أخرى أو خطأ إعداد لا يُسقط فاتورة الدورة الأخيرة بإلغاءٍ مبكر."""
        subscription = activate_paid_subscription(tenant=self.tenant, billing_customer=self.customer, actor=self.admin)
        subscription.period_start = date(2026, 1, 1)
        subscription.period_end = date(2026, 1, 31)
        subscription.scheduled_cancellation_date = date(2026, 1, 31)
        subscription.cancellation_reason = "نهاية الدورة"
        subscription.save(update_fields=[
            "period_start", "period_end", "scheduled_cancellation_date", "cancellation_reason",
        ])
        first_of_february = timezone.make_aware(datetime(2026, 2, 1, 6, 0))

        unbilled = apply_due_subscription_cancellations(now=first_of_february)
        self.assertEqual(unbilled["applied_count"], 0)
        self.assertEqual(unbilled["awaiting_final_billing_subscription_ids"], [subscription.pk])
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, ServiceSubscription.Status.ACTIVE)

        # الفوترة الناجحة لدورة يناير تنقل الدورة إلى فبراير — عندها فقط يُطبَّق الإلغاء.
        ServiceSubscription.objects.filter(pk=subscription.pk).update(
            period_start=date(2026, 2, 1), period_end=date(2026, 2, 28),
        )
        billed = apply_due_subscription_cancellations(now=first_of_february)
        self.assertEqual(billed["applied_subscription_ids"], [subscription.pk])
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, ServiceSubscription.Status.CANCELLED)

    def test_trial_not_billed_by_preflight(self):
        subscription = start_service_trial(tenant=self.tenant, actor=self.admin)
        err = billing_preflight(
            subscription=subscription,
            period_start=timezone.localdate(),
            period_end=timezone.localdate() + timedelta(days=30),
            fixed_fee_product_id=1,
        )
        self.assertIsNotNone(err)
        self.assertEqual(err.code, "subscription_in_trial")

    # ── عميل الفوترة ──────────────────────────────────────────────
    def test_billing_customer_must_come_from_the_policy_billing_tenant(self):
        with self.assertRaises(BillingConfigurationError) as ctx:
            activate_paid_subscription(tenant=self.tenant, billing_customer=self.same_tenant_customer, actor=self.admin)
        self.assertEqual(ctx.exception.code, "billing_customer_same_tenant")

        with self.assertRaises(BillingConfigurationError) as ctx:
            activate_paid_subscription(tenant=self.tenant, billing_customer=self.unrelated_customer, actor=self.admin)
        self.assertEqual(ctx.exception.code, "billing_customer_wrong_platform_tenant")

        accepted = activate_paid_subscription(tenant=self.tenant, billing_customer=self.customer, actor=self.admin)
        self.assertEqual(accepted.billing_customer_id, self.customer.pk)

        with self.assertRaises(BillingConfigurationError):
            update_subscription_commercial_settings(subscription=accepted, billing_customer=self.same_tenant_customer)

    def test_customer_search_cannot_leak_another_tenant(self):
        matches = search_platform_billing_customers(query="Customer")
        self.assertIn(self.customer, list(matches))
        self.assertNotIn(self.unrelated_customer, list(matches))
        self.assertNotIn(self.same_tenant_customer, list(matches))

    def test_settings_event_records_non_pii_before_and_after_values(self):
        subscription = activate_paid_subscription(tenant=self.tenant, billing_customer=self.customer, actor=self.admin)
        update_subscription_commercial_settings(
            subscription=subscription,
            actor=self.admin,
            plan="enterprise",
            monthly_fee=Decimal("420.00"),
            included_quota=420,
            overage_unit_price=Decimal("2.50"),
            billing_customer=self.second_customer,
            reason="تفاوض خاص مع الشركة",
        )
        event = ServiceSubscriptionEvent.objects.get(
            subscription=subscription,
            action=ServiceSubscriptionEvent.Action.SETTINGS_UPDATED,
        )
        self.assertEqual(event.reason, "تفاوض خاص مع الشركة")
        self.assertEqual(event.details["changes"]["plan"], {"before": "standard", "after": "enterprise"})
        self.assertEqual(event.details["changes"]["monthly_fee"], {"before": "300.00", "after": "420.00"})
        self.assertEqual(
            event.details["changes"]["billing_customer"],
            {"before": self.customer.pk, "after": self.second_customer.pk},
        )

    # ── التفعيل المدفوع يلزمه عميل فوترة (لا سجلّ جزئي) ─────────────────
    def test_paid_activation_and_trial_conversion_require_a_billing_customer(self):
        with self.assertRaises(BillingConfigurationError) as ctx:
            activate_paid_subscription(tenant=self.tenant, actor=self.admin)
        self.assertEqual(ctx.exception.code, "billing_customer_required")
        self.assertFalse(ServiceSubscription.objects.filter(tenant=self.tenant).exists())

        trial = start_service_trial(tenant=self.tenant, actor=self.admin)
        self.assertIsNone(trial.billing_customer_id)
        with self.assertRaises(BillingConfigurationError) as ctx:
            activate_paid_subscription(tenant=self.tenant, actor=self.admin)
        self.assertEqual(ctx.exception.code, "billing_customer_required")
        trial.refresh_from_db()
        self.assertEqual(trial.status, ServiceSubscription.Status.TRIAL)

    def test_plan_is_chosen_at_activation_and_defaults_to_standard(self):
        chosen = activate_paid_subscription(
            tenant=self.tenant, billing_customer=self.customer, plan="enterprise", actor=self.admin,
        )
        self.assertEqual(chosen.plan, "enterprise")
        other_tenant, _ = _make_platform_tenant_pair(2320)
        default = activate_paid_subscription(tenant=other_tenant, billing_customer=self.customer, actor=self.admin)
        self.assertEqual(default.plan, "standard")

    def test_paid_subscription_customer_cannot_be_cleared_but_plan_only_change_skips_customer_validation(self):
        subscription = activate_paid_subscription(tenant=self.tenant, billing_customer=self.customer, actor=self.admin)
        with self.assertRaises(SubscriptionManagementError) as ctx:
            update_subscription_commercial_settings(subscription=subscription, billing_customer=None)
        self.assertEqual(ctx.exception.code, "billing_customer_required")

        # عميلٌ قديم من خارج شركة الفوترة الملتقطة (بيانات سابقة للقاعدة) لا يمنع تعديل الباقة وحدها.
        ServiceSubscription.objects.filter(pk=subscription.pk).update(billing_customer=self.unrelated_customer)
        updated = update_subscription_commercial_settings(subscription=subscription, plan="pilot", reason="ترقية")
        self.assertEqual(updated.plan, "pilot")
        self.assertEqual(updated.billing_customer_id, self.unrelated_customer.pk)

    def test_trial_conversion_records_the_scheduled_cancellation_it_clears(self):
        trial = start_service_trial(tenant=self.tenant, actor=self.admin)
        scheduled = schedule_service_subscription_cancellation(subscription=trial, reason="لن نكمل", actor=self.admin)
        scheduled_date = scheduled.scheduled_cancellation_date
        converted = activate_paid_subscription(tenant=self.tenant, billing_customer=self.customer, actor=self.admin)
        self.assertIsNone(converted.scheduled_cancellation_date)
        event = ServiceSubscriptionEvent.objects.get(
            subscription=converted, action=ServiceSubscriptionEvent.Action.TRIAL_CONVERTED,
        )
        self.assertEqual(event.details["cleared_scheduled_cancellation_date"], scheduled_date.isoformat())


class SubscriptionBillingCommandOrderTests(TestCase):
    def test_command_bills_before_applying_due_cancellations_and_dry_run_does_neither(self):
        result = {"billed_count": 1, "already_billed_count": 0, "skipped_count": 0, "error_count": 0,
                  "billed": [], "already_billed": [], "skipped": [], "errors": []}
        call_order = []
        with patch(
            "platform_ops.management.commands.bill_service_subscriptions.bill_subscriptions_for_period",
            side_effect=lambda **kwargs: call_order.append("bill") or result,
        ) as bill, patch(
            "platform_ops.management.commands.bill_service_subscriptions.apply_due_subscription_cancellations",
            side_effect=lambda: call_order.append("cancel") or {
                "applied_count": 1, "applied_subscription_ids": [1], "awaiting_final_billing_subscription_ids": [],
                "failed": [],
            },
        ) as cancel:
            call_command("bill_service_subscriptions", period="2026-01", fixed_fee_product_id=1)
            self.assertEqual(call_order, ["bill", "cancel"])
            call_command("bill_service_subscriptions", period="2026-01", fixed_fee_product_id=1, dry_run=True)
            self.assertEqual(bill.call_count, 1)
            self.assertEqual(cancel.call_count, 1)


class SubscriptionManagementApiTests(TestCase):
    def setUp(self):
        _activate_unit_catalog()
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            username="api_admin", email="api_admin@example.test", password="x",
        )
        self.staff_user = User.objects.create_user(
            username="api_staff", email="api_staff@example.test", password="x",
        )
        PlatformEmployee.objects.create(
            user=self.staff_user, specialty="data_entry", status=PlatformEmployee.Status.ACTIVE,
        )
        self.plain_user = User.objects.create_user(
            username="api_plain", email="api_plain@example.test", password="x",
        )
        self.tenant, self.platform_tenant = _make_platform_tenant_pair(2400)
        self.customer = Partner.objects.create(
            tenant=self.platform_tenant, name="Api Billing Customer", partner_type="Customer",
        )
        draft = create_subscription_policy_draft(billing_tenant=self.platform_tenant, fixed_fee_product=_service_product(self.platform_tenant))
        self.policy = activate_subscription_policy(policy=draft, actor=self.admin, change_reason="إطلاق")

    def _auth(self, user):
        self.client.force_authenticate(user=user)

    def test_non_superadmin_including_platform_staff_gets_403_on_every_subscription_and_policy_route(self):
        subscription = start_service_trial(tenant=self.tenant, actor=self.admin)
        subscriptions = "/api/platform/ops/subscriptions"
        policies = "/api/platform/ops/subscription-policies"
        endpoints = [
            ("get", f"{subscriptions}/"),
            ("get", f"{subscriptions}/{subscription.pk}/"),
            ("post", f"{subscriptions}/start-trial/"),
            ("post", f"{subscriptions}/activate-paid/"),
            ("post", f"{subscriptions}/{subscription.pk}/activate-paid/"),
            ("post", f"{subscriptions}/{subscription.pk}/suspend/"),
            ("post", f"{subscriptions}/{subscription.pk}/resume/"),
            ("post", f"{subscriptions}/{subscription.pk}/cancel/"),
            ("post", f"{subscriptions}/{subscription.pk}/withdraw-cancellation/"),
            ("post", f"{subscriptions}/{subscription.pk}/update-settings/"),
            ("get", f"{subscriptions}/{subscription.pk}/events/"),
            ("get", f"{subscriptions}/billing-customers/"),
            ("get", f"{policies}/"),
            ("get", f"{policies}/{self.policy.pk}/"),
            ("post", f"{policies}/draft/"),
            ("post", f"{policies}/{self.policy.pk}/update-draft/"),
            ("post", f"{policies}/{self.policy.pk}/clone/"),
            ("post", f"{policies}/{self.policy.pk}/preview/"),
            ("get", f"{policies}/{self.policy.pk}/billing-products/"),
            ("post", f"{policies}/{self.policy.pk}/activate/"),
        ]
        # كلُّ مسارٍ مسجَّل في الموجّهين مذكورٌ هنا — مسارٌ جديد بلا حارس يُسقط هذا العدّ.
        from platform_ops.views import ServiceSubscriptionViewSet, SubscriptionPolicyViewSet

        registered_actions = {
            viewset: len(viewset.get_extra_actions()) + 2  # list + retrieve
            for viewset in (ServiceSubscriptionViewSet, SubscriptionPolicyViewSet)
        }
        self.assertEqual(sum(registered_actions.values()), len(endpoints))

        company_member = User.objects.create_user(
            username="api_company_member", email="api_company_member@example.test", password="x",
        )
        UserCompanyMembership.objects.create(user=company_member, tenant=self.tenant, role="manager")
        for user in (self.staff_user, self.plain_user, company_member):
            self._auth(user)
            for method, url in endpoints:
                with self.subTest(user=user.username, method=method, url=url):
                    response = getattr(self.client, method)(url, {}, format="json")
                    self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, ServiceSubscription.Status.TRIAL)

    def test_update_settings_returns_400_with_code_for_invalid_customer_and_200_for_plan_only_change(self):
        self._auth(self.admin)
        subscription = activate_paid_subscription(tenant=self.tenant, billing_customer=self.customer, actor=self.admin)
        same_tenant_customer = Partner.objects.create(tenant=self.tenant, name="Own Customer", partner_type="Customer")
        url = f"/api/platform/ops/subscriptions/{subscription.pk}/update-settings/"

        refused = self.client.post(url, {"billing_customer": same_tenant_customer.pk}, format="json")
        self.assertEqual(refused.status_code, status.HTTP_400_BAD_REQUEST, refused.data)
        self.assertEqual(refused.data["code"], "billing_customer_same_tenant")

        # صفٌّ يحمل عميلاً قديماً غير صالح للقاعدة الجديدة: تعديل الباقة وحده لا يعيد فحصه.
        ServiceSubscription.objects.filter(pk=subscription.pk).update(billing_customer=same_tenant_customer)
        plan_only = self.client.post(url, {"plan": "pilot", "reason": "ترقية"}, format="json")
        self.assertEqual(plan_only.status_code, status.HTTP_200_OK, plan_only.data)
        self.assertEqual(plan_only.data["plan"], "pilot")

    def test_billing_customer_search_for_a_subscription_uses_its_snapshotted_billing_tenant(self):
        self._auth(self.admin)
        trial = start_service_trial(tenant=self.tenant, actor=self.admin)
        new_billing_tenant = Tenant.objects.create(TenantID=2430, CompanyName="Newer Billing Tenant")
        Partner.objects.create(tenant=new_billing_tenant, name="Newer Customer", partner_type="Customer")
        newer = create_subscription_policy_draft(billing_tenant=new_billing_tenant, fixed_fee_product=_service_product(new_billing_tenant))
        activate_subscription_policy(policy=newer, actor=self.admin, change_reason="نقل الفوترة")

        policy_scoped = self.client.get("/api/platform/ops/subscriptions/billing-customers/")
        self.assertEqual([row["name"] for row in policy_scoped.data], ["Newer Customer"])

        scoped = self.client.get(f"/api/platform/ops/subscriptions/billing-customers/?subscription={trial.pk}")
        self.assertEqual(scoped.status_code, status.HTTP_200_OK)
        offered_ids = [row["id"] for row in scoped.data]
        self.assertEqual(offered_ids, [self.customer.pk])

        converted = self.client.post(
            f"/api/platform/ops/subscriptions/{trial.pk}/activate-paid/",
            {"billing_customer": offered_ids[0]},
            format="json",
        )
        self.assertEqual(converted.status_code, status.HTTP_200_OK, converted.data)

        invalid = self.client.get("/api/platform/ops/subscriptions/billing-customers/?subscription=abc")
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)

    def test_billing_customer_search_follows_the_plan_scope_that_activation_will_validate(self):
        _, premium_billing = _make_platform_tenant_pair(2420)
        premium_customer = Partner.objects.create(
            tenant=premium_billing, name="Premium Billing Customer", partner_type="Customer",
        )
        premium_draft = create_subscription_policy_draft(
            plan="premium", billing_tenant=premium_billing, fixed_fee_product=_service_product(premium_billing),
        )
        activate_subscription_policy(policy=premium_draft, actor=self.admin, change_reason="خطة مميزة")
        self._auth(self.admin)

        scoped = self.client.get("/api/platform/ops/subscriptions/billing-customers/", {"plan": "premium"})
        self.assertEqual(scoped.status_code, status.HTTP_200_OK)
        # بلا نطاق الخطة كان المنتقي يعرض عملاء شركةٍ يرفضها التفعيل بعد سطرين.
        self.assertEqual([row["id"] for row in scoped.json()], [premium_customer.pk])

        general = self.client.get("/api/platform/ops/subscriptions/billing-customers/")
        self.assertEqual([row["id"] for row in general.json()], [self.customer.pk])

    def test_unknown_subscription_status_filter_is_refused_not_read_as_no_rows(self):
        start_service_trial(tenant=self.tenant, actor=self.admin)
        self._auth(self.admin)

        typo = self.client.get("/api/platform/ops/subscriptions/", {"status": "trail"})
        self.assertEqual(typo.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("status", typo.json())

        known = self.client.get("/api/platform/ops/subscriptions/", {"status": "trial"})
        self.assertEqual(known.status_code, status.HTTP_200_OK)

    def test_policy_billing_products_endpoint_lists_service_products_of_its_billing_tenant_only(self):
        self._auth(self.admin)
        in_scope = _service_product(self.platform_tenant, "SUB-SEARCH")
        Product.objects.create(tenant=self.platform_tenant, sku="SUB-PHYS", name_ar="سلعة", is_service=False)
        _service_product(self.tenant, "SUB-OTHER")
        response = self.client.get(f"/api/platform/ops/subscription-policies/{self.policy.pk}/billing-products/?q=SUB-")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        skus = {row["sku"] for row in response.data}
        self.assertIn(in_scope.sku, skus)
        self.assertNotIn("SUB-PHYS", skus)
        self.assertNotIn("SUB-OTHER", skus)

    def test_policy_activation_endpoint_accepts_a_future_effective_date(self):
        self._auth(self.admin)
        draft = create_subscription_policy_draft(
            billing_tenant=self.platform_tenant, fixed_fee_product=_service_product(self.platform_tenant),
        )
        starts = (timezone.now() + timedelta(days=3)).replace(microsecond=0)
        response = self.client.post(
            f"/api/platform/ops/subscription-policies/{draft.pk}/activate/",
            {"change_reason": "مجدولة", "effective_from": starts.isoformat()},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["effective_state"], "scheduled")

    def test_new_paid_activation_requires_customer_and_accepts_plan(self):
        self._auth(self.admin)
        url = "/api/platform/ops/subscriptions/activate-paid/"
        missing = self.client.post(url, {"tenant": self.tenant.pk}, format="json")
        self.assertEqual(missing.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(ServiceSubscription.objects.filter(tenant=self.tenant).exists())

        created = self.client.post(
            url, {"tenant": self.tenant.pk, "billing_customer": self.customer.pk, "plan": "enterprise"}, format="json",
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.data)
        self.assertEqual(created.data["plan"], "enterprise")

    def test_policy_draft_endpoint_needs_only_the_billing_tenant_and_audits_with_the_header_id(self):
        self._auth(self.admin)
        response = self.client.post(
            "/api/platform/ops/subscription-policies/draft/",
            {"billing_tenant": self.platform_tenant.pk},
            format="json",
            HTTP_X_CORRELATION_ID="policy-draft-1",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        self.assertEqual(response.data["monthly_fee"], "300.00")
        self.assertEqual(response.data["included_quota"], 300)
        event = ServiceSubscriptionPolicyEvent.objects.get(policy_id=response.data["id"])
        self.assertEqual((event.action, event.correlation_id), ("created", "policy-draft-1"))

        preview = self.client.post(
            f"/api/platform/ops/subscription-policies/{response.data['id']}/preview/", {}, format="json",
        )
        self.assertEqual(preview.status_code, status.HTTP_200_OK)
        # المسودة الجديدة بلا صنف رسم بعد — الفرق الوحيد عن النسخة السارية.
        self.assertEqual(
            preview.data["diff"],
            {"fixed_fee_product_id": {"active": self.policy.fixed_fee_product_id, "draft": None}},
        )

    def test_subscription_list_uses_a_constant_query_count_for_active_engagement_counts(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        self._auth(self.admin)
        activate_paid_subscription(tenant=self.tenant, billing_customer=self.customer, actor=self.admin)

        def list_query_count():
            with CaptureQueriesContext(connection) as queries:
                response = self.client.get("/api/platform/ops/subscriptions/")
            self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
            return len(queries)

        one_subscription_query_count = list_query_count()
        for tenant_id in (2410, 2411, 2412):
            tenant = Tenant.objects.create(TenantID=tenant_id, CompanyName=f"List Query Tenant {tenant_id}")
            activate_paid_subscription(tenant=tenant, billing_customer=self.customer, actor=self.admin)

        many_subscriptions_query_count = list_query_count()
        self.assertEqual(many_subscriptions_query_count, one_subscription_query_count)
        self.assertLessEqual(many_subscriptions_query_count, 1)

    def test_full_lifecycle_through_the_api(self):
        self._auth(self.admin)
        started = self.client.post(
            "/api/platform/ops/subscriptions/start-trial/", {"tenant": self.tenant.pk}, format="json",
        )
        self.assertEqual(started.status_code, status.HTTP_201_CREATED, started.data)
        subscription_id = started.data["id"]
        self.assertEqual(started.data["status"], ServiceSubscription.Status.TRIAL)
        self.assertTrue(started.data["is_trial"])

        settings_resp = self.client.post(
            f"/api/platform/ops/subscriptions/{subscription_id}/update-settings/",
            {"plan": "pilot", "reason": "تسمية الباقة التجريبية"},
            format="json",
        )
        self.assertEqual(settings_resp.status_code, status.HTTP_200_OK, settings_resp.data)

        suspended = self.client.post(
            f"/api/platform/ops/subscriptions/{subscription_id}/suspend/",
            {"reason": "تأخر سداد"},
            format="json",
        )
        self.assertEqual(suspended.status_code, status.HTTP_200_OK, suspended.data)
        self.assertEqual(suspended.data["status"], ServiceSubscription.Status.SUSPENDED)

        resumed = self.client.post(f"/api/platform/ops/subscriptions/{subscription_id}/resume/", {}, format="json")
        self.assertEqual(resumed.status_code, status.HTTP_200_OK, resumed.data)
        self.assertEqual(resumed.data["status"], ServiceSubscription.Status.TRIAL)

        without_customer = self.client.post(
            f"/api/platform/ops/subscriptions/{subscription_id}/activate-paid/", {}, format="json",
        )
        self.assertEqual(without_customer.status_code, status.HTTP_400_BAD_REQUEST)

        converted = self.client.post(
            f"/api/platform/ops/subscriptions/{subscription_id}/activate-paid/",
            {"billing_customer": self.customer.pk},
            format="json",
        )
        self.assertEqual(converted.status_code, status.HTTP_200_OK, converted.data)
        self.assertEqual(converted.data["status"], ServiceSubscription.Status.ACTIVE)

        cancelled = self.client.post(
            f"/api/platform/ops/subscriptions/{subscription_id}/cancel/",
            {"reason": "انتهى pilot", "immediate": True},
            format="json",
        )
        self.assertEqual(cancelled.status_code, status.HTTP_200_OK, cancelled.data)
        self.assertEqual(cancelled.data["status"], ServiceSubscription.Status.CANCELLED)

        events = self.client.get(f"/api/platform/ops/subscriptions/{subscription_id}/events/")
        self.assertEqual(events.status_code, status.HTTP_200_OK)
        actions = [row["action"] for row in events.data]
        self.assertIn("trial_started", actions)
        self.assertIn("cancelled", actions)

    def test_correlation_id_header_is_used_when_valid_and_generated_otherwise(self):
        self._auth(self.admin)
        response = self.client.post(
            "/api/platform/ops/subscriptions/start-trial/",
            {"tenant": self.tenant.pk},
            format="json",
            HTTP_X_CORRELATION_ID="frontend-abc123",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        event = ServiceSubscriptionEvent.objects.get(subscription_id=response.data["id"])
        self.assertEqual(event.correlation_id, "frontend-abc123")

        second_tenant, _ = _make_platform_tenant_pair(2410)
        unsafe_response = self.client.post(
            "/api/platform/ops/subscriptions/start-trial/",
            {"tenant": second_tenant.pk},
            format="json",
            HTTP_X_CORRELATION_ID="has spaces/slash",
        )
        self.assertEqual(unsafe_response.status_code, status.HTTP_201_CREATED)
        generated_event = ServiceSubscriptionEvent.objects.get(subscription_id=unsafe_response.data["id"])
        self.assertNotEqual(generated_event.correlation_id, "has spaces/slash")
        self.assertTrue(generated_event.correlation_id)

    def test_billing_customers_search_endpoint_scopes_to_policy_billing_tenant(self):
        in_tenant = Partner.objects.create(tenant=self.platform_tenant, name="Zed Customer", partner_type="Customer")
        outside_tenant = Tenant.objects.create(TenantID=2420, CompanyName="Outside Co")
        Partner.objects.create(tenant=outside_tenant, name="Zed Outsider", partner_type="Customer")

        self._auth(self.admin)
        response = self.client.get("/api/platform/ops/subscriptions/billing-customers/?q=Zed")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        ids = [row["id"] for row in response.data]
        self.assertIn(in_tenant.pk, ids)
        self.assertEqual(len(ids), 1)

    def test_policy_preview_endpoint_returns_diff_and_activation_requires_reason(self):
        self._auth(self.admin)
        draft = self.client.post(
            "/api/platform/ops/subscription-policies/draft/",
            {
                "billing_tenant": self.platform_tenant.pk,
                "monthly_fee": "350.00",
                "fixed_fee_product": _service_product(self.platform_tenant).pk,
            },
            format="json",
        )
        self.assertEqual(draft.status_code, status.HTTP_201_CREATED, draft.data)
        policy_id = draft.data["id"]

        preview = self.client.post(f"/api/platform/ops/subscription-policies/{policy_id}/preview/", {}, format="json")
        self.assertEqual(preview.status_code, status.HTTP_200_OK)
        self.assertIn("monthly_fee", preview.data["diff"])
        self.assertIsNotNone(preview.data["active"])

        missing_reason = self.client.post(f"/api/platform/ops/subscription-policies/{policy_id}/activate/", {}, format="json")
        self.assertEqual(missing_reason.status_code, status.HTTP_400_BAD_REQUEST)

        activated = self.client.post(
            f"/api/platform/ops/subscription-policies/{policy_id}/activate/",
            {"change_reason": "رفع السعر التجريبي"},
            format="json",
        )
        self.assertEqual(activated.status_code, status.HTTP_200_OK, activated.data)


class SubscriptionAssignmentEligibilityApiTests(TestCase):
    """أهلية الإسناد ولوحة القيادة تُشتق من `is_service_active` وحده."""

    def setUp(self):
        _activate_unit_catalog()
        self.admin = User.objects.create_superuser(
            username="eligibility_admin", email="eligibility_admin@example.test", password="x",
        )
        self.employee_user = User.objects.create_user(
            username="eligibility_employee", email="eligibility_employee@example.test", password="x",
        )
        self.employee = PlatformEmployee.objects.create(
            user=self.employee_user, specialty="data_entry", capacity_target=10,
            status=PlatformEmployee.Status.ACTIVE,
        )
        self.tenant, self.platform_tenant = _make_platform_tenant_pair(2500)
        self.customer = Partner.objects.create(
            tenant=self.platform_tenant, name="Eligibility Customer", partner_type="Customer",
        )
        draft = create_subscription_policy_draft(billing_tenant=self.platform_tenant, fixed_fee_product=_service_product(self.platform_tenant))
        activate_subscription_policy(policy=draft, actor=self.admin, change_reason="إطلاق")

    def test_tenant_without_any_subscription_is_ineligible_and_assignment_is_refused(self):
        self.assertFalse(is_service_active(self.tenant))
        with self.assertRaises(EngagementError) as ctx:
            assign_platform_employee(employee=self.employee, tenant=self.tenant)
        self.assertEqual(ctx.exception.code, "subscription_not_active")

    def test_cancelled_or_suspended_tenant_is_ineligible_for_assignment(self):
        subscription = activate_paid_subscription(tenant=self.tenant, billing_customer=self.customer, actor=self.admin)
        suspend_service_subscription(subscription=subscription, reason="إيقاف", actor=self.admin)
        self.assertFalse(is_service_active(self.tenant))

        resume_service_subscription(subscription=subscription, actor=self.admin)
        deactivate_service_subscription(
            subscription=subscription, new_status=ServiceSubscription.Status.CANCELLED, reason="نهائي",
        )
        self.assertFalse(is_service_active(self.tenant))
        with self.assertRaises(EngagementError):
            assign_platform_employee(employee=self.employee, tenant=self.tenant)

    def test_trial_tenant_is_eligible_for_assignment(self):
        start_service_trial(tenant=self.tenant, actor=self.admin)
        _approve_baseline(self.tenant, actor=self.admin)
        engagement = assign_platform_employee(employee=self.employee, tenant=self.tenant)
        self.assertEqual(engagement.status, Engagement.Status.ACTIVE)


class ServiceEligibilityInternalSurfacesTests(TestCase):
    """§١: أوامر العمل وصحة الشركة لا تدخلها شركةٌ بلا اشتراكٍ مؤهَّل — للمدير والموظف."""

    def setUp(self):
        _activate_unit_catalog()
        self.client = APIClient()
        self.manager = User.objects.create_superuser(
            username="surfaces_manager", email="surfaces_manager@example.test", password="x",
        )
        self.employee_user = User.objects.create_user(
            username="surfaces_employee", email="surfaces_employee@example.test", password="x",
        )
        self.employee = PlatformEmployee.objects.create(
            user=self.employee_user, specialty="data_entry", capacity_target=10,
            status=PlatformEmployee.Status.ACTIVE,
        )
        billing_tenant = Tenant.objects.create(TenantID=2700, CompanyName="Surfaces Billing Tenant")
        customer = Partner.objects.create(tenant=billing_tenant, name="Surfaces Customer", partner_type="Customer")
        draft = create_subscription_policy_draft(billing_tenant=billing_tenant, fixed_fee_product=_service_product(billing_tenant))
        activate_subscription_policy(policy=draft, actor=self.manager, change_reason="اختبار الأسطح")

        self.active = Tenant.objects.create(TenantID=2701, CompanyName="Surfaces Active")
        self.expired_trial = Tenant.objects.create(TenantID=2702, CompanyName="Surfaces Expired Trial")
        self.cancelled = Tenant.objects.create(TenantID=2703, CompanyName="Surfaces Cancelled")
        self.unassigned_active = Tenant.objects.create(TenantID=2704, CompanyName="Surfaces Unassigned Active")

        activate_paid_subscription(tenant=self.active, billing_customer=customer, actor=self.manager)
        activate_paid_subscription(tenant=self.unassigned_active, billing_customer=customer, actor=self.manager)
        expired = start_service_trial(tenant=self.expired_trial, actor=self.manager)
        cancelled = activate_paid_subscription(tenant=self.cancelled, billing_customer=customer, actor=self.manager)

        for tenant in (self.active, self.expired_trial, self.cancelled):
            _approve_baseline(tenant, actor=self.manager)
            assign_platform_employee(employee=self.employee, tenant=tenant, assigned_by=self.manager)
            WorkOrder.objects.create(
                tenant=tenant, assignee=self.employee, title=f"WO {tenant.CompanyName}",
                status=WorkOrder.Status.DATA_ENTRY,
            )
        # التجربة المنتهية تُبقي ارتباطها نشطاً — وهذا بالضبط ما يجب ألا يفتح الأسطح.
        expired.trial_ends_at = timezone.now() - timedelta(hours=1)
        expired.save(update_fields=["trial_ends_at"])
        deactivate_service_subscription(
            subscription=cancelled, new_status=ServiceSubscription.Status.CANCELLED, reason="إنهاء",
        )

    def _work_order_tenants(self):
        response = self.client.get("/api/platform/ops/work-orders/")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        rows = response.data["results"] if isinstance(response.data, dict) else response.data
        return {row["tenant"] for row in rows}

    def test_ineligible_companies_are_absent_from_work_orders_and_health_for_both_roles(self):
        self.assertEqual(
            Engagement.objects.get(tenant=self.expired_trial, employee=self.employee).status,
            Engagement.Status.ACTIVE,
        )
        for user in (self.manager, self.employee_user):
            with self.subTest(user=user.username):
                self.client.force_authenticate(user=user)
                self.assertEqual(self._work_order_tenants(), {self.active.pk})
                for tenant in (self.expired_trial, self.cancelled):
                    health = self.client.get(f"/api/platform/ops/companies/{tenant.pk}/health/")
                    self.assertEqual(health.status_code, status.HTTP_404_NOT_FOUND)
                active_health = self.client.get(f"/api/platform/ops/companies/{self.active.pk}/health/")
                self.assertEqual(active_health.status_code, status.HTTP_200_OK)

    def test_employee_cannot_open_health_of_an_eligible_company_they_are_not_engaged_with(self):
        self.client.force_authenticate(user=self.employee_user)
        response = self.client.get(f"/api/platform/ops/companies/{self.unassigned_active.pk}/health/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        self.client.force_authenticate(user=self.manager)
        manager_view = self.client.get(f"/api/platform/ops/companies/{self.unassigned_active.pk}/health/")
        self.assertEqual(manager_view.status_code, status.HTTP_200_OK)


class SubscriptionDashboardEligibilityTests(TestCase):
    def setUp(self):
        _activate_unit_catalog()
        self.manager = User.objects.create_superuser(
            username="dashboard_eligibility_manager",
            email="dashboard_eligibility_manager@example.test",
            password="x",
        )
        self.employee_user = User.objects.create_user(
            username="dashboard_eligibility_employee",
            email="dashboard_eligibility_employee@example.test",
            password="x",
        )
        self.employee = PlatformEmployee.objects.create(
            user=self.employee_user,
            specialty="data_entry",
            capacity_target=10,
            status=PlatformEmployee.Status.ACTIVE,
        )
        self.billing_tenant = Tenant.objects.create(TenantID=2600, CompanyName="Dashboard Billing Tenant")
        self.customer = Partner.objects.create(
            tenant=self.billing_tenant, name="Dashboard Customer", partner_type="Customer",
        )
        draft = create_subscription_policy_draft(billing_tenant=self.billing_tenant, fixed_fee_product=_service_product(self.billing_tenant))
        activate_subscription_policy(policy=draft, actor=self.manager, change_reason="اختبار لوحة القيادة")

        self.no_subscription = Tenant.objects.create(TenantID=2601, CompanyName="No Subscription")
        self.suspended = Tenant.objects.create(TenantID=2602, CompanyName="Suspended Subscription")
        self.cancelled = Tenant.objects.create(TenantID=2603, CompanyName="Cancelled Subscription")
        self.expired_trial = Tenant.objects.create(TenantID=2604, CompanyName="Expired Trial")
        self.valid_trial = Tenant.objects.create(TenantID=2605, CompanyName="Valid Trial")
        self.active = Tenant.objects.create(TenantID=2606, CompanyName="Active Subscription")

        suspended_subscription = activate_paid_subscription(tenant=self.suspended, billing_customer=self.customer, actor=self.manager)
        suspend_service_subscription(subscription=suspended_subscription, reason="تعليق اختبار", actor=self.manager)
        cancelled_subscription = activate_paid_subscription(tenant=self.cancelled, billing_customer=self.customer, actor=self.manager)
        deactivate_service_subscription(
            subscription=cancelled_subscription,
            new_status=ServiceSubscription.Status.CANCELLED,
            reason="إلغاء اختبار",
            actor=self.manager,
        )

        expired_subscription = start_service_trial(tenant=self.expired_trial, actor=self.manager)
        _approve_baseline(self.expired_trial, actor=self.manager)
        assign_platform_employee(employee=self.employee, tenant=self.expired_trial, assigned_by=self.manager)
        WorkOrder.objects.create(
            tenant=self.expired_trial,
            assignee=self.employee,
            title="Expired trial overdue work order",
            status=WorkOrder.Status.DATA_ENTRY,
            deadline_at=timezone.now() - timedelta(hours=2),
        )
        expired_subscription.trial_ends_at = timezone.now() - timedelta(hours=1)
        expired_subscription.save(update_fields=["trial_ends_at"])

        start_service_trial(tenant=self.valid_trial, actor=self.manager)
        activate_paid_subscription(tenant=self.active, billing_customer=self.customer, actor=self.manager)
        _approve_baseline(self.valid_trial, actor=self.manager)
        _approve_baseline(self.active, actor=self.manager)
        assign_platform_employee(employee=self.employee, tenant=self.valid_trial, assigned_by=self.manager)
        assign_platform_employee(employee=self.employee, tenant=self.active, assigned_by=self.manager)

    def test_dashboard_includes_only_eligible_service_companies_for_manager_and_employee(self):
        now = timezone.now()
        hidden_tenants = {
            self.no_subscription.pk,
            self.suspended.pk,
            self.cancelled.pk,
            self.expired_trial.pk,
        }
        expected_tenants = {self.valid_trial.pk, self.active.pk}

        for user in (self.manager, self.employee_user):
            with self.subTest(user=user.username):
                summary = get_platform_dashboard_summary(user=user, now=now)
                company_ids = {company["id"] for company in summary["companies"]}
                self.assertTrue(expected_tenants.issubset(company_ids))
                self.assertTrue(hidden_tenants.isdisjoint(company_ids))

                employee_cards = [card for card in summary["employees"] if card["id"] == self.employee.pk]
                self.assertEqual(len(employee_cards), 1)
                employee_card = employee_cards[0]
                employee_company_ids = {company["id"] for company in employee_card["companies"]}
                self.assertTrue(expected_tenants.issubset(employee_company_ids))
                self.assertTrue(hidden_tenants.isdisjoint(employee_company_ids))
                self.assertEqual(employee_card["active_work_orders_count"], 0)
                self.assertEqual(employee_card["overdue_work_orders_count"], 0)

                anomaly_tenant_ids = {
                    anomaly["tenant_id"] for anomaly in summary["anomalies"] if anomaly["tenant_id"] is not None
                }
                self.assertTrue(hidden_tenants.isdisjoint(anomaly_tenant_ids))
                self.assertNotIn(
                    "critical_delay",
                    {anomaly["anomaly_type"] for anomaly in summary["anomalies"]},
                )


class SubscriptionFrontendContractTests(TestCase):
    def setUp(self):
        self.repo_root = Path(__file__).resolve().parents[2]
        self.source = (self.repo_root / "frontend_v2" / "services" / "platformOpsApi.ts").read_text(encoding="utf-8")

    def test_frontend_declares_the_lifecycle_contract(self):
        for name in (
            "ServiceSubscriptionRow",
            "SubscriptionPolicyRow",
            "listServiceSubscriptions",
            "startServiceTrial",
            "activatePaidSubscription",
            "suspendServiceSubscription",
            "resumeServiceSubscription",
            "cancelServiceSubscription",
            "withdrawScheduledCancellation",
            "updateSubscriptionSettings",
            "listSubscriptionEvents",
            "searchBillingCustomers",
            "listSubscriptionPolicies",
            "createSubscriptionPolicyDraft",
            "cloneSubscriptionPolicy",
            "previewSubscriptionPolicy",
            "activateSubscriptionPolicy",
        ):
            self.assertIn(name, self.source, name)
        for path in (
            "platform/ops/subscriptions/",
            "start-trial/",
            "activate-paid/",
            "platform/ops/subscription-policies/",
        ):
            self.assertIn(path, self.source, path)

    def test_status_labels_helper_follows_the_server_status_labels(self):
        helper = (self.repo_root / "frontend_v2" / "utils" / "platformSubscriptionManagement.ts").read_text(encoding="utf-8")
        match = re.search(r"SUBSCRIPTION_STATUS_LABEL[^=]*=\s*\{(.*?)\};", helper, re.DOTALL)
        self.assertIsNotNone(match, "لم يُعثر على SUBSCRIPTION_STATUS_LABEL.")
        frontend_labels = dict(re.findall(r'(\w+):\s*"([^"]+)"', match.group(1)))
        self.assertEqual(frontend_labels, dict(ServiceSubscription.Status.choices))

    def test_subscription_interfaces_and_status_unions_match_the_api_exactly(self):
        from platform_ops.tests.test_my_agent_frontend_contract import _interface_fields

        from platform_ops.serializers import (
            ServiceSubscriptionEventSerializer,
            ServiceSubscriptionSerializer,
            SubscriptionPolicySerializer,
        )

        interfaces = {
            "ServiceSubscriptionRow": ServiceSubscriptionSerializer,
            "SubscriptionPolicyRow": SubscriptionPolicySerializer,
            "ServiceSubscriptionEventRow": ServiceSubscriptionEventSerializer,
        }
        for interface, serializer in interfaces.items():
            self.assertEqual(
                _interface_fields(self.source, interface),
                set(serializer.Meta.fields),
                f"واجهة {interface} يجب أن تطابق حقول {serializer.__name__} تماماً.",
            )

        for type_name, choices in (
            ("ServiceSubscriptionStatus", ServiceSubscription.Status.values),
            ("SubscriptionPolicyStatus", ServiceSubscriptionPolicy.Status.values),
            ("SubscriptionPolicyEffectiveState", ["draft", "scheduled", "current", "retired"]),
        ):
            match = re.search(rf"export type {type_name} = ([^;]+);", self.source)
            self.assertIsNotNone(match, f"لم يعثر على union {type_name}.")
            frontend_choices = set(re.findall(r'"([^"]+)"', match.group(1)))
            self.assertEqual(frontend_choices, set(choices), f"خيارات {type_name} لا تطابق choices الخادم.")
