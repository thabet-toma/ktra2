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

    def test_company_manager_cannot_list_or_grant_super_admin(self):
        self.client.force_authenticate(self.company_manager)
        listed = self.client.get("/api/platform/super-admins/")
        granted = self.client.post(
            "/api/platform/super-admins/",
            {"identifier": "company-manager"}, format="json",
        )
        self.assertEqual(listed.status_code, 403)
        self.assertEqual(granted.status_code, 403)
        self.company_manager.refresh_from_db()
        self.assertFalse(self.company_manager.is_superuser)

    def test_super_admin_grants_and_revokes_another_super_admin(self):
        self.client.force_authenticate(self.superuser)

        granted = self.client.post(
            "/api/platform/super-admins/",
            {"identifier": "company-manager"}, format="json",
        )
        self.assertEqual(granted.status_code, 201, granted.content)
        self.assertEqual(granted.data["username"], "company-manager")
        self.assertTrue(granted.data["removable"])
        self.company_manager.refresh_from_db()
        self.assertTrue(self.company_manager.is_superuser)

        # المرقّى الجديد يصل لوحة المنصة فعلاً — لا علم بلا وصول.
        self.client.force_authenticate(self.company_manager)
        self.assertEqual(self.client.get("/api/platform/dashboard/").status_code, 200)

        self.client.force_authenticate(self.superuser)
        listed = self.client.get("/api/platform/super-admins/")
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertIn("company-manager", [row["username"] for row in listed.data])

        revoked = self.client.delete(
            f"/api/platform/super-admins/{self.company_manager.pk}/")
        self.assertEqual(revoked.status_code, 204, revoked.content)
        self.company_manager.refresh_from_db()
        self.assertFalse(self.company_manager.is_superuser)

    def test_grant_rejects_unknown_identifier_and_existing_super_admin(self):
        self.client.force_authenticate(self.superuser)
        unknown = self.client.post(
            "/api/platform/super-admins/", {"identifier": "لا-أحد"}, format="json")
        already = self.client.post(
            "/api/platform/super-admins/", {"identifier": "platform-root"}, format="json")
        empty = self.client.post("/api/platform/super-admins/", {}, format="json")
        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(already.status_code, 400)
        self.assertEqual(empty.status_code, 400)

    def test_grant_accepts_email_as_identifier(self):
        self.client.force_authenticate(self.superuser)
        response = self.client.post(
            "/api/platform/super-admins/",
            {"identifier": "platform@example.com"}, format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        self.configured_admin.refresh_from_db()
        self.assertTrue(self.configured_admin.is_superuser)

    def test_revoke_refuses_self_and_settings_configured_admin(self):
        self.client.force_authenticate(self.superuser)
        myself = self.client.delete(f"/api/platform/super-admins/{self.superuser.pk}/")
        self.assertEqual(myself.status_code, 400)
        self.superuser.refresh_from_db()
        self.assertTrue(self.superuser.is_superuser)

        self.configured_admin.is_superuser = True
        self.configured_admin.save(update_fields=["is_superuser"])
        with self.settings(SUPER_ADMIN_EMAILS=["platform@example.com"]):
            blocked = self.client.delete(
                f"/api/platform/super-admins/{self.configured_admin.pk}/")
        self.assertEqual(blocked.status_code, 400)
        self.configured_admin.refresh_from_db()
        self.assertTrue(self.configured_admin.is_superuser)

    @override_settings(SUPER_ADMIN_EMAILS=["platform@example.com"])
    def test_list_includes_settings_configured_admin_as_unremovable(self):
        self.client.force_authenticate(self.superuser)
        rows = {row["username"]: row for row in self.client.get(
            "/api/platform/super-admins/").data}
        self.assertEqual(rows["configured-admin"]["source"], "settings")
        self.assertFalse(rows["configured-admin"]["removable"])
        self.assertEqual(rows["platform-root"]["source"], "flag")

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
