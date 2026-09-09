"""اختبارات تسجيل نشاط إدارة الأعضاء في سجل النشاط (ActivityLog).

فحص المشكلة: إضافة عضو وتعديل دوره وحذفه في tenants كانت لا تُسجَّل إطلاقاً.
هذه الاختبارات تتأكد من كتابة صف في ActivityLog بالقيم الصحيحة (action, entity_type, اسم العضو).
"""
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient
from hr.models import UserDevice

from core.models import ActivityLog
from tenants.models import Tenant, UserCompanyMembership


class MemberActivityLogTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(TenantID=940, CompanyName="Activity Co")
        cls.manager = User.objects.create_user(username="act_mgr", password="x", email="act_mgr@x.co")
        cls.staff = User.objects.create_user(username="act_stf", password="x", email="act_stf@x.co")
        cls.candidate = User.objects.create_user(username="act_cand", password="x", email="act_cand@x.co")
        for u in (cls.manager, cls.staff, cls.candidate):
            UserDevice.objects.create(user=u)
        cls.mgr_membership = UserCompanyMembership.objects.create(
            user=cls.manager, tenant=cls.tenant, role="manager"
        )
        cls.staff_membership = UserCompanyMembership.objects.create(
            user=cls.staff, tenant=cls.tenant, role="staff"
        )

    def _client(self, user):
        c = APIClient()
        c.force_authenticate(user=user)
        c.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))
        return c

    def test_add_member_logs_activity(self):
        """إضافة عضو جديد تنشئ سجلاً في ActivityLog بـ action='create'."""
        client = self._client(self.manager)
        resp = client.post(
            f"/api/tenants/companies/{self.tenant.TenantID}/members/",
            {"username_or_email": self.candidate.username, "role": "accountant"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201, resp.content)

        log = ActivityLog.objects.filter(
            tenant=self.tenant,
            entity_type="company_member",
            action="create",
        ).order_by("-id").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.user, self.manager)
        self.assertEqual(log.entity_label, self.candidate.username)
        self.assertIn(self.candidate.username, log.description)

    def test_change_member_role_logs_activity(self):
        """تعديل دور العضو ينشئ سجلاً في ActivityLog بـ action='update' ويوثق الدور القديم والجديد."""
        client = self._client(self.manager)
        resp = client.post(
            f"/api/tenants/companies/{self.tenant.TenantID}/members/change-role/",
            {"membership_id": self.staff_membership.id, "role": "viewer"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)

        log = ActivityLog.objects.filter(
            tenant=self.tenant,
            entity_type="company_member",
            action="update",
        ).order_by("-id").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.user, self.manager)
        self.assertEqual(log.entity_label, self.staff.username)
        self.assertIn("موظف", log.description)
        self.assertIn("مستعرض", log.description)

    def test_remove_member_logs_activity(self):
        """إزالة عضو تنشئ سجلاً في ActivityLog بـ action='delete' وتلتقط هوية العضو قبل الحذف."""
        client = self._client(self.manager)
        member_id = self.staff_membership.id
        resp = client.post(
            f"/api/tenants/companies/{self.tenant.TenantID}/members/remove/",
            {"membership_id": member_id},
            format="json",
        )
        self.assertEqual(resp.status_code, 200, resp.content)

        log = ActivityLog.objects.filter(
            tenant=self.tenant,
            entity_type="company_member",
            action="delete",
        ).order_by("-id").first()
        self.assertIsNotNone(log)
        self.assertEqual(log.user, self.manager)
        self.assertEqual(log.entity_id, member_id)
        self.assertEqual(log.entity_label, self.staff.username)
        self.assertIn(self.staff.username, log.description)
