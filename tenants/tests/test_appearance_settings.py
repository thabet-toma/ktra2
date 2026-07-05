"""Per-company appearance (font scale/family) on TenantSettings.

يثبت أن تفضيل الخط يُحفَظ خادمياً لكل شركة (فلا يرجع للافتراضي عند إعادة
الدخول) وأنه معزول بين الشركات (خاص بكل شركة لا بالمنصة).
"""
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth.models import User

from tenants.models import Tenant, UserCompanyMembership


class AppearanceSettingsTest(APITestCase):
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

    def test_defaults_returned_on_fresh_tenant(self):
        self.client.force_authenticate(user=self.user)
        res = self.client.get(
            "/api/tenants/settings/current/",
            HTTP_X_TENANT_ID=str(self.tenant_a.TenantID))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["font_scale"], "normal")
        self.assertEqual(res.data["font_family"], "default")

    def test_font_preference_persists(self):
        """PATCH يحفظ التفضيل، وقراءة لاحقة تُعيده كما هو (لا يرجع افتراضياً)."""
        self.client.force_authenticate(user=self.user)
        res = self.client.patch(
            "/api/tenants/settings/current/",
            {"font_scale": "large", "font_family": "tahoma"},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant_a.TenantID))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["font_scale"], "large")

        # قراءة جديدة (تحاكي إعادة فتح الموقع)
        res2 = self.client.get(
            "/api/tenants/settings/current/",
            HTTP_X_TENANT_ID=str(self.tenant_a.TenantID))
        self.assertEqual(res2.data["font_scale"], "large")
        self.assertEqual(res2.data["font_family"], "tahoma")

    def test_font_preference_isolated_per_company(self):
        """تفضيل الشركة A لا يسري على الشركة B (خاص بكل شركة)."""
        self.client.force_authenticate(user=self.user)
        self.client.patch(
            "/api/tenants/settings/current/",
            {"font_scale": "xlarge"},
            format="json",
            HTTP_X_TENANT_ID=str(self.tenant_a.TenantID))

        res_b = self.client.get(
            "/api/tenants/settings/current/",
            HTTP_X_TENANT_ID=str(self.tenant_b.TenantID))
        self.assertEqual(res_b.data["font_scale"], "normal")
