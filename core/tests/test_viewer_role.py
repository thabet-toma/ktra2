"""task11 R2-B — دور «مستعرض» قراءة فقط.

الأدوار كانت موجودة منذ task10 بلا أي فرض — المستعرض كان يستطيع إنشاء
وحذف وترحيل. TenantRolePermission يمنع كل الطرق غير الآمنة للمستعرض.
"""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from partners.models import Partner
from tenants.models import UserCompanyMembership
from tenants.services import create_company


class ViewerRoleTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = User.objects.create_user(username="boss", password="x")
        cls.viewer = User.objects.create_user(username="watcher", password="x")
        cls.tenant = create_company("شركة الأدوار", cls.manager)
        UserCompanyMembership.objects.create(
            user=cls.viewer, tenant=cls.tenant, role="viewer")
        cls.partner = Partner.objects.create(
            tenant=cls.tenant, name="شريك", partner_type="Customer")

    def _as(self, user):
        self.client.force_authenticate(user=user)
        return {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_viewer_can_read(self):
        h = self._as(self.viewer)
        assert self.client.get("/api/partners/", **h).status_code == 200
        assert self.client.get("/api/accounting/accounts/", **h).status_code == 200

    def test_viewer_cannot_write(self):
        h = self._as(self.viewer)
        res = self.client.post(
            "/api/partners/", {"name": "جديد", "partner_type": "Customer"},
            format="json", **h)
        assert res.status_code == 403
        res = self.client.delete(f"/api/partners/{self.partner.pk}/", **h)
        assert res.status_code == 403
        res = self.client.post(
            "/api/accounting/accounts/",
            {"code": "9999", "name": "حساب", "account_type": "Asset"},
            format="json", **h)
        assert res.status_code == 403

    def test_manager_can_write(self):
        h = self._as(self.manager)
        res = self.client.post(
            "/api/partners/", {"name": "عميل المدير", "partner_type": "Customer"},
            format="json", **h)
        assert res.status_code in (200, 201), res.content
