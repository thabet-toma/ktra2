"""زر «افتح واجهة المحاسب» لسوبر أدمن + بحث المحاسب عن شركة ليطلب الارتباط بها."""
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase

from accountant_portal.models import AccountantEngagement, AccountantProfile
from core.models import TenantModule
from core.modules import invalidate_module_cache
from tenants.models import Tenant, UserCompanyMembership


class PlatformAccountantWorkspaceTest(APITestCase):
    url = "/api/platform/accountant-workspace/"

    def setUp(self):
        self.root = User.objects.create_superuser(
            username="demo-root", email="demo-root@example.com", password="x",
        )
        self.manager = User.objects.create_user("demo-manager", password="x")

    def test_one_click_opens_a_full_accountant_workspace_for_the_super_admin(self):
        self.client.force_authenticate(self.root)

        response = self.client.post(self.url, {}, format="json")

        self.assertEqual(response.status_code, 200, response.content)
        profile = AccountantProfile.objects.get(user=self.root)
        self.assertEqual(profile.verification_status, "verified")
        self.assertIsNotNone(profile.email_verified_at)
        office_id = response.data["office"]["tenant_id"]
        self.assertTrue(
            UserCompanyMembership.objects.filter(
                user=self.root, tenant_id=office_id, role="manager",
            ).exists()
        )
        self.assertTrue(
            TenantModule.objects.get(tenant_id=office_id, module_key="accountant_portal").enabled
        )

    def test_pressing_twice_reuses_the_same_office_and_profile(self):
        self.client.force_authenticate(self.root)

        first = self.client.post(self.url, {}, format="json")
        second = self.client.post(self.url, {}, format="json")

        self.assertEqual(first.data["office"]["tenant_id"], second.data["office"]["tenant_id"])
        self.assertTrue(first.data["office_created"])
        self.assertFalse(second.data["office_created"])
        self.assertEqual(AccountantProfile.objects.filter(user=self.root).count(), 1)

    def test_only_a_platform_super_admin_may_open_it(self):
        self.client.force_authenticate(self.manager)

        response = self.client.post(self.url, {}, format="json")

        self.assertEqual(response.status_code, 403, response.content)
        self.assertFalse(AccountantProfile.objects.filter(user=self.manager).exists())

    def test_the_opened_workspace_can_immediately_request_an_engagement(self):
        client_tenant = Tenant.objects.create(CompanyName="شركة الزبون")
        TenantModule.objects.create(
            tenant=client_tenant, module_key="accountant_portal", enabled=True,
        )
        invalidate_module_cache(client_tenant.pk)
        self.client.force_authenticate(self.root)
        self.client.post(self.url, {}, format="json")

        found = self.client.get("/api/accountant/companies/lookup/?q=شركة الزبون")
        requested = self.client.post(
            "/api/accountant/engagements/request/",
            {"tenant_id": found.data["company"]["tenant_id"], "note": "طلب مراجعة"},
            format="json",
        )

        self.assertEqual(found.status_code, 200, found.content)
        self.assertEqual(requested.status_code, 201, requested.content)
        self.assertTrue(
            AccountantEngagement.objects.filter(
                accountant=self.root, tenant=client_tenant, status="pending",
            ).exists()
        )


class CompanyLookupTest(APITestCase):
    url = "/api/accountant/companies/lookup/"

    def setUp(self):
        self.accountant = User.objects.create_user("lookup-accountant", email="lookup@example.com")
        AccountantProfile.objects.create(
            user=self.accountant,
            professional_type="accountant",
            tax_registration_number="TAX-LOOKUP-1",
            business_address="رام الله",
            email_verified_at=timezone.now(),
        )
        self.licensed = Tenant.objects.create(CompanyName="شركة مرخصة")
        TenantModule.objects.create(tenant=self.licensed, module_key="accountant_portal", enabled=True)
        invalidate_module_cache(self.licensed.pk)
        self.unlicensed = Tenant.objects.create(CompanyName="شركة بلا ترخيص")
        self.client.force_authenticate(self.accountant)

    def test_exact_registered_name_finds_a_licensed_company(self):
        by_name = self.client.get(f"{self.url}?q=شركة مرخصة")
        by_id = self.client.get(f"{self.url}?q={self.licensed.pk}")

        self.assertEqual(by_name.status_code, 200, by_name.content)
        self.assertEqual(by_name.data["company"]["tenant_id"], self.licensed.pk)
        self.assertEqual(by_name.data["company"]["company_name"], "شركة مرخصة")
        # المعرّف الرقمي ليس مدخلاً للبحث — وإلا أمكن المرور على 1..N (T8).
        self.assertEqual(by_id.status_code, 400, by_id.content)

    def test_partial_names_never_enumerate_companies(self):
        response = self.client.get(f"{self.url}?q=شركة")

        self.assertEqual(response.status_code, 404, response.content)
        self.assertEqual(response.data["code"], "company_not_found")

    def test_unlicensed_company_answers_exactly_like_a_missing_one(self):
        response = self.client.get(f"{self.url}?q=شركة بلا ترخيص")

        self.assertEqual(response.status_code, 404, response.content)
        self.assertEqual(response.data["code"], "company_not_found")

    def test_existing_engagement_status_is_reported_back(self):
        AccountantEngagement.objects.create(
            accountant=self.accountant,
            tenant=self.licensed,
            initiated_by="accountant",
            status="pending",
        )

        response = self.client.get(f"{self.url}?q=شركة مرخصة")

        self.assertEqual(response.data["company"]["engagement_status"], "pending")
