"""طبقة افتتاحية لصندوق دولار بلا طبقات — `open_fx_box_lot`.

إنتاج كترا: صندوق الدولار (108) بلا طبقات ورصيده سالب؛ بعد الأمر box_ils_value =
رصيد الحساب = الجرد × السعر، والفرق المتراكم على حساب المقابل الذي يختاره المالك.
"""
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from accounting.cashbox import get_cash_box_parent_account
from accounting.fx_fifo import account_base_balance, box_fc_balance, box_ils_value, fund_box_from_capital
from accounting.models import Account, CashBoxFxLot, CashBoxLedgerAccount, JournalHeader
from accounting.services import create_fiscal_year, post_journal
from tenants.models import Currency
from tenants.services import create_company

D = lambda v: Decimal(str(v))


class OpenFxBoxLotTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="open-fx", password="x", email="of@x.co")
        Currency.objects.create(Code="ILS", Name="شيكل", IsBaseCurrency=True)
        Currency.objects.create(Code="USD", Name="دولار", IsBaseCurrency=False)
        cls.tenant = create_company("شركة الافتتاح", cls.user)
        create_fiscal_year(cls.tenant, 2026)
        parent = get_cash_box_parent_account(cls.tenant)
        cls.usd_acc = Account.objects.create(tenant=cls.tenant, code="108X", name="صندوق الدولار",
                                             parent=parent, account_type="Asset", is_active=True)
        cls.box = CashBoxLedgerAccount.objects.create(
            tenant=cls.tenant, external_id="usd1", name="صندوق الدولار",
            currency_code="USD", account=cls.usd_acc)
        cls.offset = Account.objects.create(tenant=cls.tenant, code="3999", name="فروق افتتاح الصندوق",
                                            account_type="Equity", is_active=True)
        cls.ap = Account.objects.create(tenant=cls.tenant, code="AP-OF", name="ذمم",
                                        account_type="Liability", is_active=True)

    def setUp(self):
        # دفعةٌ خرجت من الصندوق ولم يُسجَّل تمويله ⇒ رصيده سالب.
        post_journal(
            tenant_id=self.tenant.pk, transaction_date="2026-06-10", reference_type="LOGISTICS_PAYMENT",
            reference_id=1, description="قديم", idempotent=False,
            lines_data=[
                {"account": self.ap.pk, "debit": D(5000), "credit": D(0), "description": "قديم"},
                {"account": self.usd_acc.pk, "debit": D(0), "credit": D(5000), "description": "قديم"},
            ])

    def _run(self, *args, date="2026-10-07"):
        out = StringIO()
        call_command("open_fx_box_lot", "--tenant", str(self.tenant.pk), "--box-account", "108X",
                     "--fc", "1200", "--rate", "3.6", "--date", date, "--offset-account", "3999",
                     *args, stdout=out)
        return out.getvalue()

    def test_report_writes_nothing(self):
        before = JournalHeader.objects.count()
        out = self._run()
        self.assertIn("-5000.00", out)
        self.assertIn("4320.00", out)
        self.assertEqual(JournalHeader.objects.count(), before)
        self.assertFalse(CashBoxFxLot.objects.exists())

    def test_apply_makes_box_value_equal_account_balance(self):
        self._run("--apply")
        self.assertEqual(box_fc_balance(self.box), D("1200"))
        self.assertEqual(box_ils_value(self.box), D("4320.00"))
        self.assertEqual(account_base_balance(self.usd_acc.pk), D("4320.00"))
        self.assertEqual(account_base_balance(self.offset.pk), D("-9320.00"))  # 5000 + 4320
        lot = CashBoxFxLot.objects.get()
        self.assertEqual(lot.source, CashBoxFxLot.SOURCE_OPENING)
        self.assertTrue(JournalHeader.objects.filter(reference_type="FX_BOX_OPENING_ADJUST").exists())

    def test_box_that_already_has_lots_is_refused(self):
        fund_box_from_capital(self.box, 10, 3, date="2026-06-20", user=self.user)
        before = JournalHeader.objects.count()
        with self.assertRaisesMessage(CommandError, "طبقات"):
            self._run("--apply")
        self.assertEqual(JournalHeader.objects.count(), before)

    def test_date_before_the_last_box_movement_is_refused(self):
        with self.assertRaisesMessage(CommandError, "بعد"):
            self._run("--apply", date="2026-06-01")
        self.assertFalse(CashBoxFxLot.objects.exists())

    def test_later_entry_and_its_reversal_do_not_block(self):
        # إنتاج كترا: الدفعة 190 — قيدها وعكسه بتاريخ 2026-12-03 على الصندوق، صافيهما صفر.
        for debit, credit in ((D(0), D(700)), (D(700), D(0))):
            post_journal(
                tenant_id=self.tenant.pk, transaction_date="2026-12-03",
                reference_type="LOGISTICS_PAYMENT", reference_id=2, description="لاحق",
                idempotent=False,
                lines_data=[
                    {"account": self.ap.pk, "debit": credit, "credit": debit, "description": "x"},
                    {"account": self.usd_acc.pk, "debit": debit, "credit": credit, "description": "x"},
                ])
        self._run("--apply")
        self.assertEqual(account_base_balance(self.usd_acc.pk), D("4320.00"))
