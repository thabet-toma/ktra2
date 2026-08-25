"""CHQ-4 — بنك الإيداع: «أودعتُه أين؟» سؤالٌ لا جواب له في الدفاتر.

قيد الإيداع 1107 ÷ 1109 بحسابين ثابتين (حسابٌ واحد للشيكات برسم التحصيل بقرار
المالك — نهج Odoo بلا تضخيم شجرة الحسابات). فلو لم يُسجَّل البنك على الورقة
لضاعت الحقيقة التشغيلية كلها: لا يُعرف أين الشيك، ولا يُقترح بنك التحصيل
لاحقاً، ولا تُطبع قسيمة إيداع.

هنا: الإلزام مشروط بامتلاك الشركة بنوكاً نشطة، والقيد لا يتغيّر.
"""
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from rest_framework.test import APITestCase

from accounting.models import (
    Account, Bank, BankAccount, Cheque, JournalHeader,
)
from accounting.services import create_fiscal_year, transfer_cheque
from partners.models import Partner
from sales.models import SalesInvoice, SalesSettings
from tenants.models import Currency
from tenants.services import create_company


class ChequeDepositBankTest(APITestCase):

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="chq_bank", password="x")
        cls.ils = Currency.objects.create(
            Code="ILS", Name="شيكل", IsBaseCurrency=True)
        cls.tenant = create_company("شركة بنك الإيداع", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        cls.customer = Partner.objects.create(
            tenant=cls.tenant, name="عميل الإيداع", partner_type="Customer")
        cls.cash = Account.objects.get(tenant=cls.tenant, code="1101")
        SalesSettings.objects.update_or_create(
            tenant=cls.tenant, defaults={"default_cash_account": cls.cash},
        )
        cls.invoice = SalesInvoice.objects.create(
            tenant=cls.tenant, invoice_number="BNK-INV-1", customer=cls.customer,
            currency=cls.ils, invoice_date="2026-06-11",
            status=SalesInvoice.STATUS_POSTED, grand_total=Decimal("900.00"),
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.client.credentials(HTTP_X_TENANT_ID=str(self.tenant.TenantID))

    def _bank_account(self, name="الحساب الجاري"):
        bank = Bank.objects.create(tenant=self.tenant, name="بنك فلسطين")
        ledger = Account.objects.create(
            tenant=self.tenant, code=f"1102-{BankAccount.objects.count() + 1}",
            name=f"{name} — أستاذ", account_type="Asset",
            parent=Account.objects.get(tenant=self.tenant, code="1102"),
        )
        return BankAccount.objects.create(
            tenant=self.tenant, bank=bank, name=name, currency=self.ils,
            account=ledger, account_number="9911", is_active=True,
        )

    def _received_cheque(self, number="BNK-1"):
        return Cheque.objects.create(
            tenant=self.tenant, cheque_number=number, amount=Decimal("900.00"),
            currency=self.ils, partner=self.customer, status="Received",
            direction="Incoming", sales_invoice=self.invoice,
            bank_name="بنك القاهرة عمان", due_date="2026-09-30",
        )

    def test_deposit_without_a_bank_is_refused_when_the_company_has_banks(self):
        self._bank_account()
        cheque = self._received_cheque()
        with self.assertRaises(ValidationError) as ctx:
            transfer_cheque(cheque.pk, "deposit", user=self.user)
        self.assertIn("الحساب البنكي", str(ctx.exception))
        cheque.refresh_from_db()
        self.assertEqual(cheque.status, "Received", "الحالة تغيّرت رغم الرفض")

    def test_deposit_records_the_bank_but_keeps_the_journal_on_1107_over_1109(self):
        ba = self._bank_account()
        cheque = self._received_cheque("BNK-2")

        transfer_cheque(cheque.pk, "deposit", user=self.user, bank_account_id=ba.pk)

        cheque.refresh_from_db()
        self.assertEqual(cheque.status, "Under_Collection")
        self.assertEqual(cheque.deposit_bank_account_id, ba.pk)

        journal = JournalHeader.objects.get(
            tenant=self.tenant, reference_type="CHEQUE_DEPOSIT")
        accounts = {line.account.code: line for line in journal.lines.all()}
        self.assertEqual(set(accounts), {"1107", "1109"},
                         "قيد الإيداع خرج عن 1107 ÷ 1109")
        self.assertEqual(Decimal(str(accounts["1107"].debit)), Decimal("900.00"))
        self.assertEqual(Decimal(str(accounts["1109"].credit)), Decimal("900.00"))
        # حساب البنك في الشجرة لا يدخل قيد الإيداع — الورقة لم تصر نقداً بعد.
        self.assertNotIn(ba.account.code, accounts)

    def test_company_without_banks_still_deposits_on_paper(self):
        """شركة لم تسجّل بنوكها: الإلزام حقلٌ بلا خيارات — فلا يُلزَم."""
        self.assertFalse(BankAccount.objects.filter(tenant=self.tenant).exists())
        cheque = self._received_cheque("BNK-3")

        transfer_cheque(cheque.pk, "deposit", user=self.user)

        cheque.refresh_from_db()
        self.assertEqual(cheque.status, "Under_Collection")
        self.assertIsNone(cheque.deposit_bank_account_id)

    def test_the_option_announces_the_requirement_before_the_user_submits(self):
        """الشاشة تعرف أن البنك مطلوب من الخادم — لا تكتشفه من رسالة 400."""
        cheque = self._received_cheque("BNK-4")

        resp = self.client.get("/api/accounting/cheques/")
        rows = resp.data["results"] if isinstance(resp.data, dict) else resp.data
        row = next(r for r in rows if r["id"] == cheque.id)
        deposit = next(m for m in row["allowed_movements"] if m["value"] == "deposit")
        self.assertFalse(deposit["requires_bank_account"],
                         "أُلزم البنك على شركة بلا بنوك")

        self._bank_account()
        resp = self.client.get("/api/accounting/cheques/")
        rows = resp.data["results"] if isinstance(resp.data, dict) else resp.data
        row = next(r for r in rows if r["id"] == cheque.id)
        deposit = next(m for m in row["allowed_movements"] if m["value"] == "deposit")
        self.assertTrue(deposit["requires_bank_account"])
