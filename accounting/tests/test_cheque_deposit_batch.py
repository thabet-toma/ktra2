"""CHQ-4 — الإيداع الجماعي: حزمة الصباح تُودَع دفعةً واحدة أو لا تُودَع.

إيداع عشرين شيكاً كان عشرين نافذة وعشرين نداءً — والأسوأ أن فشل الورقة السابعة
كان يترك ستّاً مودَعة وستّاً لا، حالةً لا يملك المستخدم تصحيحها. فالمعيار الأول
هنا هو **الذرّية**: ورقةٌ واحدة غير مؤهَّلة ⇒ لا حركة ولا قيد على أيٍّ منها.
والقسيمة هي المخرَج الورقي الذي يُسلَّم مع الأوراق إلى البنك.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from rest_framework.test import APITestCase

from accounting.models import (
    Account, Bank, BankAccount, Cheque, ChequeMovement, JournalHeader,
)
from accounting.services import create_fiscal_year
from partners.models import Partner
from sales.models import SalesInvoice, SalesSettings
from tenants.models import Currency
from tenants.services import create_company


class ChequeDepositBatchTest(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="chq_batch", password="x")
        cls.ils = Currency.objects.create(
            Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.usd = Currency.objects.create(Code="USD", Name="دولار")
        cls.tenant = create_company("شركة الإيداع الجماعي", cls.user)
        cls.other = create_company("شركة أخرى", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        create_fiscal_year(cls.other, 2026)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="عميل الدفعة", partner_type="Customer")
        cls.cash = Account.objects.get(tenant=cls.tenant, code="1101")
        SalesSettings.objects.update_or_create(
            tenant=cls.tenant, defaults={"default_cash_account": cls.cash},
        )
        cls.invoice = SalesInvoice.objects.create(
            tenant=cls.tenant, invoice_number="BAT-INV-1", customer=cls.customer,
            currency=cls.ils, invoice_date="2026-06-11",
            status=SalesInvoice.STATUS_POSTED, grand_total=Decimal("3000.00"),
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))
        bank = Bank.objects.create(tenant=self.tenant, name="بنك فلسطين")
        ledger = Account.objects.create(
            tenant=self.tenant, code="1102-1", name="الجاري — أستاذ",
            account_type="Asset",
            parent=Account.objects.get(tenant=self.tenant, code="1102"),
        )
        self.bank_account = BankAccount.objects.create(
            tenant=self.tenant, bank=bank, name="الحساب الجاري",
            currency=self.ils, account=ledger, account_number="9911",
            is_active=True,
        )

    def _cheque(self, number, *, status="Received", amount="1000.00",
                currency=None, tenant=None):
        return Cheque.objects.create(
            tenant=tenant or self.tenant, cheque_number=number,
            amount=Decimal(amount), currency=currency or self.ils,
            partner=self.customer if tenant is None else None,
            status=status, direction="Incoming",
            sales_invoice=self.invoice if tenant is None else None,
            bank_name="بنك القاهرة عمان", due_date="2026-09-30",
        )

    def _post_batch(self, cheques, **overrides):
        body = {
            "cheque_ids": [c.pk for c in cheques],
            "bank_account": self.bank_account.pk,
            "movement_date": "2026-08-25",
            "notes": "إيداع الصباح",
        }
        body.update(overrides)
        return self.client.post(
            "/api/accounting/cheques/deposit-batch/", body, format="json")

    def test_three_cheques_deposit_together_with_one_journal_each(self):
        cheques = [self._cheque(f"BAT-{i}") for i in range(3)]

        resp = self._post_batch(cheques)

        self.assertEqual(resp.status_code, 201, resp.data)
        self.assertEqual(resp.data["deposited_count"], 3)
        for cheque in cheques:
            cheque.refresh_from_db()
            self.assertEqual(cheque.status, "Under_Collection")
            self.assertEqual(cheque.deposit_bank_account_id, self.bank_account.pk)
        self.assertEqual(
            ChequeMovement.objects.filter(
                cheque__in=cheques, movement_type="deposit").count(), 3)
        journals = JournalHeader.objects.filter(
            tenant=self.tenant, reference_type="CHEQUE_DEPOSIT")
        self.assertEqual(journals.count(), 3, "قيد لكل ورقة — لا قيد مجمَّع")

    def test_one_ineligible_cheque_leaves_the_whole_batch_untouched(self):
        """المعيار الأول: الذرّية. لا نصف دفعة."""
        good = [self._cheque(f"ATOM-{i}") for i in range(3)]
        bad = self._cheque("ATOM-BAD", status="Collected")

        resp = self._post_batch(good + [bad])

        self.assertEqual(resp.status_code, 400, resp.data)
        reasons = {r["cheque_number"]: r["reason"] for r in resp.data["rejected"]}
        self.assertIn("ATOM-BAD", reasons)
        for cheque in good:
            cheque.refresh_from_db()
            self.assertEqual(cheque.status, "Received", "أُودعت ورقة رغم رفض الدفعة")
        self.assertFalse(
            ChequeMovement.objects.filter(cheque__in=good).exists(),
            "كُتبت حركة رغم رفض الدفعة")
        self.assertFalse(
            JournalHeader.objects.filter(
                tenant=self.tenant, reference_type="CHEQUE_DEPOSIT").exists(),
            "رُحِّل قيد رغم رفض الدفعة")

    def test_a_cheque_from_another_company_is_refused(self):
        mine = self._cheque("ISO-1")
        theirs = self._cheque("ISO-2", tenant=self.other)

        resp = self._post_batch([mine, theirs])

        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertTrue(any(
            r["cheque_id"] == theirs.pk for r in resp.data["rejected"]))
        mine.refresh_from_db()
        self.assertEqual(mine.status, "Received")

    def test_two_currencies_need_two_slips(self):
        resp = self._post_batch([
            self._cheque("CUR-1"),
            self._cheque("CUR-2", currency=self.usd),
        ])
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertIn("عملة واحدة", str(resp.data["rejected"]))

    def test_batch_without_a_bank_is_refused_when_the_company_has_banks(self):
        resp = self._post_batch([self._cheque("NOBANK-1")], bank_account=None)
        self.assertEqual(resp.status_code, 400, resp.data)
        self.assertIn("الحساب البنكي", str(resp.data["rejected"]))

    def test_the_slip_carries_what_the_bank_teller_needs(self):
        cheques = [
            self._cheque("SLIP-1", amount="1200.50"),
            self._cheque("SLIP-2", amount="800.25"),
        ]

        resp = self._post_batch(cheques)

        slip = resp.data["slip"]
        self.assertEqual(Decimal(slip["total"]), Decimal("2000.75"))
        self.assertEqual(slip["bank_account"]["account_number"], "9911")
        self.assertEqual(slip["currency_code"], "ILS")
        self.assertEqual(len(slip["cheques"]), 2)
        first = slip["cheques"][0]
        for key in ("cheque_number", "drawer_bank", "partner_name",
                    "due_date", "amount"):
            self.assertIn(key, first)
        # مرجع الدفعة يبقى في ملاحظات كل حركة — القسيمة قابلة لإعادة التتبّع.
        self.assertTrue(all(
            slip["batch_ref"] in (m.notes or "")
            for m in ChequeMovement.objects.filter(cheque__in=cheques)
        ))

    def test_empty_selection_is_refused(self):
        resp = self._post_batch([], cheque_ids=[])
        self.assertEqual(resp.status_code, 400, resp.data)
