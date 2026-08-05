from datetime import date

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase

from accountant_portal.models import (
    AccountantEngagement,
    AccountantProfile,
    ReviewQuery,
    TaxPeriodReview,
)
from core.models import TenantModule
from core.modules import invalidate_module_cache
from tenants.models import Tenant, UserCompanyMembership


class WorkspaceCompaniesTest(APITestCase):
    url = "/api/accountant/workspace/companies/"

    def setUp(self):
        self.accountant = User.objects.create_user("m3-accountant", email="m3@example.com")
        AccountantProfile.objects.create(
            user=self.accountant,
            professional_type="accountant",
            tax_registration_number="TAX-M3-1",
            business_address="رام الله",
            email_verified_at=timezone.now(),
        )
        self.client.force_authenticate(self.accountant)

    def _company(self, name, *, status="active", licensed=True):
        tenant = Tenant.objects.create(CompanyName=name)
        if licensed:
            TenantModule.objects.create(tenant=tenant, module_key="accountant_portal", enabled=True)
            invalidate_module_cache(tenant.pk)
        engagement = AccountantEngagement.objects.create(
            accountant=self.accountant,
            tenant=tenant,
            initiated_by="accountant",
            status=status,
        )
        if status == "active":
            UserCompanyMembership.objects.create(
                user=self.accountant,
                tenant=tenant,
                role="legal_accountant",
            )
        return tenant, engagement

    def test_dashboard_aggregates_two_hundred_companies_within_four_queries(self):
        tenants = Tenant.objects.bulk_create(
            [Tenant(CompanyName=f"شركة {index:03d}") for index in range(200)]
        )
        tenants = list(Tenant.objects.filter(CompanyName__startswith="شركة "))
        TenantModule.objects.bulk_create(
            [
                TenantModule(tenant=tenant, module_key="accountant_portal", enabled=True)
                for tenant in tenants
            ]
        )
        AccountantEngagement.objects.bulk_create(
            [
                AccountantEngagement(
                    accountant=self.accountant,
                    tenant=tenant,
                    initiated_by="accountant",
                    status="active",
                )
                for tenant in tenants
            ]
        )
        engagements = list(AccountantEngagement.objects.filter(accountant=self.accountant))
        TaxPeriodReview.objects.bulk_create(
            [
                TaxPeriodReview(
                    tenant=engagement.tenant,
                    period_from=date(2026, 6, 1),
                    period_to=date(2026, 6, 30),
                    status="in_review",
                )
                for engagement in engagements
            ]
        )
        ReviewQuery.objects.bulk_create(
            [
                ReviewQuery(
                    tenant=engagement.tenant,
                    engagement=engagement,
                    title="نقص مرفق",
                    body="أرفق الفاتورة",
                    severity="blocker",
                )
                for engagement in engagements
            ]
        )

        with self.assertNumQueries(4):
            response = self.client.get(f"{self.url}?page_size=200")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["count"], 200)
        self.assertEqual(len(response.data["results"]), 200)
        first = response.data["results"][0]
        self.assertEqual(first["blockers"], 1)
        self.assertEqual(first["open_queries"], 1)
        self.assertEqual(first["last_period"]["status"], "in_review")

    def test_revoked_or_unlicensed_company_is_listed_but_not_accessible(self):
        self._company("شركة نشطة")
        self._company("شركة ملغاة", status="revoked")
        self._company("شركة بلا ترخيص", licensed=False)

        response = self.client.get(f"{self.url}?page_size=50")

        self.assertEqual(response.status_code, 200, response.content)
        access = {row["company_name"]: row["accessible"] for row in response.data["results"]}
        self.assertTrue(access["شركة نشطة"])
        self.assertFalse(access["شركة ملغاة"])
        self.assertFalse(access["شركة بلا ترخيص"])

    def test_dashboard_filters_by_status_and_search(self):
        self._company("مكتب الأمانة")
        self._company("مؤسسة الوفاء", status="pending")

        by_status = self.client.get(f"{self.url}?status=pending")
        by_search = self.client.get(f"{self.url}?search=الأمانة")

        self.assertEqual([row["company_name"] for row in by_status.data["results"]], ["مؤسسة الوفاء"])
        self.assertEqual([row["company_name"] for row in by_search.data["results"]], ["مكتب الأمانة"])

    def test_dashboard_never_leaks_another_accountants_companies(self):
        self._company("شركتي")
        other = User.objects.create_user("m3-other")
        other_tenant = Tenant.objects.create(CompanyName="شركة الآخر")
        AccountantEngagement.objects.create(
            accountant=other,
            tenant=other_tenant,
            initiated_by="accountant",
            status="active",
        )

        response = self.client.get(self.url)

        self.assertEqual([row["company_name"] for row in response.data["results"]], ["شركتي"])

    def test_permissions_me_exposes_module_flags(self):
        tenant, _ = self._company("شركة الأعلام")

        response = self.client.get("/api/permissions/me/", HTTP_X_TENANT_ID=str(tenant.pk))

        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.data["modules"]["accountant_portal"])
        self.assertFalse(response.data["modules"]["import"])
