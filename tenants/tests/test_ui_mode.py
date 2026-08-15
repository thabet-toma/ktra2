"""THA-110 T1 — وضع عرض الواجهة لكل (مستخدم × شركة).

يثبت أن `ui_mode` تفضيلٌ شخصيّ على العضوية لا إعدادٌ للشركة: الافتراضي
«متقدم»، والكتابة ذاتية بلا صلاحية إدارية وتمسّ عضوية المستدعي في الشركة
النشطة وحدها، ونفس المستخدم يحمل وضعين مختلفين في شركتين. حارس «مستعرض»
القراءة-فقط يبقى نافذاً كما هو — لا ثقب فيه لأجل تفضيل عرض.
"""
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from tenants.models import Tenant, UserCompanyMembership

SET_UI_MODE = "/api/tenants/companies/set-ui-mode/"
MY_PERMISSIONS = "/api/permissions/me/"


class UiModeTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant_a = Tenant.objects.create(
            TenantID=1, CompanyName="Company A", SubscriptionPlan="Enterprise",
            Status="Active")
        cls.tenant_b = Tenant.objects.create(
            TenantID=2, CompanyName="Company B", SubscriptionPlan="Enterprise",
            Status="Active")

        cls.owner = User.objects.create_user(username="owner", password="password123")
        cls.membership_a = UserCompanyMembership.objects.create(
            user=cls.owner, tenant=cls.tenant_a, role="manager", is_default=True)
        cls.membership_b = UserCompanyMembership.objects.create(
            user=cls.owner, tenant=cls.tenant_b, role="manager")

        # زميل في نفس الشركة — عضويته يجب ألا تتأثر بتبديل المالك لوضعه.
        cls.colleague = User.objects.create_user(
            username="colleague", password="password123")
        cls.membership_colleague = UserCompanyMembership.objects.create(
            user=cls.colleague, tenant=cls.tenant_a, role="staff")

        cls.viewer = User.objects.create_user(username="viewer", password="password123")
        UserCompanyMembership.objects.create(
            user=cls.viewer, tenant=cls.tenant_a, role="viewer")

        cls.superadmin = User.objects.create_superuser(
            username="root", password="password123")

    def _as(self, user, tenant):
        self.client.force_authenticate(user=user)
        return {"HTTP_X_TENANT_ID": str(tenant.TenantID)}

    def test_default_is_advanced(self):
        """عضوية جديدة تبدأ «متقدمة» — لا نبدّل تجربة أحد صامتاً."""
        self.assertEqual(self.membership_a.ui_mode, "advanced")

        headers = self._as(self.owner, self.tenant_a)
        res = self.client.get(MY_PERMISSIONS, **headers)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["ui_mode"], "advanced")

    def test_write_touches_only_caller_membership_in_active_company(self):
        """التبديل يمسّ عضوية المستدعي في الشركة النشطة وحدها."""
        headers = self._as(self.owner, self.tenant_a)
        res = self.client.post(
            SET_UI_MODE, {"ui_mode": "simple"}, format="json", **headers)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["ui_mode"], "simple")

        self.membership_a.refresh_from_db()
        self.membership_b.refresh_from_db()
        self.membership_colleague.refresh_from_db()
        self.assertEqual(self.membership_a.ui_mode, "simple")
        self.assertEqual(self.membership_b.ui_mode, "advanced")
        self.assertEqual(self.membership_colleague.ui_mode, "advanced")

    def test_same_user_holds_two_modes_in_two_companies(self):
        """سهلٌ في شركته، متقدّمٌ في شركة يحاسب لها — العضوية هي وحدة التفضيل."""
        self.client.post(
            SET_UI_MODE, {"ui_mode": "simple"}, format="json",
            **self._as(self.owner, self.tenant_a))

        res_a = self.client.get(MY_PERMISSIONS, **self._as(self.owner, self.tenant_a))
        res_b = self.client.get(MY_PERMISSIONS, **self._as(self.owner, self.tenant_b))
        self.assertEqual(res_a.data["ui_mode"], "simple")
        self.assertEqual(res_b.data["ui_mode"], "advanced")

    def test_invalid_value_rejected(self):
        """قيمة خارج القائمة ⇒ 400، والعضوية لا تتغير."""
        headers = self._as(self.owner, self.tenant_a)
        res = self.client.post(
            SET_UI_MODE, {"ui_mode": "expert"}, format="json", **headers)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

        missing = self.client.post(SET_UI_MODE, {}, format="json", **headers)
        self.assertEqual(missing.status_code, status.HTTP_400_BAD_REQUEST)

        self.membership_a.refresh_from_db()
        self.assertEqual(self.membership_a.ui_mode, "advanced")

    def test_caller_without_membership_gets_400(self):
        """سوبر أدمن بلا عضوية في الشركة النشطة: لا صفّ يُكتب عليه ⇒ 400."""
        res = self.client.post(
            SET_UI_MODE, {"ui_mode": "simple"}, format="json",
            **self._as(self.superadmin, self.tenant_a))
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(
            UserCompanyMembership.objects.filter(user=self.superadmin).exists())

    def test_viewer_is_still_read_only(self):
        """حارس «مستعرض» القراءة-فقط يبقى نافذاً — لا ثقب فيه لأجل تفضيل عرض."""
        res = self.client.post(
            SET_UI_MODE, {"ui_mode": "simple"}, format="json",
            **self._as(self.viewer, self.tenant_a))
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_my_permissions_exposes_saved_mode(self):
        """الحمولة نفسها التي تُحمَّل عند الإقلاع تحمل الوضع — بلا طلب إضافي."""
        headers = self._as(self.colleague, self.tenant_a)
        self.client.post(SET_UI_MODE, {"ui_mode": "simple"}, format="json", **headers)

        res = self.client.get(MY_PERMISSIONS, **headers)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["ui_mode"], "simple")

    def test_superadmin_without_membership_reads_advanced(self):
        """بلا عضوية لا وضع محفوظاً — يُقرأ «متقدم» ولا ينكسر شيء."""
        res = self.client.get(
            MY_PERMISSIONS, **self._as(self.superadmin, self.tenant_a))
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data["ui_mode"], "advanced")
