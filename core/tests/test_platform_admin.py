from django.contrib.auth.models import User
from django.test import override_settings
from rest_framework.test import APITestCase

from tenants.models import Tenant, UserCompanyMembership


class PlatformAdminApiTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username="platform-root", email="root@example.com", password="x",
        )
        cls.company_manager = User.objects.create_user(
            username="company-manager", password="x",
        )
        cls.configured_admin = User.objects.create_user(
            username="configured-admin", email="platform@example.com", password="x",
        )
        cls.active = Tenant.objects.create(
            CompanyName="شركة فعالة", SubscriptionPlan="Pro", Status="Active",
        )
        cls.trial = Tenant.objects.create(
            CompanyName="شركة تجريبية", SubscriptionPlan="Basic", Status="Trial",
        )
        UserCompanyMembership.objects.create(
            user=cls.company_manager, tenant=cls.active, role="manager",
        )

    def test_company_manager_cannot_access_platform_dashboard_or_notes(self):
        self.client.force_authenticate(self.company_manager)

        dashboard = self.client.get("/api/platform/dashboard/")
        notes = self.client.get("/api/platform/development-notes/")

        self.assertEqual(dashboard.status_code, 403)
        self.assertEqual(notes.status_code, 403)

    def test_superuser_dashboard_is_global_and_ignores_tenant_header(self):
        self.client.force_authenticate(self.superuser)

        response = self.client.get(
            "/api/platform/dashboard/", HTTP_X_TENANT_ID=str(self.active.TenantID),
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["companies"]["total"], 2)
        self.assertEqual(response.data["companies"]["active"], 1)
        self.assertEqual(response.data["companies"]["trial"], 1)
        self.assertEqual(response.data["memberships"], 1)
        self.assertEqual(
            {row["name"] for row in response.data["company_rows"]},
            {"شركة فعالة", "شركة تجريبية"},
        )

    @override_settings(SUPER_ADMIN_EMAILS=["platform@example.com"])
    def test_configured_super_admin_email_uses_the_same_platform_guard(self):
        self.client.force_authenticate(self.configured_admin)
        response = self.client.get("/api/platform/dashboard/")
        self.assertEqual(response.status_code, 200, response.content)

    def test_development_notes_crud_stamps_the_authenticated_super_admin(self):
        self.client.force_authenticate(self.superuser)
        created = self.client.post(
            "/api/platform/development-notes/",
            {
                "title": "تحسين شاشة العروض",
                "description": "إضافة صورة معاينة قرب رقم المستند",
                "status": "todo",
                "priority": "high",
                "assignee": "فريق الواجهة",
                "created_by": self.company_manager.id,
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.data["created_by"], self.superuser.id)
        note_id = created.data["id"]

        updated = self.client.patch(
            f"/api/platform/development-notes/{note_id}/",
            {"status": "in_progress", "updated_by": self.company_manager.id},
            format="json",
        )
        self.assertEqual(updated.status_code, 200, updated.content)
        self.assertEqual(updated.data["status"], "in_progress")
        self.assertEqual(updated.data["updated_by"], self.superuser.id)

        listed = self.client.get("/api/platform/development-notes/")
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertEqual([row["id"] for row in listed.data], [note_id])

        deleted = self.client.delete(f"/api/platform/development-notes/{note_id}/")
        self.assertEqual(deleted.status_code, 204, deleted.content)

    def test_development_note_rejects_unknown_status_and_priority(self):
        self.client.force_authenticate(self.superuser)
        response = self.client.post(
            "/api/platform/development-notes/",
            {
                "title": "قيمة غير صالحة",
                "description": "اختبار تحقق الحدود",
                "status": "hidden",
                "priority": "critical-secret",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("status", response.data)
        self.assertIn("priority", response.data)
