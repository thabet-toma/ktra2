from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from partners.models import Partner
from tenants.models import Currency, Tenant, UserCompanyMembership


class PartnerPaymentDefaultsTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="partner-bank-defaults", password="x")
        cls.tenant = Tenant.objects.create(TenantID=913, CompanyName="Partner Banks")
        UserCompanyMembership.objects.create(
            user=cls.user, tenant=cls.tenant, role="manager", is_default=True,
        )
        cls.ils = Currency.objects.create(
            CurrencyID=913, Code="ILS", Symbol="₪", IsBaseCurrency=True,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.headers = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def test_partner_card_returns_banks_and_incoming_cheque_defaults(self):
        response = self.client.post(
            "/api/partners/",
            {
                "name": "زبون بحساب",
                "partner_type": "Customer",
                "bank_accounts": [
                    {
                        "bank_name": "بنك فلسطين",
                        "account_number": "0012300456",
                        "branch_name": "رام الله",
                        "beneficiary_name": "شركة الزبون",
                        "currency": self.ils.CurrencyID,
                        "is_active": True,
                        "is_default": True,
                    },
                ],
            },
            format="json",
            **self.headers,
        )
        self.assertEqual(response.status_code, 201, response.content)
        partner_id = response.json()["id"]
        account = response.json()["bank_accounts"][0]
        self.assertEqual(account["account_number"], "0012300456")
        self.assertEqual(account["branch_name"], "رام الله")
        self.assertTrue(account["is_default"])

        defaults = self.client.get(
            f"/api/partners/{partner_id}/payment-defaults/"
            f"?direction=Incoming&currency={self.ils.CurrencyID}",
            **self.headers,
        )
        self.assertEqual(defaults.status_code, 200, defaults.content)
        self.assertEqual(defaults.json()["selected_bank_account"]["id"], account["id"])
        self.assertEqual(
            defaults.json()["selected_bank_account"]["account_number"],
            "0012300456",
        )

        outgoing = self.client.get(
            f"/api/partners/{partner_id}/payment-defaults/?direction=Outgoing",
            **self.headers,
        )
        self.assertEqual(outgoing.status_code, 200, outgoing.content)
        self.assertIsNone(outgoing.json()["selected_bank_account"])
        self.assertEqual(outgoing.json()["payee_name"], "شركة الزبون")

    def test_invalid_bank_rolls_back_the_whole_new_partner(self):
        response = self.client.post(
            "/api/partners/",
            {
                "name": "يجب التراجع عنه",
                "partner_type": "Customer",
                "bank_accounts": [
                    {
                        "bank_name": "بنك صحيح",
                        "account_number": "100",
                        "currency": self.ils.CurrencyID,
                        "is_default": True,
                    },
                    {
                        "bank_name": "",
                        "account_number": "",
                        "currency": self.ils.CurrencyID,
                    },
                ],
            },
            format="json",
            **self.headers,
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(
            Partner.objects.filter(tenant=self.tenant, name="يجب التراجع عنه").exists()
        )
