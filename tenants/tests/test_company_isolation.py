from unittest.mock import patch

from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from tenants.models import Tenant, UserCompanyMembership, TenantBook
from accounting.models import Account, Currency
from sales.models import SalesInvoice
from core.access import user_has_perm

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



class SignupOnboardingJourneyTest(APITestCase):
    signup_url = "/api/hr/auth/signup/"
    login_url = "/api/hr/auth/login/"
    companies_url = "/api/tenants/companies/"
    my_companies_url = "/api/tenants/companies/my-companies/"

    def test_new_user_sees_example_company_with_invoice_creation_access(self):
        example = Tenant.objects.create(
            CompanyName="الزهور",
            SubscriptionPlan="Enterprise",
            Status="Active",
            is_example=True,
        )
        user = User.objects.create_user(username="new-user", password="123456")
        self.client.force_authenticate(user=user)

        response = self.client.get(self.my_companies_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["tenant"]["CompanyName"], "الزهور")
        self.assertTrue(response.data[0]["tenant"]["is_example"])
        self.assertEqual(response.data[0]["role"], "staff")
        membership = UserCompanyMembership.objects.get(user=user, tenant=example)
        self.assertTrue(membership.is_example_access)
        self.assertTrue(user_has_perm(user, example, "sales.invoice.create"))
        self.assertTrue(user_has_perm(user, example, "purchase.invoice.create"))

        created = self.client.post(
            self.companies_url,
            {"CompanyName": "شركة المستخدم الحقيقية"},
            format="json",
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED, created.content)
        real_membership = UserCompanyMembership.objects.get(
            user=user, tenant_id=created.data["TenantID"],
        )
        self.assertEqual(real_membership.role, "manager")
        self.assertTrue(real_membership.is_default)

    def test_signup_login_and_first_company_bootstrap(self):
        signup = self.client.post(
            self.signup_url,
            {
                "fullName": "  Ahmad   Saleh  ",
                "email": "  FOUNDER@Example.COM ",
                "password": "123456",
                # Legacy fields must not affect the new minimal contract.
                "accountType": "employee",
                "companyName": "Ignored legacy company",
            },
            format="json",
        )
        self.assertEqual(signup.status_code, status.HTTP_201_CREATED)

        user = User.objects.get(username="founder@example.com")
        self.assertEqual(user.email, "founder@example.com")
        self.assertEqual(user.first_name, "Ahmad")
        self.assertEqual(user.last_name, "Saleh")
        self.assertTrue(user.is_active)
        self.assertFalse(UserCompanyMembership.objects.filter(user=user).exists())

        login = self.client.post(
            self.login_url,
            {"email": "FOUNDER@EXAMPLE.COM", "password": "123456"},
            format="json",
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {login.json()['token']}")

        empty_companies = self.client.get(self.my_companies_url)
        self.assertEqual(empty_companies.status_code, status.HTTP_200_OK)
        self.assertEqual(empty_companies.data, [])

        created = self.client.post(
            self.companies_url,
            {"CompanyName": "شركة أحمد"},
            format="json",
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)

        membership = UserCompanyMembership.objects.get(
            user=user, tenant_id=created.data["TenantID"]
        )
        self.assertEqual(membership.role, "manager")
        self.assertTrue(membership.is_default)

        reloaded_companies = self.client.get(self.my_companies_url)
        self.assertEqual(reloaded_companies.status_code, status.HTTP_200_OK)
        self.assertEqual(len(reloaded_companies.data), 1)
        self.assertEqual(reloaded_companies.data[0]["role"], "manager")
        self.assertTrue(reloaded_companies.data[0]["is_default"])

        profile = self.client.get(f"/api/hr/users/{user.pk}/")
        self.assertEqual(profile.status_code, status.HTTP_200_OK)
        self.assertEqual(profile.json()["role"], "manager")

    def test_signup_requires_all_three_fields(self):
        valid = {
            "fullName": "Ahmad Saleh",
            "email": "founder@example.com",
            "password": "123456",
        }
        for field in valid:
            with self.subTest(field=field):
                payload = {**valid, field: ""}
                response = self.client.post(self.signup_url, payload, format="json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertEqual(response.json()["field"], field)
        self.assertEqual(User.objects.count(), 0)

    def test_signup_rejects_invalid_and_case_insensitive_duplicate_email(self):
        invalid = self.client.post(
            self.signup_url,
            {"fullName": "Ahmad", "email": "not-an-email", "password": "123456"},
            format="json",
        )
        self.assertEqual(invalid.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(invalid.json()["field"], "email")

        User.objects.create_user(
            username="Existing@Example.com",
            email="Existing@Example.com",
            password="123456",
        )
        duplicate = self.client.post(
            self.signup_url,
            {"fullName": "Another", "email": "existing@example.COM", "password": "123456"},
            format="json",
        )
        self.assertEqual(duplicate.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            duplicate.json()["detail"],
            "البريد الإلكتروني مسجل مسبقاً.",
        )

    def test_signup_password_policy_is_minimum_six_only(self):
        short = self.client.post(
            self.signup_url,
            {"fullName": "Ahmad", "email": "short@example.com", "password": "12345"},
            format="json",
        )
        self.assertEqual(short.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(short.json()["field"], "password")

        accepted = self.client.post(
            self.signup_url,
            {"fullName": "Ahmad", "email": "simple@example.com", "password": "123456"},
            format="json",
        )
        self.assertEqual(accepted.status_code, status.HTTP_201_CREATED)

    def test_signup_rolls_back_user_when_mirror_write_fails(self):
        payload = {
            "fullName": "Ahmad Saleh",
            "email": "rollback@example.com",
            "password": "123456",
        }
        with patch(
            "hr.auth_api._sync_user_mirror",
            side_effect=RuntimeError("simulated mirror failure"),
        ), self.assertRaises(RuntimeError):
            self.client.post(self.signup_url, payload, format="json")

        self.assertFalse(User.objects.filter(email="rollback@example.com").exists())
