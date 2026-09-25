"""سند الصرف والقبض للأطراف الدائنة غير «مورد»: المخلّص ووكيل الشحن والناقل.

الواجهة كانت تفلتر سند الصرف على `partner_type == 'supplier'` فلا يُصرف للمخلّص
(إنتاج: حاييم، partner 83)، وكرته يعرض «سند قبض» كأنه عميل. الخادم لم يكن يمنع —
هذا الملف يثبّت العقد: نفس السند ونفس القيد (Dr ذمّة الطرف / Cr الصندوق)، وسند
القبض منه (استرداد زيادة) يدائن ذمّته نفسها.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import Account, JournalLine
from accounting.services import create_fiscal_year
from partners.models import Partner
from tenants.models import Currency
from tenants.services import create_company


class CreditorPartyVoucherTest(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="credvouch", password="x")
        cls.ils = Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة الأطراف الدائنة", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.cash = Account.objects.create(
            tenant=cls.tenant, code="1110-CV", name="صندوق شيكل",
            account_type="Asset", is_active=True)

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.h = {"HTTP_X_TENANT_ID": str(self.tenant.TenantID)}

    def _party(self, ptype, name):
        partner = Partner.objects.create(tenant=self.tenant, name=name, partner_type=ptype)
        partner.refresh_from_db()
        self.assertIsNotNone(partner.linked_account_id, f"{ptype} بلا حساب ذمم")
        return partner

    def _lines(self, journal_id):
        return {
            (row.account_id, row.partner_id): (row.debit, row.credit)
            for row in JournalLine.objects.filter(journal_id=journal_id)
        }

    def test_payment_voucher_posts_for_every_creditor_type(self):
        for ptype, parent in (
            ("CustomsBroker", "2107"),
            ("FreightForwarder", "2106"),
            ("LocalTransporter", "2108"),
        ):
            with self.subTest(ptype=ptype):
                party = self._party(ptype, f"طرف {ptype}")
                self.assertEqual(party.linked_account.parent.code, parent)
                res = self.client.post("/api/logistics/supplier-payments/", {
                    "partner": party.id, "payment_date": "2026-06-20", "amount": "2527",
                    "currency": self.ils.CurrencyID, "exchange_rate": "1",
                    "cash_or_bank_account": self.cash.id,
                }, format="json", **self.h)
                self.assertEqual(res.status_code, 201, res.data)
                self.assertTrue(res.data["is_posted"], res.data)
                lines = self._lines(res.data["journal"])
                self.assertEqual(
                    lines[(party.linked_account_id, party.id)], (Decimal("2527.00"), Decimal("0.00")))
                self.assertEqual(lines[(self.cash.id, None)], (Decimal("0.00"), Decimal("2527.00")))

    def test_refund_receipt_from_broker_credits_his_own_account(self):
        """«سند قبض» خيارٌ ثانٍ للدائن: استرداد زيادة Dr صندوق / Cr ذمّة المخلّص."""
        broker = self._party("CustomsBroker", "حاييم")
        res = self.client.post("/api/sales/payments/", {
            "partner": broker.id, "payment_date": "2026-06-21", "amount": "500",
            "currency": self.ils.CurrencyID, "exchange_rate": "1",
            "cash_or_bank_account": self.cash.id,
        }, format="json", **self.h)
        self.assertEqual(res.status_code, 201, res.data)
        self.assertTrue(res.data["is_posted"], res.data)
        lines = self._lines(res.data["journal"])
        self.assertEqual(
            lines[(broker.linked_account_id, broker.id)], (Decimal("0.00"), Decimal("500.00")))
        self.assertEqual(lines[(self.cash.id, None)], (Decimal("500.00"), Decimal("0.00")))
