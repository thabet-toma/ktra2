"""قراءة حالة وحدات الشركة وتبديلها من لوحة المنصة — سوبر أدمن فقط."""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from core.models import TenantModule
from tenants.models import Tenant, UserCompanyMembership


class PlatformModuleStateTest(APITestCase):
    def setUp(self):
        self.root = User.objects.create_superuser(
            username="modules-root", email="modules@example.com", password="x",
        )
        self.manager = User.objects.create_user("modules-manager", password="x")
        self.tenant = Tenant.objects.create(CompanyName="شركة الوحدات")
        UserCompanyMembership.objects.create(user=self.manager, tenant=self.tenant, role="manager")

    def test_super_admin_reads_every_module_state_for_a_company(self):
        TenantModule.objects.create(
            tenant=self.tenant,
            module_key="accountant_portal",
            enabled=True,
            plan_note="تجربة",
        )
        self.client.force_authenticate(self.root)

        response = self.client.get(f"/api/platform/companies/{self.tenant.pk}/modules/")

        self.assertEqual(response.status_code, 200, response.content)
        rows = {row["module_key"]: row for row in response.data["results"]}
        self.assertTrue(rows["accountant_portal"]["enabled"])
        self.assertEqual(rows["accountant_portal"]["plan_note"], "تجربة")
        self.assertFalse(rows["accountant_portal"]["legacy"])
        self.assertFalse(rows["import"]["enabled"])
        self.assertTrue(rows["import"]["legacy"])

    def test_company_manager_cannot_read_module_state(self):
        self.client.force_authenticate(self.manager)

        response = self.client.get(f"/api/platform/companies/{self.tenant.pk}/modules/")

        self.assertEqual(response.status_code, 403, response.content)
