"""T-DUPID — رفض إضافة طرف برقم ضريبي أو رقم حساب بنكي **شبيه** لطرف قائم.

«شبيه» = مطابق بعد التطبيع (تجاهل الفراغات والشرطات وعلامات الترقيم وحالة
الأحرف) — فـ «123-456 789» و«123456789» رقمٌ واحد وإن كُتب بشكلين. الفحص مُنطاق
بالشركة، ويشمل كل الأنواع (عميل/مورد/وكيل/مخلّص/ناقل) لأن الرقم الضريبي هوية
كيان قانوني واحد لا صفة تعامل.
"""
from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from partners.models import Partner, PartnerBankAccount
from tenants.models import Currency, Tenant, UserCompanyMembership


class PartnerDuplicateTaxNumberTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="dupid-boss", password="x")
        cls.tenant = Tenant.objects.create(TenantID=931, CompanyName="Dup Ids")
        UserCompanyMembership.objects.create(
            user=cls.user, tenant=cls.tenant, role="manager", is_default=True,
        )
        cls.other_tenant = Tenant.objects.create(TenantID=932, CompanyName="Dup Ids B")
        cls.existing = Partner.objects.create(
            tenant=cls.tenant, name="مورد قائم", partner_type="Supplier",
            tax_number="123-456 789",
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.headers = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _create(self, **payload):
        payload.setdefault("partner_type", "Customer")
        return self.client.post("/api/partners/", payload, format="json", **self.headers)

    def test_identical_tax_number_is_rejected(self):
        res = self._create(name="عميل جديد", tax_number="123-456 789")
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("مورد قائم", str(res.json()))

    def test_similar_tax_number_differing_only_in_format_is_rejected(self):
        res = self._create(name="عميل جديد", tax_number=" 123456789 ")
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("tax_number", res.json())

    def test_distinct_tax_number_is_accepted(self):
        res = self._create(name="عميل جديد", tax_number="987654321")
        self.assertEqual(res.status_code, 201, res.content)

    def test_blank_tax_number_never_blocks(self):
        first = self._create(name="عميل بلا رقم")
        self.assertEqual(first.status_code, 201, first.content)
        second = self._create(name="عميل آخر بلا رقم", tax_number="")
        self.assertEqual(second.status_code, 201, second.content)

    def test_same_partner_keeping_its_own_number_is_accepted(self):
        res = self.client.patch(
            f"/api/partners/{self.existing.id}/",
            {"name": "مورد قائم مُحدَّث", "tax_number": "123456789"},
            format="json", **self.headers,
        )
        self.assertEqual(res.status_code, 200, res.content)

    def test_another_company_with_the_same_number_does_not_block(self):
        Partner.objects.create(
            tenant=self.other_tenant, name="طرف شركة أخرى",
            partner_type="Supplier", tax_number="555000",
        )
        res = self._create(name="عميل جديد", tax_number="555-000")
        self.assertEqual(res.status_code, 201, res.content)


class PartnerDuplicateBankAccountTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="dupbank-boss", password="x")
        cls.tenant = Tenant.objects.create(TenantID=933, CompanyName="Dup Banks")
        UserCompanyMembership.objects.create(
            user=cls.user, tenant=cls.tenant, role="manager", is_default=True,
        )
        cls.ils = Currency.objects.create(
            CurrencyID=933, Code="ILS", Symbol="₪", IsBaseCurrency=True,
        )
        cls.existing = Partner.objects.create(
            tenant=cls.tenant, name="مورد بحساب", partner_type="Supplier",
        )
        PartnerBankAccount.objects.create(
            tenant=cls.tenant, partner=cls.existing, bank_name="بنك فلسطين",
            account_number="0012-300-456", currency=cls.ils, is_default=True,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.headers = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _create(self, name, account_number):
        return self.client.post(
            "/api/partners/",
            {
                "name": name,
                "partner_type": "Customer",
                "bank_accounts": [{
                    "bank_name": "بنك القاهرة عمان",
                    "account_number": account_number,
                    "currency": self.ils.CurrencyID,
                    "is_active": True,
                    "is_default": True,
                }],
            },
            format="json", **self.headers,
        )

    def test_similar_bank_account_of_another_partner_is_rejected(self):
        res = self._create("عميل جديد", "0012300456")
        self.assertEqual(res.status_code, 400, res.content)
        self.assertIn("مورد بحساب", str(res.json()))
        self.assertFalse(Partner.objects.filter(name="عميل جديد").exists())

    def test_distinct_bank_account_is_accepted(self):
        res = self._create("عميل جديد", "999888777")
        self.assertEqual(res.status_code, 201, res.content)

    def test_partner_keeping_its_own_bank_account_is_accepted(self):
        account = self.existing.bank_accounts.get()
        res = self.client.patch(
            f"/api/partners/{self.existing.id}/",
            {
                "bank_accounts": [{
                    "id": account.id,
                    "bank_name": "بنك فلسطين",
                    "account_number": "0012300456",
                    "currency": self.ils.CurrencyID,
                    "is_active": True,
                    "is_default": True,
                }],
            },
            format="json", **self.headers,
        )
        self.assertEqual(res.status_code, 200, res.content)
