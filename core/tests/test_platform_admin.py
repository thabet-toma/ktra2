from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.test import RequestFactory, override_settings
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

    def test_platform_company_endpoints_are_closed_to_a_company_manager(self):
        self.client.force_authenticate(self.company_manager)
        detail = self.client.get(f"/api/platform/companies/{self.active.pk}/")
        patched = self.client.patch(
            f"/api/platform/companies/{self.active.pk}/", {"status": "Suspended"}, format="json")
        members = self.client.get(f"/api/platform/companies/{self.active.pk}/members/")
        self.assertEqual(detail.status_code, 403)
        self.assertEqual(patched.status_code, 403)
        self.assertEqual(members.status_code, 403)

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


class PlatformCompanyControlTest(APITestCase):
    """لوحة تحكم السوبر أدمن: يدير أي شركة وأعضاءها دون أن يكون عضواً فيها."""

    @classmethod
    def setUpTestData(cls):
        cls.superuser = User.objects.create_superuser(
            username="platform-root", email="root@example.com", password="x",
        )
        cls.manager = User.objects.create_user(username="mgr", email="mgr@example.com", password="x")
        cls.staff = User.objects.create_user(username="stf", email="stf@example.com", password="x")
        cls.outsider = User.objects.create_user(username="out", email="out@example.com", password="x")
        cls.company = Tenant.objects.create(
            CompanyName="شركة العميل", SubscriptionPlan="Basic", Status="Trial",
        )
        cls.mgr_membership = UserCompanyMembership.objects.create(
            user=cls.manager, tenant=cls.company, role="manager",
        )
        cls.staff_membership = UserCompanyMembership.objects.create(
            user=cls.staff, tenant=cls.company, role="staff",
        )

    def setUp(self):
        self.client.force_authenticate(self.superuser)

    def _member_url(self, membership):
        return f"/api/platform/companies/{self.company.pk}/members/{membership.pk}/"

    def test_detail_returns_company_with_its_members(self):
        response = self.client.get(f"/api/platform/companies/{self.company.pk}/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["name"], "شركة العميل")
        self.assertEqual(
            {row["username"] for row in response.data["members"]}, {"mgr", "stf"})
        self.assertTrue(all(row["is_active"] for row in response.data["members"]))

    def test_super_admin_edits_name_plan_status_and_import(self):
        response = self.client.patch(
            f"/api/platform/companies/{self.company.pk}/",
            {"name": "شركة النور", "plan": "Enterprise", "status": "Suspended",
             "import_enabled": True},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.company.refresh_from_db()
        self.assertEqual(self.company.CompanyName, "شركة النور")
        self.assertEqual(self.company.SubscriptionPlan, "Enterprise")
        self.assertEqual(self.company.Status, "Suspended")
        self.assertTrue(self.company.import_enabled)

    def test_edit_rejects_unknown_status_plan_and_empty_name(self):
        bad_status = self.client.patch(
            f"/api/platform/companies/{self.company.pk}/", {"status": "Deleted"}, format="json")
        bad_plan = self.client.patch(
            f"/api/platform/companies/{self.company.pk}/", {"plan": "Free"}, format="json")
        empty_name = self.client.patch(
            f"/api/platform/companies/{self.company.pk}/", {"name": "  "}, format="json")
        self.assertEqual(bad_status.status_code, 400)
        self.assertEqual(bad_plan.status_code, 400)
        self.assertEqual(empty_name.status_code, 400)
        self.company.refresh_from_db()
        self.assertEqual(self.company.Status, "Trial")

    def test_super_admin_adds_changes_role_and_removes_a_member(self):
        added = self.client.post(
            f"/api/platform/companies/{self.company.pk}/members/",
            {"identifier": "out@example.com", "role": "accountant"}, format="json",
        )
        self.assertEqual(added.status_code, 201, added.content)
        membership = UserCompanyMembership.objects.get(user=self.outsider, tenant=self.company)
        self.assertEqual(membership.role, "accountant")

        changed = self.client.patch(
            f"/api/platform/companies/{self.company.pk}/members/{membership.pk}/",
            {"role": "sales"}, format="json",
        )
        self.assertEqual(changed.status_code, 200, changed.content)
        membership.refresh_from_db()
        self.assertEqual(membership.role, "sales")

        removed = self.client.delete(
            f"/api/platform/companies/{self.company.pk}/members/{membership.pk}/")
        self.assertEqual(removed.status_code, 204, removed.content)
        self.assertFalse(UserCompanyMembership.objects.filter(pk=membership.pk).exists())

    def test_add_member_rejects_unknown_user_and_duplicate(self):
        unknown = self.client.post(
            f"/api/platform/companies/{self.company.pk}/members/",
            {"identifier": "لا-أحد", "role": "staff"}, format="json")
        duplicate = self.client.post(
            f"/api/platform/companies/{self.company.pk}/members/",
            {"identifier": "stf", "role": "staff"}, format="json")
        self.assertEqual(unknown.status_code, 404)
        self.assertEqual(duplicate.status_code, 400)

    def test_last_manager_is_protected_from_demotion_and_removal(self):
        demoted = self.client.patch(
            self._member_url(self.mgr_membership), {"role": "staff"}, format="json")
        removed = self.client.delete(self._member_url(self.mgr_membership))
        self.assertEqual(demoted.status_code, 400)
        self.assertEqual(removed.status_code, 400)
        self.mgr_membership.refresh_from_db()
        self.assertEqual(self.mgr_membership.role, "manager")

    def test_member_import_access_requires_the_company_to_be_enabled(self):
        blocked = self.client.patch(
            self._member_url(self.staff_membership), {"can_access_import": True}, format="json")
        self.assertEqual(blocked.status_code, 400)

        self.client.patch(
            f"/api/platform/companies/{self.company.pk}/",
            {"import_enabled": True}, format="json")
        granted = self.client.patch(
            self._member_url(self.staff_membership), {"can_access_import": True}, format="json")
        self.assertEqual(granted.status_code, 200, granted.content)
        self.staff_membership.refresh_from_db()
        self.assertTrue(self.staff_membership.can_access_import)

    def test_super_admin_suspends_and_restores_a_user_account(self):
        suspended = self.client.post(
            f"/api/platform/users/{self.staff.pk}/set-active/", {"is_active": False}, format="json")
        self.assertEqual(suspended.status_code, 200, suspended.content)
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.is_active)

        restored = self.client.post(
            f"/api/platform/users/{self.staff.pk}/set-active/", {"is_active": True}, format="json")
        self.assertEqual(restored.status_code, 200, restored.content)
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.is_active)

    def test_super_admin_cannot_suspend_own_account(self):
        response = self.client.post(
            f"/api/platform/users/{self.superuser.pk}/set-active/",
            {"is_active": False}, format="json")
        self.assertEqual(response.status_code, 400)
        self.superuser.refresh_from_db()
        self.assertTrue(self.superuser.is_active)

    @override_settings(SUPER_ADMIN_EMAILS=["mgr@example.com"])
    def test_settings_configured_super_admin_account_cannot_be_suspended(self):
        response = self.client.post(
            f"/api/platform/users/{self.manager.pk}/set-active/",
            {"is_active": False}, format="json")
        self.assertEqual(response.status_code, 400)
        self.manager.refresh_from_db()
        self.assertTrue(self.manager.is_active)

    def test_member_cannot_manage_members_through_the_platform_route(self):
        self.client.force_authenticate(self.manager)
        response = self.client.patch(
            self._member_url(self.staff_membership), {"role": "viewer"}, format="json")
        self.assertEqual(response.status_code, 403)


