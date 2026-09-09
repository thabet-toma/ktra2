"""اختبارات طبقة الخدمات لعمليات المنصة (المرحلة الأولى).

تختبر السلوك الخارجي عبر طبقة الخدمات وحراس الصلاحيات:
- PlatformEmployee هوية صريحة (صف حقيقي أو ليس موظف منصة).
- is_service_active يعيد False لشركة بلا اشتراك، False للاشتراك المعلق/الملغى، وTrue فقط للنشط.
- IsPlatformOperationsStaff يقبل موظف المنصة حتى لو لم يكن superuser، ويرفض من لا صف له حتى لو كان superuser.
- موظف المنصة لا يُمنح IsPlatformAdmin.
"""
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from core.platform_admin_api import IsPlatformAdmin
from tenants.models import Tenant

from platform_ops.models import PlatformEmployee, ServiceSubscription
from platform_ops.permissions import (
    IsPlatformOperationsManager,
    IsPlatformOperationsStaff,
)
from platform_ops.services import is_platform_employee, is_service_active

User = get_user_model()


class PlatformEmployeeIdentityTest(TestCase):
    """اختبار صراحة هوية موظف المنصة وعدم استنتاجها من superuser."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.superuser_no_row = User.objects.create_superuser(
            username="super_no_pe",
            email="super_no_pe@platform.local",
            password="x",
        )
        self.regular_user_with_row = User.objects.create_user(
            username="staff_pe",
            email="staff_pe@platform.local",
            password="x",
        )
        self.employee = PlatformEmployee.objects.create(
            user=self.regular_user_with_row,
            specialty="data_entry",
            capacity_target=100,
            status=PlatformEmployee.Status.ACTIVE,
        )

    def test_superuser_without_row_is_not_platform_employee(self):
        """السوبر أدمن بلا صف ليس موظف منصة."""
        self.assertFalse(is_platform_employee(self.superuser_no_row))

        req = self.factory.get("/api/platform/ops/")
        req.user = self.superuser_no_row
        self.assertFalse(IsPlatformOperationsStaff().has_permission(req, None))

    def test_non_superuser_with_row_is_platform_employee(self):
        """المستخدم العادي مع صف PlatformEmployee هو موظف منصة."""
        self.assertTrue(is_platform_employee(self.regular_user_with_row))

        req = self.factory.get("/api/platform/ops/")
        req.user = self.regular_user_with_row
        self.assertTrue(IsPlatformOperationsStaff().has_permission(req, None))

    def test_platform_employee_is_not_granted_platform_admin(self):
        """قاعدة صارمة: موظف المنصة ليس سوبر أدمن ولا يملك IsPlatformAdmin."""
        req = self.factory.get("/api/platform/")
        req.user = self.regular_user_with_row
        self.assertFalse(IsPlatformAdmin().has_permission(req, None))

    def test_offboarded_employee_loses_active_staff_permission(self):
        """الموظف الذي انتهت خدمته (offboarded) يفقد صلاحية الموظف النشط."""
        self.employee.status = PlatformEmployee.Status.OFFBOARDED
        self.employee.save(update_fields=["status"])

        self.assertFalse(is_platform_employee(self.regular_user_with_row))

        req = self.factory.get("/api/platform/ops/")
        req.user = self.regular_user_with_row
        self.assertFalse(IsPlatformOperationsStaff().has_permission(req, None))

    def test_manager_permission_satisfies_superuser(self):
        """مدير العمليات متاح للسوبر أدمن."""
        req = self.factory.get("/api/platform/ops/")
        req.user = self.superuser_no_row
        self.assertTrue(IsPlatformOperationsManager().has_permission(req, None))

        req.user = self.regular_user_with_row
        self.assertFalse(IsPlatformOperationsManager().has_permission(req, None))


class ServiceSubscriptionActiveTest(TestCase):
    """اختبار خدمة is_service_active كبوابة للإسناد."""

    def setUp(self):
        self.tenant_no_sub = Tenant.objects.create(TenantID=951, CompanyName="No Sub Co")
        self.tenant_active = Tenant.objects.create(TenantID=952, CompanyName="Active Sub Co")
        self.tenant_suspended = Tenant.objects.create(TenantID=953, CompanyName="Suspended Co")
        self.tenant_cancelled = Tenant.objects.create(TenantID=954, CompanyName="Cancelled Co")

        ServiceSubscription.objects.create(
            tenant=self.tenant_active,
            status=ServiceSubscription.Status.ACTIVE,
            plan="growth",
            included_quota=500,
        )
        ServiceSubscription.objects.create(
            tenant=self.tenant_suspended,
            status=ServiceSubscription.Status.SUSPENDED,
            plan="growth",
            included_quota=500,
        )
        ServiceSubscription.objects.create(
            tenant=self.tenant_cancelled,
            status=ServiceSubscription.Status.CANCELLED,
            plan="growth",
            included_quota=500,
        )

    def test_tenant_without_subscription_returns_false(self):
        self.assertFalse(is_service_active(self.tenant_no_sub))
        self.assertFalse(is_service_active(self.tenant_no_sub.TenantID))

    def test_suspended_subscription_returns_false(self):
        self.assertFalse(is_service_active(self.tenant_suspended))

    def test_cancelled_subscription_returns_false(self):
        self.assertFalse(is_service_active(self.tenant_cancelled))

    def test_active_subscription_returns_true(self):
        self.assertTrue(is_service_active(self.tenant_active))
        self.assertTrue(is_service_active(self.tenant_active.TenantID))

    def test_none_tenant_returns_false(self):
        self.assertFalse(is_service_active(None))

    def test_a_company_cannot_hold_two_subscription_rows(self):
        """صفُّ خدمةٍ واحدٌ لكلّ شركة — والقاعدةُ تفرضه لا الاتّفاقُ الشفهيّ.

        اشتراكان لشركةٍ واحدة يجعلان الحدَّ والعدّادَ غامضين، فتقرأ الفوترةُ
        صفّاً عشوائياً. والفرادةُ هنا **غيرُ مشروطة** فتفرضها MySQL فعلاً.
        """
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ServiceSubscription.objects.create(
                    tenant=self.tenant_active,
                    status=ServiceSubscription.Status.CANCELLED,
                    plan="starter",
                )

    def test_reactivation_flips_the_same_row(self):
        """إعادةُ التفعيل تقلب حالةَ الصفّ نفسِه — لا تُنشئ صفّاً ثانياً."""
        subscription = self.tenant_cancelled.service_subscription
        subscription.status = ServiceSubscription.Status.ACTIVE
        subscription.save(update_fields=["status"])

        self.assertTrue(is_service_active(self.tenant_cancelled))
        self.assertEqual(
            ServiceSubscription.objects.filter(tenant=self.tenant_cancelled).count(), 1
        )
