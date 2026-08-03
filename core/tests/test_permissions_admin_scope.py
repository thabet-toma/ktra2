"""T-PERM المرحلة 3 — ربط الإدارة بالمحرّك وحصر ملخص الأعمال بالمدير.

كانت `admin.members.manage` و`admin.settings.manage` في الكتالوج بلا إنفاذ
(الحارس القديم `_require_company_manager` يقارن الدور نصّياً). تبقى الإدارة
محكومة بالصلاحيات، أما ملخص مؤشرات الشركة المالي فمقصور على المدير نفسه.
"""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from core.access import permission_keys
from tenants.models import RolePermission, UserCompanyMembership
from tenants.services import create_company


class AdminScopeEnforcementTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.boss = User.objects.create_user(username="adm-boss", password="x")
        cls.seller = User.objects.create_user(username="adm-seller", password="x")
        cls.tenant = create_company("شركة نطاق الإدارة", cls.boss)
        cls.m = UserCompanyMembership.objects.create(
            user=cls.seller, tenant=cls.tenant, role="sales")

    def _as(self, user):
        self.client.force_authenticate(user=user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _grant(self, key, role="sales"):
        RolePermission.objects.create(
            tenant=self.tenant, role=role, permission_key=key, allowed=True)

    # ── الكتالوج ──
    def test_dashboard_is_not_a_delegable_permission(self):
        assert "admin.dashboard.view" not in permission_keys()

    # ── إدارة الأعضاء ──
    def test_sales_employee_cannot_manage_members(self):
        base = f"/api/tenants/companies/{self.tenant.TenantID}"
        h = self._as(self.seller)
        assert self.client.post(
            f"{base}/members/", {"username_or_email": "x", "role": "staff"},
            format="json", **h).status_code == 403
        assert self.client.post(
            f"{base}/members/change-role/",
            {"membership_id": self.m.id, "role": "staff"}, format="json",
            **h).status_code == 403
        assert self.client.post(
            f"{base}/members/remove/", {"membership_id": self.m.id},
            format="json", **h).status_code == 403

    def test_granting_members_permission_opens_the_door(self):
        """الصلاحية هي الحَكَم لا اسم الدور — موظف مبيعات مُنح الإدارة يُدير."""
        self._grant("admin.members.manage")
        res = self.client.post(
            f"/api/tenants/companies/{self.tenant.TenantID}/members/change-role/",
            {"membership_id": self.m.id, "role": "staff"}, format="json",
            **self._as(self.seller))
        assert res.status_code == 200, res.content
        self.m.refresh_from_db()
        assert self.m.role == "staff"

    def test_manager_still_manages_members(self):
        res = self.client.post(
            f"/api/tenants/companies/{self.tenant.TenantID}/members/change-role/",
            {"membership_id": self.m.id, "role": "procurement"}, format="json",
            **self._as(self.boss))
        assert res.status_code == 200, res.content

    # ── إعدادات الشركة ──
    def test_company_settings_write_needs_the_permission(self):
        h = self._as(self.seller)
        assert self.client.patch(
            "/api/tenants/settings/current/", {"phone": "0599"}, format="json",
            **h).status_code == 403
        # القراءة تبقى مفتوحة (الشاشات تعرض بيانات الشركة)
        assert self.client.get(
            "/api/tenants/settings/current/", **h).status_code == 200

        self._grant("admin.settings.manage")
        assert self.client.patch(
            "/api/tenants/settings/current/", {"phone": "0599"}, format="json",
            **h).status_code == 200

    def test_dashboard_month_start_day_is_validated(self):
        h = self._as(self.boss)
        too_low = self.client.patch(
            "/api/tenants/settings/current/",
            {"dashboard_month_start_day": 0},
            format="json", **h)
        too_high = self.client.patch(
            "/api/tenants/settings/current/",
            {"dashboard_month_start_day": 32},
            format="json", **h)
        assert too_low.status_code == 400
        assert too_high.status_code == 400
        res = self.client.patch(
            "/api/tenants/settings/current/",
            {"dashboard_month_start_day": 20},
            format="json", **h)
        assert res.status_code == 200
        assert res.data["dashboard_month_start_day"] == 20

    def test_branch_management_needs_the_settings_permission(self):
        res = self.client.post(
            "/api/tenants/branches/", {"name": "فرع", "code": "BR1"},
            format="json", **self._as(self.seller))
        assert res.status_code == 403

    # ── لوحة التحكم التجارية ──
    def test_trade_dashboard_is_gated(self):
        h = self._as(self.seller)
        assert self.client.get("/api/dashboard/", **h).status_code == 403
        assert self.client.get(
            "/api/dashboard/", **self._as(self.boss)).status_code == 200
        # تجاوز قديم محفوظ لا يفتح الملخص بعد حصره بالمدير.
        self._grant("admin.dashboard.view")
        assert self.client.get(
            "/api/dashboard/", **self._as(self.seller)).status_code == 403