class SuspendedCompanyAccessTest(APITestCase):
    """إيقاف الشركة من لوحة المنصة يمنع أعضاءها فعلاً — لا حالة تزيينية."""

    @classmethod
    def setUpTestData(cls):
        cls.member = User.objects.create_user(username="member", password="x")
        cls.superuser = User.objects.create_superuser(
            username="root2", email="root2@example.com", password="x")
        cls.suspended = Tenant.objects.create(
            CompanyName="شركة موقوفة", SubscriptionPlan="Basic", Status="Suspended")
        cls.running = Tenant.objects.create(
            CompanyName="شركة عاملة", SubscriptionPlan="Basic", Status="Active")
        for tenant in (cls.suspended, cls.running):
            UserCompanyMembership.objects.create(user=cls.member, tenant=tenant, role="manager")

    def _request(self, user, tenant):
        request = RequestFactory().get("/api/anything/", HTTP_X_TENANT_ID=str(tenant.pk))
        request.user = user
        return request

    def test_member_is_blocked_from_a_suspended_company(self):
        from core.tenant_utils import get_tenant

        with self.assertRaises(PermissionDenied):
            get_tenant(self._request(self.member, self.suspended))

    def test_running_company_and_super_admin_are_unaffected(self):
        from core.tenant_utils import get_tenant

        self.assertEqual(
            get_tenant(self._request(self.member, self.running)).pk, self.running.pk)
        self.assertEqual(
            get_tenant(self._request(self.superuser, self.suspended)).pk, self.suspended.pk)
