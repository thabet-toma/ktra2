"""إشارة رصيد الطرف بحسب نوعه — الدائن كلّه لا «المورد» وحده.

إنتاج (شركة 1): المخلّص حاييم (CustomsBroker) ظهر رصيده −7,551.50 بدل «له 7,551.50»،
لأن `balance`/`profile`/`statement` قارنت النوع بـ«supplier» وحده فعاملت المخلّص ووكيل
الشحن والناقل كعميل (مدين − دائن).
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, JournalHeader, JournalLine
from partners.models import Partner, is_creditor_party
from tenants.models import Currency
from tenants.services import create_company

CREDITOR_TYPES = ("Supplier", "FreightForwarder", "CustomsBroker", "LocalTransporter", "Carrier")


class CreditorPartySignTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="creditorsign", password="x")
        Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة إشارة الرصيد", cls.user)
        cls.control = Account.objects.create(
            tenant=cls.tenant, code="2101-S", name="ذمم", account_type="Liability", is_active=True)

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.h = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _partner_with(self, partner_type, *, debit, credit):
        partner = Partner.objects.create(tenant=self.tenant, name=f"طرف {partner_type}", partner_type=partner_type)
        for d, c, day in ((0, credit, "2026-06-01"), (debit, 0, "2026-06-02")):
            jh = JournalHeader.objects.create(
                tenant=self.tenant, transaction_date=day, is_posted=True, exchange_rate=Decimal("1"),
                reference_type="MANUAL", reference_id=None)
            JournalLine.objects.create(
                tenant=self.tenant, journal=jh, account=self.control,
                debit=Decimal(str(d)), credit=Decimal(str(c)), partner=partner)
        return partner

    def test_every_creditor_type_reads_credit_minus_debit(self):
        for partner_type in CREDITOR_TYPES:
            with self.subTest(partner_type=partner_type):
                partner = self._partner_with(partner_type, debit=2000, credit=9551.50)
                balance = self.client.get(f"/api/partners/{partner.id}/balance/", **self.h).data
                self.assertEqual(Decimal(balance["open_balance"]), Decimal("7551.50"))
                self.assertTrue(balance["is_creditor"])

                profile = self.client.get(f"/api/partners/{partner.id}/profile/", **self.h).data
                self.assertEqual((Decimal(profile["balance"]), profile["balance_side"]), (Decimal("7551.50"), "Cr"))

                statement = self.client.get(
                    f"/api/partners/{partner.id}/statement/?ordering=oldest", **self.h).data
                self.assertEqual(Decimal(statement["closing_balance"]), Decimal("7551.50"))
                self.assertEqual(
                    [Decimal(r["running_balance"]) for r in statement["results"]],
                    [Decimal("9551.50"), Decimal("7551.50")])
                self.assertEqual(Decimal(statement["results"][1]["balance_before"]), Decimal("9551.50"))

    def test_customer_keeps_debit_minus_credit(self):
        partner = self._partner_with("Customer", debit=9000, credit=0)
        balance = self.client.get(f"/api/partners/{partner.id}/balance/", **self.h).data
        self.assertEqual(Decimal(balance["open_balance"]), Decimal("9000"))
        self.assertFalse(balance["is_creditor"])
        profile = self.client.get(f"/api/partners/{partner.id}/profile/", **self.h).data
        self.assertEqual((Decimal(profile["balance"]), profile["balance_side"]), (Decimal("9000"), "Dr"))

    def test_is_creditor_party_accepts_the_partner_or_its_type(self):
        self.assertTrue(is_creditor_party("CustomsBroker"))
        self.assertTrue(is_creditor_party(Partner(partner_type="Carrier")))
        self.assertFalse(is_creditor_party("Customer"))
        self.assertFalse(is_creditor_party(None))
