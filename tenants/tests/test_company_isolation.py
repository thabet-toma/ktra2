from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from tenants.models import Tenant, UserCompanyMembership, TenantBook
from accounting.models import Account, Currency
from sales.models import SalesInvoice

class CompanyIsolationTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.currency = Currency.objects.create(Code="USD", Name="US Dollar", Symbol="$", IsBaseCurrency=True)
        
        cls.tenant_a = Tenant.objects.create(TenantID=1, CompanyName="Company A", SubscriptionPlan="Enterprise", Status="Active")
        cls.tenant_b = Tenant.objects.create(TenantID=2, CompanyName="Company B", SubscriptionPlan="Enterprise", Status="Active")
        
        cls.user_a = User.objects.create_user(username="usera", password="password123")
        cls.user_b = User.objects.create_user(username="userb", password="password123")
        
        UserCompanyMembership.objects.create(user=cls.user_a, tenant=cls.tenant_a, role="manager", is_default=True)
        UserCompanyMembership.objects.create(user=cls.user_b, tenant=cls.tenant_b, role="manager", is_default=True)
        
        Account.objects.create(tenant=cls.tenant_a, code="1101", name="Cash A", account_type="Asset")
        Account.objects.create(tenant=cls.tenant_b, code="1101", name="Cash B", account_type="Asset")

    def test_tenant_access_isolation(self):
        self.client.force_authenticate(user=self.user_a)
        
        response = self.client.get(
            "/api/tenants/settings/current/",
            HTTP_X_TENANT_ID=str(self.tenant_a.TenantID)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        
        response = self.client.get(
            "/api/tenants/settings/current/",
            HTTP_X_TENANT_ID=str(self.tenant_b.TenantID)
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_switching_company_with_membership(self):
        UserCompanyMembership.objects.create(user=self.user_a, tenant=self.tenant_b, role="staff")
        self.client.force_authenticate(user=self.user_a)
        
        response = self.client.get(
            "/api/tenants/settings/current/",
            HTTP_X_TENANT_ID=str(self.tenant_b.TenantID)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_isolated_chart_of_accounts(self):
        self.client.force_authenticate(user=self.user_a)
        
        response = self.client.get(
            "/api/accounting/accounts/",
            HTTP_X_TENANT_ID=str(self.tenant_a.TenantID)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        names = [item["name"] for item in response.data]
        self.assertIn("Cash A", names)
        self.assertNotIn("Cash B", names)

    def test_independent_invoice_sequences(self):
        TenantBook.objects.create(tenant=self.tenant_a, document_type="sales_invoice", book_number=1, last_used_number=5, is_active=True)
        TenantBook.objects.create(tenant=self.tenant_b, document_type="sales_invoice", book_number=1, last_used_number=10, is_active=True)
        
        self.client.force_authenticate(user=self.user_a)
        response = self.client.get(
            "/api/sales/invoices/next-number/?book=1",
            HTTP_X_TENANT_ID=str(self.tenant_a.TenantID)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["next_number"], f"SI-1-B1-6")
        
        self.client.force_authenticate(user=self.user_b)
        response = self.client.get(
            "/api/sales/invoices/next-number/?book=1",
            HTTP_X_TENANT_ID=str(self.tenant_b.TenantID)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["next_number"], f"SI-2-B1-11")

    def test_manager_can_create_company_with_seeded_coa(self):
        """A manager creates a company → 201 + a non-empty cloned COA."""
        self.client.force_authenticate(user=self.user_a)  # manager of tenant_a
        response = self.client.post("/api/tenants/companies/", {"CompanyName": "محل جديد"})
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        new_tid = response.data["TenantID"]
        # creator is now a manager member of the new company
        self.assertTrue(
            UserCompanyMembership.objects.filter(
                user=self.user_a, tenant_id=new_tid, role="manager"
            ).exists()
        )
        # COA was cloned (template seeds standard accounts)
        self.assertGreater(Account.objects.filter(tenant_id=new_tid).count(), 10)

    def test_staff_cannot_create_company(self):
        """A non-manager member must not be able to create a company (M4-T3)."""
        staff = User.objects.create_user(username="staffer", password="password123")
        UserCompanyMembership.objects.create(user=staff, tenant=self.tenant_a, role="staff")
        self.client.force_authenticate(user=staff)
        response = self.client.post("/api/tenants/companies/", {"CompanyName": "ممنوع"})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_signup_attaches_default_company(self):
        """A fresh signup must get a membership so it isn't locked out."""
        from hr.auth_api import _attach_default_company
        newbie = User.objects.create_user(username="newbie", password="password123")
        # default tenant is pk=1 (tenant_a); newbie has no membership yet
        _attach_default_company(newbie, is_first_user=False)
        self.assertTrue(
            UserCompanyMembership.objects.filter(user=newbie, tenant=self.tenant_a).exists()
        )
