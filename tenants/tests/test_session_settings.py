"""Per-company session idle timeout on TenantSettings.

يثبت أن مهلة الخمول (بالدقائق) تُحفَظ خادمياً لكل شركة (فلا ترجع للافتراضي عند
إعادة الدخول)، معزولة بين الشركات، ومقيّدة بنطاق معقول (5..1440 دقيقة).
"""
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth.models import User

from tenants.models import Tenant, UserCompanyMembership


class SessionSettingsTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant_a = Tenant.objects.create(
            TenantID=1, CompanyName="Company A", SubscriptionPlan="Enterprise", Status="Active")
        cls.tenant_b = Tenant.objects.create(
            TenantID=2, CompanyName="Company B", SubscriptionPlan="Enterprise", Status="Active")
        cls.user = User.objects.create_user(username="usera", password="password123")
        UserCompanyMembership.objects.create(
            user=cls.user, tenant=cls.tenant_a, role="manager", is_default=True)
        UserCompanyMembership.objects.create(
            user=cls.user, tenant=cls.tenant_b, role="manager")

    def test_default_idle_timeout_on_fresh_tenant(self):
        self.client.force_authenticate(user=self.user)
        res = self.client.get(
            "/api/tenants/settings/current/",
            HTTP_X_TENANT_ID=str(self.tenant_a.TenantID))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["idle_timeout_minutes"], 180)

    def test_idle_timeout_persists(self):
        """PATCH يحفظ المهلة، وقراءة لاحقة تُعيدها كما هي (لا ترجع افتراضياً)."""
        self.client.force_authenticate(user=self.user)
        res = self.client.patch(
            "/api/tenants/settings/current/",
            {"idle_timeout_minutes": 30},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant_a.TenantID))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["idle_timeout_minutes"], 30)

        res2 = self.client.get(
            "/api/tenants/settings/current/",
            HTTP_X_TENANT_ID=str(self.tenant_a.TenantID))
        self.assertEqual(res2.data["idle_timeout_minutes"], 30)

    def test_idle_timeout_isolated_per_company(self):
        """مهلة الشركة A لا تسري على الشركة B (خاص بكل شركة)."""
        self.client.force_authenticate(user=self.user)
        self.client.patch(
            "/api/tenants/settings/current/",
            {"idle_timeout_minutes": 60},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant_a.TenantID))

        res_b = self.client.get(
            "/api/tenants/settings/current/",
            HTTP_X_TENANT_ID=str(self.tenant_b.TenantID))
        self.assertEqual(res_b.data["idle_timeout_minutes"], 180)

    def test_idle_timeout_rejects_out_of_range(self):
        """قيمة أقل من 5 أو أكبر من 1440 دقيقة تُرفَض (حماية من إدخال خاطئ)."""
        self.client.force_authenticate(user=self.user)
        too_small = self.client.patch(
            "/api/tenants/settings/current/",
            {"idle_timeout_minutes": 2},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant_a.TenantID))
        self.assertEqual(too_small.status_code, status.HTTP_400_BAD_REQUEST)

        too_big = self.client.patch(
            "/api/tenants/settings/current/",
            {"idle_timeout_minutes": 5000},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant_a.TenantID))
        self.assertEqual(too_big.status_code, status.HTTP_400_BAD_REQUEST)
